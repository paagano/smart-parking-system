"""
Loyalty Coupon Service.

Contains business logic for the SmartPark Loyalty Coupon
Programme.

Responsibilities
----------------
- Coupon creation
- Coupon retrieval
- Customer coupon retrieval
- Coupon validation
- Coupon usage
- Coupon status management
- Coupon history
- Coupon pagination
- Coupon statistics

Persistence is delegated to LoyaltyCouponRepository.

Loyalty account ownership is resolved through LoyaltyService.

Business rules belong in this service.
Database access belongs in the repository.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.handlers import (
    BadRequestException,
    NotFoundException,
)

from app.models.enums import (
    CouponStatus,
    CouponType,
)

from app.models.loyalty_coupon import (
    LoyaltyCoupon,
)

from app.repositories.loyalty_coupon_repository import (
    LoyaltyCouponRepository,
)

from app.services.loyalty_service import (
    LoyaltyService,
)


class LoyaltyCouponService:
    """
    Service responsible for SmartPark Loyalty Coupon
    business logic.
    """

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        db: AsyncSession,
        repository: LoyaltyCouponRepository,
        loyalty_service: LoyaltyService,
    ) -> None:
        """
        Create a LoyaltyCouponService instance.
        """

        self.db = db
        self.repository = repository
        self.loyalty_service = loyalty_service

    # ==========================================================
    # Pagination Validation
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

    # ==========================================================
    # Coupon Code
    # ==========================================================

    @staticmethod
    def _generate_coupon_code() -> str:
        """
        Generate a unique SmartPark coupon code.

        Database uniqueness remains the final protection
        against collisions.
        """

        return (
            f"SP-COUPON-"
            f"{uuid4().hex[:12].upper()}"
        )

    # ==========================================================
    # Date Helpers
    # ==========================================================

    @staticmethod
    def _now() -> datetime:
        """
        Return the current UTC datetime.
        """

        return datetime.now(
            timezone.utc,
        )

    @staticmethod
    def _is_datetime_expired(
        value: datetime | None,
        *,
        now: datetime,
    ) -> bool:
        """
        Determine whether a datetime has expired.

        Handles both timezone-aware and timezone-naive
        database values.
        """

        if value is None:
            return False

        if value.tzinfo is None:
            comparison_now = now.replace(
                tzinfo=None,
            )
        else:
            comparison_now = now

        return comparison_now > value

    @staticmethod
    def _is_coupon_within_validity_period(
        coupon: LoyaltyCoupon,
        *,
        now: datetime,
    ) -> bool:
        """
        Determine whether a coupon is currently within
        its configured validity period.
        """

        if coupon.valid_from is not None:
            if coupon.valid_from.tzinfo is None:
                comparison_now = now.replace(
                    tzinfo=None,
                )
            else:
                comparison_now = now

            if comparison_now < coupon.valid_from:
                return False

        if coupon.valid_until is not None:
            if coupon.valid_until.tzinfo is None:
                comparison_now = now.replace(
                    tzinfo=None,
                )
            else:
                comparison_now = now

            if comparison_now > coupon.valid_until:
                return False

        return True

    # ==========================================================
    # Coupon Validation Rules
    # ==========================================================

    @staticmethod
    def _validate_validity_period(
        *,
        valid_from: datetime | None,
        valid_until: datetime | None,
    ) -> None:
        """
        Ensure coupon validity dates are logically ordered.
        """

        if (
            valid_from is not None
            and valid_until is not None
            and valid_until < valid_from
        ):
            raise BadRequestException(
                "Coupon valid_until cannot be earlier "
                "than valid_from.",
            )

    @staticmethod
    def _validate_coupon_benefit(
        *,
        coupon_type: CouponType,
        value: Decimal | None,
        free_parking_minutes: int | None,
    ) -> None:
        """
        Validate the benefit configuration for a coupon.
        """

        discount_types = {
            CouponType.PERCENTAGE_DISCOUNT,
            CouponType.FIXED_AMOUNT_DISCOUNT,
        }

        if coupon_type in discount_types:
            if value is None:
                raise BadRequestException(
                    "Coupon value is required for "
                    "discount coupons.",
                )

            if value <= 0:
                raise BadRequestException(
                    "Coupon value must be greater than zero "
                    "for discount coupons.",
                )

        if coupon_type == CouponType.PERCENTAGE_DISCOUNT:
            if value is not None and value > 100:
                raise BadRequestException(
                    "Percentage discount cannot exceed 100.",
                )

        if coupon_type == CouponType.FREE_PARKING_HOURS:
            if free_parking_minutes is None:
                raise BadRequestException(
                    "Free parking minutes are required for "
                    "FREE_PARKING_HOURS coupons.",
                )

            if free_parking_minutes <= 0:
                raise BadRequestException(
                    "Free parking minutes must be greater "
                    "than zero.",
                )

    # ==========================================================
    # Coupon Creation
    # ==========================================================

    async def create_coupon(
        self,
        *,
        customer_id: int,
        coupon_type: CouponType,
        value: Decimal | None = None,
        free_parking_minutes: int | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        description: str | None = None,
        coupon_code: str | None = None,
        reward_redemption_id: int | None = None,
    ) -> LoyaltyCoupon:
        """
        Create a loyalty coupon for a customer.

        Customer ownership is resolved through the customer's
        LoyaltyAccount.

        This method does not allow the caller to directly
        supply loyalty_account_id.
        """

        self._validate_coupon_benefit(
            coupon_type=coupon_type,
            value=value,
            free_parking_minutes=free_parking_minutes,
        )

        self._validate_validity_period(
            valid_from=valid_from,
            valid_until=valid_until,
        )

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        if not account.is_active:
            raise BadRequestException(
                "Customer loyalty account is inactive.",
            )

        if coupon_code is None:
            coupon_code = self._generate_coupon_code()
        else:
            coupon_code = coupon_code.strip()

            if not coupon_code:
                raise BadRequestException(
                    "Coupon code cannot be empty.",
                )

            if await self.repository.exists_by_code(
                coupon_code,
            ):
                raise BadRequestException(
                    "Coupon code already exists.",
                )

        coupon = LoyaltyCoupon(
            coupon_code=coupon_code,
            loyalty_account_id=account.id,
            reward_redemption_id=reward_redemption_id,
            coupon_type=coupon_type,
            value=value,
            free_parking_minutes=free_parking_minutes,
            status=CouponStatus.ACTIVE,
            is_active=True,
            valid_from=valid_from,
            valid_until=valid_until,
            used_at=None,
            used_payment_transaction_id=None,
            description=description,
        )

        coupon = await self.repository.create(
            coupon,
        )

        await self.db.commit()

        await self.db.refresh(
            coupon,
        )

        return coupon

    # ==========================================================
    # Coupon Retrieval
    # ==========================================================

    async def get_coupon(
        self,
        coupon_id: int,
    ) -> LoyaltyCoupon:
        """
        Retrieve a coupon by ID.

        Raises NotFoundException when the coupon does not
        exist.
        """

        coupon = await self.repository.get_by_id(
            coupon_id,
        )

        if coupon is None:
            raise NotFoundException(
                "Loyalty coupon not found.",
            )

        return coupon

    async def get_coupon_by_code(
        self,
        coupon_code: str,
    ) -> LoyaltyCoupon:
        """
        Retrieve a coupon by its unique code.
        """

        coupon_code = coupon_code.strip()

        if not coupon_code:
            raise BadRequestException(
                "Coupon code cannot be empty.",
            )

        coupon = await self.repository.get_by_code(
            coupon_code,
        )

        if coupon is None:
            raise NotFoundException(
                "Loyalty coupon not found.",
            )

        return coupon

    # ==========================================================
    # Customer Coupon Ownership
    # ==========================================================

    async def get_customer_coupon(
        self,
        *,
        customer_id: int,
        coupon_id: int,
    ) -> LoyaltyCoupon:
        """
        Retrieve a coupon belonging to the authenticated
        customer's loyalty account.
        """

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        coupon = await self.repository.get_customer_coupon(
            loyalty_account_id=account.id,
            coupon_id=coupon_id,
        )

        if coupon is None:
            raise NotFoundException(
                "Loyalty coupon not found.",
            )

        return coupon

    async def get_customer_coupons(
        self,
        *,
        customer_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyCoupon]:
        """
        Retrieve coupons belonging to a customer.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        return await self.repository.get_customer_coupons(
            loyalty_account_id=account.id,
            limit=limit,
            offset=offset,
        )

    async def get_active_customer_coupons(
        self,
        *,
        customer_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyCoupon]:
        """
        Retrieve currently active coupons belonging to
        the customer.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        coupons = (
            await self.repository.get_active_customer_coupons(
                loyalty_account_id=account.id,
                limit=limit,
                offset=offset,
            )
        )

        now = self._now()

        return [
            coupon
            for coupon in coupons
            if self._is_coupon_within_validity_period(
                coupon,
                now=now,
            )
        ]

    # ==========================================================
    # Customer Coupon Status
    # ==========================================================

    async def get_customer_coupons_by_status(
        self,
        *,
        customer_id: int,
        status: CouponStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyCoupon]:
        """
        Retrieve customer coupons filtered by status.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        return (
            await self.repository.get_customer_coupons_by_status(
                loyalty_account_id=account.id,
                status=status,
                limit=limit,
                offset=offset,
            )
        )

    async def get_customer_coupons_by_type(
        self,
        *,
        customer_id: int,
        coupon_type: CouponType,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyCoupon]:
        """
        Retrieve customer coupons filtered by coupon type.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        return (
            await self.repository.get_customer_coupons_by_type(
                loyalty_account_id=account.id,
                coupon_type=coupon_type,
                limit=limit,
                offset=offset,
            )
        )

    # ==========================================================
    # Coupon Validation
    # ==========================================================

    async def validate_coupon(
        self,
        *,
        customer_id: int,
        coupon_code: str,
    ) -> LoyaltyCoupon:
        """
        Validate that a coupon can currently be used by
        the authenticated customer.

        The coupon is NOT consumed by this method.
        """

        coupon = await self.get_coupon_by_code(
            coupon_code,
        )

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        if coupon.loyalty_account_id != account.id:
            raise BadRequestException(
                "This coupon does not belong to the "
                "authenticated customer.",
            )

        self._validate_coupon_usable(
            coupon,
        )

        return coupon

    def _validate_coupon_usable(
        self,
        coupon: LoyaltyCoupon,
    ) -> None:
        """
        Validate that a coupon is currently usable.
        """

        if coupon.status != CouponStatus.ACTIVE:
            raise BadRequestException(
                "This loyalty coupon is not active.",
            )

        if not coupon.is_active:
            raise BadRequestException(
                "This loyalty coupon is currently disabled.",
            )

        now = self._now()

        if (
            coupon.valid_from is not None
            and coupon.valid_from.tzinfo is None
        ):
            comparison_now = now.replace(
                tzinfo=None,
            )
        else:
            comparison_now = now

        if (
            coupon.valid_from is not None
            and comparison_now < coupon.valid_from
        ):
            raise BadRequestException(
                "This loyalty coupon is not yet valid.",
            )

        if coupon.valid_until is not None:
            if coupon.valid_until.tzinfo is None:
                comparison_now = now.replace(
                    tzinfo=None,
                )
            else:
                comparison_now = now

            if comparison_now > coupon.valid_until:
                raise BadRequestException(
                    "This loyalty coupon has expired.",
                )

    # ==========================================================
    # Coupon Usage
    # ==========================================================

    async def use_coupon(
        self,
        *,
        customer_id: int,
        coupon_code: str,
        payment_transaction_id: int,
    ) -> LoyaltyCoupon:
        """
        Apply a loyalty coupon to a payment transaction.

        The coupon is marked as USED only after all business
        validations have succeeded.
        """

        if payment_transaction_id <= 0:
            raise BadRequestException(
                "Payment transaction ID must be greater "
                "than zero.",
            )

        coupon = await self.validate_coupon(
            customer_id=customer_id,
            coupon_code=coupon_code,
        )

        # ------------------------------------------------------
        # Prevent accidental duplicate application
        # ------------------------------------------------------

        if (
            coupon.used_payment_transaction_id
            == payment_transaction_id
        ):
            return coupon

        if coupon.used_payment_transaction_id is not None:
            raise BadRequestException(
                "This loyalty coupon has already been used.",
            )

        # ------------------------------------------------------
        # Mark coupon as used
        # ------------------------------------------------------

        coupon.status = CouponStatus.USED
        coupon.is_active = False
        coupon.used_at = self._now()
        coupon.used_payment_transaction_id = (
            payment_transaction_id
        )

        coupon = await self.repository.mark_as_used(
            coupon=coupon,
        )

        await self.db.commit()

        await self.db.refresh(
            coupon,
        )

        return coupon

    # ==========================================================
    # Coupon Update
    # ==========================================================

    async def update_coupon(
        self,
        coupon_id: int,
        *,
        coupon_type: CouponType | None = None,
        value: Decimal | None = None,
        free_parking_minutes: int | None = None,
        status: CouponStatus | None = None,
        is_active: bool | None = None,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        description: str | None = None,
    ) -> LoyaltyCoupon:
        """
        Update an existing loyalty coupon.

        Intended primarily for administrative operations.
        """

        coupon = await self.get_coupon(
            coupon_id,
        )

        new_coupon_type = (
            coupon_type
            if coupon_type is not None
            else coupon.coupon_type
        )

        new_value = (
            value
            if value is not None
            else coupon.value
        )

        new_free_parking_minutes = (
            free_parking_minutes
            if free_parking_minutes is not None
            else coupon.free_parking_minutes
        )

        new_valid_from = (
            valid_from
            if valid_from is not None
            else coupon.valid_from
        )

        new_valid_until = (
            valid_until
            if valid_until is not None
            else coupon.valid_until
        )

        self._validate_coupon_benefit(
            coupon_type=new_coupon_type,
            value=new_value,
            free_parking_minutes=(
                new_free_parking_minutes
            ),
        )

        self._validate_validity_period(
            valid_from=new_valid_from,
            valid_until=new_valid_until,
        )

        if coupon_type is not None:
            coupon.coupon_type = coupon_type

        if value is not None:
            coupon.value = value

        if free_parking_minutes is not None:
            coupon.free_parking_minutes = (
                free_parking_minutes
            )

        if status is not None:
            coupon.status = status

        if is_active is not None:
            coupon.is_active = is_active

        if valid_from is not None:
            coupon.valid_from = valid_from

        if valid_until is not None:
            coupon.valid_until = valid_until

        if description is not None:
            coupon.description = description

        coupon = await self.repository.update(
            coupon,
        )

        await self.db.commit()

        await self.db.refresh(
            coupon,
        )

        return coupon

    # ==========================================================
    # Coupon Status
    # ==========================================================

    async def update_coupon_status(
        self,
        coupon_id: int,
        *,
        status: CouponStatus,
        is_active: bool | None = None,
    ) -> LoyaltyCoupon:
        """
        Update a coupon's status.
        """

        coupon = await self.get_coupon(
            coupon_id,
        )

        coupon.status = status

        if is_active is not None:
            coupon.is_active = is_active
        elif status != CouponStatus.ACTIVE:
            coupon.is_active = False

        coupon = await self.repository.update(
            coupon,
        )

        await self.db.commit()

        await self.db.refresh(
            coupon,
        )

        return coupon

    # ==========================================================
    # Reward Redemption Lookup
    # ==========================================================

    async def get_coupon_by_reward_redemption(
        self,
        reward_redemption_id: int,
    ) -> LoyaltyCoupon:
        """
        Retrieve the coupon generated from a reward
        redemption.
        """

        coupon = (
            await self.repository.get_by_reward_redemption(
                reward_redemption_id,
            )
        )

        if coupon is None:
            raise NotFoundException(
                "Loyalty coupon for the reward redemption "
                "was not found.",
            )

        return coupon

    # ==========================================================
    # Payment Transaction Lookup
    # ==========================================================

    async def get_coupon_by_payment_transaction(
        self,
        payment_transaction_id: int,
    ) -> LoyaltyCoupon:
        """
        Retrieve the coupon associated with a payment
        transaction.
        """

        coupon = (
            await self.repository.get_by_payment_transaction(
                payment_transaction_id,
            )
        )

        if coupon is None:
            raise NotFoundException(
                "No loyalty coupon is associated with "
                "this payment transaction.",
            )

        return coupon

    # ==========================================================
    # General Coupon Queries
    # ==========================================================

    async def get_all_coupons(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyCoupon]:
        """
        Retrieve all loyalty coupons.

        Intended primarily for administrative operations.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return await self.repository.get_all(
            limit=limit,
            offset=offset,
        )

    async def get_coupons_by_status(
        self,
        *,
        status: CouponStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyCoupon]:
        """
        Retrieve coupons by status.

        Intended primarily for administrative operations.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return await self.repository.get_by_status(
            status=status,
            limit=limit,
            offset=offset,
        )

    async def get_coupons_by_type(
        self,
        *,
        coupon_type: CouponType,
        limit: int = 100,
        offset: int = 0,
    ) -> list[LoyaltyCoupon]:
        """
        Retrieve coupons by type.

        Intended primarily for administrative operations.
        """

        self._validate_pagination(
            limit=limit,
            offset=offset,
        )

        return await self.repository.get_by_type(
            coupon_type=coupon_type,
            limit=limit,
            offset=offset,
        )

    # ==========================================================
    # Counts
    # ==========================================================

    async def count_all_coupons(
        self,
    ) -> int:
        """
        Return total loyalty coupon count.
        """

        return await self.repository.count_all()

    async def count_customer_coupons(
        self,
        *,
        customer_id: int,
    ) -> int:
        """
        Return total coupon count for a customer.
        """

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        return await self.repository.count_customer_coupons(
            loyalty_account_id=account.id,
        )

    async def count_customer_coupons_by_status(
        self,
        *,
        customer_id: int,
        status: CouponStatus,
    ) -> int:
        """
        Return customer coupon count filtered by status.
        """

        account = await self.loyalty_service.get_account(
            customer_id,
        )

        return (
            await self.repository
            .count_customer_coupons_by_status(
                loyalty_account_id=account.id,
                status=status,
            )
        )

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete_coupon(
        self,
        coupon_id: int,
    ) -> None:
        """
        Delete a loyalty coupon.

        Intended for administrative operations.

        Used coupons should normally be retained for audit
        purposes rather than deleted.
        """

        coupon = await self.get_coupon(
            coupon_id,
        )

        if coupon.status == CouponStatus.USED:
            raise BadRequestException(
                "Used loyalty coupons cannot be deleted.",
            )

        await self.repository.delete(
            coupon,
        )

        await self.db.commit()