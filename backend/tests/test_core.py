import asyncio
import json
import threading
import time
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from app.config import Settings
from app.contracts import (CandidateRanking, CandidateScore, Connection, DiagramNode, DraftAction, EvidenceRef, ImportRequest, Job, Lesson, LessonPlan, ModelShort, NarrationUnit, Objective, Question, SavedLearningRequest, Short, ShortDraft, TranscriptSegment)
from app.errors import AppError, Cancelled
from app.main import create_app
from app.sources import parse_transcript, retrieve, video_id
from app.store import Store
from app.validation import validate_evidence, validate_draft, planned_duration
from app.providers import Ollama, check_cancel


def source(text="An index maps keys to rows. A scan tests many rows to find matching data in the table. An index takes storage space and must be updated when indexed values change. The query planner chooses whether to use an index for a query."):
    return parse_transcript(ImportRequest(title="Test source", text=text))


def draft_for(segments, template="process", question=False, tag=None):
    ref = EvidenceRef(source_id=segments[0].source_id, segment_ids=[segments[0].id], quote=segments[0].text)
    half = len(segments[0].text.split())//2
    texts = [" ".join(segments[0].text.split()[:half]), " ".join(segments[0].text.split()[half:])]
    if tag:
        # Distinct words per short so the repeated-narration check passes in lesson tests.
        texts = [" ".join(f"{tag}u{i}w{k}" for k in range(20))+"." for i in range(2)]
    # Deliberately fixed content for contract tests only. This is not a production provider.
    return ShortDraft(objective="Understand an index lookup", prerequisites=[],
        narration_units=[NarrationUnit(text=texts[0], evidence=ref), NarrationUnit(text=texts[1], evidence=ref)],
        template=template, nodes=[DiagramNode(id="key",label="Search value",detail="The key you look up",icon="key",role="good" if template=="dos_donts" else "start",slot=0),
                                  DiagramNode(id="row",label="Matching row",detail="Where the data lives",icon="table",role="bad" if template=="dos_donts" else "result",slot=1)]
            + ([DiagramNode(id="plan",label="Query planner",detail="Chooses the access path",icon="route",role="step",slot=2)] if template=="cycle" else []),
        connections=[Connection(id="edge",source="key",target="row")], actions=[DraftAction(kind="appear",target="key",unit=0),DraftAction(kind="appear",target="row",unit=1),DraftAction(kind="draw",target="edge",unit=1)],
        question=Question(prompt="Which statement is in the supplied material?",options=[segments[0].text.split(". ")[0]+".","This is an incorrect answer."],answer_index=0,explanation=segments[0].text.split(". ")[0]+".",evidence=ref) if question else None)


def test_srt_vtt_keep_times_and_strip_markup():
    s=parse_transcript(ImportRequest(title="Timed",text="1\n00:00:01,200 --> 00:00:04,500\n<b>An index</b> maps keys to rows.\n",format="srt"))
    assert (s.segments[0].start_ms,s.segments[0].end_ms)==(1200,4500)
    assert s.segments[0].text=="An index maps keys to rows."
    v=parse_transcript(ImportRequest(title="VTT",text="WEBVTT\n\ncue\n00:01.200 --> 00:04.500 align:start\nAn index maps keys to rows.",format="vtt"))
    assert v.segments[0].start_ms==1200

@pytest.mark.parametrize("text",["00:99.000 --> 01:01.000\nCaption.","00:04.000 --> 00:03.000\nCaption.","Caption has no timestamps."])
def test_reject_bad_timing(text):
    with pytest.raises(AppError):
        parse_transcript(ImportRequest(title="Bad",text=text,format="vtt"))


def test_plain_source_never_invents_timing():
    s=source()
    assert all(x.start_ms is None and x.end_ms is None for x in s.segments)
    ref=EvidenceRef(source_id=s.id,segment_ids=[s.segments[0].id],quote=s.segments[0].text,start_ms=0,end_ms=10)
    with pytest.raises(ValueError,match="Untimed"):
        validate_evidence(ref,s.segments)


