"""
Pricing Dependencies

Dependency Injection (DI) providers for the Pricing module.

This module composes the Pricing subsystem by wiring together:

- PricingEngine
- ParkingTariffService
- PricingService

Business logic belongs in the services.
Persistence belongs in the repositories.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.repositories import (
    ParkingTariffRepositoryDep,
)
from app.repositories.parking_tariff_repository import (
    ParkingTariffRepository,
)
from app.services.parking_tariff_service import (
    ParkingTariffService,
)
from app.services.pricing.pricing_engine import (
    PricingEngine,
)
from app.services.pricing_service import (
    PricingService,
)

# ==========================================================
# Pricing Engine
# ==========================================================


def get_pricing_engine() -> PricingEngine:
    """
    Return a PricingEngine instance.

    The PricingEngine is stateless and therefore safe
    to instantiate for dependency injection.
    """

    return PricingEngine()


# ==========================================================
# Parking Tariff Service
# ==========================================================


def get_parking_tariff_service(
    repository: ParkingTariffRepositoryDep,
) -> ParkingTariffService:
    """
    Return a ParkingTariffService instance.
    """

    return ParkingTariffService(
        repository=repository,
    )


# ==========================================================
# Pricing Service
# ==========================================================


def get_pricing_service(
    tariff_service: ParkingTariffServiceDep,
    pricing_engine: PricingEngineDep,
) -> PricingService:

    return PricingService(
        tariff_service=tariff_service,
        pricing_engine=pricing_engine,
    )


# ==========================================================
# Dependency Aliases
# ==========================================================

PricingEngineDep = Annotated[
    PricingEngine,
    Depends(get_pricing_engine),
]

ParkingTariffServiceDep = Annotated[
    ParkingTariffService,
    Depends(get_parking_tariff_service),
]

PricingServiceDep = Annotated[
    PricingService,
    Depends(get_pricing_service),
]