#!/usr/bin/env python3
"""Goal-oriented runner with expectation checks and safe fallback."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any
import sys

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from df_ai.config import get_df_root, get_logs_dir
from df_ai.executor import execute_action
from df_ai.policy import Action
from df_ai.screen import get_world_info, is_worldgen_complete
from df_ai.state import extract_runtime_state
from df_ai.verifier import verify_expectation
from df_ai.planner import plan_for_goal, load_catalog


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def start_host(df_root: Path, log_path: Path) -> subprocess.Popen:
    cmd = ["xvfb-run", "-a", "-s", "-screen 0 1280x720x24", str(df_root / "dfhack")]
    fp = log_path.open("w")
    return subprocess.Popen(cmd, stdout=fp, stderr=subprocess.STDOUT, text=True)


def default_plan() -> list[dict[str, Any]]:
    return [
        {"name": "bootstrap", "command": "ls", "expect": "ok"},
        {"name": "taxonomy", "command": "tags", "expect": "contains:fort"},
        {"name": "discover-fort", "command": "ls fort", "expect": "contains:fort"},
        {"name": "quickfort-help", "command": "help quickfort", "expect": "contains:quickfort"},
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, help="optional JSON plan file")
    parser.add_argument("--goal", type=str, default="quickfort_probe", help="named goal plan")
    parser.add_argument("--warmup", type=float, default=8.0)
    parser.add_argument("--policy", choices=["rule", "llm"], default="rule",
                        help="Use LLM planner for dynamic goal execution")
    parser.add_argument("--max-steps", type=int, default=30,
                        help="Max steps for LLM-driven execution")
    args = parser.parse_args()

    catalog = load_catalog()

    if args.plan:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    else:
        plan = plan_for_goal(args.goal, catalog)

    df_root = get_df_root()
    logs_dir = get_logs_dir()
    ts = int(time.time())
    host_log = logs_dir / f"goal_host_{ts}.log"
    run_log = logs_dir / f"goal_run_{ts}.jsonl"

    host = start_host(df_root, host_log)
    print(f"[{_now()}] host started")

    try:
        time.sleep(args.warmup)

        # LLM-driven dynamic execution
        if args.policy == "llm":
            from df_ai.policy import choose_action_llm
            print(f"[{_now()}] LLM mode goal={args.goal} max_steps={args.max_steps}")
            action_history: list[dict] = []
            with run_log.open("w", encoding="utf-8") as out:
                for step in range(args.max_steps):
                    runtime_state = extract_runtime_state(host_log)
                    action = choose_action_llm(
                        runtime_state, step,
                        goal=f"Goal: {args.goal}",
                        catalog=catalog,
                        history=action_history,
                    )
                    if action.type == "done":
                        print(f"[{_now()}] LLM done: {action.reason}")
                        event = {"ts": _now(), "step": step, "done": True, "reason": action.reason}
                        out.write(json.dumps(event, ensure_ascii=False) + "\n")
                        break
                    result = execute_action(action)
                    action_history.append({
                        "step": step, "action": result["action"],
                        "ok": result["ok"], "returncode": result["returncode"],
                    })
                    if len(action_history) > 15:
                        action_history = action_history[-10:]
                    event = {"ts": _now(), "step": step, "result": result}
                    out.write(json.dumps(event, ensure_ascii=False) + "\n")
                    out.flush()
                    shown = result["action"].get("display", "?")
                    print(f"step={step:02d} action={shown:<22} ok={result['ok']} rc={result['returncode']}")
            print(f"[{_now()}] done run_log={run_log}")
            return

        print(f"[{_now()}] goal={args.goal} steps={len(plan)}")
        with run_log.open("w", encoding="utf-8") as out:
            for step, item in enumerate(plan):
                runtime_state = extract_runtime_state(host_log)
                action_type = item.get("type", "dfhack")
                if action_type == "keystroke":
                    key = str(item.get("key", ""))
                    argv = [key] if key else []
                else:
                    argv = str(item.get("command", "")).split()
                action = Action(
                    name=item.get("name", f"step-{step}"),
                    argv=argv,
                    reason="goal plan",
                    type=action_type,
                )
                result = execute_action(action)

                expect = item.get("expect")
                if expect == "screen:worldgen_complete":
                    deadline = time.monotonic() + float(item.get("poll_seconds", 240))
                    interval = float(item.get("poll_interval", 2))
                    ok = False
                    while time.monotonic() < deadline:
                        if is_worldgen_complete():
                            ok = True
                            break
                        time.sleep(interval)
                    note = "worldgen completed" if ok else "worldgen did not complete before timeout"
                elif expect == "screen:has_world":
                    info = get_world_info()
                    ok = info.get("region_count", 0) > 0
                    note = f"region_count={info.get('region_count', 0)}"
                else:
                    ok, note = verify_expectation(expect, result, runtime_state)

                event = {
                    "ts": _now(),
                    "step": step,
                    "plan": item,
                    "result": result,
                    "verify_ok": ok,
                    "verify_note": note,
                }
                out.write(json.dumps(event, ensure_ascii=False) + "\n")
                out.flush()

                if action.type == "keystroke":
                    shown = f"key:{action.argv[0]}" if action.argv else "key:<none>"
                else:
                    shown = " ".join(action.argv)
                print(f"step={step:02d} action={shown:<22} rc={result['returncode']} verify={ok} ({note})")

                if not ok:
                    # safe fallback once
                    fallback = Action(name="fallback-help", argv=["help"], reason="verification failed")
                    fb_res = execute_action(fallback)
                    fb_ok, fb_note = verify_expectation("ok", fb_res, runtime_state)
                    print(f"  fallback cmd=help rc={fb_res['returncode']} verify={fb_ok} ({fb_note})")
                    break

        print(f"[{_now()}] done run_log={run_log}")
        print(f"[{_now()}] host_log={host_log}")

    finally:
        host.terminate()
        try:
            host.wait(timeout=5)
        except subprocess.TimeoutExpired:
            host.kill()


if __name__ == "__main__":
    main()
