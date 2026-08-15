"""
Loyalty Account Model.

Represents the loyalty account associated with a customer.

The account stores the customer's current loyalty balance,
lifetime earned points, and current loyalty tier.

Detailed point movements are stored in
LoyaltyPointTransaction.

Customer reward redemptions are stored in
LoyaltyRewardRedemption.

Customer coupons are stored in
LoyaltyCoupon.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Integer,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.models.base_model import BaseModel
from app.models.enums import LoyaltyTier


if TYPE_CHECKING:
    from app.models.user import User

    from app.models.loyalty_point_transaction import (
        LoyaltyPointTransaction,
    )

    from app.models.loyalty_reward_redemption import (
        LoyaltyRewardRedemption,
    )

    from app.models.loyalty_coupon import (
        LoyaltyCoupon,
    )


class LoyaltyAccount(BaseModel):
    """
    Loyalty account belonging to a customer.
    """

    __tablename__ = "loyalty_accounts"

    # ==========================================================
    # Primary Key
    # ==========================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ==========================================================
    # Customer
    # ==========================================================

    customer_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
        index=True,
    )

    # ==========================================================
    # Points
    # ==========================================================

    points_balance: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    lifetime_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # ==========================================================
    # Tier
    # ==========================================================

    tier: Mapped[LoyaltyTier] = mapped_column(
        Enum(
            LoyaltyTier,
            name="loyalty_tier",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
        default=LoyaltyTier.BRONZE,
        server_default=LoyaltyTier.BRONZE.value,
        index=True,
    )

    # ==========================================================
    # Status
    # ==========================================================

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # ==========================================================
    # Customer Relationship
    # ==========================================================

    customer: Mapped["User"] = relationship(
        "User",
        back_populates="loyalty_account",
    )

    # ==========================================================
    # Point Transactions
    # ==========================================================

    point_transactions: Mapped[
        list["LoyaltyPointTransaction"]
    ] = relationship(
        "LoyaltyPointTransaction",
        back_populates="loyalty_account",
        cascade="all, delete-orphan",
        order_by=(
            "LoyaltyPointTransaction.created_at.desc()"
        ),
    )

    # ==========================================================
    # Reward Redemptions
    # ==========================================================

    reward_redemptions: Mapped[
        list["LoyaltyRewardRedemption"]
    ] = relationship(
        "LoyaltyRewardRedemption",
        back_populates="loyalty_account",
        cascade="all, delete-orphan",
        order_by=(
            "LoyaltyRewardRedemption.created_at.desc()"
        ),
    )

    # ==========================================================
    # Coupons
    # ==========================================================

    coupons: Mapped[
        list["LoyaltyCoupon"]
    ] = relationship(
        "LoyaltyCoupon",
        back_populates="loyalty_account",
        cascade="all, delete-orphan",
        order_by=(
            "LoyaltyCoupon.created_at.desc()"
        ),
    )