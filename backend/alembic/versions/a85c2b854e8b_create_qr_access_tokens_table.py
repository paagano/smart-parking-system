"""create qr access tokens table

Revision ID: a85c2b854e8b
Revises: a9b2086b1a4c
Create Date: 2026-10-03 21:36:06.029637

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a85c2b854e8b"
down_revision: Union[str, Sequence[str], None] = "a9b2086b1a4c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the QR access tokens table."""

    op.create_table(
        "qr_access_tokens",
        sa.Column(
            "token_hash",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column(
            "facility_id",
            sa.Integer(),
            nullable=False,
        ),
        sa.Column(
            "purpose",
            sa.Enum(
                "ENTRY",
                "EXIT",
                name="qr_access_purpose",
            ),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
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
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["parking_facilities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "ix_qr_access_tokens_id",
        "qr_access_tokens",
        ["id"],
        unique=False,
    )

    op.create_index(
        "ix_qr_access_tokens_token_hash",
        "qr_access_tokens",
        ["token_hash"],
        unique=True,
    )

    op.create_index(
        "ix_qr_access_tokens_facility_id",
        "qr_access_tokens",
        ["facility_id"],
        unique=False,
    )

    op.create_index(
        "ix_qr_access_tokens_purpose",
        "qr_access_tokens",
        ["purpose"],
        unique=False,
    )

    op.create_index(
        "ix_qr_access_tokens_expires_at",
        "qr_access_tokens",
        ["expires_at"],
        unique=False,
    )

    op.create_index(
        "ix_qr_access_tokens_is_active",
        "qr_access_tokens",
        ["is_active"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the QR access tokens table."""

    op.drop_index(
        "ix_qr_access_tokens_is_active",
        table_name="qr_access_tokens",
    )

    op.drop_index(
        "ix_qr_access_tokens_expires_at",
        table_name="qr_access_tokens",
    )

    op.drop_index(
        "ix_qr_access_tokens_purpose",
        table_name="qr_access_tokens",
    )

    op.drop_index(
        "ix_qr_access_tokens_facility_id",
        table_name="qr_access_tokens",
    )

    op.drop_index(
        "ix_qr_access_tokens_token_hash",
        table_name="qr_access_tokens",
    )

    op.drop_index(
        "ix_qr_access_tokens_id",
        table_name="qr_access_tokens",
    )

    op.drop_table("qr_access_tokens")