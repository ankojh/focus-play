"""Regenerate the browser fixture through the real measured-timeline compiler."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.contracts import ModelStoryboard, Short, TranscriptSegment
from app.storyboard import COMPILER_VERSION, compile_storyboard
from app.validation import attach_evidence, validate_draft


def fixture_short():
    fixture = json.loads((ROOT / "fixtures/storyboard-lookup.json").read_text())
    segments = [TranscriptSegment.model_validate(s) for s in fixture["segments"]]
    draft = attach_evidence(ModelStoryboard.model_validate(fixture["draft"]), segments)
    validate_draft(draft, segments, False)
    for beat, (start, end) in zip(draft.narration_units, fixture["boundaries"], strict=True):
        beat.start_ms, beat.end_ms = start, end
    scenes, units = compile_storyboard(draft, fixture["duration_ms"])
    return Short(id="storyboard_fixture", objective=draft.objective, status="ready",
        storyboard_version=2, timeline_compiler_version=COMPILER_VERSION,
        narration_units=units, scenes=scenes, measured_duration_ms=fixture["duration_ms"],
        evidence_references=[units[0].evidence], audio_path="a" * 64 + ".wav")


if __name__ == "__main__":
    path = ROOT / "fixtures/storyboard-lookup-playback.json"
    path.write_text(json.dumps(fixture_short().model_dump(), indent=2) + "\n")
    print(path)
