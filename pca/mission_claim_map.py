from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .argument_graph import (
    ArgumentNodeKind,
    ArgumentRelation,
    argument_edges_for_mission,
    argument_nodes_for_mission,
)
from .evidence_locker import evidence_for_target
from .ledger import ContinuityLedger
from .missions import MissionItemKind, mission_briefs_from_events, require_mission


@dataclass(frozen=True)
class MissionClaimMapEntry:
    claim_item_id: str
    claim_hash: str
    claim_status: str
    confidence: str
    evidence_count: int
    reviewed_evidence_count: int
    disputed_evidence_count: int
    stale_evidence_count: int
    support_status: str
    claim_text: str = ""
    claim_type: str = "mission_hypothesis"
    direct_support_count: int = 0
    counterevidence_count: int = 0
    dependency_claims: tuple[str, ...] = ()
    falsification_condition: str = ""
    review_state: str = "raw"

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_item_id": self.claim_item_id,
            "claim_hash": self.claim_hash,
            "claim_status": self.claim_status,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "reviewed_evidence_count": self.reviewed_evidence_count,
            "disputed_evidence_count": self.disputed_evidence_count,
            "stale_evidence_count": self.stale_evidence_count,
            "support_status": self.support_status,
            "claim_text": self.claim_text,
            "claim_type": self.claim_type,
            "direct_support_count": self.direct_support_count,
            "counterevidence_count": self.counterevidence_count,
            "dependency_claims": list(self.dependency_claims),
            "falsification_condition": self.falsification_condition,
            "review_state": self.review_state,
        }


def mission_claim_map(
    ledger: ContinuityLedger,
    mission_id: str,
) -> dict[str, Any]:
    mission = require_mission(ledger.events(), mission_id)
    brief = next(
        brief for brief in mission_briefs_from_events(ledger.events())
        if brief.mission.mission_id == mission_id
    )
    linked_evidence = evidence_for_target(ledger.events(), "mission", mission_id)
    evidence_statuses = [
        str((item.get("evidence") or {}).get("review_status", "raw"))
        for item in linked_evidence
    ]
    mission_entries = [
        MissionClaimMapEntry(
            claim_item_id=item.item_id,
            claim_hash=item.summary_sha256,
            claim_status=item.status,
            confidence=item.confidence,
            evidence_count=len(linked_evidence),
            reviewed_evidence_count=evidence_statuses.count("reviewed"),
            disputed_evidence_count=evidence_statuses.count("disputed"),
            stale_evidence_count=evidence_statuses.count("stale"),
            support_status=_support_status(evidence_statuses),
            claim_text=f"Mission hypothesis {item.summary_sha256[:16]}",
            direct_support_count=len(linked_evidence),
            review_state=_support_status(evidence_statuses),
        )
        for item in brief.items
        if item.kind == MissionItemKind.HYPOTHESIS
    ]
    argument_entries = _argument_claim_entries(ledger, mission_id)
    entries = [*mission_entries, *argument_entries]
    return {
        "mission_id": mission_id,
        "mission_title": mission.title,
        "claim_count": len(entries),
        "evidence_count": len(linked_evidence),
        "reviewed_evidence_count": evidence_statuses.count("reviewed"),
        "raw_evidence_count": evidence_statuses.count("raw"),
        "disputed_evidence_count": evidence_statuses.count("disputed"),
        "stale_evidence_count": evidence_statuses.count("stale"),
        "unsupported_claim_count": sum(
            1 for entry in entries if entry.support_status == "unsupported"
        ),
        "entries": [entry.to_dict() for entry in entries],
    }


def mission_claim_maps(ledger: ContinuityLedger) -> dict[str, dict[str, Any]]:
    return {
        brief.mission.mission_id: mission_claim_map(ledger, brief.mission.mission_id)
        for brief in mission_briefs_from_events(ledger.events())
    }


def _support_status(evidence_statuses: list[str]) -> str:
    if not evidence_statuses:
        return "unsupported"
    if any(status == "disputed" for status in evidence_statuses):
        return "disputed"
    if any(status == "reviewed" for status in evidence_statuses):
        return "reviewed_support"
    if any(status == "stale" for status in evidence_statuses):
        return "stale_support"
    return "raw_support"


