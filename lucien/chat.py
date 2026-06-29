from __future__ import annotations

from dataclasses import dataclass
import hashlib
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
    build_governed_context,
    build_trace_report,
    close_chat_session,
    derive_current_claim,
    derive_self_model,
    record_chat_turn,
    record_growth_conflict,
    record_memory_signal,
    render_dashboard_html,
    start_chat_session,
    write_lucien_cockpit_html,
)

from .conflict_detector import detect_growth_conflict
from .growth_classifier import ClassifiedGrowth, classify_growth
from .llm_adapter import LocalLucienResponder
from .memory import MemoryCard, memory_cards_from_self_model
from .memory_signal_classifier import classify_memory_signal
from pca.model_adapter import ModelAdapterError
from pca.model_adapter import estimate_model_usage, normalize_model_mode


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    conflict: dict[str, Any] | None
    memory_signal: dict[str, Any] | None
    growth_gate: dict[str, Any] | None
    context_summary: dict[str, Any]
    model_usage: dict[str, Any]
    model_mode: str
    openai_requested: bool
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
            "conflict": self.conflict,
            "memory_signal": self.memory_signal,
            "growth_gate": self.growth_gate,
            "context_summary": self.context_summary,
            "model_usage": self.model_usage,
            "model_mode": self.model_mode,
            "openai_requested": self.openai_requested,
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

    def handle_message(
        self,
        user_message: str,
        model_mode: str | None = None,
        use_openai: bool = False,
        responder: LocalLucienResponder | None = None,
    ) -> LucienChatResult:
        session_id = self.start_session()
        active_model_mode = normalize_model_mode(model_mode)
        active_responder = responder or self.responder
        claim, _, _ = derive_current_claim(self.ledger, self.manifest)
        self_model = derive_self_model(self.ledger.events(), self.manifest.system_id)
        memory_cards = memory_cards_from_self_model(self_model)
        governed_context = build_governed_context(self.ledger, self.manifest)
        classified = classify_growth(user_message)
        prompt_context = governed_context.render_prompt_context()
        model_error = None
        try:
            draft = active_responder.generate(
                user_message=user_message,
                continuity_claim=claim,
                memory_cards=memory_cards,
                accepted_growth_count=self_model.accepted_growth_count,
                governed_context=prompt_context,
            )
        except ModelAdapterError as error:
            model_error = error
            draft = (
                "I could not reach the configured language model. "
                "PCA governance is still running, and the issue was recorded."
            )
            self.ledger.append(
                "chat.model_response_error",
                self.manifest.system_id,
                {
                    "provider": error.provider,
                    "model": error.model,
                    "error_type": error.error_type,
                    "error_length": len(str(error)),
                    "surface": "lucien_chat_shell",
                    "context_sha256": _text_hash(prompt_context),
                    "context_length": len(prompt_context),
                },
            )
        model_response = getattr(active_responder, "last_model_response", None)
        raw_usage = (
            (model_response.raw or {}).get("usage", {})
            if model_response is not None
            else {}
        )
        model_name = (
            model_response.model
            if model_response is not None
            else ("unavailable" if model_error else "local")
        )
        usage_estimate = estimate_model_usage(
            context_length=len(prompt_context),
            response_length=len(draft),
            raw_usage=raw_usage,
            model=model_name,
        )
        provider_name = (
            model_response.provider
            if model_response is not None
            else ("error" if model_error else "local")
        )
        if provider_name != "openai":
            usage_estimate = {
                **usage_estimate,
                "estimated_cost_usd": 0.0,
                "source": "local_no_cost",
            }
        self.ledger.append(
            "chat.model_response_generated",
            self.manifest.system_id,
            {
                "response_length": len(draft),
                "surface": "lucien_chat_shell",
                "continuity_claim": claim,
                "model_mode": active_model_mode,
                "openai_requested": bool(use_openai),
                "provider": provider_name,
                "model": model_name,
                "context_sha256": _text_hash(prompt_context),
                "context_length": len(prompt_context),
                "estimated_total_tokens": usage_estimate["total_tokens"],
                "estimated_cost_usd": usage_estimate["estimated_cost_usd"],
                "usage_source": usage_estimate["source"],
            },
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
        conflict = None
        memory_signal = None
        growth_gate = None
        if proposed_growth is not None:
            detected_conflict = detect_growth_conflict(classified, self_model)
            if detected_conflict is not None:
                conflict_record = record_growth_conflict(
                    self.ledger,
                    self.manifest.system_id,
                    proposed_growth.growth_id,
                    detected_conflict.conflicting_growth_ids,
                    detected_conflict.conflict_type,
                    detected_conflict.severity,
                    detected_conflict.reason,
                )
                conflict = conflict_record.to_dict()
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
                and conflict is None
            ):
                accepted_growth = accept_growth(
                    self.ledger,
                    self.manifest.system_id,
                    proposed_growth.growth_id,
                    reason="auto-accepted by Lucien chat shell",
                    current_claim=post_turn_claim,
                )
        classified_signal = classify_memory_signal(user_message)
        signal_target = _latest_memory_card(memory_cards)
        if classified_signal is not None and signal_target is not None:
            signal_record = record_memory_signal(
                self.ledger,
                self.manifest.system_id,
                signal_target.memory_id,
                classified_signal.signal_type,
                reason=classified_signal.reason,
                evidence_refs=[turn.input_event.event_hash],
            )
            memory_signal = signal_record.to_dict()
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
            conflict=conflict,
            memory_signal=memory_signal,
            growth_gate=growth_gate,
            context_summary=governed_context.summary(),
            model_usage=usage_estimate,
            model_mode=active_model_mode,
            openai_requested=bool(use_openai),
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


def _latest_memory_card(cards: list[MemoryCard]) -> MemoryCard | None:
    if not cards:
        return None
    return sorted(cards, key=lambda card: card.last_confirmed)[-1]
