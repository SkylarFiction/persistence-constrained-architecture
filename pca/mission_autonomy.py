from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid

from .ledger import ContinuityEvent, ContinuityLedger
from .mission_flow import MissionPhase, mission_flow_from_events
from .mission_steps import (
    MissionStepExecutionStatus,
    MissionStepRecord,
    mission_step_records_from_events,
    propose_mission_step,
)
from .missions import require_mission
from .skill_memory import accepted_skills_from_events
from .steward_inbox import steward_inbox
from .tool_router import TOOL_REGISTRY


@dataclass(frozen=True)
class MissionAutonomyRecommendation:
    recommendation_id: str
    identity_id: str
    mission_id: str
    can_propose: bool
    description: str
    risk_level: str
    required_tool: str
    expected_outcome: str
    reason: str
    blockers: list[str] = field(default_factory=list)
    source: str = "mission_autonomy_loop"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @classmethod
    def create(
        cls,
        identity_id: str,
        mission_id: str,
        can_propose: bool,
        description: str = "",
        risk_level: str = "low",
        required_tool: str = "list_files",
        expected_outcome: str = "",
        reason: str = "",
        blockers: list[str] | None = None,
    ) -> "MissionAutonomyRecommendation":
        return cls(
            recommendation_id=f"mission_autonomy_{uuid.uuid4()}",
            identity_id=identity_id,
            mission_id=mission_id,
            can_propose=can_propose,
            description=description,
            risk_level=risk_level,
            required_tool=required_tool,
            expected_outcome=expected_outcome,
            reason=reason,
            blockers=blockers or [],
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MissionAutonomyRecommendation":
        return cls(
            recommendation_id=str(data["recommendation_id"]),
            identity_id=str(data["identity_id"]),
            mission_id=str(data["mission_id"]),
            can_propose=bool(data["can_propose"]),
            description=str(data.get("description", "")),
            risk_level=str(data.get("risk_level", "low")),
            required_tool=str(data.get("required_tool", "list_files")),
            expected_outcome=str(data.get("expected_outcome", "")),
            reason=str(data.get("reason", "")),
            blockers=[str(item) for item in data.get("blockers", [])],
            source=str(data.get("source", "mission_autonomy_loop")),
            created_at=str(data["created_at"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "identity_id": self.identity_id,
            "mission_id": self.mission_id,
            "can_propose": self.can_propose,
            "description": self.description,
            "risk_level": self.risk_level,
            "required_tool": self.required_tool,
            "expected_outcome": self.expected_outcome,
            "reason": self.reason,
            "blockers": self.blockers,
            "source": self.source,
            "created_at": self.created_at,
        }


def mission_autonomy_recommendations_from_events(
    events: list[ContinuityEvent],
) -> list[MissionAutonomyRecommendation]:
    return [
        MissionAutonomyRecommendation.from_dict(event.payload)
        for event in events
        if event.event_type == "mission.autonomy_recommended"
    ]


def recommend_next_mission_step(
    ledger: ContinuityLedger,
    identity_id: str,
    mission_id: str,
) -> MissionAutonomyRecommendation:
    events = ledger.events()
    recommendation = recommend_next_mission_step_from_events(
        events,
        identity_id,
        mission_id,
        inbox_items=[item.to_dict() for item in steward_inbox(ledger)],
    )
    ledger.append("mission.autonomy_recommended", identity_id, recommendation.to_dict())
    return recommendation


def recommend_next_mission_step_from_events(
    events: list[ContinuityEvent],
    identity_id: str,
    mission_id: str,
    inbox_items: list[dict[str, Any]] | None = None,
) -> MissionAutonomyRecommendation:
    require_mission(events, mission_id)
    flow = mission_flow_from_events(events, mission_id)
    open_steps = [
        step
        for step in mission_step_records_from_events(events, mission_id)
        if step.execution_status
        in {
            MissionStepExecutionStatus.PROPOSED,
            MissionStepExecutionStatus.READY,
            MissionStepExecutionStatus.RUNNING,
        }
    ]
    if flow.blockers:
        return MissionAutonomyRecommendation.create(
            identity_id=identity_id,
            mission_id=mission_id,
            can_propose=False,
            reason="mission has blockers that require steward attention",
            blockers=flow.blockers,
        )
    if open_steps:
        return MissionAutonomyRecommendation.create(
            identity_id=identity_id,
            mission_id=mission_id,
            can_propose=False,
            reason="mission already has an active proposed, ready, or running step",
            blockers=[f"active step {step.step_id}: {step.execution_status.value}" for step in open_steps],
        )
    inbox_items = inbox_items or []
    high_priority = [
        item for item in inbox_items if item.get("severity") in {"high", "critical"}
    ]
    if high_priority:
        return MissionAutonomyRecommendation.create(
            identity_id=identity_id,
            mission_id=mission_id,
            can_propose=False,
            reason="high-priority steward inbox items should be reviewed before new mission work",
            blockers=[item["inbox_id"] for item in high_priority[:5]],
        )
    skill = _matching_skill(events)
    if skill is not None:
        return MissionAutonomyRecommendation.create(
            identity_id=identity_id,
            mission_id=mission_id,
            can_propose=True,
            description=f"Apply accepted skill: {skill.name}.",
            risk_level=skill.risk_level if skill.risk_level in {"low", "medium", "high"} else "low",
            required_tool=skill.required_tool if skill.required_tool in TOOL_REGISTRY else "git_status",
            expected_outcome="A governed result from an accepted reusable skill.",
            reason=f"accepted skill {skill.skill_id} is available for mission work",
        )
    return _phase_recommendation(identity_id, mission_id, flow.phase)


def propose_autonomous_mission_step(
    ledger: ContinuityLedger,
    identity_id: str,
    mission_id: str,
) -> dict[str, Any]:
    recommendation = recommend_next_mission_step(ledger, identity_id, mission_id)
    if not recommendation.can_propose:
        return {"recommendation": recommendation.to_dict(), "mission_step": None}
    step = propose_mission_step(
        ledger,
        identity_id,
        mission_id,
        description=recommendation.description,
        risk_level=recommendation.risk_level,
        required_tool=recommendation.required_tool,
        expected_outcome=recommendation.expected_outcome,
        reason=f"autonomous mission loop: {recommendation.reason}",
    )
    return {"recommendation": recommendation.to_dict(), "mission_step": step.to_dict()}


def _phase_recommendation(
    identity_id: str,
    mission_id: str,
    phase: MissionPhase,
) -> MissionAutonomyRecommendation:
    if phase == MissionPhase.INTAKE:
        return MissionAutonomyRecommendation.create(
            identity_id=identity_id,
            mission_id=mission_id,
            can_propose=True,
            description="Survey available project context for mission intake.",
            risk_level="low",
            required_tool="list_files",
            expected_outcome="A bounded inventory of local project context for the mission.",
            reason="mission is in intake and needs inspectable starting context",
        )
    if phase == MissionPhase.EVIDENCE_REVIEW:
        return MissionAutonomyRecommendation.create(
            identity_id=identity_id,
            mission_id=mission_id,
            can_propose=True,
            description="Preview an evidence source for the active mission.",
            risk_level="low",
            required_tool="read_file",
            expected_outcome="A bounded evidence preview that can be reviewed before use.",
            reason="mission needs evidence before planning",
        )
    if phase == MissionPhase.PLANNING:
        return MissionAutonomyRecommendation.create(
            identity_id=identity_id,
            mission_id=mission_id,
            can_propose=True,
            description="Check local project status before drafting the next plan step.",
            risk_level="low",
            required_tool="git_status",
            expected_outcome="A non-mutating status snapshot for planning.",
            reason="mission is ready for planning under low-risk local inspection",
        )
    if phase == MissionPhase.OUTCOME_REVIEW:
        return MissionAutonomyRecommendation.create(
            identity_id=identity_id,
            mission_id=mission_id,
            can_propose=True,
            description="Review local context before extracting mission lessons.",
            risk_level="low",
            required_tool="git_status",
            expected_outcome="A local status snapshot to support outcome review.",
            reason="mission outcome needs review before lesson growth",
        )
    return MissionAutonomyRecommendation.create(
        identity_id=identity_id,
        mission_id=mission_id,
        can_propose=False,
        reason=f"mission phase {phase.value} does not need a new autonomous step",
        blockers=[f"phase={phase.value}"],
    )


def _matching_skill(events: list[ContinuityEvent]):
    accepted = accepted_skills_from_events(events)
    if not accepted:
        return None
    for skill in reversed(accepted):
        if skill.required_tool in TOOL_REGISTRY:
            return skill
    return None
