"""
Add Loyalty Programme notification types.

This migration extends the existing PostgreSQL
notification_type enum with Loyalty Programme events.

Existing notification types and notification records
are preserved.

Revision ID: b6c4d8e2f701
Revises: 9a7b3c2d1e5f
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "b6c4d8e2f701"

down_revision: Union[str, Sequence[str], None] = "9a7b3c2d1e5f"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Loyalty Notification Types
# ==========================================================

LOYALTY_NOTIFICATION_TYPES = (
    "LOYALTY_POINTS_EARNED",
    "LOYALTY_TIER_UPGRADED",
    "LOYALTY_REWARD_REDEEMED",
    "LOYALTY_REFERRAL_QUALIFIED",
    "LOYALTY_REFERRAL_REWARDED",
    "LOYALTY_COUPON_ISSUED",
    "LOYALTY_COUPON_USED",
)


# ==========================================================
# Upgrade
# ==========================================================


def upgrade() -> None:
    """
    Add Loyalty Programme notification types to the existing
    PostgreSQL notification_type enum.

    The migration is deliberately defensive:

    - Existing enum values are preserved.
    - Existing notification records are preserved.
    - Existing notification table structure is untouched.
    - Already-existing enum values are not added again.
    """

    bind = op.get_bind()

    # ------------------------------------------------------
    # Verify that the notification_type enum exists.
    # ------------------------------------------------------

    enum_exists = bind.execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_type
                WHERE typname = 'notification_type'
            )
            """
        )
    ).scalar()

    if not enum_exists:
        raise RuntimeError(
            "PostgreSQL enum 'notification_type' does not exist. "
            "The existing notifications migration must be applied "
            "before this migration."
        )

    # ------------------------------------------------------
    # Read the current enum values.
    #
    # This is important because LOYALTY_REWARD already exists
    # in the current project and must NOT be added again.
    # ------------------------------------------------------

    existing_values = {
        row[0]
        for row in bind.execute(
            sa.text(
                """
                SELECT e.enumlabel
                FROM pg_enum AS e
                JOIN pg_type AS t
                    ON e.enumtypid = t.oid
                WHERE t.typname = 'notification_type'
                """
            )
        ).fetchall()
    }

    # ------------------------------------------------------
    # Add only missing Loyalty notification types.
    # ------------------------------------------------------

    for notification_type in LOYALTY_NOTIFICATION_TYPES:

        if notification_type in existing_values:
            continue

        bind.execute(
            sa.text(
                f"""
                ALTER TYPE notification_type
                ADD VALUE '{notification_type}'
                """
            )
        )


# ==========================================================
# Downgrade
# ==========================================================


def downgrade() -> None:
    """
    Downgrade is intentionally blocked.

    PostgreSQL does not support safely removing individual
    ENUM values.

    Recreating the notification_type ENUM during downgrade
    could require rewriting the notifications table and may
    compromise existing notification records.

    Therefore this migration is forward-only.
    """

    raise RuntimeError(
        "Downgrade of Loyalty notification types is intentionally "
        "blocked. PostgreSQL ENUM values cannot be safely removed "
        "without recreating the enum and potentially rewriting "
        "existing notification data."
    )