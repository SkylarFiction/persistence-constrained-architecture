from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .runtime_adapter import PCAIdentityRuntime, RuntimeSignalResult


class RedEventLogger(Protocol):
    def log_red_event(self, payload: dict[str, Any]) -> None:
        ...


@dataclass
class PCAAuditLoggerAdapter:
    bridge: "CSMRuntimeBridge"
    delegate: RedEventLogger | None = None
    last_red_payload: dict[str, Any] | None = None
    last_signal_result: RuntimeSignalResult | None = None

    def log_red_event(self, payload: dict[str, Any]) -> None:
        if self.delegate is not None:
            self.delegate.log_red_event(payload)
        self.last_red_payload = dict(payload)
        self.last_signal_result = self.bridge.record_hard_kill(payload)


class CSMRuntimeBridge:
    def __init__(self, runtime: PCAIdentityRuntime):
        self.runtime = runtime

    def audit_logger_adapter(
        self,
        delegate: RedEventLogger | None = None,
    ) -> PCAAuditLoggerAdapter:
        return PCAAuditLoggerAdapter(bridge=self, delegate=delegate)

    def record_monitor_result(
        self,
        result: dict[str, Any],
        reason: str = "",
    ) -> RuntimeSignalResult:
        state = str(result.get("state", "GREEN"))
        metrics = {key: value for key, value in result.items() if key != "state"}
        if not reason:
            reason = "CSM monitor step result"
        return self.runtime.record_runtime_signal(
            state,
            metrics=metrics,
            reason=reason,
        )

    def record_hard_kill(
        self,
        payload: dict[str, Any],
        error: Exception | None = None,
    ) -> RuntimeSignalResult:
        reason = str(payload.get("reason") or "CSM hard kill")
        if error is not None:
            reason = f"{reason}: {error}"
        return self.runtime.record_runtime_signal(
            "RED",
            metrics=dict(payload),
            reason=reason,
        )

    def process_monitor_step(
        self,
        monitor: Any,
        raise_on_hard_kill: bool = False,
        **kwargs: Any,
    ) -> RuntimeSignalResult:
        try:
            result = monitor.process_step(**kwargs)
        except RuntimeError as error:
            logger = getattr(monitor, "logger", None)
            last_signal_result = getattr(logger, "last_signal_result", None)
            if last_signal_result is not None:
                if raise_on_hard_kill:
                    raise
                return last_signal_result
            payload = {
                "state": getattr(monitor, "state", "RED"),
                "run_id": getattr(monitor, "run_id", ""),
                "step_id": getattr(monitor, "step_id", ""),
                "reason": str(error),
            }
            signal_result = self.record_hard_kill(payload, error=error)
            if raise_on_hard_kill:
                raise
            return signal_result
        return self.record_monitor_result(result)
