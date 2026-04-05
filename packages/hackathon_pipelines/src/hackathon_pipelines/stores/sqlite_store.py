"""SQLite-backed persistence for the hackathon pipeline stores."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import BaseModel

from hackathon_pipelines.contracts import (
    PostAnalyticsSnapshot,
    ProductCandidate,
    ReelSurfaceMetrics,
    VideoStructureRecord,
    VideoTemplateRecord,
)
from hackathon_pipelines.ports import (
    AnalyticsSinkPort,
    ProductCatalogPort,
    ReelMetadataSinkPort,
    TemplateStorePort,
)
from hackathon_pipelines.scoring import rank_products


def _dump(model: BaseModel) -> str:
    return model.model_dump_json()


def _load[TModel: BaseModel](model_type: type[TModel], payload: str) -> TModel:
    return model_type.model_validate_json(payload)


class SQLiteHackathonStore:
    """SQLite-backed storage for all hackathon pipeline entities."""

    def __init__(self, db_path: str | Path = "data/hackathon_pipelines.sqlite3") -> None:
        self.db_path = Path(db_path)
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_schema(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS reel_metrics (
                reel_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS video_structures (
                record_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS video_templates (
                template_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS product_candidates (
                product_id TEXT PRIMARY KEY,
                dropship_score REAL NOT NULL,
                payload TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS analytics_snapshots (
                snapshot_id TEXT PRIMARY KEY,
                payload TEXT NOT NULL
            )
            """,
        )
        with self._connect() as conn:
            for stmt in statements:
                conn.execute(stmt)

    def _upsert_json(self, table: str, key_column: str, key_value: str, payload: str) -> None:
        sql = (
            f"INSERT INTO {table} ({key_column}, payload) VALUES (?, ?) "
            f"ON CONFLICT({key_column}) DO UPDATE SET payload = excluded.payload"
        )
        with self._connect() as conn:
            conn.execute(sql, (key_value, payload))

    def _fetch_one(self, table: str, key_column: str, key_value: str) -> str | None:
        sql = f"SELECT payload FROM {table} WHERE {key_column} = ?"
        with self._connect() as conn:
            row = conn.execute(sql, (key_value,)).fetchone()
        return None if row is None else str(row["payload"])

    def _fetch_all(self, table: str, order_by: str) -> list[str]:
        sql = f"SELECT payload FROM {table} ORDER BY {order_by}"
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()
        return [str(row["payload"]) for row in rows]

    # Reel metrics
    def upsert_reel_metrics(self, metrics: list[ReelSurfaceMetrics]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO reel_metrics (reel_id, payload) VALUES (?, ?)
                ON CONFLICT(reel_id) DO UPDATE SET payload = excluded.payload
                """,
                [(metric.reel_id, _dump(metric)) for metric in metrics],
            )

    def list_reel_metrics(self) -> list[ReelSurfaceMetrics]:
        return [_load(ReelSurfaceMetrics, payload) for payload in self._fetch_all("reel_metrics", "reel_id ASC")]

    def get_reel_metric(self, reel_id: str) -> ReelSurfaceMetrics | None:
        payload = self._fetch_one("reel_metrics", "reel_id", reel_id)
        return None if payload is None else _load(ReelSurfaceMetrics, payload)

    # Video structures
    def save_structure(self, record: VideoStructureRecord) -> None:
        self._upsert_json("video_structures", "record_id", record.record_id, _dump(record))

    def list_structures(self) -> list[VideoStructureRecord]:
        return [
            _load(VideoStructureRecord, payload)
            for payload in self._fetch_all("video_structures", "record_id ASC")
        ]

    def get_structure(self, record_id: str) -> VideoStructureRecord | None:
        payload = self._fetch_one("video_structures", "record_id", record_id)
        return None if payload is None else _load(VideoStructureRecord, payload)

    # Templates
    def save_template(self, record: VideoTemplateRecord) -> None:
        self._upsert_json("video_templates", "template_id", record.template_id, _dump(record))

    def list_templates(self) -> list[VideoTemplateRecord]:
        return [
            _load(VideoTemplateRecord, payload)
            for payload in self._fetch_all("video_templates", "template_id ASC")
        ]

    def get_template(self, template_id: str) -> VideoTemplateRecord | None:
        payload = self._fetch_one("video_templates", "template_id", template_id)
        return None if payload is None else _load(VideoTemplateRecord, payload)

    def update_template(self, record: VideoTemplateRecord) -> None:
        self.save_template(record)

    # Product catalog
    def upsert_candidates(self, candidates: list[ProductCandidate]) -> None:
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO product_candidates (product_id, dropship_score, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(product_id) DO UPDATE SET
                    dropship_score = excluded.dropship_score,
                    payload = excluded.payload
                """,
                [(candidate.product_id, float(candidate.dropship_score), _dump(candidate)) for candidate in candidates],
            )

    def list_candidates(self) -> list[ProductCandidate]:
        return [_load(ProductCandidate, payload) for payload in self._fetch_all("product_candidates", "product_id ASC")]

    def get_candidate(self, product_id: str) -> ProductCandidate | None:
        payload = self._fetch_one("product_candidates", "product_id", product_id)
        return None if payload is None else _load(ProductCandidate, payload)

    def top_candidates(self, *, limit: int = 5) -> list[ProductCandidate]:
        ranked = rank_products(self.list_candidates(), limit=limit)
        return ranked

    # Analytics snapshots
    def persist_post_analytics(self, snapshot: PostAnalyticsSnapshot) -> None:
        self._upsert_json("analytics_snapshots", "snapshot_id", snapshot.snapshot_id, _dump(snapshot))

    def list_snapshots(self) -> list[PostAnalyticsSnapshot]:
        return [
            _load(PostAnalyticsSnapshot, payload)
            for payload in self._fetch_all("analytics_snapshots", "snapshot_id ASC")
        ]

    def get_snapshot(self, snapshot_id: str) -> PostAnalyticsSnapshot | None:
        payload = self._fetch_one("analytics_snapshots", "snapshot_id", snapshot_id)
        return None if payload is None else _load(PostAnalyticsSnapshot, payload)


