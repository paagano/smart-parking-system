"""
make reservation paid_at timezone aware

Revision ID: bbdc0d029922
Revises: f7ba9eaa7cbf
Create Date: 2026-08-04 00:46:17.004766
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "bbdc0d029922"
down_revision: Union[str, Sequence[str], None] = "f7ba9eaa7cbf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Make parking_reservations.paid_at timezone aware.
    """

    op.alter_column(
        "parking_reservations",
        "paid_at",
        existing_type=postgresql.TIMESTAMP(timezone=False),
        type_=sa.DateTime(timezone=True),
        existing_nullable=True,
    )


def downgrade() -> None:
    """
    Revert parking_reservations.paid_at back to
    TIMESTAMP WITHOUT TIME ZONE.
    """

    op.alter_column(
        "parking_reservations",
        "paid_at",
        existing_type=postgresql.TIMESTAMP(timezone=True),
        type_=sa.DateTime(timezone=False),
        existing_nullable=True,
    )