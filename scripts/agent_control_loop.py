#!/usr/bin/env python3
"""Run a minimal action loop against DFHack (non-interactive channel).

Loop:
  state capture -> choose action -> execute -> append jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path

import sys

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from df_ai.config import get_df_root, get_logs_dir
from df_ai.executor import execute_action
from df_ai.llm_planner import choose_action_llm
from df_ai.policy import choose_action
from df_ai.state import extract_runtime_state


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def start_host(df_root: Path, log_path: Path) -> subprocess.Popen:
    cmd = [
        "xvfb-run",
        "-a",
        "-s",
        "-screen 0 1280x720x24",
        str(df_root / "dfhack"),
    ]
    fp = log_path.open("w")
    proc = subprocess.Popen(cmd, stdout=fp, stderr=subprocess.STDOUT, text=True)
    return proc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--steps", type=int, default=20, help="Loop iterations")
    parser.add_argument("--warmup", type=float, default=8.0, help="Seconds to wait after host start")
    parser.add_argument("--interval", type=float, default=0.5, help="Seconds between steps")
    parser.add_argument(
        "--planner",
        type=str,
        choices=["rule", "llm"],
        default="rule",
        help="Planner policy to use: rule (default) or llm",
    )
    args = parser.parse_args()

    df_root = get_df_root()
    logs_dir = get_logs_dir()
    logs_dir.mkdir(parents=True, exist_ok=True)

    ts = int(time.time())
    host_log = logs_dir / f"host_{ts}.log"
    loop_log = logs_dir / f"agent_loop_{ts}.jsonl"

    print(f"[{_now()}] starting host: {df_root / 'dfhack'}")
    host = start_host(df_root, host_log)

    try:
        time.sleep(args.warmup)

        last_ok = True
        successful_commands = 0

        with loop_log.open("w", encoding="utf-8") as out:
            for step in range(args.steps):
                runtime_state = extract_runtime_state(host_log)
                runtime_state["dfhack_ready"] = bool(
                    runtime_state.get("dfhack_ready") or successful_commands > 0
                )
                runtime_state["last_ok"] = last_ok
                runtime_state["successful_commands"] = successful_commands

                if args.planner == "llm":
                    action = choose_action_llm(runtime_state, step)
                else:
                    action = choose_action(runtime_state, step)
                result = execute_action(action)

                if result["ok"]:
                    successful_commands += 1

                event = {
                    "ts": _now(),
                    "step": step,
                    "state_in": {
                        "dfhack_ready": runtime_state.get("dfhack_ready"),
                        "dfhack_prompt_count": runtime_state.get("dfhack_prompt_count"),
                        "has_floating_point_exception": runtime_state.get("has_floating_point_exception"),
                        "last_ok": runtime_state.get("last_ok"),
                        "successful_commands": successful_commands,
                    },
                    "result": result,
                    "tail": runtime_state.get("tail", [])[-5:],
                }
                out.write(json.dumps(event, ensure_ascii=False) + "\n")
                out.flush()

                last_ok = result["ok"]

                print(
                    f"step={step:02d} ready={runtime_state.get('dfhack_ready')} "
                    f"fpe={runtime_state.get('has_floating_point_exception')} "
                    f"ok_count={successful_commands} action={result['action']['display']:<20} "
                    f"ok={result['ok']} rc={result['returncode']} t={result['duration']:.2f}s"
                )
                time.sleep(args.interval)

        print(f"[{_now()}] done. loop_log={loop_log}")
        print(f"[{_now()}] host_log={host_log}")

    finally:
        host.terminate()
        try:
            host.wait(timeout=5)
        except subprocess.TimeoutExpired:
            host.kill()


if __name__ == "__main__":
    main()
