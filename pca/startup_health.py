from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any
from urllib import error, request

from .evaluator import ContinuityEvaluator
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .missions import MissionStatus, mission_briefs_from_events, open_mission
from .model_adapter import model_environment_diagnostic
from .state import derive_current_claim, record_claim_if_changed
from .steward_inbox import steward_inbox


STALE_INBOX_DAYS = 7


def startup_health(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> dict[str, Any]:
    claim, _, reasons = derive_current_claim(ledger, manifest)
    evaluation = ContinuityEvaluator().evaluate(
        manifest=manifest,
        events=ledger.events(),
        chain_valid=ledger.verify_chain(),
    )
    items = steward_inbox(ledger)
    high_items = [item for item in items if item.severity in {"high", "critical"}]
    stale_items = [
        item for item in items if _age_days(item.created_at) >= STALE_INBOX_DAYS
    ]
    missions = mission_briefs_from_events(ledger.events())
    open_missions = [
        brief for brief in missions if brief.mission.status == MissionStatus.OPEN
    ]
    model = model_environment_diagnostic()
    local_runtime = _local_model_runtime_status(model)
    problems: list[dict[str, Any]] = []
    safe_actions: list[dict[str, Any]] = []

    stale_required = [
        reason
        for reason in reasons
        if reason.startswith("required constraint evidence is stale:")
    ]
    missing_required = [
        reason
        for reason in reasons
        if reason.startswith("required constraint has no evidence:")
        or reason == "no continuity evidence has been recorded"
    ]
    if stale_required or missing_required:
        evidence_detail = "; ".join(stale_required + missing_required)
        evidence_title = (
            "Required continuity evidence is stale"
            if stale_required and not missing_required
            else "Required continuity evidence is missing"
            if missing_required and not stale_required
            else "Required continuity evidence needs refresh"
        )
        problems.append(
            {
                "code": (
                    "stale_required_evidence"
                    if stale_required and not missing_required
                    else "missing_required_evidence"
                    if missing_required and not stale_required
                    else "required_evidence_needs_refresh"
                ),
                "severity": "medium",
                "title": evidence_title,
                "detail": evidence_detail,
            }
        )
        safe_actions.append(
            {
                "action": "refresh_required_evidence",
                "label": "Refresh required evidence",
                "description": "Records fresh required constraint checks and updates the continuity claim.",
            }
        )

    if high_items:
        problems.append(
            {
                "code": "high_priority_steward_items",
                "severity": "high",
                "title": "High-priority steward items are open",
                "detail": f"{len(high_items)} high-priority item(s) need steward review.",
            }
        )
    elif items:
        problems.append(
            {
                "code": "open_steward_items",
                "severity": "medium",
                "title": "Steward items are open",
                "detail": f"{len(items)} steward item(s) need review.",
            }
        )
    if stale_items:
        problems.append(
            {
                "code": "stale_steward_items",
                "severity": "medium",
                "title": "Old steward review pressure exists",
                "detail": f"{len(stale_items)} item(s) are at least {STALE_INBOX_DAYS} days old.",
            }
        )

    if not open_missions:
        problems.append(
            {
                "code": "missing_active_mission",
                "severity": "medium",
                "title": "No active mission exists",
                "detail": "Open a mission so Lucien can orient daily work.",
            }
        )
        safe_actions.append(
            {
                "action": "open_coherence_research_mission",
                "label": "Open Coherence Physics mission",
                "description": "Creates one default governed research mission if no mission exists.",
            }
        )

    if model.get("local_model_configured") and local_runtime.get("available") is False:
        problems.append(
            {
                "code": "local_model_unavailable",
                "severity": "medium",
                "title": "Local model is unavailable",
                "detail": local_runtime.get("reason")
                or "Start Ollama or switch to Debug Mode.",
            }
        )

    status = _overall_status(problems)
    return {
        "status": status,
        "claim": claim,
        "identity_state": evaluation.state.value,
        "reasons": reasons,
        "open_steward_items": len(items),
        "high_priority_steward_items": len(high_items),
        "stale_steward_items": len(stale_items),
        "open_missions": len(open_missions),
        "local_model": {
            "provider": model.get("local_provider"),
            "model": model.get("local_model"),
            "configured": bool(model.get("local_model_configured")),
            "available": bool(local_runtime.get("available")),
            "reason": local_runtime.get("reason", ""),
        },
        "problems": problems,
        "safe_actions": safe_actions,
        "recommended_next_action": _recommended_next_action(problems),
    }


def apply_startup_health_fix(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    action: str,
    reason: str = "",
) -> dict[str, Any]:
    normalized = action.strip().lower().replace("-", "_")
    if normalized == "refresh_required_evidence":
        events = []
        for constraint in manifest.constraints:
            if constraint.required:
                events.append(
                    ledger.append(
                        "constraint.checked",
                        manifest.system_id,
                        {"constraint": constraint.name, "value": True},
                    )
                )
        claim = record_claim_if_changed(
            ledger,
            manifest,
            [event.event_hash for event in events],
        )
        return {
            "action": normalized,
            "events": [event.to_dict() for event in events],
            "claim_record": claim.to_dict() if claim else None,
            "health": startup_health(ledger, manifest),
        }
    if normalized == "open_coherence_research_mission":
        open_missions = [
            brief
            for brief in mission_briefs_from_events(ledger.events())
            if brief.mission.status == MissionStatus.OPEN
        ]
        if open_missions:
            return {
                "action": normalized,
                "created": False,
                "reason": "An open mission already exists.",
                "health": startup_health(ledger, manifest),
            }
        mission = open_mission(
            ledger,
            manifest.system_id,
            title="Coherence Physics Research Program",
            problem_statement=(
                "Continue researching, organizing, testing, and writing Coherence "
                "Physics material through governed missions, evidence review, and "
                "draft outputs."
            ),
            values=[
                "truth before comfort",
                "evidence-backed claims",
                "recoverable continuity",
            ],
            reason=reason or "startup health doctor opened default research mission",
        )
        return {
            "action": normalized,
            "created": True,
            "mission": mission.to_dict(),
            "health": startup_health(ledger, manifest),
        }
    raise ValueError(
        "startup health fix must be refresh_required_evidence or "
        "open_coherence_research_mission"
    )


def render_startup_health_text(health: dict[str, Any]) -> str:
    lines = [
        "Startup Health Doctor",
        f"Status: {health['status']}",
        f"Continuity: {health['claim']} / {health['identity_state']}",
        (
            "Steward Inbox: "
            f"{health['open_steward_items']} open / "
            f"{health['high_priority_steward_items']} high / "
            f"{health['stale_steward_items']} stale"
        ),
        f"Open missions: {health['open_missions']}",
        (
            "Local model: "
            f"{health['local_model'].get('provider') or 'none'} / "
            f"{health['local_model'].get('model') or 'none'} "
            f"({'ready' if health['local_model'].get('available') else 'not ready'})"
        ),
        "",
        f"Recommended next action: {health['recommended_next_action']}",
    ]
    if health["problems"]:
        lines.append("")
        lines.append("Problems:")
        for problem in health["problems"]:
            lines.append(
                f"- {problem['severity']}: {problem['title']} ({problem['detail']})"
            )
    if health["safe_actions"]:
        lines.append("")
        lines.append("Safe fixes:")
        for action in health["safe_actions"]:
            lines.append(f"- {action['action']}: {action['description']}")
    return "\n".join(lines)


def _overall_status(problems: list[dict[str, Any]]) -> str:
    severities = {problem["severity"] for problem in problems}
    if "critical" in severities or "high" in severities:
        return "blocked"
    if problems:
        return "needs_attention"
    return "ready"


def _recommended_next_action(problems: list[dict[str, Any]]) -> str:
    if not problems:
        return "Open Lucien and continue the active mission."
    codes = [problem["code"] for problem in problems]
    if "high_priority_steward_items" in codes:
        return "Review high-priority Steward Inbox items first."
    if (
        "stale_required_evidence" in codes
        or "missing_required_evidence" in codes
        or "required_evidence_needs_refresh" in codes
    ):
        return "Refresh required continuity evidence."
    if "missing_active_mission" in codes:
        return "Open a mission before using Lucien for work."
    if "local_model_unavailable" in codes:
        return "Start Ollama or switch to Debug Mode."
    return "Review Startup Health Doctor problems."


def _age_days(created_at: str) -> int:
    if not created_at:
        return 0
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - created).days)


def _local_model_runtime_status(diagnostic: dict[str, Any]) -> dict[str, Any]:
    base_url = str(diagnostic.get("local_base_url") or "http://127.0.0.1:11434").rstrip("/")
    model = str(diagnostic.get("local_model") or "")
    if not diagnostic.get("local_model_configured"):
        return {
            "available": False,
            "reason": "Local model is not configured.",
            "model_present": False,
        }
    try:
        with request.urlopen(f"{base_url}/api/tags", timeout=0.35) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {
            "available": False,
            "reason": "Local model unavailable. Start Ollama or switch to Debug Mode.",
            "error": exc.__class__.__name__,
            "model_present": False,
        }
    model_names = {str(item.get("name", "")) for item in payload.get("models", [])}
    model_present = model in model_names
    return {
        "available": model_present,
        "reason": "ready" if model_present else f"Model {model} is not installed in Ollama.",
        "model_present": model_present,
        "model_count": len(model_names),
    }
