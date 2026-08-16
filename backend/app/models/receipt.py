"""
Receipt Model

Represents the formal SmartPark customer-facing receipt generated
from a completed payment transaction.

A Receipt is intentionally linked to exactly one
PaymentTransaction. Financial transaction data is retained as a
snapshot on the receipt so that the customer-facing document
remains stable even if related operational data changes later.

Provider-specific receipt numbers, such as an M-Pesa receipt
number, remain owned by PaymentTransaction.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base
from app.models.enums import (
    ReceiptStatus,
    ReceiptType,
)

if TYPE_CHECKING:
    from app.models.payment_transaction import PaymentTransaction


class Receipt(Base):
    """
    Formal SmartPark receipt generated from a payment transaction.

    Business rule:
        One PaymentTransaction may have at most one Receipt.

    The Receipt stores a financial snapshot of the payment so that
    the generated customer-facing document remains consistent with
    the transaction at the time the receipt was generated.
    """

    __tablename__ = "receipts"

    # ==========================================================
    # Primary Key
    # ==========================================================

    id: Mapped[int] = mapped_column(
        primary_key=True,
        autoincrement=True,
    )

    # ==========================================================
    # Receipt Identity
    # ==========================================================

    receipt_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
    )

    receipt_type: Mapped[ReceiptType] = mapped_column(
        SAEnum(
            ReceiptType,
            name="receipt_type",
            native_enum=True,
        ),
        nullable=False,
        default=ReceiptType.PAYMENT,
        server_default=ReceiptType.PAYMENT.value,
    )

    status: Mapped[ReceiptStatus] = mapped_column(
        SAEnum(
            ReceiptStatus,
            name="receipt_status",
            native_enum=True,
        ),
        nullable=False,
        default=ReceiptStatus.PENDING,
        server_default=ReceiptStatus.PENDING.value,
        index=True,
    )

    # ==========================================================
    # Payment Transaction Relationship
    # ==========================================================

    payment_transaction_id: Mapped[int] = mapped_column(
        ForeignKey(
            "payment_transactions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        unique=True,
    )

    payment_transaction: Mapped["PaymentTransaction"] = relationship(
        "PaymentTransaction",
        back_populates="receipt",
        lazy="joined",
    )

    # ==========================================================
    # Customer
    # ==========================================================

    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # ==========================================================
    # Financial Snapshot
    # ==========================================================
    #
    # These fields intentionally duplicate the final financial
    # values from PaymentTransaction.
    #
    # Why?
    # A receipt is a customer-facing financial document and should
    # remain historically accurate even if operational records are
    # subsequently modified.
    #

    subtotal_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default="0.00",
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="KES",
        server_default="KES",
    )

    # ==========================================================
    # Payment Snapshot
    # ==========================================================

    payment_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    payment_purpose: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )

    payment_provider: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    provider_receipt_number: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        index=True,
    )

    paid_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ==========================================================
    # Customer Snapshot
    # ==========================================================
    #
    # These are snapshots used when rendering the receipt.
    # We do not want a historical receipt to change simply because
    # the customer's profile was subsequently updated.
    #

    customer_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    customer_phone: Mapped[Optional[str]] = mapped_column(
        String(30),
        nullable=True,
    )

    customer_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # ==========================================================
    # Document / Storage
    # ==========================================================

    pdf_storage_path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    pdf_url: Mapped[Optional[str]] = mapped_column(
        String(1000),
        nullable=True,
    )

    # ==========================================================
    # QR Code / Verification
    # ==========================================================

    verification_token: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        unique=True,
    )

    # ==========================================================
    # Generation / Availability
    # ==========================================================

    generated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    available_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    failure_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # ==========================================================
    # Audit Timestamps
    # ==========================================================

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        onupdate=func.current_timestamp(),
    )

    # ==========================================================
    # Table Constraints / Indexes
    # ==========================================================

    __table_args__ = (
        Index(
            "ix_receipts_customer_status",
            "customer_id",
            "status",
        ),
    )