"""
RFID Tag Repository.

Provides persistence-only data access operations for RFIDTag.

Business logic belongs in RFIDTagService.
Transaction management is handled by the Service layer.
"""

from __future__ import annotations

from sqlalchemy import (
    select,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rfid_tag import RFIDTag

from app.repositories.base_repository import BaseRepository


# ==========================================================
# RFID Tag Repository
# ==========================================================

class RFIDTagRepository(
    BaseRepository[RFIDTag],
):
    """
    Repository for RFIDTag persistence operations.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        """
        Initialize RFIDTagRepository.
        """

        super().__init__(
            db=db,
            model=RFIDTag,
        )

    # ======================================================
    # RFID Tag Lookups
    # ======================================================

    async def get_by_uid(
        self,
        uid: str,
    ) -> RFIDTag | None:
        """
        Retrieve an RFID tag by UID.

        UID matching is case-insensitive and
        whitespace-insensitive.
        """

        normalized_uid = uid.strip().upper()

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.uid
                == normalized_uid,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ======================================================
    # Vehicle Assignment
    # ======================================================

    async def get_by_vehicle_id(
        self,
        vehicle_id: int,
    ) -> RFIDTag | None:
        """
        Retrieve the RFID tag assigned to a vehicle.
        """

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.vehicle_id
                == vehicle_id,
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ======================================================
    # Active RFID Tag
    # ======================================================

    async def get_active_by_uid(
        self,
        uid: str,
    ) -> RFIDTag | None:
        """
        Retrieve an active RFID tag by UID.

        Returns None when the tag does not exist
        or is inactive.
        """

        normalized_uid = uid.strip().upper()

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.uid
                == normalized_uid,
                self.model.is_active
                == True,  # noqa: E712
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ======================================================
    # Assigned RFID Tags
    # ======================================================

    async def get_assigned_by_uid(
        self,
        uid: str,
    ) -> RFIDTag | None:
        """
        Retrieve an RFID tag by UID only when it is assigned
        to a vehicle.
        """

        normalized_uid = uid.strip().upper()

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.uid
                == normalized_uid,
                self.model.vehicle_id
                .is_not(None),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ======================================================
    # RFID Tag Listing
    # ======================================================

    async def get_all(
        self,
    ) -> list[RFIDTag]:
        """
        Retrieve all registered RFID tags.
        """

        statement = (
            select(
                self.model,
            )
            .order_by(
                self.model.created_at.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    # ======================================================
    # Active RFID Tags
    # ======================================================

    async def get_all_active(
        self,
    ) -> list[RFIDTag]:
        """
        Retrieve all active RFID tags.
        """

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.is_active
                == True,  # noqa: E712
            )
            .order_by(
                self.model.created_at.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    # ======================================================
    # Unassigned RFID Tags
    # ======================================================

    async def get_unassigned(
        self,
    ) -> list[RFIDTag]:
        """
        Retrieve RFID tags that are not currently assigned
        to a vehicle.
        """

        statement = (
            select(
                self.model,
            )
            .where(
                self.model.vehicle_id
                .is_(None),
            )
            .order_by(
                self.model.created_at.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    # ======================================================
    # UID Existence Check
    # ======================================================

    async def uid_exists(
        self,
        uid: str,
        exclude_rfid_tag_id: int | None = None,
    ) -> bool:
        """
        Determine whether an RFID UID already exists.

        Matching is case-insensitive and
        whitespace-insensitive.
        """

        normalized_uid = uid.strip().upper()

        query = select(
            self.model.id,
        ).where(
            self.model.uid
            == normalized_uid,
        )

        if exclude_rfid_tag_id is not None:
            query = query.where(
                self.model.id
                != exclude_rfid_tag_id,
            )

        result = await self.db.execute(
            query,
        )

        return result.scalar_one_or_none() is not None

    # ======================================================
    # Vehicle Assignment Check
    # ======================================================

    async def vehicle_assignment_exists(
        self,
        vehicle_id: int,
        exclude_rfid_tag_id: int | None = None,
    ) -> bool:
        """
        Determine whether a vehicle already has an RFID tag
        assigned to it.
        """

        query = select(
            self.model.id,
        ).where(
            self.model.vehicle_id
            == vehicle_id,
        )

        if exclude_rfid_tag_id is not None:
            query = query.where(
                self.model.id
                != exclude_rfid_tag_id,
            )

        result = await self.db.execute(
            query,
        )

        return result.scalar_one_or_none() is not None

    # ======================================================
    # Delete RFID Tag
    # ======================================================

    async def delete(
        self,
        rfid_tag: RFIDTag,
    ) -> None:
        """
        Delete an RFID tag from persistence.

        Transaction management remains the responsibility
        of the Service layer.
        """

        await self.db.delete(
            rfid_tag,
        )