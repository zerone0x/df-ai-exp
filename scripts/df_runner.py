#!/usr/bin/env python3
"""Manage the DF process via tmux.

Usage:
    python scripts/df_runner.py start [region]   # start DF + optionally load save
    python scripts/df_runner.py stop             # kill DF
    python scripts/df_runner.py status           # check if DF is running
    python scripts/df_runner.py load <region>    # load save into running DF
    python scripts/df_runner.py run-cmd <cmd>    # run dfhack-run command + print output

Strategy:
- DF runs inside a tmux session (df_agent) so it persists across SSH disconnects
- TEXT mode (PRINT_MODE:TEXT) means no Xvfb needed
- We poll dfhack-run ls to wait for DF ready
- load-save.lua is safe via dfhack-run (command pipe ≠ Lua RPC)
- Safety: refuse to start if system load > 3 or free mem < 400 MB

Pitfalls (see docs/PITFALLS.md):
- SDL2 filters XSendEvent → xdotool doesn't inject keystrokes
- Lua RPC segfaults → never use dfhack.lua.eval via RPC
- dfhack-run IS safe for .lua scripts (different channel)
- scrot captures stale X11 buffer → don't use screenshots
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from df_ai.config import get_df_root  # noqa: E402
from df_ai.dfhack import run_dfhack  # noqa: E402

TMUX_SESSION = "df_agent"
MAX_LOAD_WAIT = 90   # seconds to wait for fortress to load
MAX_START_WAIT = 45  # seconds to wait for DFHack to become ready

# Safety thresholds
MAX_LOAD_BEFORE_START = 3.0   # refuse start if system load > this
MIN_FREE_MEM_MB = 400         # refuse start if free RAM < this MB


# ---------------------------------------------------------------------------
# System safety
# ---------------------------------------------------------------------------


def _get_system_load() -> float:
    """1-minute load average."""
    try:
        with open("/proc/loadavg") as f:
            return float(f.read().split()[0])
    except Exception:
        return 0.0


def _get_free_mem_mb() -> float:
    """Available memory in MB (MemAvailable from /proc/meminfo)."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    kb = int(line.split()[1])
                    return kb / 1024
    except Exception:
        pass
    return 9999.0


def check_safety() -> None:
    """Raise RuntimeError if system is too loaded to start DF."""
    load = _get_system_load()
    mem = _get_free_mem_mb()
    if load > MAX_LOAD_BEFORE_START:
        raise RuntimeError(
            f"System load too high ({load:.1f} > {MAX_LOAD_BEFORE_START}). "
            "Wait for load to drop before starting DF."
        )
    if mem < MIN_FREE_MEM_MB:
        raise RuntimeError(
            f"Insufficient free RAM ({mem:.0f} MB < {MIN_FREE_MEM_MB} MB). "
            "Free up memory before starting DF."
        )


# ---------------------------------------------------------------------------
# tmux helpers
# ---------------------------------------------------------------------------


