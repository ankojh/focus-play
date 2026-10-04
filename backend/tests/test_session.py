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
        assert final['planning']['completion_reason'] == 'coverage_exhausted'
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
        failed=wait_for(client,lid,'failed')
        assert failed['job']['error']['code']=='YOUTUBE_QUOTA_OR_ACCESS'
        assert 'selectivity caveats' in provider.searches[-1]
        assert failed['planning']['missing_coverage'][0]['missing_facets']==['caveat']
        assert failed['shorts'][0]['status']=='ready'
        ledger=failed['acquisition']
        assert client.post(f'/api/lessons/{lid}/retry',json={}).status_code==202
        final=wait_for(client,lid)
        assert final['planning']['completion_reason']=='source_limit'
        assert final['acquisition']==ledger and len(provider.searches)==2
        assert final['shorts'][0]==failed['shorts'][0]


def test_source_cache_hits_are_separate_from_provider_calls(tmp_path):
    import hashlib
    from app.youtube import queries
    settings=Settings(data=tmp_path,youtube_key='synthetic-key')
    app=create_app(settings,StubModel(),StubSpeech(settings))
    req=request(300); query=queries(req['goal'],req['prior_knowledge'])[0]
    provider=StubYouTube(); candidate=provider.search(query)[0]
    src=provider.transcript(candidate,threading.Event())
    key=hashlib.sha256(('youtube-search-v2:'+query.lower()).encode()).hexdigest()
    app.state.store.cache_put(key,[candidate])
    key=hashlib.sha256((f"youtube-caption-v2:supadata:{candidate['video_id']}:en").encode()).hexdigest()
    app.state.store.cache_put(key,{'source':src.model_dump()})
    with TestClient(app) as client:
        lid=client.post('/api/lessons',json=req).json()['id']
        final=wait_for(client,lid)
        ledger=final['acquisition']
        assert ledger['search_cache_hits']==ledger['transcript_cache_hits']==1
        assert ledger['search_provider_calls']==ledger['transcript_provider_calls']==0
        assert len(ledger['rounds'])==len(ledger['tried_video_ids'])==1


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
