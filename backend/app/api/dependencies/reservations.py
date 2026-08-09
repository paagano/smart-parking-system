"""
Reservation Dependencies

Dependency Injection providers for the Reservation module.

This module composes the Reservation subsystem by wiring together:

- ParkingReservationService
- ParkingReservationRepository
- ParkingBayRepository
- ParkingSessionService

Business logic belongs in the services.
Persistence belongs in the repositories.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.repositories import (
    ParkingBayRepositoryDep,
    ParkingReservationRepositoryDep,
    VehicleRepositoryDep,
)

from app.api.dependencies.services import (
    ParkingSessionServiceDep,
)

from app.services.parking_reservation_service import (
    ParkingReservationService,
)

from app.api.dependencies.pricing import (
    PricingServiceDep,
)

# ==========================================================
# Parking Reservation Service
# ==========================================================


def get_parking_reservation_service(
    repository: ParkingReservationRepositoryDep,
    parking_bay_repository: ParkingBayRepositoryDep,
    pricing_service: PricingServiceDep,
    parking_session_service: ParkingSessionServiceDep,
    vehicle_repository: VehicleRepositoryDep,
) -> ParkingReservationService:
    """
    Return a ParkingReservationService instance.
    """

    return ParkingReservationService(
        repository=repository,
        parking_bay_repository=parking_bay_repository,
        pricing_service=pricing_service,
        parking_session_service=parking_session_service,
        vehicle_repository=vehicle_repository,
    )


# ==========================================================
# Dependency Alias
# ==========================================================

ParkingReservationServiceDep = Annotated[
    ParkingReservationService,
    Depends(get_parking_reservation_service),
]