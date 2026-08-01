"""
Parking Tariff Endpoints.

REST API endpoints for Parking Tariff management.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
    status,
)

from app.api.dependencies.pricing import (
    ParkingTariffServiceDep,
)

from app.models.enums import (
    BillingType,
    VehicleType,
)

from app.schemas.parking_tariff import (
    ParkingTariffCreate,
    ParkingTariffListResponse,
    ParkingTariffResponse,
    ParkingTariffUpdate,
)

router = APIRouter(
    prefix="/parking-tariffs",
    tags=["Parking Tariffs"],
)

# ==========================================================
# Collection Endpoints
# ==========================================================


@router.post(
    "",
    response_model=ParkingTariffResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Parking Tariff",
)
async def create_parking_tariff(
    tariff_data: ParkingTariffCreate,
    service: ParkingTariffServiceDep,
) -> ParkingTariffResponse:
    """
    Create a parking tariff.
    """

    return await service.create_tariff(
        tariff_data
    )


@router.get(
    "",
    response_model=ParkingTariffListResponse,
    summary="List Parking Tariffs",
)
async def get_parking_tariffs(
    service: ParkingTariffServiceDep,
) -> ParkingTariffListResponse:
    """
    Retrieve all parking tariffs.
    """

    tariffs = await service.get_all()

    return ParkingTariffListResponse(
        items=tariffs,
        total=len(tariffs),
    )


# ==========================================================
# Search & Lookup
# ==========================================================


@router.get(
    "/search",
    response_model=ParkingTariffListResponse,
    summary="Search Parking Tariffs",
)
async def search_parking_tariffs(
    service: ParkingTariffServiceDep,
    search_term: str = Query(
        ...,
        min_length=1,
    ),
) -> ParkingTariffListResponse:
    """
    Search parking tariffs by name or code.
    """

    tariffs = await service.search(
        search_term=search_term,
    )

    return ParkingTariffListResponse(
        items=tariffs,
        total=len(tariffs),
    )


@router.get(
    "/applicable",
    response_model=ParkingTariffResponse,
    summary="Find Applicable Parking Tariff",
)
async def get_applicable_parking_tariff(
    service: ParkingTariffServiceDep,
    vehicle_type: VehicleType = Query(...),
    billing_type: BillingType = Query(...),
    effective_at: datetime = Query(...),
) -> ParkingTariffResponse:
    """
    Retrieve the applicable parking tariff.
    """

    tariff = await service.find_applicable_tariff(
        vehicle_type=vehicle_type,
        billing_type=billing_type,
        effective_at=effective_at,
    )

    if tariff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No applicable parking tariff found.",
        )

    return tariff


# ==========================================================
# Single Tariff Endpoints
# ==========================================================


@router.get(
    "/{tariff_id:int}",
    response_model=ParkingTariffResponse,
    summary="Get Parking Tariff",
)
async def get_parking_tariff(
    tariff_id: int,
    service: ParkingTariffServiceDep,
) -> ParkingTariffResponse:

    tariff = await service.get_by_id(
        tariff_id,
    )

    if tariff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking tariff not found.",
        )

    return tariff


@router.put(
    "/{tariff_id:int}",
    response_model=ParkingTariffResponse,
    summary="Update Parking Tariff",
)
async def update_parking_tariff(
    tariff_id: int,
    tariff_data: ParkingTariffUpdate,
    service: ParkingTariffServiceDep,
) -> ParkingTariffResponse:

    tariff = await service.update_tariff(
        tariff_id=tariff_id,
        data=tariff_data,
    )

    if tariff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking tariff not found.",
        )

    return tariff


@router.delete(
    "/{tariff_id:int}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Parking Tariff",
)
async def delete_parking_tariff(
    tariff_id: int,
    service: ParkingTariffServiceDep,
):

    deleted = await service.delete_tariff(
        tariff_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking tariff not found.",
        )


# ==========================================================
# Status Endpoints
# ==========================================================


@router.patch(
    "/{tariff_id:int}/activate",
    response_model=ParkingTariffResponse,
    summary="Activate Parking Tariff",
)
async def activate_parking_tariff(
    tariff_id: int,
    service: ParkingTariffServiceDep,
):

    return await service.activate_tariff(
        tariff_id,
    )


@router.patch(
    "/{tariff_id:int}/deactivate",
    response_model=ParkingTariffResponse,
    summary="Deactivate Parking Tariff",
)
async def deactivate_parking_tariff(
    tariff_id: int,
    service: ParkingTariffServiceDep,
):

    return await service.deactivate_tariff(
        tariff_id,
    )