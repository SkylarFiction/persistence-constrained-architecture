from __future__ import annotations

from typing import Any

from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .missions import mission_briefs_from_events
from .paper_finish_plan import paper_finish_plan_for_mission
from .paper_readiness import paper_readiness_for_mission
from .source_notes import review_source_note, source_notes_for_mission


def evidence_review_desk(
    ledger: ContinuityLedger,
    mission_id: str | None = None,
    *,
    limit: int = 8,
) -> dict[str, Any]:
    """Return a focused review surface for turning source notes into reviewed support.

    This is a derived view over source notes, claim-source links, and paper
    readiness. It does not duplicate evidence records and does not mark anything
    reviewed by itself.
    """
    selected_mission_id = mission_id or _latest_mission_id(ledger)
    if not selected_mission_id:
        return {
            "status": "no_mission",
            "mission_id": None,
            "items": [],
            "counts": {},
            "recommended_action": "Open or seed a research mission first.",
        }
    readiness = paper_readiness_for_mission(ledger, selected_mission_id)
    finish_plan = paper_finish_plan_for_mission(
        ledger,
        selected_mission_id,
        review_limit=limit,
    )
    notes = source_notes_for_mission(ledger.events(), selected_mission_id)
    items = _review_items(finish_plan.get("priority_source_links") or [], notes, limit)
    counts = {
        "source_notes": readiness.get("source_note_count", 0),
        "raw_source_notes": readiness.get("raw_source_note_count", 0),
        "reviewed_source_notes": readiness.get("reviewed_source_note_count", 0),
        "reviewed_source_links": readiness.get("reviewed_source_link_count", 0),
        "manual_verification_notes": readiness.get("malformed_note_count", 0),
        "external_sources": readiness.get("external_source_count", 0),
        "external_sources_reviewed": readiness.get("reviewed_external_source_count", 0),
    }
    if items:
        recommended_action = f"Review {len(items)} priority reader-ready source note(s)."
    elif counts["raw_source_notes"]:
        recommended_action = "No priority claim links are available; inspect remaining raw notes."
    elif counts["reviewed_source_notes"]:
        recommended_action = "Source notes have reviewed support; add/review external literature next."
    else:
        recommended_action = readiness.get("recommended_action") or "Gather source notes."
    return {
        "status": "ready" if items else "no_priority_items",
        "mission_id": selected_mission_id,
        "mission_title": readiness.get("mission_title"),
        "paper_status": readiness.get("plain_status") or readiness.get("status"),
        "recommended_action": recommended_action,
        "counts": counts,
        "items": items,
        "guardrail": (
            "Reviewing a source note records steward judgment over an extracted "
            "citation card. It does not certify the whole theory, replace external "
            "peer review, or alter source files."
        ),
    }


def review_evidence_note(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    note_id: str,
    review_status: str,
    *,
    reviewer: str = "steward",
    confidence: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """Alias around source-note review with paper-facing naming."""
    record = review_source_note(
        ledger,
        manifest,
        note_id=note_id,
        review_status=review_status,
        reviewer=reviewer,
        confidence=confidence,
        reason=reason,
    )
    return {
        "status": record.review_status,
        "source_note_review": record.to_dict(),
        "message": (
            f"Source note {note_id} marked {record.review_status}. "
            "Regenerate the paper to update reviewed-source-note counts."
        ),
    }


def render_evidence_review_desk_text(desk: dict[str, Any]) -> str:
    counts = desk.get("counts") or {}
    lines = [
        "Evidence Review Desk",
        f"mission: {desk.get('mission_title') or desk.get('mission_id') or 'none'}",
        f"status: {desk.get('paper_status') or desk.get('status')}",
        f"next: {desk.get('recommended_action') or 'none'}",
        "",
        "counts:",
        f"- source notes: {counts.get('source_notes', 0)}",
        f"- raw source notes: {counts.get('raw_source_notes', 0)}",
        f"- reviewed source notes: {counts.get('reviewed_source_notes', 0)}",
        f"- reviewed source links: {counts.get('reviewed_source_links', 0)}",
        f"- manual verification notes: {counts.get('manual_verification_notes', 0)}",
        f"- external sources reviewed: {counts.get('external_sources_reviewed', 0)} / {counts.get('external_sources', 0)}",
        "",
        "priority notes:",
    ]
    items = desk.get("items") or []
    if not items:
        lines.append("- none")
    for item in items:
        lines.extend(
            [
                f"- {item.get('note_id')} ({item.get('review_status')}, {item.get('link_strength')})",
                f"  claim: {item.get('claim_text') or item.get('claim_id')}",
                f"  source: {item.get('source_path')} / {item.get('locator')}",
                f"  summary: {item.get('summary')}",
                "  accept: "
                + f"python3 pca_cli.py evidence-review-note {item.get('note_id')} --accept --reason \"verified against source\"",
                "  reject: "
                + f"python3 pca_cli.py evidence-review-note {item.get('note_id')} --reject --reason \"does not support the claim\"",
                "  manual check: "
                + f"python3 pca_cli.py evidence-review-note {item.get('note_id')} --manual-check --reason \"needs clean source verification\"",
            ]
        )
    lines.extend(["", f"guardrail: {desk.get('guardrail') or ''}"])
    return "\n".join(lines)


def _review_items(
    priority_links: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    limit: int,
) -> list[dict[str, Any]]:
    notes_by_id = {str(note.get("note_id") or ""): note for note in notes}
    items: list[dict[str, Any]] = []
    for link in priority_links:
        note_id = str(link.get("note_id") or "")
        note = notes_by_id.get(note_id, {})
        if str(note.get("review_status") or link.get("review_status") or "raw") != "raw":
            continue
        items.append(
            {
                "note_id": note_id,
                "claim_id": link.get("claim_id"),
                "claim_text": link.get("claim_text"),
                "source_path": link.get("source_path") or note.get("source_path"),
                "locator": link.get("locator") or note.get("locator"),
                "summary": link.get("summary") or note.get("summary"),
                "relation": link.get("relation"),
                "link_strength": link.get("link_strength"),
                "matched_terms": link.get("matched_terms") or [],
                "review_status": str(note.get("review_status") or "raw"),
                "confidence": note.get("confidence"),
                "recommended_actions": ["accept", "reject", "manual_check"],
            }
        )
        if len(items) >= max(1, limit):
            break
    return items


def _latest_mission_id(ledger: ContinuityLedger) -> str | None:
    briefs = mission_briefs_from_events(ledger.events())
    if not briefs:
        return None
    note_mission_ids = {
        str(note.get("mission_id") or "")
        for note in (
            event.payload
            for event in ledger.events()
            if event.event_type == "source_note.extracted"
        )
    }
    for brief in reversed(briefs):
        if brief.mission.mission_id in note_mission_ids:
            return brief.mission.mission_id
    return briefs[-1].mission.mission_id
