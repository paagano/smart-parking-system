"""add RFID timestamp defaults

Revision ID: a9b2086b1a4c
Revises: 37873e0cb1d7
Create Date: 2026-10-03 01:19:54.346437

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================================
# Revision identifiers, used by Alembic.
# ==========================================================

revision: str = "a9b2086b1a4c"

down_revision: Union[
    str,
    Sequence[str],
    None,
] = "37873e0cb1d7"

branch_labels: Union[
    str,
    Sequence[str],
    None,
] = None

depends_on: Union[
    str,
    Sequence[str],
    None,
] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """Upgrade schema."""

    op.alter_column(
        "rfid_tags",
        "created_at",
        server_default=sa.text("now()"),
    )

    op.alter_column(
        "rfid_tags",
        "updated_at",
        server_default=sa.text("now()"),
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """Downgrade schema."""

    op.alter_column(
        "rfid_tags",
        "updated_at",
        server_default=None,
    )

    op.alter_column(
        "rfid_tags",
        "created_at",
        server_default=None,
    )