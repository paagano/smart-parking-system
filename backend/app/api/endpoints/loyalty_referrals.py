"""
Loyalty Referral API Endpoints.

HTTP API for the SmartPark Loyalty Referral Programme.

Business logic belongs in LoyaltyReferralService.

Persistence belongs in LoyaltyReferralRepository.

Customer identity is resolved from the authenticated
user and is never trusted from customer-facing request
payloads.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Path,
    status,
)

from app.api.dependencies.auth import (
    require_driver,
)

from app.api.dependencies.loyalty_referrals import (
    LoyaltyReferralServiceDep,
)

from app.models.enums import (
    ReferralStatus,
)

from app.models.user import User

from app.schemas.loyalty_referral import (
    LoyaltyReferralCancellationRequest,
    LoyaltyReferralCancellationResponse,
    LoyaltyReferralCreateRequest,
    LoyaltyReferralQualificationRequest,
    LoyaltyReferralQualificationResponse,
    LoyaltyReferralResponse,
    LoyaltyReferralRewardRequest,
    LoyaltyReferralRewardResponse,
    LoyaltyReferralValidationRequest,
    LoyaltyReferralValidationResponse,
)


# ==========================================================
# Authenticated Customer Dependency
# ==========================================================

CurrentUserDep = Annotated[
    User,
    Depends(require_driver),
]


# ==========================================================
# Router
# ==========================================================

router = APIRouter(
    prefix="/loyalty",
    tags=["Loyalty Programme"],
)


# ==========================================================
# Create Referral
# ==========================================================


@router.post(
    "/referrals",
    response_model=LoyaltyReferralResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Loyalty Referral",
    description=(
        "Create a new loyalty referral using the "
        "authenticated customer as the referrer."
    ),
)
async def create_referral(
    payload: LoyaltyReferralCreateRequest,
    current_user: CurrentUserDep,
    service: LoyaltyReferralServiceDep,
) -> LoyaltyReferralResponse:
    """
    Create a loyalty referral.

    The authenticated customer becomes the referrer.
    """

    return await service.create_referral(
        referrer_id=current_user.id,
        referred_id=payload.referred_id,
        referral_code=payload.referral_code,
        reward_points=payload.reward_points,
        notes=payload.notes,
    )


# ==========================================================
# Get Referral By ID
# ==========================================================


@router.get(
    "/referrals/{referral_id}",
    response_model=LoyaltyReferralResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Loyalty Referral",
    description=(
        "Retrieve a loyalty referral by its ID."
    ),
)
async def get_referral(
    referral_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty referral ID.",
        ),
    ],
    service: LoyaltyReferralServiceDep,
) -> LoyaltyReferralResponse:
    """
    Retrieve a loyalty referral by ID.
    """

    return await service.get_referral(
        referral_id,
    )


# ==========================================================
# Get Referral By Code
#
# IMPORTANT:
# This route is intentionally defined before any route
# using /referrals/{referral_id}.
# ==========================================================


@router.get(
    "/referrals/code/{referral_code}",
    response_model=LoyaltyReferralResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Referral By Code",
    description=(
        "Retrieve a loyalty referral using its "
        "unique referral code."
    ),
)
async def get_referral_by_code(
    referral_code: Annotated[
        str,
        Path(
            min_length=1,
            max_length=100,
            description="Unique referral code.",
        ),
    ],
    service: LoyaltyReferralServiceDep,
) -> LoyaltyReferralResponse:
    """
    Retrieve a loyalty referral by referral code.
    """

    return await service.get_referral_by_code(
        referral_code,
    )


# ==========================================================
# Validate Referral Code
# ==========================================================


@router.post(
    "/referrals/validate",
    response_model=LoyaltyReferralValidationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate Referral Code",
    description=(
        "Validate a loyalty referral code for the "
        "authenticated customer."
    ),
)
async def validate_referral_code(
    payload: LoyaltyReferralValidationRequest,
    current_user: CurrentUserDep,
    service: LoyaltyReferralServiceDep,
) -> LoyaltyReferralValidationResponse:
    """
    Validate a referral code.

    Validation does not qualify or reward the referral.

    The authenticated customer is treated as the
    referred customer for validation purposes.
    """

    (
        referral,
        valid,
        referral_code_exists,
        referral_is_active,
        reason,
    ) = await service.validate_referral_code(
        customer_id=current_user.id,
        referral_code=payload.referral_code,
    )

    return LoyaltyReferralValidationResponse(
        referral=referral,
        valid=valid,
        referral_code_exists=referral_code_exists,
        referral_is_active=referral_is_active,
        customer_is_eligible=valid,
        reason=reason,
    )


# ==========================================================
# Qualify Referral
# ==========================================================


@router.post(
    "/referrals/{referral_id}/qualify",
    response_model=LoyaltyReferralQualificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Qualify Loyalty Referral",
    description=(
        "Qualify a pending loyalty referral and "
        "transition it to QUALIFIED."
    ),
)
async def qualify_referral(
    referral_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty referral ID.",
        ),
    ],
    service: LoyaltyReferralServiceDep,
) -> LoyaltyReferralQualificationResponse:
    """
    Qualify a pending referral.

    The service owns the PENDING -> QUALIFIED
    business transition.
    """

    referral = await service.qualify_referral(
        referral_id=referral_id,
    )

    return LoyaltyReferralQualificationResponse(
        referral=referral,
        qualified=True,
        qualified_at=referral.qualified_at,
        message=(
            "Referral qualified successfully."
        ),
    )


# ==========================================================
# Reward Referral
# ==========================================================


@router.post(
    "/referrals/{referral_id}/reward",
    response_model=LoyaltyReferralRewardResponse,
    status_code=status.HTTP_200_OK,
    summary="Reward Loyalty Referral",
    description=(
        "Reward a qualified loyalty referral and "
        "award the configured loyalty points."
    ),
)
async def reward_referral(
    referral_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty referral ID.",
        ),
    ],
    service: LoyaltyReferralServiceDep,
) -> LoyaltyReferralRewardResponse:
    """
    Reward a qualified referral.

    The service performs the loyalty-point award and
    transitions the referral to REWARDED.
    """

    referral = await service.reward_referral(
        referral_id=referral_id,
    )

    return LoyaltyReferralRewardResponse(
        referral=referral,
        rewarded=True,
        reward_points=referral.reward_points,
        rewarded_at=referral.rewarded_at,
        message=(
            "Referral rewarded successfully."
        ),
    )


# ==========================================================
# Cancel Referral
# ==========================================================


@router.post(
    "/referrals/{referral_id}/cancel",
    response_model=LoyaltyReferralCancellationResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel Loyalty Referral",
    description=(
        "Cancel a pending or qualified loyalty referral."
    ),
)
async def cancel_referral(
    referral_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty referral ID.",
        ),
    ],
    payload: LoyaltyReferralCancellationRequest,
    service: LoyaltyReferralServiceDep,
) -> LoyaltyReferralCancellationResponse:
    """
    Cancel a loyalty referral.

    Rewarded referrals cannot be cancelled.

    The referral_id in the URL is authoritative.
    """

    referral = await service.cancel_referral(
        referral_id=referral_id,
        reason=payload.reason,
    )

    return LoyaltyReferralCancellationResponse(
        referral=referral,
        cancelled=True,
        cancelled_at=referral.cancelled_at,
        message=(
            "Referral cancelled successfully."
        ),
    )


# ==========================================================
# Get Active Referral
# ==========================================================


@router.get(
    "/referrals/{referral_id}/active",
    response_model=LoyaltyReferralResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Active Loyalty Referral",
    description=(
        "Retrieve a loyalty referral if it is currently "
        "in an active lifecycle state."
    ),
)
async def get_active_referral(
    referral_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty referral ID.",
        ),
    ],
    service: LoyaltyReferralServiceDep,
) -> LoyaltyReferralResponse:
    """
    Retrieve an active referral.

    Active referral states are determined by the service.
    """

    return await service.get_active_referral(
        referral_id,
    )


# ==========================================================
# Referral Status
# ==========================================================


@router.get(
    "/referrals/{referral_id}/status",
    response_model=LoyaltyReferralResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Referral Status",
    description=(
        "Retrieve the current state of a loyalty referral."
    ),
)
async def get_referral_status(
    referral_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty referral ID.",
        ),
    ],
    service: LoyaltyReferralServiceDep,
) -> LoyaltyReferralResponse:
    """
    Retrieve the current referral state.

    The status is represented by the status field of the
    returned LoyaltyReferralResponse.
    """

    return await service.get_referral(
        referral_id,
    )