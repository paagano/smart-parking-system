"""
Notification Endpoints

REST API endpoints for Notification management.

Responsibilities
----------------
- Retrieve user notifications
- Retrieve unread notifications
- Count unread notifications
- Filter notifications
- Mark notifications as read
- Mark all notifications as read
- Delete notifications

Business logic belongs in NotificationService.
Persistence belongs in NotificationRepository.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Query,
    status,
)

from app.api.dependencies.auth import (
    get_current_active_user,
)

from app.api.dependencies.notifications import (
    NotificationServiceDep,
)

from app.models.enums import (
    NotificationChannel,
    NotificationType,
)

from app.models.user import User

from app.schemas.notification import (
    NotificationListResponse,
    NotificationReadResponse,
    NotificationResponse,
    NotificationUnreadCountResponse,
    NotificationMarkAllReadResponse,
)


# ==========================================================
# Router
# ==========================================================

router = APIRouter(
    prefix="/notifications",
    tags=["Notifications"],
)


# ==========================================================
# Get My Notifications
# ==========================================================

@router.get(
    "",
    response_model=NotificationListResponse,
    summary="Get My Notifications",
)
async def get_my_notifications(
    service: NotificationServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    skip: int = Query(
        default=0,
        ge=0,
        description="Number of notifications to skip.",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=100,
        description="Maximum number of notifications to return.",
    ),
) -> NotificationListResponse:
    """
    Retrieve notifications belonging to the authenticated user.

    Notifications are returned newest first.
    """

    total, notifications = await service.get_user_notifications(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )

    return NotificationListResponse(
        total=total,
        items=notifications,
        skip=skip,
        limit=limit,
    )


# ==========================================================
# Get My Unread Notifications
# ==========================================================

@router.get(
    "/unread",
    response_model=NotificationListResponse,
    summary="Get My Unread Notifications",
)
async def get_my_unread_notifications(
    service: NotificationServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    skip: int = Query(
        default=0,
        ge=0,
        description="Number of notifications to skip.",
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=100,
        description="Maximum number of notifications to return.",
    ),
) -> NotificationListResponse:
    """
    Retrieve unread notifications belonging to
    the authenticated user.
    """

    total, notifications = await service.get_unread_notifications(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )

    return NotificationListResponse(
        total=total,
        items=notifications,
        skip=skip,
        limit=limit,
    )


# ==========================================================
# Get Unread Count
# ==========================================================

@router.get(
    "/unread/count",
    response_model=NotificationUnreadCountResponse,
    summary="Get Unread Notification Count",
)
async def get_unread_notification_count(
    service: NotificationServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> NotificationUnreadCountResponse:
    """
    Return the number of unread notifications
    belonging to the authenticated user.
    """

    unread_count = await service.count_unread(
        user_id=current_user.id,
    )

    return NotificationUnreadCountResponse(
        unread_count=unread_count,
    )


# ==========================================================
# Get Notifications by Type
# ==========================================================

@router.get(
    "/type/{notification_type}",
    response_model=list[NotificationResponse],
    summary="Get My Notifications by Type",
)
async def get_notifications_by_type(
    notification_type: NotificationType,
    service: NotificationServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=100,
    ),
) -> list[NotificationResponse]:
    """
    Retrieve notifications of a specific type
    belonging to the authenticated user.
    """

    return await service.get_by_type(
        user_id=current_user.id,
        notification_type=notification_type,
        skip=skip,
        limit=limit,
    )


# ==========================================================
# Get Notifications by Channel
# ==========================================================

@router.get(
    "/channel/{channel}",
    response_model=list[NotificationResponse],
    summary="Get My Notifications by Channel",
)
async def get_notifications_by_channel(
    channel: NotificationChannel,
    service: NotificationServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
    skip: int = Query(
        default=0,
        ge=0,
    ),
    limit: int = Query(
        default=100,
        ge=1,
        le=100,
    ),
) -> list[NotificationResponse]:
    """
    Retrieve notifications delivered through
    a specific channel for the authenticated user.
    """

    return await service.get_by_channel(
        user_id=current_user.id,
        channel=channel,
        skip=skip,
        limit=limit,
    )


# ==========================================================
# Get Notification by ID
# ==========================================================

@router.get(
    "/{notification_id}",
    response_model=NotificationResponse,
    summary="Get Notification",
)
async def get_notification(
    notification_id: int,
    service: NotificationServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> NotificationResponse:
    """
    Retrieve a notification by ID.

    The notification must belong to the authenticated user.
    """

    notification = await service.get_by_id(
        notification_id,
    )

    # Do not expose another user's notification.
    if notification.user_id != current_user.id:
        from app.exceptions.handlers import NotFoundException

        raise NotFoundException(
            "Notification not found."
        )

    return notification


# ==========================================================
# Mark Notification as Read
# ==========================================================

@router.patch(
    "/{notification_id}/read",
    response_model=NotificationReadResponse,
    summary="Mark Notification as Read",
)
async def mark_notification_as_read(
    notification_id: int,
    service: NotificationServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> NotificationResponse:
    """
    Mark a notification belonging to the authenticated
    user as read.
    """

    return await service.mark_as_read(
        notification_id=notification_id,
        user_id=current_user.id,
    )


# ==========================================================
# Mark All Notifications as Read
# ==========================================================

@router.patch(
    "/read-all",
    response_model=NotificationMarkAllReadResponse,
    summary="Mark All Notifications as Read",
)
async def mark_all_notifications_as_read(
    service: NotificationServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> NotificationMarkAllReadResponse:
    """
    Mark all unread notifications belonging to the
    authenticated user as read.
    """

    updated_count = await service.mark_all_as_read(
        user_id=current_user.id,
    )

    return NotificationMarkAllReadResponse(
        updated_count=updated_count,
    )


# ==========================================================
# Delete Notification
# ==========================================================

@router.delete(
    "/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Notification",
)
async def delete_notification(
    notification_id: int,
    service: NotificationServiceDep,
    current_user: Annotated[
        User,
        Depends(get_current_active_user),
    ],
) -> None:
    """
    Delete a notification belonging to the authenticated
    user.
    """

    await service.delete_notification(
        notification_id=notification_id,
        user_id=current_user.id,
    )