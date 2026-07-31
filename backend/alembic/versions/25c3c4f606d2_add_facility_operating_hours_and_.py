"""add facility operating hours and location fields

Revision ID: 25c3c4f606d2
Revises: 8a0776922237
Create Date: 2026-07-31 02:41:39.566050

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "25c3c4f606d2"
down_revision: Union[str, Sequence[str], None] = "8a0776922237"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema.
    """

    op.add_column(
        "parking_facilities",
        sa.Column(
            "postal_code",
            sa.String(length=20),
            nullable=True,
        ),
    )

    op.add_column(
        "parking_facilities",
        sa.Column(
            "timezone",
            sa.String(length=50),
            nullable=False,
            server_default="Africa/Nairobi",
        ),
    )

    op.add_column(
        "parking_facilities",
        sa.Column(
            "opening_time",
            sa.Time(),
            nullable=False,
            server_default=sa.text("'06:00:00'"),
        ),
    )

    op.add_column(
        "parking_facilities",
        sa.Column(
            "closing_time",
            sa.Time(),
            nullable=False,
            server_default=sa.text("'22:00:00'"),
        ),
    )

    # Remove temporary defaults after existing rows have been populated.
    op.alter_column(
        "parking_facilities",
        "timezone",
        server_default=None,
    )

    op.alter_column(
        "parking_facilities",
        "opening_time",
        server_default=None,
    )

    op.alter_column(
        "parking_facilities",
        "closing_time",
        server_default=None,
    )


def downgrade() -> None:
    """
    Downgrade schema.
    """

    op.drop_column(
        "parking_facilities",
        "closing_time",
    )

    op.drop_column(
        "parking_facilities",
        "opening_time",
    )

    op.drop_column(
        "parking_facilities",
        "timezone",
    )

    op.drop_column(
        "parking_facilities",
        "postal_code",
    )