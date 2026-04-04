"""SQLite database layer with async SQLAlchemy. Adapter-friendly for Supabase/Postgres later."""

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Column, DateTime, String, Text, create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from packages.shared.config import get_settings


class Base(DeclarativeBase):
    pass


class PipelineRecord(Base):
    __tablename__ = "pipeline_records"

    id = Column(String, primary_key=True)
    contract_type = Column(String, nullable=False, index=True)
    stage = Column(String, nullable=False, index=True)
    identity_id = Column(String, index=True)
    data = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(UTC))
    stage = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    actor = Column(String, default="system")
    details = Column(Text, default="{}")


def _json_serializer(obj: Any) -> str:
    if isinstance(obj, (datetime, UUID)):
        return str(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


_async_engine = None
_async_session_factory = None


async def get_async_engine():
    global _async_engine
    if _async_engine is None:
        settings = get_settings()
        _async_engine = create_async_engine(settings.database_url, echo=False)
    return _async_engine


async def get_async_session() -> AsyncSession:
    global _async_session_factory
    if _async_session_factory is None:
        engine = await get_async_engine()
        _async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return _async_session_factory()


async def init_db():
    engine = await get_async_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def get_sync_engine():
    settings = get_settings()
    sync_url = settings.database_url.replace("+aiosqlite", "")
    return create_engine(sync_url, echo=False)


def init_db_sync():
    engine = get_sync_engine()
    Base.metadata.create_all(engine)


async def store_record(
    contract_type: str,
    stage: str,
    data: dict[str, Any],
    identity_id: str = "",
) -> str:
    record_id = data.get("id", str(UUID(int=0)))
    record = PipelineRecord(
        id=str(record_id),
        contract_type=contract_type,
        stage=stage,
        identity_id=identity_id,
        data=json.dumps(data, default=_json_serializer),
    )
    session = await get_async_session()
    async with session:
        session.add(record)
        await session.commit()
    return str(record_id)


async def get_record(record_id: str) -> dict[str, Any] | None:
    session = await get_async_session()
    async with session:
        result = await session.execute(select(PipelineRecord).where(PipelineRecord.id == record_id))
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return json.loads(row.data)


async def list_pipeline_records(
    contract_type: str,
    stage: str,
    *,
    identity_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return stored pipeline rows as decoded JSON dicts (newest first)."""

    session = await get_async_session()
    async with session:
        stmt = select(PipelineRecord).where(
            PipelineRecord.contract_type == contract_type,
            PipelineRecord.stage == stage,
        )
        if identity_id is not None and identity_id != "":
            stmt = stmt.where(PipelineRecord.identity_id == identity_id)
        stmt = stmt.order_by(PipelineRecord.created_at.desc()).limit(limit)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [json.loads(r.data) for r in rows]


async def log_audit(stage: str, action: str, actor: str = "system", **details: Any):
    from packages.contracts.base import new_id

    entry = AuditLog(
        id=str(new_id()),
        stage=stage,
        action=action,
        actor=actor,
        details=json.dumps(details, default=_json_serializer),
    )
    session = await get_async_session()
    async with session:
        session.add(entry)
        await session.commit()
