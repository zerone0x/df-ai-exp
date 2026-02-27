"""Parse dfhack-run command outputs into structured state for LLM planner.

Since Lua probes segfault, we rely on:
1. dfhack-run command text output (parsed)
2. Filesystem checks (save dir, region dirs)
3. Blueprint/quickfort listings

All parsers return dicts suitable for JSON serialization.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from .dfhack import run_dfhack, CommandResult
from .config import get_df_root


def parse_command_list(stdout: str) -> List[Dict[str, str]]:
    """Parse `ls` or `ls <tag>` output into command entries."""
    entries = []
    current = None
    for line in stdout.splitlines():
        # Strip ANSI codes
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line).rstrip()
        if not clean:
            continue
        # Command lines start with a name (no leading space) followed by description
        match = re.match(r'^(\S+)\s{2,}(.+)$', clean)
        if match:
            if current:
                entries.append(current)
            current = {"name": match.group(1), "description": match.group(2).strip()}
        elif clean.startswith(' ') and current:
            # Continuation line (tags or extended description)
            tag_match = re.match(r'\s+tags:\s*(.+)', clean)
            if tag_match:
                current["tags"] = [t.strip() for t in tag_match.group(1).split(',')]
            else:
                current["description"] += " " + clean.strip()
    if current:
        entries.append(current)
    return entries


def parse_prospect(stdout: str) -> Dict[str, Any]:
    """Parse `prospect all` output into resource summary."""
    resources = {"ores": [], "gems": [], "other": []}
    section = "other"
    for line in stdout.splitlines():
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line).strip()
        if not clean:
            continue
        if "ite ore" in clean.lower() or "ore:" in clean.lower():
            section = "ores"
        elif "gem" in clean.lower():
            section = "gems"
        # Lines like "  IRON_ORE : 1234"
        match = re.match(r'^\s*(\w[\w\s]*\w)\s*:\s*(\d+)', clean)
        if match:
            resources[section].append({
                "name": match.group(1).strip(),
                "count": int(match.group(2)),
            })
    return resources


def get_fortress_state() -> Dict[str, Any]:
    """Gather all available fortress state from dfhack commands.

    Returns a dict with whatever info we can get. Commands that fail
    (e.g., "Map not available") return empty/default values.
    """
    state: Dict[str, Any] = {
        "world": get_world_state(),
        "fortress_loaded": False,
        "commands_available": [],
        "prospect": {},
    }

    # Test if fortress is loaded by trying a fort-only command
    result = run_dfhack(["showmood"], timeout=5, retries=0, check=False)
    if result.ok or "Cannot" not in result.stdout:
        state["fortress_loaded"] = True

    # If fortress is loaded, gather more info
    if state["fortress_loaded"]:
        # Prospect
        prospect = run_dfhack(["prospect", "all"], timeout=10, retries=0, check=False)
        if prospect.ok:
            state["prospect"] = parse_prospect(prospect.stdout)

    return state


def get_world_state() -> Dict[str, Any]:
    """Filesystem-based world state check."""
    df_root = get_df_root()
    save_dir = df_root / "data" / "save"
    regions = []
    if save_dir.exists():
        regions = sorted(p.name for p in save_dir.glob("region*") if p.is_dir())

    return {
        "regions": regions,
        "region_count": len(regions),
        "has_world": len(regions) > 0,
        "latest_region": regions[-1] if regions else None,
    }


def format_state_for_llm(state: Dict[str, Any]) -> str:
    """Format state dict into a concise text block for LLM context."""
    lines = []
    world = state.get("world", {})
    lines.append(f"World: {'exists' if world.get('has_world') else 'none'} "
                 f"(regions: {world.get('region_count', 0)})")
    lines.append(f"Fortress loaded: {state.get('fortress_loaded', False)}")

    prospect = state.get("prospect", {})
    if prospect:
        ores = prospect.get("ores", [])
        if ores:
            ore_names = [o["name"] for o in ores[:5]]
            lines.append(f"Ores: {', '.join(ore_names)}")

    return "\n".join(lines)
