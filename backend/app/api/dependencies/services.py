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

from app.api.dependencies.notifications import (
    NotificationServiceDep,
)

from app.api.dependencies.pricing import (
    PricingServiceDep,
)

from app.api.dependencies.repositories import (
    DbSession,
    ParkingBayRepositoryDep,
    ParkingFacilityRepositoryDep,
    ParkingReservationRepositoryDep,
    ParkingSessionRepositoryDep,
    PaymentRepositoryDep,
    UserRepositoryDep,
    VehicleRepositoryDep,
)

from app.api.dependencies.wallet import (
    WalletServiceDep,
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

from app.services.parking_reservation_service import (
    ParkingReservationService,
)

from app.services.payment_service import (
    PaymentService,
)

from app.api.dependencies.receipts import (
    ReceiptServiceDep,
)

from app.services.vehicle_service import (
    VehicleService,
)


# ==========================================================
# Authentication Service
# ==========================================================


def get_auth_service(
    repository: UserRepositoryDep,
    wallet_service: WalletServiceDep,
) -> AuthService:
    """
    Return an AuthService instance.
    """

    return AuthService(
        user_repository=repository,
        wallet_service=wallet_service,
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
    vehicle_repository: VehicleRepositoryDep,
    notification_service: NotificationServiceDep,
) -> ParkingSessionService:
    """
    Return a ParkingSessionService instance.

    NotificationService is injected so the Parking Session
    service can create notifications for relevant session
    lifecycle events.
    """

    return ParkingSessionService(
        repository=repository,
        parking_bay_repository=parking_bay_repository,
        pricing_service=pricing_service,
        vehicle_repository=vehicle_repository,
        notification_service=notification_service,
    )


# ==========================================================
# Parking Reservation Service
# ==========================================================


def get_parking_reservation_service(
    repository: ParkingReservationRepositoryDep,
    parking_bay_repository: ParkingBayRepositoryDep,
    parking_session_service: ParkingSessionServiceDep,
) -> ParkingReservationService:
    """
    Return a ParkingReservationService instance.
    """

    return ParkingReservationService(
        repository=repository,
        parking_bay_repository=parking_bay_repository,
        parking_session_service=parking_session_service,
    )


# ==========================================================
# Payment Service
# ==========================================================


def get_payment_service(
    db: DbSession,
    repository: PaymentRepositoryDep,
    reservation_repository: ParkingReservationRepositoryDep,
    session_repository: ParkingSessionRepositoryDep,
    wallet_service: WalletServiceDep,
    notification_service: NotificationServiceDep,
    receipt_service: ReceiptServiceDep,
) -> PaymentService:
    """
    Return a PaymentService instance.

    NotificationService is injected so the Payment Service
    can create notifications for relevant payment lifecycle
    events.
    """

    return PaymentService(
        db=db,
        repository=repository,
        reservation_repository=reservation_repository,
        session_repository=session_repository,
        wallet_service=wallet_service,
        notification_service=notification_service,
        receipt_service=receipt_service,
    )

# ==========================================================
# Receipt Service
# ==========================================================

# ReceiptServiceDep is imported from the Receipt dependency
# module so API routes can inject the fully configured
# ReceiptService directly.


# ==========================================================
# Vehicle Service
# ==========================================================


def get_vehicle_service(
    repository: VehicleRepositoryDep,
) -> VehicleService:
    """
    Return a VehicleService instance.
    """

    return VehicleService(
        repository=repository,
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

ParkingReservationServiceDep = Annotated[
    ParkingReservationService,
    Depends(get_parking_reservation_service),
]

PaymentServiceDep = Annotated[
    PaymentService,
    Depends(get_payment_service),
]

VehicleServiceDep = Annotated[
    VehicleService,
    Depends(get_vehicle_service),
]