from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import hashlib
from pathlib import Path
import subprocess
from typing import Any
import uuid

from .evidence_locker import add_evidence, link_evidence
from .ledger import ContinuityEvent, ContinuityLedger
from .mission_steps import (
    MissionStepApprovalStatus,
    MissionStepExecutionStatus,
    MissionStepRisk,
    complete_mission_step,
    fail_mission_step,
    require_mission_step,
    start_mission_step,
)


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class ToolRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    BLOCKED = "blocked"


class ToolPermissionDecision(str, Enum):
    ALLOWED = "allowed"
    DENIED = "denied"


class ToolExecutionStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    DENIED = "denied"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    risk: ToolRisk
    description: str
    requires_approval: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "risk": self.risk.value,
            "description": self.description,
            "requires_approval": self.requires_approval,
        }


@dataclass(frozen=True)
class ToolPermissionRecord:
    permission_id: str
    identity_id: str
    step_id: str
    mission_id: str
    tool_name: str
    tool_risk: ToolRisk
    decision: ToolPermissionDecision
    reason: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create(
        cls,
        identity_id: str,
        step_id: str,
        mission_id: str,
        tool_name: str,
        tool_risk: str | ToolRisk,
        decision: str | ToolPermissionDecision,
        reason: str,
    ) -> "ToolPermissionRecord":
        return cls(
            permission_id=f"tool_permission_{uuid.uuid4()}",
            identity_id=identity_id,
            step_id=step_id,
            mission_id=mission_id,
            tool_name=tool_name,
            tool_risk=_parse_risk(tool_risk),
            decision=_parse_decision(decision),
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolPermissionRecord":
        return cls(
            permission_id=str(data["permission_id"]),
            identity_id=str(data["identity_id"]),
            step_id=str(data["step_id"]),
            mission_id=str(data["mission_id"]),
            tool_name=str(data["tool_name"]),
            tool_risk=_parse_risk(data["tool_risk"]),
            decision=_parse_decision(data["decision"]),
            reason=str(data.get("reason", "")),
            created_at=str(data["created_at"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "permission_id": self.permission_id,
            "identity_id": self.identity_id,
            "step_id": self.step_id,
            "mission_id": self.mission_id,
            "tool_name": self.tool_name,
            "tool_risk": self.tool_risk.value,
            "decision": self.decision.value,
            "reason": self.reason,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class ToolExecutionRecord:
    execution_id: str
    identity_id: str
    step_id: str
    mission_id: str
    tool_name: str
    status: ToolExecutionStatus
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
        step_id: str,
        mission_id: str,
        tool_name: str,
        status: str | ToolExecutionStatus,
        output: str,
        evidence_id: str | None = None,
        exit_code: int = 0,
        reason: str = "",
    ) -> "ToolExecutionRecord":
        return cls(
            execution_id=f"tool_execution_{uuid.uuid4()}",
            identity_id=identity_id,
            step_id=step_id,
            mission_id=mission_id,
            tool_name=tool_name,
            status=_parse_status(status),
            output_sha256=_text_hash(output),
            output_length=len(output),
            evidence_id=evidence_id,
            exit_code=exit_code,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolExecutionRecord":
        return cls(
            execution_id=str(data["execution_id"]),
            identity_id=str(data["identity_id"]),
            step_id=str(data["step_id"]),
            mission_id=str(data["mission_id"]),
            tool_name=str(data["tool_name"]),
            status=_parse_status(data["status"]),
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
            "step_id": self.step_id,
            "mission_id": self.mission_id,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "output_sha256": self.output_sha256,
            "output_length": self.output_length,
            "evidence_id": self.evidence_id,
            "exit_code": self.exit_code,
            "created_at": self.created_at,
            "reason": self.reason,
        }


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "list_files": ToolSpec(
        name="list_files",
        risk=ToolRisk.LOW,
        description="List files under the project root.",
    ),
    "read_file": ToolSpec(
        name="read_file",
        risk=ToolRisk.LOW,
        description="Read a project file and return a bounded preview.",
    ),
    "git_status": ToolSpec(
        name="git_status",
        risk=ToolRisk.LOW,
        description="Report local git status without changing repository state.",
    ),
    "run_check_all": ToolSpec(
        name="run_check_all",
        risk=ToolRisk.MEDIUM,
        description="Run the project verification script.",
        requires_approval=True,
    ),
    "open_dashboard": ToolSpec(
        name="open_dashboard",
        risk=ToolRisk.LOW,
        description="Return the local dashboard path or URL without opening a GUI.",
    ),
}


def tool_specs() -> list[ToolSpec]:
    return list(TOOL_REGISTRY.values())


def tool_permission_records_from_events(
    events: list[ContinuityEvent],
) -> list[ToolPermissionRecord]:
    return [
        ToolPermissionRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "tool.permission_checked"
    ]


def tool_execution_records_from_events(
    events: list[ContinuityEvent],
) -> list[ToolExecutionRecord]:
    return [
        ToolExecutionRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "tool.execution_recorded"
    ]


def run_tool_for_step(
    ledger: ContinuityLedger,
    identity_id: str,
    step_id: str,
    tool_args: dict[str, str] | None = None,
    project_root: str | Path = ".",
    reason: str = "",
) -> dict[str, Any]:
    tool_args = tool_args or {}
    root = Path(project_root).resolve()
    step = require_mission_step(ledger.events(), step_id)
    spec = _require_tool(step.required_tool)
    permission = check_tool_permission(
        ledger=ledger,
        identity_id=identity_id,
        step_id=step_id,
        reason=reason,
    )
    if permission.decision == ToolPermissionDecision.DENIED:
        record = ToolExecutionRecord.create(
            identity_id=identity_id,
            step_id=step.step_id,
            mission_id=step.mission_id,
            tool_name=spec.name,
            status=ToolExecutionStatus.DENIED,
            output=permission.reason,
            reason=permission.reason,
        )
        ledger.append("tool.execution_recorded", identity_id, record.to_dict())
        return {
            "permission": permission.to_dict(),
            "execution": record.to_dict(),
            "output": permission.reason,
        }

    running_step = step
    if step.execution_status in {
        MissionStepExecutionStatus.PROPOSED,
        MissionStepExecutionStatus.READY,
    }:
        running_step = start_mission_step(
            ledger,
            identity_id,
            step_id,
            reason=f"tool execution started: {spec.name}",
        )

    try:
        output, exit_code = _execute_tool(spec.name, tool_args, root)
    except ValueError as exc:
        output, exit_code = str(exc), 1
    status = ToolExecutionStatus.COMPLETED if exit_code == 0 else ToolExecutionStatus.FAILED
    evidence_type = _evidence_type_for_tool(spec.name, status)
    evidence = add_evidence(
        ledger=ledger,
        identity_id=identity_id,
        source_type=evidence_type,
        source=output,
        summary=_tool_summary(spec.name, status, output),
        confidence="medium" if status == ToolExecutionStatus.COMPLETED else "low",
        reason=f"tool output from mission step {running_step.step_id}",
    )
    link_evidence(
        ledger,
        identity_id,
        evidence.evidence_id,
        "mission",
        running_step.mission_id,
        reason=f"tool output for mission step {running_step.step_id}",
    )
    record = ToolExecutionRecord.create(
        identity_id=identity_id,
        step_id=running_step.step_id,
        mission_id=running_step.mission_id,
        tool_name=spec.name,
        status=status,
        output=output,
        evidence_id=evidence.evidence_id,
        exit_code=exit_code,
        reason=reason,
    )
    ledger.append("tool.execution_recorded", identity_id, record.to_dict())
    if status == ToolExecutionStatus.COMPLETED:
        final_step = complete_mission_step(
            ledger,
            identity_id,
            running_step.step_id,
            actual_outcome=_tool_summary(spec.name, status, output),
            reason=f"tool execution completed: {spec.name}",
        )
    else:
        final_step = fail_mission_step(
            ledger,
            identity_id,
            running_step.step_id,
            failure_note=_tool_summary(spec.name, status, output),
            reason=f"tool execution failed: {spec.name}",
        )
    return {
        "permission": permission.to_dict(),
        "execution": record.to_dict(),
        "evidence": evidence.to_dict(),
        "mission_step": final_step.to_dict(),
        "output": output,
    }


def check_tool_permission(
    ledger: ContinuityLedger,
    identity_id: str,
    step_id: str,
    reason: str = "",
) -> ToolPermissionRecord:
    step = require_mission_step(ledger.events(), step_id)
    spec = _require_tool(step.required_tool)
    denial_reason = _tool_denial_reason(spec, step)
    decision = (
        ToolPermissionDecision.DENIED
        if denial_reason
        else ToolPermissionDecision.ALLOWED
    )
    record = ToolPermissionRecord.create(
        identity_id=identity_id,
        step_id=step.step_id,
        mission_id=step.mission_id,
        tool_name=spec.name,
        tool_risk=spec.risk,
        decision=decision,
        reason=denial_reason or reason or "tool permission allowed",
    )
    ledger.append("tool.permission_checked", identity_id, record.to_dict())
    return record


def _tool_denial_reason(spec: ToolSpec, step) -> str:
    if spec.risk == ToolRisk.BLOCKED:
        return f"tool {spec.name} is blocked by PCA tool policy"
    if step.required_tool != spec.name:
        return "mission step required tool does not match requested tool"
    if step.execution_status in {
        MissionStepExecutionStatus.COMPLETED,
        MissionStepExecutionStatus.FAILED,
        MissionStepExecutionStatus.BLOCKED,
    }:
        return f"mission step cannot execute from {step.execution_status.value}"
    if step.risk_level in {MissionStepRisk.MEDIUM, MissionStepRisk.HIGH} and (
        step.approval_status != MissionStepApprovalStatus.APPROVED
    ):
        return "medium/high-risk mission steps require approval before tool execution"
    if spec.requires_approval and step.approval_status != MissionStepApprovalStatus.APPROVED:
        return f"tool {spec.name} requires approved mission step"
    return ""


def _execute_tool(
    tool_name: str,
    tool_args: dict[str, str],
    project_root: Path,
) -> tuple[str, int]:
    if tool_name == "list_files":
        target = _safe_project_path(project_root, tool_args.get("path", "."))
        if not target.exists():
            return f"path not found: {_display_path(project_root, target)}", 1
        if target.is_file():
            return _display_path(project_root, target), 0
        paths = [
            _display_path(project_root, path)
            for path in sorted(target.iterdir(), key=lambda item: item.name.lower())
        ]
        return "\n".join(paths[:200]), 0
    if tool_name == "read_file":
        target = _safe_project_path(project_root, tool_args.get("path", ""))
        if not target.is_file():
            return f"file not found: {_display_path(project_root, target)}", 1
        text = target.read_text(encoding="utf-8", errors="replace")
        return text[:4000], 0
    if tool_name == "git_status":
        return _run_command(["git", "status", "--short", "--branch"], project_root)
    if tool_name == "run_check_all":
        return _run_command(["python3", "scripts/check_all.py"], project_root)
    if tool_name == "open_dashboard":
        dashboard = project_root / tool_args.get("path", "reports/lucien_cockpit.html")
        safe_dashboard = _safe_project_path(project_root, str(dashboard))
        if not safe_dashboard.exists():
            return f"dashboard not found: {_display_path(project_root, safe_dashboard)}", 1
        return f"http://127.0.0.1:8787/{_display_path(project_root, safe_dashboard)}", 0
    return f"unknown tool: {tool_name}", 1


def _run_command(command: list[str], project_root: Path) -> tuple[str, int]:
    result = subprocess.run(
        command,
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    return output.strip(), result.returncode


def _safe_project_path(project_root: Path, path_value: str) -> Path:
    if not path_value:
        raise ValueError("path argument is required")
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = project_root / candidate
    resolved = candidate.resolve()
    try:
        resolved.relative_to(project_root)
    except ValueError as exc:
        raise ValueError("tool path must stay inside the project root") from exc
    return resolved


def _display_path(project_root: Path, target: Path) -> str:
    try:
        return str(target.relative_to(project_root))
    except ValueError:
        return str(target)


def _require_tool(tool_name: str) -> ToolSpec:
    try:
        return TOOL_REGISTRY[tool_name]
    except KeyError as exc:
        raise ValueError(f"Unknown PCA tool: {tool_name}") from exc


def _tool_summary(tool_name: str, status: ToolExecutionStatus, output: str) -> str:
    line_count = len(output.splitlines()) if output else 0
    return (
        f"Tool {tool_name} {status.value}; "
        f"output_length={len(output)}; output_lines={line_count}."
    )


def _evidence_type_for_tool(tool_name: str, status: ToolExecutionStatus) -> str:
    if tool_name == "run_check_all":
        return "test_result"
    if tool_name == "git_status":
        return "code_result"
    if status == ToolExecutionStatus.FAILED:
        return "tool_output"
    return "tool_output"


def _parse_risk(value: str | ToolRisk) -> ToolRisk:
    if isinstance(value, ToolRisk):
        return value
    return ToolRisk(str(value))


def _parse_decision(value: str | ToolPermissionDecision) -> ToolPermissionDecision:
    if isinstance(value, ToolPermissionDecision):
        return value
    return ToolPermissionDecision(str(value))


def _parse_status(value: str | ToolExecutionStatus) -> ToolExecutionStatus:
    if isinstance(value, ToolExecutionStatus):
        return value
    return ToolExecutionStatus(str(value))
