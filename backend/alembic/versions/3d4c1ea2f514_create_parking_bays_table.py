"""create parking bays table

Revision ID: 3d4c1ea2f514
Revises: bbb78a8d290c
Create Date: 2026-07-26 14:48:55.388020

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "3d4c1ea2f514"
down_revision: Union[str, Sequence[str], None] = "bbb78a8d290c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "parking_bays",

        # ======================================================
        # BaseModel Fields
        # ======================================================

        sa.Column(
            "id",
            sa.Integer(),
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

        # ======================================================
        # Foreign Key
        # ======================================================

        sa.Column(
            "zone_id",
            sa.Integer(),
            nullable=False,
        ),

        # ======================================================
        # Identity
        # ======================================================

        sa.Column(
            "bay_number",
            sa.String(length=20),
            nullable=False,
            comment="Human-readable bay number (e.g. A01, B15, EV-03).",
        ),

        sa.Column(
            "code",
            sa.String(length=30),
            nullable=False,
            comment="Unique internal code for the parking bay.",
        ),

        # ======================================================
        # Classification
        # ======================================================

        sa.Column(
            "bay_type",
            sa.Enum(
                "STANDARD",
                "ACCESSIBLE",
                "EV_CHARGING",
                "VIP",
                "COMPACT",
                "LARGE",
                "MOTORCYCLE",
                "STAFF",
                "VISITOR",
                "LOADING",
                name="bay_type",
            ),
            nullable=False,
        ),

        sa.Column(
            "vehicle_type",
            sa.Enum(
                "CAR",
                "SUV",
                "TRUCK",
                "MOTORCYCLE",
                "BUS",
                "ANY",
                name="vehicle_type",
            ),
            nullable=False,
        ),

        sa.Column(
            "size",
            sa.Enum(
                "SMALL",
                "MEDIUM",
                "LARGE",
                name="bay_size",
            ),
            nullable=False,
        ),

        # ======================================================
        # Features
        # ======================================================

        sa.Column(
            "is_accessible",
            sa.Boolean(),
            nullable=False,
        ),

        sa.Column(
            "is_ev_charging",
            sa.Boolean(),
            nullable=False,
        ),

        sa.Column(
            "is_vip",
            sa.Boolean(),
            nullable=False,
        ),

        sa.Column(
            "is_reservable",
            sa.Boolean(),
            nullable=False,
        ),

        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
        ),

        # ======================================================
        # Display
        # ======================================================

        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        sa.ForeignKeyConstraint(
            ["zone_id"],
            ["parking_zones.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "zone_id",
            "bay_number",
            name="uq_parking_bay_zone_number",
        ),

        sa.UniqueConstraint(
            "zone_id",
            "code",
            name="uq_parking_bay_zone_code",
        ),
    )

    op.create_index(
        "ix_parking_bay_zone_id",
        "parking_bays",
        ["zone_id"],
        unique=False,
    )

    op.create_index(
        "ix_parking_bay_bay_type",
        "parking_bays",
        ["bay_type"],
        unique=False,
    )

    op.create_index(
        "ix_parking_bay_vehicle_type",
        "parking_bays",
        ["vehicle_type"],
        unique=False,
    )

    op.create_index(
        "ix_parking_bay_is_active",
        "parking_bays",
        ["is_active"],
        unique=False,
    )

    op.create_index(
        op.f("ix_parking_bays_id"),
        "parking_bays",
        ["id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_parking_bays_id"),
        table_name="parking_bays",
    )

    op.drop_index(
        "ix_parking_bay_is_active",
        table_name="parking_bays",
    )

    op.drop_index(
        "ix_parking_bay_vehicle_type",
        table_name="parking_bays",
    )

    op.drop_index(
        "ix_parking_bay_bay_type",
        table_name="parking_bays",
    )

    op.drop_index(
        "ix_parking_bay_zone_id",
        table_name="parking_bays",
    )

    op.drop_table("parking_bays")