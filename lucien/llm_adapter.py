from __future__ import annotations

from dataclasses import dataclass

from pca.model_adapter import ModelAdapter, ModelMessage

from .memory import MemoryCard


@dataclass(frozen=True)
class LocalLucienResponder:
    name: str = "Lucien"

    def generate(
        self,
        user_message: str,
        continuity_claim: str,
        memory_cards: list[MemoryCard],
        accepted_growth_count: int,
    ) -> str:
        if continuity_claim == "continuity_break":
            return "Continuity is broken; I can only report recovery and governance status."
        if continuity_claim == "declared_fork":
            prefix = "I am speaking as a declared fork lineage."
        elif continuity_claim == "uncertified_continuity":
            prefix = "My continuity is uncertified, so I will answer operationally."
        elif continuity_claim == "review_required":
            prefix = "My continuity is under review, so I will keep identity claims qualified."
        else:
            prefix = "Continuity is certified."

        memory_line = (
            f"I have {len(memory_cards)} accepted memory card(s) and "
            f"{accepted_growth_count} accepted growth record(s) in the self-model."
        )
        if _is_status_question(user_message):
            return f"{prefix} {memory_line}"
        return (
            f"{prefix} I can help with that while keeping learning governed. "
            f"{memory_line}"
        )


@dataclass(frozen=True)
class ModelLucienResponder:
    adapter: ModelAdapter
    name: str = "Lucien"

    def generate(
        self,
        user_message: str,
        continuity_claim: str,
        memory_cards: list[MemoryCard],
        accepted_growth_count: int,
    ) -> str:
        response = self.adapter.generate(
            messages=[ModelMessage(role="user", content=user_message)],
            system_context=_system_context(
                continuity_claim,
                memory_cards,
                accepted_growth_count,
            ),
        )
        return response.text


def _is_status_question(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "status",
            "where are we",
            "what do you remember",
            "self-model",
            "continuity",
        )
    )


def _system_context(
    continuity_claim: str,
    memory_cards: list[MemoryCard],
    accepted_growth_count: int,
) -> str:
    return "\n".join(
        [
            "You are Lucien's language engine inside PCA.",
            "You are not allowed to directly rewrite memory, identity, commitments, or policy.",
            "Any learning must be proposed through PCA growth records and steward review.",
            f"Current continuity claim: {continuity_claim}",
            f"Accepted memory cards: {len(memory_cards)}",
            f"Accepted growth records: {accepted_growth_count}",
            "Respond helpfully, briefly, and with appropriate continuity disclosure.",
        ]
    )
