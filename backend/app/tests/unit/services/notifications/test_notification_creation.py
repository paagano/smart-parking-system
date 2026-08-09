"""
Notification Service - Creation Tests

Unit tests for NotificationService.create_notification().

These tests verify notification creation at the service layer
without requiring a real database.

Persistence is mocked through the NotificationRepository.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.models.notification import Notification
from app.schemas.notification import NotificationCreate
from app.services.notification_service import NotificationService


# ==========================================================
# Fixtures
# ==========================================================


@pytest.fixture
def notification_repository():
    """
    Provide a mocked NotificationRepository.

    The service depends on the repository for persistence,
    but the unit test should not require a real database.
    """

    repository = MagicMock()

    repository.create = AsyncMock()

    repository.db = MagicMock()
    repository.db.commit = AsyncMock()
    repository.db.refresh = AsyncMock()

    return repository


@pytest.fixture
def notification_service(notification_repository):
    """
    Provide a NotificationService using the mocked repository.
    """

    return NotificationService(
        repository=notification_repository,
    )


# ==========================================================
# Notification Creation
# ==========================================================


@pytest.mark.asyncio
async def test_create_notification(
    notification_service,
    notification_repository,
):
    """
    A valid notification should be created successfully.

    The service should:

    - create the Notification entity
    - assign the supplied user
    - preserve type/channel/priority
    - preserve title/message
    - initialise the notification as unread
    - initialise the notification as PENDING
    - persist through the repository
    - commit the transaction
    - refresh the entity
    """

    notification_data = NotificationCreate(
        user_id=6,
        type=NotificationType.PAYMENT_SUCCESSFUL,
        channel=NotificationChannel.IN_APP,
        priority=NotificationPriority.HIGH,
        title="Payment Successful",
        message="Your SmartPark parking payment was completed successfully.",
        related_entity_type="payment_transaction",
        related_entity_id=65,
    )

    created_notification = Notification(
        user_id=notification_data.user_id,
        type=notification_data.type,
        channel=notification_data.channel,
        status=NotificationStatus.PENDING,
        priority=notification_data.priority,
        title=notification_data.title,
        message=notification_data.message,
        is_read=False,
        read_at=None,
        related_entity_type=notification_data.related_entity_type,
        related_entity_id=notification_data.related_entity_id,
    )

    # Simulate repository persistence.
    # The real repository returns the persisted Notification.
    notification_repository.create.return_value = created_notification

    result = await notification_service.create_notification(
        notification_data
    )

    # ------------------------------------------------------
    # Verify returned notification
    # ------------------------------------------------------

    assert result is created_notification

    assert result.user_id == 6

    assert result.type == NotificationType.PAYMENT_SUCCESSFUL

    assert result.channel == NotificationChannel.IN_APP

    assert result.status == NotificationStatus.PENDING

    assert result.priority == NotificationPriority.HIGH

    assert result.title == "Payment Successful"

    assert (
        result.message
        == "Your SmartPark parking payment was completed successfully."
    )

    assert result.is_read is False

    assert result.read_at is None

    assert result.related_entity_type == "payment_transaction"

    assert result.related_entity_id == 65

    # ------------------------------------------------------
    # Verify repository interaction
    # ------------------------------------------------------

    notification_repository.create.assert_awaited_once()

    created_argument = (
        notification_repository.create.call_args.args[0]
    )

    assert isinstance(created_argument, Notification)

    assert created_argument.user_id == 6

    assert (
        created_argument.type
        == NotificationType.PAYMENT_SUCCESSFUL
    )

    assert (
        created_argument.channel
        == NotificationChannel.IN_APP
    )

    assert (
        created_argument.status
        == NotificationStatus.PENDING
    )

    assert (
        created_argument.priority
        == NotificationPriority.HIGH
    )

    assert created_argument.title == "Payment Successful"

    assert (
        created_argument.message
        == "Your SmartPark parking payment was completed successfully."
    )

    assert created_argument.is_read is False

    assert created_argument.read_at is None

    assert (
        created_argument.related_entity_type
        == "payment_transaction"
    )

    assert created_argument.related_entity_id == 65

    # ------------------------------------------------------
    # Verify transaction handling
    # ------------------------------------------------------

    notification_repository.db.commit.assert_awaited_once()

    notification_repository.db.refresh.assert_awaited_once_with(
        created_notification
    )


# ==========================================================
# Default Notification Values
# ==========================================================


@pytest.mark.asyncio
async def test_create_notification_uses_pending_status(
    notification_service,
    notification_repository,
):
    """
    Newly created notifications must always start as PENDING.

    This verifies that the service controls the notification
    lifecycle state rather than allowing callers to create
    notifications directly as SENT or DELIVERED.
    """

    notification_data = NotificationCreate(
        user_id=6,
        type=NotificationType.SYSTEM,
        channel=NotificationChannel.IN_APP,
        priority=NotificationPriority.NORMAL,
        title="System Notification",
        message="This is a SmartPark system notification.",
    )

    async def create_and_return(notification):
        """
        Simulate repository persistence while returning
        the entity supplied by the service.
        """

        return notification

    notification_repository.create.side_effect = (
        create_and_return
    )

    result = await notification_service.create_notification(
        notification_data
    )

    assert result.status == NotificationStatus.PENDING

    assert result.is_read is False

    assert result.read_at is None

    notification_repository.create.assert_awaited_once()

    created_argument = (
        notification_repository.create.call_args.args[0]
    )

    assert created_argument.status == NotificationStatus.PENDING

    assert created_argument.is_read is False

    assert created_argument.read_at is None


# ==========================================================
# Related Entity Handling
# ==========================================================


@pytest.mark.asyncio
async def test_create_notification_without_related_entity(
    notification_service,
    notification_repository,
):
    """
    A notification can be created without a related business
    entity.

    related_entity_type and related_entity_id should remain None.
    """

    notification_data = NotificationCreate(
        user_id=6,
        type=NotificationType.SYSTEM,
        channel=NotificationChannel.PUSH,
        priority=NotificationPriority.NORMAL,
        title="System Alert",
        message="SmartPark has generated a system alert.",
    )

    async def create_and_return(notification):
        return notification

    notification_repository.create.side_effect = (
        create_and_return
    )

    result = await notification_service.create_notification(
        notification_data
    )

    assert result.user_id == 6

    assert result.type == NotificationType.SYSTEM

    assert result.channel == NotificationChannel.PUSH

    assert result.priority == NotificationPriority.NORMAL

    assert result.status == NotificationStatus.PENDING

    assert result.is_read is False

    assert result.related_entity_type is None

    assert result.related_entity_id is None

    notification_repository.create.assert_awaited_once()

    notification_repository.db.commit.assert_awaited_once()

    notification_repository.db.refresh.assert_awaited_once_with(
        result
    )