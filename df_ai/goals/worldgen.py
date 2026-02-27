"""World generation goal plan and helpers."""

from __future__ import annotations

from typing import Any, Dict, List

# Classic DF 0.47.05 startup screen sequence:
#   1) OpenAL dialog  -> Return to dismiss
#   2) Bay12 splash   -> Return to skip
#   3) Welcome/alpha  -> Escape to continue
#   4) Title menu     -> appears with "Create a New World!" already first option
#                        but ESC from welcome goes directly to worldgen params
#   5) Worldgen params -> y to accept defaults and start generation
#   6) Poll until complete
#   7) Accept world   -> Return
WORLDGEN_PLAN: List[Dict[str, Any]] = [
    {"name": "dismiss-openal-dialog", "type": "keystroke", "key": "Return",
     "expect": "ok", "delay": 2.0},
    {"name": "skip-splash", "type": "keystroke", "key": "Return",
     "expect": "ok", "delay": 2.0},
    {"name": "skip-welcome", "type": "keystroke", "key": "Escape",
     "expect": "ok", "delay": 2.0},
    {"name": "start-worldgen", "type": "keystroke", "key": "y",
     "expect": "ok", "delay": 1.0},
    {"name": "poll-worldgen", "type": "dfhack", "command": "ls",
     "expect": "screen:worldgen_complete", "poll_seconds": 600,
     "poll_interval": 5},
    {"name": "accept-world", "type": "keystroke", "key": "Return",
     "expect": "ok", "delay": 5.0},
    {"name": "verify-world-exists", "type": "dfhack", "command": "ls",
     "expect": "screen:has_world"},
]


def plan_worldgen() -> List[Dict[str, Any]]:
    return [dict(step) for step in WORLDGEN_PLAN]
