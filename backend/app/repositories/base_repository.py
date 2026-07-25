from typing import Any, Generic, Type, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ModelType = TypeVar("ModelType")


class BaseRepository(Generic[ModelType]):
    """
    Base repository providing common CRUD operations.
    """

    def __init__(
        self,
        db: AsyncSession,
        model: Type[ModelType],
    ):
        self.db = db
        self.model = model

    async def get_by_id(
        self,
        id: Any,
    ) -> ModelType | None:
        """
        Retrieve a record by its primary key.
        """
        result = await self.db.execute(
            select(self.model).where(self.model.id == id)
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

    async def create(
        self,
        obj: ModelType,
    ) -> ModelType:
        """
        Persist a new record.
        """
        self.db.add(obj)

        await self.db.commit()

        await self.db.refresh(obj)

        return obj

    async def delete(
        self,
        obj: ModelType,
    ) -> None:
        """
        Delete a record.
        """

        await self.db.delete(obj)

        await self.db.commit()