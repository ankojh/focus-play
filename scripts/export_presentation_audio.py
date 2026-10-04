"""Export offline actual-voice caption examples; no model/source requests or speech changes.

These original illustrative fixtures are pronunciation/transition review material,
not evidence of comprehension or a human listening review. Run from the repository.
"""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from app.contracts import EvidenceRef, NarrationUnit
from app.providers import Speech


def main():
    speech = Speech(Settings())
    if not speech.ready():
        raise SystemExit("Configured local speech is not ready; no example exported.")
    output = ROOT / "docs" / "presentation-audio"
    output.mkdir(exist_ok=True)
    lookup = json.loads((ROOT / "fixtures/storyboard-lookup-playback.json").read_text())
    mixed = json.loads((ROOT / "fixtures/mixed-visuals.json").read_text())
    examples = {"lookup": [NarrationUnit.model_validate(u) for u in lookup["narration_units"]]}
    examples["numbers-and-code"] = [NarrationUnit(text=s["text"], evidence=EvidenceRef(
        source_id=s["source_id"], segment_ids=[s["id"]], quote=s["text"])) for s in mixed["segments"][1:]]
    report = {"notice": "Original illustrative fixtures. Actual configured local voice; no source credits used. Listening review and comprehension claims are not established.",
              "speech": speech.fingerprint(), "examples": []}
    for name, units in examples.items():
        key = hashlib.sha256(json.dumps({"example_version": 1, "speech": speech.fingerprint(),
                            "texts": [u.text for u in units]}, sort_keys=True).encode()).hexdigest()
        started = time.perf_counter()
        audio, duration, cached = speech.synthesize(units, key, threading.Event())
        elapsed = time.perf_counter() - started
        shutil.copyfile(speech.settings.data / "audio" / audio, output / f"{name}.wav")
        report["examples"].append({"file": f"{name}.wav", "duration_ms": duration,
             "synthesis_seconds": round(elapsed, 3), "cache_hit": cached,
             "captions": [{"text": u.text, "start_ms": u.start_ms, "end_ms": u.end_ms} for u in units]})
    (output / "measured-captions.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
