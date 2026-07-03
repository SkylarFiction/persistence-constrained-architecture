from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .goals import (
    GoalRecord,
    create_goal_record,
    goal_records_from_events,
    link_goal_mission,
)
from .ledger import ContinuityLedger
from .manifest import IdentityManifest
from .missions import (
    MissionItemRecord,
    MissionRecord,
    add_mission_item,
    mission_briefs_from_events,
    open_mission,
)


@dataclass(frozen=True)
class CoherenceSeedSpec:
    title: str
    purpose: str
    success_criteria: str
    priority: str
    next_action: str
    mission_title: str
    problem: str
    values: list[str] = field(default_factory=list)
    hypothesis: str = ""
    evidence_need: str = ""
    risk: str = ""
    first_plan_step: str = ""


@dataclass(frozen=True)
class CoherenceSeedResult:
    goal: GoalRecord
    mission: MissionRecord
    created_goal: bool
    created_mission: bool
    linked_goal: GoalRecord
    items: list[MissionItemRecord]

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal.to_dict(),
            "mission": self.mission.to_dict(),
            "created_goal": self.created_goal,
            "created_mission": self.created_mission,
            "linked_goal": self.linked_goal.to_dict(),
            "items": [item.to_dict() for item in self.items],
        }


COHERENCE_PHYSICS_SEED_SPECS: list[CoherenceSeedSpec] = [
    CoherenceSeedSpec(
        title="Coherence Physics Research Map",
        purpose="Turn the Coherence Physics body of ideas into a navigable research map with claims, terms, evidence gaps, and next experiments.",
        success_criteria="A reviewed mission map exists with core claims, dependency structure, evidence needs, and one prioritized next research path.",
        priority="high",
        next_action="Build the first claim map and identify the strongest unresolved evidence gap.",
        mission_title="Map Coherence Physics Claims",
        problem="Coherence Physics has many connected ideas about persistence, recoverability, identity, collapse, and bounded transformation. The mission is to organize those ideas into a research map that Lucien can grow without treating unreviewed claims as proven.",
        values=["clarity", "evidence before certainty", "recoverable reasoning", "public legibility"],
        hypothesis="Coherence Physics can be represented as a claim graph where persistence and recoverability form the organizing spine.",
        evidence_need="Collect source excerpts, definitions, examples, simulations, and objections for each core claim before promoting it.",
        risk="Unreviewed philosophical language could harden into accepted doctrine without evidence links.",
        first_plan_step="Draft a first claim graph with 5-8 root claims and mark each as supported, speculative, or needing evidence.",
    ),
    CoherenceSeedSpec(
        title="Evidence Locker for Core Claims",
        purpose="Ground the strongest Coherence Physics claims in reviewed evidence records rather than memory or confidence alone.",
        success_criteria="At least ten core claims have linked evidence records with review status, confidence, and known objections.",
        priority="high",
        next_action="Create an evidence checklist for the highest-impact persistence and recovery claims.",
        mission_title="Ground Core Claims in Evidence",
        problem="Lucien should not grow Coherence Physics by repeating attractive claims. This mission builds an evidence spine for the framework so claims can be reviewed, disputed, revised, or marked provisional.",
        values=["traceability", "anti-hallucination", "claim humility", "reviewable evidence"],
        hypothesis="A governed evidence locker can separate promising theory from accepted claim, making Coherence Physics easier to critique and improve.",
        evidence_need="Add evidence records for definitions, mathematical sketches, simulations, examples, external references, and counterexamples.",
        risk="The system may overcount internally generated summaries as evidence unless steward review distinguishes source evidence from interpretation.",
        first_plan_step="List the first ten claims that require evidence before they can appear in public materials as more than provisional.",
    ),
    CoherenceSeedSpec(
        title="Delta Omega Mind Codex Expansion",
        purpose="Grow the Lucien/Delta Omega Mind material into a coherent technical charter for governed identity, agency, memory, recovery, and bounded autonomy.",
        success_criteria="A revised outline exists with sections for identity law, memory governance, mission work, tool permissions, recovery, and limits.",
        priority="medium",
        next_action="Produce a reviewed outline that distinguishes poetic framing from enforceable architecture.",
        mission_title="Expand Delta Omega Mind Codex",
        problem="The Delta Omega Mind material needs to evolve without blurring metaphor, architecture, and testable implementation. This mission turns the vision into a structured codex that Lucien can help maintain.",
        values=["identity continuity", "governed growth", "non-overclaiming", "human stewardship"],
        hypothesis="The Codex can become a bridge document between Coherence Physics, PCA, and Lucien's governed agent architecture.",
        evidence_need="Link each codex principle to a PCA mechanism, a limitation, or a future research question.",
        risk="The codex may drift into grand claims unless every identity or agency claim is constrained by PCA status and known limits.",
        first_plan_step="Create a section map separating principles, mechanisms, open questions, and non-claims.",
    ),
    CoherenceSeedSpec(
        title="Simulation and Fit Experiments",
        purpose="Turn Coherence Physics into experiments, simulations, and falsifiable probes instead of only conceptual writing.",
        success_criteria="A first experiment backlog exists with at least three runnable simulations or data-fit tasks and clear expected observations.",
        priority="medium",
        next_action="Select one simple persistence/recovery simulation that can be implemented and inspected locally.",
        mission_title="Design Coherence Experiments",
        problem="For Coherence Physics to mature, Lucien needs missions that convert claims about persistence, recovery, slippage, and collapse into runnable experiments or measurable proxies.",
        values=["testability", "small experiments", "falsifiability", "reproducible traces"],
        hypothesis="Persistence and recoverability claims can be explored through small simulations that expose thresholds, recovery windows, and collapse behavior.",
        evidence_need="Define measurable variables, expected behavior, failure cases, and what would count against the hypothesis.",
        risk="Simulations may become illustrative metaphors unless they are labeled as exploratory and tied to explicit assumptions.",
        first_plan_step="Propose three candidate simulations and choose the lowest-risk one for a first implementation mission.",
    ),
    CoherenceSeedSpec(
        title="Public Paper and Demo Narrative",
        purpose="Prepare Coherence Physics and PCA for public explanation through a paper outline, demo story, and plain-English claims.",
        success_criteria="A public narrative exists that explains the problem, the PCA mechanism, what Lucien demonstrates, and what is explicitly not claimed.",
        priority="medium",
        next_action="Draft the first public outline using PCA as the concrete artifact and Coherence Physics as the research motivation.",
        mission_title="Write Public Coherence Narrative",
        problem="The public story needs to be powerful but sober: Lucien and PCA should be understandable without claims of consciousness, personhood, or AGI.",
        values=["public clarity", "no hype", "technical honesty", "reviewable demo"],
        hypothesis="The strongest public lane is continuity governance: smooth output is not proof that a system preserved identity through change.",
        evidence_need="Link each public claim to repo docs, demo traces, screenshots, known limits, and reproducible commands.",
        risk="Public materials could overstate what Lucien is today instead of showing the local governed workbench accurately.",
        first_plan_step="Draft a one-page outline: problem, mechanism, demo proof, limits, and next research questions.",
    ),
]


