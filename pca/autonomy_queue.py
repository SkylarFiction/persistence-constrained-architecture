from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from pathlib import Path
import subprocess
from typing import Any
import uuid

from .build_review import build_review, render_build_review_text
from .checkpoint_story import checkpoint_story, render_checkpoint_story_markdown
from .commit_readiness import commit_readiness, render_commit_readiness_text
from .daily_command_center import daily_command_center, render_daily_command_center_text
from .evidence_locker import add_evidence
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .next_build import next_governed_build, render_next_governed_build_text
from .project_brief import project_build_brief, render_project_build_brief_text
from .reflection_queue import ReflectionTaskRecord
from .reflections import ReflectionRecord
from .steward_inbox import steward_inbox


class AutonomyActionType(str, Enum):
    RUN_CHECK_ALL = "run_check_all"
    PROJECT_BRIEF = "project_brief"
    BUILD_REVIEW = "build_review"
    COMMIT_READINESS = "commit_readiness"
    NEXT_BUILD = "next_build"
    DAILY_PLAN = "daily_plan"
    OPEN_MISSION = "open_mission"
    PROPOSE_STEP = "propose_step"
    REVIEW_INBOX = "review_inbox"
    LINK_CHECKPOINT = "link_checkpoint"
    GENERATE_STORY = "generate_story"
    RUN_COHERENCE_RESEARCH_CYCLE = "run_coherence_research_cycle"


class AutonomyQueueStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class AutonomyExecutionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


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
        parsed_status = (
            status
            if isinstance(status, AutonomyQueueStatus)
            else AutonomyQueueStatus(str(status))
        )
        return AutonomyQueueItem(
            item_id=self.item_id,
            identity_id=self.identity_id,
            action_type=self.action_type,
            risk=self.risk,
            reason=self.reason,
            payload=self.payload,
            status=parsed_status,
            proposed_by=self.proposed_by,
            reviewed_by=reviewed_by,
            review_reason=reason,
            created_at=self.created_at,
            updated_at=datetime.now(timezone.utc).isoformat(),
        )


