"""
add notifications

Revision ID: c4550f3bed2a
Revises: e5b7fa55f150
Create Date: 2026-08-09 21:33:15.108748

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "c4550f3bed2a"
down_revision: Union[str, Sequence[str], None] = "e5b7fa55f150"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Create the notifications subsystem.
    """

    bind = op.get_bind()

    # ======================================================
    # Create PostgreSQL Enum Types
    # ======================================================

    notification_type = postgresql.ENUM(
        "RESERVATION_CREATED",
        "RESERVATION_CONFIRMED",
        "RESERVATION_CANCELLED",
        "RESERVATION_EXPIRED",
        "SESSION_CHECKED_IN",
        "SESSION_CHECKED_OUT",
        "PAYMENT_INITIATED",
        "PAYMENT_SUCCESSFUL",
        "PAYMENT_FAILED",
        "PAYMENT_REFUNDED",
        "RECEIPT_AVAILABLE",
        "LOYALTY_REWARD",
        "SYSTEM",
        name="notification_type",
    )

    notification_channel = postgresql.ENUM(
        "IN_APP",
        "SMS",
        "EMAIL",
        "PUSH",
        name="notification_channel",
    )

    notification_status = postgresql.ENUM(
        "PENDING",
        "SENT",
        "DELIVERED",
        "FAILED",
        name="notification_status",
    )

    notification_priority = postgresql.ENUM(
        "LOW",
        "NORMAL",
        "HIGH",
        "CRITICAL",
        name="notification_priority",
    )

    notification_type.create(
        bind,
        checkfirst=True,
    )

    notification_channel.create(
        bind,
        checkfirst=True,
    )

    notification_status.create(
        bind,
        checkfirst=True,
    )

    notification_priority.create(
        bind,
        checkfirst=True,
    )

    # ======================================================
    # Enum Types Used By Table
    #
    # create_type=False is CRITICAL here because the
    # PostgreSQL enum types have already been created above.
    # ======================================================

    notification_type_column = postgresql.ENUM(
        "RESERVATION_CREATED",
        "RESERVATION_CONFIRMED",
        "RESERVATION_CANCELLED",
        "RESERVATION_EXPIRED",
        "SESSION_CHECKED_IN",
        "SESSION_CHECKED_OUT",
        "PAYMENT_INITIATED",
        "PAYMENT_SUCCESSFUL",
        "PAYMENT_FAILED",
        "PAYMENT_REFUNDED",
        "RECEIPT_AVAILABLE",
        "LOYALTY_REWARD",
        "SYSTEM",
        name="notification_type",
        create_type=False,
    )

    notification_channel_column = postgresql.ENUM(
        "IN_APP",
        "SMS",
        "EMAIL",
        "PUSH",
        name="notification_channel",
        create_type=False,
    )

    notification_status_column = postgresql.ENUM(
        "PENDING",
        "SENT",
        "DELIVERED",
        "FAILED",
        name="notification_status",
        create_type=False,
    )

    notification_priority_column = postgresql.ENUM(
        "LOW",
        "NORMAL",
        "HIGH",
        "CRITICAL",
        name="notification_priority",
        create_type=False,
    )

    # ======================================================
    # Notifications Table
    # ======================================================

    op.create_table(
        "notifications",

        # --------------------------------------------------
        # Primary Key
        # --------------------------------------------------

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        # --------------------------------------------------
        # Recipient
        # --------------------------------------------------

        sa.Column(
            "user_id",
            sa.Integer(),
            nullable=False,
        ),

        # --------------------------------------------------
        # Classification
        # --------------------------------------------------

        sa.Column(
            "type",
            notification_type_column,
            nullable=False,
        ),

        sa.Column(
            "channel",
            notification_channel_column,
            nullable=False,
        ),

        sa.Column(
            "status",
            notification_status_column,
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),

        sa.Column(
            "priority",
            notification_priority_column,
            server_default=sa.text("'NORMAL'"),
            nullable=False,
        ),

        # --------------------------------------------------
        # Content
        # --------------------------------------------------

        sa.Column(
            "title",
            sa.String(length=200),
            nullable=False,
        ),

        sa.Column(
            "message",
            sa.Text(),
            nullable=False,
        ),

        # --------------------------------------------------
        # Read State
        # --------------------------------------------------

        sa.Column(
            "is_read",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),

        sa.Column(
            "read_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # --------------------------------------------------
        # Related Business Entity
        # --------------------------------------------------

        sa.Column(
            "related_entity_type",
            sa.String(length=50),
            nullable=True,
        ),

        sa.Column(
            "related_entity_id",
            sa.Integer(),
            nullable=True,
        ),

        # --------------------------------------------------
        # Delivery Provider Information
        # --------------------------------------------------

        sa.Column(
            "provider_message_id",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "failure_reason",
            sa.Text(),
            nullable=True,
        ),

        # --------------------------------------------------
        # TimestampMixin
        # --------------------------------------------------

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        # --------------------------------------------------
        # Constraints
        # --------------------------------------------------

        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint(
            "id",
        ),
    )

    # ======================================================
    # Indexes
    # ======================================================

    op.create_index(
        "ix_notifications_id",
        "notifications",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_user_id",
        "notifications",
        ["user_id"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_status",
        "notifications",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_type",
        "notifications",
        ["type"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_channel",
        "notifications",
        ["channel"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_priority",
        "notifications",
        ["priority"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_is_read",
        "notifications",
        ["is_read"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_created_at",
        "notifications",
        ["created_at"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_user_read",
        "notifications",
        ["user_id", "is_read"],
        unique=False,
    )

    op.create_index(
        "ix_notifications_related_entity",
        "notifications",
        [
            "related_entity_type",
            "related_entity_id",
        ],
        unique=False,
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Remove the notifications subsystem.
    """

    # ======================================================
    # Drop Indexes
    # ======================================================

    op.drop_index(
        "ix_notifications_related_entity",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_user_read",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_created_at",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_is_read",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_priority",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_channel",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_type",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_status",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_user_id",
        table_name="notifications",
    )

    op.drop_index(
        "ix_notifications_id",
        table_name="notifications",
    )

    # ======================================================
    # Drop Table
    # ======================================================

    op.drop_table(
        "notifications",
    )

    # ======================================================
    # Drop Enum Types
    # ======================================================

    bind = op.get_bind()

    notification_priority = postgresql.ENUM(
        "LOW",
        "NORMAL",
        "HIGH",
        "CRITICAL",
        name="notification_priority",
    )

    notification_status = postgresql.ENUM(
        "PENDING",
        "SENT",
        "DELIVERED",
        "FAILED",
        name="notification_status",
    )

    notification_channel = postgresql.ENUM(
        "IN_APP",
        "SMS",
        "EMAIL",
        "PUSH",
        name="notification_channel",
    )

    notification_type = postgresql.ENUM(
        "RESERVATION_CREATED",
        "RESERVATION_CONFIRMED",
        "RESERVATION_CANCELLED",
        "RESERVATION_EXPIRED",
        "SESSION_CHECKED_IN",
        "SESSION_CHECKED_OUT",
        "PAYMENT_INITIATED",
        "PAYMENT_SUCCESSFUL",
        "PAYMENT_FAILED",
        "PAYMENT_REFUNDED",
        "RECEIPT_AVAILABLE",
        "LOYALTY_REWARD",
        "SYSTEM",
        name="notification_type",
    )

    notification_priority.drop(
        bind,
        checkfirst=True,
    )

    notification_status.drop(
        bind,
        checkfirst=True,
    )

    notification_channel.drop(
        bind,
        checkfirst=True,
    )

    notification_type.drop(
        bind,
        checkfirst=True,
    )