from datetime import datetime, time

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import FacilityType


# ==========================================================
# Base Schema
# ==========================================================

class ParkingFacilityBase(BaseModel):
    """
    Base schema shared by Parking Facility requests.
    """

    name: str = Field(
        ...,
        min_length=3,
        max_length=150,
        description="Display name of the parking facility.",
        examples=["Two Rivers Mall"],
    )

    code: str = Field(
        ...,
        min_length=2,
        max_length=30,
        description="Unique business code.",
        examples=["TRM"],
    )

    facility_type: FacilityType = Field(
        ...,
        description="Category of parking facility.",
    )

    description: str | None = Field(
        default=None,
        max_length=1000,
    )

    country: str = Field(
        default="Kenya",
        min_length=2,
        max_length=100,
    )

    county: str = Field(
        ...,
        min_length=2,
        max_length=100,
    )

    city: str = Field(
        ...,
        min_length=2,
        max_length=100,
    )

    address: str = Field(
        ...,
        min_length=5,
        max_length=255,
    )

    postal_code: str | None = Field(
        default=None,
        max_length=20,
    )

    latitude: float = Field(
        ...,
        ge=-90,
        le=90,
        description="Latitude in decimal degrees.",
        examples=[-1.292066],
    )

    longitude: float = Field(
        ...,
        ge=-180,
        le=180,
        description="Longitude in decimal degrees.",
        examples=[36.821945],
    )

    timezone: str = Field(
        default="Africa/Nairobi",
        max_length=50,
    )

    opening_time: time

    closing_time: time

    is_active: bool = True

    # ==========================================================
    # Validators
    # ==========================================================

    @field_validator(
        "name",
        "country",
        "county",
        "city",
        "address",
        "postal_code",
        mode="before",
    )
    @classmethod
    def strip_strings(cls, value):
        """
        Remove leading and trailing whitespace.
        """

        if value is None:
            return value

        return value.strip()

    @field_validator(
        "code",
        mode="before",
    )
    @classmethod
    def normalize_code(cls, value: str) -> str:
        """
        Normalize facility code.
        """

        return value.strip().upper()

    @model_validator(mode="after")
    def validate_operating_hours(self):
        """
        Ensure opening time is before closing time.
        """

        if self.opening_time >= self.closing_time:
            raise ValueError(
                "Opening time must be earlier than closing time."
            )

        return self


# ==========================================================
# Create
# ==========================================================

class ParkingFacilityCreate(ParkingFacilityBase):
    """
    Request schema for creating a parking facility.
    """

    pass


# ==========================================================
# Update
# ==========================================================

class ParkingFacilityUpdate(BaseModel):
    """
    Request schema for updating a parking facility.

    All fields are optional.
    """

    name: str | None = Field(
        None,
        min_length=3,
        max_length=150,
    )

    code: str | None = Field(
        None,
        min_length=2,
        max_length=30,
    )

    facility_type: FacilityType | None = None

    description: str | None = Field(
        None,
        max_length=1000,
    )

    country: str | None = Field(
        None,
        max_length=100,
    )

    county: str | None = Field(
        None,
        max_length=100,
    )

    city: str | None = Field(
        None,
        max_length=100,
    )

    address: str | None = Field(
        None,
        max_length=255,
    )

    postal_code: str | None = Field(
        None,
        max_length=20,
    )

    latitude: float | None = Field(
        None,
        ge=-90,
        le=90,
    )

    longitude: float | None = Field(
        None,
        ge=-180,
        le=180,
    )

    timezone: str | None = Field(
        None,
        max_length=50,
    )

    opening_time: time | None = None

    closing_time: time | None = None

    is_active: bool | None = None

    @field_validator(
        "name",
        "country",
        "county",
        "city",
        "address",
        "postal_code",
        mode="before",
    )
    @classmethod
    def strip_strings(cls, value):
        if value is None:
            return value

        return value.strip()

    @field_validator(
        "code",
        mode="before",
    )
    @classmethod
    def normalize_code(cls, value):
        if value is None:
            return value

        return value.strip().upper()

    @model_validator(mode="after")
    def validate_operating_hours(self):
        if (
            self.opening_time is not None
            and self.closing_time is not None
            and self.opening_time >= self.closing_time
        ):
            raise ValueError(
                "Opening time must be earlier than closing time."
            )

        return self


# ==========================================================
# Response
# ==========================================================

class ParkingFacilityResponse(ParkingFacilityBase):
    """
    Response schema returned to API clients.

    Existing facilities in the database may have incomplete
    geographic/location information. Those fields are therefore
    nullable in API responses.

    IMPORTANT:
    ParkingFacilityCreate continues to require these fields.
    This change only affects responses returned to clients.
    """

    id: int

    # ----------------------------------------------------------
    # Existing database records may not yet have these values.
    # ----------------------------------------------------------

    county: str | None = Field(
        default=None,
        max_length=100,
    )

    address: str | None = Field(
        default=None,
        max_length=255,
    )

    latitude: float | None = Field(
        default=None,
        ge=-90,
        le=90,
        description="Latitude in decimal degrees, when available.",
    )

    longitude: float | None = Field(
        default=None,
        ge=-180,
        le=180,
        description="Longitude in decimal degrees, when available.",
    )

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True,
    )


# ==========================================================
# List Response
# ==========================================================

class ParkingFacilityListResponse(BaseModel):
    """
    Response returned when listing parking facilities.
    """

    total: int

    items: list[ParkingFacilityResponse]