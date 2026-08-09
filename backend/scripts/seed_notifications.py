"""
SmartPark AI - Notification Seed Script

Creates controlled development/test notifications for the
Notification module.

This script is intended for local development and API testing.

It:
    - Uses existing active users from the database.
    - Covers all supported notification types.
    - Covers all supported notification channels.
    - Covers all supported notification priorities.
    - Exercises notification delivery statuses.
    - Uses NotificationService for notification creation
      and lifecycle transitions.
    - Removes previously seeded notification records before
      inserting a fresh dataset.

Run from the backend directory:

    python scripts/seed_notifications.py
"""

from __future__ import annotations

import asyncio
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal

from app.models.enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)

from app.models.notification import Notification
from app.models.user import User

from app.repositories.notification_repository import (
    NotificationRepository,
)

from app.schemas.notification import NotificationCreate

from app.services.notification_service import (
    NotificationService,
)


# ==========================================================
# Configuration
# ==========================================================

SEED_TITLE_PREFIX = "[SEED] SmartPark Notification"


# ==========================================================
# Seed Definitions
# ==========================================================

NOTIFICATION_DEFINITIONS = [
    # ------------------------------------------------------
    # Reservations
    # ------------------------------------------------------

    {
        "type": NotificationType.RESERVATION_CREATED,
        "channel": NotificationChannel.IN_APP,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.DELIVERED,
        "title": "Reservation Created",
        "message": (
            "Your parking reservation has been created successfully."
        ),
    },
    {
        "type": NotificationType.RESERVATION_CREATED,
        "channel": NotificationChannel.EMAIL,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.SENT,
        "title": "Reservation Created",
        "message": (
            "Your SmartPark parking reservation has been created."
        ),
    },
    {
        "type": NotificationType.RESERVATION_CONFIRMED,
        "channel": NotificationChannel.IN_APP,
        "priority": NotificationPriority.HIGH,
        "status": NotificationStatus.DELIVERED,
        "title": "Reservation Confirmed",
        "message": (
            "Your parking reservation has been confirmed."
        ),
    },
    {
        "type": NotificationType.RESERVATION_CONFIRMED,
        "channel": NotificationChannel.SMS,
        "priority": NotificationPriority.HIGH,
        "status": NotificationStatus.SENT,
        "title": "Reservation Confirmed",
        "message": (
            "Your SmartPark parking reservation is confirmed."
        ),
    },
    {
        "type": NotificationType.RESERVATION_CANCELLED,
        "channel": NotificationChannel.IN_APP,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.DELIVERED,
        "title": "Reservation Cancelled",
        "message": (
            "Your parking reservation has been cancelled."
        ),
    },
    {
        "type": NotificationType.RESERVATION_EXPIRED,
        "channel": NotificationChannel.PUSH,
        "priority": NotificationPriority.HIGH,
        "status": NotificationStatus.PENDING,
        "title": "Reservation Expired",
        "message": (
            "Your parking reservation has expired."
        ),
    },

    # ------------------------------------------------------
    # Parking Sessions
    # ------------------------------------------------------

    {
        "type": NotificationType.SESSION_CHECKED_IN,
        "channel": NotificationChannel.IN_APP,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.DELIVERED,
        "title": "Vehicle Checked In",
        "message": (
            "Your vehicle has been checked into the parking facility."
        ),
    },
    {
        "type": NotificationType.SESSION_CHECKED_IN,
        "channel": NotificationChannel.PUSH,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.SENT,
        "title": "Vehicle Checked In",
        "message": (
            "SmartPark has recorded your vehicle check-in."
        ),
    },
    {
        "type": NotificationType.SESSION_CHECKED_OUT,
        "channel": NotificationChannel.IN_APP,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.DELIVERED,
        "title": "Vehicle Checked Out",
        "message": (
            "Your vehicle has been checked out successfully."
        ),
    },
    {
        "type": NotificationType.SESSION_CHECKED_OUT,
        "channel": NotificationChannel.EMAIL,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.PENDING,
        "title": "Vehicle Checked Out",
        "message": (
            "Your parking session has been completed."
        ),
    },

    # ------------------------------------------------------
    # Payments
    # ------------------------------------------------------

    {
        "type": NotificationType.PAYMENT_INITIATED,
        "channel": NotificationChannel.IN_APP,
        "priority": NotificationPriority.HIGH,
        "status": NotificationStatus.SENT,
        "title": "Payment Initiated",
        "message": (
            "Your parking payment has been initiated."
        ),
    },
    {
        "type": NotificationType.PAYMENT_INITIATED,
        "channel": NotificationChannel.SMS,
        "priority": NotificationPriority.HIGH,
        "status": NotificationStatus.DELIVERED,
        "title": "Payment Initiated",
        "message": (
            "A payment request has been initiated for your parking."
        ),
    },
    {
        "type": NotificationType.PAYMENT_SUCCESSFUL,
        "channel": NotificationChannel.IN_APP,
        "priority": NotificationPriority.HIGH,
        "status": NotificationStatus.DELIVERED,
        "title": "Payment Successful",
        "message": (
            "Your parking payment was completed successfully."
        ),
    },
    {
        "type": NotificationType.PAYMENT_SUCCESSFUL,
        "channel": NotificationChannel.SMS,
        "priority": NotificationPriority.HIGH,
        "status": NotificationStatus.DELIVERED,
        "title": "Payment Successful",
        "message": (
            "Your SmartPark parking payment was successful."
        ),
    },
    {
        "type": NotificationType.PAYMENT_FAILED,
        "channel": NotificationChannel.IN_APP,
        "priority": NotificationPriority.CRITICAL,
        "status": NotificationStatus.FAILED,
        "title": "Payment Failed",
        "message": (
            "Your parking payment could not be completed."
        ),
    },
    {
        "type": NotificationType.PAYMENT_FAILED,
        "channel": NotificationChannel.EMAIL,
        "priority": NotificationPriority.HIGH,
        "status": NotificationStatus.FAILED,
        "title": "Payment Failed",
        "message": (
            "Your SmartPark parking payment failed. "
            "Please try again."
        ),
    },
    {
        "type": NotificationType.PAYMENT_REFUNDED,
        "channel": NotificationChannel.EMAIL,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.SENT,
        "title": "Payment Refunded",
        "message": (
            "Your parking payment refund has been processed."
        ),
    },

    # ------------------------------------------------------
    # Receipt
    # ------------------------------------------------------

    {
        "type": NotificationType.RECEIPT_AVAILABLE,
        "channel": NotificationChannel.EMAIL,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.DELIVERED,
        "title": "Receipt Available",
        "message": (
            "Your SmartPark parking receipt is now available."
        ),
    },
    {
        "type": NotificationType.RECEIPT_AVAILABLE,
        "channel": NotificationChannel.IN_APP,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.PENDING,
        "title": "Receipt Available",
        "message": (
            "Your parking receipt is ready to view."
        ),
    },

    # ------------------------------------------------------
    # Loyalty
    # ------------------------------------------------------

    {
        "type": NotificationType.LOYALTY_REWARD,
        "channel": NotificationChannel.IN_APP,
        "priority": NotificationPriority.HIGH,
        "status": NotificationStatus.DELIVERED,
        "title": "Loyalty Reward",
        "message": (
            "Congratulations! You have earned a SmartPark loyalty reward."
        ),
    },
    {
        "type": NotificationType.LOYALTY_REWARD,
        "channel": NotificationChannel.PUSH,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.SENT,
        "title": "Loyalty Reward",
        "message": (
            "You have received a new SmartPark loyalty reward."
        ),
    },

    # ------------------------------------------------------
    # System
    # ------------------------------------------------------

    {
        "type": NotificationType.SYSTEM,
        "channel": NotificationChannel.IN_APP,
        "priority": NotificationPriority.NORMAL,
        "status": NotificationStatus.PENDING,
        "title": "System Notification",
        "message": (
            "This is a controlled SmartPark system notification."
        ),
    },
    {
        "type": NotificationType.SYSTEM,
        "channel": NotificationChannel.PUSH,
        "priority": NotificationPriority.CRITICAL,
        "status": NotificationStatus.DELIVERED,
        "title": "System Alert",
        "message": (
            "SmartPark has generated a system alert for your account."
        ),
    },
]


