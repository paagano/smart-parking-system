from typing import Sequence

from app.models.parking_zone import ParkingZone
from app.repositories.parking_zone_repository import (
    ParkingZoneRepository,
)
from app.schemas.parking_zone import (
    ParkingZoneCreate,
    ParkingZoneUpdate,
)


class ParkingZoneService:
    """
    Service responsible for Parking Zone business logic.
    """

    def __init__(
        self,
        repository: ParkingZoneRepository,
    ):
        self.repository = repository

    # ==========================================================
    # Create
    # ==========================================================

    async def create_zone(
        self,
        zone: ParkingZoneCreate,
    ) -> ParkingZone:
        """
        Create a new parking zone.
        """

        # ----------------------------------------------
        # Ensure unique code within facility
        # ----------------------------------------------

        if await self.repository.exists_by_code(
            zone.facility_id,
            zone.code,
        ):
            raise ValueError(
                "A parking zone with this code already exists in this facility."
            )

        # ----------------------------------------------
        # Ensure unique name within facility
        # ----------------------------------------------

        if await self.repository.exists_by_name(
            zone.facility_id,
            zone.name,
        ):
            raise ValueError(
                "A parking zone with this name already exists in this facility."
            )

        # ----------------------------------------------
        # Validate parent
        # ----------------------------------------------

        if zone.parent_zone_id is not None:

            parent = await self.get_zone(
                zone.parent_zone_id
            )

            if (
                parent.facility_id
                != zone.facility_id
            ):
                raise ValueError(
                    "Parent zone must belong to the same parking facility."
                )

        return await self.repository.create(zone)

    # ==========================================================
    # Read
    # ==========================================================

    async def get_zone(
        self,
        zone_id: int,
    ) -> ParkingZone:
        """
        Retrieve a parking zone by ID.
        """

        zone = await self.repository.get_by_id(
            zone_id
        )

        if zone is None:
            raise ValueError(
                "Parking zone not found."
            )

        return zone

    async def get_zone_by_code(
        self,
        facility_id: int,
        code: str,
    ) -> ParkingZone:
        """
        Retrieve a parking zone by code.
        """

        zone = await self.repository.get_by_code(
            facility_id,
            code,
        )

        if zone is None:
            raise ValueError(
                "Parking zone not found."
            )

        return zone

    async def list_zones(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingZone]:
        """
        Retrieve all parking zones.
        """

        return await self.repository.list(
            skip=skip,
            limit=limit,
        )

    async def list_active_zones(
        self,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingZone]:
        """
        Retrieve all active parking zones.
        """

        return await self.repository.list_active(
            skip=skip,
            limit=limit,
        )

    async def list_facility_zones(
        self,
        facility_id: int,
        *,
        skip: int = 0,
        limit: int = 100,
    ) -> Sequence[ParkingZone]:
        """
        Retrieve all zones belonging to a facility.
        """

        return await self.repository.list_by_facility(
            facility_id,
            skip=skip,
            limit=limit,
        )

    async def get_root_zones(
        self,
        facility_id: int,
    ) -> Sequence[ParkingZone]:
        """
        Retrieve all root zones for a facility.
        """

        return await self.repository.get_root_zones(
            facility_id
        )

    async def get_children(
        self,
        parent_zone_id: int,
    ) -> Sequence[ParkingZone]:
        """
        Retrieve direct child zones.
        """

        return await self.repository.get_children(
            parent_zone_id
        )

    async def count_zones(self) -> int:
        """
        Count all parking zones.
        """

        return await self.repository.count()

    async def count_facility_zones(
        self,
        facility_id: int,
    ) -> int:
        """
        Count zones belonging to a facility.
        """

        return await self.repository.count_by_facility(
            facility_id
        )
        # ==========================================================
    # Update
    # ==========================================================

    async def update_zone(
        self,
        zone_id: int,
        updates: ParkingZoneUpdate,
    ) -> ParkingZone:
        """
        Update an existing parking zone.
        """

        zone = await self.get_zone(zone_id)

        update_data = updates.model_dump(
            exclude_unset=True
        )

        # ------------------------------------------------------
        # Validate Code Uniqueness
        # ------------------------------------------------------

        if "code" in update_data:

            existing = await self.repository.get_by_code(
                zone.facility_id,
                update_data["code"],
            )

            if (
                existing is not None
                and existing.id != zone.id
            ):
                raise ValueError(
                    "A parking zone with this code already exists in this facility."
                )

        # ------------------------------------------------------
        # Validate Name Uniqueness
        # ------------------------------------------------------

        if "name" in update_data:

            existing = await self.repository.get_by_name(
                zone.facility_id,
                update_data["name"],
            )

            if (
                existing is not None
                and existing.id != zone.id
            ):
                raise ValueError(
                    "A parking zone with this name already exists in this facility."
                )

        # ------------------------------------------------------
        # Validate Parent Zone
        # ------------------------------------------------------

        if "parent_zone_id" in update_data:

            parent_zone_id = update_data["parent_zone_id"]

            # Allow removing the parent (making root)
            if parent_zone_id is not None:

                if parent_zone_id == zone.id:
                    raise ValueError(
                        "A parking zone cannot be its own parent."
                    )

                parent = await self.get_zone(
                    parent_zone_id
                )

                if (
                    parent.facility_id
                    != zone.facility_id
                ):
                    raise ValueError(
                        "Parent zone must belong to the same parking facility."
                    )

                # Prevent circular hierarchy
                if await self._is_descendant(
                    parent.id,
                    zone.id,
                ):
                    raise ValueError(
                        "Circular parking zone hierarchy detected."
                    )

        return await self.repository.update(
            zone,
            updates,
        )

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete_zone(
        self,
        zone_id: int,
    ) -> None:
        """
        Delete a parking zone.
        """

        zone = await self.get_zone(zone_id)

        children = await self.repository.get_children(
            zone.id
        )

        if children:
            raise ValueError(
                "Cannot delete a parking zone that contains child zones."
            )

        # Future business rule:
        # Prevent deletion if parking bays exist.

        await self.repository.delete(
            zone
        )

    # ==========================================================
    # Activation
    # ==========================================================

    async def activate_zone(
        self,
        zone_id: int,
    ) -> ParkingZone:
        """
        Activate a parking zone.
        """

        zone = await self.get_zone(zone_id)

        if zone.is_active:
            return zone

        update = ParkingZoneUpdate(
            is_active=True,
        )

        return await self.repository.update(
            zone,
            update,
        )

    async def deactivate_zone(
        self,
        zone_id: int,
    ) -> ParkingZone:
        """
        Deactivate a parking zone.
        """

        zone = await self.get_zone(zone_id)

        if not zone.is_active:
            return zone

        update = ParkingZoneUpdate(
            is_active=False,
        )

        return await self.repository.update(
            zone,
            update,
        )
        # ==========================================================
    # Hierarchy Validation Helpers
    # ==========================================================

    async def _is_descendant(
        self,
        zone_id: int,
        ancestor_id: int,
    ) -> bool:
        """
        Determine whether the supplied zone is a descendant of
        the given ancestor.

        Used to prevent circular parent relationships.

        Example:

            A
            └── B
                └── C

        _is_descendant(C, A) -> True
        _is_descendant(B, C) -> False
        """

        current = await self.repository.get_by_id(
            zone_id
        )

        while (
            current is not None
            and current.parent_zone_id is not None
        ):

            if current.parent_zone_id == ancestor_id:
                return True

            current = await self.repository.get_by_id(
                current.parent_zone_id
            )

        return False

    async def validate_parent_zone(
        self,
        facility_id: int,
        parent_zone_id: int | None,
    ) -> ParkingZone | None:
        """
        Validate that a parent zone exists and belongs to the
        specified parking facility.

        Returns the parent zone if valid.
        """

        if parent_zone_id is None:
            return None

        parent = await self.get_zone(parent_zone_id)

        if parent.facility_id != facility_id:
            raise ValueError(
                "Parent zone must belong to the same parking facility."
            )

        return parent

    async def has_children(
        self,
        zone_id: int,
    ) -> bool:
        """
        Determine whether a parking zone has child zones.
        """

        children = await self.repository.get_children(
            zone_id
        )

        return len(children) > 0

    async def is_root_zone(
        self,
        zone_id: int,
    ) -> bool:
        """
        Determine whether a zone is a root-level zone.
        """

        zone = await self.get_zone(zone_id)

        return zone.parent_zone_id is None