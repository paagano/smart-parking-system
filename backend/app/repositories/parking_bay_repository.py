"""
Repository for Parking Bay database operations.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.parking_bay import ParkingBay


class ParkingBayRepository:
    """
    Repository responsible for Parking Bay database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==========================================================
    # Create
    # ==========================================================

    async def create(
        self,
        parking_bay: ParkingBay,
    ) -> ParkingBay:
        """
        Create a new parking bay.
        """

        self.db.add(parking_bay)

        await self.db.commit()

        await self.db.refresh(parking_bay)

        return parking_bay

    # ==========================================================
    # Read
    # ==========================================================

    async def get_by_id(
        self,
        bay_id: int,
    ) -> ParkingBay | None:
        """
        Retrieve a parking bay by its ID.
        """

        result = await self.db.execute(
            select(ParkingBay).where(
                ParkingBay.id == bay_id
            )
        )

        return result.scalar_one_or_none()

    async def get_by_code(
        self,
        zone_id: int,
        code: str,
    ) -> ParkingBay | None:
        """
        Retrieve a parking bay by code within a zone.
        """

        result = await self.db.execute(
            select(ParkingBay).where(
                ParkingBay.zone_id == zone_id,
                ParkingBay.code == code,
            )
        )

        return result.scalar_one_or_none()

    async def get_by_bay_number(
        self,
        zone_id: int,
        bay_number: str,
    ) -> ParkingBay | None:
        """
        Retrieve a parking bay by bay number within a zone.
        """

        result = await self.db.execute(
            select(ParkingBay).where(
                ParkingBay.zone_id == zone_id,
                ParkingBay.bay_number == bay_number,
            )
        )

        return result.scalar_one_or_none()

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[ParkingBay]]:
        """
        Retrieve a paginated list of parking bays.
        """

        total = await self.db.scalar(
            select(func.count()).select_from(ParkingBay)
        )

        result = await self.db.execute(
            select(ParkingBay)
            .offset(skip)
            .limit(limit)
            .order_by(
                ParkingBay.sort_order,
                ParkingBay.bay_number,
            )
        )

        return total or 0, list(result.scalars().all())

    async def list_by_zone(
        self,
        zone_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[ParkingBay]]:
        """
        Retrieve parking bays for a specific zone.
        """

        total = await self.db.scalar(
            select(func.count())
            .select_from(ParkingBay)
            .where(
                ParkingBay.zone_id == zone_id
            )
        )

        result = await self.db.execute(
            select(ParkingBay)
            .where(
                ParkingBay.zone_id == zone_id
            )
            .order_by(
                ParkingBay.sort_order,
                ParkingBay.bay_number,
            )
            .offset(skip)
            .limit(limit)
        )

        return total or 0, list(result.scalars().all())

    # ==========================================================
    # Update
    # ==========================================================

    async def update(
        self,
        parking_bay: ParkingBay,
    ) -> ParkingBay:
        """
        Persist changes to a parking bay.
        """

        await self.db.commit()

        await self.db.refresh(parking_bay)

        return parking_bay

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete(
        self,
        parking_bay: ParkingBay,
    ) -> None:
        """
        Delete a parking bay.
        """

        await self.db.delete(parking_bay)

        await self.db.commit()

    # ==========================================================
    # Bay Occupancy
    # ==========================================================

    async def mark_occupied(
        self,
        parking_bay: ParkingBay,
    ) -> ParkingBay:
        """
        Mark a parking bay as occupied.

        Currently ParkingBay has no occupancy column,
        so this simply persists the entity.

        This method exists so the service layer has a
        stable API and future occupancy tracking can
        be added without changing business logic.
        """

        return await self.update(
            parking_bay,
        )

    async def mark_available(
        self,
        parking_bay: ParkingBay,
    ) -> ParkingBay:
        """
        Mark a parking bay as available.

        Currently ParkingBay has no occupancy column,
        so this simply persists the entity.

        Future occupancy flags can be added here
        without affecting services.
        """

        return await self.update(
            parking_bay,
        )

    # ==========================================================
    # State
    # ==========================================================

    async def activate(
        self,
        parking_bay: ParkingBay,
    ) -> ParkingBay:
        """
        Activate a parking bay.
        """

        parking_bay.is_active = True

        return await self.update(parking_bay)

    async def deactivate(
        self,
        parking_bay: ParkingBay,
    ) -> ParkingBay:
        """
        Deactivate a parking bay.
        """

        parking_bay.is_active = False

        return await self.update(parking_bay)