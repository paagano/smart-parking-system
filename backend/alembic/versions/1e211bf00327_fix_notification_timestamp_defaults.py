"""fix notification timestamp defaults

Revision ID: 1e211bf00327
Revises: c4550f3bed2a
Create Date: 2026-08-10 00:04:24.253329

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1e211bf00327"
down_revision: Union[str, Sequence[str], None] = "c4550f3bed2a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add database-side timestamp defaults to notifications.
    """

    # ----------------------------------------------------------
    # Backfill any existing NULL timestamps first.
    # ----------------------------------------------------------

    op.execute(
        """
        UPDATE notifications
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL
        """
    )

    op.execute(
        """
        UPDATE notifications
        SET updated_at = CURRENT_TIMESTAMP
        WHERE updated_at IS NULL
        """
    )

    # ----------------------------------------------------------
    # created_at
    # ----------------------------------------------------------

    op.alter_column(
        "notifications",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )

    # ----------------------------------------------------------
    # updated_at
    # ----------------------------------------------------------

    op.alter_column(
        "notifications",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    )


def downgrade() -> None:
    """
    Remove database-side timestamp defaults.
    """

    # ----------------------------------------------------------
    # updated_at
    # ----------------------------------------------------------

    op.alter_column(
        "notifications",
        "updated_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=None,
    )

    # ----------------------------------------------------------
    # created_at
    # ----------------------------------------------------------

    op.alter_column(
        "notifications",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=None,
    )