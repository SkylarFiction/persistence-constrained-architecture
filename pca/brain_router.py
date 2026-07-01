from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from .model_adapter import (
    MODEL_MODE_AUTO,
    MODEL_MODE_ECHO,
    MODEL_MODE_LOCAL_FIRST,
    MODEL_MODE_LOCAL_OLLAMA,
    MODEL_MODE_OPENAI,
    MODEL_MODE_SERIOUS_ONLY,
    normalize_model_mode,
)


@dataclass(frozen=True)
class BrainRouteDecision:
    route_id: str
    requested_model_mode: str
    selected_model_mode: str
    task_type: str
    reason: str
    openai_allowed: bool
    openai_recommended: bool
    estimated_cost_class: str
    fallback_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "requested_model_mode": self.requested_model_mode,
            "selected_model_mode": self.selected_model_mode,
            "task_type": self.task_type,
            "reason": self.reason,
            "openai_allowed": self.openai_allowed,
            "openai_recommended": self.openai_recommended,
            "estimated_cost_class": self.estimated_cost_class,
            "fallback_allowed": self.fallback_allowed,
        }


def select_brain_route(
    user_message: str,
    requested_model_mode: str | None = None,
    use_openai: bool = False,
    model_diagnostic: dict[str, Any] | None = None,
) -> BrainRouteDecision:
    requested = normalize_model_mode(requested_model_mode)
    task_type = classify_brain_task(user_message)
    local_ready = bool((model_diagnostic or {}).get("local_model_configured", True))

    if requested == MODEL_MODE_ECHO:
        return _decision(
            requested,
            MODEL_MODE_ECHO,
            task_type,
            "User selected diagnostic Echo mode.",
            use_openai,
            False,
            "zero",
            False,
        )

    if requested == MODEL_MODE_OPENAI:
        return _decision(
            requested,
            MODEL_MODE_OPENAI,
            task_type,
            "User selected OpenAI mode explicitly.",
            True,
            True,
            "paid",
            False,
        )

    if requested == MODEL_MODE_LOCAL_OLLAMA:
        return _decision(
            requested,
            MODEL_MODE_LOCAL_OLLAMA,
            task_type,
            "User selected local Ollama mode.",
            False,
            False,
            "zero",
            False,
        )

    if requested == MODEL_MODE_LOCAL_FIRST:
        return _decision(
            requested,
            MODEL_MODE_LOCAL_FIRST,
            task_type,
            "User selected local-first mode.",
            bool(use_openai),
            task_type == "hard_reasoning",
            "zero_or_paid_fallback" if use_openai else "zero",
            True,
        )

    if requested == MODEL_MODE_SERIOUS_ONLY:
        selected = MODEL_MODE_OPENAI if use_openai else MODEL_MODE_ECHO
        return _decision(
            requested,
            selected,
            task_type,
            "Spend-safe OpenAI mode only uses OpenAI when explicitly checked.",
            bool(use_openai),
            bool(use_openai),
            "paid" if use_openai else "zero",
            False,
        )

    if task_type == "simple_status":
        return _decision(
            requested,
            MODEL_MODE_ECHO,
            task_type,
            "Simple status or governance query can be answered by the local diagnostic brain.",
            False,
            False,
            "zero",
            False,
        )

    if task_type == "hard_reasoning" and use_openai:
        return _decision(
            requested,
            MODEL_MODE_OPENAI,
            task_type,
            "Hard reasoning request and OpenAI was explicitly allowed for this message.",
            True,
            True,
            "paid",
            False,
        )

    if task_type == "hard_reasoning":
        reason = (
            "Hard reasoning request; OpenAI is recommended but not allowed, so Lucien "
            "will use the local-first path."
        )
        selected = MODEL_MODE_LOCAL_FIRST if local_ready else MODEL_MODE_ECHO
        return _decision(
            requested,
            selected,
            task_type,
            reason,
            False,
            True,
            "zero",
            selected == MODEL_MODE_LOCAL_FIRST,
        )

    selected = MODEL_MODE_LOCAL_FIRST if local_ready else MODEL_MODE_ECHO
    return _decision(
        requested,
        selected,
        task_type,
        "Normal work should use the local model first to preserve privacy and avoid API cost.",
        False,
        False,
        "zero",
        selected == MODEL_MODE_LOCAL_FIRST,
    )


def classify_brain_task(user_message: str) -> str:
    lowered = user_message.lower()
    simple_markers = (
        "status",
        "where are we",
        "what can you do",
        "what are you",
        "summarize",
        "show me",
        "list",
        "hello",
        "hi",
    )
    hard_markers = (
        "solve",
        "strategy",
        "architect",
        "design",
        "research",
        "analyze",
        "debug",
        "prove",
        "derive",
        "world problem",
        "complex",
        "plan",
        "roadmap",
    )
    if any(marker in lowered for marker in hard_markers):
        return "hard_reasoning"
    if len(user_message.strip()) < 90 and any(marker in lowered for marker in simple_markers):
        return "simple_status"
    return "normal_conversation"


def _decision(
    requested: str,
    selected: str,
    task_type: str,
    reason: str,
    openai_allowed: bool,
    openai_recommended: bool,
    estimated_cost_class: str,
    fallback_allowed: bool,
) -> BrainRouteDecision:
    return BrainRouteDecision(
        route_id=f"brain_route_{uuid4()}",
        requested_model_mode=requested,
        selected_model_mode=selected,
        task_type=task_type,
        reason=reason,
        openai_allowed=openai_allowed,
        openai_recommended=openai_recommended,
        estimated_cost_class=estimated_cost_class,
        fallback_allowed=fallback_allowed,
    )
