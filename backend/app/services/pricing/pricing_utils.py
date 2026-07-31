"""
Pricing Utilities

Shared utility functions used by the Pricing Engine and
pricing calculators.

This module centralizes all reusable pricing calculations
such as:

- Duration calculation
- Billable minutes
- Billable hours
- Billable days
- Monetary rounding
- Minimum charge application
- Maximum daily charge application

Keeping these utilities here ensures consistent pricing
behaviour across the application.
"""

from __future__ import annotations

import math
from datetime import datetime
from decimal import (
    Decimal,
    ROUND_HALF_UP,
)


# ==========================================================
# Monetary Helpers
# ==========================================================

MONEY_PRECISION = Decimal("0.01")


def round_money(
    amount: Decimal,
) -> Decimal:
    """
    Round a monetary amount to two decimal places.

    Uses ROUND_HALF_UP which is the standard financial
    rounding method.
    """

    return amount.quantize(
        MONEY_PRECISION,
        rounding=ROUND_HALF_UP,
    )


def ensure_non_negative(
    amount: Decimal,
) -> Decimal:
    """
    Prevent negative monetary values.
    """

    if amount < Decimal("0.00"):
        return Decimal("0.00")

    return amount


# ==========================================================
# Duration Helpers
# ==========================================================

def calculate_duration_minutes(
    entry_time: datetime,
    exit_time: datetime,
) -> int:
    """
    Calculate the total parking duration in minutes.

    Raises
    ------
    ValueError
        If exit_time is before entry_time.
    """

    if exit_time < entry_time:
        raise ValueError(
            "exit_time cannot be earlier than entry_time."
        )

    duration = exit_time - entry_time

    return int(
        duration.total_seconds() // 60
    )


def calculate_billable_minutes(
    duration_minutes: int,
    grace_period_minutes: int,
) -> int:
    """
    Apply the configured grace period.

    Returns the number of billable minutes.
    """

    if duration_minutes <= grace_period_minutes:
        return 0

    return (
        duration_minutes
        - grace_period_minutes
    )


# ==========================================================
# Hourly Billing
# ==========================================================

def calculate_billable_hours(
    billable_minutes: int,
) -> int:
    """
    Convert billable minutes into billable hours.

    Any fraction of an hour is billed
    as a full hour.
    """

    if billable_minutes <= 0:
        return 0

    return math.ceil(
        billable_minutes / 60
    )


# ==========================================================
# Daily Billing
# ==========================================================

def calculate_billable_days(
    billable_minutes: int,
) -> int:
    """
    Convert billable minutes into billable days.

    Any fraction of a day is billed
    as a full day.
    """

    if billable_minutes <= 0:
        return 0

    return math.ceil(
        billable_minutes / 1440
    )


# ==========================================================
# Pricing Helpers
# ==========================================================

def apply_minimum_charge(
    *,
    base_amount: Decimal,
    minimum_charge: Decimal,
) -> Decimal:
    """
    Apply the configured minimum charge.

    If the calculated amount is below the minimum
    charge, the minimum charge is returned.
    """

    return max(
        round_money(base_amount),
        round_money(minimum_charge),
    )


def apply_maximum_daily_charge(
    *,
    amount: Decimal,
    maximum_daily_charge: Decimal,
) -> Decimal:
    """
    Apply the configured maximum daily charge.

    If the calculated amount exceeds the configured
    daily cap, the maximum daily charge is returned.
    """

    return min(
        round_money(amount),
        round_money(maximum_daily_charge),
    )


# ==========================================================
# Final Amount
# ==========================================================

def calculate_total_amount(
    *,
    base_amount: Decimal,
    discount_amount: Decimal = Decimal("0.00"),
    tax_amount: Decimal = Decimal("0.00"),
) -> Decimal:
    """
    Calculate the final payable amount.

    Formula
    -------
    Total = Base - Discount + Tax
    """

    total = (
        base_amount
        - discount_amount
        + tax_amount
    )

    return round_money(
        ensure_non_negative(total)
    )