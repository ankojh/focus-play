"""Local Z-Image-Turbo worker, run with the separate .runtime/imagegen environment.

mflux needs transformers 5, which conflicts with Kokoro in the main .venv, so the
API talks to this process over JSON lines instead of importing it. The model loads
once and stays resident. The worker exits when the API closes its stdin.

Request:  {"prompt": str, "width": int, "height": int, "seed": int, "steps": int, "out": path}
Response: {"ok": true, "seconds": float} or {"ok": false, "error": str}
"""
import json
import sys
import time


def main():
    from mflux.models.common.config import ModelConfig
    from mflux.models.z_image import ZImage
    model_path = sys.argv[1] if len(sys.argv) > 1 else "filipstrand/Z-Image-Turbo-mflux-4bit"
    model = ZImage(model_config=ModelConfig.z_image_turbo(), model_path=model_path)
    print(json.dumps({"ok": True, "ready": True}), flush=True)
    for line in sys.stdin:
        started = time.monotonic()
        try:
            job = json.loads(line)
            image = model.generate_image(prompt=job["prompt"], seed=int(job["seed"]), num_inference_steps=int(job["steps"]),
                                         width=int(job["width"]), height=int(job["height"]))
            image.save(job["out"])
            print(json.dumps({"ok": True, "seconds": time.monotonic() - started}), flush=True)
        except Exception as exc:  # Report and keep serving; one bad prompt must not kill the model.
            print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]}), flush=True)


if __name__ == "__main__":
    main()
