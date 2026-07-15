from __future__ import annotations

from pathlib import Path
from typing import Any
import re

from .claim_source_links import claim_source_links
from .coherence_corpus import (
    coherence_corpus_index_records_from_events,
    is_relevant_source_path,
)
from .external_literature import external_literature_for_mission
from .ledger import ContinuityLedger
from .mission_claim_map import mission_claim_map
from .missions import mission_briefs_from_events
from .source_notes import source_notes_for_mission


def paper_readiness_for_mission(
    ledger: ContinuityLedger,
    mission_id: str,
) -> dict[str, Any]:
    """Return the current final-paper readiness state for a mission.

    This is a derived view over ledger state. It does not create, review, or
    promote evidence; it only explains whether the paper can honestly be called
    ready and what the next blocking action is.
    """
    claim_map = mission_claim_map(ledger, mission_id)
    reader_claims = reader_facing_claim_entries(claim_map)
    source_notes = [
        annotate_source_note_quality(note)
        for note in source_notes_for_mission(ledger.events(), mission_id)
        if is_relevant_source_path(str(note.get("source_path") or ""))
    ]
    source_links = claim_source_links(reader_claims, source_notes)
    corpus_sources = corpus_sources_for_mission(ledger, mission_id)
    external_literature = external_literature_for_mission(ledger.events(), mission_id)
    readiness = compute_paper_readiness(
        claim_map=claim_map,
        reader_claims=reader_claims,
        source_links=source_links,
        source_notes=source_notes,
        corpus_sources=corpus_sources,
        external_literature=external_literature,
    )
    readiness["mission_id"] = mission_id
    readiness["mission_title"] = claim_map.get("mission_title")
    readiness["source_note_count"] = len(source_notes)
    readiness["reviewed_source_note_count"] = sum(
        1 for note in source_notes if str(note.get("review_status") or "") == "reviewed"
    )
    readiness["raw_source_note_count"] = sum(
        1 for note in source_notes if str(note.get("review_status") or "raw") == "raw"
    )
    readiness["claim_source_links"] = source_links
    readiness["external_literature"] = external_literature
    readiness["external_source_count"] = len([
        item for item in external_literature
        if str(item.get("review_status") or "raw") != "rejected"
    ])
    readiness["reviewed_external_source_count"] = len([
        item for item in external_literature
        if str(item.get("review_status") or "") == "reviewed"
    ])
    readiness["recommended_action"] = recommended_paper_action(readiness)
    readiness["buttons"] = [
        {"id": "gather_sources", "label": "Gather Sources"},
        {"id": "review_source_notes", "label": "Review Source Notes"},
        {"id": "check_readiness", "label": "Check Paper Readiness"},
        {"id": "generate_final_paper", "label": "Generate Final Paper"},
        {"id": "open_paper_folder", "label": "Open Paper Folder"},
    ]
    return readiness


