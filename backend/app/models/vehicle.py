"""
Vehicle Model.

Represents a vehicle registered by a customer.

A customer may own multiple vehicles, one of which
may be marked as the default vehicle.

Vehicles are used when creating parking reservations
and parking sessions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.parking_reservation import ParkingReservation
    from app.models.parking_session import ParkingSession

from sqlalchemy import (
    Boolean,
    Enum,
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

from app.models.enums import (
    ParkingProfile,
    VehicleType,
)


# ==========================================================
# Vehicle
# ==========================================================

class Vehicle(BaseModel):
    """
    Registered customer vehicle.
    """

    __tablename__ = "vehicles"

    # ======================================================
    # Primary Key
    # ======================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ======================================================
    # Ownership
    # ======================================================

    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )

    # ======================================================
    # Vehicle Information
    # ======================================================

    plate_country: Mapped[str] = mapped_column(
        String(2),
        default="KE",
        nullable=False,
    )

    registration_number: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=False,
    )

    nickname: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    make: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    model: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    colour: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    vehicle_type: Mapped[VehicleType] = mapped_column(
        Enum(VehicleType),
        nullable=False,
    )

    parking_profile: Mapped[ParkingProfile] = mapped_column(
        Enum(ParkingProfile),
        default=ParkingProfile.STANDARD,
        nullable=False,
    )

    # ======================================================
    # Status
    # ======================================================

    is_default: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # ======================================================
    # Relationships
    # ======================================================

    customer: Mapped["User | None"] = relationship(
        "User",
        back_populates="vehicles",
    )

    # reservations: Mapped[list["ParkingReservation"]] = relationship(
    #     "ParkingReservation",
    #     back_populates="vehicle",
    # )

    # parking_sessions: Mapped[list["ParkingSession"]] = relationship(
    #     "ParkingSession",
    #     back_populates="vehicle",
    # )

    # ======================================================
    # Representation
    # ======================================================

    def __repr__(
        self,
    ) -> str:
        return (
            f"Vehicle("
            f"id={self.id}, "
            f"registration_number='{self.registration_number}', "
            f"customer_id={self.customer_id})"
        )