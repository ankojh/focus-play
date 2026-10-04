"""Offline contract/reference-fixture regressions; not an evaluation of a live model."""
import asyncio
import json
import threading
from pathlib import Path

import httpx
import jsonschema
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.contracts import (ExampleRecord, Job, Lesson, LessonPlan, ModelQuestion, Objective,
                           SavedLearningRequest, Short)
from app.errors import AppError
from app.jobs import Jobs
from app.main import create_app
from app.providers import Ollama
from app.sources import retrieve
from app.store import Store
from app.teaching import (HISTORY_CHARS, HISTORY_ITEMS, RECENT_TEXT_CHARS, objective_for, planned_shorts,
                          record_coverage, teaching_context, validate_plan)
from app.validation import SupportCheck, check_narration, planned_duration, validate_draft, verify_support
from test_core import StubModel, StubSpeech, StubYouTube, draft_for, request_for, source, wait_for

FIXTURES = json.loads((Path(__file__).resolve().parents[2] / "fixtures/teaching-quality.json").read_text())["cases"]


def reference_plan(case, advanced=False):
    segments = source(case["passage"]).segments
    rows = case["advanced" if advanced else "beginner"]
    examples = [ExampleRecord(**case["example"], evidence_segment_ids=[segments[0].id])] if case.get("example") else []
    objectives = [Objective(concept_id=id_, title=outcome[:150], learning_outcome=outcome,
                            teaching_role=role, dependency_ids=deps, template="example" if role == "worked_example" else "process",
                            prerequisites=[], relevance=f"Supports: {case['goal']}",
                            evidence_segment_ids=[segments[0].id], visual_intent="Demonstrate the causal or procedural relationship",
                            curriculum_role="closing" if role == "recap" else "core",
                            example_id=examples[0].id if examples and role == "worked_example" else None,
                            checkpoint=role in {"application", "practice"}) for id_, outcome, role, deps in rows]
    return LessonPlan(sufficient_evidence=True, reason="", objectives=objectives, examples=examples), segments


def lesson_for(shorts, **kwargs):
    return Lesson(id="lesson_test", request=SavedLearningRequest(**request_for(None), time_budget_seconds=1200),
                  sources=[], shorts=shorts, short_ids=[s.id for s in shorts],
                  job=Job(id="job_test", lesson_id="lesson_test", created_at=0, updated_at=0), **kwargs)


@pytest.mark.parametrize("case", FIXTURES, ids=lambda c:c["id"])
def test_reference_beginner_and_knowledgeable_plans(case):
    beginner, segments = reference_plan(case)
    advanced, _ = reference_plan(case, True)
    validate_plan(beginner, segments, 8, 300000)
    validate_plan(advanced, segments, 8, 300000)
    if case["id"] != "narrow":
        assert len(advanced.objectives) < len(beginner.objectives)
        assert advanced.objectives[0].teaching_role != "foundation"
    else:
        assert len(beginner.objectives) == len(advanced.objectives) == 1
    # The fixture deliberately keeps a narrow goal narrow, even with a 20-minute budget.
    validate_plan(beginner, segments, 8, 1200000)


@pytest.mark.parametrize("mutation, message", [
    (lambda p:p.objectives[1].dependency_ids.append("missing"), "Dependencies"),
    (lambda p:p.objectives[0].dependency_ids.append("lookup"), "Dependencies"),
    (lambda p:setattr(p.objectives[1], "concept_id", "mapping"), "unique"),
    (lambda p:setattr(p.objectives[1], "learning_outcome", p.objectives[0].learning_outcome), "Duplicate"),
    (lambda p:setattr(p.objectives[0], "evidence_segment_ids", ["invented"]), "evidence"),
    (lambda p:setattr(p.objectives[0], "learning_outcome", "Understand everything about indexes"), "observable"),
    (lambda p:setattr(p.objectives[1], "example_id", "invented"), "example_id"),
    (lambda p:setattr(p.examples[0], "entities", ["customer ID 200"]), "entities"),
    (lambda p:setattr(p.examples[0], "facts", ["Illustrative: Maya's query is 90% faster."]), "synthetic"),
    (lambda p:setattr(p.examples[0], "evidence_segment_ids", ["invented"]), "Example evidence"),
    (lambda p:setattr(p.objectives[-1], "dependency_ids", []), "recap"),
    (lambda p:setattr(p.objectives[0], "target_duration_ms", 20000), "duration"),
])
def test_invalid_plan_structure_and_unsupported_examples(mutation, message):
    plan, segments = reference_plan(FIXTURES[0])
    mutation(plan)
    with pytest.raises(ValueError, match=message):
        validate_plan(plan, segments, 8, 300000)


def test_distinct_application_allowed_duplicate_and_recap_coverage():
    plan, segments = reference_plan(FIXTURES[0])
    validate_plan(plan, segments, 8, 300000)
    shorts = planned_shorts(plan, iter(["a", "b", "c", "d"]).__next__)
    lesson = lesson_for(shorts, objectives=plan.objectives, examples=plan.examples)
    for short in shorts:
        short.status = "ready"
        record_coverage(lesson, short)
        record_coverage(lesson, short)  # Missing-media retry cannot duplicate completed coverage.
    assert len(lesson.coverage_history) == 4
    assert [e.adds_coverage for e in lesson.coverage_history] == [True, True, True, False]
    sentence = "An index maps customer keys to row locations."
    with pytest.raises(ValueError, match="repeats"):
        check_narration([sentence], [sentence])
    check_narration([sentence], [sentence], allow_recap=True)
    with pytest.raises(ValueError, match="repeats"):
        check_narration([sentence, sentence], [sentence], allow_recap=True)
    # Stable concept mapping is independent of optional insertion and objective ordering.
    lesson.objectives.reverse()
    lesson.shorts.insert(0, Short(id="extra", objective="Extra example", optional=True))
    assert objective_for(lesson, shorts[1]).concept_id == "lookup"


def test_recurring_source_example_preserves_entities_and_pins_evidence():
    plan, segments = reference_plan(FIXTURES[0])
    example = plan.examples[0]
    draft = draft_for(segments)
    validate_draft(draft, segments, False, example=example)
    # An unexplained substitution is rejected before support review if no recorded entity remains.
    for unit in draft.narration_units:
        unit.text = unit.text.replace("Maya", "Alice")
    with pytest.raises(ValueError, match="entities"):
        validate_draft(draft, segments, False, example=example)
    src = source(FIXTURES[0]["passage"] + "\n\nUnrelated topic.")
    found = retrieve([src], "Unrelated", required_ids=[src.segments[0].id])
    assert src.segments[0] in found
    with pytest.raises(AppError, match="Planned evidence"):
        retrieve([src], "Unrelated", budget=10, required_ids=[src.segments[0].id])
    with pytest.raises(AppError):
        retrieve([src], "Unrelated", required_ids=["missing"])


def test_question_placement_uniqueness_and_budget():
    plan, segments = reference_plan(FIXTURES[2])
    # Practice is a meaningful checkpoint; it is not determined by the short's index.
    plan.objectives[1].checkpoint = True
    shorts = planned_shorts(plan, iter(["a", "b", "c"]).__next__)
    assert [s.question_required for s in shorts] == [False, True, True]
    assert planned_duration(shorts) == 160000
    with pytest.raises(ValueError, match="budget"):
        validate_plan(plan, segments, 8, 159999)
    validate_plan(plan, segments, 8, 160000)
    one = LessonPlan(sufficient_evidence=True, reason="", objectives=[plan.objectives[0]])
    one.objectives[0].checkpoint = True
    validate_plan(one, segments, 1, 60000)
    for correct, distractors in [("A row", [" a ROW "]), ("A row", ["A server", "a server"])]:
        with pytest.raises(ValidationError, match="distinct"):
            ModelQuestion(prompt="What does the key identify?", correct_answer=correct, distractors=distractors,
                          explanation="The index maps a key to a row.", segment_id=segments[0].id)
    draft = draft_for(source().segments, question=True)
    with pytest.raises(ValueError, match="repeat an earlier question"):
        validate_draft(draft, source().segments, True, earlier_questions=[draft.question.prompt])


