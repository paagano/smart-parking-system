"""
Add Wallet Transaction ledger.

Creates the immutable WalletTransaction ledger.

Every movement of money into or out of a Wallet is recorded
in this table.

Revision ID: 4580eb9e21eb
Revises: cdfc4af6e462
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "4580eb9e21eb"

down_revision: Union[str, Sequence[str], None] = (
    "cdfc4af6e462"
)

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Create the immutable WalletTransaction ledger.
    """

    op.create_table(

        "wallet_transactions",

        # ======================================================
        # Relationships
        # ======================================================

        sa.Column(
            "wallet_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "payment_transaction_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "created_by",
            sa.Integer(),
            nullable=True,
        ),

        # ======================================================
        # Identity
        # ======================================================

        sa.Column(
            "transaction_number",
            sa.String(60),
            nullable=False,
        ),

        sa.Column(
            "reference",
            sa.String(100),
            nullable=True,
            comment=(
                "Business reference such as reservation, "
                "session or payment number."
            ),
        ),

        # ======================================================
        # Transaction Details
        # ======================================================

        sa.Column(
            "transaction_type",
            sa.Enum(
                "TOP_UP",
                "OPENING_BALANCE",
                "CREDIT",
                "DEBIT",
                "PAYMENT",
                "RESERVATION_HOLD",
                "RESERVATION_RELEASE",
                "REFUND",
                "REVERSAL",
                "ADJUSTMENT",
                "SYSTEM_CORRECTION",
                "LOYALTY_REWARD",
                "LOYALTY_REDEMPTION",
                name="wallet_transaction_type",
            ),
            nullable=False,
        ),

        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "COMPLETED",
                "FAILED",
                "CANCELLED",
                "REVERSED",
                name="wallet_transaction_status",
            ),
            nullable=False,
            server_default=sa.text("'COMPLETED'"),
        ),

        #
        # ISO 4217 Currency Code.
        #
        # Stored as VARCHAR(3) rather than a PostgreSQL ENUM
        # to simplify migrations and future extensibility.
        #
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
        ),

        # ======================================================
        # Financial Values
        # ======================================================

        sa.Column(
            "amount",
            sa.Numeric(12, 2),
            nullable=False,
        ),

        sa.Column(
            "balance_before",
            sa.Numeric(12, 2),
            nullable=False,
        ),

        sa.Column(
            "balance_after",
            sa.Numeric(12, 2),
            nullable=False,
        ),

        # ======================================================
        # Narrative
        # ======================================================

        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),

        # ======================================================
        # Audit
        # ======================================================

        sa.Column(
            "posted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        # ======================================================
        # BaseModel
        # ======================================================

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
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        # ======================================================
        # Constraints
        # ======================================================

        sa.ForeignKeyConstraint(
            ["wallet_id"],
            ["wallets.id"],
            name="fk_wallet_transaction_wallet",
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["payment_transaction_id"],
            ["payment_transactions.id"],
            name="fk_wallet_transaction_payment",
            ondelete="SET NULL",
        ),

        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_wallet_transaction_created_by",
            ondelete="SET NULL",
        ),

        sa.PrimaryKeyConstraint("id"),

        sa.UniqueConstraint(
            "transaction_number",
            name="uq_wallet_transaction_number",
        ),
    )

    # ==========================================================
    # Indexes
    # ==========================================================

    op.create_index(
        "ix_wallet_transaction_wallet",
        "wallet_transactions",
        ["wallet_id"],
        unique=False,
    )

    op.create_index(
        "ix_wallet_transaction_payment",
        "wallet_transactions",
        ["payment_transaction_id"],
        unique=False,
    )

    op.create_index(
        "ix_wallet_transaction_number",
        "wallet_transactions",
        ["transaction_number"],
        unique=False,
    )

    op.create_index(
        "ix_wallet_transaction_status",
        "wallet_transactions",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_wallet_transaction_type",
        "wallet_transactions",
        ["transaction_type"],
        unique=False,
    )

    op.create_index(
        "ix_wallet_transaction_created_at",
        "wallet_transactions",
        ["created_at"],
        unique=False,
    )

    op.create_index(
        "ix_wallet_transactions_id",
        "wallet_transactions",
        ["id"],
        unique=False,
    )

    # ==========================================================
    # Composite Indexes for Performance
    # ==========================================================

    op.create_index(
        "ix_wallet_transaction_wallet_status",
        "wallet_transactions",
        ["wallet_id", "status"],
        unique=False,
    )

    op.create_index(
        "ix_wallet_transaction_wallet_created",
        "wallet_transactions",
        ["wallet_id", "created_at"],
        unique=False,
    )

    op.create_index(
        "ix_wallet_transaction_wallet_type",
        "wallet_transactions",
        ["wallet_id", "transaction_type"],
        unique=False,
    )

    # ==========================================================
    # Check Constraint for Balance Consistency
    # ==========================================================

    op.execute("""
        ALTER TABLE wallet_transactions
        ADD CONSTRAINT check_balance_consistency
        CHECK (
            (transaction_type IN ('CREDIT', 'TOP_UP', 'OPENING_BALANCE', 'REFUND', 'REVERSAL', 'LOYALTY_REWARD', 'SYSTEM_CORRECTION')
             AND balance_after = balance_before + amount)
            OR
            (transaction_type IN ('DEBIT', 'PAYMENT', 'RESERVATION_HOLD', 'RESERVATION_RELEASE', 'ADJUSTMENT', 'LOYALTY_REDEMPTION')
             AND balance_after = balance_before - amount)
        )
    """)


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Drop the Wallet Transaction ledger.
    """

    # ==========================================================
    # Drop Check Constraint
    # ==========================================================

    op.execute(
        "ALTER TABLE wallet_transactions DROP CONSTRAINT IF EXISTS check_balance_consistency"
    )

    # ==========================================================
    # Drop Composite Indexes
    # ==========================================================

    op.drop_index(
        "ix_wallet_transaction_wallet_type",
        table_name="wallet_transactions",
    )

    op.drop_index(
        "ix_wallet_transaction_wallet_created",
        table_name="wallet_transactions",
    )

    op.drop_index(
        "ix_wallet_transaction_wallet_status",
        table_name="wallet_transactions",
    )

    # ==========================================================
    # Drop Indexes
    # ==========================================================

    op.drop_index(
        "ix_wallet_transactions_id",
        table_name="wallet_transactions",
    )

    op.drop_index(
        "ix_wallet_transaction_created_at",
        table_name="wallet_transactions",
    )

    op.drop_index(
        "ix_wallet_transaction_type",
        table_name="wallet_transactions",
    )

    op.drop_index(
        "ix_wallet_transaction_status",
        table_name="wallet_transactions",
    )

    op.drop_index(
        "ix_wallet_transaction_number",
        table_name="wallet_transactions",
    )

    op.drop_index(
        "ix_wallet_transaction_payment",
        table_name="wallet_transactions",
    )

    op.drop_index(
        "ix_wallet_transaction_wallet",
        table_name="wallet_transactions",
    )

    # ==========================================================
    # Drop Table
    # ==========================================================

    op.drop_table(
        "wallet_transactions",
    )

    # ==========================================================
    # Drop Enum Types (PostgreSQL only)
    # ==========================================================

    # These will be automatically dropped by PostgreSQL
    # when the table is dropped, but we drop them explicitly
    # to clean up properly
    op.execute("DROP TYPE IF EXISTS wallet_transaction_type")
    op.execute("DROP TYPE IF EXISTS wallet_transaction_status")