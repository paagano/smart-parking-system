"""
Loyalty Coupon API Endpoints.

HTTP API for the SmartPark Loyalty Programme.

Business logic belongs in LoyaltyCouponService.
Persistence belongs in LoyaltyCouponRepository.

All coupon endpoints are exposed under the common
"Loyalty Programme" Swagger tag.

Customer operations
-------------------
GET    /loyalty/coupons
GET    /loyalty/coupons/active
GET    /loyalty/coupons/status/{coupon_status}
GET    /loyalty/coupons/type/{coupon_type}
GET    /loyalty/coupons/{coupon_id}
GET    /loyalty/coupons/code/{coupon_code}
GET    /loyalty/coupons/{coupon_id}/validate
POST   /loyalty/coupons/{coupon_code}/use

Administrative operations
-------------------------
POST   /loyalty/coupons
PATCH  /loyalty/coupons/{coupon_id}
PATCH  /loyalty/coupons/{coupon_id}/status
DELETE /loyalty/coupons/{coupon_id}
GET    /loyalty/coupons/admin/all
GET    /loyalty/coupons/admin/status/{coupon_status}
GET    /loyalty/coupons/admin/type/{coupon_type}
GET    /loyalty/coupons/admin/reward-redemption/{reward_redemption_id}
GET    /loyalty/coupons/admin/payment-transaction/{payment_transaction_id}
GET    /loyalty/coupons/admin/count
GET    /loyalty/coupons/admin/customer/{customer_id}/count
GET    /loyalty/coupons/admin/customer/{customer_id}/count/status/{coupon_status}
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

from app.api.dependencies.loyalty_coupons import (
    LoyaltyCouponServiceDep,
)

from app.models.enums import (
    CouponStatus,
    CouponType,
)

from app.models.user import User

from app.schemas.loyalty_coupon import (
    LoyaltyCouponCreateRequest,
    LoyaltyCouponResponse,
    LoyaltyCouponUpdateRequest,
)


# ==========================================================
# Router
# ==========================================================

router = APIRouter(
    prefix="/loyalty",
    tags=["Loyalty Programme"],
)


# ==========================================================
# Customer Coupon History
# ==========================================================

@router.get(
    "/coupons",
    response_model=list[LoyaltyCouponResponse],
    status_code=status.HTTP_200_OK,
    summary="Get My Loyalty Coupons",
    description=(
        "Retrieve the authenticated customer's loyalty "
        "coupon history."
    ),
)
async def get_my_coupons(
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyCouponServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of coupons to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of coupons to skip.",
        ),
    ] = 0,
) -> list[LoyaltyCouponResponse]:
    """
    Retrieve the authenticated customer's coupon history.
    """

    return await service.get_customer_coupons(
        customer_id=current_user.id,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Active Customer Coupons
# ==========================================================

@router.get(
    "/coupons/active",
    response_model=list[LoyaltyCouponResponse],
    status_code=status.HTTP_200_OK,
    summary="Get My Active Loyalty Coupons",
    description=(
        "Retrieve the authenticated customer's currently "
        "active and valid loyalty coupons."
    ),
)
async def get_my_active_coupons(
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyCouponServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of coupons to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of coupons to skip.",
        ),
    ] = 0,
) -> list[LoyaltyCouponResponse]:
    """
    Retrieve currently active coupons belonging to the
    authenticated customer.
    """

    return await service.get_active_customer_coupons(
        customer_id=current_user.id,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Customer Coupons by Status
#
# IMPORTANT:
# This static route is defined before:
#
#     /coupons/{coupon_id}
# ==========================================================

@router.get(
    "/coupons/status/{coupon_status}",
    response_model=list[LoyaltyCouponResponse],
    status_code=status.HTTP_200_OK,
    summary="Get My Coupons by Status",
    description=(
        "Retrieve the authenticated customer's loyalty "
        "coupons filtered by status."
    ),
)
async def get_my_coupons_by_status(
    coupon_status: Annotated[
        CouponStatus,
        Path(
            description="Coupon status.",
        ),
    ],
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyCouponServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of coupons to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of coupons to skip.",
        ),
    ] = 0,
) -> list[LoyaltyCouponResponse]:
    """
    Retrieve the authenticated customer's coupons filtered
    by coupon status.
    """

    return await service.get_customer_coupons_by_status(
        customer_id=current_user.id,
        status=coupon_status,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Customer Coupons by Type
# ==========================================================

@router.get(
    "/coupons/type/{coupon_type}",
    response_model=list[LoyaltyCouponResponse],
    status_code=status.HTTP_200_OK,
    summary="Get My Coupons by Type",
    description=(
        "Retrieve the authenticated customer's loyalty "
        "coupons filtered by coupon type."
    ),
)
async def get_my_coupons_by_type(
    coupon_type: Annotated[
        CouponType,
        Path(
            description="Coupon type.",
        ),
    ],
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyCouponServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of coupons to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of coupons to skip.",
        ),
    ] = 0,
) -> list[LoyaltyCouponResponse]:
    """
    Retrieve the authenticated customer's coupons filtered
    by coupon type.
    """

    return await service.get_customer_coupons_by_type(
        customer_id=current_user.id,
        coupon_type=coupon_type,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Customer Coupon by Code
#
# IMPORTANT:
# This static route is defined before:
#
#     /coupons/{coupon_id}
# ==========================================================

@router.get(
    "/coupons/code/{coupon_code}",
    response_model=LoyaltyCouponResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Loyalty Coupon by Code",
    description=(
        "Retrieve a loyalty coupon using its unique coupon "
        "code."
    ),
)
async def get_coupon_by_code(
    coupon_code: Annotated[
        str,
        Path(
            min_length=1,
            max_length=100,
            description="Unique loyalty coupon code.",
        ),
    ],
    service: LoyaltyCouponServiceDep,
) -> LoyaltyCouponResponse:
    """
    Retrieve a loyalty coupon by its unique code.
    """

    return await service.get_coupon_by_code(
        coupon_code,
    )


# ==========================================================
# Customer Coupon by ID
# ==========================================================

@router.get(
    "/coupons/{coupon_id}",
    response_model=LoyaltyCouponResponse,
    status_code=status.HTTP_200_OK,
    summary="Get My Loyalty Coupon",
    description=(
        "Retrieve a loyalty coupon belonging to the "
        "authenticated customer."
    ),
)
async def get_my_coupon(
    coupon_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty coupon ID.",
        ),
    ],
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyCouponServiceDep,
) -> LoyaltyCouponResponse:
    """
    Retrieve a specific coupon belonging to the authenticated
    customer.
    """

    return await service.get_customer_coupon(
        customer_id=current_user.id,
        coupon_id=coupon_id,
    )


# ==========================================================
# Validate Coupon
#
# IMPORTANT:
# This is deliberately a GET operation.
#
# Validation does NOT consume the coupon.
# ==========================================================

@router.get(
    "/coupons/{coupon_id}/validate",
    response_model=LoyaltyCouponResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate Loyalty Coupon",
    description=(
        "Validate whether a loyalty coupon is currently "
        "usable by the authenticated customer."
    ),
)
async def validate_coupon(
    coupon_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty coupon ID.",
        ),
    ],
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyCouponServiceDep,
) -> LoyaltyCouponResponse:
    """
    Validate a customer's coupon.

    The coupon is NOT consumed by this endpoint.
    """

    coupon = await service.get_customer_coupon(
        customer_id=current_user.id,
        coupon_id=coupon_id,
    )

    return await service.validate_coupon(
        customer_id=current_user.id,
        coupon_code=coupon.coupon_code,
    )


# ==========================================================
# Use / Apply Coupon
# ==========================================================

@router.post(
    "/coupons/{coupon_code}/use",
    response_model=LoyaltyCouponResponse,
    status_code=status.HTTP_200_OK,
    summary="Use Loyalty Coupon",
    description=(
        "Apply a loyalty coupon to a payment transaction. "
        "The coupon is marked as used after successful "
        "business validation."
    ),
)
async def use_coupon(
    coupon_code: Annotated[
        str,
        Path(
            min_length=1,
            max_length=100,
            description="Unique loyalty coupon code.",
        ),
    ],
    payment_transaction_id: Annotated[
        int,
        Query(
            gt=0,
            description=(
                "Payment transaction ID to which the "
                "coupon is being applied."
            ),
        ),
    ],
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyCouponServiceDep,
) -> LoyaltyCouponResponse:
    """
    Apply a loyalty coupon to a payment transaction.

    The authenticated customer is used to establish coupon
    ownership.
    """

    return await service.use_coupon(
        customer_id=current_user.id,
        coupon_code=coupon_code,
        payment_transaction_id=payment_transaction_id,
    )


# ==========================================================
# Administration - Create Coupon
# ==========================================================

@router.post(
    "/coupons",
    response_model=LoyaltyCouponResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Loyalty Coupon",
    description=(
        "Create a loyalty coupon for the authenticated "
        "customer."
    ),
)
async def create_coupon(
    payload: LoyaltyCouponCreateRequest,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    service: LoyaltyCouponServiceDep,
) -> LoyaltyCouponResponse:
    """
    Create a loyalty coupon.

    The customer's loyalty account is resolved from the
    authenticated user.
    """

    return await service.create_coupon(
        customer_id=current_user.id,
        coupon_type=payload.coupon_type,
        value=payload.value,
        free_parking_minutes=payload.free_parking_minutes,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        description=payload.description,
        coupon_code=payload.coupon_code,
        reward_redemption_id=payload.reward_redemption_id,
    )


# ==========================================================
# Administration - Update Coupon
# ==========================================================

@router.patch(
    "/coupons/{coupon_id}",
    response_model=LoyaltyCouponResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Loyalty Coupon",
    description="Update an existing loyalty coupon.",
)
async def update_coupon(
    coupon_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty coupon ID.",
        ),
    ],
    payload: LoyaltyCouponUpdateRequest,
    service: LoyaltyCouponServiceDep,
) -> LoyaltyCouponResponse:
    """
    Update an existing loyalty coupon.

    Only supplied fields are updated.
    """

    return await service.update_coupon(
        coupon_id,
        coupon_type=payload.coupon_type,
        value=payload.value,
        free_parking_minutes=payload.free_parking_minutes,
        status=payload.status,
        is_active=payload.is_active,
        valid_from=payload.valid_from,
        valid_until=payload.valid_until,
        description=payload.description,
    )


# ==========================================================
# Administration - Update Coupon Status
# ==========================================================

@router.patch(
    "/coupons/{coupon_id}/status",
    response_model=LoyaltyCouponResponse,
    status_code=status.HTTP_200_OK,
    summary="Update Loyalty Coupon Status",
    description=(
        "Update the status and active state of a loyalty "
        "coupon."
    ),
)
async def update_coupon_status(
    coupon_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty coupon ID.",
        ),
    ],
    coupon_status: Annotated[
        CouponStatus,
        Query(
            description="New coupon status.",
        ),
    ],
    service: LoyaltyCouponServiceDep,
    is_active: Annotated[
        bool | None,
        Query(
            description="Whether the coupon should remain active.",
        ),
    ] = None,
) -> LoyaltyCouponResponse:
    """
    Update a coupon's status.

    If is_active is omitted and the status is not ACTIVE,
    the service will automatically deactivate the coupon.
    """

    return await service.update_coupon_status(
        coupon_id,
        status=coupon_status,
        is_active=is_active,
    )


# ==========================================================
# Administration - All Coupons
# ==========================================================

@router.get(
    "/coupons/admin/all",
    response_model=list[LoyaltyCouponResponse],
    status_code=status.HTTP_200_OK,
    summary="Get All Loyalty Coupons",
    description=(
        "Retrieve all loyalty coupons. Intended primarily "
        "for administrative operations."
    ),
)
async def get_all_coupons(
    service: LoyaltyCouponServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of coupons to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of coupons to skip.",
        ),
    ] = 0,
) -> list[LoyaltyCouponResponse]:
    """
    Retrieve all loyalty coupons.
    """

    return await service.get_all_coupons(
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Administration - Coupons by Status
# ==========================================================

@router.get(
    "/coupons/admin/status/{coupon_status}",
    response_model=list[LoyaltyCouponResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Loyalty Coupons by Status",
    description=(
        "Retrieve loyalty coupons filtered by status."
    ),
)
async def get_coupons_by_status(
    coupon_status: Annotated[
        CouponStatus,
        Path(
            description="Coupon status.",
        ),
    ],
    service: LoyaltyCouponServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of coupons to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of coupons to skip.",
        ),
    ] = 0,
) -> list[LoyaltyCouponResponse]:
    """
    Retrieve loyalty coupons filtered by status.
    """

    return await service.get_coupons_by_status(
        status=coupon_status,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Administration - Coupons by Type
# ==========================================================

@router.get(
    "/coupons/admin/type/{coupon_type}",
    response_model=list[LoyaltyCouponResponse],
    status_code=status.HTTP_200_OK,
    summary="Get Loyalty Coupons by Type",
    description=(
        "Retrieve loyalty coupons filtered by coupon type."
    ),
)
async def get_coupons_by_type(
    coupon_type: Annotated[
        CouponType,
        Path(
            description="Coupon type.",
        ),
    ],
    service: LoyaltyCouponServiceDep,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of coupons to return.",
        ),
    ] = 100,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of coupons to skip.",
        ),
    ] = 0,
) -> list[LoyaltyCouponResponse]:
    """
    Retrieve loyalty coupons filtered by coupon type.
    """

    return await service.get_coupons_by_type(
        coupon_type=coupon_type,
        limit=limit,
        offset=offset,
    )


# ==========================================================
# Administration - Reward Redemption Lookup
# ==========================================================

@router.get(
    "/coupons/admin/reward-redemption/{reward_redemption_id}",
    response_model=LoyaltyCouponResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Coupon by Reward Redemption",
    description=(
        "Retrieve the loyalty coupon generated from a "
        "specific reward redemption."
    ),
)
async def get_coupon_by_reward_redemption(
    reward_redemption_id: Annotated[
        int,
        Path(
            ge=1,
            description="Reward redemption ID.",
        ),
    ],
    service: LoyaltyCouponServiceDep,
) -> LoyaltyCouponResponse:
    """
    Retrieve the coupon associated with a reward redemption.
    """

    return await service.get_coupon_by_reward_redemption(
        reward_redemption_id,
    )


# ==========================================================
# Administration - Payment Transaction Lookup
# ==========================================================

@router.get(
    "/coupons/admin/payment-transaction/{payment_transaction_id}",
    response_model=LoyaltyCouponResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Coupon by Payment Transaction",
    description=(
        "Retrieve the loyalty coupon associated with a "
        "payment transaction."
    ),
)
async def get_coupon_by_payment_transaction(
    payment_transaction_id: Annotated[
        int,
        Path(
            ge=1,
            description="Payment transaction ID.",
        ),
    ],
    service: LoyaltyCouponServiceDep,
) -> LoyaltyCouponResponse:
    """
    Retrieve the coupon associated with a payment transaction.
    """

    return await service.get_coupon_by_payment_transaction(
        payment_transaction_id,
    )


# ==========================================================
# Administration - Coupon Count
# ==========================================================

@router.get(
    "/coupons/admin/count",
    response_model=int,
    status_code=status.HTTP_200_OK,
    summary="Count Loyalty Coupons",
    description="Return the total number of loyalty coupons.",
)
async def count_all_coupons(
    service: LoyaltyCouponServiceDep,
) -> int:
    """
    Return total loyalty coupon count.
    """

    return await service.count_all_coupons()


# ==========================================================
# Administration - Customer Coupon Count
# ==========================================================

@router.get(
    "/coupons/admin/customer/{customer_id}/count",
    response_model=int,
    status_code=status.HTTP_200_OK,
    summary="Count Customer Loyalty Coupons",
    description=(
        "Return the total number of loyalty coupons "
        "belonging to a customer."
    ),
)
async def count_customer_coupons(
    customer_id: Annotated[
        int,
        Path(
            ge=1,
            description="Customer ID.",
        ),
    ],
    service: LoyaltyCouponServiceDep,
) -> int:
    """
    Return total coupon count for a customer.
    """

    return await service.count_customer_coupons(
        customer_id=customer_id,
    )


# ==========================================================
# Administration - Customer Coupon Count by Status
# ==========================================================

@router.get(
    "/coupons/admin/customer/{customer_id}/count/status/{coupon_status}",
    response_model=int,
    status_code=status.HTTP_200_OK,
    summary="Count Customer Coupons by Status",
    description=(
        "Return the number of a customer's loyalty coupons "
        "filtered by status."
    ),
)
async def count_customer_coupons_by_status(
    customer_id: Annotated[
        int,
        Path(
            ge=1,
            description="Customer ID.",
        ),
    ],
    coupon_status: Annotated[
        CouponStatus,
        Path(
            description="Coupon status.",
        ),
    ],
    service: LoyaltyCouponServiceDep,
) -> int:
    """
    Return customer coupon count filtered by status.
    """

    return await service.count_customer_coupons_by_status(
        customer_id=customer_id,
        status=coupon_status,
    )


# ==========================================================
# Administration - Delete Coupon
# ==========================================================

@router.delete(
    "/coupons/{coupon_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Loyalty Coupon",
    description=(
        "Delete an unused loyalty coupon. Used coupons "
        "cannot be deleted because they are retained for "
        "audit purposes."
    ),
)
async def delete_coupon(
    coupon_id: Annotated[
        int,
        Path(
            ge=1,
            description="Loyalty coupon ID.",
        ),
    ],
    service: LoyaltyCouponServiceDep,
) -> None:
    """
    Delete an unused loyalty coupon.
    """

    await service.delete_coupon(
        coupon_id,
    )