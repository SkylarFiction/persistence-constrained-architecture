from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

from .followups import FollowUpRecord
from .ledger import ContinuityEvent


@dataclass(frozen=True)
class ContinuityClaimRecord:
    claim_id: str
    identity_id: str
    claim: str
    source_event_ids: list[str]
    active_blockers: list[str]
    created_at: str
    supersedes_claim_id: str | None
    reason: str

    @classmethod
    def create(
        cls,
        identity_id: str,
        claim: str,
        source_event_ids: list[str],
        active_blockers: list[str],
        reason: str,
        supersedes_claim_id: str | None = None,
    ) -> "ContinuityClaimRecord":
        return cls(
            claim_id=f"claim_{uuid.uuid4()}",
            identity_id=identity_id,
            claim=claim,
            source_event_ids=source_event_ids,
            active_blockers=active_blockers,
            created_at=datetime.now(timezone.utc).isoformat(),
            supersedes_claim_id=supersedes_claim_id,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContinuityClaimRecord":
        return cls(
            claim_id=str(data["claim_id"]),
            identity_id=str(data["identity_id"]),
            claim=str(data["claim"]),
            source_event_ids=[str(item) for item in data.get("source_event_ids", [])],
            active_blockers=[str(item) for item in data.get("active_blockers", [])],
            created_at=str(data["created_at"]),
            supersedes_claim_id=data.get("supersedes_claim_id"),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "identity_id": self.identity_id,
            "claim": self.claim,
            "source_event_ids": self.source_event_ids,
            "active_blockers": self.active_blockers,
            "created_at": self.created_at,
            "supersedes_claim_id": self.supersedes_claim_id,
            "reason": self.reason,
        }


def claims_from_events(events: list[ContinuityEvent]) -> list[ContinuityClaimRecord]:
    return [
        ContinuityClaimRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "continuity_claim_record"
    ]


def current_claim_record(
    events: list[ContinuityEvent],
) -> ContinuityClaimRecord | None:
    claims = claims_from_events(events)
    if not claims:
        return None
    return claims[-1]


def claim_reason(claim: str, blockers: list[FollowUpRecord], base_reason: str) -> str:
    if claim == "continuity_break":
        failed = [
            blocker.followup_id
            for blocker in blockers
            if blocker.status.value == "failed"
        ]
        if failed:
            return "Continuity claim broke because follow-ups failed: " + ", ".join(failed)
    if blockers:
        return (
            "Continuity claim remains constrained by active follow-ups: "
            + ", ".join(blocker.followup_id for blocker in blockers)
        )
    return base_reason

