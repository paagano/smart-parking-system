"""
Occupancy Observation model.

An Occupancy Observation represents a point-in-time snapshot of the
occupancy state of a parking facility.

Occupancy observations form the canonical historical time-series
data layer used by the SmartPark AI machine-learning module.

Data sources may include:

- Birmingham public parking dataset
- SmartPark operational data
- Simulated data
- Parking sensors
- External APIs

The observation layer is intentionally separate from transactional
entities such as ParkingSession and ParkingReservation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import (
    OccupancyObservationSource,
    OccupancyQualityStatus,
)

if TYPE_CHECKING:
    from app.models.parking_facility import ParkingFacility


class OccupancyObservation(BaseModel):
    """
    Represents a point-in-time occupancy observation for a
    parking facility.

    The model provides the canonical historical time-series
    foundation for SmartPark AI's forecasting and predictive
    analytics capabilities.

    Example:

        observed_at       = 2026-08-18 09:00
        total_spaces      = 500
        occupied_spaces   = 372
        available_spaces  = 128
        occupancy_rate    = 0.744
    """

    __tablename__ = "occupancy_observations"

    __table_args__ = (
        # ------------------------------------------------------
        # One canonical observation per facility and timestamp.
        # ------------------------------------------------------
        UniqueConstraint(
            "facility_id",
            "observed_at",
            name="uq_occupancy_observation_facility_time",
        ),

        # ------------------------------------------------------
        # Primary ML query pattern:
        #
        # "Get observations for facility X ordered/filter
        #  by time."
        # ------------------------------------------------------
        Index(
            "ix_occupancy_observation_facility_time",
            "facility_id",
            "observed_at",
        ),

        # ------------------------------------------------------
        # Useful for cross-facility time-range queries.
        # ------------------------------------------------------
        Index(
            "ix_occupancy_observation_observed_at",
            "observed_at",
        ),

        # ------------------------------------------------------
        # Data integrity constraints.
        # ------------------------------------------------------
        CheckConstraint(
            "total_spaces > 0",
            name="ck_occupancy_observation_total_spaces_positive",
        ),

        CheckConstraint(
            "occupied_spaces >= 0",
            name="ck_occupancy_observation_occupied_non_negative",
        ),

        CheckConstraint(
            "available_spaces >= 0",
            name="ck_occupancy_observation_available_non_negative",
        ),

        CheckConstraint(
            "occupied_spaces + available_spaces = total_spaces",
            name="ck_occupancy_observation_space_balance",
        ),

        CheckConstraint(
            "occupancy_rate >= 0 AND occupancy_rate <= 1",
            name="ck_occupancy_observation_rate_range",
        ),
    )

    # ==========================================================
    # Facility Relationship
    # ==========================================================

    facility_id: Mapped[int] = mapped_column(
        ForeignKey(
            "parking_facilities.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    facility: Mapped["ParkingFacility"] = relationship(
        "ParkingFacility",
        back_populates="occupancy_observations",
    )

    # ==========================================================
    # Observation Time
    # ==========================================================

    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # ==========================================================
    # Occupancy Measurements
    # ==========================================================

    total_spaces: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    occupied_spaces: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    available_spaces: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    occupancy_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
    )

    # ==========================================================
    # Data Provenance
    # ==========================================================

    source: Mapped[OccupancyObservationSource] = mapped_column(
        Enum(
            OccupancyObservationSource,
            name="occupancy_observation_source",
        ),
        nullable=False,
    )

    # ==========================================================
    # Data Quality
    # ==========================================================

    quality_status: Mapped[OccupancyQualityStatus] = mapped_column(
        Enum(
            OccupancyQualityStatus,
            name="occupancy_quality_status",
        ),
        nullable=False,
        default=OccupancyQualityStatus.VALID,
        server_default="VALID",
    )

    quality_flags: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<OccupancyObservation("
            f"id={self.id}, "
            f"facility_id={self.facility_id}, "
            f"observed_at='{self.observed_at}', "
            f"occupied={self.occupied_spaces}, "
            f"available={self.available_spaces}, "
            f"rate={self.occupancy_rate}, "
            f"source='{self.source.value}', "
            f"quality='{self.quality_status.value}'"
            f")>"
        )