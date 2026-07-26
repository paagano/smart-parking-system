"""
Pydantic schemas for Parking Zone.

Parking Zones provide a flexible hierarchical structure for organising
parking facilities. Examples include:

Shopping Mall
    Basement B1
        Aisle A

Airport
    Terminal 1A
        Long Stay

City Parking
    CBD
        Moi Avenue
            Section A
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import ZoneType


# ==========================================================
# Base Schema
# ==========================================================


class ParkingZoneBase(BaseModel):
    """
    Shared Parking Zone fields.
    """

    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Human-readable zone name.",
        examples=["Basement B1"],
    )

    code: str = Field(
        ...,
        min_length=2,
        max_length=30,
        description="Unique zone code within a facility.",
        examples=["B1"],
    )

    zone_type: ZoneType = Field(
        ...,
        description="Type of parking zone.",
    )

    description: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional description.",
    )

    sort_order: int = Field(
        default=0,
        ge=0,
        description="Display order within parent zone.",
    )

    is_active: bool = Field(
        default=True,
        description="Whether the zone is active.",
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Zone name cannot be empty.")

        return value

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        value = value.strip().upper()

        if not value:
            raise ValueError("Zone code cannot be empty.")

        return value


# ==========================================================
# Create
# ==========================================================


class ParkingZoneCreate(ParkingZoneBase):
    """
    Schema for creating a Parking Zone.
    """

    facility_id: int = Field(
        ...,
        gt=0,
        description="Parent parking facility ID.",
    )

    parent_zone_id: Optional[int] = Field(
        default=None,
        gt=0,
        description="Optional parent zone ID.",
    )


# ==========================================================
# Update
# ==========================================================


class ParkingZoneUpdate(BaseModel):
    """
    Schema for updating a Parking Zone.
    """

    name: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    code: Optional[str] = Field(
        default=None,
        min_length=2,
        max_length=30,
    )

    zone_type: Optional[ZoneType] = None

    description: Optional[str] = Field(
        default=None,
        max_length=500,
    )

    sort_order: Optional[int] = Field(
        default=None,
        ge=0,
    )

    is_active: Optional[bool] = None

    parent_zone_id: Optional[int] = Field(
        default=None,
        gt=0,
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = value.strip()

        if not value:
            raise ValueError("Zone name cannot be empty.")

        return value

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return value

        value = value.strip().upper()

        if not value:
            raise ValueError("Zone code cannot be empty.")

        return value


# ==========================================================
# Response
# ==========================================================


class ParkingZoneResponse(ParkingZoneBase):
    """
    Parking Zone returned by the API.
    """

    id: int

    facility_id: int

    parent_zone_id: Optional[int]

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ==========================================================
# Tree Response
# ==========================================================


class ParkingZoneTreeResponse(ParkingZoneResponse):
    """
    Recursive Parking Zone tree.
    """

    children: List["ParkingZoneTreeResponse"] = Field(
        default_factory=list
    )


ParkingZoneTreeResponse.model_rebuild()


# ==========================================================
# List Response
# ==========================================================


class ParkingZoneListResponse(BaseModel):
    """
    Parking Zone list response.
    """

    total: int

    items: List[ParkingZoneResponse]