from __future__ import annotations

from datetime import time
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Enum,
    Index,
    Numeric,
    String,
    Text,
    Time,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel
from app.models.enums import FacilityType


class ParkingFacility(BaseModel):
    """
    Represents a physical parking facility.

    Examples:
        • Two Rivers Mall
        • Sarit Centre
        • JKIA Terminal 1A
        • University of Nairobi
        • Family Bank Headquarters
    """

    __tablename__ = "parking_facilities"

    __table_args__ = (
        CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="ck_facility_latitude",
        ),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_facility_longitude",
        ),
        Index(
            "ix_parking_facility_name",
            "name",
        ),
        Index(
            "ix_parking_facility_code",
            "code",
            unique=True,
        ),
    )

    # ==========================================================
    # Basic Information
    # ==========================================================

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        comment="Display name of the parking facility.",
    )

    code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Unique business identifier for the parking facility.",
    )

    facility_type: Mapped[FacilityType] = mapped_column(
        Enum(
            FacilityType,
            name="facility_type",
            native_enum=False,
        ),
        nullable=False,
        comment="Business classification of the parking facility.",
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional description of the parking facility.",
    )

    # ==========================================================
    # Address Information
    # ==========================================================

    country: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Kenya",
        comment="Country where the parking facility is located.",
    )

    county: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="County where the parking facility is located.",
    )

    city: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="City where the parking facility is located.",
    )

    address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Physical street address.",
    )

    postal_code: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Postal code.",
    )

    # ==========================================================
    # Geographic Coordinates
    # ==========================================================

    latitude: Mapped[Decimal] = mapped_column(
        Numeric(9, 6),
        nullable=False,
        comment="Latitude in decimal degrees.",
    )

    longitude: Mapped[Decimal] = mapped_column(
        Numeric(9, 6),
        nullable=False,
        comment="Longitude in decimal degrees.",
    )

    timezone: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="Africa/Nairobi",
        comment="IANA timezone.",
    )

    # ==========================================================
    # Operating Hours
    # ==========================================================

    opening_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
        comment="Daily opening time.",
    )

    closing_time: Mapped[time] = mapped_column(
        Time,
        nullable=False,
        comment="Daily closing time.",
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="Indicates whether the facility is operational.",
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    # NOTE:
    # Relationships will be added incrementally as the corresponding
    # models are implemented. The ParkingLevel relationship has been
    # intentionally omitted for now to avoid mapper initialization
    # errors before the ParkingLevel model exists.

    # ==========================================================
    # String Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<ParkingFacility("
            f"id={self.id}, "
            f"code='{self.code}', "
            f"name='{self.name}', "
            f"type='{self.facility_type.value}'"
            f")>"
        )