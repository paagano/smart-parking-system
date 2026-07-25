from typing import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.parking_facility import ParkingFacility
from app.schemas.parking_facility import (
    ParkingFacilityCreate,
    ParkingFacilityUpdate,
)


class ParkingFacilityRepository:
    """
    Repository responsible for all Parking Facility database operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==========================================================
    # Create
    # ==========================================================

    async def create(
        self,
        facility: ParkingFacilityCreate,
    ) -> ParkingFacility:
        """
        Create a new parking facility.
        """

        db_facility = ParkingFacility(**facility.model_dump())

        self.db.add(db_facility)

        await self.db.commit()

        await self.db.refresh(db_facility)

        return db_facility

    # ==========================================================
    # Read
    # ==========================================================

    async def get_by_id(
        self,
        facility_id: int,
    ) -> ParkingFacility | None:
        """
        Retrieve a parking facility by its ID.
        """

        result = await self.db.execute(
            select(ParkingFacility).where(
                ParkingFacility.id == facility_id
            )
        )

        return result.scalar_one_or_none()

    async def get_by_code(
        self,
        code: str,
    ) -> ParkingFacility | None:
        """
        Retrieve a parking facility by its unique code.
        """

        result = await self.db.execute(
            select(ParkingFacility).where(
                ParkingFacility.code == code.upper()
            )
        )

        return result.scalar_one_or_none()

    async def get_by_name(
        self,
        name: str,
    ) -> ParkingFacility | None:
        """
        Retrieve a parking facility by its name.
        """

        result = await self.db.execute(
            select(ParkingFacility).where(
                func.lower(ParkingFacility.name)
                == name.strip().lower()
            )
        )

        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingFacility]:
        """
        Retrieve all parking facilities.
        """

        result = await self.db.execute(
            select(ParkingFacility)
            .order_by(ParkingFacility.name)
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    async def list_active(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingFacility]:
        """
        Retrieve active parking facilities.
        """

        result = await self.db.execute(
            select(ParkingFacility)
            .where(ParkingFacility.is_active.is_(True))
            .order_by(ParkingFacility.name)
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    async def search(
        self,
        query: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingFacility]:
        """
        Search parking facilities by name, code, city, or county.
        """

        search = f"%{query.strip()}%"

        result = await self.db.execute(
            select(ParkingFacility)
            .where(
                or_(
                    ParkingFacility.name.ilike(search),
                    ParkingFacility.code.ilike(search),
                    ParkingFacility.city.ilike(search),
                    ParkingFacility.county.ilike(search),
                )
            )
            .order_by(ParkingFacility.name)
            .offset(skip)
            .limit(limit)
        )

        return result.scalars().all()

    async def count(self) -> int:
        """
        Count all parking facilities.
        """

        result = await self.db.execute(
            select(func.count(ParkingFacility.id))
        )

        return result.scalar_one()

    async def exists_by_code(
        self,
        code: str,
    ) -> bool:
        """
        Check whether a facility code already exists.
        """

        return await self.get_by_code(code) is not None

    async def exists_by_name(
        self,
        name: str,
    ) -> bool:
        """
        Check whether a facility name already exists.
        """

        return await self.get_by_name(name) is not None

    # ==========================================================
    # Update
    # ==========================================================

    async def update(
        self,
        facility: ParkingFacility,
        updates: ParkingFacilityUpdate,
    ) -> ParkingFacility:
        """
        Update an existing parking facility.
        """

        update_data = updates.model_dump(exclude_unset=True)

        for field, value in update_data.items():
            setattr(facility, field, value)

        await self.db.commit()

        await self.db.refresh(facility)

        return facility

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete(
        self,
        facility: ParkingFacility,
    ) -> None:
        """
        Delete a parking facility.
        """

        await self.db.delete(facility)

        await self.db.commit()