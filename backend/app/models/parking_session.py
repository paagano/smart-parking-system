"""
Parking Session model.

A Parking Session represents a single instance of a vehicle occupying
a parking bay.

Parking Sessions are transactional records and form the core operational
entity within SmartPark AI.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import (
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import (
    EntryMethod,
    ExitMethod,
    PaymentStatus,
    SessionSource,
    SessionStatus,
    VehicleType,
)

if TYPE_CHECKING:
    from app.models.parking_bay import ParkingBay
    from app.models.user import User


class ParkingSession(BaseModel):
    """
    Represents a vehicle parking event.

    One Parking Session represents one vehicle occupying one parking bay
    from entry until exit.
    """

    __tablename__ = "parking_sessions"

    __table_args__ = (
        UniqueConstraint(
            "session_number",
            name="uq_parking_sessions_session_number",
        ),
        Index(
            "ix_parking_sessions_bay",
            "parking_bay_id",
        ),
        Index(
            "ix_parking_sessions_vehicle",
            "vehicle_registration",
        ),
        Index(
            "ix_parking_sessions_status",
            "status",
        ),
        Index(
            "ix_parking_sessions_entry_time",
            "entry_time",
        ),
        Index(
            "ix_parking_sessions_payment_status",
            "payment_status",
        ),
    )

    # ==========================================================
    # Identification
    # ==========================================================

    session_number: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    parking_bay_id: Mapped[int] = mapped_column(
        ForeignKey(
            "parking_bays.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    created_by: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # ==========================================================
    # Vehicle Information
    # ==========================================================

    vehicle_registration: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    vehicle_type: Mapped[VehicleType] = mapped_column(
        Enum(
            VehicleType,
            name="vehicle_type",
            create_type=False,
        ),
        nullable=False,
    )

    # ==========================================================
    # Session Information
    # ==========================================================

    status: Mapped[SessionStatus] = mapped_column(
        Enum(
            SessionStatus,
            name="session_status",
        ),
        nullable=False,
        default=SessionStatus.ACTIVE,
        server_default=sa.text("'ACTIVE'"),
    )

    session_source: Mapped[SessionSource] = mapped_column(
        Enum(
            SessionSource,
            name="session_source",
        ),
        nullable=False,
    )

    entry_method: Mapped[EntryMethod] = mapped_column(
        Enum(
            EntryMethod,
            name="entry_method",
        ),
        nullable=False,
    )

    exit_method: Mapped[ExitMethod | None] = mapped_column(
        Enum(
            ExitMethod,
            name="exit_method",
        ),
        nullable=True,
    )

    # ==========================================================
    # Timing
    # ==========================================================

    entry_time: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
    )

    expected_exit_time: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    exit_time: Mapped[datetime | None] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=True,
    )

    duration_minutes: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    # ==========================================================
    # Payment
    # ==========================================================

    calculated_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=sa.text("0.00"),
    )

    paid_amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=sa.text("0.00"),
    )

    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(
            PaymentStatus,
            name="payment_status",
        ),
        nullable=False,
        default=PaymentStatus.PENDING,
        server_default=sa.text("'PENDING'"),
    )

    # ==========================================================
    # Additional Information
    # ==========================================================

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ==========================================================
    # ORM Relationships
    # ==========================================================

    parking_bay: Mapped["ParkingBay"] = relationship(
        "ParkingBay",
        back_populates="sessions",
    )

    created_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by],
    )

    updated_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[updated_by],
    )