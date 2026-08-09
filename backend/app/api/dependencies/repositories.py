"""
Repository Dependencies

Provides Dependency Injection (DI) factories for all repository
classes used throughout the application.

Repositories are responsible only for data persistence.

Business rules belong in the Service layer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dependencies import get_db

from app.repositories.user_repository import (
    UserRepository,
)

from app.repositories.parking_facility_repository import (
    ParkingFacilityRepository,
)

from app.repositories.parking_zone_repository import (
    ParkingZoneRepository,
)

from app.repositories.parking_bay_repository import (
    ParkingBayRepository,
)

from app.repositories.parking_session_repository import (
    ParkingSessionRepository,
)

from app.repositories.parking_reservation_repository import (
    ParkingReservationRepository,
)

from app.repositories.parking_tariff_repository import (
    ParkingTariffRepository,
)

from app.repositories.payment_repository import (
    PaymentRepository,
)

from app.repositories.vehicle_repository import (
    VehicleRepository,
)

from app.repositories.notification_repository import (
    NotificationRepository,
)


# ==========================================================
# Database Dependency
# ==========================================================

DbSession = Annotated[
    AsyncSession,
    Depends(get_db),
]


# ==========================================================
# User Repository
# ==========================================================

def get_user_repository(
    db: DbSession,
) -> UserRepository:
    """
    Return a UserRepository instance.
    """

    return UserRepository(db)


# ==========================================================
# Parking Facility Repository
# ==========================================================

def get_parking_facility_repository(
    db: DbSession,
) -> ParkingFacilityRepository:
    """
    Return a ParkingFacilityRepository instance.
    """

    return ParkingFacilityRepository(db)


# ==========================================================
# Parking Zone Repository
# ==========================================================

def get_parking_zone_repository(
    db: DbSession,
) -> ParkingZoneRepository:
    """
    Return a ParkingZoneRepository instance.
    """

    return ParkingZoneRepository(db)


# ==========================================================
# Parking Bay Repository
# ==========================================================

def get_parking_bay_repository(
    db: DbSession,
) -> ParkingBayRepository:
    """
    Return a ParkingBayRepository instance.
    """

    return ParkingBayRepository(db)


# ==========================================================
# Parking Session Repository
# ==========================================================

def get_parking_session_repository(
    db: DbSession,
) -> ParkingSessionRepository:
    """
    Return a ParkingSessionRepository instance.
    """

    return ParkingSessionRepository(db)


# ==========================================================
# Parking Reservation Repository
# ==========================================================

def get_parking_reservation_repository(
    db: DbSession,
) -> ParkingReservationRepository:
    """
    Return a ParkingReservationRepository.
    """

    return ParkingReservationRepository(
        db=db,
    )


# ==========================================================
# Parking Tariff Repository
# ==========================================================

def get_parking_tariff_repository(
    db: DbSession,
) -> ParkingTariffRepository:
    """
    Return a ParkingTariffRepository instance.
    """

    return ParkingTariffRepository(db)


# ==========================================================
# Payment Repository
# ==========================================================

def get_payment_repository(
    db: DbSession,
) -> PaymentRepository:
    """
    Return a PaymentRepository instance.
    """

    return PaymentRepository(
        db=db,
    )


# ==========================================================
# Vehicle Repository
# ==========================================================

def get_vehicle_repository(
    db: DbSession,
) -> VehicleRepository:
    """
    Return a VehicleRepository instance.
    """

    return VehicleRepository(
        db=db,
    )


# ==========================================================
# Notification Repository
# ==========================================================

def get_notification_repository(
    db: DbSession,
) -> NotificationRepository:
    """
    Return a NotificationRepository instance.
    """

    return NotificationRepository(
        db=db,
    )


# ==========================================================
# Dependency Aliases
# ==========================================================

UserRepositoryDep = Annotated[
    UserRepository,
    Depends(get_user_repository),
]


ParkingFacilityRepositoryDep = Annotated[
    ParkingFacilityRepository,
    Depends(get_parking_facility_repository),
]


ParkingZoneRepositoryDep = Annotated[
    ParkingZoneRepository,
    Depends(get_parking_zone_repository),
]


ParkingBayRepositoryDep = Annotated[
    ParkingBayRepository,
    Depends(get_parking_bay_repository),
]


ParkingSessionRepositoryDep = Annotated[
    ParkingSessionRepository,
    Depends(get_parking_session_repository),
]


ParkingReservationRepositoryDep = Annotated[
    ParkingReservationRepository,
    Depends(get_parking_reservation_repository),
]


ParkingTariffRepositoryDep = Annotated[
    ParkingTariffRepository,
    Depends(get_parking_tariff_repository),
]


PaymentRepositoryDep = Annotated[
    PaymentRepository,
    Depends(get_payment_repository),
]


VehicleRepositoryDep = Annotated[
    VehicleRepository,
    Depends(get_vehicle_repository),
]


NotificationRepositoryDep = Annotated[
    NotificationRepository,
    Depends(get_notification_repository),
]