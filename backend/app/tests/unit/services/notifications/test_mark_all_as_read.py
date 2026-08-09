"""
Unit tests for NotificationService.mark_all_as_read().

These tests verify that the Notification Service correctly marks
all unread notifications belonging to a specific user as read.

The NotificationRepository is mocked so these tests do not
require a real database.
"""

from unittest.mock import AsyncMock

import pytest

from app.services.notification_service import NotificationService


# ==========================================================
# Test: Mark All Notifications As Read
# ==========================================================


@pytest.mark.asyncio
async def test_mark_all_as_read():
    """
    The service should mark all unread notifications belonging
    to the requested user as read and return the number updated.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 6

    repository = AsyncMock()

    repository.mark_all_as_read.return_value = 5

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.mark_all_as_read(
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert repository interaction
    # ------------------------------------------------------

    repository.mark_all_as_read.assert_awaited_once_with(
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert response
    # ------------------------------------------------------

    assert result.updated_count == 5


# ==========================================================
# Test: No Unread Notifications
# ==========================================================


@pytest.mark.asyncio
async def test_mark_all_as_read_when_none_exist():
    """
    The service should return an updated count of zero when
    the user has no unread notifications.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 999

    repository = AsyncMock()

    repository.mark_all_as_read.return_value = 0

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.mark_all_as_read(
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.mark_all_as_read.assert_awaited_once_with(
        user_id=user_id,
    )

    assert result.updated_count == 0


# ==========================================================
# Test: Correct User ID Is Used
# ==========================================================


@pytest.mark.asyncio
async def test_mark_all_as_read_uses_requested_user_id():
    """
    The service must pass the supplied user ID to the repository.

    This ensures that bulk notification updates remain scoped
    to the authenticated user.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 12

    repository = AsyncMock()

    repository.mark_all_as_read.return_value = 7

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.mark_all_as_read(
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.mark_all_as_read.assert_awaited_once_with(
        user_id=12,
    )

    assert result.updated_count == 7


# ==========================================================
# Test: Idempotent Bulk Read
# ==========================================================


@pytest.mark.asyncio
async def test_mark_all_as_read_when_notifications_are_already_read():
    """
    When all notifications are already read, the repository
    should report zero updates and the service should return
    an updated count of zero.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 6

    repository = AsyncMock()

    repository.mark_all_as_read.return_value = 0

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.mark_all_as_read(
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.mark_all_as_read.assert_awaited_once_with(
        user_id=user_id,
    )

    assert result.updated_count == 0