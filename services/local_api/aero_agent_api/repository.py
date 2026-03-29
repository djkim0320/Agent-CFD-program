from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .models import ConnectionRecord, JobEvent, JobRecord, JobStatus, utcnow


class Repository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.database_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS connections (
                    id TEXT PRIMARY KEY,
                    mode TEXT NOT NULL,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL,
                    data_policy TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_validated_at TEXT
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    selected_solver TEXT NOT NULL,
                    rationale TEXT,
                    progress INTEGER NOT NULL,
                    warnings_json TEXT NOT NULL,
                    artifacts_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    error TEXT,
                    request_json TEXT NOT NULL,
                    source_file_name TEXT NOT NULL,
                    source_file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT,
                    cancelled_at TEXT,
                    completed_at TEXT,
                    failed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS job_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_job_events_job_id_seq
                    ON job_events(job_id, seq);
                """
            )

    def upsert_connection(self, connection: ConnectionRecord) -> ConnectionRecord:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO connections
                    (id, mode, label, status, data_policy, metadata_json, created_at, last_validated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    mode=excluded.mode,
                    label=excluded.label,
                    status=excluded.status,
                    data_policy=excluded.data_policy,
                    metadata_json=excluded.metadata_json,
                    last_validated_at=excluded.last_validated_at
                """,
                (
                    connection.id,
                    connection.mode.value,
                    connection.label,
                    connection.status,
                    connection.data_policy,
                    json.dumps(connection.metadata),
                    connection.created_at.isoformat(),
                    connection.last_validated_at.isoformat() if connection.last_validated_at else None,
                ),
            )
        return connection

    def list_connections(self) -> list[ConnectionRecord]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM connections ORDER BY created_at DESC").fetchall()
        return [self._row_to_connection(row) for row in rows]

    def get_connection(self, connection_id: str) -> ConnectionRecord | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM connections WHERE id = ?", (connection_id,)).fetchone()
        return self._row_to_connection(row) if row else None

    def create_job(self, job: JobRecord) -> JobRecord:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, connection_id, status, selected_solver, rationale, progress,
                    warnings_json, artifacts_json, metrics_json, error, request_json,
                    source_file_name, source_file_path, created_at, updated_at,
                    approved_at, cancelled_at, completed_at, failed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.connection_id,
                    job.status.value,
                    job.selected_solver,
                    job.rationale,
                    job.progress,
                    json.dumps(job.warnings),
                    json.dumps(job.artifacts),
                    json.dumps(job.metrics),
                    job.error,
                    job.request.model_dump_json(),
                    job.source_file_name,
                    job.source_file_path,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                    job.approved_at.isoformat() if job.approved_at else None,
                    job.cancelled_at.isoformat() if job.cancelled_at else None,
                    job.completed_at.isoformat() if job.completed_at else None,
                    job.failed_at.isoformat() if job.failed_at else None,
                ),
            )
        return job

    def update_job(self, job: JobRecord) -> JobRecord:
        job.updated_at = utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    connection_id=?,
                    status=?,
                    selected_solver=?,
                    rationale=?,
                    progress=?,
                    warnings_json=?,
                    artifacts_json=?,
                    metrics_json=?,
                    error=?,
                    request_json=?,
                    source_file_name=?,
                    source_file_path=?,
                    updated_at=?,
                    approved_at=?,
                    cancelled_at=?,
                    completed_at=?,
                    failed_at=?
                WHERE id=?
                """,
                (
                    job.connection_id,
                    job.status.value,
                    job.selected_solver,
                    job.rationale,
                    job.progress,
                    json.dumps(job.warnings),
                    json.dumps(job.artifacts),
                    json.dumps(job.metrics),
                    job.error,
                    job.request.model_dump_json(),
                    job.source_file_name,
                    job.source_file_path,
                    job.updated_at.isoformat(),
                    job.approved_at.isoformat() if job.approved_at else None,
                    job.cancelled_at.isoformat() if job.cancelled_at else None,
                    job.completed_at.isoformat() if job.completed_at else None,
                    job.failed_at.isoformat() if job.failed_at else None,
                    job.id,
                ),
            )
        return job

    def get_job(self, job_id: str) -> JobRecord | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list_jobs(self) -> list[JobRecord]:
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
        return [self._row_to_job(row) for row in rows]

    def add_event(self, event: JobEvent) -> JobEvent:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO job_events (job_id, seq, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.job_id,
                    event.seq,
                    event.event_type,
                    json.dumps(event.payload),
                    event.created_at.isoformat(),
                ),
            )
            event.id = cursor.lastrowid
        return event

    def list_events(self, job_id: str) -> list[JobEvent]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM job_events WHERE job_id = ? ORDER BY seq ASC, id ASC",
                (job_id,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def next_event_seq(self, job_id: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM job_events WHERE job_id = ?",
                (job_id,),
            ).fetchone()
        return int(row["max_seq"] or 0) + 1

    def _row_to_connection(self, row: sqlite3.Row) -> ConnectionRecord:
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return ConnectionRecord(
            id=row["id"],
            mode=row["mode"],
            label=row["label"],
            status=row["status"],
            data_policy=row["data_policy"],
            metadata=metadata,
            created_at=row["created_at"],
            last_validated_at=row["last_validated_at"],
        )

    def _row_to_job(self, row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            id=row["id"],
            connection_id=row["connection_id"],
            status=JobStatus(row["status"]),
            selected_solver=row["selected_solver"],
            rationale=row["rationale"],
            progress=row["progress"],
            warnings=json.loads(row["warnings_json"]) if row["warnings_json"] else [],
            artifacts=json.loads(row["artifacts_json"]) if row["artifacts_json"] else [],
            metrics=json.loads(row["metrics_json"]) if row["metrics_json"] else {},
            error=row["error"],
            request=json.loads(row["request_json"]),
            source_file_name=row["source_file_name"],
            source_file_path=row["source_file_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_at=row["approved_at"],
            cancelled_at=row["cancelled_at"],
            completed_at=row["completed_at"],
            failed_at=row["failed_at"],
        )

    def _row_to_event(self, row: sqlite3.Row) -> JobEvent:
        return JobEvent(
            id=row["id"],
            job_id=row["job_id"],
            seq=row["seq"],
            event_type=row["event_type"],
            payload=json.loads(row["payload_json"]) if row["payload_json"] else {},
            created_at=row["created_at"],
        )

