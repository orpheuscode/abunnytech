"""Tests for state_api FastAPI endpoints (state CRUD, not M1 pipeline API)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from state_api.main import app


@pytest.fixture
async def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ABUNNYTECH_DB", str(tmp_path / "test_api.db"))

    from state_api import main as api_mod

    db = __import__("packages.state.sqlite", fromlist=["Database"]).Database(str(tmp_path / "test_api.db"))
    await db.connect()
    registry = __import__("packages.state.registry", fromlist=["RepositoryRegistry"]).RepositoryRegistry(db)
    for repo in registry.all_repos().values():
        await repo._ensure_table()
    api_mod.app.state.db = db
    api_mod.app.state.registry = registry

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await db.disconnect()


class TestHealth:
    @pytest.mark.asyncio
    async def test_health(self, client: AsyncClient) -> None:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestSeed:
    @pytest.mark.asyncio
    async def test_seed(self, client: AsyncClient) -> None:
        resp = await client.post("/seed")
        assert resp.status_code == 200
        body = resp.json()
        assert body["seeded"] is True
        assert body["counts"]["identity_matrix"] >= 1


class TestIdentityCRUD:
    @pytest.mark.asyncio
    async def test_create_and_get(self, client: AsyncClient) -> None:
        payload = {
            "name": "Test Creator",
            "archetype": "educator",
        }
        resp = await client.post("/identity_matrix", json=payload)
        assert resp.status_code == 201
        created = resp.json()
        assert created["name"] == "Test Creator"
        item_id = created["id"]

        resp = await client.get(f"/identity_matrix/{item_id}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Test Creator"

    @pytest.mark.asyncio
    async def test_update(self, client: AsyncClient) -> None:
        payload = {"name": "Before", "archetype": "entertainer"}
        resp = await client.post("/identity_matrix", json=payload)
        assert resp.status_code == 201
        item_id = resp.json()["id"]

        updated_payload = {"name": "After", "archetype": "entertainer", "id": item_id}
        resp = await client.put(f"/identity_matrix/{item_id}", json=updated_payload)
        assert resp.status_code == 200
        assert resp.json()["name"] == "After"

    @pytest.mark.asyncio
    async def test_delete(self, client: AsyncClient) -> None:
        payload = {"name": "Doomed", "archetype": "reviewer"}
        resp = await client.post("/identity_matrix", json=payload)
        item_id = resp.json()["id"]

        resp = await client.delete(f"/identity_matrix/{item_id}")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

        resp = await client.get(f"/identity_matrix/{item_id}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_not_found(self, client: AsyncClient) -> None:
        resp = await client.get(f"/identity_matrix/{uuid4()}")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/identity_matrix")
        assert resp.status_code == 200
        assert resp.json() == []


class TestOtherCollections:
    @pytest.mark.asyncio
    async def test_list_trending_audio(self, client: AsyncClient) -> None:
        resp = await client.get("/trending_audio")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_list_video_blueprints(self, client: AsyncClient) -> None:
        resp = await client.get("/video_blueprints")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_list_content_packages(self, client: AsyncClient) -> None:
        resp = await client.get("/content_packages")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_list_distribution_records(self, client: AsyncClient) -> None:
        resp = await client.get("/distribution_records")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_list_optimization_directives(self, client: AsyncClient) -> None:
        resp = await client.get("/optimization_directives")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_list_redo_queue(self, client: AsyncClient) -> None:
        resp = await client.get("/redo_queue")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_list_product_catalog(self, client: AsyncClient) -> None:
        resp = await client.get("/product_catalog")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_seed_then_list(self, client: AsyncClient) -> None:
        await client.post("/seed")
        resp = await client.get("/identity_matrix")
        assert resp.status_code == 200
        assert len(resp.json()) >= 2
