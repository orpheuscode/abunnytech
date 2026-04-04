"""Tests for the FastAPI control plane."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from packages.shared.db import init_db
from services.control_plane.app import app


@pytest.fixture
async def client():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_root(client: AsyncClient):
    r = await client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "abunnytech"


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert "dry_run" in data
    assert "stage5_monetize" in data


@pytest.mark.asyncio
async def test_create_default_identity(client: AsyncClient):
    r = await client.post("/identity/default")
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Avery Bytes"


@pytest.mark.asyncio
async def test_list_identities(client: AsyncClient):
    await client.post("/identity/default")
    r = await client.get("/identity")
    assert r.status_code == 200
    assert len(r.json()) >= 1


@pytest.mark.asyncio
async def test_demo_pipeline(client: AsyncClient):
    r = await client.post("/pipeline/demo")
    assert r.status_code == 200
    data = r.json()
    assert data.get("demo_complete") is True
    assert "stage0_identity" in data["stages"]
    assert "stage4_analyze" in data["stages"]
