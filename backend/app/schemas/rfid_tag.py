"""
RFID Tag Schemas.

Defines request and response schemas for RFID tag management.

Business logic belongs in RFIDTagService.
Persistence belongs in RFIDTagRepository.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.enums import (
    BillingType,
)


# ==========================================================
# RFID Tag Create
# ==========================================================

class RFIDTagCreate(BaseModel):
    """
    Request schema for registering a new RFID tag.
    """

    uid: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique RFID tag UID.",
        examples=["04:A1:B2:C3:D4:E5:F6"],
    )


# ==========================================================
# RFID Tag Assignment
# ==========================================================

class RFIDTagAssign(BaseModel):
    """
    Request schema for assigning an RFID tag to a vehicle.
    """

    vehicle_id: int = Field(
        ...,
        gt=0,
        description="ID of the vehicle to assign the RFID tag to.",
        examples=[1],
    )


# ==========================================================
# RFID Tag Response
# ==========================================================

class RFIDTagResponse(BaseModel):
    """
    Response schema for an RFID tag.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    created_at: datetime
    updated_at: datetime
    uid: str
    vehicle_id: int | None
    is_active: bool


# ==========================================================
# RFID Tag With Vehicle Response
# ==========================================================

class RFIDTagVehicleResponse(BaseModel):
    """
    Response schema for an RFID tag together with its
    assigned vehicle reference.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    created_at: datetime
    updated_at: datetime
    uid: str
    vehicle_id: int | None
    is_active: bool


# ==========================================================
# RFID Tag Scan Request
# ==========================================================

class RFIDTagScanRequest(BaseModel):
    """
    Request schema representing a physical RFID reader event.

    The RFID reader supplies the tag UID captured during the
    physical scan.
    """

    uid: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="RFID UID captured by the physical reader.",
        examples=["04A82C91"],
    )


# ==========================================================
# RFID Tag Scan Response
# ==========================================================

class RFIDTagScanResponse(BaseModel):
    """
    Response schema returned after resolving an RFID reader event.

    The RFID UID is resolved through:

        RFID Tag
            ↓
        Vehicle
            ↓
        Registered Customer
    """

    rfid_tag: RFIDTagVehicleResponse

    vehicle_id: int

    registration_number: str

    vehicle_type: str

    customer_id: int | None

    customer_name: str


# ==========================================================
# RFID Parking Check-In Request
# ==========================================================

class RFIDParkingCheckInRequest(BaseModel):
    """
    Request schema for checking a registered vehicle into
    a parking facility using an RFID tag.

    The RFID UID identifies the vehicle and registered owner.
    """

    uid: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="RFID UID captured by the physical reader.",
        examples=["04:A1:B2:C3:D4:E5:F6"],
    )

    parking_bay_id: int = Field(
        ...,
        gt=0,
        description="Parking bay where the vehicle will be parked.",
        examples=[1],
    )

    billing_type: BillingType = Field(
        ...,
        description="Billing strategy used to calculate parking charges.",
    )

    expected_exit_time: datetime | None = Field(
        default=None,
        description="Expected vehicle exit time.",
    )

    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional notes for the parking session.",
    )


# ==========================================================
# RFID Parking Check-Out Request
# ==========================================================

class RFIDParkingCheckOutRequest(BaseModel):
    """
    Request schema for physically checking out a vehicle
    using an RFID tag.

    The RFID UID identifies the vehicle. The exit method is
    automatically recorded as RFID.
    """

    uid: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="RFID UID captured by the physical reader.",
        examples=["04:A1:B2:C3:D4:E5:F6"],
    )

    notes: str | None = Field(
        default=None,
        max_length=1000,
        description="Optional checkout notes.",
    )


# ==========================================================
# RFID Parking Check-Out Response
# ==========================================================

class RFIDParkingCheckOutResponse(BaseModel):
    """
    Response schema for an RFID parking check-out attempt.

    The backend remains authoritative for the current parking
    charge and wallet balance.

    The response allows the operator frontend to determine
    whether the vehicle was paid and checked out, or whether
    another payment method is required.
    """

    parking_session_id: int

    vehicle_id: int

    registration_number: str

    customer_id: int | None

    current_bill: Decimal

    wallet_balance: Decimal | None

    wallet_sufficient: bool

    payment_required: bool

    wallet_payment_successful: bool

    payment_transaction_id: int | None = None

    payment_reference: str | None = None

    checkout_completed: bool

    message: str

    model_config = ConfigDict(
        from_attributes=True,
    )