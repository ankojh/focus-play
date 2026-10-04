"""Diagnostic fixtures compiled through production contracts, never live quality claims.
All text/data below are original illustrative test content, not observations.
"""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.contracts import ModelStoryboard, Short, TranscriptSegment
from app.config import Settings
from app.store import Store
from app.assets import Assets
from app.storyboard import COMPILER_VERSION, compile_storyboard
from app.validation import attach_evidence, validate_draft

SEGMENTS = [
    dict(id='seg_lookup', source_id='src_visual', text='A key maps to a row. The illustrative table lists key A with row Alpha and key B with row Beta. These names illustrate lookup, not a measured dataset.'),
    dict(id='seg_chart', source_id='src_visual', text='The illustrative data are negative -12 units, zero 0 units and large 1500 units. These synthetic values test a zero-inclusive linear scale, not a benchmark or measurements.'),
    dict(id='seg_code', source_id='src_visual', text='The source snippet is displayed as text, never executed: SELECT name\nFROM customers;\nThe SELECT clause names the field and FROM names the table. This is an original display-only fixture.'),
]

def authored(asset_id):
    diagram = dict(id='scene_0',kind='diagram',summary='Trace the key to a row',template='process',nodes=[
        dict(id='node_0',label='Search key',detail='Selects the matching row',slot=0,icon='key',role='start'),
        dict(id='node_1',label='Table row',detail='Contains the matching data',slot=1,icon='table',role='result')],connections=[dict(id='conn_0',source='node_0',target='node_1')],states=[])
    table = dict(id='scene_1',kind='table',summary='Look up the same key in a table',payload=dict(columns=['Key','Row'],rows=[dict(id='row_0',cells=['A','Alpha']),dict(id='row_1',cells=['B','Beta'])],illustrative=True))
    chart = dict(id='scene_2',kind='chart',summary='Compare signed source values on one scale',payload=dict(chart_kind='bar',unit='units',axis_label='Illustrative value',scale_policy='zero_inclusive',illustrative=True,points=[dict(id=f'point_{i}',label=label,value=v,segment_id='seg_chart') for i,(label,v) in enumerate([('Negative',-12),('Zero',0),('Large',1500)])]))
    code = dict(id='scene_0',kind='code',summary='Read a display-only source snippet',payload=dict(language='sql',text='SELECT name\nFROM customers;',segment_id='seg_code'))
    image = dict(id='scene_0',kind='image',summary='A managed illustration of key-to-row lookup',payload=dict(asset_id=asset_id,width=640,height=400,alt='Illustrative key card pointing to a table row',caption='Key-to-row schematic, not a software screenshot.',annotations=[dict(id='annotation_0',x=.75,y=.6,label='Matching row',segment_id='seg_lookup')]))
    def op(kind,target):return dict(kind=kind,target=target)
    def beat(i,scene,text,sid,operations):return dict(beat_id=f'beat_{i}',scene_id=scene,purpose='Explain the supported visible mechanism',text=text,segment_id=sid,operations=operations)
    def draft(scenes,beats):return dict(storyboard_version=2,objective='Explain a bounded source-supported visual',prerequisites=[],scenes=scenes,narration_units=beats,question=None)
    mixed=draft([diagram,table,chart],[
        beat(0,'scene_0','A key identifies a matching row. Follow the connection from the search key to the row that contains the data.','seg_lookup',[op('reveal','node_0'),op('reveal','node_1'),op('connect','conn_0')]),
        beat(1,'scene_1','The illustrative table uses the same lookup idea: key A maps to Alpha, while key B maps to Beta.','seg_lookup',[op('reveal','row_0'),op('reveal','row_1'),op('focus','row_0_c1')]),
        beat(2,'scene_2','These synthetic values test the scale rather than performance. Negative and positive values extend from a shared zero baseline.','seg_chart',[op('reveal','point_0'),op('reveal','point_1'),op('reveal','point_2'),op('focus','point_0')])])
    coding=draft([code],[
        beat(0,'scene_0','Read this source snippet as text only. The SELECT clause identifies the field that the source example requests from the table.','seg_code',[op('reveal','line_1'),op('focus','line_1')]),
        beat(1,'scene_0','The FROM clause identifies the table used by the source example. This player displays the code without executing either line.','seg_code',[op('reveal','line_2'),op('focus','line_2')])])
    imaging=draft([image],[
        beat(0,'scene_0','This illustration shows a key pointing to a row. It is a schematic of lookup, not a product screenshot or a benchmark.','seg_lookup',[op('reveal','image')]),
        beat(1,'scene_0','The annotation identifies the matching row. The image permission allows display, but factual teaching claims still need the separate supporting passage.','seg_lookup',[op('reveal','annotation_0'),op('focus','annotation_0')])])
    return [mixed,coding,imaging]


def compile_fixture(assets):
    segments=[TranscriptSegment.model_validate(s) for s in SEGMENTS]
    asset_id=assets.candidates()[0]['id']
    drafts=authored(asset_id)
    shorts=[]
    for i,body in enumerate(drafts):
        draft=attach_evidence(ModelStoryboard.model_validate(body),segments)
        validate_draft(draft,segments,False)
        length=len(draft.narration_units)
        for j,b in enumerate(draft.narration_units):b.start_ms,b.end_ms=j*30000//length,(j+1)*30000//length
        scenes,units=compile_storyboard(draft,30000,assets)
        shorts.append(Short(id=f'visual_{i}',objective=draft.objective,status='ready',storyboard_version=2,timeline_compiler_version=COMPILER_VERSION,scenes=scenes,narration_units=units,measured_duration_ms=30000,audio_path='a'*64+'.wav',evidence_references=[u.evidence for u in units]))
    return dict(notice='Original illustrative diagnostic fixtures. Synthetic data, no live provider or human quality review.',segments=SEGMENTS,drafts=drafts,shorts=[s.model_dump() for s in shorts])

if __name__=='__main__':
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        store=Store(Settings(data=Path(directory)).data)
        assets=Assets(store);assets.install_bundled()
        fixture=compile_fixture(assets)
        # Stable acquisition time for reproducible browser diagnostics only.
        for short in fixture['shorts']:
            for scene in short['scenes']:
                if scene['kind']=='image':scene['asset']['acquired_at']=0
        path=ROOT/'fixtures/mixed-visuals.json';path.write_text(json.dumps(fixture,indent=2)+'\n')
        store.close();print(path)
