"""
SmartPark AI
Birmingham XGBoost Feature Importance & Prediction-Time Safety Audit

Purpose
-------
Audit the strongest XGBoost features after the initial Birmingham benchmark.

The audit is deliberately READ-ONLY.

It does NOT:
    - modify the feature pipeline
    - modify persisted Parquet datasets
    - modify the XGBoost model
    - retrain XGBoost
    - load the test dataset
    - perform hyperparameter tuning

It evaluates the strongest features against the persisted training dataset
and the existing feature definitions.

Primary objectives
------------------
1. Load the persisted XGBoost feature importance results.
2. Identify the strongest features.
3. Classify features into logical families.
4. Inspect feature values in the persisted training dataset.
5. Determine whether features are directly or indirectly target-derived.
6. Check whether the feature values are consistent with prediction-time
   information.
7. Specifically investigate demand_class_code and related demand features.
8. Produce an audit report for the next ablation/tuning stage.

IMPORTANT
---------
This audit does not claim semantic safety merely because a feature is
mathematically correlated with current occupancy.

The final classification is based on:
    - feature naming
    - known feature pipeline structure
    - dependency/source columns where identifiable
    - persisted data behaviour
    - target relationship

Any item that cannot be conclusively determined is reported as
"REQUIRES_SOURCE_REVIEW" rather than guessed.
"""

from __future__ import annotations

import json
import math
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ============================================================================
# PATHS
# ============================================================================

BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_ROOT.parent

DATASET_ROOT = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
)

TARGET_NAME = "target_occupancy_rate_30m"

TRAIN_FILE = (
    DATASET_ROOT
    / TARGET_NAME
    / "train.parquet"
)

VALIDATION_FILE = (
    DATASET_ROOT
    / TARGET_NAME
    / "validation.parquet"
)

IMPORTANCE_FILE = (
    DATASET_ROOT
    / "xgboost_benchmark"
    / "xgboost_feature_importance.csv"
)

BENCHMARK_RESULTS_FILE = (
    DATASET_ROOT
    / "xgboost_benchmark"
    / "xgboost_benchmark_results.json"
)

OUTPUT_DIR = (
    DATASET_ROOT
    / "xgboost_feature_importance_audit"
)

OUTPUT_JSON = (
    OUTPUT_DIR
    / "feature_importance_audit.json"
)

OUTPUT_CSV = (
    OUTPUT_DIR
    / "feature_importance_audit.csv"
)

SUMMARY_FILE = (
    OUTPUT_DIR
    / "feature_importance_audit_summary.txt"
)


# ============================================================================
# CONTRACTS
# ============================================================================

METADATA_COLUMNS = {
    "source_facility_code",
    "normalized_at",
    "observation_present",
    "gap_status",
    "is_operational_gap",
    "is_data_gap",
    "sequence_break",
    "is_eligible_for_sequence",
    "quality_status",
    "quality_flags",
    "source",
    "target_exclusion_reason",
}

TARGET_COLUMNS = {
    "target_occupancy_rate_30m",
    "target_occupancy_rate_1h",
    "target_occupancy_rate_2h",
    "target_tomorrow_morning_demand",
}

TARGET_AVAILABILITY_COLUMNS = {
    "target_30m_available",
    "target_1h_available",
    "target_2h_available",
    "target_tomorrow_morning_available",
}


# ============================================================================
# FEATURE GROUP DEFINITIONS
# ============================================================================

FEATURE_GROUP_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    (
        "temporal",
        (
            "year",
            "month",
            "quarter",
            "day_of_month",
            "day_of_year",
            "week_of_year",
            "day_of_week",
            "hour",
            "minute",
            "half_hour",
            "time_slot",
            "minutes_since",
            "is_weekday",
            "is_weekend",
            "is_monday",
            "is_tuesday",
            "is_wednesday",
            "is_thursday",
            "is_friday",
            "is_saturday",
            "is_sunday",
            "hour_sin",
            "hour_cos",
            "day_of_week_sin",
            "day_of_week_cos",
            "day_of_year_sin",
            "day_of_year_cos",
        ),
    ),
    (
        "calendar",
        (
            "calendar_",
            "is_month_start",
            "is_month_end",
            "days_to_month_end",
            "is_quarter_start",
            "is_quarter_end",
            "is_quarter_start_month",
            "is_quarter_end_month",
            "is_year_start",
            "is_year_end",
        ),
    ),
    (
        "occupancy",
        (
            "occupancy",
            "occupied_",
            "capacity_",
            "vacancy",
            "available_ratio",
            "availability_rate",
            "remaining_capacity",
            "is_empty",
            "is_low_occupancy",
            "is_moderate_occupancy",
            "is_high_occupancy",
            "is_near_full",
            "is_full",
        ),
    ),
    (
        "demand",
        (
            "demand",
        ),
    ),
    (
        "lag",
        (
            "_lag_",
            "_lag",
        ),
    ),
    (
        "rolling",
        (
            "_roll_",
            "_rolling_",
            "rolling_",
        ),
    ),
]