def seed_coherence_physics_goals(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
) -> list[CoherenceSeedResult]:
    results: list[CoherenceSeedResult] = []
    for spec in COHERENCE_PHYSICS_SEED_SPECS:
        goal, created_goal = _get_or_create_goal(ledger, manifest, spec)
        mission, created_mission = _get_or_create_mission(ledger, manifest, spec)
        linked_goal = _link_goal_if_needed(ledger, manifest, goal, mission)
        items: list[MissionItemRecord] = []
        if created_mission or not _mission_has_seed_items(ledger, mission.mission_id):
            items = _seed_mission_items(ledger, manifest, mission, spec)
        results.append(
            CoherenceSeedResult(
                goal=goal,
                mission=mission,
                created_goal=created_goal,
                created_mission=created_mission,
                linked_goal=linked_goal,
                items=items,
            )
        )
    return results


def render_coherence_seed_text(results: list[CoherenceSeedResult]) -> str:
    lines = [
        "Coherence Physics Seed",
        f"Tracks: {len(results)}",
    ]
    for result in results:
        lines.extend(
            [
                "",
                result.goal.title,
                f"goal: {result.goal.goal_id} / {'created' if result.created_goal else 'existing'}",
                f"mission: {result.mission.mission_id} / {'created' if result.created_mission else 'existing'}",
                f"seed items: {len(result.items)}",
                f"next: {result.linked_goal.next_recommended_action}",
            ]
        )
    return "\n".join(lines)


def _get_or_create_goal(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    spec: CoherenceSeedSpec,
) -> tuple[GoalRecord, bool]:
    for goal in goal_records_from_events(ledger.events()):
        if goal.title == spec.title:
            return goal, False
    return (
        create_goal_record(
            ledger,
            manifest.system_id,
            title=spec.title,
            purpose=spec.purpose,
            success_criteria=spec.success_criteria,
            priority=spec.priority,
            next_recommended_action=spec.next_action,
            review_state="pending",
            reason="seeded Coherence Physics research goal",
        ),
        True,
    )


def _get_or_create_mission(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    spec: CoherenceSeedSpec,
) -> tuple[MissionRecord, bool]:
    for brief in mission_briefs_from_events(ledger.events()):
        if brief.mission.title == spec.mission_title:
            return brief.mission, False
    return (
        open_mission(
            ledger,
            manifest.system_id,
            title=spec.mission_title,
            problem_statement=spec.problem,
            values=spec.values,
            reason="seeded Coherence Physics research mission",
        ),
        True,
    )


def _link_goal_if_needed(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    goal: GoalRecord,
    mission: MissionRecord,
) -> GoalRecord:
    if mission.mission_id in goal.linked_mission_ids:
        return goal
    return link_goal_mission(
        ledger,
        manifest.system_id,
        goal.goal_id,
        mission.mission_id,
        reason="linked Coherence Physics seed mission to goal",
    )


def _mission_has_seed_items(ledger: ContinuityLedger, mission_id: str) -> bool:
    for brief in mission_briefs_from_events(ledger.events()):
        if brief.mission.mission_id == mission_id:
            return bool(brief.items)
    return False


def _seed_mission_items(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    mission: MissionRecord,
    spec: CoherenceSeedSpec,
) -> list[MissionItemRecord]:
    return [
        add_mission_item(
            ledger,
            manifest.system_id,
            mission.mission_id,
            "hypothesis",
            spec.hypothesis,
            status="proposed",
            confidence="low",
            reason="seeded Coherence Physics hypothesis",
            bridge_reflection=False,
        ),
        add_mission_item(
            ledger,
            manifest.system_id,
            mission.mission_id,
            "evidence",
            spec.evidence_need,
            status="needed",
            confidence="unknown",
            reason="seeded Coherence Physics evidence need",
            bridge_reflection=False,
        ),
        add_mission_item(
            ledger,
            manifest.system_id,
            mission.mission_id,
            "risk",
            spec.risk,
            status="open",
            confidence="medium",
            reason="seeded Coherence Physics research risk",
            bridge_reflection=False,
        ),
        add_mission_item(
            ledger,
            manifest.system_id,
            mission.mission_id,
            "plan_step",
            spec.first_plan_step,
            status="proposed",
            confidence="medium",
            reason="seeded Coherence Physics first plan step",
            bridge_reflection=False,
        ),
    ]
