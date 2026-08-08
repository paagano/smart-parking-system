"""
M-Pesa Payment Provider.

Implements the PaymentProvider contract for the
Safaricom Daraja API.

Responsibilities
----------------
- Translate SmartPark payment requests into M-Pesa requests.
- Delegate all Daraja communication to MpesaClient.
- Convert Daraja responses into PaymentProviderResponse.

Business rules DO NOT belong here.

Business workflows remain inside PaymentService.
"""

from __future__ import annotations

from typing import Any

from app.models.enums import (
    PaymentProvider as PaymentProviderEnum,
    PaymentStatus,
)

from app.schemas.mpesa import (
    MpesaStkPushRequest,
)

from app.schemas.payment_provider import (
    PaymentProviderResponse,
)

from app.services.payment_providers.base import (
    PaymentProvider,
)

from app.services.payment_providers.mpesa_client import (
    MpesaClient,
)


class MpesaProvider(PaymentProvider):
    """
    Safaricom Daraja payment provider.
    """

    def __init__(
        self,
    ) -> None:

        #
        # Shared enterprise client.
        #
        self.client = MpesaClient()

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

        return PaymentProviderEnum.SAFARICOM.value

    # ==========================================================
    # Payment Processing
    # ==========================================================

    async def process_payment(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Initiate an STK Push.

        Expected kwargs
        ---------------
        payment:
            ReservationPaymentCreate |
            SessionPaymentCreate |
            WalletTopUpCreate
        """

        payment = kwargs.get("payment")

        if payment is None:
            raise ValueError(
                "Payment request is required."
            )

        if not payment.payer_phone:
            raise ValueError(
                "payer_phone is required for M-Pesa payments."
            )

        request = MpesaStkPushRequest(

            amount=int(payment.total_amount),

            phone_number=payment.payer_phone,

            account_reference=(
                payment.payment_purpose.value
            ),

            transaction_desc=(
                payment.payment_purpose.label
            ),

        )

        response = await self.client.stk_push(
            request,
        )

        #
        # Safaricom returns ResponseCode "0"
        # when the STK request has been accepted.
        #
        if response.response_code == "0":

            return PaymentProviderResponse(

                success=True,

                provider=self.provider_name,

                provider_reference=(
                    response.checkout_request_id
                ),

                status=PaymentStatus.PENDING,

                message=response.customer_message,

                raw_response=response.model_dump(
                    by_alias=True,
                ),

            )

        return PaymentProviderResponse(

            success=False,

            provider=self.provider_name,

            provider_reference=None,

            status=PaymentStatus.FAILED,

            message=response.response_description,

            raw_response=response.model_dump(
                by_alias=True,
            ),

        )

    # ==========================================================
    # Refund
    # ==========================================================

    async def refund(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Refunds are not yet implemented.

        They will use the Daraja Reversal API.
        """

        raise NotImplementedError(
            "M-Pesa refunds are not implemented."
        )

    # ==========================================================
    # Reversal
    # ==========================================================

    async def reverse(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Reversals are not yet implemented.
        """

        raise NotImplementedError(
            "M-Pesa reversals are not implemented."
        )

    # ==========================================================
    # Payment Status
    # ==========================================================

    async def query_status(
        self,
        **kwargs: Any,
    ) -> PaymentProviderResponse:
        """
        Query an STK Push status.

        Expected kwargs
        ---------------
        checkout_request_id:
            Daraja CheckoutRequestID
        """

        checkout_request_id = kwargs.get(
            "checkout_request_id",
        )

        if checkout_request_id is None:
            raise ValueError(
                "checkout_request_id is required."
            )

        response = await self.client.stk_query(

            checkout_request_id=checkout_request_id,

        )

        return PaymentProviderResponse(

            success=True,

            provider=self.provider_name,

            provider_reference=checkout_request_id,

            #
            # We'll translate ResultCode into
            # SmartPark PaymentStatus later.
            #
            status=PaymentStatus.PENDING,

            message="STK query completed.",

            raw_response=response,

        )

    # ==========================================================
    # Callback
    # ==========================================================

    async def handle_callback(
        self,
        payload: dict[str, Any],
    ) -> PaymentProviderResponse:
        """
        Handle Daraja callback.

        Full callback processing will be implemented
        in Phase 3.
        """

        return PaymentProviderResponse(

            success=True,

            provider=self.provider_name,

            provider_reference=None,

            status=PaymentStatus.PENDING,

            message="Callback received.",

            raw_response=payload,

        )

    # ==========================================================
    # Health Check
    # ==========================================================

    async def health_check(
        self,
    ) -> bool:
        """
        Verify connectivity with Safaricom.
        """

        return await self.client.health_check()