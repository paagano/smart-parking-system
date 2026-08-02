"""
Pydantic schemas for Parking Sessions.

These schemas define the request and response contracts for the
Parking Session API.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    EntryMethod,
    ExitMethod,
    PaymentStatus,
    SessionSource,
    SessionStatus,
    VehicleType,
)


# ==========================================================
# Base Schema
# ==========================================================


class ParkingSessionBase(BaseModel):
    """Common Parking Session fields."""

    parking_bay_id: int = Field(..., gt=0)

    customer_id: Optional[int] = Field(
    default=None,
    gt=0,
    description="Registered customer. Leave null for guest walk-ins.",
    )

    vehicle_registration: str = Field(
        ...,
        min_length=3,
        max_length=20,
        description="Vehicle registration number.",
    )

    vehicle_type: VehicleType

    session_source: SessionSource

    entry_method: EntryMethod

    expected_exit_time: Optional[datetime] = None

    notes: Optional[str] = Field(
        default=None,
        max_length=1000,
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


class ParkingSessionResponse(ParkingSessionBase):
    """Schema returned by the API."""

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    session_number: str

    status: SessionStatus

    exit_method: Optional[ExitMethod] = None

    entry_time: datetime

    exit_time: Optional[datetime] = None

    duration_minutes: Optional[int] = None

    calculated_amount: Decimal

    paid_amount: Decimal

    payment_status: PaymentStatus

    created_by: Optional[int] = None

    updated_by: Optional[int] = None

    created_at: datetime

    updated_at: datetime


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