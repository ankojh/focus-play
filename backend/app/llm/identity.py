"""Local launch receipt, not an identity claim made by /health.

The explicit launcher verifies the installation once and records file identities.
Health checks compare metadata and bind PID/start time/argv to the listening port.
This trusts the operator-owned receipt and OS, not arbitrary remote servers.
"""
import hashlib
import json
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from ..errors import AppError


def digest(path):
    with Path(path).open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def file_identity(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError("Identity files must be regular non-symlink files.")
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def process_identity(pid):
    return subprocess.check_output(["/bin/ps", "-p", str(int(pid)), "-o", "lstart=", "-o", "command="], text=True, timeout=3).strip()


def listening(pid, port):
    output = subprocess.check_output(["/usr/sbin/lsof", "-nP", "-a", "-p", str(int(pid)),
                                      f"-iTCP:{int(port)}", "-sTCP:LISTEN", "-Fn"], text=True, timeout=3)
    names = [line[1:] for line in output.splitlines() if line.startswith("n")]
    return names == [f"127.0.0.1:{port}"]


class LaunchIdentity:
    def __init__(self, settings):
        self.settings = settings
        self.cached_metadata = None
        self.verified = None

    def verify(self):
        try:
            path = self.settings.identity_receipt
            if path is None:
                raise ValueError("LLM_IDENTITY_RECEIPT is required. Use scripts/turbofieldfare_server.py to verify and launch the existing install.")
            metadata = file_identity(path)
            if metadata != self.cached_metadata:
                if Path(path).stat().st_size > 1_000_000:
                    raise ValueError("Oversized launch receipt.")
                receipt = json.loads(Path(path).read_text())
                if not isinstance(receipt, dict) or any(not isinstance(receipt.get(key), dict) for key in ("profile", "files", "fingerprint")):
                    raise ValueError("Malformed ownership receipt.")
                if receipt["version"] != 1 or receipt["base_url"] != self.settings.base_url:
                    raise ValueError("Receipt endpoint/version differs from LLM_BASE_URL.")
                self.verified = receipt
                self.cached_metadata = metadata
            receipt = self.verified
            if receipt["model"] != self.settings.model or self.settings.context > receipt["profile"]["max_context"]:
                raise ValueError("LLM_MODEL/LLM_CONTEXT exceeds or differs from the owned server profile; restart it explicitly.")
            if process_identity(receipt["pid"]) != receipt["process_identity"]:
                raise ValueError("Owned server process changed or stopped; relaunch to refresh the receipt.")
            if not listening(receipt["pid"], urlparse(self.settings.base_url).port):
                raise ValueError("Receipt process is not the loopback endpoint owner.")
            for name, expected in receipt["files"].items():
                if file_identity(name) != expected:
                    raise ValueError("Runtime/model metadata changed; verify and relaunch before cache reuse.")
            # Stable across restarts: PID, time and absolute paths are not model provenance.
            return receipt["fingerprint"]
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
            raise AppError("MODEL_IDENTITY_INVALID", f"TurboFieldfare identity unavailable: {str(exc)[:350]}", 503) from None
