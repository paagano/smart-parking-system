"""
SmartPark AI - Birmingham Facility Master Data Bootstrap.

Purpose
-------
Create canonical ParkingFacility master records required by the
Birmingham production observation bootstrap.

IMPORTANT
---------
This module is NOT an ML training component.

It does NOT:
    - train XGBoost
    - train LSTM
    - tune hyperparameters
    - rebuild features
    - modify frozen model artifacts
    - modify train/validation/test datasets
    - insert occupancy observations

It only establishes the domain/master-data relationship:

    Birmingham source_facility_code
                |
                v
         parking_facilities
                |
                v
       occupancy_observations

The subsequent observation_ingestion.py module performs the actual
occupancy observation ingestion.

The operation is idempotent:
    - Existing facilities are reused.
    - Missing facilities are created.
    - Existing records are not duplicated.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import AsyncSessionLocal
from app.models.enums import FacilityType
from app.models.parking_facility import ParkingFacility


# ============================================================================
# Constants
# ============================================================================

DEFAULT_DATASET_ROOT = (
    Path(__file__).resolve().parents[4]
    / "datasets"
    / "raw"
)

# Birmingham source facilities are public parking locations.
#
# We deliberately use PUBLIC rather than inventing categories such as
# shopping mall, hospital, airport, etc. unless the source explicitly
# provides that information.
DEFAULT_FACILITY_TYPE = FacilityType.PUBLIC

DEFAULT_COUNTRY = "United Kingdom"
DEFAULT_CITY = "Birmingham"

DEFAULT_TIMEZONE = "Europe/London"

# Birmingham public parking source is represented as an operational
# parking facility for the purposes of the SmartPark domain model.
DEFAULT_OPENING_TIME = "00:00"
DEFAULT_CLOSING_TIME = "23:59"


# ============================================================================
# Exceptions
# ============================================================================


class FacilityBootstrapError(Exception):
    """Base exception for facility bootstrap failures."""


class FacilityBootstrapDataError(
    FacilityBootstrapError
):
    """Raised when source facility information is invalid."""


# ============================================================================
# Result
# ============================================================================


@dataclass(slots=True)
class FacilityBootstrapResult:
    """Summary of a facility bootstrap operation."""

    source_facility_count: int
    existing_facility_count: int
    created_facility_count: int
    dry_run: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_facility_count": self.source_facility_count,
            "existing_facility_count": self.existing_facility_count,
            "created_facility_count": self.created_facility_count,
            "dry_run": self.dry_run,
        }


# ============================================================================
# Console helpers
# ============================================================================


def print_header() -> None:
    print()
    print("=" * 78)
    print(
        "SMARTPARK AI - BIRMINGHAM FACILITY MASTER DATA BOOTSTRAP"
    )
    print("=" * 78)
    print()

    print("Purpose:")
    print(
        "  Establish canonical ParkingFacility records required "
        "for Birmingham observation ingestion."
    )

    print()
    print("This operation:")
    print("  ML training                         : NO")
    print("  XGBoost training                    : NO")
    print("  Hyperparameter tuning               : NO")
    print("  Feature engineering                 : NO")
    print("  Frozen model modification           : NO")
    print("  Occupancy observation insertion     : NO")
    print("  Facility master-data creation      : YES")


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
# Source facility extraction
# ============================================================================


def load_normalized_birmingham_observations(
    dataset_root: Path,
) -> pd.DataFrame:
    """
    Load the same canonical normalized Birmingham observation dataset
    used by production observation_ingestion.py.

    We intentionally reuse the existing temporal normalization pipeline.

    No raw parsing logic is duplicated here.
    """

    print_section(
        "LOADING CANONICAL BIRMINGHAM OBSERVATIONS"
    )

    print_status(
        "Dataset root",
        dataset_root,
    )

    if not dataset_root.exists():
        raise FacilityBootstrapDataError(
            f"Dataset root does not exist: {dataset_root}"
        )

    try:
        from app.ml.data.temporal_normalizer import (
            normalize_birmingham_temporal,
        )
    except ImportError as exc:
        raise FacilityBootstrapError(
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
        raise FacilityBootstrapDataError(
            "Birmingham temporal normalizer did not "
            "return a pandas DataFrame."
        )

    required = {
        "source_facility_code",
        "observation_present",
    }

    missing = sorted(
        required
        - set(dataframe.columns)
    )

    if missing:
        raise FacilityBootstrapDataError(
            "Normalized Birmingham dataset is missing "
            f"required columns: {missing}"
        )

    print_status(
        "Normalized rows",
        f"{len(dataframe):,}",
    )

    return dataframe


def extract_source_facility_codes(
    dataframe: pd.DataFrame,
) -> list[str]:
    """
    Extract distinct Birmingham facility codes from actual
    observations only.

    Missing normalized slots are ignored because they do not
    represent actual parking observations.
    """

    print_section(
        "EXTRACTING SOURCE FACILITIES"
    )

    presence = (
        dataframe["observation_present"]
        .fillna(False)
        .astype(bool)
    )

    observed = dataframe.loc[
        presence
    ].copy()

    codes = (
        observed["source_facility_code"]
        .astype("string")
        .str.strip()
    )

    codes = codes[
        codes.notna()
        & codes.ne("")
    ]

    unique_codes = sorted(
        set(
            codes.tolist()
        )
    )

    if not unique_codes:
        raise FacilityBootstrapDataError(
            "No source facility codes were found "
            "in actual Birmingham observations."
        )

    print_status(
        "Actual observation rows",
        f"{len(observed):,}",
    )

    print_status(
        "Distinct source facilities",
        len(unique_codes),
    )

    print()

    for code in unique_codes:
        print(
            f"  - {code}"
        )

    return unique_codes


# ============================================================================
# Facility construction
# ============================================================================


def build_facility_payload(
    source_code: str,
) -> dict[str, Any]:
    """
    Build the canonical ParkingFacility payload.

    The Birmingham source facility code becomes the canonical
    SmartPark facility code.

    This is deliberate: it preserves source identity and makes
    the facility mapping deterministic.

    We do not invent capacity because total capacity belongs to
    occupancy observations and varies according to the source
    observation stream.
    """

    return {
        "name": (
            f"Birmingham Parking - {source_code}"
        ),
        "code": source_code,
        "facility_type": DEFAULT_FACILITY_TYPE,
        "description": (
            "Canonical SmartPark facility representing "
            f"Birmingham source parking facility {source_code}. "
            "Created as historical/production bootstrap master data."
        ),
        "country": DEFAULT_COUNTRY,
        "county": None,
        "city": DEFAULT_CITY,
        "address": None,
        "postal_code": None,
        "latitude": None,
        "longitude": None,
        "timezone": DEFAULT_TIMEZONE,
        "opening_time": pd.Timestamp(
            DEFAULT_OPENING_TIME
        ).time(),
        "closing_time": pd.Timestamp(
            DEFAULT_CLOSING_TIME
        ).time(),
        "is_active": True,
    }


# ============================================================================
# Existing facility lookup
# ============================================================================


async def load_existing_facilities(
    session: AsyncSession,
    source_codes: list[str],
) -> dict[str, ParkingFacility]:
    """
    Load existing facilities matching the source codes.

    Matching is performed against ParkingFacility.code.
    """

    result = await session.execute(
        select(ParkingFacility).where(
            ParkingFacility.code.in_(
                source_codes
            )
        )
    )

    facilities = result.scalars().all()

    return {
        str(
            facility.code
        ): facility
        for facility in facilities
    }


# ============================================================================
# Bootstrap
# ============================================================================


async def bootstrap_facilities(
    *,
    dataset_root: Path,
    dry_run: bool,
) -> FacilityBootstrapResult:
    """
    Create missing Birmingham facility master records.

    Existing records are never duplicated.

    In dry-run mode no database writes are committed.
    """

    dataframe = (
        load_normalized_birmingham_observations(
            dataset_root
        )
    )

    source_codes = (
        extract_source_facility_codes(
            dataframe
        )
    )

    print_section(
        "RESOLVING FACILITY MASTER DATA"
    )

    async with AsyncSessionLocal() as session:

        existing = await load_existing_facilities(
            session,
            source_codes,
        )

        existing_codes = set(
            existing.keys()
        )

        missing_codes = [
            code
            for code in source_codes
            if code not in existing_codes
        ]

        print_status(
            "Source facilities",
            len(source_codes),
        )

        print_status(
            "Existing canonical facilities",
            len(existing_codes),
        )

        print_status(
            "Missing canonical facilities",
            len(missing_codes),
        )

        if existing_codes:
            print()
            print("Existing facilities:")

            for code in sorted(existing_codes):
                facility = existing[code]

                print(
                    f"  [EXISTS] "
                    f"id={facility.id} | "
                    f"code={facility.code} | "
                    f"name={facility.name}"
                )

        if missing_codes:
            print()
            print("Facilities to create:")

            for code in missing_codes:
                print(
                    f"  [CREATE] "
                    f"code={code}"
                )

        if dry_run:

            print_section(
                "DRY RUN"
            )

            print_status(
                "Database writes",
                "SKIPPED",
            )

            print_status(
                "Facilities that would be created",
                len(missing_codes),
            )

            return FacilityBootstrapResult(
                source_facility_count=len(
                    source_codes
                ),
                existing_facility_count=len(
                    existing_codes
                ),
                created_facility_count=0,
                dry_run=True,
            )

        # --------------------------------------------------------------
        # Actual persistence
        # --------------------------------------------------------------

        print_section(
            "CREATING CANONICAL FACILITIES"
        )

        created_count = 0

        for code in missing_codes:

            payload = build_facility_payload(
                code
            )

            facility = ParkingFacility(
                **payload
            )

            session.add(
                facility
            )

            created_count += 1

            print(
                f"  [CREATED] "
                f"code={code}"
            )

        if created_count:
            await session.commit()

        else:
            print(
                "  No new facilities required."
            )

        # --------------------------------------------------------------
        # Final verification
        # --------------------------------------------------------------

        verified = await load_existing_facilities(
            session,
            source_codes,
        )

        missing_after_commit = sorted(
            set(source_codes)
            - set(verified.keys())
        )

        if missing_after_commit:
            raise FacilityBootstrapError(
                "Facility bootstrap completed but "
                "some source facilities remain unmapped: "
                f"{missing_after_commit}"
            )

        print_status(
            "Facility master-data verification",
            "PASS",
        )

        return FacilityBootstrapResult(
            source_facility_count=len(
                source_codes
            ),
            existing_facility_count=len(
                existing_codes
            ),
            created_facility_count=created_count,
            dry_run=False,
        )


# ============================================================================
# CLI
# ============================================================================


def parse_arguments() -> argparse.Namespace:

    parser = argparse.ArgumentParser(
        description=(
            "Bootstrap canonical ParkingFacility "
            "records for the Birmingham source."
        )
    )

    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=DEFAULT_DATASET_ROOT,
        help=(
            "Root directory containing the Birmingham "
            "raw dataset."
        ),
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Discover and validate facilities without "
            "writing to PostgreSQL."
        ),
    )

    return parser.parse_args()


# ============================================================================
# Main
# ============================================================================


async def main() -> int:

    print_header()

    args = parse_arguments()

    print_section(
        "BOOTSTRAP POLICY"
    )

    print_status(
        "Source",
        "BIRMINGHAM",
    )

    print_status(
        "Target domain table",
        "parking_facilities",
    )

    print_status(
        "Occupancy observations written",
        "NO",
    )

    print_status(
        "Training datasets loaded",
        "NO",
    )

    print_status(
        "XGBoost training",
        "NO",
    )

    print_status(
        "Frozen model modified",
        "NO",
    )

    print_status(
        "Dry run",
        "YES" if args.dry_run else "NO",
    )

    try:

        result = await bootstrap_facilities(
            dataset_root=(
                args.dataset_root.resolve()
            ),
            dry_run=args.dry_run,
        )

        print_section(
            "FINAL FACILITY BOOTSTRAP RESULT"
        )

        print_status(
            "Source facilities",
            result.source_facility_count,
        )

        print_status(
            "Existing facilities",
            result.existing_facility_count,
        )

        print_status(
            "Facilities created",
            result.created_facility_count,
        )

        print_status(
            "Result",
            "PASS",
        )

        print()
        print("=" * 78)

        if args.dry_run:
            print(
                "BIRMINGHAM FACILITY BOOTSTRAP "
                "DRY RUN COMPLETED SUCCESSFULLY"
            )
        else:
            print(
                "BIRMINGHAM FACILITY MASTER DATA "
                "BOOTSTRAP COMPLETED SUCCESSFULLY"
            )

        print("=" * 78)
        print()

        print(
            "Next step:"
        )

        if args.dry_run:
            print(
                "  Run without --dry-run to create the "
                "canonical facility master records."
            )
        else:
            print(
                "  Run:"
            )
            print(
                "    python -m "
                "app.ml.production.observation_ingestion "
                "--dry-run"
            )
            print()
            print(
                "  Then, after the dry run passes:"
            )
            print(
                "    python -m "
                "app.ml.production.observation_ingestion"
            )

        return 0

    except Exception as exc:

        print()
        print("=" * 78)
        print(
            "BIRMINGHAM FACILITY BOOTSTRAP FAILED"
        )
        print("=" * 78)
        print()

        print(
            f"ERROR: {type(exc).__name__}: {exc}"
        )

        print()
        print(
            "No ML training was performed."
        )

        print(
            "No frozen model was modified."
        )

        print(
            "No occupancy observations were inserted."
        )

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
            "Facility bootstrap interrupted."
        )

        sys.exit(130)