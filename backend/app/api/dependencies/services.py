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
    RevokedTokenRepositoryDep,
    UserRepositoryDep,
    VehicleRepositoryDep,
)

from app.api.dependencies.wallet import (
    WalletServiceDep,
)

from app.api.dependencies.storage import (
    ProfilePictureStorageServiceDep,
)

from app.services.ai.chat_service import (
    SmartParkChatService,
)

from app.services.ai.smartpark_ai_tools import (
    SmartParkAITools,
)
from app.ml.production.observation_repository import (
    OccupancyObservationRepository,
)
from app.ml.production.service import (
    ProductionForecastService,
)

from app.services.auth_service import (
    AuthService,
)

from app.services.email_service import (
    EmailService,
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

from app.api.dependencies.loyalty import (
    LoyaltyServiceDep,
)

from app.api.dependencies.loyalty_reward import (
    LoyaltyRewardServiceDep,
)

from app.services.vehicle_service import (
    VehicleService,
)


# ==========================================================
# Email Service
# ==========================================================


def get_email_service() -> EmailService:
    """
    Return an EmailService instance.
    """

    return EmailService()


# ==========================================================
# SmartPark AI Tools
# ==========================================================


def get_smartpark_ai_tools(
    db: DbSession,
    reservation_repository: ParkingReservationRepositoryDep,
    parking_bay_repository: ParkingBayRepositoryDep,
    parking_session_service: ParkingSessionServiceDep,
    pricing_service: PricingServiceDep,
    vehicle_repository: VehicleRepositoryDep,
    vehicle_service: VehicleServiceDep,
    notification_service: NotificationServiceDep,
    receipt_service: ReceiptServiceDep,
    loyalty_service: LoyaltyServiceDep,
    loyalty_reward_service: LoyaltyRewardServiceDep,
) -> SmartParkAITools:
    """
    Return a SmartParkAITools instance using the current
    asynchronous database session and fully configured reservation
    dependencies.
    """

    reservation_service = ParkingReservationService(
        repository=reservation_repository,
        parking_bay_repository=parking_bay_repository,
        pricing_service=pricing_service,
        parking_session_service=parking_session_service,
        vehicle_repository=vehicle_repository,
        notification_service=notification_service,
    )

    # ----------------------------------------------------------
    # Production occupancy forecasting
    # ----------------------------------------------------------
    #
    # Reuse the existing production forecasting service contract.
    # The observation repository is adapted to the ML service's
    # observation-provider interface exactly as the existing
    # forecasting API does.
    # ----------------------------------------------------------

    observation_repository = OccupancyObservationRepository(
        db,
    )

    async def observation_provider(
        facility_id: int,
        prediction_timestamp,
        lookback_minutes: int,
    ):
        return await observation_repository.get_observations_for_forecast(
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
            lookback_minutes=lookback_minutes,
        )

    forecast_service = ProductionForecastService(
        observation_provider=observation_provider,
    )

    return SmartParkAITools(
        db=db,
        reservation_service=reservation_service,
        vehicle_repository=vehicle_repository,
        vehicle_service=vehicle_service,
        forecast_service=forecast_service,
        receipt_service=receipt_service,
        loyalty_service=loyalty_service,
        loyalty_reward_service=loyalty_reward_service,
    )

SmartParkAIToolsDep = Annotated[
    SmartParkAITools,
    Depends(get_smartpark_ai_tools),
]


# ==========================================================
# SmartPark AI Chat Service
# ==========================================================


def get_smartpark_chat_service(
    tools: SmartParkAIToolsDep,
) -> SmartParkChatService:
    """
    Return a SmartParkChatService instance with the
    SmartPark AI database tools injected.
    """

    return SmartParkChatService(
        tools=tools,
    )


# ==========================================================
# Authentication Service
# ==========================================================


def get_auth_service(
    repository: UserRepositoryDep,
    wallet_service: WalletServiceDep,
    parking_facility_repository: ParkingFacilityRepositoryDep,
    revoked_token_repository: RevokedTokenRepositoryDep,
    profile_picture_storage_service: ProfilePictureStorageServiceDep,
    email_service: Annotated[
        EmailService,
        Depends(get_email_service),
    ],
) -> AuthService:
    """
    Return an AuthService instance.
    """

    return AuthService(
        user_repository=repository,
        wallet_service=wallet_service,
        parking_facility_repository=parking_facility_repository,
        revoked_token_repository=revoked_token_repository,
        storage_service=profile_picture_storage_service,
        email_service=email_service,
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
    pricing_service: PricingServiceDep,
    parking_session_service: ParkingSessionServiceDep,
    vehicle_repository: VehicleRepositoryDep,
    notification_service: NotificationServiceDep,
) -> ParkingReservationService:
    """
    Return a fully configured ParkingReservationService instance.
    """

    return ParkingReservationService(
        repository=repository,
        parking_bay_repository=parking_bay_repository,
        pricing_service=pricing_service,
        parking_session_service=parking_session_service,
        vehicle_repository=vehicle_repository,
        notification_service=notification_service,
    )

# ==========================================================
# Payment Service
# ==========================================================


def get_payment_service(
    db: DbSession,
    repository: PaymentRepositoryDep,
    reservation_repository: ParkingReservationRepositoryDep,
    session_repository: ParkingSessionRepositoryDep,
    pricing_service: PricingServiceDep,
    wallet_service: WalletServiceDep,
    notification_service: NotificationServiceDep,
    receipt_service: ReceiptServiceDep,
) -> PaymentService:
    """
    Return a PaymentService instance.

    NotificationService is injected so the Payment Service
    can create notifications for relevant payment lifecycle
    events.

    PricingService is injected so the Payment Service can
    calculate/validate the current parking amount before
    processing a session payment.
    """

    return PaymentService(
        db=db,
        repository=repository,
        reservation_repository=reservation_repository,
        session_repository=session_repository,
        pricing_service=pricing_service,
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


SmartParkAIToolsDep = Annotated[
    SmartParkAITools,
    Depends(get_smartpark_ai_tools),
]


SmartParkChatServiceDep = Annotated[
    SmartParkChatService,
    Depends(get_smartpark_chat_service),
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