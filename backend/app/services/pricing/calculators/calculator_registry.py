"""
Calculator Registry

Provides a registry of all pricing calculator strategies.

The Pricing Engine retrieves calculators from this registry
instead of instantiating them directly.

This keeps the Pricing Engine independent from concrete
calculator implementations and makes the pricing subsystem
easily extensible.

Example
-------

calculator = get_calculator(BillingType.HOURLY)

context = calculator.calculate(context)
"""

from __future__ import annotations

from app.models.enums import BillingType
from app.services.pricing.calculators.base_calculator import (
    BaseCalculator,
)
from app.services.pricing.calculators.daily_calculator import (
    DailyCalculator,
)
from app.services.pricing.calculators.flat_calculator import (
    FlatCalculator,
)
from app.services.pricing.calculators.hourly_calculator import (
    HourlyCalculator,
)


# ==========================================================
# Calculator Registry
# ==========================================================

_CALCULATORS: dict[BillingType, BaseCalculator] = {
    BillingType.HOURLY: HourlyCalculator(),
    BillingType.DAILY: DailyCalculator(),
    BillingType.FLAT: FlatCalculator(),
}


# ==========================================================
# Public API
# ==========================================================

def get_calculator(
    billing_type: BillingType,
) -> BaseCalculator:
    """
    Retrieve the calculator responsible for the supplied
    billing strategy.

    Parameters
    ----------
    billing_type:
        Billing strategy.

    Returns
    -------
    BaseCalculator

    Raises
    ------
    ValueError
        If no calculator has been registered for the supplied
        billing type.
    """

    try:
        return _CALCULATORS[billing_type]

    except KeyError as exc:
        raise ValueError(
            f"No calculator registered for "
            f"billing type '{billing_type.value}'."
        ) from exc


def registered_billing_types() -> list[BillingType]:
    """
    Return every registered billing type.
    """

    return list(_CALCULATORS.keys())