"""
RFID Tag Service.

Contains business logic for RFID tag management.

The RFID access chain is:

    RFID Tag
        ↓
    Vehicle
        ↓
    Customer / Owner

The service is responsible for:
- RFID UID normalization
- RFID tag registration
- Duplicate UID prevention
- RFID-to-vehicle assignment
- RFID unassignment
- RFID activation/deactivation
- RFID resolution for parking access

Persistence and database access are delegated to
RFIDTagRepository and VehicleRepository.
"""

from __future__ import annotations

from app.models.rfid_tag import RFIDTag
from app.models.vehicle import Vehicle
from app.repositories.rfid_tag_repository import RFIDTagRepository
from app.repositories.vehicle_repository import VehicleRepository


# ==========================================================
# RFID Tag Service
# ==========================================================

class RFIDTagService:
    """
    Business logic for RFID Tag Management.
    """

    def __init__(
        self,
        repository: RFIDTagRepository,
        vehicle_repository: VehicleRepository,
    ) -> None:
        self.repository = repository
        self.vehicle_repository = vehicle_repository

    # ======================================================
    # Register RFID Tag
    # ======================================================

    async def create_rfid_tag(
        self,
        *,
        uid: str,
    ) -> RFIDTag:
        """
        Register a new RFID tag.

        The UID is normalized before persistence.
        """

        #
        # Normalize UID.
        #
        normalized_uid = uid.strip().upper()

        #
        # Validate UID.
        #
        if not normalized_uid:
            raise ValueError(
                "RFID UID is required."
            )

        #
        # Prevent duplicate RFID UIDs.
        #
        exists = await self.repository.uid_exists(
            normalized_uid,
        )

        if exists:
            raise ValueError(
                "An RFID tag with this UID already exists."
            )

        #
        # Create RFID tag.
        #
        rfid_tag = RFIDTag(
            uid=normalized_uid,
            vehicle_id=None,
            is_active=True,
        )

        #
        # Persist.
        #
        await self.repository.save(
            rfid_tag,
        )

        await self.repository.commit()

        await self.repository.refresh(
            rfid_tag,
        )

        return rfid_tag

    # ======================================================
    # Get RFID Tag
    # ======================================================

    async def get_rfid_tag(
        self,
        rfid_tag_id: int,
    ) -> RFIDTag:
        """
        Retrieve an RFID tag by ID.
        """

        rfid_tag = await self.repository.get_by_id(
            rfid_tag_id,
        )

        if rfid_tag is None:
            raise ValueError(
                "RFID tag not found."
            )

        return rfid_tag

    # ======================================================
    # Get By UID
    # ======================================================

    async def get_by_uid(
        self,
        uid: str,
    ) -> RFIDTag:
        """
        Retrieve an RFID tag using its UID.

        UID matching is case-insensitive and ignores
        leading/trailing whitespace.
        """

        normalized_uid = uid.strip().upper()

        if not normalized_uid:
            raise ValueError(
                "RFID UID is required."
            )

        rfid_tag = await self.repository.get_by_uid(
            normalized_uid,
        )

        if rfid_tag is None:
            raise ValueError(
                "RFID tag not found."
            )

        return rfid_tag

    # ======================================================
    # Get All RFID Tags
    # ======================================================

    async def get_all_rfid_tags(
        self,
    ) -> list[RFIDTag]:
        """
        Retrieve all registered RFID tags.
        """

        return await self.repository.get_all()

    # ======================================================
    # Get Active RFID Tags
    # ======================================================

    async def get_active_rfid_tags(
        self,
    ) -> list[RFIDTag]:
        """
        Retrieve all active RFID tags.
        """

        return await self.repository.get_all_active()

    # ======================================================
    # Get Unassigned RFID Tags
    # ======================================================

    async def get_unassigned_rfid_tags(
        self,
    ) -> list[RFIDTag]:
        """
        Retrieve RFID tags that are not assigned to a vehicle.
        """

        return await self.repository.get_unassigned()

    # ======================================================
    # Assign RFID Tag To Vehicle
    # ======================================================

    async def assign_rfid_tag(
        self,
        *,
        rfid_tag_id: int,
        vehicle_id: int,
    ) -> RFIDTag:
        """
        Assign an RFID tag to a registered vehicle.
        """

        #
        # Retrieve RFID tag.
        #
        rfid_tag = await self.get_rfid_tag(
            rfid_tag_id,
        )

        #
        # Inactive RFID tags cannot be assigned.
        #
        if not rfid_tag.is_active:
            raise ValueError(
                "Inactive RFID tags cannot be assigned."
            )

        #
        # Retrieve vehicle.
        #
        vehicle = await self.vehicle_repository.get_by_id(
            vehicle_id,
        )

        if vehicle is None:
            raise ValueError(
                "Vehicle not found."
            )

        #
        # Inactive vehicles cannot receive RFID access.
        #
        if not vehicle.is_active:
            raise ValueError(
                "Inactive vehicles cannot be assigned an RFID tag."
            )

        #
        # Prevent assigning a different RFID tag to a vehicle
        # that already has one.
        #
        existing_assignment = (
            await self.repository.get_by_vehicle_id(
                vehicle_id,
            )
        )

        if (
            existing_assignment is not None
            and existing_assignment.id != rfid_tag.id
        ):
            raise ValueError(
                "This vehicle is already assigned to another RFID tag."
            )

        #
        # Already assigned to this vehicle.
        #
        if rfid_tag.vehicle_id == vehicle_id:
            return rfid_tag

        #
        # Prevent silently moving an RFID tag that is already
        # assigned to another vehicle.
        #
        if rfid_tag.vehicle_id is not None:
            raise ValueError(
                "This RFID tag is already assigned to another vehicle."
            )

        #
        # Assign RFID tag.
        #
        rfid_tag.vehicle_id = vehicle_id

        await self.repository.save(
            rfid_tag,
        )

        await self.repository.commit()

        await self.repository.refresh(
            rfid_tag,
        )

        return rfid_tag

    # ======================================================
    # Assign RFID Tag To Vehicle By UID
    # ======================================================

    async def assign_rfid_tag_by_uid(
        self,
        *,
        uid: str,
        vehicle_id: int,
    ) -> RFIDTag:
        """
        Assign an RFID tag identified by UID to a vehicle.
        """

        normalized_uid = uid.strip().upper()

        if not normalized_uid:
            raise ValueError(
                "RFID UID is required."
            )

        rfid_tag = await self.repository.get_by_uid(
            normalized_uid,
        )

        if rfid_tag is None:
            raise ValueError(
                "RFID tag not found."
            )

        return await self.assign_rfid_tag(
            rfid_tag_id=rfid_tag.id,
            vehicle_id=vehicle_id,
        )

    # ======================================================
    # Unassign RFID Tag
    # ======================================================

    async def unassign_rfid_tag(
        self,
        *,
        rfid_tag_id: int,
    ) -> RFIDTag:
        """
        Remove the vehicle assignment from an RFID tag.

        The RFID tag itself is retained in the registry.
        """

        rfid_tag = await self.get_rfid_tag(
            rfid_tag_id,
        )

        #
        # Already unassigned.
        #
        if rfid_tag.vehicle_id is None:
            return rfid_tag

        #
        # Remove vehicle assignment.
        #
        rfid_tag.vehicle_id = None

        await self.repository.save(
            rfid_tag,
        )

        await self.repository.commit()

        await self.repository.refresh(
            rfid_tag,
        )

        return rfid_tag

    # ======================================================
    # Deactivate RFID Tag
    # ======================================================

    async def deactivate_rfid_tag(
        self,
        *,
        rfid_tag_id: int,
    ) -> RFIDTag:
        """
        Deactivate an RFID tag.

        The tag remains registered for historical and
        administrative purposes.
        """

        rfid_tag = await self.get_rfid_tag(
            rfid_tag_id,
        )

        #
        # Already inactive.
        #
        if not rfid_tag.is_active:
            return rfid_tag

        #
        # Deactivate.
        #
        rfid_tag.is_active = False

        await self.repository.save(
            rfid_tag,
        )

        await self.repository.commit()

        await self.repository.refresh(
            rfid_tag,
        )

        return rfid_tag

    # ======================================================
    # Activate RFID Tag
    # ======================================================

    async def activate_rfid_tag(
        self,
        *,
        rfid_tag_id: int,
    ) -> RFIDTag:
        """
        Activate a previously deactivated RFID tag.
        """

        rfid_tag = await self.get_rfid_tag(
            rfid_tag_id,
        )

        #
        # Already active.
        #
        if rfid_tag.is_active:
            return rfid_tag

        #
        # Activate.
        #
        rfid_tag.is_active = True

        await self.repository.save(
            rfid_tag,
        )

        await self.repository.commit()

        await self.repository.refresh(
            rfid_tag,
        )

        return rfid_tag

    # ======================================================
    # Resolve RFID Tag
    # ======================================================

    async def resolve_rfid_tag(
        self,
        *,
        uid: str,
    ) -> tuple[RFIDTag, Vehicle]:
        """
        Resolve an RFID UID into an active assigned vehicle.

        Access flow:

            UID
             ↓
            RFIDTag
             ↓
            Vehicle
             ↓
            Customer / Owner

        Only active RFID tags assigned to active vehicles
        are eligible for access.

        The returned Vehicle contains the customer_id that
        identifies the registered owner.
        """

        normalized_uid = uid.strip().upper()

        if not normalized_uid:
            raise ValueError(
                "RFID UID is required."
            )

        #
        # Retrieve active RFID tag.
        #
        rfid_tag = await self.repository.get_active_by_uid(
            normalized_uid,
        )

        if rfid_tag is None:
            raise ValueError(
                "RFID tag not found or inactive."
            )

        #
        # RFID must be assigned to a vehicle.
        #
        if rfid_tag.vehicle_id is None:
            raise ValueError(
                "RFID tag is not assigned to a vehicle."
            )

        #
        # Retrieve assigned vehicle.
        #
        vehicle = await self.vehicle_repository.get_by_id(
            rfid_tag.vehicle_id,
        )

        if vehicle is None:
            raise ValueError(
                "The vehicle assigned to this RFID tag was not found."
            )

        #
        # Inactive vehicles cannot grant parking access.
        #
        if not vehicle.is_active:
            raise ValueError(
                "The vehicle assigned to this RFID tag is inactive."
            )

        return rfid_tag, vehicle

    # ======================================================
    # Get RFID Tag By Vehicle
    # ======================================================

    async def get_by_vehicle_id(
        self,
        *,
        vehicle_id: int,
    ) -> RFIDTag | None:
        """
        Retrieve the RFID tag assigned to a vehicle.
        """

        return await self.repository.get_by_vehicle_id(
            vehicle_id,
        )