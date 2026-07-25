from typing import Sequence

from app.repositories.parking_facility_repository import (
    ParkingFacilityRepository,
)
from app.schemas.parking_facility import (
    ParkingFacilityCreate,
    ParkingFacilityUpdate,
)
from app.models.parking_facility import ParkingFacility


class ParkingFacilityService:
    """
    Service responsible for Parking Facility business logic.
    """

    def __init__(
        self,
        repository: ParkingFacilityRepository,
    ):
        self.repository = repository

    # ==========================================================
    # Create
    # ==========================================================

    async def create_facility(
        self,
        facility: ParkingFacilityCreate,
    ) -> ParkingFacility:
        """
        Create a new parking facility.
        """

        if await self.repository.exists_by_code(facility.code):
            raise ValueError(
                "A parking facility with this code already exists."
            )

        if await self.repository.exists_by_name(facility.name):
            raise ValueError(
                "A parking facility with this name already exists."
            )

        return await self.repository.create(facility)

    # ==========================================================
    # Read
    # ==========================================================

    async def get_facility(
        self,
        facility_id: int,
    ) -> ParkingFacility:
        """
        Retrieve a parking facility by ID.
        """

        facility = await self.repository.get_by_id(facility_id)

        if facility is None:
            raise ValueError("Parking facility not found.")

        return facility

    async def get_facility_by_code(
        self,
        code: str,
    ) -> ParkingFacility:
        """
        Retrieve a parking facility by its code.
        """

        facility = await self.repository.get_by_code(code)

        if facility is None:
            raise ValueError("Parking facility not found.")

        return facility

    async def list_facilities(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingFacility]:
        """
        Retrieve all parking facilities.
        """

        return await self.repository.list(
            skip=skip,
            limit=limit,
        )

    async def list_active_facilities(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingFacility]:
        """
        Retrieve active parking facilities.
        """

        return await self.repository.list_active(
            skip=skip,
            limit=limit,
        )

    async def search_facilities(
        self,
        query: str,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingFacility]:
        """
        Search parking facilities.
        """

        return await self.repository.search(
            query=query,
            skip=skip,
            limit=limit,
        )

    async def count_facilities(self) -> int:
        """
        Return the total number of parking facilities.
        """

        return await self.repository.count()

    # ==========================================================
    # Update
    # ==========================================================

    async def update_facility(
        self,
        facility_id: int,
        updates: ParkingFacilityUpdate,
    ) -> ParkingFacility:
        """
        Update a parking facility.
        """

        facility = await self.get_facility(facility_id)

        update_data = updates.model_dump(exclude_unset=True)

        # Check code uniqueness
        if "code" in update_data:
            existing = await self.repository.get_by_code(
                update_data["code"]
            )

            if (
                existing is not None
                and existing.id != facility.id
            ):
                raise ValueError(
                    "A parking facility with this code already exists."
                )

        # Check name uniqueness
        if "name" in update_data:
            existing = await self.repository.get_by_name(
                update_data["name"]
            )

            if (
                existing is not None
                and existing.id != facility.id
            ):
                raise ValueError(
                    "A parking facility with this name already exists."
                )

        return await self.repository.update(
            facility,
            updates,
        )

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete_facility(
        self,
        facility_id: int,
    ) -> None:
        """
        Delete a parking facility.
        """

        facility = await self.get_facility(facility_id)

        # Future business rule:
        # Prevent deletion if Parking Levels exist.

        await self.repository.delete(facility)

    # ==========================================================
    # Activation
    # ==========================================================

    async def activate_facility(
        self,
        facility_id: int,
    ) -> ParkingFacility:
        """
        Activate a parking facility.
        """

        facility = await self.get_facility(facility_id)

        if facility.is_active:
            return facility

        update = ParkingFacilityUpdate(
            is_active=True,
        )

        return await self.repository.update(
            facility,
            update,
        )

    async def deactivate_facility(
        self,
        facility_id: int,
    ) -> ParkingFacility:
        """
        Deactivate a parking facility.
        """

        facility = await self.get_facility(facility_id)

        if not facility.is_active:
            return facility

        update = ParkingFacilityUpdate(
            is_active=False,
        )

        return await self.repository.update(
            facility,
            update,
        )