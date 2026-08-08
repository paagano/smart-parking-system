"""
M-Pesa Schemas.

Pydantic schemas representing the contract between
SmartPark AI and the Safaricom Daraja API.

Phase 1
-------
- STK Push Request
- STK Push Response

Future Phases
-------------
- STK Query
- Callback
- Reversal
- Transaction Status
- Account Balance
"""

from __future__ import annotations

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


# ==========================================================
# STK Push Request
# ==========================================================


class MpesaStkPushRequest(BaseModel):
    """
    Internal STK Push request.

    This schema is consumed by MpesaClient and
    represents the data required to initiate an
    STK Push transaction.
    """

    phone_number: str = Field(
        ...,
        min_length=12,
        max_length=12,
        description="Customer phone number in 2547XXXXXXXX format.",
    )

    amount: int = Field(
        ...,
        gt=0,
        description="Amount to charge.",
    )

    account_reference: str = Field(
        ...,
        max_length=50,
        description="Internal payment reference.",
    )

    transaction_desc: str = Field(
        ...,
        max_length=100,
        description="Transaction description.",
    )


# ==========================================================
# STK Push Response
# ==========================================================


class MpesaStkPushResponse(BaseModel):
    """
    Response returned by the Daraja STK Push API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    merchant_request_id: str = Field(
        alias="MerchantRequestID",
    )

    checkout_request_id: str = Field(
        alias="CheckoutRequestID",
    )

    response_code: str = Field(
        alias="ResponseCode",
    )

    response_description: str = Field(
        alias="ResponseDescription",
    )

    customer_message: str = Field(
        alias="CustomerMessage",
    )


# ==========================================================
# Module Exports
# ==========================================================

__all__ = [
    "MpesaStkPushRequest",
    "MpesaStkPushResponse",
]