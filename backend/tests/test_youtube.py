import json
import threading
import time
from types import SimpleNamespace
import pytest
from fastapi.testclient import TestClient
from app.config import Settings
from app.contracts import Lesson, SavedLearningRequest, Job, Short, Objective, LessonPlan
from app.errors import AppError
from app.main import create_app
from app.youtube import source_from_transcript, require_youtube
from test_core import StubModel, StubSpeech, StubYouTube, source, request_for, wait_for


class Candidates(StubYouTube):
    def search(self,query):
        self.searches.append(query)
        offset=(len(self.searches)-1)*6
        return [{"video_id":f"video{i:06d}","title":"Synthetic test video","channel":"Test channel"} for i in range(offset,offset+6)]


def test_new_lesson_automatically_searches_and_all_content_has_youtube_evidence(tmp_path):
    settings=Settings(data=tmp_path);provider=StubYouTube();model=StubModel(.02)
    app=create_app(settings,model,StubSpeech(settings),provider)
    with TestClient(app) as client:
        assert client.get('/api/sources').json()['sources']==[]
        request={**request_for(None),"prior_knowledge":"I know SQL"}
        accepted=client.post('/api/lessons',json=request)
        assert accepted.status_code==202
        lid=accepted.json()['id']
        ready=wait_for(client,lid)
        assert provider.searches and 'SQL' in provider.searches[0]
        assert all(s['source_type']=='youtube' and s['video_id'] and s['channel'] for s in ready['sources'])
        source_ids={s['id'] for s in ready['sources']}
        for short in ready['shorts']:
            assert all(ref['source_id'] in source_ids for ref in short['evidence_references'])
            if short['question']:
                assert short['question']['evidence']['source_id'] in source_ids
        stages=[body['stage'] for _,body in app.state.store.events(lid,0)]
        assert 'Searching YouTube' in stages and 'Reading video transcripts' in stages
        assert client.post('/api/lessons',json=request).json()['id']==lid
        assert len(provider.searches)==1


@pytest.mark.parametrize('legacy',[{'source_mode':'import'},{'source_mode':'youtube'},{'source_ids':['sample']},{'source_ids':[]}])
def test_direct_requests_cannot_select_a_manual_source_path(tmp_path,legacy):
    settings=Settings(data=tmp_path);provider=StubYouTube()
    with TestClient(create_app(settings,StubModel(),StubSpeech(settings),provider)) as client:
        assert client.post('/api/lessons',json={**request_for(None),**legacy}).status_code==422
        assert client.post('/api/sources/import',json={'title':'Source','text':'An index maps keys to rows.'}).status_code==404
        assert provider.searches==[]


@pytest.mark.parametrize('code',['YOUTUBE_KEY_MISSING','YOUTUBE_QUOTA_OR_ACCESS','SOURCE_NETWORK_FAILED','TRANSCRIPT_ACCESS_REQUIRED'])
def test_source_access_errors_fail_without_using_the_model_or_sample(tmp_path,code):
    class Failure(StubYouTube):
        def search(self,query):
            if code!='TRANSCRIPT_ACCESS_REQUIRED':raise AppError(code,'Check source access, then retry.',503)
            return super().search(query)
        def transcript(self,*args):raise AppError(code,'Check transcript access, then retry.',503)
    settings=Settings(data=tmp_path);model=StubModel()
    with TestClient(create_app(settings,model,StubSpeech(settings),Failure())) as client:
        lid=client.post('/api/lessons',json=request_for(None)).json()['id']
        failed=wait_for(client,lid,'failed')
        assert failed['job']['error']['code']==code and failed['sources']==[] and failed['shorts']==[]
        assert model.calls==0


def test_unavailable_captions_try_other_videos_with_bounded_limits(tmp_path):
    class Missing(Candidates):
        def transcript(self,candidate,cancel):
            self.fetches.append(candidate['video_id'])
            raise AppError('TRANSCRIPT_UNAVAILABLE','No captions.')
    settings=Settings(data=tmp_path);provider=Missing();model=StubModel()
    with TestClient(create_app(settings,model,StubSpeech(settings),provider)) as client:
        lid=client.post('/api/lessons',json=request_for(None)).json()['id']
        failed=wait_for(client,lid,'failed')
        assert failed['job']['error']['code']=='NO_USABLE_TRANSCRIPTS'
        assert len(provider.searches)==2 and len(provider.fetches)==8 and model.calls==0
        assert client.post(f'/api/lessons/{lid}/retry',json={}).status_code==202
        wait_for(client,lid,'failed')
        assert len(provider.fetches)==16


def test_insufficient_plan_searches_again_before_generating(tmp_path):
    class MoreEvidence(StubModel):
        def generate(self,contract,task,cancel,validate=None):
            if contract is LessonPlan and len({s['source_id'] for s in task['segments']})<3:
                return LessonPlan(sufficient_evidence=False,reason='More evidence is needed.',objectives=[])
            return super().generate(contract,task,cancel,validate)
    settings=Settings(data=tmp_path);provider=Candidates()
    with TestClient(create_app(settings,MoreEvidence(),StubSpeech(settings),provider)) as client:
        lid=client.post('/api/lessons',json=request_for(None)).json()['id']
        ready=wait_for(client,lid)
        assert len(provider.searches)==2 and len(ready['sources'])==4


