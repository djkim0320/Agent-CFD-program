from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

from aero_agent_contracts import (
    AIAssistMode,
    AnalysisRequest,
    ArtifactRecord,
    ConnectionRecord,
    ExecutionMode,
    JobEventRecord,
    JobRecord,
    JobStatus,
    MetricRecord,
    PreflightSnapshot,
    SnapshotStatus,
)

from .models import utcnow


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
                CREATE TABLE IF NOT EXISTS preflight_snapshots (
                    id TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    source_file_name TEXT NOT NULL,
                    source_file_relpath TEXT NOT NULL,
                    normalized_manifest_relpath TEXT NOT NULL,
                    preflight_plan_relpath TEXT NOT NULL,
                    subagent_findings_relpath TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    normalized_manifest_hash TEXT NOT NULL,
                    selected_solver TEXT NOT NULL,
                    execution_mode TEXT NOT NULL,
                    ai_assist_mode TEXT NOT NULL,
                    runtime_blockers_json TEXT NOT NULL,
                    install_warnings_json TEXT NOT NULL,
                    ai_warnings_json TEXT NOT NULL,
                    policy_warnings_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    consumed_by_job_id TEXT,
                    consumed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    connection_id TEXT NOT NULL,
                    preflight_snapshot_id TEXT,
                    status TEXT NOT NULL,
                    selected_solver TEXT NOT NULL,
                    execution_mode TEXT NOT NULL DEFAULT 'scaffold',
                    ai_assist_mode TEXT NOT NULL DEFAULT 'disabled',
                    rationale TEXT,
                    progress INTEGER NOT NULL,
                    warnings_json TEXT NOT NULL,
                    runtime_blockers_json TEXT NOT NULL DEFAULT '[]',
                    install_warnings_json TEXT NOT NULL DEFAULT '[]',
                    ai_warnings_json TEXT NOT NULL DEFAULT '[]',
                    policy_warnings_json TEXT NOT NULL DEFAULT '[]',
                    artifacts_json TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    error TEXT,
                    request_json TEXT NOT NULL,
                    source_file_name TEXT NOT NULL,
                    source_file_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    approved_at TEXT,
                    queued_at TEXT,
                    started_at TEXT,
                    cancelled_at TEXT,
                    cancel_requested_at TEXT,
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
            self._ensure_job_columns(conn)

    def _ensure_job_columns(self, conn: sqlite3.Connection) -> None:
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        required = {
            "preflight_snapshot_id": "TEXT",
            "execution_mode": "TEXT NOT NULL DEFAULT 'scaffold'",
            "ai_assist_mode": "TEXT NOT NULL DEFAULT 'disabled'",
            "runtime_blockers_json": "TEXT NOT NULL DEFAULT '[]'",
            "install_warnings_json": "TEXT NOT NULL DEFAULT '[]'",
            "ai_warnings_json": "TEXT NOT NULL DEFAULT '[]'",
            "policy_warnings_json": "TEXT NOT NULL DEFAULT '[]'",
            "queued_at": "TEXT",
            "started_at": "TEXT",
            "cancel_requested_at": "TEXT",
        }
        for column, ddl in required.items():
            if column not in existing:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {column} {ddl}")

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

    def create_preflight_snapshot(self, snapshot: PreflightSnapshot) -> PreflightSnapshot:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO preflight_snapshots (
                    id, connection_id, status, source_file_name, source_file_relpath,
                    normalized_manifest_relpath, preflight_plan_relpath, subagent_findings_relpath,
                    request_json, request_digest, source_hash, normalized_manifest_hash,
                    selected_solver, execution_mode, ai_assist_mode, runtime_blockers_json,
                    install_warnings_json, ai_warnings_json, policy_warnings_json,
                    created_at, expires_at, consumed_by_job_id, consumed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.id,
                    snapshot.connection_id,
                    snapshot.status.value,
                    snapshot.source_file_name,
                    snapshot.source_file_relpath,
                    snapshot.normalized_manifest_relpath,
                    snapshot.preflight_plan_relpath,
                    snapshot.subagent_findings_relpath,
                    snapshot.request.model_dump_json(),
                    snapshot.request_digest,
                    snapshot.source_hash,
                    snapshot.normalized_manifest_hash,
                    snapshot.selected_solver.value,
                    snapshot.execution_mode.value,
                    snapshot.ai_assist_mode.value,
                    json.dumps(snapshot.runtime_blockers),
                    json.dumps(snapshot.install_warnings),
                    json.dumps(snapshot.ai_warnings),
                    json.dumps(snapshot.policy_warnings),
                    snapshot.created_at.isoformat(),
                    snapshot.expires_at.isoformat(),
                    snapshot.consumed_by_job_id,
                    snapshot.consumed_at.isoformat() if snapshot.consumed_at else None,
                ),
            )
        return snapshot

    def get_preflight_snapshot(self, snapshot_id: str) -> PreflightSnapshot | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM preflight_snapshots WHERE id = ?", (snapshot_id,)).fetchone()
        return self._row_to_snapshot(row) if row else None

    def update_preflight_snapshot(self, snapshot: PreflightSnapshot) -> PreflightSnapshot:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE preflight_snapshots SET
                    connection_id=?,
                    status=?,
                    source_file_name=?,
                    source_file_relpath=?,
                    normalized_manifest_relpath=?,
                    preflight_plan_relpath=?,
                    subagent_findings_relpath=?,
                    request_json=?,
                    request_digest=?,
                    source_hash=?,
                    normalized_manifest_hash=?,
                    selected_solver=?,
                    execution_mode=?,
                    ai_assist_mode=?,
                    runtime_blockers_json=?,
                    install_warnings_json=?,
                    ai_warnings_json=?,
                    policy_warnings_json=?,
                    created_at=?,
                    expires_at=?,
                    consumed_by_job_id=?,
                    consumed_at=?
                WHERE id=?
                """,
                (
                    snapshot.connection_id,
                    snapshot.status.value,
                    snapshot.source_file_name,
                    snapshot.source_file_relpath,
                    snapshot.normalized_manifest_relpath,
                    snapshot.preflight_plan_relpath,
                    snapshot.subagent_findings_relpath,
                    snapshot.request.model_dump_json(),
                    snapshot.request_digest,
                    snapshot.source_hash,
                    snapshot.normalized_manifest_hash,
                    snapshot.selected_solver.value,
                    snapshot.execution_mode.value,
                    snapshot.ai_assist_mode.value,
                    json.dumps(snapshot.runtime_blockers),
                    json.dumps(snapshot.install_warnings),
                    json.dumps(snapshot.ai_warnings),
                    json.dumps(snapshot.policy_warnings),
                    snapshot.created_at.isoformat(),
                    snapshot.expires_at.isoformat(),
                    snapshot.consumed_by_job_id,
                    snapshot.consumed_at.isoformat() if snapshot.consumed_at else None,
                    snapshot.id,
                ),
            )
        return snapshot

    def list_expired_snapshot_ids(self, now: datetime) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id FROM preflight_snapshots
                WHERE status != 'consumed' AND expires_at <= ?
                """,
                (now.isoformat(),),
            ).fetchall()
        return [str(row["id"]) for row in rows]

    def delete_snapshot(self, snapshot_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM preflight_snapshots WHERE id = ?", (snapshot_id,))

    def create_job(self, job: JobRecord) -> JobRecord:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, connection_id, preflight_snapshot_id, status, selected_solver, execution_mode,
                    ai_assist_mode, rationale, progress, warnings_json, runtime_blockers_json,
                    install_warnings_json, ai_warnings_json, policy_warnings_json,
                    artifacts_json, metrics_json, error, request_json,
                    source_file_name, source_file_path, created_at, updated_at,
                    approved_at, queued_at, started_at, cancelled_at, cancel_requested_at,
                    completed_at, failed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._job_params(job),
            )
        return job

    def update_job(self, job: JobRecord) -> JobRecord:
        job.updated_at = utcnow()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE jobs SET
                    connection_id=?,
                    preflight_snapshot_id=?,
                    status=?,
                    selected_solver=?,
                    execution_mode=?,
                    ai_assist_mode=?,
                    rationale=?,
                    progress=?,
                    warnings_json=?,
                    runtime_blockers_json=?,
                    install_warnings_json=?,
                    ai_warnings_json=?,
                    policy_warnings_json=?,
                    artifacts_json=?,
                    metrics_json=?,
                    error=?,
                    request_json=?,
                    source_file_name=?,
                    source_file_path=?,
                    created_at=?,
                    updated_at=?,
                    approved_at=?,
                    queued_at=?,
                    started_at=?,
                    cancelled_at=?,
                    cancel_requested_at=?,
                    completed_at=?,
                    failed_at=?
                WHERE id=?
                """,
                self._job_params(job, include_id=True),
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

    def add_event(self, event: JobEventRecord) -> JobEventRecord:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO job_events (job_id, seq, event_type, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.job_id,
                    event.seq,
                    str(event.event_type),
                    json.dumps(event.payload),
                    event.created_at.isoformat(),
                ),
            )
            event.id = cursor.lastrowid
        return event

    def list_events(self, job_id: str) -> list[JobEventRecord]:
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

    def _job_params(self, job: JobRecord, *, include_id: bool = False) -> tuple[object, ...]:
        payload = (
            job.connection_id,
            job.preflight_snapshot_id,
            job.status.value,
            job.selected_solver.value,
            job.execution_mode.value,
            job.ai_assist_mode.value,
            job.rationale,
            job.progress,
            json.dumps(job.warnings),
            json.dumps(job.runtime_blockers),
            json.dumps(job.install_warnings),
            json.dumps(job.ai_warnings),
            json.dumps(job.policy_warnings),
            json.dumps([artifact.model_dump(mode="json") for artifact in job.artifacts]),
            json.dumps([metric.model_dump(mode="json") for metric in job.metrics]),
            job.error,
            job.request.model_dump_json(),
            job.source_file_name,
            job.source_file_path,
            job.created_at.isoformat(),
            job.updated_at.isoformat(),
            job.approved_at.isoformat() if job.approved_at else None,
            job.queued_at.isoformat() if job.queued_at else None,
            job.started_at.isoformat() if job.started_at else None,
            job.cancelled_at.isoformat() if job.cancelled_at else None,
            job.cancel_requested_at.isoformat() if job.cancel_requested_at else None,
            job.completed_at.isoformat() if job.completed_at else None,
            job.failed_at.isoformat() if job.failed_at else None,
        )
        if include_id:
            return payload + (job.id,)
        return (job.id,) + payload

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

    def _row_to_snapshot(self, row: sqlite3.Row) -> PreflightSnapshot:
        return PreflightSnapshot(
            id=row["id"],
            connection_id=row["connection_id"],
            status=SnapshotStatus(row["status"]),
            source_file_name=row["source_file_name"],
            source_file_relpath=row["source_file_relpath"],
            normalized_manifest_relpath=row["normalized_manifest_relpath"],
            preflight_plan_relpath=row["preflight_plan_relpath"],
            subagent_findings_relpath=row["subagent_findings_relpath"],
            request=AnalysisRequest.model_validate_json(row["request_json"]),
            request_digest=row["request_digest"],
            source_hash=row["source_hash"],
            normalized_manifest_hash=row["normalized_manifest_hash"],
            selected_solver=row["selected_solver"],
            execution_mode=ExecutionMode(row["execution_mode"]),
            ai_assist_mode=AIAssistMode(row["ai_assist_mode"]),
            runtime_blockers=json.loads(row["runtime_blockers_json"]) if row["runtime_blockers_json"] else [],
            install_warnings=json.loads(row["install_warnings_json"]) if row["install_warnings_json"] else [],
            ai_warnings=json.loads(row["ai_warnings_json"]) if row["ai_warnings_json"] else [],
            policy_warnings=json.loads(row["policy_warnings_json"]) if row["policy_warnings_json"] else [],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            consumed_by_job_id=row["consumed_by_job_id"],
            consumed_at=row["consumed_at"],
        )

    def _row_to_job(self, row: sqlite3.Row) -> JobRecord:
        artifacts_payload = json.loads(row["artifacts_json"]) if row["artifacts_json"] else []
        metrics_payload = json.loads(row["metrics_json"]) if row["metrics_json"] else []
        return JobRecord(
            id=row["id"],
            connection_id=row["connection_id"],
            preflight_snapshot_id=row["preflight_snapshot_id"] or "",
            status=JobStatus(row["status"]),
            selected_solver=row["selected_solver"],
            execution_mode=ExecutionMode(row["execution_mode"] or "scaffold"),
            ai_assist_mode=AIAssistMode(row["ai_assist_mode"] or "disabled"),
            rationale=row["rationale"],
            progress=row["progress"],
            warnings=json.loads(row["warnings_json"]) if row["warnings_json"] else [],
            runtime_blockers=json.loads(row["runtime_blockers_json"]) if row["runtime_blockers_json"] else [],
            install_warnings=json.loads(row["install_warnings_json"]) if row["install_warnings_json"] else [],
            ai_warnings=json.loads(row["ai_warnings_json"]) if row["ai_warnings_json"] else [],
            policy_warnings=json.loads(row["policy_warnings_json"]) if row["policy_warnings_json"] else [],
            artifacts=[ArtifactRecord.model_validate(item) for item in artifacts_payload],
            metrics=[MetricRecord.model_validate(item) for item in metrics_payload],
            error=row["error"],
            request=AnalysisRequest.model_validate_json(row["request_json"]),
            source_file_name=row["source_file_name"],
            source_file_path=row["source_file_path"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_at=row["approved_at"],
            queued_at=row["queued_at"],
            started_at=row["started_at"],
            cancelled_at=row["cancelled_at"],
            cancel_requested_at=row["cancel_requested_at"],
            completed_at=row["completed_at"],
            failed_at=row["failed_at"],
        )

    def _row_to_event(self, row: sqlite3.Row) -> JobEventRecord:
        return JobEventRecord(
            id=row["id"],
            job_id=row["job_id"],
            seq=row["seq"],
            event_type=row["event_type"],
            payload=json.loads(row["payload_json"]) if row["payload_json"] else {},
            created_at=row["created_at"],
        )
