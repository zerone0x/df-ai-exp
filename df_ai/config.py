"""Configuration helpers for the DF automation stack."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CONFIG_DIR = _PROJECT_ROOT / "config"
_DEFAULT_LOG_DIR = _PROJECT_ROOT / "logs"


def get_project_root() -> Path:
    """Return the repository root."""
    return _PROJECT_ROOT


def _from_env(var_name: str) -> Optional[Path]:
    value = os.environ.get(var_name)
    if not value:
        return None
    candidate = Path(value).expanduser()
    if not candidate.exists():
        raise FileNotFoundError(f"Configured path for {var_name} does not exist: {candidate}")
    return candidate


def _from_config_file() -> Optional[Path]:
    config_file = _CONFIG_DIR / "df_root.txt"
    if not config_file.exists():
        return None
    text = config_file.read_text().strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    if not candidate.exists():
        raise FileNotFoundError(f"Path in {config_file} does not exist: {candidate}")
    return candidate


def get_df_root() -> Path:
    """Resolve the DF install root.

    Resolution order:
    1. Environment variable ``DF_ROOT``
    2. ``config/df_root.txt`` (ignored by git)

    Returns:
        Path: The resolved DF root path.

    Raises:
        RuntimeError: If no configuration is available.
        FileNotFoundError: If a configured path does not exist.
    """

    env_path = _from_env("DF_ROOT")
    if env_path is not None:
        return env_path

    file_path = _from_config_file()
    if file_path is not None:
        return file_path

    raise RuntimeError(
        "DF root is not configured. Set DF_ROOT or create config/df_root.txt with the path."
    )


def get_logs_dir() -> Path:
    """Return the directory for runtime logs (created if missing)."""
    log_path = os.environ.get("DF_AI_LOG_DIR")
    if log_path:
        path = Path(log_path).expanduser()
        path.mkdir(parents=True, exist_ok=True)
        return path

    _DEFAULT_LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _DEFAULT_LOG_DIR
