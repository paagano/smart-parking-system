"""
Notification Service

Contains business logic for creating, retrieving, and managing
SmartPark notifications.

The service layer owns:
- Notification creation rules
- Transaction boundaries
- Read/unread state management
- Notification lifecycle management

Database access is delegated to NotificationRepository.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.exceptions.handlers import (
    NotFoundException,
)

from app.models.enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)
from app.models.notification import Notification
from app.repositories.notification_repository import (
    NotificationRepository,
)
from app.schemas.notification import (
    NotificationCreate,
)


class NotificationService:
    """
    Service responsible for Notification business operations.
    """

    def __init__(
        self,
        repository: NotificationRepository,
    ):
        self.repository = repository

    # ==========================================================
    # Create Notification
    # ==========================================================

    async def create_notification(
        self,
        data: NotificationCreate,
    ) -> Notification:
        """
        Create a new notification.

        New notifications always begin in PENDING status.

        The caller specifies:
        - Recipient
        - Notification type
        - Channel
        - Priority
        - Content
        - Optional related entity
        """

        notification = Notification(
            user_id=data.user_id,
            type=data.type,
            channel=data.channel,
            status=NotificationStatus.PENDING,
            priority=data.priority,
            title=data.title,
            message=data.message,
            is_read=False,
            read_at=None,
            related_entity_type=data.related_entity_type,
            related_entity_id=data.related_entity_id,
        )

        notification = await self.repository.create(
            notification,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            notification,
        )

        return notification

    # ==========================================================
    # Get Notification
    # ==========================================================

    async def get_by_id(
        self,
        notification_id: int,
    ) -> Notification:
        """
        Retrieve a notification by ID.

        Raises:
            NotFoundException:
                When the notification does not exist.
        """

        notification = await self.repository.get_by_id(
            notification_id,
        )

        if notification is None:
            raise NotFoundException(
                "Notification not found."
            )

        return notification

    # ==========================================================
    # Get User Notifications
    # ==========================================================

    async def get_user_notifications(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[Notification]]:
        """
        Retrieve notifications belonging to a user.

        Results are returned newest first.
        """

        return await self.repository.get_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit,
        )

    # ==========================================================
    # Get Unread Notifications
    # ==========================================================

    async def get_unread_notifications(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[Notification]]:
        """
        Retrieve unread notifications for a user.
        """

        return await self.repository.get_unread_by_user(
            user_id=user_id,
            skip=skip,
            limit=limit,
        )

    # ==========================================================
    # Count Unread Notifications
    # ==========================================================

    async def count_unread(
        self,
        user_id: int,
    ) -> int:
        """
        Return the number of unread notifications
        belonging to a user.
        """

        return await self.repository.count_unread_by_user(
            user_id=user_id,
        )

    # ==========================================================
    # Get by Type
    # ==========================================================

    async def get_by_type(
        self,
        user_id: int,
        notification_type: NotificationType,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Notification]:
        """
        Retrieve notifications of a specific type
        for a user.
        """

        return await self.repository.get_by_type(
            user_id=user_id,
            notification_type=notification_type,
            skip=skip,
            limit=limit,
        )

    # ==========================================================
    # Get by Channel
    # ==========================================================

    async def get_by_channel(
        self,
        user_id: int,
        channel: NotificationChannel,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Notification]:
        """
        Retrieve notifications delivered through
        a specific channel for a user.
        """

        return await self.repository.get_by_channel(
            user_id=user_id,
            channel=channel,
            skip=skip,
            limit=limit,
        )

    # ==========================================================
    # Get by Status
    # ==========================================================

    async def get_by_status(
        self,
        status: NotificationStatus,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Notification]:
        """
        Retrieve notifications by delivery status.
        """

        return await self.repository.get_by_status(
            status=status,
            skip=skip,
            limit=limit,
        )

    # ==========================================================
    # Get by Related Entity
    # ==========================================================

    async def get_by_related_entity(
        self,
        entity_type: str,
        entity_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Notification]:
        """
        Retrieve notifications associated with a
        business entity.

        Example:

            entity_type = "PARKING_SESSION"
            entity_id = 33
        """

        return await self.repository.get_by_related_entity(
            entity_type=entity_type,
            entity_id=entity_id,
            skip=skip,
            limit=limit,
        )

    # ==========================================================
    # Mark Notification as Read
    # ==========================================================

    async def mark_as_read(
        self,
        notification_id: int,
        user_id: int,
    ) -> Notification:
        """
        Mark a notification as read.

        The notification must belong to the supplied user.

        If the notification is already read, the existing
        read timestamp is preserved.
        """

        notification = await self.get_by_id(
            notification_id,
        )

        # ------------------------------------------------------
        # Ownership
        # ------------------------------------------------------

        if notification.user_id != user_id:
            raise NotFoundException(
                "Notification not found."
            )

        # ------------------------------------------------------
        # Already read
        # ------------------------------------------------------

        if notification.is_read:
            return notification

        # ------------------------------------------------------
        # Mark as read
        # ------------------------------------------------------

        read_at = datetime.now(
            timezone.utc,
        )

        notification = await self.repository.mark_as_read(
            notification=notification,
            read_at=read_at,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            notification,
        )

        return notification

    # ==========================================================
    # Mark All Notifications as Read
    # ==========================================================

    async def mark_all_as_read(
        self,
        user_id: int,
    ) -> int:
        """
        Mark all unread notifications belonging to a user
        as read.

        Returns the number of notifications updated.
        """

        read_at = datetime.now(
            timezone.utc,
        )

        updated_count = (
            await self.repository.mark_all_as_read(
                user_id=user_id,
                read_at=read_at,
            )
        )

        await self.repository.db.commit()

        return updated_count

    # ==========================================================
    # Mark as Sent
    # ==========================================================

    async def mark_as_sent(
        self,
        notification_id: int,
        provider_message_id: str | None = None,
    ) -> Notification:
        """
        Mark a notification as successfully sent.

        This method is intended for use by notification
        delivery providers.

        Example:

            SMS provider
            EMAIL provider
            PUSH provider
        """

        notification = await self.get_by_id(
            notification_id,
        )

        notification.status = NotificationStatus.SENT

        if provider_message_id:
            notification.provider_message_id = (
                provider_message_id
            )

        notification.failure_reason = None

        notification = await self.repository.save(
            notification,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            notification,
        )

        return notification

    # ==========================================================
    # Mark as Delivered
    # ==========================================================

    async def mark_as_delivered(
        self,
        notification_id: int,
    ) -> Notification:
        """
        Mark a notification as successfully delivered.
        """

        notification = await self.get_by_id(
            notification_id,
        )

        notification.status = (
            NotificationStatus.DELIVERED
        )

        notification.failure_reason = None

        notification = await self.repository.save(
            notification,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            notification,
        )

        return notification

    # ==========================================================
    # Mark as Failed
    # ==========================================================

    async def mark_as_failed(
        self,
        notification_id: int,
        failure_reason: str,
    ) -> Notification:
        """
        Mark a notification delivery as failed.
        """

        notification = await self.get_by_id(
            notification_id,
        )

        notification.status = (
            NotificationStatus.FAILED
        )

        notification.failure_reason = (
            failure_reason
        )

        notification = await self.repository.save(
            notification,
        )

        await self.repository.db.commit()

        await self.repository.db.refresh(
            notification,
        )

        return notification

    # ==========================================================
    # Delete Notification
    # ==========================================================

    async def delete_notification(
        self,
        notification_id: int,
        user_id: int,
    ) -> None:
        """
        Delete a notification belonging to a user.
        """

        notification = await self.get_by_id(
            notification_id,
        )

        if notification.user_id != user_id:
            raise NotFoundException(
                "Notification not found."
            )

        await self.repository.remove(
            notification,
        )

        await self.repository.db.commit()