@dataclass(frozen=True)
class AutonomyExecutionRecord:
    execution_id: str
    identity_id: str
    item_id: str
    action_type: AutonomyActionType
    status: AutonomyExecutionStatus
    output_sha256: str
    output_length: int
    evidence_id: str | None = None
    exit_code: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        item_id: str,
        action_type: str | AutonomyActionType,
        status: str | AutonomyExecutionStatus,
        output: str,
        evidence_id: str | None = None,
        exit_code: int = 0,
        reason: str = "",
    ) -> "AutonomyExecutionRecord":
        return cls(
            execution_id=f"autonomy_execution_{uuid.uuid4()}",
            identity_id=identity_id,
            item_id=item_id,
            action_type=_parse_action_type(action_type),
            status=_parse_execution_status(status),
            output_sha256=hashlib.sha256(output.encode("utf-8")).hexdigest(),
            output_length=len(output),
            evidence_id=evidence_id,
            exit_code=exit_code,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutonomyExecutionRecord":
        return cls(
            execution_id=str(data["execution_id"]),
            identity_id=str(data["identity_id"]),
            item_id=str(data["item_id"]),
            action_type=_parse_action_type(data["action_type"]),
            status=_parse_execution_status(data["status"]),
            output_sha256=str(data["output_sha256"]),
            output_length=int(data["output_length"]),
            evidence_id=data.get("evidence_id"),
            exit_code=int(data.get("exit_code", 0)),
            created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_id": self.execution_id,
            "identity_id": self.identity_id,
            "item_id": self.item_id,
            "action_type": self.action_type.value,
            "status": self.status.value,
            "output_sha256": self.output_sha256,
            "output_length": self.output_length,
            "evidence_id": self.evidence_id,
            "exit_code": self.exit_code,
            "created_at": self.created_at,
            "reason": self.reason,
        }


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


def execute_autonomy_action(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    item_id: str,
    project_root: str | Path = ".",
    reason: str = "",
) -> dict[str, Any]:
    item = require_autonomy_item(ledger.events(), item_id)
    if item.status != AutonomyQueueStatus.APPROVED:
        raise ValueError("Only approved autonomy actions can execute.")
    if _execution_for_item(ledger.events(), item_id):
        raise ValueError(f"Autonomy item already executed: {item_id}")
    output, exit_code = _execute_allowed_action(item, ledger, manifest, Path(project_root))
    status = (
        AutonomyExecutionStatus.COMPLETED
        if exit_code == 0
        else AutonomyExecutionStatus.FAILED
    )
    evidence = add_evidence(
        ledger,
        manifest.system_id,
        source_type="test_result" if item.action_type == AutonomyActionType.RUN_CHECK_ALL else "tool_output",
        source=output,
        summary=f"Autonomy action {item.action_type.value} {status.value}.",
        confidence="medium" if status == AutonomyExecutionStatus.COMPLETED else "low",
        reason=f"autonomy execution for {item.item_id}",
    )
    record = AutonomyExecutionRecord.create(
        identity_id=manifest.system_id,
        item_id=item.item_id,
        action_type=item.action_type,
        status=status,
        output=output,
        evidence_id=evidence.evidence_id,
        exit_code=exit_code,
        reason=reason,
    )
    event = ledger.append("autonomy.action_executed", manifest.system_id, record.to_dict())
    reflection = None
    task = None
    if status == AutonomyExecutionStatus.FAILED:
        reflection = ReflectionRecord.create(
            identity_id=manifest.system_id,
            continuity_claim="autonomy_execution_review",
            focus="autonomy_execution_failure",
            severity="medium",
            observations=[f"autonomy action failed: {item.action_type.value}"],
            recommended_actions=["review failed autonomy execution before retrying"],
            source_event_ids=[event.event_hash],
        )
        ledger.append("lucien.reflection_recorded", manifest.system_id, reflection.to_dict())
        task = ReflectionTaskRecord.create(
            identity_id=manifest.system_id,
            kind="review_mission",
            severity="medium",
            source_reflection_id=reflection.reflection_id,
            reason=f"autonomy execution failed: {item.item_id}",
            recommended_action="Review the autonomy execution output and decide whether to retry, revise, or reject the action.",
        )
        ledger.append("reflection.task_opened", manifest.system_id, task.to_dict())
    return {
        "item": item.to_dict(),
        "execution": record.to_dict(),
        "evidence": evidence.to_dict(),
        "output": output,
        "reflection": reflection.to_dict() if reflection else None,
        "reflection_task": task.to_dict() if task else None,
    }


def execute_approved_autonomy_actions(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    project_root: str | Path = ".",
) -> list[dict[str, Any]]:
    executed_item_ids = {record.item_id for record in autonomy_execution_records_from_events(ledger.events())}
    results = []
    for item in autonomy_queue_items_from_events(ledger.events(), "approved"):
        if item.item_id in executed_item_ids:
            continue
        results.append(
            execute_autonomy_action(
                ledger,
                manifest,
                item.item_id,
                project_root=project_root,
                reason="batch approved autonomy execution",
            )
        )
    return results


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


def autonomy_execution_records_from_events(
    events: list[ContinuityEvent],
) -> list[AutonomyExecutionRecord]:
    return [
        AutonomyExecutionRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "autonomy.action_executed"
    ]


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


def _execute_allowed_action(
    item: AutonomyQueueItem,
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    project_root: Path,
) -> tuple[str, int]:
    if item.action_type == AutonomyActionType.RUN_CHECK_ALL:
        return _run_command(["python3", "scripts/check_all.py"], project_root)
    if item.action_type == AutonomyActionType.PROJECT_BRIEF:
        return render_project_build_brief_text(project_build_brief(project_root)), 0
    if item.action_type == AutonomyActionType.BUILD_REVIEW:
        return render_build_review_text(build_review(project_root)), 0
    if item.action_type == AutonomyActionType.COMMIT_READINESS:
        return render_commit_readiness_text(commit_readiness(project_root)), 0
    if item.action_type == AutonomyActionType.NEXT_BUILD:
        return render_next_governed_build_text(next_governed_build(ledger, manifest)), 0
    if item.action_type == AutonomyActionType.DAILY_PLAN:
        return render_daily_command_center_text(daily_command_center(ledger, manifest)), 0
    if item.action_type == AutonomyActionType.REVIEW_INBOX:
        items = steward_inbox(ledger)
        return f"Steward inbox: {len(items)} open item(s).", 0
    if item.action_type == AutonomyActionType.GENERATE_STORY:
        return render_checkpoint_story_markdown(checkpoint_story(project_root)), 0
    if item.action_type == AutonomyActionType.RUN_COHERENCE_RESEARCH_CYCLE:
        from .coherence_research_cycle import (
            render_coherence_research_cycle_text,
            run_coherence_research_cycle,
        )

        result = run_coherence_research_cycle(
            ledger,
            manifest,
            project_root=project_root,
            mission_id=item.payload.get("mission_id") or None,
            corpus_limit=int(item.payload.get("limit") or 12),
            use_knowledge_hub=bool(item.payload.get("knowledge_hub", True)),
            force=bool(item.payload.get("force", False)),
            theory_revision=bool(item.payload.get("theory_revision", False)),
            llama_writer=bool(item.payload.get("llama_writer", False)),
            reason=f"approved autonomy research cycle {item.item_id}",
        )
        return render_coherence_research_cycle_text(result), 0
    return (
        f"Autonomy action {item.action_type.value} is approval-only and not executable in this version.",
        1,
    )


def _run_command(command: list[str], project_root: Path) -> tuple[str, int]:
    result = subprocess.run(
        command,
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    return output, result.returncode


def _execution_for_item(
    events: list[ContinuityEvent],
    item_id: str,
) -> AutonomyExecutionRecord | None:
    for record in autonomy_execution_records_from_events(events):
        if record.item_id == item_id:
            return record
    return None


def _parse_action_type(value: str | AutonomyActionType) -> AutonomyActionType:
    if isinstance(value, AutonomyActionType):
        return value
    return AutonomyActionType(str(value))


def _parse_execution_status(value: str | AutonomyExecutionStatus) -> AutonomyExecutionStatus:
    if isinstance(value, AutonomyExecutionStatus):
        return value
    return AutonomyExecutionStatus(str(value))


def _risk_for_action(action_type: AutonomyActionType) -> str:
    if action_type == AutonomyActionType.RUN_CHECK_ALL:
        return "medium"
    if action_type == AutonomyActionType.LINK_CHECKPOINT:
        return "medium"
    if action_type == AutonomyActionType.RUN_COHERENCE_RESEARCH_CYCLE:
        return "medium"
    return "low"
