"""
Base Repository

Provides common data access operations shared across repositories.

Repositories should remain persistence-only and must not contain
business logic.

Transaction management (commit/rollback) is handled by the
Service layer.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """
    Base repository providing common read operations.
    """

    def __init__(
        self,
        db: AsyncSession,
        model: type[ModelType],
    ):
        self.db = db
        self.model = model

    # ==========================================================
    # Read Operations
    # ==========================================================

    async def get_by_id(
        self,
        id: Any,
    ) -> ModelType | None:
        """
        Retrieve a record by its primary key.
        """

        result = await self.db.execute(
            select(self.model).where(
                self.model.id == id
            )
        )

        return result.scalar_one_or_none()

    async def get_all(
        self,
    ) -> list[ModelType]:
        """
        Retrieve all records.
        """

        result = await self.db.execute(
            select(self.model)
        )

        return list(result.scalars().all())

        # ==========================================================
    # Persistence
    # ==========================================================

    async def save(
        self,
        obj: ModelType,
    ) -> ModelType:
        """
        Persist an entity.

        The transaction is not committed here.
        Commit is handled by the Service layer.
        """

        self.db.add(obj)

        await self.db.flush()

        await self.db.refresh(obj)

        return obj

    async def remove(
        self,
        obj: ModelType,
    ) -> None:
        """
        Remove an entity.

        Commit is handled by the Service layer.
        """

        await self.db.delete(obj)