"""
Vehicle Service.

Contains business logic for vehicle management.

The service layer is responsible for:
- Vehicle ownership
- Registration number validation
- Default vehicle management
- Vehicle activation/deactivation
- Updating vehicle details
- Vehicle deletion

Persistence and database access are delegated to
VehicleRepository.
"""

from __future__ import annotations

from app.models.vehicle import Vehicle
from app.repositories.vehicle_repository import VehicleRepository
from app.schemas.vehicle import (
    VehicleCreate,
    VehicleUpdate,
)


# ==========================================================
# Vehicle Service
# ==========================================================

class VehicleService:
    """
    Business logic for Vehicle Management.
    """

    def __init__(
        self,
        repository: VehicleRepository,
    ) -> None:
        self.repository = repository

    # ======================================================
    # Create Vehicle
    # ======================================================

    async def create_vehicle(
        self,
        *,
        customer_id: int,
        data: VehicleCreate,
    ) -> Vehicle:
        """
        Register a new vehicle for a customer.
        """

        #
        # Normalize registration number.
        #
        registration_number = "".join(
            data.registration_number.split()
        ).upper()

        #
        # Prevent duplicate registration numbers.
        #
        exists = await self.repository.registration_exists(
            registration_number,
        )

        if exists:
            raise ValueError(
                "A vehicle with this registration number "
                "already exists."
            )

        #
        # If this is the customer's first vehicle,
        # make it the default automatically.
        #
        customer_vehicles = (
            await self.repository.get_by_customer_id(
                customer_id,
            )
        )

        is_first_vehicle = (
            len(customer_vehicles) == 0
        )

        vehicle = Vehicle(
            customer_id=customer_id,
            plate_country=data.plate_country.upper(),
            registration_number=registration_number,
            nickname=data.nickname,
            make=data.make,
            model=data.model,
            colour=data.colour,
            year=data.year,
            vehicle_type=data.vehicle_type,
            parking_profile=data.parking_profile,
            is_default=(
                data.is_default
                or is_first_vehicle
            ),
            is_active=True,
        )

        #
        # If explicitly/default selected, remove
        # default status from the customer's existing
        # vehicles.
        #
        if vehicle.is_default:
            await self._clear_customer_default_vehicle(
                customer_id=customer_id,
            )

        #
        # Persist.
        #
        await self.repository.save(
            vehicle,
        )

        await self.repository.commit()

        await self.repository.refresh(
            vehicle,
        )

        return vehicle

    # ======================================================
    # Get Vehicle
    # ======================================================

    async def get_vehicle(
        self,
        vehicle_id: int,
    ) -> Vehicle:
        """
        Retrieve a vehicle by ID.
        """

        vehicle = await self.repository.get_by_id(
            vehicle_id,
        )

        if vehicle is None:
            raise ValueError(
                "Vehicle not found."
            )

        return vehicle

    # ======================================================
    # Get Customer Vehicles
    # ======================================================

    async def get_customer_vehicles(
        self,
        *,
        customer_id: int,
    ) -> list[Vehicle]:
        """
        Retrieve all vehicles belonging to a customer.
        """

        return await self.repository.get_by_customer_id(
            customer_id,
        )

    # ======================================================
    # Get Active Customer Vehicles
    # ======================================================

    async def get_active_customer_vehicles(
        self,
        *,
        customer_id: int,
    ) -> list[Vehicle]:
        """
        Retrieve all active vehicles belonging to a customer.
        """

        return await self.repository.get_active_by_customer_id(
            customer_id,
        )

    # ======================================================
    # Get Default Vehicle
    # ======================================================

    async def get_default_vehicle(
        self,
        *,
        customer_id: int,
    ) -> Vehicle | None:
        """
        Retrieve the customer's default vehicle.
        """

        return await self.repository.get_default_vehicle(
            customer_id,
        )

    # ======================================================
    # Get By Registration Number
    # ======================================================

    async def get_by_registration_number(
        self,
        registration_number: str,
    ) -> Vehicle:
        """
        Retrieve a vehicle using its registration number.

        Registration numbers are matched case-insensitively
        and without whitespace.

        This will later be useful for ANPR integration.
        """

        normalized_registration = "".join(
            registration_number.split()
        ).upper()

        vehicle = (
            await self.repository.get_by_registration_number(
                normalized_registration,
            )
        )

        if vehicle is None:
            raise ValueError(
                "Vehicle not found."
            )

        return vehicle

    # ======================================================
    # Update Vehicle
    # ======================================================

    async def update_vehicle(
        self,
        *,
        vehicle_id: int,
        customer_id: int,
        data: VehicleUpdate,
    ) -> Vehicle:
        """
        Update a vehicle owned by the customer.
        """

        vehicle = await self.get_vehicle(
            vehicle_id,
        )

        #
        # Ownership check.
        #
        if vehicle.customer_id != customer_id:
            raise ValueError(
                "You are not authorized to modify this vehicle."
            )

        #
        # Only active vehicles may be updated.
        #
        if not vehicle.is_active:
            raise ValueError(
                "Inactive vehicles cannot be updated."
            )

        #
        # Convert only fields actually supplied.
        #
        update_data = data.model_dump(
            exclude_unset=True,
        )

        #
        # Registration number.
        #
        if "registration_number" in update_data:
            registration_number = "".join(
                update_data["registration_number"].split()
            ).upper()

            exists = (
                await self.repository.registration_exists(
                    registration_number,
                    exclude_vehicle_id=vehicle.id,
                )
            )

            if exists:
                raise ValueError(
                    "A vehicle with this registration number "
                    "already exists."
                )

            update_data[
                "registration_number"
            ] = registration_number

        #
        # Country code.
        #
        if "plate_country" in update_data:
            update_data[
                "plate_country"
            ] = update_data[
                "plate_country"
            ].upper()

        #
        # Apply changes.
        #
        for field, value in update_data.items():
            setattr(
                vehicle,
                field,
                value,
            )

        #
        # Preserve existing behaviour.
        #
        vehicle.is_default = True

        await self.repository.save(
            vehicle,
        )

        await self.repository.commit()

        await self.repository.refresh(
            vehicle,
        )

        return vehicle

    # ======================================================
    # Set Default Vehicle
    # ======================================================

    async def set_default_vehicle(
        self,
        *,
        vehicle_id: int,
        customer_id: int,
    ) -> Vehicle:
        """
        Make a customer's vehicle the default vehicle.
        """

        vehicle = await self.get_vehicle(
            vehicle_id,
        )

        #
        # Ownership check.
        #
        if vehicle.customer_id != customer_id:
            raise ValueError(
                "You are not authorized to modify this vehicle."
            )

        #
        # Inactive vehicles cannot become default.
        #
        if not vehicle.is_active:
            raise ValueError(
                "Inactive vehicles cannot be set as default."
            )

        #
        # Already default.
        #
        if vehicle.is_default:
            return vehicle

        #
        # Remove default status from other vehicles.
        #
        await self._clear_customer_default_vehicle(
            customer_id=customer_id,
        )

        #
        # Set new default.
        #
        vehicle.is_default = True

        await self.repository.save(
            vehicle,
        )

        return vehicle

    # ======================================================
    # Deactivate Vehicle
    # ======================================================

    async def deactivate_vehicle(
        self,
        *,
        vehicle_id: int,
        customer_id: int,
    ) -> Vehicle:
        """
        Deactivate a vehicle.

        The vehicle is retained for historical records.
        """

        vehicle = await self.get_vehicle(
            vehicle_id,
        )

        #
        # Ownership check.
        #
        if vehicle.customer_id != customer_id:
            raise ValueError(
                "You are not authorized to modify this vehicle."
            )

        #
        # Already inactive.
        #
        if not vehicle.is_active:
            return vehicle

        #
        # Do not leave an inactive vehicle as default.
        #
        if vehicle.is_default:
            vehicle.is_default = False

        vehicle.is_active = False

        await self.repository.save(
            vehicle,
        )

        await self.repository.commit()

        await self.repository.refresh(
            vehicle,
        )

        return vehicle

    # ======================================================
    # Activate Vehicle
    # ======================================================

    async def activate_vehicle(
        self,
        *,
        vehicle_id: int,
        customer_id: int,
    ) -> Vehicle:
        """
        Reactivate a previously deactivated vehicle.
        """

        vehicle = await self.get_vehicle(
            vehicle_id,
        )

        #
        # Ownership check.
        #
        if vehicle.customer_id != customer_id:
            raise ValueError(
                "You are not authorized to modify this vehicle."
            )

        #
        # Already active.
        #
        if vehicle.is_active:
            return vehicle

        vehicle.is_active = True

        await self.repository.save(
            vehicle,
        )

        await self.repository.commit()

        await self.repository.refresh(
            vehicle,
        )

        return vehicle

    # ======================================================
    # Delete Vehicle
    # ======================================================

    async def delete_vehicle(
        self,
        *,
        vehicle_id: int,
        customer_id: int,
    ) -> None:
        """
        Permanently delete a vehicle from the customer's
        vehicle profile.

        Delete is intended for vehicles that the customer
        no longer owns, for example a vehicle that has been
        sold or transferred.

        This is deliberately different from deactivate_vehicle(),
        which retains the vehicle for historical records.

        Ownership is verified before deletion.
        """

        vehicle = await self.get_vehicle(
            vehicle_id,
        )

        #
        # Ownership check.
        #
        if vehicle.customer_id != customer_id:
            raise ValueError(
                "You are not authorized to delete this vehicle."
            )

        #
        # Delete the vehicle.
        #
        # The repository is responsible for persistence.
        # Database relationships/constraints remain the
        # authority for determining whether the record can
        # safely be removed.
        #
        await self.repository.delete(
            vehicle,
        )

        await self.repository.commit()

    # ======================================================
    # Internal Helper
    # ======================================================

    async def _clear_customer_default_vehicle(
        self,
        *,
        customer_id: int,
    ) -> None:
        """
        Remove default status from all of the customer's
        existing vehicles.

        This is an internal business operation.
        """

        vehicles = (
            await self.repository.get_by_customer_id(
                customer_id,
            )
        )

        for vehicle in vehicles:
            if vehicle.is_default:
                vehicle.is_default = False

                await self.repository.save(
                    vehicle,
                )