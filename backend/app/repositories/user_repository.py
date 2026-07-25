from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    """
    Repository for User-specific database operations.
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db, User)

    async def get_by_email(
        self,
        email: str,
    ) -> User | None:

        result = await self.db.execute(
            select(User).where(User.email == email)
        )

        return result.scalar_one_or_none()

    async def get_by_phone(
        self,
        phone_number: str,
    ) -> User | None:

        result = await self.db.execute(
            select(User).where(
                User.phone_number == phone_number
            )
        )

        return result.scalar_one_or_none()