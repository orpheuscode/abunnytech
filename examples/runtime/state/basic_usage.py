"""Basic usage of the packages.state layer.

Creates an in-memory database, inserts an identity, and lists all identities.
"""

from __future__ import annotations

import asyncio

from packages.state.models import IdentityMatrix, PersonaArchetype, Platform, PlatformPresence
from packages.state.registry import RepositoryRegistry
from packages.state.sqlite import Database


async def main() -> None:
    db = Database(":memory:")
    await db.connect()
    registry = RepositoryRegistry(db)

    await registry.identity_matrix._ensure_table()

    identity = IdentityMatrix(
        name="Demo Creator",
        archetype=PersonaArchetype.EDUCATOR,
        tagline="AI-powered content, simplified.",
        platforms=[
            PlatformPresence(platform=Platform.TIKTOK, handle="@demo_creator"),
        ],
    )
    await registry.identity_matrix.create(identity)
    print(f"Created identity: {identity.name} ({identity.id})")

    all_identities = await registry.identity_matrix.list_all()
    print(f"Total identities: {len(all_identities)}")

    for ident in all_identities:
        print(f"  - {ident.name} ({ident.archetype.value})")

    await db.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
