"""Local configuration. Secrets are read through os.getenv, never returned to UI."""

from __future__ import annotations

import os
import math
from pathlib import Path

from dotenv import dotenv_values

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
_file_values: dict[str, str] = {}
_ENV_KEYS = (
    "DEMO_MODE", "AI_PROVIDER", "AI_TIMEOUT_SECONDS", "OPENAI_API_KEY",
    "OPENAI_MODEL", "NVIDIA_API_KEY", "NVIDIA_MODEL",
)


def reload_env() -> None:
    """Refresh file-owned values while preserving explicit process environment."""
    values = dotenv_values(ENV_PATH)
    for key in _ENV_KEYS:
        old = _file_values.get(key)
        if key in os.environ and (old is None or os.environ[key] != old):
            continue
        if key in values:
            value = values[key] or ""
            os.environ[key] = value
            _file_values[key] = value
        elif key in _file_values:
            os.environ.pop(key, None)
            _file_values.pop(key, None)


def get_settings() -> dict:
    reload_env()
    provider = os.getenv("AI_PROVIDER", "auto").strip().lower()
    if provider not in {"auto", "openai", "nvidia"}:
        provider = "auto"
    try:
        timeout = float(os.getenv("AI_TIMEOUT_SECONDS", "20"))
        timeout = min(60.0, max(3.0, timeout)) if math.isfinite(timeout) else 20.0
    except ValueError:
        timeout = 20.0
    return {
        "demo": os.getenv("DEMO_MODE", "true").strip().lower() in {"1", "true", "yes", "on", "да"},
        "provider": provider,
        "timeout": timeout,
        "openai_model": os.getenv("OPENAI_MODEL", "").strip() or "gpt-4o-mini",
        "nvidia_model": os.getenv("NVIDIA_MODEL", "").strip() or "nvidia/nemotron-3-super-120b-a12b",
        "openai_ready": bool(os.getenv("OPENAI_API_KEY", "").strip()),
        "nvidia_ready": bool(os.getenv("NVIDIA_API_KEY", "").strip()),
    }
