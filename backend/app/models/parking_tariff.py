"""
Parking Tariff model.

Defines pricing rules for parking based on vehicle type and
billing strategy.

Tariffs are versioned business entities consumed by the Pricing
Service to calculate parking charges.

This model intentionally supports future enhancements including:
- Dynamic pricing
- Membership pricing
- Promotional pricing
- Subscription pricing
- AI-driven pricing
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import (
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.models.base_model import BaseModel
from app.models.enums import (
    BillingType,
    VehicleType,
)

if TYPE_CHECKING:
    from app.models.user import User


class ParkingTariff(BaseModel):
    """
    Parking pricing configuration.
    """

    __tablename__ = "parking_tariffs"

    __table_args__ = (

        UniqueConstraint(
            "code",
            name="uq_parking_tariffs_code",
        ),

        Index(
            "ix_tariff_vehicle_type",
            "vehicle_type",
        ),

        Index(
            "ix_tariff_billing_type",
            "billing_type",
        ),

        Index(
            "ix_tariff_active",
            "is_active",
        ),

        Index(
            "ix_tariff_priority",
            "pricing_priority",
        ),

        Index(
            "ix_tariff_effective_from",
            "effective_from",
        ),

        Index(
            "ix_tariff_effective_to",
            "effective_to",
        ),

        Index(
            "ix_tariff_lookup",
            "vehicle_type",
            "billing_type",
            "is_active",
        ),
    )

    # ==========================================================
    # Identification
    # ==========================================================

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    display_order: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=sa.text("1"),
    )

    pricing_priority: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        server_default=sa.text("100"),
    )

    # ==========================================================
    # Classification
    # ==========================================================

    vehicle_type: Mapped[VehicleType] = mapped_column(
        Enum(
            VehicleType,
            name="vehicle_type",
            create_type=False,
        ),
        nullable=False,
    )

    billing_type: Mapped[BillingType] = mapped_column(
        Enum(
            BillingType,
            name="billing_type",
            create_type=False,
        ),
        nullable=False,
    )

    # ==========================================================
    # Pricing
    # ==========================================================

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="KES",
        server_default=sa.text("'KES'"),
    )

    grace_period_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=sa.text("0"),
    )

    minimum_charge: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    hourly_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    daily_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    flat_rate: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    max_daily_charge: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    # ==========================================================
    # Validity
    # ==========================================================

    effective_from: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    effective_to: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    # ==========================================================
    # Status
    # ==========================================================

    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default=sa.true(),
    )

    # ==========================================================
    # Audit
    # ==========================================================

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # ==========================================================
    # Additional Information
    # ==========================================================

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    created_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by],
        lazy="select",
    )

    updated_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[updated_by],
        lazy="select",
    )

    # ==========================================================
    # String Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<ParkingTariff("
            f"code='{self.code}', "
            f"vehicle_type='{self.vehicle_type.value}', "
            f"billing_type='{self.billing_type.value}')>"
        )