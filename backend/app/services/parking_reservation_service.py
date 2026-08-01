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

Persistence belongs in repositories.
"""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from app.models.enums import (
    ReservationStatus,
)

from app.models.parking_reservation import (
    ParkingReservation,
)

from app.repositories.parking_bay_repository import (
    ParkingBayRepository,
)

from app.repositories.parking_reservation_repository import (
    ParkingReservationRepository,
)

from app.schemas.parking_reservation import (
    ParkingReservationCreate,
    ParkingReservationUpdate,
)

from app.services.pricing_service import (
    PricingService,
)

from app.services.parking_session_service import (
    ParkingSessionService,
)


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
    ) -> None:
        """
        Create a Reservation Service.
        """

        self.repository = repository

        self.parking_bay_repository = (
            parking_bay_repository
        )

        self.pricing_service = pricing_service

        self.parking_session_service = (
            parking_session_service
        )

    # ==========================================================
    # Reservation Number
    # ==========================================================

    async def _generate_reservation_number(
        self,
    ) -> str:
        """
        Generate a unique reservation number.

        Example

        RES-8A2C6D91
        """

        while True:

            reservation_number = (
                f"RES-{uuid4().hex[:8].upper()}"
            )

            exists = (
                await self.repository.reservation_exists(
                    reservation_number,
                )
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
        Validate that the parking bay exists
        and is reservable.
        """

        bay = (
            await self.parking_bay_repository.get_by_id(
                parking_bay_id,
            )
        )

        if bay is None:
            raise ValueError(
                "Parking bay does not exist."
            )

        if not bay.is_active:
            raise ValueError(
                "Parking bay is inactive."
            )

        if not bay.is_reservable:
            raise ValueError(
                "Parking bay cannot be reserved."
            )

        return bay

    async def _validate_no_conflicts(
        self,
        parking_bay_id: int,
        reserved_from: datetime,
        reserved_until: datetime,
        exclude_reservation_id: int | None = None,
    ) -> None:
        """
        Ensure there are no overlapping reservations.
        """

        conflicts = (
            await self.repository.find_conflicting_reservations(
                parking_bay_id=parking_bay_id,
                reserved_from=reserved_from,
                reserved_until=reserved_until,
                exclude_reservation_id=exclude_reservation_id,
            )
        )

        if conflicts:
            raise ValueError(
                "The parking bay is already reserved "
                "for the requested period."
            )

            # ==========================================================
    # Create Reservation
    # ==========================================================

    async def create_reservation(
        self,
        data: ParkingReservationCreate,
    ) -> ParkingReservation:
        """
        Create a new parking reservation.
        """

        # Validate parking bay
        await self._validate_parking_bay(
            data.parking_bay_id,
        )

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

        reservation = ParkingReservation(
            reservation_number=reservation_number,
            customer_id=data.customer_id,
            parking_bay_id=data.parking_bay_id,
            vehicle_registration=data.vehicle_registration,
            vehicle_type=data.vehicle_type,
            reserved_from=data.reserved_from,
            reserved_until=data.reserved_until,
            notes=data.notes,
            status=ReservationStatus.CREATED,
        )

        await self.repository.save(
            reservation,
        )

        await self.repository.commit()

        await self.repository.refresh(
            reservation,
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

        return (
            await self.repository.get_by_reservation_number(
                reservation_number,
            )
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
        """

        reservation = (
            await self.repository.get_by_id(
                reservation_id,
            )
        )

        if reservation is None:
            return None

        update_data = data.model_dump(
            exclude_unset=True,
        )

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

        await self._validate_parking_bay(
            parking_bay_id,
        )

        await self._validate_no_conflicts(
            parking_bay_id=parking_bay_id,
            reserved_from=reserved_from,
            reserved_until=reserved_until,
            exclude_reservation_id=reservation.id,
        )

        for field, value in update_data.items():
            setattr(
                reservation,
                field,
                value,
            )

        reservation.updated_at = datetime.utcnow()

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

        reservation = (
            await self.repository.get_by_id(
                reservation_id,
            )
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
            raise ValueError(
                "Only CREATED reservations can be confirmed."
            )

        reservation.status = ReservationStatus.CONFIRMED
        reservation.confirmed_at = datetime.utcnow()
        reservation.updated_at = datetime.utcnow()

        await self.repository.save(
            reservation,
        )

        await self.repository.commit()

        await self.repository.refresh(
            reservation,
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
            raise ValueError(
                "Completed or checked-in reservations "
                "cannot be cancelled."
            )

        reservation.status = ReservationStatus.CANCELLED
        reservation.cancelled_at = datetime.utcnow()
        reservation.updated_at = datetime.utcnow()

        await self.repository.save(
            reservation,
        )

        await self.repository.commit()

        await self.repository.refresh(
            reservation,
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

        reservation.status = ReservationStatus.EXPIRED
        reservation.updated_at = datetime.utcnow()

        await self.repository.save(
            reservation,
        )

        await self.repository.commit()

        await self.repository.refresh(
            reservation,
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

        expired = await self.repository.find_expired_reservations(
            datetime.utcnow(),
        )

        count = 0

        for reservation in expired:

            reservation.status = ReservationStatus.EXPIRED
            reservation.updated_at = datetime.utcnow()

            await self.repository.save(
                reservation,
            )

            count += 1

        if count > 0:
            await self.repository.commit()

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

        # ==========================================================
    # Check In
    # ==========================================================

    async def check_in(
        self,
        reservation_id: int,
    ) -> ParkingReservation | None:
        """
        Check in a reservation.

        The reservation is converted into an active
        Parking Session.
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
            raise ValueError(
                "Only CREATED or CONFIRMED reservations "
                "can be checked in."
            )

        session = await self.parking_session_service.create_from_reservation(
            reservation,
        )

        reservation.status = ReservationStatus.CHECKED_IN

        reservation.checked_in_at = datetime.utcnow()

        reservation.updated_at = datetime.utcnow()

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

        return (
            await self.repository.count_active_reservations()
        )

    async def count_customer_reservations(
        self,
        customer_id: int,
    ) -> int:
        """
        Count reservations belonging to a customer.
        """

        return (
            await self.repository.count_customer_reservations(
                customer_id,
            )
        )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(
        self,
    ) -> str:
        """
        Developer representation.
        """

        return (
            f"{self.__class__.__name__}("
            f"repository={self.repository.__class__.__name__}"
            f")"
        )