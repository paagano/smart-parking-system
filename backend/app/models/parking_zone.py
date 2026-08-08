from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.parking_facility import ParkingFacility
    from app.models.parking_bay import ParkingBay
    from app.models.parking_session import ParkingSession
    from app.models.parking_reservation import ParkingReservation

from sqlalchemy import (
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import ZoneType


class ParkingZone(BaseModel):
    """
    Represents a logical parking zone within a parking facility.

    Parking Zones provide a flexible hierarchical structure capable of
    modelling many different parking environments, including:

    • Shopping malls
        Basement B1
            └── Aisle A

    • Airports
        Terminal 1
            └── Long Stay

    • Universities
        Engineering Block
            └── Staff Parking

    • Municipal parking
        CBD
            └── Moi Avenue
                    └── Section A

    A Parking Zone belongs to exactly one Parking Facility and may have
    another Parking Zone as its parent, allowing unlimited hierarchy.
    """

    __tablename__ = "parking_zones"

    __table_args__ = (
        UniqueConstraint(
            "facility_id",
            "code",
            name="uq_parking_zone_facility_code",
        ),
        Index(
            "ix_parking_zone_facility",
            "facility_id",
        ),
        Index(
            "ix_parking_zone_parent",
            "parent_zone_id",
        ),
        Index(
            "ix_parking_zone_type",
            "zone_type",
        ),
    )

    # ==========================================================
    # Foreign Keys
    # ==========================================================

    facility_id: Mapped[int] = mapped_column(
        ForeignKey(
            "parking_facilities.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    parent_zone_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "parking_zones.id",
            ondelete="CASCADE",
        ),
        nullable=True,
    )

    # ==========================================================
    # Zone Details
    # ==========================================================

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    zone_type: Mapped[ZoneType] = mapped_column(
        Enum(
            ZoneType,
            name="zone_type",
        ),
        nullable=False,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        default=True,
        nullable=False,
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    facility: Mapped["ParkingFacility"] = relationship(
        "ParkingFacility",
        back_populates="zones",
    )

    parent: Mapped["ParkingZone | None"] = relationship(
        "ParkingZone",
        remote_side="ParkingZone.id",
        back_populates="children",
    )

    children: Mapped[list["ParkingZone"]] = relationship(
        "ParkingZone",
        back_populates="parent",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    bays: Mapped[list["ParkingBay"]] = relationship(
        "ParkingBay",
        back_populates="zone",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<ParkingZone("
            f"id={self.id}, "
            f"name='{self.name}', "
            f"code='{self.code}', "
            f"type='{self.zone_type.value}', "
            f"facility_id={self.facility_id}"
            f")>"
        )