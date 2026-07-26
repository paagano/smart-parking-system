from sqlalchemy import Boolean, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base_model import BaseModel
from app.models.enums import FacilityType


class ParkingFacility(BaseModel):
    """
    Represents a parking facility.

    A parking facility is the highest-level physical location within the
    SmartPark AI platform. It may represent a shopping mall, airport,
    university, hospital, office complex, residential estate, municipal
    parking area, or any other managed parking location.

    A facility contains one or more hierarchical Parking Zones.
    """

    __tablename__ = "parking_facilities"

    # ==========================================================
    # Facility Details
    # ==========================================================

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
        unique=True,
        index=True,
    )

    code: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        unique=True,
        index=True,
    )

    facility_type: Mapped[FacilityType] = mapped_column(
        Enum(
            FacilityType,
            name="facility_type",
        ),
        nullable=False,
    )

    address: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    city: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    county: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    country: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="Kenya",
    )

    latitude: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    longitude: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    zones: Mapped[list["ParkingZone"]] = relationship(
        "ParkingZone",
        back_populates="facility",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<ParkingFacility("
            f"id={self.id}, "
            f"name='{self.name}', "
            f"code='{self.code}', "
            f"type='{self.facility_type.value}'"
            f")>"
        )