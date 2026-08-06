"""
Parking Session Service

Business logic for Parking Sessions.

Supported Workflows
-------------------
1. Guest Walk-in
2. Registered Customer Walk-in
3. Reservation Check-in
4. Vehicle Check-out

Responsibilities
----------------
- Vehicle validation
- Parking Bay validation
- Session lifecycle
- Reservation -> Session conversion
- Pricing orchestration
- Parking bay state transitions

Persistence is delegated to the Repository layer.
Pricing calculations are delegated to PricingService.
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
    EntryMethod,
    SessionSource,
    SessionStatus,
)

from app.models.parking_reservation import ParkingReservation
from app.models.parking_session import ParkingSession

from app.repositories.parking_session_repository import (
    ParkingSessionRepository,
)

from app.repositories.parking_bay_repository import (
    ParkingBayRepository,
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
    Business logic for Parking Sessions.

    Supports:

    • Guest Walk-ins
    • Registered Customer Walk-ins
    • Reservation Check-ins

    Future support:

    • Vehicle Ownership
    • Loyalty
    • ANPR
    """

    # ==========================================================
    # Constructor
    # ==========================================================

    def __init__(
        self,
        repository: ParkingSessionRepository,
        parking_bay_repository: ParkingBayRepository,
        pricing_service: PricingService,
    ) -> None:

        self.repository = repository
        self.parking_bay_repository = parking_bay_repository
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
    

    async def _ensure_vehicle_not_parked(
        self,
        registration: str,
    ) -> None:
        """
        Ensure vehicle has no active session.
        """

        exists = await self.repository.active_session_exists(
            registration
        )

        if exists:
            raise BadRequestException(
                "Vehicle already has an active parking session."
            )

    async def _ensure_bay_available(
        self,
        parking_bay_id: int,
    ) -> None:
        """
        Ensure parking bay is available.
        """

        occupied = await self.repository.active_bay_session_exists(
            parking_bay_id
        )

        if occupied:
            raise BadRequestException(
                "Parking bay is currently occupied."
            )

    # ==========================================================
    # Read Operations
    # ==========================================================

    async def get_by_id(
        self,
        session_id: int,
    ) -> ParkingSession:

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

        registration = self._validate_registration(
            registration
        )

        return await self.repository.get_by_registration(
            registration
        )

    async def list_active(
        self,
    ) -> list[ParkingSession]:

        return await self.repository.get_active_sessions()

    async def list_completed(
        self,
    ) -> list[ParkingSession]:

        return await self.repository.get_completed_sessions()

    async def search_registration(
        self,
        registration: str,
    ) -> list[ParkingSession]:

        registration = registration.strip().upper()

        if not registration:
            return []

        return await self.repository.search_registration(
            registration
        )

    # ==========================================================
    # Walk-in Check-In
    # ==========================================================

    async def check_in_vehicle(
        self,
        parking_session_data: ParkingSessionCreate,
    ) -> ParkingSession:
        """
        Start a new parking session for a walk-in customer.

        Supports both:
        - Guest customers
        - Registered customers
        """

        registration = self._validate_registration(
            parking_session_data.vehicle_registration,
        )

        await self._validate_bay(
            parking_session_data.parking_bay_id,
        )

        await self._ensure_bay_available(
            parking_session_data.parking_bay_id,
        )

        await self._ensure_vehicle_not_parked(
            registration,
        )

        parking_session = ParkingSession(
            session_number=self._generate_session_number(),

            parking_bay_id=parking_session_data.parking_bay_id,

            customer_id=parking_session_data.customer_id,

            reservation_id=None,

            vehicle_registration=registration,

            vehicle_type=parking_session_data.vehicle_type,

            status=SessionStatus.ACTIVE,

            session_source=parking_session_data.session_source,

            entry_method=parking_session_data.entry_method,

            entry_time=utc_now(),

            expected_exit_time=parking_session_data.expected_exit_time,

            notes=parking_session_data.notes,
        )

        await self.repository.save(
            parking_session,
        )

        #
        # Bay becomes OCCUPIED
        #
        parking_bay = await self.parking_bay_repository.get_by_id(
            parking_session.parking_bay_id,
        )

        if parking_bay is None:
            raise ValueError(
                "Parking bay not found."
            )

        await self.parking_bay_repository.mark_occupied(
            parking_bay,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            parking_session,
        )

        return parking_session

    # ==========================================================
    # Reservation Check-In
    # ==========================================================

    async def create_from_reservation(
        self,
        reservation: ParkingReservation,
    ) -> ParkingSession:
        """
        Convert a reservation into an active parking session.

        Workflow

        Reservation
                ↓
        Driver Arrives
                ↓
        Reservation Validated
                ↓
        Session Created
                ↓
        Bay becomes OCCUPIED
        """

        await self._ensure_vehicle_not_parked(
            reservation.vehicle_registration,
        )

        parking_session = ParkingSession(
            session_number=self._generate_session_number(),

            parking_bay_id=reservation.parking_bay_id,

            customer_id=reservation.customer_id,

            reservation_id=reservation.id,

            vehicle_registration=reservation.vehicle_registration,

            vehicle_type=reservation.vehicle_type,

            status=SessionStatus.ACTIVE,

            session_source=SessionSource.RESERVATION,

            # Reservation arrivals use QR Code by default.
            # Future versions may support RFID / ANPR.
            entry_method=EntryMethod.QR_CODE,

            entry_time=utc_now(),

            expected_exit_time=reservation.reserved_until,

            notes=reservation.notes,
        )

        await self.repository.save(
            parking_session,
        )

        # Reservation becomes occupied.
 
        # await self.parking_bay_repository.mark_occupied(
        #     reservation.parking_bay_id,
        # )

        # Reservation is no longer active.
        await self.repository.db.commit() 

        await self.repository.db.refresh(
            parking_session,
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
        Complete an active parking session.

        Workflow

        Active Session
                ↓
        Calculate Parking Fee
                ↓
        Complete Session
                ↓
        Release Parking Bay
        """

        parking_session = await self.get_by_id(
            session_id,
        )

        if parking_session.status != SessionStatus.ACTIVE:
            raise BadRequestException(
                "Parking session is not active."
            )

        #
        # Determine exit time
        #
        exit_time = utc_now()

        #
        # Delegate pricing to Pricing Service.
        #
        # PricingService should determine the applicable tariff
        # using the parking bay and vehicle type.
        #
        pricing = await self.pricing_service.calculate_for_session(
            parking_bay_id=parking_session.parking_bay_id,
            vehicle_type=parking_session.vehicle_type,
            entry_time=parking_session.entry_time,
            exit_time=exit_time,
        )

        #
        # Update Session
        #
        parking_session.exit_time = exit_time

        parking_session.exit_method = (
            checkout_data.exit_method
        )

        parking_session.status = (
            SessionStatus.COMPLETED
        )

        parking_session.duration_minutes = (
            pricing.duration_minutes
        )

        parking_session.calculated_amount = (
            pricing.total_amount
        )

        #
        # Payment is handled separately.
        #
        # At checkout we simply calculate the amount due.
        #
        parking_session.notes = (
            checkout_data.notes
            or parking_session.notes
        )

        await self.repository.save(
            parking_session,
        )

        #
        # Bay becomes AVAILABLE again.
        #
        await self.parking_bay_repository.release_bay(
            parking_session.parking_bay_id,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            parking_session,
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

        Only operational fields are editable.
        Session lifecycle fields are managed by
        dedicated business workflows.
        """

        parking_session = await self.get_by_id(
            session_id,
        )

        update_data = session_data.model_dump(
            exclude_unset=True,
        )

        #
        # Validate registration
        #
        if "vehicle_registration" in update_data:

            update_data["vehicle_registration"] = (
                self._validate_registration(
                    update_data["vehicle_registration"],
                )
            )

        #
        # Validate parking bay
        #
        if "parking_bay_id" in update_data:

            await self._validate_bay(
                update_data["parking_bay_id"],
            )

        #
        # Apply updates
        #
        for field, value in update_data.items():

            setattr(
                parking_session,
                field,
                value,
            )

        await self.repository.save(
            parking_session,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            parking_session,
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
            session_id,
        )

        if parking_session.status == SessionStatus.ACTIVE:

            raise BadRequestException(
                "Active parking sessions cannot be deleted."
            )

        #
        # Defensive release.
        #
        # If the bay somehow wasn't released,
        # ensure it is available again.
        #
        await self.parking_bay_repository.release_bay(
            parking_session.parking_bay_id,
        )

        await self.repository.remove(
            parking_session,
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
        Ensure the supplied vehicle does not already
        have an active parking session.
        """

        if await self.repository.active_session_exists(
            registration,
        ):

            raise BadRequestException(
                "Vehicle already has an active parking session."
            )

    async def _ensure_bay_available(
        self,
        parking_bay_id: int,
    ) -> None:
        """
        Ensure the supplied parking bay is available.
        """

        if await self.repository.active_bay_session_exists(
            parking_bay_id,
        ):

            raise BadRequestException(
                "Parking bay is currently occupied."
            )

    async def _validate_bay(
        self,
        parking_bay_id: int,
    ) -> None:
        """
        Validate that the parking bay may be used.

        Validation Rules
        ----------------
        - Parking bay must exist.
        - Parking bay must be active.
        - Parking bay must be reservable.
        """

        parking_bay = (
            await self.parking_bay_repository.get_by_id(
                parking_bay_id,
            )
        )

        if parking_bay is None:
            raise NotFoundException(
                "Parking bay not found."
            )

        if not parking_bay.is_active:
            raise BadRequestException(
                "Parking bay is inactive."
            )

        if not parking_bay.is_reservable:
            raise BadRequestException(
                "Parking bay is currently not reservable."
            )

    async def has_active_session(
        self,
        parking_bay_id: int,
    ) -> bool:
        """
        Determine whether a parking bay currently has
        an active parking session.
        """

        return await self.repository.has_active_session(
            parking_bay_id,
        )

    # ==========================================================
    # Utilities
    # ==========================================================

    def _generate_session_number(
        self,
    ) -> str:
        """
        Generate a unique parking session number.

        Example

            PS-4F7A8C91DE
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

        return (
            f"{self.__class__.__name__}("
            f"repository={self.repository.__class__.__name__}, "
            f"pricing_service={self.pricing_service.__class__.__name__})"
        )