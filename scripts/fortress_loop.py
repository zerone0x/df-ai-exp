#!/usr/bin/env python3
"""LLM-driven Dwarf Fortress fortress agent loop.

Full loop:
  1. Read fortress state (dfhack-run + filesystem)
  2. Format state for LLM
  3. LLM decides next action (dfhack-run command)
  4. Execute action, record result
  5. Go to 1

Usage:
    # Start fresh (loads a save first):
    python scripts/fortress_loop.py --region region29 --goal "dig a 5x5 room and build stockpiles"

    # Connect to already-running DF:
    python scripts/fortress_loop.py --goal "prospect minerals and report findings"

    # Dry-run (no execution, just print planned actions):
    python scripts/fortress_loop.py --dry-run --goal "explore commands"

    # Use specific model:
    DF_AI_MODEL=claude-opus-4-20250514 python scripts/fortress_loop.py ...

Safety:
    - Blocked commands: die, kill-lua, teleport, reveal (destructive/risky)
    - Max steps enforced
    - dfhack-run timeout per command
    - System load guard before starting DF
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from df_ai.config import get_df_root, get_logs_dir  # noqa: E402
from df_ai.dfhack import run_dfhack  # noqa: E402
from df_ai.fortress_state import (  # noqa: E402
    format_state_for_llm,
    get_latest_save,
    is_dfhack_ready,
    read_fortress_state,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("fortress_loop")

# ---------------------------------------------------------------------------
# LLM integration
# ---------------------------------------------------------------------------

FORTRESS_SYSTEM_PROMPT = """\
You are an AI agent controlling a Dwarf Fortress fortress via DFHack command-line.

## Your Job
Read the fortress state, decide the single most useful next dfhack-run command, execute it.
Focus on gathering information first, then taking actions.

## Available DFHack Commands (safe to use)
| Command                     | Purpose                                              |
|-----------------------------|------------------------------------------------------|
| ls                          | list all available commands                          |
| ls fort                     | list fortress-mode commands                          |
| ls design                   | list designation/build commands                      |
| help <cmd>                  | detailed help for a command                          |
| prospect all                | survey all minerals/ores in the area                 |
| showmood                    | show current dwarf moods                             |
| autolabor                   | list/manage labor assignments                        |
| quickfort list              | list available blueprints                            |
| quickfort run <id>          | apply a blueprint (dig/build designations)           |
| dig-now                     | immediately process pending dig designations         |
| build-now                   | immediately process pending build orders             |
| allneeds                    | report all unmet dwarf needs                        |
| cursecheck                  | check for cursed units                              |
| burial                      | manage burial assignments                            |
| deathcause                  | explain recent deaths                               |

## Command Format
Respond with ONLY valid JSON — no markdown, no explanation:
{"cmd": ["dfhack-command", "arg1", "arg2"], "reason": "one line why"}

To stop when goal is achieved:
{"done": true, "summary": "what was accomplished"}

