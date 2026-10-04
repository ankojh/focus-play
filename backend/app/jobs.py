from __future__ import annotations
import asyncio
import hashlib
import json
import threading
import time
import uuid
from .contracts import Job, Lesson, LessonPlan, Scene, SceneAction, Short, ShortDraft, ErrorInfo, ModelShort, SavedLearningRequest, CandidateRanking
from .errors import AppError, Cancelled
from .providers import check_cancel
from .ranking import KEEP, pick, ranking_task, validator
from .sources import retrieve
from .validation import validate_draft, verify_support, planned_duration, attach_evidence, refine_cues, diagram_evidence
from .youtube import YouTubeSources, queries, require_youtube


TEMPLATES = {
    "process": "2 to 4 stages in order; roles start, step, result; connect each stage to the next.",
    "steps": "2 to 4 numbered how-to steps; each detail is a short instruction; roles step.",
    "cycle": "3 or 4 stages that repeat in a loop; roles step. The application draws the loop.",
    "comparison": "two to four options compared side by side; slots 0 and 1 are the main pair.",
    "dos_donts": "the right way (role good) against the wrong way (role bad); include at least one of each.",
    "key_fact": "node_0 is the single most important rule or number; 1 to 3 supporting nodes explain it.",
    "timeline": "events in time order; roles step.",
    "example": "a concrete worked example from the passages, from situation to outcome.",
    "chart": "bars whose values are numbers stated in the passages; never invent values.",
}
TEMPLATE_GUIDE = " ".join(f"{name}: {text}" for name, text in TEMPLATES.items())


def uid(prefix):
    return prefix + uuid.uuid4().hex[:20]

def cache_key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

