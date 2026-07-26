from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.parking_zone import ParkingZone
from app.schemas.parking_zone import (
    ParkingZoneCreate,
    ParkingZoneUpdate,
)


class ParkingZoneRepository:
    """
    Repository responsible for all Parking Zone database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==========================================================
    # Create
    # ==========================================================

    async def create(
        self,
        zone: ParkingZoneCreate,
    ) -> ParkingZone:
        """
        Create a new parking zone.
        """

        db_zone = ParkingZone(**zone.model_dump())

        self.db.add(db_zone)

        await self.db.commit()

        await self.db.refresh(db_zone)

        return db_zone

    # ==========================================================
    # Read
    # ==========================================================

    async def get_by_id(
        self,
        zone_id: int,
    ) -> ParkingZone | None:
        """
        Retrieve a parking zone by ID.
        """

        result = await self.db.execute(
            select(ParkingZone).where(
                ParkingZone.id == zone_id
            )
        )

        return result.scalar_one_or_none()

    async def get_by_code(
        self,
        facility_id: int,
        code: str,
    ) -> ParkingZone | None:
        """
        Retrieve a parking zone by code within a facility.
        """

        result = await self.db.execute(
            select(ParkingZone).where(
                ParkingZone.facility_id == facility_id,
                ParkingZone.code == code.strip().upper(),
            )
        )

        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        facility_id: int,
        name: str,
    ) -> ParkingZone | None:
        """
        Retrieve a parking zone by name within a facility.
        """

        result = await self.db.execute(
            select(ParkingZone).where(
                ParkingZone.facility_id == facility_id,
                func.lower(ParkingZone.name)
                == name.strip().lower(),
            )
        )

        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingZone]:
        """
        Retrieve all parking zones.
        """

        result = await self.db.execute(
            select(ParkingZone)
            .order_by(
                ParkingZone.sort_order,
                ParkingZone.name,
            )
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    async def list_by_facility(
        self,
        facility_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingZone]:
        """
        Retrieve all parking zones for a facility.
        """

        result = await self.db.execute(
            select(ParkingZone)
            .where(
                ParkingZone.facility_id == facility_id
            )
            .order_by(
                ParkingZone.sort_order,
                ParkingZone.name,
            )
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    async def list_active(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingZone]:
        """
        Retrieve active parking zones.
        """

        result = await self.db.execute(
            select(ParkingZone)
            .where(
                ParkingZone.is_active.is_(True)
            )
            .order_by(
                ParkingZone.sort_order,
                ParkingZone.name,
            )
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    async def get_root_zones(
        self,
        facility_id: int,
    ) -> Sequence[ParkingZone]:
        """
        Retrieve all root-level zones for a facility.
        """

        result = await self.db.execute(
            select(ParkingZone)
            .where(
                ParkingZone.facility_id == facility_id,
                ParkingZone.parent_zone_id.is_(None),
            )
            .order_by(
                ParkingZone.sort_order,
                ParkingZone.name,
            )
        )

        return result.scalars().all()

    async def get_children(
        self,
        parent_zone_id: int,
    ) -> Sequence[ParkingZone]:
        """
        Retrieve direct child zones.
        """

        result = await self.db.execute(
            select(ParkingZone)
            .where(
                ParkingZone.parent_zone_id == parent_zone_id
            )
            .order_by(
                ParkingZone.sort_order,
                ParkingZone.name,
            )
        )

        return result.scalars().all()

    async def count(self) -> int:
        """
        Count all parking zones.
        """

        result = await self.db.execute(
            select(func.count(ParkingZone.id))
        )

        return result.scalar_one()

    async def count_by_facility(
        self,
        facility_id: int,
    ) -> int:
        """
        Count parking zones belonging to a facility.
        """

        result = await self.db.execute(
            select(func.count(ParkingZone.id)).where(
                ParkingZone.facility_id == facility_id
            )
        )

        return result.scalar_one()

    async def exists_by_code(
        self,
        facility_id: int,
        code: str,
    ) -> bool:
        """
        Check whether a zone code already exists within a facility.
        """

        return (
            await self.get_by_code(
                facility_id,
                code,
            )
            is not None
        )

    async def exists_by_name(
        self,
        facility_id: int,
        name: str,
    ) -> bool:
        """
        Check whether a zone name already exists within a facility.
        """

        return (
            await self.get_by_name(
                facility_id,
                name,
            )
            is not None
        )

    # ==========================================================
    # Update
    # ==========================================================

    async def update(
        self,
        zone: ParkingZone,
        updates: ParkingZoneUpdate,
    ) -> ParkingZone:
        """
        Update an existing parking zone.
        """

        update_data = updates.model_dump(
            exclude_unset=True
        )

        for field, value in update_data.items():
            setattr(zone, field, value)

        await self.db.commit()

        await self.db.refresh(zone)

        return zone

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete(
        self,
        zone: ParkingZone,
    ) -> None:
        """
        Delete a parking zone.
        """

        await self.db.delete(zone)

        await self.db.commit()