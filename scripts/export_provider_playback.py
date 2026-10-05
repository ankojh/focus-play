"""Export PASSED real-provider output and measured audio to an isolated playback store.

No model/speech/source calls, no fixture substitution, no edits to the user library.
A pre-resume report requires explicit original evidence; newer reports embed it.
"""
import argparse
import hashlib
import json
import re
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from app.contracts import Job, Lesson, ModelStoryboard, SavedLearningRequest, Short, Source, TranscriptSegment
from app.store import Store
from app.storyboard import COMPILER_VERSION, compile_storyboard
from app.validation import attach_evidence, validate_draft
from app.assets import Assets
from app.readiness import required_media, snapshot_readiness


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, help="Original evidence file for older reports lacking embedded evidence")
    args = parser.parse_args()
    report = json.loads(args.report.read_text())
    stages = {r["stage"]: r for r in report["rows"]}
    if any(stages.get(name, {}).get("status") != "passed" for name in ("storyboard", "review")):
        parser.error("A real passed storyboard AND source/teaching review with measured speech are required.")
    passages = report.get("evidence")
    if passages is None:
        if args.evidence is None: parser.error("Supply the actual original evidence for this older report; never guess it.")
        passages = json.loads(args.evidence.read_text())["segments"]
    segments = [TranscriptSegment.model_validate(s) for s in passages]
    if len({s.source_id for s in segments}) != 1:
        parser.error("This exporter requires the single-source local diagnostic fixture.")
    original = Settings()
    if args.output_dir.exists(): parser.error("Use a new isolated output directory; no data is overwritten.")
    settings = Settings(data=args.output_dir)
    if (original.data / "hf").is_dir():
        (settings.data / "hf").rmdir()  # Only the newly created empty directory.
        (settings.data / "hf").symlink_to(original.data / "hf", target_is_directory=True)
    store = Store(settings.data)
    try:
        assets = Assets(store); assets.install_bundled()
        draft = attach_evidence(ModelStoryboard.model_validate(stages["storyboard"]["output"]), segments)
        validate_draft(draft, segments, False)
        media = stages["review"]["measured_media"]
        if not re.fullmatch(r"[a-f0-9]{64}\.wav", media["audio"]):
            raise ValueError("Invalid managed audio filename in report.")
        audio = original.data / "audio" / media["audio"]
        meta = json.loads((original.data / "cache" / (audio.stem + ".json")).read_text())
        if meta["texts"] != [u.text for u in draft.narration_units] or meta["duration_ms"] != media["duration_ms"]:
            raise ValueError("Measured audio cache does not match the report's actual narration/duration.")
        import soundfile as sf
        info = sf.info(audio)
        if info.samplerate != 24000 or info.channels != 1 or round(info.duration * 1000) != meta["duration_ms"]:
            raise ValueError("Invalid measured WAV; do not synthesize substitute audio.")
        for unit, (start, end) in zip(draft.narration_units, meta["boundaries"], strict=True):
            unit.start_ms, unit.end_ms = start, end
        scenes, units = compile_storyboard(draft, meta["duration_ms"], assets)
        provenance = {**report["fingerprint"], "speech": media["speech"], "language": "en"}
        short = Short(id="provider_check_mixed", objective=draft.objective, prerequisites=draft.prerequisites,
                      narration_units=units, scenes=scenes, evidence_references=[u.evidence for u in units],
                      storyboard_version=2, timeline_compiler_version=COMPILER_VERSION, status="ready",
                      measured_duration_ms=meta["duration_ms"], audio_path=audio.name, provider_settings=provenance)
        shutil.copy2(audio, settings.data / "audio" / audio.name)
        required_media(short, settings.data, assets)
        source = Source(id=segments[0].source_id, title="Original local illustrative evidence (real provider check)",
                        source_type="original_sample", transcript_status="available", segments=segments,
                        provenance="Original illustrative fixtures; generated teaching/audio are real TurboFieldfare/Kokoro. Not a live YouTube lesson.",
                        content_hash=hashlib.sha256(json.dumps(passages, sort_keys=True).encode()).hexdigest())
        store.put_source(source)
        now = time.time()
        lesson = Lesson(id="lesson_real_provider_check", request=SavedLearningRequest(
                            goal="Provider verification: inspect the actual generated mixed storyboard", request_id="provider-playback-check"),
                        shorts=[short], short_ids=[short.id], sources=[source], status="ready",
                        planned_duration_ms=short.measured_duration_ms, original_planned_duration_ms=short.measured_duration_ms,
                        provider_settings=provenance, job=Job(id="provider_playback_job", lesson_id="lesson_real_provider_check",
                            status="complete", stage="complete", created_at=now, updated_at=now))
        lesson.readiness = snapshot_readiness(lesson, settings.data, assets)
        store.save(lesson)
        (settings.data / "playback-origin.json").write_text(json.dumps({"report": str(args.report.resolve()),
            "report_sha256": hashlib.sha256(args.report.read_bytes()).hexdigest(),
            "scope": source.provenance, "lesson_id": lesson.id}, indent=2) + "\n")
        print(settings.data)
    finally:
        store.close()


if __name__ == "__main__":
    main()
