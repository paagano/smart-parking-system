"""
SQLAlchemy model for Payment Transactions.

This model represents every financial transaction within
the Smart Parking System.

Examples

- Reservation payment
- Parking session payment
- Wallet top-up
- Refund
- Loyalty redemption
- Subscription payment

The Payment Transaction acts as the financial ledger of the system.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.parking_session import ParkingSession
    from app.models.parking_reservation import ParkingReservation
    from app.models.wallet_transaction import WalletTransaction
    from typing import Any, Optional

from sqlalchemy.orm import Mapped, mapped_column, relationship

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.models.base_model import BaseModel
from app.models.enums import (
    Currency,
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentStatus,
    PaymentType,
)


class PaymentTransaction(BaseModel):
    """
    Represents a financial transaction.

    Every successful or failed payment attempt is recorded.

    This table becomes the single source of truth
    for all financial operations.
    """

    __tablename__ = "payment_transactions"

    __table_args__ = (

        Index(
            "ix_payment_transaction_number",
            "transaction_number",
        ),

        Index(
            "ix_payment_transaction_status",
            "status",
        ),

        Index(
            "ix_payment_transaction_method",
            "payment_method",
        ),

        Index(
            "ix_payment_transaction_purpose",
            "payment_purpose",
        ),

        Index(
            "ix_payment_transaction_created_at",
            "created_at",
        ),

        Index(
            "ix_payment_customer",
            "customer_id",
        ),

        Index(
            "ix_payment_reservation",
            "reservation_id",
        ),

        Index(
            "ix_payment_session",
            "parking_session_id",
        ),

        Index(
            "ix_payment_provider_txn",
            "provider_transaction_id",
        ),

        Index(
            "ix_payment_customer_status",
            "customer_id",
            "status",
        ),

        Index(
            "ix_payment_transaction_type",
            "payment_type",
        ),

        Index(
            "ix_payment_paid_at",
            "paid_at",
        ),

    )

    # ==========================================================
    # References
    # ==========================================================

    reservation_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "parking_reservations.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    parking_session_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "parking_sessions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # ==========================================================
    # Identity
    # ==========================================================

    transaction_number: Mapped[str] = mapped_column(
        String(60),
        unique=True,
        nullable=False,
    )

    external_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Reference returned by payment provider.",
    )

    receipt_number: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    # ==========================================================
    # Payment Details
    # ==========================================================

    payment_type: Mapped[PaymentType] = mapped_column(
        Enum(
            PaymentType,
            name="payment_transaction_type",
        ),
        nullable=False,
    )

    parent_transaction_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "payment_transactions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    balance_after: Mapped[Decimal | None] = mapped_column(
        Numeric(
            12,
            2,
        ),
        nullable=True,
    )

    is_reconciled: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    payment_purpose: Mapped[PaymentPurpose] = mapped_column(
        Enum(
            PaymentPurpose,
            name="payment_transaction_purpose",
        ),
        nullable=False,
    )

    payment_method: Mapped[PaymentMethod] = mapped_column(
        Enum(
            PaymentMethod,
            name="payment_transaction_method",
        ),
        nullable=False,
    )

    payment_provider: Mapped[PaymentProvider] = mapped_column(
        Enum(
            PaymentProvider,
            name="payment_transaction_provider",
        ),
        nullable=False,
    )

    status: Mapped[PaymentStatus] = mapped_column(
        Enum(
            PaymentStatus,
            name="payment_transaction_status",
        ),
        default=PaymentStatus.PENDING,
        server_default="PENDING",
        nullable=False,
    )

    currency: Mapped[Currency] = mapped_column(
        Enum(
            Currency,
            name="payment_transaction_currency",
        ),
        nullable=False,
    )

    subtotal_amount: Mapped[Decimal] = mapped_column(
        Numeric(
            12,
            2,
        ),
        nullable=False,
    )

    tax_amount: Mapped[Decimal] = mapped_column(
        Numeric(
            12,
            2,
        ),
        default=Decimal("0.00"),
        nullable=False,
    )

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(
            12,
            2,
        ),
        default=Decimal("0.00"),
        nullable=False,
    )

    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(
            12,
            2,
        ),
        nullable=False,
    )

    idempotency_key: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
    )

    # ==========================================================
    # Payer Information
    # ==========================================================

    payer_name: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    payer_phone: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    payer_email: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    # ==========================================================
    # Loyalty and Rewards
    # ==========================================================

    loyalty_points_earned: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    loyalty_points_redeemed: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    # ==========================================================
    # Provider Information
    # ==========================================================

    provider_transaction_id: Mapped[str | None] = mapped_column(
        String(100),
        unique=True,
        nullable=True,
    )

    provider_status_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    provider_response: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    # ==========================================================
    # Audit DB Fields
    # ==========================================================

    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    customer: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[customer_id],
    )

    #
    # Reservation this payment belongs to.
    #
    reservation: Mapped["ParkingReservation | None"] = relationship(
        "ParkingReservation",
        back_populates="payments",
        foreign_keys=[reservation_id],
    )

    # Parking session this payment belongs to.
    parking_session: Mapped["ParkingSession | None"] = relationship(
        "ParkingSession",
        foreign_keys=[parking_session_id],
        back_populates="payments",
    )

    # Parent payment (used for refunds, reversals, adjustments).
    parent_transaction: Mapped["PaymentTransaction | None"] = relationship(
        "PaymentTransaction",
        remote_side=lambda: [PaymentTransaction.id],
        foreign_keys=[parent_transaction_id],
        back_populates="child_transactions",
    )

    #
    # Child payments (refunds, reversals, adjustments).
    #
    child_transactions: Mapped[list["PaymentTransaction"]] = relationship(
        "PaymentTransaction",
        foreign_keys=[parent_transaction_id],
        back_populates="parent_transaction",
        cascade="save-update, merge",
    )

    # 
    # Wallet Relationships
    # 
    wallet_transactions: Mapped[
        list["WalletTransaction"]
    ] = relationship(
        "WalletTransaction",
        foreign_keys="WalletTransaction.payment_transaction_id",
        back_populates="payment_transaction",
    )

    # 
    # Receipts Relationships
    #
    receipt: Mapped[Any] = relationship(
        "Receipt",
        back_populates="payment_transaction",
        uselist=False,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<PaymentTransaction("
            f"id={self.id}, "
            f"transaction_number='{self.transaction_number}', "
            f"amount={self.total_amount}, "
            f"status='{self.status.value}'"
            f")>"
        )