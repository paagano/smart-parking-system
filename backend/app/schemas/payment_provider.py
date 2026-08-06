"""
Payment Provider Schemas.

Common request/response contracts shared by all
payment provider implementations.

Examples
--------
- Internal Cash
- Wallet
- M-Pesa
- Airtel Money
- Visa
- Mastercard
- Bank Transfer
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PaymentStatus


# ==========================================================
# Provider Response
# ==========================================================


class PaymentProviderResponse(BaseModel):
    """
    Standard response returned by every payment provider.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    success: bool = Field(
        ...,
        description="Whether the provider processed the request successfully.",
    )

    provider: str = Field(
        ...,
        description="Payment provider name.",
    )

    provider_reference: str | None = Field(
        default=None,
        description="Provider transaction reference.",
    )

    status: PaymentStatus = Field(
        ...,
        description="Provider payment status.",
    )

    message: str | None = Field(
        default=None,
        description="Human-readable provider message.",
    )

    raw_response: dict[str, Any] | None = Field(
        default=None,
        description="Original provider response.",
    )