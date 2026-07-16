from __future__ import annotations

from typing import Any

from .ledger import ContinuityLedger
from .paper_readiness import paper_readiness_for_mission
from .review_queue import review_queue_for_mission


def paper_finish_plan_for_mission(
    ledger: ContinuityLedger,
    mission_id: str,
    *,
    review_limit: int = 5,
) -> dict[str, Any]:
    """Summarize the smallest human-facing path from draft to paper.

    This is a derived view over paper readiness and the review queue. It does
    not approve, reject, link, or generate anything. The purpose is to keep the
    app usable when the raw queue contains dozens of ledger-backed review items.
    """
    readiness = paper_readiness_for_mission(ledger, mission_id)
    queue = review_queue_for_mission(ledger, mission_id)
    source_links = readiness.get("claim_source_links") or []
    priority_links = _priority_source_links(source_links, limit=review_limit)

    actions = _finish_actions(readiness, queue, priority_links)
    primary_action = next((action for action in actions if action["status"] != "done"), None)
    if primary_action is None:
        primary_action = {
            "id": "generate_final_paper",
            "label": "Generate Final Paper",
            "status": "ready",
            "reason": "All tracked blockers are clear.",
        }

    return {
        "mission_id": mission_id,
        "mission_title": readiness.get("mission_title"),
        "ready": bool(readiness.get("ready")),
        "plain_status": readiness.get("plain_status") or readiness.get("status"),
        "primary_action": primary_action,
        "actions": actions,
        "priority_source_links": priority_links,
        "counts": {
            "reader_claims": readiness.get("reader_claim_count", 0),
            "linked_claims": readiness.get("linked_claim_count", 0),
            "unlinked_claims": readiness.get("unlinked_claim_count", 0),
            "reviewed_source_links": readiness.get("reviewed_source_link_count", 0),
            "candidate_source_links": len(priority_links),
            "damaged_notes": len(queue.get("malformed_source_notes") or []),
            "raw_evidence": len(queue.get("raw_evidence") or []),
            "external_unreviewed": len(queue.get("external_literature_unreviewed") or []),
            "external_missing": 1 if queue.get("external_literature_missing") else 0,
            "total_queue_items": queue.get("total_pending_items", 0),
        },
        "why_this_exists": (
            "This checklist reduces the raw paper review queue to the next few "
            "human decisions most likely to improve the reader-facing paper."
        ),
        "governance": (
            "The checklist is advisory. Reviews, source additions, and paper "
            "generation still use the existing PCA gates."
        ),
    }


def render_paper_finish_plan_text(plan: dict[str, Any]) -> str:
    primary = plan.get("primary_action") or {}
    counts = plan.get("counts") or {}
    lines = [
        "Final Paper Checklist",
        f"mission: {plan.get('mission_title') or plan.get('mission_id') or 'none'}",
        f"status: {plan.get('plain_status') or 'unknown'}",
        f"primary action: {primary.get('label') or primary.get('id') or 'none'}",
        f"reason: {primary.get('reason') or 'none'}",
        "",
        "counts:",
        f"- reader claims: {counts.get('reader_claims', 0)}",
        f"- linked claims: {counts.get('linked_claims', 0)}",
        f"- unlinked claims: {counts.get('unlinked_claims', 0)}",
        f"- reviewed source links: {counts.get('reviewed_source_links', 0)}",
        f"- priority source links to inspect: {counts.get('candidate_source_links', 0)}",
        f"- damaged notes: {counts.get('damaged_notes', 0)}",
        f"- external missing: {counts.get('external_missing', 0)}",
        "",
        "steps:",
    ]
    for action in plan.get("actions") or []:
        lines.append(
            f"- [{action.get('status') or 'todo'}] "
            f"{action.get('label') or action.get('id')}: {action.get('reason') or ''}"
        )
    links = plan.get("priority_source_links") or []
    if links:
        lines.extend(["", "priority source links:"])
        for link in links:
            lines.append(
                f"- {link.get('note_id')} -> {link.get('claim_id')} "
                f"({link.get('link_strength')}, {link.get('relation')})"
            )
    lines.extend(["", f"guardrail: {plan.get('governance') or ''}"])
    return "\n".join(lines)


