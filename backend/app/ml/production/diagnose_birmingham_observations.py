from __future__ import annotations

from pathlib import Path

import pandas as pd


def main() -> None:
    print("=" * 78)
    print("SMARTPARK AI - BIRMINGHAM OBSERVATION DATA QUALITY DIAGNOSTIC")
    print("=" * 78)

    dataset_root = (
        Path(__file__).resolve().parents[4]
        / "datasets"
        / "raw"
    )

    print()
    print("Dataset root:", dataset_root)
    print()

    from app.ml.data.temporal_normalizer import (
        normalize_birmingham_temporal,
    )

    result = normalize_birmingham_temporal(
        dataset_root=dataset_root,
    )

    df = result.dataframe.copy()

    print("Normalized rows:", len(df))

    observed = df.loc[
        df["observation_present"]
        .fillna(False)
        .astype(bool)
    ].copy()

    print("Observed rows:", len(observed))

    numeric_columns = [
        "total_spaces",
        "occupied_spaces",
        "available_spaces",
        "occupancy_rate",
    ]

    for column in numeric_columns:
        observed[column] = pd.to_numeric(
            observed[column],
            errors="coerce",
        )

    # ----------------------------------------------------------
    # Negative available spaces
    # ----------------------------------------------------------

    bad_available = observed.loc[
        observed["available_spaces"] < 0
    ].copy()

    print()
    print("-" * 78)
    print("NEGATIVE AVAILABLE-SPACE OBSERVATIONS")
    print("-" * 78)

    print("Count:", len(bad_available))

    if bad_available.empty:
        print("None found.")
    else:
        print()
        print(
            bad_available[
                [
                    "source_facility_code",
                    "source_observed_at",
                    "normalized_at",
                    "total_spaces",
                    "occupied_spaces",
                    "available_spaces",
                    "occupancy_rate",
                    "source",
                    "quality_status",
                    "quality_flags",
                ]
            ]
            .head(50)
            .to_string(index=False)
        )

    # ----------------------------------------------------------
    # Occupied > capacity
    # ----------------------------------------------------------

    occupied_exceeds_capacity = observed.loc[
        observed["occupied_spaces"]
        > observed["total_spaces"]
    ].copy()

    print()
    print("-" * 78)
    print("OCCUPIED > TOTAL CAPACITY")
    print("-" * 78)

    print(
        "Count:",
        len(occupied_exceeds_capacity),
    )

    # ----------------------------------------------------------
    # Capacity balance
    # ----------------------------------------------------------

    observed["balance_difference"] = (
        observed["occupied_spaces"]
        + observed["available_spaces"]
        - observed["total_spaces"]
    )

    balance_errors = observed.loc[
        observed["balance_difference"] != 0
    ].copy()

    print()
    print("-" * 78)
    print("CAPACITY BALANCE VIOLATIONS")
    print("-" * 78)

    print(
        "Count:",
        len(balance_errors),
    )

    if not balance_errors.empty:
        print()
        print(
            balance_errors[
                [
                    "source_facility_code",
                    "source_observed_at",
                    "normalized_at",
                    "total_spaces",
                    "occupied_spaces",
                    "available_spaces",
                    "balance_difference",
                    "occupancy_rate",
                ]
            ]
            .head(50)
            .to_string(index=False)
        )

    # ----------------------------------------------------------
    # Summary by facility
    # ----------------------------------------------------------

    print()
    print("-" * 78)
    print("NEGATIVE AVAILABLE SPACES BY FACILITY")
    print("-" * 78)

    if not bad_available.empty:
        summary = (
            bad_available
            .groupby("source_facility_code")
            .agg(
                observations=("available_spaces", "size"),
                min_available_spaces=(
                    "available_spaces",
                    "min",
                ),
                max_occupied_spaces=(
                    "occupied_spaces",
                    "max",
                ),
                max_total_spaces=(
                    "total_spaces",
                    "max",
                ),
            )
            .sort_values(
                "observations",
                ascending=False,
            )
        )

        print(summary.to_string())

    # ----------------------------------------------------------
    # Save diagnostic
    # ----------------------------------------------------------

    output_dir = (
        Path(__file__).resolve().parents[4]
        / "datasets"
        / "processed"
        / "birmingham"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        output_dir
        / "birmingham_observation_quality_diagnostic.csv"
    )

    bad_available.to_csv(
        output_file,
        index=False,
    )

    print()
    print("-" * 78)
    print("Diagnostic output")
    print("-" * 78)
    print("File:", output_file)

    print()
    print("=" * 78)
    print("DIAGNOSTIC COMPLETED")
    print("=" * 78)


if __name__ == "__main__":
    main()