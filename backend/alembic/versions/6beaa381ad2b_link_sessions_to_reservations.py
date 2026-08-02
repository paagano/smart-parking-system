"""link sessions to reservations

Revision ID: 6beaa381ad2b
Revises: d2156addbe04
Create Date: 2026-08-01 21:14:22.811154

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6beaa381ad2b'
down_revision: Union[str, Sequence[str], None] = 'd2156addbe04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Link Parking Sessions to Reservations.
    """

    # ------------------------------------------------------
    # Add Customer
    # ------------------------------------------------------

    op.add_column(
        "parking_sessions",
        sa.Column(
            "customer_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # ------------------------------------------------------
    # Add Reservation
    # ------------------------------------------------------

    op.add_column(
        "parking_sessions",
        sa.Column(
            "reservation_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # ------------------------------------------------------
    # Foreign Keys
    # ------------------------------------------------------

    op.create_foreign_key(
        "fk_parking_session_customer",
        "parking_sessions",
        "users",
        ["customer_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_foreign_key(
        "fk_parking_session_reservation",
        "parking_sessions",
        "parking_reservations",
        ["reservation_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ------------------------------------------------------
    # Constraints
    # ------------------------------------------------------

    op.create_unique_constraint(
        "uq_parking_session_reservation",
        "parking_sessions",
        ["reservation_id"],
    )

    # ------------------------------------------------------
    # Indexes
    # ------------------------------------------------------

    op.create_index(
        "ix_parking_sessions_customer",
        "parking_sessions",
        ["customer_id"],
        unique=False,
    )

    op.create_index(
        "ix_parking_sessions_reservation",
        "parking_sessions",
        ["reservation_id"],
        unique=False,
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Remove Reservation relationships from Parking Sessions.
    """

    # ------------------------------------------------------
    # Drop Indexes
    # ------------------------------------------------------

    op.drop_index(
        "ix_parking_sessions_reservation",
        table_name="parking_sessions",
    )

    op.drop_index(
        "ix_parking_sessions_customer",
        table_name="parking_sessions",
    )

    # ------------------------------------------------------
    # Drop Constraints
    # ------------------------------------------------------

    op.drop_constraint(
        "uq_parking_session_reservation",
        "parking_sessions",
        type_="unique",
    )

    # ------------------------------------------------------
    # Drop Foreign Keys
    # ------------------------------------------------------

    op.drop_constraint(
        "fk_parking_session_reservation",
        "parking_sessions",
        type_="foreignkey",
    )

    op.drop_constraint(
        "fk_parking_session_customer",
        "parking_sessions",
        type_="foreignkey",
    )

    # ------------------------------------------------------
    # Drop Columns
    # ------------------------------------------------------

    op.drop_column(
        "parking_sessions",
        "reservation_id",
    )

    op.drop_column(
        "parking_sessions",
        "customer_id",
    )