def test_evidence_rejects_unknown_wrong_source_quote_and_outside_time():
    s=parse_transcript(ImportRequest(title="Timed",text="00:01.000 --> 00:04.000\nAn index maps keys to rows.",format="vtt"))
    base=EvidenceRef(source_id=s.id,segment_ids=[s.segments[0].id],quote=s.segments[0].text)
    validate_evidence(base,s.segments)
    assert base.start_ms==1000 and base.end_ms==4000
    for change in [dict(source_id="fake"),dict(segment_ids=["fake"]),dict(quote="A fabricated supporting quote."),dict(start_ms=0,end_ms=5000)]:
        with pytest.raises(ValueError):
            validate_evidence(base.model_copy(update=change),s.segments)


def test_import_url_and_size_boundaries():
    assert video_id("https://youtu.be/dQw4w9WgXcQ")=="dQw4w9WgXcQ"
    for url in ["https://evil.test/watch?v=dQw4w9WgXcQ","file:///etc/passwd","https://youtube.com.evil.test/watch?v=dQw4w9WgXcQ"]:
        with pytest.raises(AppError):video_id(url)
    with pytest.raises(AppError):source("é"*110000)


def test_retrieval_is_bounded_and_relevant():
    s=source("A bicycle has wheels.\n\nA database index maps keys to rows.\n\nTrees can store keys.")
    found=retrieve([s],"database index",limit=1)
    assert len(found)==1 and "database index" in found[0].text


def test_retrieval_skips_filler_shares_videos_and_keeps_spoken_order():
    chatty=source("I want you to subscribe, my name is Sam and I drift cars.\n\nShift your weight to the rear.\n\nKick the clutch to break traction and start drifting.\n\nDrifting needs a rear wheel drive car.")
    other=source("Counter steer to hold the drift angle.\n\nThanks for watching.")
    other=other.model_copy(update={"id":"other","segments":[x.model_copy(update={"source_id":"other","id":f"other_{i}"}) for i,x in enumerate(other.segments)]})
    found=retrieve([chatty,other],"I want to learn to drift a car",limit=4)
    texts=[x.text for x in found]
    assert not any("subscribe" in t for t in texts)
    assert any("Counter steer" in t for t in texts)
    # Matches bring the following passage for context, and each video stays in spoken order.
    assert texts.index("Kick the clutch to break traction and start drifting.")<texts.index("Drifting needs a rear wheel drive car.")
    # The budget fits the best passage but not its neighbour.
    assert retrieve([chatty],"drift",budget=60)==[chatty.segments[2]]

@pytest.mark.parametrize("change",[{"nodes":[{"id":"a","label":"A","slot":0},{"id":"b","label":"B","slot":0}]},{"actions":[{"kind":"appear","target":"<script>","unit":0}]},{"actions":[{"kind":"move","target":"key","unit":0,"to_slot":1}]},{"connections":[{"id":"edge","source":"key","target":"missing"}]},{"template":"javascript"}])
def test_invalid_scene_cannot_enter_contract(change):
    payload=draft_for(source().segments).model_dump();payload.update(change)
    with pytest.raises(ValidationError):ShortDraft.model_validate(payload)


def test_budget_reserves_unfinished_speech_and_question():
    shorts=[Short(id=str(i),objective="An objective",question_required=i==2) for i in range(6)]
    assert planned_duration(shorts)==260000
    shorts[0].status="ready";shorts[0].measured_duration_ms=23000
    assert planned_duration(shorts)==243000
    shorts.insert(1,Short(id="extra",objective="Optional example",optional=True))
    assert planned_duration(shorts)==283000

class StubModel:
    def __init__(self, delay: float=0):self.calls=0;self.delay=delay
    def fingerprint(self):return {"model":"test-only","digest":"stub","context":8192}
    def generate(self,contract,task,cancel,validate=None):
        from app.validation import SupportCheck
        self.calls+=1
        if self.delay:cancel.wait(self.delay)
        check_cancel(cancel)
        if contract is LessonPlan:
            result=LessonPlan(sufficient_evidence=True,reason="",objectives=[Objective(title=f"Learning point {i}",template=t,prerequisites=[]) for i,t in enumerate(["process","comparison","example"])])
        elif contract is SupportCheck:result=SupportCheck(supported=True,reason="Test only")
        elif contract is CandidateRanking:result=CandidateRanking(scores=[CandidateScore(video_id=c["video_id"],relevance=5,level_fit=5,teaching=5,density=5,captions=5,reason="Test only") for c in task["candidates"]])
        else:
            draft=draft_for([TranscriptSegment.model_validate(s) for s in task["segments"]],task["template"],task["question_required"],tag=f"s{self.calls}")
            body=draft.model_dump();body.pop("actions")
            for u in body['narration_units']:
                u['segment_id']=u.pop('evidence')['segment_ids'][0];u.pop('start_ms');u.pop('end_ms')
            if body['question']:
                body['question']['segment_id']=body['question'].pop('evidence')['segment_ids'][0];body['question'].pop('allowance_ms');body['question']['correct_answer']=body['question']['options'][body['question']['answer_index']];body['question']['distractors']=[o for i,o in enumerate(body['question'].pop('options')) if i!=body['question']['answer_index']];body['question'].pop('answer_index')
            result=ModelShort.model_validate(body)
        if validate:validate(result)
        return result

