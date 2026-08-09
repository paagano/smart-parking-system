"""add vehicle id to parking sessions

Revision ID: ef455a73edee
Revises: 17f66a0b0c36
Create Date: 2026-08-09 06:27:50.383354

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "ef455a73edee"
down_revision: Union[str, Sequence[str], None] = "17f66a0b0c36"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================


def upgrade() -> None:
    """
    Add optional vehicle reference to parking sessions.

    A parking session may represent:

    1. A registered vehicle:
       vehicle_id contains the registered vehicle ID.

    2. A borrowed/unregistered vehicle:
       vehicle_id remains NULL while vehicle_registration
       and vehicle_type contain the captured vehicle details.

    Existing parking sessions are preserved because vehicle_id
    is nullable.
    """

    op.add_column(
        "parking_sessions",
        sa.Column(
            "vehicle_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_parking_sessions_vehicle_id",
        "parking_sessions",
        ["vehicle_id"],
        unique=False,
    )

    op.create_foreign_key(
        "fk_parking_sessions_vehicle_id_vehicles",
        "parking_sessions",
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
    Remove the optional vehicle reference from parking sessions.
    """

    op.drop_constraint(
        "fk_parking_sessions_vehicle_id_vehicles",
        "parking_sessions",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_parking_sessions_vehicle_id",
        table_name="parking_sessions",
    )

    op.drop_column(
        "parking_sessions",
        "vehicle_id",
    )