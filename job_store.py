from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class QueueFullError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    """Small persistent queue shared by the web process and one worker."""

    def __init__(self, database_path: Path):
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('queued', 'processing', 'complete', 'failed')),
                    original_name TEXT NOT NULL,
                    download_name TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    options_json TEXT NOT NULL,
                    midi_filename TEXT,
                    metadata_json TEXT,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at)"
            )

    def enqueue(
        self,
        *,
        job_id: str,
        original_name: str,
        download_name: str,
        mode: str,
        options: dict[str, Any],
        max_active_jobs: int | None = None,
    ) -> None:
        now = utc_now()
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if max_active_jobs is not None:
                active_jobs = connection.execute(
                    "SELECT COUNT(*) FROM jobs WHERE status IN ('queued', 'processing')"
                ).fetchone()[0]
                if active_jobs >= max_active_jobs:
                    connection.rollback()
                    raise QueueFullError("The conversion queue is currently full.")
            connection.execute(
                """
                INSERT INTO jobs (
                    id, status, original_name, download_name, mode,
                    options_json, created_at, updated_at
                ) VALUES (?, 'queued', ?, ?, ?, ?, ?, ?)
                """,
                (job_id, original_name, download_name, mode, json.dumps(options), now, now),
            )
            connection.commit()
        finally:
            connection.close()

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            job = dict(row)
            job["options"] = json.loads(job.pop("options_json"))
            metadata_json = job.pop("metadata_json")
            job["metadata"] = json.loads(metadata_json) if metadata_json else None
            return job

    def claim_next(self) -> dict[str, Any] | None:
        """Atomically claim one job; safe if multiple workers are started."""
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT id FROM jobs WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            now = utc_now()
            updated = connection.execute(
                "UPDATE jobs SET status = 'processing', updated_at = ? "
                "WHERE id = ? AND status = 'queued'",
                (now, row["id"]),
            )
            connection.commit()
            if updated.rowcount != 1:
                return None
            return self.get(row["id"])
        finally:
            connection.close()

    def complete(self, job_id: str, midi_filename: str, metadata: dict[str, Any]) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'complete', midi_filename = ?, metadata_json = ?,
                    error = NULL, updated_at = ?
                WHERE id = ?
                """,
                (midi_filename, json.dumps(metadata), utc_now(), job_id),
            )

    def fail(self, job_id: str, error: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'failed', error = ?, updated_at = ?
                WHERE id = ?
                """,
                (error[:4000], utc_now(), job_id),
            )

    def queue_position(self, job_id: str) -> int | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT status, created_at FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None or row["status"] != "queued":
                return None
            count = connection.execute(
                "SELECT COUNT(*) FROM jobs WHERE status = 'queued' AND created_at <= ?",
                (row["created_at"],),
            ).fetchone()[0]
            return int(count)

    def expired_terminal_jobs(self, retention_hours: int) -> list[str]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=retention_hours)).isoformat()
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT id FROM jobs
                WHERE status IN ('complete', 'failed') AND updated_at < ?
                """,
                (cutoff,),
            ).fetchall()
            return [row["id"] for row in rows]

    def requeue_stale_processing(self, stale_hours: int) -> int:
        """Recover work abandoned by a worker crash without touching active jobs."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=stale_hours)).isoformat()
        with self.connect() as connection:
            updated = connection.execute(
                """
                UPDATE jobs SET status = 'queued', updated_at = ?
                WHERE status = 'processing' AND updated_at < ?
                """,
                (utc_now(), cutoff),
            )
            return updated.rowcount

    def delete(self, job_id: str) -> None:
        with self.connect() as connection:
            connection.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
