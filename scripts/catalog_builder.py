#!/usr/bin/env python3
"""Build a command catalog from loop logs (jsonl)."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Any

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def strip_ansi(s: str) -> str:
    return ANSI_RE.sub("", s)


def risk_for(argv: list[str]) -> str:
    cmd = argv[0] if argv else ""
    low = {"ls", "help", "tags"}
    return "low" if cmd in low else "unknown"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path, help="agent_loop_*.jsonl path")
    parser.add_argument("--out", type=Path, default=Path("config/command_catalog.json"))
    args = parser.parse_args()

    entries: Dict[str, Dict[str, Any]] = {}

    for line in args.log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        res = obj.get("result", {})
        action = res.get("action", {})
        argv = action.get("argv") or []
        if not argv:
            display = action.get("display", "")
            argv = display.split() if display else []
        if not argv:
            continue

        key = " ".join(argv)
        stdout = strip_ansi(str(res.get("stdout", "")))
        sample = "\n".join(stdout.splitlines()[:3])

        cur = entries.get(key)
        if not cur:
            entries[key] = {
                "argv": argv,
                "risk": risk_for(argv),
                "success_count": 1 if res.get("ok") else 0,
                "fail_count": 0 if res.get("ok") else 1,
                "last_rc": res.get("returncode"),
                "sample_stdout": sample,
            }
        else:
            if res.get("ok"):
                cur["success_count"] += 1
            else:
                cur["fail_count"] += 1
            cur["last_rc"] = res.get("returncode")
            if sample:
                cur["sample_stdout"] = sample

    out = {
        "source_log": str(args.log),
        "commands": sorted(entries.values(), key=lambda x: (x["risk"], " ".join(x["argv"]))),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(args.out)


if __name__ == "__main__":
    main()
