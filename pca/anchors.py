from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any
import uuid

from .ledger import ContinuityLedger, GENESIS_HASH


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class LedgerAnchorRecord:
    anchor_id: str
    ledger_path: str
    event_count: int
    head_hash: str
    chain_valid: bool
    created_at: str
    authority: str = "local_operator"
    note: str = ""
    previous_anchor_hash: str = GENESIS_HASH
    anchor_hash: str = ""

    @classmethod
    def create(
        cls,
        ledger: ContinuityLedger,
        previous_anchor_hash: str = GENESIS_HASH,
        authority: str = "local_operator",
        note: str = "",
    ) -> "LedgerAnchorRecord":
        events = ledger.events()
        record = cls(
            anchor_id=f"anchor_{uuid.uuid4()}",
            ledger_path=str(ledger.path),
            event_count=len(events),
            head_hash=ledger.last_hash(),
            chain_valid=ledger.verify_chain(),
            created_at=datetime.now(timezone.utc).isoformat(),
            authority=authority,
            note=note,
            previous_anchor_hash=previous_anchor_hash,
        )
        return record.with_hash()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LedgerAnchorRecord":
        return cls(
            anchor_id=str(data["anchor_id"]),
            ledger_path=str(data["ledger_path"]),
            event_count=int(data["event_count"]),
            head_hash=str(data["head_hash"]),
            chain_valid=bool(data["chain_valid"]),
            created_at=str(data["created_at"]),
            authority=str(data.get("authority", "local_operator")),
            note=str(data.get("note", "")),
            previous_anchor_hash=str(data.get("previous_anchor_hash", GENESIS_HASH)),
            anchor_hash=str(data.get("anchor_hash", "")),
        )

    def hash_payload(self) -> dict[str, Any]:
        return {
            "anchor_id": self.anchor_id,
            "ledger_path": self.ledger_path,
            "event_count": self.event_count,
            "head_hash": self.head_hash,
            "chain_valid": self.chain_valid,
            "created_at": self.created_at,
            "authority": self.authority,
            "note": self.note,
            "previous_anchor_hash": self.previous_anchor_hash,
        }

    def with_hash(self) -> "LedgerAnchorRecord":
        anchor_hash = hashlib.sha256(
            _canonical_json(self.hash_payload()).encode("utf-8")
        ).hexdigest()
        return LedgerAnchorRecord(
            anchor_id=self.anchor_id,
            ledger_path=self.ledger_path,
            event_count=self.event_count,
            head_hash=self.head_hash,
            chain_valid=self.chain_valid,
            created_at=self.created_at,
            authority=self.authority,
            note=self.note,
            previous_anchor_hash=self.previous_anchor_hash,
            anchor_hash=anchor_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        data = self.hash_payload()
        data["anchor_hash"] = self.anchor_hash
        return data


@dataclass(frozen=True)
class AnchorVerification:
    valid: bool
    reasons: list[str] = field(default_factory=list)
    latest_anchor: LedgerAnchorRecord | None = None
    current_head_hash: str = ""
    current_event_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "reasons": self.reasons,
            "latest_anchor": (
                self.latest_anchor.to_dict() if self.latest_anchor is not None else None
            ),
            "current_head_hash": self.current_head_hash,
            "current_event_count": self.current_event_count,
        }


@dataclass(frozen=True)
class AnchorExport:
    exported_at: str
    anchor_path: str
    verification: AnchorVerification
    export_hash: str = ""

    @classmethod
    def create(
        cls,
        anchor_path: str | Path,
        verification: AnchorVerification,
    ) -> "AnchorExport":
        export = cls(
            exported_at=datetime.now(timezone.utc).isoformat(),
            anchor_path=str(anchor_path),
            verification=verification,
        )
        return export.with_hash()

    def hash_payload(self) -> dict[str, Any]:
        return {
            "exported_at": self.exported_at,
            "anchor_path": self.anchor_path,
            "verification": self.verification.to_dict(),
        }

    def with_hash(self) -> "AnchorExport":
        export_hash = hashlib.sha256(
            _canonical_json(self.hash_payload()).encode("utf-8")
        ).hexdigest()
        return AnchorExport(
            exported_at=self.exported_at,
            anchor_path=self.anchor_path,
            verification=self.verification,
            export_hash=export_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        data = self.hash_payload()
        data["export_hash"] = self.export_hash
        return data


def load_anchor_records(path: str | Path) -> list[LedgerAnchorRecord]:
    anchor_path = Path(path)
    if not anchor_path.exists():
        return []
    return [
        LedgerAnchorRecord.from_dict(json.loads(line))
        for line in anchor_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def append_ledger_anchor(
    ledger: ContinuityLedger,
    path: str | Path,
    authority: str = "local_operator",
    note: str = "",
) -> LedgerAnchorRecord:
    anchor_path = Path(path)
    anchors = load_anchor_records(anchor_path)
    previous_hash = anchors[-1].anchor_hash if anchors else GENESIS_HASH
    record = LedgerAnchorRecord.create(
        ledger=ledger,
        previous_anchor_hash=previous_hash,
        authority=authority,
        note=note,
    )
    anchor_path.parent.mkdir(parents=True, exist_ok=True)
    with anchor_path.open("a", encoding="utf-8") as handle:
        handle.write(_canonical_json(record.to_dict()) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return record


def verify_anchor_chain(path: str | Path) -> AnchorVerification:
    anchors = load_anchor_records(path)
    if not anchors:
        return AnchorVerification(valid=False, reasons=["no anchor records found"])
    previous_hash = GENESIS_HASH
    reasons: list[str] = []
    for anchor in anchors:
        if anchor.previous_anchor_hash != previous_hash:
            reasons.append(f"anchor previous hash mismatch: {anchor.anchor_id}")
        if anchor.with_hash().anchor_hash != anchor.anchor_hash:
            reasons.append(f"anchor hash mismatch: {anchor.anchor_id}")
        previous_hash = anchor.anchor_hash
    return AnchorVerification(
        valid=not reasons,
        reasons=reasons or ["anchor chain valid"],
        latest_anchor=anchors[-1],
    )


def verify_latest_anchor(
    ledger: ContinuityLedger,
    path: str | Path,
) -> AnchorVerification:
    chain = verify_anchor_chain(path)
    if not chain.valid or chain.latest_anchor is None:
        return chain
    events = ledger.events()
    reasons = []
    current_head_hash = ledger.last_hash()
    current_event_count = len(events)
    if chain.latest_anchor.head_hash != current_head_hash:
        reasons.append("ledger head hash does not match latest anchor")
    if chain.latest_anchor.event_count != current_event_count:
        reasons.append("ledger event count does not match latest anchor")
    if not ledger.verify_chain():
        reasons.append("ledger hash chain is invalid")
    return AnchorVerification(
        valid=not reasons,
        reasons=reasons or ["latest anchor matches ledger head"],
        latest_anchor=chain.latest_anchor,
        current_head_hash=current_head_hash,
        current_event_count=current_event_count,
    )


def export_latest_anchor(
    ledger: ContinuityLedger,
    anchor_path: str | Path,
    output_path: str | Path,
) -> AnchorExport:
    export = AnchorExport.create(
        anchor_path=anchor_path,
        verification=verify_latest_anchor(ledger, anchor_path),
    )
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(export.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return export
