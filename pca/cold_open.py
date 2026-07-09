from __future__ import annotations

from typing import Any

from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .mission_onboarding import mission_onboarding_state
from .start_here import start_here_decision
from .startup_health import startup_health
from .workbench import workbench_status


def cold_open_report(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> dict[str, Any]:
    """Summarize the first action a user should take after opening Lucien."""
    health = startup_health(ledger, manifest)
    workbench = workbench_status(ledger, manifest)
    active_mission = workbench.get("active_mission") or None
    onboarding: dict[str, Any] = {}
    if active_mission and active_mission.get("mission_id"):
        onboarding[active_mission["mission_id"]] = mission_onboarding_state(
            ledger,
            active_mission["mission_id"],
        ).to_dict()
    status = {
        "startup_health": health,
        "workbench": workbench,
        "mission_onboarding": onboarding,
        "model_usage": {
            "latest_cost_usd": workbench.get("latest_cost_usd", 0),
        },
    }
    decision = start_here_decision(status)
    return {
        "decision": decision,
        "one_sentence": _one_sentence(decision),
        "one_action": decision.get("primary_label", "Ask What To Do Next"),
        "continuity": workbench.get("continuity_state", "unknown"),
        "output_gate": workbench.get("output_gate_mode", "unknown"),
        "active_mission": active_mission,
        "open_steward_items": workbench.get("open_steward_inbox_count", 0),
        "high_priority_steward_items": workbench.get("high_priority_inbox_count", 0),
        "stale_steward_items": health.get("stale_steward_items", 0),
        "local_model": health.get("local_model", {}),
        "startup_status": health.get("status", "unknown"),
    }


def render_cold_open_report_text(report: dict[str, Any]) -> str:
    mission = report.get("active_mission") or {}
    local = report.get("local_model") or {}
    lines = [
        "Lucien Cold Open",
        report.get("one_sentence", "Open Lucien and ask for the next safe step."),
        "",
        f"Do first: {report.get('one_action', 'Ask What To Do Next')}",
        f"Continuity: {report.get('continuity', 'unknown')} / output: {report.get('output_gate', 'unknown')}",
        (
            "Steward inbox: "
            f"{report.get('open_steward_items', 0)} open / "
            f"{report.get('high_priority_steward_items', 0)} high / "
            f"{report.get('stale_steward_items', 0)} stale"
        ),
        (
            "Mission: "
            f"{mission.get('title', 'none')} "
            f"({mission.get('phase', 'no phase')})"
        ),
        (
            "Local brain: "
            f"{local.get('provider') or 'none'} / {local.get('model') or 'none'} "
            f"({'ready' if local.get('available') else 'not ready'})"
        ),
    ]
    return "\n".join(lines)


def _one_sentence(decision: dict[str, Any]) -> str:
    title = str(decision.get("title") or "Lucien is ready.").strip()
    summary = str(decision.get("summary") or "").strip()
    if not summary:
        return title
    return f"{title}: {summary}"
