"""Opt-in real Jobs/LLM/Kokoro check using already saved real YouTube evidence.

No new search/transcript credits: source acquisition is disabled, not mocked.
New lessons/media/diagnostics live in a fresh isolated directory, never the library.
This checks the cached-evidence path, NOT fresh YouTube acquisition.
"""
import argparse
import asyncio
import json
import sqlite3
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from app.contracts import Lesson, LearningRequest
from app.errors import AppError
from app.jobs import Jobs
from app.providers import create_model, Speech
from app.store import Store
from app.youtube import require_youtube


class AcquisitionDisabled:
    def search(self, *args, **kwargs):
        raise AppError("SOURCE_CREDITS_NOT_APPROVED", "This cached-evidence check cannot acquire more sources.", 422)
    transcript = search


class SearchRecorder(AcquisitionDisabled):
    """Records the queries a lesson would search; returns no videos. Never calls a provider."""
    def __init__(self):
        self.queries = []
    def search(self, query, *args, **kwargs):
        self.queries.append(query)
        return []


def read_saved_lesson(data, lid):
    # Read-only input; don't instantiate another writable application store.
    with sqlite3.connect((data / "records.sqlite3").as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute("SELECT body FROM lessons WHERE id=?", (lid,)).fetchone()
    if row is None:
        raise ValueError("Saved source lesson not found.")
    lesson = Lesson.model_validate_json(row[0])
    if not lesson.sources:
        raise ValueError("Saved lesson has no evidence.")
    for source in lesson.sources:
        require_youtube(source)
    return lesson


async def run(args):
    original = Settings()
    expected = getattr(args, 'expected_provider', 'turbofieldfare')
    if original.provider != expected or original.speech != "kokoro":
        label = {'turbofieldfare': 'TurboFieldfare', 'ollama': 'Ollama'}[expected]
        raise ValueError(f"This check requires the selected {label}/Kokoro profile; no substitute provider is used.")
    source_lesson = read_saved_lesson(original.data, args.source_lesson)
    args.work_dir = args.work_dir.resolve()
    if args.work_dir.exists():
        raise ValueError("Use a fresh isolated work directory; existing data is never overwritten or deleted.")
    if not (original.data / "hf").is_dir():
        raise ValueError("Existing local Kokoro cache is required; no download occurs.")
    settings = Settings(data=args.work_dir)
    settings.youtube_key = settings.supadata_key = ""
    # Reuse speech weights in place. Only remove the newly created EMPTY HF dir.
    (settings.data / "hf").rmdir()
    (settings.data / "hf").symlink_to(original.data / "hf", target_is_directory=True)
    store = Store(settings.data)
    model, speech = create_model(settings), Speech(settings)
    # GenerationService resets its per-task list. Keep a bounded cross-task trace
    # for this diagnostic instead of reporting only the next clip's cancellation.
    attempt_history = []
    record_attempt = model.record_attempt
    def record(*args, **kwargs):
        record_attempt(*args, **kwargs)
        attempt_history.append(dict(model.attempts[-1]))
        del attempt_history[:-100]
    model.record_attempt = record
    sources = SearchRecorder() if getattr(args, 'record_searches', False) else AcquisitionDisabled()
    jobs = Jobs(store, model, speech, settings, sources)
    report = {"scope": f"Real Jobs/{settings.provider}/Kokoro with already saved real YouTube captions; no fresh acquisition or actual source network calls.",
              "source_lesson_id": source_lesson.id, "source_hashes": {s.id: s.content_hash for s in source_lesson.sources},
              "work_dir": str(settings.data), "fingerprint": model.fingerprint()}
    started = time.monotonic()
    lesson = None
    try:
        for source in source_lesson.sources:
            store.put_source(source)
        jobs.start()
        request = LearningRequest(goal=args.goal or source_lesson.request.goal,
                                  prior_knowledge=source_lesson.request.prior_knowledge,
                                  time_budget_seconds=args.duration_seconds,
                                  request_id="cached-check-" + uuid.uuid4().hex)
        lesson = jobs.create(request)
        # Seed at the persisted acquisition boundary before yielding to the worker.
        # Evidence remains actual saved YouTube captions with original IDs/times.
        lesson.sources = source_lesson.sources
        if getattr(args, 'record_searches', False):
            # Carry over the saved lesson's real first search so a request for
            # more sources uses its second search slot. That search is recorded
            # and answered with no results: no network call, no credits.
            lesson.acquisition = source_lesson.acquisition.model_copy(deep=True)
            assert all(r.completed for r in lesson.acquisition.rounds)
        store.save(lesson)
        deadline = time.monotonic() + args.budget_seconds
        while True:
            lesson = jobs.present(store.lesson(lesson.id))
            if getattr(args, 'first_only', False) and lesson.readiness.ready_short_ids:
                report['first_playable_observed_seconds'] = time.monotonic() - started
                report['stopped_after_first_playable'] = True
                lesson = jobs.cancel(lesson.id)
                break
            if lesson.job.status in {"complete", "failed", "cancelled", "interrupted"}:
                break
            if time.monotonic() >= deadline:
                lesson = jobs.cancel(lesson.id)
                report["timed_out"] = True
                break
            await asyncio.sleep(.25)
    finally:
        await jobs.stop()
        if lesson:
            lesson = jobs.present(store.lesson(lesson.id))
            report.update(lesson=lesson.model_dump(), seconds=time.monotonic() - started,
                          model_attempts=attempt_history,
                          recorded_searches_not_sent=getattr(sources, 'queries', []))
        store.close()
        (settings.data / "cached-lesson-check.json").write_text(json.dumps(report, indent=2) + "\n")
    if lesson:
        print(json.dumps({"status": lesson.job.status, "error": lesson.job.error.model_dump() if lesson.job.error else None,
                          "seconds": report["seconds"], "ready_shorts": len(lesson.readiness.ready_short_ids),
                          "source_provider_calls": lesson.acquisition.search_provider_calls + lesson.acquisition.transcript_provider_calls,
                          "work_dir": report["work_dir"]}, indent=2), flush=True)
    return 0 if lesson and (lesson.job.status == "complete" or (getattr(args, 'first_only', False) and report.get('stopped_after_first_playable'))) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-inference", action="store_true")
    parser.add_argument("--source-lesson", required=True)
    parser.add_argument("--expected-provider", choices=['turbofieldfare', 'ollama'], default='turbofieldfare',
                        help="Explicitly require the configured provider; never switches it automatically")
    parser.add_argument("--record-searches", action="store_true",
                        help="Let the lesson request its second search; record the query and return no videos (no credits)")
    parser.add_argument("--first-only", action="store_true", help="Stop after the first validated playable short; no claim of full-session completion")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--goal", help="Optional narrower goal supported by the same captions")
    parser.add_argument("--duration-seconds", type=int, default=60)
    parser.add_argument("--budget-seconds", type=int, default=900)
    args = parser.parse_args()
    maximum_duration = 300  # --budget-seconds bounds actual run time
    if not args.approve_inference or not 60 <= args.duration_seconds <= maximum_duration or not 1 <= args.budget_seconds <= 1800:
        parser.error(f"Approve inference with a 60–{maximum_duration}s lesson and a 1–1800s preparation budget.")
    raise SystemExit(asyncio.run(run(args)))


if __name__ == "__main__":
    main()
