"""Executor layer: action -> dfhack-run command execution."""

from __future__ import annotations

from typing import Any, Dict

from .dfhack import CommandResult, run_dfhack
from .policy import Action


def execute_action(action: Action, *, timeout: float = 10.0) -> Dict[str, Any]:
    """Execute an Action through dfhack-run and return a structured result."""

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