# ============================================================================
# FEATURES REQUIRING PARTICULAR ATTENTION
# ============================================================================

PRIORITY_FEATURES = [
    "demand_class_code",
    "availability_rate",
    "available_ratio",
    "calculated_demand_level",
    "occupied_ratio",
    "remaining_capacity_ratio",
    "capacity_utilization",
    "is_moderate_occupancy",
    "demand_pressure",
    "demand_level",
]


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class FeatureAudit:
    rank: int
    feature: str
    importance: float
    importance_type: str

    feature_group: str

    dtype: str
    numeric: bool
    categorical: bool

    train_rows: int
    train_non_null: int
    train_nulls: int
    train_unique_values: int

    validation_non_null: int | None
    validation_nulls: int | None
    validation_unique_values: int | None

    train_min: float | None
    train_max: float | None
    train_mean: float | None

    validation_min: float | None
    validation_max: float | None
    validation_mean: float | None

    constant_feature: bool
    train_validation_schema_match: bool

    target_correlation: float | None

    target_dependency_status: str
    prediction_time_status: str
    future_lookup_status: str
    audit_status: str

    notes: list[str]


# ============================================================================
# UTILITIES
# ============================================================================


def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def safe_float(value: Any) -> float | None:

    try:

        if value is None:
            return None

        value = float(value)

        if not math.isfinite(value):
            return None

        return value

    except (TypeError, ValueError):

        return None


def load_json(path: Path) -> dict[str, Any]:

    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:

        return json.load(handle)


def feature_group(feature: str) -> str:

    name = str(feature)

    for group, patterns in FEATURE_GROUP_PATTERNS:

        for pattern in patterns:

            if pattern in name:
                return group

    return "other"


def is_categorical(feature: str) -> bool:

    return feature in {
        "occupancy_level",
        "demand_class",
    }


def is_target_like(feature: str) -> bool:

    lowered = feature.lower()

    target_terms = (
        "target_",
        "future_",
        "next_",
        "tomorrow_",
    )

    return lowered.startswith(
        target_terms
    )


def is_future_named_feature(feature: str) -> bool:

    lowered = feature.lower()

    future_terms = (
        "future",
        "next_",
        "tomorrow",
        "forward",
        "lead_",
    )

    return any(
        term in lowered
        for term in future_terms
    )


def is_lag_or_rolling(feature: str) -> bool:

    lowered = feature.lower()

    return (
        "_lag" in lowered
        or "_roll" in lowered
        or "rolling_" in lowered
    )


def numeric_series(
    series: pd.Series,
) -> pd.Series:

    return pd.to_numeric(
        series,
        errors="coerce",
    )


def finite_numeric_values(
    series: pd.Series,
) -> np.ndarray:

    values = numeric_series(
        series
    ).to_numpy(
        dtype=float
    )

    return values[
        np.isfinite(values)
    ]


def safe_correlation(
    feature: pd.Series,
    target: pd.Series,
) -> float | None:

    x = numeric_series(
        feature
    )

    y = numeric_series(
        target
    )

    frame = pd.DataFrame(
        {
            "x": x,
            "y": y,
        }
    ).dropna()

    if len(frame) < 2:
        return None

    if frame["x"].nunique() <= 1:
        return None

    if frame["y"].nunique() <= 1:
        return None

    try:

        value = frame["x"].corr(
            frame["y"]
        )

        return safe_float(
            value
        )

    except Exception:

        return None


# ============================================================================
# LOAD VALIDATION
# ============================================================================


def validate_required_files() -> None:

    required = [
        TRAIN_FILE,
        VALIDATION_FILE,
        IMPORTANCE_FILE,
    ]

    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]

    if missing:

        raise FileNotFoundError(
            "Required audit files are missing:\n"
            + "\n".join(missing)
        )


def load_datasets() -> tuple[pd.DataFrame, pd.DataFrame]:

    print_section(
        "LOADING PERSISTED DATASETS"
    )

    print(
        f"Training file:\n  {TRAIN_FILE}"
    )

    print(
        f"Validation file:\n  {VALIDATION_FILE}"
    )

    train = pd.read_parquet(
        TRAIN_FILE
    )

    validation = pd.read_parquet(
        VALIDATION_FILE
    )

    print(
        f"Training rows      : {len(train):,}"
    )

    print(
        f"Validation rows    : {len(validation):,}"
    )

    print(
        f"Training columns   : {len(train.columns):,}"
    )

    print(
        f"Validation columns : {len(validation.columns):,}"
    )

    return train, validation


