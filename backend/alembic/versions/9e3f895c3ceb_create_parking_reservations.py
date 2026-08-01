"""
create parking reservations

Revision ID: 9e3f895c3ceb
Revises: f9aedb8b4114
Create Date: 2026-08-01 19:46:04.933181
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "9e3f895c3ceb"
down_revision: Union[str, Sequence[str], None] = "f9aedb8b4114"
branch_labels = None
depends_on = None


# ==========================================================
# PostgreSQL ENUMS
# ==========================================================

reservation_status_enum = postgresql.ENUM(
    "CREATED",
    "CONFIRMED",
    "CHECKED_IN",
    "COMPLETED",
    "CANCELLED",
    "EXPIRED",
    name="reservation_status_enum",
    create_type=False,
)


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Create Parking Reservations table.
    """

    # ------------------------------------------------------
    # Create ENUM
    # ------------------------------------------------------

    reservation_status_enum.create(
        op.get_bind(),
        checkfirst=True,
    )

    # ------------------------------------------------------
    # Create Table
    # ------------------------------------------------------

    op.create_table(
        "parking_reservations",

        # ==================================================
        # Primary Key
        # ==================================================

        sa.Column(
            "id",
            sa.Integer(),
            nullable=False,
        ),

        # ==================================================
        # Identification
        # ==================================================

        sa.Column(
            "reservation_number",
            sa.String(length=50),
            nullable=False,
        ),

        # ==================================================
        # Relationships
        # ==================================================

        sa.Column(
            "customer_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "parking_bay_id",
            sa.Integer(),
            nullable=False,
        ),

        # ==================================================
        # Vehicle Information
        # ==================================================

        sa.Column(
            "vehicle_registration",
            sa.String(length=20),
            nullable=False,
        ),

        sa.Column(
            "vehicle_type",
            postgresql.ENUM(
                name="vehicle_type",
                create_type=False,
            ),
            nullable=False,
        ),

        # ==================================================
        # Reservation Timing
        # ==================================================

        sa.Column(
            "reserved_from",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "reserved_until",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "checked_in_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

                # ==================================================
        # Pricing
        # ==================================================

        sa.Column(
            "estimated_amount",
            sa.Numeric(10, 2),
            nullable=True,
        ),

        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="KES",
        ),

        # ==================================================
        # Status
        # ==================================================

        sa.Column(
            "status",
            reservation_status_enum,
            nullable=False,
            server_default=sa.text("'CREATED'"),
        ),

        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),

        # ==================================================
        # Additional Information
        # ==================================================

        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),

        # ==================================================
        # Audit Fields
        # ==================================================

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

        # ==================================================
        # BaseModel Fields
        # ==================================================

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

        # ==================================================
        # Constraints
        # ==================================================

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_parking_reservations",
        ),

        sa.UniqueConstraint(
            "reservation_number",
            name="uq_parking_reservation_number",
        ),

        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            ondelete="RESTRICT",
            name="fk_parking_reservation_customer",
        ),

        sa.ForeignKeyConstraint(
            ["parking_bay_id"],
            ["parking_bays.id"],
            ondelete="RESTRICT",
            name="fk_parking_reservation_parking_bay",
        ),

        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_parking_reservation_created_by",
        ),

        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_parking_reservation_updated_by",
        ),

        sa.CheckConstraint(
            "reserved_until > reserved_from",
            name="ck_reservation_period",
        ),

        sa.CheckConstraint(
            "estimated_amount IS NULL OR estimated_amount >= 0",
            name="ck_reservation_estimated_amount",
        ),

        sa.CheckConstraint(
            "currency <> ''",
            name="ck_reservation_currency",
        ),
    )

        # ------------------------------------------------------
    # Indexes
    # ------------------------------------------------------

    op.create_index(
        "ix_parking_reservation_number",
        "parking_reservations",
        ["reservation_number"],
    )

    op.create_index(
        "ix_parking_reservation_customer",
        "parking_reservations",
        ["customer_id"],
    )

    op.create_index(
        "ix_parking_reservation_bay",
        "parking_reservations",
        ["parking_bay_id"],
    )

    op.create_index(
        "ix_parking_reservation_vehicle",
        "parking_reservations",
        ["vehicle_registration"],
    )

    op.create_index(
        "ix_parking_reservation_status",
        "parking_reservations",
        ["status"],
    )

    op.create_index(
        "ix_parking_reservation_reserved_from",
        "parking_reservations",
        ["reserved_from"],
    )

    op.create_index(
        "ix_parking_reservation_reserved_until",
        "parking_reservations",
        ["reserved_until"],
    )

    op.create_index(
        "ix_parking_reservation_period",
        "parking_reservations",
        [
            "reserved_from",
            "reserved_until",
        ],
    )

    op.create_index(
        "ix_parking_reservation_bay_period",
        "parking_reservations",
        [
            "parking_bay_id",
            "reserved_from",
            "reserved_until",
        ],
    )

    op.create_index(
        "ix_parking_reservation_expiry",
        "parking_reservations",
        ["expires_at"],
    )

    # ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Drop Parking Reservations table.
    """

    # ------------------------------------------------------
    # Drop Indexes
    # ------------------------------------------------------

    op.drop_index(
        "ix_parking_reservation_expiry",
        table_name="parking_reservations",
    )

    op.drop_index(
        "ix_parking_reservation_bay_period",
        table_name="parking_reservations",
    )

    op.drop_index(
        "ix_parking_reservation_period",
        table_name="parking_reservations",
    )

    op.drop_index(
        "ix_parking_reservation_reserved_until",
        table_name="parking_reservations",
    )

    op.drop_index(
        "ix_parking_reservation_reserved_from",
        table_name="parking_reservations",
    )

    op.drop_index(
        "ix_parking_reservation_status",
        table_name="parking_reservations",
    )

    op.drop_index(
        "ix_parking_reservation_vehicle",
        table_name="parking_reservations",
    )

    op.drop_index(
        "ix_parking_reservation_bay",
        table_name="parking_reservations",
    )

    op.drop_index(
        "ix_parking_reservation_customer",
        table_name="parking_reservations",
    )

    op.drop_index(
        "ix_parking_reservation_number",
        table_name="parking_reservations",
    )

    # ------------------------------------------------------
    # Drop Table
    # ------------------------------------------------------

    op.drop_table(
        "parking_reservations",
    )

    # ------------------------------------------------------
    # Drop ENUM
    # ------------------------------------------------------

    reservation_status_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )