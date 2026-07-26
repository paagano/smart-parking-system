from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Response,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies.auth import (
    get_current_active_user,
    require_admin,
)
from app.database.session import get_db
from app.models.user import User
from app.repositories.parking_zone_repository import (
    ParkingZoneRepository,
)
from app.schemas.parking_zone import (
    ParkingZoneCreate,
    ParkingZoneListResponse,
    ParkingZoneResponse,
    ParkingZoneUpdate,
)
from app.services.parking_zone_service import (
    ParkingZoneService,
)

router = APIRouter(
    prefix="/parking-zones",
    tags=["Parking Zones"],
)


# ==========================================================
# Dependency
# ==========================================================


def get_parking_zone_service(
    db: AsyncSession = Depends(get_db),
) -> ParkingZoneService:
    """
    Dependency that provides a ParkingZoneService.
    """

    repository = ParkingZoneRepository(db)

    return ParkingZoneService(repository)


# ==========================================================
# Create
# ==========================================================


@router.post(
    "",
    response_model=ParkingZoneResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_parking_zone(
    zone: ParkingZoneCreate,
    _: User = Depends(require_admin),
    service: ParkingZoneService = Depends(
        get_parking_zone_service,
    ),
):
    """
    Create a new parking zone.

    Admin only.
    """

    try:
        return await service.create_zone(zone)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ==========================================================
# Get All
# ==========================================================


@router.get(
    "",
    response_model=ParkingZoneListResponse,
)
async def get_parking_zones(
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    service: ParkingZoneService = Depends(
        get_parking_zone_service,
    ),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve all parking zones.
    """

    zones = await service.list_zones(
        skip=skip,
        limit=limit,
    )

    total = await service.count_zones()

    return ParkingZoneListResponse(
        total=total,
        items=zones,
    )


# ==========================================================
# Get By ID
# ==========================================================


@router.get(
    "/{zone_id}",
    response_model=ParkingZoneResponse,
)
async def get_parking_zone(
    zone_id: int,
    service: ParkingZoneService = Depends(
        get_parking_zone_service,
    ),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve a parking zone by ID.
    """

    try:
        return await service.get_zone(
            zone_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


# ==========================================================
# Get By Facility
# ==========================================================


@router.get(
    "/facility/{facility_id}",
    response_model=ParkingZoneListResponse,
)
async def get_facility_zones(
    facility_id: int,
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    service: ParkingZoneService = Depends(
        get_parking_zone_service,
    ),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve all parking zones belonging to a facility.
    """

    zones = await service.list_facility_zones(
        facility_id,
        skip=skip,
        limit=limit,
    )

    total = await service.count_facility_zones(
        facility_id,
    )

    return ParkingZoneListResponse(
        total=total,
        items=zones,
    )
# ==========================================================
# Get Root Zones
# ==========================================================


@router.get(
    "/facility/{facility_id}/roots",
    response_model=ParkingZoneListResponse,
)
async def get_root_zones(
    facility_id: int,
    service: ParkingZoneService = Depends(
        get_parking_zone_service,
    ),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve all root parking zones within a facility.
    """

    zones = await service.get_root_zones(
        facility_id,
    )

    return ParkingZoneListResponse(
        total=len(zones),
        items=zones,
    )


# ==========================================================
# Get Children
# ==========================================================


@router.get(
    "/{zone_id}/children",
    response_model=ParkingZoneListResponse,
)
async def get_child_zones(
    zone_id: int,
    service: ParkingZoneService = Depends(
        get_parking_zone_service,
    ),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve all direct child zones.
    """

    zones = await service.get_children(
        zone_id,
    )

    return ParkingZoneListResponse(
        total=len(zones),
        items=zones,
    )


# ==========================================================
# Update
# ==========================================================


@router.put(
    "/{zone_id}",
    response_model=ParkingZoneResponse,
)
async def update_parking_zone(
    zone_id: int,
    updates: ParkingZoneUpdate,
    _: User = Depends(require_admin),
    service: ParkingZoneService = Depends(
        get_parking_zone_service,
    ),
):
    """
    Update a parking zone.

    Admin only.
    """

    try:
        return await service.update_zone(
            zone_id,
            updates,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


# ==========================================================
# Delete
# ==========================================================


@router.delete(
    "/{zone_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_parking_zone(
    zone_id: int,
    _: User = Depends(require_admin),
    service: ParkingZoneService = Depends(
        get_parking_zone_service,
    ),
):
    """
    Delete a parking zone.

    Admin only.
    """

    try:
        await service.delete_zone(
            zone_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )

    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
    )
# ==========================================================
# Activate
# ==========================================================


@router.patch(
    "/{zone_id}/activate",
    response_model=ParkingZoneResponse,
)
async def activate_parking_zone(
    zone_id: int,
    _: User = Depends(require_admin),
    service: ParkingZoneService = Depends(
        get_parking_zone_service,
    ),
):
    """
    Activate a parking zone.

    Admin only.
    """

    try:
        return await service.activate_zone(
            zone_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


# ==========================================================
# Deactivate
# ==========================================================


@router.patch(
    "/{zone_id}/deactivate",
    response_model=ParkingZoneResponse,
)
async def deactivate_parking_zone(
    zone_id: int,
    _: User = Depends(require_admin),
    service: ParkingZoneService = Depends(
        get_parking_zone_service,
    ),
):
    """
    Deactivate a parking zone.

    Admin only.
    """

    try:
        return await service.deactivate_zone(
            zone_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )