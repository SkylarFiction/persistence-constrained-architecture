from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re


STOPWORDS = {
    "about",
    "above",
    "against",
    "also",
    "and",
    "are",
    "because",
    "been",
    "being",
    "can",
    "claim",
    "claims",
    "continuity",
    "does",
    "from",
    "have",
    "into",
    "not",
    "ordinary",
    "preserved",
    "raw",
    "should",
    "system",
    "than",
    "that",
    "the",
    "their",
    "this",
    "through",
    "under",
    "when",
    "where",
    "which",
    "with",
    "without",
}

CLAIM_KEYWORDS = {
    "empirical_subclaim": {
        "recovery",
        "threshold",
        "index",
        "rti",
        "variance",
        "collapse",
        "warning",
    },
    "implementation_claim": {
        "ledger",
        "hash",
        "event",
        "manifest",
        "invariant",
        "constraint",
        "lineage",
        "pca",
        "tamper",
    },
    "architecture_claim": {
        "pca",
        "lineage",
        "fork",
        "identity",
        "transform",
        "ledger",
    },
    "evidence_governance_claim": {
        "evidence",
        "review",
        "reviewed",
        "source",
        "confidence",
        "claim",
    },
    "continuity_claim": {
        "output",
        "style",
        "memory",
        "authority",
        "state",
        "identity",
        "lineage",
        "behavior",
    },
}

CHALLENGE_TERMS = {
    "counter",
    "fail",
    "failed",
    "failure",
    "false",
    "falsification",
    "insufficient",
    "not support",
    "reject",
    "contradict",
    "weak",
}


@dataclass(frozen=True)
class ClaimSourceLink:
    claim_id: str
    claim_text: str
    note_id: str
    source_path: str
    locator: str
    relation: str
    score: float
    matched_terms: tuple[str, ...]
    review_status: str
    note_quality: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "claim_text": self.claim_text,
            "note_id": self.note_id,
            "source_path": self.source_path,
            "locator": self.locator,
            "relation": self.relation,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "review_status": self.review_status,
            "note_quality": self.note_quality,
            "summary": self.summary,
        }


def claim_source_links(
    claim_entries: list[dict[str, Any]],
    source_notes: list[dict[str, Any]],
    *,
    max_links_per_claim: int = 3,
    min_score: float = 0.16,
) -> list[dict[str, Any]]:
    """Build a conservative, derived claim-to-source-note map.

    This is not a review workflow and does not upgrade confidence. It only says:
    "this raw source note appears textually relevant to this claim." Notes that
    are registration-only, malformed, or manual-verification only should already
    be marked non-usable by the caller and will be ignored here.
    """
    usable_notes = [
        note
        for note in source_notes
        if note.get("note_kind") == "claim_candidate"
        and str(note.get("note_quality") or "reader_ready") == "reader_ready"
    ]
    links: list[ClaimSourceLink] = []
    for claim in claim_entries:
        claim_id = str(claim.get("claim_item_id") or claim.get("claim_hash") or "")
        claim_text = str(claim.get("claim_text") or "")
        claim_terms = _claim_terms(claim)
        scored: list[ClaimSourceLink] = []
        for note in usable_notes:
            summary = str(note.get("summary") or "")
            note_terms = _terms(summary)
            matched = tuple(sorted(claim_terms & note_terms))
            if not matched:
                continue
            score = _score_match(claim_terms, note_terms, matched, summary)
            if score < min_score:
                continue
            scored.append(
                ClaimSourceLink(
                    claim_id=claim_id,
                    claim_text=claim_text,
                    note_id=str(note.get("note_id") or ""),
                    source_path=str(note.get("source_path") or ""),
                    locator=str(note.get("locator") or ""),
                    relation=_relation(summary),
                    score=round(score, 3),
                    matched_terms=matched,
                    review_status=str(note.get("review_status") or "raw"),
                    note_quality=str(note.get("note_quality") or "reader_ready"),
                    summary=_truncate(summary, 220),
                )
            )
        links.extend(
            sorted(scored, key=lambda item: (-item.score, item.note_id))[:max_links_per_claim]
        )
    return [link.to_dict() for link in links]


def _claim_terms(claim: dict[str, Any]) -> set[str]:
    claim_type = str(claim.get("claim_type") or "")
    terms = _terms(str(claim.get("claim_text") or ""))
    terms |= CLAIM_KEYWORDS.get(claim_type, set())
    return terms


def _terms(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z0-9]{2,}", text.lower())
        if token not in STOPWORDS
    }


def _score_match(
    claim_terms: set[str],
    note_terms: set[str],
    matched: tuple[str, ...],
    summary: str,
) -> float:
    if not claim_terms or not note_terms:
        return 0.0
    coverage = len(matched) / max(1, len(claim_terms))
    density = len(matched) / max(1, len(note_terms))
    bonus = 0.0
    lowered = summary.lower()
    if "rti" in claim_terms and "rti" in lowered:
        bonus += 0.18
    if "ledger" in claim_terms and "ledger" in lowered:
        bonus += 0.12
    if "evidence" in claim_terms and "evidence" in lowered:
        bonus += 0.10
    return coverage * 0.75 + density * 0.25 + bonus


def _relation(summary: str) -> str:
    lowered = summary.lower()
    if any(term in lowered for term in CHALLENGE_TERMS):
        return "challenges"
    return "supports"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rsplit(" ", 1)[0] + "..."
