"""
Loyalty Referral Service Dependencies.

Dependency Injection providers for the LoyaltyReferralService.

This module composes the LoyaltyReferralService by wiring:

    DbSession
        +
    LoyaltyReferralRepository
        +
    LoyaltyService

Business logic belongs in LoyaltyReferralService.

Persistence belongs in LoyaltyReferralRepository.
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

from app.repositories.loyalty_referral_repository import (
    LoyaltyReferralRepository,
)

from app.services.loyalty_referral_service import (
    LoyaltyReferralService,
)


# ==========================================================
# Loyalty Referral Repository
# ==========================================================


def get_loyalty_referral_repository(
    db: DbSession,
) -> LoyaltyReferralRepository:
    """
    Return a LoyaltyReferralRepository instance using the
    current database session.
    """

    return LoyaltyReferralRepository(
        db=db,
    )


# ==========================================================
# Loyalty Referral Service
# ==========================================================


def get_loyalty_referral_service(
    db: DbSession,
    repository: Annotated[
        LoyaltyReferralRepository,
        Depends(get_loyalty_referral_repository),
    ],
    loyalty_service: LoyaltyServiceDep,
) -> LoyaltyReferralService:
    """
    Return a fully configured LoyaltyReferralService instance.

    The service receives:

    - The current database session.
    - A LoyaltyReferralRepository backed by that session.
    - The existing LoyaltyService for loyalty-account and
      loyalty-point operations.
    """

    return LoyaltyReferralService(
        db=db,
        repository=repository,
        loyalty_service=loyalty_service,
    )


# ==========================================================
# Dependency Aliases
# ==========================================================


LoyaltyReferralRepositoryDep = Annotated[
    LoyaltyReferralRepository,
    Depends(get_loyalty_referral_repository),
]


LoyaltyReferralServiceDep = Annotated[
    LoyaltyReferralService,
    Depends(get_loyalty_referral_service),
]