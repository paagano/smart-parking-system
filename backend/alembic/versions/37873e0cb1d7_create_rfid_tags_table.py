"""create rfid tags table

Revision ID: 37873e0cb1d7
Revises: 8b1d7c3e4f20
Create Date: 2026-10-03 00:35:20.680542

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "37873e0cb1d7"
down_revision: Union[str, Sequence[str], None] = "8b1d7c3e4f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create persistent RFID tag registry."""

    op.create_table(
        "rfid_tags",
        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "uid",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "vehicle_id",
            sa.Integer(),
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.PrimaryKeyConstraint(
            "id",
        ),
        sa.ForeignKeyConstraint(
            ["vehicle_id"],
            ["vehicles.id"],
            name="fk_rfid_tags_vehicle_id_vehicles",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "uid",
            name="uq_rfid_tags_uid",
        ),
        sa.UniqueConstraint(
            "vehicle_id",
            name="uq_rfid_tags_vehicle_id",
        ),
    )

    op.create_index(
        "ix_rfid_tags_uid",
        "rfid_tags",
        ["uid"],
        unique=False,
    )

    op.create_index(
        "ix_rfid_tags_vehicle_id",
        "rfid_tags",
        ["vehicle_id"],
        unique=False,
    )


def downgrade() -> None:
    """Remove persistent RFID tag registry."""

    op.drop_index(
        "ix_rfid_tags_vehicle_id",
        table_name="rfid_tags",
    )

    op.drop_index(
        "ix_rfid_tags_uid",
        table_name="rfid_tags",
    )

    op.drop_table(
        "rfid_tags",
    )