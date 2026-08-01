"""
Service Dependencies

Dependency Injection providers for application services.

This module composes service-layer dependencies by wiring
repositories into services.

Business logic belongs in services.
Persistence belongs in repositories.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.pricing import (
    PricingServiceDep,
)
from app.api.dependencies.repositories import (
    ParkingBayRepositoryDep,
    ParkingFacilityRepositoryDep,
    ParkingSessionRepositoryDep,
    UserRepositoryDep,
)

from app.services.auth_service import (
    AuthService,
)
from app.services.parking_facility_service import (
    ParkingFacilityService,
)
from app.services.parking_session_service import (
    ParkingSessionService,
)

# ==========================================================
# Authentication Service
# ==========================================================


def get_auth_service(
    repository: UserRepositoryDep,
) -> AuthService:
    """
    Return an AuthService instance.
    """

    return AuthService(
        repository=repository,
    )


# ==========================================================
# Parking Facility Service
# ==========================================================


def get_parking_facility_service(
    repository: ParkingFacilityRepositoryDep,
) -> ParkingFacilityService:
    """
    Return a ParkingFacilityService instance.
    """

    return ParkingFacilityService(
        repository=repository,
    )


# ==========================================================
# Parking Session Service
# ==========================================================


def get_parking_session_service(
    repository: ParkingSessionRepositoryDep,
    parking_bay_repository: ParkingBayRepositoryDep,
    pricing_service: PricingServiceDep,
) -> ParkingSessionService:
    """
    Return a ParkingSessionService instance.
    """

    return ParkingSessionService(
        repository=repository,
        parking_bay_repository=parking_bay_repository,
        pricing_service=pricing_service,
    )


# ==========================================================
# Dependency Aliases
# ==========================================================

AuthServiceDep = Annotated[
    AuthService,
    Depends(get_auth_service),
]

ParkingFacilityServiceDep = Annotated[
    ParkingFacilityService,
    Depends(get_parking_facility_service),
]

ParkingSessionServiceDep = Annotated[
    ParkingSessionService,
    Depends(get_parking_session_service),
]