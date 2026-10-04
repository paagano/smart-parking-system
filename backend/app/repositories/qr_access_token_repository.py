"""
QR Access Token Repository.

Provides persistence-only data access operations for QRAccessToken.

Business logic belongs in QRAccessTokenService.
Transaction management is handled by the Service layer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    select,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import QRAccessPurpose
from app.models.qr_access_token import QRAccessToken

from app.repositories.base_repository import BaseRepository


# ==========================================================
# QR Access Token Repository
# ==========================================================

class QRAccessTokenRepository(
    BaseRepository[QRAccessToken],
):
    """
    Repository for QRAccessToken persistence operations.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        """
        Initialize QRAccessTokenRepository.
        """

        super().__init__(
            db=db,
            model=QRAccessToken,
        )

    # ======================================================
    # Token Lookup
    # ======================================================

    async def get_by_token_hash(
        self,
        token_hash: str,
    ) -> QRAccessToken | None:
        """
        Retrieve a QR access token by its SHA-256 token hash.
        """

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.token_hash
                == token_hash,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ======================================================
    # Active Token Lookup
    # ======================================================

    async def get_active_by_token_hash(
        self,
        token_hash: str,
    ) -> QRAccessToken | None:
        """
        Retrieve an active QR access token by token hash.

        Expiry validation remains the responsibility of the
        Service layer.
        """

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.token_hash
                == token_hash,
                self.model.is_active
                == True,  # noqa: E712
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ======================================================
    # Facility Token Lookup
    # ======================================================

    async def get_active_by_facility_and_purpose(
        self,
        facility_id: int,
        purpose: QRAccessPurpose,
    ) -> QRAccessToken | None:
        """
        Retrieve the active QR access token for a facility
        and access purpose.

        Returns the most recently created active token when
        multiple active records exist.
        """

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.facility_id
                == facility_id,
                self.model.purpose
                == purpose,
                self.model.is_active
                == True,  # noqa: E712
            )
            .order_by(
                self.model.created_at.desc(),
            )
            .limit(1)
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ======================================================
    # Facility Token Listing
    # ======================================================

    async def get_all_by_facility(
        self,
        facility_id: int,
    ) -> list[QRAccessToken]:
        """
        Retrieve all QR access tokens belonging to a facility.
        """

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.facility_id
                == facility_id,
            )
            .order_by(
                self.model.created_at.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    # ======================================================
    # Active Facility Tokens
    # ======================================================

    async def get_all_active_by_facility(
        self,
        facility_id: int,
    ) -> list[QRAccessToken]:
        """
        Retrieve all active QR access tokens belonging to
        a facility.
        """

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.facility_id
                == facility_id,
                self.model.is_active
                == True,  # noqa: E712
            )
            .order_by(
                self.model.created_at.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    # ======================================================
    # Token Expiry Lookup
    # ======================================================

    async def get_expired_active_tokens(
        self,
        current_time: datetime,
    ) -> list[QRAccessToken]:
        """
        Retrieve active QR tokens whose expiry time has passed.

        The Service layer decides whether and when these tokens
        should be deactivated.
        """

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.is_active
                == True,  # noqa: E712
                self.model.expires_at
                <= current_time,
            )
            .order_by(
                self.model.expires_at.asc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    # ======================================================
    # Deactivate Token
    # ======================================================

    async def deactivate(
        self,
        qr_access_token: QRAccessToken,
    ) -> None:
        """
        Deactivate a QR access token.

        Transaction management remains the responsibility
        of the Service layer.
        """

        qr_access_token.is_active = False

    # ======================================================
    # Delete Token
    # ======================================================

    async def delete(
        self,
        qr_access_token: QRAccessToken,
    ) -> None:
        """
        Delete a QR access token from persistence.

        Transaction management remains the responsibility
        of the Service layer.
        """

        await self.db.delete(
            qr_access_token,
        )