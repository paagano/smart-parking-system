"""
Loyalty Reward Model.

Represents a reward available in the SmartPark loyalty
programme.

Rewards are redeemed using loyalty points.

The model represents the reward catalogue only.
Customer-specific redemptions are stored separately in
LoyaltyRewardRedemption.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import (
    LoyaltyRewardStatus,
    LoyaltyRewardType,
    LoyaltyTier,
)

if TYPE_CHECKING:
    from app.models.loyalty_reward_redemption import (
        LoyaltyRewardRedemption,
    )


class LoyaltyReward(BaseModel):
    """
    Represents a reward available for loyalty point redemption.
    """

    __tablename__ = "loyalty_rewards"

    # ==========================================================
    # Primary Key
    # ==========================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ==========================================================
    # Reward Information
    # ==========================================================

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reward_type: Mapped[LoyaltyRewardType] = mapped_column(
        Enum(
            LoyaltyRewardType,
            name="loyalty_reward_type",
            native_enum=True,
        ),
        nullable=False,
        index=True,
    )

    # ==========================================================
    # Redemption Cost
    # ==========================================================

    points_cost: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # ==========================================================
    # Reward Value
    # ==========================================================

    monetary_value: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    # ==========================================================
    # Status
    # ==========================================================

    status: Mapped[LoyaltyRewardStatus] = mapped_column(
        Enum(
            LoyaltyRewardStatus,
            name="loyalty_reward_status",
            native_enum=True,
        ),
        nullable=False,
        default=LoyaltyRewardStatus.ACTIVE,
        server_default=LoyaltyRewardStatus.ACTIVE.value,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    # ==========================================================
    # Eligibility
    # ==========================================================

    minimum_tier: Mapped[LoyaltyTier | None] = mapped_column(
        Enum(
            LoyaltyTier,
            name="loyalty_tier",
            native_enum=True,
            create_type=False,
        ),
        nullable=True,
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
    )
    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<LoyaltyReward("
            f"id={self.id}, "
            f"name='{self.name}', "
            f"type='{self.reward_type.value}', "
            f"points_cost={self.points_cost}, "
            f"status='{self.status.value}'"
            f")>"
        )

    # ==========================================================
    # Reward Redemptions
    # ==========================================================

    redemptions: Mapped[
        list["LoyaltyRewardRedemption"]
    ] = relationship(
        "LoyaltyRewardRedemption",
        back_populates="reward",
    )