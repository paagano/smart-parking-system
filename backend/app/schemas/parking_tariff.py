"""
Parking Tariff Schemas.

Pydantic schemas for Parking Tariff CRUD operations.

These schemas define the API contract between the client and the
backend while keeping the persistence model isolated.

Future extensions supported:

- Dynamic pricing
- Membership pricing
- Promotional pricing
- Subscription pricing
- AI-driven pricing
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.models.enums import (
    BillingType,
    VehicleType,
)


# ==========================================================
# Common Decimal Type
# ==========================================================

Money = Annotated[
    Decimal,
    Field(
        max_digits=10,
        decimal_places=2,
        ge=0,
    ),
]


# ==========================================================
# Base Schema
# ==========================================================

class ParkingTariffBase(BaseModel):
    """
    Common Parking Tariff fields.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        examples=["Standard Hourly Parking"],
    )

    code: str = Field(
        ...,
        min_length=2,
        max_length=50,
        examples=["STD_HOURLY"],
    )

    display_order: int = Field(
        default=1,
        ge=1,
    )

    pricing_priority: int = Field(
        default=100,
        ge=1,
    )

    vehicle_type: VehicleType

    billing_type: BillingType

    currency: str = Field(
        default="KES",
        min_length=3,
        max_length=3,
    )

    grace_period_minutes: int = Field(
        default=0,
        ge=0,
    )

    minimum_charge: Money | None = Field(
        default=None,
        ge=0,
    )

    hourly_rate: Money | None = Field(
        default=None,
        ge=0,
    )

    daily_rate: Money | None = Field(
        default=None,
        ge=0,
    )

    flat_rate: Money | None = Field(
        default=None,
        ge=0,
    )

    max_daily_charge: Money | None = Field(
        default=None,
        ge=0,
    )

    effective_from: datetime

    effective_to: datetime | None = None

    is_active: bool = True

    notes: str | None = Field(
        default=None,
        max_length=5000,
    )

    # ------------------------------------------------------
    # Field Validators
    # ------------------------------------------------------

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return value.upper()

    @field_validator("effective_to")
    @classmethod
    def validate_effective_dates(
        cls,
        value: datetime | None,
        info,
    ) -> datetime | None:
        if (
            value is not None
            and "effective_from" in info.data
            and value <= info.data["effective_from"]
        ):
            raise ValueError(
                "effective_to must be after effective_from."
            )

        return value

# ==========================================================
# Business Validators
# ==========================================================

@model_validator(mode="after")
def validate_business_rules(self):

    if (
        self.billing_type == BillingType.HOURLY
        and self.hourly_rate is None
    ):
        raise ValueError(
            "hourly_rate is required for HOURLY tariffs."
        )

    if (
        self.billing_type == BillingType.DAILY
        and self.daily_rate is None
    ):
        raise ValueError(
            "daily_rate is required for DAILY tariffs."
        )

    if (
        self.billing_type == BillingType.FLAT
        and self.flat_rate is None
    ):
        raise ValueError(
            "flat_rate is required for FLAT tariffs."
        )

    if (
        self.daily_rate is not None
        and self.max_daily_charge is not None
        and self.max_daily_charge < self.daily_rate
    ):
        raise ValueError(
            "max_daily_charge cannot be less than daily_rate."
        )

    if self.minimum_charge is not None:

        applicable_rate = {
            BillingType.HOURLY: self.hourly_rate,
            BillingType.DAILY: self.daily_rate,
            BillingType.FLAT: self.flat_rate,
        }.get(self.billing_type)

        if (
            applicable_rate is not None
            and self.minimum_charge > applicable_rate
        ):
            raise ValueError(
                "minimum_charge cannot exceed the applicable tariff rate."
            )

    return self

# ==========================================================
# Create
# ==========================================================

class ParkingTariffCreate(ParkingTariffBase):
    """
    Schema used when creating a tariff.
    """
    pass


# ==========================================================
# Update
# ==========================================================

class ParkingTariffUpdate(BaseModel):
    """
    Schema used when updating a tariff.

    All fields are optional.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    code: str | None = Field(
        default=None,
        min_length=2,
        max_length=50,
    )

    display_order: int | None = Field(
        default=None,
        ge=1,
    )

    pricing_priority: int | None = Field(
        default=None,
        ge=1,
    )

    vehicle_type: VehicleType | None = None

    billing_type: BillingType | None = None

    currency: str | None = Field(
        default=None,
        min_length=3,
        max_length=3,
    )

    grace_period_minutes: int | None = Field(
        default=None,
        ge=0,
    )

    minimum_charge: Money | None = Field(
        default=None,
        ge=0,
    )

    hourly_rate: Money | None = Field(
        default=None,
        ge=0,
    )

    daily_rate: Money | None = Field(
        default=None,
        ge=0,
    )

    flat_rate: Money | None = Field(
        default=None,
        ge=0,
    )

    max_daily_charge: Money | None = Field(
        default=None,
        ge=0,
    )

    effective_from: datetime | None = None

    effective_to: datetime | None = None

    is_active: bool | None = None

    notes: str | None = Field(
        default=None,
        max_length=5000,
    )

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        if value is None:
            return value

        return value.upper()


# ==========================================================
# Response
# ==========================================================

class ParkingTariffResponse(ParkingTariffBase):
    """
    Parking Tariff returned to clients.
    """

    id: int

    created_by: int | None

    updated_by: int | None

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
    from_attributes=True,
    extra="forbid",
    )


# ==========================================================
# List Response
# ==========================================================

class ParkingTariffListResponse(BaseModel):
    """
    List of parking tariffs.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    items: list[ParkingTariffResponse]

    total: int