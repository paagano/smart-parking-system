"""
Loyalty Reward Service Dependencies.

Dependency Injection providers for the LoyaltyRewardService.

This module composes the LoyaltyRewardService by wiring:

    DbSession
        +
    LoyaltyRewardRepository
        +
    LoyaltyService
        =
    LoyaltyRewardService

Business logic belongs in LoyaltyRewardService.
Persistence belongs in LoyaltyRewardRepository.
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

from app.repositories.loyalty_reward_repository import (
    LoyaltyRewardRepository,
)

from app.services.loyalty_reward_service import (
    LoyaltyRewardService,
)


# ==========================================================
# Loyalty Reward Repository
# ==========================================================


def get_loyalty_reward_repository(
    db: DbSession,
) -> LoyaltyRewardRepository:
    """
    Return a LoyaltyRewardRepository instance using the
    current database session.
    """

    return LoyaltyRewardRepository(
        db=db,
    )


# ==========================================================
# Dependency Alias
# ==========================================================


LoyaltyRewardRepositoryDep = Annotated[
    LoyaltyRewardRepository,
    Depends(get_loyalty_reward_repository),
]


# ==========================================================
# Loyalty Reward Service
# ==========================================================


def get_loyalty_reward_service(
    db: DbSession,
    repository: LoyaltyRewardRepositoryDep,
    loyalty_service: LoyaltyServiceDep,
) -> LoyaltyRewardService:
    """
    Return a fully configured LoyaltyRewardService instance.

    The service receives:

        - the current database session
        - a LoyaltyRewardRepository backed by that session
        - the existing LoyaltyService

    LoyaltyService is responsible for loyalty point balance
    manipulation.

    LoyaltyRewardRepository is responsible for reward and
    redemption persistence.
    """

    return LoyaltyRewardService(
        db=db,
        repository=repository,
        loyalty_service=loyalty_service,
    )


# ==========================================================
# Dependency Alias
# ==========================================================


LoyaltyRewardServiceDep = Annotated[
    LoyaltyRewardService,
    Depends(get_loyalty_reward_service),
]