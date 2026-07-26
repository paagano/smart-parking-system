"""create parking_zones table

Revision ID: bbb78a8d290c
Revises: f200ea283f04
Create Date: 2026-07-26 02:15:42.757693
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "bbb78a8d290c"
down_revision: Union[str, Sequence[str], None] = "f200ea283f04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "parking_zones",

        sa.Column(
            "facility_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "parent_zone_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "code",
            sa.String(length=30),
            nullable=False,
        ),

        sa.Column(
            "zone_type",
            sa.Enum(
                "BUILDING_LEVEL",
                "WING",
                "SECTION",
                "AISLE",
                "BLOCK",
                "REGION",
                "DISTRICT",
                "STREET",
                "TERMINAL",
                "PARKING_LOT",
                "CUSTOM",
                name="zone_type",
            ),
            nullable=False,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["parking_facilities.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["parent_zone_id"],
            ["parking_zones.id"],
            ondelete="CASCADE",
        ),

        sa.UniqueConstraint(
            "facility_id",
            "code",
            name="uq_parking_zone_facility_code",
        ),
    )

    op.create_index(
        "ix_parking_zone_facility",
        "parking_zones",
        ["facility_id"],
    )

    op.create_index(
        "ix_parking_zone_parent",
        "parking_zones",
        ["parent_zone_id"],
    )

    op.create_index(
        "ix_parking_zone_type",
        "parking_zones",
        ["zone_type"],
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_parking_zone_type",
        table_name="parking_zones",
    )

    op.drop_index(
        "ix_parking_zone_parent",
        table_name="parking_zones",
    )

    op.drop_index(
        "ix_parking_zone_facility",
        table_name="parking_zones",
    )

    op.drop_table("parking_zones")