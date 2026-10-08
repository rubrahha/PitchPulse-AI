"""Environment-driven settings; secrets never go to the browser."""
import os
import importlib.util
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def positive_int(name: str, default: int, minimum: int = 1, maximum: int = 86400) -> int:
    try:
        return min(max(int(os.environ.get(name, default)), minimum), maximum)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini").strip()
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2").strip()
    stt_provider: str = os.getenv("STT_PROVIDER", "auto").strip().lower()
    stt_model: str = os.getenv("STT_MODEL", "gpt-4o-mini-transcribe").strip()
    stt_local_model: str = os.getenv("STT_LOCAL_MODEL", "tiny").strip()
    cricket_api_key: str = os.getenv("CRICKET_API_KEY", "").strip()
    football_api_key: str = os.getenv("FOOTBALL_API_KEY", "").strip()
    news_cache_seconds: int = positive_int("NEWS_CACHE_SECONDS", 180, 30)
    cricket_cache_seconds: int = positive_int("CRICKET_CACHE_SECONDS", 1200, 60)
    football_cache_seconds: int = positive_int("FOOTBALL_CACHE_SECONDS", 180, 60)

    @property
    def ai_ready(self) -> bool:
        return (self.llm_provider == "openai" and bool(self.openai_api_key)) or self.llm_provider == "ollama"

    @property
    def stt_backend(self) -> str:
        if self.stt_provider in ("off", "none"):
            return "none"
        if self.stt_provider == "openai":
            return "openai" if self.openai_api_key else "none"
        if self.stt_provider == "local":
            return "local" if importlib.util.find_spec("faster_whisper") else "none"
        if self.openai_api_key:
            return "openai"
        if importlib.util.find_spec("faster_whisper"):
            return "local"
        return "none"
