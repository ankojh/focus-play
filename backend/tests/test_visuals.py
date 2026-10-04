"""Local deterministic renderer/asset tests; no live acquisition or execution."""
import io
import json
from pathlib import Path
import sys
import threading

import pytest
from PIL import Image
from pydantic import ValidationError
from fastapi.testclient import TestClient
from app.assets import Assets, MAX_BYTES
from app.config import Settings
from app.contracts import ModelStoryboard, Short, TranscriptSegment
from app.errors import AppError, Cancelled
from app.main import create_app
from app.store import Store
from app.validation import attach_evidence, validate_draft
from app.storyboard import compile_storyboard
from test_core import StubModel, StubSpeech, StubYouTube
from test_providers import scripted_model, chunk
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from export_visual_fixture import compile_fixture, SEGMENTS

@pytest.fixture
def assets(tmp_path):
    store=Store(Settings(data=tmp_path).data)
    service=Assets(store);service.install_bundled()
    yield service
    store.close()


def test_all_renderers_roundtrip_measured_timeline_and_saved_offline_assets(assets):
    fixture=compile_fixture(assets)
    assert [s['kind'] for s in fixture['shorts'][0]['scenes']]==['diagram','table','chart']
    assert [s['start_ms'] for s in fixture['shorts'][0]['scenes']]==[0,10000,20000]
    assert fixture['shorts'][1]['scenes'][0]['kind']=='code'
    image=Short.model_validate(fixture['shorts'][2])
    for body in fixture['shorts']:Short.model_validate_json(json.dumps(body))
    assets.reference(image.scenes,'saved_lesson',image.id)
    assert assets.store.db.execute('SELECT COUNT(*) FROM asset_refs').fetchone()[0]==1
    reopened=Assets(assets.store)
    assert reopened.attach(image.scenes[0].payload.asset_id).status=='ready'


def test_committed_fixture_matches_compiler(assets):
    actual=compile_fixture(assets)
    for s in actual['shorts']:
        for scene in s['scenes']:
            if scene['kind']=='image':scene['asset']['acquired_at']=0
    assert actual==json.loads((ROOT/'fixtures/mixed-visuals.json').read_text())


@pytest.mark.parametrize('change',[
    lambda d:d['scenes'][1].update(kind='html'),
    lambda d:d['scenes'][1]['payload'].update(rows=[]),
    lambda d:d['scenes'][1]['payload']['rows'][0].update(cells=['wrong width']),
    lambda d:d['scenes'][1]['payload']['rows'][1].update(id='row_0'),
    lambda d:d['narration_units'][1]['operations'][2].update(target='row_8_c4'),
    lambda d:d['narration_units'][1]['operations'][2].update(kind='move',to_slot=2),
    lambda d:d['narration_units'][1]['operations'][2].update(kind='hide'),
    lambda d:d['scenes'][2]['payload'].update(points=[]),
    lambda d:d['scenes'][2]['payload'].update(scale_policy='log'),
    lambda d:d['scenes'][2]['payload']['points'][0].update(value=float('nan')),
    lambda d:d['scenes'][2]['payload']['points'][0].update(value=float('inf')),
    lambda d:d['scenes'][2]['payload']['points'][0].update(value=1e13),
    lambda d:d['scenes'][2]['payload']['points'][1].update(id='point_0'),
])
def test_reject_malformed_discriminated_payloads_and_illegal_operations(assets,change):
    body=compile_fixture(assets)['drafts'][0]
    change(body)
    with pytest.raises((ValueError,ValidationError)):
        content=ModelStoryboard.model_validate(body)
        attach_evidence(content,[TranscriptSegment.model_validate(s) for s in SEGMENTS])