def compute_paper_readiness(
    *,
    claim_map: dict[str, Any],
    reader_claims: list[dict[str, Any]],
    source_links: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
    corpus_sources: list[dict[str, Any]],
    external_literature: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    external_literature = external_literature or []
    reader_claim_ids = {
        str(entry.get("claim_item_id") or entry.get("claim_hash") or "")
        for entry in reader_claims
    }
    linked_claim_ids = {str(link.get("claim_id") or "") for link in source_links}
    unlinked_claim_count = len(reader_claim_ids - linked_claim_ids)
    reviewed_evidence_count = int(claim_map.get("reviewed_evidence_count", 0) or 0)
    malformed_note_count = sum(
        1
        for note in source_notes
        if note.get("note_kind") == "claim_candidate"
        and note.get("note_quality") != "reader_ready"
    )
    reviewed_source_links = [
        link for link in source_links
        if str(link.get("review_status") or "") == "reviewed"
    ]
    blockers: list[str] = []
    if reviewed_evidence_count == 0 and not reviewed_source_links:
        blockers.append("No source evidence has been steward-reviewed yet.")
    if unlinked_claim_count:
        blockers.append(f"{unlinked_claim_count} reader-facing claim(s) lack direct source-note links.")
    if malformed_note_count:
        blockers.append(f"{malformed_note_count} source note(s) require manual extraction verification.")
    external_count = len([
        item for item in external_literature
        if str(item.get("review_status") or "raw") != "rejected"
    ])
    reviewed_external_count = len([
        item for item in external_literature
        if str(item.get("review_status") or "") == "reviewed"
    ])
    if external_count == 0:
        blockers.append("No external scholarly literature review has been attached yet.")
    elif reviewed_external_count == 0:
        blockers.append("External scholarly literature is attached, but none has been steward-reviewed yet.")
    status = "draft_packet"
    if not blockers:
        status = "review_ready_manuscript"
    elif source_links:
        status = "evidence_linked_draft"
    plain_status = {
        "draft_packet": "Not ready: structured draft",
        "evidence_linked_draft": "Not ready: evidence-linked draft",
        "review_ready_manuscript": "Ready for human manuscript review",
    }[status]
    return {
        "status": status,
        "ready": status == "review_ready_manuscript",
        "plain_status": plain_status,
        "reader_claim_count": len(reader_claims),
        "source_link_count": len(source_links),
        "linked_claim_count": len(linked_claim_ids & reader_claim_ids),
        "unlinked_claim_count": unlinked_claim_count,
        "reviewed_source_link_count": len(reviewed_source_links),
        "external_source_count": external_count,
        "reviewed_external_source_count": reviewed_external_count,
        "reviewed_evidence_count": reviewed_evidence_count,
        "malformed_note_count": malformed_note_count,
        "blockers": blockers,
        "what_this_is": (
            "A governed research manuscript draft with traceable claims, "
            "source-note links, and explicit blockers."
        ),
        "what_this_is_not": (
            "Not a final scientific paper, not a peer-reviewed result, and not "
            "proof that Coherence Physics is established science."
        ),
        "next_actions": [
            "Review source notes and mark usable evidence as reviewed.",
            "Add direct source-note links for unlinked claims.",
            "Add external scholarly literature before calling this a final paper.",
            "Run the direct continuity experiment and report the result.",
        ],
    }


def paper_readiness_records(
    ledger: ContinuityLedger,
) -> dict[str, dict[str, Any]]:
    return {
        brief.mission.mission_id: paper_readiness_for_mission(
            ledger,
            brief.mission.mission_id,
        )
        for brief in mission_briefs_from_events(ledger.events())
    }


def render_paper_readiness_text(readiness: dict[str, Any]) -> str:
    lines = [
        "Paper Readiness",
        f"mission: {readiness.get('mission_title') or readiness.get('mission_id') or 'none'}",
        f"status: {readiness.get('plain_status') or readiness.get('status')}",
        f"ready: {'yes' if readiness.get('ready') else 'no'}",
        f"reader claims: {readiness.get('reader_claim_count', 0)}",
        f"linked claims: {readiness.get('linked_claim_count', 0)}",
        f"source notes reviewed: {readiness.get('reviewed_source_note_count', 0)} / {readiness.get('source_note_count', 0)}",
        f"reviewed source links: {readiness.get('reviewed_source_link_count', 0)}",
        f"malformed source notes: {readiness.get('malformed_note_count', 0)}",
        f"external sources reviewed: {readiness.get('reviewed_external_source_count', 0)} / {readiness.get('external_source_count', 0)}",
        f"next: {readiness.get('recommended_action') or 'none'}",
    ]
    blockers = readiness.get("blockers") or []
    if blockers:
        lines.append("blockers:")
        for blocker in blockers:
            lines.append(f"- {blocker}")
    else:
        lines.append("blockers: none")
    return "\n".join(lines)


def recommended_paper_action(readiness: dict[str, Any]) -> str:
    if not readiness.get("source_note_count"):
        return "Gather sources and extract source notes."
    if readiness.get("raw_source_note_count", 0):
        return "Review source notes before generating a final paper."
    if readiness.get("unlinked_claim_count", 0):
        return "Link or approve source support for unlinked claims."
    if readiness.get("malformed_note_count", 0):
        return "Fix or reject malformed source notes."
    if readiness.get("external_source_count", 0) == 0:
        return "Add external scholarly literature before final-paper status."
    if readiness.get("reviewed_external_source_count", 0) == 0:
        return "Review attached external literature before final-paper status."
    if readiness.get("ready"):
        return "Generate the final paper and inspect the PDF."
    return "Run paper readiness again after the current review work."


def reader_facing_claim_entries(claim_map: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        entry
        for entry in claim_map.get("entries", [])
        if entry.get("claim_type") != "mission_hypothesis"
    ]


def annotate_source_note_quality(note: dict[str, Any]) -> dict[str, Any]:
    annotated = dict(note)
    annotated["note_quality"] = (
        "reader_ready" if source_note_reader_ready(note) else "manual_verification"
    )
    return annotated


def source_note_reader_ready(note: dict[str, Any]) -> bool:
    if note.get("note_kind") != "claim_candidate":
        return False
    if not is_relevant_source_path(str(note.get("source_path") or "")):
        return False
    return reader_facing_extraction_quality(str(note.get("summary") or ""))["usable"]


def reader_facing_extraction_quality(text: str) -> dict[str, Any]:
    clean = str(text)
    reasons: list[str] = []
    if re.search(r"(?:/x[0-9A-Fa-f]{2}){2,}", clean):
        reasons.append("raw glyph code leakage")
    if re.search(r"\b(?:tau|rho|delta|grad|mu|alpha|beta|gamma)[A-Za-z]{3,}(?:\(|=|->|\b)", clean):
        reasons.append("malformed mathematical extraction")
    if clean.count("?") >= 3:
        reasons.append("replacement characters")
    return {"usable": not reasons, "reasons": reasons}


def corpus_sources_for_mission(
    ledger: ContinuityLedger,
    mission_id: str,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in coherence_corpus_index_records_from_events(ledger.events()):
        if record.get("mission_id") != mission_id:
            continue
        source_mode = str(record.get("source_mode") or "curated_roots")
        for group in ("indexed", "reused"):
            for item in record.get(group) or []:
                path = str(item.get("path") or "")
                if not path or not is_relevant_source_path(path):
                    continue
                key = (path, str(item.get("content_sha256") or ""))
                if key in seen:
                    continue
                seen.add(key)
                sources.append({**item, "source_mode": source_mode})
    return sources
