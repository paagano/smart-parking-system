"""
add billing type to parking sessions

Revision ID: e5b7fa55f150
Revises: ef455a73edee
Create Date: 2026-08-09 18:09:01.861130

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "e5b7fa55f150"
down_revision: Union[str, Sequence[str], None] = "ef455a73edee"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Add billing_type to parking_sessions.

    Existing parking sessions are backfilled as HOURLY so the
    new non-nullable column can be introduced safely.

    New sessions must explicitly provide their billing type
    through the application/service layer.
    """

    # ------------------------------------------------------
    # 1. Add billing_type temporarily as nullable
    # ------------------------------------------------------

    op.add_column(
        "parking_sessions",
        sa.Column(
            "billing_type",
            sa.Enum(
                "HOURLY",
                "DAILY",
                "FLAT",
                name="billing_type",
                create_type=False,
            ),
            nullable=True,
        ),
    )

    # ------------------------------------------------------
    # 2. Backfill existing sessions
    # ------------------------------------------------------

    op.execute(
        """
        UPDATE parking_sessions
        SET billing_type = 'HOURLY'
        WHERE billing_type IS NULL
        """
    )

    # ------------------------------------------------------
    # 3. Make billing_type mandatory
    # ------------------------------------------------------

    op.alter_column(
        "parking_sessions",
        "billing_type",
        existing_type=sa.Enum(
            "HOURLY",
            "DAILY",
            "FLAT",
            name="billing_type",
            create_type=False,
        ),
        nullable=False,
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Remove billing_type from parking_sessions.
    """

    op.drop_column(
        "parking_sessions",
        "billing_type",
    )