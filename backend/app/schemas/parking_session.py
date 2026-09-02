"""
Pydantic schemas for Parking Sessions.

These schemas define the request and response contracts for the
Parking Session API.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import (
    BillingType,
    EntryMethod,
    ExitMethod,
    PaymentStatus,
    SessionPaymentStatus,
    SessionSource,
    SessionStatus,
    VehicleType,
)


# ==========================================================
# Base Schema
# ==========================================================
class ParkingSessionBase(BaseModel):
    """
    Common Parking Session fields.

    A session may use either:

    1. A registered vehicle identified by vehicle_id.
    2. A borrowed/unregistered vehicle identified by
       vehicle_registration and vehicle_type.

    vehicle_id and vehicle_registration/vehicle_type are
    therefore mutually exclusive at the API boundary.
    """

    parking_bay_id: int = Field(
        ...,
        gt=0,
    )

    customer_id: Optional[int] = Field(
        default=None,
        gt=0,
        description=(
            "Registered customer responsible for the session. "
            "Leave null for guest walk-ins."
        ),
    )

    vehicle_id: Optional[int] = Field(
        default=None,
        gt=0,
        description=(
            "Registered vehicle identifier. "
            "Leave blank if using a borrowed or unregistered vehicle."
        ),
    )

    vehicle_registration: Optional[str] = Field(
        default=None,
        min_length=3,
        max_length=20,
        description=(
            "Vehicle registration number. "
            "Required when vehicle_id is not supplied."
        ),
    )

    vehicle_type: Optional[VehicleType] = Field(
        default=None,
        description=(
            "Vehicle type. Required when vehicle_id is not supplied."
        ),
    )

    billing_type: BillingType = Field(
        ...,
        description=(
            "Billing strategy used to calculate parking charges. "
            "Supported values: HOURLY, DAILY, FLAT."
        ),
    )

    session_source: SessionSource

    entry_method: EntryMethod

    expected_exit_time: Optional[datetime] = None

    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
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
            return None

        value = value.strip().upper()

        if not value:
            raise ValueError(
                "Vehicle registration cannot be blank."
            )

        return value

    @model_validator(mode="after")
    def validate_vehicle_reference(
        self,
    ) -> "ParkingSessionBase":
        """
        Validate the vehicle representation supplied
        for the parking session.

        Registered vehicle:
            vehicle_id is supplied.
            Registration and vehicle type are resolved
            from the registered Vehicle record.

        Borrowed/unregistered vehicle:
            vehicle_id is null.
            vehicle_registration and vehicle_type are required.
        """

        if self.vehicle_id is not None:
            if (
                self.vehicle_registration is not None
                or self.vehicle_type is not None
            ):
                raise ValueError(
                    "When vehicle_id is provided, "
                    "vehicle_registration and vehicle_type "
                    "must not be provided."
                )

            return self

        if not self.vehicle_registration:
            raise ValueError(
                "vehicle_registration is required when "
                "vehicle_id is not provided."
            )

        if self.vehicle_type is None:
            raise ValueError(
                "vehicle_type is required when "
                "vehicle_id is not provided."
            )

        return self

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
        str_strip_whitespace=True,
    )


# ==========================================================
# Create
# ==========================================================
class ParkingSessionCreate(ParkingSessionBase):
    """Schema used when creating a parking session."""

    pass


# ==========================================================
# Update
# ==========================================================
class ParkingSessionUpdate(BaseModel):
    """
    Schema used when updating a parking session.

    Only fields that are safe for users to modify are exposed.
    System-managed fields such as status, exit time, duration,
    fees and payment information are updated through dedicated
    business workflows.
    """

    parking_bay_id: Optional[int] = Field(
        None,
        gt=0,
    )

    vehicle_registration: Optional[str] = Field(
        None,
        min_length=3,
        max_length=20,
    )

    vehicle_type: Optional[VehicleType] = None

    session_source: Optional[SessionSource] = None

    entry_method: Optional[EntryMethod] = None

    expected_exit_time: Optional[datetime] = None

    notes: Optional[str] = Field(
        None,
        max_length=1000,
    )


# ==========================================================
# Response
# ==========================================================
class ParkingSessionResponse(BaseModel):
    """Schema returned by the Parking Session API."""

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    parking_bay_id: int

    customer_id: Optional[int] = None

    vehicle_id: Optional[int] = None

    vehicle_registration: str

    vehicle_type: VehicleType

    billing_type: BillingType

    session_source: SessionSource

    entry_method: EntryMethod

    expected_exit_time: Optional[datetime] = None

    notes: Optional[str] = None

    session_number: str

    status: SessionStatus

    exit_method: Optional[ExitMethod] = None

    entry_time: datetime

    exit_time: Optional[datetime] = None

    duration_minutes: Optional[int] = None

    calculated_amount: Decimal

    paid_amount: Decimal

    payment_status: SessionPaymentStatus

    created_by: Optional[int] = None

    updated_by: Optional[int] = None

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Quote Response
# ==========================================================
class ParkingSessionQuoteResponse(BaseModel):
    """
    Live pricing quote for an active parking session.

    This is a read-only calculation and is not persisted
    to the parking session.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    tariff_id: int

    tariff_name: str

    billing_type: BillingType

    duration_minutes: int

    billable_minutes: int

    grace_period_applied: bool

    base_amount: Decimal

    discount_amount: Decimal = Decimal("0.00")

    tax_amount: Decimal = Decimal("0.00")

    total_amount: Decimal

    calculated_at: datetime


# ==========================================================
# List Response
# ==========================================================
class ParkingSessionListResponse(BaseModel):
    """
    Parking Session list response.

    Pagination will be added later.
    """

    items: list[ParkingSessionResponse]

    total: int


# ==========================================================
# Checkout
# ==========================================================
class ParkingSessionCheckout(BaseModel):
    """
    Vehicle checkout request.
    """

    vehicle_registration: str

    exit_method: ExitMethod

    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
    )