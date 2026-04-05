"""SQLite implementation of the repository layer.

Uses a JSON-document-store pattern: each table has an ``id`` primary key
and a ``data`` TEXT column holding the full Pydantic model as JSON.  This
makes the schema migration-friendly (adding model fields requires no DDL)
and straightforward to swap for Postgres JSONB later.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar
from uuid import UUID

from pydantic import BaseModel

from packages.state.base import Repository

T = TypeVar("T", bound=BaseModel)


class Database:
    """Thin wrapper around a sqlite3 connection with async lifecycle helpers."""

    def __init__(self, path: str | Path = "abunnytech.db") -> None:
        self.path = str(path)
        self._conn: sqlite3.Connection | None = None

    async def connect(self) -> None:
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        if self.path != ":memory:":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.commit()

    async def disconnect(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected – call connect() first")
        return self._conn


class SQLiteRepository(Repository[T]):
    """Generic JSON-document repository backed by a single SQLite table."""

    def __init__(self, db: Database, table: str, model_cls: type[T]) -> None:
        self._db = db
        self._table = table
        self._model = model_cls
        self._ready = False

    async def _execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        cursor = self._db.conn.execute(sql, params)
        return cursor.rowcount

    async def _fetchone(self, sql: str, params: tuple[object, ...] = ()) -> sqlite3.Row | None:
        cursor = self._db.conn.execute(sql, params)
        return cursor.fetchone()

    async def _fetchall(self, sql: str, params: tuple[object, ...] = ()) -> list[sqlite3.Row]:
        cursor = self._db.conn.execute(sql, params)
        return cursor.fetchall()

    async def _commit(self) -> None:
        self._db.conn.commit()

    async def _ensure_table(self) -> None:
        if self._ready:
            return
        await self._execute(
            f"CREATE TABLE IF NOT EXISTS [{self._table}] ("
            "  id TEXT PRIMARY KEY,"
            "  data TEXT NOT NULL,"
            "  created_at TEXT NOT NULL,"
            "  updated_at TEXT NOT NULL"
            ")"
        )
        await self._commit()
        self._ready = True

    # -- reads ---------------------------------------------------------------

    async def get(self, id: UUID) -> T | None:
        await self._ensure_table()
        row = await self._fetchone(f"SELECT data FROM [{self._table}] WHERE id = ?", (str(id),))
        if row is None:
            return None
        return self._model.model_validate_json(row[0])

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[T]:
        await self._ensure_table()
        rows = await self._fetchall(
            f"SELECT data FROM [{self._table}] ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [self._model.model_validate_json(r[0]) for r in rows]

    async def count(self) -> int:
        await self._ensure_table()
        row = await self._fetchone(f"SELECT COUNT(*) FROM [{self._table}]")
        return row[0] if row else 0

    # -- writes --------------------------------------------------------------

    async def create(self, item: T) -> T:
        await self._ensure_table()
        dump = item.model_dump(mode="python")
        now = datetime.now(UTC).isoformat()
        await self._execute(
            f"INSERT INTO [{self._table}] (id, data, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (str(dump["id"]), item.model_dump_json(), now, now),
        )
        await self._commit()
        return item

    async def update(self, id: UUID, item: T) -> T | None:
        await self._ensure_table()
        existing = await self.get(id)
        if existing is None:
            return None
        now = datetime.now(UTC).isoformat()
        await self._execute(
            f"UPDATE [{self._table}] SET data = ?, updated_at = ? WHERE id = ?",
            (item.model_dump_json(), now, str(id)),
        )
        await self._commit()
        return item

    async def delete(self, id: UUID) -> bool:
        await self._ensure_table()
        rowcount = await self._execute(f"DELETE FROM [{self._table}] WHERE id = ?", (str(id),))
        await self._commit()
        return rowcount > 0
