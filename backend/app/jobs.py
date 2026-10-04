from __future__ import annotations
import asyncio
import hashlib
import json
import threading
import time
import uuid
from .contracts import Job, Lesson, LessonPlan, Short, StoryboardDraft, ErrorInfo, ModelStoryboard, SavedLearningRequest, CandidateRanking
from .storyboard import STORYBOARD_VERSION, COMPILER_VERSION, compile_storyboard
from .errors import AppError, Cancelled
from .providers import check_cancel
from .ranking import KEEP, pick, ranking_task, validator
from .sources import retrieve
from .validation import validate_draft, verify_support, planned_duration, attach_evidence, diagram_evidence
from .youtube import YouTubeSources, queries, require_youtube
from .teaching import (TEACHING_VERSION, validate_plan as check_plan, planned_shorts,
                       objective_for, teaching_context, record_coverage, plan_diagnostics)


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

    async def reviewed(self,draft,task,segments,valid,cancel,short=None,lesson=None):
        # A rejected short is rewritten once with the reviewer's reason before the lesson fails.
        for attempt in range(2):
            try:
                review = await asyncio.to_thread(verify_support, self.model, draft, segments, cancel, task.get("teaching"))
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
                draft = attach_evidence(await asyncio.to_thread(self.model.generate, ModelStoryboard, retry, cancel, valid), segments)
        return draft

    def cache_draft(self, key, draft, short):
        self.store.cache_put(key, {"draft": draft.model_dump(), "source_review_reason": short.source_review_reason,
                                   "teaching_diagnostics": short.teaching_diagnostics, "review_repair_reasons": short.review_repair_reasons})

    def context(self,lesson,focus=None,required_ids=()):
        sources=self.youtube_sources(lesson)
        segments=retrieve(sources,focus or lesson.request.goal,required_ids=required_ids)
        key_base={"source_policy":"youtube-v1","sources":[{"id":s.id,"hash":s.content_hash} for s in sources],
            "settings":lesson.provider_settings,"storyboard_version":STORYBOARD_VERSION,"timeline_compiler_version":COMPILER_VERSION,
            "teaching_version":TEACHING_VERSION,
            "request":lesson.request.model_dump(exclude={"request_id","source_mode","source_ids"})}
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
            max_shorts = min(8, (lesson.request.time_budget_seconds * 1000) // 40000)
            def validate_plan(plan):
                check_plan(plan, segments, max_shorts, lesson.request.time_budget_seconds * 1000)
            while True:
                plan_key=cache_key({**key_base,"stage":"plan"})
                cached=self.store.cache_get(plan_key)
                plan=LessonPlan.model_validate(cached) if cached else await asyncio.to_thread(self.model.generate,LessonPlan,
                    {"task":f"Plan a coherent source-grounded lesson with 1 to {max_shorts} ordered outcomes, not a list of summaries. "
                        "Start with the learner's goal and prior knowledge: skip basics they know, but preserve needed dependencies. "
                        "Use stable concept_id values; dependency_ids can name only earlier concepts. Express an observable learning_outcome (explain, predict, choose, trace, apply). "
                        "Give each short one outcome, its relevance to this learner and supplied evidence_segment_ids. "
                        "Progress where useful from understanding a mechanism to a worked example, distinction/misconception, application and recall. "
                        "Do not force every role or expand a narrow goal. Longer lessons should add useful depth, not introductions in new words. "
                        "Classify core/extension/closing separately from teaching_role. A recap is closing, depends on earlier concepts and does not add new coverage. "
                        "Place checkpoint=true at a coherent application, difficult distinction or closing boundary, not every third short. "
                        f"Reserve 40000ms per clip plus 20000ms per checkpoint within {lesson.request.time_budget_seconds * 1000}ms. target_duration_ms=40000 until calibrated duration planning is available. "
                        "Use up to two recurring example records only when sources contain them: stable entities, exact excerpt facts, evidence_segment_ids. "
                        "No synthetic substitutions or invented values, even labelled illustrative. Omit unsupported examples. "
                        "Describe visual_intent before choosing a renderer template: "+TEMPLATE_GUIDE+" "
                        "Keep strings concise to fit the local output limit. Prerequisites are short knowledge concepts; [] if none. "
                        "Set sufficient_evidence=false with a reason if the actual requested goal is unsupported, and return objectives=[] and examples=[]. "
                        "Do not imply a short partial lesson fully covers the goal; record limitations in reason.",
                     "plan_version":2,"max_objectives":max_shorts,"request":key_base["request"],"segments":[s.model_dump() for s in segments]},cancel,validate_plan)
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
            lesson.teaching_plan_version = 2
            lesson.examples = plan.examples
            lesson.plan_diagnostics = ([plan.reason] if plan.reason else []) + plan_diagnostics(plan)
            lesson.shorts = planned_shorts(plan, lambda: uid("short_"))
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
        objective = objective_for(lesson, short)
        example = next((e for e in lesson.examples if e.id == short.example_id), None)
        required_ids = list(dict.fromkeys((objective.evidence_segment_ids if objective and not short.optional else []) +
                                         (example.evidence_segment_ids if example else [])))
        focus=f"{lesson.request.goal} {short.learning_outcome or short.objective}"
        segments,key_base=self.context(lesson,focus,required_ids)
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
        template = "example" if short.optional and short.objective.startswith("Show") else objective.template if objective else "process"
        history = teaching_context(lesson, short)
        earlier_narration = history["recent_narration"]
        earlier_questions = [s.question.prompt for s in lesson.shorts[:index] if s.question][-6:]
        teaching = {"goal": lesson.request.goal, "learner": lesson.request.prior_knowledge,
                    "outcome": short.learning_outcome or short.objective, "role": short.teaching_role,
                    "plan": objective.model_dump() if objective and not short.optional else None,
                    "example": example.model_dump() if example else None, "history": history}
        short_key = cache_key({**key_base, "teaching": teaching, "template": template, "question": short.question_required,
                               "earlier_questions": earlier_questions, "segments": [s.id for s in segments], "stage": "draft"})
        cached = self.store.cache_get(short_key)
        await self.stage(lesson, "preparing the first short" if index == 0 else f"preparing short {index + 1}", short, "generating")
        model_start = time.monotonic()
        def valid(content):
            draft = attach_evidence(content, segments) if isinstance(content, ModelStoryboard) else content
            if draft.scenes[0].template != template:
                raise ValueError(f"Use the {template} template for the first scene.")
            validate_draft(draft, segments, short.question_required, earlier_narration,
                           allow_recap=short.teaching_role == "recap", earlier_questions=earlier_questions, example=example)
        task = {"task": "Teach one learning outcome with a supported visual demonstration. Return a complete ModelStoryboard version 2. "
                    "Aim for 3 to 5 brief beats: question/situation, baseline, meaningful change or alternative, takeaway. A simpler two-beat explanation is allowed. "
                    "Use 40 to 80 total spoken words, not more words just to add beats. Each beat has a unique beat_id, purpose, scene_id, cited segment_id and explicit operations. "
                    "Use 1 to 3 scenes in contiguous order. A changed scene_id replaces the scene; never return to an earlier scene. "
                    "Reveal nodes before focusing, moving, hiding or changing their state; connect only after both endpoints are revealed. "
                    "Show concepts changing, not every label at once. Explicitly target the concept being taught, not a name mentioned as absent. "
                    "State changes select an authored state_id for that target with supported label/detail/role. Use source-only examples; no synthetic substitutions or invented benchmarks. "
                    "Preserve the supplied example entities and facts. Open directly with the outcome, define necessary terms once, show why/how, then give a concise takeaway or condition. "
                    "Every node needs a reveal and every connection a connect. For cycle supply the explicit loop connections; dos_donts has no connections. "
                    "Use the compact coverage history to add new meaning, not synonym-based duplicates. An explicit recap may briefly revisit its dependencies without claiming new coverage. "
                    "A distinct application of a known concept is allowed. Avoid generic hooks, filler and false guarantees. "
                    "A required checkpoint tests the outcome actually taught: prediction/application over trivia, one unambiguous correct_answer, "
                    "1 to 3 plausible distractors representing misconceptions and supported reasoning in explanation. Do not repeat earlier questions. Question must be null unless required. "
                    "Use 2 to 4 nodes per scene with IDs node_0 through node_3 in order and unique slots. "
                    f"First scene template {template}: {TEMPLATES[template]} Later scenes can use any allowed template. Do not author timestamps or renderer code.",
                "objective": short.objective, "template": template, "question_required": short.question_required,
                "learner": lesson.request.prior_knowledge, "teaching": teaching, "earlier_questions": earlier_questions,
                "segments": [s.model_dump() for s in segments]}
        if cached:
            short.source_review_status = "model_supported"
            short.source_review_reason = cached["source_review_reason"]
            short.teaching_diagnostics = cached["teaching_diagnostics"]
            short.review_repair_reasons = cached["review_repair_reasons"]
        draft = StoryboardDraft.model_validate(cached["draft"]) if cached else attach_evidence(await asyncio.to_thread(self.model.generate, ModelStoryboard, task, cancel, valid), segments)
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
        for duration_attempt in range(2):
            speech_key = cache_key({"texts": [u.text for u in draft.narration_units], "settings": lesson.provider_settings, "sources": key_base["sources"], "language": lesson.request.language,
                                    "storyboard_version": STORYBOARD_VERSION, "timeline_compiler_version": COMPILER_VERSION})
            try:
                audio, duration, audio_cached = await asyncio.to_thread(self.speech.synthesize, draft.narration_units, speech_key, cancel)
                break
            except AppError as exc:
                if exc.code != "SPEECH_DURATION" or duration_attempt:
                    raise
                task["task"] += " The speech exceeded 40 seconds. Shorten to 40 to 50 words."
                draft = attach_evidence(await asyncio.to_thread(self.model.generate, ModelStoryboard, task, cancel, valid), segments)
                draft = await self.reviewed(draft, task, segments, valid, cancel, short, lesson)
                self.cache_draft(short_key, draft, short)
        else:
            raise AppError("SPEECH_DURATION", "Speech could not fit the short duration limit.", 422)
        check_cancel(cancel)
        short.timings["speech_seconds"] = time.monotonic() - speech_start
        compile_start = time.monotonic()
        try:
            scenes, units = compile_storyboard(draft, duration)
        except ValueError as exc:
            raise AppError("STORYBOARD_TIMELINE_INVALID", "The measured storyboard could not be compiled. Retry to regenerate this short; ready shorts are preserved.", 422) from exc
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
        short.status = "ready"
        # Validate the final playback object before the atomic store publication.
        Short.model_validate(short.model_dump())
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
        record_coverage(lesson, short)
        lesson.status = "partially_ready"
        lesson.job.stage_timings = {name: sum(s.timings.get(name, 0) for s in lesson.shorts)
                                   for name in ("generation_seconds", "validation_seconds", "speech_seconds", "storyboard_compile_seconds")}
        check_cancel(cancel)
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
