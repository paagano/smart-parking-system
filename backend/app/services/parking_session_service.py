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
- Session notifications

Persistence is delegated to the Repository layer.
Pricing calculations are delegated to PricingService.
Notification creation is delegated to NotificationService.
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
    NotificationChannel,
    NotificationPriority,
    NotificationType,
    SessionSource,
    SessionStatus,
    VehicleType,
)

from app.models.parking_reservation import ParkingReservation
from app.models.parking_session import ParkingSession

from app.repositories.parking_session_repository import (
    ParkingSessionRepository,
)

from app.repositories.vehicle_repository import (
    VehicleRepository,
)

from app.repositories.parking_bay_repository import (
    ParkingBayRepository,
)

from app.services.pricing_service import (
    PricingService,
)

from app.services.notification_service import (
    NotificationService,
)

from app.schemas.notification import (
    NotificationCreate,
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
    • Session Notifications

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
        vehicle_repository: VehicleRepository,
        notification_service: NotificationService,
    ):
        self.repository = repository
        self.parking_bay_repository = parking_bay_repository
        self.pricing_service = pricing_service
        self.vehicle_repository = vehicle_repository
        self.notification_service = notification_service

    # ==========================================================
    # Notification Helper
    # ==========================================================

    async def _create_session_notification(
        self,
        *,
        parking_session: ParkingSession,
        notification_type: NotificationType,
        title: str,
        message: str,
    ) -> None:
        """
        Create an in-app notification for a parking session event.

        The session operation is committed before this method is
        called.

        Notification failures are intentionally isolated from the
        core parking session operation so that an already successful
        parking transaction is not converted into a failed operation
        because of a notification problem.
        """

        try:
            await self.notification_service.create_notification(
                data=NotificationCreate(
                    user_id=parking_session.customer_id,
                    type=notification_type,
                    channel=NotificationChannel.IN_APP,
                    priority=NotificationPriority.NORMAL,
                    title=title,
                    message=message,
                    related_entity_type="PARKING_SESSION",
                    related_entity_id=parking_session.id,
                ),
            )

        except Exception:
            # Notification creation must not break an already
            # successfully committed parking session operation.
            #
            # Proper logging/observability can be introduced later
            # as part of the Notification Delivery hardening phase.
            pass

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

    async def _resolve_vehicle(
        self,
        *,
        vehicle_id: int | None,
        vehicle_registration: str | None,
        vehicle_type: VehicleType | None,
    ) -> dict:
        """
        Resolve vehicle information.

        Registered vehicle flow:
            vehicle_id is supplied.
            Registration and vehicle type are obtained
            from the registered Vehicle record.

        Borrowed/unregistered vehicle flow:
            vehicle_id is None.
            Registration and vehicle type must be supplied
            directly by the caller.

        Vehicle ownership is intentionally NOT validated here.
        A driver may use another customer's registered vehicle.
        """

        # ======================================================
        # Registered Vehicle
        # ======================================================

        if vehicle_id is not None:

            vehicle = await self.vehicle_repository.get_by_id(
                vehicle_id
            )

            if vehicle is None:
                raise NotFoundException(
                    "Registered vehicle not found."
                )

            if not vehicle.is_active:
                raise BadRequestException(
                    "Registered vehicle is inactive."
                )

            registration = self._validate_registration(
                vehicle.registration_number
            )

            return {
                "vehicle_id": vehicle.id,
                "registration": registration,
                "vehicle_type": vehicle.vehicle_type,
            }

        # ======================================================
        # Borrowed / Unregistered Vehicle
        # ======================================================

        if not vehicle_registration:
            raise BadRequestException(
                "Vehicle registration is required when vehicle_id is not provided."
            )

        if vehicle_type is None:
            raise BadRequestException(
                "Vehicle type is required when vehicle_id is not provided."
            )

        registration = self._validate_registration(
            vehicle_registration
        )

        return {
            "vehicle_id": None,
            "registration": registration,
            "vehicle_type": vehicle_type,
        }

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
        Retrieve a parking session by its session number.
        """

        parking_session = await self.repository.get_by_session_number(
            session_number
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
            registration
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
    # Walk-in Check-In
    # ==========================================================

    async def check_in_vehicle(
        self,
        parking_session_data: ParkingSessionCreate,
    ) -> ParkingSession:
        """
        Start a new parking session for a walk-in customer.

        Supports:

        1. Guest/unregistered vehicle
        - vehicle_id = None
        - vehicle_registration supplied
        - vehicle_type supplied

        2. Registered vehicle
        - vehicle_id supplied
        - registration and vehicle type resolved
            from the Vehicle record

        The driver/customer does not have to own the vehicle.
        """

        # ======================================================
        # Resolve Vehicle
        # ======================================================

        vehicle = await self._resolve_vehicle(
            vehicle_id=parking_session_data.vehicle_id,
            vehicle_registration=parking_session_data.vehicle_registration,
            vehicle_type=parking_session_data.vehicle_type,
        )

        vehicle_id = vehicle["vehicle_id"]
        registration = vehicle["registration"]
        vehicle_type = vehicle["vehicle_type"]

        # ======================================================
        # Validate Parking Bay
        # ======================================================

        await self._validate_bay(
            parking_session_data.parking_bay_id,
        )

        await self._ensure_bay_available(
            parking_session_data.parking_bay_id,
        )

        # ======================================================
        # Ensure Vehicle Is Not Already Parked
        # ======================================================

        await self._ensure_vehicle_not_parked(
            registration,
        )

        # ======================================================
        # Create Parking Session
        # ======================================================

        parking_session = ParkingSession(
            session_number=self._generate_session_number(),
            parking_bay_id=parking_session_data.parking_bay_id,

            # Driver/customer associated with THIS session.
            # This is deliberately independent of vehicle ownership.
            customer_id=parking_session_data.customer_id,

            reservation_id=None,

            # Registered vehicle -> Vehicle.id
            # Borrowed/unregistered -> None
            vehicle_id=vehicle_id,

            vehicle_registration=registration,
            vehicle_type=vehicle_type,
            billing_type=parking_session_data.billing_type,

            status=SessionStatus.ACTIVE,

            session_source=parking_session_data.session_source,
            entry_method=parking_session_data.entry_method,

            entry_time=utc_now(),

            expected_exit_time=(
                parking_session_data.expected_exit_time
            ),

            notes=parking_session_data.notes,
        )

        # ======================================================
        # Persist Session
        # ======================================================

        await self.repository.save(
            parking_session,
        )

        # ======================================================
        # Bay Becomes OCCUPIED
        # ======================================================

        parking_bay = await self.parking_bay_repository.get_by_id(
            parking_session.parking_bay_id,
        )

        if parking_bay is None:
            raise NotFoundException(
                "Parking bay not found."
            )

        await self.parking_bay_repository.mark_occupied(
            parking_bay,
        )

        # ======================================================
        # Commit
        # ======================================================

        await self.repository.db.commit()

        await self.repository.db.refresh(
            parking_session,
        )

        # ======================================================
        # Notification
        # ======================================================

        await self._create_session_notification(
            parking_session=parking_session,
            notification_type=NotificationType.SESSION_CHECKED_IN,
            title="Parking Session Started",
            message=(
                f"Your parking session "
                f"{parking_session.session_number} "
                f"has started successfully."
            ),
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
        --------
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
            vehicle_id=reservation.vehicle_id
        )

        await self.repository.save(
            parking_session,
        )

        # ==========================================================
        # Bay Becomes OCCUPIED
        # ==========================================================

        parking_bay = await self.parking_bay_repository.get_by_id(
            parking_session.parking_bay_id,
        )

        if parking_bay is None:
            raise NotFoundException(
                "Parking bay not found."
            )

        await self.parking_bay_repository.mark_occupied(
            parking_bay,
        )

        # ==========================================================
        # Commit
        # ==========================================================

        await self.repository.db.commit()

        await self.repository.db.refresh(
            parking_session,
        )

        # ==========================================================
        # Notification
        # ==========================================================

        await self._create_session_notification(
            parking_session=parking_session,
            notification_type=NotificationType.SESSION_CHECKED_IN,
            title="Parking Session Started",
            message=(
                f"Your parking session "
                f"{parking_session.session_number} "
                f"has started successfully."
            ),
        )

        return parking_session

    # ==========================================================
    # Vehicle Check-Out
    # ==========================================================

    async def check_out_vehicle(
        self,
        checkout_data: ParkingSessionCheckout,
    ) -> ParkingSession:
        """
        Complete an active parking session.

        Workflow
        --------
        Active Session
                ↓
        Calculate Parking Fee
                ↓
        Complete Session
                ↓
        Release Parking Bay
        """

        parking_session = await self.repository.get_active_by_registration(
            checkout_data.vehicle_registration
        )

        if parking_session is None:
            raise NotFoundException(
                "No active parking session found for this vehicle."
            )

        if parking_session.status != SessionStatus.ACTIVE:
            raise BadRequestException(
                "Parking session is not active."
            )

        # ------------------------------------------------------
        # Determine exit time
        # ------------------------------------------------------

        exit_time = utc_now()

        # ------------------------------------------------------
        # Calculate parking fee
        # ------------------------------------------------------

        pricing = await self.pricing_service.calculate_for_session(
            vehicle_type=parking_session.vehicle_type,
            billing_type=parking_session.billing_type,
            entry_time=parking_session.entry_time,
            exit_time=exit_time,
        )

        # ------------------------------------------------------
        # Update session
        # ------------------------------------------------------

        parking_session.exit_time = exit_time
        parking_session.exit_method = checkout_data.exit_method
        parking_session.status = SessionStatus.COMPLETED
        parking_session.duration_minutes = pricing.duration_minutes
        parking_session.calculated_amount = pricing.total_amount

        parking_session.notes = (
            checkout_data.notes
            or parking_session.notes
        )

        await self.repository.save(
            parking_session,
        )

        # ------------------------------------------------------
        # Release parking bay
        # ------------------------------------------------------

        parking_bay = await self.parking_bay_repository.release_bay(
            parking_session.parking_bay_id,
        )

        if parking_bay is None:
            raise NotFoundException(
                "Parking bay not found."
            )

        # ------------------------------------------------------
        # Commit transaction
        # ------------------------------------------------------

        await self.repository.db.commit()

        await self.repository.db.refresh(
            parking_session,
        )

        # ======================================================
        # Notification
        # ======================================================

        await self._create_session_notification(
            parking_session=parking_session,
            notification_type=NotificationType.SESSION_CHECKED_OUT,
            title="Parking Session Completed",
            message=(
                f"Your parking session "
                f"{parking_session.session_number} "
                f"has been completed. "
                f"Parking amount: "
                f"KES {parking_session.calculated_amount}."
            ),
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

        parking_bay = await self.parking_bay_repository.get_by_id(
            parking_bay_id,
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

        Example
        -------
        PS-4F7A8C91DE
        """

        return "PS-" + uuid4().hex[:10].upper()

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