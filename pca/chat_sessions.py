from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger


@dataclass(frozen=True)
class ChatSessionRecord:
    session_id: str
    identity_id: str
    status: str
    started_at: str
    closed_at: str | None = None
    turn_count: int = 0
    reason: str = ""

    @classmethod
    def start(
        cls,
        identity_id: str,
        reason: str = "",
    ) -> "ChatSessionRecord":
        return cls(
            session_id=f"session_{uuid.uuid4()}",
            identity_id=identity_id,
            status="open",
            started_at=datetime.now(timezone.utc).isoformat(),
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatSessionRecord":
        return cls(
            session_id=str(data["session_id"]),
            identity_id=str(data["identity_id"]),
            status=str(data["status"]),
            started_at=str(data["started_at"]),
            closed_at=data.get("closed_at"),
            turn_count=int(data.get("turn_count", 0)),
            reason=str(data.get("reason", "")),
        )

    def close(self, turn_count: int, reason: str = "") -> "ChatSessionRecord":
        return ChatSessionRecord(
            session_id=self.session_id,
            identity_id=self.identity_id,
            status="closed",
            started_at=self.started_at,
            closed_at=datetime.now(timezone.utc).isoformat(),
            turn_count=turn_count,
            reason=reason or self.reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "identity_id": self.identity_id,
            "status": self.status,
            "started_at": self.started_at,
            "closed_at": self.closed_at,
            "turn_count": self.turn_count,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ChatTurnRecord:
    turn_id: str
    session_id: str
    identity_id: str
    turn_index: int
    input_event_id: str
    output_event_id: str
    growth_event_ids: list[str] = field(default_factory=list)
    output_allowed: bool = True
    continuity_claim: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create(
        cls,
        session_id: str,
        identity_id: str,
        turn_index: int,
        input_event_id: str,
        output_event_id: str,
        growth_event_ids: list[str] | None = None,
        output_allowed: bool = True,
        continuity_claim: str = "",
    ) -> "ChatTurnRecord":
        return cls(
            turn_id=f"turn_{uuid.uuid4()}",
            session_id=session_id,
            identity_id=identity_id,
            turn_index=turn_index,
            input_event_id=input_event_id,
            output_event_id=output_event_id,
            growth_event_ids=growth_event_ids or [],
            output_allowed=output_allowed,
            continuity_claim=continuity_claim,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatTurnRecord":
        return cls(
            turn_id=str(data["turn_id"]),
            session_id=str(data["session_id"]),
            identity_id=str(data["identity_id"]),
            turn_index=int(data["turn_index"]),
            input_event_id=str(data["input_event_id"]),
            output_event_id=str(data["output_event_id"]),
            growth_event_ids=[str(item) for item in data.get("growth_event_ids", [])],
            output_allowed=bool(data.get("output_allowed", True)),
            continuity_claim=str(data.get("continuity_claim", "")),
            created_at=str(data["created_at"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_id": self.turn_id,
            "session_id": self.session_id,
            "identity_id": self.identity_id,
            "turn_index": self.turn_index,
            "input_event_id": self.input_event_id,
            "output_event_id": self.output_event_id,
            "growth_event_ids": self.growth_event_ids,
            "output_allowed": self.output_allowed,
            "continuity_claim": self.continuity_claim,
            "created_at": self.created_at,
        }


def start_chat_session(
    ledger: ContinuityLedger,
    identity_id: str,
    reason: str = "",
) -> ChatSessionRecord:
    record = ChatSessionRecord.start(identity_id, reason=reason)
    ledger.append("lucien.chat_session_started", identity_id, record.to_dict())
    return record


def record_chat_turn(
    ledger: ContinuityLedger,
    identity_id: str,
    session_id: str,
    turn_index: int,
    input_event_id: str,
    output_event_id: str,
    growth_event_ids: list[str] | None = None,
    output_allowed: bool = True,
    continuity_claim: str = "",
) -> ChatTurnRecord:
    record = ChatTurnRecord.create(
        session_id=session_id,
        identity_id=identity_id,
        turn_index=turn_index,
        input_event_id=input_event_id,
        output_event_id=output_event_id,
        growth_event_ids=growth_event_ids,
        output_allowed=output_allowed,
        continuity_claim=continuity_claim,
    )
    ledger.append("lucien.chat_turn_recorded", identity_id, record.to_dict())
    return record


def close_chat_session(
    ledger: ContinuityLedger,
    identity_id: str,
    session_id: str,
    reason: str = "",
) -> ChatSessionRecord:
    session = _require_session(chat_sessions_from_events(ledger.events()), session_id)
    turn_count = len(
        [
            turn
            for turn in chat_turns_from_events(ledger.events())
            if turn.session_id == session_id
        ]
    )
    closed = session.close(turn_count=turn_count, reason=reason)
    ledger.append("lucien.chat_session_closed", identity_id, closed.to_dict())
    return closed


def chat_sessions_from_events(events: list[ContinuityEvent]) -> list[ChatSessionRecord]:
    sessions: dict[str, ChatSessionRecord] = {}
    for event in events:
        if event.event_type in {
            "lucien.chat_session_started",
            "lucien.chat_session_closed",
        }:
            session = ChatSessionRecord.from_dict(event.payload)
            sessions[session.session_id] = session
    return list(sessions.values())


def chat_turns_from_events(events: list[ContinuityEvent]) -> list[ChatTurnRecord]:
    return [
        ChatTurnRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "lucien.chat_turn_recorded"
    ]


def _require_session(
    sessions: list[ChatSessionRecord],
    session_id: str,
) -> ChatSessionRecord:
    for session in sessions:
        if session.session_id == session_id:
            return session
    raise ValueError(f"Chat session not found: {session_id}")
