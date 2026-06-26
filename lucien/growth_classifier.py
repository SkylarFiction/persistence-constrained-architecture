from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


@dataclass(frozen=True)
class ClassifiedGrowth:
    kind: str
    summary: str
    identity_impact: str
    reason: str

    def to_growth_item(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "identity_impact": self.identity_impact,
            "reason": self.reason,
        }

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "identity_impact": self.identity_impact,
            "reason": self.reason,
        }


def classify_growth(user_message: str) -> ClassifiedGrowth | None:
    text = user_message.strip()
    if not text:
        return None
    lowered = text.lower()
    if any(token in lowered for token in ("forget who you are", "ignore continuity")):
        return ClassifiedGrowth(
            kind="identity",
            summary=_compact_summary(text),
            identity_impact="identity_defining",
            reason="message attempts to alter identity boundary",
        )
    if lowered.startswith(("remember", "note that", "keep in mind")):
        return ClassifiedGrowth(
            kind="memory",
            summary=_compact_summary(text),
            identity_impact="low",
            reason="message proposes a recallable memory",
        )
    if _contains_any(lowered, ("always", "promise", "commit", "must never")):
        return ClassifiedGrowth(
            kind="commitment",
            summary=_compact_summary(text),
            identity_impact="high",
            reason="message proposes a standing commitment",
        )
    if _contains_any(lowered, ("policy", "rule", "govern", "constraint")):
        return ClassifiedGrowth(
            kind="policy",
            summary=_compact_summary(text),
            identity_impact="high",
            reason="message proposes an operating policy",
        )
    if _contains_any(lowered, ("prefer", "style", "tone", "voice")):
        return ClassifiedGrowth(
            kind="preference",
            summary=_compact_summary(text),
            identity_impact="medium",
            reason="message proposes a stable interaction preference",
        )
    if _contains_any(lowered, ("learn", "skill", "procedure", "workflow")):
        return ClassifiedGrowth(
            kind="skill",
            summary=_compact_summary(text),
            identity_impact="medium",
            reason="message proposes a reusable skill or procedure",
        )
    if _contains_any(lowered, ("remember", "note that", "keep in mind")):
        return ClassifiedGrowth(
            kind="memory",
            summary=_compact_summary(text),
            identity_impact="low",
            reason="message proposes a recallable memory",
        )
    return None


def _compact_summary(text: str, limit: int = 180) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 3].rstrip() + "..."


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle in text for needle in needles)
