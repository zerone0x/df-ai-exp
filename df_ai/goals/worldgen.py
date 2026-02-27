"""World generation goal plan and helpers."""

from __future__ import annotations

from typing import Any, Dict, List

# Keystroke sequence from title screen using defaults:
# 1) Enter title menu
# 2) Move to "Create New World"
# 3) Confirm defaults and start generation
# 4) Wait/poll until done
WORLDGEN_PLAN: List[Dict[str, Any]] = [
    {"name": "open-title-menu", "type": "keystroke", "key": "Return", "expect": "ok"},
    {"name": "select-create-new-world", "type": "keystroke", "key": "Down", "expect": "ok"},
    {"name": "confirm-create-new-world", "type": "keystroke", "key": "Return", "expect": "ok"},
    {"name": "accept-world-defaults", "type": "keystroke", "key": "Return", "expect": "ok"},
    {"name": "accept-parameters", "type": "keystroke", "key": "Return", "expect": "ok"},
    {"name": "poll-worldgen", "type": "dfhack", "command": "lua print('worldgen-poll')", "expect": "screen:worldgen_complete", "poll_seconds": 300, "poll_interval": 2},
    {"name": "verify-world-exists", "type": "dfhack", "command": "lua print(df.global.gamemode)", "expect": "screen:has_world"},
]


def plan_worldgen() -> List[Dict[str, Any]]:
    return [dict(step) for step in WORLDGEN_PLAN]
