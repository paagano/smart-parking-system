from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.parking_facility import ParkingFacility

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    String,
)
from sqlalchemy.orm import (
    Mapped,
    mapped_column,
    relationship,
)

from app.models.base_model import BaseModel
from app.models.enums import QRAccessPurpose


class QRAccessToken(BaseModel):
    """
    Represents a temporary QR access token used to initiate
    QR-based parking entry or exit.

    The raw token is never stored in the database. The backend
    stores a SHA-256 hash of the token and returns the raw token
    only when generating the QR access URL.

    QR access flow:

        Operator QR Display
                ↓
        Temporary QR Token
                ↓
        Driver scans QR
                ↓
        Backend validates token
                ↓
        Registered / Guest access workflow
    """

    __tablename__ = "qr_access_tokens"

    # ==========================================================
    # Token
    # ==========================================================

    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )

    # ==========================================================
    # Facility
    # ==========================================================

    facility_id: Mapped[int] = mapped_column(
        ForeignKey(
            "parking_facilities.id",
            ondelete="CASCADE",
        ),
        index=True,
        nullable=False,
    )

    # ==========================================================
    # Purpose
    # ==========================================================

    purpose: Mapped[QRAccessPurpose] = mapped_column(
        Enum(
            QRAccessPurpose,
            name="qr_access_purpose",
        ),
        nullable=False,
        index=True,
    )

    # ==========================================================
    # Lifecycle
    # ==========================================================

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    # ==========================================================
    # Relationships
    # ==========================================================

    facility: Mapped["ParkingFacility"] = relationship(
        "ParkingFacility",
        back_populates="qr_access_tokens",
    )

    # ==========================================================
    # Representation
    # ==========================================================

    def __repr__(self) -> str:
        return (
            f"<QRAccessToken("
            f"id={self.id}, "
            f"facility_id={self.facility_id}, "
            f"purpose='{self.purpose.value}', "
            f"expires_at='{self.expires_at}', "
            f"is_active={self.is_active}"
            f")>"
        )