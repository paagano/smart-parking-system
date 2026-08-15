"""
Create loyalty referrals.

Revision ID: 9a7b3c2d1e5f
Revises: 8f6d2c1a4b9e
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "9a7b3c2d1e5f"
down_revision: Union[str, Sequence[str], None] = "8f6d2c1a4b9e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# Upgrade
# ==========================================================


def upgrade() -> None:
    """
    Create the referral_status enum and loyalty_referrals
    table.
    """

    bind = op.get_bind()

    # ======================================================
    # Create Referral Status Enum
    # ======================================================

    referral_status_enum = postgresql.ENUM(
        "PENDING",
        "QUALIFIED",
        "REWARDED",
        "CANCELLED",
        name="referral_status",
    )

    referral_status_enum.create(
        bind,
        checkfirst=True,
    )

    # ======================================================
    # Create Loyalty Referrals Table
    # ======================================================

    referral_status_column = postgresql.ENUM(
        "PENDING",
        "QUALIFIED",
        "REWARDED",
        "CANCELLED",
        name="referral_status",
        create_type=False,
    )

    op.create_table(
        "loyalty_referrals",

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
        # Referrer
        # --------------------------------------------------

        sa.Column(
            "referrer_id",
            sa.Integer(),
            nullable=False,
        ),

        # --------------------------------------------------
        # Referred Customer
        # --------------------------------------------------

        sa.Column(
            "referred_id",
            sa.Integer(),
            nullable=False,
        ),

        # --------------------------------------------------
        # Referral Code
        # --------------------------------------------------

        sa.Column(
            "referral_code",
            sa.String(length=100),
            nullable=False,
        ),

        # --------------------------------------------------
        # Status
        # --------------------------------------------------

        sa.Column(
            "status",
            referral_status_column,
            nullable=False,
            server_default="PENDING",
        ),

        # --------------------------------------------------
        # Reward Points
        # --------------------------------------------------

        sa.Column(
            "reward_points",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        # --------------------------------------------------
        # Qualification
        # --------------------------------------------------

        sa.Column(
            "qualified_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # --------------------------------------------------
        # Reward
        # --------------------------------------------------

        sa.Column(
            "rewarded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # --------------------------------------------------
        # Cancellation
        # --------------------------------------------------

        sa.Column(
            "cancelled_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        # --------------------------------------------------
        # Notes
        # --------------------------------------------------

        sa.Column(
            "notes",
            sa.Text(),
            nullable=True,
        ),

        # --------------------------------------------------
        # Base Model Audit Columns
        # --------------------------------------------------

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

        # --------------------------------------------------
        # Primary Key
        # --------------------------------------------------

        sa.PrimaryKeyConstraint(
            "id",
        ),

        # --------------------------------------------------
        # Foreign Keys
        # --------------------------------------------------

        sa.ForeignKeyConstraint(
            ["referrer_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["referred_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),

        # --------------------------------------------------
        # Business Constraints
        # --------------------------------------------------

        sa.CheckConstraint(
            "referrer_id <> referred_id",
            name="ck_loyalty_referral_different_customers",
        ),

        sa.CheckConstraint(
            "reward_points >= 0",
            name="ck_loyalty_referral_reward_points_non_negative",
        ),

        # --------------------------------------------------
        # Unique Referral Code
        # --------------------------------------------------

        sa.UniqueConstraint(
            "referral_code",
            name="uq_loyalty_referrals_referral_code",
        ),
    )

    # ======================================================
    # Indexes
    # ======================================================

    op.create_index(
        "ix_loyalty_referrals_referrer_id",
        "loyalty_referrals",
        ["referrer_id"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_referrals_referred_id",
        "loyalty_referrals",
        ["referred_id"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_referrals_referral_code",
        "loyalty_referrals",
        ["referral_code"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_referrals_status",
        "loyalty_referrals",
        ["status"],
        unique=False,
    )


# ==========================================================
# Downgrade
# ==========================================================


def downgrade() -> None:
    """
    Drop the loyalty_referrals table and referral_status
    enum.
    """

    # ======================================================
    # Drop Indexes
    # ======================================================

    op.drop_index(
        "ix_loyalty_referrals_status",
        table_name="loyalty_referrals",
    )

    op.drop_index(
        "ix_loyalty_referrals_referral_code",
        table_name="loyalty_referrals",
    )

    op.drop_index(
        "ix_loyalty_referrals_referred_id",
        table_name="loyalty_referrals",
    )

    op.drop_index(
        "ix_loyalty_referrals_referrer_id",
        table_name="loyalty_referrals",
    )

    # ======================================================
    # Drop Table
    # ======================================================

    op.drop_table(
        "loyalty_referrals",
    )

    # ======================================================
    # Drop Enum
    # ======================================================

    referral_status_enum = postgresql.ENUM(
        "PENDING",
        "QUALIFIED",
        "REWARDED",
        "CANCELLED",
        name="referral_status",
    )

    referral_status_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )