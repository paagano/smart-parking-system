"""
Notification Dependencies

Dependency Injection providers for the Notification module.

This module composes the Notification subsystem by wiring together:

- NotificationService
- NotificationRepository
- UserRepository
- EmailService

Business logic belongs in the Service layer.
Persistence belongs in the Repository layer.
Email delivery belongs in EmailService.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from app.api.dependencies.repositories import (
    NotificationRepositoryDep,
    UserRepositoryDep,
)

from app.services.email_service import (
    EmailService,
)

from app.services.notification_service import (
    NotificationService,
)


# ==========================================================
# Email Service
# ==========================================================


def get_email_service() -> EmailService:
    """
    Return an EmailService instance.
    """

    return EmailService()


# ==========================================================
# Notification Service
# ==========================================================


def get_notification_service(
    repository: NotificationRepositoryDep,
    user_repository: UserRepositoryDep,
    email_service: Annotated[
        EmailService,
        Depends(get_email_service),
    ],
) -> NotificationService:
    """
    Return a fully configured NotificationService instance.

    The service receives:

    - NotificationRepository for notification persistence.
    - UserRepository for resolving recipient email addresses.
    - EmailService for email delivery.
    """

    return NotificationService(
        repository=repository,
        user_repository=user_repository,
        email_service=email_service,
    )


# ==========================================================
# Dependency Alias
# ==========================================================

NotificationServiceDep = Annotated[
    NotificationService,
    Depends(get_notification_service),
]