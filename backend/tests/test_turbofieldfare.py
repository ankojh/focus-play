"""Offline real-contract/provider conformance; no weights, credits or live server."""
import asyncio
import json
import threading
import time
from pathlib import Path

import httpx
import pytest

from app.config import Settings, TURBO_MODEL
from app.contracts import CandidateRanking, LessonPlan, ModelStoryboard
from app.errors import AppError, Cancelled
from app.jobs import Jobs
from app.llm.sse import SSEDecoder
from app.llm.turbofieldfare import TurboFieldfare
from app.providers import create_model, health, strict_json_object
from app.validation import SupportCheck, attach_evidence, validate_draft
from test_core import StubSpeech, source
from test_teaching import reference_plan, FIXTURES, lesson_for


PLAN = {"sufficient_evidence": True, "reason": "Evidence supports this point", "objectives": []}


def frame(delta=None, finish=None, **extra):
    return "data: " + json.dumps({"model": TURBO_MODEL, "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}], **extra}, ensure_ascii=False) + "\n\n"


def stream(text, reason="stop"):
    return (": ping\r\n\r\n" + frame({"role": "assistant", "content": None}) + frame({"content": text})
            + frame(finish=reason) + "data: " + json.dumps({"model": TURBO_MODEL, "choices": [], "usage": {
                "prompt_tokens": 321, "completion_tokens": 30, "prompt_tokens_details": {"cached_tokens": 42}}})
            + "\n\ndata: [DONE]\n\n").encode()


class Bytes(httpx.AsyncByteStream):
    def __init__(self, data): self.data = data; self.closed = False
    async def __aiter__(self):
        for i in range(0, len(self.data), 7):
            yield self.data[i:i+7]
    async def aclose(self): self.closed = True


@pytest.fixture
def scripted(monkeypatch, tmp_path):
    requests, replies = [], []
    real = httpx.AsyncClient
    def handler(request):
        requests.append(json.loads(request.content))
        reply = replies.pop(0)
        if isinstance(reply, Exception): raise reply
        if isinstance(reply, int): return httpx.Response(reply, json={"error": {"code": "context_length_exceeded", "message": "private source text"}})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Bytes(reply))
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    settings = Settings(data=tmp_path, provider="turbofieldfare", model=TURBO_MODEL,
                        base_url="http://127.0.0.1:8080/v1", context=16384, predict=2200)
    return TurboFieldfare(settings), replies, requests


def test_request_mapping_usage_and_prompt(scripted):
    model, replies, requests = scripted
    replies.append(stream(json.dumps(PLAN)))
    assert model.generate(LessonPlan, {"segments": []}, threading.Event()).sufficient_evidence
    request = requests[0]
    assert set(request) == {"model", "messages", "stream", "stream_options", "temperature", "seed", "repetition_penalty", "max_completion_tokens"}
    assert request["stream_options"] == {"include_usage": True}
    schema, _ = json.JSONDecoder().raw_decode(request["messages"][0]["content"].split("Match this JSON schema: ")[1])
    assert schema["title"] == "LessonPlan"
    assert model.attempts[0]["cached_prompt_tokens"] == 42
    assert model.attempts[0]["prompt_tokens"] == 321
    assert model.attempts[0]["ttft_seconds"] >= 0


@pytest.mark.parametrize("name", ["storyboard", "mixed", "plan", "ranking", "review"])
def test_real_contracts_use_shared_pipeline(scripted, name):
    model, replies, requests = scripted
    root = Path(__file__).resolve().parents[2]
    validate = None
    if name == "storyboard":
        fixture = json.loads((root / "fixtures/storyboard-lookup.json").read_text())
        body, task, contract = fixture["draft"], {"segments": fixture["segments"], "question_required": False}, ModelStoryboard
    elif name == "mixed":
        fixture = json.loads((root / "fixtures/mixed-visuals.json").read_text())
        body, task, contract = fixture["drafts"][0], {}, ModelStoryboard
    elif name == "plan":
        plan, segments = reference_plan(FIXTURES[0])
        body, contract = plan.model_dump(), LessonPlan
        task = {"plan_version": 3, "max_objectives": 8, "max_target_ms": 40000, "segments": [s.model_dump() for s in segments]}
    elif name == "ranking":
        contract = CandidateRanking
        task = {"candidates": [{"video_id": "video000001"}]}
        body = {"scores": [{"video_id": "video000001", "relevance": 5, "level_fit": 5, "teaching": 4, "density": 4, "captions": 5, "reason": "Useful evidence"}]}
    else:
        contract, task = SupportCheck, {"teaching": {"outcome": "Explain a supported point"}}
        body = SupportCheck(supported=True, reason="Supported by the passages").model_dump()
    if name == "mixed":
        task = {"segments": fixture["segments"], "question_required": False}
    replies.append(stream(json.dumps(body)))
    result = model.generate(contract, task, threading.Event(), validate)
    assert isinstance(result, contract)
    assert len(requests) == 1


@pytest.mark.parametrize("broken", ["```json\n{}\n```", "{bad", " \n" * 100, '{"x":NaN}', '{"x":1,"x":2}'])
def test_clean_repair_keeps_evidence(scripted, broken):
    model, replies, requests = scripted
    replies.extend([stream(broken), stream(json.dumps(PLAN))])
    model.generate(LessonPlan, {"segments": ["same evidence"]}, threading.Event())
    assert len(requests) == 2
    assert requests[0]["messages"] == requests[1]["messages"][:2]
    assert [m["role"] for m in requests[1]["messages"]] == ["system", "user", "user"]
    assert requests[1]["seed"] == 43


@pytest.mark.parametrize("bad", [
    stream(json.dumps(PLAN)).replace(b"data: [DONE]\n\n", b""),
    frame({"content": json.dumps(PLAN)}).encode(),
    (frame({"content": json.dumps(PLAN)}) + "data: [DONE]\n\n").encode(),
    (frame({"tool_calls": [{"function": {"name": "shell"}}]}) + frame(finish="tool_calls") + "data: [DONE]\n\n").encode(),
    (frame({"reasoning_content": "private thought"}) + frame(finish="stop") + "data: [DONE]\n\n").encode(),
])
def test_terminal_and_channel_failures_are_not_evidence_failures(scripted, bad):
    model, replies, requests = scripted
    replies.extend([bad] * 3)
    with pytest.raises(AppError) as error: model.generate(LessonPlan, {}, threading.Event())
    assert error.value.code == "MODEL_OUTPUT_INVALID"
    assert len(requests) == 3


def test_length_and_domain_errors_are_distinct(scripted):
    model, replies, requests = scripted
    replies.extend([stream(json.dumps(PLAN), "length")] * 3)
    with pytest.raises(AppError) as error: model.generate(LessonPlan, {}, threading.Event())
    assert error.value.code == "MODEL_OUTPUT_TRUNCATED"
    assert "LLM_MAX_OUTPUT_TOKENS" in error.value.message
    replies.extend([stream(json.dumps(PLAN))] * 3)
    def reject(value): raise ValueError("Unsupported claim")
    with pytest.raises(AppError) as error: model.generate(LessonPlan, {}, threading.Event(), reject)
    assert error.value.code == "MODEL_DATA_INVALID"
    assert requests[-1]["messages"][2]["role"] == "assistant"


@pytest.mark.parametrize("status", [400, 404, 429, 500, 503])
def test_http_errors_have_no_hidden_retries_or_private_messages(scripted, status):
    model, replies, requests = scripted
    replies.append(status)
    with pytest.raises(AppError) as error: model.generate(LessonPlan, {}, threading.Event())
    assert error.value.code == "MODEL_REQUEST_FAILED"
    assert "private" not in error.value.message
    assert len(requests) == 1


def test_connection_timeout_and_instream_error(scripted):
    model, replies, requests = scripted
    replies.append(httpx.ConnectError("connection refused"))
    with pytest.raises(AppError) as error: model.generate(LessonPlan, {}, threading.Event())
    assert error.value.code == "MODEL_UNAVAILABLE"
    replies.append(b'data: {"error":{"message":"private"}}\n\ndata: [DONE]\n\n')
    with pytest.raises(AppError) as error: model.generate(LessonPlan, {}, threading.Event())
    assert error.value.code == "MODEL_REQUEST_FAILED"
    assert len(requests) == 2


def test_decoder_arbitrary_utf8_crlf_multiline_and_bounds():
    data = ': heartbeat\r\ndata: {"text":\r\ndata: "café 🐦"}\r\n\r\n'.encode()
    for size in range(1, len(data) + 1):
        decoder, frames = SSEDecoder(), []
        for start in range(0, len(data), size): frames += decoder.feed(data[start:start+size])
        decoder.finish()
        assert json.loads(frames[0]) == {"text": "café 🐦"}
    with pytest.raises(ValueError): SSEDecoder(limit=10).feed(b"data: " + b"x" * 11)
    with pytest.raises(ValueError): SSEDecoder(total_limit=10).feed(b"x" * 11)
    decoder = SSEDecoder(); decoder.feed(b"data: partial")
    with pytest.raises(ValueError): decoder.finish()


@pytest.mark.parametrize("during", ["prefill", "stream", "repair", "deadline", "task_deadline", "first_playable_deadline"])
def test_cancellation_and_deadline_close_stream_before_return(scripted, monkeypatch, during):
    model, _, _ = scripted
    cancel, entered, closed = threading.Event(), threading.Event(), threading.Event()
    calls = []
    real = httpx.AsyncClient
    class Stalled(httpx.AsyncByteStream):
        async def __aiter__(self):
            entered.set()
            if during == "stream": yield frame({"content": "{"}).encode()
            if during == "repair" and len(calls) == 1:
                yield stream("invalid"); return
            await asyncio.sleep(60)
            yield b""
        async def aclose(self): closed.set()
    def handle(request):
        calls.append(request)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Stalled())
    # Use the actual AsyncClient class, bypassing the scripted fixture wrapper.
    from httpx import _client
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _client.AsyncClient(transport=httpx.MockTransport(handle), **kw))
    if during == "deadline": model.settings.attempt_timeout = .15
    elif during == 'task_deadline': model.generation_deadline = time.monotonic() + .15
    elif during == 'first_playable_deadline': cancel.deadline = time.monotonic() + .15
    else:
        def trigger():
            entered.wait(2)
            if during == "repair":
                while len(calls) < 2: time.sleep(.01)
            time.sleep(.05); cancel.set()
        timer = threading.Thread(target=trigger, daemon=True); timer.start()
    started = time.monotonic()
    with pytest.raises(AppError if 'deadline' in during else Cancelled) as error:
        model.generate(LessonPlan, {}, cancel)
    if during == 'task_deadline': assert error.value.code == 'MODEL_TASK_TIMEOUT'
    if during == 'first_playable_deadline': assert error.value.code == 'FIRST_PLAYABLE_TIMEOUT'
    assert time.monotonic() - started < 1
    assert closed.is_set()
    assert len(calls) == (2 if during == "repair" else 1)


