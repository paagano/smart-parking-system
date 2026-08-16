"""
Pydantic schemas for Payment Transactions.

These schemas define the API contract for the Payments module.

Responsibilities
----------------
✔ Request validation
✔ Response serialization
✔ Financial transaction validation
✔ Swagger documentation

The Payment schemas support:

- Reservation payments
- Parking session payments
- Wallet top-ups
- Refunds
- Future loyalty integration
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import (
    Currency,
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentStatus,
    PaymentType,
)


# ==========================================================
# Base Schema
# ==========================================================


class PaymentBase(BaseModel):
    """
    Base schema shared by all payment requests.
    """

    payment_method: PaymentMethod = Field(
        ...,
        description="Payment method used by the customer.",
    )

    payment_provider: PaymentProvider = Field(
        ...,
        description="Financial service provider.",
    )

    payment_purpose: PaymentPurpose = Field(
        ...,
        description="Business purpose of the payment.",
    )

    payment_type: PaymentType = Field(
        default=PaymentType.PAYMENT,
        description="Type of financial transaction.",
    )

    currency: Currency = Field(
        default=Currency.KES,
        description="Transaction currency.",
    )

    subtotal_amount: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        decimal_places=2,
        description="Subtotal before discounts and taxes.",
    )

    discount_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        decimal_places=2,
        description="Discount amount.",
    )

    tax_amount: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        decimal_places=2,
        description="Tax amount.",
    )

    total_amount: Decimal = Field(
        ...,
        ge=Decimal("0.00"),
        decimal_places=2,
        description="Final payable amount.",
    )

    payer_name: str | None = Field(
        default=None,
        max_length=100,
    )

    payer_phone: str | None = Field(
        default=None,
        max_length=20,
    )

    payer_email: str | None = Field(
        default=None,
        max_length=255,
    )

    notes: str | None = Field(
        default=None,
        max_length=1000,
    )

    # ------------------------------------------------------
    # Validators
    # ------------------------------------------------------

    @field_validator(
        "subtotal_amount",
        "discount_amount",
        "tax_amount",
        "total_amount",
    )
    @classmethod
    def validate_amounts(
        cls,
        value: Decimal,
    ) -> Decimal:
        """
        Ensure monetary values are rounded
        to two decimal places.
        """

        return value.quantize(
            Decimal("0.01"),
        )

    @model_validator(mode="after")
    def validate_total_amount(self):
        """
        Ensure the financial calculation is valid.

            subtotal
            - discount
            + tax
            - loyalty points contribution
            = total cash payment

        Loyalty points are valued at:
            1 Loyalty Point = KES 1.00
        """

        loyalty_contribution = Decimal(
            str(
                getattr(
                    self,
                    "loyalty_points_to_redeem",
                    0,
                )
            )
        )

        expected_total = (
            self.subtotal_amount
            - self.discount_amount
            + self.tax_amount
            - loyalty_contribution
        ).quantize(
            Decimal("0.01"),
        )

        if expected_total < Decimal("0.00"):
            raise ValueError(
                "Loyalty-points contribution cannot exceed "
                "the required payment amount."
            )

        if expected_total != self.total_amount.quantize(
            Decimal("0.01"),
        ):
            raise ValueError(
                "Total amount must equal subtotal - discount + tax "
                "- loyalty-points contribution."
            )

        return self

    # ------------------------------------------------------
    # Configuration
    # ------------------------------------------------------

    model_config = ConfigDict(
        from_attributes=True,
        use_enum_values=False,
    )


# ==========================================================
# Update Schema
# ==========================================================


class PaymentUpdate(BaseModel):
    """
    Fields that may be updated after
    a payment has been created.
    """

    status: PaymentStatus | None = None

    external_reference: str | None = Field(
        default=None,
        max_length=100,
    )

    idempotency_key: str | None = Field(
        default=None,
    )

    provider_transaction_id: str | None = Field(
        default=None,
        max_length=100,
    )

    provider_status_message: str | None = None

    provider_response: dict | None = None

    receipt_number: str | None = Field(
        default=None,
        max_length=50,
    )

    paid_at: datetime | None = None

    is_reconciled: bool | None = None

    notes: str | None = None


# ==========================================================
# Summary Schema
# ==========================================================


class PaymentSummary(BaseModel):
    """
    Lightweight payment summary.
    Useful for lists and dashboards.
    """

    id: int

    transaction_number: str

    payment_type: PaymentType

    payment_purpose: PaymentPurpose

    payment_method: PaymentMethod

    status: PaymentStatus

    currency: Currency

    total_amount: Decimal

    paid_at: datetime | None

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


# ==========================================================
# Reservation Payment
# ==========================================================


class ReservationPaymentCreate(PaymentBase):
    """
    Create a payment for a parking reservation.

    Loyalty points may optionally be redeemed towards
    the reservation payment.

    One loyalty point is worth KES 1.00.
    """

    reservation_id: int = Field(
        ...,
        gt=0,
        description="Reservation being paid for.",
    )

    customer_id: int | None = Field(
        default=None,
        gt=0,
        description="Registered customer making the payment.",
    )

    loyalty_points_to_redeem: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of loyalty points to redeem towards this payment. "
            "1 loyalty point is worth KES 1.00. "
            "Set to 0 for a normal payment."
        ),
    )


# ==========================================================
# Parking Session Payment
# ==========================================================


class SessionPaymentCreate(PaymentBase):
    """
    Request model for settling a completed parking session.

    The payment amount must match the calculated parking fee
    for the specified parking session.

    Loyalty points may optionally be redeemed towards
    the parking session payment.

    One loyalty point is worth KES 1.00.
    """

    parking_session_id: int = Field(
        ...,
        gt=0,
        description=(
            "Unique identifier of the parking session being settled."
        ),
    )

    customer_id: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Registered customer making the payment. "
            "Optional for anonymous or drive-in customers."
        ),
    )

    loyalty_points_to_redeem: int = Field(
        default=0,
        ge=0,
        description=(
            "Number of loyalty points to redeem towards this payment. "
            "1 loyalty point is worth KES 1.00. "
            "Set to 0 for a normal payment."
        ),
    )


# ==========================================================
# Wallet Top-up
# ==========================================================


class WalletTopUpCreate(PaymentBase):
    """
    Top up a customer's wallet.

    This creates a Payment Transaction.
    The Wallet module will later update
    the customer's wallet balance.
    """

    customer_id: int = Field(
        ...,
        gt=0,
        description="Customer receiving the wallet top-up.",
    )


# ==========================================================
# Refund | Reversal
# ==========================================================


class RefundCreate(PaymentBase):
    """
    Create a refund transaction.

    Refunds are always linked to
    an existing payment transaction.
    """

    parent_transaction_id: int = Field(
        ...,
        gt=0,
        description="Original payment transaction.",
    )

    reason: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Reason for the refund.",
    )


class ReversalCreate(PaymentBase):
    """
    Reverse an existing payment transaction.
    """

    parent_transaction_id: int = Field(
        ...,
        gt=0,
        description="Original payment transaction.",
    )

    reason: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Reason for reversal.",
    )


# ==========================================================
# Generic Payment Create
# ==========================================================


class PaymentCreate(PaymentBase):
    """
    Generic payment schema.

    Used internally when the payment
    purpose is determined dynamically.
    """

    customer_id: int | None = Field(
        default=None,
        gt=0,
    )

    reservation_id: int | None = Field(
        default=None,
        gt=0,
    )

    parking_session_id: int | None = Field(
        default=None,
        gt=0,
    )

    parent_transaction_id: int | None = Field(
        default=None,
        gt=0,
    )

    @field_validator("parent_transaction_id")
    @classmethod
    def validate_refund(
        cls,
        value,
    ):
        """
        Parent transaction must be positive.
        """

        if value is not None and value <= 0:
            raise ValueError(
                "Parent transaction ID must be greater than zero."
            )

        return value


# ==========================================================
# Payment Response
# ==========================================================


class PaymentResponse(BaseModel):
    """
    Full Payment Transaction response.
    """

    id: int

    transaction_number: str

    reservation_id: int | None

    parking_session_id: int | None

    customer_id: int | None

    parent_transaction_id: int | None

    payment_type: PaymentType

    payment_purpose: PaymentPurpose

    payment_method: PaymentMethod

    payment_provider: PaymentProvider

    status: PaymentStatus

    currency: Currency

    subtotal_amount: Decimal

    discount_amount: Decimal

    tax_amount: Decimal

    total_amount: Decimal

    balance_after: Decimal | None

    receipt_number: str | None

    external_reference: str | None

    provider_transaction_id: str | None

    provider_status_message: str | None

    provider_response: dict | None

    payer_name: str | None

    payer_phone: str | None

    payer_email: str | None

    loyalty_points_earned: int

    loyalty_points_redeemed: int

    is_reconciled: bool

    paid_at: datetime | None

    notes: str | None

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


# ==========================================================
# Payment List Response
# ==========================================================


class PaymentListResponse(BaseModel):
    """
    Paginated payment results.
    """

    items: list[PaymentSummary]

    total: int

    page: int = 1

    page_size: int = 50

    total_pages: int = 1


# ==========================================================
# Payment Statistics
# ==========================================================


class PaymentStatistics(BaseModel):
    """
    Payment dashboard statistics.
    """

    total_transactions: int

    successful_transactions: int

    pending_transactions: int

    failed_transactions: int

    refunded_transactions: int

    total_revenue: Decimal

    total_refunds: Decimal

    currency: Currency = Currency.KES


# ==========================================================
# Revenue Summary
# ==========================================================


class RevenueSummary(BaseModel):
    """
    Revenue summary.
    """

    subtotal: Decimal

    discounts: Decimal

    tax: Decimal

    revenue: Decimal

    refunds: Decimal

    net_revenue: Decimal

    currency: Currency = Currency.KES


# ==========================================================
# Payment Search Filters
# ==========================================================


class PaymentSearchFilters(BaseModel):
    """
    Filters used when searching
    payment transactions.
    """

    customer_id: int | None = None

    reservation_id: int | None = None

    parking_session_id: int | None = None

    transaction_number: str | None = None

    provider_transaction_id: str | None = None

    payment_method: PaymentMethod | None = None

    payment_provider: PaymentProvider | None = None

    payment_purpose: PaymentPurpose | None = None

    payment_type: PaymentType | None = None

    status: PaymentStatus | None = None

    paid_from: datetime | None = None

    paid_to: datetime | None = None


# ==========================================================
# Payment Receipt
# ==========================================================


class PaymentReceipt(BaseModel):
    """
    Receipt details returned after
    a successful payment.
    """

    receipt_number: str

    transaction_number: str

    payment_status: PaymentStatus

    payment_method: PaymentMethod

    payment_provider: PaymentProvider

    total_amount: Decimal

    currency: Currency

    paid_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )