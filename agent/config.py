"""Agent configuration using Pydantic BaseSettings.

Centralises every tuneable parameter for the Pipecat voice pipeline into a
single validated settings object.  Values are loaded (in priority order) from:

1. Explicit constructor kwargs
2. Environment variables
3. The project-root ``.env`` file
4. Field defaults defined below

Usage::

    from agent.config import settings
    print(settings.ollama_model)  # "gpt-oss:20b-cloud"
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings
from loguru import logger


class AgentSettings(BaseSettings):
    """Configuration for the Maya voice-agent pipeline.

    Every field maps 1-to-1 to an environment variable whose name is the
    upper-cased version of the field (e.g. ``ollama_base_url`` -> ``OLLAMA_BASE_URL``).
    """

    # ── Ollama LLM ──────────────────────────────────────────────────────
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL for the Ollama API server.",
    )
    ollama_model: str = Field(
        default="gpt-oss:20b-cloud",
        description="Ollama model tag. MUST be gpt-oss:20b-cloud.",
    )

    # ── API Backend ─────────────────────────────────────────────────────
    api_base_url: str = Field(
        default="http://localhost:8000",
        description="FastAPI backend base URL used by tool handlers.",
    )

    # ── Agent Server ────────────────────────────────────────────────────
    agent_host: str = Field(
        default="0.0.0.0",
        description="Bind host for the agent's FastAPI/Uvicorn server.",
    )
    agent_port: int = Field(
        default=7860,
        description="Port for the agent's FastAPI/Uvicorn server.",
    )

    # ── STT (Faster-Whisper) ────────────────────────────────────────────
    whisper_model: str = Field(
        default="base.en",
        description="Faster-Whisper model size. Use base.en for CPU.",
    )
    whisper_device: str = Field(
        default="cpu",
        description="Inference device. MUST be 'cpu' (no GPU).",
    )
    whisper_compute_type: str = Field(
        default="int8",
        description="CTranslate2 quantisation. int8 for CPU efficiency.",
    )
    whisper_language: str = Field(
        default="en",
        description="Language code for speech recognition.",
    )

    # ── TTS (Kokoro 82M ONNX) ──────────────────────────────────────────
    kokoro_voice: str = Field(
        default="af_bella",
        description="Kokoro voice preset name.",
    )
    kokoro_speed: float = Field(
        default=1.0,
        ge=0.5,
        le=2.0,
        description="TTS speaking rate multiplier.",
    )

    # ── VAD (Silero) ────────────────────────────────────────────────────
    vad_stop_secs: float = Field(
        default=0.5,
        ge=0.1,
        le=3.0,
        description="Seconds of silence before speech is considered ended.",
    )
    vad_start_secs: float = Field(
        default=0.2,
        ge=0.05,
        le=1.0,
        description="Minimum seconds of audio before speech is confirmed.",
    )
    vad_confidence: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Silero VAD confidence threshold.",
    )
    vad_min_volume: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Minimum RMS volume to consider as speech.",
    )

    # ── LangFuse Observability (optional) ───────────────────────────────
    langfuse_public_key: str = Field(
        default="",
        description="LangFuse public key. Leave empty to disable tracing.",
    )
    langfuse_secret_key: str = Field(
        default="",
        description="LangFuse secret key.",
    )
    langfuse_host: str = Field(
        default="http://localhost:3001",
        description="LangFuse server URL.",
    )

    # ── Conversation Behaviour ──────────────────────────────────────────
    idle_timeout_secs: int = Field(
        default=10,
        ge=5,
        le=120,
        description="Seconds of silence before prompting 'Are you still there?'.",
    )
    max_tool_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Number of retries for failed tool calls before giving up.",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


def _load_settings() -> AgentSettings:
    """Instantiate and validate agent settings, logging the result."""
    try:
        _settings = AgentSettings()
        logger.info(
            "Agent settings loaded | model={} | api={} | whisper={} | voice={}",
            _settings.ollama_model,
            _settings.api_base_url,
            _settings.whisper_model,
            _settings.kokoro_voice,
        )
        return _settings
    except Exception as exc:
        logger.error("Failed to load agent settings: {}", exc)
        raise


settings: AgentSettings = _load_settings()
