from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # env_ignore_empty: `STT_LANGUAGE=` in .env means "use the default", not "".
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://sectra:sectra@localhost:5433/sectra"
    redis_url: str = "redis://localhost:6380/0"
    #: Root of the shared media volume (downloads, transcripts, exports).
    data_dir: Path = Path("data")

    #: Stable consumer name: on restart the worker replays its own un-acked messages.
    worker_name: str = "worker-1"
    #: Jobs one worker runs at once per stream; resource semaphores bound the real work.
    job_concurrency: int = Field(default=4, ge=1)
    #: Deliveries before a job that keeps crashing the worker is marked failed.
    job_max_attempts: int = Field(default=3, ge=1)

    #: Threads for blocking libraries (yt-dlp, numpy, file writes).
    blocking_threads: int = Field(default=8, ge=1)
    download_concurrency: int = Field(default=2, ge=1)
    ffmpeg_concurrency: int = Field(default=2, ge=1)
    #: Netscape cookies file for sites that need a login (e.g. age-restricted YouTube).
    ytdlp_cookies_file: Path | None = None

    vad_model_path: Path = Path("models/silero_vad.onnx")
    vad_concurrency: int = Field(default=2, ge=1)

    #: faster_whisper runs locally in the worker; openai_compat calls STT_BASE_URL
    #: (OpenAI, Groq, or any whisper server with verbose_json word timestamps).
    stt_provider: Literal["faster_whisper", "openai_compat"] = "faster_whisper"
    #: Whisper size for faster_whisper (tiny/base/small/medium/large-v3), or the API model.
    stt_model: str = "small"
    stt_base_url: str | None = None
    stt_api_key: str | None = None
    #: Chunks transcribed at once: ~1 for local CPU, higher for cloud APIs.
    stt_concurrency: int = Field(default=1, ge=1)
    #: ISO code like "en"; unset = auto-detect per chunk.
    stt_language: str | None = None

    #: openai_compat covers Ollama (http://host.docker.internal:11434/v1), OpenAI, Groq,
    #: OpenRouter, LM Studio, vLLM; anthropic is the native Claude API.
    llm_provider: Literal["openai_compat", "anthropic"] = "openai_compat"
    llm_base_url: str | None = "http://host.docker.internal:11434/v1"
    llm_model: str = "qwen2.5:14b"
    llm_api_key: str | None = None
    #: Requests in flight at once: 1-2 for local Ollama, ~4 for cloud APIs.
    llm_concurrency: int = Field(default=2, ge=1)
    llm_timeout_seconds: float = Field(default=300, gt=0)
    #: Transcript minutes per LLM request. Raise it only with a larger context window
    #: (for Ollama, OLLAMA_CONTEXT_LENGTH); the default fits a 4k context.
    llm_window_seconds: float = Field(default=300, ge=60)

    #: The Montserrat files the preview uses; libass renders captions with the same ones.
    fonts_dir: Path = Path("../assets/fonts")
    #: Built-in CC0 music library (manifest.json + files from `make music`).
    default_music_dir: Path = Path("../assets/music")

    clip_min_seconds: float = Field(default=15, gt=0)
    clip_max_seconds: float = Field(default=60, gt=0)
    clip_max_count: int = Field(default=10, ge=1)

    @model_validator(mode="after")
    def _check_providers(self) -> "Settings":
        if self.stt_provider == "openai_compat" and not self.stt_base_url:
            raise ValueError("STT_BASE_URL is required when STT_PROVIDER=openai_compat")
        if self.llm_provider == "openai_compat" and not self.llm_base_url:
            raise ValueError("LLM_BASE_URL is required when LLM_PROVIDER=openai_compat")
        if self.llm_provider == "anthropic" and not self.llm_api_key:
            raise ValueError("LLM_API_KEY is required when LLM_PROVIDER=anthropic")
        if self.clip_min_seconds >= self.clip_max_seconds:
            raise ValueError("CLIP_MIN_SECONDS must be less than CLIP_MAX_SECONDS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
