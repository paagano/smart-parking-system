"""
Add session payment tracking.

Revision ID: b44221177066
Revises: bbdc0d029922
Create Date: 2026-08-04 20:11:33.780861
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "b44221177066"
down_revision: Union[str, Sequence[str], None] = "bbdc0d029922"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Add payment tracking fields to parking sessions.
    """

    # ------------------------------------------------------
    # Last successful payment transaction
    # ------------------------------------------------------

    op.add_column(
        "parking_sessions",
        sa.Column(
            "last_payment_transaction_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # ------------------------------------------------------
    # Timestamp payment completed
    # ------------------------------------------------------

    op.add_column(
        "parking_sessions",
        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # ------------------------------------------------------
    # Index
    # ------------------------------------------------------

    op.create_index(
        "ix_session_last_payment_transaction",
        "parking_sessions",
        ["last_payment_transaction_id"],
        unique=False,
    )

    # ------------------------------------------------------
    # Foreign Key
    # ------------------------------------------------------

    op.create_foreign_key(
        "fk_parking_session_last_payment_transaction",
        "parking_sessions",
        "payment_transactions",
        ["last_payment_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Remove payment tracking fields from parking sessions.
    """

    # ------------------------------------------------------
    # Foreign Key
    # ------------------------------------------------------

    op.drop_constraint(
        "fk_parking_session_last_payment_transaction",
        "parking_sessions",
        type_="foreignkey",
    )

    # ------------------------------------------------------
    # Index
    # ------------------------------------------------------

    op.drop_index(
        "ix_session_last_payment_transaction",
        table_name="parking_sessions",
    )

    # ------------------------------------------------------
    # Columns
    # ------------------------------------------------------

    op.drop_column(
        "parking_sessions",
        "paid_at",
    )

    op.drop_column(
        "parking_sessions",
        "last_payment_transaction_id",
    )