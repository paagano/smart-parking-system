"""
Parking Reservation Service

Business service responsible for Parking Reservation
management.

Responsibilities
----------------
✔ Reservation lifecycle
✔ Reservation validation
✔ Reservation numbering
✔ Bay availability validation
✔ Reservation conflict detection
✔ Pricing estimation
✔ Check-in workflow
✔ Reservation notifications

Persistence belongs in repositories.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from app.exceptions.handlers import (
    BadRequestException,
    NotFoundException,
)

from app.models.enums import (
    BillingType,
    NotificationChannel,
    NotificationPriority,
    NotificationType,
    ReservationStatus,
)

from app.models.parking_reservation import ParkingReservation

from app.repositories.parking_bay_repository import (
    ParkingBayRepository,
)

from app.repositories.parking_reservation_repository import (
    ParkingReservationRepository,
)

from app.repositories.parking_session_repository import (
    ParkingSessionRepository,
)

from app.repositories.vehicle_repository import (
    VehicleRepository,
)

from app.schemas.notification import (
    NotificationCreate,
)

from app.schemas.parking_reservation import (
    ParkingReservationCreate,
    ParkingReservationUpdate,
)

from app.services.notification_service import (
    NotificationService,
)

from app.services.parking_session_service import (
    ParkingSessionService,
)

from app.services.pricing_service import (
    PricingService,
)

from app.utils.datetime import utc_now


class ParkingReservationService:
    """
    Enterprise Reservation Service.
    """

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        repository: ParkingReservationRepository,
        parking_bay_repository: ParkingBayRepository,
        pricing_service: PricingService,
        parking_session_service: ParkingSessionService,
        vehicle_repository: VehicleRepository,
        notification_service: NotificationService,
    ) -> None:
        """
        Create a Reservation Service.
        """

        self.repository = repository
        self.parking_bay_repository = parking_bay_repository
        self.pricing_service = pricing_service
        self.parking_session_service = parking_session_service
        self.vehicle_repository = vehicle_repository
        self.notification_service = notification_service

    # ==========================================================
    # Notification Helper
    # ==========================================================

    async def _create_reservation_notification(
        self,
        *,
        reservation: ParkingReservation,
        notification_type: NotificationType,
        title: str,
        message: str,
    ) -> None:
        """
        Create an in-app notification for a reservation event.

        Notifications are created only after the underlying
        reservation operation has successfully committed.

        Notification failures are intentionally isolated from
        the reservation business operation so that a notification
        problem cannot invalidate an already successful
        reservation transaction.
        """

        try:
            await self.notification_service.create_notification(
                data=NotificationCreate(
                    user_id=reservation.customer_id,
                    type=notification_type,
                    channel=NotificationChannel.IN_APP,
                    priority=NotificationPriority.NORMAL,
                    title=title,
                    message=message,
                    related_entity_type="PARKING_RESERVATION",
                    related_entity_id=reservation.id,
                ),
            )

        except Exception:
            # Notification delivery/persistence must not break
            # an already successful reservation operation.
            #
            # The reservation has already been committed before
            # this method is called.
            #
            # We deliberately do not re-raise the exception here.
            pass

    # ==========================================================
    # Reservation Number
    # ==========================================================

    async def _generate_reservation_number(self) -> str:
        """
        Generate a unique reservation number.

        Example
        -------
        RES-8A2C6D91
        """

        while True:
            reservation_number = (
                f"RES-{uuid4().hex[:8].upper()}"
            )

            exists = await self.repository.reservation_exists(
                reservation_number,
            )

            if not exists:
                return reservation_number

    # ==========================================================
    # Validation
    # ==========================================================

    async def _validate_parking_bay(
        self,
        parking_bay_id: int,
    ):
        """
        Validate that the parking bay exists and is reservable.
        """

        bay = await self.parking_bay_repository.get_by_id(
            parking_bay_id,
        )

        if bay is None:
            raise NotFoundException(
                "Parking bay does not exist."
            )

        if not bay.is_active:
            raise BadRequestException(
                "Parking bay is inactive."
            )

        if not bay.is_reservable:
            raise BadRequestException(
                "Parking bay cannot be reserved."
            )

        return bay

    async def _validate_vehicle(
        self,
        *,
        vehicle_id: int,
        customer_id: int,
    ):
        """
        Validate that the vehicle exists, is active,
        and belongs to the customer making the reservation.
        """

        vehicle = await self.vehicle_repository.get_by_id(
            vehicle_id,
        )

        if vehicle is None:
            raise BadRequestException(
                "Vehicle does not exist."
            )

        if not vehicle.is_active:
            raise BadRequestException(
                "Vehicle is inactive."
            )

        if vehicle.customer_id != customer_id:
            raise BadRequestException(
                "Vehicle does not belong to the customer."
            )

        return vehicle

    async def _validate_no_conflicts(
        self,
        parking_bay_id: int,
        reserved_from: datetime,
        reserved_until: datetime,
        exclude_reservation_id: int | None = None,
    ) -> None:
        """
        Ensure the parking bay is available for reservation.

        A bay is unavailable if:

        - it already has an ACTIVE parking session
        - it has an overlapping active reservation
        """

        #
        # Active parking session
        #

        if await self.parking_session_service.has_active_session(
            parking_bay_id,
        ):
            raise BadRequestException(
                "The parking bay is currently occupied."
            )

        #
        # Overlapping reservation
        #

        conflicts = (
            await self.repository.find_conflicting_reservations(
                parking_bay_id=parking_bay_id,
                reserved_from=reserved_from,
                reserved_until=reserved_until,
                exclude_reservation_id=exclude_reservation_id,
            )
        )

        if conflicts:
            raise BadRequestException(
                "The parking bay is already reserved "
                "for the requested period."
            )

    # ==========================================================
    # Create Reservation
    # ==========================================================

    async def create_reservation(
        self,
        data: ParkingReservationCreate,
        customer_id: int,
    ) -> ParkingReservation:
        """
        Create a new parking reservation.
        """

        # Validate parking bay

        await self._validate_parking_bay(
            data.parking_bay_id,
        )

        # ======================================================
        # Resolve Vehicle
        # ======================================================

        vehicle = None

        if data.vehicle_id is not None:

            # Registered vehicle

            vehicle = await self._validate_vehicle(
                vehicle_id=data.vehicle_id,
                customer_id=customer_id,
            )

            resolved_vehicle_id = vehicle.id

            resolved_vehicle_registration = (
                vehicle.registration_number
            )

            resolved_vehicle_type = vehicle.vehicle_type

        else:

            # Borrowed / temporary vehicle

            resolved_vehicle_id = None

            resolved_vehicle_registration = (
                data.vehicle_registration
            )

            resolved_vehicle_type = data.vehicle_type

        # Check for overlapping reservations

        await self._validate_no_conflicts(
            parking_bay_id=data.parking_bay_id,
            reserved_from=data.reserved_from,
            reserved_until=data.reserved_until,
        )

        # Generate reservation number

        reservation_number = (
            await self._generate_reservation_number()
        )

        expires_at = (
            data.reserved_from
            - timedelta(minutes=30)
        )

        # Calculate estimated amount once

        vehicle_type = (
            vehicle.vehicle_type
            if vehicle is not None
            else data.vehicle_type
        )

        pricing = await self.pricing_service.estimate_price(
            vehicle_type=resolved_vehicle_type,
            billing_type=BillingType.HOURLY,
            entry_time=data.reserved_from,
            exit_time=data.reserved_until,
        )

        estimated_amount = pricing.total_amount

        reservation = ParkingReservation(
            reservation_number=reservation_number,
            customer_id=customer_id,
            parking_bay_id=data.parking_bay_id,
            vehicle_id=resolved_vehicle_id,
            vehicle_registration=resolved_vehicle_registration,
            vehicle_type=resolved_vehicle_type,
            reserved_from=data.reserved_from,
            reserved_until=data.reserved_until,
            estimated_amount=estimated_amount,
            notes=data.notes,
            expires_at=expires_at,
            status=ReservationStatus.CREATED,
        )

        await self.repository.save(
            reservation,
        )

        await self.repository.commit()

        # ======================================================
        # Notification
        # ======================================================

        await self._create_reservation_notification(
            reservation=reservation,
            notification_type=NotificationType.RESERVATION_CREATED,
            title="Reservation Created",
            message=(
                f"Your parking reservation "
                f"{reservation.reservation_number} "
                f"has been created successfully."
            ),
        )

        return reservation

    # ==========================================================
    # Get Reservation
    # ==========================================================

    async def get_by_id(
        self,
        reservation_id: int,
    ) -> ParkingReservation | None:
        """
        Retrieve a reservation by ID.
        """

        return await self.repository.get_by_id(
            reservation_id,
        )

    async def get_by_reservation_number(
        self,
        reservation_number: str,
    ) -> ParkingReservation | None:
        """
        Retrieve a reservation by reservation number.
        """

        return await self.repository.get_by_reservation_number(
            reservation_number,
        )

    async def get_all(
        self,
    ) -> list[ParkingReservation]:
        """
        Retrieve all reservations.
        """

        return await self.repository.get_all()

    async def search(
        self,
        search_term: str,
    ) -> list[ParkingReservation]:
        """
        Search reservations.
        """

        return await self.repository.search(
            search_term,
        )

    # ==========================================================
    # Update Reservation
    # ==========================================================

    async def update_reservation(
        self,
        reservation_id: int,
        data: ParkingReservationUpdate,
    ) -> ParkingReservation | None:
        """
        Update an existing reservation.

        Vehicle-related updates are controlled by the registered
        Vehicle entity. The client may provide vehicle_id, but
        vehicle_registration and vehicle_type are always derived
        from the registered vehicle.

        Existing reservation/payment behaviour is preserved.
        """

        # ======================================================
        # Retrieve Reservation
        # ======================================================

        reservation = await self.repository.get_by_id(
            reservation_id,
        )

        if reservation is None:
            return None

        # ======================================================
        # Extract Update Data
        # ======================================================

        update_data = data.model_dump(
            exclude_unset=True,
        )

        # ======================================================
        # Resolve Reservation Values
        # ======================================================

        parking_bay_id = update_data.get(
            "parking_bay_id",
            reservation.parking_bay_id,
        )

        reserved_from = update_data.get(
            "reserved_from",
            reservation.reserved_from,
        )

        reserved_until = update_data.get(
            "reserved_until",
            reservation.reserved_until,
        )

        # ======================================================
        # Validate Parking Bay
        # ======================================================

        await self._validate_parking_bay(
            parking_bay_id,
        )

        # ======================================================
        # Vehicle Integration
        # ======================================================

        vehicle = None

        # ======================================================
        # Vehicle Change Handling
        # ======================================================

        if "vehicle_id" in data.model_fields_set:

            if (
                data.vehicle_id is not None
                and (
                    data.vehicle_registration is not None
                    or data.vehicle_type is not None
                )
            ):
                raise BadRequestException(
                    "When vehicle_id is provided, "
                    "vehicle_registration and vehicle_type "
                    "must not be supplied."
                )

            # --------------------------------------------------
            # Switch to registered vehicle
            # --------------------------------------------------

            if data.vehicle_id is not None:

                vehicle = await self._validate_vehicle(
                    vehicle_id=data.vehicle_id,
                    customer_id=reservation.customer_id,
                )

                reservation.vehicle_id = vehicle.id

                reservation.vehicle_registration = (
                    vehicle.registration_number
                )

                reservation.vehicle_type = (
                    vehicle.vehicle_type
                )

            # --------------------------------------------------
            # Switch to borrowed vehicle
            # --------------------------------------------------

            else:

                if data.vehicle_registration is None:
                    raise BadRequestException(
                        "Vehicle registration is required "
                        "when using a borrowed vehicle."
                    )

                if data.vehicle_type is None:
                    raise BadRequestException(
                        "Vehicle type is required "
                        "when using a borrowed vehicle."
                    )

                reservation.vehicle_id = None

                reservation.vehicle_registration = (
                    data.vehicle_registration
                )

                reservation.vehicle_type = (
                    data.vehicle_type
                )

        # ======================================================
        # Validate Reservation Conflicts
        # ======================================================

        await self._validate_no_conflicts(
            parking_bay_id=parking_bay_id,
            reserved_from=reserved_from,
            reserved_until=reserved_until,
            exclude_reservation_id=reservation.id,
        )

        # ======================================================
        # Apply Non-Vehicle Updates
        # ======================================================

        for field, value in update_data.items():

            if field in (
                "vehicle_id",
                "vehicle_registration",
                "vehicle_type",
            ):
                continue

            setattr(
                reservation,
                field,
                value,
            )

        # ======================================================
        # Apply Vehicle Update
        # ======================================================

        if vehicle is not None:

            reservation.vehicle_id = vehicle.id

            reservation.vehicle_registration = (
                vehicle.registration_number
            )

            reservation.vehicle_type = (
                vehicle.vehicle_type
            )

        # ======================================================
        # Update Expiry
        # ======================================================

        if "reserved_from" in update_data:

            reservation.expires_at = (
                reservation.reserved_from
                - timedelta(minutes=30)
            )

        # ======================================================
        # Recalculate Estimated Amount
        # ======================================================

        if (
            "parking_bay_id" in update_data
            or "vehicle_id" in update_data
            or "vehicle_type" in update_data
            or "reserved_from" in update_data
            or "reserved_until" in update_data
        ):

            pricing = await self.pricing_service.estimate_price(
                vehicle_type=reservation.vehicle_type,
                billing_type=BillingType.HOURLY,
                entry_time=reservation.reserved_from,
                exit_time=reservation.reserved_until,
            )

            reservation.estimated_amount = (
                pricing.total_amount
            )

        # ======================================================
        # Audit Timestamp
        # ======================================================

        reservation.updated_at = utc_now()

        # ======================================================
        # Persist
        # ======================================================

        await self.repository.save(
            reservation,
        )

        await self.repository.commit()

        await self.repository.refresh(
            reservation,
        )

        return reservation

    # ==========================================================
    # Delete Reservation
    # ==========================================================

    async def delete_reservation(
        self,
        reservation_id: int,
    ) -> bool:
        """
        Delete a reservation.
        """

        reservation = await self.repository.get_by_id(
            reservation_id,
        )

        if reservation is None:
            return False

        await self.repository.remove(
            reservation,
        )

        await self.repository.commit()

        return True

    # ==========================================================
    # Confirm Reservation
    # ==========================================================

    async def confirm_reservation(
        self,
        reservation_id: int,
    ) -> ParkingReservation | None:
        """
        Confirm a reservation.
        """

        reservation = await self.repository.get_by_id(
            reservation_id,
        )

        if reservation is None:
            return None

        if reservation.status != ReservationStatus.CREATED:
            raise BadRequestException(
                "Only CREATED reservations can be confirmed."
            )

        reservation.status = (
            ReservationStatus.CONFIRMED
        )

        reservation.confirmed_at = utc_now()

        reservation.updated_at = utc_now()

        await self.repository.save(
            reservation,
        )

        await self.repository.commit()

        await self.repository.refresh(
            reservation,
        )

        # ======================================================
        # Notification
        # ======================================================

        await self._create_reservation_notification(
            reservation=reservation,
            notification_type=NotificationType.RESERVATION_CONFIRMED,
            title="Reservation Confirmed",
            message=(
                f"Your parking reservation "
                f"{reservation.reservation_number} "
                f"has been confirmed."
            ),
        )

        return reservation

    # ==========================================================
    # Cancel Reservation
    # ==========================================================

    async def cancel_reservation(
        self,
        reservation_id: int,
    ) -> ParkingReservation | None:
        """
        Cancel a reservation.
        """

        reservation = await self.repository.get_by_id(
            reservation_id,
        )

        if reservation is None:
            return None

        if reservation.status in (
            ReservationStatus.CHECKED_IN,
            ReservationStatus.COMPLETED,
        ):
            raise BadRequestException(
                "Completed or checked-in reservations "
                "cannot be cancelled."
            )

        reservation.status = (
            ReservationStatus.CANCELLED
        )

        reservation.cancelled_at = utc_now()

        reservation.updated_at = utc_now()

        await self.repository.save(
            reservation,
        )

        await self.repository.commit()

        await self.repository.refresh(
            reservation,
        )

        # ======================================================
        # Notification
        # ======================================================

        await self._create_reservation_notification(
            reservation=reservation,
            notification_type=NotificationType.RESERVATION_CANCELLED,
            title="Reservation Cancelled",
            message=(
                f"Your parking reservation "
                f"{reservation.reservation_number} "
                f"has been cancelled."
            ),
        )

        return reservation

    # ==========================================================
    # Expire Reservation
    # ==========================================================

    async def expire_reservation(
        self,
        reservation_id: int,
    ) -> ParkingReservation | None:
        """
        Mark a reservation as expired.
        """

        reservation = await self.repository.get_by_id(
            reservation_id,
        )

        if reservation is None:
            return None

        if reservation.status not in (
            ReservationStatus.CREATED,
            ReservationStatus.CONFIRMED,
        ):
            return reservation

        reservation.status = (
            ReservationStatus.EXPIRED
        )

        reservation.updated_at = utc_now()

        await self.repository.save(
            reservation,
        )

        await self.repository.commit()

        await self.repository.refresh(
            reservation,
        )

        # ======================================================
        # Notification
        # ======================================================

        await self._create_reservation_notification(
            reservation=reservation,
            notification_type=NotificationType.RESERVATION_EXPIRED,
            title="Reservation Expired",
            message=(
                f"Your parking reservation "
                f"{reservation.reservation_number} "
                f"has expired."
            ),
        )

        return reservation

    # ==========================================================
    # Expire Overdue Reservations
    # ==========================================================

    async def expire_overdue_reservations(
        self,
    ) -> int:
        """
        Expire all overdue reservations.

        Returns
        -------
        int
            Number of reservations expired.
        """

        expired = (
            await self.repository.find_expired_reservations(
                utc_now(),
            )
        )

        count = 0

        for reservation in expired:

            reservation.status = (
                ReservationStatus.EXPIRED
            )

            reservation.updated_at = utc_now()

            await self.repository.save(
                reservation,
            )

            count += 1

        if count > 0:

            await self.repository.commit()

            # Release all expired bays

            for reservation in expired:

                await self.parking_bay_repository.release_bay(
                    reservation.parking_bay_id,
                )

            # ==================================================
            # Notifications
            # ==================================================

            for reservation in expired:

                await self._create_reservation_notification(
                    reservation=reservation,
                    notification_type=(
                        NotificationType.RESERVATION_EXPIRED
                    ),
                    title="Reservation Expired",
                    message=(
                        f"Your parking reservation "
                        f"{reservation.reservation_number} "
                        f"has expired."
                    ),
                )

        return count

    # ==========================================================
    # Customer Queries
    # ==========================================================

    async def get_customer_reservations(
        self,
        customer_id: int,
    ) -> list[ParkingReservation]:
        """
        Retrieve all reservations for a customer.
        """

        return await self.repository.get_by_customer(
            customer_id,
        )

    async def get_active_customer_reservations(
        self,
        customer_id: int,
    ) -> list[ParkingReservation]:
        """
        Retrieve active reservations for a customer.
        """

        return await self.repository.get_active_by_customer(
            customer_id,
        )

    async def get_by_vehicle(
        self,
        vehicle_registration: str,
    ) -> list[ParkingReservation]:
        """
        Retrieve all reservations for a vehicle registration.
        """

        return await self.repository.get_by_vehicle(
            vehicle_registration,
        )

    async def get_active_by_vehicle(
        self,
        vehicle_registration: str,
    ) -> list[ParkingReservation]:
        """
        Retrieve active reservations for a vehicle.
        """

        return await self.repository.get_active_by_vehicle(
            vehicle_registration,
        )

    async def get_by_parking_bay(
        self,
        parking_bay_id: int,
    ) -> list[ParkingReservation]:
        """
        Retrieve all reservations for a parking bay.
        """

        return await self.repository.get_by_parking_bay(
            parking_bay_id,
        )

    async def get_active_by_parking_bay(
        self,
        parking_bay_id: int,
    ) -> list[ParkingReservation]:
        """
        Retrieve active reservations for a parking bay.
        """

        return await self.repository.get_active_by_parking_bay(
            parking_bay_id,
        )

    # ==========================================================
    # Check In
    # ==========================================================

    async def check_in(
        self,
        reservation_id: int,
    ) -> ParkingReservation | None:
        """
        Check in a reservation.

        The reservation is converted into an active Parking Session.
        """

        reservation = await self.repository.get_by_id(
            reservation_id,
        )

        if reservation is None:
            return None

        if reservation.status not in (
            ReservationStatus.CREATED,
            ReservationStatus.CONFIRMED,
        ):
            raise BadRequestException(
                "Only CREATED or CONFIRMED reservations "
                "can be checked in."
            )

        now = utc_now()

        if now < reservation.reserved_from - timedelta(
            minutes=30,
        ):
            raise BadRequestException(
                "Vehicles can only be checked in 30 minutes "
                "before their reserved time."
            )

        if now > reservation.reserved_until:
            raise BadRequestException(
                "Vehicles cannot be checked in after "
                "their reserved time."
            )

        # Create parking session from reservation

        await self.parking_session_service.create_from_reservation(
            reservation,
        )

        reservation.status = (
            ReservationStatus.CHECKED_IN
        )

        reservation.checked_in_at = utc_now()

        reservation.updated_at = utc_now()

        await self.repository.save(
            reservation,
        )

        await self.repository.commit()

        await self.repository.refresh(
            reservation,
        )

        return reservation

    # ==========================================================
    # Reservation Statistics
    # ==========================================================

    async def count_active_reservations(
        self,
    ) -> int:
        """
        Count active reservations.
        """

        return await self.repository.count_active_reservations()

    async def count_customer_reservations(
        self,
        customer_id: int,
    ) -> int:
        """
        Count reservations belonging to a customer.
        """

        return await self.repository.count_customer_reservations(
            customer_id,
        )

    async def count_vehicle_reservations(
        self,
        vehicle_registration: str,
    ) -> int:
        """
        Count reservations belonging to a vehicle.
        """

        return await self.repository.count_vehicle_reservations(
            vehicle_registration,
        )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        """
        Developer representation.
        """

        return (
            f"{self.__class__.__name__}("
            f"repository={self.repository.__class__.__name__}"
            f")"
        )