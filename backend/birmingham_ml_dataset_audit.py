from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from app.ml.data.dataset_builder import (
    build_birmingham_ml_dataset,
)
from app.ml.features.feature_pipeline import (
    build_feature_pipeline,
    validate_feature_pipeline,
)


# ============================================================
# Configuration
# ============================================================

DATASET_ROOT = "../datasets/raw"

TOP_N = 20

TARGET_COLUMNS = (
    "target_occupancy_rate_30m",
    "target_occupancy_rate_1h",
    "target_occupancy_rate_2h",
    "target_tomorrow_morning_demand",
)

TARGET_AVAILABILITY_COLUMNS = (
    "target_30m_available",
    "target_1h_available",
    "target_2h_available",
    "target_tomorrow_morning_available",
)

LAG_AVAILABILITY_COLUMNS = (
    "occupancy_rate_lag_30m_available",
    "occupancy_rate_lag_1h_available",
    "occupancy_rate_lag_2h_available",
    "occupancy_rate_lag_3h_available",
    "occupancy_rate_lag_6h_available",
    "occupancy_rate_lag_12h_available",
    "occupancy_rate_lag_1d_available",
)

ROLLING_AVAILABILITY_COLUMNS = (
    "occupancy_rate_roll_1h_available",
    "occupancy_rate_roll_2h_available",
    "occupancy_rate_roll_3h_available",
    "occupancy_rate_roll_6h_available",
    "occupancy_rate_roll_12h_available",
    "occupancy_rate_roll_24h_available",
)

FACILITY_COLUMN = "source_facility_code"
TIMESTAMP_COLUMN = "normalized_at"


# ============================================================
# Formatting helpers
# ============================================================

def percentage(
    numerator: int | float,
    denominator: int | float,
) -> float:
    if denominator == 0:
        return 0.0

    return (
        float(numerator)
        / float(denominator)
        * 100.0
    )


def print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_subsection(title: str) -> None:
    print()
    print(f"--- {title} ---")


# ============================================================
# Dataset overview
# ============================================================

def audit_dataset_overview(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "1. DATASET OVERVIEW"
    )

    print(
        "Rows:",
        f"{len(dataframe):,}",
    )

    print(
        "Columns:",
        f"{len(dataframe.columns):,}",
    )

    if FACILITY_COLUMN in dataframe.columns:

        print(
            "Facilities:",
            dataframe[
                FACILITY_COLUMN
            ]
            .nunique(
                dropna=True
            ),
        )

    if TIMESTAMP_COLUMN in dataframe.columns:

        timestamp = pd.to_datetime(
            dataframe[
                TIMESTAMP_COLUMN
            ],
            errors="coerce",
        )

        print(
            "First timestamp:",
            timestamp.min(),
        )

        print(
            "Last timestamp:",
            timestamp.max(),
        )

        print(
            "Invalid timestamps:",
            int(timestamp.isna().sum()),
        )


# ============================================================
# Pipeline overview
# ============================================================

def audit_pipeline_result(
    result,
) -> None:

    print_section(
        "2. FEATURE PIPELINE RESULT"
    )

    print(
        "Output rows:",
        f"{len(result.dataframe):,}",
    )

    print(
        "Output columns:",
        f"{len(result.dataframe.columns):,}",
    )

    print(
        "ML features:",
        f"{len(result.feature_columns):,}",
    )

    print(
        "Targets:",
        f"{len(result.target_columns):,}",
    )

    print(
        "Target availability:",
        f"{len(result.target_availability_columns):,}",
    )

    print(
        "Metadata:",
        f"{len(result.metadata_columns):,}",
    )

    print_subsection(
        "Feature groups"
    )

    for (
        name,
        columns,
    ) in result.metadata[
        "feature_groups"
    ].items():

        print(
            f"{name:15}: "
            f"{len(columns):,}"
        )


# ============================================================
# Facility coverage
# ============================================================

