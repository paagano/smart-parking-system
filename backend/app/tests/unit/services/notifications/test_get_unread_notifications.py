"""
Unit tests for NotificationService.get_unread_notifications().

These tests verify that the Notification Service correctly retrieves
unread notifications belonging to a specific user.

The NotificationRepository is mocked so these tests remain isolated
from the database.
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
# Test: Get Unread Notifications
# ==========================================================


@pytest.mark.asyncio
async def test_get_unread_notifications():
    """
    The service should return only unread notifications
    belonging to the requested user.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 6
    skip = 0
    limit = 10

    unread_notification_1 = SimpleNamespace(
        id=31,
        user_id=user_id,
        type=NotificationType.PAYMENT_SUCCESSFUL,
        channel=NotificationChannel.IN_APP,
        status=NotificationStatus.DELIVERED,
        priority=NotificationPriority.HIGH,
        title="Payment Successful",
        message="Your parking payment was completed successfully.",
        is_read=False,
        read_at=None,
        related_entity_type="payment_transaction",
        related_entity_id=65,
        provider_message_id=None,
        failure_reason=None,
        created_at=None,
        updated_at=None,
    )

    unread_notification_2 = SimpleNamespace(
        id=32,
        user_id=user_id,
        type=NotificationType.LOYALTY_REWARD,
        channel=NotificationChannel.PUSH,
        status=NotificationStatus.SENT,
        priority=NotificationPriority.NORMAL,
        title="Loyalty Reward",
        message="You have received a SmartPark loyalty reward.",
        is_read=False,
        read_at=None,
        related_entity_type=None,
        related_entity_id=None,
        provider_message_id=None,
        failure_reason=None,
        created_at=None,
        updated_at=None,
    )

    unread_notifications = [
        unread_notification_1,
        unread_notification_2,
    ]

    repository = AsyncMock()

    repository.get_unread_notifications.return_value = (
        unread_notifications,
        2,
    )

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_unread_notifications(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    # ------------------------------------------------------
    # Assert repository interaction
    # ------------------------------------------------------

    repository.get_unread_notifications.assert_awaited_once_with(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    # ------------------------------------------------------
    # Assert response
    # ------------------------------------------------------

    assert result.total == 2

    assert len(result.items) == 2

    assert result.skip == skip

    assert result.limit == limit

    # ------------------------------------------------------
    # Assert first notification
    # ------------------------------------------------------

    first = result.items[0]

    assert first.id == 31
    assert first.user_id == user_id

    assert (
        first.type
        == NotificationType.PAYMENT_SUCCESSFUL
    )

    assert first.channel == NotificationChannel.IN_APP

    assert first.status == NotificationStatus.DELIVERED

    assert first.priority == NotificationPriority.HIGH

    assert first.is_read is False

    assert first.read_at is None

    assert first.related_entity_type == "payment_transaction"

    assert first.related_entity_id == 65

    # ------------------------------------------------------
    # Assert second notification
    # ------------------------------------------------------

    second = result.items[1]

    assert second.id == 32
    assert second.user_id == user_id

    assert (
        second.type
        == NotificationType.LOYALTY_REWARD
    )

    assert second.channel == NotificationChannel.PUSH

    assert second.status == NotificationStatus.SENT

    assert second.priority == NotificationPriority.NORMAL

    assert second.is_read is False

    assert second.read_at is None

    assert second.related_entity_type is None

    assert second.related_entity_id is None


# ==========================================================
# Test: Pagination Parameters
# ==========================================================


@pytest.mark.asyncio
async def test_get_unread_notifications_passes_pagination_parameters():
    """
    The service should pass skip and limit to the repository
    unchanged.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 6
    skip = 10
    limit = 5

    repository = AsyncMock()

    repository.get_unread_notifications.return_value = (
        [],
        18,
    )

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_unread_notifications(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.get_unread_notifications.assert_awaited_once_with(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    assert result.total == 18

    assert result.items == []

    assert result.skip == 10

    assert result.limit == 5


# ==========================================================
# Test: No Unread Notifications
# ==========================================================


@pytest.mark.asyncio
async def test_get_unread_notifications_when_none_exist():
    """
    The service should return an empty list and a total of zero
    when the user has no unread notifications.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 999
    skip = 0
    limit = 10

    repository = AsyncMock()

    repository.get_unread_notifications.return_value = (
        [],
        0,
    )

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_unread_notifications(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.get_unread_notifications.assert_awaited_once_with(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    assert result.total == 0

    assert result.items == []

    assert result.skip == 0

    assert result.limit == 10