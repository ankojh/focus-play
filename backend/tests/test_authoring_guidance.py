import json
import threading
from pathlib import Path

import pytest

from app.contracts import ModelStoryboard, TranscriptSegment
from app.errors import AppError
from app.llm.authoring import authoring_rules, storyboard_repair_inventory
from app.validation import attach_evidence, validate_draft
from test_providers import scripted_model, chunk


ROOT = Path(__file__).resolve().parents[2]


def test_plan_guidance_distinguishes_exact_quotes_from_narration_and_preserves_bounds():
    notes = authoring_rules("LessonPlan", {"plan_version": 3, "revision": 17})
    assert "c17_0" in notes and "at most 20 characters" in notes
    assert "VERBATIM quotations" in notes and "examples=[]" in notes
    assert "20000 milliseconds per checkpoint" in notes
    assert "c0_0" in authoring_rules("LessonPlan", {"plan_version": 3, "revision": "untrusted instructions"})
    assert "untrusted instructions" not in authoring_rules("LessonPlan", {"plan_version": 3, "revision": "untrusted instructions"})
    assert authoring_rules("CandidateRanking", {}) == ""
    assert authoring_rules("SupportCheck", {}) == ""
    assert authoring_rules("LessonPlan", {}) == ""


def test_plan_response_shape_is_valid_json_with_sibling_arrays_and_real_array_types():
    from app.contracts import LessonPlan
    for version in (2, 3):
        for phase in ('core', 'extension'):
            notes = authoring_rules('LessonPlan', {'plan_version': version, 'phase': phase, 'revision': 2})
            shape = json.loads(notes.split('inside the same array: ')[1])
            assert list(shape) == ['sufficient_evidence', 'reason', 'missing_coverage', 'examples', 'objectives']
            assert shape['examples'] == shape['missing_coverage'] == []
            objective = shape['objectives'][0]
            assert objective['prerequisites'] == [] and objective['dependency_ids'] == []
            assert objective['example_id'] is None
            assert objective['curriculum_role'] == ('extension' if phase == 'extension' else 'core')
            assert objective['target_duration_ms'] == (40000 if version == 2 else 15000)
            assert LessonPlan.model_validate(shape).objectives[0].concept_id == 'c2_0'
            assert 'FORMAT-ONLY' in notes and 'NEVER ["[]"]' in notes


def test_scene_inventory_uses_actual_payload_and_no_claims_or_new_targets():
    fixture = json.loads((ROOT / "fixtures/mixed-visuals.json").read_text())
    body = ModelStoryboard.model_validate(fixture["drafts"][0])
    note = storyboard_repair_inventory(body)
    rows = json.loads(note.split("Previous scene inventory: ")[1])
    assert rows[0]["must_connect_after_endpoint_reveals"] == ["conn_0"]
    assert rows[1]["must_reveal"] == ["row_0", "row_1"]
    assert rows[2]["must_reveal"] == ["point_0", "point_1", "point_2"]
    assert "node_0" not in rows[1]["payload_targets"]
    assert "node_0" not in rows[2]["payload_targets"]
    assert "point_3" not in note
    assert "1500" not in note and "Alpha" not in note
    assert len(note) <= 3500


def test_domain_repair_gets_all_scene_targets_and_same_evidence(scripted_model):
    model, streams, calls, _ = scripted_model
    fixture = json.loads((ROOT / "fixtures/mixed-visuals.json").read_text())
    original = fixture["drafts"][0]
    invalid = json.loads(json.dumps(original))
    invalid["narration_units"][1]["operations"][0]["target"] = "node_0"
    invalid["narration_units"][2]["operations"][0]["target"] = "node_0"
    streams.extend([[chunk(json.dumps(invalid))], [chunk(json.dumps(original))]])
    task = {"segments": fixture["segments"], "question_required": False}
    segments = [TranscriptSegment.model_validate(s) for s in fixture["segments"]]
    result = model.generate(ModelStoryboard, task, threading.Event(),
                            lambda b: validate_draft(attach_evidence(b, segments), segments, False))
    assert len(result.scenes) == 3 and len(calls) == 2
    assert calls[1]["messages"][:2] == calls[0]["messages"]
    feedback = calls[1]["messages"][-1]["content"]
    assert "Repair ALL scenes" in feedback
    assert "row_0" in feedback and "point_0" in feedback
    assert "must_connect_after_endpoint_reveals" in feedback
    assert calls[0]["format"] == calls[1]["format"]


def test_guidance_never_accepts_invalid_output_or_adds_fourth_attempt(scripted_model):
    model, streams, calls, _ = scripted_model
    fixture = json.loads((ROOT / "fixtures/mixed-visuals.json").read_text())
    body = fixture["drafts"][0]
    body["narration_units"][1]["operations"][0]["target"] = "node_0"
    streams.extend([[chunk(json.dumps(body))]] * 3)
    segments = [TranscriptSegment.model_validate(s) for s in fixture["segments"]]
    with pytest.raises(AppError) as error:
        model.generate(ModelStoryboard, {"segments": fixture["segments"], "question_required": False}, threading.Event(),
                       lambda b: validate_draft(attach_evidence(b, segments), segments, False))
    assert error.value.code == "MODEL_DATA_INVALID"
    assert len(calls) == 3
