"""payment provider async support

Revision ID: 1053b272df4a
Revises: 4580eb9e21eb
Create Date: 2026-08-07 21:03:22.797363

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1053b272df4a"
down_revision: Union[str, Sequence[str], None] = "4580eb9e21eb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema.
    """

    op.add_column(
        "payment_transactions",
        sa.Column(
            "provider_message",
            sa.Text(),
            nullable=True,
            comment="Message returned by the payment provider.",
        ),
    )


def downgrade() -> None:
    """
    Downgrade schema.
    """

    op.drop_column(
        "payment_transactions",
        "provider_message",
    )