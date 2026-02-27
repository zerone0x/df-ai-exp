"""Goal planner backed by command catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .goals.embark import plan_embark
from .goals.worldgen import plan_worldgen


CATALOG_PATH = Path(__file__).resolve().parents[1] / "config" / "command_catalog.json"


def load_catalog(path: Path | None = None) -> Dict[str, Any]:
    p = path or CATALOG_PATH
    if not p.exists():
        return {"commands": []}
    return json.loads(p.read_text(encoding="utf-8"))


def _has_command(catalog: Dict[str, Any], argv: List[str]) -> bool:
    for item in catalog.get("commands", []):
        if item.get("argv") == argv:
            return True
    return False


def plan_for_goal(goal: str, catalog: Dict[str, Any] | None = None) -> List[Dict[str, Any]]:
    cat = catalog or load_catalog()

    if goal == "quickfort_probe":
        plan: List[Dict[str, str]] = [
            {"name": "bootstrap", "command": "ls", "expect": "ok"},
            {"name": "taxonomy", "command": "tags", "expect": "contains:fort"},
        ]
        if _has_command(cat, ["ls", "fort"]):
            plan.append({"name": "discover-fort", "command": "ls fort", "expect": "ok"})
        if _has_command(cat, ["help", "quickfort"]):
            plan.append({"name": "quickfort-help", "command": "help quickfort", "expect": "contains:quickfort"})
        if _has_command(cat, ["help", "blueprint"]):
            plan.append({"name": "blueprint-help", "command": "help blueprint", "expect": "contains:blueprint"})
        return plan

    if goal == "automation_probe":
        plan: List[Dict[str, str]] = [
            {"name": "bootstrap", "command": "ls", "expect": "ok"},
            {"name": "discover-auto", "command": "ls auto", "expect": "ok"},
        ]
        # probe a few high-value automation commands
        for cmd in (["help", "autolabor"], ["help", "autofarm"], ["help", "autobutcher"]):
            plan.append({
                "name": f"probe-{cmd[1]}",
                "command": " ".join(cmd),
                "expect": "ok",
            })
        return plan

    if goal == "worldgen":
        return plan_worldgen()

    if goal == "embark":
        return plan_embark()

    # default conservative goal
    return [
        {"name": "bootstrap", "command": "ls", "expect": "ok"},
        {"name": "taxonomy", "command": "tags", "expect": "contains:fort"},
    ]
