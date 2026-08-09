"""
Notification Dependencies

Dependency Injection providers for the Notification module.

This module composes the Notification subsystem by wiring together:

- NotificationService
- NotificationRepository

Business logic belongs in the Service layer.
Persistence belongs in the Repository layer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.repositories import (
    NotificationRepositoryDep,
)

from app.services.notification_service import (
    NotificationService,
)


# ==========================================================
# Notification Service
# ==========================================================

def get_notification_service(
    repository: NotificationRepositoryDep,
) -> NotificationService:
    """
    Return a NotificationService instance.
    """

    return NotificationService(
        repository=repository,
    )


# ==========================================================
# Dependency Alias
# ==========================================================

NotificationServiceDep = Annotated[
    NotificationService,
    Depends(get_notification_service),
]