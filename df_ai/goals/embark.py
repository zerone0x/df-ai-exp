"""Embark goal plan — navigate from title screen to fortress mode."""

from __future__ import annotations

from typing import Any, Dict, List

# Classic DF 0.47.05 embark sequence (assumes a world already exists):
#   Title screen  -> "Start Playing" is highlighted
#   1) Enter      -> select "Start Playing"
#   2) Enter      -> select "Dwarf Fortress" (already highlighted)
#                    triggers world loading ("Loading civilized populations...")
#   3) e          -> "Embark!" at the default map location
#   4) Enter      -> "Play Now!" with default supplies
#   5) Enter      -> dismiss "A Dwarven Outpost" arrival text
#   6) Now in fortress mode, *PAUSED*
EMBARK_PLAN: List[Dict[str, Any]] = [
    {"name": "select-start-playing", "type": "keystroke", "key": "Return",
     "expect": "ok", "delay": 2.0},
    {"name": "select-dwarf-fortress", "type": "keystroke", "key": "Return",
     "expect": "ok", "delay": 15.0},
    {"name": "embark-default-location", "type": "keystroke", "key": "e",
     "expect": "ok", "delay": 2.0},
    {"name": "play-now-defaults", "type": "keystroke", "key": "Return",
     "expect": "ok", "delay": 3.0},
    {"name": "dismiss-intro-text", "type": "keystroke", "key": "Return",
     "expect": "ok", "delay": 3.0},
    {"name": "verify-fortress-mode", "type": "dfhack", "command": "ls",
     "expect": "ok"},
]


def plan_embark() -> List[Dict[str, Any]]:
    return [dict(step) for step in EMBARK_PLAN]