@pytest.mark.parametrize('change',[
    lambda d:d['scenes'][2]['payload']['points'][0].update(value=-13),
    lambda d:d['scenes'][2]['payload']['points'][0].update(segment_id='seg_lookup'),
    lambda d:d['scenes'][2]['payload'].update(unit='milliseconds'),
])
def test_chart_requires_signed_numbers_and_units_in_own_cited_passage(assets,change):
    body=compile_fixture(assets)['drafts'][0];change(body)
    segments=[TranscriptSegment.model_validate(s) for s in SEGMENTS]
    with pytest.raises(ValueError):validate_draft(attach_evidence(ModelStoryboard.model_validate(body),segments),segments,False)


@pytest.mark.parametrize('text', ['print(1)', 'a\n'*30, 'x'*201, '<script>alert(1)</script>'])
def test_code_is_bounded_and_exact_source_display_only(assets,text):
    body=compile_fixture(assets)['drafts'][1];body['scenes'][0]['payload']['text']=text
    segments=[TranscriptSegment.model_validate(s) for s in SEGMENTS]
    with pytest.raises(ValueError):validate_draft(attach_evidence(ModelStoryboard.model_validate(body),segments),segments,False)


@pytest.mark.parametrize('change',[
    lambda s:s.update(kind='footage'),
    lambda s:s['payload'].update(asset_id='../../etc/passwd'),
    lambda s:s['payload']['annotations'][0].update(x=1.01),
    lambda s:s['payload']['annotations'][0].update(y=float('nan')),
    lambda s:s['payload']['annotations'][0].update(id='image'),
    lambda s:s['payload'].update(width=1),
    lambda s:s['asset'].update(status='missing'),
    lambda s:s['asset'].update(permission_basis=''),
    lambda s:s['asset'].update(managed_filename='../image.png'),
    lambda s:s['actions'][1].update(kind='draw'),
])
def test_image_contract_rejects_unmanaged_or_unusable_assets(assets,change):
    body=compile_fixture(assets)['shorts'][2];change(body['scenes'][0])
    with pytest.raises(ValueError):Short.model_validate(body)


def test_mutated_payload_is_revalidated_before_compilation(assets):
    body=compile_fixture(assets)['drafts'][0]
    draft=attach_evidence(ModelStoryboard.model_validate(body),[TranscriptSegment.model_validate(s) for s in SEGMENTS])
    for i,unit in enumerate(draft.narration_units):unit.start_ms,unit.end_ms=i*10000,(i+1)*10000
    draft.scenes[2].payload.points[0].value=float('nan')
    with pytest.raises(ValueError):compile_storyboard(draft,30000,assets)


def test_new_chart_drafts_cannot_use_legacy_diagram_mini_bars(assets):
    body=compile_fixture(assets)['drafts'][0];body['scenes'][0]['template']='chart'
    segments=[TranscriptSegment.model_validate(s) for s in SEGMENTS]
    with pytest.raises(ValueError,match='legacy diagram bars'):
        validate_draft(attach_evidence(ModelStoryboard.model_validate(body),segments),segments,False)
    legacy=json.loads((ROOT/'fixtures/storyboard-lookup-playback.json').read_text())
    legacy['scenes'][0]['template']='chart'
    assert Short.model_validate(legacy).scenes[0].template=='chart'


def test_legacy_diagram_without_kind_still_loads():
    body=json.loads((ROOT/'fixtures/storyboard-lookup-playback.json').read_text())
    body['storyboard_version']=1
    for scene in body['scenes']:scene.pop('kind')
    assert all(s.kind=='diagram' for s in Short.model_validate(body).scenes)


def raster(size=(10,10),format='PNG'):
    out=io.BytesIO();Image.new('RGB',size,'blue').save(out,format=format);return out.getvalue()


def rights(**changes):
    return dict(kind='image',original_source='bundled:test',creator='Fixture author',permission_basis='Original CC0 test fixture',attribution='Fixture author · CC0',source_context='Original diagnostic raster fixture',illustrative=True,**changes)


