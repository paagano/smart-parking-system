"""
RFID Tag Model.

Represents a physical RFID tag registered within SmartPark AI.

An RFID tag may be assigned to one registered vehicle. The vehicle
then provides the link to the registered owner/customer.

RFID access flow:

    RFID Tag
        ↓
    Vehicle
        ↓
    Customer / Owner

The RFID tag itself does not store customer or facility information.
Facility access remains controlled by the operator's facility scope.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.vehicle import Vehicle

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.models.base_model import BaseModel


# ==========================================================
# RFID Tag
# ==========================================================

class RFIDTag(BaseModel):
    """
    Persistent RFID tag registration.

    Each physical RFID tag has a unique UID and may be assigned
    to one registered vehicle.

    An RFID tag may temporarily remain unassigned. Unassigned or
    inactive RFID tags must not be permitted to grant parking access.
    """

    __tablename__ = "rfid_tags"

    # ======================================================
    # RFID Identity
    # ======================================================

    uid: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )

    # ======================================================
    # Vehicle Assignment
    # ======================================================

    vehicle_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "vehicles.id",
            ondelete="SET NULL",
        ),
        unique=True,
        index=True,
        nullable=True,
    )

    # ======================================================
    # Status
    # ======================================================

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ======================================================
    # Relationships
    # ======================================================

    vehicle: Mapped["Vehicle | None"] = relationship(
        "Vehicle",
        back_populates="rfid_tag",
    )

    # ======================================================
    # Representation
    # ======================================================

    def __repr__(self) -> str:
        return (
            f"RFIDTag("
            f"id={self.id}, "
            f"uid='{self.uid}', "
            f"vehicle_id={self.vehicle_id}, "
            f"is_active={self.is_active}"
            f")"
        )
