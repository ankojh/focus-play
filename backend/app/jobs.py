from __future__ import annotations
import asyncio
import hashlib
import json
import threading
import time
import uuid
from .contracts import (Job, Lesson, LessonPlan, Short, StoryboardDraft, ErrorInfo, ModelStoryboard,
                        SavedLearningRequest, CandidateRanking, AcquisitionLedger, AcquisitionRound)
from .planning import (PLANNING_VERSION, MIN_TARGET_MS, DEFAULT_TARGET_MS, new_state, refresh,
                       aggregate, candidate_capacity, recalibrate_queued, remaining_for_batch,
                       needs_expansion, coverage_for, speech_prediction, useful_minimum)
from .validation import similar, word_set
from .storyboard import STORYBOARD_VERSION, COMPILER_VERSION, compile_storyboard
from .assets import Assets
from .photos import PhotoSearch
from .imagegen import ImageGenerator
from .visuals import VISUAL_VERSION, chartable
from .errors import AppError, Cancelled
from .readiness import required_media, snapshot_readiness
from .providers import check_cancel
from .ranking import KEEP, pick, ranking_task, validator
from .sources import retrieve
from .validation import validate_draft, verify_support, attach_evidence, diagram_evidence
from .youtube import YouTubeSources, queries, require_youtube
from .teaching import (TEACHING_VERSION, validate_plan as check_plan, planned_shorts,
                       objective_for, teaching_context, record_coverage, plan_diagnostics)


TEMPLATES = {
    "process": "2 to 8 stages in order; roles start, step, result; connect each stage to the next.",
    "steps": "2 to 8 numbered how-to steps; each detail is a short instruction; roles step.",
    "cycle": "3 to 8 stages that repeat in a loop; roles step. The application draws the loop.",
    "comparison": "two to four options compared side by side; slots 0 and 1 are the main pair.",
    "dos_donts": "the right way (role good) against the wrong way (role bad); include at least one of each.",
    "key_fact": "node_0 is the single most important rule or number; 1 to 7 supporting nodes explain it.",
    "timeline": "events in time order; roles step.",
    "example": "a concrete worked example from the passages, from situation to outcome.",
    "funnel": "3 to 8 stages that narrow in order, widest first (e.g. many candidates to few results); roles step, last result; no connections.",
    "matrix": "a 2x2 grid of four quadrants split by two factors; node_0 top-left, node_1 top-right, node_2 bottom-left, node_3 bottom-right; no connections.",
    "hierarchy": "node_0 is the parent (organisation, system, category); 2 to 7 child nodes are its parts; connect node_0 to each child.",
    "venn": "exactly 3 nodes: node_0 and node_1 are two ideas, node_2 is what they share (the overlap); no connections.",
    "chart": "quantitative comparison using kind chart with source values, units and a zero-inclusive scale; never legacy diagram mini-bars or invented values.",
}
TEMPLATE_GUIDE = " ".join(f"{name}: {text}" for name, text in TEMPLATES.items())


# Content failures of one short: skipped, never fatal to the lesson. System
# problems (model/speech/source unavailable, credits, work limits) still fail it.
SKIPPABLE = {"MODEL_DATA_INVALID", "MODEL_OUTPUT_INVALID", "MODEL_OUTPUT_TRUNCATED", "UNSUPPORTED_CLAIM",
             "TEACHING_QUALITY_FAILED", "STORYBOARD_TIMELINE_INVALID", "SPEECH_DURATION"}
DRAFT_FAILURES = {"MODEL_DATA_INVALID", "MODEL_OUTPUT_INVALID", "MODEL_OUTPUT_TRUNCATED"}
SIMPLE_TEMPLATE = "key_fact"
SKIP_REASONS = {
    "MODEL_DATA_INVALID": "its draft failed the accuracy checks",
    "MODEL_OUTPUT_INVALID": "the model could not produce a valid draft",
    "MODEL_OUTPUT_TRUNCATED": "the model could not produce a complete draft",
    "UNSUPPORTED_CLAIM": "the source review could not confirm its claims",
    "TEACHING_QUALITY_FAILED": "the teaching review rejected it",
    "STORYBOARD_TIMELINE_INVALID": "its visuals could not be timed to the narration",
    "SPEECH_DURATION": "its narration could not fit the time",
}


def contained_title(a, b):
    """"Standing Up" vs "Standing Up from Ice": one title's words all inside the other's.

    Needs at least two words in the shorter title, so a one-word title such as
    "Balance" does not block a genuinely narrower later point.
    """
    x, y = word_set(a), word_set(b)
    shorter, longer = (x, y) if len(x) <= len(y) else (y, x)
    return len(shorter) >= 2 and shorter <= longer


def searches_left(lesson):
    ledger = lesson.acquisition
    return any(not r.completed for r in ledger.rounds) or len(ledger.rounds) < ledger.round_limit


def uid(prefix):
    return prefix + uuid.uuid4().hex[:20]

def cache_key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

