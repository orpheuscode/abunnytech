from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any


class RunRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create_run(self, run_id: str | None = None) -> str:
        rid = run_id or str(uuid.uuid4())
        self._conn.execute("INSERT OR IGNORE INTO runs (id) VALUES (?)", (rid,))
        self._conn.commit()
        return rid

    def ensure_run(self, run_id: str) -> None:
        self._conn.execute("INSERT OR IGNORE INTO runs (id) VALUES (?)", (run_id,))
        self._conn.commit()

    def run_exists(self, run_id: str) -> bool:
        row = self._conn.execute("SELECT 1 FROM runs WHERE id = ?", (run_id,)).fetchone()
        return row is not None

    def set_artifact(self, run_id: str, artifact_type: str, payload: Any) -> None:
        self.ensure_run(run_id)
        self._conn.execute(
            """
            INSERT INTO artifacts (run_id, artifact_type, payload_json)
            VALUES (?, ?, ?)
            ON CONFLICT(run_id, artifact_type) DO UPDATE SET
                payload_json = excluded.payload_json,
                updated_at = datetime('now')
            """,
            (run_id, artifact_type, json.dumps(payload, default=str)),
        )
        self._conn.commit()

    def get_artifact(self, run_id: str, artifact_type: str) -> Any | None:
        row = self._conn.execute(
            "SELECT payload_json FROM artifacts WHERE run_id = ? AND artifact_type = ?",
            (run_id, artifact_type),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_json"])

    def list_artifact_types(self, run_id: str) -> list[str]:
        rows = self._conn.execute(
            "SELECT artifact_type FROM artifacts WHERE run_id = ? ORDER BY artifact_type",
            (run_id,),
        ).fetchall()
        return [r["artifact_type"] for r in rows]

    def get_all_artifacts(self, run_id: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for t in self.list_artifact_types(run_id):
            data = self.get_artifact(run_id, t)
            if data is not None:
                out[t] = data
        return out
