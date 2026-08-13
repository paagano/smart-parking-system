"""
Loyalty Point Transaction Model.

Represents an auditable movement of loyalty points.

Positive points represent points awarded to the customer.

Negative points represent points spent, expired, reversed,
or otherwise deducted.
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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import LoyaltyPointTransactionType

if TYPE_CHECKING:
    from app.models.loyalty_account import LoyaltyAccount


class LoyaltyPointTransaction(BaseModel):
    """
    Immutable-style audit record for a loyalty point movement.
    """

    __tablename__ = "loyalty_point_transactions"

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
    # Transaction
    # ==========================================================

    transaction_type: Mapped[
        LoyaltyPointTransactionType
    ] = mapped_column(
        Enum(
            LoyaltyPointTransactionType,
            name="loyalty_point_transaction_type",
            native_enum=True,
        ),
        nullable=False,
        index=True,
    )

    points: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    balance_after: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # ==========================================================
    # Reference
    # ==========================================================

    reference_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        index=True,
    )

    reference_id: Mapped[int | None] = mapped_column(
        Integer,
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
    # Expiration
    # ==========================================================

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    # ==========================================================
    # Relationship
    # ==========================================================

    loyalty_account: Mapped["LoyaltyAccount"] = relationship(
        "LoyaltyAccount",
        back_populates="point_transactions",
    )