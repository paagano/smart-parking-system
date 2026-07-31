"""
Pricing Request

Represents the information required by the Pricing Engine
to calculate parking charges.

This model is a domain contract and is not persisted.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.services.pricing.tariff_snapshot import TariffSnapshot


class PricingRequest(BaseModel):
    """
    Request passed to the Pricing Engine.
    """

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=True,
        extra="forbid",
    )

    # ==========================================================
    # Parking Session
    # ==========================================================

    entry_time: datetime

    exit_time: datetime

    # ==========================================================
    # Vehicle
    # ==========================================================

    vehicle_registration: str = Field(
        min_length=1,
        max_length=20,
    )

    # ==========================================================
    # Tariff
    # ==========================================================

    tariff: TariffSnapshot

    # ==========================================================
    # Optional Context
    # ==========================================================

    facility_id: int | None = None

    zone_id: int | None = None

    bay_id: int | None = None