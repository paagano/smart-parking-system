"""add facility assignment to users

Revision ID: 8b1d7c3e4f20
Revises: 474fb60e0056
Create Date: 2026-09-12 17:23:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "8b1d7c3e4f20"
down_revision: Union[str, Sequence[str], None] = "474fb60e0056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add optional facility assignment to users.

    The column remains nullable for existing drivers/admins and for any
    legacy attendant accounts until an administrator assigns a facility.
    Operator-only workflows will require a non-null facility_id.
    """
    op.add_column(
        "users",
        sa.Column("facility_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_users_facility_id",
        "users",
        ["facility_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_users_facility_id_parking_facilities",
        "users",
        "parking_facilities",
        ["facility_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove user facility assignment."""
    op.drop_constraint(
        "fk_users_facility_id_parking_facilities",
        "users",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_users_facility_id",
        table_name="users",
    )
    op.drop_column("users", "facility_id")
