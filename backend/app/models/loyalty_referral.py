"""
Loyalty Referral Model.

Represents a referral made by one SmartPark customer
(referrer) for another customer (referred customer).

The model stores the referral relationship, referral code,
lifecycle status, and the loyalty points awarded when the
referral qualifies.

Business rules belong in LoyaltyReferralService.

Persistence belongs in LoyaltyReferralRepository.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
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
from app.models.enums import ReferralStatus

if TYPE_CHECKING:
    from app.models.user import User


class LoyaltyReferral(BaseModel):
    """
    Represents a customer referral within the SmartPark
    Loyalty Programme.

    A referral connects:

        referrer -> customer who initiated the referral
        referred -> customer who was referred

    The referral progresses through the following lifecycle:

        PENDING
            ↓
        QUALIFIED
            ↓
        REWARDED

    A referral may also be cancelled before completion.
    """

    __tablename__ = "loyalty_referrals"

    # ==========================================================
    # Primary Key
    # ==========================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ==========================================================
    # Referrer
    # ==========================================================

    referrer_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # ==========================================================
    # Referred Customer
    # ==========================================================

    referred_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    # ==========================================================
    # Referral Code
    # ==========================================================

    referral_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    # ==========================================================
    # Referral Status
    # ==========================================================

    status: Mapped[ReferralStatus] = mapped_column(
        Enum(
            ReferralStatus,
            name="referral_status",
            native_enum=True,
            create_type=False,
        ),
        nullable=False,
        default=ReferralStatus.PENDING,
        server_default=ReferralStatus.PENDING.value,
        index=True,
    )

    # ==========================================================
    # Reward Points
    # ==========================================================

    reward_points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )

    # ==========================================================
    # Qualification
    # ==========================================================

    qualified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ==========================================================
    # Reward
    # ==========================================================

    rewarded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ==========================================================
    # Cancellation
    # ==========================================================

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ==========================================================
    # Notes
    # ==========================================================

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    referrer: Mapped["User"] = relationship(
        "User",
        foreign_keys=[referrer_id],
    )

    referred: Mapped["User"] = relationship(
        "User",
        foreign_keys=[referred_id],
    )

    # ==========================================================
    # Constraints
    # ==========================================================

    __table_args__ = (
        CheckConstraint(
            "referrer_id <> referred_id",
            name="ck_loyalty_referral_different_customers",
        ),
        CheckConstraint(
            "reward_points >= 0",
            name="ck_loyalty_referral_reward_points_non_negative",
        ),
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<LoyaltyReferral("
            f"id={self.id}, "
            f"referral_code="
            f"'{self.referral_code}', "
            f"referrer_id={self.referrer_id}, "
            f"referred_id={self.referred_id}, "
            f"status='{self.status.value}', "
            f"reward_points={self.reward_points}"
            f")>"
        )