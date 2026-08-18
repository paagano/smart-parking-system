"""add occupancy observations

Revision ID: 80c475517a4b
Revises: a26f0aceebcb
Create Date: 2026-08-18 22:26:12.319087

Creates the canonical occupancy observation time-series table
used by the SmartPark AI / ML module.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# ============================================================
# Revision identifiers
# ============================================================

revision: str = "80c475517a4b"
down_revision: Union[str, Sequence[str], None] = "a26f0aceebcb"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ============================================================
# PostgreSQL ENUM definitions
# ============================================================

# create_type=False is intentional.
#
# The migration explicitly creates these ENUM types in upgrade()
# before creating the table. This prevents SQLAlchemy from trying
# to create the same PostgreSQL ENUM again during create_table().
#
occupancy_observation_source_enum = postgresql.ENUM(
    "BIRMINGHAM",
    "SMARTPARK",
    "SIMULATED",
    "SENSOR",
    "API",
    name="occupancy_observation_source",
    create_type=False,
)

occupancy_quality_status_enum = postgresql.ENUM(
    "VALID",
    "SUSPECT",
    "INVALID",
    name="occupancy_quality_status",
    create_type=False,
)


# ============================================================
# Upgrade
# ============================================================


def upgrade() -> None:
    """Create the occupancy observations table and supporting objects."""

    bind = op.get_bind()

    # --------------------------------------------------------
    # Create PostgreSQL ENUM types explicitly.
    # --------------------------------------------------------

    occupancy_observation_source_enum.create(
        bind,
        checkfirst=True,
    )

    occupancy_quality_status_enum.create(
        bind,
        checkfirst=True,
    )

    # --------------------------------------------------------
    # Create occupancy_observations
    # --------------------------------------------------------

    op.create_table(
        "occupancy_observations",

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
        # Facility relationship
        # ----------------------------------------------------

        sa.Column(
            "facility_id",
            sa.Integer(),
            nullable=False,
        ),

        # ----------------------------------------------------
        # Observation timestamp
        # ----------------------------------------------------

        sa.Column(
            "observed_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        # ----------------------------------------------------
        # Occupancy measurements
        # ----------------------------------------------------

        sa.Column(
            "total_spaces",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "occupied_spaces",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "available_spaces",
            sa.Integer(),
            nullable=False,
        ),

        sa.Column(
            "occupancy_rate",
            sa.Numeric(
                precision=5,
                scale=4,
            ),
            nullable=False,
        ),

        # ----------------------------------------------------
        # Data provenance
        # ----------------------------------------------------

        sa.Column(
            "source",
            occupancy_observation_source_enum,
            nullable=False,
        ),

        # ----------------------------------------------------
        # Data quality
        # ----------------------------------------------------

        sa.Column(
            "quality_status",
            occupancy_quality_status_enum,
            nullable=False,
            server_default=sa.text(
                "'VALID'::occupancy_quality_status"
            ),
        ),

        sa.Column(
            "quality_flags",
            postgresql.JSONB(),
            nullable=True,
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
            name="pk_occupancy_observations",
        ),

        # ----------------------------------------------------
        # Facility foreign key
        # ----------------------------------------------------

        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["parking_facilities.id"],
            name="fk_occupancy_observations_facility_id",
            ondelete="RESTRICT",
        ),

        # ----------------------------------------------------
        # Prevent duplicate observations for the same
        # facility at the same point in time.
        # ----------------------------------------------------

        sa.UniqueConstraint(
            "facility_id",
            "observed_at",
            name="uq_occupancy_observation_facility_time",
        ),

        # ----------------------------------------------------
        # Data integrity constraints
        # ----------------------------------------------------

        sa.CheckConstraint(
            "total_spaces > 0",
            name="ck_occupancy_observation_total_spaces_positive",
        ),

        sa.CheckConstraint(
            "occupied_spaces >= 0",
            name="ck_occupancy_observation_occupied_non_negative",
        ),

        sa.CheckConstraint(
            "available_spaces >= 0",
            name="ck_occupancy_observation_available_non_negative",
        ),

        sa.CheckConstraint(
            "occupied_spaces + available_spaces = total_spaces",
            name="ck_occupancy_observation_space_balance",
        ),

        sa.CheckConstraint(
            "occupancy_rate >= 0 AND occupancy_rate <= 1",
            name="ck_occupancy_observation_rate_range",
        ),
    )

    # --------------------------------------------------------
    # ML query indexes
    # --------------------------------------------------------

    # Primary time-series access pattern:
    #
    # WHERE facility_id = ?
    # ORDER BY observed_at
    #
    op.create_index(
        "ix_occupancy_observation_facility_time",
        "occupancy_observations",
        ["facility_id", "observed_at"],
        unique=False,
    )

    # Cross-facility time-range queries.
    op.create_index(
        "ix_occupancy_observation_observed_at",
        "occupancy_observations",
        ["observed_at"],
        unique=False,
    )


# ============================================================
# Downgrade
# ============================================================


def downgrade() -> None:
    """Remove the occupancy observations table and ENUM types."""

    bind = op.get_bind()

    # --------------------------------------------------------
    # Drop indexes
    # --------------------------------------------------------

    op.drop_index(
        "ix_occupancy_observation_observed_at",
        table_name="occupancy_observations",
    )

    op.drop_index(
        "ix_occupancy_observation_facility_time",
        table_name="occupancy_observations",
    )

    # --------------------------------------------------------
    # Drop table
    # --------------------------------------------------------

    op.drop_table("occupancy_observations")

    # --------------------------------------------------------
    # Drop PostgreSQL ENUM types
    # --------------------------------------------------------

    occupancy_quality_status_enum.drop(
        bind,
        checkfirst=True,
    )

    occupancy_observation_source_enum.drop(
        bind,
        checkfirst=True,
    )