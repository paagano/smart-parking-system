"""
M-Pesa Callback Schemas.

Represents the callback payload sent by the
Safaricom Daraja STK Push API.

Documentation
-------------
https://developer.safaricom.co.ke/

The callback contains:

- CheckoutRequestID
- MerchantRequestID
- ResultCode
- ResultDesc

If ResultCode == 0, additional metadata is included,
such as:

- MpesaReceiptNumber
- Amount
- PhoneNumber
- TransactionDate
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ==========================================================
# Callback Metadata Item
# ==========================================================


class MpesaCallbackItem(BaseModel):
    """
    Individual callback metadata item.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    name: str = Field(alias="Name")

    value: Any | None = Field(
        default=None,
        alias="Value",
    )


# ==========================================================
# Callback Metadata
# ==========================================================


class MpesaCallbackMetadata(BaseModel):
    """
    Callback metadata collection.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    item: list[MpesaCallbackItem] = Field(
        default_factory=list,
        alias="Item",
    )


# ==========================================================
# STK Callback
# ==========================================================


class MpesaStkCallback(BaseModel):
    """
    Main STK callback payload.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    merchant_request_id: str = Field(
        alias="MerchantRequestID",
    )

    checkout_request_id: str = Field(
        alias="CheckoutRequestID",
    )

    result_code: int = Field(
        alias="ResultCode",
    )

    result_desc: str = Field(
        alias="ResultDesc",
    )

    callback_metadata: MpesaCallbackMetadata | None = Field(
        default=None,
        alias="CallbackMetadata",
    )

    # ------------------------------------------------------
    # Convenience Helpers
    # ------------------------------------------------------

    def metadata_dict(self) -> dict[str, Any]:
        """
        Convert callback metadata into a dictionary.
        """

        if self.callback_metadata is None:
            return {}

        return {
            item.name: item.value
            for item in self.callback_metadata.item
        }

    @property
    def amount(self) -> Decimal | None:
        value = self.metadata_dict().get("Amount")

        if value is None:
            return None

        return Decimal(str(value))

    @property
    def receipt_number(self) -> str | None:
        value = self.metadata_dict().get(
            "MpesaReceiptNumber",
        )

        if value is None:
            return None

        return str(value)

    @property
    def phone_number(self) -> str | None:
        value = self.metadata_dict().get(
            "PhoneNumber",
        )

        if value is None:
            return None

        return str(value)

    @property
    def transaction_date(self) -> str | None:
        value = self.metadata_dict().get(
            "TransactionDate",
        )

        if value is None:
            return None

        return str(value)


# ==========================================================
# Body
# ==========================================================


class MpesaCallbackBody(BaseModel):
    """
    Body section.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    stk_callback: MpesaStkCallback = Field(
        alias="stkCallback",
    )


# ==========================================================
# Root Callback
# ==========================================================


class MpesaCallbackRequest(BaseModel):
    """
    Complete callback request.

    This is the model that the FastAPI endpoint
    will receive.
    """

    model_config = ConfigDict(
        populate_by_name=True,
    )

    body: MpesaCallbackBody = Field(
        alias="Body",
    )