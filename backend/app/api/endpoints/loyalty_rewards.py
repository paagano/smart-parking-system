"""
Loyalty Reward API Endpoints.

HTTP API for the SmartPark Loyalty Reward Programme.

Business logic belongs in LoyaltyRewardService.
Persistence belongs in LoyaltyRewardRepository.

This router exposes:

Customer:
    GET  /loyalty/rewards
    GET  /loyalty/rewards/eligible
    GET  /loyalty/rewards/{reward_id}
    POST /loyalty/rewards/{reward_id}/redeem
    GET  /loyalty/reward-redemptions
    GET  /loyalty/reward-redemptions/reference/{reference}
    GET  /loyalty/reward-redemptions/status/{status}
    GET  /loyalty/reward-redemptions/{redemption_id}
    GET  /loyalty/reward-redemptions/{redemption_id}/active

Administration:
    POST  /loyalty/rewards
    PATCH /loyalty/rewards/{reward_id}
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
    status,
)

from app.api.dependencies.auth import (
    get_current_active_user,
)

from app.api.dependencies.loyalty_reward import (
    LoyaltyRewardServiceDep,
)

from app.models.enums import (
    RewardRedemptionStatus,
)

from app.models.user import User

from app.schemas.loyalty_reward import (
    LoyaltyRewardCreateRequest,
    LoyaltyRewardRedemptionResponse,
    LoyaltyRewardRedemptionResult,
    LoyaltyRewardResponse,
    LoyaltyRewardUpdateRequest,
)


# ==========================================================
# Router
# ==========================================================


router = APIRouter(
    prefix="/loyalty",
    tags=["Loyalty Programme"],
)


# ==========================================================
# Administration - Create Reward
#
# IMPORTANT:
# This is defined before the parameterised reward routes.
# ==========================================================


@router.post(
    "/rewards",
    response_model=LoyaltyRewardResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Loyalty Reward",
    description="Create a new loyalty reward.",
)
async def create_reward(
    payload: LoyaltyRewardCreateRequest,
    service: LoyaltyRewardServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> LoyaltyRewardResponse:
    """
    Create a new loyalty reward.

    This endpoint is intended for administrative use.

    Administrative authorization should be enforced through
    the appropriate role/permission dependency when the
    authorization layer is finalized.
    """

    return await service.create_reward(
        name=payload.name,
        description=payload.description,
        reward_type=payload.reward_type,
        points_cost=payload.points_cost,
        monetary_value=payload.monetary_value,
        status=payload.status,
        is_active=payload.is_active,
        minimum_tier=payload.minimum_tier,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
    )


# ==========================================================
# Reward Catalogue
# ==========================================================


@router.get(
    "/rewards",
    response_model=list[LoyaltyRewardResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Loyalty Rewards",
    description=(
        "Retrieve active loyalty rewards available in the "
        "SmartPark reward catalogue."
    ),
)
async def get_rewards(
    service: LoyaltyRewardServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of rewards to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of rewards to skip.",
        ),
    ] = 0,
) -> list[LoyaltyRewardResponse]:
    """
    Retrieve active loyalty rewards.
    """

    return await service.get_active_rewards(
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Eligible Rewards
#
# IMPORTANT:
# This static route MUST appear before:
#
#     /rewards/{reward_id}
#
# Otherwise "eligible" could be interpreted as reward_id.
# ==========================================================


@router.get(
    "/rewards/eligible",
    response_model=list[LoyaltyRewardResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Eligible Loyalty Rewards",
    description=(
        "Retrieve loyalty rewards currently eligible for "
        "the authenticated customer."
    ),
)
async def get_eligible_rewards(
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyRewardServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of rewards to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of rewards to skip.",
        ),
    ] = 0,
) -> list[LoyaltyRewardResponse]:
    """
    Retrieve rewards eligible for the authenticated customer.

    Eligibility is determined by the customer's current
    loyalty tier and the reward validity period.
    """

    return await service.get_eligible_rewards(
        customer_id=current_user.id,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Reward by ID
# ==========================================================


@router.get(
    "/rewards/{reward_id}",
    response_model=LoyaltyRewardResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Loyalty Reward",
    description="Retrieve a loyalty reward by its ID.",
)
async def get_reward(
    reward_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty reward ID.",
        ),
    ],
    service: LoyaltyRewardServiceDep,
) -> LoyaltyRewardResponse:
    """
    Retrieve a loyalty reward by ID.
    """

    return await service.get_reward(
        reward_id,
    )


# ==========================================================
# Administration - Update Reward
# ==========================================================


@router.patch(
    "/rewards/{reward_id}",
    response_model=LoyaltyRewardResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Loyalty Reward",
    description="Update an existing loyalty reward.",
)
async def update_reward(
    reward_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty reward ID.",
        ),
    ],
    payload: LoyaltyRewardUpdateRequest,
    service: LoyaltyRewardServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> LoyaltyRewardResponse:
    """
    Update an existing loyalty reward.

    Only fields supplied in the request are modified.

    Administrative authorization should be enforced through
    the appropriate role/permission dependency when the
    authorization layer is finalized.
    """

    return await service.update_reward(
        reward_id,
        name=payload.name,
        description=payload.description,
        reward_type=payload.reward_type,
        points_cost=payload.points_cost,
        monetary_value=payload.monetary_value,
        status=payload.status,
        is_active=payload.is_active,
        minimum_tier=payload.minimum_tier,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
    )


# ==========================================================
# Redeem Reward
# ==========================================================


@router.post(
    "/rewards/{reward_id}/redeem",
    response_model=LoyaltyRewardRedemptionResult,
    status_code=status.HTTP_201_CREATED,
    summary="Redeem Loyalty Reward",
    description=(
        "Redeem a loyalty reward using the authenticated "
        "customer's loyalty points."
    ),
)
async def redeem_reward(
    reward_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty reward ID.",
        ),
    ],
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyRewardServiceDep,
) -> LoyaltyRewardRedemptionResult:
    """
    Redeem a loyalty reward for the authenticated customer.

    The LoyaltyRewardService handles:

        - account validation
        - reward validation
        - validity period
        - tier eligibility
        - sufficient points
        - point deduction
        - redemption creation

    The service returns:

        redemption
        reward
        remaining points
        current loyalty tier
    """

    (
        redemption,
        reward,
        remaining_points,
        loyalty_tier,
    ) = await service.redeem_reward(
        customer_id=current_user.id,
        reward_id=reward_id,
    )

    # ------------------------------------------------------
    # Important:
    #
    # The service has already successfully deducted the
    # reward's points and created the redemption.
    #
    # points_spent must therefore come from the actual
    # redemption record, rather than being omitted from
    # the response.
    # ------------------------------------------------------

    return LoyaltyRewardRedemptionResult(
        redemption=redemption,
        reward=reward,
        points_spent=redemption.points_spent,
        remaining_points=remaining_points,
        loyalty_tier=loyalty_tier,
    )


# ==========================================================
# Customer Reward Redemption History
# ==========================================================


@router.get(
    "/reward-redemptions",
    response_model=list[LoyaltyRewardRedemptionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get My Reward Redemptions",
    description=(
        "Retrieve the authenticated customer's loyalty "
        "reward redemption history."
    ),
)
async def get_my_reward_redemptions(
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyRewardServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of redemptions to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of redemptions to skip.",
        ),
    ] = 0,
) -> list[LoyaltyRewardRedemptionResponse]:
    """
    Retrieve the authenticated customer's reward redemption
    history.
    """

    return await service.get_customer_redemptions(
        customer_id=current_user.id,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Redemption by Reference
#
# IMPORTANT:
# This static route MUST appear before:
#
#     /reward-redemptions/{redemption_id}
# ==========================================================


@router.get(
    "/reward-redemptions/reference/{redemption_reference}",
    response_model=LoyaltyRewardRedemptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Reward Redemption by Reference",
    description=(
        "Retrieve a loyalty reward redemption using its "
        "unique redemption reference."
    ),
)
async def get_reward_redemption_by_reference(
    redemption_reference: Annotated[
        str,
        Path(
            min_length=1,
            max_length=100,
            description="Unique reward redemption reference.",
        ),
    ],
    service: LoyaltyRewardServiceDep,
) -> LoyaltyRewardRedemptionResponse:
    """
    Retrieve a reward redemption by its unique reference.
    """

    return await service.get_redemption_by_reference(
        redemption_reference,
    )


# ==========================================================
# Customer Redemption History by Status
#
# IMPORTANT:
# This static route MUST appear before:
#
#     /reward-redemptions/{redemption_id}
# ==========================================================


@router.get(
    "/reward-redemptions/status/{redemption_status}",
    response_model=list[LoyaltyRewardRedemptionResponse],
    status_code=status.HTTP_200_OK,
    summary="Get My Reward Redemptions by Status",
    description=(
        "Retrieve the authenticated customer's reward "
        "redemption history filtered by status."
    ),
)
async def get_my_reward_redemptions_by_status(
    redemption_status: RewardRedemptionStatus,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyRewardServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of redemptions to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of redemptions to skip.",
        ),
    ] = 0,
) -> list[LoyaltyRewardRedemptionResponse]:
    """
    Retrieve the authenticated customer's reward redemptions
    filtered by status.
    """

    return await service.get_customer_redemptions_by_status(
        customer_id=current_user.id,
        status=redemption_status,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Customer Redemption by ID
# ==========================================================


@router.get(
    "/reward-redemptions/{redemption_id}",
    response_model=LoyaltyRewardRedemptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Reward Redemption",
    description="Retrieve a loyalty reward redemption by ID.",
)
async def get_reward_redemption(
    redemption_id: Annotated[
        int,
        Path(
            ge=1,
            description="Reward redemption ID.",
        ),
    ],
    service: LoyaltyRewardServiceDep,
) -> LoyaltyRewardRedemptionResponse:
    """
    Retrieve a reward redemption by ID.
    """

    return await service.get_redemption(
        redemption_id,
    )


# ==========================================================
# Active Redemption
# ==========================================================


@router.get(
    "/reward-redemptions/{redemption_id}/active",
    response_model=LoyaltyRewardRedemptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Active Reward Redemption",
    description=(
        "Retrieve an active loyalty reward redemption."
    ),
)
async def get_active_reward_redemption(
    redemption_id: Annotated[
        int,
        Path(
            ge=1,
            description="Reward redemption ID.",
        ),
    ],
    service: LoyaltyRewardServiceDep,
) -> LoyaltyRewardRedemptionResponse:
    """
    Retrieve an active reward redemption.
    """

    return await service.get_active_redemption(
        redemption_id,
    )