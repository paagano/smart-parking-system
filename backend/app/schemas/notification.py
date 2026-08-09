"""
Notification Schemas

Pydantic schemas used by the Notification API.

These schemas define the contract between the API layer and clients.
Business logic belongs in the Notification Service.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    NotificationChannel,
    NotificationPriority,
    NotificationStatus,
    NotificationType,
)


# ==========================================================
# Base Notification Schema
# ==========================================================


class NotificationBase(BaseModel):
    """
    Common notification fields.
    """

    type: NotificationType = Field(
        ...,
        description="Business event that triggered the notification.",
    )

    channel: NotificationChannel = Field(
        default=NotificationChannel.IN_APP,
        description="Delivery channel for the notification.",
    )

    priority: NotificationPriority = Field(
        default=NotificationPriority.NORMAL,
        description="Notification priority.",
    )

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Notification title.",
    )

    message: str = Field(
        ...,
        min_length=1,
        description="Notification message.",
    )

    related_entity_type: str | None = Field(
        default=None,
        max_length=50,
        description=(
            "Type of business entity related to the notification."
        ),
    )

    related_entity_id: int | None = Field(
        default=None,
        description=(
            "ID of the business entity related to the notification."
        ),
    )


# ==========================================================
# Create Notification
# ==========================================================


class NotificationCreate(NotificationBase):
    """
    Request schema for creating a notification.

    user_id identifies the notification recipient.
    """

    user_id: int = Field(
        ...,
        gt=0,
        description="ID of the user receiving the notification.",
    )


# ==========================================================
# Internal Notification Creation
# ==========================================================


class NotificationCreateInternal(NotificationCreate):
    """
    Internal schema used by the service layer when creating
    notifications.

    This schema exists separately so the external API contract
    can evolve independently from internal notification creation.
    """

    status: NotificationStatus = Field(
        default=NotificationStatus.PENDING,
        description="Initial notification delivery status.",
    )


# ==========================================================
# Notification Response
# ==========================================================


class NotificationResponse(BaseModel):
    """
    API response representing a notification.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    id: int

    user_id: int

    type: NotificationType

    channel: NotificationChannel

    status: NotificationStatus

    priority: NotificationPriority

    title: str

    message: str

    is_read: bool

    read_at: datetime | None

    related_entity_type: str | None

    related_entity_id: int | None

    provider_message_id: str | None

    failure_reason: str | None

    created_at: datetime

    updated_at: datetime


# ==========================================================
# Notification List Response
# ==========================================================


class NotificationListResponse(BaseModel):
    """
    Paginated notification response.
    """

    total: int = Field(
        ...,
        ge=0,
        description="Total number of notifications.",
    )

    items: list[NotificationResponse] = Field(
        default_factory=list,
        description="Notifications returned for the current page.",
    )

    skip: int = Field(
        ...,
        ge=0,
    )

    limit: int = Field(
        ...,
        ge=1,
    )


# ==========================================================
# Unread Count Response
# ==========================================================


class NotificationUnreadCountResponse(BaseModel):
    """
    Response containing the number of unread notifications
    belonging to a user.
    """

    unread_count: int = Field(
        ...,
        ge=0,
    )


# ==========================================================
# Mark as Read
# ==========================================================


class NotificationReadResponse(BaseModel):
    """
    Response returned after marking a notification as read.
    """

    id: int

    is_read: bool

    read_at: datetime | None

    model_config = ConfigDict(
        from_attributes=True,
    )


# ==========================================================
# Mark All as Read
# ==========================================================


class NotificationMarkAllReadResponse(BaseModel):
    """
    Response returned after marking all unread notifications
    for a user as read.
    """

    updated_count: int = Field(
        ...,
        ge=0,
        description="Number of notifications marked as read.",
    )