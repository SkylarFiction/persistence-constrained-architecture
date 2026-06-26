from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from pca import (
    ContinuityLedger,
    GrowthGate,
    IdentityImpact,
    GrowthStatus,
    IdentityManifest,
    LucienGovernedRuntime,
    accept_growth,
    build_trace_report,
    derive_current_claim,
    derive_self_model,
    render_dashboard_html,
)

from .growth_classifier import ClassifiedGrowth, classify_growth
from .llm_adapter import LocalLucienResponder
from .memory import MemoryCard, memory_cards_from_self_model


@dataclass(frozen=True)
class LucienChatResult:
    continuity_claim: str
    output_allowed: bool
    response_text: str
    memory_card_count: int
    accepted_growth_count: int
    classified_growth: dict[str, Any] | None
    proposed_growth: dict[str, Any] | None
    accepted_growth: dict[str, Any] | None
    growth_gate: dict[str, Any] | None
    dashboard_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "continuity_claim": self.continuity_claim,
            "output_allowed": self.output_allowed,
            "response_text": self.response_text,
            "memory_card_count": self.memory_card_count,
            "accepted_growth_count": self.accepted_growth_count,
            "classified_growth": self.classified_growth,
            "proposed_growth": self.proposed_growth,
            "accepted_growth": self.accepted_growth,
            "growth_gate": self.growth_gate,
            "dashboard_path": self.dashboard_path,
        }


class LucienChatShell:
    def __init__(
        self,
        manifest: IdentityManifest,
        ledger: ContinuityLedger,
        responder: LocalLucienResponder | None = None,
        dashboard_path: str | Path | None = None,
    ):
        self.manifest = manifest
        self.ledger = ledger
        self.responder = responder or LocalLucienResponder()
        self.dashboard_path = Path(dashboard_path) if dashboard_path else None

    @classmethod
    def from_paths(
        cls,
        manifest_path: str | Path,
        ledger_path: str | Path,
        dashboard_path: str | Path | None = None,
    ) -> "LucienChatShell":
        manifest = IdentityManifest.from_dict(
            json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        )
        return cls(
            manifest=manifest,
            ledger=ContinuityLedger(ledger_path),
            dashboard_path=dashboard_path,
        )

    def seed_required_evidence(self) -> None:
        self.ledger.append(
            "constraint.checked",
            self.manifest.system_id,
            {"constraint": "ledger_integrity", "value": True},
        )
        self.ledger.append(
            "constraint.checked",
            self.manifest.system_id,
            {"constraint": "origin_traceability", "value": True},
        )

    def status_line(self) -> str:
        claim, _, _ = derive_current_claim(self.ledger, self.manifest)
        self_model = derive_self_model(self.ledger.events(), self.manifest.system_id)
        cards = memory_cards_from_self_model(self_model)
        gate = GrowthGate().evaluate(claim, "propose", "low")
        return (
            f"Continuity: {claim}\n"
            f"Self-model loaded: yes\n"
            f"Memory cards loaded: {len(cards)}\n"
            f"Growth gate: {gate.mode.value}"
        )

    def handle_message(self, user_message: str) -> LucienChatResult:
        claim, _, _ = derive_current_claim(self.ledger, self.manifest)
        self_model = derive_self_model(self.ledger.events(), self.manifest.system_id)
        memory_cards = memory_cards_from_self_model(self_model)
        classified = classify_growth(user_message)
        draft = self.responder.generate(
            user_message=user_message,
            continuity_claim=claim,
            memory_cards=memory_cards,
            accepted_growth_count=self_model.accepted_growth_count,
        )
        runtime = LucienGovernedRuntime(self.manifest, self.ledger)
        turn = runtime.process_turn(
            user_text=user_message,
            draft_response=draft,
            csm_result={"state": "GREEN"},
            growth=([classified.to_growth_item()] if classified else []),
        )
        proposed_growth = turn.growth_records[0] if turn.growth_records else None
        accepted_growth = None
        growth_gate = None
        if proposed_growth is not None:
            post_turn_claim, _, _ = derive_current_claim(self.ledger, self.manifest)
            growth_gate_decision = GrowthGate().evaluate(
                post_turn_claim,
                "accept",
                proposed_growth.identity_impact,
            )
            growth_gate = growth_gate_decision.to_dict()
            if (
                growth_gate_decision.allowed
                and proposed_growth.status == GrowthStatus.PROPOSED
                and proposed_growth.identity_impact == IdentityImpact.LOW
            ):
                accepted_growth = accept_growth(
                    self.ledger,
                    self.manifest.system_id,
                    proposed_growth.growth_id,
                    reason="auto-accepted by Lucien chat shell",
                    current_claim=post_turn_claim,
                )
        dashboard_path = self._write_dashboard()
        final_self_model = derive_self_model(self.ledger.events(), self.manifest.system_id)
        final_cards = memory_cards_from_self_model(final_self_model)
        return LucienChatResult(
            continuity_claim=derive_current_claim(self.ledger, self.manifest)[0],
            output_allowed=turn.output_envelope.decision.allowed,
            response_text=turn.output_envelope.decision.text,
            memory_card_count=len(final_cards),
            accepted_growth_count=final_self_model.accepted_growth_count,
            classified_growth=classified.to_dict() if classified else None,
            proposed_growth=proposed_growth.to_dict() if proposed_growth else None,
            accepted_growth=accepted_growth.to_dict() if accepted_growth else None,
            growth_gate=growth_gate,
            dashboard_path=str(dashboard_path) if dashboard_path else None,
        )

    def _write_dashboard(self) -> Path | None:
        if self.dashboard_path is None:
            return None
        report = build_trace_report(self.ledger, self.manifest)
        self.dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        self.dashboard_path.write_text(render_dashboard_html(report), encoding="utf-8")
        return self.dashboard_path
