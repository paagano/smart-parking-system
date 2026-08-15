"""
Loyalty Referral Service.

Contains business logic for the SmartPark Loyalty Referral
Programme.

Responsibilities
----------------
- Referral creation
- Referral-code validation
- Referral retrieval
- Customer referral history
- Referral qualification
- Referral reward processing
- Referral cancellation
- Referral status management
- Referral statistics

Persistence is delegated to LoyaltyReferralRepository.

Loyalty point balance manipulation is delegated to
LoyaltyService.

Business rules belong in this service.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.handlers import (
    BadRequestException,
    NotFoundException,
)

from app.models.enums import (
    LoyaltyPointTransactionType,
    NotificationChannel,
    NotificationPriority,
    NotificationType,
    ReferralStatus,
)

from app.models.loyalty_referral import (
    LoyaltyReferral,
)

from app.models.user import User

from app.schemas.notification import (
    NotificationCreateInternal,
)

from app.repositories.loyalty_referral_repository import (
    LoyaltyReferralRepository,
)

from app.services.loyalty_service import (
    LoyaltyService,
)

from app.services.notification_service import (
    NotificationService,
)


class LoyaltyReferralService:
    """
    Service responsible for SmartPark Loyalty Referral
    business logic.
    """

    # ==========================================================
    # Referral Programme Configuration
    # ==========================================================

    DEFAULT_REWARD_POINTS = 100

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        db: AsyncSession,
        repository: LoyaltyReferralRepository,
        loyalty_service: LoyaltyService,
        notification_service: NotificationService,
    ) -> None:
        """
        Create a LoyaltyReferralService instance.
        """

        self.db = db
        self.repository = repository
        self.loyalty_service = loyalty_service
        self.notification_service = notification_service

    # ==========================================================
    # Referral Creation
    # ==========================================================

    async def create_referral(
        self,
        *,
        referrer_id: int,
        referred_id: int,
        referral_code: str,
        reward_points: int = DEFAULT_REWARD_POINTS,
        notes: str | None = None,
    ) -> LoyaltyReferral:
        """
        Create a new loyalty referral.

        The authenticated customer should normally be supplied
        as referrer_id by the API layer.

        Business rules:
        - Referrer and referred customer cannot be the same.
        - Referred customer must exist.
        - Referrer must exist.
        - Referral code must be unique.
        - Referred customer cannot have another pending referral.
        - Reward points cannot be negative.

        Raises
        ------
        BadRequestException
            If the referral violates business rules.

        NotFoundException
            If either customer does not exist.
        """

        # ------------------------------------------------------
        # Basic Validation
        # ------------------------------------------------------

        if referrer_id <= 0:
            raise BadRequestException(
                "Invalid referrer customer ID.",
            )

        if referred_id <= 0:
            raise BadRequestException(
                "Invalid referred customer ID.",
            )

        if referrer_id == referred_id:
            raise BadRequestException(
                "A customer cannot refer themselves.",
            )

        if not referral_code or not referral_code.strip():
            raise BadRequestException(
                "Referral code is required.",
            )

        referral_code = referral_code.strip().upper()

        if reward_points < 0:
            raise BadRequestException(
                "Referral reward points cannot be negative.",
            )

        # ------------------------------------------------------
        # Validate Referrer
        # ------------------------------------------------------

        referrer_result = await self.db.execute(
            select(User).where(
                User.id == referrer_id,
            )
        )

        referrer = (
            referrer_result.scalar_one_or_none()
        )

        if referrer is None:
            raise NotFoundException(
                "Referrer customer not found.",
            )

        if not referrer.is_active:
            raise BadRequestException(
                "Referrer customer is inactive.",
            )

        # ------------------------------------------------------
        # Validate Referred Customer
        # ------------------------------------------------------

        referred_result = await self.db.execute(
            select(User).where(
                User.id == referred_id,
            )
        )

        referred = (
            referred_result.scalar_one_or_none()
        )

        if referred is None:
            raise NotFoundException(
                "Referred customer not found.",
            )

        if not referred.is_active:
            raise BadRequestException(
                "Referred customer is inactive.",
            )

        # ------------------------------------------------------
        # Referral Code Uniqueness
        # ------------------------------------------------------

        existing_code = (
            await self.repository.get_by_code(
                referral_code,
            )
        )

        if existing_code is not None:
            raise BadRequestException(
                "Referral code already exists.",
            )

        # ------------------------------------------------------
        # Existing Pending Referral
        # ------------------------------------------------------

        pending_referral = (
            await self.repository
            .get_pending_for_referred_customer(
                referred_id,
            )
        )

        if pending_referral is not None:
            raise BadRequestException(
                "The referred customer already has "
                "a pending referral.",
            )

        # ------------------------------------------------------
        # Create Referral
        # ------------------------------------------------------

        referral = LoyaltyReferral(
            referrer_id=referrer_id,
            referred_id=referred_id,
            referral_code=referral_code,
            status=ReferralStatus.PENDING,
            reward_points=reward_points,
            notes=notes,
        )

        referral = await self.repository.save(
            referral,
        )

        await self.db.commit()

        await self.db.refresh(
            referral,
        )

        return referral

    # ==========================================================
    # Referral Retrieval
    # ==========================================================

    async def get_referral(
        self,
        referral_id: int,
    ) -> LoyaltyReferral:
        """
        Retrieve a referral by ID.

        Raises
        ------
        NotFoundException
            If the referral does not exist.
        """

        referral = await self.repository.get_by_id(
            referral_id,
        )

        if referral is None:
            raise NotFoundException(
                "Loyalty referral not found.",
            )

        return referral

    # ==========================================================
    # Referral Code
    # ==========================================================

    async def get_referral_by_code(
        self,
        referral_code: str,
    ) -> LoyaltyReferral:
        """
        Retrieve a referral by referral code.
        """

        referral_code = (
            referral_code.strip().upper()
        )

        referral = (
            await self.repository.get_by_code(
                referral_code,
            )
        )

        if referral is None:
            raise NotFoundException(
                "Loyalty referral not found.",
            )

        return referral

    # ==========================================================
    # Referral Code Validation
    # ==========================================================

    async def validate_referral_code(
        self,
        *,
        customer_id: int,
        referral_code: str,
    ) -> tuple[
        LoyaltyReferral | None,
        bool,
        bool,
        bool,
        str | None,
    ]:
        """
        Validate a referral code for a customer.

        Returns
        -------
        tuple
            (
                referral,
                valid,
                referral_code_exists,
                referral_is_active,
                reason,
            )

        Validation rules
        ----------------
        A referral code is valid when:

        - The customer ID is valid.
        - The referral code exists.
        - The referral is PENDING.
        - The customer is not the referrer.
        - The referral belongs to the customer being validated,
          OR the referral is available for that customer to claim.
        - The customer does not already have another pending
          referral.

        Important:
        The referral returned by get_by_code() is itself a pending
        referral for the referred customer. Therefore, when checking
        whether the customer already has a pending referral, the
        current referral must be excluded from that check.
        """

        # ------------------------------------------------------
        # Basic Validation
        # ------------------------------------------------------

        if customer_id <= 0:
            raise BadRequestException(
                "Invalid customer ID.",
            )

        referral_code = (
            referral_code.strip().upper()
        )

        if not referral_code:
            raise BadRequestException(
                "Referral code is required.",
            )

        # ------------------------------------------------------
        # Find Referral
        # ------------------------------------------------------

        referral = (
            await self.repository.get_by_code(
                referral_code,
            )
        )

        # ------------------------------------------------------
        # Referral Does Not Exist
        # ------------------------------------------------------

        if referral is None:
            return (
                None,
                False,
                False,
                False,
                "Referral code does not exist.",
            )

        # ------------------------------------------------------
        # Referral Status
        # ------------------------------------------------------

        if referral.status != ReferralStatus.PENDING:
            return (
                referral,
                False,
                True,
                False,
                "Referral is no longer active.",
            )

        # ------------------------------------------------------
        # Self Referral
        # ------------------------------------------------------

        if referral.referrer_id == customer_id:
            return (
                referral,
                False,
                True,
                True,
                "A customer cannot use their own referral code.",
            )

        # ------------------------------------------------------
        # Existing Pending Referral
        # ------------------------------------------------------

        existing_pending = (
            await self.repository
            .get_pending_for_referred_customer(
                customer_id,
            )
        )

        # IMPORTANT:
        #
        # The query above will normally return the referral we
        # have just found because the referral is already pending
        # for this customer.
        #
        # That referral must NOT invalidate itself.
        #
        # Only reject the validation when another pending referral
        # exists for the same customer.

        if (
            existing_pending is not None
            and existing_pending.id != referral.id
        ):
            return (
                referral,
                False,
                True,
                True,
                "Customer already has a pending referral.",
            )

        # ------------------------------------------------------
        # Valid Referral
        # ------------------------------------------------------

        return (
            referral,
            True,
            True,
            True,
            None,
        )

        # ------------------------------------------------------
        # Referral Status
        # ------------------------------------------------------

        if referral.status != ReferralStatus.PENDING:
            return (
                referral,
                False,
                True,
                False,
                "Referral is no longer active.",
            )

        # ------------------------------------------------------
        # Self Referral
        # ------------------------------------------------------

        if referral.referrer_id == customer_id:
            return (
                referral,
                False,
                True,
                True,
                "A customer cannot use their own referral code.",
            )

        # ------------------------------------------------------
        # Customer Already Referred
        # ------------------------------------------------------

        existing_pending = (
            await self.repository
            .get_pending_for_referred_customer(
                customer_id,
            )
        )

        if existing_pending is not None:
            return (
                referral,
                False,
                True,
                True,
                "Customer already has a pending referral.",
            )

        # ------------------------------------------------------
        # Valid
        # ------------------------------------------------------

        return (
            referral,
            True,
            True,
            True,
            None,
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
        Retrieve referral history for a customer.

        The customer may appear either as:
        - referrer
        - referred customer
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return (
            await self.repository
            .get_customer_referrals(
                customer_id,
                limit=limit,
                offset=offset,
            )
        )

    # ==========================================================
    # Referrals Created By Customer
    # ==========================================================

    async def get_referrer_referrals(
        self,
        customer_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve referrals created by a customer.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return (
            await self.repository.get_by_referrer(
                customer_id,
                limit=limit,
                offset=offset,
            )
        )

    # ==========================================================
    # Referral Associated With Customer
    # ==========================================================

    async def get_referred_customer_referrals(
        self,
        customer_id: int,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve referrals where the customer is the
        referred customer.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return (
            await self.repository
            .get_by_referred_customer(
                customer_id,
                limit=limit,
                offset=offset,
            )
        )

    # ==========================================================
    # All Referrals
    # ==========================================================

    async def get_all_referrals(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve all referrals.

        Intended primarily for administrative use.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return await self.repository.get_all(
            limit=limit,
            offset=offset,
        )

    # ==========================================================
    # Status Queries
    # ==========================================================

    async def get_referrals_by_status(
        self,
        referral_status: ReferralStatus,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyReferral]:
        """
        Retrieve referrals by status.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return await self.repository.get_by_status(
            referral_status,
            limit=limit,
            offset=offset,
        )

    # ==========================================================
    # Active Referral
    # ==========================================================

    async def get_active_referral(
        self,
        referral_id: int,
    ) -> LoyaltyReferral:
        """
        Retrieve an active referral.

        Active referrals are:
        - PENDING
        - QUALIFIED
        """

        referral = (
            await self.repository.get_active_by_id(
                referral_id,
            )
        )

        if referral is None:
            raise NotFoundException(
                "Active loyalty referral not found.",
            )

        return referral

    # ==========================================================
    # Qualification
    # ==========================================================

    async def qualify_referral(
        self,
        *,
        referral_id: int,
    ) -> LoyaltyReferral:
        """
        Qualify a pending referral.

        A referral may only transition:

            PENDING → QUALIFIED

        The referral is NOT rewarded by this operation.
        """

        referral = await self.get_referral(
            referral_id,
        )

        if referral.status != ReferralStatus.PENDING:
            raise BadRequestException(
                "Only pending referrals can be qualified.",
            )

        referral.status = ReferralStatus.QUALIFIED

        referral.qualified_at = datetime.now(
            timezone.utc,
        )

        referral = await self.repository.update(
            referral,
        )

        await self.db.commit()

        await self.db.refresh(
            referral,
        )

        # ------------------------------------------------------
        # Loyalty Referral Qualified Notification
        # ------------------------------------------------------

        await self.notification_service.create_notification(
            NotificationCreateInternal(
                user_id=referral.referrer_id,
                type=NotificationType.LOYALTY_REFERRAL_QUALIFIED,
                channel=NotificationChannel.IN_APP,
                priority=NotificationPriority.NORMAL,
                title="Referral Qualified",
                message=(
                    f"Your referral {referral.referral_code} "
                    f"has been successfully qualified."
                ),
                related_entity_type="LOYALTY_REFERRAL",
                related_entity_id=referral.id,
            )
        )

        return referral

    # ==========================================================
    # Reward Referral
    # ==========================================================

    async def reward_referral(
        self,
        *,
        referral_id: int,
    ) -> LoyaltyReferral:
        """
        Reward a qualified referral.

        A referral may only transition:

            QUALIFIED → REWARDED

        The configured reward points are awarded to the
        referrer through LoyaltyService.

        The loyalty ledger reference is the referral ID,
        providing idempotency.
        """

        referral = await self.get_referral(
            referral_id,
        )

        if referral.status != ReferralStatus.QUALIFIED:
            raise BadRequestException(
                "Only qualified referrals can be rewarded.",
            )

        if referral.reward_points <= 0:
            raise BadRequestException(
                "Referral reward points must be greater "
                "than zero before rewarding.",
            )

        # ------------------------------------------------------
        # Award Points to Referrer
        # ------------------------------------------------------

        await self.loyalty_service.award_points(
            customer_id=referral.referrer_id,
            points=referral.reward_points,
            transaction_type=(
                LoyaltyPointTransactionType.REFERRAL
                if hasattr(
                    LoyaltyPointTransactionType,
                    "REFERRAL",
                )
                else LoyaltyPointTransactionType.EARN
            ),
            reference_type="LOYALTY_REFERRAL",
            reference_id=referral.id,
            description=(
                "Referral reward for "
                f"referral {referral.referral_code}."
            ),
        )

        # ------------------------------------------------------
        # Update Referral
        # ------------------------------------------------------

        referral.status = ReferralStatus.REWARDED

        referral.rewarded_at = datetime.now(
            timezone.utc,
        )

        referral = await self.repository.update(
            referral,
        )

        await self.db.commit()

        await self.db.refresh(
            referral,
        )

        # ------------------------------------------------------
        # Loyalty Referral Rewarded Notification
        # ------------------------------------------------------

        await self.notification_service.create_notification(
            NotificationCreateInternal(
                user_id=referral.referrer_id,
                type=NotificationType.LOYALTY_REFERRAL_REWARDED,
                channel=NotificationChannel.IN_APP,
                priority=NotificationPriority.NORMAL,
                title="Referral Rewarded",
                message=(
                    f"Your referral {referral.referral_code} "
                    f"has been rewarded with "
                    f"{referral.reward_points} loyalty points."
                ),
                related_entity_type="LOYALTY_REFERRAL",
                related_entity_id=referral.id,
            )
        )

        return referral

    # ==========================================================
    # Cancel Referral
    # ==========================================================

    async def cancel_referral(
        self,
        *,
        referral_id: int,
        reason: str | None = None,
    ) -> LoyaltyReferral:
        """
        Cancel a referral.

        Pending or qualified referrals may be cancelled.

        Rewarded referrals cannot be cancelled because the
        loyalty points have already been awarded.
        """

        referral = await self.get_referral(
            referral_id,
        )

        if referral.status not in {
            ReferralStatus.PENDING,
            ReferralStatus.QUALIFIED,
        }:
            raise BadRequestException(
                "Only pending or qualified referrals "
                "can be cancelled.",
            )

        referral.status = ReferralStatus.CANCELLED

        referral.cancelled_at = datetime.now(
            timezone.utc,
        )

        if reason is not None:
            reason = reason.strip()

            if reason:
                referral.notes = reason

        referral = await self.repository.update(
            referral,
        )

        await self.db.commit()

        await self.db.refresh(
            referral,
        )

        # ------------------------------------------------------
        # Loyalty Referral Rewarded Notification
        # ------------------------------------------------------

        await self.notification_service.create_notification(
            NotificationCreateInternal(
                user_id=referral.referrer_id,
                type=NotificationType.LOYALTY_REFERRAL_REWARDED,
                channel=NotificationChannel.IN_APP,
                priority=NotificationPriority.NORMAL,
                title="Referral Rewarded",
                message=(
                    f"Your referral {referral.referral_code} "
                    f"has been rewarded with "
                    f"{referral.reward_points} loyalty points."
                ),
                related_entity_type="LOYALTY_REFERRAL",
                related_entity_id=referral.id,
            )
        )

        return referral

    # ==========================================================
    # Status Update
    # ==========================================================

    async def update_status(
        self,
        *,
        referral_id: int,
        status: ReferralStatus,
    ) -> LoyaltyReferral:
        """
        Update referral status through controlled lifecycle
        transitions.

        Supported transitions:

            PENDING → QUALIFIED
            PENDING → CANCELLED
            QUALIFIED → REWARDED
            QUALIFIED → CANCELLED

        REWARDED and CANCELLED are terminal states.
        """

        referral = await self.get_referral(
            referral_id,
        )

        current_status = referral.status

        # ------------------------------------------------------
        # No-Op
        # ------------------------------------------------------

        if current_status == status:
            return referral

        # ------------------------------------------------------
        # PENDING
        # ------------------------------------------------------

        if current_status == ReferralStatus.PENDING:

            if status == ReferralStatus.QUALIFIED:
                return await self.qualify_referral(
                    referral_id=referral_id,
                )

            if status == ReferralStatus.CANCELLED:
                return await self.cancel_referral(
                    referral_id=referral_id,
                )

            raise BadRequestException(
                "Invalid referral status transition "
                f"from {current_status.value} "
                f"to {status.value}.",
            )

        # ------------------------------------------------------
        # QUALIFIED
        # ------------------------------------------------------

        if current_status == ReferralStatus.QUALIFIED:

            if status == ReferralStatus.REWARDED:
                return await self.reward_referral(
                    referral_id=referral_id,
                )

            if status == ReferralStatus.CANCELLED:
                return await self.cancel_referral(
                    referral_id=referral_id,
                )

            raise BadRequestException(
                "Invalid referral status transition "
                f"from {current_status.value} "
                f"to {status.value}.",
            )

        # ------------------------------------------------------
        # Terminal States
        # ------------------------------------------------------

        raise BadRequestException(
            "Referral is already in a terminal state "
            f"({current_status.value}).",
        )

    # ==========================================================
    # Statistics
    # ==========================================================

    async def get_customer_statistics(
        self,
        customer_id: int,
    ) -> dict[str, int]:
        """
        Retrieve referral statistics for a customer.

        The statistics describe referrals where the customer
        is the referrer.
        """

        total = await self.repository.count_by_referrer(
            customer_id,
        )

        pending = (
            await self._count_referrer_by_status(
                customer_id=customer_id,
                status=ReferralStatus.PENDING,
            )
        )

        qualified = (
            await self._count_referrer_by_status(
                customer_id=customer_id,
                status=ReferralStatus.QUALIFIED,
            )
        )

        rewarded = (
            await self._count_referrer_by_status(
                customer_id=customer_id,
                status=ReferralStatus.REWARDED,
            )
        )

        cancelled = (
            await self._count_referrer_by_status(
                customer_id=customer_id,
                status=ReferralStatus.CANCELLED,
            )
        )

        total_reward_points = 0

        rewarded_referrals = (
            await self.repository.get_by_referrer(
                customer_id,
                limit=10000,
                offset=0,
            )
        )

        for referral in rewarded_referrals:
            if referral.status == ReferralStatus.REWARDED:
                total_reward_points += (
                    referral.reward_points
                )

        return {
            "total_referrals": total,
            "pending_referrals": pending,
            "qualified_referrals": qualified,
            "rewarded_referrals": rewarded,
            "cancelled_referrals": cancelled,
            "total_reward_points": total_reward_points,
        }

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

        if limit > 100:
            raise BadRequestException(
                "Limit cannot exceed 100.",
            )

        if offset < 0:
            raise BadRequestException(
                "Offset cannot be negative.",
            )

    # ==========================================================
    # Internal Status Count
    # ==========================================================

    async def _count_referrer_by_status(
        self,
        *,
        customer_id: int,
        status: ReferralStatus,
    ) -> int:
        """
        Count referrals belonging to a referrer for a
        particular status.

        This uses the repository's existing referrer query
        rather than introducing persistence logic into the
        service.
        """

        referrals = (
            await self.repository.get_by_referrer(
                customer_id,
                limit=10000,
                offset=0,
            )
        )

        return sum(
            1
            for referral in referrals
            if referral.status == status
        )

    # ==========================================================
    # Referral Code Generation
    # ==========================================================

    @staticmethod
    def generate_referral_code() -> str:
        """
        Generate a unique referral code.

        The generated code is suitable for use with
        create_referral().
        """

        return (
            "REF-"
            f"{uuid4().hex[:12].upper()}"
        )