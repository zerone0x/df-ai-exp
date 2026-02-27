"""Runtime state extraction from DF/DFHack host logs."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict


def extract_runtime_state(log_path: Path) -> Dict[str, Any]:
    if not log_path.exists():
        return {
            "dfhack_ready": False,
            "dfhack_prompt_count": 0,
            "has_floating_point_exception": False,
            "has_audio_errors": False,
            "tail": [],
        }

    text = log_path.read_text(errors="ignore")
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    return {
        "dfhack_ready": "DFHack is ready. Have a nice day!" in text,
        "dfhack_prompt_count": len(re.findall(r"\[DFHack\]#", text)),
        "has_floating_point_exception": "Floating point exception" in text,
        "has_audio_errors": "ALSA lib" in text,
        "tail": lines[-20:],
    }