class StubSpeech:
    def __init__(self,settings):self.settings=settings;self.actual_voice="test"
    def prepare(self):pass
    def fingerprint(self):return {"voice":"test"}
    def synthesize(self,units,key,cancel):
        import wave
        check_cancel(cancel)
        filename=key+".wav"
        with wave.open(str(self.settings.data/"audio"/filename),"wb") as w:
            w.setnchannels(1);w.setsampwidth(2);w.setframerate(24000);w.writeframes(b'\0'*(24000*2*2))
        for i,u in enumerate(units):u.start_ms=i*1000;u.end_ms=(i+1)*1000
        return filename,2000,False


class StubYouTube:
    """Explicit test provider. These are synthetic captions, not a live YouTube result."""
    def __init__(self):self.searches=[];self.fetches=[]
    def search(self,query):
        self.searches.append(query)
        return [{"video_id":"dQw4w9WgXcQ","title":"Test-only YouTube source","channel":"Test channel"}]
    def transcript(self,candidate,cancel):
        check_cancel(cancel);self.fetches.append(candidate["video_id"])
        original=source();sid="src_test_"+candidate["video_id"]
        return original.model_copy(update={"id":sid,"segments":[segment.model_copy(update={"id":f"{sid}_{i}","source_id":sid}) for i,segment in enumerate(original.segments)],"source_type":"youtube","video_id":candidate["video_id"],"url":f"https://www.youtube.com/watch?v={candidate['video_id']}","channel":candidate["channel"],"transcript_provider":"supadata","provenance":"Synthetic test transcript. Not a live result."})


def wait_for(client,lid,state="complete"):
    deadline=time.monotonic()+8
    lesson={}
    while time.monotonic()<deadline:
        lesson=client.get(f"/api/lessons/{lid}").json()
        if lesson["job"]["status"]==state:return lesson
        time.sleep(.01)
    raise AssertionError(lesson)


def request_for(sid,rid="test-request-id"):
    return {"goal":"Understand database indexes","request_id":rid}


def test_job_idempotency_publication_retry_cancel_and_events(tmp_path):
    settings=Settings(data=tmp_path);model=StubModel(.05);app=create_app(settings,model,StubSpeech(settings),StubYouTube())
    with TestClient(app) as c:
        sid='unused-legacy-id'
        first=c.post('/api/lessons',json=request_for(sid));assert first.status_code==202
        lid=first.json()['id']
        assert c.post('/api/lessons',json=request_for(sid)).json()['id']==lid
        assert c.post('/api/lessons',json={**request_for(sid),'goal':'Different goal'}).status_code==409
        ready=wait_for(c,lid);assert ready['status']=='ready' and ready['planned_duration_ms']<=300000
        assert all(s['status']=='ready' and s['audio_path'] and s['scenes'] for s in ready['shorts'])
        assert 'first_playable_seconds' in ready['metrics']
        events=c.get(f'/api/lessons/{lid}/events',headers={'Last-Event-ID':'2'}).text
        assert 'event: snapshot' in events and 'event: done' in events and 'id: 1\n' not in events
        assert c.get('/api/audio/'+ready['shorts'][0]['audio_path']).status_code==200
        assert c.get('/api/audio/secret').status_code==404
        sid_short=ready['short_ids'][0]
        body={'kind':'example','added_seconds':40,'request_id':'extra-request-id'}
        assert c.post(f'/api/lessons/{lid}/shorts/{sid_short}/explanations',json=body).status_code==202
        assert c.post(f'/api/lessons/{lid}/shorts/{sid_short}/explanations',json=body).status_code==202
        extra=wait_for(c,lid);assert len(extra['shorts'])==4 and extra['extra_allowance_ms']==40000
        assert extra['shorts'][2]['id']==ready['shorts'][1]['id']
        second=c.post('/api/lessons',json=request_for(sid,'cancel-request-id')).json()
        cancelled=c.post(f"/api/lessons/{second['id']}/cancel",json={}).json()
        assert cancelled['status']=='cancelled'
        time.sleep(.2)
        assert c.get(f"/api/lessons/{second['id']}").json()['status']=='cancelled'
        assert c.post(f"/api/lessons/{second['id']}/retry",json={}).status_code==202
        assert wait_for(c,second['id'])['status']=='ready'


