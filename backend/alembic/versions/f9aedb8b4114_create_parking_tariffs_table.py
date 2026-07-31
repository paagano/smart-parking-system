"""
create parking tariffs table

Revision ID: f9aedb8b4114
Revises: 25c3c4f606d2
Create Date: 2026-07-31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers
revision: str = "f9aedb8b4114"
down_revision: Union[str, Sequence[str], None] = "25c3c4f606d2"
branch_labels = None
depends_on = None


billing_type_enum = postgresql.ENUM(
    "HOURLY",
    "DAILY",
    "FLAT",
    name="billing_type",
    create_type=False,
)


def upgrade() -> None:
    """
    Create Parking Tariffs table.
    """

    # ---------------------------------------------------------
    # Create ENUM
    # ---------------------------------------------------------

    billing_type_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    # ---------------------------------------------------------
    # Create Table
    # ---------------------------------------------------------

    op.create_table(
        "parking_tariffs",

        # =====================================================
        # Primary Key
        # =====================================================

        sa.Column("id", sa.Integer(), nullable=False),

        # =====================================================
        # Identification
        # =====================================================

        sa.Column(
            "name",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "code",
            sa.String(length=50),
            nullable=False,
        ),

        sa.Column(
            "display_order",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),

        sa.Column(
            "pricing_priority",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),

        # =====================================================
        # Classification
        # =====================================================

        sa.Column(
            "vehicle_type",
            postgresql.ENUM(
                name="vehicle_type",
                create_type=False,
            ),
            nullable=False,
        ),

        sa.Column(
            "billing_type",
            billing_type_enum,
            nullable=False,
        ),

        # =====================================================
        # Pricing
        # =====================================================

        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="KES",
        ),

        sa.Column(
            "grace_period_minutes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "minimum_charge",
            sa.Numeric(10, 2),
            nullable=True,
        ),

        sa.Column(
            "hourly_rate",
            sa.Numeric(10, 2),
            nullable=True,
        ),

        sa.Column(
            "daily_rate",
            sa.Numeric(10, 2),
            nullable=True,
        ),

        sa.Column(
            "flat_rate",
            sa.Numeric(10, 2),
            nullable=True,
        ),

        sa.Column(
            "max_daily_charge",
            sa.Numeric(10, 2),
            nullable=True,
        ),

        # =====================================================
        # Validity
        # =====================================================

        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "effective_to",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # =====================================================
        # Status
        # =====================================================

        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        # =====================================================
        # Audit
        # =====================================================

        sa.Column(
            "created_by",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "updated_by",
            sa.Integer(),
            nullable=True,
        ),

        # =====================================================
        # Additional Information
        # =====================================================

        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),

        # =====================================================
        # BaseModel Fields
        # =====================================================

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),

        # =====================================================
        # Constraints
        # =====================================================

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "code",
            name="uq_parking_tariffs_code",
        ),

        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            ondelete="SET NULL",
        ),

        sa.CheckConstraint(
            "grace_period_minutes >= 0",
            name="ck_tariff_grace_period",
        ),

        sa.CheckConstraint(
            "pricing_priority > 0",
            name="ck_tariff_priority",
        ),

        sa.CheckConstraint(
            "minimum_charge IS NULL OR minimum_charge >= 0",
            name="ck_tariff_minimum_charge",
        ),

        sa.CheckConstraint(
            "hourly_rate IS NULL OR hourly_rate >= 0",
            name="ck_tariff_hourly_rate",
        ),

        sa.CheckConstraint(
            "daily_rate IS NULL OR daily_rate >= 0",
            name="ck_tariff_daily_rate",
        ),

        sa.CheckConstraint(
            "flat_rate IS NULL OR flat_rate >= 0",
            name="ck_tariff_flat_rate",
        ),

        sa.CheckConstraint(
            "max_daily_charge IS NULL OR max_daily_charge >= 0",
            name="ck_tariff_max_daily_charge",
        ),
    )

    # ---------------------------------------------------------
    # Indexes
    # ---------------------------------------------------------

    op.create_index(
        "ix_tariff_vehicle_type",
        "parking_tariffs",
        ["vehicle_type"],
    )

    op.create_index(
        "ix_tariff_billing_type",
        "parking_tariffs",
        ["billing_type"],
    )

    op.create_index(
        "ix_tariff_active",
        "parking_tariffs",
        ["is_active"],
    )

    op.create_index(
        "ix_tariff_priority",
        "parking_tariffs",
        ["pricing_priority"],
    )

    op.create_index(
        "ix_tariff_effective_from",
        "parking_tariffs",
        ["effective_from"],
    )

    op.create_index(
        "ix_tariff_effective_to",
        "parking_tariffs",
        ["effective_to"],
    )

    op.create_index(
        "ix_tariff_lookup",
        "parking_tariffs",
        [
            "vehicle_type",
            "billing_type",
            "is_active",
            "pricing_priority",
        ],
    )


def downgrade() -> None:
    """
    Drop Parking Tariffs table.
    """

    op.drop_index("ix_tariff_lookup", table_name="parking_tariffs")
    op.drop_index("ix_tariff_effective_to", table_name="parking_tariffs")
    op.drop_index("ix_tariff_effective_from", table_name="parking_tariffs")
    op.drop_index("ix_tariff_priority", table_name="parking_tariffs")
    op.drop_index("ix_tariff_active", table_name="parking_tariffs")
    op.drop_index("ix_tariff_billing_type", table_name="parking_tariffs")
    op.drop_index("ix_tariff_vehicle_type", table_name="parking_tariffs")

    op.drop_table("parking_tariffs")

    billing_type_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )