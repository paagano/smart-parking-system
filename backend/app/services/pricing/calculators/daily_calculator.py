"""
Daily Calculator

Calculates the base parking charge for DAILY tariffs.

This calculator is responsible ONLY for calculating the
base parking charge.

It intentionally does NOT apply:

- Minimum charge
- Maximum daily charge
- Discounts
- Taxes

Those responsibilities belong to the Pricing Engine.
"""

from __future__ import annotations

from decimal import Decimal

from app.models.enums import BillingType
from app.services.pricing.calculators.base_calculator import (
    BaseCalculator,
)
from app.services.pricing.pricing_context import PricingContext
from app.services.pricing.pricing_utils import (
    calculate_billable_days,
    round_money,
)


class DailyCalculator(BaseCalculator):
    """
    Calculator for daily parking tariffs.
    """

    # ==========================================================
    # Calculator Metadata
    # ==========================================================

    @property
    def billing_type(self) -> BillingType:
        """
        Billing strategy supported by this calculator.
        """

        return BillingType.DAILY

    # ==========================================================
    # Public API
    # ==========================================================

    def calculate(
        self,
        context: PricingContext,
    ) -> PricingContext:
        """
        Calculate the base parking charge.

        Parameters
        ----------
        context:
            Current pricing context.

        Returns
        -------
        PricingContext
            Updated pricing context containing the calculated
            base amount.
        """

        self.validate(context)

        tariff = context.tariff

        if tariff.daily_rate is None:
            raise ValueError(
                "Daily tariff must define a daily_rate."
            )

        billable_days = calculate_billable_days(
            context.billable_minutes
        )

        base_amount = round_money(
            tariff.daily_rate
            * Decimal(billable_days)
        )

        return self.update_context(
            context=context,
            base_amount=base_amount,
        )