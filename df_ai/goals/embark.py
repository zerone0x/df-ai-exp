"""Embark goal plan — placeholder for Classic DF key sequence.

TODO: Sober is mapping the exact key sequence on her Mac.
This will be filled in once the embark flow is confirmed.

Classic DF 0.47.05 embark flow (approximate):
  1) From title menu, arrow to "Start Playing" → Enter
  2) Select "Dwarf Fortress" mode → Enter
  3) Embark screen appears with world map
  4) Select embark location (or accept default) → e to embark
  5) Prepare carefully screen (optional) → e to embark
  6) Wait for fortress to load

DF 50+ (Steam) Classic mode may differ — keys TBD.
"""

from __future__ import annotations

from typing import Any, Dict, List


# Placeholder — will be filled by local testing
EMBARK_PLAN: List[Dict[str, Any]] = [
    # Step sequence TBD by local Mac testing
    {"name": "placeholder", "type": "keystroke", "key": "Return",
     "expect": "ok", "delay": 1.0,
     "note": "TODO: replace with actual embark key sequence"},
]


def plan_embark() -> List[Dict[str, Any]]:
    return [dict(step) for step in EMBARK_PLAN]
