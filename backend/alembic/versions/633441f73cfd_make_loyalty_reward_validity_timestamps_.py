"""
Make loyalty reward validity timestamps timezone aware.

Revision ID: 633441f73cfd
Revises: 8f2a6c9d4b17
Create Date: 2026-08-15 03:15:18.514333
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy.dialects import postgresql


# ==========================================================
# Revision identifiers, used by Alembic.
# ==========================================================

revision: str = "633441f73cfd"

down_revision: Union[str, Sequence[str], None] = "8f2a6c9d4b17"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Convert loyalty reward validity timestamps from
    timezone-naive timestamps to timezone-aware timestamps.

    Existing values are interpreted as UTC when converted
    to TIMESTAMP WITH TIME ZONE.

    This migration intentionally changes ONLY:

        loyalty_rewards.valid_from
        loyalty_rewards.valid_until
    """

    op.alter_column(
        "loyalty_rewards",
        "valid_from",
        existing_type=postgresql.TIMESTAMP(timezone=False),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=True,
        postgresql_using=(
            "valid_from AT TIME ZONE 'UTC'"
        ),
    )

    op.alter_column(
        "loyalty_rewards",
        "valid_until",
        existing_type=postgresql.TIMESTAMP(timezone=False),
        type_=postgresql.TIMESTAMP(timezone=True),
        existing_nullable=True,
        postgresql_using=(
            "valid_until AT TIME ZONE 'UTC'"
        ),
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Revert loyalty reward validity timestamps back to
    timezone-naive timestamps.

    Existing timezone-aware values are converted to UTC
    before the timezone information is removed.
    """

    op.alter_column(
        "loyalty_rewards",
        "valid_until",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=postgresql.TIMESTAMP(timezone=False),
        existing_nullable=True,
        postgresql_using=(
            "valid_until AT TIME ZONE 'UTC'"
        ),
    )

    op.alter_column(
        "loyalty_rewards",
        "valid_from",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=postgresql.TIMESTAMP(timezone=False),
        existing_nullable=True,
        postgresql_using=(
            "valid_from AT TIME ZONE 'UTC'"
        ),
    )