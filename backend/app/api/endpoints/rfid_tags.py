"""
RFID Tag API Endpoints.

Provides authenticated RFID tag management operations and
RFID-based parking access operations.

RFID reader flow:

    Physical RFID Reader
            ↓
        RFID Tag Registry
            ↓
          Vehicle
            ↓
      Registered Customer
            ↓
       Parking Session
"""

from __future__ import annotations

from datetime import timedelta

from app.utils.datetime import utc_now

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.api.dependencies.auth import (
    ensure_operator_facility_access,
    require_facility_attendant,
)

from app.api.dependencies.repositories import (
    DbSession,
)

from app.api.dependencies.services import (
    RFIDTagServiceDep,
    ParkingReservationServiceDep,
    PaymentServiceDep,
    get_parking_session_service,
)

from app.models.enums import (
    EntryMethod,
    ExitMethod,
    ReservationStatus,
    SessionSource,
)

from app.models.user import User

from app.schemas.parking_session import (
    ParkingSessionCheckout,
    ParkingSessionCreate,
    ParkingSessionResponse,
)

from app.schemas.rfid_tag import (
    RFIDParkingCheckInRequest,
    RFIDParkingCheckOutRequest,
    RFIDTagAssign,
    RFIDTagCreate,
    RFIDTagResponse,
    RFIDTagScanRequest,
    RFIDTagScanResponse,
    RFIDTagVehicleResponse,
    RFIDParkingCheckOutResponse,
)

from app.services.parking_session_service import (
    ParkingSessionService,
)


# ==========================================================
# Router
# ==========================================================

router = APIRouter(
    prefix="/rfid-tags",
    tags=["RFID Tags"],
)


# ==========================================================
# Register RFID Tag
# ==========================================================

