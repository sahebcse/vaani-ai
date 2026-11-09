"""Call ledger: append-only record of completed calls (in-memory; Unit 7+ persists)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CallRecord:
    call_id: str
    tenant: str
    frames_received: int
    frames_dropped: int
    errors: int
    transcript_chars: int
    escalated: bool


class CallLog:
    def __init__(self, limit: int = 1000) -> None:
        self._records: list[CallRecord] = []
        self._limit = limit

    def append(self, record: CallRecord) -> None:
        self._records.append(record)
        if len(self._records) > self._limit:
            del self._records[: len(self._records) - self._limit]

    def list_recent(self, limit: int = 50) -> list[CallRecord]:
        return list(reversed(self._records[-limit:]))

    def count(self) -> int:
        return len(self._records)
