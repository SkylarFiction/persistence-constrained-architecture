from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger


class AutonomyActionType(str, Enum):
    RUN_CHECK_ALL = "run_check_all"
    OPEN_MISSION = "open_mission"
    PROPOSE_STEP = "propose_step"
    REVIEW_INBOX = "review_inbox"
    LINK_CHECKPOINT = "link_checkpoint"
    GENERATE_STORY = "generate_story"


class AutonomyQueueStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AutonomyQueueItem:
    item_id: str
    identity_id: str
    action_type: AutonomyActionType
    risk: str
    reason: str
    payload: dict[str, Any] = field(default_factory=dict)
    status: AutonomyQueueStatus = AutonomyQueueStatus.PROPOSED
    proposed_by: str = "lucien"
    reviewed_by: str = ""
    review_reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str | None = None

    @classmethod
    def create(
        cls,
        identity_id: str,
        action_type: str | AutonomyActionType,
        reason: str,
        payload: dict[str, Any] | None = None,
        proposed_by: str = "lucien",
    ) -> "AutonomyQueueItem":
        parsed = _parse_action_type(action_type)
        return cls(
            item_id=f"autonomy_{uuid.uuid4()}",
            identity_id=identity_id,
            action_type=parsed,
            risk=_risk_for_action(parsed),
            reason=reason,
            payload=payload or {},
            proposed_by=proposed_by,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutonomyQueueItem":
        return cls(
            item_id=str(data["item_id"]),
            identity_id=str(data["identity_id"]),
            action_type=_parse_action_type(data["action_type"]),
            risk=str(data.get("risk", "low")),
            reason=str(data.get("reason", "")),
            payload=dict(data.get("payload", {})),
            status=AutonomyQueueStatus(str(data.get("status", "proposed"))),
            proposed_by=str(data.get("proposed_by", "lucien")),
            reviewed_by=str(data.get("reviewed_by", "")),
            review_reason=str(data.get("review_reason", "")),
            created_at=str(data["created_at"]),
            updated_at=data.get("updated_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "identity_id": self.identity_id,
            "action_type": self.action_type.value,
            "risk": self.risk,
            "reason": self.reason,
            "payload": self.payload,
            "status": self.status.value,
            "proposed_by": self.proposed_by,
            "reviewed_by": self.reviewed_by,
            "review_reason": self.review_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def with_review(
        self,
        status: str | AutonomyQueueStatus,
        reviewed_by: str,
        reason: str,
    ) -> "AutonomyQueueItem":
        return AutonomyQueueItem(
            item_id=self.item_id,
            identity_id=self.identity_id,
            action_type=self.action_type,
            risk=self.risk,
            reason=self.reason,
            payload=self.payload,
            status=AutonomyQueueStatus(str(status)),
            proposed_by=self.proposed_by,
            reviewed_by=reviewed_by,
            review_reason=reason,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )


def propose_autonomy_action(
    ledger: ContinuityLedger,
    identity_id: str,
    action_type: str,
    reason: str,
    payload: dict[str, Any] | None = None,
    proposed_by: str = "lucien",
) -> AutonomyQueueItem:
    item = AutonomyQueueItem.create(
        identity_id=identity_id,
        action_type=action_type,
        reason=reason,
        payload=payload,
        proposed_by=proposed_by,
    )
    ledger.append("autonomy.action_proposed", identity_id, item.to_dict())
    return item


def review_autonomy_action(
    ledger: ContinuityLedger,
    identity_id: str,
    item_id: str,
    decision: str,
    reviewed_by: str = "steward",
    reason: str = "",
) -> AutonomyQueueItem:
    if decision not in {"approve", "reject"}:
        raise ValueError("decision must be approve or reject")
    item = require_autonomy_item(ledger.events(), item_id)
    if item.status != AutonomyQueueStatus.PROPOSED:
        raise ValueError(f"Autonomy item is already {item.status.value}.")
    updated = item.with_review(
        AutonomyQueueStatus.APPROVED if decision == "approve" else AutonomyQueueStatus.REJECTED,
        reviewed_by=reviewed_by,
        reason=reason or f"steward {decision}d autonomy action",
    )
    ledger.append("autonomy.action_reviewed", identity_id, updated.to_dict())
    return updated


def autonomy_queue_items_from_events(
    events: list[ContinuityEvent],
    status: str | None = None,
) -> list[AutonomyQueueItem]:
    records: dict[str, AutonomyQueueItem] = {}
    for event in events:
        if event.event_type in {"autonomy.action_proposed", "autonomy.action_reviewed"}:
            item = AutonomyQueueItem.from_dict(event.payload)
            records[item.item_id] = item
    items = list(records.values())
    if status:
        items = [item for item in items if item.status.value == status]
    return sorted(items, key=lambda item: (item.created_at, item.item_id))


def require_autonomy_item(
    events: list[ContinuityEvent],
    item_id: str,
) -> AutonomyQueueItem:
    for item in autonomy_queue_items_from_events(events):
        if item.item_id == item_id:
            return item
    raise ValueError(f"Autonomy queue item not found: {item_id}")


def render_autonomy_queue_text(items: list[AutonomyQueueItem]) -> str:
    lines = ["Autonomy Queue", f"Items: {len(items)}"]
    if not items:
        lines.append("No autonomy actions proposed.")
        return "\n".join(lines)
    for item in items:
        lines.extend(
            [
                "",
                f"{item.item_id} / {item.status.value}",
                f"type: {item.action_type.value}",
                f"risk: {item.risk}",
                f"reason: {item.reason}",
            ]
        )
    return "\n".join(lines)


def _parse_action_type(value: str | AutonomyActionType) -> AutonomyActionType:
    if isinstance(value, AutonomyActionType):
        return value
    return AutonomyActionType(str(value))


def _risk_for_action(action_type: AutonomyActionType) -> str:
    if action_type == AutonomyActionType.RUN_CHECK_ALL:
        return "medium"
    if action_type == AutonomyActionType.LINK_CHECKPOINT:
        return "medium"
    return "low"
