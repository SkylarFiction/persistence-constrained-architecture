from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .evidence_locker import EvidenceReviewStatus, evidence_records_from_events
from .evidence_locker import review_evidence
from .growth import (
    GrowthReviewDecision,
    GrowthStatus,
    growth_records_from_events,
    review_growth,
)
from .growth_conflicts import (
    growth_conflict_records_from_events,
    growth_conflict_resolution_records_from_events,
    resolve_growth_conflict,
)
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .mission_flow import mission_flows_from_events
from .recovery import RecoveryStatus, recovery_records_from_events
from .reflection_queue import (
    ReflectionTaskStatus,
    active_reflection_tasks,
    resolve_matching_reflection_tasks,
    update_reflection_task,
)
from .skill_memory import (
    SkillCandidateStatus,
    review_skill_candidate,
    skill_candidates_from_events,
)
from .state import derive_current_claim


@dataclass(frozen=True)
class StewardInboxItem:
    inbox_id: str
    source_type: str
    source_id: str
    severity: str
    title: str
    reason: str
    linked_target_type: str = ""
    linked_target_id: str = ""
    recommended_actions: list[str] = field(default_factory=list)
    created_at: str = ""
    status: str = "open"

    def to_dict(self) -> dict[str, Any]:
        return {
            "inbox_id": self.inbox_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "severity": self.severity,
            "title": self.title,
            "reason": self.reason,
            "linked_target_type": self.linked_target_type,
            "linked_target_id": self.linked_target_id,
            "recommended_actions": self.recommended_actions,
            "created_at": self.created_at,
            "status": self.status,
        }


def steward_inbox(
    ledger: ContinuityLedger,
    source_type: str | None = None,
    high_priority: bool = False,
) -> list[StewardInboxItem]:
    events = ledger.events()
    items: list[StewardInboxItem] = []
    items.extend(_reflection_task_items(events))
    items.extend(_growth_items(events))
    items.extend(_skill_items(events))
    items.extend(_evidence_items(events))
    items.extend(_conflict_items(events))
    items.extend(_mission_items(events))
    items.extend(_recovery_items(events))
    items.sort(key=lambda item: (item.created_at, item.inbox_id))
    if source_type:
        normalized = _normalize_filter(source_type)
        items = [item for item in items if _filter_matches(item, normalized)]
    if high_priority:
        items = [item for item in items if item.severity in {"high", "critical"}]
    return items


def find_steward_inbox_item(
    ledger: ContinuityLedger,
    inbox_id: str,
) -> StewardInboxItem | None:
    for item in steward_inbox(ledger):
        if item.inbox_id == inbox_id:
            return item
    return None


