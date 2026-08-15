"""
Add server defaults to loyalty reward timestamps.

Revision ID: 8f2a6c9d4b17
Revises: 7c4e91b6a2d8
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "8f2a6c9d4b17"
down_revision: Union[str, Sequence[str], None] = "7c4e91b6a2d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================


def upgrade() -> None:
    """
    Add PostgreSQL server defaults for created_at and
    updated_at on loyalty reward tables.

    The application TimestampMixin expects PostgreSQL to
    generate these timestamps automatically.
    """

    # ======================================================
    # Loyalty Rewards
    # ======================================================

    op.alter_column(
        "loyalty_rewards",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_nullable=False,
    )

    op.alter_column(
        "loyalty_rewards",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_nullable=False,
    )

    # ======================================================
    # Loyalty Reward Redemptions
    # ======================================================

    op.alter_column(
        "loyalty_reward_redemptions",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_nullable=False,
    )

    op.alter_column(
        "loyalty_reward_redemptions",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=sa.text("CURRENT_TIMESTAMP"),
        existing_nullable=False,
    )


# ==========================================================
# Downgrade
# ==========================================================


def downgrade() -> None:
    """
    Remove the server defaults from loyalty reward timestamps.
    """

    # ======================================================
    # Loyalty Reward Redemptions
    # ======================================================

    op.alter_column(
        "loyalty_reward_redemptions",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )

    op.alter_column(
        "loyalty_reward_redemptions",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )

    # ======================================================
    # Loyalty Rewards
    # ======================================================

    op.alter_column(
        "loyalty_rewards",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )

    op.alter_column(
        "loyalty_rewards",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        server_default=None,
        existing_nullable=False,
    )