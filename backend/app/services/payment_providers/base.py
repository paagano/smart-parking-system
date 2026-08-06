"""
Base Payment Provider.

Defines the common contract that every internal or external
payment provider must implement.

Examples
--------
- Internal Cash Office
- Wallet
- M-Pesa
- Airtel Money
- Visa
- Mastercard
- Bank Transfer

PaymentService communicates ONLY with this interface.

Concrete implementations are resolved by the
PaymentProviderFactory.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.payment_provider import (
    PaymentProviderResponse,
)


class PaymentProvider(ABC):
    """
    Abstract base class for all payment providers.

    Every payment provider must implement the same contract
    regardless of whether it is an internal provider or an
    external payment gateway.
    """

    # ==========================================================
    # Provider Information
    # ==========================================================

    @property
    @abstractmethod
    def provider_name(
        self,
    ) -> str:
        """
        Human-readable provider name.

        Examples
        --------
        INTERNAL
        MPESA
        AIRTEL
        VISA
        MASTERCARD
        BANK
        """

        raise NotImplementedError

    # ==========================================================
    # Payment Processing
    # ==========================================================

    @abstractmethod
    async def process_payment(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Process a payment request.

        Returns
        -------
        PaymentProviderResponse
            Standardized provider response.
        """

        raise NotImplementedError

    # ==========================================================
    # Refund
    # ==========================================================

    @abstractmethod
    async def refund(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Refund a previously successful payment.

        Returns
        -------
        PaymentProviderResponse
        """

        raise NotImplementedError

    # ==========================================================
    # Reversal
    # ==========================================================

    @abstractmethod
    async def reverse(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Reverse a payment transaction.

        Returns
        -------
        PaymentProviderResponse
        """

        raise NotImplementedError

    # ==========================================================
    # Payment Status
    # ==========================================================

    @abstractmethod
    async def query_status(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Query the latest payment status from the provider.

        Returns
        -------
        PaymentProviderResponse
        """

        raise NotImplementedError

    # ==========================================================
    # Provider Callback
    # ==========================================================

    @abstractmethod
    async def handle_callback(
        self,
        payload: dict[str, Any],
    ) -> PaymentProviderResponse:
        """
        Handle asynchronous callbacks/webhooks from the provider.

        This is used by providers such as:

        - M-Pesa
        - Airtel Money
        - Visa
        - Mastercard
        - Bank APIs

        Internal providers may simply return a successful response.

        Parameters
        ----------
        payload:
            Raw callback payload received from the provider.

        Returns
        -------
        PaymentProviderResponse
        """

        raise NotImplementedError

    # ==========================================================
    # Health Check
    # ==========================================================

    async def health_check(
        self,
    ) -> bool:
        """
        Check whether the provider is currently healthy.

        External providers may override this method to perform
        authentication or connectivity checks.

        Returns
        -------
        bool
        """

        return True