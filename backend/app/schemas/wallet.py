"""
Wallet Schemas.

Pydantic schemas for Wallet entities.

These schemas represent the wallet itself.

Wallet operations such as top-ups, debits,
refunds and statements are defined in
wallet_transaction.py.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.enums import (
    Currency,
    WalletStatus,
)


# ==========================================================
# Base Schema
# ==========================================================


class WalletBase(BaseModel):
    """
    Base wallet schema.
    """

    currency: Currency = Field(
        default=Currency.KES,
        description="Wallet currency.",
    )


# ==========================================================
# Create Wallet
# ==========================================================


class WalletCreate(WalletBase):
    """
    Request used when creating a wallet.
    """

    customer_id: int = Field(
        ...,
        gt=0,
        description="Customer identifier.",
    )


# ==========================================================
# Wallet Response
# ==========================================================


class WalletResponse(BaseModel):
    """
    Full wallet response.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    wallet_number: str

    customer_id: int

    status: WalletStatus

    currency: Currency

    available_balance: Decimal

    reserved_balance: Decimal

    total_credited: Decimal

    total_debited: Decimal

    last_transaction_at: datetime | None = None

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Balance Response
# ==========================================================


class WalletBalanceResponse(BaseModel):
    """
    Wallet balance information.
    """

    wallet_id: int

    wallet_number: str

    currency: Currency

    available_balance: Decimal

    reserved_balance: Decimal

    current_balance: Decimal


# ==========================================================
# Wallet Summary
# ==========================================================


class WalletSummaryResponse(BaseModel):
    """
    Wallet summary for dashboard screens.
    """

    wallet_id: int

    wallet_number: str

    customer_id: int

    status: WalletStatus

    available_balance: Decimal

    reserved_balance: Decimal

    current_balance: Decimal

    total_credited: Decimal

    total_debited: Decimal

    last_transaction_at: datetime | None = None


# ==========================================================
# Wallet Statistics
# ==========================================================


class WalletStatisticsResponse(BaseModel):
    """
    Wallet statistics returned by WalletService.
    """

    wallet_id: int

    total_transactions: int

    total_credits: Decimal

    total_debits: Decimal

    available_balance: Decimal

    reserved_balance: Decimal

    current_balance: Decimal


# ==========================================================
# Module Exports
# ==========================================================

__all__ = [
    "WalletBase",
    "WalletCreate",
    "WalletResponse",
    "WalletBalanceResponse",
    "WalletSummaryResponse",
    "WalletStatisticsResponse",
]