"""Structured session logger for all DF-AI operations.

Every interaction with DFHack — scripted or interactive — goes through this
logger so we have a complete, queryable record of what happened.

Usage:

    from df_ai.session_log import SessionLog

    log = SessionLog("embark")          # creates logs/embark_<ts>.jsonl
    log.record("select-start-playing",
               action={"type": "keystroke", "key": "Return"},
               focus_before="title",
               focus_after="choose_start_site")
    log.close()

Or as a context manager:

    with SessionLog("phase1") as log:
        log.record("dig-farm", commands=[...], state_before={...})
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


class SessionLog:
    """Append-only JSONL logger for a DF-AI session."""

    def __init__(self, name: str, logs_dir: Path | None = None):
        d = logs_dir or _LOGS_DIR
        d.mkdir(parents=True, exist_ok=True)
        ts = int(time.time())
        self.path = d / f"{name}_{ts}.jsonl"
        self._fp = self.path.open("w", encoding="utf-8")
        self._step_idx = 0

    # -- core API ----------------------------------------------------------

    def record(self, step: str, **fields: Any) -> dict[str, Any]:
        """Write one log entry.  Returns the entry dict."""
        entry: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "seq": self._step_idx,
            "step": step,
        }
        entry.update(fields)
        self._fp.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._fp.flush()
        self._step_idx += 1
        return entry

    # -- convenience helpers -----------------------------------------------

    def record_command(
        self,
        step: str,
        command: list[str],
        *,
        ok: bool,
        stdout: str = "",
        duration: float = 0.0,
        **extra: Any,
    ) -> dict[str, Any]:
        """Shorthand for logging a single dfhack command."""
        return self.record(
            step,
            command=command,
            ok=ok,
            stdout_preview=stdout[:500] if stdout else "",
            duration=duration,
            **extra,
        )

    def record_keystroke(
        self,
        step: str,
        key: str,
        *,
        focus_before: str = "",
        focus_after: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        """Shorthand for logging a keystroke action."""
        return self.record(
            step,
            action={"type": "keystroke", "key": key, "method": "xdotool"},
            focus_before=focus_before,
            focus_after=focus_after,
            **extra,
        )

    # -- lifecycle ---------------------------------------------------------

    def close(self) -> None:
        if self._fp and not self._fp.closed:
            self._fp.close()

    def __enter__(self) -> SessionLog:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"SessionLog({self.path})"
