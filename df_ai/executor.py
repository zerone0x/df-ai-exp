"""Executor layer: action -> command/keystroke execution."""

from __future__ import annotations

from typing import Any, Dict

from .dfhack import CommandResult, run_dfhack
from .keystroke import send_key
from .policy import Action


def execute_action(action: Action, *, timeout: float = 10.0) -> Dict[str, Any]:
    """Execute an Action and return a structured result."""

    if action.type == "keystroke":
        key = action.argv[0] if action.argv else ""
        ok = bool(key) and send_key(key)
        return {
            "action": action.to_dict(),
            "ok": ok,
            "returncode": 0 if ok else 1,
            "stdout": "",
            "stderr": "" if ok else "failed to send key (window not found or xdotool error)",
            "attempts": 1,
            "duration": 0.0,
        }

    if action.type != "dfhack":
        return {
            "action": action.to_dict(),
            "ok": False,
            "returncode": 1,
            "stdout": "",
            "stderr": f"unknown action type: {action.type}",
            "attempts": 1,
            "duration": 0.0,
        }

    result: CommandResult = run_dfhack(
        action.argv,
        timeout=timeout,
        retries=1,
        retry_delay=0.8,
        check=False,
    )

    return {
        "action": action.to_dict(),
        "ok": result.ok,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "attempts": result.attempts,
        "duration": result.duration,
    }
