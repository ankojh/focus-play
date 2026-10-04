"""Download speech assets only. No learner content is sent."""
import json
import os
import sys
from pathlib import Path
os.environ["HF_HUB_OFFLINE"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.config import Settings
settings = Settings()
from huggingface_hub import snapshot_download
folder = snapshot_download("hexgrad/Kokoro-82M", allow_patterns=["config.json", "kokoro-v1_0.pth", f"voices/{settings.voice}.pt", "README.md", "LICENSE"], cache_dir=str(settings.data / "hf" / "hub"))
# Save the exact revision and voice used during setup.
(settings.data / "speech-download.json").write_text(json.dumps({"repository": "hexgrad/Kokoro-82M", "revision": Path(folder).name, "voice": settings.voice}, indent=2))
print(f"Speech assets are ready: {folder}")
