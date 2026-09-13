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
from datetime import datetime, timezone
from decimal import Decimal
import re

from pydantic import BaseModel, Field

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

from app.models.enums import (
    Currency,
    PaymentMethod,
    PaymentProvider,
    PaymentPurpose,
    PaymentType,
    SessionStatus,
)

from app.schemas.payment import (
    PaymentResponse,
    RefundCreate,
    ReversalCreate,
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
from app.api.dependencies.pricing import PricingServiceDep

from app.api.dependencies.wallet import WalletServiceDep

from app.api.dependencies.auth import require_facility_attendant
from app.api.dependencies.repositories import (
    ParkingBayRepositoryDep,
    ParkingSessionRepositoryDep,
    UserRepositoryDep,
    VehicleRepositoryDep,
)
from app.models.user import User

from app.schemas.mpesa_callback import (
    MpesaCallbackRequest,
)

# ==========================================================
# Operator M-Pesa STK Push
# ==========================================================

class OperatorSessionStkPushRequest(BaseModel):
    """
    Request used by an authenticated parking Operator to initiate
    an M-Pesa STK Push for an active parking session.

    The payable amount is deliberately NOT accepted from the client.
    It is recalculated by PaymentService from the authoritative
    pricing service at the moment the STK Push is initiated.
    """

    parking_session_id: int = Field(gt=0)

    use_registered_number: bool = Field(
        default=True,
        description=(
            "Use the registered driver's phone number associated "
            "with the parking session."
        ),
    )

    mobile_number: str | None = Field(
        default=None,
        max_length=20,
        description=(
            "Alternative Kenyan Safaricom number. Required when "
            "use_registered_number is false."
        ),
    )

    notes: str | None = Field(
        default=None,
        max_length=1000,
    )


class OperatorSessionStkPushResponse(BaseModel):
    """
    Result returned after the Operator STK Push has been accepted
    by Safaricom.

    The amount is the authoritative current parking charge calculated
    by the backend PaymentService.
    """

    payment_id: int
    transaction_number: str
    parking_session_id: int
    amount: Decimal
    currency: str
    status: str
    phone_number: str
    checkout_request_id: str | None = None
    message: str
    duration_minutes: int
    billable_minutes: int
    grace_period_applied: bool
    tariff_name: str


class OperatorSessionPaymentOptionsResponse(BaseModel):
    """Payment options available for an Operator at the vehicle exit."""

    parking_session_id: int
    registered_driver_available: bool
    registered_driver_name: str | None = None
    registered_mobile_masked: str | None = None


class OperatorSessionCashPaymentRequest(BaseModel):
    """Request used by an Operator to record a cash parking payment."""

    parking_session_id: int = Field(gt=0)
    notes: str | None = Field(default=None, max_length=1000)


class OperatorSessionCashPaymentResponse(BaseModel):
    """Result of an Operator-recorded cash parking payment."""

    payment_id: int
    transaction_number: str
    parking_session_id: int
    amount: Decimal
    currency: str
    status: str
    message: str
    duration_minutes: int
    billable_minutes: int
    grace_period_applied: bool
    tariff_name: str


# Router Definition
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

# ==========================================================
# Operator Parking Session M-Pesa STK Push
# ==========================================================

def _normalize_operator_mpesa_phone(value: str) -> str:
    """
    Normalize a Kenyan M-Pesa number to 2547XXXXXXXX format.

    The existing Mpesa schema/client requires the normalized
    12-digit international representation.
    """
    digits = re.sub(r"\D", "", value or "")

    if digits.startswith("00"):
        digits = digits[2:]

    if digits.startswith("0"):
        digits = "254" + digits[1:]
    elif digits.startswith("7") and len(digits) == 9:
        digits = "254" + digits

    if not re.fullmatch(r"2547\d{8}", digits):
        raise ValueError(
            "Please provide a valid Kenyan Safaricom number, "
            "for example 0712345678 or 254712345678."
        )

    return digits


def _mask_operator_mpesa_phone(phone: str) -> str:
    """Mask a normalized Kenyan phone number for the UI."""
    return f"{phone[:6]}****{phone[-2:]}"



async def _get_registered_driver_for_session(
    *,
    parking_session,
    vehicle_repository: VehicleRepositoryDep,
    user_repository: UserRepositoryDep,
):
    """
    Resolve registration -> registered Vehicle -> registered User.

    This deliberately does not use parking_session.customer_id because a
    manual drive-in session can be anonymous even when its registration
    belongs to a registered SmartPark customer.
    """
    vehicle = await vehicle_repository.get_by_registration_number(
        parking_session.vehicle_registration,
    )

    if vehicle is None or not vehicle.is_active or vehicle.customer_id is None:
        return None, None

    registered_user = await user_repository.get_by_id(vehicle.customer_id)

    if (
        registered_user is None
        or not registered_user.is_active
        or not registered_user.phone_number
    ):
        return vehicle, None

    return vehicle, registered_user


@router.get(
    "/operator/session/{parking_session_id}/payment-options",
    response_model=OperatorSessionPaymentOptionsResponse,
    summary="Get Operator Parking Session Payment Options",
)
async def operator_session_payment_options(
    parking_session_id: int,
    session_repository: ParkingSessionRepositoryDep,
    parking_bay_repository: ParkingBayRepositoryDep,
    vehicle_repository: VehicleRepositoryDep,
    user_repository: UserRepositoryDep,
    operator: User = Depends(require_facility_attendant),
) -> OperatorSessionPaymentOptionsResponse:
    """
    Determine whether the vehicle registration is tied to a registered
    SmartPark customer with a usable registered mobile number.

    Cash is always available to the Operator and is intentionally not
    represented as a customer-registration-dependent option.
    """
    parking_session = await session_repository.get_by_id(parking_session_id)

    if parking_session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking session not found.",
        )

    facility_id = await parking_bay_repository.get_facility_id(
        parking_session.parking_bay_id,
    )

    if facility_id != operator.facility_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This parking session does not belong to your assigned facility.",
        )

    _, registered_user = await _get_registered_driver_for_session(
        parking_session=parking_session,
        vehicle_repository=vehicle_repository,
        user_repository=user_repository,
    )

    if registered_user is None:
        return OperatorSessionPaymentOptionsResponse(
            parking_session_id=parking_session.id,
            registered_driver_available=False,
        )

    payer_phone = _normalize_operator_mpesa_phone(registered_user.phone_number)

    return OperatorSessionPaymentOptionsResponse(
        parking_session_id=parking_session.id,
        registered_driver_available=True,
        registered_driver_name=(
            f"{registered_user.first_name or ''} "
            f"{registered_user.last_name or ''}"
        ).strip() or None,
        registered_mobile_masked=_mask_operator_mpesa_phone(payer_phone),
    )


