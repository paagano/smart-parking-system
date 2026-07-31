"""
Pricing Context

Internal working model used by the Pricing Engine during
charge calculation.

This model is not exposed outside the Pricing Engine.

It allows each calculation step to enrich the pricing
information without passing numerous parameters between
private methods.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import BillingType
from app.services.pricing.pricing_request import PricingRequest
from app.services.pricing.tariff_snapshot import TariffSnapshot


class PricingContext(BaseModel):
    """
    Internal pricing context.

    This object carries all intermediate calculation values
    while the Pricing Engine executes.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    # ==========================================================
    # Original Request
    # ==========================================================

    request: PricingRequest

    tariff: TariffSnapshot

    # ==========================================================
    # Duration
    # ==========================================================

    duration_minutes: int = Field(
        default=0,
        ge=0,
    )

    billable_minutes: int = Field(
        default=0,
        ge=0,
    )

    grace_period_applied: bool = False

    # ==========================================================
    # Billing
    # ==========================================================

    billing_type: BillingType

    # ==========================================================
    # Monetary Values
    # ==========================================================

    base_amount: Decimal = Decimal("0.00")

    minimum_charge: Decimal = Decimal("0.00")

    maximum_daily_charge: Decimal | None = None

    discount_amount: Decimal = Decimal("0.00")

    tax_amount: Decimal = Decimal("0.00")

    total_amount: Decimal = Decimal("0.00")

    # ==========================================================
    # Audit
    # ==========================================================

    calculated_at: datetime