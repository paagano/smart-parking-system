"""
Internal Payment Provider.

Implements the PaymentProvider interface for internal
SmartPark payment processing.

Supported payment methods include:

- INTERNAL (Cash Office / Exit Cashier)
- WALLET

Unlike external providers (M-Pesa, Airtel, Visa, etc.),
this provider performs all processing internally.

Business rules remain inside PaymentService.

This provider only represents the provider contract.
"""

from __future__ import annotations

from typing import Any

from app.models.enums import (
    PaymentProvider as PaymentProviderEnum,
    PaymentStatus,
)

from app.schemas.payment_provider import (
    PaymentProviderResponse,
)

from app.services.payment_providers.base import (
    PaymentProvider,
)


class InternalProvider(PaymentProvider):
    """
    Internal SmartPark payment provider.
    """

    # ==========================================================
    # Provider Information
    # ==========================================================

    @property
    def provider_name(
        self,
    ) -> str:
        """
        Provider name.
        """

        return PaymentProviderEnum.INTERNAL.value

    # ==========================================================
    # Payment Processing
    # ==========================================================

    async def process_payment(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Process an internal payment.

        Internal payments complete immediately.
        """

        return PaymentProviderResponse(

            success=True,

            provider=self.provider_name,

            provider_reference=None,

            status=PaymentStatus.SUCCESSFUL,

            message="Payment processed internally.",

            raw_response=None,
        )

    # ==========================================================
    # Refund
    # ==========================================================

    async def refund(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Process an internal refund.
        """

        return PaymentProviderResponse(

            success=True,

            provider=self.provider_name,

            provider_reference=None,

            status=PaymentStatus.REFUNDED,

            message="Refund processed internally.",

            raw_response=None,
        )

    # ==========================================================
    # Reversal
    # ==========================================================

    async def reverse(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Reverse an internal payment.
        """

        return PaymentProviderResponse(

            success=True,

            provider=self.provider_name,

            provider_reference=None,

            status=PaymentStatus.VOIDED,

            message="Payment reversed internally.",

            raw_response=None,
        )

    # ==========================================================
    # Payment Status
    # ==========================================================

    async def query_status(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Query payment status.

        Internal payments are processed immediately,
        therefore their status is always final.
        """

        return PaymentProviderResponse(

            success=True,

            provider=self.provider_name,

            provider_reference=None,

            status=PaymentStatus.SUCCESSFUL,

            message="Internal payment already processed.",

            raw_response=None,
        )

    # ==========================================================
    # Provider Callback
    # ==========================================================

    async def handle_callback(
        self,
        payload: dict[str, Any],
    ) -> PaymentProviderResponse:
        """
        Internal providers do not receive callbacks.

        This method exists only to satisfy the provider
        contract.
        """

        return PaymentProviderResponse(

            success=True,

            provider=self.provider_name,

            provider_reference=None,

            status=PaymentStatus.SUCCESSFUL,

            message="Internal provider does not require callbacks.",

            raw_response=payload,
        )

    # ==========================================================
    # Health Check
    # ==========================================================

    async def health_check(
        self,
    ) -> bool:
        """
        Internal provider is always available.
        """

        return True