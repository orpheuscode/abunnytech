"""SQLite implementation of the repository layer using aiosqlite.

Uses a JSON-document-store pattern: each table has an ``id`` primary key
and a ``data`` TEXT column holding the full Pydantic model as JSON.  This
makes the schema migration-friendly (adding model fields requires no DDL)
and straightforward to swap for Postgres JSONB later.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar
from uuid import UUID

import aiosqlite
from pydantic import BaseModel

from packages.state.base import Repository

T = TypeVar("T", bound=BaseModel)


class Database:
    """Thin wrapper around an aiosqlite connection with lifecycle helpers."""

    def __init__(self, path: str | Path = "abunnytech.db") -> None:
        self.path = str(path)
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

    async def disconnect(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
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

    async def _ensure_table(self) -> None:
        if self._ready:
            return
        await self._db.conn.execute(
            f"CREATE TABLE IF NOT EXISTS [{self._table}] ("
            "  id TEXT PRIMARY KEY,"
            "  data TEXT NOT NULL,"
            "  created_at TEXT NOT NULL,"
            "  updated_at TEXT NOT NULL"
            ")"
        )
        await self._db.conn.commit()
        self._ready = True

    # -- reads ---------------------------------------------------------------

    async def get(self, id: UUID) -> T | None:
        await self._ensure_table()
        async with self._db.conn.execute(
            f"SELECT data FROM [{self._table}] WHERE id = ?", (str(id),)
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return self._model.model_validate_json(row[0])

    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[T]:
        await self._ensure_table()
        async with self._db.conn.execute(
            f"SELECT data FROM [{self._table}] ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        return [self._model.model_validate_json(r[0]) for r in rows]

    async def count(self) -> int:
        await self._ensure_table()
        async with self._db.conn.execute(
            f"SELECT COUNT(*) FROM [{self._table}]"
        ) as cur:
            row = await cur.fetchone()
        return row[0] if row else 0

    # -- writes --------------------------------------------------------------

    async def create(self, item: T) -> T:
        await self._ensure_table()
        dump = item.model_dump(mode="python")
        now = datetime.now(UTC).isoformat()
        await self._db.conn.execute(
            f"INSERT INTO [{self._table}] (id, data, created_at, updated_at) "
            "VALUES (?, ?, ?, ?)",
            (str(dump["id"]), item.model_dump_json(), now, now),
        )
        await self._db.conn.commit()
        return item

    async def update(self, id: UUID, item: T) -> T | None:
        await self._ensure_table()
        existing = await self.get(id)
        if existing is None:
            return None
        now = datetime.now(UTC).isoformat()
        await self._db.conn.execute(
            f"UPDATE [{self._table}] SET data = ?, updated_at = ? WHERE id = ?",
            (item.model_dump_json(), now, str(id)),
        )
        await self._db.conn.commit()
        return item

    async def delete(self, id: UUID) -> bool:
        await self._ensure_table()
        cur = await self._db.conn.execute(
            f"DELETE FROM [{self._table}] WHERE id = ?", (str(id),)
        )
        await self._db.conn.commit()
        return cur.rowcount > 0