class Jobs:
    def __init__(self, store, model, speech, settings, youtube=None):
        self.store, self.model, self.speech, self.settings = store, model, speech, settings
        self.youtube = youtube or YouTubeSources(store,settings)
        self.queue = asyncio.PriorityQueue(maxsize=settings.queue_size)
        self.cancel_flags = {}
        self.active = set()
        self.sequence = 0
        self.task = None
        self.closing = False

    def start(self):
        self.store.recover()
        self.task = asyncio.create_task(self.worker())

    async def stop(self):
        self.closing = True
        for flag in self.cancel_flags.values():
            flag.set()
        # Provider calls finish or see the cancellation flag before the store closes.
        if self.task:
            await self.queue.put((-1, -1, None))
            await self.task

    def reserve(self, lid):
        if lid in self.active:
            raise AppError("JOB_ACTIVE", "This lesson is already being prepared.", 409)
        if len(self.active) >= self.settings.queue_size or self.queue.full():
            raise AppError("QUEUE_FULL", "The local queue is full. Wait for a lesson to finish, then retry.", 429)
        self.active.add(lid)
        self.cancel_flags[lid] = threading.Event()

    def enqueue(self, lid, priority=0):
        self.sequence += 1
        self.queue.put_nowait((priority, self.sequence, lid))

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
                        job=Job(id=uid("job_"), lesson_id=lid, created_at=now, updated_at=now))
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
        missing_media = any(s.status == "ready" and not (self.settings.data / "audio" / (s.audio_path or "missing")).is_file() for s in lesson.shorts)
        if lesson.job.status not in {"failed", "cancelled", "interrupted"} and not missing_media:
            raise AppError("RETRY_NOT_AVAILABLE", "Retry is available after a failure, cancellation, or server restart.", 409)
        self.reserve(lid)
        lesson.job.status = "queued"
        lesson.job.stage = "queued"
        lesson.job.error = None
        lesson.status = "partially_ready" if any(s.status == "ready" for s in lesson.shorts) else "queued"
        for short in lesson.shorts:
            if short.status != "ready" or not (self.settings.data / "audio" / (short.audio_path or "missing")).exists():
                short.status = "queued"
                short.error = None
        self.store.save(lesson)
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
        lesson.planned_duration_ms = planned_duration(lesson.shorts)
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
            try:
                check_cancel(self.cancel_flags[lid])
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
                self.queue.task_done()
                if requeue and not self.closing and not self.cancel_flags[lid].is_set():
                    self.enqueue(lid, 10)
                else:
                    self.active.discard(lid)
                    self.cancel_flags.pop(lid, None)

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

    async def acquire(self,lesson,cancel,tried,round_number,focus=None):
        await self.stage(lesson,"Searching YouTube")
        query=queries(lesson.request.goal,lesson.request.prior_knowledge,focus)[round_number]
        candidates=await asyncio.to_thread(self.youtube.search,query)
        # Each transcript request costs one provider credit, including videos without captions.
        limit=self.settings.rank_candidates
        fetched,attempts=[],0
        for candidate in candidates:
            check_cancel(cancel)
            if candidate["video_id"] in tried:
                continue
            if attempts>=limit or len(tried)>=2*limit:
                break
            tried.add(candidate["video_id"])
            attempts+=1
            await self.stage(lesson,"Reading video transcripts")
            try:
                source=await asyncio.to_thread(self.youtube.transcript,candidate,cancel)
                require_youtube(source)
            except AppError as exc:
                if exc.code in {"TRANSCRIPT_UNAVAILABLE","INVALID_YOUTUBE_TRANSCRIPT","TRANSCRIPT_TIMEOUT"}:
                    continue
                raise
            check_cancel(cancel)
            if not any(s.id==source.id for s in lesson.sources):
                fetched.append((candidate,source))
        chosen=await self.rank(lesson,fetched,cancel,focus)
        for source in chosen:
            self.store.put_source(source)
            lesson.sources.append(source)
        self.store.save(lesson)
        return len(chosen)

    async def rank(self,lesson,fetched,cancel,focus=None):
        if len(fetched)<=1:
            return [s for _,s in fetched]
        await self.stage(lesson,"Choosing the best videos")
        task=ranking_task(lesson.request,fetched,focus)
        key=cache_key({"stage":"rank","model":self.settings.model,"task":task})
        cached=self.store.cache_get(key)
        try:
            ranking=CandidateRanking.model_validate(cached) if cached else await asyncio.to_thread(self.model.generate,CandidateRanking,task,cancel,validator(fetched))
        except AppError:
            # Ranking only improves the choice. Keep YouTube's order when the model cannot rank.
            return [s for _,s in fetched][:KEEP]
        check_cancel(cancel)
        if not cached:
            self.store.cache_put(key,ranking.model_dump())
        lesson.video_rankings.extend(ranking.scores)
        return pick(ranking,fetched)

    async def reviewed(self,draft,task,segments,valid,cancel):
        # A rejected short is rewritten once with the reviewer's reason before the lesson fails.
        for attempt in range(2):
            try:
                await asyncio.to_thread(verify_support, self.model, draft, segments, cancel)
                check_cancel(cancel)
                return draft
            except ValueError as exc:
                if attempt:
                    raise AppError("UNSUPPORTED_CLAIM", "The model source review could not support this short. Retry or use a more focused learning goal.", 422) from exc
                retry={**task,"task":task["task"]+" A reviewer rejected the previous version: "+str(exc)[:400]+" Fix that problem."}
                draft = attach_evidence(await asyncio.to_thread(self.model.generate, ModelShort, retry, cancel, valid), segments)
        return draft

    def context(self,lesson,focus=None):
        sources=self.youtube_sources(lesson)
        segments=retrieve(sources,focus or lesson.request.goal)
        key_base={"source_policy":"youtube-v1","sources":[{"id":s.id,"hash":s.content_hash} for s in sources],
            "settings":lesson.provider_settings,"request":lesson.request.model_dump(exclude={"request_id","source_mode","source_ids"})}
        return segments,key_base

    async def advance(self, lid):
        started = time.monotonic()
        lesson = self.store.lesson(lid)
        cancel = self.cancel_flags[lid]
        source_start=time.monotonic()
        tried={s.video_id for s in self.youtube_sources(lesson)}
        rounds=0
        if not tried:
            while rounds<2:
                added=await self.acquire(lesson,cancel,tried,rounds)
                rounds+=1
                if added:
                    break
            if not self.youtube_sources(lesson):
                raise AppError("NO_USABLE_TRANSCRIPTS","No accessible English YouTube transcripts were found within the search limit. Retry or use a more focused goal.",422)
        lesson.metrics["source_acquisition_seconds"]=lesson.metrics.get("source_acquisition_seconds",0)+time.monotonic()-source_start
        started=time.monotonic()
        await self.stage(lesson, "checking local providers")
        fingerprint = await asyncio.to_thread(self.model.fingerprint)
        await asyncio.to_thread(self.speech.prepare)
        check_cancel(cancel)
        lesson.provider_settings = {**fingerprint, "speech": self.speech.fingerprint(), "language": lesson.request.language}
        if "provider_load_seconds" not in lesson.metrics:
            lesson.metrics["provider_load_seconds"] = time.monotonic() - started
        segments,key_base=self.context(lesson)
        if not lesson.shorts:
            lesson.status = "preparing"
            await self.stage(lesson, "planning the lesson")
            planning_started = time.monotonic()
            max_shorts = min(8, (lesson.request.time_budget_seconds * 1000) // 46667)
            def validate_plan(plan):
                if plan.sufficient_evidence and not 1 <= len(plan.objectives) <= max_shorts:
                    raise ValueError(f"Use 1 to {max_shorts} ordered objectives.")
            while True:
                plan_key=cache_key({**key_base,"stage":"plan"})
                cached=self.store.cache_get(plan_key)
                plan=LessonPlan.model_validate(cached) if cached else await asyncio.to_thread(self.model.generate,LessonPlan,
                    {"task":f"Plan a coherent lesson with 1 to {max_shorts} ordered objectives. Order them the way a teacher would for this learner: basics first, then core technique, then refinement. "
                        "The first objective must be a sensible starting point for the learner's current knowledge. Each objective teaches one distinct idea; do not repeat or overlap objectives. "
                        "Title objectives as short learner goals. Choose the diagram template that best shows each idea: "+TEMPLATE_GUIDE+" Vary templates across the lesson. "
                        "Prerequisites are brief knowledge concepts; use [] if none are needed. Plan brief introductory learning points, not a comprehensive course. "
                        "Set sufficient_evidence=true if any useful learning points can be taught; partial topic coverage is fine.","request":key_base["request"],"segments":[s.model_dump() for s in segments]},cancel,validate_plan)
                validate_plan(plan)
                check_cancel(cancel)
                if plan.sufficient_evidence:
                    break
                if rounds>=2:
                    raise AppError("INSUFFICIENT_EVIDENCE","Available YouTube transcripts cannot support this goal. Retry or use a more focused goal. "+plan.reason,422)
                added=await self.acquire(lesson,cancel,tried,rounds)
                rounds+=1
                if not added:
                    raise AppError("INSUFFICIENT_EVIDENCE","Available YouTube transcripts cannot support this goal within the search limit. Retry or use a more focused goal.",422)
                segments,key_base=self.context(lesson)
                await self.stage(lesson,"planning the lesson")
            if not cached:
                self.store.cache_put(plan_key,plan.model_dump())
            lesson.objectives = plan.objectives
            lesson.shorts = [Short(id=uid("short_"), objective=o.title, prerequisites=o.prerequisites, question_required=(i + 1) % 3 == 0) for i, o in enumerate(plan.objectives)]
            lesson.short_ids = [s.id for s in lesson.shorts]
            lesson.planned_duration_ms = planned_duration(lesson.shorts)
            if lesson.planned_duration_ms > lesson.request.time_budget_seconds * 1000:
                raise AppError("BUDGET_EXCEEDED", "The plan exceeds the time budget. Use fewer objectives.", 422)
            lesson.original_planned_duration_ms = lesson.planned_duration_ms
            lesson.metrics["planning_seconds"] = time.monotonic() - planning_started
            lesson.metrics["plan_cache_hit"] = int(bool(cached))
            self.store.save(lesson)
        short = next((s for s in lesson.shorts if s.status != "ready"), None)
        if short is None:
            self.complete(lesson)
            return False
        index = lesson.shorts.index(short)
        core_index = len([s for s in lesson.shorts[:index] if not s.optional])
        focus=f"{lesson.request.goal} {short.objective}"
        segments,key_base=self.context(lesson,focus)
        if short.optional:
            while True:
                support=await asyncio.to_thread(self.model.generate,LessonPlan,
                    {"task":"Check whether the supplied YouTube transcript passages support this additional learning point. Return sufficient_evidence=false if not. Return objectives=[]. Do not use outside knowledge.","goal":lesson.request.goal,"objective":short.objective,"segments":[s.model_dump() for s in segments]},cancel)
                check_cancel(cancel)
                if support.sufficient_evidence:
                    break
                if rounds>=2 or not await self.acquire(lesson,cancel,tried,rounds,focus):
                    raise AppError("INSUFFICIENT_EVIDENCE","Available YouTube transcripts cannot support this additional short. Retry or start a more focused lesson.",422)
                rounds+=1
                segments,key_base=self.context(lesson,focus)
        template = "example" if short.optional and short.objective.startswith("Show") else lesson.objectives[min(core_index, len(lesson.objectives) - 1)].template
        earlier_narration=[u.text for s in lesson.shorts[:index] for u in s.narration_units]
        short_key = cache_key({**key_base, "objective": short.objective, "template": template, "question": short.question_required, "earlier": [s.objective for s in lesson.shorts[:index]], "earlier_narration": earlier_narration, "stage": "draft"})
        cached = self.store.cache_get(short_key)
        await self.stage(lesson, "preparing the first short" if index == 0 else f"preparing short {index + 1}", short, "generating")
        model_start = time.monotonic()
        def valid(content):
            draft = attach_evidence(content, segments) if isinstance(content, ModelShort) else content
            if draft.template != template:
                raise ValueError(f"Use the {template} template.")
            validate_draft(draft, segments, short.question_required, earlier_narration)
            refine_cues(draft)
        task = {"task": "Teach one learning point to this learner in your own words. Return a complete ModelShort. "
                    "The first unit opens the idea plainly; the second explains how or why, or gives a concrete tip. Each unit cites the segment_id whose passage teaches it. "
                    "Do not repeat earlier_narration. A question supplies a correct_answer, 1 to 3 plausible incorrect distractors, and a one-sentence explanation. Question must be null unless required. "
                    "Use 40 to 80 total spoken words in exactly two narration units. Use 2 to 4 nodes with IDs node_0 through node_3 in order and unique slots. "
                    f"Template {template}: {TEMPLATES[template]} Connections refer to existing nodes. The application derives all animation cues.",
                "objective": short.objective, "template": template, "question_required": short.question_required,
                "learner": lesson.request.prior_knowledge, "earlier_objectives": [s.objective for s in lesson.shorts[:index]],
                "earlier_narration": earlier_narration, "segments": [s.model_dump() for s in segments]}
        draft = ShortDraft.model_validate(cached) if cached else attach_evidence(await asyncio.to_thread(self.model.generate, ModelShort, task, cancel, valid), segments)
        valid(draft)
        short.timings["generation_seconds"] = time.monotonic() - model_start
        await self.stage(lesson, "validating source references", short, "validating")
        validation_start = time.monotonic()
        if not cached:
            draft = await self.reviewed(draft, task, segments, valid, cancel)
            self.store.cache_put(short_key, draft.model_dump())
        short.timings["validation_seconds"] = time.monotonic() - validation_start
        await self.stage(lesson, "generating local speech", short, "synthesizing")
        speech_start = time.monotonic()
        # Duration repair is separate from the two schema repairs; voice speed remains fixed.
        for duration_attempt in range(2):
            speech_key = cache_key({"texts": [u.text for u in draft.narration_units], "settings": lesson.provider_settings, "sources": key_base["sources"], "language": lesson.request.language})
            try:
                audio, duration, audio_cached = await asyncio.to_thread(self.speech.synthesize, draft.narration_units, speech_key, cancel)
                break
            except AppError as exc:
                if exc.code != "SPEECH_DURATION" or duration_attempt:
                    raise
                task["task"] += " The speech exceeded 40 seconds. Shorten to 40 to 50 words."
                draft = attach_evidence(await asyncio.to_thread(self.model.generate, ModelShort, task, cancel, valid), segments)
                draft = await self.reviewed(draft, task, segments, valid, cancel)
                self.store.cache_put(short_key, draft.model_dump())
        else:
            raise AppError("SPEECH_DURATION", "Speech could not fit the short duration limit.", 422)
        check_cancel(cancel)
        short.timings["speech_seconds"] = time.monotonic() - speech_start
        short.narration_units = draft.narration_units
        refs = [u.evidence for u in draft.narration_units] + diagram_evidence(draft,segments)
        if draft.question:
            refs.append(draft.question.evidence)
        short.evidence_references = list({(ref.source_id,tuple(ref.segment_ids)):ref for ref in refs}.values())
        short.prerequisites = draft.prerequisites
        short.question = draft.question
        short.measured_duration_ms = duration
        short.audio_path = audio
        short.scenes = [Scene(template=draft.template, nodes=draft.nodes, connections=draft.connections,
            actions=[SceneAction(kind=a.kind, target=a.target, to_slot=a.to_slot, at_ms=draft.narration_units[a.unit].start_ms) for a in draft.actions], end_ms=duration)]
        short.status = "ready"
        short.error = None
        short.cache_hit = bool(cached and audio_cached)
        short.provider_settings = dict(lesson.provider_settings)
        lesson.planned_duration_ms = planned_duration(lesson.shorts)
        if lesson.planned_duration_ms > lesson.request.time_budget_seconds * 1000 + lesson.extra_allowance_ms:
            raise AppError("BUDGET_EXCEEDED", "The measured lesson exceeds the approved time budget.", 422)
        elapsed = time.time() - lesson.job.created_at
        short.timings["ready_after_seconds"] = elapsed
        if index == 0:
            lesson.metrics["first_playable_seconds"] = elapsed
        else:
            preceding = sum(s.measured_duration_ms + (20000 if s.question else 0) for s in lesson.shorts[:index]) / 1000
            lesson.metrics[f"waiting_before_short_{index + 1}_seconds"] = max(0, elapsed - lesson.metrics.get("first_playable_seconds", elapsed) - preceding)
        lesson.status = "partially_ready"
        lesson.job.stage_timings = {"generation_seconds": sum(s.timings.get("generation_seconds", 0) for s in lesson.shorts), "validation_seconds": sum(s.timings.get("validation_seconds", 0) for s in lesson.shorts), "speech_seconds": sum(s.timings.get("speech_seconds", 0) for s in lesson.shorts)}
        self.store.save(lesson)
        if all(s.status == "ready" for s in lesson.shorts):
            self.complete(lesson)
            return False
        return True

    def complete(self, lesson):
        lesson.status = "ready"
        lesson.job.status = "complete"
        lesson.job.stage = "ready"
        lesson.metrics["total_preparation_seconds"] = time.time() - lesson.job.created_at
        self.store.save(lesson)