def audit_facility_coverage(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "3. FACILITY COVERAGE"
    )

    if (
        FACILITY_COLUMN
        not in dataframe.columns
    ):

        print(
            "Facility column not found:",
            FACILITY_COLUMN,
        )

        return

    timestamp = pd.to_datetime(
        dataframe[
            TIMESTAMP_COLUMN
        ],
        errors="coerce",
    )

    working = dataframe.copy()

    working[
        "__audit_timestamp"
    ] = timestamp

    grouped = (
        working
        .groupby(
            FACILITY_COLUMN,
            dropna=False,
        )
        .agg(
            observations=(
                FACILITY_COLUMN,
                "size",
            ),
            first_timestamp=(
                "__audit_timestamp",
                "min",
            ),
            last_timestamp=(
                "__audit_timestamp",
                "max",
            ),
        )
        .reset_index()
    )

    grouped[
        "calendar_span_days"
    ] = (
        grouped[
            "last_timestamp"
        ]
        - grouped[
            "first_timestamp"
        ]
    ).dt.total_seconds() / 86400.0

    grouped[
        "expected_30m_slots"
    ] = (
        grouped[
            "calendar_span_days"
        ]
        * 48
    )

    grouped[
        "observation_coverage_pct"
    ] = grouped.apply(
        lambda row: percentage(
            row["observations"],
            row["expected_30m_slots"],
        ),
        axis=1,
    )

    print(
        grouped.to_string(
            index=False
        )
    )


# ============================================================
# Duplicate facility/timestamp audit
# ============================================================

def audit_duplicates(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "4. DUPLICATE FACILITY/TIMESTAMP AUDIT"
    )

    if not {
        FACILITY_COLUMN,
        TIMESTAMP_COLUMN,
    }.issubset(
        dataframe.columns
    ):

        print(
            "Required columns are missing."
        )

        return

    duplicates = dataframe.duplicated(
        subset=[
            FACILITY_COLUMN,
            TIMESTAMP_COLUMN,
        ],
        keep=False,
    )

    duplicate_count = int(
        duplicates.sum()
    )

    duplicate_groups = int(
        dataframe.loc[
            duplicates,
            [
                FACILITY_COLUMN,
                TIMESTAMP_COLUMN,
            ],
        ]
        .drop_duplicates()
        .shape[0]
    )

    print(
        "Duplicate rows:",
        f"{duplicate_count:,}",
    )

    print(
        "Duplicate facility/timestamp groups:",
        f"{duplicate_groups:,}",
    )


# ============================================================
# Target availability
# ============================================================

def audit_target_availability(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "5. TARGET AVAILABILITY"
    )

    total_rows = len(
        dataframe
    )

    for column in (
        TARGET_AVAILABILITY_COLUMNS
    ):

        if column not in dataframe.columns:

            print(
                f"{column:45}: MISSING"
            )

            continue

        available = int(
            dataframe[column]
            .fillna(False)
            .astype(bool)
            .sum()
        )

        unavailable = (
            total_rows
            - available
        )

        print(
            f"{column:45}: "
            f"available={available:,} "
            f"({percentage(available, total_rows):6.2f}%) "
            f"unavailable={unavailable:,} "
            f"({percentage(unavailable, total_rows):6.2f}%)"
        )


# ============================================================
# Target value profile
# ============================================================

def audit_target_values(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "6. TARGET VALUE PROFILE"
    )

    for column in TARGET_COLUMNS:

        print_subsection(
            column
        )

        if column not in dataframe.columns:

            print(
                "Column missing."
            )

            continue

        series = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

        non_null = int(
            series.notna().sum()
        )

        null_count = int(
            series.isna().sum()
        )

        print(
            "Non-null:",
            f"{non_null:,}",
        )

        print(
            "Null:",
            f"{null_count:,}",
        )

        if non_null == 0:
            continue

        print(
            "Min:",
            series.min(),
        )

        print(
            "Max:",
            series.max(),
        )

        print(
            "Mean:",
            series.mean(),
        )

        print(
            "Median:",
            series.median(),
        )

        print(
            "Std:",
            series.std(),
        )


