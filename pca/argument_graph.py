from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
import hashlib
import uuid

from .evidence_locker import EvidenceReviewStatus
from .falsification_lab import falsification_lab_verdict
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .missions import require_mission


class ArgumentNodeKind(str, Enum):
    CLAIM = "claim"
    DEFINITION = "definition"
    PREMISE = "premise"
    EVIDENCE = "evidence"
    COUNTEREVIDENCE = "counterevidence"
    IMPLEMENTATION_FACT = "implementation_fact"
    INFERENCE = "inference"
    LIMITATION = "limitation"
    TEST = "test"
    VERDICT = "verdict"


class ArgumentRelation(str, Enum):
    SUPPORTS = "supports"
    CHALLENGES = "challenges"
    RESPONDS_TO = "responds_to"
    TESTS = "tests"
    YIELDS = "yields"
    LIMITS = "limits"


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ArgumentNodeRecord:
    node_id: str
    identity_id: str
    mission_id: str
    kind: ArgumentNodeKind
    statement: str
    statement_hash: str
    confidence: str
    status: EvidenceReviewStatus
    created_at: str
    reason: str

    @classmethod
    def create(
        cls,
        identity_id: str,
        mission_id: str,
        kind: str | ArgumentNodeKind,
        statement: str,
        confidence: str = "unknown",
        status: str | EvidenceReviewStatus = EvidenceReviewStatus.RAW,
        reason: str = "",
    ) -> "ArgumentNodeRecord":
        kind_value = kind.value if isinstance(kind, ArgumentNodeKind) else str(kind)
        status_value = (
            status.value if isinstance(status, EvidenceReviewStatus) else str(status)
        )
        return cls(
            node_id=f"argnode_{uuid.uuid4()}",
            identity_id=identity_id,
            mission_id=mission_id,
            kind=ArgumentNodeKind(kind_value),
            statement=statement,
            statement_hash=_text_hash(statement),
            confidence=confidence,
            status=EvidenceReviewStatus(status_value),
            created_at=datetime.now(timezone.utc).isoformat(),
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArgumentNodeRecord":
        return cls(
            node_id=str(data["node_id"]),
            identity_id=str(data["identity_id"]),
            mission_id=str(data["mission_id"]),
            kind=ArgumentNodeKind(str(data["kind"])),
            statement=str(data["statement"]),
            statement_hash=str(data["statement_hash"]),
            confidence=str(data.get("confidence", "unknown")),
            status=EvidenceReviewStatus(str(data.get("status", "raw"))),
            created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "identity_id": self.identity_id,
            "mission_id": self.mission_id,
            "kind": self.kind.value,
            "statement": self.statement,
            "statement_hash": self.statement_hash,
            "confidence": self.confidence,
            "status": self.status.value,
            "created_at": self.created_at,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class ArgumentEdgeRecord:
    edge_id: str
    identity_id: str
    mission_id: str
    from_node_id: str
    to_node_id: str
    relation: ArgumentRelation
    created_at: str
    reason: str

    @classmethod
    def create(
        cls,
        identity_id: str,
        mission_id: str,
        from_node_id: str,
        to_node_id: str,
        relation: str | ArgumentRelation,
        reason: str = "",
    ) -> "ArgumentEdgeRecord":
        relation_value = (
            relation.value if isinstance(relation, ArgumentRelation) else str(relation)
        )
        return cls(
            edge_id=f"argedge_{uuid.uuid4()}",
            identity_id=identity_id,
            mission_id=mission_id,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            relation=ArgumentRelation(relation_value),
            created_at=datetime.now(timezone.utc).isoformat(),
            reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArgumentEdgeRecord":
        return cls(
            edge_id=str(data["edge_id"]),
            identity_id=str(data["identity_id"]),
            mission_id=str(data["mission_id"]),
            from_node_id=str(data["from_node_id"]),
            to_node_id=str(data["to_node_id"]),
            relation=ArgumentRelation(str(data["relation"])),
            created_at=str(data["created_at"]),
            reason=str(data.get("reason", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "identity_id": self.identity_id,
            "mission_id": self.mission_id,
            "from_node_id": self.from_node_id,
            "to_node_id": self.to_node_id,
            "relation": self.relation.value,
            "created_at": self.created_at,
            "reason": self.reason,
        }


def add_argument_node(
    ledger: ContinuityLedger,
    identity_id: str,
    mission_id: str,
    kind: str | ArgumentNodeKind,
    statement: str,
    confidence: str = "unknown",
    status: str | EvidenceReviewStatus = EvidenceReviewStatus.RAW,
    reason: str = "",
) -> ArgumentNodeRecord:
    record = ArgumentNodeRecord.create(
        identity_id, mission_id, kind, statement, confidence, status, reason
    )
    ledger.append("argument_node.added", identity_id, record.to_dict())
    return record


def add_argument_edge(
    ledger: ContinuityLedger,
    identity_id: str,
    mission_id: str,
    from_node_id: str,
    to_node_id: str,
    relation: str | ArgumentRelation,
    reason: str = "",
) -> ArgumentEdgeRecord:
    record = ArgumentEdgeRecord.create(
        identity_id, mission_id, from_node_id, to_node_id, relation, reason
    )
    ledger.append("argument_edge.added", identity_id, record.to_dict())
    return record


def argument_nodes_for_mission(
    events: list[ContinuityEvent],
    mission_id: str,
) -> list[ArgumentNodeRecord]:
    return [
        ArgumentNodeRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "argument_node.added"
        and event.payload.get("mission_id") == mission_id
    ]


def argument_edges_for_mission(
    events: list[ContinuityEvent],
    mission_id: str,
) -> list[ArgumentEdgeRecord]:
    return [
        ArgumentEdgeRecord.from_dict(event.payload)
        for event in events
        if event.event_type == "argument_edge.added"
        and event.payload.get("mission_id") == mission_id
    ]


def mission_argument_graph(ledger: ContinuityLedger, mission_id: str) -> dict[str, Any]:
    events = ledger.events()
    nodes = argument_nodes_for_mission(events, mission_id)
    edges = argument_edges_for_mission(events, mission_id)
    return {
        "mission_id": mission_id,
        "node_count": len(nodes),
        "edge_count": len(edges),
        "nodes": [node.to_dict() for node in nodes],
        "edges": [edge.to_dict() for edge in edges],
    }


def seed_continuity_argument_graph(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    mission_id: str,
    project_root: str | Path = ".",
    reason: str = "",
) -> dict[str, Any]:
    """Seed one real, fully-grounded argument graph for the paper's central claim.

    Idempotent: re-running with the same statements reuses existing nodes/edges
    (matched by statement hash / endpoint+relation) instead of duplicating them.
    """
    require_mission(ledger.events(), mission_id)
    reason = reason or "seeded continuity argument graph"
    workspace_root = Path(project_root).resolve().parent

    existing_nodes = {
        node.statement_hash: node
        for node in argument_nodes_for_mission(ledger.events(), mission_id)
    }
    existing_edges = {
        (edge.from_node_id, edge.to_node_id, edge.relation.value)
        for edge in argument_edges_for_mission(ledger.events(), mission_id)
    }
    created_nodes: list[str] = []
    created_edges: list[str] = []

    def node(
        kind: ArgumentNodeKind, statement: str, confidence: str = "unknown"
    ) -> ArgumentNodeRecord:
        statement_hash = _text_hash(statement)
        if statement_hash in existing_nodes:
            return existing_nodes[statement_hash]
        record = add_argument_node(
            ledger,
            manifest.system_id,
            mission_id,
            kind,
            statement,
            confidence=confidence,
            reason=reason,
        )
        existing_nodes[statement_hash] = record
        created_nodes.append(record.node_id)
        return record

    def edge(
        from_record: ArgumentNodeRecord,
        to_record: ArgumentNodeRecord,
        relation: ArgumentRelation,
    ) -> None:
        key = (from_record.node_id, to_record.node_id, relation.value)
        if key in existing_edges:
            return
        record = add_argument_edge(
            ledger,
            manifest.system_id,
            mission_id,
            from_record.node_id,
            to_record.node_id,
            relation,
            reason=reason,
        )
        existing_edges.add(key)
        created_edges.append(record.edge_id)

    claim = node(
        ArgumentNodeKind.CLAIM,
        "Fluent output is insufficient evidence of identity continuity.",
        confidence="medium",
    )
    premise = node(
        ArgumentNodeKind.PREMISE,
        "A model may preserve style while its memory, lineage, or authorization state changes.",
    )
    implementation_fact = node(
        ArgumentNodeKind.IMPLEMENTATION_FACT,
        "PCA's identity manifest fixes invariants, constraints, and allowed transforms, and its "
        "hash-chained continuity ledger records every event with a hash of the previous one, so "
        "continuity claims can be checked against a concrete artifact rather than taken on faith.",
    )
    counterevidence = node(
        ArgumentNodeKind.COUNTEREVIDENCE,
        "Behavioral continuity may be sufficient for some operational definitions of identity.",
    )
    inference = node(
        ArgumentNodeKind.INFERENCE,
        "This paper concerns governed lineage continuity, not mere behavioral equivalence, so "
        "behavioral sufficiency does not resolve the claim -- a system can be behaviorally "
        "continuous and still fail lineage continuity.",
    )
    test = node(
        ArgumentNodeKind.TEST,
        "coherence-falsification-lab/claims/claim_001_rti_vs_variance.md: a predeclared, "
        "adversarial test of whether Recovery Threshold Index (RTI) gives earlier or more "
        "reliable warning of an approaching collapse than raw variance, on a locked synthetic "
        "saddle-node protocol. This tests a narrower sub-claim (recovery-time detection), not "
        "the full continuity claim above, directly.",
    )
    verdict_data = falsification_lab_verdict(workspace_root)
    if verdict_data:
        reason_text = "; ".join(verdict_data["reasons"]) if verdict_data["reasons"] else (
            "no reasons recorded"
        )
        verdict_statement = (
            f"{verdict_data['verdict']} on the primary median-lead-time claim. {reason_text}."
        )
    else:
        verdict_statement = (
            "No verdict file found; coherence-falsification-lab is not present in this "
            "workspace."
        )
    verdict = node(ArgumentNodeKind.VERDICT, verdict_statement)
    limitation = node(
        ArgumentNodeKind.LIMITATION,
        "No direct test yet exists for the full continuity claim above; the falsification-lab "
        "result only covers the narrower recovery-detection sub-claim, not lineage, "
        "authorization, or memory continuity directly.",
    )

    edge(premise, claim, ArgumentRelation.SUPPORTS)
    edge(implementation_fact, claim, ArgumentRelation.SUPPORTS)
    edge(counterevidence, claim, ArgumentRelation.CHALLENGES)
    edge(inference, counterevidence, ArgumentRelation.RESPONDS_TO)
    edge(test, claim, ArgumentRelation.TESTS)
    edge(verdict, test, ArgumentRelation.YIELDS)
    edge(limitation, claim, ArgumentRelation.LIMITS)

    record = {
        "mission_id": mission_id,
        "node_count": len(existing_nodes),
        "edge_count": len(existing_edges),
        "created_node_count": len(created_nodes),
        "created_edge_count": len(created_edges),
        "reason": reason,
    }
    ledger.append("argument_graph.seeded", manifest.system_id, record)
    return record


def render_argument_graph_text(graph: dict[str, Any]) -> str:
    nodes_by_id = {node["node_id"]: node for node in graph.get("nodes", [])}
    lines = [
        "Continuity Argument Graph",
        f"mission: {graph.get('mission_id')}",
        f"nodes: {graph.get('node_count', 0)}",
        f"edges: {graph.get('edge_count', 0)}",
        "nodes:",
    ]
    for node in graph.get("nodes", []):
        lines.append(f"- [{node['kind']}] {node['node_id']}: {node['statement']}")
    lines.append("edges:")
    for edge in graph.get("edges", []):
        from_kind = nodes_by_id.get(edge["from_node_id"], {}).get("kind", "?")
        to_kind = nodes_by_id.get(edge["to_node_id"], {}).get("kind", "?")
        lines.append(
            f"- {from_kind}({edge['from_node_id']}) --{edge['relation']}--> "
            f"{to_kind}({edge['to_node_id']})"
        )
    return "\n".join(lines)
