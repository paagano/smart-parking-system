"""
Flat Calculator

Calculates the base parking charge for FLAT tariffs.

This calculator simply returns the configured flat rate,
regardless of parking duration.

It intentionally does NOT apply:

- Minimum charge
- Maximum daily charge
- Discounts
- Taxes

Those responsibilities belong to the Pricing Engine.
"""

from __future__ import annotations

from app.models.enums import BillingType
from app.services.pricing.calculators.base_calculator import (
    BaseCalculator,
)
from app.services.pricing.pricing_context import PricingContext
from app.services.pricing.pricing_utils import (
    round_money,
)


class FlatCalculator(BaseCalculator):
    """
    Calculator for flat-rate parking tariffs.
    """

    # ==========================================================
    # Calculator Metadata
    # ==========================================================

    @property
    def billing_type(self) -> BillingType:
        """
        Billing strategy supported by this calculator.
        """

        return BillingType.FLAT

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

        if tariff.flat_rate is None:
            raise ValueError(
                "Flat tariff must define a flat_rate."
            )

        base_amount = round_money(
            tariff.flat_rate
        )

        return self.update_context(
            context=context,
            base_amount=base_amount,
        )