# ============================================================================
# IMPORTANCE LOADING
# ============================================================================


def load_importance() -> pd.DataFrame:

    print_section(
        "LOADING XGBOOST FEATURE IMPORTANCE"
    )

    print(
        f"Importance file:\n  {IMPORTANCE_FILE}"
    )

    importance = pd.read_csv(
        IMPORTANCE_FILE
    )

    required_columns = {
        "rank",
        "feature",
        "importance",
        "importance_type",
    }

    missing = (
        required_columns
        - set(importance.columns)
    )

    if missing:

        raise ValueError(
            "Feature importance file is missing "
            f"required columns: {sorted(missing)}"
        )

    importance = (
        importance
        .sort_values(
            "rank"
        )
        .reset_index(
            drop=True
        )
    )

    print(
        f"Importance rows : {len(importance):,}"
    )

    print()
    print(
        "Top 20 features:"
    )

    print(
        importance.head(20).to_string(
            index=False
        )
    )

    return importance


# ============================================================================
# FEATURE DEPENDENCY CLASSIFICATION
# ============================================================================


def classify_target_dependency(
    feature: str,
) -> tuple[str, list[str]]:

    notes: list[str] = []

    lowered = feature.lower()

    if feature in TARGET_COLUMNS:

        return (
            "TARGET_COLUMN",
            [
                "Feature is itself a target column."
            ],
        )

    if is_target_like(feature):

        return (
            "SUSPICIOUS_TARGET_NAMING",
            [
                "Feature name suggests future or target information."
            ],
        )

    if is_future_named_feature(feature):

        return (
            "REQUIRES_SOURCE_REVIEW",
            [
                "Feature name contains future-looking terminology."
            ],
        )

    # Explicitly safe naming families.
    if is_lag_or_rolling(feature):

        notes.append(
            "Feature appears to be historical lag/rolling derived."
        )

        return (
            "NO_DIRECT_TARGET_DEPENDENCY_IDENTIFIED",
            notes,
        )

    # Demand / occupancy features are deliberately not automatically
    # classified as safe because their implementation must be reviewed.
    if (
        "demand" in lowered
        or "occupancy" in lowered
        or "availability" in lowered
        or "occupied" in lowered
    ):

        notes.append(
            "Feature is derived from occupancy/demand/availability "
            "information and requires source-level review."
        )

        return (
            "REQUIRES_SOURCE_REVIEW",
            notes,
        )

    return (
        "NO_DIRECT_TARGET_DEPENDENCY_IDENTIFIED",
        notes,
    )


def classify_prediction_time(
    feature: str,
) -> tuple[str, list[str]]:

    notes: list[str] = []

    lowered = feature.lower()

    if is_future_named_feature(feature):

        return (
            "SUSPICIOUS",
            [
                "Feature name indicates possible future information."
            ],
        )

    if (
        "_lag" in lowered
        or "_roll" in lowered
        or "rolling_" in lowered
    ):

        notes.append(
            "Historical feature family based on naming."
        )

        return (
            "LIKELY_AVAILABLE_AT_PREDICTION_TIME",
            notes,
        )

    if feature in {
        "hour",
        "minute",
        "day_of_week",
        "day_of_month",
        "day_of_year",
        "month",
        "quarter",
        "is_weekday",
        "is_weekend",
    }:

        return (
            "AVAILABLE_AT_PREDICTION_TIME",
            [
                "Calendar/time feature."
            ],
        )

    if (
        "occupancy" in lowered
        or "availability" in lowered
        or "occupied" in lowered
        or "demand" in lowered
    ):

        return (
            "REQUIRES_SOURCE_REVIEW",
            [
                "Current operational feature requires "
                "verification against inference-time availability."
            ],
        )

    return (
        "REQUIRES_SOURCE_REVIEW",
        notes,
    )


def classify_future_lookup(
    feature: str,
) -> str:

    if is_future_named_feature(feature):

        return "POSSIBLE_FUTURE_LOOKUP"

    if is_lag_or_rolling(feature):

        return "NO_FUTURE_LOOKUP_BY_NAMING"

    return "NOT_DETERMINED_FROM_NAME"


# ============================================================================
# FEATURE STATISTICS
# ============================================================================


