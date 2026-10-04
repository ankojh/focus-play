from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlparse
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

@dataclass
class Settings:
    data: Path = ROOT / os.getenv("DATA_DIR", ".data")
    ollama_url: str = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
    model: str = os.getenv("OLLAMA_MODEL", "qwen3:8b")
    context: int = int(os.getenv("OLLAMA_CONTEXT", "8192"))
    predict: int = int(os.getenv("OLLAMA_PREDICT", "2200"))
    speech: str = os.getenv("SPEECH_PROVIDER", "kokoro")
    voice: str = os.getenv("KOKORO_VOICE", "af_heart")
    macos_voice: str = os.getenv("MACOS_VOICE", "Samantha")
    youtube_key: str = os.getenv("YOUTUBE_API_KEY", "")
    queue_size: int = 8
    def __post_init__(self):
        url = urlparse(self.ollama_url)
        if url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"} or url.username or url.password or url.path not in {"", "/"}:
            raise ValueError("Ollama must use a loopback HTTP address.")
        if "cloud" in self.model.lower() or self.speech not in {"kokoro", "macos"}:
            raise ValueError("Use an installed local model and a supported local speech provider.")
        if not 2048 <= self.context <= 16384 or not 512 <= self.predict <= 4096:
            raise ValueError("Model context or output limit is outside the supported range.")
        self.data = self.data.resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        for folder in ["audio", "transcripts", "cache", "hf"]:
            (self.data / folder).mkdir(exist_ok=True)
        os.environ.setdefault("HF_HOME", str(self.data / "hf"))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