@pytest.mark.parametrize('data', [b'<svg onload="alert(1)"></svg>',b'<html>bad</html>',b'GIF89a',b'not PNG',b'x'*(MAX_BYTES+1)])
def test_reject_non_raster_and_oversized_content(assets,data):
    with pytest.raises(ValueError):assets.register_bytes(data,**rights())


def test_raster_header_is_verified_and_metadata_and_appended_scripts_stripped(assets):
    dirty=raster()+b'<script>alert(1)</script>'
    record=assets.register_bytes(dirty,**rights())
    clean,_=assets.read(record.id)
    assert b'<script>' not in clean
    assert record.mime_type=='image/png'
    assert assets.register_bytes(dirty,**rights()).id==record.id
    assert len(list(assets.root.glob(record.id+'*')))==1
    assert not list(assets.root.glob('*.tmp'))
    with pytest.raises(ValueError):assets.register_bytes(raster()[:-20],**rights())


def test_dimensions_pixels_rights_and_animated_images_are_bounded(assets):
    for size in [(4097,1),(3000,3000)]:
        with pytest.raises(ValueError):assets.register_bytes(raster(size),**rights())
    metadata=rights();metadata['permission_basis']=''
    with pytest.raises(ValueError):assets.register_bytes(raster(),**metadata)
    out=io.BytesIO();Image.new('RGB',(10,10),'red').save(out,format='PNG',save_all=True,append_images=[Image.new('RGB',(10,10),'blue')],duration=100,loop=0)
    with pytest.raises(ValueError):assets.register_bytes(out.getvalue(),**rights())


def test_decompression_bomb_header_is_rejected_without_decoding(assets):
    import struct
    import zlib
    data=bytearray(raster());data[16:24]=struct.pack('>II',50000,50000)
    data[29:33]=struct.pack('>I',zlib.crc32(data[12:29]) & 0xffffffff)
    with pytest.raises(ValueError):assets.register_bytes(bytes(data),**rights())


def test_actual_jpeg_encoding_becomes_safe_canonical_png(assets):
    metadata=rights();metadata['kind']='screenshot';metadata['source_context']='Original fixture software version 1, captured for diagnostics only.'
    record=assets.register_bytes(raster(format='JPEG'),**metadata)
    data,_=assets.read(record.id)
    assert record.kind=='screenshot' and record.mime_type=='image/png'
    assert data.startswith(b'\x89PNG\r\n\x1a\n')


def test_cancellation_during_atomic_write_removes_temp_and_does_not_publish(assets):
    class CancelAtWrite:
        calls=0
        def is_set(self):
            self.calls+=1
            return self.calls>=4
    before=assets.store.db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
    with pytest.raises(Cancelled):assets.register_bytes(raster(),cancel=CancelAtWrite(),**rights())
    assert not list(assets.root.glob('*.tmp'))
    assert assets.store.db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]==before
    assert assets.register_bytes(raster(),**rights()).status=='ready'


def test_missing_corrupt_symlink_files_fail_closed_and_bundled_retry_repairs(assets,tmp_path):
    record=assets.candidates()[0];path=assets.root/(record['id']+'.png')
    path.unlink()
    with pytest.raises(AppError):assets.attach(record['id'])
    assert assets.get(record['id']).status=='missing'
    assets.install_bundled();assert assets.attach(record['id']).status=='ready'
    path.write_bytes(b'corrupt')
    with pytest.raises(AppError):assets.read(record['id'])
    path.unlink();outside=tmp_path/'outside.png';outside.write_bytes(raster());path.symlink_to(outside)
    with pytest.raises(AppError):assets.read(record['id'])
    with pytest.raises(ValueError):assets.install_bundled()


def test_root_symlink_and_traversal_rejected(assets,tmp_path):
    for value in ['../secret','https://127.0.0.1/private','file:///etc/passwd','a'*63]:
        with pytest.raises(AppError):assets.read(value)
    record=assets.candidates()[0];moved=tmp_path/'moved';assets.root.rename(moved);assets.root.symlink_to(moved,target_is_directory=True)
    with pytest.raises(AppError):assets.read(record['id'])
    with pytest.raises(ValueError):Assets(assets.store)


