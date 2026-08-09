"""
Parking Reservation Schemas

Pydantic schemas for Parking Reservation API.

These schemas define the API contract between clients
and the Reservation module.

The Reservation Service owns the business rules while
these schemas are responsible for validation and
serialization.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import (
    ReservationStatus,
    VehicleType,
)


# ==========================================================
# Base Schema
# ==========================================================

class ReservationBase(BaseModel):
    """
    Base Reservation schema.

    Shared by Create and Update schemas.
    """

    parking_bay_id: int = Field(
        ...,
        gt=0,
        description="Parking Bay identifier.",
    )

    vehicle_id: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Registered vehicle identifier. "
            "Leave null when using a borrowed vehicle."
        ),
    )

    vehicle_registration: str | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description=(
            "Vehicle registration number. "
            "Required when using a borrowed vehicle."
        ),
        examples=["KDK123A"],
    )

    vehicle_type: VehicleType | None = Field(
        default=None,
        description=(
            "Vehicle type. "
            "Required when using a borrowed vehicle."
        ),
    )

    reserved_from: datetime = Field(
        ...,
        description="Reservation start time.",
    )

    reserved_until: datetime = Field(
        ...,
        description="Reservation end time.",
    )

    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional reservation notes.",
    )

    # ==========================================================
    # Validation
    # ==========================================================

    @field_validator("vehicle_registration")
    @classmethod
    def validate_vehicle_registration(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Normalize vehicle registration when supplied.
        """

        if value is None:
            return None

        value = value.strip().upper()

        if not value:
            raise ValueError(
                "Vehicle registration cannot be blank."
            )

        return value

    @model_validator(mode="after")
    def validate_vehicle_selection(
        self,
    ) -> "ReservationBase":
        """
        Validate the vehicle selection mode.

        Registered vehicle:
            vehicle_id is supplied.

        Borrowed vehicle:
            vehicle_id is null and both registration and
            vehicle_type are supplied.
        """

        # ------------------------------------------------------
        # Registered vehicle
        # ------------------------------------------------------

        if self.vehicle_id is not None:

            if (
                self.vehicle_registration is not None
                or self.vehicle_type is not None
            ):
                raise ValueError(
                    "When vehicle_id is provided, "
                    "vehicle_registration and vehicle_type "
                    "must not be supplied."
                )

            return self

        # ------------------------------------------------------
        # Borrowed vehicle
        # ------------------------------------------------------

        if self.vehicle_registration is None:
            raise ValueError(
                "Vehicle registration is required when "
                "vehicle_id is not provided."
            )

        if self.vehicle_type is None:
            raise ValueError(
                "Vehicle type is required when "
                "vehicle_id is not provided."
            )

        return self

    @model_validator(mode="after")
    def validate_reservation_period(
        self,
    ) -> "ParkingReservationUpdate":
        """
        Validate reservation period and vehicle changes.
        """

        if (
            self.reserved_from is not None
            and self.reserved_until is not None
            and self.reserved_until <= self.reserved_from
        ):
            raise ValueError(
                "reserved_until must be later than reserved_from."
            )

        # ======================================================
        # Temporary Vehicle Validation
        # ======================================================

        if (
            "vehicle_id" in self.model_fields_set
            and self.vehicle_id is None
        ):
            if not self.vehicle_registration:
                raise ValueError(
                    "vehicle_registration is required "
                    "when switching to a temporary vehicle."
                )

            if self.vehicle_type is None:
                raise ValueError(
                    "vehicle_type is required "
                    "when switching to a temporary vehicle."
                )

        return self

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        str_strip_whitespace=True,
        extra="forbid",
    )

# ==========================================================
# Create
# ==========================================================

class ParkingReservationCreate(ReservationBase):
    """
    Schema used when creating a parking reservation.
    """
    pass


# ==========================================================
# Update
# ==========================================================

class ParkingReservationUpdate(BaseModel):
    """
    Schema used for updating a reservation.

    Only editable reservation fields are exposed.
    Business-controlled fields such as reservation number,
    status, estimated amount and expiry timestamps are
    intentionally excluded.
    """

    parking_bay_id: int | None = Field(
        default=None,
        gt=0,
        description="Parking Bay identifier.",
    )

    vehicle_id: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Registered vehicle identifier. "
            "Leave null when using a temporary/borrowed vehicle."
        ),
    )

    vehicle_registration: str | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="Vehicle registration number.",
    )

    vehicle_type: VehicleType | None = Field(
        default=None,
        description="Vehicle type.",
    )

    reserved_from: datetime | None = Field(
        default=None,
        description="Reservation start time.",
    )

    reserved_until: datetime | None = Field(
        default=None,
        description="Reservation end time.",
    )

    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Reservation notes.",
    )

    @field_validator("vehicle_registration")
    @classmethod
    def normalize_vehicle_registration(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Normalize vehicle registration.
        """

        if value is None:
            return value

        value = value.strip().upper()

        if not value:
            raise ValueError(
                "Vehicle registration cannot be blank."
            )

        return value

    @model_validator(mode="after")
    def validate_reservation_period(
        self,
    ) -> "ParkingReservationUpdate":
        """
        Validate reservation period when both dates
        are supplied.
        """

        if (
            self.reserved_from is not None
            and self.reserved_until is not None
            and self.reserved_until <= self.reserved_from
        ):
            raise ValueError(
                "reserved_until must be later than reserved_from."
            )

        return self

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        str_strip_whitespace=True,
    )

# ==========================================================
# Response
# ==========================================================

class ParkingReservationResponse(BaseModel):
    """
    Reservation response returned by the API.
    """

    id: int

    reservation_number: str

    customer_id: int | None = None

    parking_bay_id: int

    vehicle_id: int | None = None

    vehicle_registration: str

    vehicle_type: VehicleType

    reserved_from: datetime

    reserved_until: datetime

    estimated_amount: Decimal | None

    currency: str

    status: ReservationStatus

    expires_at: datetime | None

    confirmed_at: datetime | None

    checked_in_at: datetime | None

    completed_at: datetime | None

    cancelled_at: datetime | None

    notes: str | None

    is_active: bool

    created_at: datetime

    updated_at: datetime

    created_by: int | None

    updated_by: int | None

    model_config = ConfigDict(
        from_attributes=True,
    )

# ==========================================================
# List Response
# ==========================================================

class ParkingReservationListResponse(BaseModel):
    """
    Paginated-style response for parking reservations.

    Used by endpoints returning multiple reservations.
    """

    items: list[ParkingReservationResponse] = Field(
        default_factory=list,
        description="List of parking reservations.",
    )

    total: int = Field(
        ...,
        ge=0,
        description="Total number of reservations returned.",
    )

    model_config = ConfigDict(
        from_attributes=True,
    )