# ==========================================================
# Database Helpers
# ==========================================================

async def clear_existing_seed_notifications(
    db: AsyncSession,
) -> int:
    """
    Remove notifications previously created by this seed script.

    Only notifications whose title starts with
    SEED_TITLE_PREFIX are removed.

    Returns:
        Number of deleted notifications.
    """

    result = await db.execute(
        select(Notification).where(
            Notification.title.like(
                f"{SEED_TITLE_PREFIX}%"
            )
        )
    )

    notifications = list(
        result.scalars().all()
    )

    for notification in notifications:
        await db.delete(notification)

    if notifications:
        await db.flush()

    return len(notifications)


# ==========================================================
# Apply Notification Status
# ==========================================================

async def apply_status(
    service: NotificationService,
    notification: Notification,
    target_status: NotificationStatus,
) -> Notification:
    """
    Move a newly-created notification from PENDING to the
    requested test status using NotificationService lifecycle
    methods.

    New notifications are expected to start as PENDING.
    """

    if target_status == NotificationStatus.PENDING:
        return notification

    if target_status == NotificationStatus.SENT:
        return await service.mark_as_sent(
            notification_id=notification.id,
            provider_message_id=(
                f"SEED-PROVIDER-{notification.id}"
            ),
        )

    if target_status == NotificationStatus.DELIVERED:
        notification = await service.mark_as_sent(
            notification_id=notification.id,
            provider_message_id=(
                f"SEED-PROVIDER-{notification.id}"
            ),
        )

        return await service.mark_as_delivered(
            notification_id=notification.id,
        )

    if target_status == NotificationStatus.FAILED:
        return await service.mark_as_failed(
            notification_id=notification.id,
            failure_reason=(
                "Controlled seed notification failure."
            ),
        )

    raise ValueError(
        f"Unsupported notification status: {target_status}"
    )


