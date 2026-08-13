"""
Create loyalty account and point transaction tables.

Revision ID: 2a747149bf94
Revises: deeed1dcc491
Create Date: 2026-08-13
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "2a747149bf94"
down_revision: Union[str, Sequence[str], None] = "deeed1dcc491"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================


def upgrade() -> None:
    """
    Create Loyalty Account and Loyalty Point Transaction
    tables.
    """

    # ======================================================
    # PostgreSQL ENUM Types
    # ======================================================

    loyalty_tier = postgresql.ENUM(
        "BRONZE",
        "SILVER",
        "GOLD",
        "PLATINUM",
        name="loyalty_tier",
        create_type=False,
    )

    loyalty_point_transaction_type = postgresql.ENUM(
        "EARN",
        "REDEEM",
        "REFERRAL_BONUS",
        "ADJUSTMENT",
        "REVERSAL",
        "EXPIRATION",
        name="loyalty_point_transaction_type",
        create_type=False,
    )

    # ======================================================
    # Create ENUM Types
    # ======================================================

    loyalty_tier.create(
        op.get_bind(),
        checkfirst=True,
    )

    loyalty_point_transaction_type.create(
        op.get_bind(),
        checkfirst=True,
    )

    # ======================================================
    # Loyalty Accounts
    # ======================================================

    op.create_table(
        "loyalty_accounts",

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "customer_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "points_balance",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),

        sa.Column(
            "lifetime_points",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),

        sa.Column(
            "tier",
            loyalty_tier,
            server_default="BRONZE",
            nullable=False,
        ),

        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default="true",
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

        sa.ForeignKeyConstraint(
            ["customer_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    # ======================================================
    # Loyalty Account Indexes
    # ======================================================

    op.create_index(
        "ix_loyalty_accounts_customer_id",
        "loyalty_accounts",
        ["customer_id"],
        unique=True,
    )

    op.create_index(
        "ix_loyalty_accounts_tier",
        "loyalty_accounts",
        ["tier"],
        unique=False,
    )

    # ======================================================
    # Loyalty Point Transactions
    # ======================================================

    op.create_table(
        "loyalty_point_transactions",

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "loyalty_account_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "transaction_type",
            loyalty_point_transaction_type,
            nullable=False,
        ),

        sa.Column(
            "points",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "balance_after",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "reference_type",
            sa.String(length=50),
            nullable=True,
        ),

        sa.Column(
            "reference_id",
            sa.Integer(),
            nullable=True,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
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

        sa.ForeignKeyConstraint(
            ["loyalty_account_id"],
            ["loyalty_accounts.id"],
            ondelete="CASCADE",
        ),

        sa.PrimaryKeyConstraint("id"),
    )

    # ======================================================
    # Loyalty Point Transaction Indexes
    # ======================================================

    op.create_index(
        "ix_loyalty_point_transactions_loyalty_account_id",
        "loyalty_point_transactions",
        ["loyalty_account_id"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_point_transactions_transaction_type",
        "loyalty_point_transactions",
        ["transaction_type"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_point_transactions_reference_type",
        "loyalty_point_transactions",
        ["reference_type"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_point_transactions_reference_id",
        "loyalty_point_transactions",
        ["reference_id"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_point_transactions_expires_at",
        "loyalty_point_transactions",
        ["expires_at"],
        unique=False,
    )


# ==========================================================
# Downgrade
# ==========================================================


def downgrade() -> None:
    """
    Remove Loyalty Account and Loyalty Point Transaction
    tables.
    """

    # ======================================================
    # Drop Loyalty Point Transaction Indexes
    # ======================================================

    op.drop_index(
        "ix_loyalty_point_transactions_expires_at",
        table_name="loyalty_point_transactions",
    )

    op.drop_index(
        "ix_loyalty_point_transactions_reference_id",
        table_name="loyalty_point_transactions",
    )

    op.drop_index(
        "ix_loyalty_point_transactions_reference_type",
        table_name="loyalty_point_transactions",
    )

    op.drop_index(
        "ix_loyalty_point_transactions_transaction_type",
        table_name="loyalty_point_transactions",
    )

    op.drop_index(
        "ix_loyalty_point_transactions_loyalty_account_id",
        table_name="loyalty_point_transactions",
    )

    # ======================================================
    # Drop Loyalty Point Transactions
    # ======================================================

    op.drop_table(
        "loyalty_point_transactions",
    )

    # ======================================================
    # Drop Loyalty Account Indexes
    # ======================================================

    op.drop_index(
        "ix_loyalty_accounts_tier",
        table_name="loyalty_accounts",
    )

    op.drop_index(
        "ix_loyalty_accounts_customer_id",
        table_name="loyalty_accounts",
    )

    # ======================================================
    # Drop Loyalty Accounts
    # ======================================================

    op.drop_table(
        "loyalty_accounts",
    )

    # ======================================================
    # Drop PostgreSQL ENUM Types
    # ======================================================

    loyalty_point_transaction_type = postgresql.ENUM(
        "EARN",
        "REDEEM",
        "REFERRAL_BONUS",
        "ADJUSTMENT",
        "REVERSAL",
        "EXPIRATION",
        name="loyalty_point_transaction_type",
        create_type=False,
    )

    loyalty_tier = postgresql.ENUM(
        "BRONZE",
        "SILVER",
        "GOLD",
        "PLATINUM",
        name="loyalty_tier",
        create_type=False,
    )

    loyalty_point_transaction_type.drop(
        op.get_bind(),
        checkfirst=True,
    )

    loyalty_tier.drop(
        op.get_bind(),
        checkfirst=True,
    )