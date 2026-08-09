"""
Pricing Service

Coordinates parking pricing.

Responsibilities
----------------
- Resolve the applicable tariff
- Build immutable tariff snapshots
- Build pricing requests
- Delegate calculations to PricingEngine

Contains NO pricing formulas.
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

    PricingService performs four tasks:

        1. Resolve the applicable tariff
        2. Build an immutable TariffSnapshot
        3. Build a PricingRequest
        4. Delegate calculations to PricingEngine
    """

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(
        self,
        tariff_service: ParkingTariffService,
        pricing_engine: PricingEngine,
    ) -> None:

        self.tariff_service = tariff_service
        self.engine = pricing_engine

    # ==========================================================
    # Public API
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
        """

        tariff = await self._get_tariff_snapshot(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            effective_at=entry_time,
        )

        request = self._build_request(
            tariff=tariff,
            entry_time=entry_time,
            exit_time=exit_time,
        )

        return self._calculate(
            request,
        )

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
        """

        return await self.calculate_price(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            entry_time=entry_time,
            exit_time=exit_time,
        )

    async def estimate_price(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        entry_time: datetime,
        exit_time: datetime,
    ) -> PricingResult:
        """
        Semantic alias for calculate_price().
        """

        return await self.calculate_price(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            entry_time=entry_time,
            exit_time=exit_time,
        )

    # ==========================================================
    # Tariff Resolution
    # ==========================================================

    async def get_applicable_tariff(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        effective_at: datetime,
    ) -> TariffSnapshot:
        """
        Retrieve the immutable tariff snapshot that applies
        at the supplied datetime.
        """

        return await self._get_tariff_snapshot(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            effective_at=effective_at,
        )

    # ==========================================================
    # Session Pricing
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
        Calculate pricing for an active parking session.

        This is the primary method used by
        ParkingSessionService during checkout.
        """

        return await self.calculate_price(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            entry_time=entry_time,
            exit_time=exit_time,
        )

    # ==========================================================
    # Tariff Validation
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

    async def can_calculate(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        effective_at: datetime,
    ) -> bool:
        """
        Determine whether pricing can be calculated.
        """

        return await self.tariff_exists(
            vehicle_type=vehicle_type,
            billing_type=billing_type,
            effective_at=effective_at,
        )

    # ==========================================================
    # Private Helpers
    # ==========================================================

    async def _get_tariff_snapshot(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        effective_at: datetime,
    ) -> TariffSnapshot:
        """
        Retrieve the immutable tariff snapshot that will be
        supplied to the Pricing Engine.
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

    def _calculate(
        self,
        request: PricingRequest,
    ) -> PricingResult:
        """
        Execute the Pricing Engine.

        This centralized method provides a future extension
        point for:

        - Logging
        - Auditing
        - Metrics
        - Performance monitoring
        - Caching
        """

        return self.engine.calculate(
            request
        )

    # ==========================================================
    # Health
    # ==========================================================

    async def health_check(
        self,
        *,
        vehicle_type: VehicleType,
        billing_type: BillingType,
        effective_at: datetime,
    ) -> bool:
        """
        Verify that pricing can be calculated.

        This checks only whether an applicable tariff exists.
        It does not perform a pricing calculation.
        """

        return await self.can_calculate(
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
        Read-only access to the Pricing Engine.

        Primarily intended for testing.
        """

        return self.engine

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(
        self,
    ) -> str:

        return (
            f"{self.__class__.__name__}("
            f"tariff_service="
            f"{self.tariff_service.__class__.__name__}, "
            f"pricing_engine="
            f"{self.engine.__class__.__name__}"
            f")"
        )