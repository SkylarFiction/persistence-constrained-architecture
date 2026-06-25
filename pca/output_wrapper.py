from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from .ledger import ContinuityEvent
from .runtime_adapter import PCAIdentityRuntime, RuntimeOutputDecision


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class OutputEnvelope:
    decision: RuntimeOutputDecision
    audit_event: ContinuityEvent

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_dict(),
            "audit_event": self.audit_event.to_dict(),
        }


class PCAOutputWrapper:
    def __init__(self, runtime: PCAIdentityRuntime):
        self.runtime = runtime

    def emit(
        self,
        text: str,
        channel: str = "assistant",
        metadata: dict[str, Any] | None = None,
    ) -> OutputEnvelope:
        decision = self.runtime.process_output(text)
        audit_event = self.runtime.ledger.append(
            "runtime.output_gate",
            self.runtime.manifest.system_id,
            {
                "channel": channel,
                "claim": decision.output_gate.claim,
                "mode": decision.output_gate.mode.value,
                "allowed": decision.allowed,
                "must_disclose": decision.output_gate.must_disclose,
                "prohibited_claims": decision.output_gate.prohibited_claims,
                "input_sha256": _text_hash(text),
                "output_sha256": _text_hash(decision.text),
                "input_length": len(text),
                "output_length": len(decision.text),
                "metadata": metadata or {},
            },
        )
        return OutputEnvelope(decision=decision, audit_event=audit_event)
