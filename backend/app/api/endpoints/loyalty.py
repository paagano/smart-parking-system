"""
Loyalty API Endpoints.

REST API endpoints for customer loyalty management.

Responsibilities:

- Retrieve the authenticated customer's loyalty account
- Retrieve current loyalty balance
- Retrieve lifetime loyalty points
- Retrieve current loyalty tier
- Retrieve loyalty point transaction history
- Redeem loyalty points

Business logic belongs in LoyaltyService.
Persistence belongs in LoyaltyRepository.

Points are NOT awarded through a customer-facing endpoint.
Points awarding will be triggered by trusted business events
such as successful payments and referrals.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
)

from app.api.dependencies.auth import (
    get_current_active_user,
)

from app.api.dependencies.loyalty import (
    LoyaltyServiceDep,
)

from app.models.user import User

from app.schemas.loyalty import (
    LoyaltyAccountResponse,
    LoyaltyPointHistoryResponse,
    LoyaltyPointTransactionResponse,
    LoyaltyRedeemRequest,
)


# ==========================================================
# Router
# ==========================================================

router = APIRouter(
    prefix="/loyalty",
    tags=["Loyalty"],
)


# ==========================================================
# Get My Loyalty Account
# ==========================================================

@router.get(
    "",
    response_model=LoyaltyAccountResponse,
    summary="Get My Loyalty Account",
)
async def get_my_loyalty_account(
    service: LoyaltyServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> LoyaltyAccountResponse:
    """
    Retrieve the authenticated customer's loyalty account.

    If the customer does not yet have a loyalty account,
    the service creates one.
    """

    return await service.get_or_create_account(
        customer_id=current_user.id,
    )


# ==========================================================
# Get Loyalty Balance
# ==========================================================

@router.get(
    "/balance",
    summary="Get Loyalty Points Balance",
)
async def get_loyalty_balance(
    service: LoyaltyServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> dict[str, int]:
    """
    Retrieve the authenticated customer's current
    loyalty points balance.
    """

    balance = await service.get_points_balance(
        customer_id=current_user.id,
    )

    return {
        "points_balance": balance,
    }


# ==========================================================
# Get Lifetime Points
# ==========================================================

@router.get(
    "/lifetime-points",
    summary="Get Lifetime Loyalty Points",
)
async def get_lifetime_points(
    service: LoyaltyServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> dict[str, int]:
    """
    Retrieve the authenticated customer's lifetime
    earned loyalty points.
    """

    lifetime_points = await service.get_lifetime_points(
        customer_id=current_user.id,
    )

    return {
        "lifetime_points": lifetime_points,
    }


# ==========================================================
# Get Loyalty Tier
# ==========================================================

@router.get(
    "/tier",
    summary="Get Loyalty Tier",
)
async def get_loyalty_tier(
    service: LoyaltyServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> dict[str, str]:
    """
    Retrieve the authenticated customer's current
    loyalty tier.
    """

    tier = await service.get_tier(
        customer_id=current_user.id,
    )

    return {
        "tier": tier.value,
    }


# ==========================================================
# Get Point History
# ==========================================================

@router.get(
    "/history",
    response_model=LoyaltyPointHistoryResponse,
    summary="Get Loyalty Point History",
)
async def get_point_history(
    service: LoyaltyServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    limit: int = Query(
        default=100,
        ge=1,
        le=100,
        description=(
            "Maximum number of point transactions "
            "to return."
        ),
    ),
    offset: int = Query(
        default=0,
        ge=0,
        description=(
            "Number of point transactions to skip."
        ),
    ),
) -> LoyaltyPointHistoryResponse:
    """
    Retrieve the authenticated customer's loyalty point
    transaction history.
    """

    transactions = await service.get_point_history(
        customer_id=current_user.id,
        limit=limit,
        offset=offset,
    )

    total = await service.count_point_history(
        customer_id=current_user.id,
    )

    return LoyaltyPointHistoryResponse(
        items=transactions,
        total=total,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Redeem Loyalty Points
# ==========================================================

@router.post(
    "/redeem",
    response_model=LoyaltyPointTransactionResponse,
    summary="Redeem Loyalty Points",
)
async def redeem_points(
    request: LoyaltyRedeemRequest,
    service: LoyaltyServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> LoyaltyPointTransactionResponse:
    """
    Redeem loyalty points belonging to the authenticated
    customer.

    The LoyaltyService validates:

    - Loyalty account existence
    - Account status
    - Requested point amount
    - Available point balance
    - Redemption idempotency
    """

    return await service.redeem_points(
        customer_id=current_user.id,
        points=request.points,
        reference_type=request.reference_type,
        reference_id=request.reference_id,
        description=request.description,
    )