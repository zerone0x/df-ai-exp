"""Screen/state query helpers for DF worldgen automation."""

from __future__ import annotations

from typing import Any, Dict

from .config import get_df_root
from .dfhack import run_dfhack


def _lua_print(expr: str) -> str:
    result = run_dfhack(["lua", f"print({expr})"], timeout=6.0, retries=0, check=False)
    if not result.ok:
        return ""
    return result.stdout.strip().splitlines()[-1] if result.stdout.strip() else ""


def get_game_mode() -> str:
    """Return current `df.global.gamemode` numeric value as text."""

    return _lua_print("df.global.gamemode")


def get_game_type() -> str:
    """Return current `df.global.gametype` numeric value as text."""

    return _lua_print("df.global.gametype")


def get_world_info() -> Dict[str, Any]:
    """Return basic world metadata that can be queried non-interactively."""

    save_dir = get_df_root() / "data" / "save"
    regions = sorted(p.name for p in save_dir.glob("region*") if p.is_dir()) if save_dir.exists() else []
    newest_region = regions[-1] if regions else ""
    return {
        "save_dir": str(save_dir),
        "regions": regions,
        "latest_region": newest_region,
        "region_count": len(regions),
        "gamemode": get_game_mode(),
        "gametype": get_game_type(),
    }


def is_worldgen_complete() -> bool:
    """Best-effort completion check for world generation.

    MVP heuristic:
    - world save folder exists with at least one `region*` directory
    - mode/type values are readable through dfhack-run lua probes
    """

    info = get_world_info()
    has_region = info["region_count"] > 0
    mode_known = info["gamemode"] != ""
    type_known = info["gametype"] != ""
    return has_region and mode_known and type_known
