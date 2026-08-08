"""
Vehicle Schemas.

Pydantic schemas used for Vehicle API requests and responses.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.enums import (
    ParkingProfile,
    VehicleType,
)


# ==========================================================
# Base Vehicle Schema
# ==========================================================

class VehicleBase(
    BaseModel,
):
    """
    Common Vehicle fields.
    """

    plate_country: str = Field(
        default="KE",
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code.",
    )

    registration_number: str = Field(
        min_length=1,
        max_length=20,
        description="Vehicle registration number.",
    )

    nickname: str | None = Field(
        default=None,
        max_length=100,
        description="Optional friendly name for the vehicle.",
    )

    make: str = Field(
        min_length=1,
        max_length=100,
        description="Vehicle make.",
    )

    model: str = Field(
        min_length=1,
        max_length=100,
        description="Vehicle model.",
    )

    colour: str | None = Field(
        default=None,
        max_length=50,
        description="Vehicle colour.",
    )

    year: int | None = Field(
        default=None,
        ge=1886,
        le=2100,
        description="Vehicle manufacture year.",
    )

    vehicle_type: VehicleType = Field(
        description="Vehicle type.",
    )

    parking_profile: ParkingProfile = Field(
        default=ParkingProfile.STANDARD,
        description="Smart parking profile.",
    )


# ==========================================================
# Create Vehicle
# ==========================================================

class VehicleCreate(
    VehicleBase,
):
    """
    Create a new vehicle.

    customer_id is deliberately not supplied by the client.
    The authenticated customer will be used by the service
    layer when ownership is established.
    """

    is_default: bool = Field(
        default=False,
        description="Whether this should be the customer's default vehicle.",
    )


# ==========================================================
# Update Vehicle
# ==========================================================

class VehicleUpdate(
    BaseModel,
):
    """
    Update an existing vehicle.

    All fields are optional so that partial updates are
    supported.
    """

    plate_country: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        description="ISO 3166-1 alpha-2 country code.",
    )

    registration_number: str | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        description="Vehicle registration number.",
    )

    nickname: str | None = Field(
        default=None,
        max_length=100,
        description="Optional friendly name for the vehicle.",
    )

    make: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Vehicle make.",
    )

    model: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Vehicle model.",
    )

    colour: str | None = Field(
        default=None,
        max_length=50,
        description="Vehicle colour.",
    )

    year: int | None = Field(
        default=None,
        ge=1886,
        le=2100,
        description="Vehicle manufacture year.",
    )

    vehicle_type: VehicleType | None = Field(
        default=None,
        description="Vehicle type.",
    )

    parking_profile: ParkingProfile | None = Field(
        default=None,
        description="Smart parking profile.",
    )


# ==========================================================
# Vehicle Response
# ==========================================================

class VehicleResponse(
    VehicleBase,
):
    """
    Vehicle API response.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    customer_id: int | None

    is_default: bool

    is_active: bool

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Vehicle List Response
# ==========================================================

class VehicleListResponse(
    BaseModel,
):
    """
    Response containing a customer's vehicles.
    """

    vehicles: list[VehicleResponse]

    total: int