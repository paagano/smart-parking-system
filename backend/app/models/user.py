from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Enum,
    String,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.models.base_model import BaseModel
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.parking_reservation import ParkingReservation
    from app.models.parking_session import ParkingSession
    from app.models.wallet import Wallet


class User(BaseModel):
    """
    Represents a system user.
    """

    __tablename__ = "users"

    # ==========================================================
    # Personal Information
    # ==========================================================

    first_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    last_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    phone_number: Mapped[str | None] = mapped_column(
        String(20),
        unique=True,
        nullable=True,
    )

    # ==========================================================
    # Authentication
    # ==========================================================

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
        ),
        nullable=False,
        default=UserRole.DRIVER,
    )

    # ==========================================================
    # Status
    # ==========================================================

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    # Parking Reservations
    parking_reservations: Mapped[
        list["ParkingReservation"]
    ] = relationship(
        "ParkingReservation",
        foreign_keys="ParkingReservation.customer_id",
        back_populates="customer",
        cascade="all, delete-orphan",
    )

    # Parking Sessions
    parking_sessions: Mapped[
        list["ParkingSession"]
    ] = relationship(
        "ParkingSession",
        foreign_keys="ParkingSession.customer_id",
        back_populates="customer",
    )

    # Wallet
    wallet: Mapped["Wallet | None"] = relationship(
        "Wallet",
        back_populates="customer",
        uselist=False,
        passive_deletes=True,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<User("
            f"id={self.id}, "
            f"email='{self.email}', "
            f"role='{self.role.value}'"
            f")>"
        )