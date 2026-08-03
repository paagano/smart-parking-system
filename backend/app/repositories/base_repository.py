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
    Base repository providing common CRUD and persistence operations.
    """

    def __init__(
        self,
        db: AsyncSession,
        model: type[ModelType],
    ) -> None:
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
                self.model.id == id,
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

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Persistence
    # ==========================================================

    async def save(
        self,
        obj: ModelType,
    ) -> ModelType:
        """
        Persist an entity.

        Notes
        -----
        - Adds the entity to the current session.
        - Flushes pending changes so database-generated
          values (e.g. primary keys) become immediately
          available.
        - Does NOT commit the transaction.
        - Does NOT refresh the entity.

        Transaction management is the responsibility of
        the Service layer.
        """

        self.db.add(obj)

        await self.db.flush()

        return obj

    async def remove(
        self,
        obj: ModelType,
    ) -> None:
        """
        Remove an entity.

        Commit is handled by the Service layer.
        """

        await self.db.delete(
            obj,
        )

    # ==========================================================
    # Transaction Management
    # ==========================================================

    async def commit(
        self,
    ) -> None:
        """
        Commit the current transaction.
        """

        await self.db.commit()

    async def rollback(
        self,
    ) -> None:
        """
        Roll back the current transaction.
        """

        await self.db.rollback()

    async def refresh(
        self,
        obj: ModelType,
    ) -> ModelType:
        """
        Refresh an entity from the database.

        This should normally be called by the Service
        layer after a successful commit when the latest
        database state is required.
        """

        await self.db.refresh(
            obj,
        )

        return obj

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(
        self,
    ) -> str:
        return (
            f"{self.__class__.__name__}"
            f"(model={self.model.__name__})"
        )