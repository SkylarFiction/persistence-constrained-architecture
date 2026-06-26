from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .growth import (
    GrowthKind,
    GrowthRecord,
    GrowthStatus,
    growth_records_from_events,
    growth_review_records_from_events,
)
from .ledger import ContinuityEvent


@dataclass(frozen=True)
class MemoryCard:
    memory_id: str
    identity_id: str
    source_growth_id: str
    summary_sha256: str
    summary_length: int
    evidence_refs: list[str]
    identity_impact: str
    confidence: float
    created_at: str
    last_confirmed: str
    continuity_claim_at_acceptance: str
    reason: str

    @classmethod
    def from_growth(
        cls,
        growth: GrowthRecord,
        continuity_claim_at_acceptance: str = "not_recorded",
    ) -> "MemoryCard":
        confirmed_at = growth.updated_at or growth.created_at
        claim = growth.acceptance_continuity_claim or continuity_claim_at_acceptance
        return cls(
            memory_id=f"mem_{growth.growth_id.removeprefix('growth_')}",
            identity_id=growth.identity_id,
            source_growth_id=growth.growth_id,
            summary_sha256=growth.summary_sha256,
            summary_length=growth.summary_length,
            evidence_refs=growth.evidence_refs,
            identity_impact=growth.identity_impact.value,
            confidence=_confidence_for_impact(growth.identity_impact.value),
            created_at=growth.created_at,
            last_confirmed=confirmed_at,
            continuity_claim_at_acceptance=claim,
            reason=growth.reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "identity_id": self.identity_id,
            "source_growth_id": self.source_growth_id,
            "summary_sha256": self.summary_sha256,
            "summary_length": self.summary_length,
            "evidence_refs": self.evidence_refs,
            "identity_impact": self.identity_impact,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "last_confirmed": self.last_confirmed,
            "continuity_claim_at_acceptance": self.continuity_claim_at_acceptance,
            "reason": self.reason,
        }


def memory_cards_from_events(
    events: list[ContinuityEvent],
    identity_id: str | None = None,
) -> list[MemoryCard]:
    review_claims = {
        review.growth_id: review.continuity_claim
        for review in growth_review_records_from_events(events)
        if review.growth_status_after == GrowthStatus.ACCEPTED
    }
    cards = []
    for growth in growth_records_from_events(events):
        if identity_id is not None and growth.identity_id != identity_id:
            continue
        if growth.kind != GrowthKind.MEMORY:
            continue
        if growth.status != GrowthStatus.ACCEPTED:
            continue
        cards.append(
            MemoryCard.from_growth(
                growth,
                continuity_claim_at_acceptance=review_claims.get(
                    growth.growth_id,
                    "not_recorded",
                ),
            )
        )
    return cards


def _confidence_for_impact(impact: str) -> float:
    values = {
        "low": 0.92,
        "medium": 0.82,
        "high": 0.68,
        "identity_defining": 0.5,
    }
    return values.get(impact, 0.6)
