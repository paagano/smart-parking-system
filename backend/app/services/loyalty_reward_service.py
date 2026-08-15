"""
Loyalty Reward Service.

Contains business logic for the SmartPark Loyalty Reward Engine.

Responsibilities
----------------
- Reward catalogue management
- Reward retrieval
- Reward eligibility
- Reward validity
- Reward redemption
- Redemption history
- Redemption validation
- Point deduction through LoyaltyService

Persistence is delegated to LoyaltyRewardRepository.

Point balance manipulation is delegated to LoyaltyService.

Business rules belong in this service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.handlers import (
    BadRequestException,
    NotFoundException,
)

from app.models.enums import (
    LoyaltyRewardStatus,
    LoyaltyRewardType,
    LoyaltyTier,
    RewardRedemptionStatus,
    NotificationChannel,
    NotificationPriority,
    NotificationType,
)

from app.models.loyalty_reward import (
    LoyaltyReward,
)

from app.models.loyalty_reward_redemption import (
    LoyaltyRewardRedemption,
)

from app.repositories.loyalty_reward_repository import (
    LoyaltyRewardRepository,
)

from app.services.loyalty_service import (
    LoyaltyService,
)

from app.schemas.notification import (
    NotificationCreateInternal,
)

from app.services.notification_service import (
    NotificationService,
)


class LoyaltyRewardService:
    """
    Service responsible for SmartPark Loyalty Reward
    business logic.
    """

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        db: AsyncSession,
        repository: LoyaltyRewardRepository,
        loyalty_service: LoyaltyService,
        notification_service: NotificationService,
    ) -> None:
        """
        Create a LoyaltyRewardService instance.
        """

        self.db = db
        self.repository = repository
        self.loyalty_service = loyalty_service
        self.notification_service = notification_service

    # ==========================================================
    # Reward Catalogue
    # ==========================================================

    async def get_reward(
        self,
        reward_id: int,
    ) -> LoyaltyReward:
        """
        Retrieve a loyalty reward by ID.

        Raises
        ------
        NotFoundException
            If the reward does not exist.
        """

        reward = await self.repository.get_by_id(
            reward_id,
        )

        if reward is None:
            raise NotFoundException(
                "Loyalty reward not found.",
            )

        return reward

    async def get_active_reward(
        self,
        reward_id: int,
    ) -> LoyaltyReward:
        """
        Retrieve an active loyalty reward.

        Raises
        ------
        NotFoundException
            If the reward does not exist or is inactive.
        """

        reward = await self.repository.get_active_by_id(
            reward_id,
        )

        if reward is None:
            raise NotFoundException(
                "Active loyalty reward not found.",
            )

        return reward

    async def get_all_rewards(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReward]:
        """
        Retrieve all rewards with pagination.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return await self.repository.get_all(
            limit=limit,
            offset=offset,
        )

    async def get_active_rewards(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReward]:
        """
        Retrieve active rewards with pagination.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return await self.repository.get_active_rewards(
            limit=limit,
            offset=offset,
        )

    async def get_rewards_by_type(
        self,
        reward_type: LoyaltyRewardType,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReward]:
        """
        Retrieve rewards by reward type.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return await self.repository.get_by_type(
            reward_type=reward_type,
            limit=limit,
            offset=offset,
        )

    async def get_active_rewards_by_type(
        self,
        reward_type: LoyaltyRewardType,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReward]:
        """
        Retrieve active rewards by reward type.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return await self.repository.get_active_by_type(
            reward_type=reward_type,
            limit=limit,
            offset=offset,
        )

    async def get_eligible_rewards(
        self,
        customer_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReward]:
        """
        Retrieve rewards eligible for a customer.

        Eligibility is determined from the customer's current
        loyalty tier.

        Rewards must also currently be valid.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        rewards = await self.repository.get_eligible_rewards(
            tier=account.tier,
            limit=limit,
            offset=offset,
        )

        return [
            reward
            for reward in rewards
            if self._is_reward_valid(
                reward,
            )
        ]

    async def count_rewards(
        self,
    ) -> int:
        """
        Return the total number of rewards.
        """

        return await self.repository.count_rewards()

    async def count_active_rewards(
        self,
    ) -> int:
        """
        Return the number of active rewards.
        """

        return await self.repository.count_active_rewards()

    # ==========================================================
    # Reward Creation
    # ==========================================================

    async def create_reward(
        self,
        *,
        name: str,
        description: str | None,
        reward_type: LoyaltyRewardType,
        points_cost: int,
        monetary_value=None,
        status: LoyaltyRewardStatus = (
            LoyaltyRewardStatus.ACTIVE
        ),
        is_active: bool = True,
        minimum_tier: LoyaltyTier | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> LoyaltyReward:
        """
        Create a new loyalty reward.

        Business validation is performed before persistence.
        """

        self._validate_reward_values(
            name=name,
            points_cost=points_cost,
            monetary_value=monetary_value,
            valid_from=valid_from,
            valid_until=valid_until,
        )

        reward = LoyaltyReward(
            name=name.strip(),
            description=description,
            reward_type=reward_type,
            points_cost=points_cost,
            monetary_value=monetary_value,
            status=status,
            is_active=is_active,
            minimum_tier=minimum_tier,
            valid_from=valid_from,
            valid_until=valid_until,
        )

        reward = await self.repository.save(
            reward,
        )

        await self.db.commit()

        await self.db.refresh(
            reward,
        )

        return reward

    # ==========================================================
    # Reward Update
    # ==========================================================

    async def update_reward(
        self,
        reward_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        reward_type: LoyaltyRewardType | None = None,
        points_cost: int | None = None,
        monetary_value=None,
        status: LoyaltyRewardStatus | None = None,
        is_active: bool | None = None,
        minimum_tier: LoyaltyTier | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> LoyaltyReward:
        """
        Update an existing loyalty reward.

        Only supplied fields are changed.
        """

        reward = await self.get_reward(
            reward_id,
        )

        if name is not None:
            name = name.strip()

            if not name:
                raise BadRequestException(
                    "Reward name cannot be empty.",
                )

            reward.name = name

        if description is not None:
            reward.description = description

        if reward_type is not None:
            reward.reward_type = reward_type

        if points_cost is not None:
            if points_cost <= 0:
                raise BadRequestException(
                    "Reward points cost must be greater than zero.",
                )

            reward.points_cost = points_cost

        if monetary_value is not None:
            if monetary_value < 0:
                raise BadRequestException(
                    "Reward monetary value cannot be negative.",
                )

            reward.monetary_value = monetary_value

        if status is not None:
            reward.status = status

        if is_active is not None:
            reward.is_active = is_active

        if minimum_tier is not None:
            reward.minimum_tier = minimum_tier

        if valid_from is not None:
            reward.valid_from = valid_from

        if valid_until is not None:
            reward.valid_until = valid_until

        self._validate_validity_period(
            valid_from=reward.valid_from,
            valid_until=reward.valid_until,
        )

        await self.db.commit()

        await self.db.refresh(
            reward,
        )

        return reward

    # ==========================================================
    # Reward Redemption
    # ==========================================================

    async def redeem_reward(
        self,
        *,
        customer_id: int,
        reward_id: int,
    ) -> tuple[
        LoyaltyRewardRedemption,
        LoyaltyReward,
        int,
        LoyaltyTier,
    ]:
        """
        Redeem a loyalty reward for a customer.

        Process:

        1. Retrieve the customer's loyalty account.
        2. Validate the reward.
        3. Validate customer tier eligibility.
        4. Validate reward validity period.
        5. Validate sufficient points.
        6. Deduct points through LoyaltyService.
        7. Create redemption record.
        8. Return redemption details and remaining balance.

        Returns
        -------
        tuple
            (
                redemption,
                reward,
                remaining_points,
                loyalty_tier,
            )
        """

        # ------------------------------------------------------
        # Loyalty Account
        # ------------------------------------------------------

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        if not account.is_active:
            raise BadRequestException(
                "Loyalty account is inactive.",
            )

        # ------------------------------------------------------
        # Reward
        # ------------------------------------------------------

        reward = await self.repository.get_active_by_id(
            reward_id,
        )

        if reward is None:
            raise NotFoundException(
                "Active loyalty reward not found.",
            )

        # ------------------------------------------------------
        # Reward Validity
        # ------------------------------------------------------

        self._validate_reward_available(
            reward,
        )

        # ------------------------------------------------------
        # Tier Eligibility
        # ------------------------------------------------------

        if not self._is_tier_eligible(
            customer_tier=account.tier,
            minimum_tier=reward.minimum_tier,
        ):
            raise BadRequestException(
                "Customer loyalty tier is not eligible "
                "for this reward.",
            )

        # ------------------------------------------------------
        # Points
        # ------------------------------------------------------

        if account.points_balance < reward.points_cost:
            raise BadRequestException(
                "Insufficient loyalty points to redeem "
                "this reward.",
            )

        # ------------------------------------------------------
        # Redemption Reference
        # ------------------------------------------------------

        redemption_reference = (
            self._generate_redemption_reference()
        )

        # ------------------------------------------------------
        # Deduct Loyalty Points
        # ------------------------------------------------------

        await self.loyalty_service.redeem_points(
            customer_id=customer_id,
            points=reward.points_cost,
            reference_type="LOYALTY_REWARD",
            reference_id=reward.id,
            description=(
                f"Redeemed loyalty reward: "
                f"{reward.name}"
            ),
        )

        # ------------------------------------------------------
        # Calculate Redemption Expiry
        # ------------------------------------------------------

        expires_at = reward.valid_until

        # ------------------------------------------------------
        # Create Redemption
        # ------------------------------------------------------

        redemption = LoyaltyRewardRedemption(
            loyalty_account_id=account.id,
            reward_id=reward.id,
            redemption_reference=redemption_reference,
            points_spent=reward.points_cost,
            status=RewardRedemptionStatus.REDEEMED,
            used_at=None,
            expires_at=expires_at,
            description=reward.description,
        )

        redemption = await self.repository.save(
            redemption,
        )

        await self.db.commit()

        await self.db.refresh(
            redemption,
        )

        # ------------------------------------------------------
        # Loyalty Reward Redeemed Notification
        # ------------------------------------------------------

        await self.notification_service.create_notification(
            NotificationCreateInternal(
                user_id=customer_id,
                type=NotificationType.LOYALTY_REWARD_REDEEMED,
                channel=NotificationChannel.IN_APP,
                priority=NotificationPriority.NORMAL,
                title="Loyalty Reward Redeemed",
                message=(
                    f"You have successfully redeemed the loyalty reward "
                    f"'{reward.name}' for {reward.points_cost} points."
                ),
                related_entity_type="LOYALTY_REWARD_REDEMPTION",
                related_entity_id=redemption.id,
            )
        )

        # ------------------------------------------------------
        # Refresh Account
        # ------------------------------------------------------

        refreshed_account = (
            await self.loyalty_service.get_account(
                customer_id,
            )
        )

        return (
            redemption,
            reward,
            refreshed_account.points_balance,
            refreshed_account.tier,
        )

    # ==========================================================
    # Redemption Retrieval
    # ==========================================================

    async def get_redemption(
        self,
        redemption_id: int,
    ) -> LoyaltyRewardRedemption:
        """
        Retrieve a redemption by ID.
        """

        redemption = (
            await self.repository.get_redemption_by_id(
                redemption_id,
            )
        )

        if redemption is None:
            raise NotFoundException(
                "Loyalty reward redemption not found.",
            )

        return redemption

    async def get_redemption_by_reference(
        self,
        redemption_reference: str,
    ) -> LoyaltyRewardRedemption:
        """
        Retrieve a redemption by its unique reference.
        """

        redemption = (
            await self.repository.get_redemption_by_reference(
                redemption_reference,
            )
        )

        if redemption is None:
            raise NotFoundException(
                "Loyalty reward redemption not found.",
            )

        return redemption

    async def redemption_exists(
        self,
        redemption_reference: str,
    ) -> bool:
        """
        Determine whether a redemption reference exists.
        """

        return await self.repository.redemption_exists(
            redemption_reference,
        )

    # ==========================================================
    # Customer Redemption History
    # ==========================================================

    async def get_customer_redemptions(
        self,
        customer_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyRewardRedemption]:
        """
        Retrieve reward redemption history for a customer.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        return await self.repository.get_customer_redemptions(
            loyalty_account_id=account.id,
            limit=limit,
            offset=offset,
        )

    async def get_customer_redemptions_by_status(
        self,
        customer_id: int,
        status: RewardRedemptionStatus,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyRewardRedemption]:
        """
        Retrieve customer redemption history filtered
        by redemption status.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        return (
            await self.repository
            .get_customer_redemptions_by_status(
                loyalty_account_id=account.id,
                status=status,
                limit=limit,
                offset=offset,
            )
        )

    async def count_customer_redemptions(
        self,
        customer_id: int,
    ) -> int:
        """
        Count all reward redemptions belonging to
        a customer.
        """

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        return await self.repository.count_customer_redemptions(
            loyalty_account_id=account.id,
        )

    # ==========================================================
    # Reward Redemption History
    # ==========================================================

    async def get_reward_redemptions(
        self,
        reward_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyRewardRedemption]:
        """
        Retrieve redemption history for a specific reward.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        await self.get_reward(
            reward_id,
        )

        return await self.repository.get_redemptions_for_reward(
            reward_id=reward_id,
            limit=limit,
            offset=offset,
        )

    async def count_reward_redemptions(
        self,
        reward_id: int,
    ) -> int:
        """
        Count redemptions for a specific reward.
        """

        await self.get_reward(
            reward_id,
        )

        return await self.repository.count_redemptions_for_reward(
            reward_id=reward_id,
        )

    # ==========================================================
    # Redemption Status
    # ==========================================================

    async def get_active_redemption(
        self,
        redemption_id: int,
    ) -> LoyaltyRewardRedemption:
        """
        Retrieve a currently redeemed reward redemption.
        """

        redemption = (
            await self.repository.get_active_redemption(
                redemption_id,
            )
        )

        if redemption is None:
            raise NotFoundException(
                "Active reward redemption not found.",
            )

        return redemption

    # ==========================================================
    # Validation Helpers
    # ==========================================================

    @staticmethod
    def _validate_pagination(
        *,
        limit: int,
        offset: int,
    ) -> None:
        """
        Validate pagination parameters.
        """

        if limit < 1:
            raise BadRequestException(
                "Limit must be greater than zero.",
            )

        if offset < 0:
            raise BadRequestException(
                "Offset cannot be negative.",
            )

    @staticmethod
    def _validate_reward_values(
        *,
        name: str,
        points_cost: int,
        monetary_value,
        valid_from: datetime | None,
        valid_until: datetime | None,
    ) -> None:
        """
        Validate reward creation values.
        """

        if not name or not name.strip():
            raise BadRequestException(
                "Reward name cannot be empty.",
            )

        if points_cost <= 0:
            raise BadRequestException(
                "Reward points cost must be greater than zero.",
            )

        if monetary_value is not None and monetary_value < 0:
            raise BadRequestException(
                "Reward monetary value cannot be negative.",
            )

        LoyaltyRewardService._validate_validity_period(
            valid_from=valid_from,
            valid_until=valid_until,
        )

    @staticmethod
    def _validate_validity_period(
        *,
        valid_from: datetime | None,
        valid_until: datetime | None,
    ) -> None:
        """
        Ensure reward validity dates are logically ordered.
        """

        if (
            valid_from is not None
            and valid_until is not None
            and valid_until < valid_from
        ):
            raise BadRequestException(
                "Reward valid_until cannot be earlier "
                "than valid_from.",
            )

    @staticmethod
    def _is_reward_valid(
        reward: LoyaltyReward,
    ) -> bool:
        """
        Determine whether a reward is currently within
        its validity period.

        NULL valid_from means no start restriction.

        NULL valid_until means no expiry restriction.
        """

        now = datetime.now(
            timezone.utc,
        )

        if reward.valid_from is not None:
            valid_from = reward.valid_from

            if valid_from.tzinfo is None:
                now_for_comparison = now.replace(
                    tzinfo=None,
                )
            else:
                now_for_comparison = now

            if now_for_comparison < valid_from:
                return False

        if reward.valid_until is not None:
            valid_until = reward.valid_until

            if valid_until.tzinfo is None:
                now_for_comparison = now.replace(
                    tzinfo=None,
                )
            else:
                now_for_comparison = now

            if now_for_comparison > valid_until:
                return False

        return True

    def _validate_reward_available(
        self,
        reward: LoyaltyReward,
    ) -> None:
        """
        Validate that a reward is currently redeemable.
        """

        if reward.status != LoyaltyRewardStatus.ACTIVE:
            raise BadRequestException(
                "This loyalty reward is not active.",
            )

        if not reward.is_active:
            raise BadRequestException(
                "This loyalty reward is currently disabled.",
            )

        if not self._is_reward_valid(
            reward,
        ):
            raise BadRequestException(
                "This loyalty reward is outside its "
                "valid redemption period.",
            )

    @staticmethod
    def _is_tier_eligible(
        *,
        customer_tier: LoyaltyTier,
        minimum_tier: LoyaltyTier | None,
    ) -> bool:
        """
        Determine whether a customer's tier satisfies
        the reward's minimum tier requirement.

        Tier hierarchy:

            BRONZE < SILVER < GOLD < PLATINUM
        """

        if minimum_tier is None:
            return True

        tier_rank = {
            LoyaltyTier.BRONZE: 1,
            LoyaltyTier.SILVER: 2,
            LoyaltyTier.GOLD: 3,
            LoyaltyTier.PLATINUM: 4,
        }

        return (
            tier_rank[customer_tier]
            >= tier_rank[minimum_tier]
        )

    @staticmethod
    def _generate_redemption_reference() -> str:
        """
        Generate a unique redemption reference.

        Example:

            SPR-REWARD-7F8A9C123456
        """

        return (
            "SPR-REWARD-"
            f"{uuid4().hex[:12].upper()}"
        )