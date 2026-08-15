"""
Loyalty Dependencies.

Dependency Injection providers for the Loyalty module.

This module composes LoyaltyService by wiring together:

- LoyaltyRepository
- NotificationService

Business logic belongs in LoyaltyService.

Persistence belongs in LoyaltyRepository.

Notification persistence and delivery belong in the
Notification subsystem.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.repositories import (
    DbSession,
)

from app.api.dependencies.notifications import (
    NotificationServiceDep,
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
    Return a LoyaltyRepository instance using the current
    database session.
    """

    return LoyaltyRepository(
        db=db,
    )


# ==========================================================
# Loyalty Service
# ==========================================================


def get_loyalty_service(
    db: DbSession,
    repository: Annotated[
        LoyaltyRepository,
        Depends(get_loyalty_repository),
    ],
    notification_service: NotificationServiceDep,
) -> LoyaltyService:
    """
    Return a fully configured LoyaltyService instance.

    The service receives:

    - Current database session.
    - LoyaltyRepository backed by that session.
    - Existing NotificationService for Loyalty event
      notifications.
    """

    return LoyaltyService(
        db=db,
        repository=repository,
        notification_service=notification_service,
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