"""
QR Access Token Schemas.

Defines request and response schemas for temporary
QR-based parking access tokens.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import QRAccessPurpose


class QRAccessTokenCreate(BaseModel):
    """
    Request to generate a temporary QR access token.
    """

    purpose: QRAccessPurpose
    expires_in_seconds: int = Field(
        default=300,
        gt=0,
        le=3600,
        description="QR token validity period in seconds.",
    )


class QRAccessTokenResponse(BaseModel):
    """
    Public representation of a QR access token record.

    The raw token is intentionally excluded because it is
    only returned at token generation time.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int
    facility_id: int
    purpose: QRAccessPurpose
    expires_at: datetime
    is_active: bool
    created_at: datetime
    updated_at: datetime


class QRAccessTokenDisplayResponse(QRAccessTokenResponse):
    """
    Response returned when generating a QR access token
    for display by the operator portal.

    raw_token is returned only at creation time.
    qr_url is the URL encoded into the QR code.
    """

    raw_token: str
    qr_url: str


class QRAccessTokenResolveRequest(BaseModel):
    """
    Request submitted by a driver/mobile client after
    scanning a QR code.
    """

    token: str = Field(
        min_length=1,
        description="Opaque QR access token obtained from the QR code.",
    )


class QRAccessTokenResolveResponse(BaseModel):
    """
    Result of resolving a QR access token.
    """

    valid: bool
    facility_id: int
    purpose: QRAccessPurpose
    expires_at: datetime
    message: str


class QRAccessEntryIdentifyRequest(BaseModel):
    """
    Request submitted by a driver/mobile client after
    scanning an ENTRY QR code and entering a vehicle
    registration number.
    """

    token: str = Field(
        min_length=1,
        description="Opaque QR access token obtained from the QR code.",
    )

    registration_number: str = Field(
        min_length=1,
        description="Vehicle registration number entered by the driver.",
    )


class QRAccessEntryIdentifyResponse(BaseModel):
    """
    Result of identifying a vehicle for QR-based entry.

    This endpoint only identifies the vehicle and determines
    whether it is registered. It does not authenticate the
    driver or create a parking session.
    """

    valid: bool
    facility_id: int
    purpose: QRAccessPurpose
    expires_at: datetime
    registration_number: str
    vehicle_id: int | None
    registered: bool
    vehicle_active: bool
    message: str