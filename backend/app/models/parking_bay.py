"""
SQLAlchemy model for Parking Bays.

A Parking Bay represents an individual parking space within a Parking Zone.

Hierarchy:

Parking Facility
    └── Parking Zone
            └── Parking Bay

Parking Bays are relatively static master data. Dynamic information such as
occupancy, reservations, and active parking sessions are modelled in their
respective modules rather than being stored directly on the Parking Bay.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import (
    BaySize,
    BayType,
    VehicleType,
)

if TYPE_CHECKING:
    from app.models.parking_zone import ParkingZone
    from app.models.parking_session import ParkingSession


class ParkingBay(BaseModel):
    """
    Represents an individual parking bay.

    Every parking bay belongs to exactly one Parking Zone.

    Future relationships include:

    - Parking Sessions
    - Reservations
    - IoT Sensors
    - Pricing Rules
    - Maintenance Records
    """

    __tablename__ = "parking_bays"

    __table_args__ = (
        UniqueConstraint(
            "zone_id",
            "bay_number",
            name="uq_parking_bay_zone_number",
        ),
        UniqueConstraint(
            "zone_id",
            "code",
            name="uq_parking_bay_zone_code",
        ),
        Index(
            "ix_parking_bay_zone_id",
            "zone_id",
        ),
        Index(
            "ix_parking_bay_bay_type",
            "bay_type",
        ),
        Index(
            "ix_parking_bay_vehicle_type",
            "vehicle_type",
        ),
        Index(
            "ix_parking_bay_is_active",
            "is_active",
        ),
    )

    # ==========================================================
    # Foreign Key
    # ==========================================================

    zone_id: Mapped[int] = mapped_column(
        ForeignKey(
            "parking_zones.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    # ==========================================================
    # Identity
    # ==========================================================

    bay_number: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Human-readable bay number (e.g. A01, B15, EV-03).",
    )

    code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="Unique internal code for the parking bay.",
    )

    # ==========================================================
    # Classification
    # ==========================================================

    bay_type: Mapped[BayType] = mapped_column(
        Enum(
            BayType,
            name="bay_type",
        ),
        nullable=False,
    )

    vehicle_type: Mapped[VehicleType] = mapped_column(
        Enum(
            VehicleType,
            name="vehicle_type",
        ),
        nullable=False,
    )

    size: Mapped[BaySize] = mapped_column(
        Enum(
            BaySize,
            name="bay_size",
        ),
        nullable=False,
    )

    # ==========================================================
    # Features
    # ==========================================================

    is_accessible: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_ev_charging: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_vip: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_reservable: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ==========================================================
    # Display
    # ==========================================================

    sort_order: Mapped[int] = mapped_column(
        default=0,
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    zone: Mapped["ParkingZone"] = relationship(
        "ParkingZone",
        back_populates="bays",
    )

    sessions: Mapped[list["ParkingSession"]] = relationship(
    "ParkingSession",
    back_populates="parking_bay",
    passive_deletes=True,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<ParkingBay("
            f"id={self.id}, "
            f"bay_number='{self.bay_number}', "
            f"code='{self.code}', "
            f"zone_id={self.zone_id}"
            f")>"
        )