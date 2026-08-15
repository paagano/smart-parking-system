"""
Loyalty Coupon Repository.

Persistence operations for the LoyaltyCoupon model.

Business rules belong in LoyaltyCouponService.
Database access and query construction belong here.
"""

from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import CouponStatus, CouponType
from app.models.loyalty_coupon import LoyaltyCoupon


class LoyaltyCouponRepository:
    """
    Repository for LoyaltyCoupon persistence operations.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        self.db = db

    # ==========================================================
    # Create
    # ==========================================================

    async def create(
        self,
        coupon: LoyaltyCoupon,
    ) -> LoyaltyCoupon:
        """
        Persist a new loyalty coupon.
        """

        self.db.add(coupon)

        await self.db.flush()
        await self.db.refresh(coupon)

        return coupon

    # ==========================================================
    # Get by ID
    # ==========================================================

    async def get_by_id(
        self,
        coupon_id: int,
    ) -> LoyaltyCoupon | None:
        """
        Retrieve a loyalty coupon by primary key.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon).where(
                LoyaltyCoupon.id == coupon_id
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Get by Coupon Code
    # ==========================================================

    async def get_by_code(
        self,
        coupon_code: str,
    ) -> LoyaltyCoupon | None:
        """
        Retrieve a loyalty coupon by its unique coupon code.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon).where(
                LoyaltyCoupon.coupon_code == coupon_code
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Coupon Existence
    # ==========================================================

    async def exists_by_code(
        self,
        coupon_code: str,
    ) -> bool:
        """
        Determine whether a coupon code already exists.
        """

        result = await self.db.execute(
            select(
                func.count(LoyaltyCoupon.id)
            ).where(
                LoyaltyCoupon.coupon_code == coupon_code
            )
        )

        return (result.scalar_one() or 0) > 0

    # ==========================================================
    # Get Customer Coupon
    # ==========================================================

    async def get_customer_coupon(
        self,
        *,
        loyalty_account_id: int,
        coupon_id: int,
    ) -> LoyaltyCoupon | None:
        """
        Retrieve a specific coupon belonging to a loyalty account.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon).where(
                LoyaltyCoupon.id == coupon_id,
                LoyaltyCoupon.loyalty_account_id
                == loyalty_account_id,
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Get Customer Coupons
    # ==========================================================

    async def get_customer_coupons(
        self,
        *,
        loyalty_account_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[LoyaltyCoupon]:
        """
        Retrieve coupons belonging to a loyalty account.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon)
            .where(
                LoyaltyCoupon.loyalty_account_id
                == loyalty_account_id
            )
            .order_by(
                LoyaltyCoupon.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )

        return result.scalars().all()

    # ==========================================================
    # Get Active Customer Coupons
    # ==========================================================

    async def get_active_customer_coupons(
        self,
        *,
        loyalty_account_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[LoyaltyCoupon]:
        """
        Retrieve active coupons belonging to a loyalty account.

        Only persistence-level status and active flags are
        considered here. Detailed eligibility rules belong
        in the service layer.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon)
            .where(
                LoyaltyCoupon.loyalty_account_id
                == loyalty_account_id,
                LoyaltyCoupon.status
                == CouponStatus.ACTIVE,
                LoyaltyCoupon.is_active.is_(True),
            )
            .order_by(
                LoyaltyCoupon.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )

        return result.scalars().all()

    # ==========================================================
    # Get by Status
    # ==========================================================

    async def get_by_status(
        self,
        *,
        status: CouponStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[LoyaltyCoupon]:
        """
        Retrieve coupons by status.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon)
            .where(
                LoyaltyCoupon.status == status
            )
            .order_by(
                LoyaltyCoupon.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )

        return result.scalars().all()

    # ==========================================================
    # Get Customer Coupons by Status
    # ==========================================================

    async def get_customer_coupons_by_status(
        self,
        *,
        loyalty_account_id: int,
        status: CouponStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[LoyaltyCoupon]:
        """
        Retrieve customer coupons filtered by status.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon)
            .where(
                LoyaltyCoupon.loyalty_account_id
                == loyalty_account_id,
                LoyaltyCoupon.status == status,
            )
            .order_by(
                LoyaltyCoupon.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )

        return result.scalars().all()

    # ==========================================================
    # Get by Type
    # ==========================================================

    async def get_by_type(
        self,
        *,
        coupon_type: CouponType,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[LoyaltyCoupon]:
        """
        Retrieve coupons by coupon type.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon)
            .where(
                LoyaltyCoupon.coupon_type
                == coupon_type
            )
            .order_by(
                LoyaltyCoupon.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )

        return result.scalars().all()

    # ==========================================================
    # Get Customer Coupons by Type
    # ==========================================================

    async def get_customer_coupons_by_type(
        self,
        *,
        loyalty_account_id: int,
        coupon_type: CouponType,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[LoyaltyCoupon]:
        """
        Retrieve customer coupons filtered by type.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon)
            .where(
                LoyaltyCoupon.loyalty_account_id
                == loyalty_account_id,
                LoyaltyCoupon.coupon_type
                == coupon_type,
            )
            .order_by(
                LoyaltyCoupon.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )

        return result.scalars().all()

    # ==========================================================
    # Get by Reward Redemption
    # ==========================================================

    async def get_by_reward_redemption(
        self,
        reward_redemption_id: int,
    ) -> LoyaltyCoupon | None:
        """
        Retrieve the coupon generated from a reward redemption.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon).where(
                LoyaltyCoupon.reward_redemption_id
                == reward_redemption_id
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Get by Payment Transaction
    # ==========================================================

    async def get_by_payment_transaction(
        self,
        payment_transaction_id: int,
    ) -> LoyaltyCoupon | None:
        """
        Retrieve a coupon associated with a payment transaction.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon).where(
                LoyaltyCoupon.used_payment_transaction_id
                == payment_transaction_id
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Get All Coupons
    # ==========================================================

    async def get_all(
        self,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> Sequence[LoyaltyCoupon]:
        """
        Retrieve all loyalty coupons with pagination.
        """

        result = await self.db.execute(
            select(LoyaltyCoupon)
            .order_by(
                LoyaltyCoupon.created_at.desc()
            )
            .limit(limit)
            .offset(offset)
        )

        return result.scalars().all()

    # ==========================================================
    # Count All Coupons
    # ==========================================================

    async def count_all(self) -> int:
        """
        Count all loyalty coupons.
        """

        result = await self.db.execute(
            select(
                func.count(LoyaltyCoupon.id)
            )
        )

        return result.scalar_one()

    # ==========================================================
    # Count Customer Coupons
    # ==========================================================

    async def count_customer_coupons(
        self,
        *,
        loyalty_account_id: int,
    ) -> int:
        """
        Count coupons belonging to a loyalty account.
        """

        result = await self.db.execute(
            select(
                func.count(LoyaltyCoupon.id)
            ).where(
                LoyaltyCoupon.loyalty_account_id
                == loyalty_account_id
            )
        )

        return result.scalar_one()

    # ==========================================================
    # Count Customer Coupons by Status
    # ==========================================================

    async def count_customer_coupons_by_status(
        self,
        *,
        loyalty_account_id: int,
        status: CouponStatus,
    ) -> int:
        """
        Count customer coupons by status.
        """

        result = await self.db.execute(
            select(
                func.count(LoyaltyCoupon.id)
            ).where(
                LoyaltyCoupon.loyalty_account_id
                == loyalty_account_id,
                LoyaltyCoupon.status == status,
            )
        )

        return result.scalar_one()

    # ==========================================================
    # Update
    # ==========================================================

    async def update(
        self,
        coupon: LoyaltyCoupon,
    ) -> LoyaltyCoupon:
        """
        Persist changes to an existing coupon.
        """

        self.db.add(coupon)

        await self.db.flush()
        await self.db.refresh(coupon)

        return coupon

    # ==========================================================
    # Mark Coupon as Used
    # ==========================================================

    async def mark_as_used(
        self,
        *,
        coupon: LoyaltyCoupon,
    ) -> LoyaltyCoupon:
        """
        Persist an already-updated coupon as used.

        Business validation must be performed by the service
        before this method is called.
        """

        self.db.add(coupon)

        await self.db.flush()
        await self.db.refresh(coupon)

        return coupon

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete(
        self,
        coupon: LoyaltyCoupon,
    ) -> None:
        """
        Delete a loyalty coupon.
        """

        await self.db.delete(coupon)
        await self.db.flush()