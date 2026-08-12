"""
Receipt Schemas

Pydantic schemas used by the Receipt module.

These schemas define the API and service-layer contracts for:

- Receipt creation
- Receipt responses
- Receipt lookup / verification
- Customer receipt listing
- Receipt generation status

Business logic belongs in the Receipt Service.
Persistence belongs in the Receipt Repository.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.enums import (
    ReceiptStatus,
    ReceiptType,
)


# ==========================================================
# Base Receipt Schema
# ==========================================================


class ReceiptBase(BaseModel):
    """
    Common fields shared across Receipt schemas.
    """

    receipt_type: ReceiptType = ReceiptType.PAYMENT

    subtotal_amount: Decimal = Field(
        ...,
        ge=0,
        decimal_places=2,
    )

    discount_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        decimal_places=2,
    )

    tax_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        decimal_places=2,
    )

    total_amount: Decimal = Field(
        ...,
        ge=0,
        decimal_places=2,
    )

    currency: str = Field(
        default="KES",
        min_length=3,
        max_length=3,
    )

    payment_method: str = Field(
        ...,
        min_length=1,
        max_length=50,
    )

    payment_provider: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    provider_receipt_number: Optional[str] = Field(
        default=None,
        max_length=100,
    )

    paid_at: Optional[datetime] = None

    customer_name: Optional[str] = Field(
        default=None,
        max_length=255,
    )

    customer_phone: Optional[str] = Field(
        default=None,
        max_length=30,
    )

    customer_email: Optional[str] = Field(
        default=None,
        max_length=255,
    )


# ==========================================================
# Receipt Creation
# ==========================================================


class ReceiptCreate(ReceiptBase):
    """
    Schema used when creating a Receipt.

    The receipt number and verification token are generated
    by the Receipt Service rather than supplied by the API
    consumer.
    """

    payment_transaction_id: int = Field(
        ...,
        gt=0,
    )

    customer_id: Optional[int] = Field(
        default=None,
        gt=0,
    )


# ==========================================================
# Receipt Update
# ==========================================================


class ReceiptUpdate(BaseModel):
    """
    Schema for controlled Receipt lifecycle updates.

    The Receipt Service is responsible for deciding when these
    values may be changed.
    """

    status: Optional[ReceiptStatus] = None

    pdf_storage_path: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    pdf_url: Optional[str] = Field(
        default=None,
        max_length=1000,
    )

    generated_at: Optional[datetime] = None

    available_at: Optional[datetime] = None

    failure_reason: Optional[str] = None


# ==========================================================
# Receipt Response
# ==========================================================


class ReceiptResponse(ReceiptBase):
    """
    Complete Receipt representation returned by the API.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    receipt_number: str

    receipt_type: ReceiptType

    status: ReceiptStatus

    payment_transaction_id: int

    customer_id: Optional[int]

    pdf_storage_path: Optional[str]

    pdf_url: Optional[str]

    verification_token: str

    generated_at: Optional[datetime]

    available_at: Optional[datetime]

    failure_reason: Optional[str]

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Receipt Summary
# ==========================================================


class ReceiptSummary(BaseModel):
    """
    Lightweight receipt representation used for customer
    receipt listings.

    This intentionally excludes internal storage information
    and the verification token.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    receipt_number: str

    receipt_type: ReceiptType

    status: ReceiptStatus

    payment_transaction_id: int

    total_amount: Decimal

    currency: str

    payment_method: str

    payment_provider: Optional[str]

    provider_receipt_number: Optional[str]

    paid_at: Optional[datetime]

    created_at: datetime


# ==========================================================
# Receipt Lookup
# ==========================================================


class ReceiptLookupResponse(BaseModel):
    """
    Public-facing receipt verification / lookup response.

    This provides enough information for a customer or
    verification endpoint to confirm the authenticity of a
    receipt without exposing unnecessary internal data.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    receipt_number: str

    receipt_type: ReceiptType

    status: ReceiptStatus

    total_amount: Decimal

    currency: str

    payment_method: str

    payment_provider: Optional[str]

    provider_receipt_number: Optional[str]

    customer_name: Optional[str]

    paid_at: Optional[datetime]

    payment_transaction_id: int

    created_at: datetime


# ==========================================================
# Receipt List Response
# ==========================================================


class ReceiptListResponse(BaseModel):
    """
    Paginated receipt list response.
    """

    total: int

    items: list[ReceiptSummary]


# ==========================================================
# Receipt Generation Response
# ==========================================================


class ReceiptGenerationResponse(BaseModel):
    """
    Response returned when a receipt has been generated.

    The actual PDF may be stored locally or in Supabase,
    depending on the active storage implementation.
    """

    receipt_number: str

    status: ReceiptStatus

    pdf_url: Optional[str]

    generated_at: Optional[datetime]

    available_at: Optional[datetime]


# ==========================================================
# Receipt Verification
# ==========================================================


class ReceiptVerificationResponse(BaseModel):
    """
    Result of receipt verification.

    This deliberately does not expose the verification token
    itself.
    """

    valid: bool

    receipt_number: str

    status: ReceiptStatus

    receipt_type: ReceiptType

    total_amount: Decimal

    currency: str

    payment_transaction_id: int

    paid_at: Optional[datetime]

    verified_at: datetime