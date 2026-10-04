"""Readiness/scheduling fixtures: no live provider requests or sleep-based races."""
import asyncio
import json
import wave
from pathlib import Path

import pytest
from app.config import Settings
from app.contracts import Job, LearningRequest, Lesson, Short
from app.errors import AppError, Cancelled
from app.jobs import Jobs
from app.readiness import contiguous_media, required_media, simulate_one_pass, snapshot_readiness
from app.store import Store
from test_core import StubModel, StubSpeech, StubYouTube

ROOT = Path(__file__).resolve().parents[2]


def ready_short(id='one'):
    body = json.loads((ROOT / 'fixtures/storyboard-lookup-playback.json').read_text())
    body.update(id=id, audio_path='a' * 64 + '.wav')
    return Short.model_validate(body)


def lesson_with(shorts):
    return Lesson(id='lesson_fixture', request={'goal':'Fixture goal', 'request_id':'fixture-request-id'},
                  sources=[], shorts=shorts, short_ids=[s.id for s in shorts],
                  job=Job(id='job_fixture', lesson_id='lesson_fixture', created_at=0, updated_at=0))


def audio_file(settings, short):
    with wave.open(str(settings.data / 'audio' / short.audio_path), 'wb') as file:
        file.setnchannels(1); file.setsampwidth(2); file.setframerate(24000)
        file.writeframes(b'\0' * (48 * short.measured_duration_ms))


@pytest.mark.parametrize('position,expected', [(0, 60000), (5000, 55000), (30000, 30000), (90000, 30000), (-1000, 60000)])
def test_contiguous_media_clamps_position_and_stops_at_gap(position, expected):
    shorts = [ready_short('one'), ready_short('two'), Short(id='gap', objective='Not ready'), ready_short('distant')]
    assert contiguous_media(shorts, 'one', position) == expected
    assert contiguous_media(shorts, 'gap') == 0
    assert contiguous_media(shorts, 'distant', 10000) == 20000


def test_pause_replay_loop_and_jump_do_not_bank_extra_media_or_practice():
    shorts = [ready_short('one'), ready_short('two')]
    shorts[0].question_required = True
    # Pausing retains position; replay/loop resets the remaining media, never adds a loop.
    assert contiguous_media(shorts, 'one', 12000) == contiguous_media(shorts, 'one', 12000) == 48000
    assert contiguous_media(shorts, 'one', 0) == 60000
    assert contiguous_media(shorts, 'two', 1000) == 29000
    assert contiguous_media(shorts, 'one', 20000) == 40000
    assert contiguous_media(shorts, 'one', ready_ids={'two'}) == 0


@pytest.mark.parametrize('interval,stalls', [(5, [0] * 6), (10, [0] * 6), (15, [0, 5, 5, 5, 5, 5])])
def test_fixture_production_rates_and_cumulative_sequential_stalls(interval, stalls):
    result = simulate_one_pass([interval * (i + 1) for i in range(6)], [10000] * 6)
    assert result['startup_seconds'] == interval
    assert result['stalls_seconds'] == stalls
    assert all(value >= 10000 for value in result['ready_ahead_ms'])


def test_experimental_buffer_trades_startup_for_lead_not_a_guarantee():
    publications = [15 * (i + 1) for i in range(20)]
    immediate = simulate_one_pass(publications, [10000] * 20)
    buffered = simulate_one_pass(publications, [10000] * 20, 60000)
    assert buffered['startup_seconds'] == 90
    assert sum(buffered['stalls_seconds']) < sum(immediate['stalls_seconds'])
    assert sum(buffered['stalls_seconds']) > 0  # Slow production eventually consumes the lead.
    shorter = simulate_one_pass([5, 10], [10000, 10000], 60000)
    assert shorter['experimental_buffer_reached_seconds'] is None
    assert shorter['startup_seconds'] == 10


def test_snapshot_checks_durable_audio_and_essential_assets(tmp_path):
    settings = Settings(data=tmp_path); store = Store(settings.data)
    jobs = Jobs(store, StubModel(), StubSpeech(settings), settings, StubYouTube())
    try:
        short = ready_short(); lesson = lesson_with([short]); audio_file(settings, short)
        assert snapshot_readiness(lesson, settings.data, jobs.assets).ready_short_ids == ['one']
        (settings.data / 'audio' / short.audio_path).unlink()
        summary = snapshot_readiness(lesson, settings.data, jobs.assets)
        assert summary.missing_media_short_ids == ['one'] and summary.initial_contiguous_media_ms == 0
        audio_file(settings, short)
        # Image payload comes from the validated mixed-media fixture.
        from app.contracts import ImageScene
        payload = json.loads((ROOT / 'fixtures/mixed-visuals.json').read_text())
        short.scenes = [ImageScene.model_validate(payload['shorts'][2]['scenes'][0])]
        required_media(short, settings.data, jobs.assets)
        asset = jobs.assets.get(short.scenes[0].payload.asset_id)
        (settings.data / 'assets' / asset.managed_filename).unlink()
        assert snapshot_readiness(lesson, settings.data, jobs.assets).ready_short_ids == []
        jobs.assets.install_bundled()
        assert snapshot_readiness(lesson, settings.data, jobs.assets).ready_short_ids == ['one']
    finally:
        store.close()