def test_extra_short_searches_again_when_existing_evidence_is_insufficient(tmp_path):
    class ExtraEvidence(StubModel):
        def generate(self,contract,task,cancel,validate=None):
            if contract is LessonPlan and 'objective' in task and len({s['source_id'] for s in task['segments']})<3:
                return LessonPlan(sufficient_evidence=False,reason='An example needs more evidence.',objectives=[])
            return super().generate(contract,task,cancel,validate)
    settings=Settings(data=tmp_path);provider=Candidates()
    with TestClient(create_app(settings,ExtraEvidence(),StubSpeech(settings),provider)) as client:
        lid=client.post('/api/lessons',json=request_for(None)).json()['id'];ready=wait_for(client,lid)
        response=client.post(f"/api/lessons/{lid}/shorts/{ready['short_ids'][0]}/explanations",json={'kind':'example','request_id':'new-extra-request'})
        assert response.status_code==202
        final=wait_for(client,lid)
        assert len(provider.searches)==2 and len(final['shorts'])==4
        assert final['shorts'][1]['optional'] and final['shorts'][1]['evidence_references']
        assert all(s['source_type']=='youtube' for s in final['sources'])


def test_saved_manual_lesson_remains_unchanged_and_new_extra_uses_youtube(tmp_path):
    settings=Settings(data=tmp_path);app=create_app(settings,StubModel(),StubSpeech(settings),StubYouTube())
    old=source();request=SavedLearningRequest(**request_for(None),source_mode='import',source_ids=[old.id])
    ready=Short(id='saved_short',objective='Understand database indexes',status='ready',measured_duration_ms=2000)
    lesson=Lesson(id='saved_lesson',request=request,sources=[old],shorts=[ready],short_ids=[ready.id],objectives=[Objective(title=ready.objective,template='process',prerequisites=[])],job=Job(id='saved_job',lesson_id='saved_lesson',status='complete',created_at=time.time(),updated_at=time.time()))
    app.state.store.put_source(old);app.state.store.save(lesson)
    # Simulate a saved record that predates the added source metadata fields.
    body=lesson.model_dump();body['sources'][0].pop('channel');body['sources'][0].pop('transcript_provider')
    with app.state.store.db:app.state.store.db.execute('UPDATE lessons SET body=? WHERE id=?',(json.dumps(body),lesson.id))
    with TestClient(app) as client:
        saved=client.get('/api/lessons/saved_lesson').json()
        assert saved['request']['source_mode']=='import' and saved['request']['source_ids']==[old.id]
        assert saved['sources'][0]['source_type']=='import'
        assert client.post('/api/lessons/saved_lesson/shorts/saved_short/explanations',json={'kind':'example','request_id':'saved-extra-request'}).status_code==202
        final=wait_for(client,lesson.id)
        assert final['sources'][0]['source_type']=='import' and final['shorts'][0]==saved['shorts'][0]
        youtube_ids={s['id'] for s in final['sources'] if s['source_type']=='youtube'}
        assert youtube_ids and all(ref['source_id'] in youtube_ids for ref in final['shorts'][1]['evidence_references'])


def test_provider_cannot_supply_an_import_under_the_new_flow(tmp_path):
    class Invalid(StubYouTube):
        def transcript(self,*args):return source()
    settings=Settings(data=tmp_path);model=StubModel()
    with TestClient(create_app(settings,model,StubSpeech(settings),Invalid())) as client:
        lid=client.post('/api/lessons',json=request_for(None)).json()['id']
        assert wait_for(client,lid,'failed')['job']['error']['code']=='YOUTUBE_SOURCE_REQUIRED'
        assert model.calls==0


def fetched(rows):
    return SimpleNamespace(video_id='video000000',language_code='en',is_generated=True,to_raw_data=lambda:rows)


def test_caption_passages_keep_video_metadata_and_supplied_time_bounds():
    text='An index maps a search key to matching rows in a database table.'
    rows=[{'text':text,'start':1+i*5,'duration':4} for i in range(6)]
    source=source_from_transcript({'video_id':'video000000','title':'Test captions','channel':'Test channel'},fetched(rows))
    require_youtube(source)
    assert source.channel=='Test channel' and source.url=='https://www.youtube.com/watch?v=video000000'
    assert source.segments[0].start_ms==1000 and source.segments[-1].end_ms==30000
    assert ' '.join(s.text for s in source.segments)==' '.join(r['text'] for r in rows)
    assert all(len(s.text)<=280 and s.end_ms>s.start_ms for s in source.segments)


@pytest.mark.parametrize('timing',[{'start':-1,'duration':2},{'start':1,'duration':0},{'start':float('nan'),'duration':2}])
def test_invalid_caption_timing_is_rejected(timing):
    with pytest.raises(AppError,match='timing'):
        source_from_transcript({'video_id':'video000000','title':'Test','channel':'Test'},fetched([{'text':'A real caption.',**timing}]))
