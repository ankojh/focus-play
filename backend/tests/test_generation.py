"""Regressions for local model stalls and paraphrased short review."""
import asyncio
import json
import threading

import httpx
import pytest

from app.config import Settings
from app.contracts import LessonPlan, ModelStoryboard
from app.errors import AppError
from app.jobs import Jobs
from app.providers import Ollama
from app.store import Store
from app.validation import SupportCheck, attach_evidence, validate_draft
from test_core import StubModel, StubSpeech, draft_for, source


def test_repeated_output_is_repaired_and_prompt_prefill_has_time(monkeypatch, tmp_path):
    attempts = []
    timeouts = []
    plan = {"sufficient_evidence": True, "reason": "Test only", "objectives": []}

    class Response:
        is_success = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_lines(self):
            output = "practice-" * 100 if len(attempts) == 1 else json.dumps(plan)
            yield json.dumps({"message": {"content": output}, "done": True})

    class Client:
        def __init__(self, **kwargs):
            timeouts.append(kwargs["timeout"])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def stream(self, *args, **kwargs):
            attempts.append(kwargs["json"])
            return Response()

    monkeypatch.setattr(httpx, "Client", Client)
    result = Ollama(Settings(data=tmp_path)).generate(LessonPlan, {}, threading.Event())
    assert isinstance(result, LessonPlan)
    assert result.sufficient_evidence
    assert len(attempts) == 2
    assert "repeating" in attempts[1]["messages"][-1]["content"]
    assert timeouts[0].read == 120
    assert timeouts[0].connect == 5


def test_generation_wall_clock_limit_is_bounded(monkeypatch, tmp_path):
    from app import providers

    ticks = iter([0, 301])
    monkeypatch.setattr(providers.time, "monotonic", lambda: next(ticks))

    class Response:
        is_success = True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_lines(self):
            yield json.dumps({"message": {"content": "{}"}, "done": True})

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def stream(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(httpx, "Client", Client)
    with pytest.raises(AppError) as error:
        Ollama(Settings(data=tmp_path)).generate(LessonPlan, {}, threading.Event())
    assert error.value.code == "MODEL_TIMEOUT"


def test_storyboard_runtime_schema_and_prompt_are_not_flat(monkeypatch, tmp_path):
    from pathlib import Path
    import jsonschema
    fixture = json.loads((Path(__file__).resolve().parents[2] / 'fixtures/storyboard-lookup.json').read_text())
    captured = []
    class Response:
        is_success = True
        def __enter__(self):return self
        def __exit__(self, *args):pass
        def iter_lines(self):
            yield json.dumps({'message':{'content':json.dumps(fixture['draft'])},'done':True})
    class Client:
        def __init__(self, **kwargs):pass
        def __enter__(self):return self
        def __exit__(self, *args):pass
        def stream(self, *args, **kwargs):captured.append(kwargs['json']);return Response()
    monkeypatch.setattr(httpx, 'Client', Client)
    task = {'segments':fixture['segments'],'template':'example','question_required':False}
    result = Ollama(Settings(data=tmp_path)).generate(ModelStoryboard, task, threading.Event())
    assert len(result.narration_units) == 4
    schema = captured[0]['format']
    assert schema['properties']['narration_units']['minItems'] == 2
    assert schema['properties']['narration_units']['maxItems'] == 5
    assert 'exactly two' not in captured[0]['messages'][0]['content']
    assert 'explicit beat operations' in captured[0]['messages'][0]['content']
    for change in (lambda b:b['narration_units'][0].update(segment_id='invented'),
                   lambda b:b['narration_units'][0]['operations'][0].update(target='invented'),
                   lambda b:b['narration_units'][0].update(scene_id='invented'),
                   lambda b:b['narration_units'][0].update(start_ms=100)):
        wrong = json.loads(json.dumps(fixture['draft']))
        change(wrong)
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(wrong, schema)


def test_source_review_rewrites_once_with_the_rejection_reason(tmp_path):
    class Reviewer(StubModel):
        reviews = 0

        def generate(self, contract, task, cancel, validate=None):
            if contract is SupportCheck:
                self.reviews += 1
                return SupportCheck(supported=self.reviews > 1, reason="Avoid the unsupported guarantee.")
            assert "unsupported guarantee" in task["task"]
            return super().generate(contract, task, cancel, validate)

    settings = Settings(data=tmp_path)
    store = Store(settings.data)
    model = Reviewer()
    jobs = Jobs(store, model, StubSpeech(settings), settings)
    segments = source().segments
    task = {"task": "Teach the point.", "template": "process", "question_required": False,
            "segments": [s.model_dump() for s in segments]}
    try:
        draft = asyncio.run(jobs.reviewed(draft_for(segments), task, segments,
            lambda value: validate_draft(attach_evidence(value, segments), segments, False), threading.Event()))
        assert model.reviews == 2 and model.calls == 1
        validate_draft(draft, segments, False)
    finally:
        store.close()
