from __future__ import annotations

import sqlite3
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends

from pipeline_core.audit import AuditLogger
from pipeline_core.db import get_connection, init_schema
from pipeline_core.repository import RunRepository
from pipeline_core.settings import Settings, get_settings


def _db_conn(settings: Settings) -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection(settings)
    init_schema(conn)
    try:
        yield conn
    finally:
        conn.close()


def get_settings_dep() -> Settings:
    return get_settings()


def get_conn(
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> Generator[sqlite3.Connection, None, None]:
    yield from _db_conn(settings)


def get_repo(conn: Annotated[sqlite3.Connection, Depends(get_conn)]) -> RunRepository:
    return RunRepository(conn)


def get_audit(conn: Annotated[sqlite3.Connection, Depends(get_conn)]) -> AuditLogger:
    return AuditLogger(conn)
