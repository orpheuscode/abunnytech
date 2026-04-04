"""FastAPI app that exposes CRUD endpoints over the packages.state layer."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from packages.state.fixtures import seed_all
from packages.state.registry import COLLECTION_MAP, RepositoryRegistry
from packages.state.sqlite import Database


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = os.getenv("ABUNNYTECH_DB", "abunnytech.db")
    db = Database(db_path)
    await db.connect()
    registry = RepositoryRegistry(db)

    for repo in registry.all_repos().values():
        await repo._ensure_table()

    if os.getenv("SEED_ON_STARTUP", "").lower() in ("1", "true", "yes"):
        await seed_all(registry)

    app.state.db = db
    app.state.registry = registry

    yield

    await db.disconnect()


app = FastAPI(
    title="abunnytech API",
    description="CRUD API backed by the packages.state layer.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _registry() -> RepositoryRegistry:
    return app.state.registry


# ---- Health & seed ---------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@app.post("/seed")
async def seed() -> dict[str, Any]:
    counts = await seed_all(_registry())
    return {"seeded": True, "counts": counts}


# ---- Generic CRUD for every collection -------------------------------------

def _register_crud(collection: str) -> None:
    """Register list / get / create / update / delete for *collection*."""

    model_cls = COLLECTION_MAP[collection]

    async def list_items(limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        repo = _registry().get_repo(collection)
        items = await repo.list_all(limit=limit, offset=offset)
        return [item.model_dump(mode="json") for item in items]

    async def get_item(item_id: UUID) -> dict[str, Any]:
        repo = _registry().get_repo(collection)
        item = await repo.get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail=f"{collection} {item_id} not found")
        return item.model_dump(mode="json")

    async def create_item(payload: dict[str, Any]) -> dict[str, Any]:
        repo = _registry().get_repo(collection)
        item = model_cls.model_validate(payload)
        created = await repo.create(item)
        return created.model_dump(mode="json")

    async def update_item(item_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
        repo = _registry().get_repo(collection)
        item = model_cls.model_validate(payload)
        updated = await repo.update(item_id, item)
        if updated is None:
            raise HTTPException(status_code=404, detail=f"{collection} {item_id} not found")
        return updated.model_dump(mode="json")

    async def delete_item(item_id: UUID) -> dict[str, bool]:
        repo = _registry().get_repo(collection)
        ok = await repo.delete(item_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"{collection} {item_id} not found")
        return {"deleted": True}

    list_items.__name__ = f"list_{collection}"
    get_item.__name__ = f"get_{collection}"
    create_item.__name__ = f"create_{collection}"
    update_item.__name__ = f"update_{collection}"
    delete_item.__name__ = f"delete_{collection}"

    app.get(f"/{collection}", name=f"list_{collection}")(list_items)
    app.get(f"/{collection}/{{item_id}}", name=f"get_{collection}")(get_item)
    app.post(f"/{collection}", name=f"create_{collection}", status_code=201)(create_item)
    app.put(f"/{collection}/{{item_id}}", name=f"update_{collection}")(update_item)
    app.delete(f"/{collection}/{{item_id}}", name=f"delete_{collection}")(delete_item)


for _col in COLLECTION_MAP:
    _register_crud(_col)
