"""
SmartPark AI - Production Occupancy Observation Ingestion.

Purpose
-------
Backfill canonical Birmingham parking observations into the
SmartPark operational PostgreSQL table:

    occupancy_observations

This module is part of the PRODUCTION ML runtime layer.

Important architectural distinction
------------------------------------

Training / development:

    Birmingham raw dataset
            |
            v
    app.ml.data.sources.local
            |
            v
    ML data engineering
            |
            v
    Feature engineering
            |
            v
    XGBoost / LSTM / Baseline

Production:

    Birmingham / operational observations
            |
            v
    occupancy_observations
            |
            v
    Production feature builder
            |
            v
    Frozen production model
            |
            v
    Prediction API

This module does NOT:

- train XGBoost
- tune hyperparameters
- rebuild the XGBoost model
- modify the frozen model artifact
- create ML features
- create forecast targets
- load train.parquet
- load validation.parquet
- load test.parquet

It only creates canonical occupancy observations.

Birmingham source
-----------------

The existing temporal normalization pipeline is reused so that
production observation ingestion uses the same canonical temporal
semantics already established by the ML pipeline.

Only rows where:

    observation_present == True

are persisted.

Missing normalized time slots are intentionally NOT persisted
as occupancy observations.

Capacity-exceeded observations
------------------------------

The Birmingham source can contain observations where:

    occupied_spaces > total_spaces

which results in:

    available_spaces < 0

These observations are retained because they represent real source
observations, but they cannot be persisted directly because the
canonical occupancy_observations table requires:

    available_spaces >= 0

Therefore capacity-exceeded observations are normalized as follows:

    available_spaces -> 0

    occupancy_rate ->
        occupied_spaces / total_spaces
        capped to [0, 1]

and are marked:

    quality_status = SUSPECT

The original anomaly is preserved in quality_flags, including:

- source_available_spaces
- capacity_excess_spaces
- source_total_spaces
- source_occupied_spaces
- CAPACITY_EXCEEDED = True

This means the production database remains structurally valid while
retaining the provenance of the source anomaly.

Idempotency
-----------

The occupancy_observations table enforces:

    facility_id + observed_at

as a unique key.

This module uses PostgreSQL ON CONFLICT DO UPDATE so that:

- the ingestion can safely be rerun
- duplicate observations are not created
- corrected source values can refresh an existing observation

Facility mapping
----------------

Birmingham's:

    source_facility_code

must correspond to an existing:

    parking_facilities.code

The ingestion deliberately does NOT silently create parking
facilities. Facility master-data creation belongs to the
facility-management/domain layer, not ML ingestion.

If one or more Birmingham facility codes are missing from
parking_facilities, the ingestion stops before writing any
observations.

Usage
-----

From:

    backend/

Dry run:

    python -m app.ml.production.observation_ingestion --dry-run

Actual ingestion:

    python -m app.ml.production.observation_ingestion

Optional dataset root:

    python -m app.ml.production.observation_ingestion \
        --dataset-root ../datasets/raw

The script is intentionally executable as a module so that
imports resolve consistently from the backend package.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal
from app.models.enums import (
    OccupancyObservationSource,
    OccupancyQualityStatus,
)
from app.models.occupancy_observation import (
    OccupancyObservation,
)
from app.models.parking_facility import ParkingFacility


# ============================================================================
# Constants
# ============================================================================

TARGET_SOURCE = "BIRMINGHAM"

REQUIRED_COLUMNS: tuple[str, ...] = (
    "source_facility_code",
    "normalized_at",
    "source_observed_at",
    "total_spaces",
    "occupied_spaces",
    "available_spaces",
    "occupancy_rate",
    "observation_present",
    "source",
    "quality_flags",
    "quality_status",
)

BATCH_SIZE = 1_000

DEFAULT_DATASET_ROOT = (
    Path(__file__).resolve().parents[4]
    / "datasets"
    / "raw"
)


# ============================================================================
# Exceptions
# ============================================================================


class ObservationIngestionError(Exception):
    """Base exception for production observation ingestion."""


class ObservationSchemaError(
    ObservationIngestionError
):
    """Raised when the normalized observation schema is invalid."""


class ObservationDataError(
    ObservationIngestionError
):
    """Raised when observation data violates production rules."""


class FacilityMappingError(
    ObservationIngestionError
):
    """Raised when source facility codes cannot be mapped."""


# ============================================================================
# Result
# ============================================================================


@dataclass(slots=True)
class ObservationIngestionResult:
    """Summary of an observation ingestion run."""

    source_rows: int
    normalized_rows: int
    observed_rows: int
    skipped_missing_rows: int
    capacity_exceeded_rows: int
    facility_count: int
    inserted_or_updated: int
    dry_run: bool
    started_at: str
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_rows": self.source_rows,
            "normalized_rows": self.normalized_rows,
            "observed_rows": self.observed_rows,
            "skipped_missing_rows": (
                self.skipped_missing_rows
            ),
            "capacity_exceeded_rows": (
                self.capacity_exceeded_rows
            ),
            "facility_count": self.facility_count,
            "inserted_or_updated": (
                self.inserted_or_updated
            ),
            "dry_run": self.dry_run,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


# ============================================================================
# Console helpers
# ============================================================================


def print_header() -> None:
    print()
    print("=" * 78)
    print(
        "SMARTPARK AI - PRODUCTION OCCUPANCY "
        "OBSERVATION INGESTION"
    )
    print("=" * 78)
    print()

    print("Purpose:")
    print(
        "  Backfill canonical Birmingham observations "
        "into occupancy_observations."
    )

    print()
    print("Production flow:")
    print(
        "  Birmingham observations"
        " -> occupancy_observations"
        " -> production features"
        " -> frozen XGBoost"
    )

    print()
    print("Model:")
    print("  Frozen TUNE_014")
    print("  Target: target_occupancy_rate_30m")
    print("  Forecast horizon: T + 30 minutes")
    print()


def print_section(title: str) -> None:
    print()
    print("--- " + title + " ---")


def print_status(
    label: str,
    value: Any,
) -> None:
    print(
        f"{label:<48}: {value}"
    )


# ============================================================================
# Dataset loading
# ============================================================================


def load_birmingham_observations(
    dataset_root: Path,
) -> pd.DataFrame:
    """
    Run the existing Birmingham temporal normalization pipeline.

    This deliberately reuses the existing ML data engineering
    implementation rather than duplicating Birmingham parsing logic.
    """

    print_section(
        "LOADING BIRMINGHAM NORMALIZED OBSERVATIONS"
    )

    print_status(
        "Dataset root",
        dataset_root,
    )

    if not dataset_root.exists():
        raise FileNotFoundError(
            f"Dataset root does not exist: {dataset_root}"
        )

    try:
        from app.ml.data.temporal_normalizer import (
            normalize_birmingham_temporal,
        )
    except ImportError as exc:
        raise ObservationIngestionError(
            "Unable to import the existing Birmingham "
            "temporal normalizer."
        ) from exc

    result = normalize_birmingham_temporal(
        dataset_root=dataset_root,
    )

    dataframe = result.dataframe

    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):
        raise ObservationIngestionError(
            "Birmingham temporal normalizer did not "
            "return a pandas DataFrame."
        )

    print_status(
        "Normalized rows",
        f"{len(dataframe):,}",
    )

    if hasattr(
        result,
        "statistics",
    ):
        statistics = result.statistics

        for attribute in (
            "source_row_count",
            "normalized_row_count",
            "observed_slots",
            "missing_slots",
            "duplicate_source_slots",
        ):
            if hasattr(
                statistics,
                attribute,
            ):
                print_status(
                    attribute,
                    f"{getattr(statistics, attribute):,}",
                )

    return dataframe


# ============================================================================
# Schema validation
# ============================================================================


def validate_schema(
    dataframe: pd.DataFrame,
) -> None:
    """
    Validate that the normalized dataset contains all columns
    required to populate occupancy_observations.
    """

    print_section(
        "VALIDATING OBSERVATION SCHEMA"
    )

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in dataframe.columns
    ]

    if missing:
        raise ObservationSchemaError(
            "Missing required normalized observation "
            f"columns: {missing}"
        )

    duplicate_columns = (
        dataframe.columns[
            dataframe.columns.duplicated()
        ]
        .tolist()
    )

    if duplicate_columns:
        raise ObservationSchemaError(
            "Duplicate dataframe columns detected: "
            f"{duplicate_columns}"
        )

    print_status(
        "Required columns",
        len(REQUIRED_COLUMNS),
    )

    print_status(
        "Schema validation",
        "PASS",
    )


# ============================================================================
# Observation filtering
# ============================================================================


def select_real_observations(
    dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    """
    Select only actual observations.

    Missing normalized slots are not database observations.
    """

    print_section(
        "SELECTING REAL OBSERVATIONS"
    )

    presence = (
        dataframe["observation_present"]
        .fillna(False)
        .astype(bool)
    )

    observed = (
        dataframe.loc[presence]
        .copy()
    )

    skipped = int(
        len(dataframe)
        - len(observed)
    )

    print_status(
        "Normalized rows",
        f"{len(dataframe):,}",
    )

    print_status(
        "Actual observations",
        f"{len(observed):,}",
    )

    print_status(
        "Missing normalized slots skipped",
        f"{skipped:,}",
    )

    if observed.empty:
        raise ObservationDataError(
            "No real observations were found "
            "after filtering observation_present=True."
        )

    return observed, skipped


# ============================================================================
# Quality mapping
# ============================================================================


def map_quality_status(
    value: Any,
) -> OccupancyQualityStatus:
    """
    Convert ML temporal-normalizer quality states into
    the database quality contract.

    Current Birmingham normalizer state:

        CLEAN

    maps to:

        VALID

    Any non-clean observed state is conservatively mapped
    to SUSPECT rather than silently marked VALID.
    """

    if value is None:
        return OccupancyQualityStatus.SUSPECT

    normalized = str(value).strip().upper()

    if normalized == "CLEAN":
        return OccupancyQualityStatus.VALID

    if normalized in {
        "VALID",
        "OK",
        "PASS",
    }:
        return OccupancyQualityStatus.VALID

    if normalized in {
        "INVALID",
        "ERROR",
        "FAILED",
    }:
        return OccupancyQualityStatus.INVALID

    return OccupancyQualityStatus.SUSPECT


# ============================================================================
# JSON-safe quality flags
# ============================================================================


def normalize_quality_flags(
    value: Any,
) -> dict[str, Any] | None:
    """
    Convert the normalizer's quality flags into JSONB-safe data.
    """

    if value is None:
        return None

    if isinstance(
        value,
        dict,
    ):
        return value

    if isinstance(
        value,
        (list, tuple, set),
    ):
        return {
            "flags": [
                str(item)
                for item in value
            ]
        }

    if isinstance(
        value,
        str,
    ):
        value = value.strip()

        if not value:
            return None

        try:
            parsed = json.loads(
                value
            )

            if isinstance(
                parsed,
                dict,
            ):
                return parsed

            return {
                "flags": parsed
            }

        except json.JSONDecodeError:
            return {
                "flags": [value]
            }

    return {
        "value": str(value)
    }


# ============================================================================
# Capacity-exceeded normalization
# ============================================================================


def normalize_capacity_exceeded_observations(
    dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, int]:
    """
    Normalize observations where occupied spaces exceed capacity.

    Birmingham can contain observations such as:

        total_spaces     = 387
        occupied_spaces  = 403
        available_spaces = -16

    These are retained because they are real source observations.

    However, the canonical occupancy_observations database contract
    requires:

        available_spaces >= 0

    Therefore the production representation becomes:

        available_spaces = 0

    and:

        occupancy_rate =
            occupied_spaces / total_spaces

    capped to [0, 1].

    The observation is marked SUSPECT and the original anomaly is
    preserved in quality_flags.

    The source dataset is never modified.
    """

    print_section(
        "NORMALIZING CAPACITY-EXCEEDED OBSERVATIONS"
    )

    normalized = dataframe.copy()

    numeric_total = pd.to_numeric(
        normalized["total_spaces"],
        errors="coerce",
    )

    numeric_occupied = pd.to_numeric(
        normalized["occupied_spaces"],
        errors="coerce",
    )

    numeric_available = pd.to_numeric(
        normalized["available_spaces"],
        errors="coerce",
    )

    capacity_exceeded = (
        (
            numeric_available < 0
        )
        | (
            numeric_occupied > numeric_total
        )
    )

    exceeded_count = int(
        capacity_exceeded.sum()
    )

    print_status(
        "Capacity-exceeded observations",
        f"{exceeded_count:,}",
    )

    if exceeded_count == 0:
        print_status(
            "Capacity-exceeded normalization",
            "NOT REQUIRED",
        )

        return normalized, 0

    for index in normalized.index[
        capacity_exceeded
    ]:
        original_available = int(
            numeric_available.loc[index]
        )

        total_spaces = int(
            numeric_total.loc[index]
        )

        occupied_spaces = int(
            numeric_occupied.loc[index]
        )

        excess_spaces = max(
            occupied_spaces
            - total_spaces,
            0,
        )

        existing_flags = normalize_quality_flags(
            normalized.at[
                index,
                "quality_flags",
            ]
        )

        flags = dict(
            existing_flags
            or {}
        )

        flags[
            "CAPACITY_EXCEEDED"
        ] = True

        flags[
            "source_available_spaces"
        ] = original_available

        flags[
            "capacity_excess_spaces"
        ] = excess_spaces

        flags[
            "source_total_spaces"
        ] = total_spaces

        flags[
            "source_occupied_spaces"
        ] = occupied_spaces

        # --------------------------------------------------------------
        # Canonical production representation
        # --------------------------------------------------------------
        #
        # The source has reported more occupied spaces than the
        # physical capacity. The canonical observation table requires:
        #
        #     occupied_spaces + available_spaces = total_spaces
        #
        # Therefore we cap occupied_spaces at total capacity and set
        # available_spaces to zero.
        #
        # The ORIGINAL source values are retained in quality_flags
        # above so that the anomaly remains completely auditable.
        # --------------------------------------------------------------

        canonical_occupied_spaces = min(
            occupied_spaces,
            total_spaces,
        )

        canonical_available_spaces = (
            total_spaces
            - canonical_occupied_spaces
        )

        normalized.at[
            index,
            "occupied_spaces"
        ] = canonical_occupied_spaces

        normalized.at[
            index,
            "available_spaces"
        ] = canonical_available_spaces

        normalized.at[
            index,
            "occupancy_rate"
        ] = (
            canonical_occupied_spaces
            / total_spaces
        )

        normalized.at[
            index,
            "quality_status"
        ] = "SUSPECT"

        normalized.at[
            index,
            "quality_flags"
        ] = flags

    print_status(
        "Available spaces normalized",
        f"{exceeded_count:,}",
    )

    print_status(
        "Capacity-exceeded status",
        "SUSPECT",
    )

    print_status(
        "Original anomaly preserved",
        "YES",
    )

    print_status(
        "Source dataset modified",
        "NO",
    )

    return normalized, exceeded_count


# ============================================================================
# Data validation
# ============================================================================


def validate_observation_values(
    dataframe: pd.DataFrame,
) -> None:
    """
    Validate the final production representation before database
    persistence.

    Capacity-exceeded Birmingham records should already have been
    normalized by normalize_capacity_exceeded_observations().

    Database constraints remain the final authority.
    """

    print_section(
        "VALIDATING OBSERVATION VALUES"
    )

    errors: list[str] = []

    # ------------------------------------------------------------------
    # Required non-null fields.
    # ------------------------------------------------------------------

    required_non_null = (
        "source_facility_code",
        "normalized_at",
        "total_spaces",
        "occupied_spaces",
        "available_spaces",
        "occupancy_rate",
    )

    for column in required_non_null:
        null_count = int(
            dataframe[column].isna().sum()
        )

        if null_count:
            errors.append(
                f"{column} contains "
                f"{null_count:,} null values."
            )

    # ------------------------------------------------------------------
    # Numeric conversion.
    # ------------------------------------------------------------------

    numeric_columns = (
        "total_spaces",
        "occupied_spaces",
        "available_spaces",
        "occupancy_rate",
    )

    numeric = dataframe.copy()

    for column in numeric_columns:
        numeric[column] = pd.to_numeric(
            numeric[column],
            errors="coerce",
        )

    # ------------------------------------------------------------------
    # Detect numeric conversion failures.
    # ------------------------------------------------------------------

    for column in numeric_columns:
        if numeric[column].isna().any():
            errors.append(
                f"{column} contains values that "
                "cannot be converted to numeric."
            )

    # ------------------------------------------------------------------
    # Capacity.
    # ------------------------------------------------------------------

    invalid_capacity = (
        numeric["total_spaces"] <= 0
    )

    if invalid_capacity.any():
        errors.append(
            "One or more observations have "
            "total_spaces <= 0."
        )

    # ------------------------------------------------------------------
    # Occupied.
    # ------------------------------------------------------------------

    invalid_occupied = (
        numeric["occupied_spaces"] < 0
    )

    if invalid_occupied.any():
        errors.append(
            "One or more observations have "
            "occupied_spaces < 0."
        )

    # ------------------------------------------------------------------
    # Available.
    #
    # This is intentionally retained as a hard assertion.
    #
    # Capacity-exceeded records should already have been normalized
    # before this function is called.
    # ------------------------------------------------------------------

    invalid_available = (
        numeric["available_spaces"] < 0
    )

    if invalid_available.any():
        errors.append(
            "One or more observations still have "
            "available_spaces < 0 after capacity-exceeded "
            "normalization."
        )

    # ------------------------------------------------------------------
    # Capacity balance.
    # ------------------------------------------------------------------

    balance_difference = (
        numeric["occupied_spaces"]
        + numeric["available_spaces"]
        - numeric["total_spaces"]
    )

    invalid_balance = (
        balance_difference.abs()
        > 0
    )

    if invalid_balance.any():
        errors.append(
            "One or more observations violate "
            "occupied_spaces + available_spaces = "
            "total_spaces."
        )

    # ------------------------------------------------------------------
    # Occupancy rate.
    # ------------------------------------------------------------------

    invalid_rate = (
        (numeric["occupancy_rate"] < 0)
        | (numeric["occupancy_rate"] > 1)
    )

    if invalid_rate.any():
        errors.append(
            "One or more observations have "
            "occupancy_rate outside [0, 1]."
        )

    # ------------------------------------------------------------------
    # Timestamp.
    # ------------------------------------------------------------------

    timestamps = pd.to_datetime(
        dataframe["normalized_at"],
        errors="coerce",
    )

    if timestamps.isna().any():
        errors.append(
            "One or more observations have "
            "invalid normalized_at timestamps."
        )

    # ------------------------------------------------------------------
    # Facility code.
    # ------------------------------------------------------------------

    facility_codes = (
        dataframe["source_facility_code"]
        .astype("string")
        .str.strip()
    )

    if facility_codes.isna().any():
        errors.append(
            "One or more observations have "
            "missing source facility codes."
        )

    if (
        facility_codes
        .eq("")
        .any()
    ):
        errors.append(
            "One or more observations have "
            "empty source facility codes."
        )

    # ------------------------------------------------------------------
    # Final validation result.
    # ------------------------------------------------------------------

    if errors:
        raise ObservationDataError(
            "Observation validation failed:\n"
            + "\n".join(
                f"  - {error}"
                for error in errors
            )
        )

    print_status(
        "Observation value validation",
        "PASS",
    )

    print_status(
        "Occupancy rate minimum",
        f"{numeric['occupancy_rate'].min():.6f}",
    )

    print_status(
        "Occupancy rate maximum",
        f"{numeric['occupancy_rate'].max():.6f}",
    )

    print_status(
        "Available spaces minimum",
        f"{numeric['available_spaces'].min():,.0f}",
    )


# ============================================================================
# Facility resolution
# ============================================================================


async def resolve_facilities(
    session: AsyncSession,
    source_codes: list[str],
) -> dict[str, int]:
    """
    Resolve Birmingham source facility codes to
    SmartPark parking_facilities IDs.

    The production ML ingestion layer does NOT create facilities.
    """

    print_section(
        "RESOLVING PARKING FACILITIES"
    )

    unique_codes = sorted(
        set(source_codes)
    )

    result = await session.execute(
        select(
            ParkingFacility.id,
            ParkingFacility.code,
        ).where(
            ParkingFacility.code.in_(
                unique_codes
            )
        )
    )

    mapping = {
        str(code): int(facility_id)
        for facility_id, code in result.all()
    }

    missing = sorted(
        set(unique_codes)
        - set(mapping)
    )

    print_status(
        "Birmingham facility codes",
        len(unique_codes),
    )

    print_status(
        "Mapped facilities",
        len(mapping),
    )

    if missing:
        print()
        print(
            "Missing facility mappings:"
        )

        for code in missing:
            print(
                f"  - {code}"
            )

        raise FacilityMappingError(
            "One or more Birmingham facility codes "
            "do not exist in parking_facilities. "
            "Create/map the facility master data first."
        )

    print_status(
        "Facility mapping",
        "PASS",
    )

    return mapping


# ============================================================================
# Database row preparation
# ============================================================================


def build_database_rows(
    dataframe: pd.DataFrame,
    facility_mapping: dict[str, int],
) -> list[dict[str, Any]]:
    """
    Convert canonical normalized observations into database rows.
    """

    print_section(
        "BUILDING DATABASE OBSERVATION ROWS"
    )

    rows: list[dict[str, Any]] = []

    for record in dataframe.to_dict(
        orient="records"
    ):
        source_code = str(
            record[
                "source_facility_code"
            ]
        ).strip()

        facility_id = facility_mapping[
            source_code
        ]

        observed_at = pd.Timestamp(
            record["normalized_at"]
        )

        if observed_at.tzinfo is None:
            # Birmingham historical timestamps are naive
            # local observations. The normalization pipeline
            # established them as Birmingham-local historical
            # slots. We store them as timezone-aware UTC by
            # explicitly localizing to Europe/London.
            observed_at = (
                observed_at
                .tz_localize(
                    "Europe/London",
                    ambiguous="NaT",
                    nonexistent="shift_forward",
                )
            )

        if pd.isna(observed_at):
            raise ObservationDataError(
                "Unable to resolve timestamp for "
                f"facility {source_code}."
            )

        occupied = int(
            record["occupied_spaces"]
        )

        available = int(
            record["available_spaces"]
        )

        total = int(
            record["total_spaces"]
        )

        occupancy_rate = float(
            record["occupancy_rate"]
        )

        quality_flags = (
            normalize_quality_flags(
                record.get(
                    "quality_flags"
                )
            )
        )

        quality_status = (
            map_quality_status(
                record.get(
                    "quality_status"
                )
            )
        )

        rows.append(
            {
                "facility_id": facility_id,
                "observed_at": (
                    observed_at.to_pydatetime()
                ),
                "total_spaces": total,
                "occupied_spaces": occupied,
                "available_spaces": available,
                "occupancy_rate": occupancy_rate,
                "source": (
                    OccupancyObservationSource.BIRMINGHAM
                ),
                "quality_status": quality_status,
                "quality_flags": quality_flags,
            }
        )

    print_status(
        "Database rows prepared",
        f"{len(rows):,}",
    )

    return rows


# ============================================================================
# Database persistence
# ============================================================================


async def persist_observations(
    session: AsyncSession,
    rows: list[dict[str, Any]],
) -> int:
    """
    Insert/update occupancy observations in batches.

    PostgreSQL uniqueness:

        facility_id + observed_at

    is used as the idempotency key.
    """

    print_section(
        "PERSISTING OCCUPANCY OBSERVATIONS"
    )

    if not rows:
        return 0

    total_processed = 0

    for start in range(
        0,
        len(rows),
        BATCH_SIZE,
    ):
        batch = rows[
            start : start + BATCH_SIZE
        ]

        statement = insert(
            OccupancyObservation
        ).values(
            batch
        )

        excluded = statement.excluded

        statement = statement.on_conflict_do_update(
            constraint=(
                "uq_occupancy_observation_facility_time"
            ),
            set_={
                "total_spaces": (
                    excluded.total_spaces
                ),
                "occupied_spaces": (
                    excluded.occupied_spaces
                ),
                "available_spaces": (
                    excluded.available_spaces
                ),
                "occupancy_rate": (
                    excluded.occupancy_rate
                ),
                "source": (
                    excluded.source
                ),
                "quality_status": (
                    excluded.quality_status
                ),
                "quality_flags": (
                    excluded.quality_flags
                ),
                "updated_at": datetime.now().astimezone(),
            },
        )

        result = await session.execute(
            statement
        )

        total_processed += (
            result.rowcount
            if result.rowcount is not None
            else len(batch)
        )

        print_status(
            "Batch persisted",
            f"{min(start + BATCH_SIZE, len(rows)):,} / "
            f"{len(rows):,}",
        )

    await session.commit()

    print_status(
        "Database persistence",
        "PASS",
    )

    return total_processed


# ============================================================================
# Main ingestion operation
# ============================================================================


async def run_ingestion(
    *,
    dataset_root: Path,
    dry_run: bool,
) -> ObservationIngestionResult:
    """
    Execute the complete Birmingham production observation
    backfill.
    """

    started = datetime.now().astimezone()

    dataframe = load_birmingham_observations(
        dataset_root
    )

    source_row_count = len(dataframe)

    validate_schema(
        dataframe
    )

    observed, skipped = (
        select_real_observations(
            dataframe
        )
    )

    observed, capacity_exceeded_count = (
        normalize_capacity_exceeded_observations(
            observed
        )
    )

    validate_observation_values(
        observed
    )

    source_codes = (
        observed[
            "source_facility_code"
        ]
        .astype(str)
        .str.strip()
        .tolist()
    )

    async with AsyncSessionLocal() as session:

        facility_mapping = (
            await resolve_facilities(
                session,
                source_codes,
            )
        )

        rows = build_database_rows(
            observed,
            facility_mapping,
        )

        if dry_run:
            print_section(
                "DRY RUN"
            )

            print_status(
                "Database writes",
                "SKIPPED",
            )

            processed = 0

        else:
            processed = (
                await persist_observations(
                    session,
                    rows,
                )
            )

    completed = datetime.now().astimezone()

    return ObservationIngestionResult(
        source_rows=source_row_count,
        normalized_rows=len(
            dataframe
        ),
        observed_rows=len(
            observed
        ),
        skipped_missing_rows=skipped,
        capacity_exceeded_rows=(
            capacity_exceeded_count
        ),
        facility_count=len(
            facility_mapping
        ),
        inserted_or_updated=processed,
        dry_run=dry_run,
        started_at=started.isoformat(),
        completed_at=completed.isoformat(),
    )


# ============================================================================
# Post-ingestion verification
# ============================================================================


async def verify_database_counts() -> None:
    """
    Verify that occupancy_observations contains data after ingestion.
    """

    print_section(
        "VERIFYING OCCUPANCY_OBSERVATIONS"
    )

    async with AsyncSessionLocal() as session:

        from sqlalchemy import func

        result = await session.execute(
            select(
                func.count(
                    OccupancyObservation.id
                )
            )
        )

        count = int(
            result.scalar_one()
        )

        print_status(
            "occupancy_observations rows",
            f"{count:,}",
        )

        if count <= 0:
            raise ObservationIngestionError(
                "Ingestion completed but "
                "occupancy_observations contains no rows."
            )

        print_status(
            "Production observation store",
            "PASS",
        )


# ============================================================================
# CLI
# ============================================================================


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill Birmingham occupancy observations "
            "into SmartPark occupancy_observations."
        )
    )

    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
        help=(
            "Root directory containing the raw Birmingham "
            "dataset. Default: ../datasets/raw"
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate and prepare observations without "
            "writing to PostgreSQL."
        ),
    )

    return parser.parse_args()


# ============================================================================
# Entry point
# ============================================================================


async def main() -> int:
    print_header()

    args = parse_arguments()

    print_section(
        "INGESTION POLICY"
    )

    print_status(
        "Source",
        "BIRMINGHAM",
    )

    print_status(
        "Target table",
        "occupancy_observations",
    )

    print_status(
        "Training dataset loaded",
        "NO",
    )

    print_status(
        "Validation dataset loaded",
        "NO",
    )

    print_status(
        "Test dataset loaded",
        "NO",
    )

    print_status(
        "XGBoost training",
        "NO",
    )

    print_status(
        "Hyperparameter tuning",
        "NO",
    )

    print_status(
        "Feature pipeline rebuilt",
        "NO",
    )

    print_status(
        "Dry run",
        "YES" if args.dry_run else "NO",
    )

    try:
        result = await run_ingestion(
            dataset_root=(
                args.dataset_root.resolve()
            ),
            dry_run=args.dry_run,
        )

        if not args.dry_run:
            await verify_database_counts()

        print_section(
            "FINAL INGESTION RESULT"
        )

        print_status(
            "Source rows",
            f"{result.source_rows:,}",
        )

        print_status(
            "Normalized rows",
            f"{result.normalized_rows:,}",
        )

        print_status(
            "Actual observations",
            f"{result.observed_rows:,}",
        )

        print_status(
            "Missing slots skipped",
            f"{result.skipped_missing_rows:,}",
        )

        print_status(
            "Capacity-exceeded observations",
            f"{result.capacity_exceeded_rows:,}",
        )

        print_status(
            "Capacity-exceeded records marked",
            "SUSPECT",
        )

        print_status(
            "Original anomalies preserved",
            "YES",
        )

        print_status(
            "Facilities mapped",
            result.facility_count,
        )

        print_status(
            "Rows inserted/updated",
            f"{result.inserted_or_updated:,}",
        )

        print_status(
            "Result",
            "PASS",
        )

        print()
        print("=" * 78)

        if args.dry_run:
            print(
                "BIRMINGHAM OBSERVATION INGESTION "
                "DRY RUN COMPLETED SUCCESSFULLY"
            )
        else:
            print(
                "BIRMINGHAM OBSERVATION INGESTION "
                "COMPLETED SUCCESSFULLY"
            )

        print("=" * 78)
        print()

        print(
            "occupancy_observations is ready for "
            "production ML consumption."
        )

        return 0

    except Exception as exc:
        print()
        print("=" * 78)
        print(
            "BIRMINGHAM OBSERVATION INGESTION FAILED"
        )
        print("=" * 78)
        print()

        print(
            f"ERROR: {type(exc).__name__}: {exc}"
        )

        print()
        print(
            "No training/validation/test dataset was "
            "modified."
        )

        print(
            "No XGBoost training was performed."
        )

        print(
            "No hyperparameter tuning was performed."
        )

        print(
            "No feature pipeline was rebuilt."
        )

        print()

        return 1


if __name__ == "__main__":
    try:
        sys.exit(
            asyncio.run(
                main()
            )
        )

    except KeyboardInterrupt:
        print()
        print(
            "Observation ingestion interrupted."
        )
        sys.exit(130)