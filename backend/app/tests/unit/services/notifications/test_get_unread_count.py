"""
Unit tests for NotificationService.get_unread_count().

These tests verify that the Notification Service correctly
retrieves the number of unread notifications belonging to
a specific user.

The NotificationRepository is mocked so these tests do not
require a real database.
"""

from unittest.mock import AsyncMock

import pytest

from app.services.notification_service import NotificationService


# ==========================================================
# Test: Get Unread Count
# ==========================================================


@pytest.mark.asyncio
async def test_get_unread_count():
    """
    The service should return the number of unread notifications
    for the requested user.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 6

    repository = AsyncMock()

    repository.get_unread_count.return_value = 3

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_unread_count(
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.get_unread_count.assert_awaited_once_with(
        user_id=user_id,
    )

    assert result.unread_count == 3


# ==========================================================
# Test: Zero Unread Notifications
# ==========================================================


@pytest.mark.asyncio
async def test_get_unread_count_when_none_exist():
    """
    The service should return zero when the user has no
    unread notifications.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 999

    repository = AsyncMock()

    repository.get_unread_count.return_value = 0

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_unread_count(
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.get_unread_count.assert_awaited_once_with(
        user_id=user_id,
    )

    assert result.unread_count == 0


# ==========================================================
# Test: Different Users Are Queried Independently
# ==========================================================


@pytest.mark.asyncio
async def test_get_unread_count_uses_requested_user_id():
    """
    The service must query the repository using the supplied
    user ID and must not use a hard-coded user.
    """

    # ------------------------------------------------------
    # Arrange
    # ------------------------------------------------------

    user_id = 12

    repository = AsyncMock()

    repository.get_unread_count.return_value = 7

    service = NotificationService(
        repository=repository,
    )

    # ------------------------------------------------------
    # Act
    # ------------------------------------------------------

    result = await service.get_unread_count(
        user_id=user_id,
    )

    # ------------------------------------------------------
    # Assert
    # ------------------------------------------------------

    repository.get_unread_count.assert_awaited_once_with(
        user_id=12,
    )

    assert result.unread_count == 7