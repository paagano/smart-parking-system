"""
Pydantic schemas for Parking Bays.

A Parking Bay represents an individual parking space within a Parking Zone.

Hierarchy:

Parking Facility
    └── Parking Zone
            └── Parking Bay

Parking Bays are relatively static master data. Dynamic information such as
occupancy, reservations, and active parking sessions are managed in their
respective modules.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    BaySize,
    BayType,
    VehicleType,
)


# ==========================================================
# Base Schema
# ==========================================================


class ParkingBayBase(BaseModel):
    """
    Shared Parking Bay fields.
    """

    bay_number: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Human-readable parking bay number.",
        examples=["A01"],
    )

    code: str = Field(
        ...,
        min_length=2,
        max_length=30,
        description="Unique internal parking bay code.",
        examples=["BAY-A01"],
    )

    bay_type: BayType = Field(
        ...,
        description="Classification of the parking bay.",
    )

    vehicle_type: VehicleType = Field(
        ...,
        description="Vehicle category permitted to use the bay.",
    )

    size: BaySize = Field(
        ...,
        description="Physical size classification.",
    )

    is_accessible: bool = Field(
        default=False,
        description="Whether the bay is accessible.",
    )

    is_ev_charging: bool = Field(
        default=False,
        description="Whether the bay has EV charging.",
    )

    is_vip: bool = Field(
        default=False,
        description="Whether the bay is VIP.",
    )

    is_reservable: bool = Field(
        default=True,
        description="Whether the bay can be reserved.",
    )

    is_active: bool = Field(
        default=True,
        description="Whether the bay is active.",
    )

    sort_order: int = Field(
        default=0,
        ge=0,
        description="Display order within the zone.",
    )

    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional description.",
    )

    @field_validator("bay_number")
    @classmethod
    def validate_bay_number(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("Bay number cannot be empty.")

        return value

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("Bay code cannot be empty.")

        return value


# ==========================================================
# Create
# ==========================================================


class ParkingBayCreate(ParkingBayBase):
    """
    Schema for creating a Parking Bay.
    """

    zone_id: int = Field(
        ...,
        gt=0,
        description="Parent Parking Zone ID.",
    )


# ==========================================================
# Update
# ==========================================================


class ParkingBayUpdate(BaseModel):
    """
    Schema for updating a Parking Bay.
    """

    bay_number: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=20,
    )

    code: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=30,
    )

    bay_type: Optional[BayType] = None

    vehicle_type: Optional[VehicleType] = None

    size: Optional[BaySize] = None

    is_accessible: Optional[bool] = None

    is_ev_charging: Optional[bool] = None

    is_vip: Optional[bool] = None

    is_reservable: Optional[bool] = None

    is_active: Optional[bool] = None

    sort_order: Optional[int] = Field(
        default=None,
        ge=0,
    )

    description: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    @field_validator("bay_number")
    @classmethod
    def validate_bay_number(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = value.strip().upper()

        if not value:
            raise ValueError("Bay number cannot be empty.")

        return value

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = value.strip().upper()

        if not value:
            raise ValueError("Bay code cannot be empty.")

        return value


# ==========================================================
# Response
# ==========================================================


class ParkingBayResponse(ParkingBayBase):
    """
    Parking Bay returned by the API.
    """

    id: int

    zone_id: int

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================================
# List Response
# ==========================================================


class ParkingBayListResponse(BaseModel):
    """
    Parking Bay list response.
    """

    total: int

    items: list[ParkingBayResponse]