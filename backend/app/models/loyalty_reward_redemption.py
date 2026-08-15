"""
Loyalty Reward Redemption Model.

Represents a customer's redemption of a loyalty reward.

The LoyaltyReward model represents the reward catalogue.
This model represents the customer's actual redemption
of a catalogue reward.

A redemption may optionally generate a LoyaltyCoupon.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
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
    RewardRedemptionStatus,
)


if TYPE_CHECKING:
    from app.models.loyalty_account import (
        LoyaltyAccount,
    )

    from app.models.loyalty_reward import (
        LoyaltyReward,
    )

    from app.models.loyalty_coupon import (
        LoyaltyCoupon,
    )


class LoyaltyRewardRedemption(BaseModel):
    """
    Represents a customer's redemption of a loyalty reward.

    A redemption records the customer's loyalty account,
    the reward redeemed, points spent, redemption status,
    validity information, and optional coupon generated
    from the redemption.
    """

    __tablename__ = "loyalty_reward_redemptions"

    # ==========================================================
    # Primary Key
    # ==========================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
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
    # Reward
    # ==========================================================

    reward_id: Mapped[int] = mapped_column(
        ForeignKey(
            "loyalty_rewards.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    # ==========================================================
    # Redemption Reference
    # ==========================================================

    redemption_reference: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    # ==========================================================
    # Points
    # ==========================================================

    points_spent: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # ==========================================================
    # Status
    # ==========================================================

    status: Mapped[RewardRedemptionStatus] = mapped_column(
        Enum(
            RewardRedemptionStatus,
            name="reward_redemption_status",
            native_enum=True,
        ),
        nullable=False,
        default=RewardRedemptionStatus.REDEEMED,
        server_default=RewardRedemptionStatus.REDEEMED.value,
        index=True,
    )

    # ==========================================================
    # Benefit / Usage
    # ==========================================================

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
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

    loyalty_account: Mapped[
        "LoyaltyAccount"
    ] = relationship(
        "LoyaltyAccount",
        back_populates="reward_redemptions",
    )

    reward: Mapped[
        "LoyaltyReward"
    ] = relationship(
        "LoyaltyReward",
        back_populates="redemptions",
    )

    # ==========================================================
    # Coupon
    # ==========================================================

    coupon: Mapped[
        "LoyaltyCoupon | None"
    ] = relationship(
        "LoyaltyCoupon",
        back_populates="reward_redemption",
        uselist=False,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<LoyaltyRewardRedemption("
            f"id={self.id}, "
            f"redemption_reference="
            f"'{self.redemption_reference}', "
            f"reward_id={self.reward_id}, "
            f"points_spent={self.points_spent}, "
            f"status='{self.status.value}'"
            f")>"
        )