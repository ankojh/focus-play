"""Deterministic arithmetic/orchestration diagnostics, not live teaching evaluation.

The fake reviewer and tagged narration deliberately test control flow. Topic
labels distinguish fixture outcomes; they do not establish semantic support by
an actual model or a real YouTube video.
"""
import asyncio
import json
import random
import re
import threading
import time
import wave

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.contracts import (AcquisitionLedger, CoverageGap, Job, Lesson, LessonPlan,
                           ModelStoryboard, Objective, SavedLearningRequest, Short,
                           TranscriptSegment)
from app.errors import AppError, Cancelled
from app.jobs import Jobs
from app.main import create_app
from app.planning import (aggregate, candidate_capacity, new_state, practice,
                          recalibrate_queued, refresh, speech_prediction)
from app.providers import check_cancel
from app.sources import retrieve
from app.store import Store
from test_core import StubModel, StubSpeech, StubYouTube, wait_for

TOPICS = [
    'key lookup', 'leaf traversal', 'hash collision', 'composite prefix', 'range boundaries',
    'uniqueness enforcement', 'covering columns', 'write maintenance', 'storage overhead',
    'selectivity estimates', 'cardinality statistics', 'sort avoidance', 'reverse iteration',
    'partial predicates', 'expression matching', 'null handling', 'collation ordering',
    'equality constraints', 'join probing', 'bitmap combination', 'page splitting',
    'fill factor', 'clustered organization', 'heap access', 'random reads',
    'sequential scans', 'bulk loading', 'locking contention', 'hot partitions',
    'index intersection', 'duplicate entries', 'row identifiers', 'key compression',
    'prefix truncation', 'dense leaves', 'sparse navigation', 'branch fanout',
    'tree height', 'buffer residency', 'disk latency', 'rebuild scheduling',
    'invisible candidates', 'query hints', 'parameter sensitivity', 'skew distributions',
    'multicolumn correlation', 'descending keys', 'functional dependencies', 'foreign references',
    'multivalue expansion', 'spatial bounds', 'text postings', 'update amplification',
    'vacuum cleanup', 'dead entries', 'transaction visibility', 'online construction',
    'plan comparison', 'usage monitoring', 'redundancy detection', 'constraint validation',
    'partition pruning', 'timestamp windows', 'pagination seeking', 'aggregate grouping',
    'minmax skipping', 'index lifetime', 'benchmark interpretation', 'workload sampling',
    'migration rollback', 'physical locality', 'predicate implication', 'cost estimation',
    'range merging', 'access path selection', 'validation checklist', 'deployment tradeoffs',
]


class SessionSources(StubYouTube):
    def transcript(self, candidate, cancel):
        original = super().transcript(candidate, cancel)
        return original.model_copy(update={'segments': [TranscriptSegment(
            id=f'{original.id}_{i}', source_id=original.id,
            text=f'Database index diagnostic topic: {topic}. This is an original synthetic passage naming this fixture outcome, not live source evidence.',
            start_ms=i*10000, end_ms=(i+1)*10000) for i, topic in enumerate(TOPICS)]})


