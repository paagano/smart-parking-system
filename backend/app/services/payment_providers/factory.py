"""
Payment Provider Factory.

Responsible for resolving the correct payment provider
implementation at runtime.

The factory hides provider creation from PaymentService.

Adding a new provider requires only:

1. Implement PaymentProvider
2. Register it in _PROVIDERS

No changes to PaymentService are required.
"""

from __future__ import annotations

from app.models.enums import PaymentProvider

from app.services.payment_providers.base import (
    PaymentProvider as BasePaymentProvider,
)

from app.services.payment_providers.internal import (
    InternalProvider,
)

from app.services.payment_providers.mpesa import (
    MpesaProvider,
)

# from app.services.payment_providers.airtel import (
#     AirtelProvider,
# )

# from app.services.payment_providers.visa import (
#     VisaProvider,
# )

# from app.services.payment_providers.mastercard import (
#     MastercardProvider,
# )

# from app.services.payment_providers.bank import (
#     BankProvider,
# )

# from app.services.payment_providers.other import (
#     OtherProvider,
# )


# ==========================================================
# Provider Registry
# ==========================================================

_PROVIDERS: dict[
    PaymentProvider,
    type[BasePaymentProvider],
] = {

    PaymentProvider.INTERNAL: InternalProvider,

    PaymentProvider.SAFARICOM: MpesaProvider,

    # PaymentProvider.AIRTEL: AirtelProvider,

    # PaymentProvider.VISA: VisaProvider,

    # PaymentProvider.MASTERCARD: MastercardProvider,

    # PaymentProvider.BANK: BankProvider,

    # PaymentProvider.OTHER: OtherProvider,
}


# ==========================================================
# Factory
# ==========================================================

class PaymentProviderFactory:
    """
    Factory responsible for resolving payment providers.
    """

    @staticmethod
    def get_provider(
        payment_provider: PaymentProvider,
    ) -> BasePaymentProvider:
        """
        Resolve the appropriate payment provider.

        Parameters
        ----------
        payment_provider:
            Payment provider enumeration.

        Returns
        -------
        PaymentProvider

        Raises
        ------
        ValueError
            If the provider is not supported.
        """

        provider_class = _PROVIDERS.get(
            payment_provider,
        )

        if provider_class is None:

            raise ValueError(
                f"Unsupported payment provider: "
                f"{payment_provider}"
            )

        return provider_class()

    # ======================================================
    # Registration
    # ======================================================

    @staticmethod
    def register_provider(
        payment_provider: PaymentProvider,
        provider: type[BasePaymentProvider],
    ) -> None:
        """
        Register a provider dynamically.

        This is primarily intended for:

        - Plugins
        - Testing
        - Future extensions
        """

        _PROVIDERS[payment_provider] = provider

    # ======================================================
    # Discovery
    # ======================================================

    @staticmethod
    def supported_providers() -> list[PaymentProvider]:
        """
        Return every registered provider.
        """

        return list(
            _PROVIDERS.keys(),
        )