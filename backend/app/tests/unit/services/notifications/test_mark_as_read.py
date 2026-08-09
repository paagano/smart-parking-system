"""
Unit tests for NotificationService.mark_as_read().

These tests verify that the Notification Service correctly marks
a notification as read while preserving the user ownership boundary.

The NotificationRepository is mocked so these tests do not
require a real database.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.services.notification_service import NotificationService


# ==========================================================
# Test: Mark Notification As Read
# ==========================================================


@pytest.mark.asyncio
async def test_mark_as_read():
    """
    A user should be able to mark one of their own notifications
    as read.
    """
    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------
    user_id = 6
    notification_id = 21

    read_at = datetime.now(timezone.utc)

    notification = SimpleNamespace(
        id=notification_id,
        user_id=user_id,
        type=NotificationType.PAYMENT_SUCCESSFUL,
        channel=NotificationChannel.IN_APP,
        status=NotificationStatus.DELIVERED,
        priority=NotificationPriority.HIGH,
        title="Payment Successful",
        message="Your parking payment was completed successfully.",
        is_read=True,
        read_at=read_at,
        related_entity_type="payment_transaction",
        related_entity_id=65,
        provider_message_id=None,
        failure_reason=None,
        created_at=None,
        updated_at=None,
    )

    repository = AsyncMock()
    repository.mark_as_read.return_value = notification

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------
    result = await service.mark_as_read(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert repository interaction
    # ------------------------------------------------------
    repository.mark_as_read.assert_awaited_once_with(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert result
    # ------------------------------------------------------
    assert result is notification
    assert result.id == notification_id
    assert result.user_id == user_id
    assert result.is_read is True
    assert result.read_at == read_at


# ==========================================================
# Test: Ownership Is Enforced
# ==========================================================


@pytest.mark.asyncio
async def test_mark_as_read_returns_none_for_another_users_notification():
    """
    A user must not be able to mark another user's notification
    as read.

    The repository is expected to enforce ownership by using
    both notification_id and user_id.
    """
    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------
    authenticated_user_id = 6
    notification_id = 25

    repository = AsyncMock()
    repository.mark_as_read.return_value = None

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------
    result = await service.mark_as_read(
        notification_id=notification_id,
        user_id=authenticated_user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------
    repository.mark_as_read.assert_awaited_once_with(
        notification_id=notification_id,
        user_id=authenticated_user_id,
    )

    assert result is None


# ==========================================================
# Test: Notification Does Not Exist
# ==========================================================


@pytest.mark.asyncio
async def test_mark_as_read_when_notification_does_not_exist():
    """
    The service should return None when the requested
    notification does not exist.
    """
    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------
    user_id = 6
    notification_id = 999999

    repository = AsyncMock()
    repository.mark_as_read.return_value = None

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------
    result = await service.mark_as_read(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------
    repository.mark_as_read.assert_awaited_once_with(
        notification_id=notification_id,
        user_id=user_id,
    )

    assert result is None


# ==========================================================
# Test: Already Read Notification
# ==========================================================


@pytest.mark.asyncio
async def test_mark_as_read_when_notification_is_already_read():
    """
    Marking an already-read notification as read should remain
    idempotent from the service perspective.

    The notification should still be returned as read.
    """
    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------
    user_id = 6
    notification_id = 30

    read_at = datetime.now(timezone.utc)

    notification = SimpleNamespace(
        id=notification_id,
        user_id=user_id,
        type=NotificationType.SYSTEM,
        channel=NotificationChannel.IN_APP,
        status=NotificationStatus.DELIVERED,
        priority=NotificationPriority.NORMAL,
        title="System Notification",
        message="This notification has already been read.",
        is_read=True,
        read_at=read_at,
        related_entity_type=None,
        related_entity_id=None,
        provider_message_id=None,
        failure_reason=None,
        created_at=None,
        updated_at=None,
    )

    repository = AsyncMock()
    repository.mark_as_read.return_value = notification

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------
    result = await service.mark_as_read(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------
    repository.mark_as_read.assert_awaited_once_with(
        notification_id=notification_id,
        user_id=user_id,
    )

    assert result is notification
    assert result.id == notification_id
    assert result.user_id == user_id
    assert result.is_read is True
    assert result.read_at == read_at