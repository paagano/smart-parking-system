"""add vehicle to parking reservations

Revision ID: 17f66a0b0c36
Revises: 4d4e58eb0fe4
Create Date: 2026-08-08 21:12:24.034824

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "17f66a0b0c36"

down_revision: Union[str, Sequence[str], None] = "4d4e58eb0fe4"

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Add vehicle reference to parking reservations.

    The vehicle relationship is intentionally nullable so
    existing reservations can remain valid without requiring
    an immediate vehicle assignment.
    """

    # ======================================================
    # Vehicle Reference
    # ======================================================

    op.add_column(
        "parking_reservations",
        sa.Column(
            "vehicle_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # ======================================================
    # Vehicle Index
    # ======================================================

    op.create_index(
        "ix_parking_reservations_vehicle_id",
        "parking_reservations",
        ["vehicle_id"],
        unique=False,
    )

    # ======================================================
    # Vehicle Foreign Key
    # ======================================================

    op.create_foreign_key(
        "fk_parking_reservations_vehicle_id_vehicles",
        "parking_reservations",
        "vehicles",
        ["vehicle_id"],
        ["id"],
        ondelete="SET NULL",
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Remove vehicle reference from parking reservations.
    """

    # ======================================================
    # Foreign Key
    # ======================================================

    op.drop_constraint(
        "fk_parking_reservations_vehicle_id_vehicles",
        "parking_reservations",
        type_="foreignkey",
    )

    # ======================================================
    # Index
    # ======================================================

    op.drop_index(
        "ix_parking_reservations_vehicle_id",
        table_name="parking_reservations",
    )

    # ======================================================
    # Column
    # ======================================================

    op.drop_column(
        "parking_reservations",
        "vehicle_id",
    )