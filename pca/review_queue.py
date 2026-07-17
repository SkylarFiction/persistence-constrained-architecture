from __future__ import annotations

from typing import Any

from .claim_source_links import claim_source_links
from .coherence_corpus import is_relevant_source_path
from .evidence_locker import evidence_for_target
from .external_literature import external_literature_for_mission
from .ledger import ContinuityLedger
from .mission_claim_map import mission_claim_map
from .research_pdf import _reader_facing_claim_entries, _source_note_reader_ready
from .source_notes import source_notes_for_mission

REVIEWER_PLACEHOLDER = "<your-name>"
DEFAULT_RENDER_LIMIT = 6


def review_queue_for_mission(ledger: ContinuityLedger, mission_id: str) -> dict[str, Any]:
    """Turn paper_readiness's blocker sentences into the actual items behind
    them, each with the exact review command to run. review_evidence,
    review_source_note, and review_external_literature already exist and are
    already wired into the CLI (evidence-review, source-note-review,
    external-literature-review) -- this does not add a new review mechanism,
    it makes the existing one discoverable and actionable instead of leaving
    a steward to guess which of N raw evidence IDs still needs a decision.
    Nothing here reviews, accepts, or rejects anything automatically: review
    is a human judgment call by this system's own design, not something a
    script should do on a mission's behalf.
    """
    events = ledger.events()

    linked_evidence = evidence_for_target(events, "mission", mission_id)
    raw_evidence_items: list[dict[str, Any]] = []
    for link in linked_evidence:
        evidence = link.get("evidence") or {}
        if str(evidence.get("review_status") or "raw") != "raw":
            continue
        evidence_id = str(evidence.get("evidence_id") or "")
        raw_evidence_items.append(
            {
                "evidence_id": evidence_id,
                "source_type": evidence.get("source_type"),
                "confidence": evidence.get("confidence"),
                "command": (
                    f"python3 pca_cli.py evidence-review {evidence_id} --accept "
                    f"--reviewer {REVIEWER_PLACEHOLDER}"
                ),
            }
        )

    # Must match the same relevance filter export_research_pdf/_paper_readiness
    # apply before scoring claim-source links, or this queue's counts silently
    # drift from the paper_readiness numbers it's supposed to explain.
    source_notes = [
        note
        for note in source_notes_for_mission(events, mission_id)
        if is_relevant_source_path(str(note.get("source_path") or ""))
    ]
    malformed_note_items: list[dict[str, Any]] = []
    for note in source_notes:
        if note.get("note_kind") != "claim_candidate":
            continue
        if _source_note_reader_ready(note):
            continue
        note_id = str(note.get("note_id") or "")
        malformed_note_items.append(
            {
                "note_id": note_id,
                "source_path": note.get("source_path"),
                "locator": note.get("locator"),
                "summary": note.get("summary"),
                "command": (
                    f"python3 pca_cli.py source-note-review {note_id} --dispute "
                    f"--reviewer {REVIEWER_PLACEHOLDER} "
                    '--reason "extraction damaged, needs manual verification against the source"'
                ),
            }
        )

    claim_map = mission_claim_map(ledger, mission_id)
    reader_claims = _reader_facing_claim_entries(claim_map)
    source_links = claim_source_links(reader_claims, source_notes)
    linked_claim_ids = {str(link.get("claim_id") or "") for link in source_links}
    unlinked_claim_items: list[dict[str, Any]] = []
    for claim in reader_claims:
        claim_id = str(claim.get("claim_item_id") or claim.get("claim_hash") or "")
        if claim_id in linked_claim_ids:
            continue
        unlinked_claim_items.append(
            {
                "claim_id": claim_id,
                "claim_text": claim.get("claim_text"),
                "note": (
                    "No reader-ready source note is linked yet -- needs a direct "
                    "citation added, not an automated review."
                ),
            }
        )

    external_literature = external_literature_for_mission(events, mission_id)
    external_literature_missing = len(external_literature) == 0
    external_unreviewed_items: list[dict[str, Any]] = [
        {
            "literature_id": item.get("literature_id"),
            "title": item.get("title"),
            "command": (
                f"python3 pca_cli.py external-literature-review {item.get('literature_id')} "
                f"--accept --reviewer {REVIEWER_PLACEHOLDER}"
            ),
        }
        for item in external_literature
        if str(item.get("review_status") or "raw") == "raw"
    ]

    total_pending_items = (
        len(raw_evidence_items)
        + len(malformed_note_items)
        + len(unlinked_claim_items)
        + len(external_unreviewed_items)
        + (1 if external_literature_missing else 0)
    )
    summary = {
        "raw_evidence": len(raw_evidence_items),
        "malformed_source_notes": len(malformed_note_items),
        "unlinked_claims": len(unlinked_claim_items),
        "external_literature_missing": external_literature_missing,
        "external_literature_unreviewed": len(external_unreviewed_items),
        "total_pending_items": total_pending_items,
    }
    priority_actions = _priority_actions(
        raw_evidence_items=raw_evidence_items,
        malformed_note_items=malformed_note_items,
        unlinked_claim_items=unlinked_claim_items,
        external_literature_missing=external_literature_missing,
        external_unreviewed_items=external_unreviewed_items,
    )

    return {
        "mission_id": mission_id,
        "summary": summary,
        "priority_actions": priority_actions,
        "raw_evidence": raw_evidence_items,
        "malformed_source_notes": malformed_note_items,
        "unlinked_claims": unlinked_claim_items,
        "external_literature_missing": external_literature_missing,
        "external_literature_unreviewed": external_unreviewed_items,
        "total_pending_items": total_pending_items,
        "governance": (
            "this command only surfaces what needs a human decision; it does not "
            "review, accept, or reject anything on its own"
        ),
    }


