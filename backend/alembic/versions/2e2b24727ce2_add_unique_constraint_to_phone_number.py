"""add_unique_constraint_to_phone_number

Revision ID: 2e2b24727ce2
Revises: c84a7f0c2ce7
Create Date: 2026-07-22 05:12:07.010753
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2e2b24727ce2"
down_revision: Union[str, Sequence[str], None] = "c84a7f0c2ce7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_unique_constraint(
        "uq_users_phone_number",
        "users",
        ["phone_number"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_constraint(
        "uq_users_phone_number",
        "users",
        type_="unique",
    )