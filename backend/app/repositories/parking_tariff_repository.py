"""
Parking Tariff Repository

Handles all database access for Parking Tariffs.

Business rules belong in the Service layer.
This repository is responsible only for persistence.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    BillingType,
    VehicleType,
)
from app.models.parking_tariff import (
    ParkingTariff,
)
from app.repositories.base_repository import (
    BaseRepository,
)


class ParkingTariffRepository(
    BaseRepository[ParkingTariff]
):
    """
    Repository for ParkingTariff persistence.
    """

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        super().__init__(
            db=db,
            model=ParkingTariff,
        )

    # ==========================================================
    # Primary Key
    # ==========================================================

    async def get_by_id(
        self,
        tariff_id: int,
    ) -> ParkingTariff | None:
        """
        Retrieve a parking tariff by ID.
        """

        return await super().get_by_id(
            tariff_id
        )

    # ==========================================================
    # Code
    # ==========================================================

    async def get_by_code(
        self,
        code: str,
    ) -> ParkingTariff | None:
        """
        Retrieve a tariff by its unique code.
        """

        result = await self.db.execute(
            select(ParkingTariff).where(
                ParkingTariff.code == code
            )
        )

        return result.scalar_one_or_none()

    async def code_exists(
        self,
        code: str,
    ) -> bool:
        """
        Determine whether a tariff code already exists.
        """

        return (
            await self.get_by_code(code)
        ) is not None

    # ==========================================================
    # Active Tariffs
    # ==========================================================

    async def get_active_tariffs(
        self,
    ) -> list[ParkingTariff]:
        """
        Retrieve all active parking tariffs.
        """

        result = await self.db.execute(
            select(ParkingTariff)
            .where(
                ParkingTariff.is_active.is_(True)
            )
            .order_by(
                ParkingTariff.pricing_priority.asc(),
                ParkingTariff.display_order.asc(),
                ParkingTariff.name.asc(),
            )
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Vehicle Type
    # ==========================================================

    async def get_by_vehicle_type(
        self,
        vehicle_type: VehicleType,
    ) -> list[ParkingTariff]:
        """
        Retrieve all active tariffs for the supplied
        vehicle type.
        """

        result = await self.db.execute(
            select(ParkingTariff)
            .where(
                ParkingTariff.vehicle_type == vehicle_type,
                ParkingTariff.is_active.is_(True),
            )
            .order_by(
                ParkingTariff.pricing_priority.asc(),
                ParkingTariff.display_order.asc(),
                ParkingTariff.name.asc(),
            )
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Billing Type
    # ==========================================================

    async def get_by_billing_type(
        self,
        billing_type: BillingType,
    ) -> list[ParkingTariff]:
        """
        Retrieve all active tariffs for the supplied
        billing type.
        """

        result = await self.db.execute(
            select(ParkingTariff)
            .where(
                ParkingTariff.billing_type == billing_type,
                ParkingTariff.is_active.is_(True),
            )
            .order_by(
                ParkingTariff.pricing_priority.asc(),
                ParkingTariff.display_order.asc(),
                ParkingTariff.name.asc(),
            )
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
    ) -> list[ParkingTariff]:
        """
        Search parking tariffs by name or code.
        """

        result = await self.db.execute(
            select(ParkingTariff)
            .where(
                ParkingTariff.name.ilike(
                    f"%{search_term}%"
                )
                |
                ParkingTariff.code.ilike(
                    f"%{search_term}%"
                )
            )
            .order_by(
                ParkingTariff.pricing_priority.asc(),
                ParkingTariff.display_order.asc(),
                ParkingTariff.name.asc(),
            )
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Active Lookups
    # ==========================================================

    async def get_active_hourly_tariffs(
        self,
    ) -> list[ParkingTariff]:
        """
        Retrieve all active hourly tariffs.
        """

        result = await self.db.execute(
            select(ParkingTariff)
            .where(
                ParkingTariff.billing_type == BillingType.HOURLY,
                ParkingTariff.is_active.is_(True),
            )
            .order_by(
                ParkingTariff.pricing_priority.asc(),
                ParkingTariff.display_order.asc(),
            )
        )

        return list(
            result.scalars().all()
        )

    async def get_active_daily_tariffs(
        self,
    ) -> list[ParkingTariff]:
        """
        Retrieve all active daily tariffs.
        """

        result = await self.db.execute(
            select(ParkingTariff)
            .where(
                ParkingTariff.billing_type == BillingType.DAILY,
                ParkingTariff.is_active.is_(True),
            )
            .order_by(
                ParkingTariff.pricing_priority.asc(),
                ParkingTariff.display_order.asc(),
            )
        )

        return list(
            result.scalars().all()
        )

    async def get_active_flat_rate_tariffs(
        self,
    ) -> list[ParkingTariff]:
        """
        Retrieve all active flat-rate tariffs.
        """

        result = await self.db.execute(
            select(ParkingTariff)
            .where(
                ParkingTariff.billing_type == BillingType.FLAT,
                ParkingTariff.is_active.is_(True),
            )
            .order_by(
                ParkingTariff.pricing_priority.asc(),
                ParkingTariff.display_order.asc(),
            )
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Applicable Tariff
    # ==========================================================

    async def find_applicable_tariff(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        effective_at: datetime,
    ) -> ParkingTariff | None:
        """
        Retrieve the highest-priority active tariff that is
        effective at the supplied datetime.
        """

        result = await self.db.execute(
            select(ParkingTariff)
            .where(
                ParkingTariff.vehicle_type == vehicle_type,
                ParkingTariff.billing_type == billing_type,
                ParkingTariff.is_active.is_(True),
                ParkingTariff.effective_from <= effective_at,
                (
                    ParkingTariff.effective_to.is_(None)
                    | (
                        ParkingTariff.effective_to >= effective_at
                    )
                ),
            )
            .order_by(
                ParkingTariff.pricing_priority.asc(),
                ParkingTariff.display_order.asc(),
            )
        )

        return result.scalars().first()

    # ==========================================================
    # Overlapping Tariffs
    # ==========================================================

    async def find_overlapping_tariffs(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        effective_from: datetime,
        effective_to: datetime | None,
        exclude_tariff_id: int | None = None,
    ) -> list[ParkingTariff]:
        """
        Retrieve tariffs whose effective periods overlap
        with the supplied effective period.
        """

        query = (
            select(ParkingTariff)
            .where(
                ParkingTariff.vehicle_type == vehicle_type,
                ParkingTariff.billing_type == billing_type,
            )
        )

        if exclude_tariff_id is not None:
            query = query.where(
                ParkingTariff.id != exclude_tariff_id
            )

        result = await self.db.execute(query)

        tariffs = list(result.scalars().all())

        overlapping: list[ParkingTariff] = []

        new_end = effective_to or datetime.max

        for tariff in tariffs:

            existing_end = (
                tariff.effective_to
                or datetime.max
            )

            if (
                tariff.effective_from <= new_end
                and effective_from <= existing_end
            ):
                overlapping.append(
                    tariff
                )

        return overlapping

    # ==========================================================
    # Priority Conflicts
    # ==========================================================

    async def find_priority_conflicts(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        pricing_priority: int,
        exclude_tariff_id: int | None = None,
    ) -> list[ParkingTariff]:
        """
        Retrieve tariffs using the same pricing priority.
        """

        query = (
            select(ParkingTariff)
            .where(
                ParkingTariff.vehicle_type == vehicle_type,
                ParkingTariff.billing_type == billing_type,
                ParkingTariff.pricing_priority == pricing_priority,
            )
        )

        if exclude_tariff_id is not None:
            query = query.where(
                ParkingTariff.id != exclude_tariff_id
            )

        result = await self.db.execute(query)

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Validation Helpers
    # ==========================================================

    async def active_tariff_exists(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        effective_at: datetime,
    ) -> bool:
        """
        Determine whether an applicable active tariff exists.
        """

        return (
            await self.find_applicable_tariff(
                vehicle_type=vehicle_type,
                billing_type=billing_type,
                effective_at=effective_at,
            )
            is not None
        )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(
        self,
    ) -> str:
        """
        String representation.
        """

        return (
            f"{self.__class__.__name__}("
            f"model={self.model.__name__})"
        )