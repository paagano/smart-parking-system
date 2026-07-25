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
from app.repositories.parking_facility_repository import (
    ParkingFacilityRepository,
)
from app.schemas.parking_facility import (
    ParkingFacilityCreate,
    ParkingFacilityListResponse,
    ParkingFacilityResponse,
    ParkingFacilityUpdate,
)
from app.services.parking_facility_service import (
    ParkingFacilityService,
)

router = APIRouter(
    prefix="/parking-facilities",
    tags=["Parking Facilities"],
)


# ==========================================================
# Dependency
# ==========================================================


def get_parking_facility_service(
    db: AsyncSession = Depends(get_db),
) -> ParkingFacilityService:
    """
    Dependency that provides a ParkingFacilityService.
    """

    repository = ParkingFacilityRepository(db)

    return ParkingFacilityService(repository)


# ==========================================================
# Create
# ==========================================================


@router.post(
    "",
    response_model=ParkingFacilityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_parking_facility(
    facility: ParkingFacilityCreate,
    _: User = Depends(require_admin),
    service: ParkingFacilityService = Depends(
        get_parking_facility_service,
    ),
):
    """
    Create a new parking facility.

    Admin only.
    """

    try:
        return await service.create_facility(facility)

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
    response_model=ParkingFacilityListResponse,
)
async def get_parking_facilities(
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    service: ParkingFacilityService = Depends(
        get_parking_facility_service,
    ),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve all parking facilities.
    """

    facilities = await service.list_facilities(
        skip=skip,
        limit=limit,
    )

    total = await service.count_facilities()

    return ParkingFacilityListResponse(
        total=total,
        items=facilities,
    )


# ==========================================================
# Search
# ==========================================================


@router.get(
    "/search",
    response_model=ParkingFacilityListResponse,
)
async def search_parking_facilities(
    q: str = Query(
        ...,
        min_length=1,
        description="Search term.",
    ),
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
    service: ParkingFacilityService = Depends(
        get_parking_facility_service,
    ),
    _: User = Depends(get_current_active_user),
):
    """
    Search parking facilities.
    """

    facilities = await service.search_facilities(
        query=q,
        skip=skip,
        limit=limit,
    )

    return ParkingFacilityListResponse(
        total=len(facilities),
        items=facilities,
    )


# ==========================================================
# Get By ID
# ==========================================================


@router.get(
    "/{facility_id}",
    response_model=ParkingFacilityResponse,
)
async def get_parking_facility(
    facility_id: int,
    service: ParkingFacilityService = Depends(
        get_parking_facility_service,
    ),
    _: User = Depends(get_current_active_user),
):
    """
    Retrieve a parking facility by ID.
    """

    try:
        return await service.get_facility(facility_id)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )


# ==========================================================
# Update
# ==========================================================


@router.put(
    "/{facility_id}",
    response_model=ParkingFacilityResponse,
)
async def update_parking_facility(
    facility_id: int,
    updates: ParkingFacilityUpdate,
    _: User = Depends(require_admin),
    service: ParkingFacilityService = Depends(
        get_parking_facility_service,
    ),
):
    """
    Update a parking facility.

    Admin only.
    """

    try:
        return await service.update_facility(
            facility_id,
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
    "/{facility_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_parking_facility(
    facility_id: int,
    _: User = Depends(require_admin),
    service: ParkingFacilityService = Depends(
        get_parking_facility_service,
    ),
):
    """
    Delete a parking facility.

    Admin only.
    """

    try:
        await service.delete_facility(facility_id)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ==========================================================
# Activate
# ==========================================================


@router.patch(
    "/{facility_id}/activate",
    response_model=ParkingFacilityResponse,
)
async def activate_parking_facility(
    facility_id: int,
    _: User = Depends(require_admin),
    service: ParkingFacilityService = Depends(
        get_parking_facility_service,
    ),
):
    """
    Activate a parking facility.

    Admin only.
    """

    try:
        return await service.activate_facility(
            facility_id,
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
    "/{facility_id}/deactivate",
    response_model=ParkingFacilityResponse,
)
async def deactivate_parking_facility(
    facility_id: int,
    _: User = Depends(require_admin),
    service: ParkingFacilityService = Depends(
        get_parking_facility_service,
    ),
):
    """
    Deactivate a parking facility.

    Admin only.
    """

    try:
        return await service.deactivate_facility(
            facility_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )