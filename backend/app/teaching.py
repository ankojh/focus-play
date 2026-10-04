"""Bounded curriculum checks and persisted teaching history (no provider calls)."""
import json
import re
from .contracts import CoverageEntry, Short
from .validation import similar, normalize

TEACHING_VERSION = "2"
RECENT_TEXT_CHARS = 1200
HISTORY_ITEMS = 12
HISTORY_CHARS = 4800


def validate_plan(plan, segments, max_shorts, budget_ms):
    if not plan.sufficient_evidence:
        if plan.objectives or plan.examples:
            raise ValueError("An unsupported plan must have no objectives or examples.")
        return
    if not 1 <= len(plan.objectives) <= max_shorts:
        raise ValueError(f"Use 1 to {max_shorts} ordered objectives.")
    known = {s.id: s for s in segments}
    ids = [o.concept_id for o in plan.objectives]
    if None in ids or len(set(ids)) != len(ids):
        raise ValueError("Every concept needs a stable unique concept_id.")
    examples = {e.id: e for e in plan.examples}
    if len(examples) != len(plan.examples):
        raise ValueError("Example IDs must be unique.")
    for example in plan.examples:
        if any(sid not in known for sid in example.evidence_segment_ids):
            raise ValueError("Example evidence must use supplied segment IDs.")
        passages = [known[sid].text for sid in example.evidence_segment_ids]
        if any(not any(fact in text for text in passages) for fact in example.facts):
            raise ValueError("Example facts must be exact source excerpts; synthetic facts are not permitted.")
        if any(not any(entity.casefold() in text.casefold() for text in passages) for entity in example.entities):
            raise ValueError("Example entities must already occur in its evidence.")
    earlier = {}
    closing_seen = False
    for objective in plan.objectives:
        if objective.target_duration_ms != 40000:
            raise ValueError("Use the 40000ms duration reservation until calibrated duration planning is available.")
        if not objective.learning_outcome or not objective.relevance or not objective.visual_intent:
            raise ValueError("Supply an observable learning_outcome, learner relevance and visual intent.")
        # An observable action is required; this is a structural guard, not a quality score.
        verbs = {"explain", "identify", "compare", "predict", "choose", "apply", "trace", "describe", "distinguish", "demonstrate", "recall", "calculate", "justify", "perform", "use", "recognize", "evaluate", "construct", "write", "select"}
        if not verbs.intersection(re.findall(r"[a-z]+", objective.learning_outcome.lower())):
            raise ValueError("Learning outcomes must name an observable action, e.g. explain, predict or choose.")
        if len(set(objective.dependency_ids)) != len(objective.dependency_ids) or any(dep not in earlier for dep in objective.dependency_ids):
            raise ValueError("Dependencies must name earlier concepts; missing, forward and cyclic dependencies are invalid.")
        if not objective.evidence_segment_ids or any(sid not in known for sid in objective.evidence_segment_ids):
            raise ValueError("Each outcome needs supplied evidence segment IDs.")
        if objective.example_id is not None and objective.example_id not in examples:
            raise ValueError("Select an existing example_id.")
        if objective.teaching_role == "recap":
            if not objective.dependency_ids or objective.curriculum_role != "closing":
                raise ValueError("A recap needs earlier dependencies and closing classification.")
        else:
            for previous in earlier.values():
                if similar(objective.learning_outcome, previous.learning_outcome, .8):
                    raise ValueError("Duplicate outcomes do not add coverage; use an explicit recap or a distinct application.")
        if closing_seen and objective.curriculum_role != "closing":
            raise ValueError("Closing activities must follow all core and extension activities.")
        closing_seen |= objective.curriculum_role == "closing"
        earlier[objective.concept_id] = objective
    # Use the existing conservative speech cap until the duration workstream supplies predictions.
    if sum(40000 + (20000 if o.checkpoint else 0) for o in plan.objectives) > budget_ms:
        raise ValueError("Teaching and planned 20-second practice allowances exceed the session budget.")


def planned_shorts(plan, make_id):
    return [Short(id=make_id(), objective=o.title, prerequisites=o.prerequisites,
                  concept_id=o.concept_id, learning_outcome=o.learning_outcome,
                  teaching_role=o.teaching_role, curriculum_role=o.curriculum_role,
                  example_id=o.example_id, question_required=o.checkpoint) for o in plan.objectives]


def objective_for(lesson, short):
    if short.concept_id:
        return next((o for o in lesson.objectives if o.concept_id == short.concept_id), None)
    # Legacy unfinished items retain their original positional mapping.
    index = lesson.shorts.index(short)
    core_index = sum(not s.optional for s in lesson.shorts[:index])
    return lesson.objectives[min(core_index, len(lesson.objectives) - 1)] if lesson.objectives else None


def teaching_context(lesson, short):
    index = lesson.shorts.index(short)
    earlier = [s for s in lesson.shorts[:index] if s.status == "ready"]
    recent = [u.text for s in earlier[-2:] for u in s.narration_units]
    bounded = []
    remaining = RECENT_TEXT_CHARS
    for text in reversed(recent):
        if len(text) > remaining:
            break  # Whole units only: never introduce a dangling partial sentence.
        bounded.insert(0, text)
        remaining -= len(text)
    by_short = {entry.short_id: entry for entry in lesson.coverage_history}
    entries = []
    for previous in earlier:
        entry = by_short.get(previous.id)
        entries.append({"concept_id": previous.concept_id or previous.id,
                        "outcome": (previous.learning_outcome or previous.objective)[:180],
                        "role": previous.teaching_role,
                        "claim": entry.claim_summary if entry else "",
                        "adds_coverage": entry.adds_coverage if entry else previous.teaching_role != "recap"})
    context = {"covered_ids": [e["concept_id"] for e in entries][-64:],
               "coverage": entries[-HISTORY_ITEMS:], "recent_narration": bounded}
    while len(json.dumps(context, ensure_ascii=False)) > HISTORY_CHARS and context["coverage"]:
        context["coverage"].pop(0)
    return context


def record_coverage(lesson, short):
    if not short.concept_id or not short.learning_outcome:
        return  # Do not silently migrate legacy ready media.
    entry = CoverageEntry(short_id=short.id, concept_id=short.concept_id,
                          learning_outcome=short.learning_outcome, teaching_role=short.teaching_role,
                          claim_summary=normalize("; ".join(u.purpose or u.text for u in short.narration_units))[:240],
                          evidence_segment_ids=list(dict.fromkeys(sid for ref in short.evidence_references for sid in ref.segment_ids))[:20],
                          example_id=short.example_id, adds_coverage=short.teaching_role != "recap")
    # Idempotent across a missing-media retry, published in the same lesson snapshot as ready output.
    lesson.coverage_history = [e for e in lesson.coverage_history if e.short_id != short.id] + [entry]


def plan_diagnostics(plan):
    diagnostics = []
    if not any(o.checkpoint for o in plan.objectives):
        diagnostics.append("No practice checkpoint planned; evaluate whether a small check would fit.")
    if len(plan.objectives) > 2 and all(o.teaching_role == "foundation" for o in plan.objectives):
        diagnostics.append("All outcomes are foundations; evaluate useful depth rather than introductory repetition.")
    return diagnostics