@pytest.mark.parametrize("mutation", [
    lambda b: b["narration_units"][0].update(segment_id="invented"),
    lambda b: b["narration_units"][0]["operations"][0].update(target="unknown"),
    lambda b: b["narration_units"][0].update(text="I will explain this video to you with no supporting source."),
    lambda b: b["scenes"][2]["payload"]["points"][0].update(value=-999),
    lambda b: b["scenes"][2]["payload"].update(unit="seconds"),
])
def test_actual_storyboard_schema_and_domain_mutations_never_publish(scripted, mutation):
    model, replies, requests = scripted
    root = Path(__file__).resolve().parents[2]
    fixture = json.loads((root / "fixtures/mixed-visuals.json").read_text())
    body = fixture["drafts"][0]
    mutation(body)
    from app.contracts import TranscriptSegment
    segments = [TranscriptSegment.model_validate(s) for s in fixture["segments"]]
    replies.extend([stream(json.dumps(body))] * 3)
    with pytest.raises(AppError) as error:
        model.generate(ModelStoryboard, {"segments": fixture["segments"], "question_required": False}, threading.Event(),
                       lambda b: validate_draft(attach_evidence(b, segments), segments, False))
    assert error.value.code == "MODEL_DATA_INVALID"
    assert len(requests) == 3