@router.post(
    "/operator/session/cash",
    response_model=OperatorSessionCashPaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record Operator Cash Parking Session Payment",
)
async def operator_session_cash_payment(
    request: OperatorSessionCashPaymentRequest,
    service: PaymentServiceDep,
    pricing_service: PricingServiceDep,
    session_repository: ParkingSessionRepositoryDep,
    parking_bay_repository: ParkingBayRepositoryDep,
    operator: User = Depends(require_facility_attendant),
) -> OperatorSessionCashPaymentResponse:
    """
    Record cash payment for an ACTIVE parking session.

    The amount is calculated by the backend at the moment the Operator
    records the cash payment. The client never supplies the amount.

    The session is transitioned to COMPLETED / PAID, but its physical
    exit_time remains unset. The existing physical checkout workflow then
    records the vehicle's actual exit and releases the bay.
    """
    try:
        parking_session = await session_repository.get_by_id(
            request.parking_session_id,
        )

        if parking_session is None:
            raise ValueError("Parking session not found.")

        facility_id = await parking_bay_repository.get_facility_id(
            parking_session.parking_bay_id,
        )

        if facility_id != operator.facility_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This parking session does not belong to your assigned facility.",
            )

        if parking_session.status != SessionStatus.ACTIVE:
            raise ValueError(
                "Only ACTIVE parking sessions can be settled by cash."
            )

        if parking_session.is_paid:
            raise ValueError("This parking session has already been paid.")

        pricing_exit_time = datetime.now(timezone.utc)
        pricing_result = await pricing_service.calculate_for_session(
            vehicle_type=parking_session.vehicle_type,
            billing_type=parking_session.billing_type,
            entry_time=parking_session.entry_time,
            exit_time=pricing_exit_time,
        )

        expected_amount = pricing_result.total_amount.quantize(
            Decimal("0.01"),
        )

        # Persist the authoritative pricing snapshot used by this payment.
        parking_session.calculated_amount = expected_amount
        parking_session.duration_minutes = pricing_result.duration_minutes

        # Mark the billing lifecycle complete before invoking the existing
        # PaymentService workflow. exit_time remains NULL until physical exit.
        parking_session.status = SessionStatus.COMPLETED

        await session_repository.save(parking_session)

        payment = SessionPaymentCreate(
            payment_method=PaymentMethod.CASH,
            payment_provider=PaymentProvider.INTERNAL,
            payment_purpose=PaymentPurpose.PARKING_SESSION,
            payment_type=PaymentType.PAYMENT,
            currency=Currency.KES,
            subtotal_amount=expected_amount,
            discount_amount=Decimal("0.00"),
            tax_amount=Decimal("0.00"),
            total_amount=expected_amount,
            parking_session_id=parking_session.id,
            customer_id=parking_session.customer_id,
            payer_name=None,
            payer_phone=None,
            payer_email=None,
            notes=(
                request.notes.strip()
                if request.notes and request.notes.strip()
                else "Operator-recorded cash payment"
            ),
            loyalty_points_to_redeem=0,
        )

        # Reuse the existing production payment workflow. Because the
        # provider is INTERNAL, it completes immediately without Safaricom.
        payment_transaction = await service.process_session_payment(payment)

        return OperatorSessionCashPaymentResponse(
            payment_id=payment_transaction.id,
            transaction_number=payment_transaction.transaction_number,
            parking_session_id=parking_session.id,
            amount=payment_transaction.total_amount,
            currency=payment_transaction.currency.value,
            status=payment_transaction.status.value,
            message=(
                "Cash payment recorded successfully. "
                "The parking session is paid and ready for physical vehicle exit."
            ),
            duration_minutes=pricing_result.duration_minutes,
            billable_minutes=pricing_result.billable_minutes,
            grace_period_applied=pricing_result.grace_period_applied,
            tariff_name=pricing_result.tariff_name,
        )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/operator/session/stk-push",
    response_model=OperatorSessionStkPushResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Operator Initiated Parking Session M-Pesa STK Push",
)
async def operator_session_stk_push(
    request: OperatorSessionStkPushRequest,
    service: PaymentServiceDep,
    session_repository: ParkingSessionRepositoryDep,
    parking_bay_repository: ParkingBayRepositoryDep,
    user_repository: UserRepositoryDep,
    vehicle_repository: VehicleRepositoryDep,
    operator: User = Depends(require_facility_attendant),
) -> OperatorSessionStkPushResponse:
    """
    Allow a facility Operator to initiate an M-Pesa STK Push for
    an active parking session at their assigned facility.

    Security:
        - Operator must have an assigned facility.
        - The parking session's bay must belong to that facility.
        - The amount is calculated exclusively by the backend.
        - The client cannot supply or override the payable amount.
    """

    try:
        parking_session = await session_repository.get_by_id(
            request.parking_session_id,
        )

        if parking_session is None:
            raise ValueError("Parking session not found.")

        facility_id = await parking_bay_repository.get_facility_id(
            parking_session.parking_bay_id,
        )

        if facility_id != operator.facility_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This parking session does not belong to your assigned facility.",
            )

        if parking_session.status.value.upper() != "ACTIVE":
            raise ValueError(
                "Only ACTIVE parking sessions can receive an Operator-initiated payment."
            )

        if parking_session.is_paid:
            raise ValueError("This parking session has already been paid.")

        if request.use_registered_number:
            _, registered_user = await _get_registered_driver_for_session(
                parking_session=parking_session,
                vehicle_repository=vehicle_repository,
                user_repository=user_repository,
            )

            if registered_user is None:
                raise ValueError(
                    "This vehicle registration is not tied to an active registered "
                    "SmartPark driver with a usable registered mobile number."
                )

            payer_phone = registered_user.phone_number
            payer_name = (
                f"{registered_user.first_name or ''} "
                f"{registered_user.last_name or ''}"
            ).strip()
            payer_email = registered_user.email
        else:
            if not request.mobile_number:
                raise ValueError(
                    "An alternative Safaricom mobile number is required."
                )

            payer_phone = request.mobile_number
            payer_name = None
            payer_email = None

        payer_phone = _normalize_operator_mpesa_phone(payer_phone)

        result = await service.initiate_operator_mpesa_session_payment(
            parking_session_id=parking_session.id,
            payer_phone=payer_phone,
            payer_name=payer_name,
            payer_email=payer_email,
            notes=request.notes,
        )

        return OperatorSessionStkPushResponse(
            payment_id=result["payment_id"],
            transaction_number=result["transaction_number"],
            parking_session_id=result["parking_session_id"],
            amount=result["amount"],
            currency=result["currency"],
            status=result["status"],
            phone_number=_mask_operator_mpesa_phone(payer_phone),
            checkout_request_id=result["checkout_request_id"],
            message=result["message"],
            duration_minutes=result["duration_minutes"],
            billable_minutes=result["billable_minutes"],
            grace_period_applied=result["grace_period_applied"],
            tariff_name=result["tariff_name"],
        )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


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
# Reversal
# ==========================================================

@router.post(
    "/reversal",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Process Reversal",
)
async def process_reversal(
    payment: ReversalCreate,
    service: PaymentServiceDep,
):
    """
    Reverse a payment transaction.
    """

    try:
        return await service.process_reversal(
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

@router.post(
    "/mpesa/callback",
    summary="Safaricom M-Pesa Callback",
)
async def mpesa_callback(
    callback: MpesaCallbackRequest,
    service: PaymentServiceDep,
):
    """
    Receive asynchronous STK Push callbacks
    from Safaricom Daraja.
    """

    try:

        #
        # Complete the pending payment.
        #
        await service.process_mpesa_callback(
            callback,
        )

    except Exception as ex:

        #
        # Logging just for now - For Debugging.
        #
        print("\n========== CALLBACK ERROR ==========")
        print(ex)

    #
    # Acknowledge receipt to Safaricom.
    #
    return {
        "ResultCode": 0,
        "ResultDesc": "Accepted",
    }

