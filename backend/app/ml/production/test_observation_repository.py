"""
SmartPark AI - Occupancy Observation Repository Smoke Test.

Purpose
-------
Verify that the production ML repository can successfully read
occupancy observations from PostgreSQL without modifying the database.

This test does NOT:

- insert observations
- update observations
- delete observations
- train XGBoost
- load validation.parquet
- load test.parquet
- rebuild the feature pipeline
- modify the frozen model artifact

It only verifies the DB -> Repository boundary.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.database.session import AsyncSessionLocal
from app.models.occupancy_observation import OccupancyObservation
from app.ml.production.observation_repository import (
    OccupancyObservationRepository,
)


# ============================================================
# Display helpers
# ============================================================


def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def status(label: str, passed: bool) -> None:
    print(
        f"{label:<55}: "
        f"{'PASS' if passed else 'FAIL'}"
    )


# ============================================================
# Main smoke test
# ============================================================


async def main() -> None:

    banner(
        "SMARTPARK AI - OCCUPANCY OBSERVATION "
        "REPOSITORY SMOKE TEST"
    )

    print()
    print("Purpose:")
    print(
        "  Verify PostgreSQL -> "
        "OccupancyObservationRepository."
    )
    print()
    print("Database writes:")
    print("  INSERT   : NO")
    print("  UPDATE   : NO")
    print("  DELETE   : NO")
    print()
    print("ML training:")
    print("  XGBoost training       : NO")
    print("  Hyperparameter tuning  : NO")
    print("  Feature rebuild       : NO")
    print()
    print("Dataset files:")
    print("  train.parquet          : NOT LOADED")
    print("  validation.parquet    : NOT LOADED")
    print("  test.parquet          : NOT LOADED")

    try:

        async with AsyncSessionLocal() as session:

            # ==================================================
            # Database connectivity
            # ==================================================

            banner(
                "--- DATABASE CONNECTIVITY ---"
            )

            result = await session.execute(
                select(func.count())
                .select_from(
                    OccupancyObservation
                )
            )

            total_count = int(
                result.scalar_one()
            )

            print(
                f"Total occupancy observations          : "
                f"{total_count}"
            )

            status(
                "Database connection",
                True,
            )

            # ==================================================
            # Facility distribution
            # ==================================================

            banner(
                "--- OBSERVATION DATASET OVERVIEW ---"
            )

            facility_statement = (
                select(
                    OccupancyObservation.facility_id,
                    func.count(
                        OccupancyObservation.id
                    ).label(
                        "observation_count"
                    ),
                    func.min(
                        OccupancyObservation.observed_at
                    ).label(
                        "earliest_observation"
                    ),
                    func.max(
                        OccupancyObservation.observed_at
                    ).label(
                        "latest_observation"
                    ),
                )
                .group_by(
                    OccupancyObservation.facility_id
                )
                .order_by(
                    OccupancyObservation.facility_id
                )
            )

            facility_result = await session.execute(
                facility_statement
            )

            facility_rows = (
                facility_result.all()
            )

            print(
                f"Facilities with observations          : "
                f"{len(facility_rows)}"
            )

            if not facility_rows:

                print()
                print(
                    "WARNING: occupancy_observations is "
                    "currently EMPTY."
                )

                print()
                print(
                    "The repository itself is ready, but "
                    "there is no production observation data "
                    "to consume yet."
                )

                print()
                print(
                    "NEXT STEP:"
                )
                print(
                    "  Build the Birmingham -> "
                    "occupancy_observations bootstrap importer."
                )

                status(
                    "Observation data available",
                    False,
                )

                return

            status(
                "Observation data available",
                True,
            )

            print()

            for row in facility_rows:

                print(
                    f"Facility {row.facility_id}: "
                    f"{row.observation_count} observations"
                )

                print(
                    f"  Earliest : "
                    f"{row.earliest_observation}"
                )

                print(
                    f"  Latest   : "
                    f"{row.latest_observation}"
                )

            # ==================================================
            # Select a real facility
            # ==================================================

            facility_id = int(
                facility_rows[0].facility_id
            )

            print()
            print(
                f"Selected facility for repository test : "
                f"{facility_id}"
            )

            # ==================================================
            # Latest observation
            # ==================================================

            banner(
                "--- REPOSITORY LATEST OBSERVATION TEST ---"
            )

            repository = (
                OccupancyObservationRepository(
                    session=session,
                )
            )

            latest = await repository.get_latest(
                facility_id=facility_id,
            )

            if latest is None:

                status(
                    "Latest observation retrieval",
                    False,
                )

                raise RuntimeError(
                    "Repository returned no latest "
                    "observation for the selected facility."
                )

            status(
                "Latest observation retrieval",
                True,
            )

            print()
            print(
                "Latest observation:"
            )

            for key, value in latest.items():

                print(
                    f"  {key:<22}: {value}"
                )

            # ==================================================
            # Production temporal cutoff test
            # ==================================================

            banner(
                "--- PRODUCTION TEMPORAL CUTOFF TEST ---"
            )

            latest_timestamp = latest[
                "observed_at"
            ]

            if latest_timestamp.tzinfo is None:

                latest_timestamp = (
                    latest_timestamp.replace(
                        tzinfo=timezone.utc
                    )
                )

            repository_dataframe = (
                await repository.get_for_forecast(
                    facility_id=facility_id,
                    prediction_timestamp=latest_timestamp,
                    lookback_minutes=24 * 60,
                )
            )

            print(
                f"Observations returned                  : "
                f"{len(repository_dataframe)}"
            )

            if repository_dataframe.empty:

                status(
                    "Forecast observation retrieval",
                    False,
                )

                raise RuntimeError(
                    "Repository returned an empty "
                    "forecast observation window."
                )

            status(
                "Forecast observation retrieval",
                True,
            )

            # ==================================================
            # Required schema
            # ==================================================

            required_columns = {
                "observed_at",
                "total_spaces",
                "occupied_spaces",
                "available_spaces",
                "occupancy_rate",
            }

            actual_columns = set(
                repository_dataframe.columns
            )

            missing_columns = (
                required_columns
                - actual_columns
            )

            status(
                "Required observation schema",
                not missing_columns,
            )

            if missing_columns:

                raise RuntimeError(
                    "Missing repository columns: "
                    f"{sorted(missing_columns)}"
                )

            # ==================================================
            # Temporal boundary verification
            # ==================================================

            timestamps = (
                repository_dataframe[
                    "observed_at"
                ]
            )

            max_timestamp = timestamps.max()

            cutoff = latest_timestamp

            if max_timestamp.tzinfo is None:

                max_timestamp = (
                    max_timestamp.tz_localize(
                        "UTC"
                    )
                )

            if cutoff.tzinfo is None:

                cutoff = cutoff.replace(
                    tzinfo=timezone.utc
                )

            cutoff_passed = (
                max_timestamp
                <= cutoff
            )

            status(
                "No observations after prediction timestamp",
                cutoff_passed,
            )

            if not cutoff_passed:

                raise RuntimeError(
                    "Temporal leakage detected: repository "
                    "returned an observation after T."
                )

            # ==================================================
            # Data integrity verification
            # ==================================================

            banner(
                "--- OBSERVATION DATA INTEGRITY ---"
            )

            total_spaces = (
                repository_dataframe[
                    "total_spaces"
                ]
            )

            occupied_spaces = (
                repository_dataframe[
                    "occupied_spaces"
                ]
            )

            available_spaces = (
                repository_dataframe[
                    "available_spaces"
                ]
            )

            occupancy_rate = (
                repository_dataframe[
                    "occupancy_rate"
                ]
            )

            status(
                "total_spaces > 0",
                bool(
                    (total_spaces > 0).all()
                ),
            )

            status(
                "occupied_spaces >= 0",
                bool(
                    (occupied_spaces >= 0).all()
                ),
            )

            status(
                "available_spaces >= 0",
                bool(
                    (available_spaces >= 0).all()
                ),
            )

            status(
                "occupied + available = total",
                bool(
                    (
                        occupied_spaces
                        + available_spaces
                        == total_spaces
                    ).all()
                ),
            )

            status(
                "occupancy_rate within [0,1]",
                bool(
                    (
                        (occupancy_rate >= 0)
                        & (occupancy_rate <= 1)
                    ).all()
                ),
            )

            # ==================================================
            # Duplicate timestamp check
            # ==================================================

            duplicate_timestamps = (
                timestamps.duplicated().any()
            )

            status(
                "No duplicate observation timestamps",
                not duplicate_timestamps,
            )

            if duplicate_timestamps:

                raise RuntimeError(
                    "Duplicate observation timestamps "
                    "detected."
                )

            # ==================================================
            # Summary
            # ==================================================

            banner(
                "--- REPOSITORY SMOKE TEST SUMMARY ---"
            )

            print(
                f"Facility tested                      : "
                f"{facility_id}"
            )

            print(
                f"Observation rows retrieved           : "
                f"{len(repository_dataframe)}"
            )

            print(
                f"Observation window start             : "
                f"{timestamps.min()}"
            )

            print(
                f"Observation window end               : "
                f"{timestamps.max()}"
            )

            print(
                f"Latest occupancy rate                : "
                f"{float(occupancy_rate.iloc[-1]):.4f}"
            )

            print()
            print(
                "Database writes performed            : NO"
            )
            print(
                "XGBoost training performed           : NO"
            )
            print(
                "Hyperparameter tuning performed      : NO"
            )
            print(
                "Feature pipeline rebuilt             : NO"
            )

            banner(
                "OCCUPANCY OBSERVATION REPOSITORY "
                "SMOKE TEST PASSED"
            )

    except Exception as exc:

        banner(
            "OCCUPANCY OBSERVATION REPOSITORY "
            "SMOKE TEST FAILED"
        )

        print()
        print(
            f"ERROR: {type(exc).__name__}: {exc}"
        )

        print()
        print(
            "Database writes performed: NO"
        )
        print(
            "XGBoost training performed: NO"
        )
        print(
            "Validation dataset loaded: NO"
        )
        print(
            "Test dataset loaded: NO"
        )

        raise


# ============================================================
# Entry point
# ============================================================


if __name__ == "__main__":
    asyncio.run(main())