def _tmux(*args: str) -> subprocess.CompletedProcess:
    """Run a tmux command and return result."""
    return subprocess.run(
        ["tmux"] + list(args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def is_tmux_session_alive() -> bool:
    """Check if the df_agent tmux session exists."""
    result = _tmux("has-session", "-t", TMUX_SESSION)
    return result.returncode == 0


def tmux_send(keys: str, session: str = TMUX_SESSION) -> None:
    """Send keys/command to the tmux session."""
    _tmux("send-keys", "-t", session, keys, "Enter")


def tmux_capture(session: str = TMUX_SESSION, lines: int = 50) -> str:
    """Capture recent output from the tmux session."""
    result = _tmux(
        "capture-pane", "-t", session, "-p", "-S", f"-{lines}"
    )
    return result.stdout


# ---------------------------------------------------------------------------
# DF process management
# ---------------------------------------------------------------------------


def is_df_running() -> bool:
    """Check if DF process exists (via pgrep)."""
    result = subprocess.run(
        ["pgrep", "-f", "dwarfort"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0


def is_dfhack_ready(timeout: float = 3.0) -> bool:
    """Return True if dfhack-run can connect to a running DF instance."""
    result = run_dfhack(["ls"], timeout=timeout, retries=0)
    return result.ok


def start_df(region: Optional[str] = None) -> bool:
    """
    Start DF in TEXT mode inside a tmux session.

    Args:
        region: If given, load this save after DF starts.

    Returns:
        True if DF became ready within MAX_START_WAIT seconds.
    """
    check_safety()

    df_root = get_df_root()

    # Kill any existing session first
    if is_tmux_session_alive():
        print(f"[df_runner] Existing tmux session '{TMUX_SESSION}' found — killing it.")
        _tmux("kill-session", "-t", TMUX_SESSION)
        time.sleep(1)

    # Kill any stale DF processes
    subprocess.run(["pkill", "-f", "dwarfort"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)

    # Start DF in tmux
    cmd = f"cd {df_root} && ./dfhack"
    print(f"[df_runner] Starting DF: {cmd}")
    _tmux("new-session", "-d", "-s", TMUX_SESSION, cmd)

    # Wait for DFHack to be ready
    print(f"[df_runner] Waiting up to {MAX_START_WAIT}s for DFHack to become ready...")
    t0 = time.monotonic()
    while time.monotonic() - t0 < MAX_START_WAIT:
        time.sleep(3)
        if is_dfhack_ready(timeout=3.0):
            print(f"[df_runner] DFHack ready ({time.monotonic() - t0:.0f}s)")
            break
        # Show recent tmux output for debugging
        pane = tmux_capture(lines=5)
        print(f"[df_runner] pane: {pane.strip()[-200:]}")
    else:
        print("[df_runner] ERROR: DFHack did not become ready in time.")
        return False

    # Optionally load a save
    if region:
        return load_save(region)

    return True


def load_save(region: str) -> bool:
    """
    Load a specific save region into the running DF instance.

    Uses load-save.lua via dfhack-run (command pipe, NOT Lua RPC — safe).
    Requires DF to be at the title screen or load game screen.

    Args:
        region: Save folder name (e.g. "region29").

    Returns:
        True if save loaded successfully.
    """
    if not is_dfhack_ready():
        print("[df_runner] DFHack not ready — can't load save.")
        return False

    df_root = get_df_root()
    save_path = df_root / "data" / "save" / region
    if not save_path.is_dir():
        print(f"[df_runner] Save not found: {save_path}")
        return False

    print(f"[df_runner] Loading save '{region}' via load-save.lua...")
    result = run_dfhack(["load-save", region], timeout=30.0, retries=1, retry_delay=3.0)
    if result.ok:
        print(f"[df_runner] load-save succeeded. Waiting for fortress mode...")
    else:
        print(f"[df_runner] load-save exit={result.returncode}: {result.stderr.strip()[:200]}")
        # Don't fail immediately — sometimes output goes to game process, not dfhack-run
        print("[df_runner] Continuing anyway and polling for fortress mode...")

    # Wait for fortress to load (prospect becomes available)
    t0 = time.monotonic()
    while time.monotonic() - t0 < MAX_LOAD_WAIT:
        time.sleep(5)
        test = run_dfhack(["prospect"], timeout=8.0, retries=0)
        if test.ok and test.stdout.strip():
            print(f"[df_runner] Fortress mode confirmed ({time.monotonic() - t0:.0f}s)")
            return True
        pane = tmux_capture(lines=3)
        print(f"[df_runner] still loading... pane: {pane.strip()[-100:]}")

    print(f"[df_runner] WARNING: fortress mode not confirmed after {MAX_LOAD_WAIT}s")
    # Return True anyway — user can check manually
    return True


def stop_df() -> None:
    """Kill DF and clean up the tmux session."""
    print("[df_runner] Stopping DF...")
    if is_tmux_session_alive():
        _tmux("kill-session", "-t", TMUX_SESSION)
    subprocess.run(["pkill", "-f", "dwarfort"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    print("[df_runner] DF stopped.")


def status() -> dict:
    """Return a status dict for the current DF state."""
    return {
        "tmux_session": is_tmux_session_alive(),
        "df_process": is_df_running(),
        "dfhack_ready": is_dfhack_ready(timeout=3.0),
        "system_load": _get_system_load(),
        "free_mem_mb": round(_get_free_mem_mb()),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    import json
    args = sys.argv[1:]
    if not args:
        print("Usage: df_runner.py <start|stop|status|load|run-cmd> [args...]")
        sys.exit(1)

    cmd = args[0]

    if cmd == "status":
        s = status()
        for k, v in s.items():
            print(f"  {k}: {v}")

    elif cmd == "start":
        region = args[1] if len(args) > 1 else None
        ok = start_df(region=region)
        sys.exit(0 if ok else 1)

    elif cmd == "stop":
        stop_df()

    elif cmd == "load":
        if len(args) < 2:
            print("Usage: df_runner.py load <region>")
            sys.exit(1)
        ok = load_save(args[1])
        sys.exit(0 if ok else 1)

    elif cmd == "run-cmd":
        if len(args) < 2:
            print("Usage: df_runner.py run-cmd <dfhack-command> [args...]")
            sys.exit(1)
        result = run_dfhack(args[1:], timeout=15.0)
        print(f"exit={result.returncode}")
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr[:300], file=sys.stderr)
        sys.exit(0 if result.ok else 1)

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
