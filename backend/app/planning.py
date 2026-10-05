"""Version-2 session ledger and bounded planning policy. No provider calls.

15s is an operational minimum target, not a claim that shorter measured media
is invalid. 80 = ceil(1200 / 15); the count ceiling cannot recreate the old
six-minute ceiling. Batches stay at four for the local 2200-token planner.
"""
from math import ceil
from statistics import median
from .contracts import DurationLedger, PlanningState, OutcomeCoverage

PLANNING_VERSION = "2-session"
MIN_TARGET_MS = 15000
DEFAULT_TARGET_MS = 30000
MAX_MEDIA_MS = 40000
PRACTICE_MS = 20000
TARGET_PERCENT = 95


def new_state(budget_ms):
    limit = min(80, ceil(budget_ms / MIN_TARGET_MS))
    return PlanningState(activity_limit=limit, expansion_limit=limit,
                         candidate_limit=3 * limit + 9,
                         model_call_limit=36 * limit + 60)


def practice(short):
    # A scheduled question is an allowance, never actual learner elapsed time.
    return short.question.allowance_ms if short.question else PRACTICE_MS if short.question_required else 0


def aggregate(shorts, *, budget_ms=0, final=False):
    """Canonical accounting: closing media is separated, never counted twice."""
    measured = unready = closing = reserved = original = extra = 0
    for short in shorts:
        allowance = practice(short)
        media = short.measured_duration_ms if short.status == "ready" else short.target_duration_ms
        reserved += allowance
        if short.status == "ready":
            measured += media
        elif short.curriculum_role == "closing" and not short.optional:
            closing += media
        else:
            unready += media
        if short.optional:
            extra += (media if short.status == "ready" else 0) + allowance
        else:
            original += (media if short.status == "ready" else 0) + allowance
    total = measured + unready + closing + reserved
    return DurationLedger(measured_ready_media_ms=measured, reserved_practice_ms=reserved,
                          estimated_unready_media_ms=unready, reserved_closing_ms=closing,
                          forecast_total_ms=total, final_content_ms=total if final else None,
                          original_content_ms=original, extra_content_ms=extra,
                          utilisation=original / budget_ms if budget_ms else 0,
                          shortfall_ms=max(0, ceil(budget_ms * TARGET_PERCENT / 100) - original))


def refresh(lesson, *, final=False):
    ledger = aggregate(lesson.shorts, budget_ms=lesson.request.time_budget_seconds * 1000, final=final)
    # Compatibility: planned_duration_ms remains measured ready + queued forecast
    # + practice. Version 2 queued forecasts use explicit per-activity targets.
    lesson.planned_duration_ms = ledger.forecast_total_ms
    if lesson.planning:
        lesson.duration_ledger = ledger
    return ledger


def useful_minimum(lesson):
    return lesson.planning.minimum_media_ms if lesson.planning else MIN_TARGET_MS


def group_budget(lesson, short):
    return lesson.extra_allowance_ms if short.optional else lesson.request.time_budget_seconds * 1000


def candidate_capacity(lesson, short):
    """Strict publish ceiling with useful minimums for required queued media.

    Only user-approved extras share the extra pool. Existing ready media is
    immutable. Optional curriculum extensions can be deferred before calling.
    """
    peers = [s for s in lesson.shorts if s.optional == short.optional]
    remaining = group_budget(lesson, short) - sum(practice(s) for s in peers)
    for peer in peers:
        if peer.id == short.id:
            continue
        if peer.status == "ready":
            remaining -= peer.measured_duration_ms
        else:
            remaining -= useful_minimum(lesson)
    return max(0, min(MAX_MEDIA_MS, remaining))


def remaining_for_batch(lesson):
    # Queued closing is already included by aggregate; no second reservation.
    original = [s for s in lesson.shorts if not s.optional]
    forecast = aggregate(original).forecast_total_ms
    forecast -= sum(s.target_duration_ms - useful_minimum(lesson) for s in original
                    if s.curriculum_role == "closing" and s.status != "ready")
    return max(0, lesson.request.time_budget_seconds * 1000 - forecast)


def needs_expansion(lesson):
    if not lesson.planning or lesson.planning.completion_reason:
        return False
    originals = [s for s in lesson.shorts if not s.optional]
    forecast = aggregate(originals).forecast_total_ms
    # Expand before closing based on its useful minimum, not its optimistic target.
    forecast -= sum(s.target_duration_ms - useful_minimum(lesson) for s in originals
                    if s.curriculum_role == "closing" and s.status != "ready")
    return forecast * 100 < lesson.request.time_budget_seconds * 1000 * TARGET_PERCENT


def recalibrate_queued(lesson):
    """Reduce only unpublished reservations if measured speech used headroom."""
    if not lesson.planning:
        return
    for optional in (False, True):
        peers = [s for s in lesson.shorts if s.optional == optional]
        budget = lesson.extra_allowance_ms if optional else lesson.request.time_budget_seconds * 1000
        excess = aggregate(peers).forecast_total_ms - budget
        for short in reversed(peers):
            if excess <= 0:
                break
            if short.status == "ready":
                continue
            reduction = min(excess, max(0, short.target_duration_ms - useful_minimum(lesson)))
            short.target_duration_ms -= reduction
            excess -= reduction
        if excess > 0:
            raise ValueError("Required minimum media and practice do not fit the authorised budget.")
    refresh(lesson)


def coverage_for(objective):
    facets = {"foundation": ["definition"], "mechanism": ["mechanism"],
              "worked_example": ["example"], "misconception": ["caveat"],
              "comparison": ["caveat"], "application": ["application"]}
    return OutcomeCoverage(concept_id=objective.concept_id, outcome=objective.learning_outcome,
                           evidence_segment_ids=objective.evidence_segment_ids,
                           supported_facets=facets.get(objective.teaching_role, []))


def speech_prediction(samples):
    """Milliseconds/word + uncertainty. Caller keys samples by full voice settings.

    Initial 430ms/word prior is deliberately cautious; recent actual clips
    replace it. Bounds avoid a pathological sample corrupting future targets.
    """
    rates = [s["duration_ms"] / s["words"] for s in samples if s["words"] > 0]
    rate = max(100, min(1000, median(rates))) if rates else 430
    uncertainty = round(median([abs(r - rate) for r in rates]) * 70) if len(rates) > 1 else 5000
    return round(rate), min(10000, max(2000, uncertainty))