def feature_statistics(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    feature: str,
) -> dict[str, Any]:

    train_series = train[feature]

    validation_series = validation[feature]

    numeric = (
        pd.api.types.is_numeric_dtype(
            train_series
        )
    )

    if numeric:

        train_values = finite_numeric_values(
            train_series
        )

        validation_values = finite_numeric_values(
            validation_series
        )

        train_min = (
            safe_float(
                np.min(train_values)
            )
            if len(train_values)
            else None
        )

        train_max = (
            safe_float(
                np.max(train_values)
            )
            if len(train_values)
            else None
        )

        train_mean = (
            safe_float(
                np.mean(train_values)
            )
            if len(train_values)
            else None
        )

        validation_min = (
            safe_float(
                np.min(validation_values)
            )
            if len(validation_values)
            else None
        )

        validation_max = (
            safe_float(
                np.max(validation_values)
            )
            if len(validation_values)
            else None
        )

        validation_mean = (
            safe_float(
                np.mean(validation_values)
            )
            if len(validation_values)
            else None
        )

    else:

        train_min = None
        train_max = None
        train_mean = None

        validation_min = None
        validation_max = None
        validation_mean = None

    return {
        "dtype": str(
            train_series.dtype
        ),
        "numeric": numeric,
        "categorical": is_categorical(
            feature
        ),
        "train_rows": len(train_series),
        "train_non_null": int(
            train_series.notna().sum()
        ),
        "train_nulls": int(
            train_series.isna().sum()
        ),
        "train_unique_values": int(
            train_series.nunique(
                dropna=True
            )
        ),
        "validation_non_null": int(
            validation_series.notna().sum()
        ),
        "validation_nulls": int(
            validation_series.isna().sum()
        ),
        "validation_unique_values": int(
            validation_series.nunique(
                dropna=True
            )
        ),
        "train_min": train_min,
        "train_max": train_max,
        "train_mean": train_mean,
        "validation_min": validation_min,
        "validation_max": validation_max,
        "validation_mean": validation_mean,
        "constant_feature": (
            train_series.nunique(
                dropna=True
            )
            <= 1
        ),
        "train_validation_schema_match": (
            train_series.dtype
            == validation_series.dtype
        ),
    }


# ============================================================================
# FEATURE AUDIT
# ============================================================================


