"""Explicit owned loopback server launcher. Reuses binaries/weights; never builds/downloads.

Foreground ownership: Control-C/SIGTERM stops only the child this script started.
Upstream verifier is non-destructive to weights but refreshes verified-install.json.
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import httpx
from app.config import TURBO_MODEL
from app.llm.identity import digest, file_identity, process_identity, listening

CHECKPOINT = "0d77464eeb233a2da68ebf9d7dc4edaac7db956d"
SNAPSHOT = "sha256:bf198c9f5ea6462addca1966e5dd669c407537a876e82cf06db9084c5c850b13"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--runtime-revision", required=True, help="Exact inspected checkout revision; binary SHA is authoritative build identity")
    parser.add_argument("--receipt", type=Path, default=ROOT / ".runtime/turbofieldfare-launch.json")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--context", type=int, choices=[4096, 8192, 16384], default=16384)
    args = parser.parse_args()
    if sys.platform != "darwin" or not 1 <= args.port <= 65535:
        parser.error("This owned-process integration requires macOS and a valid port.")
    checkout, model = args.checkout.resolve(), args.model.resolve()
    revision = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if revision != args.runtime_revision or len(revision) != 40:
        parser.error("Checkout differs from the inspected --runtime-revision. Do not silently change versions.")
    if subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"], text=True).strip():
        parser.error("Inspect/resolve dirty runtime checkout before claiming its revision.")
    server, verifier = [checkout / ".build/release" / name for name in ("TurboFieldfareServer", "TurboFieldfareRepack")]
    if not server.is_file() or not verifier.is_file():
        parser.error("Compatible server/verifier binaries are required. Build separately with approval; this launcher never builds.")
    processes = subprocess.check_output(["ps", "-axo", "comm="], text=True)
    if any(Path(line.strip()).name in {"TurboFieldfareServer", "TurboFieldfareMac", "TurboFieldfareCLI", "TurboFieldfareDecodeService", "mlx_lm", "mlx-lm"} for line in processes.splitlines()):
        parser.error("Another model-owning product is active. Reuse it or obtain permission to stop it; no second server was launched.")
    # Port ownership check does not load a model.
    occupied = subprocess.run(["/usr/sbin/lsof", "-nP", f"-iTCP:{args.port}", "-sTCP:LISTEN"], capture_output=True)
    if occupied.returncode == 0:
        parser.error("Port is occupied; inspect/reuse the existing service instead.")
    manifest_path = model / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest["modelID"] != "mlx-community/gemma-4-26b-a4b-it-4bit" or manifest["sourceSnapshotHash"] != SNAPSHOT:
        parser.error("Model is not the pinned compatible Gemma 4 checkpoint; do not replace it automatically.")
    # Existing executable only: documented offline verification, no swift run/build.
    subprocess.run([str(verifier), "--verify-install", "--input-gturbo", str(model)], check=True)
    paths = [server, verifier, manifest_path, model / "verified-install.json"]
    paths += [model / name for name in manifest["files"]]
    paths += sorted((model / "tokenizer").rglob("*"))
    files = {str(path): file_identity(path) for path in paths if not path.is_dir()}
    profile = {"max_context": args.context, "expert_cache_slots": 16, "expert_cache_policy": "lfu",
               "prefill": "on", "prefill_chunk_tokens": 128, "rdadvise": "off", "prompt_cache_mode": "single-prefix"}
    command = [str(server), "--model", str(model), "--model-id", TURBO_MODEL, "--port", str(args.port)]
    for key, value in profile.items():
        command += ["--" + key.replace("_", "-"), str(value)]
    fingerprint = {"runtime_binary_sha256": digest(server), "runtime_checkout_commit": revision,
                   "runtime_commit_scope": "inspected clean checkout; existing build commit unavailable; binary hash identifies build",
                   "checkpoint_revision": CHECKPOINT, "checkpoint_revision_basis": "pinned source index SHA matches validated manifest",
                   "manifest_sha256": digest(manifest_path), "source_snapshot_hash": SNAPSHOT,
                   "tokenizer_sha256": {path.name: digest(path) for path in (model / "tokenizer").iterdir() if path.is_file()},
                   "quantization": manifest["quant"], "runtime_profile": profile,
                   "identity_scope": "upstream-verified install + local owned PID/argv/listening-port receipt"}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    child = subprocess.Popen(command, cwd=checkout)
    stopping = False
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
        if child.poll() is None:
            child.terminate()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        url = f"http://127.0.0.1:{args.port}/v1"
        deadline = time.monotonic() + 120
        with httpx.Client(timeout=2, trust_env=False, follow_redirects=False) as client:
            while child.poll() is None and not stopping:
                try:
                    health = client.get(url.removesuffix("/v1") + "/health")
                    models = client.get(url + "/models")
                    if health.json().get("status") == "ok" and models.json()["data"][0]["id"] == TURBO_MODEL and listening(child.pid, args.port):
                        break
                except (httpx.HTTPError, ValueError, KeyError):
                    pass
                if time.monotonic() > deadline:
                    raise RuntimeError("Server readiness timed out; inspect its local log.")
                time.sleep(.25)
            else:
                raise RuntimeError("Server exited before readiness.")
        receipt = {"version": 1, "pid": child.pid, "process_identity": process_identity(child.pid),
                   "base_url": url, "model": TURBO_MODEL, "profile": profile, "files": files,
                   "fingerprint": fingerprint, "command": command, "model_path": str(model)}
        temporary = args.receipt.with_suffix(".tmp")
        temporary.write_text(json.dumps(receipt, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(args.receipt)
        print(f"Owned server ready; LLM_IDENTITY_RECEIPT={args.receipt.resolve()}", flush=True)
        child.wait()
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()  # Only our exact child, never an unrelated service.
                child.wait()
        # Leave receipt for diagnosis; a stopped PID fails readiness automatically.


if __name__ == "__main__":
    main()
