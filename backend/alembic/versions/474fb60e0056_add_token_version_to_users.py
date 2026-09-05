"""add token version to users

Revision ID: 474fb60e0056
Revises: 7fe881625b2b
Create Date: 2026-09-05 04:12:11.957445

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "474fb60e0056"
down_revision: Union[str, Sequence[str], None] = "7fe881625b2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_column(
        "users",
        "token_version",
    )