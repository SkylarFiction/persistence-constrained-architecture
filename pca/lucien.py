from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from .csm_bridge import CSMRuntimeBridge
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .output_wrapper import OutputEnvelope, PCAOutputWrapper
from .runtime_adapter import PCAIdentityRuntime, RuntimeSignalResult


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LucienTurnResult:
    input_event: ContinuityEvent
    memory_event: ContinuityEvent | None
    tool_event: ContinuityEvent | None
    signal_result: RuntimeSignalResult
    output_envelope: OutputEnvelope

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_event": self.input_event.to_dict(),
            "memory_event": self.memory_event.to_dict() if self.memory_event else None,
            "tool_event": self.tool_event.to_dict() if self.tool_event else None,
            "signal_result": self.signal_result.to_dict(),
            "output_envelope": self.output_envelope.to_dict(),
        }


class LucienGovernedRuntime:
    def __init__(
        self,
        manifest: IdentityManifest,
        ledger: ContinuityLedger,
        signal_source: str = "lucien_csm",
    ):
        self.manifest = manifest
        self.ledger = ledger
        self.identity_runtime = PCAIdentityRuntime(
            manifest=manifest,
            ledger=ledger,
            signal_source=signal_source,
        )
        self.csm_bridge = CSMRuntimeBridge(self.identity_runtime)
        self.output_wrapper = PCAOutputWrapper(self.identity_runtime)

    def record_input(
        self,
        text: str,
        channel: str = "user",
        metadata: dict[str, Any] | None = None,
    ) -> ContinuityEvent:
        return self.ledger.append(
            "lucien.input",
            self.manifest.system_id,
            {
                "channel": channel,
                "input_sha256": _text_hash(text),
                "input_length": len(text),
                "metadata": metadata or {},
            },
        )

    def record_memory_digest(
        self,
        digest: str,
        commitments: list[str] | None = None,
        source_event_ids: list[str] | None = None,
    ) -> ContinuityEvent:
        return self.ledger.append(
            "lucien.memory_digest",
            self.manifest.system_id,
            {
                "digest_sha256": _text_hash(digest),
                "digest_length": len(digest),
                "commitment_count": len(commitments or []),
                "commitment_hashes": [
                    _text_hash(commitment) for commitment in commitments or []
                ],
                "source_event_ids": source_event_ids or [],
            },
        )

    def record_tool_use(
        self,
        tool_name: str,
        purpose: str,
        result_summary: str = "",
        source_event_ids: list[str] | None = None,
    ) -> ContinuityEvent:
        return self.ledger.append(
            "lucien.tool_use",
            self.manifest.system_id,
            {
                "tool_name": tool_name,
                "purpose": purpose,
                "result_summary_sha256": _text_hash(result_summary),
                "result_summary_length": len(result_summary),
                "source_event_ids": source_event_ids or [],
            },
        )

    def process_turn(
        self,
        user_text: str,
        draft_response: str,
        csm_result: dict[str, Any] | None = None,
        memory_digest: str = "",
        commitments: list[str] | None = None,
        tool_name: str | None = None,
        tool_purpose: str = "",
        tool_result_summary: str = "",
    ) -> LucienTurnResult:
        input_event = self.record_input(user_text)
        source_event_ids = [input_event.event_hash]
        memory_event = None
        if memory_digest:
            memory_event = self.record_memory_digest(
                memory_digest,
                commitments=commitments,
                source_event_ids=source_event_ids,
            )
            source_event_ids.append(memory_event.event_hash)
        tool_event = None
        if tool_name:
            tool_event = self.record_tool_use(
                tool_name,
                tool_purpose,
                tool_result_summary,
                source_event_ids=source_event_ids,
            )
            source_event_ids.append(tool_event.event_hash)
        signal_result = self.csm_bridge.record_monitor_result(
            csm_result or {"state": "GREEN"},
            reason="Lucien governed turn CSM result",
        )
        output_envelope = self.output_wrapper.emit(
            draft_response,
            channel="lucien",
            metadata={
                "runtime": "lucien_governed",
                "input_event_id": input_event.event_hash,
                "memory_event_id": memory_event.event_hash if memory_event else "",
                "tool_event_id": tool_event.event_hash if tool_event else "",
                "signal_event_id": signal_result.signal_event.event_hash,
            },
        )
        return LucienTurnResult(
            input_event=input_event,
            memory_event=memory_event,
            tool_event=tool_event,
            signal_result=signal_result,
            output_envelope=output_envelope,
        )