# ============================================================
# Target exclusion reasons
# ============================================================

def audit_target_exclusion_reasons(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "7. TARGET EXCLUSION REASONS"
    )

    possible_columns = (
        "target_exclusion_reason",
        "reason",
    )

    reason_column = next(
        (
            column
            for column in possible_columns
            if column in dataframe.columns
        ),
        None,
    )

    if reason_column is None:

        print(
            "No target exclusion reason "
            "column found."
        )

        return

    counts = (
        dataframe[
            reason_column
        ]
        .fillna("<NULL>")
        .astype(str)
        .value_counts(
            dropna=False
        )
    )

    print(
        counts.to_string()
    )


# ============================================================
# Target availability by facility
# ============================================================

def audit_target_availability_by_facility(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "8. TARGET AVAILABILITY BY FACILITY"
    )

    required = {
        FACILITY_COLUMN,
        *TARGET_AVAILABILITY_COLUMNS,
    }

    missing = (
        required
        - set(dataframe.columns)
    )

    if missing:

        print(
            "Missing columns:",
            sorted(missing),
        )

        return

    rows = []

    for facility, group in (
        dataframe.groupby(
            FACILITY_COLUMN,
            dropna=False,
        )
    ):

        row = {
            FACILITY_COLUMN: facility,
            "rows": len(group),
        }

        for column in (
            TARGET_AVAILABILITY_COLUMNS
        ):

            available = int(
                group[column]
                .fillna(False)
                .astype(bool)
                .sum()
            )

            row[
                column
                .replace(
                    "target_",
                    "",
                )
                .replace(
                    "_available",
                    "",
                )
                + "_pct"
            ] = percentage(
                available,
                len(group),
            )

        rows.append(row)

    result = pd.DataFrame(
        rows
    )

    print(
        result.to_string(
            index=False
        )
    )


# ============================================================
# Lag availability
# ============================================================

def audit_lag_availability(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "9. LAG FEATURE AVAILABILITY"
    )

    total_rows = len(
        dataframe
    )

    for column in (
        LAG_AVAILABILITY_COLUMNS
    ):

        if column not in dataframe.columns:

            print(
                f"{column:45}: MISSING"
            )

            continue

        available = int(
            dataframe[column]
            .fillna(False)
            .astype(bool)
            .sum()
        )

        print(
            f"{column:45}: "
            f"{available:,} / "
            f"{total_rows:,} "
            f"({percentage(available, total_rows):6.2f}%)"
        )


# ============================================================
# Rolling availability
# ============================================================

def audit_rolling_availability(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "10. ROLLING FEATURE AVAILABILITY"
    )

    total_rows = len(
        dataframe
    )

    for column in (
        ROLLING_AVAILABILITY_COLUMNS
    ):

        if column not in dataframe.columns:

            print(
                f"{column:45}: MISSING"
            )

            continue

        available = int(
            dataframe[column]
            .fillna(False)
            .astype(bool)
            .sum()
        )

        print(
            f"{column:45}: "
            f"{available:,} / "
            f"{total_rows:,} "
            f"({percentage(available, total_rows):6.2f}%)"
        )


# ============================================================
# Feature null profile
# ============================================================

def audit_feature_nulls(
    dataframe: pd.DataFrame,
    feature_columns,
) -> None:

    print_section(
        "11. FEATURE NULL PROFILE"
    )

    existing = [
        column
        for column in feature_columns
        if column in dataframe.columns
    ]

    if not existing:

        print(
            "No feature columns found."
        )

        return

    null_counts = (
        dataframe[existing]
        .isna()
        .sum()
        .sort_values(
            ascending=False
        )
    )

    total_null_cells = int(
        null_counts.sum()
    )

    features_with_nulls = (
        int(
            (
                null_counts > 0
            ).sum()
        )
    )

    print(
        "Total feature null cells:",
        f"{total_null_cells:,}",
    )

    print(
        "Features containing nulls:",
        features_with_nulls,
    )

    print_subsection(
        f"Top {TOP_N} features by null count"
    )

    print(
        null_counts
        .head(TOP_N)
        .to_string()
    )


