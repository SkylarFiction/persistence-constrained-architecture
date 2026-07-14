from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import hashlib
import os
import re

from .ledger import ContinuityLedger
from .manifest import IdentityManifest


KNOWLEDGE_HUB_EVENT = "knowledge_hub.indexed"

SUPPORTED_HUB_SUFFIXES = {
    ".csv",
    ".docx",
    ".epub",
    ".html",
    ".md",
    ".pdf",
    ".tex",
    ".txt",
}

SKIP_DIR_NAMES = {
    ".agents",
    ".codex",
    ".git",
    ".pytest_cache",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}

PROJECT_GENERATED_PREFIXES = (
    "persistence_constrained_architecture/data/",
    "persistence_constrained_architecture/reports/",
    "persistence_constrained_architecture/scenario_runs/",
)

TOPIC_PATTERNS = {
    "coherence_physics": (
        "coherence",
        "csm",
        "rti",
        "ucft",
        "unified coherence",
        "recovery threshold",
        "collapse framework",
    ),
    "ai_identity": (
        "lucien",
        "identity",
        "persistence",
        "continuity",
        "agent",
        "memory",
        "pca",
    ),
    "math_physics": (
        "theorem",
        "proof",
        "equation",
        "navier",
        "smooth",
        "field",
        "physics",
        "math",
    ),
    "fiction_narrative": (
        "fiction",
        "novel",
        "diary",
        "story",
        "chapter",
        "101 ways",
    ),
    "theology_breath": (
        "christian",
        "pantheist",
        "theology",
        "breath",
        "cosmos",
    ),
    "research_archive": (
        "paper",
        "essay",
        "draft",
        "research",
        "notes",
        "source",
    ),
}


@dataclass(frozen=True)
class KnowledgeHubSourceRecord:
    source_id: str
    relative_path: str
    suffix: str
    size_bytes: int
    content_sha256: str
    title: str
    topic: str
    mtime_ns: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "relative_path": self.relative_path,
            "suffix": self.suffix,
            "size_bytes": self.size_bytes,
            "content_sha256": self.content_sha256,
            "title": self.title,
            "topic": self.topic,
            "mtime_ns": self.mtime_ns,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "KnowledgeHubSourceRecord":
        return cls(
            source_id=str(payload["source_id"]),
            relative_path=str(payload["relative_path"]),
            suffix=str(payload["suffix"]),
            size_bytes=int(payload["size_bytes"]),
            content_sha256=str(payload["content_sha256"]),
            title=str(payload["title"]),
            topic=str(payload["topic"]),
            mtime_ns=int(payload.get("mtime_ns", 0)),
        )


def index_knowledge_hub(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    project_root: str | Path = ".",
    limit: int = 250,
    topic: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """Catalog readable Master files as governed source inventory.

    This does not delete, move, rewrite, or ingest full source text into memory.
    It writes only file metadata and content hashes into the PCA ledger so later
    research steps can choose relevant evidence deliberately.
    """
    workspace_root = Path(project_root).resolve().parent
    previous_sources = knowledge_hub_sources_from_events(ledger.events())
    discovered = discover_knowledge_hub_sources(
        workspace_root, limit=limit, topic=topic, previous_sources=previous_sources
    )
    existing_source_ids = {source.source_id for source in previous_sources}
    new_sources = [source for source in discovered if source.source_id not in existing_source_ids]
    reused_sources = [source for source in discovered if source.source_id in existing_source_ids]
    record = {
        "workspace_root": str(workspace_root),
        "candidate_count": len(discovered),
        "indexed_count": len(new_sources),
        "reused_count": len(reused_sources),
        "topic_filter": topic,
        "topic_counts": _topic_counts(discovered),
        "sources": [source.to_dict() for source in discovered],
        "generated_output_root": str((workspace_root / "knowledge_hub" / "generated").resolve()),
        "governance": "Master files are read-only knowledge sources; generated documents must be written separately.",
        "will_not": [
            "delete existing Master files",
            "rewrite or normalize source documents in place",
            "treat cataloged files as reviewed evidence automatically",
            "cite every cataloged file in a topic-specific paper",
        ],
        "reason": reason or "knowledge hub index run",
    }
    ledger.append(KNOWLEDGE_HUB_EVENT, manifest.system_id, record)
    return record


def discover_knowledge_hub_sources(
    workspace_root: str | Path,
    limit: int = 250,
    topic: str | None = None,
    previous_sources: list[KnowledgeHubSourceRecord] | None = None,
) -> list[KnowledgeHubSourceRecord]:
    workspace = Path(workspace_root).resolve()
    # Hashing the full content of every candidate file is the dominant cost of
    # indexing (SHA-256 over a few hundred PDFs/books can take tens of
    # seconds) and was previously done unconditionally on every run, even
    # when nothing on disk had changed. Cheap stat() metadata (size + mtime)
    # is enough to tell an unchanged file from a changed one in the common
    # case, so a file whose size and mtime still match the last indexed
    # record reuses that record's hash instead of re-reading the file.
    previous_by_path = {record.relative_path: record for record in previous_sources or []}
    candidates: list[KnowledgeHubSourceRecord] = []
    for current_root, dir_names, file_names in os.walk(workspace):
        root_path = Path(current_root)
        dir_names[:] = sorted(
            name for name in dir_names if not _should_skip_dir(root_path / name, workspace)
        )
        for file_name in sorted(file_names):
            if len(candidates) >= limit:
                break
            path = root_path / file_name
            if path.is_symlink() or not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix not in SUPPORTED_HUB_SUFFIXES:
                continue
            relative_path = _relative_to_workspace(path, workspace)
            if _is_project_generated_path(relative_path):
                continue
            source_topic = classify_knowledge_hub_source(relative_path)
            if topic and source_topic != topic:
                continue
            stat = path.stat()
            previous = previous_by_path.get(relative_path)
            if (
                previous is not None
                and previous.size_bytes == stat.st_size
                and previous.mtime_ns == stat.st_mtime_ns
            ):
                content_sha256 = previous.content_sha256
            else:
                content_sha256 = _file_sha256(path)
            candidates.append(
                KnowledgeHubSourceRecord(
                    source_id=_source_id(relative_path, content_sha256),
                    relative_path=relative_path,
                    suffix=suffix,
                    size_bytes=stat.st_size,
                    content_sha256=content_sha256,
                    title=_title_from_path(path),
                    topic=source_topic,
                    mtime_ns=stat.st_mtime_ns,
                )
            )
        if len(candidates) >= limit:
            break
    return candidates


def knowledge_hub_sources_from_events(events: list[Any]) -> list[KnowledgeHubSourceRecord]:
    latest: dict[str, KnowledgeHubSourceRecord] = {}
    for event in events:
        if event.event_type != KNOWLEDGE_HUB_EVENT:
            continue
        for item in event.payload.get("sources", []):
            record = KnowledgeHubSourceRecord.from_dict(item)
            latest[record.source_id] = record
    return list(latest.values())


def knowledge_hub_snapshot(events: list[Any], topic: str | None = None) -> dict[str, Any]:
    sources = knowledge_hub_sources_from_events(events)
    if topic:
        sources = [source for source in sources if source.topic == topic]
    return {
        "count": len(sources),
        "topic_filter": topic,
        "topic_counts": _topic_counts(sources),
        "sources": [source.to_dict() for source in sources],
    }


def render_knowledge_hub_index_text(record: dict[str, Any]) -> str:
    lines = [
        "Knowledge Hub Index",
        f"workspace: {record['workspace_root']}",
        f"indexed: {record['indexed_count']} new / {record['reused_count']} reused / {record['candidate_count']} cataloged",
        f"generated documents: {record['generated_output_root']}",
        "governance: existing Master files are read-only sources",
    ]
    if record.get("topic_counts"):
        lines.append("topics:")
        for topic, count in sorted(record["topic_counts"].items()):
            lines.append(f"  {topic}: {count}")
    for source in record.get("sources", [])[:10]:
        lines.append(f"- {source['topic']} | {source['relative_path']}")
    if len(record.get("sources", [])) > 10:
        lines.append(f"... {len(record['sources']) - 10} more")
    return "\n".join(lines)


def render_knowledge_hub_sources_text(snapshot: dict[str, Any]) -> str:
    lines = [
        "Knowledge Hub Sources",
        f"count: {snapshot['count']}",
    ]
    if snapshot.get("topic_filter"):
        lines.append(f"topic: {snapshot['topic_filter']}")
    for source in snapshot.get("sources", [])[:50]:
        lines.append(
            f"- {source['topic']} | {source['title']} | {source['relative_path']}"
        )
    if snapshot["count"] > 50:
        lines.append(f"... {snapshot['count'] - 50} more")
    return "\n".join(lines)


def classify_knowledge_hub_source(relative_path: str) -> str:
    haystack = relative_path.lower().replace("-", " ").replace("_", " ")
    for topic, patterns in TOPIC_PATTERNS.items():
        if any(pattern in haystack for pattern in patterns):
            return topic
    return "general_archive"


def _should_skip_dir(path: Path, workspace: Path) -> bool:
    if path.name in SKIP_DIR_NAMES:
        return True
    return _is_project_generated_path(_relative_to_workspace(path, workspace) + "/")


def _is_project_generated_path(relative_path: str) -> bool:
    normalized = relative_path.replace("\\", "/")
    return any(normalized.startswith(prefix) for prefix in PROJECT_GENERATED_PREFIXES)


def _relative_to_workspace(path: Path, workspace: Path) -> str:
    return path.resolve().relative_to(workspace).as_posix()


def _title_from_path(path: Path) -> str:
    stem = re.sub(r"[_-]+", " ", path.stem)
    stem = re.sub(r"\s+", " ", stem).strip()
    return stem or path.name


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_id(relative_path: str, content_sha256: str) -> str:
    digest = hashlib.sha256(f"{relative_path}\n{content_sha256}".encode("utf-8")).hexdigest()
    return f"kh_{digest[:16]}"


def _topic_counts(sources: list[KnowledgeHubSourceRecord]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for source in sources:
        counts[source.topic] = counts.get(source.topic, 0) + 1
    return counts
