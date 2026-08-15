"""
Loyalty Coupon Service Dependencies.

Dependency Injection providers for the LoyaltyCouponService.

This module composes the LoyaltyCouponService by wiring the
LoyaltyCouponRepository and LoyaltyService into the service.

Business logic belongs in LoyaltyCouponService.
Persistence belongs in LoyaltyCouponRepository.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.loyalty import (
    LoyaltyServiceDep,
)

from app.api.dependencies.repositories import (
    DbSession,
)

from app.repositories.loyalty_coupon_repository import (
    LoyaltyCouponRepository,
)

from app.services.loyalty_coupon_service import (
    LoyaltyCouponService,
)


# ==========================================================
# Loyalty Coupon Repository
# ==========================================================


def get_loyalty_coupon_repository(
    db: DbSession,
) -> LoyaltyCouponRepository:
    """
    Return a LoyaltyCouponRepository instance using the
    current database session.
    """

    return LoyaltyCouponRepository(
        db=db,
    )


# ==========================================================
# Loyalty Coupon Service
# ==========================================================


def get_loyalty_coupon_service(
    db: DbSession,
    repository: Annotated[
        LoyaltyCouponRepository,
        Depends(get_loyalty_coupon_repository),
    ],
    loyalty_service: LoyaltyServiceDep,
) -> LoyaltyCouponService:
    """
    Return a fully configured LoyaltyCouponService instance.

    The service receives:

    - The current database session.
    - A LoyaltyCouponRepository backed by that session.
    - The existing LoyaltyService for loyalty-account
      operations and loyalty business rules.
    """

    return LoyaltyCouponService(
        db=db,
        repository=repository,
        loyalty_service=loyalty_service,
    )


# ==========================================================
# Dependency Aliases
# ==========================================================


LoyaltyCouponRepositoryDep = Annotated[
    LoyaltyCouponRepository,
    Depends(get_loyalty_coupon_repository),
]


LoyaltyCouponServiceDep = Annotated[
    LoyaltyCouponService,
    Depends(get_loyalty_coupon_service),
]