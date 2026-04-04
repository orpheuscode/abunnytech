"""
SQLite-backed state adapter for Stage 4.

Persists:
  - PerformanceMetricRecords
  - OptimizationDirectiveEnvelopes
  - RedoQueueItems
  - BaselineSnapshots

The schema is deliberately simple — all contract types are stored as JSON
blobs so schema migrations don't block hackathon iteration. Only index
columns used in WHERE clauses are stored as first-class columns.

Adapter-friendly: swap out the engine by subclassing StateAdapter and
overriding the four read/write pairs. The runner only calls the public API.
"""
from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from .contracts import (
    OptimizationDirectiveEnvelope,
    PerformanceMetricRecord,
    RedoQueueItem,
)
from .models import BaselineSnapshot

DEFAULT_DB_PATH = "./data/stage4_analytics.db"


class StateAdapter:
    """
    Thread-safe SQLite state adapter for Stage 4.

    Usage:
        adapter = StateAdapter()
        adapter.save_metric(record)
        records = adapter.load_metrics(platform="tiktok", since=..., until=...)
    """

    def __init__(self, db_path: str = DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS performance_metrics (
                    record_id TEXT PRIMARY KEY,
                    distribution_record_id TEXT NOT NULL,
                    post_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    blob TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_pm_platform
                    ON performance_metrics (platform);
                CREATE INDEX IF NOT EXISTS idx_pm_recorded_at
                    ON performance_metrics (recorded_at);

                CREATE TABLE IF NOT EXISTS directives (
                    envelope_id TEXT PRIMARY KEY,
                    directive_type TEXT NOT NULL,
                    target_stage TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    generated_at TEXT NOT NULL,
                    blob TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS redo_queue (
                    item_id TEXT PRIMARY KEY,
                    source_distribution_record_id TEXT NOT NULL,
                    redo_reason TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'queued',
                    queued_at TEXT NOT NULL,
                    blob TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_rq_status
                    ON redo_queue (status);

                CREATE TABLE IF NOT EXISTS baselines (
                    platform TEXT NOT NULL,
                    niche TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    blob TEXT NOT NULL,
                    PRIMARY KEY (platform, niche)
                );
            """)

    # ------------------------------------------------------------------
    # PerformanceMetricRecord
    # ------------------------------------------------------------------

    def save_metric(self, record: PerformanceMetricRecord) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO performance_metrics
                   (record_id, distribution_record_id, post_id, platform, recorded_at, blob)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    record.record_id,
                    record.distribution_record_id,
                    record.post_id,
                    record.platform,
                    record.recorded_at.isoformat(),
                    record.model_dump_json(),
                ),
            )

    def save_metrics(self, records: list[PerformanceMetricRecord]) -> None:
        for r in records:
            self.save_metric(r)

    def load_metrics(
        self,
        platform: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> list[PerformanceMetricRecord]:
        clauses: list[str] = []
        params: list[Any] = []
        if platform:
            clauses.append("platform = ?")
            params.append(platform)
        if since:
            clauses.append("recorded_at >= ?")
            params.append(since.isoformat())
        if until:
            clauses.append("recorded_at <= ?")
            params.append(until.isoformat())
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT blob FROM performance_metrics {where} ORDER BY recorded_at DESC",
                params,
            ).fetchall()
        return [PerformanceMetricRecord.model_validate_json(row["blob"]) for row in rows]

    # ------------------------------------------------------------------
    # OptimizationDirectiveEnvelope
    # ------------------------------------------------------------------

    def save_directive(self, directive: OptimizationDirectiveEnvelope) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO directives
                   (envelope_id, directive_type, target_stage, priority, generated_at, blob)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    directive.envelope_id,
                    directive.directive_type,
                    directive.target_stage,
                    directive.priority,
                    directive.generated_at.isoformat(),
                    directive.model_dump_json(),
                ),
            )

    def save_directives(self, directives: list[OptimizationDirectiveEnvelope]) -> None:
        for d in directives:
            self.save_directive(d)

    def load_directives(
        self,
        target_stage: str | None = None,
        since: datetime | None = None,
    ) -> list[OptimizationDirectiveEnvelope]:
        clauses: list[str] = []
        params: list[Any] = []
        if target_stage:
            clauses.append("target_stage = ?")
            params.append(target_stage)
        if since:
            clauses.append("generated_at >= ?")
            params.append(since.isoformat())
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT blob FROM directives {where} ORDER BY generated_at DESC",
                params,
            ).fetchall()
        return [OptimizationDirectiveEnvelope.model_validate_json(row["blob"]) for row in rows]

    # ------------------------------------------------------------------
    # RedoQueueItem
    # ------------------------------------------------------------------

    def save_redo_item(self, item: RedoQueueItem) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO redo_queue
                   (item_id, source_distribution_record_id, redo_reason,
                    priority, status, queued_at, blob)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.item_id,
                    item.source_distribution_record_id,
                    item.redo_reason,
                    item.priority,
                    item.status,
                    item.queued_at.isoformat(),
                    item.model_dump_json(),
                ),
            )

    def save_redo_items(self, items: list[RedoQueueItem]) -> None:
        for i in items:
            self.save_redo_item(i)

    def load_redo_queue(
        self,
        status: str | None = "queued",
    ) -> list[RedoQueueItem]:
        clauses: list[str] = []
        params: list[Any] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT blob FROM redo_queue {where} ORDER BY priority, queued_at",
                params,
            ).fetchall()
        return [RedoQueueItem.model_validate_json(row["blob"]) for row in rows]

    def mark_redo_done(self, item_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE redo_queue SET status = 'done' WHERE item_id = ?",
                (item_id,),
            )

    # ------------------------------------------------------------------
    # BaselineSnapshot
    # ------------------------------------------------------------------

    def save_baseline(self, snapshot: BaselineSnapshot) -> None:
        blob = json.dumps(snapshot.__dict__)
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO baselines (platform, niche, updated_at, blob)
                   VALUES (?, ?, ?, ?)""",
                (snapshot.platform, snapshot.niche, snapshot.updated_at, blob),
            )

    def load_baseline(self, platform: str, niche: str = "general") -> BaselineSnapshot | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT blob FROM baselines WHERE platform = ? AND niche = ?",
                (platform, niche),
            ).fetchone()
        if not row:
            return None
        data = json.loads(row["blob"])
        return BaselineSnapshot(**data)