# ============================================================
# Feature null percentage
# ============================================================

def audit_feature_null_percentages(
    dataframe: pd.DataFrame,
    feature_columns,
) -> None:

    print_section(
        "12. HIGHEST FEATURE NULL PERCENTAGES"
    )

    existing = [
        column
        for column in feature_columns
        if column in dataframe.columns
    ]

    if not existing:
        return

    null_percentages = (
        dataframe[existing]
        .isna()
        .mean()
        .mul(100)
        .sort_values(
            ascending=False
        )
    )

    print(
        null_percentages
        .head(TOP_N)
        .map(
            lambda value:
            f"{value:.2f}%"
        )
        .to_string()
    )


# ============================================================
# Infinite values
# ============================================================

def audit_infinite_values(
    dataframe: pd.DataFrame,
    feature_columns,
) -> None:

    print_section(
        "13. INFINITE VALUE AUDIT"
    )

    numeric = (
        dataframe[
            [
                column
                for column in feature_columns
                if column
                in dataframe.columns
            ]
        ]
        .select_dtypes(
            include=np.number
        )
    )

    if numeric.empty:

        print(
            "No numeric features found."
        )

        return

    infinite_mask = (
        np.isinf(
            numeric.to_numpy(
                dtype="float64"
            )
        )
    )

    total_infinite = int(
        infinite_mask.sum()
    )

    print(
        "Infinite numeric cells:",
        total_infinite,
    )

    if total_infinite:

        counts = pd.Series(
            infinite_mask.sum(
                axis=0
            ),
            index=numeric.columns,
        )

        print(
            counts[
                counts > 0
            ]
            .sort_values(
                ascending=False
            )
            .to_string()
        )


# ============================================================
# Feature dtypes
# ============================================================

def audit_feature_dtypes(
    dataframe: pd.DataFrame,
    feature_columns,
) -> None:

    print_section(
        "14. FEATURE DTYPES"
    )

    existing = [
        column
        for column in feature_columns
        if column in dataframe.columns
    ]

    dtype_counts = (
        dataframe[existing]
        .dtypes
        .astype(str)
        .value_counts()
    )

    print(
        dtype_counts.to_string()
    )


# ============================================================
# Constant features
# ============================================================

def audit_constant_features(
    dataframe: pd.DataFrame,
    feature_columns,
) -> None:

    print_section(
        "15. CONSTANT FEATURE AUDIT"
    )

    constant = []

    for column in feature_columns:

        if column not in dataframe.columns:
            continue

        if (
            dataframe[column]
            .nunique(
                dropna=False
            )
            <= 1
        ):

            constant.append(
                column
            )

    print(
        "Constant features:",
        len(constant),
    )

    if constant:

        print(
            constant
        )


# ============================================================
# Facility target coverage
# ============================================================

def audit_facility_target_counts(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "16. USABLE TARGET ROWS BY FACILITY"
    )

    required = {
        FACILITY_COLUMN,
        *TARGET_COLUMNS,
    }

    missing = (
        required
        - set(dataframe.columns)
    )

    if missing:

        print(
            "Missing columns:",
            sorted(missing),
        )

        return

    rows = []

    for facility, group in (
        dataframe.groupby(
            FACILITY_COLUMN,
            dropna=False,
        )
    ):

        row = {
            FACILITY_COLUMN: facility,
            "rows": len(group),
        }

        for column in TARGET_COLUMNS:

            usable = int(
                group[column]
                .notna()
                .sum()
            )

            short_name = (
                column
                .replace(
                    "target_",
                    "",
                )
            )

            row[
                f"{short_name}_usable"
            ] = usable

            row[
                f"{short_name}_pct"
            ] = percentage(
                usable,
                len(group),
            )

        rows.append(row)

    result = pd.DataFrame(
        rows
    )

    print(
        result.to_string(
            index=False
        )
    )


