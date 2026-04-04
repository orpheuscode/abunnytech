"""Tests for the state/storage layer – repository CRUD and registry."""

from __future__ import annotations

from uuid import uuid4

import pytest

from packages.state.events import EventBus, JobRegistry
from packages.state.fixtures import seed_all
from packages.state.models import (
    ContentPackage,
    IdentityMatrix,
    PersonaArchetype,
    Platform,
    PlatformPresence,
    TrendingAudioItem,
    VideoBlueprint,
)
from packages.state.registry import RepositoryRegistry
from packages.state.sqlite import SQLiteRepository

# ---------------------------------------------------------------------------
# SQLiteRepository CRUD
# ---------------------------------------------------------------------------


class TestSQLiteRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, registry: RepositoryRegistry) -> None:
        repo = registry.identity_matrix
        item = IdentityMatrix(
            name="Test Creator",
            archetype=PersonaArchetype.EDUCATOR,
        )
        created = await repo.create(item)
        assert created.id == item.id

        fetched = await repo.get(item.id)
        assert fetched is not None
        assert fetched.name == "Test Creator"

    @pytest.mark.asyncio
    async def test_list_all(self, registry: RepositoryRegistry) -> None:
        repo = registry.trending_audio
        for i in range(5):
            await repo.create(
                TrendingAudioItem(
                    audio_id=f"a{i}", title=f"Track {i}", trend_score=float(i)
                )
            )
        items = await repo.list_all(limit=3)
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_update(self, registry: RepositoryRegistry) -> None:
        repo = registry.identity_matrix
        item = IdentityMatrix(name="Before", archetype=PersonaArchetype.ENTERTAINER)
        await repo.create(item)

        item.name = "After"
        updated = await repo.update(item.id, item)
        assert updated is not None
        assert updated.name == "After"

        fetched = await repo.get(item.id)
        assert fetched is not None
        assert fetched.name == "After"

    @pytest.mark.asyncio
    async def test_update_nonexistent_returns_none(
        self, registry: RepositoryRegistry
    ) -> None:
        repo = registry.identity_matrix
        item = IdentityMatrix(name="Ghost", archetype=PersonaArchetype.REVIEWER)
        result = await repo.update(uuid4(), item)
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, registry: RepositoryRegistry) -> None:
        repo = registry.video_blueprints
        bp = VideoBlueprint(title="Doomed Video", status="draft")
        await repo.create(bp)
        assert await repo.count() == 1

        deleted = await repo.delete(bp.id)
        assert deleted is True
        assert await repo.count() == 0

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(
        self, registry: RepositoryRegistry
    ) -> None:
        repo = registry.video_blueprints
        assert await repo.delete(uuid4()) is False

    @pytest.mark.asyncio
    async def test_count(self, registry: RepositoryRegistry) -> None:
        repo = registry.content_packages
        assert await repo.count() == 0
        await repo.create(ContentPackage(caption="one"))
        await repo.create(ContentPackage(caption="two"))
        assert await repo.count() == 2

    @pytest.mark.asyncio
    async def test_complex_model_roundtrip(self, registry: RepositoryRegistry) -> None:
        repo = registry.identity_matrix
        item = IdentityMatrix(
            name="Full Creator",
            archetype=PersonaArchetype.STORYTELLER,
            tagline="Once upon a time...",
            platforms=[
                PlatformPresence(platform=Platform.TIKTOK, handle="@story"),
                PlatformPresence(platform=Platform.YOUTUBE, handle="@story_yt"),
            ],
        )
        await repo.create(item)

        fetched = await repo.get(item.id)
        assert fetched is not None
        assert len(fetched.platforms) == 2
        assert fetched.platforms[0].handle == "@story"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    @pytest.mark.asyncio
    async def test_all_repos_returns_twelve(self, registry: RepositoryRegistry) -> None:
        repos = registry.all_repos()
        assert len(repos) == 12

    @pytest.mark.asyncio
    async def test_get_repo_by_name(self, registry: RepositoryRegistry) -> None:
        repo = registry.get_repo("identity_matrix")
        assert isinstance(repo, SQLiteRepository)

    @pytest.mark.asyncio
    async def test_get_unknown_repo_raises(self, registry: RepositoryRegistry) -> None:
        with pytest.raises(KeyError):
            registry.get_repo("nonexistent")


# ---------------------------------------------------------------------------
# Fixtures / seeding
# ---------------------------------------------------------------------------


class TestFixtures:
    @pytest.mark.asyncio
    async def test_seed_all(self, registry: RepositoryRegistry) -> None:
        counts = await seed_all(registry)
        assert counts["identity_matrix"] == 2
        assert counts["trending_audio"] == 2
        assert all(v >= 1 for v in counts.values())

        fetched = await registry.identity_matrix.list_all()
        assert len(fetched) == 2


# ---------------------------------------------------------------------------
# EventBus & JobRegistry
# ---------------------------------------------------------------------------


class TestEventBus:
    @pytest.mark.asyncio
    async def test_emit_calls_handler(self) -> None:
        bus = EventBus()
        received: list[str] = []

        async def handler(msg: str = "") -> None:
            received.append(msg)

        bus.on("test", handler)
        await bus.emit("test", msg="hello")
        assert received == ["hello"]

    @pytest.mark.asyncio
    async def test_off_removes_handler(self) -> None:
        bus = EventBus()
        calls = 0

        async def handler(**_: object) -> None:
            nonlocal calls
            calls += 1

        bus.on("x", handler)
        await bus.emit("x")
        bus.off("x", handler)
        await bus.emit("x")
        assert calls == 1


class TestJobRegistry:
    @pytest.mark.asyncio
    async def test_register_and_run(self) -> None:
        jr = JobRegistry()

        async def my_job(x: int = 0) -> int:
            return x * 2

        jr.register("double", my_job)
        result = await jr.run("double", x=5)
        assert result == 10

    @pytest.mark.asyncio
    async def test_unknown_job_raises(self) -> None:
        jr = JobRegistry()
        with pytest.raises(KeyError):
            await jr.run("nope")

    def test_list_jobs(self) -> None:
        jr = JobRegistry()

        async def noop() -> None: ...

        jr.register("b", noop)
        jr.register("a", noop)
        assert jr.list_jobs() == ["a", "b"]
