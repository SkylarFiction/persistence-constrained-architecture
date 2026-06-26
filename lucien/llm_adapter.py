from __future__ import annotations

from dataclasses import dataclass

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
