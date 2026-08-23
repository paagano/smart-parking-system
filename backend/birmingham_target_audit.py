from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.ml.data.dataset_builder import (
    build_birmingham_ml_dataset,
)


# ============================================================
# Configuration
# ============================================================

DATASET_ROOT = "../datasets/raw"

FACILITY_COLUMN = "source_facility_code"
TIMESTAMP_COLUMN = "normalized_at"

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

POSSIBLE_REASON_COLUMNS = (
    "target_exclusion_reason",
    "reason",
)

TOP_N = 20


# ============================================================
# Formatting helpers
# ============================================================

def print_section(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_subsection(title: str) -> None:
    print()
    print(f"--- {title} ---")


def pct(
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


def fmt_pct(value: float) -> str:
    return f"{value:6.2f}%"


# ============================================================
# Dataset loading
# ============================================================

def load_birmingham_dataset() -> pd.DataFrame:

    print_section(
        "SMARTPARK AI - BIRMINGHAM TARGET AUDIT"
    )

    print(
        "Dataset root:",
        DATASET_ROOT,
    )

    print()
    print(
        "Building Birmingham ML dataset..."
    )

    result = build_birmingham_ml_dataset(
        dataset_root=DATASET_ROOT,
    )

    dataframe = result.dataframe.copy()

    print(
        "Rows:",
        f"{len(dataframe):,}",
    )

    print(
        "Columns:",
        f"{len(dataframe.columns):,}",
    )

    return dataframe


# ============================================================
# Basic dataset audit
# ============================================================

def audit_basic_structure(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "1. DATASET STRUCTURE"
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

        timestamps = pd.to_datetime(
            dataframe[
                TIMESTAMP_COLUMN
            ],
            errors="coerce",
        )

        print(
            "First timestamp:",
            timestamps.min(),
        )

        print(
            "Last timestamp:",
            timestamps.max(),
        )

        print(
            "Invalid timestamps:",
            int(
                timestamps.isna().sum()
            ),
        )


# ============================================================
# Facility coverage
# ============================================================

def audit_facility_coverage(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "2. FACILITY OBSERVATION COVERAGE"
    )

    required = {
        FACILITY_COLUMN,
        TIMESTAMP_COLUMN,
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

    working = dataframe.copy()

    working[
        "__audit_timestamp"
    ] = pd.to_datetime(
        working[
            TIMESTAMP_COLUMN
        ],
        errors="coerce",
    )

    rows = []

    for (
        facility,
        group,
    ) in working.groupby(
        FACILITY_COLUMN,
        dropna=False,
    ):

        first_timestamp = (
            group[
                "__audit_timestamp"
            ].min()
        )

        last_timestamp = (
            group[
                "__audit_timestamp"
            ].max()
        )

        span_days = (
            (
                last_timestamp
                - first_timestamp
            )
            .total_seconds()
            / 86400.0
            if pd.notna(
                first_timestamp
            )
            and pd.notna(
                last_timestamp
            )
            else 0.0
        )

        expected_slots = (
            span_days * 48
        )

        observations = len(
            group
        )

        rows.append(
            {
                "facility":
                    facility,
                "observations":
                    observations,
                "first_timestamp":
                    first_timestamp,
                "last_timestamp":
                    last_timestamp,
                "span_days":
                    round(
                        span_days,
                        2,
                    ),
                "expected_30m_slots":
                    round(
                        expected_slots,
                        0,
                    ),
                "coverage_pct":
                    round(
                        pct(
                            observations,
                            expected_slots,
                        ),
                        2,
                    ),
            }
        )

    result = (
        pd.DataFrame(rows)
        .sort_values(
            "observations"
        )
    )

    print(
        result.to_string(
            index=False
        )
    )


# ============================================================
# Target availability overview
# ============================================================

def audit_target_availability(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "3. TARGET AVAILABILITY OVERVIEW"
    )

    total_rows = len(
        dataframe
    )

    for (
        target,
        availability,
    ) in zip(
        TARGET_COLUMNS,
        TARGET_AVAILABILITY_COLUMNS,
    ):

        print_subsection(
            target
        )

        if target not in dataframe.columns:

            print(
                "Target column: MISSING"
            )

            continue

        if (
            availability
            in dataframe.columns
        ):

            available = int(
                dataframe[
                    availability
                ]
                .fillna(False)
                .astype(bool)
                .sum()
            )

        else:

            available = int(
                dataframe[
                    target
                ]
                .notna()
                .sum()
            )

        unavailable = (
            total_rows
            - available
        )

        print(
            "Total rows:",
            f"{total_rows:,}",
        )

        print(
            "Available:",
            f"{available:,}",
            f"({fmt_pct(pct(available, total_rows))})",
        )

        print(
            "Unavailable:",
            f"{unavailable:,}",
            f"({fmt_pct(pct(unavailable, total_rows))})",
        )


# ============================================================
# Target value statistics
# ============================================================

def audit_target_values(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "4. TARGET VALUE STATISTICS"
    )

    for target in TARGET_COLUMNS:

        print_subsection(
            target
        )

        if target not in dataframe.columns:

            print(
                "Column missing."
            )

            continue

        values = pd.to_numeric(
            dataframe[target],
            errors="coerce",
        )

        non_null = int(
            values.notna().sum()
        )

        null_count = int(
            values.isna().sum()
        )

        print(
            "Usable values:",
            f"{non_null:,}",
        )

        print(
            "Missing values:",
            f"{null_count:,}",
        )

        if values.notna().any():

            print(
                "Minimum:",
                values.min(),
            )

            print(
                "Maximum:",
                values.max(),
            )

            print(
                "Mean:",
                values.mean(),
            )

            print(
                "Median:",
                values.median(),
            )

            print(
                "Std:",
                values.std(),
            )


# ============================================================
# Target exclusion reasons
# ============================================================

def find_reason_column(
    dataframe: pd.DataFrame,
) -> str | None:

    for column in POSSIBLE_REASON_COLUMNS:

        if column in dataframe.columns:
            return column

    return None


def audit_target_exclusion_reasons(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "5. TARGET EXCLUSION REASONS"
    )

    reason_column = (
        find_reason_column(
            dataframe
        )
    )

    if reason_column is None:

        print(
            "No target exclusion reason "
            "column found."
        )

        return

    print(
        "Reason column:",
        reason_column,
    )

    reasons = (
        dataframe[
            reason_column
        ]
        .fillna("<NULL>")
        .astype(str)
        .value_counts(
            dropna=False
        )
    )

    total_rows = len(
        dataframe
    )

    output = pd.DataFrame(
        {
            "count":
                reasons,
            "percentage":
                (
                    reasons
                    / total_rows
                    * 100.0
                ),
        }
    )

    output[
        "percentage"
    ] = output[
        "percentage"
    ].round(2)

    print()

    print(
        output.to_string()
    )


# ============================================================
# Target availability by facility
# ============================================================

def audit_target_availability_by_facility(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    print_section(
        "6. TARGET AVAILABILITY BY FACILITY"
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

        return pd.DataFrame()

    rows = []

    for (
        facility,
        group,
    ) in dataframe.groupby(
        FACILITY_COLUMN,
        dropna=False,
    ):

        row = {
            "facility":
                facility,
            "rows":
                len(group),
        }

        for availability in (
            TARGET_AVAILABILITY_COLUMNS
        ):

            available = int(
                group[
                    availability
                ]
                .fillna(False)
                .astype(bool)
                .sum()
            )

            short_name = (
                availability
                .replace(
                    "target_",
                    "",
                )
                .replace(
                    "_available",
                    "",
                )
            )

            row[
                f"{short_name}_available"
            ] = available

            row[
                f"{short_name}_pct"
            ] = round(
                pct(
                    available,
                    len(group),
                ),
                2,
            )

        rows.append(
            row
        )

    result = pd.DataFrame(
        rows
    )

    result = result.sort_values(
        "rows",
        ascending=False,
    )

    print(
        result.to_string(
            index=False
        )
    )

    return result


# ============================================================
# Usable target rows by facility
# ============================================================

def audit_usable_targets_by_facility(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:

    print_section(
        "7. USABLE TARGET ROWS BY FACILITY"
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

        return pd.DataFrame()

    rows = []

    for (
        facility,
        group,
    ) in dataframe.groupby(
        FACILITY_COLUMN,
        dropna=False,
    ):

        row = {
            "facility":
                facility,
            "rows":
                len(group),
        }

        for target in TARGET_COLUMNS:

            usable = int(
                group[target]
                .notna()
                .sum()
            )

            short_name = (
                target
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
            ] = round(
                pct(
                    usable,
                    len(group),
                ),
                2,
            )

        rows.append(
            row
        )

    result = pd.DataFrame(
        rows
    )

    result = result.sort_values(
        "rows",
        ascending=False,
    )

    print(
        result.to_string(
            index=False
        )
    )

    return result


# ============================================================
# NIA North investigation
# ============================================================

def audit_nia_north(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "8. NIA NORTH INVESTIGATION"
    )

    if FACILITY_COLUMN not in dataframe.columns:

        print(
            "Facility column missing."
        )

        return

    facilities = (
        dataframe[
            FACILITY_COLUMN
        ]
        .dropna()
        .astype(str)
        .unique()
    )

    nia_candidates = [
        facility
        for facility in facilities
        if "NIA" in facility.upper()
    ]

    if not nia_candidates:

        print(
            "No facility containing 'NIA' "
            "was found."
        )

        return

    print(
        "Matching facilities:",
        nia_candidates,
    )

    for facility in nia_candidates:

        print_subsection(
            facility
        )

        group = dataframe[
            dataframe[
                FACILITY_COLUMN
            ].astype(str)
            == facility
        ].copy()

        timestamps = pd.to_datetime(
            group[
                TIMESTAMP_COLUMN
            ],
            errors="coerce",
        )

        print(
            "Rows:",
            f"{len(group):,}",
        )

        print(
            "First timestamp:",
            timestamps.min(),
        )

        print(
            "Last timestamp:",
            timestamps.max(),
        )

        for target in TARGET_COLUMNS:

            if target not in group.columns:
                continue

            usable = int(
                group[target]
                .notna()
                .sum()
            )

            print(
                f"{target:45}: "
                f"{usable:,} "
                f"({fmt_pct(pct(usable, len(group)))})"
            )


# ============================================================
# Target availability by date
# ============================================================

def audit_target_availability_by_date(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "9. TARGET AVAILABILITY BY DATE"
    )

    if (
        TIMESTAMP_COLUMN
        not in dataframe.columns
    ):

        print(
            "Timestamp column missing."
        )

        return

    working = dataframe.copy()

    working[
        "__audit_date"
    ] = pd.to_datetime(
        working[
            TIMESTAMP_COLUMN
        ],
        errors="coerce",
    ).dt.date

    rows = []

    for date, group in (
        working.groupby(
            "__audit_date",
            dropna=False,
        )
    ):

        row = {
            "date":
                date,
            "rows":
                len(group),
        }

        for target in TARGET_COLUMNS:

            if target not in group.columns:
                continue

            usable = int(
                group[target]
                .notna()
                .sum()
            )

            short_name = (
                target
                .replace(
                    "target_",
                    "",
                )
            )

            row[
                short_name
                + "_usable"
            ] = usable

            row[
                short_name
                + "_pct"
            ] = round(
                pct(
                    usable,
                    len(group),
                ),
                2,
            )

        rows.append(
            row
        )

    result = pd.DataFrame(
        rows
    )

    print(
        result.to_string(
            index=False
        )
    )


# ============================================================
# Target availability by hour
# ============================================================

def audit_target_availability_by_hour(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "10. TARGET AVAILABILITY BY HOUR"
    )

    if (
        TIMESTAMP_COLUMN
        not in dataframe.columns
    ):

        print(
            "Timestamp column missing."
        )

        return

    working = dataframe.copy()

    working[
        "__audit_hour"
    ] = pd.to_datetime(
        working[
            TIMESTAMP_COLUMN
        ],
        errors="coerce",
    ).dt.hour

    rows = []

    for hour, group in (
        working.groupby(
            "__audit_hour",
            dropna=False,
        )
    ):

        row = {
            "hour":
                hour,
            "rows":
                len(group),
        }

        for target in TARGET_COLUMNS:

            if target not in group.columns:
                continue

            usable = int(
                group[target]
                .notna()
                .sum()
            )

            short_name = (
                target
                .replace(
                    "target_",
                    "",
                )
            )

            row[
                short_name
                + "_pct"
            ] = round(
                pct(
                    usable,
                    len(group),
                ),
                2,
            )

        rows.append(
            row
        )

    result = pd.DataFrame(
        rows
    )

    print(
        result.to_string(
            index=False
        )
    )


# ============================================================
# Target availability by day of week
# ============================================================

def audit_target_availability_by_weekday(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "11. TARGET AVAILABILITY BY DAY OF WEEK"
    )

    if (
        TIMESTAMP_COLUMN
        not in dataframe.columns
    ):

        print(
            "Timestamp column missing."
        )

        return

    working = dataframe.copy()

    working[
        "__audit_weekday"
    ] = pd.to_datetime(
        working[
            TIMESTAMP_COLUMN
        ],
        errors="coerce",
    ).dt.day_name()

    weekday_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]

    rows = []

    for weekday in weekday_order:

        group = working[
            working[
                "__audit_weekday"
            ]
            == weekday
        ]

        if group.empty:
            continue

        row = {
            "weekday":
                weekday,
            "rows":
                len(group),
        }

        for target in TARGET_COLUMNS:

            if target not in group.columns:
                continue

            usable = int(
                group[target]
                .notna()
                .sum()
            )

            short_name = (
                target
                .replace(
                    "target_",
                    "",
                )
            )

            row[
                short_name
                + "_pct"
            ] = round(
                pct(
                    usable,
                    len(group),
                ),
                2,
            )

        rows.append(
            row
        )

    result = pd.DataFrame(
        rows
    )

    print(
        result.to_string(
            index=False
        )
    )


# ============================================================
# Trainable row summary
# ============================================================

def audit_trainable_row_counts(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "12. TRAINABLE ROW COUNTS"
    )

    total_rows = len(
        dataframe
    )

    for target in TARGET_COLUMNS:

        if target not in dataframe.columns:
            continue

        usable = int(
            dataframe[target]
            .notna()
            .sum()
        )

        print(
            f"{target:45}: "
            f"{usable:,} / "
            f"{total_rows:,} "
            f"({fmt_pct(pct(usable, total_rows))})"
        )

    # Rows where all four targets are available.
    existing_targets = [
        target
        for target in TARGET_COLUMNS
        if target in dataframe.columns
    ]

    if existing_targets:

        all_targets_available = (
            dataframe[
                existing_targets
            ]
            .notna()
            .all(
                axis=1
            )
        )

        count = int(
            all_targets_available.sum()
        )

        print()

        print(
            "Rows with ALL targets available:",
            f"{count:,}",
            f"({fmt_pct(pct(count, total_rows))})",
        )


# ============================================================
# Target range validation
# ============================================================

def audit_target_ranges(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "13. TARGET RANGE VALIDATION"
    )

    for target in TARGET_COLUMNS:

        if target not in dataframe.columns:
            continue

        values = pd.to_numeric(
            dataframe[target],
            errors="coerce",
        ).dropna()

        if values.empty:
            continue

        below_zero = int(
            (values < 0).sum()
        )

        above_one = int(
            (values > 1).sum()
        )

        print(
            f"{target:45}: "
            f"<0={below_zero:,} "
            f">1={above_one:,}"
        )


# ============================================================
# Current observation availability
# ============================================================

def audit_current_observation_availability(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "14. CURRENT OBSERVATION AVAILABILITY"
    )

    candidate_columns = (
        "observation_present",
        "is_eligible_for_sequence",
        "is_data_gap",
        "is_operational_gap",
        "gap_status",
        "quality_status",
    )

    existing = [
        column
        for column in candidate_columns
        if column in dataframe.columns
    ]

    if not existing:

        print(
            "No current-observation "
            "diagnostic columns found."
        )

        return

    for column in existing:

        print_subsection(
            column
        )

        print(
            dataframe[column]
            .value_counts(
                dropna=False
            )
            .head(TOP_N)
            .to_string()
        )


# ============================================================
# Target availability by facility
# with current observation diagnostics
# ============================================================

def audit_missing_targets_by_facility(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "15. MISSING TARGETS BY FACILITY"
    )

    if FACILITY_COLUMN not in dataframe.columns:
        return

    rows = []

    for (
        facility,
        group,
    ) in dataframe.groupby(
        FACILITY_COLUMN,
        dropna=False,
    ):

        row = {
            "facility":
                facility,
            "rows":
                len(group),
        }

        for target in TARGET_COLUMNS:

            if target not in group.columns:
                continue

            missing = int(
                group[target]
                .isna()
                .sum()
            )

            short_name = (
                target
                .replace(
                    "target_",
                    "",
                )
            )

            row[
                short_name
                + "_missing"
            ] = missing

        rows.append(
            row
        )

    result = pd.DataFrame(
        rows
    )

    print(
        result.to_string(
            index=False
        )
    )


# ============================================================
# Final recommendations
# ============================================================

def print_audit_interpretation(
    dataframe: pd.DataFrame,
) -> None:

    print_section(
        "16. AUDIT INTERPRETATION"
    )

    total_rows = len(
        dataframe
    )

    print(
        "Total observations:",
        f"{total_rows:,}",
    )

    print()

    for target in TARGET_COLUMNS:

        if target not in dataframe.columns:
            continue

        usable = int(
            dataframe[target]
            .notna()
            .sum()
        )

        print(
            f"{target}: "
            f"{usable:,} usable training rows "
            f"({pct(usable, total_rows):.2f}%)"
        )

    print()

    print(
        "IMPORTANT:"
    )

    print(
        "This script is diagnostic only."
    )

    print(
        "It does NOT drop rows."
    )

    print(
        "It does NOT fill target values."
    )

    print(
        "It does NOT modify the feature pipeline."
    )

    print(
        "It does NOT create train/validation/test splits."
    )

    print()

    print(
        "The next stage should use the audit findings "
        "to construct target-specific supervised datasets."
    )


# ============================================================
# Main
# ============================================================

def main() -> None:

    dataframe = (
        load_birmingham_dataset()
    )

    audit_basic_structure(
        dataframe
    )

    audit_facility_coverage(
        dataframe
    )

    audit_current_observation_availability(
        dataframe
    )

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

    audit_usable_targets_by_facility(
        dataframe
    )

    audit_nia_north(
        dataframe
    )

    audit_target_availability_by_date(
        dataframe
    )

    audit_target_availability_by_hour(
        dataframe
    )

    audit_target_availability_by_weekday(
        dataframe
    )

    audit_trainable_row_counts(
        dataframe
    )

    audit_target_ranges(
        dataframe
    )

    audit_missing_targets_by_facility(
        dataframe
    )

    print_audit_interpretation(
        dataframe
    )

    print_section(
        "BIRMINGHAM TARGET AUDIT COMPLETED"
    )

    print(
        "No source data was modified."
    )

    print(
        "No feature data was saved."
    )

    print(
        "No rows were dropped."
    )

    print()


if __name__ == "__main__":
    main()