from __future__ import annotations

from dataclasses import dataclass

from .ledger import ContinuityEvent


@dataclass(frozen=True)
class LineageRecord:
    parent_id: str
    child_id: str
    reason: str
    event_hash: str
    timestamp: str

    def to_dict(self) -> dict[str, str]:
        return {
            "parent_id": self.parent_id,
            "child_id": self.child_id,
            "reason": self.reason,
            "event_hash": self.event_hash,
            "timestamp": self.timestamp,
        }


def lineage_records(events: list[ContinuityEvent]) -> list[LineageRecord]:
    records: list[LineageRecord] = []
    for event in events:
        if event.event_type != "identity.forked":
            continue
        child_id = event.payload.get("child_id")
        if not child_id:
            continue
        records.append(
            LineageRecord(
                parent_id=event.subject_id,
                child_id=str(child_id),
                reason=str(event.payload.get("fork_reason", "")),
                event_hash=event.event_hash,
                timestamp=event.timestamp,
            )
        )
    return records

