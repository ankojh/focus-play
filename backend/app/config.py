import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
TURBO_MODEL = "gemma-4-26b-a4b-it"


def local_url(value: str, path: str) -> str:
    """Only literal loopback HTTP endpoints; no redirects, proxy or credentials."""
    try:
        url = urlparse(value)
        port = url.port
        if (url.scheme != "http" or url.hostname not in {"localhost", "127.0.0.1", "::1"}
                or url.username is not None or url.password is not None
                or url.query or url.fragment or "?" in value or "#" in value
                or url.path.rstrip("/") != path or port is None or not 1 <= port <= 65535):
            raise ValueError
    except ValueError:
        raise ValueError(f"Use a loopback HTTP URL with an explicit port and path '{path or '/'}'; no credentials/query/fragment.") from None
    return value.rstrip("/")


def env_provider():
    # Existing OLLAMA_* installations are NOT silently migrated. New setup is TurboFieldfare.
    return os.getenv("LLM_PROVIDER") or ("ollama" if any(k.startswith("OLLAMA_") for k in os.environ) else "turbofieldfare")


@dataclass
class Settings:
    data: Path = field(default_factory=lambda: ROOT / os.getenv("DATA_DIR", ".data"))
    provider: str = field(default_factory=env_provider)
    base_url: str | None = None
    ollama_url: str | None = None
    model: str | None = None
    context: int | None = None
    predict: int | None = None
    identity_receipt: Path | None = field(default_factory=lambda: Path(os.environ["LLM_IDENTITY_RECEIPT"]) if os.getenv("LLM_IDENTITY_RECEIPT") else None)
    connect_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_CONNECT_TIMEOUT", "5")))
    read_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_READ_TIMEOUT", "120")))
    attempt_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_ATTEMPT_TIMEOUT", "300")))
    task_timeout: float = field(default_factory=lambda: float(os.getenv("LLM_TASK_TIMEOUT", "60")))
    first_playable_timeout: float = field(default_factory=lambda: float(os.getenv("FIRST_PLAYABLE_TIMEOUT", "180")))
    speech: str = field(default_factory=lambda: os.getenv("SPEECH_PROVIDER", "kokoro"))
    voice: str = field(default_factory=lambda: os.getenv("KOKORO_VOICE", "af_heart"))
    macos_voice: str = field(default_factory=lambda: os.getenv("MACOS_VOICE", "Samantha"))
    youtube_key: str = field(default_factory=lambda: os.getenv("YOUTUBE_API_KEY", ""))
    supadata_key: str = field(default_factory=lambda: os.getenv("SUPADATA_API_KEY", ""))
    rank_candidates: int = field(default_factory=lambda: int(os.getenv("RANK_CANDIDATES", "8")))
    image_search: str = field(default_factory=lambda: os.getenv("IMAGE_SEARCH", "openverse"))
    imagegen_python: Path = field(default_factory=lambda: ROOT / os.getenv("IMAGEGEN_PYTHON", ".runtime/imagegen/bin/python"))
    imagegen_model: str = field(default_factory=lambda: os.getenv("IMAGEGEN_MODEL", "filipstrand/Z-Image-Turbo-mflux-4bit"))
    queue_size: int = 8

    def __post_init__(self):
        if self.provider not in {"turbofieldfare", "ollama"}:
            raise ValueError("LLM_PROVIDER must be turbofieldfare or ollama; no automatic fallback is supported.")
        turbo = self.provider == "turbofieldfare"
        def setting(new, old, default):
            return os.getenv(new) or (os.getenv(old) if not turbo else None) or default
        self.model = self.model or setting("LLM_MODEL", "OLLAMA_MODEL", TURBO_MODEL if turbo else "gemma4:12b-mlx")
        self.context = int(self.context if self.context is not None else setting("LLM_CONTEXT", "OLLAMA_CONTEXT", "16384" if turbo else "8192"))
        self.predict = int(self.predict if self.predict is not None else setting("LLM_MAX_OUTPUT_TOKENS", "OLLAMA_PREDICT", "2200"))
        self.ollama_url = self.ollama_url or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        self.base_url = local_url(self.base_url or setting("LLM_BASE_URL", "OLLAMA_URL", "http://127.0.0.1:8080/v1" if turbo else self.ollama_url), "/v1" if turbo else "")
        if not turbo:
            self.ollama_url = self.base_url
        if (turbo and self.model != TURBO_MODEL) or (not turbo and self.model == TURBO_MODEL):
            raise ValueError("LLM_MODEL does not match LLM_PROVIDER. TurboFieldfare requires gemma-4-26b-a4b-it; Ollama needs its installed tag.")
        if "cloud" in self.model.lower() or self.speech not in {"kokoro", "macos"}:
            raise ValueError("Use an installed local model and a supported local speech provider.")
        if not 2048 <= self.context <= 16384 or not 512 <= self.predict <= 4096 or self.predict >= self.context:
            raise ValueError("Model context/output limit is outside the supported range (context 2048–16384, output 512–4096 and below context).")
        if not (1 <= self.connect_timeout <= 30 and 1 <= self.read_timeout <= 300 and 1 <= self.attempt_timeout <= 600):
            raise ValueError("LLM timeouts must be bounded: connect 1–30s, read 1–300s, attempt 1–600s.")
        if not 1 <= self.task_timeout <= 120 or not 1 <= self.first_playable_timeout <= 240:
            raise ValueError("Generation budgets must be bounded: task 1–120s, first playable 1–240s.")
        if self.image_search not in {"openverse", "generate", "off"}:
            raise ValueError("IMAGE_SEARCH must be openverse, generate or off.")
        if not 2 <= self.rank_candidates <= 15:
            raise ValueError("RANK_CANDIDATES must be between 2 and 15.")
        if self.identity_receipt is not None:
            self.identity_receipt = (ROOT / self.identity_receipt).resolve()
        self.data = self.data.resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        for folder in ["audio", "transcripts", "cache", "hf"]:
            (self.data / folder).mkdir(exist_ok=True)
        os.environ.setdefault("HF_HOME", str(self.data / "hf"))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
