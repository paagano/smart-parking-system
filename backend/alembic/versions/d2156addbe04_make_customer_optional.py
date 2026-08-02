"""
make customer optional

Revision ID: d2156addbe04
Revises: 9e3f895c3ceb
Create Date: 2026-08-01 21:07:24.311088
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision: str = "d2156addbe04"
down_revision: Union[str, Sequence[str], None] = "9e3f895c3ceb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Make Reservation customer optional.
    """

    # ------------------------------------------------------
    # Drop existing foreign key
    # ------------------------------------------------------

    op.drop_constraint(
        "fk_parking_reservation_customer",
        "parking_reservations",
        type_="foreignkey",
    )

    # ------------------------------------------------------
    # Allow NULL customer
    # ------------------------------------------------------

    op.alter_column(
        "parking_reservations",
        "customer_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    # ------------------------------------------------------
    # Recreate FK
    # ------------------------------------------------------

    op.create_foreign_key(
        "fk_parking_reservation_customer",
        "parking_reservations",
        "users",
        ["customer_id"],
        ["id"],
        ondelete="SET NULL",
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Restore mandatory Reservation customer.
    """

    # ------------------------------------------------------
    # Drop FK
    # ------------------------------------------------------

    op.drop_constraint(
        "fk_parking_reservation_customer",
        "parking_reservations",
        type_="foreignkey",
    )

    # ------------------------------------------------------
    # Restore NOT NULL
    # ------------------------------------------------------

    op.alter_column(
        "parking_reservations",
        "customer_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    # ------------------------------------------------------
    # Restore original FK
    # ------------------------------------------------------

    op.create_foreign_key(
        "fk_parking_reservation_customer",
        "parking_reservations",
        "users",
        ["customer_id"],
        ["id"],
        ondelete="RESTRICT",
    )