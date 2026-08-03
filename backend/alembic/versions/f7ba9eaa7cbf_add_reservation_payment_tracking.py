"""add reservation payment tracking

Revision ID: f7ba9eaa7cbf
Revises: 69999887d035
Create Date: 2026-08-03 23:02:58.352232

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "f7ba9eaa7cbf"
down_revision: Union[str, Sequence[str], None] = "69999887d035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Add payment tracking to parking reservations.
    """

    # Create the enum type first
    payment_status_enum = sa.Enum(
        "PENDING",
        "PAID",
        "PARTIALLY_PAID",
        "FAILED",
        "REFUNDED",
        name="reservation_payment_status",
    )
    payment_status_enum.create(op.get_bind(), checkfirst=True)

    # ======================================================
    # Payment Status
    # ======================================================

    op.add_column(
        "parking_reservations",
        sa.Column(
            "payment_status",
            payment_status_enum,
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),
    )

    # ======================================================
    # Payment Reference
    # ======================================================

    op.add_column(
        "parking_reservations",
        sa.Column(
            "last_payment_transaction_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    # ======================================================
    # Payment Timestamp
    # ======================================================

    op.add_column(
        "parking_reservations",
        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # ======================================================
    # Foreign Key
    # ======================================================

    op.create_foreign_key(
        "fk_reservation_payment_transaction",
        "parking_reservations",
        "payment_transactions",
        ["last_payment_transaction_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # ======================================================
    # Indexes
    # ======================================================

    op.create_index(
        "ix_reservation_payment_status",
        "parking_reservations",
        ["payment_status"],
        unique=False,
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Remove payment tracking from parking reservations.
    """

    # ======================================================
    # Drop Indexes
    # ======================================================

    op.drop_index(
        "ix_reservation_payment_status",
        table_name="parking_reservations",
    )

    # ======================================================
    # Drop Foreign Key
    # ======================================================

    op.drop_constraint(
        "fk_reservation_payment_transaction",
        "parking_reservations",
        type_="foreignkey",
    )

    # ======================================================
    # Drop Columns
    # ======================================================

    op.drop_column(
        "parking_reservations",
        "paid_at",
    )

    op.drop_column(
        "parking_reservations",
        "last_payment_transaction_id",
    )

    op.drop_column(
        "parking_reservations",
        "payment_status",
    )

    # ======================================================
    # Drop Enum
    # ======================================================

    sa.Enum(
        name="reservation_payment_status",
    ).drop(
        op.get_bind(),
        checkfirst=True,
    )