class Jobs:
    def __init__(self, store, model, speech, settings, youtube=None):
        self.store, self.model, self.speech, self.settings = store, model, speech, settings
        self.youtube = youtube or YouTubeSources(store,settings)
        self.assets = Assets(store)
        self.assets.install_bundled()
        mode = getattr(settings, "image_search", "off")
        self.photos = PhotoSearch(self.assets) if mode == "openverse" else None
        if mode == "generate":
            self.photos = ImageGenerator(self.assets, settings.imagegen_python, settings.imagegen_model)
            threading.Thread(target=self.photos.warm, daemon=True).start()
        self.queue = asyncio.PriorityQueue(maxsize=settings.queue_size)
        self.cancel_flags = {}
        self.active = set()
        self.sequence = 0
        self.task = None
        self.closing = False
        self.enqueued_at = {}
        self.turn_started = {}
        self.current_short = {}
        self.accepted_at = {}

    def present(self, lesson):
        lesson.readiness = snapshot_readiness(lesson, self.settings.data, self.assets)
        return lesson

    def media_available(self, short):
        try:
            required_media(short, self.settings.data, self.assets)
            return True
        except (AppError, OSError):
            return False

    def measure(self, lesson, metric, elapsed):
        lesson.metrics[metric] = lesson.metrics.get(metric, 0) + elapsed
        short = self.current_short.get(lesson.id)
        if short is not None:
            short.timings[metric] = short.timings.get(metric, 0) + elapsed

    def start(self):
        self.store.recover()
        self.task = asyncio.create_task(self.worker())

    async def stop(self):
        self.closing = True
        if hasattr(self.photos, "stop"):
            self.photos.stop()
        for flag in self.cancel_flags.values():
            flag.set()
        # Provider calls finish or see the cancellation flag before the store closes.
        if self.task:
            await self.queue.put((-1, -1, None))
            await self.task

    def reserve(self, lid):
        if self.closing:
            raise AppError("SERVER_STOPPING", "The server is shutting down. Retry after restart.", 503)
        if lid in self.active:
            raise AppError("JOB_ACTIVE", "This lesson is already being prepared.", 409)
        if len(self.active) >= self.settings.queue_size or self.queue.full():
            raise AppError("QUEUE_FULL", "The local queue is full. Wait for a lesson to finish, then retry.", 429)
        self.active.add(lid)
        self.cancel_flags[lid] = threading.Event()

    def enqueue(self, lid):
        # FIFO turns: new arrivals cannot leapfrog an existing continuation.
        # At most queue_size - 1 other turns precede a requeued lesson.
        self.sequence += 1
        self.enqueued_at[lid] = time.monotonic()
        self.queue.put_nowait((0, self.sequence, lid))

    def create(self, request):
        existing = self.store.by_request(request.request_id)
        if existing:
            if existing.request.model_dump(exclude={"source_mode","source_ids"}) != request.model_dump():
                raise AppError("REQUEST_ID_CONFLICT", "This request ID belongs to a different lesson request.", 409)
            return existing
        lid = uid("lesson_")
        self.reserve(lid)
        now = time.time()
        lesson = Lesson(id=lid, request=SavedLearningRequest.model_validate(request.model_dump()), sources=[],
                        job=Job(id=uid("job_"), lesson_id=lid, created_at=now, updated_at=now),
                        planning=new_state(request.time_budget_seconds * 1000),
                        acquisition=AcquisitionLedger(per_round_limit=self.settings.rank_candidates,
                                                      transcript_limit=2 * self.settings.rank_candidates))
        self.accepted_at[lid] = time.monotonic()
        self.store.save(lesson)
        self.enqueue(lid)
        return lesson

    def cancel(self, lid):
        lesson = self.store.lesson(lid)
        if lesson.job.status == "complete":
            return lesson
        if lid in self.cancel_flags:
            self.cancel_flags[lid].set()
        lesson.status = "cancelled"
        lesson.job.status = "cancelled"
        lesson.job.stage = "cancelled"
        for short in lesson.shorts:
            if short.status != "ready":
                short.status = "cancelled"
        self.store.save(lesson)
        return lesson

    def retry(self, lid):
        lesson = self.store.lesson(lid)
        missing_media = any(s.status == "ready" and not self.media_available(s) for s in lesson.shorts)
        if lesson.job.status not in {"failed", "cancelled", "interrupted"} and not missing_media:
            raise AppError("RETRY_NOT_AVAILABLE", "Retry is available after a failure, cancellation, or server restart.", 409)
        self.reserve(lid)
        lesson.job.status = "queued"
        lesson.job.stage = "queued"
        lesson.job.error = None
        lesson.status = "partially_ready" if any(s.status == "ready" for s in lesson.shorts) else "queued"
        for short in lesson.shorts:
            if short.status != "ready" or not self.media_available(short):
                short.status = "queued"
                short.error = None
        self.store.save(lesson, resume=True)
        self.enqueue(lid)
        return lesson

    def explain(self, lid, short_id, request):
        lesson = self.store.lesson(lid)
        with self.store.lock:
            previous = self.store.db.execute("SELECT lesson_id,short_id,kind FROM requests WHERE id=?", (request.request_id,)).fetchone()
        if previous:
            if tuple(previous) != (lid, short_id, request.kind):
                raise AppError("REQUEST_ID_CONFLICT", "This request ID belongs to a different explanation.", 409)
            return lesson
        if lesson.job.status != "complete":
            raise AppError("LESSON_BUSY", "Wait for this lesson to finish before you add an explanation.", 409)
        if lesson.extra_allowance_ms >= 120000:
            raise AppError("EXPLANATION_LIMIT", "This lesson already has three extra shorts. Start a new lesson for more detail.")
        index = next((i for i, s in enumerate(lesson.shorts) if s.id == short_id), None)
        if index is None:
            raise AppError("SHORT_NOT_FOUND", "The selected short is missing.", 404)
        base = lesson.shorts[index]
        new = Short(id=uid("short_"), objective=("Show an example: " if request.kind == "example" else "Explain again: ") + base.objective, optional=True)
        self.reserve(lid)
        lesson.shorts.insert(index + 1, new)
        lesson.short_ids = [s.id for s in lesson.shorts]
        lesson.extra_allowance_ms += request.added_seconds * 1000
        refresh(lesson)
        lesson.job.status = "queued"
        lesson.job.stage = "queued"
        lesson.status = "partially_ready"
        with self.store.lock, self.store.db:
            self.store.db.execute("INSERT INTO requests VALUES (?,?,?,?)", (request.request_id, lid, short_id, request.kind))
            self.store.save(lesson)
        self.enqueue(lid)
        return lesson

    async def worker(self):
        while True:
            _, _, lid = await self.queue.get()
            if lid is None:
                self.queue.task_done()
                return
            requeue = False
            turn_start = time.monotonic()
            self.turn_started[lid] = turn_start
            queued = self.enqueued_at.pop(lid, turn_start)
            lesson = self.store.lesson(lid)
            self.measure(lesson, "queue_wait_seconds", max(0, turn_start - queued))
            lesson.metrics["worker_turns"] = lesson.metrics.get("worker_turns", 0) + 1
            self.store.save(lesson)
            try:
                flag = self.cancel_flags[lid]
                if any(s.status == 'ready' for s in lesson.shorts):
                    flag.deadline = None
                elif getattr(flag, 'deadline', None) is None:
                    flag.deadline = turn_start + self.settings.first_playable_timeout
                check_cancel(flag)
                requeue = await self.advance(lid)
            except Cancelled:
                # Preserve ready output; the cancel endpoint already persisted the user decision.
                lesson = self.store.lesson(lid)
                if lesson.job.status != "cancelled":
                    lesson.job.status = "interrupted"
                    lesson.status = "interrupted"
                    lesson.job.stage = "interrupted"
                    lesson.job.error = ErrorInfo(code="JOB_INTERRUPTED", message="The server stopped during preparation. Retry to keep ready shorts and continue.")
                    for short in lesson.shorts:
                        if short.status != "ready":
                            short.status = "failed"
                    self.store.save(lesson)
            except Exception as exc:
                flag = self.cancel_flags.get(lid)
                if flag is not None and flag.is_set():
                    requeue = False
                else:
                    lesson = self.store.lesson(lid)
                    error = ErrorInfo(code=exc.code if isinstance(exc, AppError) else "GENERATION_FAILED",
                                      message=exc.message if isinstance(exc, AppError) else "Lesson preparation failed. Retry or use a more focused learning goal.")
                    lesson.status = "partially_ready" if any(s.status == "ready" for s in lesson.shorts) else "failed"
                    lesson.job.status = "failed"
                    lesson.job.error = error
                    for short in lesson.shorts:
                        if short.status not in {"ready", "queued"}:
                            short.status, short.error = "failed", error
                    self.store.save(lesson)
            finally:
                # Use the latest authoritative copy, including cancellation/failure.
                lesson = self.store.lesson(lid)
                self.measure(lesson, "active_processing_seconds", time.monotonic() - turn_start)
                active_seconds = lesson.metrics["active_processing_seconds"]
                if active_seconds:
                    # Conservative uncached output over ALL active work, including
                    # plans, failed attempts and cache checks (never queue/downtime).
                    lesson.metrics["uncached_output_per_active_second"] = lesson.metrics.get("uncached_media_seconds", 0) / active_seconds
                self.store.save(lesson)
                self.current_short.pop(lid, None)
                self.turn_started.pop(lid, None)
                self.queue.task_done()
                if requeue and not self.closing and not self.cancel_flags[lid].is_set():
                    self.enqueue(lid)
                else:
                    self.active.discard(lid)
                    self.cancel_flags.pop(lid, None)
                    self.accepted_at.pop(lid, None)

    async def stage(self, lesson, name, short=None, status=None):
        check_cancel(self.cancel_flags[lesson.id])
        lesson.job.stage = name
        lesson.job.status = "running"
        if short is not None and status:
            short.status = status
        self.store.save(lesson)
        await asyncio.sleep(0)

    @staticmethod
    def youtube_sources(lesson):
        sources=[s for s in lesson.sources if s.source_type=="youtube"]
        for source in sources:
            require_youtube(source)
        return sources

    def acquisition_audit(self, lesson, kind):
        ledger = lesson.acquisition
        if kind == "search_cache_hit":
            ledger.search_cache_hits += 1
            ledger.search_provider_calls -= 1
        elif kind == "transcript_cache_hit":
            ledger.transcript_cache_hits += 1
            ledger.transcript_provider_calls -= 1
        elif kind == "supadata":
            ledger.transcript_http_calls += 1
        else:
            ledger.youtube_http_calls += 1
            ledger.youtube_quota_units += 100 if kind == "youtube_search" else 1
        # Persist at the actual HTTP boundary, including quota/network failures.
        self.store.save(lesson)

    async def acquire(self, lesson, cancel, focus=None):
        from functools import partial
        ledger = lesson.acquisition
        if not ledger.rounds:
            # Legacy adapters must not raise a smaller configured source limit.
            ledger.per_round_limit = min(ledger.per_round_limit, self.settings.rank_candidates)
            ledger.transcript_limit = min(ledger.transcript_limit, 2 * self.settings.rank_candidates)
        audit = partial(self.acquisition_audit, lesson)
        real_provider = isinstance(self.youtube, YouTubeSources)
        round_ = next((r for r in ledger.rounds if not r.completed), None)
        if round_ is None:
            if len(ledger.rounds) >= ledger.round_limit:
                return 0
            query = queries(lesson.request.goal, lesson.request.prior_knowledge, focus)[len(ledger.rounds)]
            round_ = AcquisitionRound(query=query, completed=True)
            ledger.rounds.append(round_)
            cached = False if real_provider else getattr(self.youtube, "search_cached", lambda q: False)(query)
            ledger.search_cache_hits += int(cached)
            ledger.search_provider_calls += int(not cached)
            # Reserve spend BEFORE the call. Failed calls also consume a round.
            await self.stage(lesson, "Searching YouTube")
            search = partial(self.youtube.search, audit=audit) if real_provider else self.youtube.search
            round_.candidates = await self.provider_work(lesson, search, query)
            round_.completed = False
            self.store.save(lesson)
        fetched = [(c, self.store.source(sid)) for sid in round_.source_ids
                   for c in round_.candidates if c["video_id"] == self.store.source(sid).video_id]
        for candidate in round_.candidates:
            check_cancel(cancel)
            vid = candidate["video_id"]
            if vid in ledger.tried_video_ids:
                continue
            if round_.transcript_attempts >= ledger.per_round_limit or len(ledger.tried_video_ids) >= ledger.transcript_limit:
                break
            ledger.tried_video_ids.append(vid)
            round_.transcript_attempts += 1
            cached = False if real_provider else getattr(self.youtube, "transcript_cached", lambda c: False)(candidate)
            ledger.transcript_cache_hits += int(cached)
            ledger.transcript_provider_calls += int(not cached)
            await self.stage(lesson, "Reading video transcripts")
            try:
                transcript = partial(self.youtube.transcript, audit=audit) if real_provider else self.youtube.transcript
                source = await self.provider_work(lesson, transcript, candidate, cancel)
                require_youtube(source)
            except AppError as exc:
                if exc.code in {"TRANSCRIPT_UNAVAILABLE", "INVALID_YOUTUBE_TRANSCRIPT"}:
                    continue
                raise
            self.store.put_source(source)
            round_.source_ids.append(source.id)
            # Keep pending successful transcripts through cancellation/restart.
            self.store.save(lesson)
            fetched.append((candidate, source))
        chosen = await self.rank(lesson, fetched, cancel, focus)
        check_cancel(cancel)
        for source in chosen:
            if not any(s.id == source.id for s in lesson.sources):
                lesson.sources.append(source)
        round_.completed = True
        self.store.save(lesson)
        return len(chosen)

    async def acquire_more(self, lesson, cancel, focus):
        """Optional search while expanding a lesson that already has videos.

        A source error here (YouTube/Supadata failure, credits, work limit)
        stops adding material; it never fails the lesson or its ready videos.
        Cancellation still propagates. Returns (sources added, failure detail).
        """
        try:
            return await self.acquire(lesson, cancel, focus), None
        except AppError as exc:
            lesson.metrics["expansion_search_failures"] = lesson.metrics.get("expansion_search_failures", 0) + 1
            return 0, (f"The extra search for more videos failed: {exc.message[:200]} "
                       "The lesson finished with what was ready instead of padding.")

    async def provider_work(self, lesson, function, *args):
        state = lesson.planning
        if state and state.work_seconds >= state.work_limit_seconds:
            raise AppError("GENERATION_LIMIT", "This lesson reached its persisted work-time limit. Ready videos are saved.", 422)
        started = time.monotonic()
        try:
            return await asyncio.to_thread(function, *args)
        finally:
            elapsed = time.monotonic() - started
            name = getattr(function, "__name__", getattr(getattr(function, "func", None), "__name__", "provider"))
            self.measure(lesson, f"{name}_seconds", elapsed)
            if state:
                state.work_seconds += elapsed
            self.store.save(lesson)

    def generate(self, lesson, contract, task, cancel, validate=None, *, metric=None):
        """Reserve worst-case schema attempts; retries cannot reset local work."""
        state = lesson.planning if lesson else None
        if state:
            if state.model_call_units + 3 > state.model_call_limit or state.work_seconds >= state.work_limit_seconds:
                raise AppError("GENERATION_LIMIT", "This lesson reached its persisted generation limit. Ready videos are saved; start a new, more focused request.", 422)
            state.model_call_units += 3
            self.store.save(lesson)
        started = time.monotonic()
        # Aggregate only this call's counters. Bounded field-error diagnostics
        # remain local to the adapter and are not persisted in lesson metrics.
        self.model.attempts = []
        try:
            if getattr(self.model, 'compact_authoring', False):
                task = {**task, 'compact_authoring': True}
            return self.model.generate(contract, task, cancel, validate)
        finally:
            elapsed = time.monotonic() - started
            if lesson is not None:
                name = metric or {"LessonPlan": "plan" if task.get("phase") == "core" else "continuation_plan",
                                  "ModelStoryboard": "draft", "SupportCheck": "review", "CandidateRanking": "ranking"}.get(contract.__name__, "model")
                self.measure(lesson, f"{name}_seconds", elapsed)
                attempts = getattr(self.model, "attempts", [])
                self.measure(lesson, "model_attempts", len(attempts))
                self.measure(lesson, "model_repairs", sum(a["attempt"] > 1 for a in attempts))
                self.measure(lesson, "model_first_pass_successes", sum(a["attempt"] == 1 and a["kind"] == "success" for a in attempts))
                for field in ("prompt_tokens", "completion_tokens", "cached_prompt_tokens"):
                    self.measure(lesson, field, sum(a.get(field, 0) for a in attempts))
                if state:
                    state.work_seconds += elapsed
                self.store.save(lesson)

    def speech_profile(self, lesson):
        key = cache_key({"speech_prediction_version": 1, "speech": lesson.provider_settings["speech"]})
        samples = self.store.cache_get(key) or []
        return key, samples, speech_prediction(samples)

    async def plan_batch(self, lesson, cancel, *, initial=False):
        state = lesson.planning
        budget = lesson.request.time_budget_seconds * 1000 if initial else remaining_for_batch(lesson)
        previous = [] if initial else [o for o in lesson.objectives if o.curriculum_role != "closing"]
        count = min(state.batch_limit, state.activity_limit - len(lesson.objectives), budget // useful_minimum(lesson))
        limited = (state.expansion_attempts >= state.expansion_limit or
                   state.model_call_units + 15 > state.model_call_limit or state.work_seconds >= state.work_limit_seconds)
        if count < 1 or limited:
            state.completion_reason = "generation_limit" if len(lesson.objectives) >= state.activity_limit or limited else "budget_fit"
            state.completion_detail = "No further useful activity fits within the remaining budget or bounded generation limit."
            return False
        state.expansion_attempts += 1
        self.store.save(lesson)
        await self.stage(lesson, "planning the lesson" if initial else "expanding the lesson outline")
        focus = " ".join(g.query_intent for g in state.missing_coverage) or lesson.request.goal
        # Rotate bounded retrieval toward unused passages; drafts still require exact selected IDs.
        used = {sid for e in state.coverage for sid in e.evidence_segment_ids}
        segments, key_base = self.context(lesson, focus, excluded_ids=used if not initial else ())
        task = {"task": f"Plan a bounded batch of 1 to {count} useful source-supported outcomes for this SAME goal. "
                "Do not broaden a narrow goal, paraphrase covered claims or use transcript word count as proof of support. "
                "Use distinct observable outcomes (explain, trace, compare, predict, apply); stable new concept_id values, earlier dependency_ids, "
                "learner relevance, evidence_segment_ids and visual_intent. Each clip has one teaching purpose. "
                "Core supplies needed concepts; extensions add supported examples, mechanisms, caveats or applications; closing recaps earlier dependencies. "
                "For the initial batch include necessary core and a reserved closing recap where useful; a very narrow one-clip goal can close with its own takeaway. "
                "For later batches add only useful extensions, not another introduction or recap. Do not replace the committed core or closing. "
                "If the requested goal itself is unsupported, return sufficient_evidence=false and objectives=[]. "
                "In an extension batch, if no DISTINCT supported content remains, return objectives=[] and explain why. "
                "covered_outcomes is a compact list of concept_id|outcome strings; never repeat these outcomes. "
                "If a specific missing facet could help this outcome, return up to two missing_coverage entries with focused query_intent, not a broader topic. "
                f"Aim for {DEFAULT_TARGET_MS}ms media per clip (15000 to 40000ms); sum targets plus 20000ms for each checkpoint must fit {budget}ms. "
                "Practice is untimed allowance; use a checkpoint only at a useful boundary that fits. Preserve a useful closing without double counting it. "
                "Use at most two source-only examples across the lesson; facts are exact excerpts, no invented examples or numbers. "
                "Existing examples may be referenced; do not re-declare them. Prerequisites=[] when none. "
                "Keep output compact for the local token bound. Templates: " + TEMPLATE_GUIDE,
                "plan_version": 3, "max_objectives": count, "max_target_ms": min(40000, budget),
                "request": key_base["request"], "phase": "core" if initial else "extension",
                "remaining_ms": budget, "revision": state.revision,
                "covered_outcomes": [f"{o.concept_id}|{o.learning_outcome[:48]}" for o in previous],
                "covered_points": [{"title": o.title, "outcome": o.learning_outcome} for o in previous],
                "nothing_new": state.nothing_new[-12:],
                "sources_exhausted": not initial and state.repeat_skips_since_sources >= 2 and searches_left(lesson),
                "recent_coverage": [{"id": e.concept_id, "claim": e.used_claims[0][:100] if e.used_claims else "",
                                     "segments": e.evidence_segment_ids[:2], "facets": e.supported_facets}
                                    for e in state.coverage[-4:]],
                "examples": [e.model_dump() for e in lesson.examples],
                "segments": [s.model_dump() for s in segments]}
        def valid(plan):
            if not initial:
                # Identical proposed work is exhaustion, not a reason to publish duplicates.
                # Outcomes alone missed a re-planned "Safe Falling Mechanics" with an
                # identical title, so near-identical titles count as duplicates too.
                # Extra core/recap items in an extension batch are dropped the same way:
                # the committed core/closing stay, never a reason to fail optional expansion.
                dropped = {o.concept_id for o in plan.objectives if o.curriculum_role != "extension" or any(
                    o.concept_id == p.concept_id or
                    (o.teaching_role != "recap" and (similar(o.learning_outcome or o.title, p.learning_outcome or p.title, .8)
                                                     or similar(o.title, p.title, .8) or contained_title(o.title, p.title)))
                    for p in lesson.objectives)}
                # Real failure: a kept item depended on a dropped repeat, so the
                # whole batch failed validation. Drop anything built on a dropped item.
                while True:
                    more = {o.concept_id for o in plan.objectives if set(o.dependency_ids) & dropped} - dropped
                    if not more:
                        break
                    dropped |= more
                plan.objectives = [o for o in plan.objectives if o.concept_id not in dropped]
                plan.examples = [e for e in plan.examples if e.id not in {old.id for old in lesson.examples}]
            check_plan(plan, segments, count, budget, calibrated=True, previous=previous,
                       examples_before=lesson.examples)
            if len(lesson.examples) + len(plan.examples) > 2:
                raise ValueError("Use at most two recurring examples across the lesson.")
        key = cache_key({**key_base, "stage": "session-plan", "task": task})
        cached = self.store.cache_get(key)
        try:
            plan = LessonPlan.model_validate(cached) if cached else await asyncio.to_thread(self.generate, lesson, LessonPlan, task, cancel, valid)
        except AppError as exc:
            # Expansion is optional. A bounded model failure here stops adding
            # material; queued work (e.g. the committed recap) still finishes.
            if initial or exc.code not in {"MODEL_DATA_INVALID", "MODEL_OUTPUT_INVALID", "MODEL_OUTPUT_TRUNCATED", "MODEL_TASK_TIMEOUT"}:
                raise
            state.completion_reason = "generation_limit"
            state.completion_detail = ("The model could not plan more distinct material within its bounded attempts, "
                                       "so the lesson finished with what was ready instead of padding.")
            lesson.metrics["expansion_plan_failures"] = lesson.metrics.get("expansion_plan_failures", 0) + 1
            self.store.save(lesson)
            return False
        valid(plan)
        check_cancel(cancel)
        lesson.metrics["plan_cache_hits"] = lesson.metrics.get("plan_cache_hits", 0) + int(bool(cached))
        if initial:
            lesson.metrics["plan_cache_hit"] = int(bool(cached))
        state.missing_coverage = plan.missing_coverage
        if task["sources_exhausted"] and plan.missing_coverage:
            # Drafts kept repeating the current sources: search for a related
            # subtopic before planning more from the same exhausted material.
            focus = " ".join(g.query_intent for g in plan.missing_coverage)
            added, failure = await self.acquire_more(lesson, cancel, focus)
            if added:
                state.repeat_skips_since_sources = 0
                return await self.plan_batch(lesson, cancel)
            state.completion_reason = "source_limit"
            state.completion_detail = failure or ("The sources ran out of distinct material and the search limit was reached, "
                                                  "so the lesson finished with what was ready instead of padding.")
            self.store.save(lesson)
            return False
        if not plan.sufficient_evidence or not plan.objectives:
            # The original two-round allowance is shared with focused acquisition.
            # A short lesson searches again even when the model suggests no query:
            # the student asked for the full time, so fetch new videos first.
            if plan.missing_coverage or not plan.sufficient_evidence or (not initial and searches_left(lesson)):
                focus = " ".join(g.query_intent for g in plan.missing_coverage) or lesson.request.goal
                added, failure = (await self.acquire(lesson, cancel, focus), None) if initial else await self.acquire_more(lesson, cancel, focus)
                if added:
                    state.repeat_skips_since_sources = 0
                    return await self.plan_batch(lesson, cancel, initial=initial)
                state.completion_reason = "source_limit"
                state.completion_detail = failure or ("The videos found ran out of new material and the search limit was reached, "
                                                      "so the lesson finished with what was ready instead of padding.")
            else:
                state.completion_reason = "coverage_exhausted"
                state.completion_detail = plan.reason or "The available sources do not support more distinct useful outcomes for this goal."
            if initial:
                state.completion_detail = plan.reason or state.completion_detail
            if initial:
                raise AppError("INSUFFICIENT_EVIDENCE", "Available YouTube transcripts cannot support this goal within the search limit. " + state.completion_detail, 422)
            self.store.save(lesson)
            return False
        if not cached:
            self.store.cache_put(key, plan.model_dump())
        insert = next((i for i, s in enumerate(lesson.shorts) if s.curriculum_role == "closing" and s.status != "ready"), len(lesson.shorts))
        if not initial:
            for closing in lesson.shorts:
                if closing.curriculum_role == "closing" and closing.status != "ready" and not closing.optional:
                    closing.target_duration_ms = useful_minimum(lesson)
        objective_insert = next((i for i, o in enumerate(lesson.objectives) if o.curriculum_role == "closing"), len(lesson.objectives))
        lesson.objectives[objective_insert:objective_insert] = plan.objectives
        lesson.examples.extend(plan.examples)
        lesson.shorts[insert:insert] = planned_shorts(plan, lambda: uid("short_"))
        _, _, (_, uncertainty) = self.speech_profile(lesson)
        for short in lesson.shorts[insert:insert + len(plan.objectives)]:
            short.duration_uncertainty_ms = uncertainty
        state.coverage.extend(coverage_for(o) for o in plan.objectives)
        state.revision += 1
        lesson.short_ids = [s.id for s in lesson.shorts]
        lesson.teaching_plan_version = 2
        if initial:
            lesson.plan_diagnostics = ([plan.reason] if plan.reason else []) + plan_diagnostics(plan)
        refresh(lesson)
        if initial:
            lesson.original_planned_duration_ms = lesson.planned_duration_ms
        self.store.save(lesson)
        return True

    async def rank(self,lesson,fetched,cancel,focus=None):
        if getattr(self.model, 'compact_authoring', False):
            # Ranking is optional: use the same source-order fallback previously
            # used after model failure, without spending 3 calls before playback.
            check_cancel(cancel)
            lesson.metrics['ranking_model_skipped'] = lesson.metrics.get('ranking_model_skipped', 0) + 1
            chosen, channels = [], {}
            for candidate, source in fetched:
                channel = candidate.get('channel', '')
                if channel and channels.get(channel, 0) >= 2:
                    continue
                chosen.append(source)
                channels[channel] = channels.get(channel, 0) + 1
                if len(chosen) == KEEP:
                    break
            return chosen
        if len(fetched)<=1:
            return [s for _,s in fetched]
        await self.stage(lesson,"Choosing the best videos")
        task=ranking_task(lesson.request,fetched,focus)
        key=cache_key({"stage":"rank","settings":lesson.provider_settings,"task":task})
        cached=self.store.cache_get(key)
        try:
            ranking=CandidateRanking.model_validate(cached) if cached else await asyncio.to_thread(self.generate,lesson,CandidateRanking,task,cancel,validator(fetched))
        except AppError as exc:
            if exc.code not in {"MODEL_DATA_INVALID", "MODEL_OUTPUT_INVALID", "MODEL_OUTPUT_TRUNCATED"}:
                raise
            # Ranking only improves the choice. Keep YouTube's order when the model cannot rank.
            return [s for _,s in fetched][:KEEP]
        check_cancel(cancel)
        lesson.metrics["ranking_cache_hits"] = lesson.metrics.get("ranking_cache_hits", 0) + int(bool(cached))
        if not cached:
            self.store.cache_put(key,ranking.model_dump())
        lesson.video_rankings.extend(ranking.scores)
        return pick(ranking,fetched)

    async def reviewed(self,draft,task,segments,valid,cancel,short=None,lesson=None):
        # A rejected short is rewritten once with the reviewer's reason before the lesson fails.
        for attempt in range(2):
            try:
                from types import SimpleNamespace
                from functools import partial
                reviewer = SimpleNamespace(generate=partial(self.generate, lesson)) if lesson else self.model
                review = await asyncio.to_thread(verify_support, reviewer, draft, segments, cancel, task.get("teaching"))
                check_cancel(cancel)
                if short is not None:
                    short.source_review_status = "model_supported"
                    short.source_review_reason = review.reason
                    short.teaching_diagnostics = review.teaching_issues
                return draft
            except ValueError as exc:
                if short is not None:
                    short.source_review_status = "unchecked"
                    short.review_repair_reasons = (short.review_repair_reasons + [str(exc)[:500]])[-2:]
                    if lesson is not None:
                        check_cancel(cancel)
                        self.store.save(lesson)
                if attempt:
                    teaching_failure = str(exc).startswith("The teaching review")
                    raise AppError("TEACHING_QUALITY_FAILED" if teaching_failure else "UNSUPPORTED_CLAIM",
                                   "The bounded teaching review rejected this short. Retry or use a more focused learning goal." if teaching_failure else "The model source review could not support this short. Retry or use a more focused learning goal.", 422) from exc
                retry={**task,"task":task["task"]+" A reviewer rejected the previous version: "+str(exc)[:400]+" Fix that problem."}
                draft = attach_evidence(await asyncio.to_thread(self.generate, lesson, ModelStoryboard, retry, cancel, valid, metric="repair"), segments)
        return draft

    def cache_draft(self, key, draft, short):
        self.store.cache_put(key, {"draft": draft.model_dump(), "source_review_reason": short.source_review_reason,
                                   "teaching_diagnostics": short.teaching_diagnostics, "review_repair_reasons": short.review_repair_reasons})

    def context(self,lesson,focus=None,required_ids=(),excluded_ids=()):
        sources=self.youtube_sources(lesson)
        segments=retrieve(sources,focus or lesson.request.goal,required_ids=required_ids,excluded_ids=excluded_ids)
        key_base={"source_policy":"youtube-v1","sources":[{"id":s.id,"hash":s.content_hash} for s in sources],
            "settings":lesson.provider_settings,"storyboard_version":STORYBOARD_VERSION,"timeline_compiler_version":COMPILER_VERSION,
            "teaching_version":TEACHING_VERSION,"planning_version":PLANNING_VERSION if lesson.planning else "legacy",
            "request":lesson.request.model_dump(exclude={"request_id","source_mode","source_ids"})}
        return segments,key_base

    @staticmethod
    def pin_provider(lesson, selected):
        saved = lesson.provider_settings
        if saved:
            if "provider" in saved:
                compatible = saved == selected
            else:
                # Pre-migration fingerprints were Ollama-only. Compare every
                # saved field; do not retrofit new metadata onto historical media.
                compatible = selected.get("provider", "ollama") == "ollama" and all(selected.get(k) == v for k, v in saved.items())
            if not compatible and "provider" in saved:
                # Same-runtime authoring fixes may resume unpublished lessons.
                # Preserve the committed plan, source/work allowances and IDs;
                # once media is ready, never silently rebind its provenance.
                repair_versions = {"prompt_version", "parser_version", "repair_policy_version", "authoring_version"}
                same_runtime = ({k: v for k, v in saved.items() if k not in repair_versions}
                                == {k: v for k, v in selected.items() if k not in repair_versions})
                unpublished = (not lesson.coverage_history and not any(
                    s.status == 'ready' or s.audio_path or s.scenes or s.narration_units for s in lesson.shorts))
                if same_runtime and unpublished:
                    lesson.provider_settings = dict(selected)
                    return
            if not compatible:
                raise AppError("PROVIDER_SETTINGS_MISMATCH", "This unfinished lesson belongs to a different provider/model/settings profile. Restore its original profile or create a fresh lesson. Ready output and source allowances are preserved.", 422)
        else:
            lesson.provider_settings = selected

    async def repair_media(self, lesson, short, cancel):
        speech_settings = self.speech.fingerprint()
        if short.provider_settings.get("speech", lesson.provider_settings.get("speech")) != speech_settings:
            raise AppError("MEDIA_REPAIR_SETTINGS", "Restore this short's original speech settings before repairing its missing audio.", 422)
        await self.provider_work(lesson, self.speech.prepare)
        units = [u.model_copy(deep=True) for u in short.narration_units]
        audio, measured, _ = await self.provider_work(lesson, self.speech.synthesize, units, short.audio_path.removesuffix(".wav"), cancel)
        check_cancel(cancel)
        if measured != short.measured_duration_ms or [(u.start_ms, u.end_ms) for u in units] != [(u.start_ms, u.end_ms) for u in short.narration_units]:
            raise AppError("MEDIA_REPAIR_TIMING", "The repaired voice no longer matches the published timeline. Restore the original speech provider/settings; ready content is unchanged.", 422)
        short.audio_path = audio
        required_media(short, self.settings.data, self.assets)
        short.status = "ready"
        Short.model_validate(short.model_dump())
        refresh(lesson)
        self.store.save(lesson)

    async def advance(self, lid):
        started = time.monotonic()
        lesson = self.store.lesson(lid)
        cancel = self.cancel_flags[lid]
        check_cancel(cancel)
        if lesson.shorts and all(s.status == "ready" for s in lesson.shorts):
            closing_ready = any(s.curriculum_role == "closing" and not s.optional for s in lesson.shorts)
            if not needs_expansion(lesson) or closing_ready:
                # Finalise validated media without requiring providers to remain
                # online for an otherwise unnecessary completion checkpoint.
                self.complete(lesson)
                return False
        # Published media repair must not depend on an obsolete/unavailable LLM
        # or spend source credits. Keep historical provenance and exact timings.
        short = next((s for s in lesson.shorts if s.status != "ready"), None)
        if short and short.audio_path and short.narration_units and short.measured_duration_ms:
            await self.repair_media(lesson, short, cancel)
            return True
        provider_started = time.monotonic()
        await self.stage(lesson, "checking local providers")
        fingerprint = await self.provider_work(lesson, self.model.fingerprint)
        selected = {**fingerprint, "speech": self.speech.fingerprint(), "language": lesson.request.language}
        self.pin_provider(lesson, selected)
        await self.provider_work(lesson, self.speech.prepare)
        check_cancel(cancel)
        if "provider_load_seconds" not in lesson.metrics:
            lesson.metrics["provider_load_seconds"] = time.monotonic() - provider_started
        source_start=time.monotonic()
        if not self.youtube_sources(lesson):
            while any(not r.completed for r in lesson.acquisition.rounds) or len(lesson.acquisition.rounds) < lesson.acquisition.round_limit:
                added=await self.acquire(lesson,cancel)
                if added:
                    break
            if not self.youtube_sources(lesson):
                raise AppError("NO_USABLE_TRANSCRIPTS","No accessible English YouTube transcripts were found within this lesson's search limit. Check source access, then start a new, more focused request; retry does not reset the acquisition allowance.",422)
        lesson.metrics["source_acquisition_seconds"]=lesson.metrics.get("source_acquisition_seconds",0)+time.monotonic()-source_start
        segments,key_base=self.context(lesson)
        if not lesson.shorts:
            lesson.status = "preparing"
            await self.stage(lesson, "planning the lesson")
            planning_started = time.monotonic()
            # Legacy empty interrupted jobs can resume, but old ready media is never migrated.
            if lesson.planning is None:
                lesson.planning = new_state(lesson.request.time_budget_seconds * 1000)
            if lesson.planning.completion_reason:
                # Failed initial planning may use the remaining persisted allowance.
                lesson.planning.completion_reason = None
            if not await self.plan_batch(lesson, cancel, initial=True):
                raise AppError("GENERATION_LIMIT", "Initial planning reached its persisted operational limit. Start a new, more focused request.", 422)
            lesson.metrics["planning_seconds"] = time.monotonic() - planning_started
            self.store.save(lesson)
        short = next((s for s in lesson.shorts if s.status != "ready"), None)
        if (short is None or (short.curriculum_role == "closing" and not short.optional)) and needs_expansion(lesson):
            # Append before unpublished closing only; never move a ready/selected activity.
            if not any(s.curriculum_role == "closing" and s.status == "ready" and not s.optional for s in lesson.shorts):
                await self.plan_batch(lesson, cancel)
                short = next((s for s in lesson.shorts if s.status != "ready"), None)
        if short is None:
            self.complete(lesson)
            return False
        if lesson.planning:
            state = lesson.planning
            if state.candidate_attempts >= state.candidate_limit:
                raise AppError("GENERATION_LIMIT", "The persisted candidate limit was reached. Ready videos are saved; use a more focused request.", 422)
            state.candidate_attempts += 1
            if short.curriculum_role == "closing" and not short.optional:
                short.target_duration_ms = max(useful_minimum(lesson), min(40000, candidate_capacity(lesson, short)))
            self.store.save(lesson)
        self.current_short[lid] = short
        preparation_start = time.monotonic()
        index = lesson.shorts.index(short)
        objective = objective_for(lesson, short)
        example = next((e for e in lesson.examples if e.id == short.example_id), None)
        required_ids = list(dict.fromkeys((objective.evidence_segment_ids if objective and not short.optional else []) +
                                         (example.evidence_segment_ids if example else [])))
        focus=f"{lesson.request.goal} {short.learning_outcome or short.objective}"
        segments,key_base=self.context(lesson,focus,required_ids)
        if short.optional:
            while True:
                support=await asyncio.to_thread(self.generate,lesson,LessonPlan,
                    {"task":"Check whether the supplied YouTube transcript passages support this additional learning point. Return sufficient_evidence=false if not. Return objectives=[]. Do not use outside knowledge.","goal":lesson.request.goal,"objective":short.objective,"segments":[s.model_dump() for s in segments]},cancel)
                check_cancel(cancel)
                if support.sufficient_evidence:
                    break
                if not await self.acquire(lesson,cancel,focus):
                    raise AppError("INSUFFICIENT_EVIDENCE","Available YouTube transcripts cannot support this additional short. Retry or start a more focused lesson.",422)
                segments,key_base=self.context(lesson,focus)
        template = "example" if short.optional and short.objective.startswith("Show") else objective.template if objective else "process"
        if template == "chart" and not chartable(s.text for s in segments if s.id in required_ids):
            # Real failure: "Soil Nutrients" was planned as a chart but its passage has
            # no numbers, so the model plotted invented 1/2/3 values and the short
            # failed. Compare the items instead; same teaching, no made-up data.
            template = "comparison"
            lesson.metrics["chart_without_numbers"] = lesson.metrics.get("chart_without_numbers", 0) + 1
        history = teaching_context(lesson, short)
        earlier_narration = history["recent_narration"]
        earlier_questions = [s.question.prompt for s in lesson.shorts[:index] if s.question][-6:]
        teaching = {"goal": lesson.request.goal, "learner": lesson.request.prior_knowledge,
                    "outcome": short.learning_outcome or short.objective, "role": short.teaching_role,
                    "plan": objective.model_dump() if objective and not short.optional else None,
                    "example": example.model_dump() if example else None, "history": history}
        asset_candidates = self.assets.candidates()
        capacity = candidate_capacity(lesson, short) if lesson.planning else 40000
        target_ms = min(short.target_duration_ms, capacity)
        if target_ms < MIN_TARGET_MS and lesson.planning:
            raise AppError("BUDGET_FIT_FAILED", "The remaining budget cannot support this unpublished activity. Ready content is unchanged.", 422)
        profile_key, samples, (ms_per_word, uncertainty) = self.speech_profile(lesson)
        target_words = max(30, min(90, round((target_ms - min(2000, uncertainty)) / ms_per_word)))
        short_key = cache_key({**key_base, "target_duration_ms": target_ms, "target_words": target_words, "visual_version": VISUAL_VERSION, "asset_candidates": [a["id"] for a in asset_candidates], "teaching": teaching, "template": template, "question": short.question_required,
                               "earlier_questions": earlier_questions, "segments": [s.id for s in segments], "stage": "draft"})
        cached = self.store.cache_get(short_key)
        await self.stage(lesson, "preparing the first short" if index == 0 else f"preparing short {index + 1}", short, "generating")
        # Found or generated alongside drafting and speech, so it rarely delays the short.
        cover = asyncio.create_task(self.cover_photo(lesson, short, cancel))
        model_start = time.monotonic()
        def valid(content):
            draft = attach_evidence(content, segments) if isinstance(content, ModelStoryboard) else content
            for visual in draft.scenes:
                if visual.kind == "image":
                    if visual.payload.asset_id not in {a["id"] for a in asset_candidates}:
                        raise ValueError("Select an existing allowed managed asset ID.")
                    asset = self.assets.attach(visual.payload.asset_id)
                    if (asset.width, asset.height) != (visual.payload.width, visual.payload.height):
                        raise ValueError("Use the managed asset's actual dimensions.")
            validate_draft(draft, segments, short.question_required, earlier_narration,
                           allow_recap=short.teaching_role == "recap", earlier_questions=earlier_questions, example=example)
        task = {"task": "Teach one learning outcome with a supported visual demonstration. Return a complete ModelStoryboard version 2. "
                    "Use as many brief beats as the content needs (2 to 8), one per item: question/situation, the steps or parts, takeaway. Never pad or cut a list to a fixed size. "
                    "Use 40 to 80 total spoken words, not more words just to add beats. Each beat has a unique beat_id, purpose, scene_id, cited segment_id and explicit operations. "
                    "Use 1 to 3 scenes in contiguous order. A changed scene_id replaces the scene; never return to an earlier scene. "
                    "Reveal nodes before focusing, moving, hiding or changing their state; connect only after both endpoints are revealed. "
                    "Show concepts changing, not every label at once. Explicitly target the concept being taught, not a name mentioned as absent. "
                    "State changes select an authored state_id for that target with supported label/detail/role. Use source-only examples; no synthetic substitutions or invented benchmarks. "
                    "Preserve the supplied example entities and facts. Tell it as a short story: open with a real situation, problem or question from the passages that leads into the outcome, define necessary terms once, show what happens and why, then resolve it with a concise takeaway or condition. Use only situations, people and examples from the passages; never invent characters or hypothetical anecdotes. "
                    "Every node needs a reveal and every connection a connect. For cycle supply the explicit loop connections; dos_donts has no connections. "
                    "Use the compact coverage history to add new meaning, not synonym-based duplicates. An explicit recap may briefly revisit its dependencies without claiming new coverage. "
                    "A distinct application of a known concept is allowed. Avoid generic hooks, filler and false guarantees. "
                    "A required checkpoint tests the outcome actually taught: prediction/application over trivia, one unambiguous correct_answer, "
                    "1 to 3 plausible distractors representing misconceptions and supported reasoning in explanation. Do not repeat earlier questions. Question must be null unless required. "
                    "Choose the format for the teaching intent, not random variety: diagram for relationships/processes, table for lookup, code for exact source snippets, chart for quantitative comparison, image only when an allowed candidate is relevant. "
                    "Diagram scenes use as many nodes as the content needs (2 to 8), node_0 through node_7 and unique slots; never pad or truncate a list to a fixed size. "
                    "Table operations target row_0 through row_7 or row_0_c0 cells; code targets line_1 through line_30; charts target point_0 through point_7; images target image or annotation_0 through annotation_5. "
                    "Non-diagram renderers allow only reveal/hide/focus. Reveal every row, code line, chart point, image and annotation before focus/hide; cells inherit row visibility. "
                    "Code is display-only and must be copied exactly from its cited segment, never invented or executed. Chart values and units must match each point's cited passage. "
                    "Images select only candidate asset_id and actual dimensions. Asset rights do not prove a claim; captions/annotations need source support. Use a simpler supported format if no suitable asset exists. "
                    f"Suggested visual intent {template}: {TEMPLATES[template]} The diagram chart template is legacy-only. Do not author timestamps or renderer code.",
                "target_duration_ms": target_ms, "max_duration_ms": capacity, "target_words": target_words,
                "objective": short.objective, "template": template, "question_required": short.question_required,
                "learner": lesson.request.prior_knowledge, "teaching": teaching, "earlier_questions": earlier_questions,
                "asset_candidates": asset_candidates, "visual_version": VISUAL_VERSION,
                "segments": [s.model_dump() for s in segments]}
        task["task"] += f" Draft near {target_words} spoken words for about {target_ms}ms. Measured media must fit {capacity}ms without slowing speech or padding."
        if cached:
            short.source_review_status = "model_supported"
            short.source_review_reason = cached["source_review_reason"]
            short.teaching_diagnostics = cached["teaching_diagnostics"]
            short.review_repair_reasons = cached["review_repair_reasons"]
        try:
            draft = StoryboardDraft.model_validate(cached["draft"]) if cached else await self.draft_with_fallback(lesson, task, cancel, valid, segments)
            valid(draft)
            short.timings["generation_seconds"] = time.monotonic() - model_start
            await self.stage(lesson, "validating source references", short, "validating")
            validation_start = time.monotonic()
            if not cached:
                draft = await self.reviewed(draft, task, segments, valid, cancel, short, lesson)
                self.cache_draft(short_key, draft, short)
            short.timings["validation_seconds"] = time.monotonic() - validation_start
            await self.stage(lesson, "generating local speech", short, "synthesizing")
            speech_start = time.monotonic()
            # Duration repair is separate from the two schema repairs; voice speed remains fixed.
            repair_words = max(30, min(50, int(target_words * .7)))
            for duration_attempt in range(2):
                speech_key = cache_key({"texts": [u.text for u in draft.narration_units], "settings": lesson.provider_settings, "sources": key_base["sources"], "language": lesson.request.language,
                                        "storyboard_version": STORYBOARD_VERSION, "timeline_compiler_version": COMPILER_VERSION})
                try:
                    audio, duration, audio_cached = await self.provider_work(lesson, self.speech.synthesize, draft.narration_units, speech_key, cancel)
                    if duration > capacity:
                        words = len(" ".join(u.text for u in draft.narration_units).split())
                        repair_words = max(30, int(words * capacity / duration * .9))
                        raise AppError("SPEECH_DURATION", f"Measured speech must fit the remaining {capacity}ms. Shorten to about {repair_words} words.", 422)
                    break
                except AppError as exc:
                    if exc.code != "SPEECH_DURATION":
                        raise
                    if duration_attempt:
                        if lesson.planning and not short.optional and short.curriculum_role in {"extension", "closing"}:
                            # A good but unfit candidate stays unpublished. Defer its
                            # dependent queued work too, rather than dropping prerequisites.
                            deferred = {short.concept_id}
                            while True:
                                dependents = {o.concept_id for o in lesson.objectives if set(o.dependency_ids) & deferred}
                                if dependents <= deferred:
                                    break
                                deferred |= dependents
                            removed = [s for s in lesson.shorts if s.status != "ready" and s.concept_id in deferred]
                            lesson.shorts = [s for s in lesson.shorts if s not in removed]
                            lesson.short_ids = [s.id for s in lesson.shorts]
                            state = lesson.planning
                            state.deferred_concept_ids.extend(s.concept_id for s in removed)
                            state.revision += 1
                            refresh(lesson)
                            # Real run: one slightly-too-long short stopped the lesson at
                            # 77% with 68 s free. Only stop when no useful short still fits.
                            if remaining_for_batch(lesson) < 2 * useful_minimum(lesson):
                                state.completion_reason = "budget_fit"
                                state.completion_detail = "Additional supported content could not fit the remaining authorised time after a bounded speech repair. Ready videos were not changed or padded."
                            else:
                                state.skipped_points = (state.skipped_points + [f"{s.objective[:80]} ({SKIP_REASONS['SPEECH_DURATION']})" for s in removed])[-80:]
                                state.failed_skips_in_row += 1
                                if state.failed_skips_in_row >= 3:
                                    state.completion_reason = "generation_limit"
                                    state.completion_detail = ("Several planned points in a row could not be made accurately, "
                                                               "so the lesson stopped adding material instead of publishing them.")
                            check_cancel(cancel)
                            self.store.save(lesson)
                            return True
                        raise
                    task["target_words"] = repair_words
                    task["task"] += " " + exc.message + f" Shorten to about {repair_words} words. Repair only this unpublished activity, not any ready content."
                    draft = attach_evidence(await asyncio.to_thread(self.generate, lesson, ModelStoryboard, task, cancel, valid, metric="repair"), segments)
                    draft = await self.reviewed(draft, task, segments, valid, cancel, short, lesson)
                    self.cache_draft(short_key, draft, short)
            else:
                raise AppError("SPEECH_DURATION", "Speech could not fit the short duration limit.", 422)
        except AppError as exc:
            # Repeating published shorts means this outcome has nothing new;
            # skip it instead of failing the lesson or publishing filler.
            if exc.code == "NO_NEW_CONTENT" and self.skip_repeated(lesson, short, cancel):
                return True
            if exc.code in SKIPPABLE and self.skip_failed(lesson, short, exc, cancel):
                return True
            raise
        check_cancel(cancel)
        short.timings["speech_seconds"] = time.monotonic() - speech_start
        compile_start = time.monotonic()
        try:
            scenes, units = compile_storyboard(draft, duration, self.assets)
            self.assets.reference(scenes, lesson.id, short.id)
        except ValueError as exc:
            error = AppError("STORYBOARD_TIMELINE_INVALID", "The measured storyboard could not be compiled. Retry to regenerate this short; ready shorts are preserved.", 422)
            if self.skip_failed(lesson, short, error, cancel):
                return True
            raise error from exc
        check_cancel(cancel)
        short.timings["storyboard_compile_seconds"] = time.monotonic() - compile_start
        short.narration_units = units
        refs = [u.evidence for u in draft.narration_units] + diagram_evidence(draft,segments)
        if draft.question:
            refs.append(draft.question.evidence)
        short.evidence_references = list({(ref.source_id,tuple(ref.segment_ids)):ref for ref in refs}.values())
        short.prerequisites = draft.prerequisites
        short.question = draft.question
        short.measured_duration_ms = duration
        short.audio_path = audio
        short.scenes = scenes
        short.storyboard_version = STORYBOARD_VERSION
        short.timeline_compiler_version = COMPILER_VERSION
        short.cover = await cover
        short.status = "ready"
        if lesson.planning:
            lesson.planning.failed_skips_in_row = 0
        # Capacity was checked before publication; only queued predictions may shrink.
        if lesson.planning:
            try:
                recalibrate_queued(lesson)
            except ValueError as exc:
                raise AppError("BUDGET_EXCEEDED", str(exc), 422) from exc
        # Validate the final playback object before the atomic store publication.
        Short.model_validate(short.model_dump())
        required_media(short, self.settings.data, self.assets)
        short.error = None
        short.cache_hit = bool(cached and audio_cached)
        short.provider_settings = dict(lesson.provider_settings)
        refresh(lesson)
        if lesson.planned_duration_ms > lesson.request.time_budget_seconds * 1000 + lesson.extra_allowance_ms:
            raise AppError("BUDGET_EXCEEDED", "The measured lesson exceeds the approved time budget.", 422)
        elapsed = max(0, time.time() - lesson.job.created_at)
        short.timings["ready_after_seconds"] = elapsed  # legacy session elapsed, includes retry gaps
        short.timings["published_at"] = time.time()
        if lid in self.accepted_at:
            short.timings["published_after_monotonic_seconds"] = time.monotonic() - self.accepted_at[lid]
        preparation_seconds = time.monotonic() - preparation_start
        short.timings["preparation_seconds"] = preparation_seconds
        short.timings["draft_cache_hit"] = int(bool(cached))
        short.timings["audio_cache_hit"] = int(bool(audio_cached))
        cache_class = "fully_cached" if cached and audio_cached else "partially_cached" if cached or audio_cached else "uncached"
        self.measure(lesson, f"{cache_class}_preparation_seconds", preparation_seconds)
        lesson.metrics[f"{cache_class}_media_seconds"] = lesson.metrics.get(f"{cache_class}_media_seconds", 0) + duration / 1000
        uncached_seconds = lesson.metrics.get("uncached_preparation_seconds", 0)
        if uncached_seconds:
            lesson.metrics["successful_short_uncached_media_production_rate"] = lesson.metrics.get("uncached_media_seconds", 0) / uncached_seconds
        if "first_playable_seconds" not in lesson.metrics:
            lesson.metrics["first_playable_seconds"] = elapsed
            lesson.metrics["first_playable_session_elapsed_seconds"] = elapsed
            lesson.metrics["first_playable_active_seconds"] = lesson.metrics.get("active_processing_seconds", 0) + time.monotonic() - self.turn_started.get(lid, preparation_start)
            if lid in self.accepted_at:
                lesson.metrics["first_playable_monotonic_seconds"] = time.monotonic() - self.accepted_at[lid]
        # Retire misleading waiting_before_short_N metrics. Offline one-pass
        # simulation now accounts for prior stalls and excludes practice credit.
        record_coverage(lesson, short)
        if lesson.planning:
            entry = next((e for e in lesson.planning.coverage if e.concept_id == short.concept_id), None)
            if entry:
                published = next(e for e in lesson.coverage_history if e.short_id == short.id)
                entry.used_claims = [published.claim_summary]
                entry.evidence_segment_ids = list(dict.fromkeys(entry.evidence_segment_ids + published.evidence_segment_ids))[:20]
            lesson.planning.revision += 1
        words = len(" ".join(u.text for u in short.narration_units).split())
        samples = [s for s in samples if s["short_id"] != short.id] + [{"short_id": short.id, "duration_ms": duration, "words": words}]
        self.store.cache_put(profile_key, samples[-16:])
        if lesson.planning:
            calibrated_rate, _ = speech_prediction(samples[-16:])
            lesson.planning.minimum_media_ms = max(MIN_TARGET_MS, min(40000, 30 * calibrated_rate + 1000))
        lesson.status = "partially_ready"
        lesson.job.stage_timings = {name: sum(s.timings.get(name, 0) for s in lesson.shorts)
                                   for name in ("generation_seconds", "validation_seconds", "speech_seconds", "storyboard_compile_seconds")}
        check_cancel(cancel)
        self.store.save(lesson)
        # Re-enter at the measured checkpoint rather than prematurely completing
        # the original fixed outline. The next advance may select a stable batch.
        return True

    async def cover_photo(self, lesson, short, cancel):
        if self.photos is None or short.cover is not None:
            return short.cover
        used = {s.cover.asset.original_source for s in lesson.shorts if s.cover and s.id != short.id}
        started = time.monotonic()
        try:
            return await asyncio.wait_for(asyncio.to_thread(self.photos.cover, lesson.request.goal, short.objective, used, cancel),
                                          getattr(self.photos, "wait_seconds", 20))
        except Exception:
            # Photos are optional decoration; never fail a short because of one.
            return None
        finally:
            short.timings["cover_photo_seconds"] = time.monotonic() - started

    async def draft_with_fallback(self, lesson, task, cancel, valid, segments):
        """Draft a short; if it still fails after its repair, try once with the simplest visual.

        Real failure: a chart planned for a passage with no numbers. The narration
        was fine; only the visual was impossible to do honestly. A key-fact card
        (main point plus supports) avoids most visual-specific checks.
        The task is updated in place so later review/speech repairs keep it.
        """
        try:
            return attach_evidence(await asyncio.to_thread(self.generate, lesson, ModelStoryboard, task, cancel, valid), segments)
        except AppError as exc:
            if exc.code not in DRAFT_FAILURES or task.get("template") == SIMPLE_TEMPLATE:
                raise
        lesson.metrics["simpler_visual_fallbacks"] = lesson.metrics.get("simpler_visual_fallbacks", 0) + 1
        task["template"] = SIMPLE_TEMPLATE
        task["task"] += (" The previous visual could not be made accurately. Use a simple key_fact diagram: "
                         "the main point first, then 1 to 7 supporting points from the passages.")
        return attach_evidence(await asyncio.to_thread(self.generate, lesson, ModelStoryboard, task, cancel, valid, metric="repair"), segments)

    def skip_failed(self, lesson, short, exc, cancel):
        """Skip a planned short that still fails a content check after its repairs.

        One inaccurate or unbuildable short no longer fails the whole lesson: it is
        dropped, recorded for the learner, and the lesson keeps going. Queued shorts
        that depend on it are dropped too (they would build on an untaught point),
        except the closing recap, which recaps whatever was published.
        Returns False (so the lesson fails) for user-requested optional shorts, or
        when nothing at all could be made.
        """
        if not lesson.planning or short.optional or short.status == "ready" or short not in lesson.shorts:
            return False
        dropped = {short.concept_id}
        while True:
            more = {o.concept_id for o in lesson.objectives if set(o.dependency_ids) & dropped and o.curriculum_role != "closing"} - dropped
            if not more:
                break
            dropped |= more
        removed = [s for s in lesson.shorts if s is short or (s.status != "ready" and s.concept_id in dropped and s.curriculum_role != "closing")]
        kept = [s for s in lesson.shorts if s not in removed]
        if not kept:
            return False  # Nothing ready and nothing left to try: report the real error.
        state = lesson.planning
        lesson.shorts = kept
        lesson.short_ids = [s.id for s in kept]
        state.deferred_concept_ids.extend(s.concept_id for s in removed)
        reason = SKIP_REASONS.get(exc.code, "it could not be made accurately")
        state.skipped_points = (state.skipped_points + [f"{s.objective[:80]} ({reason})" for s in removed])[-80:]
        state.failed_skips_in_row += 1
        if state.failed_skips_in_row >= 3:
            state.completion_reason = "generation_limit"
            state.completion_detail = ("Several planned points in a row could not be made accurately, "
                                       "so the lesson stopped adding material instead of publishing them.")
        lesson.metrics["failed_shorts_skipped"] = lesson.metrics.get("failed_shorts_skipped", 0) + len(removed)
        state.revision += 1
        refresh(lesson)
        check_cancel(cancel)
        self.store.save(lesson)
        return True

    def skip_repeated(self, lesson, short, cancel):
        """Drop an unpublished planned short whose outcome only repeats published shorts.

        Ready media is untouched. Dependents stay queued because the concept is
        already taught by the earlier shorts it repeated. Expansion continues so
        the session can still fill its time: the planner is told which points had
        nothing new, and after two skips it must search for related material.
        It stops only once searches are used up or skips keep recurring.
        """
        if not lesson.planning or short.optional or short.status == "ready" or short not in lesson.shorts:
            return False
        state = lesson.planning
        lesson.shorts = [s for s in lesson.shorts if s is not short]
        lesson.short_ids = [s.id for s in lesson.shorts]
        state.deferred_concept_ids.append(short.concept_id)
        state.nothing_new = (state.nothing_new + [short.objective[:100]])[-80:]
        state.repeat_skips_since_sources += 1
        if state.repeat_skips_since_sources >= 3 or (state.repeat_skips_since_sources >= 2 and not searches_left(lesson)):
            state.completion_reason = "coverage_exhausted"
            state.completion_detail = ("The sources ran out of distinct material: drafts only repeated earlier shorts, "
                                       "so those points were skipped instead of publishing repeats.")
        lesson.metrics["repeat_skipped_shorts"] = lesson.metrics.get("repeat_skipped_shorts", 0) + 1
        lesson.planning.revision += 1
        refresh(lesson)
        check_cancel(cancel)
        self.store.save(lesson)
        return True

    def complete(self, lesson):
        ledger = refresh(lesson, final=True)
        if any(s.status != "ready" for s in lesson.shorts):
            raise AppError("LESSON_NOT_READY", "Unpublished work must finish before completion.", 422)
        if (ledger.forecast_total_ms > lesson.request.time_budget_seconds * 1000 + lesson.extra_allowance_ms or
            (lesson.planning and (ledger.original_content_ms > lesson.request.time_budget_seconds * 1000 or
                                 ledger.extra_content_ms > lesson.extra_allowance_ms))):
            raise AppError("BUDGET_EXCEEDED", "Final content exceeds the approved time budget or uses the wrong allowance pool.", 422)
        if lesson.planning:
            if ledger.shortfall_ms == 0:
                lesson.planning.completion_reason = "target_met"
                lesson.planning.completion_detail = "The requested videos-and-practice target was met."
            elif not lesson.planning.completion_reason:
                lesson.planning.completion_reason = "budget_fit"
                lesson.planning.completion_detail = "The useful closing finished below the target; published media was not padded."
        lesson.status = "ready"
        lesson.job.status = "complete"
        lesson.job.stage = "ready"
        lesson.metrics["total_preparation_seconds"] = time.time() - lesson.job.created_at
        self.store.save(lesson)