def test_restart_preserves_ready_short_and_marks_interruption(tmp_path):
    settings=Settings(data=tmp_path);store=Store(settings.data);s=source();store.put_source(s)
    req=SavedLearningRequest(**request_for(s.id),source_mode="import",source_ids=[s.id]);lesson=Lesson(id="lesson",request=req,sources=[s],shorts=[Short(id="ready",objective="Saved output",status="ready",measured_duration_ms=2000),Short(id="later",objective="Unfinished",status="generating")],job=Job(id="job",lesson_id="lesson",status="running",created_at=time.time(),updated_at=time.time()))
    store.save(lesson);store.close()
    reopened=Store(settings.data);reopened.recover();lesson=reopened.lesson('lesson')
    assert lesson.job.status=='interrupted' and lesson.shorts[0].status=='ready' and lesson.shorts[1].status=='failed';reopened.close()


def test_provider_and_origin_errors_are_actionable(tmp_path):
    app=create_app(Settings(data=tmp_path,youtube_key=""),StubModel(),StubSpeech(Settings(data=tmp_path)))
    with TestClient(app) as c:
        assert c.get('/api/sources/search?q=database').json()['code']=='YOUTUBE_KEY_MISSING'
        assert c.post('/api/lessons',json={},headers={'Origin':'https://hostile.test'}).status_code==403
        assert c.post('/api/lessons',json={}).json()['code']=='INVALID_REQUEST'


def test_ollama_repair_attempts_are_bounded(monkeypatch,tmp_path):
    import httpx
    calls=[]
    class Response:
        is_success=True
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def iter_lines(self):yield json.dumps({'message':{'content':'{"bad":"data"}'},'done':True})
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def stream(self,*a,**kw):calls.append(kw);return Response()
    monkeypatch.setattr(httpx,'Client',Client)
    with pytest.raises(AppError,match="after two repairs"):
        Ollama(Settings(data=tmp_path)).generate(LessonPlan,{},threading.Event())
    assert len(calls)==3


def test_same_text_with_different_formats_has_different_identity():
    text="00:01.000 --> 00:04.000\nAn index maps keys to rows."
    plain=parse_transcript(ImportRequest(title="Source",text=text,format="txt"))
    timed=parse_transcript(ImportRequest(title="Source",text=text,format="vtt"))
    assert plain.id!=timed.id and plain.segments[0].start_ms is None and timed.segments[0].start_ms==1000


def test_insufficient_evidence_is_a_recoverable_job_error(tmp_path):
    class Insufficient(StubModel):
        def generate(self,contract,task,cancel,validate=None):
            return LessonPlan(sufficient_evidence=False,reason="This source has no evidence about the requested topic.",objectives=[])
    settings=Settings(data=tmp_path)
    with TestClient(create_app(settings,Insufficient(),StubSpeech(settings),StubYouTube())) as c:
        sid='unused-legacy-id'
        lid=c.post('/api/lessons',json=request_for(sid)).json()['id']
        result=wait_for(c,lid,'failed')
        assert result['job']['error']['code']=='INSUFFICIENT_EVIDENCE' and not result['shorts']


def test_later_speech_failure_keeps_ready_outputs_and_retry_uses_them(tmp_path):
    class FailSpeech(StubSpeech):
        calls=0
        def synthesize(self,units,key,cancel):
            self.calls+=1
            if self.calls==2:raise AppError('SPEECH_FAILED','Speech failed. Check the voice and retry.')
            return super().synthesize(units,key,cancel)
    settings=Settings(data=tmp_path);speech=FailSpeech(settings)
    with TestClient(create_app(settings,StubModel(),speech,StubYouTube())) as c:
        sid='unused-legacy-id'
        lid=c.post('/api/lessons',json=request_for(sid)).json()['id']
        result=wait_for(c,lid,'failed');first=result['shorts'][0]
        assert result['status']=='partially_ready' and first['status']=='ready'
        assert c.post(f'/api/lessons/{lid}/retry',json={}).status_code==202
        final=wait_for(c,lid)
        assert final['shorts'][0]==first and speech.calls==4
        media=settings.data/'audio'/first['audio_path'];media.unlink()
        assert c.post(f'/api/lessons/{lid}/retry',json={}).status_code==202
        repaired=wait_for(c,lid)
        assert media.exists() and repaired['shorts'][0]['status']=='ready'


