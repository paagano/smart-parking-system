from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.revoked_token import RevokedToken
from app.repositories.base_repository import BaseRepository


class RevokedTokenRepository(BaseRepository[RevokedToken]):
    """
    Repository for managing revoked JWT tokens.
    """

    def __init__(
        self,
        db: AsyncSession,
    ):
        super().__init__(
            db,
            RevokedToken,
        )

    async def get_by_jti(
        self,
        jti: str,
    ) -> RevokedToken | None:
        """
        Retrieve a revoked token by its JWT identifier.
        """

        result = await self.db.execute(
            select(RevokedToken).where(
                RevokedToken.jti == jti,
            )
        )

        return result.scalar_one_or_none()

    async def is_revoked(
        self,
        jti: str,
    ) -> bool:
        """
        Check whether a JWT identifier has been revoked.
        """

        token = await self.get_by_jti(jti)

        return token is not None

    async def revoke(
        self,
        jti: str,
        expires_at: datetime,
    ) -> RevokedToken:
        """
        Store a JWT identifier as revoked.
        """

        revoked_token = RevokedToken(
            jti=jti,
            expires_at=expires_at,
        )

        await self.save(
            revoked_token,
        )

        return revoked_token