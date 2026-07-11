from __future__ import annotations

from typing import Any

from .evidence_locker import evidence_for_target
from .ledger import ContinuityLedger
from .mission_claim_map import mission_claim_map
from .missions import MissionStatus, mission_briefs_from_events, require_mission
from .research_sandbox import research_outputs_from_events
from .steward_inbox import steward_inbox


def research_review_desk(
    ledger: ContinuityLedger,
    mission_id: str | None = None,
) -> dict[str, Any]:
    mission = _select_mission(ledger, mission_id)
    if mission is None:
        return {
            "ready": False,
            "mission_id": None,
            "mission_title": None,
            "summary": "No open mission is available. Start a mission before reviewing research.",
            "next_action": "Start a mission.",
            "cards": _cards(0, 0, 0, 0, 0),
            "raw_evidence_ids": [],
            "output_ids": [],
            "review_items": [],
        }
    linked_evidence = evidence_for_target(ledger.events(), "mission", mission.mission_id)
    outputs = research_outputs_from_events(ledger.events(), mission.mission_id)
    claim_map = mission_claim_map(ledger, mission.mission_id)
    raw_evidence_ids = [
        str((item.get("evidence") or {}).get("evidence_id"))
        for item in linked_evidence
        if (item.get("evidence") or {}).get("review_status", "raw") == "raw"
    ]
    disputed_evidence_ids = [
        str((item.get("evidence") or {}).get("evidence_id"))
        for item in linked_evidence
        if (item.get("evidence") or {}).get("review_status") == "disputed"
    ]
    mission_items = [
        item.to_dict()
        for item in steward_inbox(ledger)
        if item.linked_target_id == mission.mission_id
        or mission.mission_id in item.reason
    ]
    unsupported = int(claim_map.get("unsupported_claim_count", 0) or 0)
    reviewed_evidence = int(claim_map.get("reviewed_evidence_count", 0) or 0)
    raw_evidence = int(claim_map.get("raw_evidence_count", 0) or 0)
    next_action = _next_action(
        outputs=len(outputs),
        raw_evidence=raw_evidence,
        disputed_evidence=len(disputed_evidence_ids),
        unsupported=unsupported,
        reviewed_evidence=reviewed_evidence,
        review_items=len(mission_items),
    )
    return {
        "ready": True,
        "mission_id": mission.mission_id,
        "mission_title": mission.title,
        "summary": (
            f"{mission.title}: {len(outputs)} research output(s), "
            f"{raw_evidence} raw evidence item(s), "
            f"{reviewed_evidence} reviewed evidence item(s)."
        ),
        "next_action": next_action,
        "cards": _cards(
            len(outputs),
            int(claim_map.get("claim_count", 0) or 0),
            raw_evidence,
            reviewed_evidence,
            len(mission_items),
        ),
        "claim_map": claim_map,
        "raw_evidence_ids": raw_evidence_ids,
        "disputed_evidence_ids": disputed_evidence_ids,
        "output_ids": [output.output_id for output in outputs],
        "latest_output": outputs[-1].to_dict() if outputs else None,
        "review_items": mission_items,
        "pdf_ready": bool(outputs),
        "safe_actions": [
            "run_research_autopilot",
            "review_raw_evidence",
            "save_research_pdf",
            "draft_paper_after_review",
        ],
        "will_not": [
            "accept claims as true automatically",
            "publish",
            "write final papers without review",
            "spend OpenAI credit unless Cloud Assist is explicitly enabled",
        ],
    }


def research_review_desks(ledger: ContinuityLedger) -> dict[str, dict[str, Any]]:
    return {
        brief.mission.mission_id: research_review_desk(ledger, brief.mission.mission_id)
        for brief in mission_briefs_from_events(ledger.events())
    }


def render_research_review_text(review: dict[str, Any]) -> str:
    lines = [
        "Research Review Desk",
        f"mission: {review.get('mission_title') or 'none'}",
        f"summary: {review.get('summary') or 'none'}",
        f"next: {review.get('next_action') or 'none'}",
    ]
    cards = review.get("cards") or {}
    for name, card in cards.items():
        lines.append(f"- {name}: {card.get('value')}")
    return "\n".join(lines)


def _select_mission(ledger: ContinuityLedger, mission_id: str | None):
    if mission_id:
        return require_mission(ledger.events(), mission_id)
    for brief in reversed(mission_briefs_from_events(ledger.events())):
        if brief.mission.status == MissionStatus.OPEN:
            return brief.mission
    return None


def _cards(
    outputs: int,
    claims: int,
    raw_evidence: int,
    reviewed_evidence: int,
    review_items: int,
) -> dict[str, dict[str, Any]]:
    return {
        "outputs": {"title": "Research Outputs", "value": outputs},
        "claims": {"title": "Claims", "value": claims},
        "raw_evidence": {"title": "Raw Evidence", "value": raw_evidence},
        "reviewed_evidence": {"title": "Reviewed Evidence", "value": reviewed_evidence},
        "review_items": {"title": "Review Items", "value": review_items},
    }


def _next_action(
    outputs: int,
    raw_evidence: int,
    disputed_evidence: int,
    unsupported: int,
    reviewed_evidence: int,
    review_items: int,
) -> str:
    if outputs == 0:
        return "Start today's research run."
    if disputed_evidence:
        return "Resolve disputed evidence before drafting conclusions."
    if raw_evidence:
        return "Review raw evidence, then export the research PDF."
    if unsupported:
        return "Gather or link evidence for unsupported claims."
    if review_items:
        return "Resolve mission review items."
    if reviewed_evidence:
        return "Create a paper draft from reviewed evidence."
    return "Export the research packet and decide the next source to gather."
