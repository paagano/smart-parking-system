"""
Loyalty Referral Schemas.

Pydantic schemas for the SmartPark Loyalty Referral
Programme.

Business rules belong in LoyaltyReferralService.

Persistence belongs in LoyaltyReferralRepository.

Customer identity is intentionally NOT supplied by
customer-facing requests. The authenticated customer is
resolved by the API authentication context and passed to
the service layer.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.enums import ReferralStatus


# ==========================================================
# Referral Creation
# ==========================================================


class LoyaltyReferralCreateRequest(BaseModel):
    """
    Request schema for creating a loyalty referral.

    The referrer/customer identity is intentionally excluded
    from the request.

    The authenticated customer is resolved by the API/service
    layer and becomes the referrer.
    """

    referral_code: str = Field(
        min_length=1,
        max_length=100,
    )

    referred_id: int = Field(
        gt=0,
    )

    reward_points: int = Field(
        default=0,
        ge=0,
    )

    notes: str | None = Field(
        default=None,
        max_length=2000,
    )


# ==========================================================
# Referral Update
# ==========================================================


class LoyaltyReferralUpdateRequest(BaseModel):
    """
    Request schema for partially updating a loyalty referral.

    Referral lifecycle business rules belong in
    LoyaltyReferralService.
    """

    status: ReferralStatus | None = None

    reward_points: int | None = Field(
        default=None,
        ge=0,
    )

    qualified_at: datetime | None = None

    rewarded_at: datetime | None = None

    cancelled_at: datetime | None = None

    notes: str | None = Field(
        default=None,
        max_length=2000,
    )


# ==========================================================
# Referral Response
# ==========================================================


class LoyaltyReferralResponse(BaseModel):
    """
    Public representation of a loyalty referral.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    referrer_id: int

    referred_id: int

    referral_code: str

    status: ReferralStatus

    reward_points: int

    qualified_at: datetime | None = None

    rewarded_at: datetime | None = None

    cancelled_at: datetime | None = None

    notes: str | None = None

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Referral List Response
# ==========================================================


class LoyaltyReferralListResponse(BaseModel):
    """
    Paginated loyalty referral response.
    """

    items: list[LoyaltyReferralResponse]

    total: int = Field(
        ge=0,
    )

    limit: int = Field(
        ge=1,
    )

    offset: int = Field(
        ge=0,
    )


# ==========================================================
# Referral Code Validation Request
# ==========================================================


class LoyaltyReferralValidationRequest(BaseModel):
    """
    Request schema for validating a referral code.

    The authenticated customer is resolved by the service
    layer and is treated as the referred customer.
    """

    referral_code: str = Field(
        min_length=1,
        max_length=100,
    )


# ==========================================================
# Referral Validation Response
# ==========================================================


class LoyaltyReferralValidationResponse(BaseModel):
    """
    Result of validating a loyalty referral code.

    Validation does not create or reward the referral.
    """

    referral: LoyaltyReferralResponse | None = None

    valid: bool

    referral_code_exists: bool

    referral_is_active: bool

    customer_is_eligible: bool

    reason: str | None = None


# ==========================================================
# Referral Qualification Request
# ==========================================================


class LoyaltyReferralQualificationRequest(BaseModel):
    """
    Request schema for qualifying a referral.

    The referral ID identifies the referral being processed.

    Whether the referral actually qualifies is determined by
    LoyaltyReferralService.
    """

    referral_id: int = Field(
        gt=0,
    )


# ==========================================================
# Referral Qualification Response
# ==========================================================


class LoyaltyReferralQualificationResponse(BaseModel):
    """
    Response returned after a referral is successfully
    qualified.
    """

    referral: LoyaltyReferralResponse

    qualified: bool

    qualified_at: datetime

    message: str


# ==========================================================
# Referral Reward Request
# ==========================================================


class LoyaltyReferralRewardRequest(BaseModel):
    """
    Request schema for rewarding a qualified referral.

    The service determines the actual reward amount according
    to the configured loyalty programme rules.
    """

    referral_id: int = Field(
        gt=0,
    )


# ==========================================================
# Referral Reward Response
# ==========================================================


class LoyaltyReferralRewardResponse(BaseModel):
    """
    Response returned after a referral has been rewarded.
    """

    referral: LoyaltyReferralResponse

    rewarded: bool

    reward_points: int = Field(
        ge=0,
    )

    rewarded_at: datetime

    message: str


# ==========================================================
# Referral Cancellation Request
# ==========================================================


class LoyaltyReferralCancellationRequest(BaseModel):
    """
    Request schema for cancelling a loyalty referral.
    """

    referral_id: int = Field(
        gt=0,
    )

    reason: str | None = Field(
        default=None,
        max_length=2000,
    )


# ==========================================================
# Referral Cancellation Response
# ==========================================================


class LoyaltyReferralCancellationResponse(BaseModel):
    """
    Response returned after a referral has been cancelled.
    """

    referral: LoyaltyReferralResponse

    cancelled: bool

    cancelled_at: datetime

    message: str


# ==========================================================
# Referral History
# ==========================================================


class LoyaltyReferralHistoryResponse(BaseModel):
    """
    Paginated referral history for the authenticated
    customer.

    The history may contain referrals where the customer was
    either the referrer or the referred customer.
    """

    items: list[LoyaltyReferralResponse]

    total: int = Field(
        ge=0,
    )

    limit: int = Field(
        ge=1,
    )

    offset: int = Field(
        ge=0,
    )


# ==========================================================
# Referral Statistics
# ==========================================================


class LoyaltyReferralStatisticsResponse(BaseModel):
    """
    Referral statistics for a customer.
    """

    total_referrals: int = Field(
        ge=0,
    )

    pending_referrals: int = Field(
        ge=0,
    )

    qualified_referrals: int = Field(
        ge=0,
    )

    rewarded_referrals: int = Field(
        ge=0,
    )

    cancelled_referrals: int = Field(
        ge=0,
    )

    total_reward_points: int = Field(
        ge=0,
    )


# ==========================================================
# Referral Result
# ==========================================================


class LoyaltyReferralResult(BaseModel):
    """
    General result returned after successfully processing
    a loyalty referral.
    """

    referral: LoyaltyReferralResponse

    success: bool

    message: str

    reward_points: int = Field(
        ge=0,
    )