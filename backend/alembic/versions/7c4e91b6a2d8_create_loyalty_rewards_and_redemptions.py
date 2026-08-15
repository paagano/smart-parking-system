"""Create loyalty rewards and reward redemption tables.

Revision ID: 7c4e91b6a2d8
Revises: 2a747149bf94
Create Date: 2026-08-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ==========================================================
# Revision identifiers
# ==========================================================

revision: str = "7c4e91b6a2d8"
down_revision: Union[str, Sequence[str], None] = "2a747149bf94"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ==========================================================
# PostgreSQL Enum Definitions
# ==========================================================

# These objects are used ONLY to create/drop the PostgreSQL
# enum types themselves.

loyalty_reward_type_enum = postgresql.ENUM(
    "DISCOUNT",
    "FREE_PARKING",
    "COUPON",
    "VIP_BENEFIT",
    name="loyalty_reward_type",
)

loyalty_reward_status_enum = postgresql.ENUM(
    "ACTIVE",
    "INACTIVE",
    "EXPIRED",
    name="loyalty_reward_status",
)

reward_redemption_status_enum = postgresql.ENUM(
    "PENDING",
    "REDEEMED",
    "CANCELLED",
    name="reward_redemption_status",
)


# ==========================================================
# Upgrade
# ==========================================================

def upgrade() -> None:
    """
    Create loyalty reward catalogue and reward redemption
    tables.
    """

    bind = op.get_bind()

    # ======================================================
    # Create PostgreSQL Enum Types
    # ======================================================

    loyalty_reward_type_enum.create(
        bind,
        checkfirst=True,
    )

    loyalty_reward_status_enum.create(
        bind,
        checkfirst=True,
    )

    reward_redemption_status_enum.create(
        bind,
        checkfirst=True,
    )

    # ======================================================
    # Loyalty Rewards
    # ======================================================

    op.create_table(
        "loyalty_rewards",

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        sa.Column(
            "name",
            sa.String(length=150),
            nullable=False,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        # IMPORTANT:
        # create_type=False prevents SQLAlchemy from attempting
        # to create loyalty_reward_type again.
        sa.Column(
            "reward_type",
            postgresql.ENUM(
                "DISCOUNT",
                "FREE_PARKING",
                "COUPON",
                "VIP_BENEFIT",
                name="loyalty_reward_type",
                create_type=False,
            ),
            nullable=False,
        ),

        sa.Column(
            "points_cost",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "monetary_value",
            sa.Numeric(
                precision=12,
                scale=2,
            ),
            nullable=True,
        ),

        # IMPORTANT:
        # create_type=False prevents duplicate enum creation.
        sa.Column(
            "status",
            postgresql.ENUM(
                "ACTIVE",
                "INACTIVE",
                "EXPIRED",
                name="loyalty_reward_status",
                create_type=False,
            ),
            nullable=False,
            server_default="ACTIVE",
        ),

        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),

        # IMPORTANT:
        # loyalty_tier already exists from the previous Loyalty
        # migration. It must NEVER be recreated here.
        sa.Column(
            "minimum_tier",
            postgresql.ENUM(
                "BRONZE",
                "SILVER",
                "GOLD",
                "PLATINUM",
                name="loyalty_tier",
                create_type=False,
            ),
            nullable=True,
        ),

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

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.PrimaryKeyConstraint(
            "id",
        ),
    )

    # ======================================================
    # Loyalty Reward Indexes
    # ======================================================

    op.create_index(
        "ix_loyalty_rewards_reward_type",
        "loyalty_rewards",
        ["reward_type"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_rewards_status",
        "loyalty_rewards",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_rewards_minimum_tier",
        "loyalty_rewards",
        ["minimum_tier"],
        unique=False,
    )

    # ======================================================
    # Loyalty Reward Redemptions
    # ======================================================

    op.create_table(
        "loyalty_reward_redemptions",

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
            "reward_id",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "redemption_reference",
            sa.String(length=100),
            nullable=False,
        ),

        sa.Column(
            "points_spent",
            sa.Integer(),
            nullable=False,
        ),

        # IMPORTANT:
        # create_type=False prevents duplicate enum creation.
        sa.Column(
            "status",
            postgresql.ENUM(
                "PENDING",
                "REDEEMED",
                "CANCELLED",
                name="reward_redemption_status",
                create_type=False,
            ),
            nullable=False,
            server_default="REDEEMED",
        ),

        sa.Column(
            "used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),

        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.ForeignKeyConstraint(
            ["loyalty_account_id"],
            ["loyalty_accounts.id"],
            ondelete="CASCADE",
        ),

        sa.ForeignKeyConstraint(
            ["reward_id"],
            ["loyalty_rewards.id"],
            ondelete="RESTRICT",
        ),

        sa.PrimaryKeyConstraint(
            "id",
        ),

        sa.UniqueConstraint(
            "redemption_reference",
            name="uq_loyalty_reward_redemptions_reference",
        ),
    )

    # ======================================================
    # Redemption Indexes
    # ======================================================

    op.create_index(
        "ix_loyalty_reward_redemptions_loyalty_account_id",
        "loyalty_reward_redemptions",
        ["loyalty_account_id"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_reward_redemptions_reward_id",
        "loyalty_reward_redemptions",
        ["reward_id"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_reward_redemptions_redemption_reference",
        "loyalty_reward_redemptions",
        ["redemption_reference"],
        unique=True,
    )

    op.create_index(
        "ix_loyalty_reward_redemptions_status",
        "loyalty_reward_redemptions",
        ["status"],
        unique=False,
    )

    op.create_index(
        "ix_loyalty_reward_redemptions_expires_at",
        "loyalty_reward_redemptions",
        ["expires_at"],
        unique=False,
    )


# ==========================================================
# Downgrade
# ==========================================================

def downgrade() -> None:
    """
    Remove loyalty reward redemption and reward catalogue
    structures.
    """

    # ======================================================
    # Redemption Indexes
    # ======================================================

    op.drop_index(
        "ix_loyalty_reward_redemptions_expires_at",
        table_name="loyalty_reward_redemptions",
    )

    op.drop_index(
        "ix_loyalty_reward_redemptions_status",
        table_name="loyalty_reward_redemptions",
    )

    op.drop_index(
        "ix_loyalty_reward_redemptions_redemption_reference",
        table_name="loyalty_reward_redemptions",
    )

    op.drop_index(
        "ix_loyalty_reward_redemptions_reward_id",
        table_name="loyalty_reward_redemptions",
    )

    op.drop_index(
        "ix_loyalty_reward_redemptions_loyalty_account_id",
        table_name="loyalty_reward_redemptions",
    )

    # ======================================================
    # Redemption Table
    # ======================================================

    op.drop_table(
        "loyalty_reward_redemptions",
    )

    # ======================================================
    # Reward Indexes
    # ======================================================

    op.drop_index(
        "ix_loyalty_rewards_minimum_tier",
        table_name="loyalty_rewards",
    )

    op.drop_index(
        "ix_loyalty_rewards_status",
        table_name="loyalty_rewards",
    )

    op.drop_index(
        "ix_loyalty_rewards_reward_type",
        table_name="loyalty_rewards",
    )

    # ======================================================
    # Reward Table
    # ======================================================

    op.drop_table(
        "loyalty_rewards",
    )

    # ======================================================
    # PostgreSQL Enum Types
    # ======================================================

    reward_redemption_status_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )

    loyalty_reward_status_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )

    loyalty_reward_type_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )