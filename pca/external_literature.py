from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
import hashlib
import uuid

from .ledger import ContinuityEvent, ContinuityLedger
from .manifest import IdentityManifest
from .missions import require_mission


EXTERNAL_LITERATURE_STATUSES = {"raw", "reviewed", "rejected", "disputed", "stale"}


@dataclass(frozen=True)
class ExternalLiteratureRecord:
    literature_id: str
    identity_id: str
    mission_id: str
    title: str
    authors: str
    year: str
    venue: str
    doi: str
    url: str
    summary: str
    confidence: str
    review_status: str
    source_hash: str
    created_at: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExternalLiteratureReviewRecord:
    review_id: str
    identity_id: str
    literature_id: str
    review_status: str
    reviewer: str
    confidence: str | None
    created_at: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def add_external_literature(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    mission_id: str,
    *,
    title: str,
    authors: str = "",
    year: str = "",
    venue: str = "",
    doi: str = "",
    url: str = "",
    summary: str = "",
    confidence: str = "unknown",
    reason: str = "",
) -> ExternalLiteratureRecord:
    require_mission(ledger.events(), mission_id)
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("title is required")
    descriptor = "\n".join(
        [
            f"title:{clean_title}",
            f"authors:{authors.strip()}",
            f"year:{year.strip()}",
            f"venue:{venue.strip()}",
            f"doi:{doi.strip()}",
            f"url:{url.strip()}",
            f"summary:{summary.strip()}",
        ]
    )
    record = ExternalLiteratureRecord(
        literature_id=f"external_lit_{uuid.uuid4()}",
        identity_id=manifest.system_id,
        mission_id=mission_id,
        title=clean_title,
        authors=authors.strip(),
        year=year.strip(),
        venue=venue.strip(),
        doi=doi.strip(),
        url=url.strip(),
        summary=summary.strip(),
        confidence=confidence.strip() or "unknown",
        review_status="raw",
        source_hash=hashlib.sha256(descriptor.encode("utf-8")).hexdigest(),
        created_at=datetime.now(timezone.utc).isoformat(),
        reason=reason or "external scholarly literature attached to mission",
    )
    ledger.append("external_literature.added", manifest.system_id, record.to_dict())
    return record


def review_external_literature(
    ledger: ContinuityLedger,
    manifest: IdentityManifest,
    literature_id: str,
    review_status: str,
    *,
    reviewer: str = "human_steward",
    confidence: str | None = None,
    reason: str = "",
) -> ExternalLiteratureReviewRecord:
    status = review_status.strip().lower()
    if status not in EXTERNAL_LITERATURE_STATUSES:
        raise ValueError(f"Unsupported external literature review status: {review_status}")
    require_external_literature(ledger.events(), literature_id)
    record = ExternalLiteratureReviewRecord(
        review_id=f"external_lit_review_{uuid.uuid4()}",
        identity_id=manifest.system_id,
        literature_id=literature_id,
        review_status=status,
        reviewer=reviewer,
        confidence=confidence,
        created_at=datetime.now(timezone.utc).isoformat(),
        reason=reason or f"external literature marked {status}",
    )
    ledger.append("external_literature.reviewed", manifest.system_id, record.to_dict())
    return record


def require_external_literature(
    events: list[ContinuityEvent],
    literature_id: str,
) -> ExternalLiteratureRecord:
    for record in external_literature_records_from_events(events):
        if record.literature_id == literature_id:
            return record
    raise ValueError(f"External literature not found: {literature_id}")


def external_literature_records_from_events(
    events: list[ContinuityEvent],
    mission_id: str | None = None,
) -> list[ExternalLiteratureRecord]:
    records: list[ExternalLiteratureRecord] = []
    for event in events:
        if event.event_type != "external_literature.added":
            continue
        payload = event.payload
        if mission_id and payload.get("mission_id") != mission_id:
            continue
        records.append(ExternalLiteratureRecord(**payload))
    return records


def external_literature_review_records_from_events(
    events: list[ContinuityEvent],
    literature_id: str | None = None,
) -> list[ExternalLiteratureReviewRecord]:
    records: list[ExternalLiteratureReviewRecord] = []
    for event in events:
        if event.event_type != "external_literature.reviewed":
            continue
        payload = event.payload
        if literature_id and payload.get("literature_id") != literature_id:
            continue
        records.append(ExternalLiteratureReviewRecord(**payload))
    return records


def external_literature_for_mission(
    events: list[ContinuityEvent],
    mission_id: str,
) -> list[dict[str, Any]]:
    latest_reviews: dict[str, ExternalLiteratureReviewRecord] = {}
    for review in external_literature_review_records_from_events(events):
        latest_reviews[review.literature_id] = review
    records: list[dict[str, Any]] = []
    for record in external_literature_records_from_events(events, mission_id):
        item = record.to_dict()
        review = latest_reviews.get(record.literature_id)
        if review:
            item["review_status"] = review.review_status
            item["reviewer"] = review.reviewer
            item["review_reason"] = review.reason
            item["reviewed_at"] = review.created_at
            if review.confidence:
                item["confidence"] = review.confidence
        records.append(item)
    return records


def render_external_literature_text(records: list[dict[str, Any]]) -> str:
    lines = ["External Literature"]
    if not records:
        lines.append("No external scholarly sources attached.")
        return "\n".join(lines)
    for record in records:
        lines.append(
            "- "
            f"{record.get('review_status', 'raw')} / "
            f"{record.get('title', 'untitled')} / "
            f"{record.get('year') or 'unknown year'} / "
            f"{record.get('doi') or record.get('url') or 'no locator'}"
        )
    return "\n".join(lines)
