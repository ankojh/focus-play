"""Opt-in real-provider checks on fixed local evidence; never calls source services.

Reports actual attempts/usage and valid measured media, not fixture inference.
No output is inserted into the user's library. Local reports contain source text.
"""
import argparse
import hashlib
import json
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.assets import Assets
from app.config import Settings
from app.contracts import CandidateRanking, LessonPlan, ModelStoryboard, TranscriptSegment, Short
from app.errors import AppError, Cancelled
from app.providers import create_model, Speech
from app.storyboard import COMPILER_VERSION, compile_storyboard
from app.store import Store
from app.teaching import validate_plan
from app.validation import SupportCheck, attach_evidence, validate_draft, verify_support


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-inference", action="store_true")
    parser.add_argument("--stages", nargs="+", choices=["ranking", "planning", "storyboard", "review", "insufficient"],
                        default=["ranking", "planning", "storyboard", "review", "insufficient"])
    parser.add_argument("--budget-seconds", type=int, default=900)
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime/turbofieldfare-provider-check.json")
    parser.add_argument("--block-python-network", action="store_true")
    args = parser.parse_args(argv)
    if not args.approve_inference or not 1 <= args.budget_seconds <= 1800:
        parser.error("Use --approve-inference with a 1–1800 second budget. No paid source calls occur.")
    if args.output.exists(): parser.error("Choose a new output path; historical checks are not overwritten.")
    if args.block_python_network:
        connect = socket.socket.connect
        def local_connect(sock, address):
            if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
                raise OSError("External Python connections are blocked.")
            return connect(sock, address)
        socket.socket.connect = local_connect
    settings = Settings()
    model, speech = create_model(settings), Speech(settings)
    cancel = threading.Event()
    timer = threading.Timer(args.budget_seconds, cancel.set); timer.daemon = True; timer.start()
    report = {"scope": "Real local inference on original illustrative fixtures; no YouTube acquisition or live-source quality claim.",
              "network_boundary": "Python external sockets blocked; separate Swift process not sandboxed" if args.block_python_network else "Loopback inference; no source calls",
              "rows": []}
    store = Store(settings.data)
    assets = Assets(store); assets.install_bundled()
    fixture = json.loads((ROOT / "fixtures/mixed-visuals.json").read_text())
    segments = [TranscriptSegment.model_validate(s) for s in fixture["segments"]]
    passages = [s.model_dump() for s in segments]
    report["evidence"] = passages
    draft = None
    try:
        report["fingerprint"] = model.fingerprint()
        for stage in args.stages:
            started = time.monotonic(); model.attempts = []
            row = {"stage": stage}
            try:
                if stage == "ranking":
                    candidates = [{"video_id": f"fixture0000{i}", "transcript_excerpt": s.text, "title": "Original local diagnostic", "channel": "Fixture"} for i, s in enumerate(segments)]
                    def valid(result):
                        if sorted(s.video_id for s in result.scores) != sorted(c["video_id"] for c in candidates):
                            raise ValueError("Score every supplied candidate exactly once.")
                    result = model.generate(CandidateRanking, {"task": "Score every supplied candidate once, 1–5, for teaching key-to-row lookup from its passage. Do not invent evidence.", "candidates": candidates}, cancel, valid)
                elif stage == "planning":
                    task = {"task": "Plan two source-supported observable outcomes: key-to-row mapping, then comparing the supplied signed values. Use plan version 3, target durations 15000–30000, curriculum_role core, explicit concept IDs/dependencies and evidence. No invented examples. Do not pad.",
                            "plan_version": 3, "max_objectives": 2, "max_target_ms": 30000, "segments": passages}
                    result = model.generate(LessonPlan, task, cancel, lambda p: validate_plan(p, segments, 2, 60000, calibrated=True))
                elif stage == "storyboard":
                    task = {"task": "Teach the supplied key-to-row lookup and signed scale examples in one ModelStoryboard version 2 with exactly three scenes, in order: diagram scene_0 (key to row), table scene_1 (A/Alpha and B/Beta), chart scene_2 (-12, 0, 1500 units). Use 3 beats, 40–80 total spoken words. Cite seg_lookup for diagram/table and seg_chart for chart. Values are explicitly illustrative synthetic fixtures, not a performance benchmark. Reveal every visual target before focus/connect; every diagram node needs a 3–8 word detail and allowed icon. Question must be null; prerequisites=[]. No new values or facts.",
                            "segments": passages, "question_required": False}
                    def valid(body):
                        candidate = attach_evidence(body, segments)
                        validate_draft(candidate, segments, False)
                        if [s.kind for s in candidate.scenes] != ["diagram", "table", "chart"]:
                            raise ValueError("Use exactly the requested diagram/table/chart scenes in that order.")
                    result = model.generate(ModelStoryboard, task, cancel, valid)
                    draft = attach_evidence(result, segments)
                elif stage == "review":
                    if draft is None:
                        raise ValueError("A successful actual storyboard is required before review; no fixture is substituted.")
                    verify_support(model, draft, segments, cancel, teaching={"outcome": draft.objective, "role": "mechanism"})
                    result = {"source_and_teaching_review": "passed"}
                    speech.prepare()
                    key = hashlib.sha256(json.dumps({"draft": draft.model_dump(), "llm": report["fingerprint"], "speech": speech.fingerprint()}, sort_keys=True).encode()).hexdigest()
                    audio, duration, hit = speech.synthesize(draft.narration_units, key, cancel)
                    scenes, units = compile_storyboard(draft, duration, assets)
                    row["measured_media"] = {"audio": audio, "duration_ms": duration, "audio_cache_hit": hit, "visual_kinds": [s.kind for s in scenes], "speech": speech.fingerprint()}
                    row["playback"] = Short(id="provider_check_mixed", objective=draft.objective,
                        prerequisites=draft.prerequisites, narration_units=units, scenes=scenes,
                        evidence_references=[u.evidence for u in units], status="ready", storyboard_version=2,
                        timeline_compiler_version=COMPILER_VERSION, audio_path=audio, measured_duration_ms=duration,
                        provider_settings={**report["fingerprint"], "speech": speech.fingerprint(), "language": "en"}).model_dump()
                else:
                    result = model.generate(LessonPlan, {"task": "The passages cannot support the requested weather prediction. Return sufficient_evidence=false, objectives=[], no invented claims.", "goal": "Predict tomorrow's rainfall in Paris", "segments": passages}, cancel)
                    if result.sufficient_evidence or result.objectives: raise ValueError("Insufficient evidence must not invent a plan.")
                row["status"] = "passed"
                row["output"] = result.model_dump() if hasattr(result, "model_dump") else result
            except (AppError, ValueError, Cancelled) as exc:
                row.update(status="failed", error_code=getattr(exc, "code", type(exc).__name__), error=str(exc)[:500])
            row["seconds"] = time.monotonic() - started
            row["attempts"] = model.attempts
            report["rows"].append(row)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
            print(f"{stage}: {row['status']} ({row['seconds']:.1f}s, {len(model.attempts)} attempts)", flush=True)
            if cancel.is_set(): break
    finally:
        timer.cancel(); store.close()
    return 0 if len(report["rows"]) == len(args.stages) and all(r["status"] == "passed" for r in report["rows"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
