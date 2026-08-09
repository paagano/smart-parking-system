"""
Unit tests for NotificationService.delete_notification().

These tests verify that the Notification Service correctly
deletes a notification belonging to a specific user.

The NotificationRepository is mocked so these tests do not
require a real database.
"""

from unittest.mock import AsyncMock

import pytest

from app.services.notification_service import NotificationService


# ==========================================================
# Test: Delete Notification
# ==========================================================


@pytest.mark.asyncio
async def test_delete_notification():
    """
    A user should be able to delete one of their own
    notifications.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 6
    notification_id = 21

    repository = AsyncMock()

    repository.delete.return_value = True

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.delete_notification(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert repository interaction
    # ------------------------------------------------------

    repository.delete.assert_awaited_once_with(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert result
    # ------------------------------------------------------

    assert result is True


# ==========================================================
# Test: Notification Does Not Exist
# ==========================================================


@pytest.mark.asyncio
async def test_delete_notification_when_notification_does_not_exist():
    """
    The service should return False when the requested
    notification does not exist.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 6
    notification_id = 999999

    repository = AsyncMock()

    repository.delete.return_value = False

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.delete_notification(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.delete.assert_awaited_once_with(
        notification_id=notification_id,
        user_id=user_id,
    )

    assert result is False


# ==========================================================
# Test: Cannot Delete Another User's Notification
# ==========================================================


@pytest.mark.asyncio
async def test_delete_notification_returns_false_for_another_user():
    """
    A user must not be able to delete another user's
    notification.

    The repository is expected to enforce ownership by using
    both notification_id and user_id.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    authenticated_user_id = 6
    notification_id = 25

    repository = AsyncMock()

    repository.delete.return_value = False

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.delete_notification(
        notification_id=notification_id,
        user_id=authenticated_user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.delete.assert_awaited_once_with(
        notification_id=notification_id,
        user_id=authenticated_user_id,
    )

    assert result is False


# ==========================================================
# Test: Correct User ID Is Used
# ==========================================================


@pytest.mark.asyncio
async def test_delete_notification_uses_requested_user_id():
    """
    The service must pass the supplied user ID to the repository.

    This ensures that deletion remains scoped to the
    authenticated user.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 12
    notification_id = 45

    repository = AsyncMock()

    repository.delete.return_value = True

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.delete_notification(
        notification_id=notification_id,
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.delete.assert_awaited_once_with(
        notification_id=45,
        user_id=12,
    )

    assert result is True