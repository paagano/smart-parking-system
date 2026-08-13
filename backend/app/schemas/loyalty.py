"""
Loyalty Schemas.

Pydantic schemas for Loyalty Account and
Loyalty Point Transaction API requests and responses.

Business logic belongs in LoyaltyService.
Persistence belongs in LoyaltyRepository.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from app.models.enums import (
    LoyaltyPointTransactionType,
    LoyaltyTier,
)


# ==========================================================
# Loyalty Point Transaction
# ==========================================================


class LoyaltyPointTransactionResponse(
    BaseModel,
):
    """
    Public representation of a loyalty point transaction.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    loyalty_account_id: int

    transaction_type: LoyaltyPointTransactionType

    points: int

    balance_after: int

    reference_type: str | None = None

    reference_id: int | None = None

    description: str | None = None

    expires_at: datetime | None = None

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Loyalty Point History
# ==========================================================


class LoyaltyPointHistoryResponse(
    BaseModel,
):
    """
    Paginated loyalty point transaction history.
    """

    items: list[
        LoyaltyPointTransactionResponse
    ]

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
# Loyalty Account
# ==========================================================


class LoyaltyAccountResponse(
    BaseModel,
):
    """
    Public representation of a customer's loyalty account.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    customer_id: int

    points_balance: int

    lifetime_points: int

    tier: LoyaltyTier

    is_active: bool

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Loyalty Point Redemption Request
# ==========================================================


class LoyaltyRedeemRequest(
    BaseModel,
):
    """
    Request to redeem loyalty points.

    The authenticated customer is taken from the
    authentication context and therefore customer_id
    is intentionally not accepted from the request.
    """

    points: int = Field(
        gt=0,
        description=(
            "Number of loyalty points to redeem."
        ),
    )

    reference_type: str | None = Field(
        default=None,
        max_length=50,
        description=(
            "Business entity associated with the redemption."
        ),
    )

    reference_id: int | None = Field(
        default=None,
        description=(
            "ID of the business entity associated "
            "with the redemption."
        ),
    )

    description: str | None = Field(
        default=None,
        description=(
            "Optional description of the redemption."
        ),
    )