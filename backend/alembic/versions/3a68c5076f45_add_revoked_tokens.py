"""add revoked tokens

Revision ID: 3a68c5076f45
Revises: 80c475517a4b
Create Date: 2026-09-04
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# ============================================================
# Revision identifiers
# ============================================================

revision: str = "3a68c5076f45"
down_revision: Union[str, Sequence[str], None] = "80c475517a4b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ============================================================
# Upgrade
# ============================================================

def upgrade() -> None:
    """
    Create the revoked_tokens table.
    """

    op.create_table(
        "revoked_tokens",

        # ----------------------------------------------------
        # Primary key
        # ----------------------------------------------------

        sa.Column(
            "id",
            sa.Integer(),
            autoincrement=True,
            nullable=False,
        ),

        # ----------------------------------------------------
        # JWT identifier
        # ----------------------------------------------------

        sa.Column(
            "jti",
            sa.String(length=255),
            nullable=False,
        ),

        # ----------------------------------------------------
        # Token expiration
        # ----------------------------------------------------

        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        # ----------------------------------------------------
        # Audit timestamps
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # Primary key
        # ----------------------------------------------------

        sa.PrimaryKeyConstraint(
            "id",
        ),

        # ----------------------------------------------------
        # Prevent duplicate revoked JWT identifiers
        # ----------------------------------------------------

        sa.UniqueConstraint(
            "jti",
            name="uq_revoked_tokens_jti",
        ),
    )

    # --------------------------------------------------------
    # Query index
    # --------------------------------------------------------

    op.create_index(
        "ix_revoked_tokens_jti",
        "revoked_tokens",
        ["jti"],
        unique=False,
    )

    # --------------------------------------------------------
    # Expiration index
    #
    # This will support future cleanup of expired revoked
    # token records.
    # --------------------------------------------------------

    op.create_index(
        "ix_revoked_tokens_expires_at",
        "revoked_tokens",
        ["expires_at"],
        unique=False,
    )


# ============================================================
# Downgrade
# ============================================================

def downgrade() -> None:
    """
    Remove the revoked_tokens table.
    """

    op.drop_index(
        "ix_revoked_tokens_expires_at",
        table_name="revoked_tokens",
    )

    op.drop_index(
        "ix_revoked_tokens_jti",
        table_name="revoked_tokens",
    )

    op.drop_table(
        "revoked_tokens",
    )