def test_context_is_bounded_for_twenty_minutes_and_continuations():
    shorts = []
    for i in range(40):
        draft = draft_for(source().segments, tag=f"s{i}")
        short = Short(id=f"s{i}", objective=f"Goal {i}", concept_id=f"concept_{i}", learning_outcome=f"Predict a distinct application {i}",
                      teaching_role="application", status="ready", narration_units=draft.narration_units)
        shorts.append(short)
    next_short = Short(id="next", objective="Next application")
    lesson = lesson_for([*shorts, next_short])
    for short in shorts:
        record_coverage(lesson, short)
    history = teaching_context(lesson, next_short)
    assert 1 <= len(history["coverage"]) <= HISTORY_ITEMS
    assert len(history["covered_ids"]) == 40
    assert sum(map(len, history["recent_narration"])) <= RECENT_TEXT_CHARS
    assert len(json.dumps(history, ensure_ascii=False)) <= HISTORY_CHARS
    reloaded = Lesson.model_validate(lesson.model_dump())
    assert teaching_context(reloaded, reloaded.shorts[-1]) == history
    assert shorts[0].narration_units[0].text not in history["recent_narration"]


def test_new_planner_schema_requires_outcomes_but_legacy_lessons_load(monkeypatch, tmp_path):
    plan, segments = reference_plan(FIXTURES[0])
    captured = []
    class Response:
        is_success = True
        def __enter__(self):return self
        def __exit__(self, *args):pass
        def iter_lines(self):yield json.dumps({"message":{"content":plan.model_dump_json()},"done":True})
    class Client:
        def __init__(self, **kwargs):pass
        def __enter__(self):return self
        def __exit__(self, *args):pass
        def stream(self, *args, **kwargs):captured.append(kwargs["json"]);return Response()
    monkeypatch.setattr(httpx, "Client", Client)
    task = {"plan_version":2,"max_objectives":8,"segments":[s.model_dump() for s in segments]}
    result = Ollama(Settings(data=tmp_path)).generate(LessonPlan, task, threading.Event(),
        lambda p:validate_plan(p, segments, 8, 300000))
    assert result == plan
    schema = captured[0]["format"]
    for key in ("concept_id", "learning_outcome", "dependency_ids", "checkpoint", "evidence_segment_ids"):
        invalid = plan.model_dump()
        invalid["objectives"][0].pop(key)
        with pytest.raises(jsonschema.ValidationError):jsonschema.validate(invalid, schema)
    old = Objective(title="Understand an index", template="process", prerequisites=[])
    ready = Short(id="old", objective=old.title, status="ready", audio_path="saved.wav")
    saved = lesson_for([ready], objectives=[old])
    loaded = Lesson.model_validate(saved.model_dump())
    assert loaded.teaching_plan_version == 1 and loaded.coverage_history == []
    assert loaded.shorts[0] == ready


