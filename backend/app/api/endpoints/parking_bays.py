"""
API endpoints for Parking Bays.
"""

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    Query,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.schemas.parking_bay import (
    ParkingBayCreate,
    ParkingBayListResponse,
    ParkingBayResponse,
    ParkingBayUpdate,
)
from app.services.parking_bay_service import ParkingBayService

router = APIRouter(
    prefix="/parking-bays",
    tags=["Parking Bays"],
)


# ==========================================================
# Create
# ==========================================================


@router.post(
    "",
    response_model=ParkingBayResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Parking Bay",
)
async def create_parking_bay(
    payload: ParkingBayCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new parking bay.
    """

    service = ParkingBayService(db)

    return await service.create(payload)


# ==========================================================
# Read
# ==========================================================


@router.get(
    "",
    response_model=ParkingBayListResponse,
    summary="List Parking Bays",
)
async def list_parking_bays(
    skip: int = Query(
        0,
        ge=0,
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    List parking bays.
    """

    service = ParkingBayService(db)

    total, items = await service.list(
        skip=skip,
        limit=limit,
    )

    return ParkingBayListResponse(
        total=total,
        items=items,
    )


@router.get(
    "/{bay_id}",
    response_model=ParkingBayResponse,
    summary="Get Parking Bay",
)
async def get_parking_bay(
    bay_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve a parking bay by ID.
    """

    service = ParkingBayService(db)

    return await service.get_by_id(
        bay_id
    )


@router.get(
    "/zone/{zone_id}",
    response_model=ParkingBayListResponse,
    summary="List Parking Bays by Zone",
)
async def list_parking_bays_by_zone(
    zone_id: int,
    skip: int = Query(
        0,
        ge=0,
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    List all parking bays belonging to a parking zone.
    """

    service = ParkingBayService(db)

    total, items = await service.list_by_zone(
        zone_id=zone_id,
        skip=skip,
        limit=limit,
    )

    return ParkingBayListResponse(
        total=total,
        items=items,
    )


# ==========================================================
# Update
# ==========================================================


@router.put(
    "/{bay_id}",
    response_model=ParkingBayResponse,
    summary="Update Parking Bay",
)
async def update_parking_bay(
    bay_id: int,
    payload: ParkingBayUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update a parking bay.
    """

    service = ParkingBayService(db)

    return await service.update(
        bay_id,
        payload,
    )


# ==========================================================
# Delete
# ==========================================================


@router.delete(
    "/{bay_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Parking Bay",
)
async def delete_parking_bay(
    bay_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a parking bay.
    """

    service = ParkingBayService(db)

    await service.delete(
        bay_id
    )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )


# ==========================================================
# State Management
# ==========================================================


@router.patch(
    "/{bay_id}/activate",
    response_model=ParkingBayResponse,
    summary="Activate Parking Bay",
)
async def activate_parking_bay(
    bay_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Activate a parking bay.
    """

    service = ParkingBayService(db)

    return await service.activate(
        bay_id
    )


@router.patch(
    "/{bay_id}/deactivate",
    response_model=ParkingBayResponse,
    summary="Deactivate Parking Bay",
)
async def deactivate_parking_bay(
    bay_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Deactivate a parking bay.
    """

    service = ParkingBayService(db)

    return await service.deactivate(
        bay_id
    )