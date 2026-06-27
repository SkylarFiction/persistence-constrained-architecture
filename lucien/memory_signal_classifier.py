from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClassifiedMemorySignal:
    signal_type: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "signal_type": self.signal_type,
            "reason": self.reason,
        }


def classify_memory_signal(user_message: str) -> ClassifiedMemorySignal | None:
    lowered = user_message.lower()
    if _contains_any(
        lowered,
        (
            "that's right",
            "that is right",
            "correct",
            "yes exactly",
            "confirmed",
            "keep that memory",
        ),
    ):
        return ClassifiedMemorySignal(
            signal_type="reinforced",
            reason="user confirmed the active memory context",
        )
    if _contains_any(
        lowered,
        (
            "that's wrong",
            "that is wrong",
            "incorrect",
            "not true",
            "forget that memory",
            "that memory is wrong",
        ),
    ):
        return ClassifiedMemorySignal(
            signal_type="contradicted",
            reason="user contradicted the active memory context",
        )
    if _contains_any(
        lowered,
        (
            "that memory is outdated",
            "that is outdated",
            "no longer true",
            "stale memory",
        ),
    ):
        return ClassifiedMemorySignal(
            signal_type="stale",
            reason="user marked the active memory context as stale",
        )
    return None


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