class SQLiteReelSink(ReelMetadataSinkPort):
    def __init__(
        self,
        db_path: str | Path = "data/hackathon_pipelines.sqlite3",
        *,
        store: SQLiteHackathonStore | None = None,
    ) -> None:
        self._store = store or SQLiteHackathonStore(db_path)

    def persist_reel_metrics(self, metrics: list[ReelSurfaceMetrics]) -> None:
        self._store.upsert_reel_metrics(metrics)


class SQLiteTemplateStore(TemplateStorePort):
    def __init__(
        self,
        db_path: str | Path = "data/hackathon_pipelines.sqlite3",
        *,
        store: SQLiteHackathonStore | None = None,
    ) -> None:
        self._store = store or SQLiteHackathonStore(db_path)

    def save_structure(self, record: VideoStructureRecord) -> None:
        self._store.save_structure(record)

    def save_template(self, record: VideoTemplateRecord) -> None:
        self._store.save_template(record)

    def list_templates(self) -> list[VideoTemplateRecord]:
        return self._store.list_templates()

    def get_template(self, template_id: str) -> VideoTemplateRecord | None:
        return self._store.get_template(template_id)

    def update_template(self, record: VideoTemplateRecord) -> None:
        self._store.update_template(record)


class SQLiteProductCatalog(ProductCatalogPort):
    def __init__(
        self,
        db_path: str | Path = "data/hackathon_pipelines.sqlite3",
        *,
        store: SQLiteHackathonStore | None = None,
    ) -> None:
        self._store = store or SQLiteHackathonStore(db_path)

    def upsert_candidates(self, candidates: list[ProductCandidate]) -> None:
        self._store.upsert_candidates(candidates)

    def top_by_score(self, *, limit: int = 5) -> list[ProductCandidate]:
        return self._store.top_candidates(limit=limit)


class SQLiteAnalyticsSink(AnalyticsSinkPort):
    def __init__(
        self,
        db_path: str | Path = "data/hackathon_pipelines.sqlite3",
        *,
        store: SQLiteHackathonStore | None = None,
    ) -> None:
        self._store = store or SQLiteHackathonStore(db_path)

    def persist_post_analytics(self, snapshot: PostAnalyticsSnapshot) -> None:
        self._store.persist_post_analytics(snapshot)
