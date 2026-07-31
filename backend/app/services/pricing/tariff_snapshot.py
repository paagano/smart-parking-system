"""
Tariff Snapshot

Immutable representation of a parking tariff used by the
Pricing Engine.

This class is a domain value object that captures the
pricing configuration at the time a parking charge is
calculated.

It intentionally contains only pricing-related fields and
is completely independent of SQLAlchemy and persistence.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BillingType, VehicleType


Money = Annotated[
    Decimal,
    Field(
        max_digits=10,
        decimal_places=2,
        ge=0,
    ),
]


class TariffSnapshot(BaseModel):
    """
    Immutable tariff snapshot used by the Pricing Engine.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    # ==========================================================
    # Identity
    # ==========================================================

    id: int

    name: str

    code: str

    # ==========================================================
    # Classification
    # ==========================================================

    vehicle_type: VehicleType

    billing_type: BillingType

    # ==========================================================
    # Pricing Rules
    # ==========================================================

    grace_period_minutes: int = Field(
        ge=0,
    )

    minimum_charge: Money

    hourly_rate: Money | None = None

    daily_rate: Money | None = None

    flat_rate: Money | None = None

    max_daily_charge: Money | None = None

    # ==========================================================
    # Validity
    # ==========================================================

    effective_from: datetime

    effective_to: datetime | None = None

    is_active: bool