def apply_steward_inbox_action(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    inbox_id: str,
    action: str,
    reason: str = "",
    reviewer: str = "steward",
) -> dict[str, Any]:
    item = find_steward_inbox_item(ledger, inbox_id)
    if item is None:
        raise ValueError(f"Steward inbox item not found: {inbox_id}")
    normalized_action = action.strip().lower().replace("-", "_")
    reason = reason or f"steward inbox action {normalized_action}"
    if item.source_type in {"growth_review", "memory_review"}:
        if normalized_action == "request_evidence" and item.source_type == "memory_review":
            event = ledger.append(
                "lucien.memory_evidence_requested",
                manifest.system_id,
                {
                    "growth_id": item.source_id,
                    "reason": reason,
                    "requested_by": reviewer,
                },
            )
            return {"item": item.to_dict(), "event": event.to_dict()}
        if normalized_action not in {"accept", "reject"}:
            raise ValueError("growth inbox action must be accept, reject, or request_evidence")
        growth, review = review_growth(
            ledger=ledger,
            identity_id=manifest.system_id,
            growth_id=item.source_id,
            decision=(
                GrowthReviewDecision.ACCEPT
                if normalized_action == "accept"
                else GrowthReviewDecision.REJECT
            ),
            reviewer=reviewer,
            reason=reason,
            current_claim=derive_current_claim(ledger, manifest)[0],
        )
        resolved_tasks = resolve_matching_reflection_tasks(
            ledger,
            manifest.system_id,
            "review_growth",
            "growth record",
            f"reviewed by steward inbox {review.review_id}",
        )
        return {
            "item": item.to_dict(),
            "growth": growth.to_dict(),
            "review": review.to_dict(),
            "resolved_tasks": [task.to_dict() for task in resolved_tasks],
        }
    if item.source_type == "reflection_task":
        if normalized_action not in {"resolve", "dismiss"}:
            raise ValueError("reflection task action must be resolve or dismiss")
        task = update_reflection_task(
            ledger,
            manifest.system_id,
            item.source_id,
            (
                ReflectionTaskStatus.RESOLVED
                if normalized_action == "resolve"
                else ReflectionTaskStatus.DISMISSED
            ),
            reason=reason,
        )
        return {"item": item.to_dict(), "task": task.to_dict()}
    if item.source_type == "skill_candidate":
        if normalized_action not in {"accept", "reject"}:
            raise ValueError("skill candidate action must be accept or reject")
        skill = review_skill_candidate(
            ledger,
            manifest.system_id,
            item.source_id,
            normalized_action,
            reason=reason,
        )
        return {"item": item.to_dict(), "skill": skill.to_dict()}
    if item.source_type == "evidence_review":
        status_by_action = {
            "accept": EvidenceReviewStatus.REVIEWED.value,
            "resolve": EvidenceReviewStatus.REVIEWED.value,
            "reject": EvidenceReviewStatus.REJECTED.value,
            "mark_stale": EvidenceReviewStatus.STALE.value,
        }
        if normalized_action not in status_by_action:
            raise ValueError("evidence action must be accept, resolve, reject, or mark_stale")
        evidence = review_evidence(
            ledger,
            manifest.system_id,
            item.source_id,
            status_by_action[normalized_action],
            reviewer=reviewer,
            reason=reason,
        )
        return {"item": item.to_dict(), "evidence": evidence.to_dict()}
    if item.source_type == "conflict_resolution":
        if normalized_action not in {"accept_new", "keep_existing", "fork"}:
            raise ValueError("conflict action must be accept_new, keep_existing, or fork")
        resolution = resolve_growth_conflict(
            ledger,
            manifest.system_id,
            item.source_id,
            normalized_action,
            resolved_by=reviewer,
            reason=reason,
        )
        resolved_tasks = resolve_matching_reflection_tasks(
            ledger,
            manifest.system_id,
            "resolve_conflict",
            "growth conflict",
            f"resolved by steward inbox {resolution.resolution_id}",
        )
        return {
            "item": item.to_dict(),
            "resolution": resolution.to_dict(),
            "resolved_tasks": [task.to_dict() for task in resolved_tasks],
        }
    raise ValueError(
        f"Actions for {item.source_type} are not routed yet; use the linked workflow."
    )


def _reflection_task_items(events) -> list[StewardInboxItem]:
    items = []
    for task in active_reflection_tasks(events):
        items.append(
            StewardInboxItem(
                inbox_id=f"reflection_task:{task.task_id}",
                source_type="reflection_task",
                source_id=task.task_id,
                severity=task.severity,
                title=f"{task.kind.value.replace('_', ' ').title()}",
                reason=task.reason,
                linked_target_type="reflection",
                linked_target_id=task.source_reflection_id,
                recommended_actions=["resolve", "dismiss"],
                created_at=task.created_at,
                status=task.status.value,
            )
        )
    return items


def _growth_items(events) -> list[StewardInboxItem]:
    items = []
    for record in growth_records_from_events(events):
        if record.status not in {GrowthStatus.PROPOSED, GrowthStatus.REQUIRES_REVIEW}:
            continue
        source_type = "memory_review" if record.kind.value == "memory" else "growth_review"
        actions = ["accept", "reject"]
        if record.kind.value == "memory":
            actions.append("request_evidence")
        items.append(
            StewardInboxItem(
                inbox_id=f"{source_type}:{record.growth_id}",
                source_type=source_type,
                source_id=record.growth_id,
                severity=_severity_for_impact(record.identity_impact.value),
                title=f"{record.kind.value.replace('_', ' ').title()} growth needs review",
                reason=record.reason or "Pending governed growth review.",
                linked_target_type="growth",
                linked_target_id=record.growth_id,
                recommended_actions=actions,
                created_at=record.created_at,
                status=record.status.value,
            )
        )
    return items


def _skill_items(events) -> list[StewardInboxItem]:
    items = []
    for record in skill_candidates_from_events(events):
        if record.status != SkillCandidateStatus.PROPOSED:
            continue
        items.append(
            StewardInboxItem(
                inbox_id=f"skill_candidate:{record.skill_id}",
                source_type="skill_candidate",
                source_id=record.skill_id,
                severity=_severity_for_risk(record.risk_level),
                title=f"Skill candidate: {record.name}",
                reason=record.reason or "Skill candidate awaits steward review.",
                linked_target_type="skill",
                linked_target_id=record.skill_id,
                recommended_actions=["accept", "reject"],
                created_at=record.created_at,
                status=record.status.value,
            )
        )
    return items


