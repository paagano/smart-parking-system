"""
Wallet Dependencies

Dependency Injection (DI) providers for the Wallet module.

This module wires together:

- WalletRepository
- WalletTransactionRepository
- WalletService

Repositories remain responsible for persistence.

Business rules remain inside WalletService.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dependencies import get_db

from app.repositories.wallet_repository import (
    WalletRepository,
)

from app.repositories.wallet_transaction_repository import (
    WalletTransactionRepository,
)

from app.services.wallet_service import (
    WalletService,
)

# ==========================================================
# Database Dependency
# ==========================================================

DbSession = Annotated[
    AsyncSession,
    Depends(get_db),
]

# ==========================================================
# Wallet Repository
# ==========================================================


def get_wallet_repository(
    db: DbSession,
) -> WalletRepository:
    """
    Return a WalletRepository instance.
    """

    return WalletRepository(
        db=db,
    )


# ==========================================================
# Wallet Transaction Repository
# ==========================================================


def get_wallet_transaction_repository(
    db: DbSession,
) -> WalletTransactionRepository:
    """
    Return a WalletTransactionRepository instance.
    """

    return WalletTransactionRepository(
        db=db,
    )


# ==========================================================
# Wallet Service
# ==========================================================


def get_wallet_service(
    db: DbSession,
    wallet_repository: Annotated[
        WalletRepository,
        Depends(get_wallet_repository),
    ],
    wallet_transaction_repository: Annotated[
        WalletTransactionRepository,
        Depends(get_wallet_transaction_repository),
    ],
) -> WalletService:
    """
    Return a production WalletService instance.
    """

    return WalletService(
        db=db,
        wallet_repository=wallet_repository,
        wallet_transaction_repository=wallet_transaction_repository,
    )


# ==========================================================
# Dependency Aliases
# ==========================================================

WalletRepositoryDep = Annotated[
    WalletRepository,
    Depends(get_wallet_repository),
]

WalletTransactionRepositoryDep = Annotated[
    WalletTransactionRepository,
    Depends(get_wallet_transaction_repository),
]

WalletServiceDep = Annotated[
    WalletService,
    Depends(get_wallet_service),
]