"""
Parking Reservation Repository

Repository responsible for persistence operations for
Parking Reservations.

Responsibilities
----------------
- CRUD operations
- Reservation lookup
- Search
- Conflict detection
- Availability queries

Business rules belong in the Reservation Service.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Select,
    or_,
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
    BaseRepository[ParkingReservation]
):
    """
    Repository for ParkingReservation persistence.
    """

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        """
        Create repository instance.
        """

        super().__init__(
            db=db,
            model=ParkingReservation,
        )

    # ==========================================================
    # Get By ID
    # ==========================================================

    async def get_by_id(
        self,
        reservation_id: int,
    ) -> ParkingReservation | None:
        """
        Retrieve a reservation by its identifier.
        """

        statement: Select = (
            select(
                ParkingReservation,
            )
            .where(
                ParkingReservation.id == reservation_id,
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
        Retrieve a reservation using its business
        reservation number.
        """

        statement: Select = (
            select(
                ParkingReservation,
            )
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
        Retrieve all reservations ordered by
        reservation start date.
        """

        statement: Select = (
            select(
                ParkingReservation,
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
    # Search
    # ==========================================================

    async def search(
        self,
        search_term: str,
    ) -> list[ParkingReservation]:
        """
        Search reservations by reservation number or
        vehicle registration.
        """

        statement: Select = (
            select(
                ParkingReservation,
            )
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
        Retrieve all reservations belonging to a customer.
        """

        statement: Select = (
            select(
                ParkingReservation,
            )
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

        return list(
            result.scalars().all()
        )

    async def get_active_by_customer(
        self,
        customer_id: int,
    ) -> list[ParkingReservation]:
        """
        Retrieve active reservations for a customer.
        """

        statement: Select = (
            select(
                ParkingReservation,
            )
            .where(
                ParkingReservation.customer_id == customer_id,
                ParkingReservation.status.in_(
                    (
                        ReservationStatus.CREATED,
                        ReservationStatus.CONFIRMED,
                    )
                ),
            )
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
    # Parking Bay Queries
    # ==========================================================

    async def get_by_parking_bay(
        self,
        parking_bay_id: int,
    ) -> list[ParkingReservation]:
        """
        Retrieve all reservations for a parking bay.
        """

        statement: Select = (
            select(
                ParkingReservation,
            )
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

        return list(
            result.scalars().all()
        )

    async def get_active_by_parking_bay(
        self,
        parking_bay_id: int,
    ) -> list[ParkingReservation]:
        """
        Retrieve active reservations for a parking bay.
        """

        statement: Select = (
            select(
                ParkingReservation,
            )
            .where(
                ParkingReservation.parking_bay_id
                == parking_bay_id,
                ParkingReservation.status.in_(
                    (
                        ReservationStatus.CREATED,
                        ReservationStatus.CONFIRMED,
                    )
                ),
            )
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
        Find reservations that overlap the supplied
        reservation period for the same parking bay.

        Overlap Rule
        ------------

        Existing: |--------|

        New:          |--------|

        OR

        Existing:     |--------|

        New:      |--------------|

        Only active reservations participate in
        conflict detection.
        """

        statement = (
            select(
                ParkingReservation,
            )
            .where(
                ParkingReservation.parking_bay_id
                == parking_bay_id,
                ParkingReservation.status.in_(
                    (
                        ReservationStatus.CREATED,
                        ReservationStatus.CONFIRMED,
                    )
                ),
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
        Find the active reservation occupying a bay
        at the supplied point in time.
        """

        statement = (
            select(
                ParkingReservation,
            )
            .where(
                ParkingReservation.parking_bay_id
                == parking_bay_id,
                ParkingReservation.status.in_(
                    (
                        ReservationStatus.CREATED,
                        ReservationStatus.CONFIRMED,
                    )
                ),
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
        Retrieve reservations that have expired but
        have not yet been marked as EXPIRED.
        """

        statement = (
            select(
                ParkingReservation,
            )
            .where(
                ParkingReservation.status.in_(
                    (
                        ReservationStatus.CREATED,
                        ReservationStatus.CONFIRMED,
                    )
                ),
                ParkingReservation.expires_at.is_not(None),
                ParkingReservation.expires_at < as_of,
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
        Retrieve all active reservations.
        """

        statement = (
            select(
                ParkingReservation,
            )
            .where(
                ParkingReservation.status.in_(
                    (
                        ReservationStatus.CREATED,
                        ReservationStatus.CONFIRMED,
                    )
                ),
            )
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
        Count active reservations.

        Active reservations are those currently in either
        CREATED or CONFIRMED status.
        """

        statement = (
            select(
                ParkingReservation,
            )
            .where(
                ParkingReservation.status.in_(
                    (
                        ReservationStatus.CREATED,
                        ReservationStatus.CONFIRMED,
                    )
                )
            )
        )

        result = await self.db.execute(
            statement,
        )

        return len(
            result.scalars().all()
        )

    async def count_customer_reservations(
        self,
        customer_id: int,
    ) -> int:
        """
        Count reservations belonging to a customer.
        """

        statement = (
            select(
                ParkingReservation,
            )
            .where(
                ParkingReservation.customer_id
                == customer_id,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return len(
            result.scalars().all()
        )

    # ==========================================================
    # Convenience Methods
    # ==========================================================

    async def reservation_exists(
        self,
        reservation_number: str,
    ) -> bool:
        """
        Determine whether a reservation number already
        exists.
        """

        reservation = await self.get_by_reservation_number(
            reservation_number,
        )

        return reservation is not None

    async def has_conflicts(
        self,
        parking_bay_id: int,
        reserved_from: datetime,
        reserved_until: datetime,
        exclude_reservation_id: int | None = None,
    ) -> bool:
        """
        Determine whether the supplied reservation
        conflicts with any existing reservation.
        """

        conflicts = await self.find_conflicting_reservations(
            parking_bay_id=parking_bay_id,
            reserved_from=reserved_from,
            reserved_until=reserved_until,
            exclude_reservation_id=exclude_reservation_id,
        )

        return len(conflicts) > 0

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(
        self,
    ) -> str:
        """
        Developer-friendly representation.
        """

        return (
            f"{self.__class__.__name__}"
            f"(model={self.model.__name__})"
        )