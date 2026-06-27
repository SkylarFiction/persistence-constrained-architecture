from __future__ import annotations

from pca import MemoryCard, SelfModel


def memory_cards_from_self_model(self_model: SelfModel) -> list[MemoryCard]:
    cards = []
    for record in self_model.by_kind.get("memory", []):
        cards.append(
            MemoryCard(
                memory_id=f"mem_{str(record['growth_id']).removeprefix('growth_')}",
                identity_id=self_model.identity_id,
                source_growth_id=str(record["growth_id"]),
                summary_sha256=str(record["summary_sha256"]),
                summary_length=int(record["summary_length"]),
                evidence_refs=[str(ref) for ref in record["evidence_refs"]],
                identity_impact=str(record["identity_impact"]),
                confidence=_confidence_for_impact(str(record["identity_impact"])),
                effective_confidence=_confidence_for_impact(str(record["identity_impact"])),
                signal_score=0.0,
                reinforcement_count=0,
                contradiction_count=0,
                stale_signal_count=0,
                created_at=str(record["accepted_at"]),
                last_confirmed=str(record["accepted_at"]),
                continuity_claim_at_acceptance=str(
                    record.get("acceptance_continuity_claim") or "not_recorded"
                ),
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
