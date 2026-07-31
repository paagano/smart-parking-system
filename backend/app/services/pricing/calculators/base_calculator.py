"""
Base Calculator

Abstract base class for all pricing calculators.

Each pricing calculator is responsible for calculating the
base parking charge for a specific billing strategy.

Business rules such as:

- Minimum charge
- Maximum daily charge
- Discounts
- Taxes

are intentionally NOT handled here. They belong to the
Pricing Engine.

Concrete implementations:

- HourlyCalculator
- DailyCalculator
- FlatCalculator
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from app.models.enums import BillingType
from app.services.pricing.pricing_context import PricingContext


class BaseCalculator(ABC):
    """
    Abstract pricing calculator.

    Concrete pricing calculators implement the calculate()
    method to determine the base parking charge.
    """

    # ==========================================================
    # Calculator Metadata
    # ==========================================================

    @property
    @abstractmethod
    def billing_type(self) -> BillingType:
        """
        Billing type supported by this calculator.
        """
        raise NotImplementedError

    # ==========================================================
    # Public API
    # ==========================================================

    @abstractmethod
    def calculate(
        self,
        context: PricingContext,
    ) -> PricingContext:
        """
        Calculate the base parking charge.

        Returns
        -------
        PricingContext
            Updated pricing context containing the calculated
            base amount.

        Notes
        -----
        This method MUST NOT:

        - Apply discounts
        - Apply taxes
        - Apply minimum charge
        - Apply maximum daily charge

        Those responsibilities belong to the Pricing Engine.
        """
        raise NotImplementedError

    # ==========================================================
    # Protected Helpers
    # ==========================================================

    def validate(
        self,
        context: PricingContext,
    ) -> None:
        """
        Validate that this calculator supports the supplied
        billing type.
        """

        if context.billing_type != self.billing_type:
            raise ValueError(
                f"{self.__class__.__name__} cannot calculate "
                f"{context.billing_type.value} tariffs."
            )

    def zero(self) -> Decimal:
        """
        Return a Decimal zero.

        Centralized to avoid repeated construction of
        Decimal("0.00").
        """

        return Decimal("0.00")

    def ensure_non_negative(
        self,
        amount: Decimal,
    ) -> Decimal:
        """
        Ensure the calculated amount is never negative.
        """

        if amount < self.zero():
            return self.zero()

        return amount

    def update_context(
        self,
        context: PricingContext,
        *,
        base_amount: Decimal,
    ) -> PricingContext:
        """
        Return a copy of the pricing context with the
        calculated base amount populated.
        """

        return context.model_copy(
            update={
                "base_amount": self.ensure_non_negative(
                    base_amount
                )
            }
        )