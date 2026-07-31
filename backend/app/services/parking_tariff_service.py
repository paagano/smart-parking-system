"""
Parking Tariff Service

Application service responsible for managing parking tariffs.

Responsibilities
----------------
- Tariff CRUD operations
- Tariff lifecycle management
- Business rule enforcement
- Tariff lookup
- Tariff snapshot generation

Pricing calculation itself is delegated to the Pricing Engine.
"""

from __future__ import annotations

from app.models.parking_tariff import ParkingTariff

from app.repositories.parking_tariff_repository import (
    ParkingTariffRepository,
)

from app.schemas.parking_tariff import (
    ParkingTariffCreate,
    ParkingTariffUpdate,
)

from app.services.pricing.tariff_mapper import (
    tariff_to_snapshot,
)

from app.services.pricing.tariff_snapshot import (
    TariffSnapshot,
)

from app.services.pricing.pricing_exceptions import (
    DuplicateTariffCodeException,
    OverlappingTariffException,
    TariffActivationException,
)


class ParkingTariffService:
    """
    Service responsible for Parking Tariff management.
    """

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        repository: ParkingTariffRepository,
    ) -> None:
        """
        Create a Parking Tariff service.

        Parameters
        ----------
        repository:
            Repository used for parking tariff persistence.
        """

        self.repository = repository

    # ==========================================================
    # Queries
    # ==========================================================

    async def get_by_id(
        self,
        tariff_id: int,
    ) -> ParkingTariff | None:
        """
        Retrieve a tariff by its primary key.
        """

        return await self.repository.get_by_id(
            tariff_id
        )

    async def get_by_code(
        self,
        code: str,
    ) -> ParkingTariff | None:
        """
        Retrieve a tariff using its unique code.
        """

        return await self.repository.get_by_code(
            code
        )

    async def get_all(
        self,
    ) -> list[ParkingTariff]:
        """
        Return every parking tariff.
        """

        return await self.repository.get_all()

    # ==========================================================
    # Create
    # ==========================================================

    async def create_tariff(
        self,
        data: ParkingTariffCreate,
    ) -> ParkingTariff:
        """
        Create a new parking tariff.

        Business validation is performed before the tariff
        is persisted.
        """

        await self._validate_duplicate_code(
            data.code,
        )

        await self._validate_effective_dates(
            data,
        )

        await self._validate_priority(
            data,
        )

        tariff = ParkingTariff(
            **data.model_dump()
        )

        tariff = await self.repository.save(
            tariff,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            tariff,
        )

        return tariff

    # ==========================================================
    # Snapshot
    # ==========================================================

    async def get_snapshot(
        self,
        tariff_id: int,
    ) -> TariffSnapshot | None:
        """
        Retrieve an immutable pricing snapshot.
        """

        tariff = await self.get_by_id(
            tariff_id,
        )

        if tariff is None:
            return None

        return tariff_to_snapshot(
            tariff,
        )

        # ==========================================================
    # Business Rule Validation
    # ==========================================================

    async def _validate_duplicate_code(
        self,
        code: str,
        exclude_tariff_id: int | None = None,
    ) -> None:
        """
        Ensure the tariff code is unique.

        Parameters
        ----------
        code:
            Tariff business code.

        exclude_tariff_id:
            Used during updates to exclude the current tariff.
        """

        existing = await self.repository.get_by_code(code)

        if existing is None:
            return

        if (
            exclude_tariff_id is not None
            and existing.id == exclude_tariff_id
        ):
            return

        raise DuplicateTariffCodeException(
            f"A tariff with code '{code}' already exists."
        )

    async def _validate_effective_dates(
        self,
        data: ParkingTariffCreate | ParkingTariffUpdate,
        exclude_tariff_id: int | None = None,
    ) -> None:
        """
        Ensure there are no overlapping effective tariffs
        with the same billing and vehicle type.
        """

        overlaps = await self.repository.find_overlapping_tariffs(
            vehicle_type=data.vehicle_type,
            billing_type=data.billing_type,
            effective_from=data.effective_from,
            effective_to=data.effective_to,
            exclude_tariff_id=exclude_tariff_id,
        )

        if overlaps:
            raise OverlappingTariffException(
                "Another tariff already exists for the supplied "
                "vehicle type, billing type and effective period."
            )

    async def _validate_priority(
        self,
        data: ParkingTariffCreate | ParkingTariffUpdate,
        exclude_tariff_id: int | None = None,
    ) -> None:
        """
        Validate tariff priority.

        Priority conflicts are permitted, but a warning could
        later be logged or surfaced to administrators.

        This method exists to centralize future priority rules.
        """

        conflicting = (
            await self.repository.find_priority_conflicts(
                vehicle_type=data.vehicle_type,
                billing_type=data.billing_type,
                pricing_priority=data.pricing_priority,
                exclude_tariff_id=exclude_tariff_id,
            )
        )

        #
        # Current Business Rule
        #
        # Equal priorities are allowed.
        #
        # In the future this method can enforce:
        #
        # - unique priorities
        # - priority ranges
        # - facility-specific priorities
        # - dynamic priorities
        #
        if conflicting:
            return

    async def _validate_activation(
        self,
        tariff: ParkingTariff,
    ) -> None:
        """
        Validate whether a tariff can be activated.

        A tariff cannot be activated if another active tariff
        overlaps its effective period for the same billing and
        vehicle type.
        """

        overlaps = await self.repository.find_overlapping_tariffs(
            vehicle_type=tariff.vehicle_type,
            billing_type=tariff.billing_type,
            effective_from=tariff.effective_from,
            effective_to=tariff.effective_to,
            exclude_tariff_id=tariff.id,
        )

        if overlaps:
            raise TariffActivationException(
                "Cannot activate tariff because another "
                "active tariff overlaps its effective period."
            )

    # ==========================================================
    # Update
    # ==========================================================

    async def update_tariff(
        self,
        tariff_id: int,
        data: ParkingTariffUpdate,
    ) -> ParkingTariff | None:
        """
        Update an existing parking tariff.
        """

        tariff = await self.get_by_id(
            tariff_id,
        )

        if tariff is None:
            return None

        update_data = data.model_dump(
            exclude_unset=True,
        )

        #
        # Business Validation
        #

        if (
            "code" in update_data
            and update_data["code"] != tariff.code
        ):
            await self._validate_duplicate_code(
                update_data["code"],
                exclude_tariff_id=tariff.id,
            )

        if any(
            field in update_data
            for field in (
                "vehicle_type",
                "billing_type",
                "effective_from",
                "effective_to",
            )
        ):
            merged = ParkingTariffCreate(
                **{
                    **tariff.__dict__,
                    **update_data,
                }
            )

            await self._validate_effective_dates(
                merged,
                exclude_tariff_id=tariff.id,
            )

            await self._validate_priority(
                merged,
                exclude_tariff_id=tariff.id,
            )

        #
        # Apply Updates
        #

        for field, value in update_data.items():
            setattr(
                tariff,
                field,
                value,
            )

        await self.repository.save(
            tariff,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            tariff,
        )

        return tariff

    # ==========================================================
    # Activation
    # ==========================================================

    async def activate_tariff(
        self,
        tariff_id: int,
    ) -> ParkingTariff | None:
        """
        Activate a parking tariff.
        """

        tariff = await self.get_by_id(
            tariff_id,
        )

        if tariff is None:
            return None

        await self._validate_activation(
            tariff,
        )

        tariff.is_active = True

        await self.repository.save(
            tariff,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            tariff,
        )

        return tariff

    async def deactivate_tariff(
        self,
        tariff_id: int,
    ) -> ParkingTariff | None:
        """
        Deactivate a parking tariff.
        """

        tariff = await self.get_by_id(
            tariff_id,
        )

        if tariff is None:
            return None

        tariff.is_active = False

        await self.repository.save(
            tariff,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            tariff,
        )

        return tariff

    # ==========================================================
    # Delete
    # ==========================================================

    async def delete_tariff(
        self,
        tariff_id: int,
    ) -> bool:
        """
        Delete a parking tariff.

        Returns
        -------
        bool
            True if deleted.
        """

        tariff = await self.get_by_id(
            tariff_id,
        )

        if tariff is None:
            return False

        await self.repository.remove(
            tariff,
        )

        await self.repository.db.commit()

        return True

    # ==========================================================
    # Tariff Lookup
    # ==========================================================

    async def find_applicable_tariff(
        self,
        vehicle_type,
        billing_type,
        effective_at,
    ) -> ParkingTariff | None:
        """
        Find the highest-priority active tariff applicable
        at the supplied datetime.
        """

        return await self.repository.find_applicable_tariff(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            effective_at=effective_at,
        )

    # ==========================================================
    # Snapshot
    # ==========================================================

    async def get_applicable_snapshot(
        self,
        vehicle_type,
        billing_type,
        effective_at,
    ) -> TariffSnapshot | None:
        """
        Retrieve the immutable pricing snapshot for the
        applicable tariff.
        """

        tariff = await self.find_applicable_tariff(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            effective_at=effective_at,
        )

        if tariff is None:
            return None

        return tariff_to_snapshot(
            tariff
        )

    # ==========================================================
    # Queries
    # ==========================================================

    async def get_active_tariffs(
        self,
    ) -> list[ParkingTariff]:
        """
        Return all active parking tariffs.
        """

        return await self.repository.get_active_tariffs()

    async def search(
        self,
        search_term: str,
    ) -> list[ParkingTariff]:
        """
        Search tariffs by name or code.
        """

        return await self.repository.search(
            search_term
        )