def audit_features(
    importance: pd.DataFrame,
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> list[FeatureAudit]:

    print_section(
        "AUDITING TOP FEATURES"
    )

    if TARGET_NAME not in train.columns:

        raise ValueError(
            f"Target column not found: {TARGET_NAME}"
        )

    target = train[
        TARGET_NAME
    ]

    audits: list[FeatureAudit] = []

    for _, row in importance.iterrows():

        feature = str(
            row["feature"]
        )

        if feature not in train.columns:

            audit = FeatureAudit(
                rank=int(row["rank"]),
                feature=feature,
                importance=float(
                    row["importance"]
                ),
                importance_type=str(
                    row["importance_type"]
                ),
                feature_group=feature_group(
                    feature
                ),
                dtype="MISSING",
                numeric=False,
                categorical=is_categorical(
                    feature
                ),
                train_rows=0,
                train_non_null=0,
                train_nulls=0,
                train_unique_values=0,
                validation_non_null=None,
                validation_nulls=None,
                validation_unique_values=None,
                train_min=None,
                train_max=None,
                train_mean=None,
                validation_min=None,
                validation_max=None,
                validation_mean=None,
                constant_feature=False,
                train_validation_schema_match=False,
                target_correlation=None,
                target_dependency_status="MISSING_FEATURE",
                prediction_time_status="UNKNOWN",
                future_lookup_status="UNKNOWN",
                audit_status="FAIL",
                notes=[
                    "Feature appears in importance registry "
                    "but not in persisted training dataset."
                ],
            )

            audits.append(
                audit
            )

            continue

        stats = feature_statistics(
            train,
            validation,
            feature,
        )

        dependency_status, dependency_notes = (
            classify_target_dependency(
                feature
            )
        )

        prediction_status, prediction_notes = (
            classify_prediction_time(
                feature
            )
        )

        future_status = classify_future_lookup(
            feature
        )

        correlation = safe_correlation(
            train[feature],
            target,
        )

        notes = (
            dependency_notes
            + prediction_notes
        )

        if stats["constant_feature"]:

            notes.append(
                "Feature is constant in training data."
            )

        if (
            stats["train_validation_schema_match"]
            is False
        ):

            notes.append(
                "Training and validation dtypes differ."
            )

        if stats["train_nulls"] > 0:

            notes.append(
                "Training data contains missing values."
            )

        if stats["validation_nulls"] > 0:

            notes.append(
                "Validation data contains missing values."
            )

        if (
            feature
            in PRIORITY_FEATURES
        ):

            notes.append(
                "Priority feature selected for manual review."
            )

        if (
            dependency_status
            == "TARGET_COLUMN"
        ):

            status = "FAIL"

        elif (
            dependency_status
            == "SUSPICIOUS_TARGET_NAMING"
        ):

            status = "REVIEW"

        elif (
            prediction_status
            == "SUSPICIOUS"
        ):

            status = "REVIEW"

        elif (
            dependency_status
            == "REQUIRES_SOURCE_REVIEW"
            or prediction_status
            == "REQUIRES_SOURCE_REVIEW"
        ):

            status = "REVIEW"

        else:

            status = "PASS"

        audit = FeatureAudit(
            rank=int(
                row["rank"]
            ),
            feature=feature,
            importance=float(
                row["importance"]
            ),
            importance_type=str(
                row["importance_type"]
            ),
            feature_group=feature_group(
                feature
            ),
            dtype=stats["dtype"],
            numeric=stats["numeric"],
            categorical=stats["categorical"],
            train_rows=stats["train_rows"],
            train_non_null=stats["train_non_null"],
            train_nulls=stats["train_nulls"],
            train_unique_values=stats[
                "train_unique_values"
            ],
            validation_non_null=stats[
                "validation_non_null"
            ],
            validation_nulls=stats[
                "validation_nulls"
            ],
            validation_unique_values=stats[
                "validation_unique_values"
            ],
            train_min=stats["train_min"],
            train_max=stats["train_max"],
            train_mean=stats["train_mean"],
            validation_min=stats[
                "validation_min"
            ],
            validation_max=stats[
                "validation_max"
            ],
            validation_mean=stats[
                "validation_mean"
            ],
            constant_feature=stats[
                "constant_feature"
            ],
            train_validation_schema_match=stats[
                "train_validation_schema_match"
            ],
            target_correlation=correlation,
            target_dependency_status=dependency_status,
            prediction_time_status=prediction_status,
            future_lookup_status=future_status,
            audit_status=status,
            notes=notes,
        )

        audits.append(
            audit
        )

    return audits


# ============================================================================
# PRIORITY FEATURE REVIEW
# ============================================================================


def print_priority_review(
    audits: list[FeatureAudit],
) -> None:

    print_section(
        "PRIORITY FEATURE REVIEW"
    )

    by_name = {
        audit.feature: audit
        for audit in audits
    }

    for feature in PRIORITY_FEATURES:

        audit = by_name.get(
            feature
        )

        if audit is None:

            print()
            print(
                f"{feature:<35} NOT PRESENT IN IMPORTANCE FILE"
            )

            continue

        print()
        print(
            f"{feature}"
        )

        print(
            f"  Rank                    : {audit.rank}"
        )

        print(
            f"  Importance              : "
            f"{audit.importance:.6f}"
        )

        print(
            f"  Feature group           : "
            f"{audit.feature_group}"
        )

        print(
            f"  Data type               : "
            f"{audit.dtype}"
        )

        print(
            f"  Training nulls          : "
            f"{audit.train_nulls:,}"
        )

        print(
            f"  Training unique values  : "
            f"{audit.train_unique_values:,}"
        )

        print(
            f"  Training mean           : "
            f"{audit.train_mean}"
        )

        print(
            f"  Target correlation      : "
            f"{audit.target_correlation}"
        )

        print(
            f"  Target dependency       : "
            f"{audit.target_dependency_status}"
        )

        print(
            f"  Prediction-time status  : "
            f"{audit.prediction_time_status}"
        )

        print(
            f"  Future lookup status    : "
            f"{audit.future_lookup_status}"
        )

        print(
            f"  Audit status            : "
            f"{audit.audit_status}"
        )

        for note in audit.notes:

            print(
                f"  NOTE                    : {note}"
            )


# ============================================================================
# TOP FEATURE SUMMARY
# ============================================================================


def print_top_feature_summary(
    audits: list[FeatureAudit],
) -> None:

    print_section(
        "TOP FEATURE SUMMARY"
    )

    rows = []

    for audit in audits[:20]:

        rows.append(
            {
                "rank": audit.rank,
                "feature": audit.feature,
                "group": audit.feature_group,
                "importance": audit.importance,
                "correlation": audit.target_correlation,
                "dependency": audit.target_dependency_status,
                "prediction_time": audit.prediction_time_status,
                "status": audit.audit_status,
            }
        )

    if rows:

        frame = pd.DataFrame(
            rows
        )

        print(
            frame.to_string(
                index=False
            )
        )


# ============================================================================
# GROUP SUMMARY
# ============================================================================


def print_group_summary(
    audits: list[FeatureAudit],
) -> None:

    print_section(
        "FEATURE IMPORTANCE BY GROUP"
    )

    frame = pd.DataFrame(
        [
            {
                "feature": audit.feature,
                "group": audit.feature_group,
                "importance": audit.importance,
            }
            for audit in audits
        ]
    )

    if frame.empty:
        return

    summary = (
        frame
        .groupby(
            "group",
            as_index=False,
        )
        .agg(
            feature_count=(
                "feature",
                "count",
            ),
            total_importance=(
                "importance",
                "sum",
            ),
            max_importance=(
                "importance",
                "max",
            ),
        )
        .sort_values(
            "total_importance",
            ascending=False,
        )
    )

    total = summary[
        "total_importance"
    ].sum()

    if total > 0:

        summary[
            "importance_share_pct"
        ] = (
            summary[
                "total_importance"
            ]
            / total
            * 100.0
        )

    print(
        summary.to_string(
            index=False
        )
    )


# ============================================================================
# TARGET CORRELATION WARNINGS
# ============================================================================


def print_high_correlation_review(
    audits: list[FeatureAudit],
) -> None:

    print_section(
        "HIGH TARGET-CORRELATION REVIEW"
    )

    candidates = [
        audit
        for audit in audits
        if audit.target_correlation is not None
        and abs(
            audit.target_correlation
        ) >= 0.90
    ]

    if not candidates:

        print(
            "No audited feature has absolute target "
            "correlation >= 0.90."
        )

        return

    print(
        "IMPORTANT: High correlation does NOT prove leakage."
    )

    print(
        "These features require source-level review."
    )

    print()

    for audit in candidates:

        print(
            f"{audit.feature:<40}"
            f"corr={audit.target_correlation:.6f}"
            f"  status={audit.audit_status}"
        )


# ============================================================================
# SOURCE CODE REVIEW
# ============================================================================


def inspect_feature_source_files() -> dict[str, Any]:

    print_section(
        "FEATURE SOURCE FILE CHECK"
    )

    source_files = {
        "demand_features.py": (
            BACKEND_ROOT
            / "app"
            / "ml"
            / "features"
            / "demand_features.py"
        ),
        "occupancy_features.py": (
            BACKEND_ROOT
            / "app"
            / "ml"
            / "features"
            / "occupancy_features.py"
        ),
        "feature_pipeline.py": (
            BACKEND_ROOT
            / "app"
            / "ml"
            / "features"
            / "feature_pipeline.py"
        ),
    }

    result: dict[str, Any] = {}

    for name, path in source_files.items():

        exists = path.exists()

        result[name] = {
            "path": str(path),
            "exists": exists,
        }

        print(
            f"{name:<25} : "
            f"{'FOUND' if exists else 'NOT FOUND'}"
        )

    return result


# ============================================================================
# SIMPLE SOURCE TEXT SEARCH
# ============================================================================


def search_source_for_feature(
    feature: str,
) -> list[dict[str, Any]]:

    files = [
        BACKEND_ROOT
        / "app"
        / "ml"
        / "features"
        / "demand_features.py",

        BACKEND_ROOT
        / "app"
        / "ml"
        / "features"
        / "occupancy_features.py",

        BACKEND_ROOT
        / "app"
        / "ml"
        / "features"
        / "feature_pipeline.py",
    ]

    matches: list[dict[str, Any]] = []

    for path in files:

        if not path.exists():
            continue

        try:

            text = path.read_text(
                encoding="utf-8"
            )

        except UnicodeDecodeError:

            text = path.read_text(
                encoding="utf-8-sig"
            )

        lines = text.splitlines()

        for line_number, line in enumerate(
            lines,
            start=1,
        ):

            if feature in line:

                matches.append(
                    {
                        "file": str(path),
                        "line": line_number,
                        "text": line.strip(),
                    }
                )

    return matches


def print_source_search_for_priority_features() -> dict[str, Any]:

    print_section(
        "SOURCE IMPLEMENTATION SEARCH"
    )

    result: dict[str, Any] = {}

    for feature in PRIORITY_FEATURES:

        matches = search_source_for_feature(
            feature
        )

        result[feature] = matches

        print()
        print(
            f"{feature}:"
        )

        if not matches:

            print(
                "  No direct source-code occurrence found."
            )

            continue

        for match in matches[:10]:

            print(
                f"  {Path(match['file']).name}:"
                f"{match['line']}: "
                f"{match['text']}"
            )

        if len(matches) > 10:

            print(
                f"  ... {len(matches) - 10} additional matches"
            )

    return result


# ============================================================================
# BENCHMARK RESULT SUMMARY
# ============================================================================


def load_benchmark_results() -> dict[str, Any] | None:

    if not BENCHMARK_RESULTS_FILE.exists():

        return None

    try:

        return load_json(
            BENCHMARK_RESULTS_FILE
        )

    except Exception:

        return None


def print_benchmark_context() -> None:

    print_section(
        "BENCHMARK CONTEXT"
    )

    results = load_benchmark_results()

    if not results:

        print(
            "Benchmark JSON not available."
        )

        return

    # Handle common possible structures without making assumptions
    # about the exact benchmark JSON schema.

    for key in (
        "target",
        "model_name",
        "mae",
        "rmse",
        "r2",
        "mape",
    ):

        if key in results:

            print(
                f"{key:<30}: "
                f"{results[key]}"
            )


# ============================================================================
# AUDIT RESULT
# ============================================================================


def determine_overall_status(
    audits: list[FeatureAudit],
) -> tuple[str, list[str]]:

    failures: list[str] = []
    reviews: list[str] = []

    for audit in audits:

        if audit.audit_status == "FAIL":

            failures.append(
                audit.feature
            )

        elif audit.audit_status == "REVIEW":

            reviews.append(
                audit.feature
            )

    if failures:

        return (
            "FAIL",
            failures,
        )

    if reviews:

        return (
            "REVIEW_REQUIRED",
            reviews,
        )

    return (
        "PASS",
        [],
    )


# ============================================================================
# PERSISTENCE
# ============================================================================


def persist_results(
    audits: list[FeatureAudit],
    source_search: dict[str, Any],
    source_files: dict[str, Any],
    overall_status: str,
    review_features: list[str],
) -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ------------------------------------------------------------------------
    # JSON
    # ------------------------------------------------------------------------

    payload = {
        "audit_name": (
            "Birmingham XGBoost Feature Importance "
            "and Prediction-Time Safety Audit"
        ),
        "dataset": "birmingham",
        "target": TARGET_NAME,
        "read_only": True,
        "test_dataset_loaded": False,
        "test_dataset_modified": False,
        "training_dataset_modified": False,
        "validation_dataset_modified": False,
        "feature_pipeline_modified": False,
        "overall_status": overall_status,
        "review_features": review_features,
        "priority_features": PRIORITY_FEATURES,
        "feature_audits": [
            asdict(audit)
            for audit in audits
        ],
        "source_files": source_files,
        "source_search": source_search,
    }

    with OUTPUT_JSON.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            payload,
            handle,
            indent=2,
            default=str,
        )

    # ------------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------------

    frame = pd.DataFrame(
        [
            asdict(audit)
            for audit in audits
        ]
    )

    if not frame.empty:

        frame["notes"] = frame[
            "notes"
        ].apply(
            lambda values: " | ".join(
                values
            )
        )

    frame.to_csv(
        OUTPUT_CSV,
        index=False,
    )

    # ------------------------------------------------------------------------
    # Human-readable summary
    # ------------------------------------------------------------------------

    with SUMMARY_FILE.open(
        "w",
        encoding="utf-8",
    ) as handle:

        handle.write(
            "SMARTPARK AI - BIRMINGHAM "
            "XGBOOST FEATURE IMPORTANCE AUDIT\n"
        )

        handle.write(
            "=" * 78
            + "\n\n"
        )

        handle.write(
            f"Target: {TARGET_NAME}\n"
        )

        handle.write(
            f"Overall status: {overall_status}\n"
        )

        handle.write(
            "\n"
        )

        handle.write(
            "IMPORTANT:\n"
        )

        handle.write(
            "This audit is read-only. It does not modify "
            "datasets, models, or feature pipeline code.\n"
        )

        handle.write(
            "\n"
        )

        handle.write(
            "Priority feature findings:\n"
        )

        for audit in audits:

            if audit.feature not in PRIORITY_FEATURES:
                continue

            handle.write(
                f"\n{audit.feature}\n"
            )

            handle.write(
                f"  Rank: {audit.rank}\n"
            )

            handle.write(
                f"  Importance: {audit.importance}\n"
            )

            handle.write(
                f"  Group: {audit.feature_group}\n"
            )

            handle.write(
                f"  Target dependency: "
                f"{audit.target_dependency_status}\n"
            )

            handle.write(
                f"  Prediction-time status: "
                f"{audit.prediction_time_status}\n"
            )

            handle.write(
                f"  Future lookup status: "
                f"{audit.future_lookup_status}\n"
            )

            handle.write(
                f"  Target correlation: "
                f"{audit.target_correlation}\n"
            )

            handle.write(
                f"  Audit status: "
                f"{audit.audit_status}\n"
            )

            for note in audit.notes:

                handle.write(
                    f"  Note: {note}\n"
                )


