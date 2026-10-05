"""Real job orchestration with fixture transports; preserves old ready provenance."""
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import AppError
from app.main import create_app
from test_core import StubModel, StubSpeech, StubYouTube, request_for, wait_for


def test_audio_repair_needs_neither_old_llm_nor_source_acquisition(tmp_path):
    settings = Settings(data=tmp_path)
    model, youtube = StubModel(), StubYouTube()
    app = create_app(settings, model, StubSpeech(settings), youtube)
    with TestClient(app) as client:
        lesson = client.post('/api/lessons', json=request_for(None, 'media-identity-repair')).json()
        ready = wait_for(client, lesson['id'])
        original = ready['shorts'][0]
        (settings.data / 'audio' / original['audio_path']).unlink()
        def unavailable(*args): raise AppError('TURBOFIELDFARE_UNAVAILABLE', 'Selected LLM is offline.', 503)
        model.fingerprint = unavailable
        model.generate = unavailable
        youtube.search = unavailable
        youtube.transcript = unavailable
        client.post(f"/api/lessons/{lesson['id']}/retry", json={}).raise_for_status()
        repaired = wait_for(client, lesson['id'])
        assert repaired['provider_settings'] == ready['provider_settings']
        assert repaired['shorts'][0]['provider_settings'] == original['provider_settings']
        assert repaired['shorts'][0]['narration_units'] == original['narration_units']
        assert repaired['shorts'][0]['scenes'] == original['scenes']
        assert repaired['acquisition'] == ready['acquisition']


def test_unfinished_provider_switch_fails_before_sources_and_preserves_identity(tmp_path):
    settings = Settings(data=tmp_path)
    model, youtube = StubModel(), StubYouTube()
    app = create_app(settings, model, StubSpeech(settings), youtube)
    with TestClient(app) as client:
        lesson = client.post('/api/lessons', json=request_for(None, 'unfinished-identity-test')).json()
        ready = wait_for(client, lesson['id'])
        stored = app.state.store.lesson(lesson['id'])
        # Queue genuinely new LLM work, rather than missing-media recovery.
        body = {'kind': 'example', 'added_seconds': 40, 'request_id': 'switch-profile-extra'}
        historical = dict(stored.provider_settings)
        model.fingerprint = lambda: {'provider': 'turbofieldfare', 'model': 'gemma-4-26b-a4b-it', 'runtime_binary_sha256': 'different'}
        client.post(f"/api/lessons/{lesson['id']}/shorts/{stored.shorts[0].id}/explanations", json=body).raise_for_status()
        failed = wait_for(client, lesson['id'], 'failed')
        assert failed['job']['error']['code'] == 'PROVIDER_SETTINGS_MISMATCH'
        assert failed['provider_settings'] == historical
        assert failed['acquisition'] == ready['acquisition']
        assert [s['id'] for s in failed['shorts'] if s['status'] == 'ready'] == [s['id'] for s in ready['shorts']]


def unplanned_lesson():
    from app.contracts import Job, Lesson, SavedLearningRequest
    from app.planning import new_state
    return Lesson(id='failed-plan', request=SavedLearningRequest(**request_for(None)), sources=[],
                  job=Job(id='failed-job', lesson_id='failed-plan', created_at=0, updated_at=0),
                  planning=new_state(300000), provider_settings={
                      'provider': 'turbofieldfare', 'model': 'gemma-4-26b-a4b-it',
                      'runtime_binary_sha256': 'same-runtime', 'context': 16384,
                      'max_completion_tokens': 3000, 'schema_version': 'same-schema',
                      'prompt_version': '22', 'parser_version': 'old-parser', 'repair_policy_version': 'old-repair',
                      'speech': {'voice': 'af_heart'}, 'language': 'en',
                  })


def test_failed_initial_plan_can_retry_prompt_parser_fix_without_resetting_allowances():
    from app.jobs import Jobs
    lesson = unplanned_lesson()
    lesson.planning.model_call_units = 9
    lesson.planning.expansion_attempts = 1
    lesson.planning.work_seconds = 120
    lesson.acquisition.transcript_provider_calls = 8
    before = lesson.model_dump(exclude={'provider_settings'})
    selected = {**lesson.provider_settings, 'prompt_version': '23', 'parser_version': 'new-parser',
                'repair_policy_version': 'new-repair'}
    Jobs.pin_provider(lesson, selected)
    assert lesson.provider_settings == selected
    assert lesson.model_dump(exclude={'provider_settings'}) == before
    assert lesson.provider_settings is not selected


def test_unplanned_retry_still_rejects_changed_runtime_model_settings_or_schema():
    import pytest
    from app.jobs import Jobs
    for field, value in [('provider', 'ollama'), ('model', 'another-model'), ('context', 8192),
                         ('max_completion_tokens', 4096), ('schema_version', 'different'),
                         ('runtime_binary_sha256', 'different'), ('speech', {'voice': 'another'})]:
        lesson = unplanned_lesson()
        before = lesson.model_dump()
        selected = {**lesson.provider_settings, 'prompt_version': '23', field: value}
        with pytest.raises(AppError) as error:
            Jobs.pin_provider(lesson, selected)
        assert error.value.code == 'PROVIDER_SETTINGS_MISMATCH'
        assert lesson.model_dump() == before


def test_authoring_fix_preserves_unpublished_plan_and_short_ids():
    from app.contracts import Objective, Short
    from app.jobs import Jobs
    lesson = unplanned_lesson()
    lesson.objectives = [Objective(title='Understand a supported idea', template='key_fact', prerequisites=[])]
    lesson.shorts = [Short(id='queued-short', objective='Understand a supported idea')]
    before = lesson.model_dump(exclude={'provider_settings'})
    Jobs.pin_provider(lesson, {**lesson.provider_settings, 'prompt_version': '24', 'authoring_version': 'compact-1'})
    assert lesson.model_dump(exclude={'provider_settings'}) == before
    assert lesson.provider_settings['authoring_version'] == 'compact-1'


def test_authoring_fix_cannot_rebind_published_or_repairable_media():
    import pytest
    from app.contracts import Short
    from app.jobs import Jobs
    for change in ({'status': 'ready'}, {'audio_path': 'published.wav'}):
        lesson = unplanned_lesson()
        lesson.shorts = [Short(id='existing-short', objective='Understand a supported idea', **change)]
        before = lesson.model_dump()
        with pytest.raises(AppError) as error:
            Jobs.pin_provider(lesson, {**lesson.provider_settings, 'prompt_version': '24', 'authoring_version': 'compact-1'})
        assert error.value.code == 'PROVIDER_SETTINGS_MISMATCH'
        assert lesson.model_dump() == before
