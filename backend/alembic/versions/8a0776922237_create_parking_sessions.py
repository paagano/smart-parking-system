"""create parking sessions

Revision ID: 8a0776922237
Revises: 89a7829c591e
Create Date: 2026-07-26 23:59:22.747107
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8a0776922237"
down_revision: Union[str, Sequence[str], None] = "89a7829c591e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "parking_sessions",

        sa.Column(
            "session_number",
            sa.String(30),
            nullable=False,
        ),

        sa.Column(
            "parking_bay_id",
            sa.Integer(),
            nullable=False,
        ),

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

        sa.Column(
            "vehicle_registration",
            sa.String(20),
            nullable=False,
        ),

        # Existing PostgreSQL enum
        sa.Column(
            "vehicle_type",
            postgresql.ENUM(
                "CAR",
                "SUV",
                "TRUCK",
                "MOTORCYCLE",
                "BUS",
                "ANY",
                name="vehicle_type",
                create_type=False,
            ),
            nullable=False,
        ),

        # New enums (created by this migration)
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "COMPLETED",
                "CANCELLED",
                "EXPIRED",
                name="session_status",
            ),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),

        sa.Column(
            "session_source",
            sa.Enum(
                "ATTENDANT",
                "RESERVATION",
                "DRIVE_IN",
                "SENSOR",
                "API",
                name="session_source",
            ),
            nullable=False,
        ),

        sa.Column(
            "entry_method",
            sa.Enum(
                "MANUAL",
                "QR_CODE",
                "RFID",
                "ANPR",
                "MOBILE_APP",
                "SENSOR",
                name="entry_method",
            ),
            nullable=False,
        ),

        sa.Column(
            "exit_method",
            sa.Enum(
                "MANUAL",
                "QR_CODE",
                "RFID",
                "ANPR",
                "MOBILE_APP",
                "SENSOR",
                name="exit_method",
            ),
            nullable=True,
        ),

        sa.Column(
            "entry_time",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "expected_exit_time",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "exit_time",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "duration_minutes",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "calculated_amount",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),

        sa.Column(
            "paid_amount",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),

        sa.Column(
            "payment_status",
            sa.Enum(
                "PENDING",
                "PARTIAL",
                "PAID",
                "FAILED",
                "WAIVED",
                "REFUNDED",
                name="payment_status",
            ),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),

        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
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
            ["parking_bay_id"],
            ["parking_bays.id"],
            ondelete="RESTRICT",
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

        sa.UniqueConstraint(
            "session_number",
            name="uq_parking_sessions_session_number",
        ),
    )

    op.create_index(
        "ix_parking_sessions_bay",
        "parking_sessions",
        ["parking_bay_id"],
        unique=False,
    )

    op.create_index(
        "ix_parking_sessions_entry_time",
        "parking_sessions",
        ["entry_time"],
        unique=False,
    )

    op.create_index(
        "ix_parking_sessions_payment_status",
        "parking_sessions",
        ["payment_status"],
        unique=False,
    )

    op.create_index(
        "ix_parking_sessions_status",
        "parking_sessions",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_parking_sessions_vehicle",
        "parking_sessions",
        ["vehicle_registration"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        "ix_parking_sessions_vehicle",
        table_name="parking_sessions",
    )

    op.drop_index(
        "ix_parking_sessions_status",
        table_name="parking_sessions",
    )

    op.drop_index(
        "ix_parking_sessions_payment_status",
        table_name="parking_sessions",
    )

    op.drop_index(
        "ix_parking_sessions_entry_time",
        table_name="parking_sessions",
    )

    op.drop_index(
        "ix_parking_sessions_bay",
        table_name="parking_sessions",
    )

    op.drop_table("parking_sessions")