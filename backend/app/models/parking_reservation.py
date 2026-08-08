"""
Parking Reservation Model

Represents a customer's reservation for a parking bay.

A reservation reserves a parking bay for a specified period
before the customer arrives.

Reservation Lifecycle
---------------------

CREATED
    ↓
CONFIRMED
    ↓
CHECKED_IN
    ↓
COMPLETED

Alternative paths:

CREATED → CANCELLED

CREATED → EXPIRED

Notes
-----
A Reservation is NOT a Parking Session.

Once a customer checks in, the reservation is linked to a
ParkingSession, which manages the actual parking lifecycle.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)

from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.models.base_model import BaseModel

from app.models.enums import (
    Currency,
    ReservationPaymentStatus,
    ReservationStatus,
    VehicleType,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.parking_bay import ParkingBay
    from app.models.parking_session import ParkingSession
    from app.models.payment_transaction import PaymentTransaction

class ParkingReservation(BaseModel):
    """
    Parking Reservation entity.
    """

    __tablename__ = "parking_reservations"

    # ==========================================================
    # Identity
    # ==========================================================

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        
    )

    reservation_number: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        
    )

    # ==========================================================
    # Customer
    # ==========================================================

    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    # ==========================================================
    # Parking Bay
    # ==========================================================

    parking_bay_id: Mapped[int] = mapped_column(
        ForeignKey(
            "parking_bays.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        
    )

    # ==========================================================
    # Vehicle
    # ==========================================================

    vehicle_registration: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        
    )

    vehicle_type: Mapped[VehicleType] = mapped_column(
        Enum(
            VehicleType,
            name="vehicle_type",
        ),
        nullable=False,
    )

    # ==========================================================
    # Reservation Period
    # ==========================================================

    reserved_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        
    )

    reserved_until: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        
    )

    # ==========================================================
    # Pricing
    # ==========================================================

    estimated_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="KES",
        server_default="KES",
    )

    # ==========================================================
    # Reservation Status (DB Fields)
    # ==========================================================

    status: Mapped[ReservationStatus] = mapped_column(
        Enum(
            ReservationStatus,
            name="reservation_status_enum",
        ),
        nullable=False,
        default=ReservationStatus.CREATED,
        server_default=ReservationStatus.CREATED.value,
        
    )

    payment_status: Mapped[
        ReservationPaymentStatus
    ] = mapped_column(
        Enum(
            ReservationPaymentStatus,
            name="reservation_payment_status",
        ),
        default=ReservationPaymentStatus.PENDING,
        server_default="PENDING",
        nullable=False,
    )

    last_payment_transaction_id: Mapped[
        int | None
    ] = mapped_column(
        ForeignKey(
            "payment_transactions.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    paid_at: Mapped[
        datetime | None
    ] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ==========================================================
    # Reservation Lifecycle
    # ==========================================================

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    checked_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ==========================================================
    # Notes
    # ==========================================================

    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    # ==========================================================
    # Audit DB Fields
    # ==========================================================

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
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
    # Relationships
    # ==========================================================

    customer: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[customer_id],
        back_populates="parking_reservations",
    )

    parking_bay: Mapped["ParkingBay"] = relationship(
        "ParkingBay",
        back_populates="reservations",
    )

    parking_session: Mapped["ParkingSession | None"] = relationship(
        "ParkingSession",
        back_populates="reservation",
        uselist=False,
    )

    created_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[created_by],
    )

    updated_by_user: Mapped["User | None"] = relationship(
        "User",
        foreign_keys=[updated_by],
    )

    #
    # All payments made against this reservation
    #
    payments: Mapped[list["PaymentTransaction"]] = relationship(
        "PaymentTransaction",
        back_populates="reservation",
        foreign_keys="PaymentTransaction.reservation_id",
        cascade="save-update, merge",
    )

    #
    # Most recent successful payment
    #
    last_payment_transaction: Mapped[
        "PaymentTransaction | None"
    ] = relationship(
        "PaymentTransaction",
        foreign_keys=[last_payment_transaction_id],
        post_update=True,
    )

    # vehicle_id = mapped_column(
    # ForeignKey("vehicles.id"),
    # nullable=False,
    # )

    # vehicle = relationship(
    #     "Vehicle",
    #     back_populates="reservations",
    # )

    # ==========================================================
    # Table Indexes
    # ==========================================================

    __table_args__ = (

        # Reservation Number
        Index(
            "ix_parking_reservation_number",
            "reservation_number",
        ),

        # Customer
        Index(
            "ix_parking_reservation_customer",
            "customer_id",
        ),

        # Parking Bay
        Index(
            "ix_parking_reservation_bay",
            "parking_bay_id",
        ),

        # Vehicle Registration
        Index(
            "ix_parking_reservation_vehicle",
            "vehicle_registration",
        ),

        # Reservation Status
        Index(
            "ix_parking_reservation_status",
            "status",
        ),

        # Reservation Period
        Index(
            "ix_parking_reservation_period",
            "reserved_from",
            "reserved_until",
        ),

        # Bay Availability Lookups
        Index(
            "ix_parking_reservation_bay_period",
            "parking_bay_id",
            "reserved_from",
            "reserved_until",
        ),

        # Reservation Expiry
        Index(
            "ix_parking_reservation_expiry",
            "expires_at",
        ),

        # Payment Status
        Index(
            "ix_reservation_payment_status",
            "payment_status",
        ),

    )

    # ==========================================================
    # Helper Properties
    # ==========================================================

    @property
    def duration_minutes(self) -> int:
        """
        Return the reserved duration in minutes.
        """

        return int(
            (
                self.reserved_until
                - self.reserved_from
            ).total_seconds()
            // 60
        )

    @property
    def duration_hours(self) -> float:
        """
        Return the reserved duration in hours.
        """

        return round(
            self.duration_minutes / 60,
            2,
        )

    @property
    def is_expired(self) -> bool:
        """
        Determine whether the reservation has expired.
        """

        if self.expires_at is None:
            return False

        return datetime.utcnow() >= self.expires_at

    @property
    def is_active_reservation(self) -> bool:
        """
        Determine whether the reservation is currently active.

        Active reservations are those that have not yet been
        completed, cancelled or expired.
        """

        return (
            self.is_active
            and self.status
            in (
                ReservationStatus.CREATED,
                ReservationStatus.CONFIRMED,
            )
        )

    @property
    def has_checked_in(self) -> bool:
        """
        Indicates whether the customer has checked in.
        """

        return (
            self.status
            == ReservationStatus.CHECKED_IN
        )

    @property
    def is_completed(self) -> bool:
        """
        Indicates whether the reservation lifecycle
        has completed.
        """

        return (
            self.status
            == ReservationStatus.COMPLETED
        )

    @property
    def is_cancelled(self) -> bool:
        """
        Indicates whether the reservation was cancelled.
        """

        return (
            self.status
            == ReservationStatus.CANCELLED
        )

    @property
    def is_paid(self) -> bool:
        """
        Return True if the reservation
        has been fully paid.
        """

        return (
            self.payment_status
            == ReservationPaymentStatus.PAID
        )

    @property
    def can_check_in(self) -> bool:
        """
        Return True if the reservation
        can be checked in.
        """

        return (
            self.status == ReservationStatus.CONFIRMED
            and self.is_paid
        )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        """
        Developer-friendly representation.
        """

        return (
            f"<ParkingReservation("
            f"id={self.id}, "
            f"reservation_number='{self.reservation_number}', "
            f"status='{self.status.value}', "
            f"vehicle='{self.vehicle_registration}'"
            f")>"
        )

    def __str__(self) -> str:
        """
        Human-readable representation.
        """

        return (
            f"{self.reservation_number} "
            f"({self.vehicle_registration})"
        )