class SessionModel(StubModel):
    def __init__(self, available=77):
        super().__init__()
        self.available = available
        self.plan_tasks = []
        self.draft_tasks = []

    def generate(self, contract, task, cancel, validate=None):
        if contract is LessonPlan:
            self.calls += 1
            self.plan_tasks.append(task)
            initial = task['phase'] == 'core'
            known = {o.split('|', 1)[0] for o in task['covered_outcomes']}
            segments = [s for s in task['segments'] if int(s['id'].rsplit('_', 1)[1]) < self.available
                        and f"topic_{s['id'].rsplit('_', 1)[1]}" not in known]
            budget = task['remaining_ms']
            count = min(task['max_objectives'], len(segments), max(1, budget // 30000))
            # Reserve closing in the initial batch, not in every expansion.
            closing = initial and count > 1
            rows = []
            for i, segment in enumerate(segments[:count]):
                n = int(segment['id'].rsplit('_', 1)[1])
                recap = closing and i == count-1
                checkpoint = not recap and n % 3 == 2 and budget >= count*30000 + 20000
                target = min(30000, (budget - (20000 if checkpoint else 0)) // count)
                target = max(15000, target)
                topic = TOPICS[n]
                rows.append(Objective(concept_id='closing' if recap else f'topic_{n}',
                    learning_outcome='Recall the core access path tradeoffs' if recap else f'Explain {topic}',
                    title='Recap the access path' if recap else f'Explore {topic}',
                    teaching_role='recap' if recap else 'mechanism',
                    dependency_ids=[rows[-1].concept_id] if recap else [],
                    relevance='Supports the index design goal', evidence_segment_ids=[segment['id']],
                    curriculum_role='closing' if recap else 'core' if initial else 'extension',
                    target_duration_ms=target, visual_intent='Trace the supported relationship',
                    template='process', prerequisites=[], checkpoint=checkpoint))
            # Multiple checkpoint decisions must fit the canonical budget too.
            while sum(o.target_duration_ms + (20000 if o.checkpoint else 0) for o in rows) > budget:
                next(o for o in reversed(rows) if o.checkpoint).checkpoint = False
            result = LessonPlan(sufficient_evidence=True, reason='' if rows else 'No distinct useful fixture outcomes remain.', objectives=rows)
            if validate:
                validate(result)
            return result
        if contract is ModelStoryboard:
            self.draft_tasks.append(task)
            result = super().generate(contract, task, cancel)
            words = task.get('target_words', 40)
            repair = re.search(r'Shorten to about (\d+) words', task['task'])
            if repair:
                words = int(repair.group(1))
            # Tagged diagnostic narration tests duplicate detection and measured
            # durations; source/teaching support is intentionally a fake verdict.
            for i, unit in enumerate(result.narration_units):
                count = words//2 + (words % 2 if i else 0)
                unit.text = ' '.join(f'x{self.calls:x}{i}{k:x}' for k in range(count)) + '.'
                unit.segment_id = task['teaching']['plan']['evidence_segment_ids'][0]
            if result.question:
                topic = task['teaching']['outcome'].removeprefix('Explain ')
                result.question.prompt = f'Which supported description explains {topic}?'
                result.question.segment_id = task['teaching']['plan']['evidence_segment_ids'][0]
            if validate:
                validate(result)
            return result
        return super().generate(contract, task, cancel, validate)


class DurationSpeech(StubSpeech):
    def __init__(self, settings, rate=400):
        super().__init__(settings)
        self.rate = rate
        self.durations = []

    def synthesize(self, units, key, cancel):
        check_cancel(cancel)
        durations = [len(u.text.split()) * self.rate for u in units]
        duration = sum(durations)
        self.durations.append(duration)
        if duration > 40000:
            raise AppError('SPEECH_DURATION', 'The speech exceeded 40 seconds. Shorten to about 50 words.', 422)
        filename = key + '.wav'
        with wave.open(str(self.settings.data/'audio'/filename), 'wb') as file:
            file.setnchannels(1); file.setsampwidth(2); file.setframerate(24000)
            file.writeframes(b'\0' * (duration * 48))
        cursor = 0
        for unit, length in zip(units, durations):
            unit.start_ms, unit.end_ms = cursor, cursor+length
            cursor += length
        return filename, duration, False


def request(seconds=300):
    return dict(goal='Understand database index design and tradeoffs', time_budget_seconds=seconds,
                request_id='session-request', prior_knowledge='beginner')


@pytest.mark.parametrize('seconds', [60, 73, 120, 137, 300, 600, 1200])
@pytest.mark.parametrize('rate', [250, 430, 550])
def test_session_matrix_meets_band_without_overrun_or_padding(tmp_path, seconds, rate):
    settings = Settings(data=tmp_path)
    model, speech, sources = SessionModel(), DurationSpeech(settings, rate), SessionSources()
    with TestClient(create_app(settings, model, speech, sources)) as client:
        lid = client.post('/api/lessons', json=request(seconds)).json()['id']
        final = wait_for(client, lid)
        ledger = final['duration_ledger']
        assert .9 <= ledger['utilisation'] <= 1, final
        assert ledger['final_content_ms'] == final['planned_duration_ms'] <= seconds*1000
        assert ledger['measured_ready_media_ms'] == sum(s['measured_duration_ms'] for s in final['shorts'])
        assert ledger['reserved_practice_ms'] == sum(20000 for s in final['shorts'] if s['question'])
        assert ledger['reserved_closing_ms'] == ledger['estimated_unready_media_ms'] == 0
        assert final['planning']['completion_reason'] == 'target_met', final['planning']
        assert len({o['learning_outcome'] for o in final['objectives']}) == len(final['objectives'])
        assert sum(s['curriculum_role']=='closing' for s in final['shorts']) <= 1
        assert all(s['audio_path'] and s['scenes'] and s['status']=='ready' for s in final['shorts'])
        assert all(len(t['segments']) <= 20 and sum(len(s['text']) for s in t['segments']) <= 4500 for t in model.plan_tasks + model.draft_tasks)
        assert all(t['max_objectives'] <= 4 and len(json.dumps(t)) < 19000 for t in model.plan_tasks)
        if seconds >= 600:
            assert len(final['shorts']) > 8
        assert len(sources.searches) == 1
        assert final['extra_allowance_ms'] == 0


def test_shorter_media_triggers_distinct_bounded_extensions(tmp_path):
    settings = Settings(data=tmp_path)
    model = SessionModel()
    with TestClient(create_app(settings, model, DurationSpeech(settings, 250), SessionSources())) as client:
        lid = client.post('/api/lessons', json=request()).json()['id']
        final = wait_for(client, lid)
        assert len(model.plan_tasks) > 1
        assert final['planning']['expansion_attempts'] <= final['planning']['expansion_limit']
        assert any(s['curriculum_role']=='extension' and not s['optional'] for s in final['shorts'])
        assert final['planning']['candidate_attempts'] == len(final['shorts'])


def test_longer_prediction_repairs_only_unpublished_work(tmp_path):
    settings = Settings(data=tmp_path)
    model, speech = SessionModel(), DurationSpeech(settings, 650)
    with TestClient(create_app(settings, model, speech, SessionSources())) as client:
        lid = client.post('/api/lessons', json=request(120)).json()['id']
        final = wait_for(client, lid)
        assert any('Repair only this unpublished activity' in t['task'] for t in model.draft_tasks)
        assert final['duration_ledger']['utilisation'] >= .9
        assert all(s['measured_duration_ms'] <= 40000 for s in final['shorts'])
        assert len(speech.durations) > len(final['shorts'])


def test_narrow_coverage_finishes_honestly_without_filler(tmp_path):
    settings = Settings(data=tmp_path)
    model = SessionModel(available=1)
    with TestClient(create_app(settings, model, DurationSpeech(settings), SessionSources())) as client:
        lid = client.post('/api/lessons', json=request(1200)).json()['id']
        final = wait_for(client, lid)
        assert len(final['shorts']) == 1
        # Short of time, so it used its second search; no new videos, so it stops.
        assert len(final['acquisition']['rounds']) == 2
        assert final['planning']['completion_reason'] == 'source_limit'
        assert final['duration_ledger']['shortfall_ms'] > 0
        assert final['duration_ledger']['utilisation'] < .9
        assert final['planning']['completion_detail']


def test_ledger_conservation_random_durations_and_separate_pools():
    rng = random.Random(742)
    for _ in range(600):
        shorts = [Short(id=str(i), objective='A supported point', target_duration_ms=rng.randint(15000,40000),
                        measured_duration_ms=rng.randint(1000,40000), status=rng.choice(['queued','ready']),
                        curriculum_role=rng.choice(['core','extension','closing']), optional=rng.choice([True, False]),
                        question_required=rng.choice([True, False])) for i in range(rng.randint(1,80))]
        ledger = aggregate(shorts, budget_ms=1200000)
        total = sum((s.measured_duration_ms if s.status=='ready' else s.target_duration_ms)+practice(s) for s in shorts)
        assert total == ledger.forecast_total_ms
        assert ledger.forecast_total_ms == ledger.measured_ready_media_ms + ledger.estimated_unready_media_ms + ledger.reserved_closing_ms + ledger.reserved_practice_ms
        assert ledger.original_content_ms + ledger.extra_content_ms == ledger.measured_ready_media_ms + ledger.reserved_practice_ms
        assert all(value >= 0 for value in [ledger.measured_ready_media_ms, ledger.reserved_closing_ms, ledger.reserved_practice_ms, ledger.shortfall_ms])
        assert aggregate(shorts, final=True).final_content_ms == total


def lesson_for(seconds=120, **kwargs):
    return Lesson(id='session', request=SavedLearningRequest(**request(seconds)), sources=[],
                  planning=new_state(seconds*1000),
                  job=Job(id='job', lesson_id='session', created_at=time.time(), updated_at=time.time()), **kwargs)


def test_practice_closing_capacity_and_extra_budget_are_never_double_counted():
    core = Short(id='core', objective='Core', status='ready', measured_duration_ms=25000, question_required=True)
    extension = Short(id='ext', objective='Extension', target_duration_ms=30000)
    closing = Short(id='close', objective='Closing', target_duration_ms=30000, curriculum_role='closing')
    extra = Short(id='extra', objective='Approved extra', optional=True)
    lesson = lesson_for(shorts=[core, extension, closing, extra], extra_allowance_ms=40000)
    ledger = refresh(lesson)
    assert ledger.forecast_total_ms == 145000
    assert ledger.reserved_closing_ms == 30000 and ledger.reserved_practice_ms == 20000
    assert candidate_capacity(lesson, extra) == 40000
    assert candidate_capacity(lesson, extension) == 40000
    extension.status='ready'; extension.measured_duration_ms=39000
    recalibrate_queued(lesson)
    assert core.measured_duration_ms == 25000 and core.status=='ready'
    assert aggregate([s for s in lesson.shorts if not s.optional]).forecast_total_ms <= 120000
    assert aggregate([s for s in lesson.shorts if s.optional]).forecast_total_ms <= 40000


def test_v3_planner_schema_uses_bounded_dynamic_targets(monkeypatch,tmp_path):
    import httpx
    from app.providers import Ollama
    from app.teaching import validate_plan
    from test_teaching import reference_plan, FIXTURES
    plan,segments=reference_plan(FIXTURES[0])
    for objective in plan.objectives: objective.target_duration_ms=25000
    captured=[]
    class Response:
        is_success=True
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_lines(self):yield json.dumps({'message':{'content':plan.model_dump_json()},'done':True})
    class Client:
        def __init__(self,**kw):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def stream(self,*args,**kw):captured.append(kw['json']);return Response()
    monkeypatch.setattr(httpx,'Client',Client)
    task={'plan_version':3,'max_objectives':4,'max_target_ms':30000,'segments':[s.model_dump() for s in segments]}
    result=Ollama(Settings(data=tmp_path)).generate(LessonPlan,task,threading.Event(),
        lambda p:validate_plan(p,segments,4,140000,calibrated=True))
    assert result==plan
    schema=captured[0]['format']
    assert schema['properties']['objectives']['maxItems']==4
    target=schema['$defs']['Objective']['properties']['target_duration_ms']
    assert target['minimum']==15000 and target['maximum']==30000 and 'const' not in target


def test_voice_prediction_is_calibrated_and_profile_identity_isolated(tmp_path):
    assert speech_prediction([]) == (430,5000)
    assert speech_prediction([{'words':50,'duration_ms':20000}])[0] == 400
    assert speech_prediction([{'words':40,'duration_ms':24000}])[0] == 600
    settings=Settings(data=tmp_path); store=Store(settings.data)
    jobs=Jobs(store,StubModel(),StubSpeech(settings),settings)
    try:
        lesson=lesson_for(); lesson.provider_settings={'speech':{'provider':'kokoro','voice':'af_heart','speed':1}}
        first,_,_=jobs.speech_profile(lesson)
        store.cache_put(first,[{'words':50,'duration_ms':20000}])
        assert jobs.speech_profile(lesson)[2][0]==400
        for speech in [{'provider':'macos','voice':'Samantha','speed':1}, {'provider':'kokoro','voice':'af_heart','speed':1.1}]:
            lesson.provider_settings={'speech':speech}
            assert jobs.speech_profile(lesson)[0]!=first and jobs.speech_profile(lesson)[2][0]==430
    finally: store.close()


def test_focused_retrieval_rotates_unused_passages_without_losing_required_ids():
    provider=SessionSources(); src=provider.transcript(provider.search('test')[0], threading.Event())
    first=retrieve([src],'database index')
    second=retrieve([src],'database index',excluded_ids={s.id for s in first})
    assert {s.id for s in second} - {s.id for s in first}
    required=first[0].id
    selected=retrieve([src],'database index',required_ids=[required],excluded_ids={required})
    assert required in {s.id for s in selected}
    assert sum(len(s.text) for s in selected)<=4500 and len(selected)<=20


def test_model_limit_and_work_clock_survive_restart_and_retry(tmp_path):
    settings=Settings(data=tmp_path); store=Store(settings.data); model=StubModel()
    jobs=Jobs(store,model,StubSpeech(settings),settings)
    lesson=lesson_for(); lesson.planning.model_call_limit=3
    store.save(lesson)
    jobs.generate(lesson,LessonPlan,{'segments':[source.model_dump() for source in SessionSources().transcript({'video_id':'dQw4w9WgXcQ','title':'Test','channel':'Test'},threading.Event()).segments]},threading.Event())
    store.close()
    reopened=Store(settings.data); resumed=reopened.lesson(lesson.id)
    try:
        assert resumed.planning.model_call_units==3 and resumed.planning.work_seconds>0
        resumed.job.status='queued'; reopened.save(resumed, resume=True)
        jobs=Jobs(reopened,model,StubSpeech(settings),settings)
        with pytest.raises(AppError,match='persisted generation limit'):
            jobs.generate(resumed,LessonPlan,{},threading.Event())
        assert model.calls==1
    finally: reopened.close()


@pytest.mark.parametrize('phase', ['acquisition', 'drafting', 'synthesis', 'extension'])
def test_cancel_resume_preserves_allowances_and_stable_committed_ids(tmp_path, phase):
    settings=Settings(data=tmp_path); store=Store(settings.data)
    model=SessionModel(); speech=DurationSpeech(settings); sources=SessionSources()
    jobs=Jobs(store,model,speech,settings,sources)
    lesson=lesson_for(300, acquisition=AcquisitionLedger(per_round_limit=4,transcript_limit=8))
    store.save(lesson); jobs.cancel_flags[lesson.id]=threading.Event()
    flag=jobs.cancel_flags[lesson.id]
    if phase=='acquisition':
        original=sources.transcript
        def cancel_transcript(*args):
            result=original(*args); flag.set(); return result
        sources.transcript=cancel_transcript
    elif phase in {'drafting','extension'}:
        original=model.generate
        def cancel_model(contract,task,*args):
            if (phase=='drafting' and contract is ModelStoryboard) or (phase=='extension' and task.get('phase')=='extension'):
                flag.set(); raise Cancelled()
            return original(contract,task,*args)
        model.generate=cancel_model
    else:
        original=speech.synthesize
        def cancel_speech(*args):
            flag.set(); raise Cancelled()
        speech.synthesize=cancel_speech
    try:
        with pytest.raises(Cancelled):
            while asyncio.run(jobs.advance(lesson.id)):
                pass
        jobs.cancel(lesson.id)
        cancelled=store.lesson(lesson.id)
        ready=[s.model_dump() for s in cancelled.shorts if s.status=='ready']
        ids=[s.id for s in cancelled.shorts]
        rounds=len(cancelled.acquisition.rounds)
        calls=cancelled.planning.model_call_units
        candidates=cancelled.planning.candidate_attempts
        store.close(); store=Store(settings.data); store.recover()
        # Resume with fresh providers like a real server restart. Stable queued
        # IDs and attempted video IDs survive, not just cached ready clips.
        fresh_model=SessionModel(); fresh_sources=SessionSources()
        resumed_jobs=Jobs(store,fresh_model,DurationSpeech(settings),settings,fresh_sources)
        resumed_jobs.retry(lesson.id)
        while asyncio.run(resumed_jobs.advance(lesson.id)):
            pass
        final=store.lesson(lesson.id)
        assert final.job.status=='complete'
        assert final.planning.model_call_units>=calls and final.planning.candidate_attempts>=candidates
        assert len(final.acquisition.rounds)==rounds and len(final.acquisition.tried_video_ids)==1
        assert len(fresh_sources.fetches)==0
        assert all(id_ in final.short_ids for id_ in ids)
        assert [s.model_dump() for s in final.shorts if s.id in {r['id'] for r in ready}]==ready
        assert len(final.short_ids)==len(set(final.short_ids))
    finally: store.close()


def test_focused_acquisition_and_actionable_quota_failure_are_not_exhaustion(tmp_path):
    class MissingFacet(SessionModel):
        def generate(self, contract, task, cancel, validate=None):
            if contract is LessonPlan and task.get('phase')=='extension':
                result=LessonPlan(sufficient_evidence=False,reason='The lookup caveat needs evidence.', objectives=[],
                    missing_coverage=[CoverageGap(outcome='Explain lookup limits',missing_facets=['caveat'],query_intent='index lookup selectivity caveats')])
                if validate: validate(result)
                return result
            return super().generate(contract,task,cancel,validate)
    class Quota(SessionSources):
        def search(self, query):
            if self.searches:
                self.searches.append(query)
                raise AppError('YOUTUBE_QUOTA_OR_ACCESS','Check YouTube quota before retrying.',503)
            return super().search(query)
    settings=Settings(data=tmp_path); provider=Quota()
    with TestClient(create_app(settings,MissingFacet(available=1),DurationSpeech(settings),provider)) as client:
        lid=client.post('/api/lessons',json=request(300)).json()['id']
        # The focused search still runs with the planner's query; a quota error
        # there finishes the lesson with its ready video and an actionable note,
        # instead of failing it.
        final=wait_for(client,lid)
        assert final['job']['error'] is None
        assert 'selectivity caveats' in provider.searches[-1] and len(provider.searches)==2
        assert final['planning']['missing_coverage'][0]['missing_facets']==['caveat']
        assert final['shorts'][0]['status']=='ready'
        assert final['planning']['completion_reason']=='source_limit'
        assert 'Check YouTube quota' in final['planning']['completion_detail']


def test_source_cache_hits_are_separate_from_provider_calls(tmp_path):
    import hashlib
    from app.youtube import queries
    settings=Settings(data=tmp_path,youtube_key='synthetic-key')
    app=create_app(settings,StubModel(),StubSpeech(settings))
    req=request(300); query=queries(req['goal'],req['prior_knowledge'])[0]
    provider=StubYouTube(); candidate=provider.search(query)[0]
    src=provider.transcript(candidate,threading.Event())
    # The lesson ends short and uses its second search; cache that query too so
    # this test stays offline (the synthetic key must never reach Google).
    for q in queries(req['goal'],req['prior_knowledge']):
        key=hashlib.sha256(('youtube-search-v2:'+q.lower()).encode()).hexdigest()
        app.state.store.cache_put(key,[candidate])
    key=hashlib.sha256((f"youtube-caption-v2:supadata:{candidate['video_id']}:en").encode()).hexdigest()
    app.state.store.cache_put(key,{'source':src.model_dump()})
    with TestClient(app) as client:
        lid=client.post('/api/lessons',json=req).json()['id']
        final=wait_for(client,lid)
        ledger=final['acquisition']
        assert final['job']['status']=='complete'
        assert ledger['search_cache_hits']==2 and ledger['transcript_cache_hits']==1
        assert ledger['search_provider_calls']==ledger['transcript_provider_calls']==0
        assert len(ledger['rounds'])==2 and len(ledger['tried_video_ids'])==1


def test_started_http_and_quota_accounting_survives_actual_provider_errors(monkeypatch,tmp_path):
    import httpx
    import app.sources as source_module
    import app.youtube as youtube_module
    def google(path,params):
        if path=='search':
            return httpx.Response(200,json={'items':[{'id':{'videoId':'dQw4w9WgXcQ'},'snippet':{'title':'Synthetic test','channelTitle':'Test'}}]})
        return httpx.Response(200,json={'items':[{'id':'dQw4w9WgXcQ','contentDetails':{'duration':'PT8M'}}]})
    monkeypatch.setattr(source_module,'youtube_get',google)
    monkeypatch.setattr(youtube_module,'SUPADATA_INTERVAL',0)
    monkeypatch.setattr(youtube_module.httpx,'get',lambda *a,**k:httpx.Response(402,json={}))
    settings=Settings(data=tmp_path,youtube_key='test-key',supadata_key='test-key')
    with TestClient(create_app(settings,StubModel(),StubSpeech(settings))) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        failed=wait_for(client,lid,'failed')
        ledger=failed['acquisition']
        assert failed['job']['error']['code']=='TRANSCRIPT_ACCESS_REQUIRED'
        assert ledger['youtube_http_calls']==2 and ledger['youtube_quota_units']==101
        assert ledger['transcript_http_calls']==1
        assert ledger['search_provider_calls']==ledger['transcript_provider_calls']==1
        assert len(ledger['tried_video_ids'])==1
        assert client.post(f'/api/lessons/{lid}/retry',json={}).status_code==202
        final=wait_for(client,lid,'failed')
        assert final['acquisition']['transcript_http_calls']==1
        assert final['acquisition']['youtube_http_calls']==4
        assert final['acquisition']['youtube_quota_units']==202


def test_unfit_optional_curriculum_is_deferred_without_touching_ready_media(tmp_path):
    class TooLongClosing(DurationSpeech):
        def synthesize(self, units, key, cancel):
            # Once the first core is published, pretend this voice cannot fit
            # another candidate even after one repair. Never publish that WAV.
            if len(self.durations):
                raise AppError('SPEECH_DURATION','This unpublished script cannot fit the remaining time.',422)
            return super().synthesize(units,key,cancel)
    settings=Settings(data=tmp_path); model=SessionModel()
    with TestClient(create_app(settings,model,TooLongClosing(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request(60)).json()['id']
        final=wait_for(client,lid)
        assert len(final['shorts'])==1 and final['shorts'][0]['status']=='ready'
        assert 'closing' in final['planning']['deferred_concept_ids']
        assert final['planning']['completion_reason']=='budget_fit'
        assert final['duration_ledger']['shortfall_ms']>0
        assert all(s['measured_duration_ms']<=40000 for s in final['shorts'])


def test_generation_limit_can_finish_a_valid_shorter_session(tmp_path):
    settings=Settings(data=tmp_path); store=Store(settings.data)
    try:
        lesson=lesson_for(1200,shorts=[Short(id='ready',objective='Published useful outcome',status='ready',measured_duration_ms=30000)])
        lesson.planning.expansion_attempts=lesson.planning.expansion_limit
        store.save(lesson)
        jobs=Jobs(store,SessionModel(),DurationSpeech(settings),settings,SessionSources())
        # Avoid acquisition for this direct checkpoint test by injecting the
        # already acquired valid synthetic transcript like persisted recovery.
        provider=SessionSources(); lesson.sources=[provider.transcript(provider.search('index')[0],threading.Event())]
        store.save(lesson); jobs.cancel_flags[lesson.id]=threading.Event()
        assert asyncio.run(jobs.advance(lesson.id)) is False
        final=store.lesson(lesson.id)
        assert final.job.status=='complete' and final.planning.completion_reason=='generation_limit'
        assert final.shorts[0].id=='ready' and final.shorts[0].measured_duration_ms==30000
    finally: store.close()


def test_final_gate_enforces_original_and_extra_pools_independently(tmp_path):
    settings=Settings(data=tmp_path); store=Store(settings.data)
    try:
        lesson=lesson_for(60,shorts=[Short(id='core',objective='Core',status='ready',measured_duration_ms=70000)],extra_allowance_ms=40000)
        jobs=Jobs(store,StubModel(),StubSpeech(settings),settings)
        with pytest.raises(AppError,match='wrong allowance pool'):
            jobs.complete(lesson)
    finally: store.close()


def test_cancellation_save_guard_retains_terminal_decision_and_sequences(tmp_path):
    settings=Settings(data=tmp_path); store=Store(settings.data)
    try:
        lesson=lesson_for(shorts=[Short(id='a',objective='Pending')]); store.save(lesson)
        stale=store.lesson(lesson.id)
        lesson.status='cancelled'; lesson.job.status='cancelled'; store.save(lesson)
        stale.planning.model_call_units=3; stale.job.status='running'
        stale.shorts[0].status='ready'; stale.shorts[0].measured_duration_ms=12000
        store.save(stale)
        saved=store.lesson(lesson.id)
        assert saved.job.status=='cancelled' and saved.shorts[0].status=='cancelled'
        assert saved.planning.model_call_units==3
        assert saved.job.event_sequence==3
    finally: store.close()


def test_outcome_with_nothing_new_is_skipped_and_lesson_finishes(tmp_path):
    # Real failure: thin sources, the planner re-taught one idea, and the third
    # retelling failed the whole lesson. Skip it; never pad or touch ready media.
    class Repeats(SessionModel):
        def generate(self, contract, task, cancel, validate=None):
            if contract is ModelStoryboard and self.draft_tasks and task['teaching']['role'] != 'recap':
                self.draft_tasks.append(task)
                raise AppError('NO_NEW_CONTENT', 'The sources had nothing new to add for this storyboard.', 422)
            return super().generate(contract, task, cancel, validate)
    settings=Settings(data=tmp_path); model=Repeats()
    with TestClient(create_app(settings,model,DurationSpeech(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        final=wait_for(client,lid)
        assert final['job']['status']=='complete' and final['job']['error'] is None
        assert all(s['status']=='ready' for s in final['shorts'])
        roles=[s['curriculum_role'] for s in final['shorts']]
        assert roles[0]=='core' and roles[-1]=='closing' and len(roles)==2
        skipped=final['metrics']['repeat_skipped_shorts']
        assert skipped>=1 and len(final['planning']['deferred_concept_ids'])==skipped
        assert final['planning']['completion_reason']=='coverage_exhausted'
        assert 'repeat' in final['planning']['completion_detail']
        assert final['duration_ledger']['shortfall_ms']>0
        # Expansion continued (to fill the time) but stopped once skips kept recurring.
        # Stops at the 3rd skip; already-queued points from that batch are tried once each.
        assert 3<=skipped<=6 and len(final['planning']['nothing_new'])==skipped
        extensions=[t for t in model.plan_tasks if t['phase']=='extension']
        assert extensions and extensions[0]['nothing_new']
        # After two skips the planner was told the sources were exhausted.
        assert extensions[-1]['sources_exhausted'] is True


def test_optional_requested_short_still_reports_no_new_content(tmp_path):
    from app.jobs import Jobs
    settings=Settings(data=tmp_path); store=Store(settings.data)
    try:
        jobs=Jobs(store,SessionModel(),DurationSpeech(settings),settings,SessionSources())
        lesson=lesson_for(300,shorts=[Short(id='extra',objective='Show another supported example',optional=True)])
        assert not jobs.skip_repeated(lesson,lesson.shorts[0],threading.Event())
        assert [s.id for s in lesson.shorts]==['extra'] and lesson.planning.completion_reason is None
    finally:
        store.close()


def test_failed_optional_expansion_finishes_lesson_with_committed_recap(tmp_path):
    class ExpansionFails(SessionModel):
        def generate(self, contract, task, cancel, validate=None):
            if contract is LessonPlan and task.get('phase') == 'extension':
                self.plan_tasks.append(task)
                raise AppError('MODEL_DATA_INVALID', "The local model's lesson plan failed validation after one repair.", 422)
            return super().generate(contract, task, cancel, validate)
    settings=Settings(data=tmp_path); model=ExpansionFails()
    with TestClient(create_app(settings,model,DurationSpeech(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        final=wait_for(client,lid)
        assert final['job']['status']=='complete' and final['job']['error'] is None
        assert [s['curriculum_role'] for s in final['shorts']][-1]=='closing'
        assert all(s['status']=='ready' for s in final['shorts'])
        assert final['planning']['completion_reason']=='generation_limit'
        assert final['metrics']['expansion_plan_failures']==1
        assert sum(t.get('phase')=='extension' for t in model.plan_tasks)==1


def test_extension_batch_drops_extra_recap_and_items_built_on_it(tmp_path):
    class ExtraRecap(SessionModel):
        def generate(self, contract, task, cancel, validate=None):
            if contract is not LessonPlan or task.get('phase') != 'extension':
                return super().generate(contract, task, cancel, validate)
            plan = super().generate(contract, task, cancel, None)
            if plan.objectives:
                first = plan.objectives[0]
                plan.objectives.insert(0, first.model_copy(update={'concept_id': 'extra_recap', 'teaching_role': 'recap',
                    'curriculum_role': 'closing', 'learning_outcome': 'Recall the earlier fixture outcomes', 'title': 'Recap again'}))
                plan.objectives.append(first.model_copy(update={'concept_id': 'built_on_recap', 'dependency_ids': ['extra_recap'],
                    'learning_outcome': 'Apply the extra recap', 'title': 'Built on recap'}))
            if validate:
                validate(plan)
            return plan
    settings=Settings(data=tmp_path); model=ExtraRecap()
    with TestClient(create_app(settings,model,DurationSpeech(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        final=wait_for(client,lid)
        assert final['job']['status']=='complete'
        concepts=[s['concept_id'] for s in final['shorts']]
        assert 'extra_recap' not in concepts and 'built_on_recap' not in concepts
        assert sum(s['curriculum_role']=='closing' for s in final['shorts'])==1
        assert any(s['curriculum_role']=='extension' for s in final['shorts'])


def test_extension_with_a_repeated_title_is_dropped_but_distinct_titles_stay(tmp_path):
    class SameTitle(SessionModel):
        def generate(self, contract, task, cancel, validate=None):
            if contract is not LessonPlan or task.get('phase') != 'extension':
                return super().generate(contract, task, cancel, validate)
            plan = super().generate(contract, task, cancel, None)
            if plan.objectives:
                # Real failure: a new outcome under an already-used title.
                plan.objectives[0] = plan.objectives[0].model_copy(update={'title': 'Explore key lookup'})
            if validate:
                validate(plan)
            return plan
    settings=Settings(data=tmp_path); model=SameTitle()
    with TestClient(create_app(settings,model,DurationSpeech(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        final=wait_for(client,lid)
        titles=[o['title'] for o in final['objectives']]
        assert titles.count('Explore key lookup')==1
        assert any(o['curriculum_role']=='extension' for o in final['objectives'])



def test_exhausted_sources_trigger_one_related_search_then_planning_continues(tmp_path):
    # User decision: keep videos coming by fetching new sources, not padding.
    from app.contracts import CoverageGap
    class SearchesWhenExhausted(SessionModel):
        searched = False
        def generate(self, contract, task, cancel, validate=None):
            if contract is LessonPlan and task.get('sources_exhausted'):
                self.plan_tasks.append(task)
                self.searched = True
                plan = LessonPlan(sufficient_evidence=True, reason='Current sources only repeat covered points.', objectives=[],
                                  missing_coverage=[CoverageGap(outcome='Related material for the remaining session time',
                                                                missing_facets=[], query_intent='database index maintenance')])
                if validate:
                    validate(plan)
                return plan
            if (contract is ModelStoryboard and not self.searched and self.draft_tasks
                    and task['teaching']['role'] != 'recap'):
                self.draft_tasks.append(task)
                raise AppError('NO_NEW_CONTENT', 'The sources had nothing new to add for this storyboard.', 422)
            return super().generate(contract, task, cancel, validate)
    class NewVideoPerSearch(SessionSources):
        def search(self, query):
            super().search(query)
            return [{'video_id': ['dQw4w9WgXcQ', 'aBcDeFgHiJk'][len(self.searches)-1], 'title': 'Test-only YouTube source', 'channel': 'Test channel'}]
    settings=Settings(data=tmp_path); model=SearchesWhenExhausted()
    with TestClient(create_app(settings,model,DurationSpeech(settings),NewVideoPerSearch())) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        final=wait_for(client,lid)
        assert final['job']['status']=='complete'
        rounds=final['acquisition']['rounds']
        assert len(rounds)==2 and rounds[1]['query'].startswith('database index maintenance')
        assert final['planning']['repeat_skips_since_sources']==0
        assert final['metrics']['repeat_skipped_shorts']==2
        # Planning resumed after the search and produced new ready extension shorts.
        assert sum(s['curriculum_role']=='extension' and s['status']=='ready' for s in final['shorts'])>=1
        assert final['planning']['completion_reason']!='coverage_exhausted'


def test_contained_titles_are_repeats_but_one_word_titles_do_not_block():
    from app.jobs import contained_title
    assert contained_title('Standing Up', 'Standing Up from Ice')
    assert contained_title('Standing Up from Ice', 'Standing Up')
    assert not contained_title('Balance', 'Balance on One Foot')
    assert not contained_title('Safe Falling Technique', 'Safe Falling and Recovery')


def test_short_lesson_searches_again_even_without_a_model_query(tmp_path):
    # Real run: the planner returned no items and no query, so the lesson
    # stopped at 55% with a search still unused.
    class NoQuery(SessionModel):
        def generate(self, contract, task, cancel, validate=None):
            if contract is LessonPlan and task.get('phase') == 'extension':
                self.plan_tasks.append(task)
                plan = LessonPlan(sufficient_evidence=True, reason='Nothing new in these sources.', objectives=[])
                if validate:
                    validate(plan)
                return plan
            return super().generate(contract, task, cancel, validate)
    class Recorder(SessionSources):
        def search(self, query):
            super().search(query)
            return [] if len(self.searches) > 1 else [{'video_id': 'dQw4w9WgXcQ', 'title': 'Test-only YouTube source', 'channel': 'Test channel'}]
    settings=Settings(data=tmp_path); sources=Recorder()
    with TestClient(create_app(settings,NoQuery(),DurationSpeech(settings),sources)) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        final=wait_for(client,lid)
        assert final['job']['status']=='complete'
        assert len(sources.searches)==2 and len(final['acquisition']['rounds'])==2
        assert final['planning']['completion_reason']=='source_limit'
        assert 'search limit' in final['planning']['completion_detail']



def test_failed_extra_search_finishes_lesson_with_ready_videos(tmp_path):
    class SearchBreaksLater(SessionSources):
        def search(self, query):
            if self.searches:
                raise AppError('SOURCE_SEARCH_FAILED', 'YouTube search failed. Check the server API key, then retry.', 503)
            return super().search(query)
    settings=Settings(data=tmp_path); model=SessionModel(available=1)
    with TestClient(create_app(settings,model,DurationSpeech(settings),SearchBreaksLater())) as client:
        lid=client.post('/api/lessons',json=request(1200)).json()['id']
        final=wait_for(client,lid)
        assert final['job']['status']=='complete' and final['job']['error'] is None
        assert final['shorts'] and all(s['status']=='ready' for s in final['shorts'])
        assert final['planning']['completion_reason']=='source_limit'
        assert 'YouTube search failed' in final['planning']['completion_detail']
        assert final['metrics']['expansion_search_failures']==1


def test_item_built_on_a_dropped_repeat_is_dropped_not_fatal(tmp_path):
    # Real failure: a kept item depended on a dropped repeat, so the whole
    # extension batch was rejected twice and the lesson stopped expanding.
    class DependsOnRepeat(SessionModel):
        def generate(self, contract, task, cancel, validate=None):
            if contract is not LessonPlan or task.get('phase') != 'extension':
                return super().generate(contract, task, cancel, validate)
            plan = super().generate(contract, task, cancel, None)
            if len(plan.objectives) >= 2:
                repeat, built = plan.objectives[0], plan.objectives[1]
                plan.objectives[0] = repeat.model_copy(update={'title': 'Explore key lookup'})
                plan.objectives[1] = built.model_copy(update={'dependency_ids': [repeat.concept_id]})
                self.dropped = {repeat.concept_id, built.concept_id}
            if validate:
                validate(plan)
            return plan
    settings=Settings(data=tmp_path); model=DependsOnRepeat()
    with TestClient(create_app(settings,model,DurationSpeech(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        final=wait_for(client,lid)
        assert final['job']['status']=='complete' and 'expansion_plan_failures' not in final['metrics']
        concepts={o['concept_id'] for o in final['objectives']}
        assert not concepts & model.dropped
        assert any(o['curriculum_role']=='extension' for o in final['objectives'])


class FailsTopic(SessionModel):
    """Storyboards for one fixture outcome fail; fallback can be made to succeed."""
    def __init__(self, bad='Explain leaf traversal', code='MODEL_DATA_INVALID', fallback_ok=False):
        super().__init__()
        self.bad, self.code, self.fallback_ok, self.bad_templates = bad, code, fallback_ok, []
    def generate(self, contract, task, cancel, validate=None):
        if contract is ModelStoryboard and task['teaching']['outcome'] == self.bad:
            self.bad_templates.append(task['template'])
            if not (self.fallback_ok and task['template'] == 'key_fact'):
                self.draft_tasks.append(task)
                raise AppError(self.code, 'Chart value must match a number in its own cited passage.', 422)
        return super().generate(contract, task, cancel, validate)


def test_short_that_keeps_failing_is_skipped_and_the_lesson_finishes(tmp_path):
    settings=Settings(data=tmp_path); model=FailsTopic()
    with TestClient(create_app(settings,model,DurationSpeech(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        final=wait_for(client,lid)
        assert final['job']['status']=='complete' and final['job']['error'] is None
        assert all(s['status']=='ready' for s in final['shorts']) and len(final['shorts'])>=2
        assert 'Explore leaf traversal' not in [s['objective'] for s in final['shorts']]
        assert final['planning']['skipped_points']==['Explore leaf traversal (its draft failed the accuracy checks)']
        assert final['metrics']['failed_shorts_skipped']==1 and final['metrics']['simpler_visual_fallbacks']==1
        # Tried its planned visual, then the simple key-fact card, then skipped.
        assert model.bad_templates==['process','key_fact']


def test_simpler_visual_rescues_a_short(tmp_path):
    settings=Settings(data=tmp_path); model=FailsTopic(fallback_ok=True)
    with TestClient(create_app(settings,model,DurationSpeech(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        final=wait_for(client,lid)
        rescued=next(s for s in final['shorts'] if s['objective']=='Explore leaf traversal')
        assert rescued['status']=='ready' and final['planning']['skipped_points']==[]
        assert final['metrics']['simpler_visual_fallbacks']==1


def test_review_rejection_skips_without_a_visual_retry(tmp_path):
    settings=Settings(data=tmp_path); model=FailsTopic(code='UNSUPPORTED_CLAIM')
    with TestClient(create_app(settings,model,DurationSpeech(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        final=wait_for(client,lid)
        assert final['job']['status']=='complete'
        assert final['planning']['skipped_points']==['Explore leaf traversal (the source review could not confirm its claims)']
        assert model.bad_templates==['process'] and 'simpler_visual_fallbacks' not in final['metrics']


def test_lesson_with_nothing_makeable_still_reports_the_real_error(tmp_path):
    settings=Settings(data=tmp_path); model=FailsTopic(bad='Explain key lookup'); model.available=1
    with TestClient(create_app(settings,model,DurationSpeech(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request(60)).json()['id']
        failed=wait_for(client,lid,'failed')
        assert failed['job']['error']['code']=='MODEL_DATA_INVALID' and failed['shorts']


def test_three_skips_in_a_row_stop_expansion(tmp_path):
    class AllExtensionsFail(SessionModel):
        def generate(self, contract, task, cancel, validate=None):
            if contract is ModelStoryboard and task['teaching']['plan'] and task['teaching']['plan']['curriculum_role']=='extension':
                self.draft_tasks.append(task)
                raise AppError('MODEL_DATA_INVALID', 'Draft failed.', 422)
            return super().generate(contract, task, cancel, validate)
    settings=Settings(data=tmp_path); model=AllExtensionsFail()
    with TestClient(create_app(settings,model,DurationSpeech(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request(600)).json()['id']
        final=wait_for(client,lid)
        assert final['job']['status']=='complete'
        assert final['planning']['completion_reason']=='generation_limit'
        assert 'in a row' in final['planning']['completion_detail']
        assert final['metrics']['failed_shorts_skipped']>=3
        assert sum(t['phase']=='extension' for t in model.plan_tasks)<=2


def test_skipping_drops_queued_dependents_but_keeps_the_recap(tmp_path):
    from app.jobs import Jobs
    settings=Settings(data=tmp_path); store=Store(settings.data)
    try:
        jobs=Jobs(store,SessionModel(),DurationSpeech(settings),settings,SessionSources())
        objectives=[Objective(concept_id=c,title=f'Point {c}',template='process',prerequisites=[],dependency_ids=d,curriculum_role=r)
                    for c,d,r in [('a',[],'core'),('b',['a'],'core'),('c',[],'core'),('recap',['a','b','c'],'closing')]]
        lesson=lesson_for(300,objectives=objectives,shorts=[Short(id=c,objective=f'Point {c}',concept_id=c,curriculum_role=r)
                    for c,r in [('a','core'),('b','core'),('c','core'),('recap','closing')]])
        assert jobs.skip_failed(lesson,lesson.shorts[0],AppError('UNSUPPORTED_CLAIM','x',422),threading.Event())
        assert [s.id for s in lesson.shorts]==['c','recap']
        assert lesson.planning.skipped_points==['Point a (the source review could not confirm its claims)',
                                                'Point b (the source review could not confirm its claims)']
        # Optional, user-requested extras are never silently skipped.
        extra=Short(id='extra',objective='Show another example',optional=True); lesson.shorts.append(extra)
        assert not jobs.skip_failed(lesson,extra,AppError('MODEL_DATA_INVALID','x',422),threading.Event())
    finally:
        store.close()



def test_too_long_short_with_time_left_is_skipped_and_expansion_continues(tmp_path):
    # Real run: one slightly-too-long extension stopped the lesson at 77% with 68 s free.
    class OneTooLong(DurationSpeech):
        fails = 0
        def synthesize(self, units, key, cancel):
            # Three core shorts publish first; fail the next (first extension) draft and its repair.
            if len(self.durations) == 3 and self.fails < 2:
                self.fails += 1
                raise AppError('SPEECH_DURATION', 'This unpublished script cannot fit the remaining time.', 422)
            return super().synthesize(units, key, cancel)
    settings=Settings(data=tmp_path); model=SessionModel()
    with TestClient(create_app(settings,model,OneTooLong(settings),SessionSources())) as client:
        lid=client.post('/api/lessons',json=request()).json()['id']
        final=wait_for(client,lid)
        assert final['job']['status']=='complete'
        skipped=final['planning']['skipped_points']
        assert len(skipped)==1 and skipped[0].endswith('(its narration could not fit the time)')
        assert not skipped[0].startswith('Recap')
        assert final['planning']['completion_reason']!='budget_fit' or final['duration_ledger']['shortfall_ms']==0
        assert sum(s['curriculum_role']=='extension' and s['status']=='ready' for s in final['shorts'])>=1
