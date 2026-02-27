"""LLM-based action planner using Anthropic Claude API."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .policy import Action
from .prompts import SYSTEM_PROMPT, format_catalog, format_state

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-20250514"


def _get_model() -> str:
    return os.environ.get("DF_AI_MODEL", _DEFAULT_MODEL)


def _get_client():  # -> anthropic.Anthropic | None
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed: pip install anthropic")
        return None

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        logger.error("ANTHROPIC_API_KEY not set")
        return None
    return anthropic.Anthropic(api_key=key)


# Commands that should never be executed via LLM suggestions.
_BLOCKED_COMMANDS = {"die", "kill-lua", "quickfort"}


def _validate_action(data: Dict[str, Any]) -> Optional[Action]:
    """Parse and validate LLM JSON output into an Action."""

    if data.get("done"):
        return Action(name="llm_done", argv=[], reason=data.get("reason", "done"), type="done")

    name = str(data.get("name", "llm_action"))
    argv = data.get("argv", [])
    action_type = str(data.get("type", "dfhack"))
    reason = str(data.get("reason", ""))

    if not isinstance(argv, list) or not argv:
        return None

    argv = [str(a) for a in argv]

    # Safety: block dangerous commands
    if action_type == "dfhack" and argv[0] in _BLOCKED_COMMANDS:
        logger.warning("LLM suggested blocked command: %s", argv)
        return None

    if action_type not in ("dfhack", "keystroke"):
        return None

    return Action(name=name, argv=argv, reason=reason, type=action_type)


class LLMPlanner:
    """Stateless planner that asks Claude for the next action."""

    def __init__(self, model: str | None = None):
        self.model = model or _get_model()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = _get_client()
        return self._client

    def choose(
        self,
        state: Dict[str, Any],
        step: int,
        *,
        goal: str = "",
        catalog: Dict[str, Any] | None = None,
        history: List[Dict[str, Any]] | None = None,
    ) -> Optional[Action]:
        """Ask the LLM for the next action. Returns None on failure."""

        client = self.client
        if client is None:
            return None

        catalog_text = format_catalog(catalog or {})
        user_msg = format_state(
            state=state,
            goal=goal,
            catalog_summary=catalog_text,
            history=history or [],
            step=step,
        )

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=256,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
        except Exception:
            logger.exception("Anthropic API call failed")
            return None

        text = response.content[0].text.strip() if response.content else ""

        # Strip markdown fences if present
        if text.startswith("```"):
            lines = text.splitlines()
            lines = [l for l in lines if not l.startswith("```")]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.error("LLM returned non-JSON: %s", text[:200])
            return None

        return _validate_action(data)
