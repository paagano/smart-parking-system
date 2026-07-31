"""
sync parking facility schema

Revision ID: 89a7829c591e
Revises: 3d4c1ea2f514
Create Date: 2026-07-26 23:37:28.798516
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "89a7829c591e"
down_revision: Union[str, Sequence[str], None] = "3d4c1ea2f514"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


facility_type_enum = postgresql.ENUM(
    "SHOPPING_MALL",
    "UNIVERSITY",
    "OFFICE",
    "AIRPORT",
    "HOSPITAL",
    "HOTEL",
    "RESIDENTIAL",
    "MUNICIPAL",
    "STADIUM",
    "TRANSPORT_HUB",
    "INDUSTRIAL",
    "PUBLIC",
    "OTHER",
    name="facility_type",
)


def upgrade() -> None:
    """Upgrade schema."""

    bind = op.get_bind()

    facility_type_enum.create(bind, checkfirst=True)

    op.execute(
        """
        ALTER TABLE parking_facilities
        ALTER COLUMN facility_type
        TYPE facility_type
        USING facility_type::facility_type;
        """
    )

    op.alter_column(
        "parking_facilities",
        "code",
        existing_type=sa.VARCHAR(length=30),
        comment=None,
        existing_comment="Unique business identifier for the parking facility.",
        existing_nullable=False,
    )

    op.alter_column(
        "parking_facilities",
        "facility_type",
        existing_type=sa.VARCHAR(length=13),
        type_=postgresql.ENUM(
            "SHOPPING_MALL",
            "UNIVERSITY",
            "OFFICE",
            "AIRPORT",
            "HOSPITAL",
            "HOTEL",
            "RESIDENTIAL",
            "MUNICIPAL",
            "STADIUM",
            "TRANSPORT_HUB",
            "INDUSTRIAL",
            "PUBLIC",
            "OTHER",
            name="facility_type",
            create_type=False,
        ),
        comment=None,
        existing_comment="Business classification of the parking facility.",
        existing_nullable=False,
    )

    op.alter_column(
        "parking_facilities",
        "address",
        existing_type=sa.VARCHAR(length=255),
        nullable=True,
        comment=None,
        existing_comment="Physical street address.",
    )

    op.alter_column(
        "parking_facilities",
        "city",
        existing_type=sa.VARCHAR(length=100),
        nullable=True,
        comment=None,
        existing_comment="City where the parking facility is located.",
    )

    op.alter_column(
        "parking_facilities",
        "county",
        existing_type=sa.VARCHAR(length=100),
        nullable=True,
        comment=None,
        existing_comment="County where the parking facility is located.",
    )

    op.alter_column(
        "parking_facilities",
        "country",
        existing_type=sa.VARCHAR(length=100),
        comment=None,
        existing_comment="Country where the parking facility is located.",
        existing_nullable=False,
    )

    op.alter_column(
        "parking_facilities",
        "latitude",
        existing_type=sa.NUMERIC(precision=9, scale=6),
        type_=sa.Float(),
        nullable=True,
        comment=None,
        existing_comment="Latitude in decimal degrees.",
    )

    op.alter_column(
        "parking_facilities",
        "longitude",
        existing_type=sa.NUMERIC(precision=9, scale=6),
        type_=sa.Float(),
        nullable=True,
        comment=None,
        existing_comment="Longitude in decimal degrees.",
    )

    op.alter_column(
        "parking_facilities",
        "description",
        existing_type=sa.TEXT(),
        comment=None,
        existing_comment="Optional description of the parking facility.",
        existing_nullable=True,
    )

    op.alter_column(
        "parking_facilities",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment=None,
        existing_comment="Indicates whether the facility is operational.",
        existing_nullable=False,
    )

    op.drop_index(
        op.f("ix_parking_facility_code"),
        table_name="parking_facilities",
    )

    op.drop_index(
        op.f("ix_parking_facility_name"),
        table_name="parking_facilities",
    )

    op.create_index(
        op.f("ix_parking_facilities_code"),
        "parking_facilities",
        ["code"],
        unique=True,
    )

    op.create_index(
        op.f("ix_parking_facilities_name"),
        "parking_facilities",
        ["name"],
        unique=True,
    )

    op.drop_column("parking_facilities", "postal_code")
    op.drop_column("parking_facilities", "closing_time")
    op.drop_column("parking_facilities", "timezone")
    op.drop_column("parking_facilities", "opening_time")


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index(
        op.f("ix_parking_zones_id"),
        table_name="parking_zones",
    )

    op.add_column(
        "parking_facilities",
        sa.Column(
            "opening_time",
            postgresql.TIME(),
            nullable=False,
            comment="Daily opening time.",
        ),
    )

    op.add_column(
        "parking_facilities",
        sa.Column(
            "timezone",
            sa.VARCHAR(length=50),
            nullable=False,
            comment="IANA timezone.",
        ),
    )

    op.add_column(
        "parking_facilities",
        sa.Column(
            "closing_time",
            postgresql.TIME(),
            nullable=False,
            comment="Daily closing time.",
        ),
    )

    op.add_column(
        "parking_facilities",
        sa.Column(
            "postal_code",
            sa.VARCHAR(length=20),
            nullable=True,
            comment="Postal code.",
        ),
    )

    op.drop_index(
        op.f("ix_parking_facilities_name"),
        table_name="parking_facilities",
    )

    op.drop_index(
        op.f("ix_parking_facilities_code"),
        table_name="parking_facilities",
    )

    op.create_index(
        op.f("ix_parking_facility_name"),
        "parking_facilities",
        ["name"],
        unique=False,
    )

    op.create_index(
        op.f("ix_parking_facility_code"),
        "parking_facilities",
        ["code"],
        unique=True,
    )

    op.alter_column(
        "parking_facilities",
        "is_active",
        existing_type=sa.BOOLEAN(),
        comment="Indicates whether the facility is operational.",
        existing_nullable=False,
    )

    op.alter_column(
        "parking_facilities",
        "description",
        existing_type=sa.TEXT(),
        comment="Optional description of the parking facility.",
        existing_nullable=True,
    )

    op.alter_column(
        "parking_facilities",
        "longitude",
        existing_type=sa.Float(),
        type_=sa.NUMERIC(precision=9, scale=6),
        nullable=False,
        comment="Longitude in decimal degrees.",
    )

    op.alter_column(
        "parking_facilities",
        "latitude",
        existing_type=sa.Float(),
        type_=sa.NUMERIC(precision=9, scale=6),
        nullable=False,
        comment="Latitude in decimal degrees.",
    )

    op.alter_column(
        "parking_facilities",
        "country",
        existing_type=sa.VARCHAR(length=100),
        comment="Country where the parking facility is located.",
        existing_nullable=False,
    )

    op.alter_column(
        "parking_facilities",
        "county",
        existing_type=sa.VARCHAR(length=100),
        nullable=False,
        comment="County where the parking facility is located.",
    )

    op.alter_column(
        "parking_facilities",
        "city",
        existing_type=sa.VARCHAR(length=100),
        nullable=False,
        comment="City where the parking facility is located.",
    )

    op.alter_column(
        "parking_facilities",
        "address",
        existing_type=sa.VARCHAR(length=255),
        nullable=False,
        comment="Physical street address.",
    )

    op.alter_column(
        "parking_facilities",
        "facility_type",
        existing_type=postgresql.ENUM(
            "SHOPPING_MALL",
            "UNIVERSITY",
            "OFFICE",
            "AIRPORT",
            "HOSPITAL",
            "HOTEL",
            "RESIDENTIAL",
            "MUNICIPAL",
            "STADIUM",
            "TRANSPORT_HUB",
            "INDUSTRIAL",
            "PUBLIC",
            "OTHER",
            name="facility_type",
        ),
        type_=sa.VARCHAR(length=13),
        comment="Business classification of the parking facility.",
        existing_nullable=False,
    )

    op.alter_column(
        "parking_facilities",
        "code",
        existing_type=sa.VARCHAR(length=30),
        comment="Unique business identifier for the parking facility.",
        existing_nullable=False,
    )

    op.alter_column(
        "parking_facilities",
        "name",
        existing_type=sa.VARCHAR(length=150),
        comment="Display name of the parking facility.",
        existing_nullable=False,
    )

    facility_type_enum.drop(
        op.get_bind(),
        checkfirst=True,
    )