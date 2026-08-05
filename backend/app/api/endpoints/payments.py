"""
REST API endpoints for Payment Transactions.

The Payments API exposes business-oriented financial
operations within SmartParkAI.

Business Operations

- Reservation Payments
- Parking Session Payments
- Wallet Top-ups
- Refunds
- Payment Lookups
- Revenue Statistics
- Financial Reconciliation

Future

- M-Pesa STK Push
- Card Payments
- Bank Transfers
- Loyalty Engine
- Customer Wallet
- Receipts
- Finance Dashboard
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db

from app.repositories.payment_repository import (
    PaymentRepository,
)

from app.repositories.parking_reservation_repository import (
    ParkingReservationRepository,
)

from app.repositories.parking_session_repository import (
    ParkingSessionRepository,
)

from app.schemas.payment import (
    PaymentResponse,
    RefundCreate,
    ReservationPaymentCreate,
    SessionPaymentCreate,
    WalletTopUpCreate,
)

from app.services.payment_service import (
    PaymentService,
)

from app.api.dependencies.services import (
    PaymentServiceDep,
)

from app.api.dependencies.wallet import WalletServiceDep

router = APIRouter(
    prefix="/payments",
    tags=[
        "Payments",
    ],
)

# ==========================================================
# Helpers
# ==========================================================


def _payment_or_404(
    payment,
):
    """
    Raise HTTP 404 if a payment
    cannot be found.
    """

    if payment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment not found.",
        )

    return payment


# ==========================================================
# Reservation Payment
# ==========================================================

@router.post(
    "/reservation",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Process Reservation Payment",
)

async def process_reservation_payment(
    payment: ReservationPaymentCreate,
    service: PaymentServiceDep,
):
    """
    Process payment for a parking reservation.
    """

    try:
        return await service.process_reservation_payment(
            payment,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# Parking Session Payment
# ==========================================================

@router.post(
    "/session",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Process Parking Session Payment",
)
async def process_session_payment(
    payment: SessionPaymentCreate,
    service: PaymentServiceDep,
) -> PaymentResponse:
    """
    Process payment for a completed parking session.
    """

    try:

        payment_transaction = (
            await service.process_session_payment(
                payment,
            )
        )

        return PaymentResponse.model_validate(
            payment_transaction,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

# ==========================================================
# Wallet Top-up
# ==========================================================

@router.post(
    "/wallet/topup",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Wallet Top-up",
)
async def process_wallet_topup(
    payment: WalletTopUpCreate,
    service: PaymentServiceDep,
):
    """
    Credit a customer's wallet.

    Future

    - Update wallet balance
    - Award loyalty points
    - Generate receipt
    """

    try:
        return await service.process_wallet_topup(
            payment,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# Refund
# ==========================================================

@router.post(
    "/refund",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Process Refund",
)
async def process_refund(
    payment: RefundCreate,
    service: PaymentServiceDep,
):
    """
    Process a refund transaction.
    """

    try:
        return await service.process_refund(
            payment,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# Transaction Lookup
# ==========================================================

@router.get(
    "/transaction/{transaction_number}",
    response_model=PaymentResponse,
    summary="Get Payment By Transaction Number",
)
async def get_transaction(
    transaction_number: str,
    service: PaymentServiceDep,
):
    """
    Retrieve a payment using its internal
    transaction number.
    """

    payment = await service.get_transaction(
        transaction_number,
    )

    return _payment_or_404(
        payment,
    )


# ==========================================================
# Receipt Lookup
# ==========================================================

@router.get(
    "/receipt/{receipt_number}",
    response_model=PaymentResponse,
    summary="Get Payment By Receipt Number",
)
async def get_receipt(
    receipt_number: str,
    service: PaymentServiceDep,
):
    """
    Retrieve a payment using its receipt number.
    """

    payment = await service.get_receipt(
        receipt_number,
    )

    return _payment_or_404(
        payment,
    )


# ==========================================================
# Recent Payments
# ==========================================================

@router.get(
    "/recent",
    response_model=list[PaymentResponse],
    summary="Recent Payments",
)
async def get_recent_payments(
    service: PaymentServiceDep,
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of payments to return.",
    ),
):
    """
    Retrieve the most recently created payments.
    """

    return await service.get_recent_payments(
        limit=limit,
    )


# ==========================================================
# Unreconciled Payments
# ==========================================================

@router.get(
    "/unreconciled",
    response_model=list[PaymentResponse],
    summary="Unreconciled Payments",
)
async def get_unreconciled_payments(
    service: PaymentServiceDep,
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
):
    """
    Retrieve all payments awaiting reconciliation.
    """

    return await service.get_unreconciled_payments(
        limit=limit,
        offset=offset,
    )

# ==========================================================
# Customer Payments
# ==========================================================

@router.get(
    "/customer/{customer_id}",
    response_model=list[PaymentResponse],
    summary="Customer Payment History",
)
async def get_customer_payments(
    customer_id: int,
    service: PaymentServiceDep,
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
        description="Maximum number of records.",
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description="Pagination offset.",
    ),
):
    """
    Retrieve payment history for a customer.
    """

    return await service.get_customer_payments(
        customer_id=customer_id,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Reservation Payments
# ==========================================================

@router.get(
    "/reservation/{reservation_id}",
    response_model=list[PaymentResponse],
    summary="Reservation Payments",
)
async def get_reservation_payments(
    reservation_id: int,
    service: PaymentServiceDep,
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
):
    """
    Retrieve payments belonging to
    a reservation.
    """

    return await service.get_reservation_payments(
        reservation_id=reservation_id,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Parking Session Payments
# ==========================================================

@router.get(
    "/session/{parking_session_id}",
    response_model=list[PaymentResponse],
    summary="Parking Session Payments",
)
async def get_session_payments(
    parking_session_id: int,
    service: PaymentServiceDep,
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
):
    """
    Retrieve payments belonging
    to a parking session.
    """

    return await service.get_session_payments(
        parking_session_id=parking_session_id,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Mark Payment Reconciled
# ==========================================================

@router.patch(
    "/{payment_id}/reconcile",
    response_model=PaymentResponse,
    summary="Mark Payment Reconciled",
)
async def reconcile_payment(
    payment_id: int,
    service: PaymentServiceDep,
):
    """
    Mark a payment as reconciled.
    """

    try:
        return await service.mark_reconciled(
            payment_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# Get Payment
# ==========================================================

@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    summary="Get Payment",
)
async def get_payment(
    payment_id: int,
    service: PaymentServiceDep,
):
    """
    Retrieve a payment by its ID.
    """

    payment = await service.get_payment(
        payment_id,
    )

    return _payment_or_404(
        payment,
    )


# ==========================================================
# List Payments
# ==========================================================

@router.get(
    "",
    response_model=list[PaymentResponse],
    summary="List Payments",
)
async def list_payments(
    service: PaymentServiceDep,
):
    """
    Retrieve all payment transactions.
    """

    return await service.get_all_payments()


# ==========================================================
# Payment Exists
# ==========================================================

@router.get(
    "/{payment_id}/exists",
    summary="Payment Exists",
)
async def payment_exists(
    payment_id: int,
    service: PaymentServiceDep,
):
    """
    Determine whether a payment exists.
    """

    return {
        "exists": await service.payment_exists(
            payment_id,
        ),
    }

# ==========================================================
# Statistics
# ==========================================================

@router.get(
    "/statistics/count",
    summary="Total Payments",
)
async def total_payments(
    service: PaymentServiceDep,
) -> dict[str, int]:
    """
    Return the total number of payment transactions.
    """

    return {
        "total_payments": await service.total_payments(),
    }


@router.get(
    "/statistics/successful",
    summary="Successful Payments",
)
async def successful_payments(
    service: PaymentServiceDep,
) -> dict[str, int]:
    """
    Return the total number of successful payments.
    """

    return {
        "successful_payments":
            await service.total_successful_payments(),
    }


@router.get(
    "/statistics/pending",
    summary="Pending Payments",
)
async def pending_payments(
    service: PaymentServiceDep,
) -> dict[str, int]:
    """
    Return the total number of pending payments.
    """

    return {
        "pending_payments":
            await service.total_pending_payments(),
    }


@router.get(
    "/statistics/failed",
    summary="Failed Payments",
)
async def failed_payments(
    service: PaymentServiceDep,
) -> dict[str, int]:
    """
    Return the total number of failed payments.
    """

    return {
        "failed_payments":
            await service.total_failed_payments(),
    }


# ==========================================================
# Revenue
# ==========================================================

@router.get(
    "/statistics/revenue",
    summary="Total Revenue",
)
async def total_revenue(
    service: PaymentServiceDep,
):
    """
    Return total successful revenue.
    """

    return {
        "total_revenue":
            await service.total_revenue(),
    }


@router.get(
    "/statistics/refunds",
    summary="Total Refunds",
)
async def total_refunds(
    service: PaymentServiceDep,
):
    """
    Return total refunded amount.
    """

    return {
        "total_refunds":
            await service.total_refunds(),
    }


# ==========================================================
# Customer Statistics
# ==========================================================

@router.get(
    "/statistics/customer/{customer_id}",
    summary="Customer Payment Statistics",
)
async def customer_statistics(
    customer_id: int,
    service: PaymentServiceDep,
):
    """
    Return payment statistics
    for a customer.
    """

    return {
        "customer_id": customer_id,
        "payment_count":
            await service.total_customer_payments(
                customer_id,
            ),
        "total_spent":
            await service.total_customer_revenue(
                customer_id,
            ),
    }


# ==========================================================
# Reconciliation Statistics
# ==========================================================

@router.get(
    "/statistics/unreconciled",
    summary="Unreconciled Payment Count",
)
async def unreconciled_count(
    service: PaymentServiceDep,
):
    """
    Return the number of unreconciled payments.
    """

    return {
        "unreconciled":
            await service.unreconciled_count(),
    }