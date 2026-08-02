"""
Parking Reservation Repository

Repository responsible for persistence operations for
Parking Reservations.

Responsibilities
----------------
- CRUD operations
- Reservation lookup
- Conflict detection
- Search
- Availability queries

Business rules belong exclusively in the Service layer.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Select,
    or_,
    func,
    select,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    ReservationStatus,
)

from app.models.parking_reservation import (
    ParkingReservation,
)

from app.repositories.base_repository import (
    BaseRepository,
)


class ParkingReservationRepository(
    BaseRepository[ParkingReservation],
):
    """
    Repository responsible for Parking Reservation persistence.
    """

    # ==========================================================
    # Repository Constants
    # ==========================================================

    ACTIVE_STATUSES = (
        ReservationStatus.CREATED,
        ReservationStatus.CONFIRMED,
    )

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:

        super().__init__(
            db=db,
            model=ParkingReservation,
        )

    # ==========================================================
    # Internal Query Helpers
    # ==========================================================

    def _base_query(
        self,
    ) -> Select:
        """
        Base query used throughout the repository.
        """

        return select(
            ParkingReservation,
        )

    def _active_query(
        self,
    ) -> Select:
        """
        Query returning only active reservations.
        """

        return (
            self._base_query()
            .where(
                ParkingReservation.status.in_(
                    self.ACTIVE_STATUSES,
                )
            )
        )

    # ==========================================================
    # Get By ID
    # ==========================================================

    async def get_by_id(
        self,
        reservation_id: int,
    ) -> ParkingReservation | None:
        """
        Retrieve reservation by primary key.
        """

        statement = (
            self._base_query()
            .where(
                ParkingReservation.id
                == reservation_id
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Get By Reservation Number
    # ==========================================================

    async def get_by_reservation_number(
        self,
        reservation_number: str,
    ) -> ParkingReservation | None:
        """
        Retrieve reservation using its business
        reservation number.
        """

        statement = (
            self._base_query()
            .where(
                ParkingReservation.reservation_number
                == reservation_number
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Get All
    # ==========================================================

    async def get_all(
        self,
    ) -> list[ParkingReservation]:
        """
        Retrieve all reservations.
        """

        statement = (
            self._base_query()
            .order_by(
                ParkingReservation.reserved_from.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Search
    # ==========================================================

    async def search(
        self,
        search_term: str,
    ) -> list[ParkingReservation]:
        """
        Search reservations.

        Matches

        - Reservation Number
        - Vehicle Registration
        """

        statement = (
            self._base_query()
            .where(
                or_(
                    ParkingReservation.reservation_number.ilike(
                        f"%{search_term}%"
                    ),
                    ParkingReservation.vehicle_registration.ilike(
                        f"%{search_term}%"
                    ),
                )
            )
            .order_by(
                ParkingReservation.reserved_from.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all()
        )

        # ==========================================================
    # Customer Queries
    # ==========================================================

    async def get_by_customer(
        self,
        customer_id: int,
    ) -> list[ParkingReservation]:
        """
        Retrieve every reservation belonging to a
        registered customer.
        """

        statement = (
            self._base_query()
            .where(
                ParkingReservation.customer_id == customer_id,
            )
            .order_by(
                ParkingReservation.reserved_from.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(result.scalars().all())

    async def get_active_by_customer(
        self,
        customer_id: int,
    ) -> list[ParkingReservation]:
        """
        Retrieve active reservations belonging to a
        registered customer.
        """

        statement = (
            self._active_query()
            .where(
                ParkingReservation.customer_id == customer_id,
            )
            .order_by(
                ParkingReservation.reserved_from.asc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(result.scalars().all())

    # ==========================================================
    # Vehicle Queries
    # ==========================================================

    async def get_by_vehicle(
        self,
        vehicle_registration: str,
    ) -> list[ParkingReservation]:
        """
        Retrieve every reservation for a vehicle.

        Supports both guest and registered drivers.
        """

        statement = (
            self._base_query()
            .where(
                ParkingReservation.vehicle_registration
                == vehicle_registration.upper(),
            )
            .order_by(
                ParkingReservation.reserved_from.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(result.scalars().all())

    async def get_active_by_vehicle(
        self,
        vehicle_registration: str,
    ) -> list[ParkingReservation]:
        """
        Retrieve active reservations for a vehicle.
        """

        statement = (
            self._active_query()
            .where(
                ParkingReservation.vehicle_registration
                == vehicle_registration.upper(),
            )
            .order_by(
                ParkingReservation.reserved_from.asc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(result.scalars().all())

    # ==========================================================
    # Parking Bay Queries
    # ==========================================================

    async def get_by_parking_bay(
        self,
        parking_bay_id: int,
    ) -> list[ParkingReservation]:
        """
        Retrieve every reservation for a parking bay.
        """

        statement = (
            self._base_query()
            .where(
                ParkingReservation.parking_bay_id
                == parking_bay_id,
            )
            .order_by(
                ParkingReservation.reserved_from.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(result.scalars().all())

    async def get_active_by_parking_bay(
        self,
        parking_bay_id: int,
    ) -> list[ParkingReservation]:
        """
        Retrieve active reservations for a parking bay.
        """

        statement = (
            self._active_query()
            .where(
                ParkingReservation.parking_bay_id
                == parking_bay_id,
            )
            .order_by(
                ParkingReservation.reserved_from.asc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(result.scalars().all())

        # ==========================================================
    # Reservation Conflict Detection
    # ==========================================================

    async def find_conflicting_reservations(
        self,
        parking_bay_id: int,
        reserved_from: datetime,
        reserved_until: datetime,
        exclude_reservation_id: int | None = None,
    ) -> list[ParkingReservation]:
        """
        Find reservations overlapping the supplied period.

        Only active reservations participate in
        conflict detection.
        """

        statement = (
            self._active_query()
            .where(
                ParkingReservation.parking_bay_id
                == parking_bay_id,

                ParkingReservation.reserved_from
                < reserved_until,

                ParkingReservation.reserved_until
                > reserved_from,
            )
        )

        if exclude_reservation_id is not None:

            statement = statement.where(
                ParkingReservation.id
                != exclude_reservation_id,
            )

        statement = statement.order_by(
            ParkingReservation.reserved_from.asc(),
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Active Reservation Lookup
    # ==========================================================

    async def find_active_reservation(
        self,
        parking_bay_id: int,
        effective_at: datetime,
    ) -> ParkingReservation | None:
        """
        Find the reservation occupying a bay at a
        particular point in time.
        """

        statement = (
            self._active_query()
            .where(
                ParkingReservation.parking_bay_id
                == parking_bay_id,

                ParkingReservation.reserved_from
                <= effective_at,

                ParkingReservation.reserved_until
                >= effective_at,
            )
            .order_by(
                ParkingReservation.reserved_from.asc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Reservation Check-in
    # ==========================================================

    async def find_due_for_checkin(
        self,
        reservation_number: str,
    ) -> ParkingReservation | None:
        """
        Retrieve a reservation that is eligible
        for check-in.
        """

        statement = (
            self._active_query()
            .where(
                ParkingReservation.reservation_number
                == reservation_number,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    async def find_vehicle_reservation(
        self,
        vehicle_registration: str,
        effective_at: datetime,
    ) -> ParkingReservation | None:
        """
        Find the reservation belonging to a vehicle
        at the supplied point in time.

        Used by:

        - QR Code
        - ANPR
        - Attendant Check-in
        """

        statement = (
            self._active_query()
            .where(
                ParkingReservation.vehicle_registration
                == vehicle_registration.upper(),

                ParkingReservation.reserved_from
                <= effective_at,

                ParkingReservation.reserved_until
                >= effective_at,
            )
            .order_by(
                ParkingReservation.reserved_from.asc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Expired Reservations
    # ==========================================================

    async def find_expired_reservations(
        self,
        as_of: datetime,
    ) -> list[ParkingReservation]:
        """
        Retrieve reservations that should now expire.
        """

        statement = (
            self._active_query()
            .where(
                ParkingReservation.expires_at.is_not(None),

                ParkingReservation.expires_at
                < as_of,
            )
            .order_by(
                ParkingReservation.expires_at.asc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Active Reservations
    # ==========================================================

    async def find_active_reservations(
        self,
    ) -> list[ParkingReservation]:
        """
        Retrieve every active reservation.
        """

        statement = (
            self._active_query()
            .order_by(
                ParkingReservation.reserved_from.asc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all()
        )

        # ==========================================================
    # Reservation Statistics
    # ==========================================================

    async def count_active_reservations(
        self,
    ) -> int:
        """
        Count all active reservations.
        """

        statement = (
            select(
                func.count(ParkingReservation.id)
            )
            .where(
                ParkingReservation.status.in_(
                    self.ACTIVE_STATUSES,
                )
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one()

    async def count_customer_reservations(
        self,
        customer_id: int,
    ) -> int:
        """
        Count reservations belonging to a customer.
        """

        statement = (
            select(
                func.count(ParkingReservation.id)
            )
            .where(
                ParkingReservation.customer_id
                == customer_id,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one()

    async def count_vehicle_reservations(
        self,
        vehicle_registration: str,
    ) -> int:
        """
        Count reservations belonging to a vehicle.

        Supports guest and registered customers.
        """

        statement = (
            select(
                func.count(ParkingReservation.id)
            )
            .where(
                ParkingReservation.vehicle_registration
                == vehicle_registration.upper(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one()

    # ==========================================================
    # Convenience Methods
    # ==========================================================

    async def reservation_exists(
        self,
        reservation_number: str,
    ) -> bool:
        """
        Determine whether a reservation exists.
        """

        return (
            await self.get_by_reservation_number(
                reservation_number,
            )
            is not None
        )

    async def has_conflicts(
        self,
        parking_bay_id: int,
        reserved_from: datetime,
        reserved_until: datetime,
        exclude_reservation_id: int | None = None,
    ) -> bool:
        """
        Determine whether a reservation conflicts
        with existing reservations.
        """

        conflicts = (
            await self.find_conflicting_reservations(
                parking_bay_id=parking_bay_id,
                reserved_from=reserved_from,
                reserved_until=reserved_until,
                exclude_reservation_id=exclude_reservation_id,
            )
        )

        return bool(conflicts)

    async def has_active_vehicle_reservation(
        self,
        vehicle_registration: str,
    ) -> bool:
        """
        Determine whether a vehicle currently has an
        active reservation.
        """

        reservations = (
            await self.get_active_by_vehicle(
                vehicle_registration,
            )
        )

        return bool(reservations)

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(
        self,
    ) -> str:

        return (
            f"{self.__class__.__name__}"
            f"(model={self.model.__name__})"
        )

    # ==========================================================
    # Bay State Management
    # ==========================================================

    async def reserve_bay(
        self,
        parking_bay_id: int,
    ) -> None:
        """
        Mark a parking bay as reserved.
        """

        bay = await self.get_by_id(parking_bay_id)

        if bay is None:
            raise ValueError(
                "Parking bay not found."
            )

        bay.is_available = False

        await self.db.flush()


    async def release_bay(
        self,
        parking_bay_id: int,
    ) -> None:
        """
        Release a parking bay.

        Used when:
        - reservation is cancelled
        - reservation expires
        - session completes
        """

        bay = await self.get_by_id(parking_bay_id)

        if bay is None:
            raise ValueError(
                "Parking bay not found."
            )

        bay.is_available = True

        if hasattr(bay, "is_occupied"):
            bay.is_occupied = False

        await self.db.flush()


    async def mark_occupied(
        self,
        parking_bay_id: int,
    ) -> None:
        """
        Mark a parking bay as occupied.
        """

        bay = await self.get_by_id(parking_bay_id)

        if bay is None:
            raise ValueError(
                "Parking bay not found."
            )

        bay.is_available = False

        if hasattr(bay, "is_occupied"):
            bay.is_occupied = True

        await self.db.flush()