"""
API endpoints for Parking Sessions.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
    status,
)

from app.api.dependencies.auth import (
    get_current_active_user,
)

from app.api.dependencies.services import (
    get_parking_session_service,
)

from app.schemas.parking_session import (
    ParkingSessionCheckout,
    ParkingSessionCreate,
    ParkingSessionListResponse,
    ParkingSessionQuoteResponse,
    ParkingSessionResponse,
    ParkingSessionUpdate,
)

from app.services.parking_session_service import (
    ParkingSessionService,
)


router = APIRouter(
    prefix="/parking-sessions",
    tags=["Parking Sessions"],
)


# ==========================================================
# Vehicle Check-In
# ==========================================================


@router.post(
    "/check-in",
    response_model=ParkingSessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Check In Vehicle",
)
async def check_in_vehicle(
    payload: ParkingSessionCreate,
    service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
):
    """
    Check a vehicle into the parking facility.
    """

    return await service.check_in_vehicle(
        payload
    )


# ==========================================================
# Vehicle Check-Out
# ==========================================================


@router.post(
    "/check-out",
    response_model=ParkingSessionResponse,
    summary="Check Out Vehicle",
)
async def check_out_vehicle(
    payload: ParkingSessionCheckout,
    service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
):
    """
    Check a vehicle out of the parking facility.

    The caller specifies how the vehicle exited
    (Manual, RFID, ANPR, QR Code, Mobile App, etc.).
    """

    return await service.check_out_vehicle(
        payload
    )


# ==========================================================
# Read Operations
# ==========================================================


@router.get(
    "",
    response_model=ParkingSessionListResponse,
    summary="List Active Parking Sessions",
)
async def list_active_sessions(
    current_user=Depends(
        get_current_active_user,
    ),
    service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
):
    """
    List active parking sessions belonging only to
    the currently authenticated customer.

    The customer ID is obtained from the authenticated
    user rather than being supplied by the client.
    """

    items = await service.list_active(
        customer_id=current_user.id,
    )

    return ParkingSessionListResponse(
        total=len(items),
        items=items,
    )


@router.get(
    "/completed",
    response_model=ParkingSessionListResponse,
    summary="List Completed Parking Sessions",
)
async def list_completed_sessions(
    current_user=Depends(
        get_current_active_user,
    ),
    service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
):
    """
    List completed parking sessions belonging only to
    the currently authenticated customer.

    The customer ID is obtained from the authenticated
    user rather than being supplied by the client.
    """

    items = await service.list_completed()

    items = [
        item
        for item in items
        if item.customer_id == current_user.id
    ]

    return ParkingSessionListResponse(
        total=len(items),
        items=items,
    )


@router.get(
    "/search",
    response_model=ParkingSessionListResponse,
    summary="Search Parking Sessions",
)
async def search_sessions(
    registration: str = Query(
        ...,
        min_length=1,
    ),
    service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
):
    """
    Search parking sessions by vehicle registration.
    """

    items = await service.search_registration(
        registration
    )

    return ParkingSessionListResponse(
        total=len(items),
        items=items,
    )


@router.get(
    "/vehicle/{registration}",
    response_model=ParkingSessionListResponse,
    summary="Vehicle Parking History",
)
async def get_vehicle_history(
    registration: str,
    service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
):
    """
    Retrieve the parking history for a vehicle.
    """

    items = await service.get_vehicle_history(
        registration
    )

    return ParkingSessionListResponse(
        total=len(items),
        items=items,
    )


@router.get(
    "/number/{session_number}",
    response_model=ParkingSessionResponse,
    summary="Get Parking Session by Session Number",
)
async def get_by_session_number(
    session_number: str,
    service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
):
    """
    Retrieve a parking session using its session number.
    """

    return await service.get_by_session_number(
        session_number
    )


# ==========================================================
# Current Parking Session Quote
# ==========================================================


@router.get(
    "/{session_id}/quote",
    response_model=ParkingSessionQuoteResponse,
    summary="Get Current Parking Session Quote",
)
async def get_parking_session_quote(
    session_id: int,
    service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
):
    """
    Calculate the current pricing quote for an active
    parking session.

    This is a read-only pricing operation. It does not
    complete the session or persist the calculated amount.
    """

    return await service.get_quote(
        session_id
    )


@router.get(
    "/{session_id}",
    response_model=ParkingSessionResponse,
    summary="Get Parking Session",
)
async def get_parking_session(
    session_id: int,
    service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
):
    """
    Retrieve a parking session by ID.
    """

    return await service.get_by_id(
        session_id
    )


# ==========================================================
# Update
# ==========================================================


@router.put(
    "/{session_id}",
    response_model=ParkingSessionResponse,
    summary="Update Parking Session",
)
async def update_parking_session(
    session_id: int,
    payload: ParkingSessionUpdate,
    service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
):
    """
    Update an existing parking session.
    """

    return await service.update(
        session_id,
        payload,
    )


# ==========================================================
# Delete
# ==========================================================


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Parking Session",
)
async def delete_parking_session(
    session_id: int,
    service: ParkingSessionService = Depends(
        get_parking_session_service,
    ),
):
    """
    Delete a completed parking session.
    """

    await service.delete(
        session_id
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )