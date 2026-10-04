import json
import threading
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.contracts import LessonPlan, ModelStoryboard
from app.errors import AppError, Cancelled
from app.providers import Ollama


PLAN = {
    "sufficient_evidence": True,
    "reason": "The supplied passages teach one useful point.",
    "objectives": [{"title": "Understand the main point", "template": "key_fact", "prerequisites": []}],
}


def chunk(content="", *, done=True, reason="stop"):
    return json.dumps({"message": {"content": content}, "done": done, "done_reason": reason})


@pytest.fixture
def scripted_model(monkeypatch, tmp_path):
    calls = []
    streams = []
    consumed = []

    class Response:
        is_success = True

        def __init__(self, lines):
            self.lines = lines

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_lines(self):
            for line in self.lines:
                consumed.append(line)
                yield line

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def stream(self, *args, **kwargs):
            calls.append(kwargs["json"])
            return Response(streams.pop(0))

    monkeypatch.setattr(httpx, "Client", Client)
    return Ollama(Settings(data=tmp_path)), streams, calls, consumed


def test_schema_is_visible_to_backends_that_do_not_enforce_format(scripted_model):
    model, streams, calls, _ = scripted_model
    streams.append([chunk(json.dumps(PLAN))])
    task = {"task": "Plan from these passages", "segments": [{"id": "supplied", "text": "Evidence"}]}
    result = model.generate(LessonPlan, task, threading.Event())
    assert result.objectives[0].prerequisites == []
    prompt = calls[0]["messages"][0]["content"]
    assert json.dumps(calls[0]["format"], separators=(",", ":")) in prompt
    assert "compact JSON" in prompt
    assert calls[0]["options"]["repeat_penalty"] == 1.0
    assert json.loads(calls[0]["messages"][1]["content"]) == task


def test_presentation_prompt_preserves_meaning_and_separates_generation_cache(scripted_model, monkeypatch):
    model, streams, calls, _ = scripted_model
    fixture = json.loads((Path(__file__).resolve().parents[2] / "fixtures/storyboard-lookup.json").read_text())
    streams.append([chunk(json.dumps(fixture["draft"]))])
    task = {"segments": fixture["segments"], "question_required": False}
    model.generate(ModelStoryboard, task, threading.Event())
    prompt = calls[0]["messages"][0]["content"]
    for instruction in ("short complete sentences", "natural clause boundaries", "repeated sentence starts",
                        "preserve qualifiers and exact values", "Do not use SSML", "complements rather than repeats"):
        assert instruction in prompt
    monkeypatch.setattr(model, "readiness", lambda: None)
    assert model.fingerprint()["prompt_version"] == "20"


def test_malformed_json_and_whitespace_loop_get_clean_retries(scripted_model):
    model, streams, calls, _ = scripted_model
    broken = '{"prerequisites": ["basics-lite], "'
    streams.extend([[chunk(broken)], [chunk('{"objectives": [' + "  \n" * 100)], [chunk(json.dumps(PLAN))]])
    result = model.generate(LessonPlan, {"segments": ["unchanged evidence"]}, threading.Event())
    assert result.sufficient_evidence
    assert len(calls) == 3
    assert [c["options"]["seed"] for c in calls] == [42, 43, 44]
    for call in calls[1:]:
        assert [m["role"] for m in call["messages"]] == ["system", "user", "user"]
        assert call["messages"][:2] == calls[0]["messages"]
        assert broken not in call["messages"][-1]["content"]
    diagnostic = json.loads((model.settings.data / "cache/model-last-error.json").read_text())
    assert diagnostic["attempt"] == 2
    assert diagnostic["kind"] == "output"
    assert "whitespace" in diagnostic["error"]


def test_repetition_is_aborted_before_consuming_entire_stream(scripted_model):
    model, streams, _, consumed = scripted_model
    unused = chunk("SHOULD NOT BE CONSUMED")
    streams.extend([[chunk('{"reason": "', done=False), chunk("  \n" * 100, done=False), unused], [chunk(json.dumps(PLAN))]])
    assert model.generate(LessonPlan, {}, threading.Event()).sufficient_evidence
    assert unused not in consumed


def test_schema_repairs_keep_valid_json_and_concise_field_error(scripted_model):
    model, streams, calls, _ = scripted_model
    invalid = {**PLAN, "objectives": [{"title": "Understand the main point", "template": "not-a-template", "prerequisites": []}]}
    output = json.dumps(invalid)
    streams.extend([[chunk(output)], [chunk(json.dumps(PLAN))]])
    model.generate(LessonPlan, {}, threading.Event())
    repair = calls[1]["messages"]
    assert repair[2] == {"role": "assistant", "content": output}
    assert "objectives.0.template" in repair[3]["content"]
    assert "Failed validating" not in repair[3]["content"]


def test_content_validator_is_never_bypassed(scripted_model):
    model, streams, calls, _ = scripted_model
    streams.extend([[chunk(json.dumps(PLAN))]] * 3)
    checked = []

    def reject(plan):
        checked.append(plan)
        raise ValueError("A claim is not supported by the supplied passages.")

    with pytest.raises(AppError) as raised:
        model.generate(LessonPlan, {}, threading.Event(), reject)
    assert raised.value.code == "MODEL_DATA_INVALID"
    assert "not supported" in raised.value.message
    assert "lesson plan" in raised.value.message
    assert len(calls) == len(checked) == 3


@pytest.mark.parametrize("content", ['{"unfinished":', "  \n" * 100])
def test_invalid_output_is_not_reported_as_insufficient_evidence(scripted_model, content):
    model, streams, calls, _ = scripted_model
    streams.extend([[chunk(content)]] * 3)
    with pytest.raises(AppError) as raised:
        model.generate(LessonPlan, {}, threading.Event())
    assert raised.value.code == "MODEL_OUTPUT_INVALID"
    assert "not a lack of source evidence" in raised.value.message
    assert "another local model" not in raised.value.message
    assert len(calls) == 3


def test_token_limit_gets_actionable_error_and_bounded_retries(scripted_model):
    model, streams, calls, _ = scripted_model
    streams.extend([[chunk('{"unfinished":', reason="length")]] * 3)
    with pytest.raises(AppError) as raised:
        model.generate(LessonPlan, {}, threading.Event())
    assert raised.value.code == "MODEL_OUTPUT_TRUNCATED"
    assert "OLLAMA_PREDICT" in raised.value.message
    assert "shorter strings" in calls[1]["messages"][-1]["content"]
    assert len(calls) == 3
    diagnostic = json.loads((model.settings.data / "cache/model-last-error.json").read_text())
    assert diagnostic["kind"] == "truncated"
    assert diagnostic["done_reason"] == "length"


def test_incomplete_stream_is_not_accepted_even_with_valid_json(scripted_model):
    model, streams, calls, _ = scripted_model
    streams.extend([[chunk(json.dumps(PLAN), done=False)]] * 3)
    with pytest.raises(AppError) as raised:
        model.generate(LessonPlan, {}, threading.Event())
    assert raised.value.code == "MODEL_OUTPUT_INVALID"
    assert len(calls) == 3


def test_cancelled_generation_does_not_retry(scripted_model):
    model, streams, calls, _ = scripted_model
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        model.generate(LessonPlan, {}, cancel)
    assert not calls