def _evidence_items(events) -> list[StewardInboxItem]:
    items = []
    for record in evidence_records_from_events(events):
        if record.review_status not in {
            EvidenceReviewStatus.RAW,
            EvidenceReviewStatus.DISPUTED,
            EvidenceReviewStatus.STALE,
        }:
            continue
        actions = ["accept", "reject", "mark_stale"]
        if record.review_status == EvidenceReviewStatus.DISPUTED:
            actions = ["resolve", "reject", "mark_stale"]
        items.append(
            StewardInboxItem(
                inbox_id=f"evidence_review:{record.evidence_id}",
                source_type="evidence_review",
                source_id=record.evidence_id,
                severity="high" if record.review_status == EvidenceReviewStatus.DISPUTED else "medium",
                title=f"Evidence {record.review_status.value}",
                reason=record.reason or f"Evidence is {record.review_status.value}.",
                linked_target_type="evidence",
                linked_target_id=record.evidence_id,
                recommended_actions=actions,
                created_at=record.created_at,
                status=record.review_status.value,
            )
        )
    return items


def _conflict_items(events) -> list[StewardInboxItem]:
    resolved_ids = {
        record.conflict_id for record in growth_conflict_resolution_records_from_events(events)
    }
    items = []
    for record in growth_conflict_records_from_events(events):
        if record.conflict_id in resolved_ids:
            continue
        items.append(
            StewardInboxItem(
                inbox_id=f"conflict_resolution:{record.conflict_id}",
                source_type="conflict_resolution",
                source_id=record.conflict_id,
                severity=record.severity,
                title=f"Growth conflict: {record.conflict_type}",
                reason=record.reason,
                linked_target_type="growth",
                linked_target_id=record.proposed_growth_id,
                recommended_actions=["accept_new", "keep_existing", "fork"],
                created_at=record.created_at,
                status="open",
            )
        )
    return items


def _mission_items(events) -> list[StewardInboxItem]:
    items = []
    for flow in mission_flows_from_events(events):
        if not flow.blockers:
            continue
        items.append(
            StewardInboxItem(
                inbox_id=f"mission_review:{flow.mission_id}",
                source_type="mission_review",
                source_id=flow.mission_id,
                severity="high",
                title=f"Mission blocked: {flow.phase.value}",
                reason="; ".join(flow.blockers),
                linked_target_type="mission",
                linked_target_id=flow.mission_id,
                recommended_actions=["resolve", "dismiss"],
                created_at="",
                status="blocked",
            )
        )
    return items


def _recovery_items(events) -> list[StewardInboxItem]:
    items = []
    for record in recovery_records_from_events(events):
        if record.status in {RecoveryStatus.CERTIFIED, RecoveryStatus.REJECTED}:
            continue
        items.append(
            StewardInboxItem(
                inbox_id=f"recovery_review:{record.recovery_id}",
                source_type="recovery_review",
                source_id=record.recovery_id,
                severity="high",
                title=f"Recovery requires review: {record.status.value}",
                reason=record.reason,
                linked_target_type="recovery",
                linked_target_id=record.recovery_id,
                recommended_actions=["resolve", "dismiss"],
                created_at=record.created_at,
                status=record.status.value,
            )
        )
    return items


def _severity_for_impact(impact: str) -> str:
    if impact in {"high", "identity_defining"}:
        return "high"
    if impact == "medium":
        return "medium"
    return "low"


def _severity_for_risk(risk: str) -> str:
    if risk in {"high", "identity_defining"}:
        return "high"
    if risk == "medium":
        return "medium"
    return "low"


def _normalize_filter(value: str) -> str:
    return value.strip().lower().replace("-", "_")


def _filter_matches(item: StewardInboxItem, normalized: str) -> bool:
    if normalized in {"all", ""}:
        return True
    groups = {
        "growth": {"growth_review"},
        "memory": {"memory_review"},
        "skills": {"skill_candidate"},
        "skill": {"skill_candidate"},
        "evidence": {"evidence_review"},
        "missions": {"mission_review"},
        "mission": {"mission_review"},
        "conflicts": {"conflict_resolution"},
        "conflict": {"conflict_resolution"},
        "recovery": {"recovery_review"},
        "reflection": {"reflection_task"},
    }
    return item.source_type in groups.get(normalized, {normalized})
