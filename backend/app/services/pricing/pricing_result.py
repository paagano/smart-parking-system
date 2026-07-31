"""
Pricing Result

Represents the outcome of a parking charge calculation.

This model is returned by the Pricing Engine and is not
persisted directly.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import BillingType


class PricingResult(BaseModel):
    """
    Result returned by the Pricing Engine.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )

    # ==========================================================
    # Tariff
    # ==========================================================

    tariff_id: int

    tariff_name: str

    billing_type: BillingType

    # ==========================================================
    # Duration
    # ==========================================================

    duration_minutes: int

    billable_minutes: int

    grace_period_applied: bool

    # ==========================================================
    # Charges
    # ==========================================================

    base_amount: Decimal

    discount_amount: Decimal = Decimal("0.00")

    tax_amount: Decimal = Decimal("0.00")

    total_amount: Decimal

    # ==========================================================
    # Audit
    # ==========================================================

    calculated_at: datetime