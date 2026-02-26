#!/usr/bin/env python3
"""Run a single automated DF session and extract a structured state snapshot."""

import json
import subprocess
import sys
import time
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from df_ai.config import get_df_root, get_logs_dir  # noqa: E402

AUTO_START = PROJECT_ROOT / "scripts" / "auto_start.exp"
STATE_EXTRACTOR = PROJECT_ROOT / "scripts" / "state_extractor.py"

DF_ROOT = get_df_root()
LOGDIR = get_logs_dir()
LOGDIR.mkdir(parents=True, exist_ok=True)


def run_once(seconds: int = 25) -> Path:
    """Launch DF/DFHack through the expect harness."""
    ts = int(time.time())
    log = LOGDIR / f"df_session_{ts}.log"
    cmd = [str(AUTO_START), str(log), str(DF_ROOT)]
    print("Running:", " ".join(cmd))
    try:
        subprocess.run(cmd, timeout=seconds, check=False)
    except subprocess.TimeoutExpired:
        print("Timed out (continuing).")
    return log


def extract(log: Path) -> Path:
    cmd = ["python3", str(STATE_EXTRACTOR), str(log)]
    res = subprocess.check_output(cmd, text=True).strip()
    return Path(res)


def main() -> None:
    log = run_once()
    json_path = extract(log)
    state = json.loads(json_path.read_text())

    print(f"Log: {log}")
    print(f"State: {json_path}")
    print("--- summary ---")
    print("dfhack_ready:", state["dfhack_ready"])
    print("prompt_count:", state["dfhack_prompt_count"])
    print("floating_point_exception:", state["has_floating_point_exception"])
    print("audio_errors:", state["has_audio_errors"])
    print("tail_last_5:")
    for line in state["tail"][-5:]:
        print("  ", line)


if __name__ == "__main__":
    main()
