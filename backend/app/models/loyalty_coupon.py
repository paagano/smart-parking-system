"""
Loyalty Coupon Model.

Represents a coupon issued to a customer as a loyalty benefit.

A coupon may be generated from a loyalty reward redemption,
or it may be issued independently by the platform.

The coupon represents the actual customer-specific benefit
that can later be validated and applied to a parking/payment
transaction.

Business rules for coupon issuance, validation and usage
belong in LoyaltyCouponService.
Persistence belongs in LoyaltyCouponRepository.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.models.base_model import BaseModel
from app.models.enums import (
    CouponStatus,
    CouponType,
)

if TYPE_CHECKING:
    from app.models.loyalty_account import LoyaltyAccount
    from app.models.loyalty_reward_redemption import (
        LoyaltyRewardRedemption,
    )
    from app.models.payment_transaction import PaymentTransaction


class LoyaltyCoupon(BaseModel):
    """
    Represents a customer-specific loyalty coupon.

    A coupon may originate from:

        1. A loyalty reward redemption.
        2. An independently issued promotional benefit.

    The coupon has its own lifecycle and can be validated
    and consumed independently of the reward that generated it.
    """

    __tablename__ = "loyalty_coupons"

    # ==========================================================
    # Coupon Code
    # ==========================================================

    coupon_code: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    # ==========================================================
    # Loyalty Account
    # ==========================================================

    loyalty_account_id: Mapped[int] = mapped_column(
        ForeignKey(
            "loyalty_accounts.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # ==========================================================
    # Source Reward Redemption
    # ==========================================================

    reward_redemption_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "loyalty_reward_redemptions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        unique=True,
        index=True,
    )

    # ==========================================================
    # Coupon Type
    # ==========================================================

    coupon_type: Mapped[CouponType] = mapped_column(
        Enum(
            CouponType,
            name="coupon_type",
            native_enum=True,
        ),
        nullable=False,
        index=True,
    )

    # ==========================================================
    # Coupon Value
    # ==========================================================

    """
    Interpretation of `value` depends on coupon_type:

        FIXED_AMOUNT_DISCOUNT
            value = monetary discount amount.

            Example:
                value = 100.00
                → KES 100 discount

        PERCENTAGE_DISCOUNT
            value = percentage.

            Example:
                value = 20.00
                → 20% discount

        FREE_PARKING
            value is normally NULL.

        FREE_PARKING_HOURS
            value is normally NULL and
            free_parking_minutes is used.
    """

    value: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    # ==========================================================
    # Free Parking Duration
    # ==========================================================

    free_parking_minutes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    # ==========================================================
    # Coupon Status
    # ==========================================================

    status: Mapped[CouponStatus] = mapped_column(
        Enum(
            CouponStatus,
            name="coupon_status",
            native_enum=True,
        ),
        nullable=False,
        default=CouponStatus.ACTIVE,
        server_default=CouponStatus.ACTIVE.value,
        index=True,
    )

    # ==========================================================
    # Active Flag
    # ==========================================================

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        index=True,
    )

    # ==========================================================
    # Validity
    # ==========================================================

    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # ==========================================================
    # Usage
    # ==========================================================

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # ==========================================================
    # Usage Transaction
    # ==========================================================

    """
    When a coupon is consumed as part of a successful payment,
    the payment transaction can be recorded here.

    This provides an auditable link between:

        Coupon
            ↓
        Payment Transaction
    """

    used_payment_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "payment_transactions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # ==========================================================
    # Description
    # ==========================================================

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    loyalty_account: Mapped["LoyaltyAccount"] = relationship(
        "LoyaltyAccount",
        back_populates="coupons",
    )

    reward_redemption: Mapped[
        "LoyaltyRewardRedemption | None"
    ] = relationship(
        "LoyaltyRewardRedemption",
        back_populates="coupon",
    )

    used_payment_transaction: Mapped[
        "PaymentTransaction | None"
    ] = relationship(
        "PaymentTransaction",
        foreign_keys=[used_payment_transaction_id],
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<LoyaltyCoupon("
            f"id={self.id}, "
            f"coupon_code='{self.coupon_code}', "
            f"coupon_type='{self.coupon_type.value}', "
            f"status='{self.status.value}', "
            f"loyalty_account_id={self.loyalty_account_id}"
            f")>"
        )