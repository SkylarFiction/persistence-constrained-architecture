from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import re

from .evidence_locker import (
    add_evidence,
    evidence_link_records_from_events,
    evidence_records_from_events,
    link_evidence,
)
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .missions import MissionStatus, mission_briefs_from_events, require_mission


SUPPORTED_SUFFIXES = {".pdf", ".tex", ".md", ".txt", ".docx", ".epub", ".csv", ".html"}

DEFAULT_CORPUS_ROOTS = [
    "coherence ",
    "finished books ",
    "papers in limbo/new cohernce papers",
    "papers in limbo/claude quality",
    "papers in limbo/Finishes Essays /coherence",
    "math_spine",
]

THEME_PATTERNS = {
    "core_axioms": ("axiom", "codex", "physics of coherence", "coherence_physics"),
    "csm_monitoring": ("csm", "stability monitor", "collapse", "threshold"),
    "identity_physics": ("identity", "persistence", "memory", "mind", "lucien"),
    "coherence_field": ("field", "ucft", "unified", "logos", "vacuum"),
    "cognitive_physics": ("cognitive", "learning", "neuron", "predictive"),
    "bio_coherence": ("bio", "biology", "breath", "neuro", "life"),
    "cosmology": ("cosmic", "gravity", "dark", "halo", "stellar", "spacetime"),
    "math_spine": ("theorem", "proof", "regularity", ".tex", "navier", "smooth"),
    "public_narrative": ("primer", "public", "architecture", "essay", "narrative"),
}

NON_CANONICAL_INCLUDE_PATTERNS = (
    "coherence physics",
    "coherence codex",
    "persistence constrained architecture",
    "pca",
    "csm",
    "coherence stability monitor",
    "recovery threshold",
    "collapse framework",
    "identity persistence",
    "identity continuity",
    "ucft",
    "unified coherence field",
)

NON_CANONICAL_EXCLUDE_PATTERNS = (
    "fiction",
    "novel",
    "diary",
    "101 ways",
    "christian pantheist",
    "pantheist theology",
    "quantum living",
    "breath of cosmos",
    "breath of life",
)


@dataclass(frozen=True)
class CorpusCandidate:
    path: Path
    relative_path: str
    theme: str
    size_bytes: int
    content_sha256: str

    def source_descriptor(self) -> str:
        return "\n".join(
            [
                f"path:{self.relative_path}",
                f"sha256:{self.content_sha256}",
                f"size:{self.size_bytes}",
            ]
        )

    def source_hash(self) -> str:
        return hashlib.sha256(self.source_descriptor().encode("utf-8")).hexdigest()

    def summary(self) -> str:
        return (
            f"Coherence Physics corpus source: {self.path.name}. "
            f"Theme: {self.theme}. Type: {self.path.suffix.lower() or 'unknown'}. "
            f"Size: {self.size_bytes} bytes. Relative path: {self.relative_path}."
        )


def index_coherence_corpus(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    project_root: str | Path = ".",
    mission_id: str | None = None,
    roots: list[str] | None = None,
    limit: int = 12,
    reason: str = "",
) -> dict[str, Any]:
    project_path = Path(project_root).resolve()
    workspace_root = project_path.parent
    mission = _select_mission(ledger, mission_id)
    candidates = discover_coherence_sources(workspace_root, roots=roots, limit=limit)
    existing_by_source_hash = {
        record.source_hash: record for record in evidence_records_from_events(ledger.events())
    }
    existing_links = {
        (link.evidence_id, link.target_type.value, link.target_id)
        for link in evidence_link_records_from_events(ledger.events())
    }
    indexed: list[dict[str, Any]] = []
    linked: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    for candidate in candidates:
        existing = existing_by_source_hash.get(candidate.source_hash())
        if existing:
            evidence = existing
            reused.append(
                {
                    "evidence_id": evidence.evidence_id,
                    "path": candidate.relative_path,
                    "theme": candidate.theme,
                }
            )
        else:
            evidence = add_evidence(
                ledger,
                manifest.system_id,
                source_type="file",
                source=candidate.source_descriptor(),
                summary=candidate.summary(),
                confidence="medium",
                reason=reason or "coherence corpus indexed source",
            )
            existing_by_source_hash[evidence.source_hash] = evidence
            indexed.append(
                {
                    "evidence_id": evidence.evidence_id,
                    "path": candidate.relative_path,
                    "theme": candidate.theme,
                }
            )
        if mission and (evidence.evidence_id, "mission", mission["mission_id"]) not in existing_links:
            link = link_evidence(
                ledger,
                manifest.system_id,
                evidence.evidence_id,
                "mission",
                mission["mission_id"],
                reason=reason or "coherence corpus linked source to research mission",
            )
            existing_links.add((evidence.evidence_id, "mission", mission["mission_id"]))
            linked.append(link.to_dict())
    record = {
        "candidate_count": len(candidates),
        "indexed_count": len(indexed),
        "reused_count": len(reused),
        "linked_count": len(linked),
        "mission_id": mission["mission_id"] if mission else None,
        "mission_title": mission["title"] if mission else None,
        "themes": _theme_counts(candidates),
        "indexed": indexed,
        "reused": reused,
        "governance": "sources are raw evidence until reviewed by steward",
        "will_not": [
            "treat indexed sources as verified",
            "extract private content into memory automatically",
            "publish or write final conclusions without review",
        ],
        "reason": reason or "coherence corpus index run",
    }
    ledger.append("coherence_corpus.indexed", manifest.system_id, record)
    return record


# Roots whose entire tree is already scoped to Coherence Physics material by curation,
# so every file in them is admitted regardless of filename. Any other root (e.g. "finished
# books ", which mixes in unrelated personal projects) must pass the relevance gate below.
CANONICAL_COHERENCE_ROOTS = {
    root for root in DEFAULT_CORPUS_ROOTS if root != "finished books "
}


