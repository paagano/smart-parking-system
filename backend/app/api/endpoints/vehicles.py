"""
Vehicle API Endpoints.

Provides authenticated CRUD and lifecycle operations
for customer vehicles.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)

from app.api.dependencies.auth import (
    get_current_active_user,
)
from app.api.dependencies.services import (
    VehicleServiceDep,
)

from app.models.user import User

from app.schemas.vehicle import (
    VehicleCreate,
    VehicleListResponse,
    VehicleResponse,
    VehicleUpdate,
)


# ==========================================================
# Router
# ==========================================================

router = APIRouter(
    prefix="/vehicles",
    tags=["Vehicles"],
)


# ==========================================================
# Create Vehicle
# ==========================================================

@router.post(
    "",
    response_model=VehicleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_vehicle(
    data: VehicleCreate,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: VehicleServiceDep,
) -> VehicleResponse:
    """
    Register a new vehicle for the authenticated customer.
    """

    try:
        vehicle = await service.create_vehicle(
            customer_id=current_user.id,
            data=data,
        )

        return vehicle

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


# ==========================================================
# List My Vehicles
# ==========================================================

@router.get(
    "",
    response_model=VehicleListResponse,
)
async def get_my_vehicles(
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: VehicleServiceDep,
) -> VehicleListResponse:
    """
    Retrieve all vehicles belonging to the authenticated customer.
    """

    vehicles = await service.get_customer_vehicles(
        customer_id=current_user.id,
    )

    return VehicleListResponse(
        vehicles=vehicles,
        total=len(vehicles),
    )


# ==========================================================
# Get Vehicle By Registration Number
# ==========================================================

@router.get(
    "/registration/{registration_number}",
    response_model=VehicleResponse,
)
async def get_vehicle_by_registration(
    registration_number: str,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: VehicleServiceDep,
) -> VehicleResponse:
    """
    Retrieve one of the authenticated customer's vehicles
    by registration number.

    This endpoint will also be useful later for ANPR integration.
    """

    try:
        vehicle = await service.get_by_registration_number(
            registration_number,
        )

        if vehicle.customer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this vehicle.",
            )

        return vehicle

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# Get Vehicle
# ==========================================================

@router.get(
    "/{vehicle_id}",
    response_model=VehicleResponse,
)
async def get_vehicle(
    vehicle_id: int,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: VehicleServiceDep,
) -> VehicleResponse:
    """
    Retrieve one of the authenticated customer's vehicles.
    """

    try:
        vehicle = await service.get_vehicle(
            vehicle_id,
        )

        if vehicle.customer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to access this vehicle.",
            )

        return vehicle

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


# ==========================================================
# Update Vehicle
# ==========================================================

@router.patch(
    "/{vehicle_id}",
    response_model=VehicleResponse,
)
async def update_vehicle(
    vehicle_id: int,
    data: VehicleUpdate,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: VehicleServiceDep,
) -> VehicleResponse:
    """
    Update an authenticated customer's vehicle.
    """

    try:
        vehicle = await service.update_vehicle(
            vehicle_id=vehicle_id,
            customer_id=current_user.id,
            data=data,
        )

        return vehicle

    except ValueError as exc:
        message = str(exc)

        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        if "not authorized" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ==========================================================
# Set Default Vehicle
# ==========================================================

@router.patch(
    "/{vehicle_id}/default",
    response_model=VehicleResponse,
)
async def set_default_vehicle(
    vehicle_id: int,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: VehicleServiceDep,
) -> VehicleResponse:
    """
    Set a vehicle as the authenticated customer's default vehicle.
    """

    try:
        vehicle = await service.set_default_vehicle(
            vehicle_id=vehicle_id,
            customer_id=current_user.id,
        )

        return vehicle

    except ValueError as exc:
        message = str(exc)

        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        if "not authorized" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ==========================================================
# Activate Vehicle
# ==========================================================

@router.patch(
    "/{vehicle_id}/activate",
    response_model=VehicleResponse,
)
async def activate_vehicle(
    vehicle_id: int,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: VehicleServiceDep,
) -> VehicleResponse:
    """
    Reactivate an authenticated customer's vehicle.
    """

    try:
        vehicle = await service.activate_vehicle(
            vehicle_id=vehicle_id,
            customer_id=current_user.id,
        )

        return vehicle

    except ValueError as exc:
        message = str(exc)

        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        if "not authorized" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ==========================================================
# Deactivate Vehicle
# ==========================================================

@router.patch(
    "/{vehicle_id}/deactivate",
    response_model=VehicleResponse,
)
async def deactivate_vehicle(
    vehicle_id: int,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: VehicleServiceDep,
) -> VehicleResponse:
    """
    Deactivate an authenticated customer's vehicle.

    The vehicle remains in the database for historical records.
    """

    try:
        vehicle = await service.deactivate_vehicle(
            vehicle_id=vehicle_id,
            customer_id=current_user.id,
        )

        return vehicle

    except ValueError as exc:
        message = str(exc)

        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        if "not authorized" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc


# ==========================================================
# Delete Vehicle
# ==========================================================

@router.delete(
    "/{vehicle_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_vehicle(
    vehicle_id: int,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: VehicleServiceDep,
) -> None:
    """
    Permanently delete an authenticated customer's vehicle.

    Use this when the customer no longer owns the vehicle,
    for example when the vehicle has been sold or transferred.

    This is different from deactivation, which keeps the
    vehicle record for historical purposes.
    """

    try:
        await service.delete_vehicle(
            vehicle_id=vehicle_id,
            customer_id=current_user.id,
        )

    except ValueError as exc:
        message = str(exc)

        if "not found" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=message,
            ) from exc

        if "not authorized" in message.lower():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=message,
            ) from exc

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=message,
        ) from exc