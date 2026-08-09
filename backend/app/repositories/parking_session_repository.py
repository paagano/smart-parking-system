"""
Parking Session Repository

Handles all database access for Parking Sessions.

Business rules belong in the Service layer.
This repository is responsible only for persistence.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import SessionStatus
from app.models.parking_session import ParkingSession
from app.repositories.base_repository import BaseRepository


class ParkingSessionRepository(BaseRepository[ParkingSession]):
    """
    Repository for ParkingSession persistence.
    """

    def __init__(
        self,
        db: AsyncSession,
    ):
        super().__init__(
            db=db,
            model=ParkingSession,
        )

    # ==========================================================
    # Get by Primary Key
    # ==========================================================

    async def get_by_id(
        self,
        session_id: int,
    ) -> ParkingSession | None:
        """
        Retrieve a parking session by ID.
        """

        return await super().get_by_id(session_id)

    # ==========================================================
    # Session Number
    # ==========================================================

    async def get_by_session_number(
        self,
        session_number: str,
    ) -> ParkingSession | None:
        """
        Retrieve a parking session using its session number.
        """

        result = await self.db.execute(
            select(ParkingSession).where(
                ParkingSession.session_number == session_number
            )
        )

        return result.scalar_one_or_none()

    # ==========================================================
    # Active Session
    # ==========================================================

    async def get_active_by_registration(
        self,
        registration: str,
    ) -> ParkingSession | None:
        """
        Return the active parking session for the supplied
        vehicle registration.

        If inconsistent data exists, the most recent active
        session is returned.
        """

        result = await self.db.execute(
            select(ParkingSession)
            .where(
                ParkingSession.vehicle_registration == registration,
                ParkingSession.status == SessionStatus.ACTIVE,
            )
            .order_by(
                ParkingSession.entry_time.desc()
            )
        )

        return result.scalars().first()

    async def get_active_session_by_bay(
        self,
        parking_bay_id: int,
    ) -> ParkingSession | None:
        """
        Return the active parking session occupying
        the supplied parking bay.

        If inconsistent data exists, the most recent active
        session is returned.
        """

        result = await self.db.execute(
            select(ParkingSession)
            .where(
                ParkingSession.parking_bay_id == parking_bay_id,
                ParkingSession.status == SessionStatus.ACTIVE,
            )
            .order_by(
                ParkingSession.entry_time.desc()
            )
        )

        return result.scalars().first()

    # ==========================================================
    # Vehicle History
    # ==========================================================

    async def get_by_registration(
        self,
        registration: str,
    ) -> list[ParkingSession]:
        """
        Return every parking session for a vehicle.
        """

        result = await self.db.execute(
            select(ParkingSession)
            .where(
                ParkingSession.vehicle_registration == registration
            )
            .order_by(
                ParkingSession.entry_time.desc()
            )
        )

        return list(result.scalars().all())

    # ==========================================================
    # Bay Sessions
    # ==========================================================

    async def get_by_bay(
        self,
        parking_bay_id: int,
    ) -> list[ParkingSession]:
        """
        Return every parking session for a parking bay.
        """

        result = await self.db.execute(
            select(ParkingSession)
            .where(
                ParkingSession.parking_bay_id == parking_bay_id
            )
            .order_by(
                ParkingSession.entry_time.desc()
            )
        )

        return list(result.scalars().all())

    # ==========================================================
    # Active Sessions
    # ==========================================================

    async def get_active_sessions(
        self,
    ) -> list[ParkingSession]:
        """
        Return all active parking sessions.
        """

        result = await self.db.execute(
            select(ParkingSession)
            .where(
                ParkingSession.status == SessionStatus.ACTIVE
            )
            .order_by(
                ParkingSession.entry_time.asc()
            )
        )

        return list(result.scalars().all())

    # ==========================================================
    # Availability
    # ==========================================================

    async def has_active_session(
        self,
        parking_bay_id: int,
    ) -> bool:
        """
        Determine whether the parking bay currently has
        an active parking session.
        """

        statement = (
            select(ParkingSession.id)
            .where(
                ParkingSession.parking_bay_id == parking_bay_id,
                ParkingSession.status == SessionStatus.ACTIVE,
            )
            .limit(1)
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none() is not None

    # ==========================================================
    # Completed Sessions
    # ==========================================================

    async def get_completed_sessions(
        self,
    ) -> list[ParkingSession]:
        """
        Return all completed parking sessions.
        """

        result = await self.db.execute(
            select(ParkingSession)
            .where(
                ParkingSession.status == SessionStatus.COMPLETED
            )
            .order_by(
                ParkingSession.exit_time.desc()
            )
        )

        return list(result.scalars().all())

    # ==========================================================
    # Search
    # ==========================================================

    async def search_registration(
        self,
        registration: str,
    ) -> list[ParkingSession]:
        """
        Search parking sessions using a partial
        vehicle registration.
        """

        result = await self.db.execute(
            select(ParkingSession)
            .where(
                ParkingSession.vehicle_registration.ilike(
                    f"%{registration}%"
                )
            )
            .order_by(
                ParkingSession.entry_time.desc()
            )
        )

        return list(result.scalars().all())

    # ==========================================================
    # Exists
    # ==========================================================

    async def active_session_exists(
        self,
        registration: str,
    ) -> bool:
        """
        Return True if the supplied vehicle currently
        has an active parking session.
        """

        return (
            await self.get_active_by_registration(
                registration
            )
            is not None
        )

    async def active_bay_session_exists(
        self,
        parking_bay_id: int,
    ) -> bool:
        """
        Return True if the supplied parking bay
        currently has an active parking session.
        """

        return (
            await self.get_active_session_by_bay(
                parking_bay_id
            )
            is not None
        )

    # ==========================================================
    # Persistence
    # ==========================================================

    async def save(
        self,
        parking_session: ParkingSession,
    ) -> ParkingSession:
        """
        Persist a parking session.

        The repository flushes changes so generated values
        and database state are available immediately.

        Commit is handled by the Service layer.
        """

        self.db.add(parking_session)

        await self.db.flush()
        await self.db.refresh(parking_session)

        return parking_session

    async def remove(
        self,
        parking_session: ParkingSession,
    ) -> None:
        """
        Delete a parking session.

        Commit is handled by the Service layer.
        """

        await self.db.delete(parking_session)
        await self.db.flush()