def test_quota_and_network_failure_do_not_become_transcripts(monkeypatch):
    import httpx
    from app.sources import search_youtube
    monkeypatch.setattr(httpx,'get',lambda *a,**kw:httpx.Response(403,json={'error':{'message':'quota'}}))
    with pytest.raises(AppError,match='quota'):search_youtube('database','test-key')
    def fail(*a,**kw):raise httpx.ConnectError('Offline')
    monkeypatch.setattr(httpx,'get',fail)
    with pytest.raises(AppError,match='internet connection'):search_youtube('database','test-key')


def test_missing_and_remote_models_never_generate(monkeypatch,tmp_path):
    import httpx
    class Client:
        remote=False
        missing=True
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def get(self,*a,**kw):return httpx.Response(200,request=httpx.Request('GET','http://localhost/api/tags'),json={'models':[] if self.missing else [{'name':'qwen3:8b','digest':'test'}]})
        def post(self,*a,**kw):return httpx.Response(200,request=httpx.Request('POST','http://localhost/api/show'),json={'remote_host':'https://remote.test'} if self.remote else {})
    monkeypatch.setattr(httpx,'Client',Client)
    model=Ollama(Settings(data=tmp_path,model="qwen3:8b"))
    with pytest.raises(AppError,match='ollama pull'):model.readiness()
    Client.missing=False;Client.remote=True
    with pytest.raises(AppError,match='remote service'):model.readiness()


def test_model_evidence_is_copied_from_source_not_generated():
    from app.validation import attach_evidence
    s=source();d=draft_for(s.segments).model_dump();d.pop("actions")
    for u in d['narration_units']:
        u['segment_id']=u.pop('evidence')['segment_ids'][0];u.pop('start_ms');u.pop('end_ms')
    model=ModelShort.model_validate(d);final=attach_evidence(model,s.segments)
    assert all(u.evidence.quote==s.segments[0].text for u in final.narration_units)
    model.narration_units[0].segment_id='invented'
    with pytest.raises(ValueError,match='existing'):attach_evidence(model,s.segments)


def test_paraphrased_narration_is_accepted_but_video_references_and_repeats_are_not():
    s=source();draft=draft_for(s.segments,question=True)
    draft.narration_units[0].text='You can think of an index as a shortcut that points straight to the matching rows.'
    assert draft.question is not None
    draft.question.explanation='The index stores where each key lives, so you skip the full scan.'
    validate_draft(draft,s.segments,True)
    for text,reason in [('Step number three covers how the planner picks an index for you.','numbered step'),
                        ('In this video the planner chooses whether to use an index.','video'),
                        ('I always add an index before running a slow query on a table.','presenter'),
                        ("We're going to see how the planner picks an index for a query.","'we'")]:
        draft.narration_units[0].text=text
        with pytest.raises(ValueError,match=reason):validate_draft(draft,s.segments,True)
    draft.narration_units[0].text='The US census tables use indexes so you can find a household fast.'
    validate_draft(draft,s.segments,True)
    with pytest.raises(ValueError,match='repeats'):validate_draft(draft,s.segments,True,[draft.narration_units[1].text])


@pytest.mark.parametrize('template,change,reason',[
    ('process',lambda d:setattr(d.nodes[0],'icon','not-an-icon'),'icon'),
    ('process',lambda d:setattr(d.nodes[0],'detail',''),'detail'),
    ('dos_donts',lambda d:setattr(d.nodes[1],'role','good'),'role good and one with role bad'),
    ('cycle',lambda d:d.nodes.pop(),'3 or 4 nodes')])
def test_diagram_needs_icons_details_and_template_structure(template,change,reason):
    s=source();draft=draft_for(s.segments,template=template)
    validate_draft(draft,s.segments,False)
    change(draft)
    with pytest.raises(ValueError,match=reason):validate_draft(draft,s.segments,False)


