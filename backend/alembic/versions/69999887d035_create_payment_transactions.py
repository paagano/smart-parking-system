"""create payment transactions

Revision ID: 69999887d035
Revises: 6beaa381ad2b
Create Date: 2026-08-03 01:14:06.662744

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "69999887d035"
down_revision: Union[str, Sequence[str], None] = "6beaa381ad2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Create the payment transaction ledger.
    """

    op.create_table(
        "payment_transactions",

        # ==================================================
        # References
        # ==================================================

        sa.Column(
            "reservation_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "parking_session_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "customer_id",
            sa.Integer(),
            nullable=True,
        ),

        # ==================================================
        # Identity
        # ==================================================

        sa.Column(
            "transaction_number",
            sa.String(60),
            nullable=False,
        ),

        sa.Column(
            "external_reference",
            sa.String(100),
            nullable=True,
            comment="Reference returned by payment provider.",
        ),

        sa.Column(
            "receipt_number",
            sa.String(50),
            nullable=True,
        ),

        # ==================================================
        # Payment Details
        # ==================================================

        sa.Column(
            "payment_type",
            sa.Enum(
                "PAYMENT",
                "REFUND",
                "ADJUSTMENT",
                "REVERSAL",
                "CREDIT",
                "DEBIT",
                "LOYALTY_REWARD",
                "LOYALTY_REDEMPTION",
                "WALLET_TOPUP",
                "WALLET_DEDUCTION",
                name="payment_transaction_type",
            ),
            nullable=False,
        ),

        sa.Column(
            "parent_transaction_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "balance_after",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=True,
        ),

        sa.Column(
            "is_reconciled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),

        sa.Column(
            "payment_purpose",
            sa.Enum(
                "RESERVATION",
                "PARKING_SESSION",
                "WALLET_TOPUP",
                "WALLET_REFUND",
                "PENALTY",
                "SUBSCRIPTION",
                name="payment_transaction_purpose",
            ),
            nullable=False,
        ),

        sa.Column(
            "payment_method",
            sa.Enum(
                "WALLET",
                "MPESA",
                "AIRTEL_MONEY",
                "CASH",
                "BANK_CARD",
                "BANK_TRANSFER",
                name="payment_transaction_method",
            ),
            nullable=False,
        ),

        sa.Column(
            "payment_provider",
            sa.Enum(
                "INTERNAL",
                "SAFARICOM",
                "AIRTEL",
                "VISA",
                "MASTERCARD",
                "BANK",
                "OTHER",
                name="payment_transaction_provider",
            ),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "PROCESSING",
                "SUCCESSFUL",
                "FAILED",
                "CANCELLED",
                "REFUNDED",
                "PARTIALLY_REFUNDED",
                "VOIDED",
                name="payment_transaction_status",
            ),
            server_default=sa.text("'PENDING'"),
            nullable=False,
        ),

        sa.Column(
            "currency",
            sa.Enum(
                "KES",
                "USD",
                "EUR",
                "GBP",
                name="payment_transaction_currency",
            ),
            server_default=sa.text("'KES'"),
            nullable=False,
        ),

        sa.Column(
            "subtotal_amount",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=False,
        ),

        sa.Column(
            "tax_amount",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            server_default=sa.text("0.00"),
            nullable=False,
        ),

        sa.Column(
            "discount_amount",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            server_default=sa.text("0.00"),
            nullable=False,
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
            "idempotency_key",
            sa.String(100),
            nullable=True,
        ),

        # ==================================================
        # Payer Information
        # ==================================================

        sa.Column(
            "payer_name",
            sa.String(100),
            nullable=True,
        ),

        sa.Column(
            "payer_phone",
            sa.String(20),
            nullable=True,
        ),

        sa.Column(
            "payer_email",
            sa.String(255),
            nullable=True,
        ),

        # ==================================================
        # Loyalty
        # ==================================================

        sa.Column(
            "loyalty_points_earned",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),

        sa.Column(
            "loyalty_points_redeemed",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),

        # ==================================================
        # Payment Provider
        # ==================================================

        sa.Column(
            "provider_transaction_id",
            sa.String(100),
            nullable=True,
        ),

        sa.Column(
            "provider_status_message",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "provider_response",
            sa.JSON(),
            nullable=True,
        ),

        # ==================================================
        # Audit
        # ==================================================

        sa.Column(
            "paid_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),

        # ==================================================
        # BaseModel Columns
        # ==================================================

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

        # ==================================================
        # Constraints
        # ==================================================

        sa.ForeignKeyConstraint(
            ["reservation_id"],
            ["parking_reservations.id"],
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["parking_session_id"],
            ["parking_sessions.id"],
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["parent_transaction_id"],
            ["payment_transactions.id"],
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint(
            "id",
        ),

        sa.UniqueConstraint(
            "transaction_number",
        ),

        sa.UniqueConstraint(
            "provider_transaction_id",
        ),

        sa.UniqueConstraint(
            "idempotency_key",
        ),
    )

    # ==========================================================
    # Indexes
    # ==========================================================

    op.create_index(
        "ix_payment_transaction_number",
        "payment_transactions",
        ["transaction_number"],
        unique=False,
    )

    op.create_index(
        "ix_payment_transaction_status",
        "payment_transactions",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_payment_transaction_method",
        "payment_transactions",
        ["payment_method"],
        unique=False,
    )

    op.create_index(
        "ix_payment_transaction_purpose",
        "payment_transactions",
        ["payment_purpose"],
        unique=False,
    )

    op.create_index(
        "ix_payment_transaction_created_at",
        "payment_transactions",
        ["created_at"],
        unique=False,
    )

    op.create_index(
        "ix_payment_customer",
        "payment_transactions",
        ["customer_id"],
        unique=False,
    )

    op.create_index(
        "ix_payment_customer_status",
        "payment_transactions",
        [
            "customer_id",
            "status",
        ],
        unique=False,
    )

    op.create_index(
        "ix_payment_reservation",
        "payment_transactions",
        ["reservation_id"],
        unique=False,
    )

    op.create_index(
        "ix_payment_session",
        "payment_transactions",
        ["parking_session_id"],
        unique=False,
    )

    op.create_index(
        "ix_payment_provider_txn",
        "payment_transactions",
        ["provider_transaction_id"],
        unique=False,
    )

    op.create_index(
        "ix_payment_paid_at",
        "payment_transactions",
        ["paid_at"],
        unique=False,
    )

    op.create_index(
        "ix_payment_transaction_type",
        "payment_transactions",
        ["payment_type"],
        unique=False,
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Drop the payment transaction ledger.
    """

    # ==========================================================
    # Drop Indexes
    # ==========================================================

    op.drop_index(
        "ix_payment_transaction_type",
        table_name="payment_transactions",
    )

    op.drop_index(
        "ix_payment_paid_at",
        table_name="payment_transactions",
    )

    op.drop_index(
        "ix_payment_provider_txn",
        table_name="payment_transactions",
    )

    op.drop_index(
        "ix_payment_session",
        table_name="payment_transactions",
    )

    op.drop_index(
        "ix_payment_reservation",
        table_name="payment_transactions",
    )

    op.drop_index(
        "ix_payment_customer_status",
        table_name="payment_transactions",
    )

    op.drop_index(
        "ix_payment_customer",
        table_name="payment_transactions",
    )

    op.drop_index(
        "ix_payment_transaction_created_at",
        table_name="payment_transactions",
    )

    op.drop_index(
        "ix_payment_transaction_purpose",
        table_name="payment_transactions",
    )

    op.drop_index(
        "ix_payment_transaction_method",
        table_name="payment_transactions",
    )

    op.drop_index(
        "ix_payment_transaction_status",
        table_name="payment_transactions",
    )

    op.drop_index(
        "ix_payment_transaction_number",
        table_name="payment_transactions",
    )

    # ==========================================================
    # Drop Table
    # ==========================================================

    op.drop_table(
        "payment_transactions",
    )