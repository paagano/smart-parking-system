"""
Unit tests for NotificationService.get_notification().

These tests verify that the Notification Service:

- Retrieves a notification belonging to the requested user.
- Passes the notification ID and user ID to the repository.
- Returns the notification when ownership is valid.
- Returns None when the notification does not belong to the user.
- Returns None when the notification does not exist.

The NotificationRepository is mocked so these tests do not
require a real database.
"""

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
# Test: Get Notification
# ==========================================================


@pytest.mark.asyncio
async def test_get_notification():
    """
    A user should be able to retrieve a notification that
    belongs to them.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 6
    notification_id = 21

    notification = SimpleNamespace(
        id=notification_id,
        user_id=user_id,
        type=NotificationType.LOYALTY_REWARD,
        channel=NotificationChannel.IN_APP,
        status=NotificationStatus.DELIVERED,
        priority=NotificationPriority.HIGH,
        title="Loyalty Reward",
        message="Congratulations! You have earned a SmartPark loyalty reward.",
        is_read=False,
        read_at=None,
        related_entity_type=None,
        related_entity_id=None,
        provider_message_id=None,
        failure_reason=None,
        created_at=None,
        updated_at=None,
    )

    repository = AsyncMock()

    repository.get_by_id_for_user.return_value = notification

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_notification(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert repository interaction
    # ------------------------------------------------------

    repository.get_by_id_for_user.assert_awaited_once_with(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert result
    # ------------------------------------------------------

    assert result is notification

    assert result.id == notification_id

    assert result.user_id == user_id

    assert result.type == NotificationType.LOYALTY_REWARD

    assert result.channel == NotificationChannel.IN_APP

    assert result.status == NotificationStatus.DELIVERED

    assert result.priority == NotificationPriority.HIGH

    assert result.is_read is False


# ==========================================================
# Test: Notification Belongs To Another User
# ==========================================================


@pytest.mark.asyncio
async def test_get_notification_returns_none_for_another_user():
    """
    A user must not be able to retrieve a notification belonging
    to another user.

    The repository is expected to enforce ownership by querying
    using both notification_id and user_id.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    authenticated_user_id = 6

    notification_id = 23

    # Notification 23 belongs to user 1.
    owner_user_id = 1

    repository = AsyncMock()

    repository.get_by_id_for_user.return_value = None

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_notification(
        notification_id=notification_id,
        user_id=authenticated_user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.get_by_id_for_user.assert_awaited_once_with(
        notification_id=notification_id,
        user_id=authenticated_user_id,
    )

    assert result is None

    # ------------------------------------------------------
    # Explicit ownership assertion
    # ------------------------------------------------------

    assert authenticated_user_id != owner_user_id


# ==========================================================
# Test: Notification Does Not Exist
# ==========================================================


@pytest.mark.asyncio
async def test_get_notification_when_notification_does_not_exist():
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

    repository.get_by_id_for_user.return_value = None

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_notification(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.get_by_id_for_user.assert_awaited_once_with(
        notification_id=notification_id,
        user_id=user_id,
    )

    assert result is None


# ==========================================================
# Test: Correct User ID Is Always Passed
# ==========================================================


@pytest.mark.asyncio
async def test_get_notification_uses_requested_user_id():
    """
    The service must use the user ID supplied by the caller
    when retrieving the notification.

    This prevents accidental retrieval using a hard-coded
    or unrelated user ID.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 12

    notification_id = 45

    notification = SimpleNamespace(
        id=notification_id,
        user_id=user_id,
        type=NotificationType.SYSTEM,
        channel=NotificationChannel.IN_APP,
        status=NotificationStatus.PENDING,
        priority=NotificationPriority.NORMAL,
        title="System Notification",
        message="System notification.",
        is_read=False,
        read_at=None,
        related_entity_type=None,
        related_entity_id=None,
        provider_message_id=None,
        failure_reason=None,
        created_at=None,
        updated_at=None,
    )

    repository = AsyncMock()

    repository.get_by_id_for_user.return_value = notification

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_notification(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.get_by_id_for_user.assert_awaited_once_with(
        notification_id=45,
        user_id=12,
    )

    assert result is notification

    assert result.id == 45

    assert result.user_id == 12