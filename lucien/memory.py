from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pca import SelfModel


@dataclass(frozen=True)
class MemoryCard:
    card_id: str
    kind: str
    summary_sha256: str
    summary_length: int
    identity_impact: str
    evidence_refs: list[str]
    confidence: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "kind": self.kind,
            "summary_sha256": self.summary_sha256,
            "summary_length": self.summary_length,
            "identity_impact": self.identity_impact,
            "evidence_refs": self.evidence_refs,
            "confidence": self.confidence,
            "reason": self.reason,
        }


def memory_cards_from_self_model(self_model: SelfModel) -> list[MemoryCard]:
    cards = []
    for kind, records in self_model.by_kind.items():
        for record in records:
            cards.append(
                MemoryCard(
                    card_id=str(record["growth_id"]),
                    kind=kind,
                    summary_sha256=str(record["summary_sha256"]),
                    summary_length=int(record["summary_length"]),
                    identity_impact=str(record["identity_impact"]),
                    evidence_refs=[str(ref) for ref in record["evidence_refs"]],
                    confidence=_confidence_for_impact(str(record["identity_impact"])),
                    reason=str(record["reason"]),
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
