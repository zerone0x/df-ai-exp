"""Screen/state query helpers for DF worldgen automation."""

from __future__ import annotations

from typing import Any, Dict

from .config import get_df_root


def get_world_info() -> Dict[str, Any]:
    """Return basic world metadata that can be queried non-interactively.

    Uses filesystem-only checks because dfhack-run Lua probes segfault
    under Rosetta emulation.
    """

    save_dir = get_df_root() / "data" / "save"
    regions = sorted(p.name for p in save_dir.glob("region*") if p.is_dir()) if save_dir.exists() else []
    newest_region = regions[-1] if regions else ""
    return {
        "save_dir": str(save_dir),
        "regions": regions,
        "latest_region": newest_region,
        "region_count": len(regions),
    }


def is_worldgen_complete() -> bool:
    """Best-effort completion check for world generation.

    Uses filesystem-only heuristic (Lua probes segfault under Rosetta):
    - world save folder exists with at least one ``region*`` directory
    """

    save_dir = get_df_root() / "data" / "save"
    if not save_dir.exists():
        return False
    return any(p.is_dir() for p in save_dir.glob("region*"))