def _argument_claim_entries(
    ledger: ContinuityLedger,
    mission_id: str,
) -> list[MissionClaimMapEntry]:
    nodes = argument_nodes_for_mission(ledger.events(), mission_id)
    edges = argument_edges_for_mission(ledger.events(), mission_id)
    if not nodes:
        return []
    nodes_by_id = {node.node_id: node for node in nodes}
    claim_nodes = [node for node in nodes if node.kind == ArgumentNodeKind.CLAIM]
    incoming: dict[str, list[Any]] = {}
    for edge in edges:
        incoming.setdefault(edge.to_node_id, []).append(edge)
    entries: list[MissionClaimMapEntry] = []
    for node in claim_nodes:
        support_edges = [
            edge
            for edge in incoming.get(node.node_id, [])
            if edge.relation == ArgumentRelation.SUPPORTS
        ]
        challenge_edges = [
            edge
            for edge in incoming.get(node.node_id, [])
            if edge.relation == ArgumentRelation.CHALLENGES
        ]
        test_edges = [
            edge
            for edge in incoming.get(node.node_id, [])
            if edge.relation == ArgumentRelation.TESTS
        ]
        limit_edges = [
            edge
            for edge in incoming.get(node.node_id, [])
            if edge.relation == ArgumentRelation.LIMITS
        ]
        dependency_claims = tuple(
            nodes_by_id[edge.from_node_id].statement_hash
            for edge in support_edges
            if nodes_by_id.get(edge.from_node_id)
            and nodes_by_id[edge.from_node_id].kind == ArgumentNodeKind.CLAIM
        )
        support_status = _argument_support_status(
            supports=len(support_edges),
            challenges=len(challenge_edges),
            tests=len(test_edges),
            limits=len(limit_edges),
            review_state=node.status.value,
        )
        entries.append(
            MissionClaimMapEntry(
                claim_item_id=node.node_id,
                claim_hash=node.statement_hash,
                claim_status=node.status.value,
                confidence=node.confidence,
                evidence_count=len(support_edges) + len(test_edges),
                reviewed_evidence_count=1 if node.status.value == "reviewed" else 0,
                disputed_evidence_count=1 if challenge_edges else 0,
                stale_evidence_count=0,
                support_status=support_status,
                claim_text=node.statement,
                claim_type=_claim_type(node.statement),
                direct_support_count=len(support_edges),
                counterevidence_count=len(challenge_edges),
                dependency_claims=dependency_claims,
                falsification_condition=_falsification_condition(
                    node.statement,
                    [nodes_by_id.get(edge.from_node_id) for edge in test_edges],
                    [nodes_by_id.get(edge.from_node_id) for edge in limit_edges],
                ),
                review_state=node.status.value,
            )
        )
    return entries


def _argument_support_status(
    supports: int,
    challenges: int,
    tests: int,
    limits: int,
    review_state: str,
) -> str:
    if challenges and tests:
        return "tested_with_counterevidence"
    if challenges:
        return "counterevidence_present"
    if supports and review_state == "reviewed":
        return "reviewed_support"
    if supports or tests:
        return "raw_support"
    if limits:
        return "limited"
    return "unsupported"


def _claim_type(statement: str) -> str:
    lowered = statement.lower()
    if "rti" in lowered or "recovery threshold" in lowered:
        return "empirical_subclaim"
    if "ledger" in lowered or "hash" in lowered:
        return "implementation_claim"
    if "pca" in lowered or "lineage" in lowered:
        return "architecture_claim"
    if "evidence" in lowered:
        return "evidence_governance_claim"
    return "continuity_claim"


def _falsification_condition(
    statement: str,
    tests: list[Any],
    limits: list[Any],
) -> str:
    if tests:
        test_text = " ".join(test.statement for test in tests if test)
        if test_text:
            return f"Fails if the associated test does not support the claim: {test_text}"
    lowered = statement.lower()
    if "output similarity" in lowered or "fluent output" in lowered:
        return (
            "Fails if output-only evaluation reliably certifies memory, authority, "
            "and lineage continuity across controlled disruptions."
        )
    if "ledger" in lowered:
        return "Fails if ledger mutation or event removal can occur without detection."
    if "reviewed evidence" in lowered:
        return "Fails if raw source count predicts claim reliability as well as review state."
    if limits:
        limit_text = " ".join(limit.statement for limit in limits if limit)
        if limit_text:
            return f"Not directly falsified yet; current limitation: {limit_text}"
    return "Needs a direct falsification protocol before confidence can increase."
