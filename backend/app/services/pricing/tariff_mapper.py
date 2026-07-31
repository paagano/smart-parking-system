"""
Tariff Mapper

Provides mapping functions between persistence models and
Pricing Engine domain models.

This module isolates the Pricing Engine from SQLAlchemy
entities and ensures the engine operates purely on immutable
domain objects.
"""

from __future__ import annotations

from app.models.parking_tariff import ParkingTariff
from app.services.pricing.tariff_snapshot import TariffSnapshot


def tariff_to_snapshot(
    tariff: ParkingTariff,
) -> TariffSnapshot:
    """
    Convert a ParkingTariff SQLAlchemy entity into an
    immutable TariffSnapshot.

    Args:
        tariff:
            ParkingTariff database entity.

    Returns:
        TariffSnapshot suitable for the Pricing Engine.
    """

    return TariffSnapshot(
        id=tariff.id,
        name=tariff.name,
        code=tariff.code,
        vehicle_type=tariff.vehicle_type,
        billing_type=tariff.billing_type,
        grace_period_minutes=tariff.grace_period_minutes,
        minimum_charge=tariff.minimum_charge,
        hourly_rate=tariff.hourly_rate,
        daily_rate=tariff.daily_rate,
        flat_rate=tariff.flat_rate,
        max_daily_charge=tariff.max_daily_charge,
        effective_from=tariff.effective_from,
        effective_to=tariff.effective_to,
        is_active=tariff.is_active,
    )