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

    return {
        "mission_id": mission_id,
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


def render_review_queue_text(result: dict[str, Any]) -> str:
    lines = [
        f"Review Queue - mission {result.get('mission_id')}",
        f"Total pending items: {result.get('total_pending_items', 0)}",
        "",
    ]

    raw_evidence = result.get("raw_evidence") or []
    lines.append(f"Raw evidence awaiting review ({len(raw_evidence)}):")
    if raw_evidence:
        for item in raw_evidence:
            lines.append(
                f"  - {item['evidence_id']} "
                f"({item.get('source_type') or 'unknown type'}, "
                f"confidence={item.get('confidence') or 'unknown'})"
            )
            lines.append(f"    {item['command']}")
    else:
        lines.append("  - none")

    malformed_notes = result.get("malformed_source_notes") or []
    lines.extend(["", f"Malformed source notes needing manual verification ({len(malformed_notes)}):"])
    if malformed_notes:
        for item in malformed_notes:
            lines.append(f"  - {item['note_id']} ({item.get('source_path')}, {item.get('locator')})")
            lines.append(f"    {item['command']}")
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
