"""
Loyalty Service Dependencies.

Dependency Injection providers for the LoyaltyService.

This module composes the LoyaltyService by wiring the
LoyaltyRepository into the service.

Business logic belongs in LoyaltyService.
Persistence belongs in LoyaltyRepository.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.repositories import (
    DbSession,
)

from app.repositories.loyalty_repository import (
    LoyaltyRepository,
)

from app.services.loyalty_service import (
    LoyaltyService,
)


# ==========================================================
# Loyalty Repository
# ==========================================================


def get_loyalty_repository(
    db: DbSession,
) -> LoyaltyRepository:
    """
    Return a LoyaltyRepository instance using the
    current database session.
    """

    return LoyaltyRepository(
        db=db,
    )


# ==========================================================
# Loyalty Service
# ==========================================================


def get_loyalty_service(
    db: DbSession,
) -> LoyaltyService:
    """
    Return a fully configured LoyaltyService instance.

    The service receives the current database session and
    a LoyaltyRepository backed by that same session.
    """

    repository = LoyaltyRepository(
        db=db,
    )

    return LoyaltyService(
        db=db,
        repository=repository,
    )


# ==========================================================
# Dependency Aliases
# ==========================================================


LoyaltyRepositoryDep = Annotated[
    LoyaltyRepository,
    Depends(get_loyalty_repository),
]


LoyaltyServiceDep = Annotated[
    LoyaltyService,
    Depends(get_loyalty_service),
]