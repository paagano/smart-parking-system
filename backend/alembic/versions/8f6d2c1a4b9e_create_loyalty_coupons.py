"""
Create loyalty coupons.

Revision ID: 8f6d2c1a4b9e
Revises: 633441f73cfd
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "8f6d2c1a4b9e"
down_revision: Union[str, Sequence[str], None] = "633441f73cfd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================


def upgrade() -> None:
    """
    Create the loyalty_coupons table and supporting
    PostgreSQL enum types.
    """

    bind = op.get_bind()

    # ======================================================
    # PostgreSQL Enum Types
    # ======================================================

    # IMPORTANT:
    #
    # create_type=False prevents SQLAlchemy from attempting
    # to automatically create these enum types again when
    # op.create_table() is executed.
    #
    # We explicitly create them below using checkfirst=True.
    # This makes the migration deterministic and prevents:
    #
    #     DuplicateObject: type "coupon_type" already exists
    #
    # ======================================================

    coupon_type = postgresql.ENUM(
        "PERCENTAGE_DISCOUNT",
        "FIXED_AMOUNT_DISCOUNT",
        "FREE_PARKING",
        "FREE_PARKING_HOURS",
        name="coupon_type",
        create_type=False,
    )

    coupon_status = postgresql.ENUM(
        "ACTIVE",
        "USED",
        "EXPIRED",
        "CANCELLED",
        name="coupon_status",
        create_type=False,
    )

    # ======================================================
    # Create Enum Types
    # ======================================================

    coupon_type.create(
        bind,
        checkfirst=True,
    )

    coupon_status.create(
        bind,
        checkfirst=True,
    )

    # ======================================================
    # Loyalty Coupons
    # ======================================================

    op.create_table(
        "loyalty_coupons",

        # --------------------------------------------------
        # Primary Key
        # --------------------------------------------------

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        # --------------------------------------------------
        # Coupon Code
        # --------------------------------------------------

        sa.Column(
            "coupon_code",
            sa.String(length=100),
            nullable=False,
        ),

        # --------------------------------------------------
        # Loyalty Account
        # --------------------------------------------------

        sa.Column(
            "loyalty_account_id",
            sa.Integer(),
            nullable=False,
        ),

        # --------------------------------------------------
        # Source Reward Redemption
        # --------------------------------------------------

        sa.Column(
            "reward_redemption_id",
            sa.Integer(),
            nullable=True,
        ),

        # --------------------------------------------------
        # Coupon Type
        # --------------------------------------------------

        sa.Column(
            "coupon_type",
            coupon_type,
            nullable=False,
        ),

        # --------------------------------------------------
        # Coupon Value
        # --------------------------------------------------

        sa.Column(
            "value",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=True,
        ),

        # --------------------------------------------------
        # Free Parking Duration
        # --------------------------------------------------

        sa.Column(
            "free_parking_minutes",
            sa.Integer(),
            nullable=True,
        ),

        # --------------------------------------------------
        # Coupon Status
        # --------------------------------------------------

        sa.Column(
            "status",
            coupon_status,
            server_default="ACTIVE",
            nullable=False,
        ),

        # --------------------------------------------------
        # Active Flag
        # --------------------------------------------------

        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),

        # --------------------------------------------------
        # Validity
        # --------------------------------------------------

        sa.Column(
            "valid_from",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "valid_until",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # --------------------------------------------------
        # Usage
        # --------------------------------------------------

        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # --------------------------------------------------
        # Payment Transaction
        # --------------------------------------------------

        sa.Column(
            "used_payment_transaction_id",
            sa.Integer(),
            nullable=True,
        ),

        # --------------------------------------------------
        # Description
        # --------------------------------------------------

        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        # --------------------------------------------------
        # TimestampMixin
        # --------------------------------------------------

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

        # --------------------------------------------------
        # Primary Key
        # --------------------------------------------------

        sa.PrimaryKeyConstraint(
            "id",
        ),

        # --------------------------------------------------
        # Loyalty Account FK
        # --------------------------------------------------

        sa.ForeignKeyConstraint(
            ["loyalty_account_id"],
            ["loyalty_accounts.id"],
            ondelete="CASCADE",
        ),

        # --------------------------------------------------
        # Reward Redemption FK
        # --------------------------------------------------

        sa.ForeignKeyConstraint(
            ["reward_redemption_id"],
            ["loyalty_reward_redemptions.id"],
            ondelete="SET NULL",
        ),

        # --------------------------------------------------
        # Payment Transaction FK
        # --------------------------------------------------

        sa.ForeignKeyConstraint(
            ["used_payment_transaction_id"],
            ["payment_transactions.id"],
            ondelete="SET NULL",
        ),

        # --------------------------------------------------
        # Unique Constraints
        # --------------------------------------------------

        sa.UniqueConstraint(
            "coupon_code",
            name="uq_loyalty_coupons_coupon_code",
        ),

        sa.UniqueConstraint(
            "reward_redemption_id",
            name="uq_loyalty_coupons_reward_redemption_id",
        ),
    )

    # ======================================================
    # Indexes
    # ======================================================

    op.create_index(
        "ix_loyalty_coupons_coupon_code",
        "loyalty_coupons",
        ["coupon_code"],
        unique=True,
    )

    op.create_index(
        "ix_loyalty_coupons_loyalty_account_id",
        "loyalty_coupons",
        ["loyalty_account_id"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_coupons_reward_redemption_id",
        "loyalty_coupons",
        ["reward_redemption_id"],
        unique=True,
    )

    op.create_index(
        "ix_loyalty_coupons_coupon_type",
        "loyalty_coupons",
        ["coupon_type"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_coupons_status",
        "loyalty_coupons",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_coupons_is_active",
        "loyalty_coupons",
        ["is_active"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_coupons_valid_until",
        "loyalty_coupons",
        ["valid_until"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_coupons_used_at",
        "loyalty_coupons",
        ["used_at"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_coupons_used_payment_transaction_id",
        "loyalty_coupons",
        ["used_payment_transaction_id"],
        unique=False,
    )


# ==========================================================
# Downgrade
# ==========================================================


def downgrade() -> None:
    """
    Remove the loyalty_coupons table and its PostgreSQL
    enum types.
    """

    # ======================================================
    # Drop Indexes
    # ======================================================

    op.drop_index(
        "ix_loyalty_coupons_used_payment_transaction_id",
        table_name="loyalty_coupons",
    )

    op.drop_index(
        "ix_loyalty_coupons_used_at",
        table_name="loyalty_coupons",
    )

    op.drop_index(
        "ix_loyalty_coupons_valid_until",
        table_name="loyalty_coupons",
    )

    op.drop_index(
        "ix_loyalty_coupons_is_active",
        table_name="loyalty_coupons",
    )

    op.drop_index(
        "ix_loyalty_coupons_status",
        table_name="loyalty_coupons",
    )

    op.drop_index(
        "ix_loyalty_coupons_coupon_type",
        table_name="loyalty_coupons",
    )

    op.drop_index(
        "ix_loyalty_coupons_reward_redemption_id",
        table_name="loyalty_coupons",
    )

    op.drop_index(
        "ix_loyalty_coupons_loyalty_account_id",
        table_name="loyalty_coupons",
    )

    op.drop_index(
        "ix_loyalty_coupons_coupon_code",
        table_name="loyalty_coupons",
    )

    # ======================================================
    # Drop Table
    # ======================================================

    op.drop_table(
        "loyalty_coupons",
    )

    # ======================================================
    # Drop Enum Types
    # ======================================================

    coupon_status = postgresql.ENUM(
        "ACTIVE",
        "USED",
        "EXPIRED",
        "CANCELLED",
        name="coupon_status",
        create_type=False,
    )

    coupon_type = postgresql.ENUM(
        "PERCENTAGE_DISCOUNT",
        "FIXED_AMOUNT_DISCOUNT",
        "FREE_PARKING",
        "FREE_PARKING_HOURS",
        name="coupon_type",
        create_type=False,
    )

    coupon_status.drop(
        op.get_bind(),
        checkfirst=True,
    )

    coupon_type.drop(
        op.get_bind(),
        checkfirst=True,
    )