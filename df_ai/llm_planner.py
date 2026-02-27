"""LLM-backed action planner with safe fallback to rule-based policy."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from .planner import load_catalog
from .policy import Action, choose_action


MODEL_NAME = "claude-sonnet-4-20250514"


def _catalog_categories(catalog: Dict[str, Any]) -> Dict[str, List[str]]:
    commands = catalog.get("commands", [])
    roots: set[str] = set()
    ls_scopes: set[str] = set()
    for item in commands:
        argv = item.get("argv") or []
        if not argv:
            continue
        roots.add(str(argv[0]))
        if len(argv) >= 2 and str(argv[0]) == "ls":
            ls_scopes.add(str(argv[1]))

    return {
        "command_roots": sorted(roots),
        "ls_scopes": sorted(ls_scopes),
    }


def _build_system_prompt(categories: Dict[str, List[str]]) -> str:
    roots = ", ".join(categories["command_roots"]) or "(none in catalog yet)"
    scopes = ", ".join(categories["ls_scopes"]) or "(none in catalog yet)"
    return (
        "You are planning one safe next command for a Dwarf Fortress automation agent.\n"
        "Environment:\n"
        "- Game: Dwarf Fortress\n"
        "- Automation channel: DFHack command runner (non-interactive)\n"
        "- Objective: choose exactly one low-risk next command for discovery/probing\n"
        "Available command categories from catalog:\n"
        f"- command roots: {roots}\n"
        f"- ls scopes: {scopes}\n"
        "Current game/runtime state will be provided by the user message as JSON.\n"
        "Interpretation hints for state fields:\n"
        "- dfhack_ready: DFHack host readiness signal\n"
        "- dfhack_prompt_count: observed DFHack prompt occurrences\n"
        "- has_floating_point_exception: crash marker; stay conservative if true\n"
        "- has_audio_errors: likely non-fatal host audio warnings\n"
        "- successful_commands and last_ok: recent control-loop outcome\n"
        "Return only valid JSON object with this exact schema:\n"
        '{"name":"...","argv":["..."],"reason":"...","type":"dfhack"}\n'
        "Rules:\n"
        "- type must be dfhack\n"
        "- argv must be a non-empty tokenized command\n"
        "- prefer low-risk commands like ls/help/tags when uncertain\n"
        "- no markdown, no prose outside JSON"
    )


def _response_text(resp: Any) -> str:
    parts: List[str] = []
    for block in getattr(resp, "content", []):
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def _parse_action_json(text: str) -> Dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start : end + 1])
    raise ValueError("No JSON object found in model response")


def _action_from_obj(obj: Dict[str, Any]) -> Action:
    name = str(obj.get("name", "")).strip()
    reason = str(obj.get("reason", "")).strip()
    action_type = str(obj.get("type", "dfhack")).strip() or "dfhack"
    argv_raw = obj.get("argv", [])
    if not isinstance(argv_raw, list):
        raise ValueError("argv must be a list")
    argv = [str(x).strip() for x in argv_raw if str(x).strip()]
    if not name or not reason or not argv:
        raise ValueError("name/reason/argv are required")
    return Action(name=name, argv=argv, reason=reason, type=action_type)


def choose_action_llm(state: Dict[str, Any], step: int) -> Action:
    """Choose next action via Claude; fallback to rule policy on errors."""

    fallback = choose_action(state, step)
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return fallback

    try:
        import anthropic

        categories = _catalog_categories(load_catalog())
        system = _build_system_prompt(categories)
        user_payload = {
            "step": step,
            "runtime_state": state,
        }

        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=MODEL_NAME,
            max_tokens=300,
            temperature=0,
            system=system,
            messages=[{"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}],
        )

        text = _response_text(resp)
        obj = _parse_action_json(text)
        action = _action_from_obj(obj)
        if action.type != "dfhack":
            return fallback
        return action
    except Exception:
        return fallback
