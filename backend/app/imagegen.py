"""Locally generated cover images (IMAGE_SEARCH=generate) with Z-Image-Turbo through mflux.

mflux runs in its own environment (scripts/imagegen_worker.py) because it needs
transformers 5, which conflicts with Kokoro. The worker keeps the model resident and
serves one request at a time. Like photo search, a cover is optional decoration:
any failure or timeout leaves the short without one.
"""
import hashlib
import json
import os
from pathlib import Path
import select
import subprocess
import tempfile
import threading
import time
from .contracts import CoverPhoto
from .photos import words

ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "scripts" / "imagegen_worker.py"
# Measured on an M3 Max: 480x848 at 6 steps took about 14 s; 720x1280 at 9 steps took 57 s.
# The cover sits behind a dark overlay, so the smaller size is enough.
WIDTH, HEIGHT, STEPS = 480, 848, 6
LOAD_TIMEOUT = 120
OUTCOME_VERBS = {"explain", "identify", "compare", "trace", "predict", "apply", "describe"}


def cover_prompt(goal, objective):
    topic = " ".join(words(goal)[:4]) or goal[:60]
    focus = objective.strip().rstrip(".")
    first, _, rest = focus.partition(" ")
    if first.lower() in OUTCOME_VERBS and rest:
        focus = rest
    return (f"A realistic editorial photograph about {topic}, showing {focus[:140]}. "
            "For an abstract idea, show a symbolic real-world scene. Natural light, sharp detail, "
            "cinematic vertical composition. No text, letters, captions, logos or watermarks.")


class ImageGenerator:
    # Publication waits this long; the first request may include loading the model.
    wait_seconds = LOAD_TIMEOUT

    def __init__(self, assets, python, model, timeout=90.0):
        self.assets, self.python, self.model, self.timeout = assets, str(python), model, timeout
        self.lock = threading.Lock()
        self.process = None

    def ensure(self):
        if self.process and self.process.poll() is None:
            return self.process
        if not Path(self.python).exists():
            raise RuntimeError(f"Image generation environment not found: {self.python}")
        (ROOT / ".runtime").mkdir(exist_ok=True)
        log = open(ROOT / ".runtime" / "imagegen.log", "ab")
        self.process = subprocess.Popen([self.python, str(WORKER), self.model], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=log, text=True, bufsize=1, env={**os.environ, "HF_HUB_OFFLINE": "1"})
        log.close()
        if not self.reply(LOAD_TIMEOUT).get("ready"):
            raise RuntimeError("Image generation worker did not become ready.")
        return self.process

    def reply(self, timeout):
        deadline = time.monotonic() + timeout
        while True:
            ready, _, _ = select.select([self.process.stdout], [], [], max(0, deadline - time.monotonic()))
            line = self.process.stdout.readline() if ready else ""
            if not line:
                # A timed-out or dead worker is restarted on the next request.
                self.stop()
                raise TimeoutError("Image generation worker timed out.")
            if line.startswith("{"):
                return json.loads(line)

    def warm(self):
        """Load the model before the first short needs it; failures surface on use."""
        try:
            with self.lock:
                self.ensure()
        except Exception:
            self.stop()

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.kill()
        self.process = None

    def cover(self, goal, objective, exclude=frozenset(), cancel=None):
        prompt = cover_prompt(goal, objective)
        # Same prompt, same seed: a retried short gets the same (deduplicated) image.
        seed = int(hashlib.sha256(prompt.encode()).hexdigest()[:8], 16)
        with self.lock, tempfile.TemporaryDirectory() as folder:
            if cancel is not None and cancel.is_set():
                return None
            out = Path(folder) / "cover.png"
            process = self.ensure()
            started = time.monotonic()
            process.stdin.write(json.dumps({"prompt": prompt, "width": WIDTH, "height": HEIGHT,
                                            "seed": seed, "steps": STEPS, "out": str(out)}) + "\n")
            process.stdin.flush()
            result = self.reply(self.timeout)
            if not result.get("ok") or not out.exists():
                raise RuntimeError(result.get("error") or "Image generation failed.")
            record = self.assets.register_bytes(out.read_bytes(), kind="image",
                original_source=f"generated:z-image-turbo:{self.model}:seed={seed}"[:500],
                creator="Z-Image-Turbo, generated locally",
                permission_basis="Generated on this computer with Z-Image-Turbo (Apache-2.0); no third-party image used.",
                attribution="AI-generated image · Z-Image-Turbo",
                source_context=f"Generated in {time.monotonic() - started:.0f}s from: {prompt}"[:300],
                illustrative=True, license_url=None, cancel=cancel)
        return CoverPhoto(asset=record, alt=f"AI-generated image: {objective}"[:240], query=prompt[:120])
