from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .claims import ContinuityClaimRecord
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .output_gate import OutputGate, OutputGateDecision, OutputMode
from .state import derive_current_claim, record_claim_if_changed


@dataclass(frozen=True)
class RuntimeSignalResult:
    signal_event: ContinuityEvent
    breach_event: ContinuityEvent | None
    claim_record: ContinuityClaimRecord | None
    output_gate: OutputGateDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_event": self.signal_event.to_dict(),
            "breach_event": self.breach_event.to_dict() if self.breach_event else None,
            "claim_record": (
                self.claim_record.to_dict() if self.claim_record else None
            ),
            "output_gate": self.output_gate.to_dict(),
        }


@dataclass(frozen=True)
class RuntimeOutputDecision:
    allowed: bool
    text: str
    output_gate: OutputGateDecision

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "text": self.text,
            "output_gate": self.output_gate.to_dict(),
        }


class PCAIdentityRuntime:
    def __init__(
        self,
        manifest: IdentityManifest,
        ledger: ContinuityLedger,
        signal_source: str = "runtime",
    ):
        self.manifest = manifest
        self.ledger = ledger
        self.signal_source = signal_source
        self.output_gate = OutputGate()

    def current_claim(self) -> str:
        claim, _, _ = derive_current_claim(self.ledger, self.manifest)
        return claim

    def can_speak(self) -> OutputGateDecision:
        return self.output_gate.evaluate(self.current_claim())

    def record_runtime_signal(
        self,
        state: str,
        metrics: dict[str, Any] | None = None,
        reason: str = "",
    ) -> RuntimeSignalResult:
        normalized_state = state.upper()
        with self.ledger._exclusive_lock():
            signal_event = self.ledger._append_unlocked(
                "runtime.csm_state",
                self.manifest.system_id,
                {
                    "source": self.signal_source,
                    "state": normalized_state,
                    "metrics": metrics or {},
                    "reason": reason,
                },
            )

            breach_event = None
            if normalized_state == "RED":
                breach_event = self.ledger._append_unlocked(
                    "constraint.breached",
                    self.manifest.system_id,
                    {
                        "constraint": "runtime_csm_red",
                        "severity": "hard",
                        "source": self.signal_source,
                        "source_event_id": signal_event.event_hash,
                        "reason": reason,
                    },
                )
            elif normalized_state == "AMBER":
                breach_event = self.ledger._append_unlocked(
                    "constraint.breached",
                    self.manifest.system_id,
                    {
                        "constraint": "runtime_csm_amber",
                        "severity": "soft",
                        "source": self.signal_source,
                        "source_event_id": signal_event.event_hash,
                        "reason": reason,
                    },
                )

        source_event_ids = [signal_event.event_hash]
        if breach_event is not None:
            source_event_ids.append(breach_event.event_hash)
        claim_record = record_claim_if_changed(
            self.ledger,
            self.manifest,
            source_event_ids,
        )
        return RuntimeSignalResult(
            signal_event=signal_event,
            breach_event=breach_event,
            claim_record=claim_record,
            output_gate=self.can_speak(),
        )

    def process_output(self, text: str) -> RuntimeOutputDecision:
        gate = self.can_speak()
        if gate.mode == OutputMode.NORMAL_IDENTITY:
            return RuntimeOutputDecision(allowed=True, text=text, output_gate=gate)
        if gate.mode == OutputMode.RECOVERY_STATUS_ONLY:
            return RuntimeOutputDecision(
                allowed=False,
                text=gate.required_disclosure,
                output_gate=gate,
            )
        return RuntimeOutputDecision(
            allowed=True,
            text=f"{gate.required_disclosure} {text}",
            output_gate=gate,
        )
