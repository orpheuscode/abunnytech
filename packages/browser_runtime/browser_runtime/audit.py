"""
Structured audit logger.

Every provider call and adapter operation writes a JSON line to the audit log.
Consumers can also call audit() directly to record stage-level events.

Log format (JSONL):
  {"ts": "...", "event": "...", "level": "INFO", "data": {...}}
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("browser_runtime.audit")


class AuditLogger:
    """
    Thread-safe JSONL audit logger.

    Usage:
        audit = AuditLogger("./logs/audit.jsonl")
        audit.log("provider.call", {"provider": "mock", "task_id": "..."})
        audit.log("adapter.post", {"platform": "tiktok", "dry_run": True}, level="WARNING")
    """

    def __init__(self, log_path: str = "./logs/browser_runtime_audit.jsonl") -> None:
        self._path = Path(log_path)
        self._lock = threading.Lock()
        self._ensure_dir()

    def _ensure_dir(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        event: str,
        data: dict[str, Any] | None = None,
        level: str = "INFO",
    ) -> None:
        record = {
            "ts": datetime.now(UTC).isoformat(),
            "event": event,
            "level": level,
            "data": data or {},
        }
        line = json.dumps(record, default=str)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        # Also emit to stdlib logger so pytest/stdout captures it
        log_fn = getattr(logger, level.lower(), logger.info)
        log_fn("[audit] %s %s", event, json.dumps(data or {}, default=str))

    def log_request(
        self,
        provider_or_adapter: str,
        operation: str,
        request_id: str,
        dry_run: bool,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.log(
            f"{provider_or_adapter}.{operation}.start",
            {"request_id": request_id, "dry_run": dry_run, **(extra or {})},
        )

    def log_result(
        self,
        provider_or_adapter: str,
        operation: str,
        request_id: str,
        success: bool,
        dry_run: bool,
        extra: dict[str, Any] | None = None,
    ) -> None:
        level = "INFO" if success else "ERROR"
        self.log(
            f"{provider_or_adapter}.{operation}.end",
            {"request_id": request_id, "success": success, "dry_run": dry_run, **(extra or {})},
            level=level,
        )

    def tail(self, n: int = 20) -> list[dict[str, Any]]:
        """Return the last n log entries (for dashboard/debug use)."""
        if not self._path.exists():
            return []
        lines = self._path.read_text(encoding="utf-8").strip().splitlines()
        return [json.loads(line) for line in lines[-n:]]


# Module-level singleton
_audit: AuditLogger | None = None


def get_audit(log_path: str | None = None) -> AuditLogger:
    global _audit
    if _audit is None:
        from .config import get_settings
        path = log_path or get_settings().audit_log_path
        _audit = AuditLogger(path)
    return _audit


def override_audit(audit: AuditLogger) -> None:
    """Replace the singleton — intended for tests."""
    global _audit
    _audit = audit