def _priority_actions(
    *,
    raw_evidence_items: list[dict[str, Any]],
    malformed_note_items: list[dict[str, Any]],
    unlinked_claim_items: list[dict[str, Any]],
    external_literature_missing: bool,
    external_unreviewed_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if external_literature_missing:
        actions.append(
            {
                "kind": "external_literature_missing",
                "severity": "high",
                "title": "Add at least one external scholarly source",
                "reason": "The paper cannot become final-review ready using only the local archive.",
                "command": "python3 pca_cli.py external-literature-add ...",
            }
        )
    elif external_unreviewed_items:
        item = external_unreviewed_items[0]
        actions.append(
            {
                "kind": "external_literature_review",
                "severity": "high",
                "title": f"Review external literature: {item.get('title') or item.get('literature_id')}",
                "reason": "External literature is attached but still raw.",
                "command": item.get("command"),
            }
        )
    for item in malformed_note_items[:3]:
        actions.append(
            {
                "kind": "source_note_review",
                "severity": "high",
                "title": f"Verify damaged source note {item.get('note_id')}",
                "reason": "Damaged extraction should be checked against the source before it supports the paper.",
                "command": item.get("command"),
            }
        )
    for item in unlinked_claim_items[:3]:
        actions.append(
            {
                "kind": "claim_source_link",
                "severity": "medium",
                "title": f"Link claim {item.get('claim_id')} to a reader-ready source note",
                "reason": str(item.get("claim_text") or "Claim needs direct support."),
                "command": "Review source notes and add or approve a direct claim-source link.",
            }
        )
    file_evidence = [
        item for item in raw_evidence_items
        if str(item.get("source_type") or "") == "file"
    ]
    for item in file_evidence[:3]:
        actions.append(
            {
                "kind": "evidence_review",
                "severity": "medium",
                "title": f"Review file evidence {item.get('evidence_id')}",
                "reason": "File evidence is more useful for a paper than mission-observation bookkeeping.",
                "command": item.get("command"),
            }
        )
    if not actions and raw_evidence_items:
        item = raw_evidence_items[0]
        actions.append(
            {
                "kind": "evidence_review",
                "severity": "low",
                "title": f"Review evidence {item.get('evidence_id')}",
                "reason": "Raw evidence remains before final-paper status.",
                "command": item.get("command"),
            }
        )
    return actions[:10]


def render_review_queue_text(result: dict[str, Any]) -> str:
    lines = [
        f"Review Queue - mission {result.get('mission_id')}",
        f"Total pending items: {result.get('total_pending_items', 0)}",
        "",
    ]
    summary = result.get("summary") or {}
    if summary:
        lines.extend(
            [
                "Summary:",
                f"- raw evidence: {summary.get('raw_evidence', 0)}",
                f"- malformed source notes: {summary.get('malformed_source_notes', 0)}",
                f"- unlinked claims: {summary.get('unlinked_claims', 0)}",
                f"- external literature missing: {'yes' if summary.get('external_literature_missing') else 'no'}",
                f"- unreviewed external literature: {summary.get('external_literature_unreviewed', 0)}",
                "",
            ]
        )

    priority_actions = result.get("priority_actions") or []
    lines.append(f"Priority next actions ({len(priority_actions)}):")
    if priority_actions:
        for index, item in enumerate(priority_actions, start=1):
            lines.append(
                f"  {index}. [{item.get('severity', 'unknown')}] "
                f"{item.get('title', item.get('kind', 'review item'))}"
            )
            if item.get("reason"):
                lines.append(f"     reason: {item['reason']}")
            if item.get("command"):
                lines.append(f"     {item['command']}")
    else:
        lines.append("  - none")
    lines.append("")

    raw_evidence = result.get("raw_evidence") or []
    lines.append(f"Raw evidence awaiting review ({len(raw_evidence)}):")
    if raw_evidence:
        for item in raw_evidence[:DEFAULT_RENDER_LIMIT]:
            lines.append(
                f"  - {item['evidence_id']} "
                f"({item.get('source_type') or 'unknown type'}, "
                f"confidence={item.get('confidence') or 'unknown'})"
            )
            lines.append(f"    {item['command']}")
        if len(raw_evidence) > DEFAULT_RENDER_LIMIT:
            lines.append(
                f"  - ... {len(raw_evidence) - DEFAULT_RENDER_LIMIT} more raw evidence item(s) hidden from text output"
            )
    else:
        lines.append("  - none")

    malformed_notes = result.get("malformed_source_notes") or []
    lines.extend(["", f"Malformed source notes needing manual verification ({len(malformed_notes)}):"])
    if malformed_notes:
        for item in malformed_notes[:DEFAULT_RENDER_LIMIT]:
            lines.append(f"  - {item['note_id']} ({item.get('source_path')}, {item.get('locator')})")
            lines.append(f"    {item['command']}")
        if len(malformed_notes) > DEFAULT_RENDER_LIMIT:
            lines.append(
                f"  - ... {len(malformed_notes) - DEFAULT_RENDER_LIMIT} more malformed note(s) hidden from text output"
            )
    else:
        lines.append("  - none")

    unlinked_claims = result.get("unlinked_claims") or []
    lines.extend(["", f"Claims without a source-note link ({len(unlinked_claims)}):"])
    if unlinked_claims:
        for item in unlinked_claims:
            lines.append(f"  - {item['claim_id']}: {item.get('claim_text')}")
            lines.append(f"    {item['note']}")
    else:
        lines.append("  - none")

    external_unreviewed = result.get("external_literature_unreviewed") or []
    lines.extend(["", f"External literature awaiting review ({len(external_unreviewed)}):"])
    if result.get("external_literature_missing"):
        lines.append(
            "  - none attached yet; add with: python3 pca_cli.py external-literature-add ..."
        )
    elif external_unreviewed:
        for item in external_unreviewed:
            lines.append(f"  - {item['literature_id']}: {item.get('title')}")
            lines.append(f"    {item['command']}")
    else:
        lines.append("  - none")

    lines.extend(["", "guardrail:", f"- {result.get('governance', '')}"])
    return "\n".join(lines)
