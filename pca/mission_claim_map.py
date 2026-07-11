from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .evidence_locker import evidence_for_target
from .ledger import ContinuityLedger
from .missions import MissionItemKind, mission_briefs_from_events, require_mission


@dataclass(frozen=True)
class MissionClaimMapEntry:
    claim_item_id: str
    claim_hash: str
    claim_status: str
    confidence: str
    evidence_count: int
    reviewed_evidence_count: int
    disputed_evidence_count: int
    stale_evidence_count: int
    support_status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_item_id": self.claim_item_id,
            "claim_hash": self.claim_hash,
            "claim_status": self.claim_status,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "reviewed_evidence_count": self.reviewed_evidence_count,
            "disputed_evidence_count": self.disputed_evidence_count,
            "stale_evidence_count": self.stale_evidence_count,
            "support_status": self.support_status,
        }


def mission_claim_map(
    ledger: ContinuityLedger,
    mission_id: str,
) -> dict[str, Any]:
    mission = require_mission(ledger.events(), mission_id)
    brief = next(
        brief for brief in mission_briefs_from_events(ledger.events())
        if brief.mission.mission_id == mission_id
    )
    linked_evidence = evidence_for_target(ledger.events(), "mission", mission_id)
    evidence_statuses = [
        str((item.get("evidence") or {}).get("review_status", "raw"))
        for item in linked_evidence
    ]
    entries = [
        MissionClaimMapEntry(
            claim_item_id=item.item_id,
            claim_hash=item.summary_sha256,
            claim_status=item.status,
            confidence=item.confidence,
            evidence_count=len(linked_evidence),
            reviewed_evidence_count=evidence_statuses.count("reviewed"),
            disputed_evidence_count=evidence_statuses.count("disputed"),
            stale_evidence_count=evidence_statuses.count("stale"),
            support_status=_support_status(evidence_statuses),
        )
        for item in brief.items
        if item.kind == MissionItemKind.HYPOTHESIS
    ]
    return {
        "mission_id": mission_id,
        "mission_title": mission.title,
        "claim_count": len(entries),
        "evidence_count": len(linked_evidence),
        "reviewed_evidence_count": evidence_statuses.count("reviewed"),
        "raw_evidence_count": evidence_statuses.count("raw"),
        "disputed_evidence_count": evidence_statuses.count("disputed"),
        "stale_evidence_count": evidence_statuses.count("stale"),
        "unsupported_claim_count": sum(
            1 for entry in entries if entry.support_status == "unsupported"
        ),
        "entries": [entry.to_dict() for entry in entries],
    }


def mission_claim_maps(ledger: ContinuityLedger) -> dict[str, dict[str, Any]]:
    return {
        brief.mission.mission_id: mission_claim_map(ledger, brief.mission.mission_id)
        for brief in mission_briefs_from_events(ledger.events())
    }


def _support_status(evidence_statuses: list[str]) -> str:
    if not evidence_statuses:
        return "unsupported"
    if any(status == "disputed" for status in evidence_statuses):
        return "disputed"
    if any(status == "reviewed" for status in evidence_statuses):
        return "reviewed_support"
    if any(status == "stale" for status in evidence_statuses):
        return "stale_support"
    return "raw_support"
