"""Opt-in transport/disconnect smoke; not structured lesson quality or paid acquisition."""
import argparse
import json
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.config import Settings
from app.errors import Cancelled
from app.providers import create_model


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-inference", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.approve_inference or args.output.exists():
        parser.error("Approve inference and choose a new output path.")
    settings = Settings()
    settings.predict = 512
    settings.attempt_timeout = 30
    model = create_model(settings)
    fingerprint = model.fingerprint()
    cancel = threading.Event()
    timer = threading.Timer(.3, cancel.set); timer.daemon = True; timer.start()
    started = time.monotonic()
    try:
        model.complete([{"role": "user", "content": "Reply with exactly READY after reading this data. " + "local fixture evidence " * 1500}], {}, 0, cancel, lambda text: None)
        raise RuntimeError("Expected cancellation during a long prompt.")
    except Cancelled:
        cancelled = time.monotonic() - started
    finally:
        timer.cancel()
    text = []
    started = time.monotonic()
    finish = model.complete([{"role": "user", "content": "Reply with exactly READY."}], {}, 0, threading.Event(), text.append)
    result = {"scope": "Real disconnect and next-request release check, not lesson/schema acceptance",
              "fingerprint": fingerprint, "client_cancel_return_seconds": cancelled,
              "next_request_seconds": time.monotonic() - started, "finish_reason": finish,
              "content": "".join(text), "usage": getattr(model, "transport_metrics", {})}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "fingerprint"}, indent=2))
    if result["content"].strip() != "READY" or finish != "stop":
        raise SystemExit("Transport completed but smoke output did not match READY.")


if __name__ == "__main__":
    main()
