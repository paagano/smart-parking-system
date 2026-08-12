"""create receipts table

Revision ID: deeed1dcc491
Revises: 1e211bf00327
Create Date: 2026-08-11 20:31:37.365626

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.

revision: str = "deeed1dcc491"
down_revision: Union[str, Sequence[str], None] = "1e211bf00327"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the receipts table."""

    # ==========================================================
    # Receipt Enum Types
    # ==========================================================

    receipt_type = sa.Enum(
        "PAYMENT",
        "REFUND",
        name="receipt_type",
    )

    receipt_status = sa.Enum(
        "PENDING",
        "GENERATED",
        "AVAILABLE",
        "FAILED",
        name="receipt_status",
    )

    # ==========================================================
    # Receipts Table
    # ==========================================================

    op.create_table(
        "receipts",

        # ------------------------------------------------------
        # Primary Key
        # ------------------------------------------------------

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        # ------------------------------------------------------
        # Receipt Identity
        # ------------------------------------------------------

        sa.Column(
            "receipt_number",
            sa.String(length=50),
            nullable=False,
            unique=True,
        ),

        sa.Column(
            "receipt_type",
            receipt_type,
            nullable=False,
            server_default="PAYMENT",
        ),

        sa.Column(
            "status",
            receipt_status,
            nullable=False,
            server_default="PENDING",
        ),

        # ------------------------------------------------------
        # Payment Relationship
        # ------------------------------------------------------

        sa.Column(
            "payment_transaction_id",
            sa.Integer(),
            nullable=False,
            unique=True,
        ),

        # ------------------------------------------------------
        # Customer
        # ------------------------------------------------------

        sa.Column(
            "customer_id",
            sa.Integer(),
            nullable=True,
        ),

        # ------------------------------------------------------
        # Financial Snapshot
        # ------------------------------------------------------

        sa.Column(
            "subtotal_amount",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=False,
        ),

        sa.Column(
            "discount_amount",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=False,
            server_default="0.00",
        ),

        sa.Column(
            "tax_amount",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=False,
            server_default="0.00",
        ),

        sa.Column(
            "total_amount",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=False,
        ),

        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default="KES",
        ),

        # ------------------------------------------------------
        # Payment Snapshot
        # ------------------------------------------------------

        sa.Column(
            "payment_method",
            sa.String(length=50),
            nullable=False,
        ),

        sa.Column(
            "payment_provider",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "provider_receipt_number",
            sa.String(length=100),
            nullable=True,
        ),

        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # ------------------------------------------------------
        # Customer Snapshot
        # ------------------------------------------------------

        sa.Column(
            "customer_name",
            sa.String(length=255),
            nullable=True,
        ),

        sa.Column(
            "customer_phone",
            sa.String(length=30),
            nullable=True,
        ),

        sa.Column(
            "customer_email",
            sa.String(length=255),
            nullable=True,
        ),

        # ------------------------------------------------------
        # Document / Storage
        # ------------------------------------------------------

        sa.Column(
            "pdf_storage_path",
            sa.String(length=500),
            nullable=True,
        ),

        sa.Column(
            "pdf_url",
            sa.String(length=1000),
            nullable=True,
        ),

        # ------------------------------------------------------
        # QR / Verification
        # ------------------------------------------------------

        sa.Column(
            "verification_token",
            sa.String(length=128),
            nullable=False,
            unique=True,
        ),

        sa.Column(
            "qr_code_data",
            sa.Text(),
            nullable=True,
        ),

        # ------------------------------------------------------
        # Generation Lifecycle
        # ------------------------------------------------------

        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "failure_reason",
            sa.Text(),
            nullable=True,
        ),

        # ------------------------------------------------------
        # Audit
        # ------------------------------------------------------

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),

        # ------------------------------------------------------
        # Constraints
        # ------------------------------------------------------

        sa.PrimaryKeyConstraint(
            "id",
        ),

        sa.ForeignKeyConstraint(
            ["payment_transaction_id"],
            ["payment_transactions.id"],
            ondelete="RESTRICT",
        ),

        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
    )

    # ==========================================================
    # Indexes
    # ==========================================================

    op.create_index(
        "ix_receipts_status",
        "receipts",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_receipts_customer_status",
        "receipts",
        ["customer_id", "status"],
        unique=False,
    )

    op.create_index(
        "ix_receipts_provider_receipt_number",
        "receipts",
        ["provider_receipt_number"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the receipts table."""

    op.drop_index(
        "ix_receipts_provider_receipt_number",
        table_name="receipts",
    )

    op.drop_index(
        "ix_receipts_customer_status",
        table_name="receipts",
    )

    op.drop_index(
        "ix_receipts_status",
        table_name="receipts",
    )

    op.drop_table("receipts")

    # ==========================================================
    # Receipt Enum Types
    # ==========================================================

    receipt_status = sa.Enum(
        "PENDING",
        "GENERATED",
        "AVAILABLE",
        "FAILED",
        name="receipt_status",
    )

    receipt_type = sa.Enum(
        "PAYMENT",
        "REFUND",
        name="receipt_type",
    )

    receipt_status.drop(
        op.get_bind(),
        checkfirst=True,
    )

    receipt_type.drop(
        op.get_bind(),
        checkfirst=True,
    )