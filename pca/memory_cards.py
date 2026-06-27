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
from .memory_signals import MemorySignalRecord, memory_signal_records_from_events


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
    effective_confidence: float
    signal_score: float
    reinforcement_count: int
    contradiction_count: int
    stale_signal_count: int
    created_at: str
    last_confirmed: str
    continuity_claim_at_acceptance: str
    reason: str

    @classmethod
    def from_growth(
        cls,
        growth: GrowthRecord,
        continuity_claim_at_acceptance: str = "not_recorded",
        signals: list[MemorySignalRecord] | None = None,
    ) -> "MemoryCard":
        confirmed_at = growth.updated_at or growth.created_at
        claim = growth.acceptance_continuity_claim or continuity_claim_at_acceptance
        base_confidence = _confidence_for_impact(growth.identity_impact.value)
        memory_signals = signals or []
        signal_score = round(sum(signal.confidence_delta for signal in memory_signals), 3)
        return cls(
            memory_id=f"mem_{growth.growth_id.removeprefix('growth_')}",
            identity_id=growth.identity_id,
            source_growth_id=growth.growth_id,
            summary_sha256=growth.summary_sha256,
            summary_length=growth.summary_length,
            evidence_refs=growth.evidence_refs,
            identity_impact=growth.identity_impact.value,
            confidence=base_confidence,
            effective_confidence=_bounded_confidence(base_confidence + signal_score),
            signal_score=signal_score,
            reinforcement_count=_count_signals(memory_signals, "reinforced"),
            contradiction_count=_count_signals(memory_signals, "contradicted"),
            stale_signal_count=_count_signals(memory_signals, "stale"),
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
            "effective_confidence": self.effective_confidence,
            "signal_score": self.signal_score,
            "reinforcement_count": self.reinforcement_count,
            "contradiction_count": self.contradiction_count,
            "stale_signal_count": self.stale_signal_count,
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
    signals_by_memory_id: dict[str, list[MemorySignalRecord]] = {}
    for signal in memory_signal_records_from_events(events):
        signals_by_memory_id.setdefault(signal.memory_id, []).append(signal)
    cards = []
    for growth in growth_records_from_events(events):
        if identity_id is not None and growth.identity_id != identity_id:
            continue
        if growth.kind != GrowthKind.MEMORY:
            continue
        if growth.status != GrowthStatus.ACCEPTED:
            continue
        memory_id = f"mem_{growth.growth_id.removeprefix('growth_')}"
        cards.append(
            MemoryCard.from_growth(
                growth,
                continuity_claim_at_acceptance=review_claims.get(
                    growth.growth_id,
                    "not_recorded",
                ),
                signals=signals_by_memory_id.get(memory_id, []),
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


def _bounded_confidence(value: float) -> float:
    return round(min(0.99, max(0.0, value)), 2)


def _count_signals(signals: list[MemorySignalRecord], signal_type: str) -> int:
    return len([signal for signal in signals if signal.signal_type.value == signal_type])
