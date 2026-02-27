"""Lightweight expectation verifier for goal execution."""

from __future__ import annotations

from typing import Any, Dict, Tuple


def verify_expectation(expect: str | None, result: Dict[str, Any], runtime_state: Dict[str, Any]) -> Tuple[bool, str]:
    """Verify whether an execution result satisfies expectation.

    Supported expectations:
    - None / "ok": command returns ok=True
    - "contains:<text>": stdout contains text
    - "state:ready": runtime state reports dfhack_ready=True
    - "state:no_fpe": runtime state has no floating point exception marker
    """

    if not expect or expect == "ok":
        ok = bool(result.get("ok"))
        return ok, "ok" if ok else "command failed"

    if expect.startswith("contains:"):
        needle = expect.split(":", 1)[1]
        hay = str(result.get("stdout", ""))
        ok = needle in hay
        return ok, f"stdout contains '{needle}'" if ok else f"stdout missing '{needle}'"

    if expect == "state:ready":
        ok = bool(runtime_state.get("dfhack_ready"))
        return ok, "runtime ready" if ok else "runtime not ready"

    if expect == "state:no_fpe":
        ok = not bool(runtime_state.get("has_floating_point_exception"))
        return ok, "no fpe marker" if ok else "fpe marker detected"

    return False, f"unknown expectation: {expect}"