def test_teaching_review_repair_is_bounded_and_dimensions_are_separate(tmp_path):
    class Reviewer(StubModel):
        reviews = 0
        def generate(self, contract, task, cancel, validate=None):
            if contract is SupportCheck:
                self.reviews += 1
                assert task["teaching"]["outcome"] == "Explain an index mapping"
                return SupportCheck(supported=True, reason="The passages support the facts.",
                                    teaching_issues=["This paraphrases covered mapping without a new application."] if self.reviews == 1 else [])
            assert "paraphrases covered mapping" in task["task"]
            return super().generate(contract, task, cancel, validate)
    settings = Settings(data=tmp_path)
    store = Store(settings.data)
    model = Reviewer()
    jobs = Jobs(store, model, StubSpeech(settings), settings)
    segments = source().segments
    short = Short(id="a", objective="Explain an index mapping")
    task = {"task":"Teach the mapping", "template":"process", "question_required":False,
            "segments":[s.model_dump() for s in segments], "teaching":{"outcome":short.objective}}
    try:
        asyncio.run(jobs.reviewed(draft_for(segments), task, segments, lambda c:None, threading.Event(), short))
        assert model.reviews == 2
        assert short.source_review_status == "model_supported"
        assert short.source_review_reason == "The passages support the facts."
        assert "teaching review" in short.review_repair_reasons[0]
        class Reject:
            def generate(self, *args):return SupportCheck(supported=False, reason="Unsupported answer", teaching_issues=[])
        with pytest.raises(ValueError, match="source review"):
            verify_support(Reject(), draft_for(segments), segments, threading.Event(), task["teaching"])
        class AlwaysReject(Reviewer):
            def generate(self, contract, task, cancel, validate=None):
                if contract is SupportCheck:return SupportCheck(supported=True, reason="Supported", teaching_issues=["No useful explanation"])
                return StubModel.generate(self, contract, task, cancel, validate)
        jobs.model = AlwaysReject()
        with pytest.raises(AppError) as error:
            asyncio.run(jobs.reviewed(draft_for(segments), task, segments, lambda c:None, threading.Event(), short))
        assert error.value.code == "TEACHING_QUALITY_FAILED"
    finally:
        store.close()


@pytest.mark.parametrize("supported, code", [(False, "UNSUPPORTED_CLAIM"), (True, "TEACHING_QUALITY_FAILED")])
def test_failed_reviews_persist_reasons_in_worker_snapshot(tmp_path, supported, code):
    class Rejected(StubModel):
        reviews = 0
        def generate(self, contract, task, cancel, validate=None):
            if contract is SupportCheck:
                self.reviews += 1
                return SupportCheck(supported=supported, reason="The example invents a benchmark.",
                                    teaching_issues=["The outcome is not explained."] if supported else [])
            return super().generate(contract, task, cancel, validate)
    settings = Settings(data=tmp_path)
    model = Rejected()
    with TestClient(create_app(settings, model, StubSpeech(settings), StubYouTube())) as client:
        lid = client.post('/api/lessons', json=request_for(None)).json()['id']
        failed = wait_for(client, lid, "failed")
        assert failed["job"]["error"]["code"] == code
        assert model.reviews == 2
        assert len(failed["shorts"][0]["review_repair_reasons"]) == 2
        assert failed["shorts"][0]["source_review_status"] == "unchecked"
        assert failed["coverage_history"] == []


def test_retry_preserves_approved_plan_coverage_and_ready_outputs(tmp_path):
    class FailSpeech(StubSpeech):
        calls = 0
        def synthesize(self, units, key, cancel):
            self.calls += 1
            if self.calls == 2:raise AppError("SPEECH_FAILED", "Test failure")
            return super().synthesize(units, key, cancel)
    settings = Settings(data=tmp_path)
    speech = FailSpeech(settings)
    model = StubModel()
    app = create_app(settings, model, speech, StubYouTube())
    with TestClient(app) as client:
        lid = client.post('/api/lessons', json=request_for(None)).json()['id']
        failed = wait_for(client, lid, "failed")
        assert failed["teaching_plan_version"] == 2
        assert len(failed["coverage_history"]) == 1
        assert [s["question_required"] for s in failed["shorts"]] == [False, True, False]
        client.post(f'/api/lessons/{lid}/retry', json={})
        ready = wait_for(client, lid)
        assert ready["objectives"] == failed["objectives"]
        assert ready["shorts"][0] == failed["shorts"][0]
        assert ready["coverage_history"][0] == failed["coverage_history"][0]
        assert len(ready["coverage_history"]) == 3
        assert all(s["source_review_status"] == "model_supported" for s in ready["shorts"])
        assert ready["shorts"][1]["question"]["allowance_ms"] == 20000
