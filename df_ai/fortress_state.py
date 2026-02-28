"""Read fortress state via dfhack-run commands (no Lua RPC required).

All state is gathered from:
  - dfhack-run command text output (parsed)
  - Filesystem checks (save dirs, region snapshots)
  - Blueprint listings via quickfort

Pitfall: Do NOT use dfhack.lua.eval or gui.getViewscreenByType via RPC —
those segfault. dfhack-run scripts (load-save.lua, etc.) run in a different
channel and are safe.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import get_df_root
from .dfhack import CommandResult, run_dfhack


# ---------------------------------------------------------------------------
# Filesystem checks (always safe, no dfhack needed)
# ---------------------------------------------------------------------------


def get_save_dirs() -> List[str]:
    """Return list of save folder names (region dirs)."""
    root = get_df_root()
    save_root = root / "data" / "save"
    if not save_root.is_dir():
        return []
    return sorted(
        d.name for d in save_root.iterdir()
        if d.is_dir() and d.name.startswith("region")
    )


def get_latest_save() -> Optional[str]:
    """Return the most recently modified save dir name, or None."""
    root = get_df_root()
    save_root = root / "data" / "save"
    if not save_root.is_dir():
        return None
    candidates = [
        d for d in save_root.iterdir()
        if d.is_dir() and d.name.startswith("region")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda d: d.stat().st_mtime).name


def get_fortress_tick(region: str) -> Optional[int]:
    """Estimate fortress age from number of region_snapshot-*.dat files."""
    root = get_df_root()
    save_dir = root / "data" / "save" / region
    if not save_dir.is_dir():
        return None
    snapshots = list(save_dir.glob("region_snapshot-*.dat"))
    if not snapshots:
        return None
    # Snapshot filenames encode tick: region_snapshot-<tick>.dat
    ticks = []
    for s in snapshots:
        m = re.match(r"region_snapshot-(\d+)\.dat", s.name)
        if m:
            ticks.append(int(m.group(1)))
    return max(ticks) if ticks else len(snapshots) * 10


def is_dfhack_running() -> bool:
    """Check if dfhack-run can connect (exit code 0 = game is running)."""
    result = run_dfhack(["ls"], timeout=3.0, retries=0)
    return result.ok


# ---------------------------------------------------------------------------
# DFHack command probes (no Lua RPC)
# ---------------------------------------------------------------------------


def probe_commands(timeout: float = 5.0) -> Dict[str, Any]:
    """Run `ls` and return basic command availability info."""
    result = run_dfhack(["ls"], timeout=timeout)
    return {
        "ok": result.ok,
        "rc": result.returncode,
        "count": len(result.stdout.splitlines()) if result.ok else 0,
        "stderr": result.stderr.strip()[:200] if result.stderr else "",
    }


def probe_prospect(timeout: float = 12.0) -> Dict[str, Any]:
    """Run `prospect all` and parse mineral resources.

    Only works in fortress mode (after embark). Returns empty dict otherwise.
    """
    result = run_dfhack(["prospect", "all"], timeout=timeout)
    if not result.ok:
        return {"available": False, "error": result.stderr.strip()[:200]}

    return {
        "available": True,
        "raw_lines": result.stdout.count("\n"),
        "resources": _parse_prospect_output(result.stdout),
    }


def _parse_prospect_output(stdout: str) -> Dict[str, Dict[str, int]]:
    """Parse prospect output into {category: {mineral: count}} dict."""
    out: Dict[str, Dict[str, int]] = {
        "stone": {},
        "ores": {},
        "gems": {},
        "soil": {},
        "other": {},
    }
    section = "stone"
    for line in stdout.splitlines():
        clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if not clean:
            continue
        low = clean.lower()
        if "ore" in low:
            section = "ores"
        elif "gem" in low:
            section = "gems"
        elif "soil" in low or "clay" in low:
            section = "soil"
        # Parse "IRON_ORE : 1234"
        m = re.match(r"([A-Z][A-Z0-9_]+)\s*:\s*(\d+)", clean)
        if m:
            out[section][m.group(1)] = int(m.group(2))
    return out


def probe_showmood(timeout: float = 5.0) -> Dict[str, Any]:
    """Run `showmood` to check current dwarf moods."""
    result = run_dfhack(["showmood"], timeout=timeout)
    return {
        "available": result.ok,
        "raw": result.stdout.strip()[:500],
        "has_moody_dwarf": "is " in result.stdout.lower(),
    }


def probe_quickfort_list(timeout: float = 5.0) -> List[Dict[str, str]]:
    """List available quickfort blueprints."""
    result = run_dfhack(["quickfort", "list"], timeout=timeout)
    if not result.ok:
        return []
    blueprints = []
    for line in result.stdout.splitlines():
        clean = re.sub(r"\x1b\[[0-9;]*m", "", line).strip()
        if not clean:
            continue
        # Format: "[N] path/to/file.csv (label) PHASE x,y,z"
        m = re.match(r"\[(\d+)\]\s+(.+)", clean)
        if m:
            blueprints.append({"id": m.group(1), "desc": m.group(2)})
        else:
            blueprints.append({"id": "?", "desc": clean})
    return blueprints


def probe_gamelog(tail: int = 20) -> List[str]:
    """Read last N lines from gamelog.txt."""
    root = get_df_root()
    gamelog = root / "gamelog.txt"
    if not gamelog.is_file():
        return []
    lines = gamelog.read_text(errors="ignore").splitlines()
    return lines[-tail:]


def probe_dfhack_log(tail: int = 30) -> List[str]:
    """Read recent DFHack stdout log."""
    root = get_df_root()
    for logname in ("stdout.log", "logs/dfhack/stdout.log"):
        logpath = root / logname
        if logpath.is_file():
            lines = logpath.read_text(errors="ignore").splitlines()
            return [l for l in lines if l.strip()][-tail:]
    return []


# ---------------------------------------------------------------------------
# Composite state reader
# ---------------------------------------------------------------------------


def read_fortress_state(
    region: Optional[str] = None,
    skip_prospect: bool = False,
    timeout_total: float = 25.0,
) -> Dict[str, Any]:
    """
    Gather comprehensive fortress state.

    Args:
        region: Which save to describe (default: latest).
        skip_prospect: Skip `prospect all` (slow, ~10s). Use True for fast polls.
        timeout_total: Total budget for all dfhack probes.

    Returns:
        Dict suitable for JSON serialization and LLM consumption.
    """
    t0 = time.monotonic()
    region = region or get_latest_save()

    state: Dict[str, Any] = {
        "timestamp": time.time(),
        "mode": "fortress",
        "region": region,
        "saves": get_save_dirs(),
        "tick": get_fortress_tick(region) if region else None,
        "dfhack_running": is_dfhack_running(),
        "gamelog": [],
        "dfhack_log": [],
        "commands": {},
        "mood": {},
        "blueprints": [],
        "resources": {},
        "errors": [],
    }

    if not state["dfhack_running"]:
        state["errors"].append("dfhack not reachable — is DF running?")
        return state

    remaining = timeout_total - (time.monotonic() - t0)

    # Commands probe
    try:
        state["commands"] = probe_commands(timeout=min(5.0, remaining))
    except Exception as exc:
        state["errors"].append(f"commands: {exc}")

    # Gamelog (filesystem, always fast)
    try:
        state["gamelog"] = probe_gamelog(tail=15)
    except Exception as exc:
        state["errors"].append(f"gamelog: {exc}")

    # DFHack stdout log
    try:
        state["dfhack_log"] = probe_dfhack_log(tail=20)
    except Exception as exc:
        state["errors"].append(f"dfhack_log: {exc}")

    # Mood
    remaining = timeout_total - (time.monotonic() - t0)
    if remaining > 2:
        try:
            state["mood"] = probe_showmood(timeout=min(5.0, remaining))
        except Exception as exc:
            state["errors"].append(f"mood: {exc}")

    # Blueprints
    remaining = timeout_total - (time.monotonic() - t0)
    if remaining > 2:
        try:
            state["blueprints"] = probe_quickfort_list(timeout=min(5.0, remaining))
        except Exception as exc:
            state["errors"].append(f"blueprints: {exc}")

    # Resources (slow — skip if requested or no time)
    remaining = timeout_total - (time.monotonic() - t0)
    if not skip_prospect and remaining > 5:
        try:
            state["resources"] = probe_prospect(timeout=min(12.0, remaining))
        except Exception as exc:
            state["errors"].append(f"resources: {exc}")

    return state


def format_state_for_llm(state: Dict[str, Any]) -> str:
    """Format fortress state into a compact LLM-friendly string."""
    lines = [
        f"## Fortress State",
        f"Region: {state.get('region', '?')}  Tick: {state.get('tick', '?')}",
        f"DFHack running: {state.get('dfhack_running')}",
        f"Available saves: {', '.join(state.get('saves', []))}",
    ]

    # Gamelog
    gamelog = state.get("gamelog", [])
    if gamelog:
        lines.append("\n## Recent Gamelog (last 10)")
        for ln in gamelog[-10:]:
            lines.append(f"  {ln}")

    # Mood
    mood = state.get("mood", {})
    if mood.get("raw"):
        lines.append(f"\n## Dwarf Moods\n  {mood['raw'][:300]}")

    # Blueprints
    bps = state.get("blueprints", [])
    if bps:
        lines.append(f"\n## Available Blueprints ({len(bps)} total)")
        for bp in bps[:5]:
            lines.append(f"  [{bp['id']}] {bp['desc'][:80]}")

    # Resources summary
    resources = state.get("resources", {})
    if resources.get("available"):
        ores = resources.get("resources", {}).get("ores", {})
        if ores:
            top_ores = sorted(ores.items(), key=lambda x: -x[1])[:5]
            lines.append("\n## Top Ores")
            for name, count in top_ores:
                lines.append(f"  {name}: {count}")

    # Errors
    errors = state.get("errors", [])
    if errors:
        lines.append(f"\n## State Errors")
        for e in errors:
            lines.append(f"  ! {e}")

    return "\n".join(lines)
