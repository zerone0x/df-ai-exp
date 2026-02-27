"""Policy layer: runtime state -> next dfhack action."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict, List


@dataclass
class Action:
    name: str
    argv: List[str]
    reason: str

    @property
    def display(self) -> str:
        return " ".join(self.argv)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["display"] = self.display
        return data


def choose_action(state: Dict[str, Any], step: int) -> Action:
    """Choose next action based on current runtime state.

    Phases:
    1) bootstrap: confirm command channel health
    2) discovery: enumerate useful command surface for fortress automation
    """

    ready = bool(state.get("dfhack_ready", False))
    fpe = bool(state.get("has_floating_point_exception", False))
    ok_count = int(state.get("successful_commands", 0))

    if not ready:
        return Action(
            name="bootstrap_probe",
            argv=["ls"],
            reason="DFHack readiness not confirmed yet; probing command channel.",
        )

    if fpe:
        return Action(
            name="fpe_safe_mode",
            argv=["help"],
            reason="FPE marker detected; stay on minimal command.",
        )

    # discovery curriculum: gather domain-specific command surface (no side effects)
    discovery = [
        ("probe_tags", ["tags"], "Collect command taxonomy."),
        ("list_fort", ["ls", "fort"], "Find fortress-relevant commands."),
        ("list_design", ["ls", "design"], "Find designation/build planning commands."),
        ("list_auto", ["ls", "auto"], "Find automation-oriented commands."),
        ("help_quickfort", ["help", "quickfort"], "Inspect blueprint execution interface."),
        ("help_blueprint", ["help", "blueprint"], "Inspect blueprint capture interface."),
    ]

    # First few ready steps: run discovery curriculum; then cycle cheap probes.
    if ok_count <= len(discovery) + 1:
        idx = min(max(ok_count - 1, 0), len(discovery) - 1)
        name, argv, reason = discovery[idx]
        return Action(name=name, argv=argv, reason=reason)

    steady = [
        ("probe_ls", ["ls"], "Keep command channel responsive."),
        ("probe_help", ["help"], "Keep concise help output flowing."),
        ("probe_tags", ["tags"], "Refresh taxonomy snapshot."),
    ]
    name, argv, reason = steady[step % len(steady)]
    return Action(name=name, argv=argv, reason=reason)