# ============================================================================
# ASSERTIONS
# ============================================================================


def run_final_assertions(
    importance: pd.DataFrame,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    audits: list[FeatureAudit],
) -> None:

    print_section(
        "FINAL AUDIT ASSERTIONS"
    )

    assertions: list[tuple[str, bool]] = []

    assertions.append(
        (
            "Training dataset non-empty",
            len(train) > 0,
        )
    )

    assertions.append(
        (
            "Validation dataset non-empty",
            len(validation) > 0,
        )
    )

    assertions.append(
        (
            "Feature importance file non-empty",
            len(importance) > 0,
        )
    )

    assertions.append(
        (
            "Target exists",
            TARGET_NAME in train.columns,
        )
    )

    assertions.append(
        (
            "Training/validation feature schema identical",
            list(train.columns)
            == list(validation.columns),
        )
    )

    assertions.append(
        (
            "No target column included in importance file",
            not any(
                feature in TARGET_COLUMNS
                for feature in importance[
                    "feature"
                ]
            ),
        )
    )

    assertions.append(
        (
            "No future-named feature included in importance file",
            not any(
                is_future_named_feature(
                    str(feature)
                )
                for feature in importance[
                    "feature"
                ]
            ),
        )
    )

    for name, passed in assertions:

        print(
            f"{name:<55}: "
            f"{'PASS' if passed else 'FAIL'}"
        )

    failed = [
        name
        for name, passed in assertions
        if not passed
    ]

    if failed:

        raise AssertionError(
            "Audit assertions failed: "
            + ", ".join(failed)
        )


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:

    print_header(
        "SMARTPARK AI - BIRMINGHAM "
        "XGBOOST FEATURE IMPORTANCE AUDIT"
    )

    print()
    print(
        "Audit policy:"
    )

    print(
        "  Read persisted feature importance only"
    )

    print(
        "  Read persisted train/validation datasets only"
    )

    print(
        "  Do NOT load test.parquet"
    )

    print(
        "  Do NOT retrain XGBoost"
    )

    print(
        "  Do NOT modify feature pipeline"
    )

    print(
        "  Do NOT modify persisted datasets"
    )

    print(
        "  Flag uncertain dependencies for manual review"
    )

    try:

        # --------------------------------------------------------------------
        # 1. Validate files
        # --------------------------------------------------------------------

        print_section(
            "REQUIRED FILE VALIDATION"
        )

        validate_required_files()

        print(
            "Training dataset : PASS"
        )

        print(
            "Validation dataset : PASS"
        )

        print(
            "Feature importance : PASS"
        )

        # --------------------------------------------------------------------
        # 2. Source file availability
        # --------------------------------------------------------------------

        source_files = (
            inspect_feature_source_files()
        )

        # --------------------------------------------------------------------
        # 3. Benchmark context
        # --------------------------------------------------------------------

        print_benchmark_context()

        # --------------------------------------------------------------------
        # 4. Load data
        # --------------------------------------------------------------------

        train, validation = (
            load_datasets()
        )

        # --------------------------------------------------------------------
        # 5. Load importance
        # --------------------------------------------------------------------

        importance = load_importance()

        # --------------------------------------------------------------------
        # 6. Audit features
        # --------------------------------------------------------------------

        audits = audit_features(
            importance,
            train,
            validation,
        )

        # --------------------------------------------------------------------
        # 7. Print summaries
        # --------------------------------------------------------------------

        print_top_feature_summary(
            audits
        )

        print_group_summary(
            audits
        )

        print_priority_review(
            audits
        )

        print_high_correlation_review(
            audits
        )

        # --------------------------------------------------------------------
        # 8. Search actual source files
        # --------------------------------------------------------------------

        source_search = (
            print_source_search_for_priority_features()
        )

        # --------------------------------------------------------------------
        # 9. Overall status
        # --------------------------------------------------------------------

        overall_status, review_features = (
            determine_overall_status(
                audits
            )
        )

        # --------------------------------------------------------------------
        # 10. Assertions
        # --------------------------------------------------------------------

        run_final_assertions(
            importance,
            train,
            validation,
            audits,
        )

        # --------------------------------------------------------------------
        # 11. Persist
        # --------------------------------------------------------------------

        print_section(
            "PERSISTING AUDIT RESULTS"
        )

        persist_results(
            audits,
            source_search,
            source_files,
            overall_status,
            review_features,
        )

        print(
            f"JSON report : {OUTPUT_JSON}"
        )

        print(
            f"CSV report  : {OUTPUT_CSV}"
        )

        print(
            f"Summary     : {SUMMARY_FILE}"
        )

        # --------------------------------------------------------------------
        # Final result
        # --------------------------------------------------------------------

        print_header(
            "BIRMINGHAM XGBOOST FEATURE IMPORTANCE AUDIT "
            "COMPLETED"
        )

        print()
        print(
            f"Overall audit status : {overall_status}"
        )

        if review_features:

            print()
            print(
                "Features requiring source-level review:"
            )

            for feature in review_features:

                print(
                    f"  - {feature}"
                )

        print()
        print(
            "IMPORTANT:"
        )

        print(
            "A REVIEW status does NOT mean leakage."
        )

        print(
            "It means the feature requires implementation-level "
            "verification before we treat it as definitively "
            "safe for prediction-time use."
        )

        print()
        print(
            "No datasets, model files, or feature pipeline files "
            "were modified."
        )

        return 0

    except Exception as exc:

        print()
        print_header(
            "BIRMINGHAM FEATURE IMPORTANCE AUDIT FAILED"
        )

        print()
        print(
            f"ERROR: {exc}"
        )

        return 1


if __name__ == "__main__":

    raise SystemExit(
        main()
    )