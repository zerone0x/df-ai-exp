#!/usr/bin/env python3
"""Run a sequence of named goals and report pass/fail."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
GOAL_RUNNER = CURRENT_DIR / "goal_runner.py"


def run_goal(goal: str, warmup: float) -> int:
    cmd = [sys.executable, str(GOAL_RUNNER), "--goal", goal, "--warmup", str(warmup)]
    print(f"\n=== running goal: {goal} ===")
    return subprocess.call(cmd)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warmup", type=float, default=8.0)
    parser.add_argument("--goals", nargs="+", default=["quickfort_probe", "automation_probe"])
    args = parser.parse_args()

    failures = 0
    for goal in args.goals:
        rc = run_goal(goal, args.warmup)
        if rc != 0:
            failures += 1

    if failures:
        print(f"\nPipeline finished with {failures} failing goal(s).")
        raise SystemExit(1)

    print("\nPipeline finished: all goals passed.")


if __name__ == "__main__":
    main()