## Rules
1. NEVER issue: die, kill-lua, teleport, reveal, exterminate, forcekill
2. Start with read-only (ls, prospect, showmood) before making changes
3. If a command failed last step, try something different
4. quickfort run modifies the map — only do this when instructed by the goal
5. Keep reasons brief (one line)
"""


def _get_llm_action(
    state_text: str,
    goal: str,
    history: List[Dict[str, Any]],
    step: int,
) -> Dict[str, Any]:
    """Call LLM and get next action. Returns dict with 'cmd' list or 'done' bool."""
    backend = _detect_backend()
    history_text = _format_history(history[-8:])
    user_msg = (
        f"## Goal\n{goal}\n\n"
        f"{state_text}\n\n"
        f"## Action History (step {step})\n{history_text}\n\n"
        "## What is the single best next dfhack command to run?"
    )

    try:
        if backend == "anthropic":
            return _call_anthropic(user_msg)
        else:
            return _call_openai(user_msg)
    except Exception as exc:
        logger.error(f"LLM call failed: {exc}")
        return {"cmd": ["ls"], "reason": f"LLM error fallback: {exc}"}


def _detect_backend() -> str:
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    return "anthropic"  # default, will fail gracefully


def _call_anthropic(user_msg: str) -> Dict[str, Any]:
    import anthropic
    client = anthropic.Anthropic(
        api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        auth_token=os.environ.get("ANTHROPIC_AUTH_TOKEN") or None,
    )
    model = os.environ.get("DF_AI_MODEL", "claude-sonnet-4-20250514")
    resp = client.messages.create(
        model=model,
        max_tokens=256,
        system=FORTRESS_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = resp.content[0].text.strip()
    return _parse_llm_json(raw)


def _call_openai(user_msg: str) -> Dict[str, Any]:
    import openai
    client = openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    model = os.environ.get("DF_AI_MODEL", "gpt-4o")
    resp = client.chat.completions.create(
        model=model,
        max_tokens=256,
        messages=[
            {"role": "system", "content": FORTRESS_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    raw = resp.choices[0].message.content.strip()
    return _parse_llm_json(raw)


def _parse_llm_json(raw: str) -> Dict[str, Any]:
    """Parse LLM response, strip markdown fences if present."""
    import re
    clean = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    clean = re.sub(r"\s*```\s*$", "", clean, flags=re.MULTILINE)
    clean = clean.strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError as exc:
        logger.warning(f"LLM output not valid JSON: {exc}\nRaw: {raw[:200]}")
        return {"cmd": ["ls"], "reason": "parse error fallback"}


def _format_history(history: List[Dict[str, Any]]) -> str:
    if not history:
        return "(none)"
    lines = []
    for h in history:
        status = "✓" if h.get("ok") else "✗"
        cmd = " ".join(h.get("cmd", []))
        lines.append(f"  {status} step={h['step']} `{cmd}` — {h.get('reason', '?')} (rc={h.get('rc', '?')})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Safety guard
# ---------------------------------------------------------------------------

_BLOCKED_COMMANDS = {
    "die", "kill-lua", "teleport", "reveal", "exterminate",
    "forcekill", "rm", "del",
}


def is_safe_command(argv: List[str]) -> tuple[bool, str]:
    """Check if a command is safe to execute. Returns (safe, reason)."""
    if not argv:
        return False, "empty command"
    cmd = argv[0].lower()
    if cmd in _BLOCKED_COMMANDS:
        return False, f"'{cmd}' is blocked"
    if any(part in _BLOCKED_COMMANDS for part in argv):
        return False, f"blocked token in argv: {argv}"
    return True, ""


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------


def run_fortress_loop(
    goal: str,
    region: Optional[str] = None,
    max_steps: int = 20,
    dry_run: bool = False,
    skip_prospect: bool = True,
    step_delay: float = 2.0,
    log_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Run the LLM fortress agent loop.

    Args:
        goal: Natural language goal for the LLM agent.
        region: Save region to describe in state (defaults to latest).
        max_steps: Maximum number of LLM→execute cycles.
        dry_run: If True, print actions but don't execute.
        skip_prospect: Skip slow prospect all (speeds up loop).
        step_delay: Seconds to wait between steps.
        log_path: If given, write JSONL log of each step.

    Returns:
        Summary dict with final state and history.
    """
    region = region or get_latest_save()
    logger.info(f"Starting fortress loop | goal: {goal!r} | region: {region} | steps: {max_steps}")

    if not is_dfhack_ready(timeout=5.0):
        logger.error("DFHack not ready — is DF running? Use df_runner.py start first.")
        return {"error": "dfhack not ready", "steps": 0}

    history: List[Dict[str, Any]] = []
    logfile = log_path or (get_logs_dir() / f"fortress_{int(time.time())}.jsonl")
    logfile.parent.mkdir(parents=True, exist_ok=True)

    final_summary = ""
    start_time = time.time()

    for step in range(1, max_steps + 1):
        logger.info(f"=== Step {step}/{max_steps} ===")

        # 1. Read state
        t0 = time.monotonic()
        state = read_fortress_state(
            region=region,
            skip_prospect=skip_prospect,
            timeout_total=20.0,
        )
        state_text = format_state_for_llm(state)
        logger.debug(f"State read in {time.monotonic()-t0:.1f}s")

        # 2. Get LLM action
        action_data = _get_llm_action(state_text, goal, history, step)

        if action_data.get("done"):
            final_summary = action_data.get("summary", "Goal achieved.")
            logger.info(f"Agent done: {final_summary}")
            break

        argv = action_data.get("cmd", ["ls"])
        reason = action_data.get("reason", "")
        logger.info(f"LLM action: {argv!r} — {reason}")

        # 3. Safety check
        safe, why = is_safe_command(argv)
        if not safe:
            logger.warning(f"BLOCKED: {why}")
            history.append({
                "step": step,
                "cmd": argv,
                "reason": reason,
                "ok": False,
                "rc": -1,
                "stdout": "",
                "blocked": True,
                "block_reason": why,
            })
            continue

        # 4. Execute
        if dry_run:
            logger.info(f"[DRY RUN] Would execute: dfhack-run {' '.join(argv)}")
            stdout = "(dry run)"
            rc = 0
            ok = True
        else:
            result = run_dfhack(argv, timeout=15.0, retries=1, retry_delay=2.0)
            stdout = result.stdout.strip()
            rc = result.returncode
            ok = result.ok
            if stdout:
                logger.info(f"Output:\n{stdout[:500]}")
            if not ok:
                logger.warning(f"Command failed (rc={rc}): {result.stderr.strip()[:200]}")

        # 5. Record
        step_record = {
            "step": step,
            "cmd": argv,
            "reason": reason,
            "ok": ok,
            "rc": rc,
            "stdout": stdout[:1000] if stdout else "",
            "timestamp": time.time(),
        }
        history.append(step_record)

        with open(logfile, "a") as f:
            f.write(json.dumps(step_record) + "\n")

        if step < max_steps:
            time.sleep(step_delay)

    else:
        final_summary = f"Max steps ({max_steps}) reached."
        logger.info(final_summary)

    summary = {
        "goal": goal,
        "region": region,
        "steps_taken": len(history),
        "ok_count": sum(1 for h in history if h.get("ok")),
        "duration_s": round(time.time() - start_time, 1),
        "final_summary": final_summary,
        "log": str(logfile),
    }

    logger.info(
        f"Loop complete: {summary['steps_taken']} steps, "
        f"{summary['ok_count']} ok, {summary['duration_s']}s"
    )
    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="LLM-driven DF fortress agent")
    parser.add_argument("--goal", default="Explore fortress capabilities and report on available commands and mineral resources.", help="Goal for the LLM agent")
    parser.add_argument("--region", default=None, help="Save region to load (e.g. region29). Defaults to latest.")
    parser.add_argument("--steps", type=int, default=15, help="Max agent steps")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument("--with-prospect", action="store_true", help="Include prospect all (slow, ~10s)")
    parser.add_argument("--step-delay", type=float, default=2.0, help="Delay between steps")
    parser.add_argument("--json", action="store_true", help="Output summary as JSON")
    args = parser.parse_args()

    summary = run_fortress_loop(
        goal=args.goal,
        region=args.region,
        max_steps=args.steps,
        dry_run=args.dry_run,
        skip_prospect=not args.with_prospect,
        step_delay=args.step_delay,
    )

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("\n=== SUMMARY ===")
        for k, v in summary.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
