"""
Loyalty Reward Schemas.

Pydantic schemas for the Loyalty Reward catalogue and
customer reward redemptions.

Business rules belong in LoyaltyRewardService.
Persistence belongs in LoyaltyRewardRepository.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.models.enums import (
    LoyaltyRewardStatus,
    LoyaltyRewardType,
    LoyaltyTier,
    RewardRedemptionStatus,
)


# ==========================================================
# Reward Creation
# ==========================================================


class LoyaltyRewardCreateRequest(BaseModel):
    """
    Request schema for creating a loyalty reward.
    """

    name: str = Field(
        min_length=1,
        max_length=150,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    reward_type: LoyaltyRewardType

    points_cost: int = Field(
        gt=0,
    )

    monetary_value: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    status: LoyaltyRewardStatus = (
        LoyaltyRewardStatus.ACTIVE
    )

    is_active: bool = True

    minimum_tier: LoyaltyTier | None = None

    valid_from: datetime | None = None

    valid_until: datetime | None = None


# ==========================================================
# Reward Update
# ==========================================================


class LoyaltyRewardUpdateRequest(BaseModel):
    """
    Request schema for updating an existing loyalty reward.

    All fields are optional so that the service can support
    partial updates.
    """

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=150,
    )

    description: str | None = Field(
        default=None,
        max_length=5000,
    )

    reward_type: LoyaltyRewardType | None = None

    points_cost: int | None = Field(
        default=None,
        gt=0,
    )

    monetary_value: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    status: LoyaltyRewardStatus | None = None

    is_active: bool | None = None

    minimum_tier: LoyaltyTier | None = None

    valid_from: datetime | None = None

    valid_until: datetime | None = None


# ==========================================================
# Reward Response
# ==========================================================


class LoyaltyRewardResponse(BaseModel):
    """
    Public representation of a loyalty reward.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    name: str

    description: str | None = None

    reward_type: LoyaltyRewardType

    points_cost: int

    monetary_value: Decimal | None = None

    status: LoyaltyRewardStatus

    is_active: bool

    minimum_tier: LoyaltyTier | None = None

    valid_from: datetime | None = None

    valid_until: datetime | None = None

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Reward Catalogue
# ==========================================================


class LoyaltyRewardListResponse(BaseModel):
    """
    Paginated loyalty reward catalogue response.
    """

    items: list[LoyaltyRewardResponse]

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
# Reward Redemption Request
# ==========================================================


class LoyaltyRewardRedeemRequest(BaseModel):
    """
    Request schema for redeeming a loyalty reward.

    The customer identity is intentionally NOT supplied
    by the client.

    The authenticated customer is determined by the API
    authentication context and passed to the service layer.

    The reward ID is normally supplied through the URL path
    by:

        POST /loyalty/rewards/{reward_id}/redeem
    """

    reward_id: int = Field(
        gt=0,
    )


# ==========================================================
# Reward Redemption Response
# ==========================================================


class LoyaltyRewardRedemptionResponse(BaseModel):
    """
    Public representation of a loyalty reward redemption.

    The underlying SQLAlchemy model contains:

        used_at
        expires_at
        description

    The API exposes:

        redeemed_at
        expires_at
        description

    ``redeemed_at`` represents the time at which the
    redemption record was created.

    ``used_at`` remains an internal/domain field representing
    when the actual reward benefit was used.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    loyalty_account_id: int

    reward_id: int

    redemption_reference: str

    points_spent: int

    status: RewardRedemptionStatus

    redeemed_at: datetime

    expires_at: datetime | None = None

    description: str | None = None

    created_at: datetime

    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def map_redeemed_at_from_model(cls, value):
        """
        Map the SQLAlchemy redemption model's creation
        timestamp to the API's ``redeemed_at`` field.

        The LoyaltyRewardRedemption model does not currently
        contain a dedicated ``redeemed_at`` column.

        A redemption record is created at the point of
        successful redemption, so ``created_at`` is the
        appropriate source for the API representation.
        """

        if isinstance(value, dict):
            if (
                "redeemed_at" not in value
                and "created_at" in value
            ):
                value["redeemed_at"] = value["created_at"]

            return value

        if not hasattr(value, "redeemed_at"):
            created_at = getattr(
                value,
                "created_at",
                None,
            )

            if created_at is not None:
                try:
                    setattr(
                        value,
                        "redeemed_at",
                        created_at,
                    )
                except Exception:
                    # SQLAlchemy model instances may reject
                    # arbitrary attributes depending on their
                    # instrumentation/configuration.
                    pass

        return value


# ==========================================================
# Redemption History
# ==========================================================


class LoyaltyRewardRedemptionHistoryResponse(BaseModel):
    """
    Paginated reward redemption history.
    """

    items: list[LoyaltyRewardRedemptionResponse]

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
# Reward Redemption Result
# ==========================================================


class LoyaltyRewardRedemptionResult(BaseModel):
    """
    Result returned after successfully redeeming a reward.

    Provides:

        - redeemed reward
        - reward definition
        - points spent
        - remaining loyalty points
        - current loyalty tier
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    redemption: LoyaltyRewardRedemptionResponse

    reward: LoyaltyRewardResponse

    points_spent: int = Field(
        gt=0,
    )

    remaining_points: int = Field(
        ge=0,
    )

    loyalty_tier: LoyaltyTier


# ==========================================================
# Reward Availability
# ==========================================================


class LoyaltyRewardAvailabilityResponse(BaseModel):
    """
    Represents whether a reward is currently available
    for redemption by the authenticated customer.
    """

    reward: LoyaltyRewardResponse

    eligible: bool

    sufficient_points: bool

    points_required: int = Field(
        gt=0,
    )

    points_balance: int = Field(
        ge=0,
    )

    loyalty_tier: LoyaltyTier

    reason: str | None = None