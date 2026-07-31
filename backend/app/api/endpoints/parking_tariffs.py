"""
Parking Tariff Endpoints.

REST API endpoints for Parking Tariff management.

Responsibilities
----------------
- CRUD operations
- Tariff activation/deactivation
- Tariff search
- Applicable tariff lookup

Business logic belongs in ParkingTariffService.
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
# Create Tariff
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
    Create a new parking tariff.
    """

    tariff = await service.create_tariff(
        tariff_data,
    )

    return tariff


# ==========================================================
# Get All Tariffs
# ==========================================================


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
# Get Tariff by ID
# ==========================================================


@router.get(
    "/{tariff_id}",
    response_model=ParkingTariffResponse,
    summary="Get Parking Tariff",
)
async def get_parking_tariff(
    tariff_id: int,
    service: ParkingTariffServiceDep,
) -> ParkingTariffResponse:
    """
    Retrieve a parking tariff by its ID.
    """

    tariff = await service.get_by_id(
        tariff_id,
    )

    if tariff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking tariff not found.",
        )

    return tariff


# ==========================================================
# Update Tariff
# ==========================================================


@router.put(
    "/{tariff_id}",
    response_model=ParkingTariffResponse,
    summary="Update Parking Tariff",
)
async def update_parking_tariff(
    tariff_id: int,
    tariff_data: ParkingTariffUpdate,
    service: ParkingTariffServiceDep,
) -> ParkingTariffResponse:
    """
    Update an existing parking tariff.
    """

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


# ==========================================================
# Delete Tariff
# ==========================================================


@router.delete(
    "/{tariff_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Parking Tariff",
)
async def delete_parking_tariff(
    tariff_id: int,
    service: ParkingTariffServiceDep,
) -> None:
    """
    Delete a parking tariff.
    """

    deleted = await service.delete_tariff(
        tariff_id,
    )

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking tariff not found.",
        )

    return None

# ==========================================================
# Activate Tariff
# ==========================================================


@router.patch(
    "/{tariff_id}/activate",
    response_model=ParkingTariffResponse,
    summary="Activate Parking Tariff",
)
async def activate_parking_tariff(
    tariff_id: int,
    service: ParkingTariffServiceDep,
) -> ParkingTariffResponse:
    """
    Activate a parking tariff.
    """

    tariff = await service.activate_tariff(
        tariff_id,
    )

    if tariff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking tariff not found.",
        )

    return tariff


# ==========================================================
# Deactivate Tariff
# ==========================================================


@router.patch(
    "/{tariff_id}/deactivate",
    response_model=ParkingTariffResponse,
    summary="Deactivate Parking Tariff",
)
async def deactivate_parking_tariff(
    tariff_id: int,
    service: ParkingTariffServiceDep,
) -> ParkingTariffResponse:
    """
    Deactivate a parking tariff.
    """

    tariff = await service.deactivate_tariff(
        tariff_id,
    )

    if tariff is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parking tariff not found.",
        )

    return tariff


# ==========================================================
# Search Tariffs
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
        description="Search by tariff code or name.",
    ),
) -> ParkingTariffListResponse:
    """
    Search parking tariffs by tariff code or name.
    """

    tariffs = await service.search(
        search_term=search_term,
    )

    return ParkingTariffListResponse(
        items=tariffs,
        total=len(tariffs),
    )

# ==========================================================
# Applicable Tariff Lookup
# ==========================================================


@router.get(
    "/applicable",
    response_model=ParkingTariffResponse,
    summary="Find Applicable Parking Tariff",
)
async def get_applicable_parking_tariff(
    service: ParkingTariffServiceDep,
    vehicle_type: VehicleType = Query(
        ...,
        description="Vehicle type.",
    ),
    billing_type: BillingType = Query(
        ...,
        description="Billing type.",
    ),
    effective_at: datetime = Query(
        ...,
        description="Date and time for which the tariff should be applicable.",
    ),
) -> ParkingTariffResponse:
    """
    Retrieve the highest-priority active parking tariff
    applicable for the supplied criteria.
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