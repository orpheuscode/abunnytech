"""
Stage3Store — SQLite persistence for DistributionRecord and DMConversationRecord.

Schema is intentionally simple: two tables with JSON blobs for the full record
plus a few indexed columns for common queries. This lets Stage 4 do fast
lookups by platform/package/date while keeping the schema migration-friendly.

To swap in Supabase/Postgres later, replace _connect() with a psycopg2/asyncpg
adapter — the public API stays identical.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .contracts import (
    DistributionRecord,
    DistributionStatus,
    DMConversationRecord,
    Platform,
)

_CREATE_DISTRIBUTION = """
CREATE TABLE IF NOT EXISTS distribution_records (
    record_id     TEXT PRIMARY KEY,
    package_id    TEXT NOT NULL,
    identity_id   TEXT,
    platform      TEXT NOT NULL,
    status        TEXT NOT NULL,
    dry_run       INTEGER NOT NULL DEFAULT 1,
    posted_at     TEXT,
    created_at    TEXT NOT NULL,
    data          TEXT NOT NULL   -- full JSON blob
);
CREATE INDEX IF NOT EXISTS idx_dist_package  ON distribution_records(package_id);
CREATE INDEX IF NOT EXISTS idx_dist_platform ON distribution_records(platform);
CREATE INDEX IF NOT EXISTS idx_dist_posted   ON distribution_records(posted_at);
"""

_CREATE_DM = """
CREATE TABLE IF NOT EXISTS dm_conversations (
    conv_id        TEXT PRIMARY KEY,
    platform       TEXT NOT NULL,
    post_id        TEXT NOT NULL,
    user_id        TEXT NOT NULL,
    fsm_state      TEXT NOT NULL,
    dry_run        INTEGER NOT NULL DEFAULT 1,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    data           TEXT NOT NULL   -- full JSON blob
);
CREATE INDEX IF NOT EXISTS idx_dm_platform  ON dm_conversations(platform);
CREATE INDEX IF NOT EXISTS idx_dm_user      ON dm_conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_dm_state     ON dm_conversations(fsm_state);
"""


class Stage3Store:
    """
    Synchronous SQLite store for Stage 3 output records.

    Thread safety: SQLite in WAL mode with check_same_thread=False is safe for
    multi-threaded reads; writes are serialised by the GIL and SQLite's own
    locking. For async contexts, run in an executor thread via asyncio.to_thread.
    """

    def __init__(self, db_path: str = "./db/stage3.db") -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_CREATE_DISTRIBUTION)
            conn.executescript(_CREATE_DM)

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(str(self._path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # DistributionRecord
    # ------------------------------------------------------------------

    def save_distribution_record(self, record: DistributionRecord) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO distribution_records
                    (record_id, package_id, identity_id, platform, status,
                     dry_run, posted_at, created_at, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.record_id,
                    record.package_id,
                    record.identity_id,
                    record.platform.value,
                    record.status.value,
                    int(record.dry_run),
                    record.posted_at.isoformat() if record.posted_at else None,
                    record.created_at.isoformat(),
                    record.model_dump_json(),
                ),
            )

    def get_distribution_record(self, record_id: str) -> DistributionRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM distribution_records WHERE record_id = ?",
                (record_id,),
            ).fetchone()
        if row is None:
            return None
        return DistributionRecord.model_validate_json(row["data"])

    def list_distribution_records(
        self,
        platform: Platform | None = None,
        package_id: str | None = None,
        status: DistributionStatus | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[DistributionRecord]:
        clauses: list[str] = []
        params: list[str | int] = []

        if platform is not None:
            clauses.append("platform = ?")
            params.append(platform.value)
        if package_id is not None:
            clauses.append("package_id = ?")
            params.append(package_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status.value)
        if since is not None:
            clauses.append("created_at >= ?")
            params.append(since.isoformat())

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT data FROM distribution_records {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [DistributionRecord.model_validate_json(row["data"]) for row in rows]

    # ------------------------------------------------------------------
    # DMConversationRecord
    # ------------------------------------------------------------------

    def save_dm_conversation(self, record: DMConversationRecord) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO dm_conversations
                    (conv_id, platform, post_id, user_id, fsm_state,
                     dry_run, created_at, updated_at, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.conv_id,
                    record.platform.value,
                    record.post_id,
                    record.user_id,
                    record.fsm_state.value,
                    int(record.dry_run),
                    record.created_at.isoformat(),
                    record.updated_at.isoformat(),
                    record.model_dump_json(),
                ),
            )

    def get_dm_conversation(self, conv_id: str) -> DMConversationRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM dm_conversations WHERE conv_id = ?",
                (conv_id,),
            ).fetchone()
        if row is None:
            return None
        return DMConversationRecord.model_validate_json(row["data"])

    def list_dm_conversations(
        self,
        platform: Platform | None = None,
        user_id: str | None = None,
        fsm_state: str | None = None,
        limit: int = 100,
    ) -> list[DMConversationRecord]:
        clauses: list[str] = []
        params: list[str | int] = []

        if platform is not None:
            clauses.append("platform = ?")
            params.append(platform.value)
        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)
        if fsm_state is not None:
            clauses.append("fsm_state = ?")
            params.append(fsm_state)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(
                f"SELECT data FROM dm_conversations {where} ORDER BY updated_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [DMConversationRecord.model_validate_json(row["data"]) for row in rows]
