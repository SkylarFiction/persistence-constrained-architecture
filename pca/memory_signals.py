from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger


class MemorySignalType(str, Enum):
    REINFORCED = "reinforced"
    CONTRADICTED = "contradicted"
    STALE = "stale"


@dataclass(frozen=True)
class MemorySignalRecord:
    signal_id: str
    identity_id: str
    memory_id: str
    signal_type: MemorySignalType
    confidence_delta: float
    reason: str
    evidence_refs: list[str] = field(default_factory=list)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @classmethod
    def create(
        cls,
        identity_id: str,
        memory_id: str,
        signal_type: str | MemorySignalType,
        reason: str = "",
        evidence_refs: list[str] | None = None,
        confidence_delta: float | None = None,
    ) -> "MemorySignalRecord":
        parsed_signal = _parse_signal_type(signal_type)
        return cls(
            signal_id=f"memory_signal_{uuid.uuid4()}",
            identity_id=identity_id,
            memory_id=memory_id,
            signal_type=parsed_signal,
            confidence_delta=(
                _default_delta(parsed_signal)
                if confidence_delta is None
                else float(confidence_delta)
            ),
            reason=reason,
            evidence_refs=evidence_refs or [],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MemorySignalRecord":
        return cls(
            signal_id=str(data["signal_id"]),
            identity_id=str(data["identity_id"]),
            memory_id=str(data["memory_id"]),
            signal_type=_parse_signal_type(data["signal_type"]),
            confidence_delta=float(data["confidence_delta"]),
            reason=str(data.get("reason", "")),
            evidence_refs=[str(item) for item in data.get("evidence_refs", [])],
            created_at=str(data["created_at"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "identity_id": self.identity_id,
            "memory_id": self.memory_id,
            "signal_type": self.signal_type.value,
            "confidence_delta": self.confidence_delta,
            "reason": self.reason,
            "evidence_refs": self.evidence_refs,
            "created_at": self.created_at,
        }


def record_memory_signal(
    ledger: ContinuityLedger,
    identity_id: str,
    memory_id: str,
    signal_type: str | MemorySignalType,
    reason: str = "",
    evidence_refs: list[str] | None = None,
    confidence_delta: float | None = None,
) -> MemorySignalRecord:
    record = MemorySignalRecord.create(
        identity_id=identity_id,
        memory_id=memory_id,
        signal_type=signal_type,
        reason=reason,
        evidence_refs=evidence_refs,
        confidence_delta=confidence_delta,
    )
    ledger.append("lucien.memory_signal_recorded", identity_id, record.to_dict())
    return record


def memory_signal_records_from_events(
    events: list[ContinuityEvent],
) -> list[MemorySignalRecord]:
    return [
        MemorySignalRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "lucien.memory_signal_recorded"
    ]


def _parse_signal_type(value: str | MemorySignalType) -> MemorySignalType:
    if isinstance(value, MemorySignalType):
        return value
    return MemorySignalType(str(value))


def _default_delta(signal_type: MemorySignalType) -> float:
    if signal_type == MemorySignalType.REINFORCED:
        return 0.04
    if signal_type == MemorySignalType.CONTRADICTED:
        return -0.18
    if signal_type == MemorySignalType.STALE:
        return -0.08
    return 0.0