def test_cancel_has_no_partial_file_or_record_then_retry_succeeds(assets):
    cancel=threading.Event();cancel.set()
    before=assets.store.db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]
    with pytest.raises(Cancelled):assets.register_bytes(raster(),cancel=cancel,**rights())
    assert assets.store.db.execute('SELECT COUNT(*) FROM assets').fetchone()[0]==before
    assert not list(assets.root.glob('*.tmp'))
    cancel.clear();assert assets.register_bytes(raster(),cancel=cancel,**rights()).status=='ready'


def test_provider_schema_selects_only_existing_assets_and_evidence(scripted_model,assets):
    model, streams, calls, _ = scripted_model
    fixture=compile_fixture(assets)
    task={'segments':SEGMENTS,'question_required':False,'asset_candidates':assets.candidates()}
    streams.append([chunk(json.dumps(fixture['drafts'][2]))])
    model.generate(ModelStoryboard,task,threading.Event())
    schema=calls[0]['format']
    assert schema['$defs']['ImagePayload']['properties']['asset_id']['enum']==[assets.candidates()[0]['id']]
    assert schema['$defs']['CodePayload']['properties']['segment_id']['enum']==[s['id'] for s in SEGMENTS]
    assert 'chart' not in schema['$defs']['StoryboardScene']['properties']['template']['enum']
    assert 'line_30' in schema['$defs']['SemanticOperation']['properties']['target']['enum']
    assert 'row_7_c3' in schema['$defs']['SemanticOperation']['properties']['target']['enum']
    streams.append([chunk(json.dumps(fixture['drafts'][1]))])
    model.generate(ModelStoryboard,{**task,'asset_candidates':[]},threading.Event())
    assert all(branch['$ref']!='#/$defs/ImageVisual' for branch in calls[-1]['format']['properties']['scenes']['items']['oneOf'])


def test_provider_rejects_unapproved_asset_id_with_bounded_repairs(scripted_model,assets):
    model,streams,calls,_=scripted_model
    body=compile_fixture(assets)['drafts'][2]
    body['scenes'][0]['payload']['asset_id']='f'*64
    streams.extend([[chunk(json.dumps(body))]]*3)
    with pytest.raises(AppError):model.generate(ModelStoryboard,{'segments':SEGMENTS,'question_required':False,'asset_candidates':assets.candidates()},threading.Event())
    assert len(calls)==3


def test_asset_registration_is_network_free(assets,monkeypatch):
    import socket
    def blocked(*args,**kwargs):raise AssertionError('Local assets must not open a network connection.')
    monkeypatch.setattr(socket,'create_connection',blocked)
    assets.install_bundled()
    assert assets.register_bytes(raster(),**rights()).status=='ready'


def test_asset_routes_remain_local_only_and_no_remote_acquisition_api(tmp_path):
    settings=Settings(data=tmp_path)
    app=create_app(settings,StubModel(),StubSpeech(settings),StubYouTube())
    with TestClient(app) as client:
        record=app.state.jobs.assets.candidates()[0]
        response=client.get('/api/assets/'+record['id'])
        assert response.status_code==200 and response.headers['content-type']=='image/png'
        assert response.headers['x-content-type-options']=='nosniff'
        assert client.get('/api/assets/'+record['id']+'/metadata').json()['attribution']
        assert client.get('/api/assets/'+record['id'],headers={'Origin':'https://evil.test'}).status_code==403
        assert client.get('/api/assets/'+record['id'],headers={'Host':'evil.test'}).status_code==403
        assert client.get('/api/assets/https:%2F%2F127.0.0.1/private').status_code==404
        assert client.post('/api/assets/import',json={'url':'http://169.254.169.254/'}).status_code in {404,405}
        assert client.get('/api/assets/'+'f'*64).status_code==404