def test_fifo_turns_prevent_new_arrival_starvation_and_are_bounded(tmp_path):
    settings = Settings(data=tmp_path, queue_size=4); store = Store(settings.data)
    jobs = Jobs(store, StubModel(), StubSpeech(settings), settings, StubYouTube())
    turns, counts, arrivals = [], {}, []
    async def exercise():
        a = jobs.create(LearningRequest(goal='Long lesson A', request_id='long-lesson-a')).id
        b = jobs.create(LearningRequest(goal='Long lesson B', request_id='long-lesson-b')).id
        finished = asyncio.Event()
        async def advance(lid):
            turns.append(lid); counts[lid] = counts.get(lid, 0) + 1
            if len(arrivals) < 6 and len(jobs.active) < settings.queue_size:
                arrivals.append(jobs.create(LearningRequest(goal='New arrival', request_id=f'arrival-{len(arrivals):03}')).id)
            again = lid in {a, b} and counts[lid] < 4
            if not again:
                lesson = store.lesson(lid); lesson.job.status = 'complete'; store.save(lesson)
            if counts.get(a) == 4 and counts.get(b) == 4: finished.set()
            return again
        jobs.advance = advance
        jobs.task = asyncio.create_task(jobs.worker())
        await finished.wait()
        await jobs.stop()
        for lid in (a, b):
            positions = [i for i, value in enumerate(turns) if value == lid]
            assert len(positions) == 4
            assert max(y - x for x, y in zip(positions, positions[1:])) <= settings.queue_size
        assert turns[:2] == [a, b] and arrivals
        assert store.lesson(a).metrics['worker_turns'] == 4
        with pytest.raises(AppError, match='shutting down'): jobs.reserve('after-shutdown')
    try: asyncio.run(exercise())
    finally: store.close()


def test_queue_backpressure_and_duplicate_work(tmp_path):
    settings = Settings(data=tmp_path, queue_size=2); store = Store(settings.data)
    jobs = Jobs(store, StubModel(), StubSpeech(settings), settings, StubYouTube())
    try:
        jobs.reserve('one'); jobs.enqueue('one'); jobs.reserve('two'); jobs.enqueue('two')
        with pytest.raises(AppError) as error: jobs.reserve('three')
        assert error.value.code == 'QUEUE_FULL'
        with pytest.raises(AppError) as error: jobs.reserve('one')
        assert error.value.code == 'JOB_ACTIVE'
    finally: store.close()


@pytest.mark.parametrize('stage', ['acquisition', 'planning', 'draft', 'review', 'speech', 'asset'])
def test_cancellation_at_stage_boundaries_never_publishes_obsolete_output(tmp_path, stage):
    settings = Settings(data=tmp_path); store = Store(settings.data)
    class Model(StubModel):
        def generate(self, contract, task, cancel, validate=None):
            target = {'LessonPlan': 'planning', 'ModelStoryboard': 'draft', 'SupportCheck': 'review'}.get(contract.__name__)
            if target == stage: jobs.cancel(lid)
            return super().generate(contract, task, cancel, validate)
    class Speech(StubSpeech):
        def synthesize(self, units, key, cancel):
            if stage == 'speech': jobs.cancel(lid)
            return super().synthesize(units, key, cancel)
    class YouTube(StubYouTube):
        def transcript(self, candidate, cancel):
            if stage == 'acquisition': jobs.cancel(lid)
            return super().transcript(candidate, cancel)
    jobs = Jobs(store, Model(), Speech(settings), settings, YouTube())
    async def exercise():
        nonlocal lid
        lid = jobs.create(LearningRequest(goal='Understand database indexes', request_id='cancel-stage-request')).id
        if stage == 'asset':
            reference = jobs.assets.reference
            def cancelled_reference(*args):
                reference(*args); jobs.cancel(lid)
            jobs.assets.reference = cancelled_reference
        with pytest.raises(Cancelled): await jobs.advance(lid)
        saved = store.lesson(lid)
        assert saved.job.status == 'cancelled'
        assert not any(s.status == 'ready' for s in saved.shorts)
        # A stale provider copy cannot resurrect cancelled work.
        stale = saved.model_copy(deep=True); stale.job.status = 'running'; store.save(stale)
        assert store.lesson(lid).job.status == 'cancelled'
    lid = ''
    try: asyncio.run(exercise())
    finally: store.close()


def test_metrics_and_retry_retain_first_publication_and_ready_content(tmp_path):
    settings = Settings(data=tmp_path); store = Store(settings.data)
    jobs = Jobs(store, StubModel(), StubSpeech(settings), settings, StubYouTube())
    async def exercise():
        lesson = jobs.create(LearningRequest(goal='Understand database indexes', request_id='metrics-request')).id
        assert await jobs.advance(lesson)
        saved = store.lesson(lesson); first = saved.metrics['first_playable_monotonic_seconds']
        assert saved.shorts[0].status == 'ready' and saved.job.status != 'complete'
        assert saved.metrics['search_seconds'] >= 0 and saved.metrics['transcript_seconds'] >= 0
        assert saved.metrics['plan_seconds'] >= 0 and saved.metrics['draft_seconds'] >= 0
        assert saved.metrics['review_seconds'] >= 0 and saved.metrics['synthesize_seconds'] >= 0
        assert saved.shorts[0].timings['audio_cache_hit'] == 0
        assert not any(k.startswith('waiting_before') for k in saved.metrics)
        store.recover(); interrupted = store.lesson(lesson)
        assert interrupted.job.status == 'interrupted' and interrupted.shorts[0].status == 'ready'
        # Direct fixture driver releases the reservation just as the worker does.
        jobs.active.clear(); jobs.cancel_flags.clear()
        resumed = jobs.retry(lesson)
        assert resumed.short_ids == saved.short_ids
        assert await jobs.advance(lesson)
        after = store.lesson(lesson)
        assert after.metrics['first_playable_monotonic_seconds'] == first
        assert after.shorts[0].model_dump() == saved.shorts[0].model_dump()
    try: asyncio.run(exercise())
    finally: store.close()
