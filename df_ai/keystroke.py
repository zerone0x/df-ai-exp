"""Keystroke helpers for interacting with the DF UI window via xdotool."""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import Iterable, Optional


def _xdotool_exists() -> bool:
    return shutil.which("xdotool") is not None


def find_df_window() -> Optional[str]:
    """Return a likely DF window id, or None when unavailable."""

    if not _xdotool_exists():
        return None

    # Try common DF/SDL window name patterns in priority order.
    patterns = [
        "Dwarf Fortress",
        "dfhack",
        "SDL_app",
    ]

    for pattern in patterns:
        try:
            completed = subprocess.run(
                ["xdotool", "search", "--name", pattern],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
            )
        except OSError:
            return None

        if completed.returncode == 0 and completed.stdout.strip():
            return completed.stdout.strip().splitlines()[-1]

    return None


def send_key(key: str, window_id: str | None = None, delay: float = 0.3) -> bool:
    """Send one key to the DF window. Returns True if sent."""

    if not _xdotool_exists():
        return False

    target = window_id or find_df_window()
    if not target:
        return False

    try:
        activate = subprocess.run(
            ["xdotool", "windowactivate", "--sync", target],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if activate.returncode != 0:
            return False

        press = subprocess.run(
            ["xdotool", "key", "--window", target, key],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if press.returncode != 0:
            return False
    except OSError:
        return False

    if delay > 0:
        time.sleep(delay)
    return True


def send_keys(keys: Iterable[str], delay: float = 0.3) -> bool:
    """Send a sequence of keys to DF. Returns False on first failure."""

    target = find_df_window()
    if not target:
        return False

    for key in keys:
        if not send_key(key, window_id=target, delay=delay):
            return False
    return True
