from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import subprocess
import uuid

from .checkpoint_story import checkpoint_story
from .evidence_locker import require_evidence
from .ledger import ContinuityEvent, ContinuityLedger
from .mission_steps import MissionStepExecutionStatus, require_mission_step
from .missions import add_mission_item, require_mission
from .skill_memory import SkillCandidateRecord, skill_candidates_from_events


@dataclass(frozen=True)
class CheckpointLinkRecord:
    link_id: str
    identity_id: str
    mission_id: str
    commit_hash: str
    checkpoint_title: str
    mission_step_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    verification_checks: list[str] = field(default_factory=list)
    checkpoint_story_summary: str = ""
    lesson_candidate: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""

    @classmethod
    def create(
        cls,
        identity_id: str,
        mission_id: str,
        commit_hash: str,
        checkpoint_title: str,
        mission_step_ids: list[str] | None = None,
        evidence_ids: list[str] | None = None,
        verification_checks: list[str] | None = None,
        checkpoint_story_summary: str = "",
        lesson_candidate: str = "",
        reason: str = "",
    ) -> "CheckpointLinkRecord":
        return cls(
            link_id=f"checkpoint_link_{uuid.uuid4()}",
            identity_id=identity_id,
            mission_id=mission_id,
            commit_hash=commit_hash,
            checkpoint_title=checkpoint_title,
            mission_step_ids=mission_step_ids or [],
            evidence_ids=evidence_ids or [],
            verification_checks=verification_checks or [],
            checkpoint_story_summary=checkpoint_story_summary,
            lesson_candidate=lesson_candidate,
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CheckpointLinkRecord":
        return cls(
            link_id=str(data["link_id"]),
            identity_id=str(data["identity_id"]),
            mission_id=str(data["mission_id"]),
            commit_hash=str(data["commit_hash"]),
            checkpoint_title=str(data.get("checkpoint_title", "")),
            mission_step_ids=[str(item) for item in data.get("mission_step_ids", [])],
            evidence_ids=[str(item) for item in data.get("evidence_ids", [])],
            verification_checks=[str(item) for item in data.get("verification_checks", [])],
            checkpoint_story_summary=str(data.get("checkpoint_story_summary", "")),
            lesson_candidate=str(data.get("lesson_candidate", "")),
            created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "link_id": self.link_id,
            "identity_id": self.identity_id,
            "mission_id": self.mission_id,
            "commit_hash": self.commit_hash,
            "checkpoint_title": self.checkpoint_title,
            "mission_step_ids": self.mission_step_ids,
            "evidence_ids": self.evidence_ids,
            "verification_checks": self.verification_checks,
            "checkpoint_story_summary": self.checkpoint_story_summary,
            "lesson_candidate": self.lesson_candidate,
            "created_at": self.created_at,
            "reason": self.reason,
        }


def link_checkpoint_to_mission(
    ledger: ContinuityLedger,
    identity_id: str,
    mission_id: str,
    commit_hash: str = "HEAD",
    mission_step_ids: list[str] | None = None,
    evidence_ids: list[str] | None = None,
    verification_checks: list[str] | None = None,
    lesson_candidate: str = "",
    reason: str = "",
    project_root: str | Path = ".",
) -> CheckpointLinkRecord:
    events = ledger.events()
    mission = require_mission(events, mission_id)
    for step_id in mission_step_ids or []:
        step = require_mission_step(events, step_id)
        if step.mission_id != mission_id:
            raise ValueError(f"Mission step {step_id} does not belong to {mission_id}")
    for evidence_id in evidence_ids or []:
        require_evidence(events, evidence_id)
    resolved_commit = _resolve_commit_hash(commit_hash, Path(project_root))
    story = checkpoint_story(project_root)
    checks = verification_checks or list(story.get("verification") or [])
    record = CheckpointLinkRecord.create(
        identity_id=identity_id,
        mission_id=mission.mission_id,
        commit_hash=resolved_commit,
        checkpoint_title=str(story.get("title") or resolved_commit),
        mission_step_ids=mission_step_ids or [],
        evidence_ids=evidence_ids or [],
        verification_checks=checks,
        checkpoint_story_summary=str(story.get("summary", "")),
        lesson_candidate=lesson_candidate,
        reason=reason,
    )
    ledger.append("checkpoint.linked_to_mission", identity_id, record.to_dict())
    return record


def checkpoint_link_records_from_events(
    events: list[ContinuityEvent],
    mission_id: str | None = None,
) -> list[CheckpointLinkRecord]:
    records = [
        CheckpointLinkRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "checkpoint.linked_to_mission"
    ]
    if mission_id is None:
        return records
    return [record for record in records if record.mission_id == mission_id]


def checkpoint_history(
    ledger: ContinuityLedger,
    mission_id: str | None = None,
) -> dict[str, Any]:
    records = checkpoint_link_records_from_events(ledger.events(), mission_id)
    by_mission: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_mission.setdefault(record.mission_id, []).append(record.to_dict())
    return {
        "count": len(records),
        "mission_id": mission_id,
        "records": [record.to_dict() for record in records],
        "by_mission": by_mission,
    }


def render_checkpoint_history_text(history: dict[str, Any]) -> str:
    lines = [
        "Checkpoint History",
        f"Linked checkpoints: {history.get('count', 0)}",
    ]
    records = history.get("records") or []
    if not records:
        lines.append("No mission-linked checkpoints recorded yet.")
        return "\n".join(lines)
    for record in records:
        lines.extend(
            [
                "",
                f"{record['commit_hash']} / {record.get('checkpoint_title') or 'checkpoint'}",
                f"mission: {record['mission_id']}",
                f"steps: {', '.join(record.get('mission_step_ids') or []) or 'none'}",
                f"evidence: {', '.join(record.get('evidence_ids') or []) or 'none'}",
                f"lesson candidate: {record.get('lesson_candidate') or 'none'}",
            ]
        )
    return "\n".join(lines)


def propose_checkpoint_lesson(
    ledger: ContinuityLedger,
    identity_id: str,
    link_id: str,
    lesson_summary: str,
    confidence: str = "medium",
    reason: str = "",
) -> dict[str, Any]:
    link = require_checkpoint_link(ledger.events(), link_id)
    before = len(ledger.events())
    lesson = add_mission_item(
        ledger,
        identity_id,
        link.mission_id,
        "lesson",
        lesson_summary,
        status="proposed",
        confidence=confidence,
        evidence_refs=[link.link_id, link.commit_hash, *link.evidence_ids],
        reason=reason or f"checkpoint lesson from {link.link_id}",
    )
    event = ledger.append(
        "checkpoint.lesson_candidate_proposed",
        identity_id,
        {
            "link_id": link.link_id,
            "mission_id": link.mission_id,
            "mission_item_id": lesson.item_id,
            "commit_hash": link.commit_hash,
            "confidence": confidence,
            "reason": reason,
        },
    )
    growth = [
        created.payload
        for created in ledger.events()[before:]
        if created.event_type == "lucien.growth_proposed"
    ]
    return {
        "checkpoint_link": link.to_dict(),
        "mission_lesson": lesson.to_dict(),
        "growth_candidates": growth,
        "event": event.to_dict(),
    }


def require_checkpoint_link(
    events: list[ContinuityEvent],
    link_id: str,
) -> CheckpointLinkRecord:
    for record in checkpoint_link_records_from_events(events):
        if record.link_id == link_id:
            return record
    raise ValueError(f"Checkpoint link not found: {link_id}")


def checkpoint_lesson_candidates_from_events(
    events: list[ContinuityEvent],
) -> list[dict[str, Any]]:
    return [
        event.payload
        for event in events
        if event.event_type == "checkpoint.lesson_candidate_proposed"
    ]


def auto_propose_checkpoint_skill_candidates(
    ledger: ContinuityLedger,
    identity_id: str,
    minimum_checkpoints: int = 2,
) -> list[SkillCandidateRecord]:
    events = ledger.events()
    existing_source_steps = {
        step_id
        for candidate in skill_candidates_from_events(events)
        for step_id in candidate.source_step_ids
    }
    grouped: dict[tuple[str, str], list[tuple[CheckpointLinkRecord, Any]]] = {}
    for link in checkpoint_link_records_from_events(events):
        for step_id in link.mission_step_ids:
            if step_id in existing_source_steps:
                continue
            step = require_mission_step(events, step_id)
            if step.execution_status != MissionStepExecutionStatus.COMPLETED:
                continue
            key = (step.required_tool, step.risk_level.value)
            grouped.setdefault(key, []).append((link, step))
    records: list[SkillCandidateRecord] = []
    for (required_tool, risk_level), pairs in grouped.items():
        checkpoint_ids = {link.link_id for link, _step in pairs}
        if len(checkpoint_ids) < minimum_checkpoints:
            continue
        steps = []
        seen_steps = set()
        for _link, step in pairs:
            if step.step_id in seen_steps:
                continue
            seen_steps.add(step.step_id)
            steps.append(step)
        if len(steps) < minimum_checkpoints:
            continue
        procedure = (
            f"Derived from {len(checkpoint_ids)} mission-linked checkpoint(s) "
            f"and {len(steps)} completed step(s) using {required_tool} at "
            f"{risk_level} risk. Reuse only after steward acceptance."
        )
        record = SkillCandidateRecord.create(
            identity_id=identity_id,
            name=f"Checkpoint-derived {required_tool} procedure",
            source_step_ids=[step.step_id for step in steps],
            required_tool=required_tool,
            risk_level=risk_level,
            procedure=procedure,
            reason="auto-proposed from repeated mission-linked checkpoints",
        )
        ledger.append("skill.candidate_proposed", identity_id, record.to_dict())
        ledger.append(
            "checkpoint.skill_candidate_proposed",
            identity_id,
            {
                "skill_id": record.skill_id,
                "checkpoint_link_ids": sorted(checkpoint_ids),
                "source_step_ids": record.source_step_ids,
                "required_tool": required_tool,
                "risk_level": risk_level,
                "minimum_checkpoints": minimum_checkpoints,
            },
        )
        records.append(record)
    return records


def checkpoint_skill_candidates_from_events(
    events: list[ContinuityEvent],
) -> list[dict[str, Any]]:
    return [
        event.payload
        for event in events
        if event.event_type == "checkpoint.skill_candidate_proposed"
    ]


def _resolve_commit_hash(commit_hash: str, project_root: Path) -> str:
    value = commit_hash.strip() or "HEAD"
    result = subprocess.run(
        ["git", "rev-parse", "--verify", value],
        cwd=project_root,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ValueError(f"Commit not found: {commit_hash}")
    return result.stdout.strip()