def test_mixed_renderer_repair_feedback_names_the_scene_and_allowed_targets(scripted):
    model, replies, requests = scripted
    fixture = json.loads((Path(__file__).resolve().parents[2] / "fixtures/mixed-visuals.json").read_text())
    body = fixture["drafts"][0]
    body["narration_units"][1]["operations"][0]["target"] = "node_0"
    from app.contracts import TranscriptSegment
    segments = [TranscriptSegment.model_validate(s) for s in fixture["segments"]]
    replies.extend([stream(json.dumps(body))] * 3)
    with pytest.raises(AppError):
        model.generate(ModelStoryboard, {"segments": fixture["segments"], "question_required": False}, threading.Event(),
                       lambda b: validate_draft(attach_evidence(b, segments), segments, False))
    feedback = requests[1]["messages"][-1]["content"]
    assert "scene_1 (table)" in feedback and "row_0" in feedback
    assert "Do not use diagram node/connection IDs" in feedback
    assert "input_value" not in feedback and "https://errors.pydantic.dev" not in feedback


def test_cancel_before_request_does_not_connect(scripted):
    model, replies, requests = scripted
    cancel = threading.Event(); cancel.set()
    with pytest.raises(Cancelled): model.generate(LessonPlan, {}, cancel)
    assert not requests


def test_no_assets_means_no_model_image_branch(scripted):
    model, replies, requests = scripted
    fixture = json.loads((Path(__file__).resolve().parents[2] / "fixtures/mixed-visuals.json").read_text())
    replies.extend([stream(json.dumps(fixture["drafts"][2]))] * 3)
    with pytest.raises(AppError) as error:
        model.generate(ModelStoryboard, {"segments": fixture["segments"], "question_required": False}, threading.Event())
    assert error.value.code == "MODEL_DATA_INVALID"
    assert len(requests) == 3


def test_provider_pinning_keeps_legacy_provenance_and_rejects_switch():
    lesson = lesson_for([])
    old = {"model": "gemma4:12b-mlx", "digest": "old", "speech": {"voice": "af_heart"}}
    lesson.provider_settings = dict(old)
    Jobs.pin_provider(lesson, {**old, "provider": "ollama", "adapter_version": "1"})
    assert lesson.provider_settings == old
    with pytest.raises(AppError) as error: Jobs.pin_provider(lesson, {**old, "provider": "turbofieldfare"})
    assert error.value.code == "PROVIDER_SETTINGS_MISMATCH"
    assert lesson.provider_settings == old
