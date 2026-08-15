"""
Loyalty Coupon Service Dependencies.

Dependency Injection providers for the LoyaltyCouponService.

This module composes the LoyaltyCouponService by wiring the
LoyaltyCouponRepository, LoyaltyService, and NotificationService
into the service.

Business logic belongs in LoyaltyCouponService.
Persistence belongs in LoyaltyCouponRepository.
Notification persistence belongs in the Notification subsystem.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.loyalty import (
    LoyaltyServiceDep,
)

from app.api.dependencies.notifications import (
    NotificationServiceDep,
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
    notification_service: NotificationServiceDep,
) -> LoyaltyCouponService:
    """
    Return a fully configured LoyaltyCouponService instance.

    The service receives:

    - The current database session.
    - A LoyaltyCouponRepository backed by that session.
    - The existing LoyaltyService for loyalty-account
      operations and loyalty business rules.
    - The existing NotificationService for loyalty coupon
      notifications.
    """

    return LoyaltyCouponService(
        db=db,
        repository=repository,
        loyalty_service=loyalty_service,
        notification_service=notification_service,
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