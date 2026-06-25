from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
from typing import Any


GENESIS_HASH = "GENESIS"


def _canonical_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ContinuityEvent:
    event_type: str
    subject_id: str
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    previous_hash: str = GENESIS_HASH
    event_hash: str = ""

    @classmethod
    def create(
        cls,
        event_type: str,
        subject_id: str,
        payload: dict[str, Any],
        previous_hash: str,
    ) -> "ContinuityEvent":
        event = cls(
            event_type=event_type,
            subject_id=subject_id,
            payload=payload,
            previous_hash=previous_hash,
        )
        return event.with_hash()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContinuityEvent":
        return cls(
            event_type=str(data["event_type"]),
            subject_id=str(data["subject_id"]),
            payload=dict(data.get("payload", {})),
            timestamp=str(data["timestamp"]),
            previous_hash=str(data.get("previous_hash", GENESIS_HASH)),
            event_hash=str(data.get("event_hash", "")),
        )

    def hash_payload(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "subject_id": self.subject_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "previous_hash": self.previous_hash,
        }

    def with_hash(self) -> "ContinuityEvent":
        event_hash = hashlib.sha256(
            _canonical_json(self.hash_payload()).encode("utf-8")
        ).hexdigest()
        return ContinuityEvent(
            event_type=self.event_type,
            subject_id=self.subject_id,
            payload=self.payload,
            timestamp=self.timestamp,
            previous_hash=self.previous_hash,
            event_hash=event_hash,
        )

    def to_dict(self) -> dict[str, Any]:
        data = self.hash_payload()
        data["event_hash"] = self.event_hash
        return data


class ContinuityLedger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.path.with_suffix(self.path.suffix + ".lock")

    def append(
        self, event_type: str, subject_id: str, payload: dict[str, Any]
    ) -> ContinuityEvent:
        with self._exclusive_lock():
            event = self._append_unlocked(event_type, subject_id, payload)
        return event

    def append_many(
        self,
        entries: list[tuple[str, str, dict[str, Any]]],
    ) -> list[ContinuityEvent]:
        with self._exclusive_lock():
            return [
                self._append_unlocked(event_type, subject_id, payload)
                for event_type, subject_id, payload in entries
            ]

    def events(self) -> list[ContinuityEvent]:
        if not self.path.exists():
            return []
        return [
            ContinuityEvent.from_dict(json.loads(line))
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def last_hash(self) -> str:
        events = self.events()
        if not events:
            return GENESIS_HASH
        return events[-1].event_hash

    def verify_chain(self) -> bool:
        previous_hash = GENESIS_HASH
        for event in self.events():
            if event.previous_hash != previous_hash:
                return False
            if event.with_hash().event_hash != event.event_hash:
                return False
            previous_hash = event.event_hash
        return True

    @contextmanager
    def _exclusive_lock(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a", encoding="utf-8") as lock_handle:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)

    def _append_unlocked(
        self,
        event_type: str,
        subject_id: str,
        payload: dict[str, Any],
    ) -> ContinuityEvent:
        previous_hash = self.last_hash()
        event = ContinuityEvent.create(
            event_type=event_type,
            subject_id=subject_id,
            payload=payload,
            previous_hash=previous_hash,
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical_json(event.to_dict()) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event