def test_icon_lists_match_between_backend_and_frontend():
    import re
    from app.icons import ICONS
    frontend=(Path(__file__).resolve().parents[2]/'frontend'/'src'/'icons.ts').read_text()
    assert sorted(re.findall(r"^  '([a-z0-9-]+)':",frontend,re.M))==sorted(ICONS)


def test_schema_allows_written_narration_but_constrains_citations_and_icons(monkeypatch,tmp_path):
    import httpx,jsonschema
    s=source();other=source('A different source describes a different topic. This passage must not support a database index quotation. It contains enough words for a useful standalone record, but it does not provide evidence for an index explanation in this test case.')
    draft=draft_for(s.segments);body=draft.model_dump();body.pop("actions");body['nodes'][0]['id']='node_0';body['nodes'][1]['id']='node_1';body['connections']=[{'id':'conn_0','source':'node_0','target':'node_1'}]
    texts=['You can picture an index as a sorted list of keys with row locations.','Your query then jumps to the rows instead of checking every one in turn.']
    for i,u in enumerate(body['narration_units']):
        u['text']=texts[i];u['segment_id']=u.pop('evidence')['segment_ids'][0];u.pop('start_ms');u.pop('end_ms')
    captured=[]
    class Response:
        is_success=True
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def iter_lines(self):yield json.dumps({'message':{'content':json.dumps(body)},'done':True})
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def stream(self,*a,**kw):captured.append(kw['json']['format']);return Response()
    monkeypatch.setattr(httpx,'Client',Client)
    task={'segments':[x.model_dump() for x in s.segments],'template':'process','question_required':False}
    model=Ollama(Settings(data=tmp_path));model.generate(ModelShort,task,threading.Event())
    jsonschema.validate(body,captured[0])
    for change in (lambda b:b['narration_units'][0].update(segment_id=other.segments[0].id),lambda b:b['nodes'][0].update(icon='not-an-icon'),lambda b:b['nodes'][0].pop('icon')):
        wrong=json.loads(json.dumps(body));change(wrong)
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(wrong,captured[0])


def test_chart_cannot_use_a_partial_numeric_match_or_missing_values():
    s=source('This original chart fixture has 100 items in group A and 20 items in group B. These are illustrative counts for a chart test, not performance results from a real computer. Compare the supplied group counts to read this example chart correctly.')
    d=draft_for(s.segments,template='chart');d.nodes[0].value=100;d.nodes[1].value=20
    validate_draft(d,s.segments,False)
    d.nodes[0].value=10
    with pytest.raises(ValueError,match='actual source number'):validate_draft(d,s.segments,False)
    d.nodes[0].value=None
    with pytest.raises(ValueError,match='numeric values'):validate_draft(d,s.segments,False)


def test_caption_matches_guide_highlight_and_diagram_has_relevant_source_refs():
    from app.validation import refine_cues,diagram_evidence
    s=source('A scan checks rows in a table. An index finds matching rows for a query. A selective query can use an index when the planner selects it. This source is original teaching material and does not give a measured speed improvement.\n\nAn index takes storage space. A change to indexed data must update the index and can add write cost.')
    d=draft_for(s.segments)
    d.nodes[0].label='Scan';d.nodes[1].label='Index'
    d.narration_units[0].text='A scan checks rows in a table.';d.narration_units[1].text='An index finds matching rows for a query.'
    refine_cues(d)
    highlights=[a.target for a in d.actions if a.kind=='highlight']
    assert highlights==['key','row']
    d.nodes.append(DiagramNode(id='cost',label='Storage cost',slot=2))
    refs=diagram_evidence(d,s.segments)
    assert any(ref.segment_ids==[s.segments[1].id] for ref in refs)


def test_scan_cue_does_not_highlight_an_index_mentioned_as_absent():
    from app.validation import refine_cues
    s=source('Without a useful index, the database can read many rows and test the condition on each row. This process is called a table scan. The table contains rows with different stored values.\n\nAn index on email can help the database find matching entries without testing the email in every row.')
    d=draft_for(s.segments)
    d.nodes[0].label='Table Scan';d.nodes[1].label='Index Lookup'
    d.narration_units[0].text=s.segments[0].text.split('. ')[0]+'.'
    d.narration_units[1].text=s.segments[1].text
    d.narration_units[1].evidence=EvidenceRef(source_id=s.id,segment_ids=[s.segments[1].id],quote=s.segments[1].text)
    refine_cues(d)
    assert [a.target for a in d.actions if a.kind=='highlight']==['key','row']
