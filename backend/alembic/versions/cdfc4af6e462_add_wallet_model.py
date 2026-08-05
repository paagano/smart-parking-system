"""
Add Wallet model.

Creates the customer Wallet table.

Each customer owns exactly one Wallet.

Revision ID: cdfc4af6e462
Revises: b44221177066
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "cdfc4af6e462"

down_revision: Union[str, Sequence[str], None] = (
    "b44221177066"
)

branch_labels: Union[str, Sequence[str], None] = None

depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """Upgrade schema."""

    # Create the Wallet table.
    op.create_table(
        "wallets",

        # ======================================================
        # Identification
        # ======================================================

        sa.Column(
            "wallet_number",
            sa.String(length=30),
            nullable=False,
        ),

        # ======================================================
        # Ownership
        # ======================================================

        sa.Column(
            "customer_id",
            sa.Integer(),
            nullable=False,
        ),

        # ======================================================
        # Wallet Status
        # ======================================================

        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "SUSPENDED",
                "CLOSED",
                name="wallet_status",
            ),
            nullable=False,
            server_default=sa.text("'ACTIVE'"),
        ),

        # ======================================================
        # Currency
        # ======================================================

        sa.Column(
            "currency",
            sa.Enum(
                "KES",
                "USD",
                "EUR",
                "GBP",
                name="currency",
            ),
            nullable=False,
            server_default=sa.text("'KES'"),
        ),

        # ======================================================
        # Financial Balances
        # ======================================================

        sa.Column(
            "available_balance",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),

        sa.Column(
            "reserved_balance",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),

        sa.Column(
            "total_credited",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),

        sa.Column(
            "total_debited",
            sa.Numeric(12, 2),
            nullable=False,
            server_default=sa.text("0.00"),
        ),

        # ======================================================
        # Audit
        # ======================================================

        sa.Column(
            "last_transaction_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # ======================================================
        # BaseModel Columns
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
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),

        # ======================================================
        # Constraints
        # ======================================================

        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),

        sa.UniqueConstraint(
            "wallet_number",
            name="uq_wallet_wallet_number",
        ),

        sa.UniqueConstraint(
            "customer_id",
            name="uq_wallet_customer",
        ),
    )

    # ==========================================================
    # Indexes
    # ==========================================================

    op.create_index(
        "ix_wallet_wallet_number",
        "wallets",
        ["wallet_number"],
        unique=False,
    )

    op.create_index(
        "ix_wallet_customer",
        "wallets",
        ["customer_id"],
        unique=False,
    )

    op.create_index(
        "ix_wallet_status",
        "wallets",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_wallets_id",
        "wallets",
        ["id"],
        unique=False,
    )

# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Revert the Wallet model.
    """

    # ==========================================================
    # Drop Indexes
    # ==========================================================

    op.drop_index(
        "ix_wallets_id",
        table_name="wallets",
    )

    op.drop_index(
        "ix_wallet_status",
        table_name="wallets",
    )

    op.drop_index(
        "ix_wallet_customer",
        table_name="wallets",
    )

    op.drop_index(
        "ix_wallet_wallet_number",
        table_name="wallets",
    )

    # ==========================================================
    # Drop Wallet Table
    # ==========================================================

    op.drop_table(
        "wallets",
    )

    





