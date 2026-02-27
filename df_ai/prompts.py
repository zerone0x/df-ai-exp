"""Prompt templates for LLM-driven DF action planning."""

from __future__ import annotations

SYSTEM_PROMPT = """\
You are an AI agent controlling Dwarf Fortress via DFHack.

## Action Types
- "dfhack": commands executed via dfhack-run CLI (e.g. ["ls"], ["help", "quickfort"])
- "keystroke": keys sent to the DF window via xdotool (e.g. ["Return"], ["Down"], ["y"])

## Available DFHack Commands (subset)
- ls [tag]: list commands (tags: fort, design, auto, dev, dfhack)
- help <cmd>: detailed help for a command
- tags: list all command tags
- quickfort: execute blueprint files
- blueprint: capture fortress as blueprint
- autolabor / autofarm / autobutcher: automation tools
- lua print(<expr>): run Lua expressions (query game state)
- die: quit DF (DANGEROUS - avoid unless explicitly told)

## Keystroke Keys
Return, Escape, Up, Down, Left, Right, Tab, space, a-z, y, n

## Rules
1. Be conservative - prefer read-only commands (ls, help, tags) over mutations
2. Never run "die" or destructive commands without explicit goal requiring it
3. If you've gathered enough info or achieved the goal, output {"done": true}
4. Keep reasons brief but informative
5. Learn from action history - don't repeat failed commands

## Output Format
Respond with ONLY a JSON object (no markdown, no explanation):
{"name": "action_name", "argv": ["cmd", "args"], "type": "dfhack", "reason": "why"}

Or to stop:
{"done": true, "reason": "goal achieved because..."}
"""

STATE_TEMPLATE = """\
## Current State
- DFHack ready: {dfhack_ready}
- FPE detected: {has_fpe}
- Successful commands so far: {ok_count}
- Game mode: {gamemode}
- Game type: {gametype}
- World regions: {region_count}
- Step: {step}

## Goal
{goal}

## Command Catalog (known working)
{catalog_summary}

## Recent Action History (last {history_len})
{history}
"""


def format_state(
    state: dict,
    goal: str,
    catalog_summary: str,
    history: list[dict],
    step: int,
) -> str:
    """Format current state into an LLM user message."""

    history_lines = []
    for h in history[-10:]:
        act = h.get("action", {})
        history_lines.append(
            f"  step={h.get('step','?')} {act.get('display','?')} "
            f"ok={h.get('ok','?')} rc={h.get('returncode','?')}"
        )

    return STATE_TEMPLATE.format(
        dfhack_ready=state.get("dfhack_ready", False),
        has_fpe=state.get("has_floating_point_exception", False),
        ok_count=state.get("successful_commands", 0),
        gamemode=state.get("gamemode", "unknown"),
        gametype=state.get("gametype", "unknown"),
        region_count=state.get("region_count", 0),
        step=step,
        goal=goal or "Explore and discover DF capabilities",
        catalog_summary=catalog_summary or "(none yet)",
        history_len=len(history),
        history="\n".join(history_lines) if history_lines else "(none)",
    )


def format_catalog(catalog: dict) -> str:
    """Summarize command catalog for LLM context."""

    commands = catalog.get("commands", [])
    if not commands:
        return "(empty)"
    lines = []
    for cmd in commands[:30]:  # cap to save tokens
        argv = " ".join(cmd.get("argv", []))
        risk = cmd.get("risk", "?")
        ok = cmd.get("success_count", 0)
        lines.append(f"  {argv} (risk={risk}, ok={ok}x)")
    return "\n".join(lines)