@router.post(
    "",
    response_model=RFIDTagResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register RFID Tag",
)
async def create_rfid_tag(
    data: RFIDTagCreate,
    _: User = Depends(require_facility_attendant),
    service: RFIDTagServiceDep = None,
) -> RFIDTagResponse:
    """
    Register a new physical RFID tag.

    The RFID tag is initially created as unassigned and active.
    """

    try:
        return await service.create_rfid_tag(
            uid=data.uid,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# List RFID Tags
# ==========================================================

@router.get(
    "",
    response_model=list[RFIDTagResponse],
    summary="List RFID Tags",
)
async def get_rfid_tags(
    _: User = Depends(require_facility_attendant),
    service: RFIDTagServiceDep = None,
) -> list[RFIDTagResponse]:
    """
    Retrieve all registered RFID tags.
    """

    return await service.get_all_rfid_tags()


# ==========================================================
# RFID Reader Scan
# ==========================================================

@router.post(
    "/scan",
    response_model=RFIDTagScanResponse,
    summary="Resolve RFID Reader Scan",
)
async def scan_rfid_tag(
    data: RFIDTagScanRequest,
    _: User = Depends(require_facility_attendant),
    service: RFIDTagServiceDep = None,
    db: DbSession = None,
) -> RFIDTagScanResponse:
    """
    Resolve a physical RFID reader event.

    The supplied UID is resolved through:

        RFID UID
            ↓
        RFID Tag
            ↓
        Vehicle
            ↓
        Registered Customer

    Only active RFID tags assigned to active vehicles are
    considered valid parking-access candidates.

    The registered customer's name is returned for operator-facing
    RFID scan confirmation.
    """

    try:
        rfid_tag, vehicle = await service.resolve_rfid_tag(
            uid=data.uid,
        )

        customer = await db.get(User, vehicle.customer_id)

        if customer is None:
            raise ValueError(
                "Registered customer for this RFID vehicle could not be found."
            )

        customer_name = f"{customer.first_name} {customer.last_name}".strip()

        return RFIDTagScanResponse(
            rfid_tag=RFIDTagVehicleResponse.model_validate(
                rfid_tag,
            ),
            vehicle_id=vehicle.id,
            registration_number=vehicle.registration_number,
            vehicle_type=vehicle.vehicle_type,
            customer_id=vehicle.customer_id,
            customer_name=customer_name,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# RFID Parking Check-In
# ==========================================================

@router.post(
    "/check-in",
    response_model=ParkingSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Check In Vehicle Using RFID",
)
async def check_in_vehicle_using_rfid(
    data: RFIDParkingCheckInRequest,
    current_user: User = Depends(require_facility_attendant),
    rfid_service: RFIDTagServiceDep = None,
    parking_session_service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
    reservation_service: ParkingReservationServiceDep = None,
) -> ParkingSessionResponse:
    """
    Check a registered vehicle into a parking facility
    using an RFID tag.

    RFID resolves:

        UID
            ↓
        RFID Tag
            ↓
        Vehicle
            ↓
        Registered Customer

    If the registered vehicle has an applicable reservation,
    the reservation parking-session workflow is used and the
    resulting session retains the reservation relationship.

    If no applicable reservation exists, the registered vehicle
    follows the normal registered-user DRIVE_IN workflow.

    RFID never accepts a manually supplied vehicle identity.
    """

    try:
        # ------------------------------------------------------
        # Resolve RFID
        # ------------------------------------------------------

        _, vehicle = await rfid_service.resolve_rfid_tag(
            uid=data.uid,
        )

        # ------------------------------------------------------
        # Find an applicable reservation for this registered
        # vehicle/customer.
        # ------------------------------------------------------

        now = utc_now()

        active_reservations = (
            await reservation_service.get_active_customer_reservations(
                vehicle.customer_id,
            )
        )

        applicable_reservations = [
            reservation
            for reservation in active_reservations
            if reservation.vehicle_id == vehicle.id
            and reservation.status in (
                ReservationStatus.CREATED,
                ReservationStatus.CONFIRMED,
            )
            and now >= (
                reservation.reserved_from
                - timedelta(minutes=30)
            )
            and now < reservation.reserved_until
        ]

        if len(applicable_reservations) > 1:
            raise ValueError(
                "Multiple active reservations were found for this RFID vehicle. "
                "The vehicle cannot be checked in automatically until the "
                "reservation conflict is resolved."
            )

        reservation = (
            applicable_reservations[0]
            if applicable_reservations
            else None
        )

        # ------------------------------------------------------
        # Reservation RFID Check-In
        #
        # The reservation's own parking bay is authoritative.
        # ------------------------------------------------------

        if reservation is not None:
            reservation_facility_id = await (
                parking_session_service
                .parking_bay_repository
                .get_facility_id(
                    reservation.parking_bay_id,
                )
            )

            ensure_operator_facility_access(
                current_user,
                reservation_facility_id,
            )

            selected_bay_facility_id = await (
                parking_session_service
                .parking_bay_repository
                .get_facility_id(
                    data.parking_bay_id,
                )
            )

            ensure_operator_facility_access(
                current_user,
                selected_bay_facility_id,
            )

            # Reuse the existing reservation-to-session workflow while
            # explicitly recording RFID as the entry method. The reserved
            # bay is selected by the frontend by default, but the operator
            # may deliberately choose another available bay when required.
            parking_session = (
                await parking_session_service.create_from_reservation(
                    reservation,
                    entry_method=EntryMethod.RFID,
                    parking_bay_id=data.parking_bay_id,
                )
            )

            # Keep the reservation lifecycle synchronized with the
            # existing reservation check-in workflow.
            reservation.status = ReservationStatus.CHECKED_IN
            reservation.checked_in_at = utc_now()
            reservation.updated_at = utc_now()

            await reservation_service.repository.save(
                reservation,
            )

            await reservation_service.repository.commit()

            await reservation_service.repository.refresh(
                reservation,
            )

            return parking_session

        # ------------------------------------------------------
        # Registered-user RFID Drive-In Check-In
        #
        # No applicable reservation exists, so the registered
        # vehicle follows the normal drive-in workflow.
        # ------------------------------------------------------

        facility_id = await (
            parking_session_service
            .parking_bay_repository
            .get_facility_id(
                data.parking_bay_id,
            )
        )

        ensure_operator_facility_access(
            current_user,
            facility_id,
        )

        parking_session_data = ParkingSessionCreate(
            parking_bay_id=data.parking_bay_id,
            customer_id=vehicle.customer_id,
            vehicle_id=vehicle.id,
            billing_type=data.billing_type,
            session_source=SessionSource.DRIVE_IN,
            entry_method=EntryMethod.RFID,
            expected_exit_time=data.expected_exit_time,
            notes=data.notes,
        )

        # ------------------------------------------------------
        # Use Existing Parking Session Workflow
        # ------------------------------------------------------

        return await parking_session_service.check_in_vehicle(
            parking_session_data,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# RFID Parking Check-Out
# ==========================================================

@router.post(
    "/check-out",
    response_model=RFIDParkingCheckOutResponse,
    summary="Check Out Vehicle Using RFID",
)
async def check_out_vehicle_using_rfid(
    data: RFIDParkingCheckOutRequest,
    current_user: User = Depends(require_facility_attendant),
    rfid_service: RFIDTagServiceDep = None,
    parking_session_service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
    payment_service: PaymentServiceDep = None,
) -> RFIDParkingCheckOutResponse:
    """
    Check out a vehicle using RFID and automatically settle the
    parking charge from the registered customer wallet when
    sufficient funds are available.

    If the wallet balance is insufficient, no physical checkout
    occurs and the response tells the operator that an external
    payment method is required.

    After an external payment succeeds, calling this endpoint
    again finalizes the physical RFID checkout.
    """

    try:
        # ------------------------------------------------------
        # Resolve RFID
        # ------------------------------------------------------

        _, vehicle = await rfid_service.resolve_rfid_tag(
            uid=data.uid,
        )

        registration = vehicle.registration_number.strip().upper()

        # ------------------------------------------------------
        # Locate the vehicle's parking session
        # ------------------------------------------------------

        sessions = await (
            parking_session_service
            .repository
            .get_by_registration(
                registration,
            )
        )

        pending_sessions = [
            session
            for session in sessions
            if session.exit_time is None
            and session.status.value in {"ACTIVE", "COMPLETED"}
        ]

        if len(pending_sessions) > 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Multiple pending parking sessions found for this vehicle.",
            )

        if not pending_sessions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No pending parking session found for this RFID vehicle.",
            )

        parking_session = pending_sessions[0]

        # ------------------------------------------------------
        # Validate Operator Facility Access
        # ------------------------------------------------------

        facility_id = await (
            parking_session_service
            .parking_bay_repository
            .get_facility_id(
                parking_session.parking_bay_id,
            )
        )

        ensure_operator_facility_access(
            current_user,
            facility_id,
        )

        # ------------------------------------------------------
        # Already paid: finalize physical checkout
        # ------------------------------------------------------

        if (
            parking_session.status.value == "COMPLETED"
            and parking_session.is_paid
        ):
            checkout_data = ParkingSessionCheckout(
                vehicle_registration=registration,
                exit_method=ExitMethod.RFID,
                notes=data.notes,
            )

            checked_out = await parking_session_service.check_out_vehicle(
                checkout_data,
            )

            return RFIDParkingCheckOutResponse(
                parking_session_id=checked_out.id,
                vehicle_id=vehicle.id,
                registration_number=registration,
                customer_id=vehicle.customer_id,
                current_bill=checked_out.paid_amount or 0,
                wallet_balance=None,
                wallet_sufficient=False,
                payment_required=False,
                wallet_payment_successful=False,
                payment_transaction_id=(
                    checked_out.last_payment_transaction_id
                    if hasattr(
                        checked_out,
                        "last_payment_transaction_id",
                    )
                    else None
                ),
                payment_reference=(
                    checked_out.last_payment_transaction.reference
                    if getattr(
                        checked_out,
                        "last_payment_transaction",
                        None,
                    )
                    else None
                ),
                checkout_completed=True,
                message=(
                    "Parking payment already completed. "
                    "Vehicle checked out successfully using RFID."
                ),
            )

        # ------------------------------------------------------
        # Wallet quote for an ACTIVE session
        # ------------------------------------------------------

        quote = await payment_service.get_rfid_wallet_checkout_quote(
            parking_session_id=parking_session.id,
            customer_id=vehicle.customer_id,
        )

        current_bill = quote["current_bill"]
        wallet_balance = quote["wallet_balance"]
        wallet_sufficient = quote["wallet_sufficient"]

        # ------------------------------------------------------
        # Insufficient wallet balance -> external payment required
        # ------------------------------------------------------

        if not wallet_sufficient:
            return RFIDParkingCheckOutResponse(
                parking_session_id=parking_session.id,
                vehicle_id=vehicle.id,
                registration_number=registration,
                customer_id=vehicle.customer_id,
                current_bill=current_bill,
                wallet_balance=wallet_balance,
                wallet_sufficient=False,
                payment_required=True,
                wallet_payment_successful=False,
                payment_transaction_id=None,
                payment_reference=None,
                checkout_completed=False,
                message=(
                    "Insufficient wallet balance. External payment is required "
                    "before the vehicle can exit."
                ),
            )

        # ------------------------------------------------------
        # Automatically settle from registered customer wallet
        # ------------------------------------------------------

        payment = await payment_service.process_rfid_wallet_payment(
            parking_session_id=parking_session.id,
            customer_id=vehicle.customer_id,
        )

        # ------------------------------------------------------
        # Wallet payment changes the session to COMPLETED.
        # Finalize the physical RFID checkout using the existing
        # ParkingSessionService workflow.
        # ------------------------------------------------------

        checkout_data = ParkingSessionCheckout(
            vehicle_registration=registration,
            exit_method=ExitMethod.RFID,
            notes=data.notes,
        )

        checked_out = await parking_session_service.check_out_vehicle(
            checkout_data,
        )

        return RFIDParkingCheckOutResponse(
            parking_session_id=checked_out.id,
            vehicle_id=vehicle.id,
            registration_number=registration,
            customer_id=vehicle.customer_id,
            current_bill=current_bill,
            wallet_balance=wallet_balance,
            wallet_sufficient=True,
            payment_required=False,
            wallet_payment_successful=True,
            payment_transaction_id=payment.id,
            payment_reference=payment.transaction_number,
            checkout_completed=True,
            message=(
                "Parking payment completed from wallet. "
                "Vehicle checked out successfully using RFID."
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# Get RFID Tag By ID
# ==========================================================

@router.get(
    "/{rfid_tag_id}",
    response_model=RFIDTagResponse,
    summary="Get RFID Tag",
)
async def get_rfid_tag(
    rfid_tag_id: int,
    _: User = Depends(require_facility_attendant),
    service: RFIDTagServiceDep = None,
) -> RFIDTagResponse:
    """
    Retrieve a registered RFID tag by ID.
    """

    try:
        return await service.get_rfid_tag(
            rfid_tag_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# Get RFID Tag By UID
# ==========================================================

@router.get(
    "/uid/{uid}",
    response_model=RFIDTagResponse,
    summary="Get RFID Tag By UID",
)
async def get_rfid_tag_by_uid(
    uid: str,
    _: User = Depends(require_facility_attendant),
    service: RFIDTagServiceDep = None,
) -> RFIDTagResponse:
    """
    Retrieve a registered RFID tag using its physical UID.
    """

    try:
        return await service.get_by_uid(
            uid,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# Assign RFID Tag To Vehicle
# ==========================================================

@router.post(
    "/{rfid_tag_id}/assign",
    response_model=RFIDTagResponse,
    summary="Assign RFID Tag To Vehicle",
)
async def assign_rfid_tag(
    rfid_tag_id: int,
    data: RFIDTagAssign,
    _: User = Depends(require_facility_attendant),
    service: RFIDTagServiceDep = None,
) -> RFIDTagResponse:
    """
    Assign an RFID tag to a registered vehicle.
    """

    try:
        return await service.assign_rfid_tag(
            rfid_tag_id=rfid_tag_id,
            vehicle_id=data.vehicle_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# Unassign RFID Tag
# ==========================================================

@router.post(
    "/{rfid_tag_id}/unassign",
    response_model=RFIDTagResponse,
    summary="Unassign RFID Tag",
)
async def unassign_rfid_tag(
    rfid_tag_id: int,
    _: User = Depends(require_facility_attendant),
    service: RFIDTagServiceDep = None,
) -> RFIDTagResponse:
    """
    Remove the vehicle assignment from an RFID tag.

    The RFID tag itself remains registered and active.
    """

    try:
        return await service.unassign_rfid_tag(
            rfid_tag_id=rfid_tag_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# Activate RFID Tag
# ==========================================================

@router.patch(
    "/{rfid_tag_id}/activate",
    response_model=RFIDTagResponse,
    summary="Activate RFID Tag",
)
async def activate_rfid_tag(
    rfid_tag_id: int,
    _: User = Depends(require_facility_attendant),
    service: RFIDTagServiceDep = None,
) -> RFIDTagResponse:
    """
    Activate an RFID tag.

    An inactive tag cannot be used for RFID parking access.
    """

    try:
        return await service.activate_rfid_tag(
            rfid_tag_id=rfid_tag_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# Deactivate RFID Tag
# ==========================================================

@router.patch(
    "/{rfid_tag_id}/deactivate",
    response_model=RFIDTagResponse,
    summary="Deactivate RFID Tag",
)
async def deactivate_rfid_tag(
    rfid_tag_id: int,
    _: User = Depends(require_facility_attendant),
    service: RFIDTagServiceDep = None,
) -> RFIDTagResponse:
    """
    Deactivate an RFID tag.

    The tag remains registered but cannot be used for
    RFID parking access.
    """

    try:
        return await service.deactivate_rfid_tag(
            rfid_tag_id=rfid_tag_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc