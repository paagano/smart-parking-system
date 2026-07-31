"""
Pricing Service

Application service responsible for parking pricing.

Responsibilities
----------------
- Retrieve the applicable parking tariff
- Build immutable tariff snapshots
- Construct pricing requests
- Delegate calculations to the Pricing Engine

This service intentionally contains NO pricing formulas.
Those belong exclusively to the Pricing Engine.
"""

from __future__ import annotations

from datetime import datetime

from app.models.enums import (
    BillingType,
    VehicleType,
)
from app.services.parking_tariff_service import (
    ParkingTariffService,
)
from app.services.pricing.pricing_engine import (
    PricingEngine,
)
from app.services.pricing.pricing_exceptions import (
    TariffNotFoundException,
)
from app.services.pricing.pricing_request import (
    PricingRequest,
)
from app.services.pricing.pricing_result import (
    PricingResult,
)
from app.services.pricing.tariff_snapshot import (
    TariffSnapshot,
)


class PricingService:
    """
    Application service responsible for parking pricing.

    This service coordinates tariff lookup and delegates all
    pricing calculations to the Pricing Engine.
    """

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        tariff_service: ParkingTariffService,
        pricing_engine: PricingEngine,
    ) -> None:
        """
        Create a PricingService.

        Parameters
        ----------
        tariff_service:
            Service responsible for tariff retrieval and
            lifecycle management.

        pricing_engine:
            Stateless Pricing Engine used to calculate
            parking charges.
        """

        self.tariff_service = tariff_service

        self.engine = pricing_engine

    # ==========================================================
    # Pricing
    # ==========================================================

    async def calculate_price(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        entry_time: datetime,
        exit_time: datetime,
    ) -> PricingResult:
        """
        Calculate parking charges.

        This is the primary entry point used by the
        Parking Session Service.
        """

        snapshot = await self._get_tariff_snapshot(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            effective_at=entry_time,
        )

        request = self._build_request(
            tariff=snapshot,
            entry_time=entry_time,
            exit_time=exit_time,
        )

        return self.engine.calculate(
            request
        )

    # ==========================================================
    # Quote
    # ==========================================================

    async def quote(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        entry_time: datetime,
        exit_time: datetime,
    ) -> PricingResult:
        """
        Alias for calculate_price().

        Intended for future quote/estimate endpoints.
        """

        return await self.calculate_price(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            entry_time=entry_time,
            exit_time=exit_time,
        )

        # ==========================================================
    # Tariff Lookup
    # ==========================================================

    async def get_applicable_tariff(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        effective_at: datetime,
    ) -> TariffSnapshot:
        """
        Retrieve the applicable parking tariff snapshot.

        Raises
        ------
        TariffNotFoundException
            If no applicable tariff exists.
        """

        return await self._get_tariff_snapshot(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            effective_at=effective_at,
        )

    # ==========================================================
    # Helpers
    # ==========================================================

    async def _get_tariff_snapshot(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        effective_at: datetime,
    ) -> TariffSnapshot:
        """
        Retrieve the immutable tariff snapshot used by the
        Pricing Engine.
        """

        snapshot = (
            await self.tariff_service.get_applicable_snapshot(
                vehicle_type=vehicle_type,
                billing_type=billing_type,
                effective_at=effective_at,
            )
        )

        if snapshot is None:
            raise TariffNotFoundException(
                "No applicable parking tariff found."
            )

        return snapshot

    def _build_request(
        self,
        *,
        tariff: TariffSnapshot,
        entry_time: datetime,
        exit_time: datetime,
    ) -> PricingRequest:
        """
        Build a PricingRequest for the Pricing Engine.
        """

        return PricingRequest(
            tariff=tariff,
            entry_time=entry_time,
            exit_time=exit_time,
        )

        # ==========================================================
    # Engine
    # ==========================================================

    def _calculate(
        self,
        request: PricingRequest,
    ) -> PricingResult:
        """
        Execute the Pricing Engine.

        This method centralizes all interaction with the
        Pricing Engine, providing a future extension point
        for logging, metrics, auditing or caching.
        """

        return self.engine.calculate(
            request
        )

    # ==========================================================
    # Estimate
    # ==========================================================

    async def estimate_price(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        entry_time: datetime,
        exit_time: datetime,
    ) -> PricingResult:
        """
        Estimate parking charges.

        Functionally identical to calculate_price().

        Exists as a semantic API for future estimate
        endpoints or pre-booking workflows.
        """

        return await self.calculate_price(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            entry_time=entry_time,
            exit_time=exit_time,
        )

    # ==========================================================
    # Parking Session
    # ==========================================================

    async def calculate_for_session(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        entry_time: datetime,
        exit_time: datetime,
    ) -> PricingResult:
        """
        Calculate pricing for a parking session.

        This is the method intended to be called by the
        ParkingSessionService when a vehicle exits.
        """

        return await self.calculate_price(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            entry_time=entry_time,
            exit_time=exit_time,
        )

    # ==========================================================
    # Validation
    # ==========================================================

    async def tariff_exists(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        effective_at: datetime,
    ) -> bool:
        """
        Determine whether an applicable tariff exists.
        """

        try:

            await self._get_tariff_snapshot(
                vehicle_type=vehicle_type,
                billing_type=billing_type,
                effective_at=effective_at,
            )

            return True

        except TariffNotFoundException:

            return False

        # ==========================================================
    # Health
    # ==========================================================

    async def can_calculate(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        effective_at: datetime,
    ) -> bool:
        """
        Determine whether pricing can be calculated.

        This method verifies that a valid tariff exists for
        the supplied parameters.

        Returns
        -------
        bool
            True if pricing can be calculated.
        """

        return await self.tariff_exists(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            effective_at=effective_at,
        )

    # ==========================================================
    # Engine Access
    # ==========================================================

    @property
    def pricing_engine(
        self,
    ) -> PricingEngine:
        """
        Expose the Pricing Engine as a read-only property.

        Primarily intended for testing or advanced scenarios.
        Application services should generally use the public
        methods on PricingService instead.
        """

        return self.engine

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
            f"engine={self.engine.__class__.__name__})"
        )