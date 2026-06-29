from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EvidenceSourceType(str, Enum):
    USER_STATEMENT = "user_statement"
    FILE = "file"
    WEB_SOURCE = "web_source"
    MISSION_OBSERVATION = "mission_observation"
    TOOL_OUTPUT = "tool_output"
    CHAT_TURN = "chat_turn"
    TEST_RESULT = "test_result"
    CODE_RESULT = "code_result"
    MANUAL_NOTE = "manual_note"


class EvidenceReviewStatus(str, Enum):
    RAW = "raw"
    REVIEWED = "reviewed"
    DISPUTED = "disputed"
    STALE = "stale"
    REJECTED = "rejected"


class EvidenceTargetType(str, Enum):
    MEMORY = "memory"
    MISSION = "mission"
    SKILL = "skill"
    CLAIM = "claim"


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    identity_id: str
    source_type: EvidenceSourceType
    source_hash: str
    summary_hash: str
    summary_length: int
    confidence: str
    review_status: EvidenceReviewStatus = EvidenceReviewStatus.RAW
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str | None = None
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        source_type: str | EvidenceSourceType,
        source: str,
        summary: str,
        confidence: str = "unknown",
        reason: str = "",
    ) -> "EvidenceRecord":
        return cls(
            evidence_id=f"evidence_{uuid.uuid4()}",
            identity_id=identity_id,
            source_type=EvidenceSourceType(str(source_type)),
            source_hash=_text_hash(source),
            summary_hash=_text_hash(summary),
            summary_length=len(summary),
            confidence=confidence,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceRecord":
        return cls(
            evidence_id=str(data["evidence_id"]),
            identity_id=str(data["identity_id"]),
            source_type=EvidenceSourceType(str(data["source_type"])),
            source_hash=str(data["source_hash"]),
            summary_hash=str(data["summary_hash"]),
            summary_length=int(data["summary_length"]),
            confidence=str(data.get("confidence", "unknown")),
            review_status=EvidenceReviewStatus(str(data.get("review_status", "raw"))),
            created_at=str(data["created_at"]),
            updated_at=data.get("updated_at"),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.evidence_id,
            "identity_id": self.identity_id,
            "source_type": self.source_type.value,
            "source_hash": self.source_hash,
            "summary_hash": self.summary_hash,
            "summary_length": self.summary_length,
            "confidence": self.confidence,
            "review_status": self.review_status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "reason": self.reason,
        }

    def with_review(
        self,
        status: str | EvidenceReviewStatus,
        confidence: str | None = None,
        reason: str = "",
    ) -> "EvidenceRecord":
        status_value = status.value if isinstance(status, EvidenceReviewStatus) else str(status)
        return EvidenceRecord(
            evidence_id=self.evidence_id,
            identity_id=self.identity_id,
            source_type=self.source_type,
            source_hash=self.source_hash,
            summary_hash=self.summary_hash,
            summary_length=self.summary_length,
            confidence=confidence or self.confidence,
            review_status=EvidenceReviewStatus(status_value),
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
            reason=reason or self.reason,
        )


@dataclass(frozen=True)
class EvidenceClaimRecord:
    claim_id: str
    identity_id: str
    statement_hash: str
    statement_length: int
    evidence_ids: list[str]
    confidence: str
    status: str = "proposed"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        statement: str,
        evidence_ids: list[str] | None = None,
        confidence: str = "unknown",
        status: str = "proposed",
        reason: str = "",
    ) -> "EvidenceClaimRecord":
        return cls(
            claim_id=f"claim_evidence_{uuid.uuid4()}",
            identity_id=identity_id,
            statement_hash=_text_hash(statement),
            statement_length=len(statement),
            evidence_ids=evidence_ids or [],
            confidence=confidence,
            status=status,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceClaimRecord":
        return cls(
            claim_id=str(data["claim_id"]),
            identity_id=str(data["identity_id"]),
            statement_hash=str(data["statement_hash"]),
            statement_length=int(data["statement_length"]),
            evidence_ids=[str(item) for item in data.get("evidence_ids", [])],
            confidence=str(data.get("confidence", "unknown")),
            status=str(data.get("status", "proposed")),
            created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "identity_id": self.identity_id,
            "statement_hash": self.statement_hash,
            "statement_length": self.statement_length,
            "evidence_ids": self.evidence_ids,
            "confidence": self.confidence,
            "status": self.status,
            "created_at": self.created_at,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EvidenceLinkRecord:
    link_id: str
    identity_id: str
    evidence_id: str
    target_type: EvidenceTargetType
    target_id: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        evidence_id: str,
        target_type: str | EvidenceTargetType,
        target_id: str,
        reason: str = "",
    ) -> "EvidenceLinkRecord":
        return cls(
            link_id=f"evidence_link_{uuid.uuid4()}",
            identity_id=identity_id,
            evidence_id=evidence_id,
            target_type=EvidenceTargetType(str(target_type)),
            target_id=target_id,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceLinkRecord":
        return cls(
            link_id=str(data["link_id"]),
            identity_id=str(data["identity_id"]),
            evidence_id=str(data["evidence_id"]),
            target_type=EvidenceTargetType(str(data["target_type"])),
            target_id=str(data["target_id"]),
            created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "identity_id": self.identity_id,
            "evidence_id": self.evidence_id,
            "target_type": self.target_type.value,
            "target_id": self.target_id,
            "created_at": self.created_at,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class EvidenceReviewRecord:
    review_id: str
    identity_id: str
    evidence_id: str
    review_status: EvidenceReviewStatus
    reviewer: str
    confidence: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        evidence_id: str,
        review_status: str | EvidenceReviewStatus,
        reviewer: str = "steward",
        confidence: str | None = None,
        reason: str = "",
    ) -> "EvidenceReviewRecord":
        status_value = (
            review_status.value
            if isinstance(review_status, EvidenceReviewStatus)
            else str(review_status)
        )
        return cls(
            review_id=f"evidence_review_{uuid.uuid4()}",
            identity_id=identity_id,
            evidence_id=evidence_id,
            review_status=EvidenceReviewStatus(status_value),
            reviewer=reviewer,
            confidence=confidence,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "EvidenceReviewRecord":
        return cls(
            review_id=str(data["review_id"]),
            identity_id=str(data["identity_id"]),
            evidence_id=str(data["evidence_id"]),
            review_status=EvidenceReviewStatus(str(data["review_status"])),
            reviewer=str(data.get("reviewer", "steward")),
            confidence=data.get("confidence"),
            created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "identity_id": self.identity_id,
            "evidence_id": self.evidence_id,
            "review_status": self.review_status.value,
            "reviewer": self.reviewer,
            "confidence": self.confidence,
            "created_at": self.created_at,
            "reason": self.reason,
        }


def add_evidence(
    ledger: ContinuityLedger,
    identity_id: str,
    source_type: str,
    summary: str,
    source: str = "",
    confidence: str = "unknown",
    reason: str = "",
) -> EvidenceRecord:
    record = EvidenceRecord.create(
        identity_id=identity_id,
        source_type=source_type,
        source=source or summary,
        summary=summary,
        confidence=confidence,
        reason=reason,
    )
    ledger.append("evidence.added", identity_id, record.to_dict())
    return record


def add_evidence_claim(
    ledger: ContinuityLedger,
    identity_id: str,
    statement: str,
    evidence_ids: list[str] | None = None,
    confidence: str = "unknown",
    status: str = "proposed",
    reason: str = "",
) -> EvidenceClaimRecord:
    _require_all_evidence(ledger.events(), evidence_ids or [])
    record = EvidenceClaimRecord.create(
        identity_id=identity_id,
        statement=statement,
        evidence_ids=evidence_ids,
        confidence=confidence,
        status=status,
        reason=reason,
    )
    ledger.append("evidence.claim_recorded", identity_id, record.to_dict())
    for evidence_id in record.evidence_ids:
        link_evidence(
            ledger,
            identity_id,
            evidence_id,
            "claim",
            record.claim_id,
            reason="claim cites evidence",
        )
    return record


def link_evidence(
    ledger: ContinuityLedger,
    identity_id: str,
    evidence_id: str,
    target_type: str,
    target_id: str,
    reason: str = "",
) -> EvidenceLinkRecord:
    require_evidence(ledger.events(), evidence_id)
    record = EvidenceLinkRecord.create(
        identity_id=identity_id,
        evidence_id=evidence_id,
        target_type=target_type,
        target_id=target_id,
        reason=reason,
    )
    ledger.append("evidence.linked", identity_id, record.to_dict())
    return record


def review_evidence(
    ledger: ContinuityLedger,
    identity_id: str,
    evidence_id: str,
    review_status: str,
    reviewer: str = "steward",
    confidence: str | None = None,
    reason: str = "",
) -> EvidenceRecord:
    current = require_evidence(ledger.events(), evidence_id)
    review = EvidenceReviewRecord.create(
        identity_id=identity_id,
        evidence_id=evidence_id,
        review_status=review_status,
        reviewer=reviewer,
        confidence=confidence,
        reason=reason,
    )
    updated = current.with_review(
        review.review_status,
        confidence=confidence,
        reason=reason,
    )
    ledger.append("evidence.reviewed", identity_id, review.to_dict())
    ledger.append("evidence.updated", identity_id, updated.to_dict())
    return updated


def evidence_records_from_events(events: list[ContinuityEvent]) -> list[EvidenceRecord]:
    records: dict[str, EvidenceRecord] = {}
    for event in events:
        if event.event_type in {"evidence.added", "evidence.updated"}:
            record = EvidenceRecord.from_dict(event.payload)
            records[record.evidence_id] = record
    return list(records.values())


def evidence_claim_records_from_events(
    events: list[ContinuityEvent],
) -> list[EvidenceClaimRecord]:
    return [
        EvidenceClaimRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "evidence.claim_recorded"
    ]


def evidence_link_records_from_events(
    events: list[ContinuityEvent],
) -> list[EvidenceLinkRecord]:
    return [
        EvidenceLinkRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "evidence.linked"
    ]


def evidence_review_records_from_events(
    events: list[ContinuityEvent],
) -> list[EvidenceReviewRecord]:
    return [
        EvidenceReviewRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "evidence.reviewed"
    ]


def evidence_for_target(
    events: list[ContinuityEvent],
    target_type: str,
    target_id: str,
) -> list[dict[str, Any]]:
    target_value = EvidenceTargetType(str(target_type)).value
    evidence_by_id = {record.evidence_id: record for record in evidence_records_from_events(events)}
    links = [
        link
        for link in evidence_link_records_from_events(events)
        if link.target_type.value == target_value and link.target_id == target_id
    ]
    return [
        {
            "link": link.to_dict(),
            "evidence": evidence_by_id[link.evidence_id].to_dict(),
        }
        for link in links
        if link.evidence_id in evidence_by_id
    ]


def evidence_locker_snapshot(events: list[ContinuityEvent]) -> dict[str, Any]:
    records = evidence_records_from_events(events)
    links = evidence_link_records_from_events(events)
    claims = evidence_claim_records_from_events(events)
    reviews = evidence_review_records_from_events(events)
    by_status: dict[str, int] = {}
    for record in records:
        by_status[record.review_status.value] = by_status.get(record.review_status.value, 0) + 1
    return {
        "count": len(records),
        "reviewed_count": by_status.get("reviewed", 0),
        "disputed_count": by_status.get("disputed", 0),
        "stale_count": by_status.get("stale", 0),
        "rejected_count": by_status.get("rejected", 0),
        "by_status": by_status,
        "evidence": [record.to_dict() for record in records],
        "links": [record.to_dict() for record in links],
        "claims": [record.to_dict() for record in claims],
        "reviews": [record.to_dict() for record in reviews],
    }


def require_evidence(
    events: list[ContinuityEvent],
    evidence_id: str,
) -> EvidenceRecord:
    for record in evidence_records_from_events(events):
        if record.evidence_id == evidence_id:
            return record
    raise ValueError(f"Evidence not found: {evidence_id}")


def _require_all_evidence(events: list[ContinuityEvent], evidence_ids: list[str]) -> None:
    for evidence_id in evidence_ids:
        require_evidence(events, evidence_id)
