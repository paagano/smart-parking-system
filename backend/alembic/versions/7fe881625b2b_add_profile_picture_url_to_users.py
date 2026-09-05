"""add profile picture url to users

Revision ID: 7fe881625b2b
Revises: 3a68c5076f45
Create Date: 2026-09-04 23:42:51.625523

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ============================================================
# Revision identifiers
# ============================================================

revision: str = "7fe881625b2b"
down_revision: Union[str, Sequence[str], None] = "3a68c5076f45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ============================================================
# Upgrade
# ============================================================

def upgrade() -> None:
    """
    Add profile_picture_url to the users table.
    """

    op.add_column(
        "users",
        sa.Column(
            "profile_picture_url",
            sa.String(length=500),
            nullable=True,
        ),
    )


# ============================================================
# Downgrade
# ============================================================

def downgrade() -> None:
    """
    Remove profile_picture_url from the users table.
    """

    op.drop_column(
        "users",
        "profile_picture_url",
    )