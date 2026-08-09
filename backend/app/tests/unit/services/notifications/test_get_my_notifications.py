"""
Unit tests for NotificationService.get_user_notifications().

These tests verify that the Notification Service correctly retrieves
notifications belonging to a specific user and applies pagination.

Business logic is tested independently of the database by mocking
the NotificationRepository.
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
# Test: Get My Notifications
# ==========================================================


@pytest.mark.asyncio
async def test_get_my_notifications():
    """
    The service should return notifications belonging to the
    requested user together with the total notification count.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 6
    skip = 0
    limit = 10

    notification_1 = SimpleNamespace(
        id=21,
        user_id=user_id,
        type=NotificationType.LOYALTY_REWARD,
        channel=NotificationChannel.IN_APP,
        status=NotificationStatus.DELIVERED,
        priority=NotificationPriority.HIGH,
        title="[SEED] SmartPark Notification - Loyalty Reward",
        message="Congratulations! You have earned a SmartPark loyalty reward.",
        is_read=False,
        read_at=None,
        related_entity_type=None,
        related_entity_id=None,
        provider_message_id="SEED-PROVIDER-21",
        failure_reason=None,
        created_at=None,
        updated_at=None,
    )

    notification_2 = SimpleNamespace(
        id=14,
        user_id=user_id,
        type=NotificationType.PAYMENT_SUCCESSFUL,
        channel=NotificationChannel.IN_APP,
        status=NotificationStatus.DELIVERED,
        priority=NotificationPriority.HIGH,
        title="[SEED] SmartPark Notification - Payment Successful",
        message="Your parking payment was completed successfully.",
        is_read=False,
        read_at=None,
        related_entity_type=None,
        related_entity_id=None,
        provider_message_id="SEED-PROVIDER-14",
        failure_reason=None,
        created_at=None,
        updated_at=None,
    )

    notifications = [
        notification_1,
        notification_2,
    ]

    repository = AsyncMock()

    repository.get_user_notifications.return_value = (
        notifications,
        2,
    )

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_user_notifications(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.get_user_notifications.assert_awaited_once_with(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    assert result.total == 2
    assert len(result.items) == 2

    assert result.items[0].id == 21
    assert result.items[0].user_id == user_id
    assert result.items[0].type == NotificationType.LOYALTY_REWARD
    assert result.items[0].channel == NotificationChannel.IN_APP
    assert result.items[0].is_read is False

    assert result.items[1].id == 14
    assert result.items[1].user_id == user_id
    assert result.items[1].type == NotificationType.PAYMENT_SUCCESSFUL
    assert result.items[1].channel == NotificationChannel.IN_APP
    assert result.items[1].is_read is False

    assert result.skip == skip
    assert result.limit == limit


# ==========================================================
# Test: Pagination Parameters
# ==========================================================


@pytest.mark.asyncio
async def test_get_my_notifications_passes_pagination_parameters():
    """
    The service should pass the requested skip and limit values
    to the repository unchanged.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 6
    skip = 5
    limit = 10

    repository = AsyncMock()

    repository.get_user_notifications.return_value = (
        [],
        15,
    )

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_user_notifications(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.get_user_notifications.assert_awaited_once_with(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    assert result.total == 15
    assert result.items == []
    assert result.skip == 5
    assert result.limit == 10


# ==========================================================
# Test: User With No Notifications
# ==========================================================


@pytest.mark.asyncio
async def test_get_my_notifications_when_user_has_no_notifications():
    """
    The service should return an empty notification list when
    the user has no notifications.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 999
    skip = 0
    limit = 100

    repository = AsyncMock()

    repository.get_user_notifications.return_value = (
        [],
        0,
    )

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_user_notifications(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.get_user_notifications.assert_awaited_once_with(
        user_id=user_id,
        skip=skip,
        limit=limit,
    )

    assert result.total == 0
    assert result.items == []
    assert result.skip == 0
    assert result.limit == 100