# ============================================================
# Leakage audit
# ============================================================

def audit_leakage(
    result,
) -> None:

    print_section(
        "17. LEAKAGE CONTRACT"
    )

    fields = (
        "future_data_used",
        "target_data_used",
        "cross_facility_data_used",
        "forward_lookup_used",
        "centered_windows_used",
    )

    for field in fields:

        value = result.metadata.get(
            field
        )

        print(
            f"{field:35}: {value}"
        )


# ============================================================
# Pipeline validation
# ============================================================

def audit_pipeline_validation(
    result,
) -> dict:

    print_section(
        "18. PIPELINE VALIDATION"
    )

    validation = (
        validate_feature_pipeline(
            result.dataframe
        )
    )

    print(
        "Valid:",
        validation["valid"],
    )

    print(
        "Expected features:",
        validation.get(
            "expected_feature_count"
        ),
    )

    print(
        "Actual features:",
        validation.get(
            "actual_feature_count"
        ),
    )

    print(
        "Errors:",
        validation["errors"],
    )

    print(
        "Warnings:",
        validation["warnings"],
    )

    return validation


# ============================================================
# Final summary
# ============================================================

def print_final_summary(
    dataframe: pd.DataFrame,
    result,
    validation: dict,
) -> None:

    print_section(
        "19. FINAL AUDIT SUMMARY"
    )

    print(
        "Rows:",
        f"{len(dataframe):,}",
    )

    print(
        "Columns:",
        f"{len(result.dataframe.columns):,}",
    )

    print(
        "Features:",
        f"{len(result.feature_columns):,}",
    )

    print(
        "Targets:",
        f"{len(result.target_columns):,}",
    )

    print(
        "Validation:",
        "PASS"
        if validation["valid"]
        else "FAIL",
    )

    print()
    print(
        "This audit does not save or modify "
        "the dataset."
    )


# ============================================================
# Main
# ============================================================

def main() -> None:

    print_section(
        "SMARTPARK AI - BIRMINGHAM ML DATASET AUDIT"
    )

    print(
        "Dataset root:",
        DATASET_ROOT,
    )

    print()
    print(
        "Building Birmingham source dataset..."
    )

    dataset_result = (
        build_birmingham_ml_dataset(
            dataset_root=DATASET_ROOT
        )
    )

    source_dataframe = (
        dataset_result.dataframe
    )

    audit_dataset_overview(
        source_dataframe
    )

    audit_duplicates(
        source_dataframe
    )

    audit_facility_coverage(
        source_dataframe
    )

    print_section(
        "RUNNING COMPLETE FEATURE PIPELINE"
    )

    result = build_feature_pipeline(
        source_dataframe
    )

    audit_pipeline_result(
        result
    )

    dataframe = result.dataframe

    audit_target_availability(
        dataframe
    )

    audit_target_values(
        dataframe
    )

    audit_target_exclusion_reasons(
        dataframe
    )

    audit_target_availability_by_facility(
        dataframe
    )

    audit_facility_target_counts(
        dataframe
    )

    audit_lag_availability(
        dataframe
    )

    audit_rolling_availability(
        dataframe
    )

    audit_feature_nulls(
        dataframe,
        result.feature_columns,
    )

    audit_feature_null_percentages(
        dataframe,
        result.feature_columns,
    )

    audit_infinite_values(
        dataframe,
        result.feature_columns,
    )

    audit_feature_dtypes(
        dataframe,
        result.feature_columns,
    )

    audit_constant_features(
        dataframe,
        result.feature_columns,
    )

    audit_leakage(
        result
    )

    validation = audit_pipeline_validation(
        result
    )

    print_final_summary(
        source_dataframe,
        result,
        validation,
    )


if __name__ == "__main__":
    main()