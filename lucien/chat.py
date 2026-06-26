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
    close_chat_session,
    derive_current_claim,
    derive_self_model,
    record_chat_turn,
    render_dashboard_html,
    start_chat_session,
    write_lucien_cockpit_html,
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
    session_id: str
    turn_id: str
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
            "session_id": self.session_id,
            "turn_id": self.turn_id,
            "dashboard_path": self.dashboard_path,
        }


class LucienChatShell:
    def __init__(
        self,
        manifest: IdentityManifest,
        ledger: ContinuityLedger,
        responder: LocalLucienResponder | None = None,
        dashboard_path: str | Path | None = None,
        cockpit_path: str | Path | None = None,
        session_id: str | None = None,
    ):
        self.manifest = manifest
        self.ledger = ledger
        self.responder = responder or LocalLucienResponder()
        self.dashboard_path = Path(dashboard_path) if dashboard_path else None
        self.cockpit_path = Path(cockpit_path) if cockpit_path else None
        self.session_id = session_id

    @classmethod
    def from_paths(
        cls,
        manifest_path: str | Path,
        ledger_path: str | Path,
        dashboard_path: str | Path | None = None,
        cockpit_path: str | Path | None = None,
    ) -> "LucienChatShell":
        manifest = IdentityManifest.from_dict(
            json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        )
        return cls(
            manifest=manifest,
            ledger=ContinuityLedger(ledger_path),
            dashboard_path=dashboard_path,
            cockpit_path=cockpit_path,
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

    def start_session(self, reason: str = "Lucien chat session") -> str:
        if self.session_id is None:
            session = start_chat_session(
                self.ledger,
                self.manifest.system_id,
                reason=reason,
            )
            self.session_id = session.session_id
        return self.session_id

    def close_session(self, reason: str = "Lucien chat session closed") -> None:
        if self.session_id is None:
            return
        close_chat_session(
            self.ledger,
            self.manifest.system_id,
            self.session_id,
            reason=reason,
        )
        self._write_dashboard()
        self._write_cockpit()

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
        session_id = self.start_session()
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
        current_claim = derive_current_claim(self.ledger, self.manifest)[0]
        turn_record = record_chat_turn(
            self.ledger,
            self.manifest.system_id,
            session_id=session_id,
            turn_index=_next_turn_index(self.ledger.events(), session_id),
            input_event_id=turn.input_event.event_hash,
            output_event_id=turn.output_envelope.audit_event.event_hash,
            growth_event_ids=_growth_event_hashes(
                self.ledger.events(),
                [record.growth_id for record in turn.growth_records],
            ),
            output_allowed=turn.output_envelope.decision.allowed,
            continuity_claim=current_claim,
        )
        dashboard_path = self._write_dashboard()
        self._write_cockpit()
        final_self_model = derive_self_model(self.ledger.events(), self.manifest.system_id)
        final_cards = memory_cards_from_self_model(final_self_model)
        return LucienChatResult(
            continuity_claim=current_claim,
            output_allowed=turn.output_envelope.decision.allowed,
            response_text=turn.output_envelope.decision.text,
            memory_card_count=len(final_cards),
            accepted_growth_count=final_self_model.accepted_growth_count,
            classified_growth=classified.to_dict() if classified else None,
            proposed_growth=proposed_growth.to_dict() if proposed_growth else None,
            accepted_growth=accepted_growth.to_dict() if accepted_growth else None,
            growth_gate=growth_gate,
            session_id=session_id,
            turn_id=turn_record.turn_id,
            dashboard_path=str(dashboard_path) if dashboard_path else None,
        )

    def _write_dashboard(self) -> Path | None:
        if self.dashboard_path is None:
            return None
        report = build_trace_report(self.ledger, self.manifest)
        self.dashboard_path.parent.mkdir(parents=True, exist_ok=True)
        self.dashboard_path.write_text(render_dashboard_html(report), encoding="utf-8")
        return self.dashboard_path

    def _write_cockpit(self) -> Path | None:
        if self.cockpit_path is None:
            return None
        report = build_trace_report(self.ledger, self.manifest)
        return write_lucien_cockpit_html(report, self.cockpit_path)


def _next_turn_index(events, session_id: str) -> int:
    return (
        len(
            [
                event
                for event in events
                if event.event_type == "lucien.chat_turn_recorded"
                and event.payload.get("session_id") == session_id
            ]
        )
        + 1
    )


def _growth_event_hashes(events, growth_ids: list[str]) -> list[str]:
    hashes = []
    wanted = set(growth_ids)
    for event in events:
        if event.event_type in {"lucien.growth_proposed", "lucien.growth_updated"}:
            if event.payload.get("growth_id") in wanted:
                hashes.append(event.event_hash)
    return hashes
