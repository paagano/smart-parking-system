"""
Loyalty Reward Repository.

Persistence layer for LoyaltyReward and
LoyaltyRewardRedemption entities.

Repositories contain ONLY database access logic.

Business rules belong in LoyaltyRewardService and LoyaltyService.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    LoyaltyRewardStatus,
    LoyaltyRewardType,
    LoyaltyTier,
    RewardRedemptionStatus,
)
from app.models.loyalty_reward import LoyaltyReward
from app.models.loyalty_reward_redemption import (
    LoyaltyRewardRedemption,
)
from app.repositories.base_repository import BaseRepository


class LoyaltyRewardRepository(
    BaseRepository[LoyaltyReward],
):
    """
    Repository responsible for LoyaltyReward persistence
    and LoyaltyRewardRedemption queries.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        super().__init__(
            db=db,
            model=LoyaltyReward,
        )

    # ==========================================================
    # Reward Catalogue
    # ==========================================================

    async def get_by_id(
        self,
        reward_id: int,
    ) -> LoyaltyReward | None:
        """
        Retrieve a loyalty reward by its primary key.
        """

        return await super().get_by_id(
            reward_id,
        )

    async def get_active_by_id(
        self,
        reward_id: int,
    ) -> LoyaltyReward | None:
        """
        Retrieve an active loyalty reward by ID.

        A reward must have both:
        - status = ACTIVE
        - is_active = True
        """

        result = await self.db.execute(
            select(
                LoyaltyReward,
            ).where(
                LoyaltyReward.id == reward_id,
                LoyaltyReward.status
                == LoyaltyRewardStatus.ACTIVE,
                LoyaltyReward.is_active.is_(True),
            )
        )

        return result.scalar_one_or_none()

    async def get_all(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReward]:
        """
        Retrieve loyalty rewards with pagination.

        Results are ordered from newest to oldest.

        ID is used as a deterministic tie-breaker to ensure
        stable pagination when multiple rewards have the same
        created_at timestamp.
        """

        result = await self.db.execute(
            select(
                LoyaltyReward,
            )
            .order_by(
                LoyaltyReward.created_at.desc(),
                LoyaltyReward.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    async def get_active_rewards(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReward]:
        """
        Retrieve currently active rewards.

        Results are ordered from newest to oldest with a
        deterministic ID tie-breaker.
        """

        result = await self.db.execute(
            select(
                LoyaltyReward,
            )
            .where(
                LoyaltyReward.status
                == LoyaltyRewardStatus.ACTIVE,
                LoyaltyReward.is_active.is_(True),
            )
            .order_by(
                LoyaltyReward.created_at.desc(),
                LoyaltyReward.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    async def get_by_type(
        self,
        reward_type: LoyaltyRewardType,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReward]:
        """
        Retrieve rewards of a specific type.

        Results are ordered from newest to oldest with a
        deterministic ID tie-breaker.
        """

        result = await self.db.execute(
            select(
                LoyaltyReward,
            )
            .where(
                LoyaltyReward.reward_type
                == reward_type,
            )
            .order_by(
                LoyaltyReward.created_at.desc(),
                LoyaltyReward.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    async def get_active_by_type(
        self,
        reward_type: LoyaltyRewardType,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReward]:
        """
        Retrieve active rewards of a specific type.
        """

        result = await self.db.execute(
            select(
                LoyaltyReward,
            )
            .where(
                LoyaltyReward.reward_type
                == reward_type,
                LoyaltyReward.status
                == LoyaltyRewardStatus.ACTIVE,
                LoyaltyReward.is_active.is_(True),
            )
            .order_by(
                LoyaltyReward.created_at.desc(),
                LoyaltyReward.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    async def get_eligible_rewards(
        self,
        tier: LoyaltyTier,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReward]:
        """
        Retrieve active rewards available to a customer
        at the supplied loyalty tier.

        Eligibility rules:

        - minimum_tier = NULL:
            Available to every customer.

        - minimum_tier = BRONZE:
            Available to BRONZE, SILVER, GOLD and PLATINUM.

        - minimum_tier = SILVER:
            Available to SILVER, GOLD and PLATINUM.

        - minimum_tier = GOLD:
            Available to GOLD and PLATINUM.

        - minimum_tier = PLATINUM:
            Available only to PLATINUM.

        The loyalty tier hierarchy is represented explicitly
        here so that the database query returns only rewards
        that are eligible for the supplied customer tier.
        """

        tier_hierarchy: dict[LoyaltyTier, tuple[LoyaltyTier, ...]] = {
            LoyaltyTier.BRONZE: (
                LoyaltyTier.BRONZE,
            ),
            LoyaltyTier.SILVER: (
                LoyaltyTier.BRONZE,
                LoyaltyTier.SILVER,
            ),
            LoyaltyTier.GOLD: (
                LoyaltyTier.BRONZE,
                LoyaltyTier.SILVER,
                LoyaltyTier.GOLD,
            ),
            LoyaltyTier.PLATINUM: (
                LoyaltyTier.BRONZE,
                LoyaltyTier.SILVER,
                LoyaltyTier.GOLD,
                LoyaltyTier.PLATINUM,
            ),
        }

        eligible_minimum_tiers = tier_hierarchy[tier]

        result = await self.db.execute(
            select(
                LoyaltyReward,
            )
            .where(
                LoyaltyReward.status
                == LoyaltyRewardStatus.ACTIVE,
                LoyaltyReward.is_active.is_(True),
                (
                    LoyaltyReward.minimum_tier.is_(None)
                    | LoyaltyReward.minimum_tier.in_(
                        eligible_minimum_tiers,
                    )
                ),
            )
            .order_by(
                LoyaltyReward.created_at.desc(),
                LoyaltyReward.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    async def count_rewards(
        self,
    ) -> int:
        """
        Count all loyalty rewards.
        """

        result = await self.db.execute(
            select(
                func.count(
                    LoyaltyReward.id,
                )
            )
        )

        return result.scalar_one()

    async def count_active_rewards(
        self,
    ) -> int:
        """
        Count active loyalty rewards.
        """

        result = await self.db.execute(
            select(
                func.count(
                    LoyaltyReward.id,
                )
            ).where(
                LoyaltyReward.status
                == LoyaltyRewardStatus.ACTIVE,
                LoyaltyReward.is_active.is_(True),
            )
        )

        return result.scalar_one()

    # ==========================================================
    # Reward Redemptions
    # ==========================================================

    async def get_redemption_by_id(
        self,
        redemption_id: int,
    ) -> LoyaltyRewardRedemption | None:
        """
        Retrieve a reward redemption by its primary key.
        """

        result = await self.db.execute(
            select(
                LoyaltyRewardRedemption,
            ).where(
                LoyaltyRewardRedemption.id
                == redemption_id,
            )
        )

        return result.scalar_one_or_none()

    async def get_redemption_by_reference(
        self,
        redemption_reference: str,
    ) -> LoyaltyRewardRedemption | None:
        """
        Retrieve a reward redemption using its unique
        redemption reference.
        """

        result = await self.db.execute(
            select(
                LoyaltyRewardRedemption,
            ).where(
                LoyaltyRewardRedemption.redemption_reference
                == redemption_reference,
            )
        )

        return result.scalar_one_or_none()

    async def get_customer_redemptions(
        self,
        loyalty_account_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyRewardRedemption]:
        """
        Retrieve reward redemption history for a loyalty
        account.

        Results are ordered from newest to oldest with a
        deterministic ID tie-breaker.
        """

        result = await self.db.execute(
            select(
                LoyaltyRewardRedemption,
            )
            .where(
                LoyaltyRewardRedemption.loyalty_account_id
                == loyalty_account_id,
            )
            .order_by(
                LoyaltyRewardRedemption.created_at.desc(),
                LoyaltyRewardRedemption.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    async def get_customer_redemptions_by_status(
        self,
        loyalty_account_id: int,
        status: RewardRedemptionStatus,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyRewardRedemption]:
        """
        Retrieve customer reward redemptions filtered
        by redemption status.
        """

        result = await self.db.execute(
            select(
                LoyaltyRewardRedemption,
            )
            .where(
                LoyaltyRewardRedemption.loyalty_account_id
                == loyalty_account_id,
                LoyaltyRewardRedemption.status
                == status,
            )
            .order_by(
                LoyaltyRewardRedemption.created_at.desc(),
                LoyaltyRewardRedemption.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    async def get_redemptions_for_reward(
        self,
        reward_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyRewardRedemption]:
        """
        Retrieve redemption history for a specific reward.
        """

        result = await self.db.execute(
            select(
                LoyaltyRewardRedemption,
            )
            .where(
                LoyaltyRewardRedemption.reward_id
                == reward_id,
            )
            .order_by(
                LoyaltyRewardRedemption.created_at.desc(),
                LoyaltyRewardRedemption.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )

        return list(
            result.scalars().all(),
        )

    async def count_customer_redemptions(
        self,
        loyalty_account_id: int,
    ) -> int:
        """
        Count reward redemptions belonging to a loyalty account.
        """

        result = await self.db.execute(
            select(
                func.count(
                    LoyaltyRewardRedemption.id,
                )
            ).where(
                LoyaltyRewardRedemption.loyalty_account_id
                == loyalty_account_id,
            )
        )

        return result.scalar_one()

    async def count_redemptions_for_reward(
        self,
        reward_id: int,
    ) -> int:
        """
        Count redemptions associated with a specific reward.
        """

        result = await self.db.execute(
            select(
                func.count(
                    LoyaltyRewardRedemption.id,
                )
            ).where(
                LoyaltyRewardRedemption.reward_id
                == reward_id,
            )
        )

        return result.scalar_one()

    # ==========================================================
    # Redemption Reference / Status
    # ==========================================================

    async def redemption_exists(
        self,
        redemption_reference: str,
    ) -> bool:
        """
        Determine whether a redemption reference already exists.
        """

        redemption = await self.get_redemption_by_reference(
            redemption_reference,
        )

        return redemption is not None

    async def get_active_redemption(
        self,
        redemption_id: int,
    ) -> LoyaltyRewardRedemption | None:
        """
        Retrieve a redemption that is still in a redeemable
        state.

        The repository only filters persisted status.
        Business rules around whether the reward has expired
        belong to the service layer.
        """

        result = await self.db.execute(
            select(
                LoyaltyRewardRedemption,
            ).where(
                LoyaltyRewardRedemption.id
                == redemption_id,
                LoyaltyRewardRedemption.status
                == RewardRedemptionStatus.REDEEMED,
            )
        )

        return result.scalar_one_or_none()