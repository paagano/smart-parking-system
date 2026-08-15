"""
Loyalty Referral Repository.

Persistence layer for LoyaltyReferral.

Repositories contain ONLY database access logic.

Business rules belong in LoyaltyReferralService.

Responsibilities
----------------
- Referral creation and persistence
- Referral retrieval
- Referral code lookup
- Referrer queries
- Referred-customer queries
- Referral status filtering
- Referral lifecycle queries
- Referral counts
- Referral updates
- Referral deletion
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ReferralStatus
from app.models.loyalty_referral import LoyaltyReferral
from app.repositories.base_repository import BaseRepository


class LoyaltyReferralRepository(
    BaseRepository[LoyaltyReferral]
):
    """
    Repository responsible for LoyaltyReferral persistence.

    Business rules such as:

        - whether a referral qualifies
        - when a referral should be rewarded
        - how many points should be awarded
        - whether a customer is eligible to refer another
        - referral programme rules

    belong in LoyaltyReferralService.
    """

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        """
        Create a LoyaltyReferralRepository instance.
        """

        super().__init__(
            db=db,
            model=LoyaltyReferral,
        )

    # ==========================================================
    # Basic Retrieval
    # ==========================================================

    async def get_by_id(
        self,
        referral_id: int,
    ) -> LoyaltyReferral | None:
        """
        Retrieve a referral by its primary key.
        """

        return await super().get_by_id(
            referral_id,
        )

    # ==========================================================
    # Referral Code
    # ==========================================================

    async def get_by_code(
        self,
        referral_code: str,
    ) -> LoyaltyReferral | None:
        """
        Retrieve a referral using its unique referral code.
        """

        result = await self.db.execute(
            select(
                LoyaltyReferral,
            ).where(
                LoyaltyReferral.referral_code
                == referral_code,
            )
        )

        return result.scalar_one_or_none()

    async def exists_by_code(
        self,
        referral_code: str,
    ) -> bool:
        """
        Determine whether a referral code already exists.
        """

        referral = await self.get_by_code(
            referral_code,
        )

        return referral is not None

    # ==========================================================
    # Persistence
    # ==========================================================

    async def save(
        self,
        referral: LoyaltyReferral,
    ) -> LoyaltyReferral:
        """
        Persist a new or modified referral.

        The transaction is controlled by the service/application
        layer. This method flushes the current session so the
        generated ID and timestamps are available immediately.
        """

        self.db.add(
            referral,
        )

        await self.db.flush()

        await self.db.refresh(
            referral,
        )

        return referral

    # ==========================================================
    # All Referrals
    # ==========================================================

    async def get_all(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve referrals with pagination.

        Results are ordered from newest to oldest.
        """

        result = await self.db.execute(
            select(
                LoyaltyReferral,
            )
            .order_by(
                LoyaltyReferral.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # Referrer Queries
    # ==========================================================

    async def get_by_referrer(
        self,
        referrer_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve referrals created by a customer.

        referrer_id refers to the customer who initiated
        the referral.
        """

        result = await self.db.execute(
            select(
                LoyaltyReferral,
            )
            .where(
                LoyaltyReferral.referrer_id
                == referrer_id,
            )
            .order_by(
                LoyaltyReferral.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # Referred Customer Queries
    # ==========================================================

    async def get_by_referred_customer(
        self,
        referred_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve referrals associated with a referred customer.

        referred_id refers to the customer who was referred.
        """

        result = await self.db.execute(
            select(
                LoyaltyReferral,
            )
            .where(
                LoyaltyReferral.referred_id
                == referred_id,
            )
            .order_by(
                LoyaltyReferral.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # Customer Referral History
    # ==========================================================

    async def get_customer_referrals(
        self,
        customer_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve the complete referral history for a customer.

        A customer may appear either as the referrer or as the
        referred customer.
        """

        result = await self.db.execute(
            select(
                LoyaltyReferral,
            )
            .where(
                (
                    LoyaltyReferral.referrer_id
                    == customer_id
                )
                | (
                    LoyaltyReferral.referred_id
                    == customer_id
                )
            )
            .order_by(
                LoyaltyReferral.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # Status Queries
    # ==========================================================

    async def get_by_status(
        self,
        referral_status: ReferralStatus,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve referrals having the supplied status.
        """

        result = await self.db.execute(
            select(
                LoyaltyReferral,
            )
            .where(
                LoyaltyReferral.status
                == referral_status,
            )
            .order_by(
                LoyaltyReferral.created_at.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    # ==========================================================
    # Pending Referrals
    # ==========================================================

    async def get_pending(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve referrals currently awaiting qualification.
        """

        return await self.get_by_status(
            ReferralStatus.PENDING,
            limit=limit,
            offset=offset,
        )

    # ==========================================================
    # Qualified Referrals
    # ==========================================================

    async def get_qualified(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve referrals that have qualified but have not
        necessarily been rewarded yet.
        """

        return await self.get_by_status(
            ReferralStatus.QUALIFIED,
            limit=limit,
            offset=offset,
        )

    # ==========================================================
    # Rewarded Referrals
    # ==========================================================

    async def get_rewarded(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve referrals for which the reward has been
        awarded.
        """

        return await self.get_by_status(
            ReferralStatus.REWARDED,
            limit=limit,
            offset=offset,
        )

    # ==========================================================
    # Cancelled Referrals
    # ==========================================================

    async def get_cancelled(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve cancelled referrals.
        """

        return await self.get_by_status(
            ReferralStatus.CANCELLED,
            limit=limit,
            offset=offset,
        )

    # ==========================================================
    # Active Referral
    # ==========================================================

    async def get_active_by_id(
        self,
        referral_id: int,
    ) -> LoyaltyReferral | None:
        """
        Retrieve a referral that is still active in the
        referral lifecycle.

        Active referrals are PENDING or QUALIFIED.
        """

        result = await self.db.execute(
            select(
                LoyaltyReferral,
            ).where(
                LoyaltyReferral.id == referral_id,
                LoyaltyReferral.status.in_(
                    [
                        ReferralStatus.PENDING,
                        ReferralStatus.QUALIFIED,
                    ]
                ),
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Pending Referral for Referred Customer
    # ==========================================================

    async def get_pending_for_referred_customer(
        self,
        referred_id: int,
    ) -> LoyaltyReferral | None:
        """
        Retrieve the pending referral associated with a
        referred customer.

        This is useful when determining whether the referred
        customer has an outstanding referral relationship.
        """

        result = await self.db.execute(
            select(
                LoyaltyReferral,
            )
            .where(
                LoyaltyReferral.referred_id
                == referred_id,
                LoyaltyReferral.status
                == ReferralStatus.PENDING,
            )
            .order_by(
                LoyaltyReferral.created_at.desc(),
            )
        )

        return result.scalars().first()

    # ==========================================================
    # Referrer + Referred Pair
    # ==========================================================

    async def get_by_referrer_and_referred(
        self,
        referrer_id: int,
        referred_id: int,
    ) -> LoyaltyReferral | None:
        """
        Retrieve a referral for a specific referrer/referred
        customer pair.
        """

        result = await self.db.execute(
            select(
                LoyaltyReferral,
            ).where(
                LoyaltyReferral.referrer_id
                == referrer_id,
                LoyaltyReferral.referred_id
                == referred_id,
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Status Update
    # ==========================================================

    async def update(
        self,
        referral: LoyaltyReferral,
    ) -> LoyaltyReferral:
        """
        Persist changes made to an existing referral.

        Business decisions about what fields should change
        belong in LoyaltyReferralService.
        """

        await self.db.flush()

        await self.db.refresh(
            referral,
        )

        return referral

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete(
        self,
        referral: LoyaltyReferral,
    ) -> None:
        """
        Delete a referral from persistence.

        Whether deletion is allowed is a business rule and
        should be enforced by LoyaltyReferralService.
        """

        await self.db.delete(
            referral,
        )

        await self.db.flush()

    # ==========================================================
    # Counts
    # ==========================================================

    async def count_all(self) -> int:
        """
        Count all referrals.
        """

        result = await self.db.execute(
            select(
                func.count(
                    LoyaltyReferral.id,
                )
            )
        )

        return int(
            result.scalar_one(),
        )

    async def count_by_status(
        self,
        referral_status: ReferralStatus,
    ) -> int:
        """
        Count referrals having the supplied status.
        """

        result = await self.db.execute(
            select(
                func.count(
                    LoyaltyReferral.id,
                )
            ).where(
                LoyaltyReferral.status
                == referral_status,
            )
        )

        return int(
            result.scalar_one(),
        )

    async def count_by_referrer(
        self,
        referrer_id: int,
    ) -> int:
        """
        Count referrals initiated by a customer.
        """

        result = await self.db.execute(
            select(
                func.count(
                    LoyaltyReferral.id,
                )
            ).where(
                LoyaltyReferral.referrer_id
                == referrer_id,
            )
        )

        return int(
            result.scalar_one(),
        )

    async def count_by_referred_customer(
        self,
        referred_id: int,
    ) -> int:
        """
        Count referrals associated with a referred customer.
        """

        result = await self.db.execute(
            select(
                func.count(
                    LoyaltyReferral.id,
                )
            ).where(
                LoyaltyReferral.referred_id
                == referred_id,
            )
        )

        return int(
            result.scalar_one(),
        )

    async def count_customer_referrals(
        self,
        customer_id: int,
    ) -> int:
        """
        Count referrals in which a customer participates either
        as referrer or referred customer.
        """

        result = await self.db.execute(
            select(
                func.count(
                    LoyaltyReferral.id,
                )
            ).where(
                (
                    LoyaltyReferral.referrer_id
                    == customer_id
                )
                | (
                    LoyaltyReferral.referred_id
                    == customer_id
                )
            )
        )

        return int(
            result.scalar_one(),
        )