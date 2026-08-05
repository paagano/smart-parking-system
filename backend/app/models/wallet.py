"""
Wallet model.

A Wallet represents a customer's electronic stored-value account.

The Wallet maintains the customer's available balance while
all financial movements are recorded separately in the
WalletTransaction ledger.

One customer owns exactly one wallet.
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
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.models.base_model import BaseModel
from app.models.enums import (
    Currency,
    WalletStatus,
)

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.wallet_transaction import WalletTransaction


class Wallet(BaseModel):
    """
    Customer electronic wallet.

    Stores the customer's current balances while the complete
    financial history is maintained by WalletTransaction.
    """

    __tablename__ = "wallets"

    __table_args__ = (

        #
        # Every wallet number must be unique.
        #
        Index(
            "ix_wallet_wallet_number",
            "wallet_number",
            unique=True,
        ),

        #
        # One wallet per customer.
        #
        Index(
            "ix_wallet_customer",
            "customer_id",
            unique=True,
        ),

        Index(
            "ix_wallet_status",
            "status",
        ),
    )

    # ==========================================================
    # Identification
    # ==========================================================

    wallet_number: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        unique=True,
    )

    # ==========================================================
    # Ownership
    # ==========================================================

    customer_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        unique=True,
    )

    # ==========================================================
    # Wallet Status
    # ==========================================================

    status: Mapped[WalletStatus] = mapped_column(
        Enum(
            WalletStatus,
            name="wallet_status",
        ),
        nullable=False,
        default=WalletStatus.ACTIVE,
        server_default=WalletStatus.ACTIVE.value,
    )

    # ==========================================================
    # Currency
    # ==========================================================

    currency: Mapped[Currency] = mapped_column(
        Enum(
            Currency,
            name="currency",
        ),
        nullable=False,
        default=Currency.KES,
        server_default=Currency.KES.value,
    )

    # ==========================================================
    # Financial Balances
    # ==========================================================

    available_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=sa.text("0.00"),
    )

    reserved_balance: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=sa.text("0.00"),
    )

    total_credited: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=sa.text("0.00"),
    )

    total_debited: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=sa.text("0.00"),
    )

    # ==========================================================
    # Audit
    # ==========================================================

    last_transaction_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ==========================================================
    # Computed Properties
    # ==========================================================

    @property
    def current_balance(self) -> Decimal:
        """
        Returns the customer's spendable balance.
        """

        return self.available_balance

    @property
    def has_balance(self) -> bool:
        """
        True if the wallet has funds.
        """

        return self.available_balance > Decimal("0.00")

    # ==========================================================
    # Relationships
    # ==========================================================

    customer: Mapped["User"] = relationship(
        "User",
        back_populates="wallet",
        foreign_keys=[customer_id],
    )

    transactions: Mapped[
        list["WalletTransaction"]
    ] = relationship(
        "WalletTransaction",
        back_populates="wallet",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WalletTransaction.id.desc()",
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<Wallet("
            f"id={self.id}, "
            f"wallet_number='{self.wallet_number}', "
            f"customer_id={self.customer_id}, "
            f"balance={self.available_balance}"
            f")>"
        )