# ==========================================================
# Seed Notifications
# ==========================================================

async def seed_notifications(
    db: AsyncSession,
) -> list[Notification]:
    """
    Create the controlled notification dataset.
    """

    # ------------------------------------------------------
    # Load existing active users
    # ------------------------------------------------------

    result = await db.execute(
        select(User.id)
        .where(
            User.is_active.is_(True)
        )
        .order_by(
            User.id.asc()
        )
    )

    user_ids = list(
        result.scalars().all()
    )

    if not user_ids:
        raise RuntimeError(
            "No active users were found. "
            "Create at least one active user before "
            "running this seed script."
        )

    print(
        f"Active users found: {len(user_ids)}"
    )

    # ------------------------------------------------------
    # Create repository and service
    # ------------------------------------------------------

    repository = NotificationRepository(
        db=db,
    )

    service = NotificationService(
        repository=repository,
    )

    created_notifications: list[Notification] = []

    # ------------------------------------------------------
    # Create notifications
    # ------------------------------------------------------

    total = len(NOTIFICATION_DEFINITIONS)

    for index, definition in enumerate(
        NOTIFICATION_DEFINITIONS,
        start=1,
    ):
        user_id = user_ids[
            (index - 1) % len(user_ids)
        ]

        notification_data = NotificationCreate(
            user_id=user_id,
            type=definition["type"],
            channel=definition["channel"],
            priority=definition["priority"],
            title=(
                f"{SEED_TITLE_PREFIX} - "
                f"{definition['title']}"
            ),
            message=definition["message"],
            related_entity_type=None,
            related_entity_id=None,
        )

        notification = await service.create_notification(
            notification_data
        )

        notification = await apply_status(
            service=service,
            notification=notification,
            target_status=definition["status"],
        )

        created_notifications.append(
            notification
        )

        print(
            f"[{index:02d}/{total:02d}] "
            f"ID={notification.id:<4} "
            f"user={user_id:<3} "
            f"type={notification.type.value:<24} "
            f"channel={notification.channel.value:<7} "
            f"status={notification.status.value:<9}"
        )

    return created_notifications


# ==========================================================
# Summary
# ==========================================================

def print_summary(
    notifications: list[Notification],
) -> None:
    """
    Print a summary of the generated dataset.
    """

    type_counts = Counter(
        notification.type.value
        for notification in notifications
    )

    channel_counts = Counter(
        notification.channel.value
        for notification in notifications
    )

    priority_counts = Counter(
        notification.priority.value
        for notification in notifications
    )

    status_counts = Counter(
        notification.status.value
        for notification in notifications
    )

    print()
    print("=" * 60)
    print("SMARTPARK AI - NOTIFICATION SEED COMPLETE")
    print("=" * 60)

    print()
    print(
        f"Total notifications created: "
        f"{len(notifications)}"
    )

    print()
    print("BY TYPE")
    print("-" * 40)

    for notification_type in NotificationType:
        count = type_counts.get(
            notification_type.value,
            0,
        )

        print(
            f"{notification_type.value:<28} {count}"
        )

    print()
    print("BY CHANNEL")
    print("-" * 40)

    for channel in NotificationChannel:
        count = channel_counts.get(
            channel.value,
            0,
        )

        print(
            f"{channel.value:<28} {count}"
        )

    print()
    print("BY PRIORITY")
    print("-" * 40)

    for priority in NotificationPriority:
        count = priority_counts.get(
            priority.value,
            0,
        )

        print(
            f"{priority.value:<28} {count}"
        )

    print()
    print("BY STATUS")
    print("-" * 40)

    for status in NotificationStatus:
        count = status_counts.get(
            status.value,
            0,
        )

        print(
            f"{status.value:<28} {count}"
        )

    print()
    print("=" * 60)
    print("SEEDING FINISHED SUCCESSFULLY")
    print("=" * 60)
    print()


# ==========================================================
# Main
# ==========================================================

async def main() -> None:
    """
    Main entry point.
    """

    print()
    print("=" * 60)
    print("SMARTPARK AI - NOTIFICATION SEED")
    print("=" * 60)
    print()

    async with AsyncSessionLocal() as db:

        try:
            # --------------------------------------------------
            # Remove previous seed data
            # --------------------------------------------------

            deleted_count = (
                await clear_existing_seed_notifications(
                    db
                )
            )

            print(
                f"Previous seed notifications removed: "
                f"{deleted_count}"
            )

            # --------------------------------------------------
            # Create fresh seed data
            # --------------------------------------------------

            notifications = await seed_notifications(
                db
            )

            # --------------------------------------------------
            # Final transaction
            # --------------------------------------------------

            await db.commit()

            print_summary(
                notifications
            )

        except Exception:
            await db.rollback()

            print()
            print("=" * 60)
            print("NOTIFICATION SEED FAILED")
            print("=" * 60)
            print()

            raise


# ==========================================================
# Script Entry Point
# ==========================================================

if __name__ == "__main__":
    asyncio.run(main())