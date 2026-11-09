"""Background jobs: feedback intake, call archival, nightly scheduler."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from vaani.ledger import CallLog


@dataclass(frozen=True)
class Feedback:
    call_id: str
    tenant: str
    helpful: bool
    note: str = ""


class FeedbackStore:
    def __init__(self) -> None:
        self._items: list[Feedback] = []

    def record(self, feedback: Feedback) -> Feedback:
        self._items.append(feedback)
        return feedback

    def list_recent(self, limit: int = 50) -> list[Feedback]:
        return list(reversed(self._items[-limit:]))

    def count(self) -> int:
        return len(self._items)


def archive_calls(log: CallLog, path: str) -> int:
    """Append all currently logged calls to a JSONL file. Returns rows written."""
    records = log.list_recent(limit=10_000)
    if not records:
        return 0
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        for record in reversed(records):
            fh.write(
                json.dumps(
                    {
                        "call_id": record.call_id,
                        "tenant": record.tenant,
                        "frames_received": record.frames_received,
                        "frames_dropped": record.frames_dropped,
                        "errors": record.errors,
                        "transcript_chars": record.transcript_chars,
                        "escalated": record.escalated,
                    }
                )
                + "\n"
            )
    return len(records)


def create_scheduler(log: CallLog, archive_path: str, archive_hours: int = 24) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        archive_calls,
        trigger="interval",
        hours=archive_hours,
        args=[log, archive_path],
        id="archive-calls",
    )
    return scheduler
