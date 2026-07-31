"""
Pricing Exceptions

Custom exceptions used by the Pricing Engine.

Using domain-specific exceptions instead of ValueError
makes the pricing subsystem easier to understand, test,
and integrate with FastAPI exception handlers.
"""

from __future__ import annotations


# ==========================================================
# Base Exception
# ==========================================================

class PricingException(Exception):
    """
    Base exception for all pricing-related errors.
    """

    default_message = "Pricing error."

    def __init__(
        self,
        message: str | None = None,
    ) -> None:
        super().__init__(
            message or self.default_message
        )


# ==========================================================
# Request Validation
# ==========================================================

class InvalidPricingRequestException(PricingException):
    """
    Raised when a PricingRequest is invalid.
    """

    default_message = "Invalid pricing request."


class InvalidParkingDurationException(PricingException):
    """
    Raised when exit time is before entry time.
    """

    default_message = (
        "Invalid parking duration."
    )


# ==========================================================
# Tariff
# ==========================================================

class InvalidTariffException(PricingException):
    """
    Raised when a tariff configuration is invalid.
    """

    default_message = (
        "Invalid parking tariff."
    )


class InactiveTariffException(PricingException):
    """
    Raised when an inactive tariff is supplied.
    """

    default_message = (
        "Parking tariff is inactive."
    )


class TariffNotEffectiveException(PricingException):
    """
    Raised when a tariff is outside its validity period.
    """

    default_message = (
        "Parking tariff is not currently effective."
    )


class MissingTariffRateException(PricingException):
    """
    Raised when the required rate is missing.
    """

    default_message = (
        "Required tariff rate is missing."
    )


# ==========================================================
# Billing
# ==========================================================

class UnsupportedBillingTypeException(
    PricingException,
):
    """
    Raised when no calculator exists for the supplied
    billing strategy.
    """

    default_message = (
        "Unsupported billing type."
    )


class BillingCalculationException(
    PricingException,
):
    """
    Raised when a calculator cannot complete the pricing
    calculation.
    """

    default_message = (
        "Pricing calculation failed."
    )


# ==========================================================
# Pricing Rules
# ==========================================================

class MinimumChargeException(
    PricingException,
):
    """
    Raised when the minimum charge cannot be applied.
    """

    default_message = (
        "Minimum charge calculation failed."
    )


class MaximumDailyChargeException(
    PricingException,
):
    """
    Raised when the maximum daily charge cannot be applied.
    """

    default_message = (
        "Maximum daily charge calculation failed."
    )


class TariffNotFoundException(
    PricingException,
):
    """
    Raised when no applicable parking tariff exists.
    """

    default_message = (
        "No applicable parking tariff found."
    )

class DuplicateTariffCodeException(PricingException):
    """
    Raised when a tariff code already exists.
    """
    default_message = "Duplicate tariff code."


class OverlappingTariffException(PricingException):
    """
    Raised when tariff effective dates overlap.
    """
    default_message = "Overlapping parking tariffs."


class TariffActivationException(PricingException):
    """
    Raised when a tariff cannot be activated.
    """
    default_message = "Tariff activation failed."