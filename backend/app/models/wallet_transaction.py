"""
Wallet Transaction model.

Represents every movement of money into or out of a customer's
wallet.

Unlike PaymentTransaction, which records payment events,
WalletTransaction records wallet balance movements.

This table acts as the immutable financial ledger for every
wallet.

Examples

- Wallet Top-up
- Reservation Payment
- Parking Session Payment
- Refund
- Reversal
- Loyalty Reward
- Administrative Adjustment
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa

from sqlalchemy import (
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
from sqlalchemy.dialects.postgresql import ENUM

from app.models.enums import (
    Currency,
    WalletTransactionStatus,
    WalletTransactionType,
)

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.wallet import Wallet
    from app.models.payment_transaction import PaymentTransaction


class WalletTransaction(BaseModel):
    """
    Immutable wallet ledger.

    Every credit and debit applied to a Wallet is recorded
    as a WalletTransaction.

    Wallet balances should never change without creating one
    of these records.
    """

    __tablename__ = "wallet_transactions"

    __table_args__ = (

        #
        # Fast lookup by transaction number.
        #
        Index(
            "ix_wallet_transaction_number",
            "transaction_number",
        ),

        #
        # Wallet history.
        #
        Index(
            "ix_wallet_transaction_wallet",
            "wallet_id",
        ),

        #
        # Transaction status.
        #
        Index(
            "ix_wallet_transaction_status",
            "status",
        ),

        #
        # Transaction type.
        #
        Index(
            "ix_wallet_transaction_type",
            "transaction_type",
        ),

        #
        # Created date.
        #
        Index(
            "ix_wallet_transaction_created_at",
            "created_at",
        ),

        #
        # Payment lookup.
        #
        Index(
            "ix_wallet_payment",
            "payment_transaction_id",
        ),
    )

        # ==========================================================
    # Relationships
    # ==========================================================

    wallet_id: Mapped[int] = mapped_column(
        ForeignKey(
            "wallets.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    payment_transaction_id: Mapped[
        int | None
    ] = mapped_column(
        ForeignKey(
            "payment_transactions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_by: Mapped[
        int | None
    ] = mapped_column(
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

    reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment=(
            "Business reference such as reservation, "
            "session or payment number."
        ),
    )

    # ==========================================================
    # Transaction Details
    # ==========================================================

    transaction_type: Mapped[
        WalletTransactionType
    ] = mapped_column(
        Enum(
            WalletTransactionType,
            name="wallet_transaction_type",
        ),
        nullable=False,
    )

    status: Mapped[
        WalletTransactionStatus
    ] = mapped_column(
        Enum(
            WalletTransactionStatus,
            name="wallet_transaction_status",
        ),
        nullable=False,
        default=WalletTransactionStatus.COMPLETED,
        server_default=WalletTransactionStatus.COMPLETED.value,
    )

    currency: Mapped[Currency] = mapped_column(
        ENUM(
            Currency,
            name="currency",
            create_type=False,
        ),
        nullable=False,
    )

    # ==========================================================
    # Financial Values
    # ==========================================================

    amount: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(
            12,
            2,
        ),
        nullable=False,
    )

    balance_before: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(
            12,
            2,
        ),
        nullable=False,
    )

    balance_after: Mapped[
        Decimal
    ] = mapped_column(
        Numeric(
            12,
            2,
        ),
        nullable=False,
    )

    # ==========================================================
    # Narrative
    # ==========================================================

    description: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    notes: Mapped[
        str | None
    ] = mapped_column(
        Text,
        nullable=True,
    )

    # ==========================================================
    # Audit
    # ==========================================================

    posted_at: Mapped[
        datetime
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    # ==========================================================
    # ORM Relationships
    # ==========================================================

    #
    # Wallet this ledger entry belongs to.
    #
    wallet: Mapped["Wallet"] = relationship(
        "Wallet",
        back_populates="transactions",
    )

    #
    # Payment responsible for this wallet movement.
    #
    payment_transaction: Mapped[
        "PaymentTransaction | None"
    ] = relationship(
        "PaymentTransaction",
        foreign_keys=[payment_transaction_id],
        back_populates="wallet_transactions",
    )

    #
    # User that initiated the transaction.
    #
    created_by_user: Mapped[
        "User | None"
    ] = relationship(
        "User",
        foreign_keys=[created_by],
    )

    # ==========================================================
    # Computed Properties
    # ==========================================================

    @property
    def is_credit(self) -> bool:
        """
        True when this transaction increases
        the wallet balance.
        """

        return self.amount > Decimal("0.00")

    @property
    def is_debit(self) -> bool:
        """
        True when this transaction decreases
        the wallet balance.
        """

        return self.amount < Decimal("0.00")

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<WalletTransaction("
            f"id={self.id}, "
            f"transaction_number='{self.transaction_number}', "
            f"type='{self.transaction_type.value}', "
            f"amount={self.amount}, "
            f"status='{self.status.value}'"
            f")>"
        )