from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import re
import uuid
import zipfile

from .coherence_corpus import coherence_corpus_index_records_from_events
from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .missions import require_mission


KEY_TERMS = (
    "coherence",
    "identity",
    "persistence",
    "recover",
    "recovery",
    "collapse",
    "memory",
    "boundary",
    "evidence",
    "constraint",
    "field",
    "stability",
)


@dataclass(frozen=True)
class SourceNoteRecord:
    note_id: str
    identity_id: str
    mission_id: str
    source_path: str
    theme: str
    title: str
    note_kind: str
    summary: str
    locator: str
    confidence: str
    review_status: str
    summary_hash: str
    excerpt_hash: str
    excerpt_length: int
    created_at: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def extract_source_notes_for_mission(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    project_root: str | Path = ".",
    mission_id: str | None = None,
    limit_sources: int = 6,
    notes_per_source: int = 3,
    reason: str = "",
) -> dict[str, Any]:
    selected_mission_id = mission_id or _latest_corpus_mission_id(ledger.events())
    if not selected_mission_id:
        record = {
            "status": "blocked",
            "created_count": 0,
            "reused_count": 0,
            "mission_id": None,
            "reason": reason or "no indexed mission sources available",
        }
        ledger.append("source_note.extraction_ran", manifest.system_id, record)
        return record
    mission = require_mission(ledger.events(), selected_mission_id)
    project_path = Path(project_root).resolve()
    workspace_root = project_path.parent
    sources = _corpus_sources_for_mission(ledger.events(), selected_mission_id)[:limit_sources]
    existing_hashes = {
        record.summary_hash for record in source_note_records_from_events(ledger.events())
    }
    created: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    entries: list[tuple[str, str, dict[str, Any]]] = []
    for source in sources:
        path_text = str(source.get("path") or "")
        source_path = _resolve_source_path(workspace_root, path_text)
        text = _read_source_text(source_path)
        notes = _notes_for_source(
            manifest=manifest,
            mission_id=selected_mission_id,
            source_path=path_text,
            theme=str(source.get("theme") or "general_coherence"),
            title=_title_from_path(path_text),
            text=text,
            notes_per_source=notes_per_source,
            reason=reason or "source note extracted for Coherence Physics paper",
        )
        for note in notes:
            if note.summary_hash in existing_hashes:
                reused.append(note.to_dict())
                continue
            existing_hashes.add(note.summary_hash)
            payload = note.to_dict()
            created.append(payload)
            entries.append(("source_note.extracted", manifest.system_id, payload))
    run_record = {
        "status": "notes_ready" if sources else "no_sources",
        "mission_id": selected_mission_id,
        "mission_title": mission.title,
        "source_count": len(sources),
        "created_count": len(created),
        "reused_count": len(reused),
        "notes": created,
        "reused": reused,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "governance": "source notes are raw citation cards until reviewed by steward",
        "will_not": [
            "treat extracted notes as final conclusions",
            "store whole source documents in the ledger",
            "publish a final paper without human review",
        ],
        "reason": reason or "source note extraction run",
    }
    entries.append(("source_note.extraction_ran", manifest.system_id, run_record))
    if entries:
        ledger.append_many(entries)
    return run_record


def source_note_records_from_events(
    events: list[ContinuityEvent],
    mission_id: str | None = None,
) -> list[SourceNoteRecord]:
    records: list[SourceNoteRecord] = []
    for event in events:
        if event.event_type != "source_note.extracted":
            continue
        payload = event.payload
        if mission_id and payload.get("mission_id") != mission_id:
            continue
        records.append(SourceNoteRecord(**payload))
    return records


def source_notes_for_mission(
    events: list[ContinuityEvent],
    mission_id: str,
) -> list[dict[str, Any]]:
    return [record.to_dict() for record in source_note_records_from_events(events, mission_id)]


def render_source_notes_text(result: dict[str, Any]) -> str:
    lines = [
        "Coherence Source Notes",
        f"status: {result.get('status')}",
        f"mission: {result.get('mission_title') or result.get('mission_id') or 'none'}",
        f"sources: {result.get('source_count', 0)}",
        f"created: {result.get('created_count', 0)}",
        f"reused: {result.get('reused_count', 0)}",
    ]
    for note in result.get("notes") or []:
        lines.append(
            "- "
            f"{note.get('note_kind', 'note')} / {note.get('theme', 'general')} / "
            f"{note.get('source_path', 'unknown')}: {note.get('summary', '')}"
        )
    lines.extend(
        [
            "guardrail:",
            "- Notes are raw citation cards until reviewed; they do not finalize claims.",
        ]
    )
    return "\n".join(lines)


def _latest_corpus_mission_id(events: list[ContinuityEvent]) -> str | None:
    for record in reversed(coherence_corpus_index_records_from_events(events)):
        if record.get("mission_id"):
            return str(record["mission_id"])
    return None


def _corpus_sources_for_mission(
    events: list[ContinuityEvent],
    mission_id: str,
) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for record in coherence_corpus_index_records_from_events(events):
        if record.get("mission_id") != mission_id:
            continue
        for item in [*(record.get("indexed") or []), *(record.get("reused") or [])]:
            key = (str(item.get("path", "")), str(item.get("theme", "")))
            if key in seen:
                continue
            seen.add(key)
            sources.append(item)
    return sources


def _notes_for_source(
    manifest: IdentityManifest,
    mission_id: str,
    source_path: str,
    theme: str,
    title: str,
    text: str,
    notes_per_source: int,
    reason: str,
) -> list[SourceNoteRecord]:
    excerpts = _select_excerpts(text, max(1, notes_per_source - 1))
    summaries = [
        (
            "source_overview",
            f"{title} is registered as a {theme} source for the Coherence Physics mission.",
            "source-metadata",
            "",
            "medium",
        )
    ]
    for index, excerpt in enumerate(excerpts, start=1):
        kind = "claim_candidate" if any(term in excerpt.lower() for term in KEY_TERMS) else "source_observation"
        summaries.append(
            (
                kind,
                _summary_from_excerpt(excerpt),
                f"text-snippet-{index}",
                excerpt,
                "medium" if kind == "claim_candidate" else "low",
            )
        )
    now = datetime.now(timezone.utc).isoformat()
    records: list[SourceNoteRecord] = []
    for note_kind, summary, locator, excerpt, confidence in summaries[:notes_per_source]:
        summary_hash = _hash_text("|".join([mission_id, source_path, note_kind, summary]))
        records.append(
            SourceNoteRecord(
                note_id=f"source_note_{uuid.uuid4()}",
                identity_id=manifest.system_id,
                mission_id=mission_id,
                source_path=source_path,
                theme=theme,
                title=title,
                note_kind=note_kind,
                summary=summary,
                locator=locator,
                confidence=confidence,
                review_status="raw",
                summary_hash=summary_hash,
                excerpt_hash=_hash_text(excerpt) if excerpt else "",
                excerpt_length=len(excerpt),
                created_at=now,
                reason=reason,
            )
        )
    return records


def _select_excerpts(text: str, limit: int) -> list[str]:
    if not text.strip():
        return []
    sentences = _candidate_sentences(text)
    scored = sorted(
        sentences,
        key=lambda sentence: (
            sum(1 for term in KEY_TERMS if term in sentence.lower()),
            min(len(sentence), 360),
        ),
        reverse=True,
    )
    chosen: list[str] = []
    seen: set[str] = set()
    for sentence in scored:
        clean = _clean_text(sentence)
        if len(clean) < 35:
            continue
        if _readable_ratio(clean) < 0.82:
            continue
        if not _looks_like_language(clean):
            continue
        key = clean[:120].lower()
        if key in seen:
            continue
        seen.add(key)
        chosen.append(clean[:420])
        if len(chosen) >= limit:
            break
    return chosen


def _candidate_sentences(text: str) -> list[str]:
    clean = _clean_text(text)
    chunks = re.split(r"(?<=[.!?])\s+|\n{2,}|(?m)^#{1,6}\s+", clean)
    return [chunk.strip(" -:\t") for chunk in chunks if chunk.strip()]


def _summary_from_excerpt(excerpt: str) -> str:
    clean = _clean_text(excerpt)
    if len(clean) <= 260:
        return clean
    return clean[:257].rsplit(" ", 1)[0] + "..."


def _read_source_text(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    suffix = path.suffix.lower()
    try:
        if suffix in {".md", ".txt", ".tex", ".csv", ".html"}:
            return path.read_text(encoding="utf-8", errors="ignore")
        if suffix == ".docx":
            return _read_docx_text(path)
        if suffix == ".epub":
            return _read_epub_text(path)
        if suffix == ".pdf":
            return _read_pdf_text_fallback(path)
    except OSError:
        return ""
    return ""


def _read_docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except (KeyError, zipfile.BadZipFile, OSError):
        return ""
    return _strip_xml(xml)


def _read_epub_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            parts = [
                archive.read(name).decode("utf-8", errors="ignore")
                for name in archive.namelist()
                if name.lower().endswith((".xhtml", ".html", ".htm"))
            ][:8]
    except (zipfile.BadZipFile, OSError):
        return ""
    return _strip_xml("\n".join(parts))


def _read_pdf_text_fallback(path: Path) -> str:
    data = path.read_bytes()[:2_000_000]
    raw = data.decode("latin-1", errors="ignore")
    strings = re.findall(r"\(([^()]{20,500})\)", raw)
    readable = [
        _clean_text(item)
        for item in strings
        if _readable_ratio(item) >= 0.82 and _looks_like_language(item)
    ]
    if readable:
        return " ".join(readable)
    raw_lines = [
        _clean_text(item)
        for item in re.split(r"[\r\n]+", raw)
        if _readable_ratio(item) >= 0.9 and _looks_like_language(item)
    ]
    return " ".join(raw_lines[:20])


def _strip_xml(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    return _clean_text(text)


def _resolve_source_path(workspace_root: Path, path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return (workspace_root / path_text).resolve()


def _title_from_path(path_text: str) -> str:
    stem = Path(path_text).stem or "Untitled source"
    return stem.replace("_", " ").replace("-", " ").strip()


def _clean_text(text: str) -> str:
    text = "".join(character if character.isprintable() else " " for character in text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _readable_ratio(text: str) -> float:
    if not text:
        return 0.0
    readable = sum(1 for character in text if character.isascii() and (character.isprintable() or character.isspace()))
    return readable / max(1, len(text))


def _looks_like_language(text: str) -> bool:
    clean = _clean_text(text)
    lowered = clean.lower()
    if any(
        marker in lowered
        for marker in ("endstream", "endobj", "/mediabox", "/contents", " obj ", " xref ")
    ):
        return False
    if "<<" in clean or clean.lstrip().startswith("/"):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'-]{2,}", clean)
    if len(words) < 5:
        return False
    alpha = sum(1 for character in clean if character.isalpha())
    punctuation = sum(1 for character in clean if character in "\\/{}[]<>^~|@#$%&*_=+")
    return alpha / max(1, len(clean)) >= 0.35 and punctuation / max(1, len(clean)) <= 0.12
