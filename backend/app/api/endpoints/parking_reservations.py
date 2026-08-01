"""
Parking Reservation Endpoints.

REST API endpoints for Parking Reservation management.

Responsibilities
----------------
- CRUD operations
- Reservation lifecycle
- Customer reservation queries

Business logic belongs in ParkingReservationService.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    status,
)

from app.api.dependencies.reservations import (
    ParkingReservationServiceDep,
)

from app.schemas.parking_reservation import (
    ParkingReservationCreate,
    ParkingReservationListResponse,
    ParkingReservationResponse,
    ParkingReservationUpdate,
)

router = APIRouter(
    prefix="/parking-reservations",
    tags=["Parking Reservations"],
)

# ==========================================================
# Create Reservation
# ==========================================================


@router.post(
    "",
    response_model=ParkingReservationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Parking Reservation",
)
async def create_parking_reservation(
    reservation_data: ParkingReservationCreate,
    service: ParkingReservationServiceDep,
) -> ParkingReservationResponse:
    """
    Create a new parking reservation.
    """

    reservation = await service.create_reservation(
        reservation_data,
    )

    return reservation


# ==========================================================
# List Reservations
# ==========================================================


@router.get(
    "",
    response_model=ParkingReservationListResponse,
    summary="List Parking Reservations",
)
async def get_parking_reservations(
    service: ParkingReservationServiceDep,
) -> ParkingReservationListResponse:
    """
    Retrieve all parking reservations.
    """

    reservations = await service.get_all()

    return ParkingReservationListResponse(
        items=reservations,
        total=len(reservations),
    )


# ==========================================================
# Search Reservations
# ==========================================================


@router.get(
    "/search",
    response_model=ParkingReservationListResponse,
    summary="Search Parking Reservations",
)
async def search_parking_reservations(
    service: ParkingReservationServiceDep,
    search_term: str = Query(
        ...,
        min_length=1,
        description=(
            "Search by reservation number "
            "or vehicle registration."
        ),
    ),
) -> ParkingReservationListResponse:
    """
    Search parking reservations.
    """

    reservations = await service.search(
        search_term=search_term,
    )

    return ParkingReservationListResponse(
        items=reservations,
        total=len(reservations),
    )

# ==========================================================
# Get Reservation by ID
# ==========================================================


@router.get(
    "/{reservation_id}",
    response_model=ParkingReservationResponse,
    summary="Get Parking Reservation",
)
async def get_parking_reservation(
    reservation_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationResponse:
    """
    Retrieve a parking reservation by its identifier.
    """

    reservation = await service.get_by_id(
        reservation_id,
    )

    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking reservation not found.",
        )

    return reservation


# ==========================================================
# Update Reservation
# ==========================================================


@router.put(
    "/{reservation_id}",
    response_model=ParkingReservationResponse,
    summary="Update Parking Reservation",
)
async def update_parking_reservation(
    reservation_id: int,
    reservation_data: ParkingReservationUpdate,
    service: ParkingReservationServiceDep,
) -> ParkingReservationResponse:
    """
    Update an existing parking reservation.
    """

    reservation = await service.update_reservation(
        reservation_id=reservation_id,
        data=reservation_data,
    )

    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking reservation not found.",
        )

    return reservation


# ==========================================================
# Delete Reservation
# ==========================================================


@router.delete(
    "/{reservation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Parking Reservation",
)
async def delete_parking_reservation(
    reservation_id: int,
    service: ParkingReservationServiceDep,
) -> None:
    """
    Delete a parking reservation.
    """

    deleted = await service.delete_reservation(
        reservation_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking reservation not found.",
        )

    return None

# ==========================================================
# Confirm Reservation
# ==========================================================


@router.patch(
    "/{reservation_id}/confirm",
    response_model=ParkingReservationResponse,
    summary="Confirm Parking Reservation",
)
async def confirm_parking_reservation(
    reservation_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationResponse:
    """
    Confirm a parking reservation.
    """

    reservation = await service.confirm_reservation(
        reservation_id,
    )

    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking reservation not found.",
        )

    return reservation


# ==========================================================
# Cancel Reservation
# ==========================================================


@router.patch(
    "/{reservation_id}/cancel",
    response_model=ParkingReservationResponse,
    summary="Cancel Parking Reservation",
)
async def cancel_parking_reservation(
    reservation_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationResponse:
    """
    Cancel a parking reservation.
    """

    reservation = await service.cancel_reservation(
        reservation_id,
    )

    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking reservation not found.",
        )

    return reservation


# ==========================================================
# Expire Reservation
# ==========================================================


@router.patch(
    "/{reservation_id}/expire",
    response_model=ParkingReservationResponse,
    summary="Expire Parking Reservation",
)
async def expire_parking_reservation(
    reservation_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationResponse:
    """
    Mark a reservation as expired.
    """

    reservation = await service.expire_reservation(
        reservation_id,
    )

    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking reservation not found.",
        )

    return reservation


# ==========================================================
# Check In Reservation
# ==========================================================


@router.patch(
    "/{reservation_id}/check-in",
    response_model=ParkingReservationResponse,
    summary="Check In Reservation",
)
async def check_in_parking_reservation(
    reservation_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationResponse:
    """
    Check in a reservation and convert it into
    an active parking session.
    """

    reservation = await service.check_in(
        reservation_id,
    )

    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking reservation not found.",
        )

    return reservation

# ==========================================================
# Customer Reservations
# ==========================================================


@router.get(
    "/customer/{customer_id}",
    response_model=ParkingReservationListResponse,
    summary="Get Customer Reservations",
)
async def get_customer_reservations(
    customer_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationListResponse:
    """
    Retrieve all reservations for a customer.
    """

    reservations = await service.get_customer_reservations(
        customer_id,
    )

    return ParkingReservationListResponse(
        items=reservations,
        total=len(reservations),
    )


@router.get(
    "/customer/{customer_id}/active",
    response_model=ParkingReservationListResponse,
    summary="Get Active Customer Reservations",
)
async def get_active_customer_reservations(
    customer_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationListResponse:
    """
    Retrieve active reservations for a customer.
    """

    reservations = (
        await service.get_active_customer_reservations(
            customer_id,
        )
    )

    return ParkingReservationListResponse(
        items=reservations,
        total=len(reservations),
    )


# ==========================================================
# Reservation Statistics
# ==========================================================


@router.get(
    "/statistics",
    summary="Reservation Statistics",
)
async def reservation_statistics(
    service: ParkingReservationServiceDep,
) -> dict:
    """
    Retrieve reservation statistics.
    """

    active = await service.count_active_reservations()

    return {
        "active_reservations": active,
    }