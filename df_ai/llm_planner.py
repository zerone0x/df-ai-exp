"""LLM-based action planner supporting OpenAI and Anthropic APIs."""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

from .policy import Action
from .prompts import SYSTEM_PROMPT, format_catalog, format_state

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_OPENAI = "gpt-4o"
_DEFAULT_MODEL_ANTHROPIC = "claude-sonnet-4-20250514"


def _detect_backend() -> str:
    """Detect which LLM backend to use based on available env vars."""
    if os.environ.get("OPENAI_API_KEY"):
        return "openai"
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "anthropic"
    return "openai"  # default


def _get_model() -> str:
    explicit = os.environ.get("DF_AI_MODEL")
    if explicit:
        return explicit
    backend = _detect_backend()
    if backend == "openai":
        return _DEFAULT_MODEL_OPENAI
    return _DEFAULT_MODEL_ANTHROPIC


def _get_openai_client():
    try:
        import openai
    except ImportError:
        logger.error("openai package not installed: pip install openai")
        return None

    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        logger.error("OPENAI_API_KEY not set")
        return None
    return openai.OpenAI(api_key=key)


def _get_anthropic_client():
    try:
        import anthropic
    except ImportError:
        logger.error("anthropic package not installed: pip install anthropic")
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    if not api_key and not auth_token:
        logger.error("ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN not set")
        return None
    return anthropic.Anthropic(
        api_key=api_key or None,
        auth_token=auth_token or None,
    )


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


def _strip_fences(text: str) -> str:
    """Remove markdown code fences if present."""
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines).strip()
    return text


class LLMPlanner:
    """Stateless planner that asks an LLM for the next action."""

    def __init__(self, model: str | None = None, backend: str | None = None):
        self.backend = backend or _detect_backend()
        self.model = model or _get_model()
        self._client = None

    @property
    def client(self):
        if self._client is None:
            if self.backend == "openai":
                self._client = _get_openai_client()
            else:
                self._client = _get_anthropic_client()
        return self._client

    def _call_openai(self, user_msg: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=256,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_msg},
            ],
        )
        return response.choices[0].message.content or ""

    def _call_anthropic(self, user_msg: str) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=256,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        return response.content[0].text if response.content else ""

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
            if self.backend == "openai":
                text = self._call_openai(user_msg)
            else:
                text = self._call_anthropic(user_msg)
        except Exception:
            logger.exception("LLM API call failed (%s)", self.backend)
            return None

        text = _strip_fences(text.strip())

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.error("LLM returned non-JSON: %s", text[:200])
            return None

        return _validate_action(data)
