from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db

# Repositories
from app.repositories.user_repository import UserRepository
from app.repositories.parking_facility_repository import (
    ParkingFacilityRepository,
)

# Services
from app.services.auth_service import AuthService
from app.services.parking_facility_service import (
    ParkingFacilityService,
)


# ==========================================================
# Authentication Service
# ==========================================================

def get_auth_service(
    db: AsyncSession = Depends(get_db),
) -> AuthService:
    """
    Dependency that provides an AuthService instance.
    """

    repository = UserRepository(db)

    return AuthService(repository)


# ==========================================================
# Parking Facility Service
# ==========================================================

def get_parking_facility_service(
    db: AsyncSession = Depends(get_db),
) -> ParkingFacilityService:
    """
    Dependency that provides a ParkingFacilityService instance.
    """

    repository = ParkingFacilityRepository(db)

    return ParkingFacilityService(repository)