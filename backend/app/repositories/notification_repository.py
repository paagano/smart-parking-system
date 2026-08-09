"""
Notification Repository

Handles database persistence and retrieval for Notifications.

Business rules belong in the Notification Service layer.
This repository is responsible only for database access.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import (
    NotificationChannel,
    NotificationStatus,
    NotificationType,
)
from app.models.notification import Notification
from app.repositories.base_repository import BaseRepository


class NotificationRepository(
    BaseRepository[Notification]
):
    """
    Repository responsible for Notification persistence.
    """

    def __init__(
        self,
        db: AsyncSession,
    ):
        super().__init__(
            db=db,
            model=Notification,
        )

    # ==========================================================
    # Get by Primary Key
    # ==========================================================

    async def get_by_id(
        self,
        notification_id: int,
    ) -> Notification | None:
        """
        Retrieve a notification by ID.
        """

        return await super().get_by_id(
            notification_id
        )

    # ==========================================================
    # Create
    # ==========================================================

    async def create(
        self,
        notification: Notification,
    ) -> Notification:
        """
        Persist a new notification.

        Commit is intentionally handled by the Service layer.
        """

        self.db.add(notification)

        await self.db.flush()
        await self.db.refresh(notification)

        return notification

    # ==========================================================
    # User Notifications
    # ==========================================================

    async def get_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[Notification]]:
        """
        Retrieve notifications belonging to a user.

        Results are returned newest first.
        """

        total = await self.db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id
            )
        )

        result = await self.db.execute(
            select(Notification)
            .where(
                Notification.user_id == user_id
            )
            .order_by(
                Notification.created_at.desc()
            )
            .offset(skip)
            .limit(limit)
        )

        return (
            total or 0,
            list(result.scalars().all()),
        )

    # ==========================================================
    # Unread Notifications
    # ==========================================================

    async def get_unread_by_user(
        self,
        user_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[int, list[Notification]]:
        """
        Retrieve unread notifications for a user.

        Results are returned newest first.
        """

        total = await self.db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )

        result = await self.db.execute(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
            .order_by(
                Notification.created_at.desc()
            )
            .offset(skip)
            .limit(limit)
        )

        return (
            total or 0,
            list(result.scalars().all()),
        )

    # ==========================================================
    # Unread Count
    # ==========================================================

    async def count_unread_by_user(
        self,
        user_id: int,
    ) -> int:
        """
        Return the number of unread notifications
        belonging to a user.
        """

        total = await self.db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )

        return total or 0

    # ==========================================================
    # Notification Type
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

        result = await self.db.execute(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.type == notification_type,
            )
            .order_by(
                Notification.created_at.desc()
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Channel
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

        result = await self.db.execute(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.channel == channel,
            )
            .order_by(
                Notification.created_at.desc()
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Status
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

        result = await self.db.execute(
            select(Notification)
            .where(
                Notification.status == status,
            )
            .order_by(
                Notification.created_at.asc()
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Related Entity
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
        particular business entity.

        Example:

            entity_type = "PARKING_SESSION"
            entity_id   = 33
        """

        result = await self.db.execute(
            select(Notification)
            .where(
                Notification.related_entity_type
                == entity_type,
                Notification.related_entity_id
                == entity_id,
            )
            .order_by(
                Notification.created_at.desc()
            )
            .offset(skip)
            .limit(limit)
        )

        return list(
            result.scalars().all()
        )

    # ==========================================================
    # Mark as Read
    # ==========================================================

    async def mark_as_read(
        self,
        notification: Notification,
        read_at: datetime,
    ) -> Notification:
        """
        Mark a notification as read.

        The Service layer determines whether the operation
        is allowed; the repository only persists the change.
        """

        notification.is_read = True
        notification.read_at = read_at

        await self.db.flush()
        await self.db.refresh(notification)

        return notification

    # ==========================================================
    # Mark All as Read
    # ==========================================================

    async def mark_all_as_read(
        self,
        user_id: int,
        read_at: datetime,
    ) -> int:
        """
        Mark all unread notifications for a user as read.

        Returns the number of notifications updated.
        """

        result = await self.db.execute(
            select(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read.is_(False),
            )
        )

        notifications = list(
            result.scalars().all()
        )

        for notification in notifications:
            notification.is_read = True
            notification.read_at = read_at

        await self.db.flush()

        return len(notifications)

    # ==========================================================
    # Persistence
    # ==========================================================

    async def save(
        self,
        notification: Notification,
    ) -> Notification:
        """
        Persist changes to an existing notification.

        Commit is handled by the Service layer.
        """

        await self.db.flush()
        await self.db.refresh(notification)

        return notification

    # ==========================================================
    # Delete
    # ==========================================================

    async def remove(
        self,
        notification: Notification,
    ) -> None:
        """
        Delete a notification.
        """

        await self.db.delete(notification)
        await self.db.flush()