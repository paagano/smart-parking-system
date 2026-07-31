"""
Parking Session Service

Contains all business logic for Parking Sessions.

Responsibilities
----------------
- Vehicle Check-In
- Vehicle Check-Out
- Parking Session Retrieval
- Parking History
- Session Validation

Pricing calculations are delegated to the PricingService.

Persistence is delegated to the Repository layer.
"""

from __future__ import annotations

import re
from uuid import uuid4

from app.utils.datetime import utc_now

from app.exceptions.handlers import (
    BadRequestException,
    NotFoundException,
)

from app.models.enums import (
    SessionStatus,
)

from app.models.parking_session import (
    ParkingSession,
)

from app.repositories.parking_session_repository import (
    ParkingSessionRepository,
)

from app.services.parking_bay_service import (
    ParkingBayService,
)

from app.services.pricing_service import (
    PricingService,
)

from app.schemas.parking_session import (
    ParkingSessionCheckout,
    ParkingSessionCreate,
    ParkingSessionUpdate,
)


class ParkingSessionService:
    """
    Service responsible for Parking Session business logic.

    This service manages the complete lifecycle of a parking
    session.

    Responsibilities
    ----------------
    - Vehicle validation
    - Bay validation
    - Session lifecycle
    - Pricing orchestration
    - Persistence coordination

    Parking fee calculation is delegated entirely to the
    PricingService.
    """

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        repository: ParkingSessionRepository,
        parking_bay_service: ParkingBayService,
        pricing_service: PricingService,
    ) -> None:
        """
        Create a ParkingSessionService.

        Parameters
        ----------
        repository:
            Parking Session repository.

        parking_bay_service:
            Service responsible for parking bay validation.

        pricing_service:
            Service responsible for parking pricing.
        """

        self.repository = repository

        self.parking_bay_service = parking_bay_service

        self.pricing_service = pricing_service

    # ==========================================================
    # Validation Helpers
    # ==========================================================

    def _validate_registration(
        self,
        registration: str,
    ) -> str:
        """
        Validate and normalize a vehicle registration.
        """

        registration = registration.strip().upper()

        if not registration:
            raise BadRequestException(
                "Vehicle registration is required."
            )

        if len(registration) < 3:
            raise BadRequestException(
                "Vehicle registration is too short."
            )

        if len(registration) > 20:
            raise BadRequestException(
                "Vehicle registration is too long."
            )

        if not re.fullmatch(
            r"[A-Z0-9 -]+",
            registration,
        ):
            raise BadRequestException(
                "Vehicle registration contains invalid characters."
            )

        return registration

    # ==========================================================
    # Read Operations
    # ==========================================================

    async def get_by_id(
        self,
        session_id: int,
    ) -> ParkingSession:
        """
        Retrieve a parking session by its ID.
        """

        parking_session = await self.repository.get_by_id(
            session_id
        )

        if parking_session is None:
            raise NotFoundException(
                "Parking session not found."
            )

        return parking_session

    async def get_by_session_number(
        self,
        session_number: str,
    ) -> ParkingSession:
        """
        Retrieve a parking session using its session number.
        """

        parking_session = (
            await self.repository.get_by_session_number(
                session_number
            )
        )

        if parking_session is None:
            raise NotFoundException(
                "Parking session not found."
            )

        return parking_session

    async def get_active_session(
        self,
        registration: str,
    ) -> ParkingSession | None:
        """
        Retrieve the active parking session for a vehicle.
        """

        registration = self._validate_registration(
            registration
        )

        return await self.repository.get_active_by_registration(
            registration
        )

    async def get_vehicle_history(
        self,
        registration: str,
    ) -> list[ParkingSession]:
        """
        Retrieve all parking sessions for a vehicle.
        """

        registration = self._validate_registration(
            registration,
        )

        return await self.repository.get_by_registration(
            registration
        )

    async def list_active(
        self,
    ) -> list[ParkingSession]:
        """
        Return all active parking sessions.
        """

        return await self.repository.get_active_sessions()

    async def list_completed(
        self,
    ) -> list[ParkingSession]:
        """
        Return all completed parking sessions.
        """

        return await self.repository.get_completed_sessions()

    async def search_registration(
        self,
        registration: str,
    ) -> list[ParkingSession]:
        """
        Search parking sessions by vehicle registration.
        """

        registration = registration.strip().upper()

        if not registration:
            return []

        return await self.repository.search_registration(
            registration
        )

    # ==========================================================
    # Vehicle Check-In
    # ==========================================================

    async def check_in_vehicle(
        self,
        parking_session_data: ParkingSessionCreate,
    ) -> ParkingSession:
        """
        Check a vehicle into the parking facility.
        """

        registration = self._validate_registration(
            parking_session_data.vehicle_registration
        )

        await self._validate_bay(
            parking_session_data.parking_bay_id
        )

        await self._ensure_bay_available(
            parking_session_data.parking_bay_id
        )

        await self._ensure_vehicle_not_parked(
            registration
        )

        parking_session = ParkingSession(
            session_number=self._generate_session_number(),
            parking_bay_id=parking_session_data.parking_bay_id,
            vehicle_registration=registration,
            vehicle_type=parking_session_data.vehicle_type,
            status=SessionStatus.ACTIVE,
            session_source=parking_session_data.session_source,
            entry_method=parking_session_data.entry_method,
            entry_time=utc_now(),
            expected_exit_time=parking_session_data.expected_exit_time,
            notes=parking_session_data.notes,
            created_by=None,
        )

        await self.repository.save(
            parking_session
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            parking_session
        )

        return parking_session

    # ==========================================================
    # Vehicle Check-Out
    # ==========================================================

    async def check_out_vehicle(
        self,
        session_id: int,
        checkout_data: ParkingSessionCheckout,
    ) -> ParkingSession:
        """
        Check a vehicle out of the parking facility.

        Pricing calculations are delegated entirely to the
        PricingService.
        """

        parking_session = await self.get_by_id(
            session_id
        )

        if parking_session.status != SessionStatus.ACTIVE:
            raise BadRequestException(
                "Parking session is not active."
            )

        exit_time = checkout_data.exit_time or utc_now()

        #
        # Delegate pricing to the Pricing Service
        #
        pricing = await self.pricing_service.calculate_for_session(
            vehicle_type=parking_session.vehicle_type,
            billing_type=parking_session.billing_type,
            entry_time=parking_session.entry_time,
            exit_time=exit_time,
        )

        #
        # Update session
        #
        parking_session.exit_time = exit_time

        parking_session.exit_method = checkout_data.exit_method

        parking_session.status = SessionStatus.COMPLETED

        parking_session.duration_minutes = (
            pricing.duration_minutes
        )

        parking_session.billable_minutes = (
            pricing.billable_minutes
        )

        parking_session.base_amount = (
            pricing.base_amount
        )

        parking_session.discount_amount = (
            pricing.discount_amount
        )

        parking_session.tax_amount = (
            pricing.tax_amount
        )

        parking_session.total_amount = (
            pricing.total_amount
        )

        parking_session.notes = (
            checkout_data.notes
            or parking_session.notes
        )

        await self.repository.save(
            parking_session
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            parking_session
        )

        return parking_session

    # ==========================================================
    # Update
    # ==========================================================

    async def update(
        self,
        session_id: int,
        session_data: ParkingSessionUpdate,
    ) -> ParkingSession:
        """
        Update a parking session.
        """

        parking_session = await self.get_by_id(
            session_id
        )

        update_data = session_data.model_dump(
            exclude_unset=True,
        )

        if (
            "vehicle_registration"
            in update_data
        ):
            update_data[
                "vehicle_registration"
            ] = self._validate_registration(
                update_data[
                    "vehicle_registration"
                ]
            )

        for field, value in update_data.items():
            setattr(
                parking_session,
                field,
                value,
            )

        await self.repository.save(
            parking_session
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            parking_session
        )

        return parking_session

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete(
        self,
        session_id: int,
    ) -> None:
        """
        Delete a parking session.

        Active sessions cannot be deleted.
        """

        parking_session = await self.get_by_id(
            session_id
        )

        if parking_session.status == SessionStatus.ACTIVE:
            raise BadRequestException(
                "Active parking sessions cannot be deleted."
            )

        await self.repository.remove(
            parking_session
        )

        await self.repository.db.commit()

    # ==========================================================
    # Business Validation
    # ==========================================================

    async def _ensure_vehicle_not_parked(
        self,
        registration: str,
    ) -> None:
        """
        Ensure the supplied vehicle does not already have
        an active parking session.
        """

        if await self.repository.active_session_exists(
            registration
        ):
            raise BadRequestException(
                "Vehicle already has an active parking session."
            )

    async def _ensure_bay_available(
        self,
        parking_bay_id: int,
    ) -> None:
        """
        Ensure the supplied parking bay is currently
        available.
        """

        if await self.repository.active_bay_session_exists(
            parking_bay_id
        ):
            raise BadRequestException(
                "Parking bay is currently occupied."
            )

    async def _validate_bay(
        self,
        parking_bay_id: int,
    ) -> None:
        """
        Validate that the parking bay exists.
        """

        await self.parking_bay_service.get_by_id(
            parking_bay_id
        )

    # ==========================================================
    # Utilities
    # ==========================================================

    def _generate_session_number(
        self,
    ) -> str:
        """
        Generate a unique parking session number.
        """

        return (
            "PS-"
            + uuid4().hex[:10].upper()
        )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(
        self,
    ) -> str:
        """
        String representation.
        """

        return (
            f"{self.__class__.__name__}("
            f"repository={self.repository.__class__.__name__}, "
            f"pricing_service={self.pricing_service.__class__.__name__})"
        )