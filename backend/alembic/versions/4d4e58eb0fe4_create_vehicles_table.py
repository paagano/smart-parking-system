"""create vehicles table

Revision ID: 4d4e58eb0fe4
Revises: 1053b272df4a
Create Date: 2026-08-08 15:30:52.337548
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.

revision: str = "4d4e58eb0fe4"
down_revision: Union[str, Sequence[str], None] = "1053b272df4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Create vehicles table.
    """

    op.create_table(
        "vehicles",

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),

        sa.Column(
            "customer_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "plate_country",
            sa.String(length=2),
            nullable=False,
            server_default=sa.text("'KE'"),
        ),

        sa.Column(
            "registration_number",
            sa.String(length=20),
            nullable=False,
        ),

        sa.Column(
            "nickname",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "make",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "model",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "colour",
            sa.String(length=50),
            nullable=True,
        ),

        sa.Column(
            "year",
            sa.Integer(),
            nullable=True,
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
                name="vehicletype",
            ),
            nullable=False,
        ),

        sa.Column(
            "parking_profile",
            sa.Enum(
                "STANDARD",
                "ELECTRIC",
                "ACCESSIBLE",
                "VIP",
                "COMMERCIAL",
                "EMERGENCY",
                name="parkingprofile",
            ),
            nullable=False,
            server_default=sa.text("'STANDARD'"),
        ),

        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),

        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )

    op.create_index(
        "ix_vehicles_customer_id",
        "vehicles",
        ["customer_id"],
    )

    op.create_index(
        "ix_vehicles_registration_number",
        "vehicles",
        ["registration_number"],
        unique=True,
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Drop vehicles table.
    """

    op.drop_index(
        "ix_vehicles_registration_number",
        table_name="vehicles",
    )

    op.drop_index(
        "ix_vehicles_customer_id",
        table_name="vehicles",
    )

    op.drop_table(
        "vehicles",
    )