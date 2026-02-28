#!/usr/bin/env python3
"""Phase 1: Survival Basics — establish food, drink, and shelter.

This script runs a hardcoded plan using dreamfort blueprints + dig-now/build-now
to rapidly set up a functional fortress. Each step queries DFHack for state
verification before and after execution, and logs everything to JSONL.

Usage:
    python scripts/phase1.py [--dry-run] [--step N]
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running from repo root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from df_ai.dfhack import run_dfhack, CommandResult


# ---------------------------------------------------------------------------
# State queries
# ---------------------------------------------------------------------------

def query_state() -> dict[str, Any]:
    """Query current fortress state via DFHack Lua."""
    queries = {
        "year_tick": "lua dfhack.println(df.global.cur_year .. '/' .. df.global.cur_year_tick)",
        "paused": "lua dfhack.println(tostring(df.global.pause_state))",
        "focus": "lua dfhack.println(dfhack.gui.getCurFocus(true))",
        "citizens": (
            "lua local c=0; for _,u in ipairs(df.global.world.units.active) do "
            "if dfhack.units.isCitizen(u) then c=c+1 end end; dfhack.println(c)"
        ),
        "buildings": "lua dfhack.println(#df.global.world.buildings.all)",
        "items": "lua dfhack.println(#df.global.world.items.all)",
        "drinks": (
            "lua local c=0; for _,item in ipairs(df.global.world.items.all) do "
            "if df.item_drinkst:is_instance(item) then c=c+1 end end; dfhack.println(c)"
        ),
    }
    state = {}
    for key, cmd in queries.items():
        r = run_dfhack(cmd)
        state[key] = r.stdout.strip() if r.ok else f"ERROR:{r.stdout.strip()}"
    return state


def ensure_paused() -> None:
    """Ensure the game is paused."""
    r = run_dfhack("lua dfhack.println(tostring(df.global.pause_state))")
    if r.ok and r.stdout.strip() == "false":
        run_dfhack("fpause")


def ensure_cursor(x: int, y: int, z: int) -> None:
    """Set the game cursor to a specific position."""
    run_dfhack(
        f"lua df.global.cursor.x={x}; df.global.cursor.y={y}; df.global.cursor.z={z}; "
        f"dfhack.println('cursor_set')"
    )


# ---------------------------------------------------------------------------
# Step definitions
# ---------------------------------------------------------------------------

@dataclass
class Step:
    name: str
    description: str
    commands: list[list[str]]  # Each command is a list of args for run_dfhack
    cursor: tuple[int, int, int] | None = None  # (x, y, z) to set before commands
    verify: str | None = None  # Lua expression that should print "ok"
    notes: list[str] = field(default_factory=list)


# Wagon position = central stairs position
CX, CY, SURFACE_Z = 94, 107, 164
FARM_Z = SURFACE_Z - 1  # z=163


def build_phase1_plan() -> list[Step]:
    """Build the Phase 1 hardcoded plan based on dreamfort."""
    return [
        Step(
            name="setup",
            description="Run dreamfort /setup to configure standing orders and burrows",
            commands=[
                ["quickfort", "run", "library/dreamfort.csv", "-n", "/setup",
                 "-c", f"{CX},{CY},{SURFACE_Z}"],
            ],
            cursor=(CX, CY, SURFACE_Z),
            notes=["Sets standing orders, creates burrows, assigns nobles"],
        ),
        Step(
            name="surface1",
            description="Clear trees, set up pastures, dig central stairs",
            commands=[
                ["quickfort", "run", "library/dreamfort.csv", "-n", "/surface1",
                 "-c", f"{CX},{CY},{SURFACE_Z}"],
                ["dig-now"],  # Instantly complete all dig designations
            ],
            cursor=(CX, CY, SURFACE_Z),
            notes=["Surface 1 designates tree clearing and central stair column"],
        ),
        Step(
            name="farming1-dig",
            description="Dig out farming level one z-level below surface",
            commands=[
                ["quickfort", "run", "library/dreamfort.csv", "-n", "/farming1",
                 "-c", f"{CX},{CY},{FARM_Z}"],
                ["dig-now"],
            ],
            cursor=(CX, CY, FARM_Z),
            notes=["Farming level dug at z=163"],
        ),
        Step(
            name="farming2-build",
            description="Build workshops and stockpiles on farming level",
            commands=[
                ["quickfort", "orders", "library/dreamfort.csv", "-n", "/farming2"],
                ["quickfort", "run", "library/dreamfort.csv", "-n", "/farming2",
                 "-c", f"{CX},{CY},{FARM_Z}"],
                ["build-now"],
            ],
            cursor=(CX, CY, FARM_Z),
            notes=["Places workshops: kitchen, brewery, butcher, fishery, tannery, etc."],
        ),
        Step(
            name="farming3-rooms",
            description="Build farm plots, dining room, dormitory",
            commands=[
                ["quickfort", "orders", "library/dreamfort.csv", "-n", "/farming3"],
                ["quickfort", "run", "library/dreamfort.csv", "-n", "/farming3",
                 "-c", f"{CX},{CY},{FARM_Z}"],
                ["build-now"],
            ],
            cursor=(CX, CY, FARM_Z),
            notes=["Farm plots for plump helmets, starter dining + dormitory"],
        ),
        Step(
            name="unpause-and-wait",
            description="Unpause game, advance 500 ticks, then check state",
            commands=[
                ["lua", "df.global.pause_state=false; dfhack.println('unpaused')"],
                # Advance time by unpausing briefly
            ],
            notes=[
                "After unpausing, dwarves will start farming and brewing.",
                "We wait a few hundred ticks for initial food production.",
            ],
        ),
        Step(
            name="verify-phase1",
            description="Verify Phase 1 success: food, drink, beds",
            commands=[
                ["fpause"],  # Re-pause for safety
                ["quicksave"],
            ],
            verify=(
                "lua local ok=true; local msg='';"
                "local drinks=0; for _,item in ipairs(df.global.world.items.all) do "
                "if df.item_drinkst:is_instance(item) then drinks=drinks+1 end end;"
                "if drinks < 5 then ok=false; msg=msg..'low_drinks(' .. drinks .. ') ' end;"
                "local citizens=0; for _,u in ipairs(df.global.world.units.active) do "
                "if dfhack.units.isCitizen(u) then citizens=citizens+1 end end;"
                "if citizens < 7 then ok=false; msg=msg..'lost_citizens(' .. citizens .. ') ' end;"
                "if ok then dfhack.println('PHASE1_OK') else dfhack.println('PHASE1_ISSUES: ' .. msg) end"
            ),
            notes=["Success = 7+ citizens alive, 5+ drinks available"],
        ),
    ]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_step(step: Step, log_file) -> dict[str, Any]:
    """Execute a single step and return the log entry."""
    entry: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "step": step.name,
        "description": step.description,
    }

    # Query state before
    entry["state_before"] = query_state()

    # Set cursor if needed
    if step.cursor:
        ensure_cursor(*step.cursor)
        entry["cursor_set"] = list(step.cursor)

    # Execute commands
    cmd_results = []
    for cmd_args in step.commands:
        r = run_dfhack(cmd_args, timeout=60)
        cmd_results.append({
            "command": cmd_args,
            "ok": r.ok,
            "returncode": r.returncode,
            "stdout_preview": r.stdout[:500] if r.stdout else "",
            "duration": r.duration,
        })
        print(f"  cmd: {' '.join(cmd_args[:4]):<50} ok={r.ok} ({r.duration:.1f}s)")
        if r.stdout.strip():
            # Print first 2 lines of output
            for line in r.stdout.strip().split("\n")[:2]:
                print(f"    > {line}")
    entry["commands"] = cmd_results

    # Verify if applicable
    if step.verify:
        vr = run_dfhack(step.verify)
        entry["verify"] = {
            "ok": vr.ok,
            "output": vr.stdout.strip(),
        }
        print(f"  verify: {vr.stdout.strip()}")

    # Query state after
    entry["state_after"] = query_state()

    # Write log
    log_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    log_file.flush()

    return entry


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phase 1: Survival Basics")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without executing")
    parser.add_argument("--step", type=int, help="Run only step N (0-indexed)")
    parser.add_argument("--from-step", type=int, default=0, help="Start from step N")
    args = parser.parse_args()

    plan = build_phase1_plan()

    if args.dry_run:
        print("Phase 1 Plan (dry run):")
        for i, step in enumerate(plan):
            print(f"\n  [{i}] {step.name}: {step.description}")
            for cmd in step.commands:
                print(f"      > {' '.join(cmd)}")
            if step.notes:
                for note in step.notes:
                    print(f"      # {note}")
        return

    # Verify we're in fortress mode
    r = run_dfhack("lua dfhack.println(dfhack.gui.getCurFocus(true))")
    focus = r.stdout.strip()
    if "dwarfmode" not in focus:
        print(f"ERROR: Not in fortress mode (focus={focus})")
        sys.exit(1)

    ensure_paused()

    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    log_path = log_dir / f"phase1_{int(time.time())}.jsonl"

    print(f"=== Phase 1: Survival Basics ===")
    print(f"Log: {log_path}")
    print(f"Steps: {len(plan)}")
    print()

    steps_to_run = [plan[args.step]] if args.step is not None else plan[args.from_step:]
    step_offset = args.step if args.step is not None else args.from_step

    with log_path.open("w") as log_file:
        for i, step in enumerate(steps_to_run):
            idx = step_offset + i
            print(f"[{idx}/{len(plan)-1}] {step.name}: {step.description}")
            entry = run_step(step, log_file)

            # Check for failures
            any_fail = any(not c["ok"] for c in entry.get("commands", []))
            if any_fail:
                print(f"  WARNING: Some commands failed in step {step.name}")

            verify = entry.get("verify", {})
            if verify and "PHASE1_ISSUES" in verify.get("output", ""):
                print(f"  ISSUES: {verify['output']}")

            print()

    print(f"=== Phase 1 Complete ===")
    print(f"Log: {log_path}")


if __name__ == "__main__":
    main()
