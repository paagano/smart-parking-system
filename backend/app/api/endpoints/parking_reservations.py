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

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.auth import (
    get_current_active_user,
)

from app.models.user import User

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
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: ParkingReservationServiceDep,
) -> ParkingReservationResponse:
    """
    Create a new parking reservation.
    """

    reservation = await service.create_reservation(
        data=reservation_data,
        customer_id=current_user.id,
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
# Reservation Statistics
# ==========================================================


@router.get(
    "/statistics/active-count",
    summary="Count Active Reservations",
)
async def count_active_reservations(
    service: ParkingReservationServiceDep,
) -> dict[str, int]:
    """
    Return the number of active reservations.
    """

    count = await service.count_active_reservations()

    return {
        "active_reservations": count,
    }


@router.get(
    "/statistics/customer/{customer_id}",
    summary="Count Customer Reservations",
)
async def count_customer_reservations(
    customer_id: int,
    service: ParkingReservationServiceDep,
) -> dict[str, int]:
    """
    Return the number of reservations belonging
    to a customer.
    """

    count = await service.count_customer_reservations(
        customer_id,
    )

    return {
        "customer_id": customer_id,
        "reservations": count,
    }


@router.get(
    "/statistics/vehicle/{vehicle_registration}",
    summary="Count Vehicle Reservations",
)

async def count_vehicle_reservations(
    vehicle_registration: str,
    service: ParkingReservationServiceDep,
) -> dict[str, str | int]:
    """
    Return the number of reservations
    for a vehicle.
    """

    count = await service.count_vehicle_reservations(
        vehicle_registration,
    )

    return {
        "vehicle_registration": vehicle_registration.upper(),
        "reservations": count,
    }


# ==========================================================
# Health
# ==========================================================


@router.get(
    "/health",
    summary="Reservation Module Health",
)
async def reservation_health() -> dict[str, str]:
    """
    Health endpoint.
    """

    return {
        "status": "healthy",
        "module": "parking_reservations",
    }


# ==========================================================
# Customer Reservations
# ==========================================================


@router.get(
    "/customer/{customer_id}",
    response_model=ParkingReservationListResponse,
    summary="Customer Reservations",
)
async def get_customer_reservations(
    customer_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationListResponse:
    """
    Retrieve all reservations belonging to a customer.
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
    summary="Customer Active Reservations",
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
# Vehicle Reservations
# ==========================================================


@router.get(
    "/vehicle/{vehicle_registration}",
    response_model=ParkingReservationListResponse,
    summary="Vehicle Reservations",
)
async def get_vehicle_reservations(
    vehicle_registration: str,
    service: ParkingReservationServiceDep,
) -> ParkingReservationListResponse:
    """
    Retrieve all reservations for a vehicle.
    """

    reservations = await service.get_by_vehicle(
        vehicle_registration,
    )

    return ParkingReservationListResponse(
        items=reservations,
        total=len(reservations),
    )


@router.get(
    "/vehicle/{vehicle_registration}/active",
    response_model=ParkingReservationListResponse,
    summary="Active Vehicle Reservations",
)
async def get_active_vehicle_reservations(
    vehicle_registration: str,
    service: ParkingReservationServiceDep,
) -> ParkingReservationListResponse:
    """
    Retrieve active reservations for a vehicle.
    """

    reservations = await service.get_active_by_vehicle(
        vehicle_registration,
    )

    return ParkingReservationListResponse(
        items=reservations,
        total=len(reservations),
    )


# ==========================================================
# Parking Bay Reservations
# ==========================================================


@router.get(
    "/parking-bay/{parking_bay_id}",
    response_model=ParkingReservationListResponse,
    summary="Parking Bay Reservations",
)
async def get_parking_bay_reservations(
    parking_bay_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationListResponse:
    """
    Retrieve reservations for a parking bay.
    """

    reservations = await service.get_by_parking_bay(
        parking_bay_id,
    )

    return ParkingReservationListResponse(
        items=reservations,
        total=len(reservations),
    )


@router.get(
    "/parking-bay/{parking_bay_id}/active",
    response_model=ParkingReservationListResponse,
    summary="Active Parking Bay Reservations",
)
async def get_active_parking_bay_reservations(
    parking_bay_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationListResponse:
    """
    Retrieve active reservations for a parking bay.
    """

    reservations = await service.get_active_by_parking_bay(
        parking_bay_id,
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
    Mark a parking reservation as expired.
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
# Expire Overdue Reservations
# ==========================================================


@router.post(
    "/expire-overdue",
    summary="Expire Overdue Reservations",
)
async def expire_overdue_reservations(
    service: ParkingReservationServiceDep,
) -> dict:
    """
    Expire all overdue reservations.
    """

    count = await service.expire_overdue_reservations()

    return {
        "expired_reservations": count,
    }


# ==========================================================

@router.get(
    "/customer/{customer_id}",
    response_model=ParkingReservationListResponse,
    summary="Customer Reservations",
)
async def get_customer_reservations(
    customer_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationListResponse:
    """
    Retrieve all reservations belonging to a customer.
    """

    reservations = await service.get_customer_reservations(
        customer_id,
    )

    return ParkingReservationListResponse(
        items=reservations,
        total=len(reservations),
    )


# ==========================================================
# Customer Active Reservations
# ==========================================================


@router.get(
    "/customer/{customer_id}/active",
    response_model=ParkingReservationListResponse,
    summary="Customer Active Reservations",
)
async def get_active_customer_reservations(
    customer_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationListResponse:
    """
    Retrieve active reservations for a customer.
    """

    reservations = await service.get_active_customer_reservations(
        customer_id,
    )

    return ParkingReservationListResponse(
        items=reservations,
        total=len(reservations),
    )


# ==========================================================
# Check In Reservation
# ==========================================================


@router.patch(
    "/{reservation_id}/check-in",
    response_model=ParkingReservationResponse,
    summary="Check In Reservation",
)
async def check_in_reservation(
    reservation_id: int,
    service: ParkingReservationServiceDep,
) -> ParkingReservationResponse:
    """
    Check in a reservation and create an active parking session.
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
# Statistics
# ==========================================================
@router.get(
    "/statistics/active-count",
    summary="Active Reservation Count",
)
async def get_active_reservation_count(
    service: ParkingReservationServiceDep,
) -> dict:
    """
    Retrieve the number of active reservations.
    """

    count = await service.count_active_reservations()

    return {
        "active_reservations": count,
    }