from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import sqlite3


class AuditLogger:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def log(self, run_id: str, stage: str, action: str, details: dict[str, Any]) -> None:
        payload = {
            **details,
            "logged_at": datetime.now(UTC).isoformat(),
        }
        self._conn.execute(
            "INSERT INTO audit_log (run_id, stage, action, details_json) VALUES (?, ?, ?, ?)",
            (run_id, stage, action, json.dumps(payload, default=str)),
        )
        self._conn.commit()
