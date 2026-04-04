"""Abstract repository interface.

Every storage backend (SQLite, Postgres, Supabase, in-memory) implements
this protocol so callers never depend on a concrete store.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class Repository(ABC, Generic[T]):
    """Async CRUD repository for a single entity type."""

    @abstractmethod
    async def get(self, id: UUID) -> T | None: ...

    @abstractmethod
    async def list_all(self, *, limit: int = 100, offset: int = 0) -> list[T]: ...

    @abstractmethod
    async def create(self, item: T) -> T: ...

    @abstractmethod
    async def update(self, id: UUID, item: T) -> T | None: ...

    @abstractmethod
    async def delete(self, id: UUID) -> bool: ...

    @abstractmethod
    async def count(self) -> int: ...
