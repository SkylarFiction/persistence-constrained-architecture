from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .evidence_locker import add_evidence, link_evidence
from .ledger import ContinuityLedger
from .mission_flow import MissionPhase, mission_flow
from .missions import MissionItemKind, add_mission_item, require_mission


@dataclass(frozen=True)
class MissionOnboardingState:
    mission_id: str
    title: str
    phase: str
    needed: list[str]
    ready: bool
    recommended_action: str
    questions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "phase": self.phase,
            "needed": self.needed,
            "ready": self.ready,
            "recommended_action": self.recommended_action,
            "questions": self.questions,
        }


def mission_onboarding_state(
    ledger: ContinuityLedger,
    mission_id: str,
) -> MissionOnboardingState:
    mission = require_mission(ledger.events(), mission_id)
    flow = mission_flow(ledger, mission_id)
    counts = flow.counts
    needed = [
        kind
        for kind in [
            MissionItemKind.HYPOTHESIS.value,
            MissionItemKind.EVIDENCE.value,
            MissionItemKind.RISK.value,
        ]
        if not counts.get(kind, 0)
    ]
    ready = bool(needed) and flow.phase in {
        MissionPhase.INTAKE,
        MissionPhase.HYPOTHESIS_BUILDING,
        MissionPhase.EVIDENCE_REVIEW,
        MissionPhase.PLANNING,
    }
    return MissionOnboardingState(
        mission_id=mission_id,
        title=mission.title,
        phase=flow.phase.value,
        needed=needed,
        ready=ready,
        recommended_action=(
            "Create a starter hypothesis, evidence need, and risk review."
            if ready
            else "Mission already has the starter structure."
        ),
        questions=[
            "What claim could be tested or clarified first?",
            "What evidence would make that claim stronger or weaker?",
            "What is the main overclaiming or misuse risk?",
        ],
    )


def create_mission_onboarding_pack(
    ledger: ContinuityLedger,
    identity_id: str,
    mission_id: str,
    reason: str = "",
) -> dict[str, Any]:
    state = mission_onboarding_state(ledger, mission_id)
    if not state.ready:
        return {"created": [], "onboarding": state.to_dict()}
    created = []
    evidence_records = []
    evidence_links = []
    if MissionItemKind.HYPOTHESIS.value in state.needed:
        created.append(
            add_mission_item(
                ledger,
                identity_id,
                mission_id=mission_id,
                kind=MissionItemKind.HYPOTHESIS,
                summary=(
                    f"First testable hypothesis for {state.title}: a core claim can be "
                    "made clearer by stating what observation would support it and what "
                    "observation would weaken it."
                ),
                status="proposed",
                confidence="low",
                reason=reason or "created by mission onboarding wizard",
            )
        )
    if MissionItemKind.EVIDENCE.value in state.needed:
        evidence_summary = (
            f"Evidence request for {state.title}: find one source, note, "
            "experiment, prior claim, or observation that can support or weaken "
            "the starter hypothesis before treating it as accepted."
        )
        created.append(
            add_mission_item(
                ledger,
                identity_id,
                mission_id=mission_id,
                kind=MissionItemKind.EVIDENCE,
                summary=evidence_summary,
                status="needed",
                confidence="unknown",
                reason=reason or "created by mission onboarding wizard",
            )
        )
        evidence = add_evidence(
            ledger,
            identity_id,
            source_type="mission_observation",
            summary=evidence_summary,
            source=f"mission:{mission_id}:onboarding:evidence_request",
            confidence="unknown",
            reason=reason or "created by mission onboarding wizard",
        )
        evidence_records.append(evidence)
        evidence_links.append(
            link_evidence(
                ledger,
                identity_id,
                evidence.evidence_id,
                "mission",
                mission_id,
                reason="mission onboarding evidence request",
            )
        )
    if MissionItemKind.RISK.value in state.needed:
        created.append(
            add_mission_item(
                ledger,
                identity_id,
                mission_id=mission_id,
                kind=MissionItemKind.RISK,
                summary=(
                    f"Risk for {state.title}: avoid converting speculative Coherence "
                    "Physics language into accepted truth without evidence review."
                ),
                status="open",
                confidence="medium",
                reason=reason or "created by mission onboarding wizard",
            )
        )
    return {
        "created": [item.to_dict() for item in created],
        "evidence": [record.to_dict() for record in evidence_records],
        "evidence_links": [record.to_dict() for record in evidence_links],
        "onboarding": mission_onboarding_state(ledger, mission_id).to_dict(),
    }
