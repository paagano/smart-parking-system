"""
REST API endpoints for Wallets.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    HTTPException,
    status,
)

from app.api.dependencies.wallet import (
    WalletServiceDep,
)

from app.schemas.wallet import (
    WalletResponse,
    WalletBalanceResponse,
)

from app.schemas.wallet_transaction import (
    WalletTransactionResponse,
)

from app.schemas.wallet import (
    WalletStatisticsResponse,
)

router = APIRouter(
    prefix="/wallets",
    tags=[
        "Wallets",
    ],
)


# ==========================================================
# Wallet Details
# ==========================================================

@router.get(
    "/{customer_id}",
    response_model=WalletResponse,
    summary="Get Customer Wallet",
)
async def get_customer_wallet(
    customer_id: int,
    service: WalletServiceDep,
):
    """
    Retrieve a customer's wallet.
    """

    try:

        return await service.get_customer_wallet(
            customer_id,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

@router.get(
    "/balance/{customer_id}",
    response_model=WalletBalanceResponse,
    summary="Get Wallet Balance",
)
async def get_wallet_balance(
    customer_id: int,
    service: WalletServiceDep,
):
    """
    Retrieve a customer's wallet balance.
    """

    try:

        return await service.get_customer_wallet_balance(
            customer_id,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

# ==========================================================
# Wallet Transactions
# ==========================================================

@router.get(
    "/transactions/{customer_id}",
    response_model=list[WalletTransactionResponse],
    summary="Wallet Transaction History",
)
async def get_wallet_transactions(
    customer_id: int,
    service: WalletServiceDep,
):
    """
    Retrieve a customer's wallet transaction history.
    """

    try:

        return await service.get_customer_wallet_transactions(
            customer_id,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

@router.get(
    "/transaction/{transaction_number}",
    response_model=WalletTransactionResponse,
    summary="Get Wallet Transaction",
)
async def get_wallet_transaction(
    transaction_number: str,
    service: WalletServiceDep,
):
    """
    Retrieve a wallet transaction.
    """

    try:

        return await service.get_wallet_transaction(
            transaction_number,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

@router.get(
    "/statistics/{customer_id}",
    response_model=WalletStatisticsResponse,
    summary="Wallet Statistics",
)
async def get_wallet_statistics(
    customer_id: int,
    service: WalletServiceDep,
):
    """
    Retrieve wallet statistics.
    """

    try:

        return await service.get_wallet_statistics(
            customer_id,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc