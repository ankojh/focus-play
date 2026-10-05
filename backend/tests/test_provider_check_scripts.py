"""Offline safety tests for opt-in cached-evidence and export operators."""
import asyncio
import importlib.util
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.config import Settings
from app.contracts import Job, Lesson, SavedLearningRequest
from app.errors import AppError
from app.store import Store
from test_core import source, StubYouTube


ROOT = Path(__file__).resolve().parents[2]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / f'{name}.py')
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_cached_source_input_is_read_only_and_preserves_ids_times_and_hash(tmp_path):
    script = module('cached_lesson_check')
    settings = Settings(data=tmp_path)
    store = Store(settings.data)
    fixture = StubYouTube()
    original = fixture.transcript(fixture.search('fixture')[0], threading.Event())
    lesson = Lesson(id='saved', request=SavedLearningRequest(goal='Existing teaching goal', request_id='saved-request-id'),
                    sources=[original], job=Job(id='old_job', lesson_id='saved', status='complete', created_at=0, updated_at=0))
    store.save(lesson)
    sequence = lesson.job.event_sequence
    store.close()
    loaded = script.read_saved_lesson(tmp_path, 'saved')
    assert loaded.sources == lesson.sources
    assert loaded.sources[0].content_hash == original.content_hash
    assert loaded.job.event_sequence == sequence
    with pytest.raises(ValueError): script.read_saved_lesson(tmp_path, 'missing')


def test_cached_check_refuses_import_sources_and_has_no_acquisition_fallback(tmp_path):
    script = module('cached_lesson_check')
    settings = Settings(data=tmp_path)
    store = Store(settings.data)
    imported = source().model_copy(update={'source_type': 'import'})
    store.save(Lesson(id='import', request=SavedLearningRequest(goal='Existing goal', request_id='import-request-id'),
                      sources=[imported], job=Job(id='job', lesson_id='import', created_at=0, updated_at=0)))
    store.close()
    with pytest.raises(AppError): script.read_saved_lesson(tmp_path, 'import')
    for operation in (script.AcquisitionDisabled().search, script.AcquisitionDisabled().transcript):
        with pytest.raises(AppError) as error: operation('anything')
        assert error.value.code == 'SOURCE_CREDITS_NOT_APPROVED'


@pytest.mark.parametrize('provider,speech', [('ollama', 'kokoro'), ('turbofieldfare', 'macos')])
def test_cached_check_refuses_substitute_profile_before_reading_or_generating(monkeypatch, provider, speech):
    script = module('cached_lesson_check')
    monkeypatch.setattr(script, 'Settings', lambda: SimpleNamespace(provider=provider, speech=speech))
    with pytest.raises(ValueError, match='selected TurboFieldfare/Kokoro profile'):
        asyncio.run(script.run(SimpleNamespace()))


def test_explicit_ollama_check_refuses_turbo_before_reading_or_generating(monkeypatch):
    script = module('cached_lesson_check')
    monkeypatch.setattr(script, 'Settings', lambda: SimpleNamespace(provider='turbofieldfare', speech='kokoro'))
    with pytest.raises(ValueError, match='selected Ollama/Kokoro profile'):
        asyncio.run(script.run(SimpleNamespace(expected_provider='ollama')))
