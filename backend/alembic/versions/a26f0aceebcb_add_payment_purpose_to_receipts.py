"""
add payment purpose to receipts

Revision ID: a26f0aceebcb
Revises: b6c4d8e2f701
Create Date: 2026-08-16 14:06:37.028606
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================================
# Revision identifiers, used by Alembic.
# ==========================================================

revision: str = "a26f0aceebcb"

down_revision: Union[str, Sequence[str], None] = "b6c4d8e2f701"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================


def upgrade() -> None:
    """
    Add payment purpose to the receipts table.

    This is intentionally a surgical migration.

    Existing receipts remain valid because the new column is
    nullable. Existing payment and receipt data is not modified.
    """

    op.add_column(
        "receipts",
        sa.Column(
            "payment_purpose",
            sa.String(length=50),
            nullable=True,
        ),
    )


# ==========================================================
# Downgrade
# ==========================================================


def downgrade() -> None:
    """
    Remove payment purpose from the receipts table.
    """

    op.drop_column(
        "receipts",
        "payment_purpose",
    )