def _priority_source_links(
    source_links: list[dict[str, Any]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    seen_note_ids: set[str] = set()
    candidates: list[dict[str, Any]] = []
    for link in sorted(
        source_links,
        key=lambda item: (
            0 if str(item.get("review_status") or "raw") == "raw" else 1,
            -float(item.get("score") or 0),
            str(item.get("note_id") or ""),
        ),
    ):
        if str(link.get("review_status") or "raw") != "raw":
            continue
        if str(link.get("note_quality") or "reader_ready") != "reader_ready":
            continue
        note_id = str(link.get("note_id") or "")
        if not note_id or note_id in seen_note_ids:
            continue
        seen_note_ids.add(note_id)
        candidates.append(
            {
                "claim_id": link.get("claim_id"),
                "claim_text": link.get("claim_text"),
                "note_id": note_id,
                "source_path": link.get("source_path"),
                "locator": link.get("locator"),
                "relation": link.get("relation"),
                "link_strength": link.get("link_strength"),
                "matched_terms": link.get("matched_terms") or [],
                "summary": link.get("summary"),
                "review_action": {
                    "action": "review_source_note",
                    "note_id": note_id,
                    "status": "reviewed",
                    "reason": "accepted priority source link from Final Paper Checklist",
                },
            }
        )
        if len(candidates) >= max(1, limit):
            break
    return candidates


def _finish_actions(
    readiness: dict[str, Any],
    queue: dict[str, Any],
    priority_links: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    external_missing = bool(queue.get("external_literature_missing"))
    external_unreviewed = queue.get("external_literature_unreviewed") or []
    unlinked_count = int(readiness.get("unlinked_claim_count") or 0)
    damaged_count = len(queue.get("malformed_source_notes") or [])
    reviewed_source_links = int(readiness.get("reviewed_source_link_count") or 0)

    return [
        {
            "id": "review_priority_source_links",
            "label": "Review Priority Source Links",
            "status": "todo" if priority_links and reviewed_source_links == 0 else "done",
            "reason": (
                f"Inspect {len(priority_links)} reader-ready source note(s) tied to core claims."
                if priority_links and reviewed_source_links == 0
                else "At least one source link has already been reviewed, or no priority links are available."
            ),
        },
        {
            "id": "add_external_literature",
            "label": "Add External Literature",
            "status": "todo" if external_missing else "done",
            "reason": (
                "Attach at least one outside scholarly source before final-paper status."
                if external_missing
                else "External literature is attached."
            ),
        },
        {
            "id": "review_external_literature",
            "label": "Review External Literature",
            "status": "todo" if external_unreviewed else "done",
            "reason": (
                f"Review {len(external_unreviewed)} attached outside source(s)."
                if external_unreviewed
                else "No attached external literature is waiting for review."
            ),
        },
        {
            "id": "link_unlinked_claims",
            "label": "Link Unlinked Claims",
            "status": "todo" if unlinked_count else "done",
            "reason": (
                f"{unlinked_count} reader-facing claim(s) still need direct source support."
                if unlinked_count
                else "All reader-facing claims have at least one derived source link."
            ),
        },
        {
            "id": "verify_damaged_notes",
            "label": "Verify Damaged Notes",
            "status": "todo" if damaged_count else "done",
            "reason": (
                f"{damaged_count} source note(s) need manual extraction verification."
                if damaged_count
                else "No damaged source notes are blocking the paper."
            ),
        },
        {
            "id": "generate_final_paper",
            "label": "Generate Final Paper",
            "status": "ready" if readiness.get("ready") else "blocked",
            "reason": (
                "Readiness is clear; generate and inspect the reader-facing PDF."
                if readiness.get("ready")
                else "Generate after the checklist blockers above are cleared."
            ),
        },
    ]
