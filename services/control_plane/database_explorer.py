"""Read-only helpers for inspecting local SQLite databases used by the demo."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from packages.shared.config import Settings


def _normalize_sqlite_url(url: str) -> Path:
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if url.startswith(prefix):
            return Path(url[len(prefix) :])
    return Path(url)


def state_database_path(settings: Settings) -> Path:
    env_path = (os.getenv("ABUNNYTECH_DB") or "").strip()
    if env_path:
        return Path(env_path)
    return _normalize_sqlite_url(settings.database_url)


def canonical_hackathon_database_path(settings: Settings) -> Path:
    return Path(settings.hackathon_pipeline_db_path)


def _classify_database(path: Path, settings: Settings) -> tuple[str, str]:
    resolved = path.resolve()
    if resolved == state_database_path(settings).resolve():
        return ("state", "state_api")
    if resolved == canonical_hackathon_database_path(settings).resolve():
        return ("hackathon", "canonical_runtime")

    name = path.name.lower()
    if "attempt" in name or "queue" in name:
        return ("hackathon", "queue_discovery")
    if "probe" in name or "instaloader" in name or "partial" in name:
        return ("hackathon", "processing_probe")
    if "e2e" in name or "smoke" in name or "simple_reels" in name:
        return ("hackathon", "e2e_demo")
    return ("hackathon", "other")


def _db_key_for_path(path: Path) -> str:
    slug = path.stem.replace(".", "_").replace("-", "_")
    return f"{slug}_{abs(hash(path.resolve())) & 0xFFFF:x}"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    with _connect(path) as conn:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    return [str(row["name"]) for row in rows]


def _row_count(conn: sqlite3.Connection, table_name: str) -> int:
    row = conn.execute(f'SELECT COUNT(*) AS count FROM "{table_name}"').fetchone()
    return int(row["count"]) if row is not None else 0


def _coerce_json_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _serialize_row(row: sqlite3.Row) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in row.keys():
        payload[str(key)] = _coerce_json_text(row[key])
    return payload


def discover_databases(settings: Settings) -> list[dict[str, Any]]:
    candidates = {
        state_database_path(settings),
        canonical_hackathon_database_path(settings),
    }
    data_dir = Path("data")
    if data_dir.exists():
        candidates.update(data_dir.glob("*.sqlite3"))
        candidates.update(data_dir.glob("*.db"))

    discovered: list[dict[str, Any]] = []
    for path in sorted(candidates, key=lambda item: str(item)):
        group, role = _classify_database(path, settings)
        exists = path.exists()
        tables = _table_names(path) if exists else []
        discovered.append(
            {
                "db_key": _db_key_for_path(path),
                "path": str(path.resolve() if exists else path),
                "filename": path.name,
                "group": group,
                "role": role,
                "exists": exists,
                "size_bytes": path.stat().st_size if exists else 0,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat() if exists else None,
                "tables": tables,
            }
        )
    return discovered


def get_database_detail(
    settings: Settings,
    *,
    db_key: str,
    table: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))
    databases = discover_databases(settings)
    selected = next((item for item in databases if item["db_key"] == db_key), None)
    if selected is None:
        raise KeyError(f"Unknown database key: {db_key}")
    if not selected["exists"]:
        return {**selected, "table_summaries": [], "selected_table": None, "preview": None}

    path = Path(selected["path"])
    table_names = list(selected["tables"])
    with _connect(path) as conn:
        table_summaries = [
            {"name": table_name, "row_count": _row_count(conn, table_name)}
            for table_name in table_names
        ]
        selected_table = table or (table_names[0] if table_names else None)
        preview = None
        if selected_table in table_names:
            columns = conn.execute(f'PRAGMA table_info("{selected_table}")').fetchall()
            total_rows = _row_count(conn, selected_table)
            offset = (page - 1) * page_size
            rows = conn.execute(
                f'SELECT * FROM "{selected_table}" LIMIT ? OFFSET ?',
                (page_size, offset),
            ).fetchall()
            preview = {
                "table": selected_table,
                "columns": [str(column["name"]) for column in columns],
                "page": page,
                "page_size": page_size,
                "total_rows": total_rows,
                "rows": [_serialize_row(row) for row in rows],
            }

    return {
        **selected,
        "table_summaries": table_summaries,
        "selected_table": selected_table,
        "preview": preview,
    }
