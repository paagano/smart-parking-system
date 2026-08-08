"""
Vehicle Repository.

Provides persistence-only data access operations for Vehicle.

Business logic belongs in VehicleService.
Transaction management is handled by the Service layer.
"""

from __future__ import annotations

from sqlalchemy import (
    func,
    select,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vehicle import Vehicle

from app.repositories.base_repository import BaseRepository


# ==========================================================
# Vehicle Repository
# ==========================================================

class VehicleRepository(
    BaseRepository[Vehicle],
):
    """
    Repository for Vehicle persistence operations.
    """

    def __init__(
        self,
        db: AsyncSession,
    ) -> None:
        """
        Initialize VehicleRepository.
        """

        super().__init__(
            db=db,
            model=Vehicle,
        )

    # ======================================================
    # Vehicle Lookups
    # ======================================================

    async def get_by_registration_number(
        self,
        registration_number: str,
    ) -> Vehicle | None:
        """
        Retrieve a vehicle by registration number.

        Matching is:
        - Case-insensitive
        - Whitespace-insensitive

        Examples:
            KCJ 980Y
            KCJ980Y
            kcj 980y

        all resolve to the same vehicle.
        """

        normalized_registration = "".join(
            registration_number.split()
        ).upper()

        result = await self.db.execute(
            select(self.model).where(
                func.replace(
                    func.upper(
                        self.model.registration_number,
                    ),
                    " ",
                    "",
                )
                == normalized_registration
            )
        )

        return result.scalar_one_or_none()

    # ======================================================
    # Customer Vehicles
    # ======================================================

    async def get_by_customer_id(
        self,
        customer_id: int,
    ) -> list[Vehicle]:
        """
        Retrieve all vehicles belonging to a customer.
        """

        statement = (
            select(
                Vehicle,
            )
            .where(
                Vehicle.customer_id
                == customer_id,
            )
            .order_by(
                Vehicle.is_default.desc(),
                Vehicle.created_at.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    # ======================================================
    # Default Vehicle
    # ======================================================

    async def get_default_vehicle(
        self,
        customer_id: int,
    ) -> Vehicle | None:
        """
        Retrieve the customer's default vehicle.

        Returns
        -------
        Vehicle | None
            The customer's default vehicle, if one exists.
        """

        statement = (
            select(
                Vehicle,
            )
            .where(
                Vehicle.customer_id
                == customer_id,
                Vehicle.is_default
                == True,  # noqa: E712
                Vehicle.is_active
                == True,  # noqa: E712
            )
        )

        result = await self.db.execute(
            statement,
        )

        return result.scalar_one_or_none()

    # ======================================================
    # Active Vehicles
    # ======================================================

    async def get_active_by_customer_id(
        self,
        customer_id: int,
    ) -> list[Vehicle]:
        """
        Retrieve all active vehicles belonging to a customer.
        """

        statement = (
            select(
                Vehicle,
            )
            .where(
                Vehicle.customer_id
                == customer_id,
                Vehicle.is_active
                == True,  # noqa: E712
            )
            .order_by(
                Vehicle.is_default.desc(),
                Vehicle.created_at.desc(),
            )
        )

        result = await self.db.execute(
            statement,
        )

        return list(
            result.scalars().all(),
        )

    # ======================================================
    # Registration Number Check
    # ======================================================

    async def registration_exists(
        self,
        registration_number: str,
        exclude_vehicle_id: int | None = None,
    ) -> bool:
        """
        Determine whether a registration number already exists.

        Matching is case-insensitive and whitespace-insensitive.
        """

        normalized_registration = "".join(
            registration_number.split()
        ).upper()

        query = select(self.model.id).where(
            func.replace(
                func.upper(
                    self.model.registration_number,
                ),
                " ",
                "",
            )
            == normalized_registration
        )

        if exclude_vehicle_id is not None:
            query = query.where(
                self.model.id != exclude_vehicle_id,
            )

        result = await self.db.execute(
            query,
        )

        return result.scalar_one_or_none() is not None