def is_relevant_source_path(relative_path: str) -> bool:
    """Whether a workspace-relative path is admissible as Coherence Physics evidence.

    Applies the same gate as corpus discovery, but keyed on the path alone so it
    can also re-check evidence and source notes already recorded in ledger
    history (which may predate this gate or a later tightening of it), rather
    than only filtering at initial indexing time.
    """
    if any(relative_path.startswith(root) for root in CANONICAL_COHERENCE_ROOTS):
        return True
    return _matches_noncanonical_relevance(relative_path)


def discover_coherence_sources(
    workspace_root: str | Path,
    roots: list[str] | None = None,
    limit: int = 12,
) -> list[CorpusCandidate]:
    workspace = Path(workspace_root).resolve()
    root_names = roots or DEFAULT_CORPUS_ROOTS
    candidates: list[CorpusCandidate] = []
    seen_titles: set[str] = set()
    for root_name in root_names:
        root = (workspace / root_name).resolve()
        if not root.exists():
            continue
        root_is_canonical = root_name in CANONICAL_COHERENCE_ROOTS or (
            roots is not None and root_name != "finished books "
        )
        for path in sorted(
            root.rglob("*"),
            key=lambda candidate: (
                _normalized_title(candidate),
                _suffix_priority(candidate),
                _copy_priority(candidate),
                str(candidate),
            ),
        ):
            if len(candidates) >= limit:
                break
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            relative_path = _relative_to_workspace(path, workspace)
            if not root_is_canonical and not _matches_noncanonical_relevance(relative_path):
                continue
            title_key = _normalized_title(path)
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            candidates.append(
                CorpusCandidate(
                    path=path,
                    relative_path=relative_path,
                    theme=classify_coherence_source(relative_path),
                    size_bytes=path.stat().st_size,
                    content_sha256=_file_sha256(path),
                )
            )
        if len(candidates) >= limit:
            break
    return candidates


def _matches_theme_pattern(path_text: str) -> bool:
    haystack = path_text.lower().replace("-", " ").replace("_", " ")
    return any(
        pattern in haystack for patterns in THEME_PATTERNS.values() for pattern in patterns
    )


def _matches_noncanonical_relevance(path_text: str) -> bool:
    haystack = path_text.lower().replace("-", " ").replace("_", " ")
    if any(pattern in haystack for pattern in NON_CANONICAL_EXCLUDE_PATTERNS):
        return False
    return any(pattern in haystack for pattern in NON_CANONICAL_INCLUDE_PATTERNS)


def _normalized_title(path: Path) -> str:
    stem = path.stem.lower()
    stem = re.sub(r"\(\d+\)", " ", stem)
    stem = re.sub(r"\b(copy|final|draft|v\d+)\b", " ", stem)
    stem = re.sub(r"[^a-z0-9]+", " ", stem)
    return stem.strip()


def _suffix_priority(path: Path) -> int:
    priorities = {
        ".pdf": 0,
        ".md": 1,
        ".txt": 1,
        ".tex": 1,
        ".docx": 2,
        ".epub": 3,
        ".html": 4,
        ".csv": 5,
    }
    return priorities.get(path.suffix.lower(), 9)


def _copy_priority(path: Path) -> int:
    return 1 if re.search(r"\bcopy\b", path.stem.lower()) else 0


def coherence_corpus_index_records_from_events(
    events: list[ContinuityEvent],
) -> list[dict[str, Any]]:
    return [
        event.payload
        for event in events
        if event.event_type == "coherence_corpus.indexed"
    ]


def render_coherence_corpus_index_text(result: dict[str, Any]) -> str:
    lines = [
        "Coherence Physics Corpus Index",
        f"mission: {result.get('mission_title') or 'none'}",
        f"candidates: {result.get('candidate_count', 0)}",
        f"indexed: {result.get('indexed_count', 0)}",
        f"reused: {result.get('reused_count', 0)}",
        f"linked: {result.get('linked_count', 0)}",
        "themes:",
    ]
    for theme, count in sorted((result.get("themes") or {}).items()):
        lines.append(f"- {theme}: {count}")
    if result.get("indexed"):
        lines.append("new evidence:")
        for item in result["indexed"]:
            lines.append(f"- {item['theme']} / {item['path']} / {item['evidence_id']}")
    return "\n".join(lines)


def classify_coherence_source(path_text: str) -> str:
    haystack = path_text.lower().replace("-", " ").replace("_", " ")
    for theme, patterns in THEME_PATTERNS.items():
        if any(pattern in haystack for pattern in patterns):
            return theme
    return "general_coherence"


def _select_mission(ledger: ContinuityLedger, mission_id: str | None) -> dict[str, str] | None:
    if mission_id:
        mission = require_mission(ledger.events(), mission_id)
        return {"mission_id": mission.mission_id, "title": mission.title}
    for brief in mission_briefs_from_events(ledger.events()):
        if (
            brief.mission.status == MissionStatus.OPEN
            and "coherence" in brief.mission.title.lower()
        ):
            return {"mission_id": brief.mission.mission_id, "title": brief.mission.title}
    for brief in mission_briefs_from_events(ledger.events()):
        if brief.mission.status == MissionStatus.OPEN:
            return {"mission_id": brief.mission.mission_id, "title": brief.mission.title}
    return None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_to_workspace(path: Path, workspace: Path) -> str:
    try:
        return str(path.resolve().relative_to(workspace))
    except ValueError:
        return str(path.resolve())


def _theme_counts(candidates: list[CorpusCandidate]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        counts[candidate.theme] = counts.get(candidate.theme, 0) + 1
    return counts
