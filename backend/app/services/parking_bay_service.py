"""
Service layer for Parking Bay business logic.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions.handlers import (
    BadRequestException,
    NotFoundException,
)
from app.models.parking_bay import ParkingBay
from app.repositories.parking_bay_repository import ParkingBayRepository
from app.repositories.parking_zone_repository import ParkingZoneRepository
from app.schemas.parking_bay import (
    ParkingBayCreate,
    ParkingBayUpdate,
)


class ParkingBayService:
    """
    Service responsible for Parking Bay business logic.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self.repository = ParkingBayRepository(db)
        self.zone_repository = ParkingZoneRepository(db)

    # ==========================================================
    # Create
    # ==========================================================

    async def create(
        self,
        payload: ParkingBayCreate,
    ) -> ParkingBay:
        """
        Create a new parking bay.
        """

        zone = await self.zone_repository.get_by_id(
            payload.zone_id
        )

        if not zone:
            raise NotFoundException("Parking zone not found.")

        existing_number = await self.repository.get_by_bay_number(
            payload.zone_id,
            payload.bay_number,
        )

        if existing_number:
            raise BadRequestException(
                "Parking bay number already exists in this zone."
            )

        existing_code = await self.repository.get_by_code(
            payload.zone_id,
            payload.code,
        )

        if existing_code:
            raise BadRequestException(
                "Parking bay code already exists in this zone."
            )

        parking_bay = ParkingBay(
            **payload.model_dump()
        )

        return await self.repository.create(
            parking_bay
        )

    # ==========================================================
    # Read
    # ==========================================================

    async def get_by_id(
        self,
        bay_id: int,
    ) -> ParkingBay:
        """
        Retrieve a parking bay.
        """

        parking_bay = await self.repository.get_by_id(
            bay_id
        )

        if not parking_bay:
            raise NotFoundException(
                "Parking bay not found."
            )

        return parking_bay

    async def list(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[ParkingBay]]:
        """
        List parking bays.
        """

        return await self.repository.list(
            skip,
            limit,
        )

    async def list_by_zone(
        self,
        zone_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[ParkingBay]]:
        """
        List parking bays belonging to a parking zone.
        """

        zone = await self.zone_repository.get_by_id(
            zone_id
        )

        if not zone:
            raise NotFoundException(
                "Parking zone not found."
            )

        return await self.repository.list_by_zone(
            zone_id,
            skip,
            limit,
        )

    # ==========================================================
    # Update
    # ==========================================================

    async def update(
        self,
        bay_id: int,
        payload: ParkingBayUpdate,
    ) -> ParkingBay:
        """
        Update a parking bay.
        """

        parking_bay = await self.get_by_id(
            bay_id
        )

        update_data = payload.model_dump(
            exclude_unset=True
        )

        if "bay_number" in update_data:
            existing = await self.repository.get_by_bay_number(
                parking_bay.zone_id,
                update_data["bay_number"],
            )

            if existing and existing.id != parking_bay.id:
                raise BadRequestException(
                    "Parking bay number already exists in this zone."
                )

        if "code" in update_data:
            existing = await self.repository.get_by_code(
                parking_bay.zone_id,
                update_data["code"],
            )

            if existing and existing.id != parking_bay.id:
                raise BadRequestException(
                    "Parking bay code already exists in this zone."
                )

        for field, value in update_data.items():
            setattr(
                parking_bay,
                field,
                value,
            )

        return await self.repository.update(
            parking_bay
        )

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete(
        self,
        bay_id: int,
    ) -> None:
        """
        Delete a parking bay.
        """

        parking_bay = await self.get_by_id(
            bay_id
        )

        await self.repository.delete(
            parking_bay
        )

    # ==========================================================
    # State
    # ==========================================================

    async def activate(
        self,
        bay_id: int,
    ) -> ParkingBay:
        """
        Activate a parking bay.
        """

        parking_bay = await self.get_by_id(
            bay_id
        )

        return await self.repository.activate(
            parking_bay
        )

    async def deactivate(
        self,
        bay_id: int,
    ) -> ParkingBay:
        """
        Deactivate a parking bay.
        """

        parking_bay = await self.get_by_id(
            bay_id
        )

        return await self.repository.deactivate(
            parking_bay
        )