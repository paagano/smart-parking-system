"""
SMARTPARK AI
Birmingham XGBoost Current-State Prediction-Time Availability Audit

Purpose
-------
Audit current-state ML features used by the Birmingham XGBoost forecasting
dataset and determine whether those features are plausibly available at the
prediction timestamp T.

This audit is intentionally separate from temporal leakage detection.

Temporal leakage asks:
    "Does a feature contain information from T + epsilon or later?"

Current-state availability asks:
    "Could this feature actually be known by the production system at T?"

Audit policy
------------
1. Inspect persisted train/validation Parquet datasets.
2. Load the registered Birmingham feature list from the manifest.
3. Inspect ML feature-generation source code.
4. Classify registered features into:
       - current_state
       - historical_lag
       - temporal_calendar
       - other
5. Identify current-state features and trace their likely source fields.
6. Distinguish:
       - directly observed current-state values
       - deterministic transformations of current-state values
       - historical rolling features
       - metadata / identifiers
7. Check that current-state features do not reference target columns.
8. Check that current-state features do not reference future offsets.
9. Check source code for suspicious temporal operations.
10. Produce a feature-level CSV and JSON audit report.
11. Do NOT load test.parquet.
12. Do NOT train XGBoost.
13. Do NOT rebuild the feature pipeline.
14. Do NOT modify persisted datasets.

Important
---------
This script cannot prove physical/API availability of a live Birmingham
parking observation. It establishes the ML feature dependency contract.

Therefore the final verdict may be:

    PASS
        All current-state features have an established prediction-time
        dependency.

    PASS_WITH_DOCUMENTATION_REVIEW
        No temporal problem detected, but one or more current-state features
        require explicit production-data-source documentation.

    FAIL
        A current-state feature demonstrably depends on future information,
        target information, or another unavailable source.

This script deliberately uses conservative rules.
"""

from __future__ import annotations

import ast
import csv
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd


# ============================================================================
# CONSTANTS
# ============================================================================

SCRIPT_NAME = (
    "birmingham_xgboost_current_state_availability_audit.py"
)

TARGET_COLUMN = "target_occupancy_rate_30m"

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
    "target_tomorrow_morning_demand_available",
    "target_tomorrow_morning_available",
}

NON_FEATURE_COLUMNS = {
    "source_facility_code",
    "normalized_at",
    "target_30m_available",
    "target_1h_available",
    "target_2h_available",
    "target_tomorrow_morning_available",
    "target_tomorrow_morning_demand_available",
    "target_exclusion_reason",
}

PROCESSED_ROOT = (
    Path(__file__).resolve().parents[1]
    / "datasets"
    / "processed"
    / "birmingham"
)

MANIFEST_PATH = (
    PROCESSED_ROOT
    / "training_dataset_manifest.json"
)

TRAIN_PATH = (
    PROCESSED_ROOT
    / "target_occupancy_rate_30m"
    / "train.parquet"
)

VALIDATION_PATH = (
    PROCESSED_ROOT
    / "target_occupancy_rate_30m"
    / "validation.parquet"
)

TEST_PATH = (
    PROCESSED_ROOT
    / "target_occupancy_rate_30m"
    / "test.parquet"
)

OUTPUT_DIR = (
    PROCESSED_ROOT
    / "xgboost_current_state_availability_audit"
)

JSON_OUTPUT = (
    OUTPUT_DIR
    / "birmingham_xgboost_current_state_availability_audit.json"
)

FEATURE_CSV_OUTPUT = (
    OUTPUT_DIR
    / "birmingham_xgboost_current_state_availability_features.csv"
)

SUMMARY_CSV_OUTPUT = (
    OUTPUT_DIR
    / "birmingham_xgboost_current_state_availability_summary.csv"
)

SOURCE_ROOT = (
    Path(__file__).resolve().parent
    / "app"
    / "ml"
)

SOURCE_DIRECTORIES = [
    SOURCE_ROOT / "data",
    SOURCE_ROOT / "features",
    SOURCE_ROOT / "ml_models",
]

SOURCE_FILE_PATTERNS = (
    "*.py",
)

EXPECTED_FEATURE_COUNT = 296


# ============================================================================
# FEATURE FAMILY DEFINITIONS
# ============================================================================

CALENDAR_FEATURE_NAMES = {
    "year",
    "month",
    "quarter",
    "day_of_month",
    "day_of_year",
    "week_of_year",
    "day_of_week",
    "hour",
    "minute",
    "half_hour_slot",
    "time_slot",
    "minutes_since_midnight",
    "minutes_since_week_start",
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
    "month_sin",
    "month_cos",
    "calendar_year",
    "calendar_month",
    "calendar_quarter",
    "calendar_week_of_year",
    "calendar_day_of_month",
    "calendar_day_of_year",
    "calendar_day_of_week",
    "calendar_week_of_month",
    "calendar_week_of_quarter",
    "is_month_start",
    "is_month_end",
    "days_to_month_end",
    "is_quarter_start",
    "is_quarter_end",
    "is_quarter_start_month",
    "is_quarter_end_month",
    "is_year_start",
    "is_year_end",
    "calendar_month_sin",
    "calendar_month_cos",
    "calendar_day_of_week_sin",
    "calendar_day_of_week_cos",
    "calendar_day_of_year_sin",
    "calendar_day_of_year_cos",
    "calendar_quarter_sin",
    "calendar_quarter_cos",
}

# Exact known current-state features from the Birmingham feature registry.
KNOWN_CURRENT_STATE_FEATURES = {
    "capacity_utilization",
    "availability_rate",
    "occupied_ratio",
    "available_ratio",
    "vacancy_ratio",
    "occupancy_level",
    "occupancy_capacity_difference",
    "occupancy_within_capacity",
    "occupancy_state_valid",
    "occupancy_rate_consistent",
    "demand_level",
    "calculated_demand_level",
    "demand_pressure",
    "demand_excess_pressure",
    "remaining_capacity_ratio",
    "availability_pressure",
    "is_low_availability",
    "is_critical_availability",
    "is_full",
    "is_zero_capacity",
    "is_capacity_exceeded",
    "demand_class",
    "demand_class_code",
    "is_low_demand",
    "is_moderate_demand",
    "is_high_demand",
    "is_very_high_demand",
    "is_empty",
    "is_low_occupancy",
    "is_moderate_occupancy",
    "is_high_occupancy",
    "is_near_full",
}

# Canonical raw/current observation fields.
CURRENT_SOURCE_FIELDS = {
    "occupancy_rate",
    "raw_occupancy_rate",
    "occupied_spaces",
    "available_spaces",
    "total_spaces",
    "capacity",
    "occupancy",
    "availability",
}

# Future / target references which must never appear in a current-state
# feature dependency.
FORBIDDEN_FUTURE_PATTERNS = (
    r"\.shift\(\s*-\s*\d+",
    r"\.shift\(\s*-\s*steps",
    r"shift\s*\(\s*-\s*",
    r"lead\s*\(",
    r"future_",
    r"next_",
    r"forecast_",
    r"lookahead",
    r"forward_window",
    r"center\s*=\s*True",
)

TARGET_REFERENCE_PATTERNS = (
    r"target_occupancy_rate_30m",
    r"target_occupancy_rate_1h",
    r"target_occupancy_rate_2h",
    r"target_tomorrow_morning_demand",
    r"target_30m_available",
    r"target_1h_available",
    r"target_2h_available",
    r"target_tomorrow_morning",
)

# Historical feature naming contract.
HISTORICAL_FEATURE_PATTERNS = (
    r"_lag_",
    r"_lag\d+",
    r"_roll_",
    r"_rolling_",
    r"_history_",
    r"_historical_",
    r"_trend_",
)

CURRENT_FEATURE_PATTERNS = (
    r"^capacity_utilization$",
    r"^availability_rate$",
    r"^available_ratio$",
    r"^vacancy_ratio$",
    r"^occupied_ratio$",
    r"^occupancy_level$",
    r"^occupancy_capacity_difference$",
    r"^occupancy_within_capacity$",
    r"^occupancy_state_valid$",
    r"^occupancy_rate_consistent$",
    r"^demand_level$",
    r"^calculated_demand_level$",
    r"^demand_pressure$",
    r"^demand_excess_pressure$",
    r"^remaining_capacity_ratio$",
    r"^availability_pressure$",
    r"^is_",
)


# ============================================================================
# DATACLASSES
# ============================================================================


@dataclass
class SourceFinding:
    file: str
    line_number: int
    finding_type: str
    text: str


@dataclass
class FeatureAudit:
    feature: str
    family: str
    classification: str
    prediction_time_status: str
    confidence: str
    current_state_dependency: str
    source_fields: str
    target_reference: bool
    future_reference: bool
    rolling_or_lag_reference: bool
    source_files: str
    source_line_numbers: str
    rationale: str
    production_action: str


# ============================================================================
# EXCEPTIONS
# ============================================================================


class CurrentStateAvailabilityAuditError(Exception):
    """Base audit exception."""


class AuditContractError(
    CurrentStateAvailabilityAuditError
):
    """Dataset or feature contract failure."""


class AuditLeakageError(
    CurrentStateAvailabilityAuditError
):
    """Confirmed leakage finding."""


# ============================================================================
# PRINTING HELPERS
# ============================================================================


def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def print_status(
    label: str,
    value: Any,
    width: int = 44,
) -> None:
    print(
        f"{label:<{width}}: {value}"
    )


def pass_line(
    label: str,
) -> None:
    print_status(
        label,
        "PASS",
    )


def fail_line(
    label: str,
) -> None:
    print_status(
        label,
        "FAIL",
    )


# ============================================================================
# PATH / FILE VALIDATION
# ============================================================================


def validate_dataset_files() -> None:
    print_section(
        "DATASET FILE VALIDATION"
    )

    print_status(
        "Training dataset",
        TRAIN_PATH,
    )

    print_status(
        "Validation dataset",
        VALIDATION_PATH,
    )

    print_status(
        "Test dataset",
        TEST_PATH,
    )

    if not TRAIN_PATH.exists():
        raise AuditContractError(
            f"Training dataset does not exist: {TRAIN_PATH}"
        )

    if not VALIDATION_PATH.exists():
        raise AuditContractError(
            "Validation dataset does not exist: "
            f"{VALIDATION_PATH}"
        )

    print_status(
        "Training file exists",
        "PASS",
    )

    print_status(
        "Validation file exists",
        "PASS",
    )

    print_status(
        "Test file exists",
        "PASS"
        if TEST_PATH.exists()
        else "NOT FOUND",
    )

    print()
    print(
        "Test dataset will NOT be loaded."
    )


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise AuditContractError(
            f"Manifest does not exist: {MANIFEST_PATH}"
        )

    try:
        manifest = json.loads(
            MANIFEST_PATH.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        raise AuditContractError(
            f"Unable to load manifest: {exc}"
        ) from exc

    if not isinstance(
        manifest,
        dict,
    ):
        raise AuditContractError(
            "Manifest root must be a JSON object."
        )

    return manifest


# ============================================================================
# DATASET LOADING
# ============================================================================


def load_persisted_datasets() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    print_section(
        "LOADING PERSISTED DATASETS"
    )

    print(
        "Loading training dataset..."
    )

    train = pd.read_parquet(
        TRAIN_PATH
    )

    print(
        "Loading validation dataset..."
    )

    validation = pd.read_parquet(
        VALIDATION_PATH
    )

    print_status(
        "Training rows",
        f"{len(train):,}",
    )

    print_status(
        "Validation rows",
        f"{len(validation):,}",
    )

    return train, validation


# ============================================================================
# FEATURE REGISTRY
# ============================================================================


def get_feature_registry(
    manifest: dict[str, Any],
) -> list[str]:
    raw = manifest.get(
        "feature_columns"
    )

    if not isinstance(
        raw,
        list,
    ):
        raise AuditContractError(
            "Manifest feature_columns is missing or invalid."
        )

    features = [
        str(column)
        for column in raw
    ]

    if len(features) != len(
        set(features)
    ):
        raise AuditContractError(
            "Manifest contains duplicate feature names."
        )

    return features


def validate_feature_registry(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
) -> None:
    print_section(
        "FEATURE REGISTRY VALIDATION"
    )

    train_missing = [
        feature
        for feature in features
        if feature not in train.columns
    ]

    validation_missing = [
        feature
        for feature in features
        if feature not in validation.columns
    ]

    if train_missing:
        raise AuditContractError(
            "Training dataset is missing registered "
            f"features: {train_missing}"
        )

    if validation_missing:
        raise AuditContractError(
            "Validation dataset is missing registered "
            f"features: {validation_missing}"
        )

    print_status(
        "Registered features",
        len(features),
    )

    print_status(
        "Training feature registry",
        "PASS",
    )

    print_status(
        "Validation feature registry",
        "PASS",
    )

    if [
        column
        for column in train[features].columns
    ] != [
        column
        for column in validation[features].columns
    ]:

        raise AuditContractError(
            "Training and validation feature registries differ."
        )

    print_status(
        "Train/validation feature registry",
        "IDENTICAL",
    )


# ============================================================================
# SOURCE FILE DISCOVERY
# ============================================================================


def discover_source_files() -> list[Path]:
    files: list[Path] = []

    for directory in SOURCE_DIRECTORIES:

        if not directory.exists():
            continue

        for pattern in SOURCE_FILE_PATTERNS:

            files.extend(
                directory.rglob(pattern)
            )

    # Deduplicate and sort.
    unique = sorted(
        set(
            path.resolve()
            for path in files
            if path.is_file()
        )
    )

    return unique


def read_source_files() -> dict[Path, str]:
    source_files = discover_source_files()

    contents: dict[Path, str] = {}

    for path in source_files:

        try:
            contents[path] = path.read_text(
                encoding="utf-8",
                errors="replace",
            )
        except Exception:
            continue

    return contents


# ============================================================================
# SOURCE CODE ANALYSIS
# ============================================================================


def find_pattern_findings(
    source_contents: dict[Path, str],
    patterns: Iterable[str],
    finding_type: str,
) -> list[SourceFinding]:

    findings: list[SourceFinding] = []

    compiled = [
        re.compile(
            pattern,
            re.IGNORECASE,
        )
        for pattern in patterns
    ]

    for path, text in source_contents.items():

        lines = text.splitlines()

        for line_number, line in enumerate(
            lines,
            start=1,
        ):

            for regex in compiled:

                if regex.search(line):

                    findings.append(
                        SourceFinding(
                            file=str(path),
                            line_number=line_number,
                            finding_type=finding_type,
                            text=line.strip(),
                        )
                    )

                    break

    return findings


def source_temporal_findings(
    source_contents: dict[Path, str],
) -> dict[str, list[SourceFinding]]:

    return {
        "future": find_pattern_findings(
            source_contents,
            FORBIDDEN_FUTURE_PATTERNS,
            "future_reference",
        ),
        "target": find_pattern_findings(
            source_contents,
            TARGET_REFERENCE_PATTERNS,
            "target_reference",
        ),
        "historical": find_pattern_findings(
            source_contents,
            HISTORICAL_FEATURE_PATTERNS,
            "historical_feature_reference",
        ),
    }


# ============================================================================
# AST-BASED FEATURE SOURCE EXTRACTION
# ============================================================================


def extract_feature_mentions_from_ast(
    source_contents: dict[Path, str],
) -> dict[str, list[tuple[str, int]]]:

    mentions: dict[
        str,
        list[tuple[str, int]],
    ] = {}

    for path, text in source_contents.items():

        try:
            tree = ast.parse(
                text,
                filename=str(path),
            )
        except SyntaxError:
            continue

        for node in ast.walk(tree):

            if not isinstance(
                node,
                ast.Subscript,
            ):
                continue

            # Look for:
            #
            # dataframe["feature"]
            # result["feature"]
            # df["feature"]
            #
            if not isinstance(
                node.slice,
                ast.Constant,
            ):
                continue

            value = node.slice.value

            if not isinstance(
                value,
                str,
            ):
                continue

            mentions.setdefault(
                value,
                [],
            ).append(
                (
                    str(path),
                    int(node.lineno),
                )
            )

    return mentions


# ============================================================================
# FEATURE CLASSIFICATION
# ============================================================================


def classify_feature(
    feature: str,
) -> str:

    if feature in CALENDAR_FEATURE_NAMES:
        return "temporal_calendar"

    if any(
        re.search(
            pattern,
            feature,
            re.IGNORECASE,
        )
        for pattern in HISTORICAL_FEATURE_PATTERNS
    ):
        return "historical_lag"

    if feature in KNOWN_CURRENT_STATE_FEATURES:
        return "current_state"

    if any(
        re.match(
            pattern,
            feature,
            re.IGNORECASE,
        )
        for pattern in CURRENT_FEATURE_PATTERNS
    ):
        return "current_state"

    return "other"


def feature_source_fields(
    feature: str,
) -> list[str]:

    lower = feature.lower()

    fields: list[str] = []

    if (
        "occupancy" in lower
        or "occupied" in lower
    ):
        fields.append(
            "occupancy/occupied_spaces"
        )

    if (
        "availability" in lower
        or "available" in lower
        or "vacancy" in lower
    ):
        fields.append(
            "availability/available_spaces"
        )

    if (
        "capacity" in lower
        or "spaces" in lower
    ):
        fields.append(
            "capacity/space counts"
        )

    if (
        "demand" in lower
    ):
        fields.append(
            "derived current demand state"
        )

    if not fields:
        fields.append(
            "feature-generation dependency requires review"
        )

    return fields


def detect_feature_temporal_flags(
    feature: str,
    source_contents: dict[Path, str],
    ast_mentions: dict[str, list[tuple[str, int]]],
) -> tuple[
    bool,
    bool,
    bool,
    list[str],
    list[int],
]:
    target_reference = False
    future_reference = False
    rolling_or_lag = False

    files: list[str] = []
    lines: list[int] = []

    # Feature-name level detection.
    if feature in TARGET_COLUMNS:
        target_reference = True

    if feature in TARGET_AVAILABILITY_COLUMNS:
        target_reference = True

    if any(
        token in feature.lower()
        for token in (
            "target_",
            "future_",
            "next_",
            "forecast_",
        )
    ):
        target_reference = True

    if any(
        re.search(
            pattern,
            feature,
            re.IGNORECASE,
        )
        for pattern in HISTORICAL_FEATURE_PATTERNS
    ):
        rolling_or_lag = True

    # AST references.
    for file_path, line_number in (
        ast_mentions.get(
            feature,
            [],
        )
    ):
        files.append(file_path)
        lines.append(line_number)

    # Inspect nearby source context.
    for path, text in source_contents.items():

        source_lower = text.lower()

        feature_lower = feature.lower()

        if feature_lower not in source_lower:
            continue

        lines_of_source = text.splitlines()

        for line_number, line in enumerate(
            lines_of_source,
            start=1,
        ):

            if feature_lower not in line.lower():
                continue

            if any(
                re.search(
                    pattern,
                    line,
                    re.IGNORECASE,
                )
                for pattern in TARGET_REFERENCE_PATTERNS
            ):
                target_reference = True

            if any(
                re.search(
                    pattern,
                    line,
                    re.IGNORECASE,
                )
                for pattern in FORBIDDEN_FUTURE_PATTERNS
            ):
                future_reference = True

            if any(
                re.search(
                    pattern,
                    line,
                    re.IGNORECASE,
                )
                for pattern in HISTORICAL_FEATURE_PATTERNS
            ):
                rolling_or_lag = True

            if str(path) not in files:
                files.append(str(path))

            if line_number not in lines:
                lines.append(line_number)

    return (
        target_reference,
        future_reference,
        rolling_or_lag,
        files,
        sorted(lines),
    )


# ============================================================================
# CURRENT-STATE DECISION ENGINE
# ============================================================================


def determine_prediction_time_status(
    feature: str,
    family: str,
    target_reference: bool,
    future_reference: bool,
    rolling_or_lag: bool,
) -> tuple[
    str,
    str,
    str,
    str,
]:
    """
    Return:

        status
        confidence
        rationale
        production_action
    """

    if target_reference:
        return (
            "FAIL",
            "HIGH",
            (
                "Feature has a target or target-availability "
                "dependency."
            ),
            (
                "Remove target dependency before production "
                "inference."
            ),
        )

    if future_reference:
        return (
            "FAIL",
            "HIGH",
            (
                "Feature has a future-looking temporal "
                "dependency."
            ),
            (
                "Remove future dependency and regenerate "
                "the dataset."
            ),
        )

    if family == "temporal_calendar":
        return (
            "SAFE",
            "HIGH",
            (
                "Calendar/time features are computable from "
                "the prediction timestamp."
            ),
            (
                "Document timestamp source and timezone."
            ),
        )

    if family == "historical_lag":
        return (
            "SAFE_IF_GENERATED_CAUSALLY",
            "HIGH",
            (
                "Historical feature is safe provided its "
                "window contains only observations at or before T."
            ),
            (
                "Document lag/rolling window construction "
                "and production data availability."
            ),
        )

    if family == "current_state":
        return (
            "REQUIRES_PRODUCTION_AVAILABILITY_CONFIRMATION",
            "MEDIUM",
            (
                "Feature is derived from current parking state. "
                "It is not inherently temporally leaky, but the "
                "source observation must be available at T."
            ),
            (
                "Document the real-time source, ingestion latency, "
                "freshness SLA, and fallback behaviour."
            ),
        )

    if rolling_or_lag:
        return (
            "SAFE_IF_GENERATED_CAUSALLY",
            "MEDIUM",
            (
                "Feature appears to depend on historical "
                "observations. Causality must be documented."
            ),
            (
                "Document historical window boundaries."
            ),
        )

    return (
        "REQUIRES_DOCUMENTATION",
        "MEDIUM",
        (
            "Feature could not be conclusively mapped to a "
            "prediction-time source from static analysis."
        ),
        (
            "Document production feature source and availability."
        ),
    )


# ============================================================================
# FEATURE AUDIT
# ============================================================================


def build_feature_audit(
    features: list[str],
    source_contents: dict[Path, str],
) -> list[FeatureAudit]:

    ast_mentions = (
        extract_feature_mentions_from_ast(
            source_contents
        )
    )

    audits: list[FeatureAudit] = []

    for feature in features:

        family = classify_feature(
            feature
        )

        (
            target_reference,
            future_reference,
            rolling_or_lag,
            source_files,
            source_lines,
        ) = detect_feature_temporal_flags(
            feature,
            source_contents,
            ast_mentions,
        )

        (
            status,
            confidence,
            rationale,
            production_action,
        ) = determine_prediction_time_status(
            feature=feature,
            family=family,
            target_reference=target_reference,
            future_reference=future_reference,
            rolling_or_lag=rolling_or_lag,
        )

        source_fields = feature_source_fields(
            feature
        )

        if family == "current_state":
            dependency = (
                "CURRENT_OBSERVATION"
            )
        elif family == "historical_lag":
            dependency = (
                "HISTORICAL_OBSERVATIONS"
            )
        elif family == "temporal_calendar":
            dependency = (
                "TIMESTAMP"
            )
        else:
            dependency = (
                "UNRESOLVED"
            )

        audits.append(
            FeatureAudit(
                feature=feature,
                family=family,
                classification=family,
                prediction_time_status=status,
                confidence=confidence,
                current_state_dependency=dependency,
                source_fields="; ".join(
                    source_fields
                ),
                target_reference=target_reference,
                future_reference=future_reference,
                rolling_or_lag_reference=(
                    rolling_or_lag
                ),
                source_files="; ".join(
                    sorted(
                        set(
                            source_files
                        )
                    )
                ),
                source_line_numbers=", ".join(
                    str(number)
                    for number in source_lines
                ),
                rationale=rationale,
                production_action=production_action,
            )
        )

    return audits


# ============================================================================
# DATASET STATISTICS
# ============================================================================


def inspect_dataset_features(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
) -> dict[str, Any]:

    train_features = train[
        features
    ]

    validation_features = validation[
        features
    ]

    train_numeric = [
        column
        for column in features
        if pd.api.types.is_numeric_dtype(
            train_features[column]
        )
    ]

    train_non_numeric = [
        column
        for column in features
        if not pd.api.types.is_numeric_dtype(
            train_features[column]
        )
    ]

    validation_numeric = [
        column
        for column in features
        if pd.api.types.is_numeric_dtype(
            validation_features[column]
        )
    ]

    validation_non_numeric = [
        column
        for column in features
        if not pd.api.types.is_numeric_dtype(
            validation_features[column]
        )
    ]

    train_numeric_values = (
        train_features[
            train_numeric
        ].to_numpy(
            dtype=float
        )
        if train_numeric
        else np.empty(
            (len(train_features), 0)
        )
    )

    validation_numeric_values = (
        validation_features[
            validation_numeric
        ].to_numpy(
            dtype=float
        )
        if validation_numeric
        else np.empty(
            (len(validation_features), 0)
        )
    )

    return {
        "training_numeric_feature_count": len(
            train_numeric
        ),
        "training_non_numeric_feature_count": len(
            train_non_numeric
        ),
        "training_non_numeric_features": (
            train_non_numeric
        ),
        "validation_numeric_feature_count": len(
            validation_numeric
        ),
        "validation_non_numeric_feature_count": len(
            validation_non_numeric
        ),
        "validation_non_numeric_features": (
            validation_non_numeric
        ),
        "training_numeric_nan_cells": int(
            np.isnan(
                train_numeric_values
            ).sum()
        ),
        "validation_numeric_nan_cells": int(
            np.isnan(
                validation_numeric_values
            ).sum()
        ),
        "training_positive_infinity_cells": int(
            np.isposinf(
                train_numeric_values
            ).sum()
        ),
        "training_negative_infinity_cells": int(
            np.isneginf(
                train_numeric_values
            ).sum()
        ),
        "validation_positive_infinity_cells": int(
            np.isposinf(
                validation_numeric_values
            ).sum()
        ),
        "validation_negative_infinity_cells": int(
            np.isneginf(
                validation_numeric_values
            ).sum()
        ),
    }


# ============================================================================
# CURRENT-STATE SOURCE CONTRACT
# ============================================================================


def build_current_state_dependency_summary(
    audits: list[FeatureAudit],
) -> dict[str, Any]:

    current = [
        audit
        for audit in audits
        if audit.family == "current_state"
    ]

    return {
        "count": len(current),
        "features": [
            audit.feature
            for audit in current
        ],
        "statuses": {
            status: sum(
                1
                for audit in current
                if audit.prediction_time_status
                == status
            )
            for status in sorted(
                {
                    audit.prediction_time_status
                    for audit in current
                }
            )
        },
    }


# ============================================================================
# LEAKAGE GATE
# ============================================================================


def run_leakage_gate(
    audits: list[FeatureAudit],
) -> dict[str, Any]:

    target_reference_features = [
        audit.feature
        for audit in audits
        if audit.target_reference
    ]

    future_reference_features = [
        audit.feature
        for audit in audits
        if audit.future_reference
    ]

    confirmed_failures = sorted(
        set(
            target_reference_features
            + future_reference_features
        )
    )

    return {
        "target_reference_features": (
            target_reference_features
        ),
        "future_reference_features": (
            future_reference_features
        ),
        "confirmed_leakage_features": (
            confirmed_failures
        ),
        "passed": not bool(
            confirmed_failures
        ),
    }


# ============================================================================
# VERDICT
# ============================================================================


def determine_final_verdict(
    audits: list[FeatureAudit],
    leakage_gate: dict[str, Any],
) -> tuple[
    str,
    list[str],
]:

    reasons: list[str] = []

    if not leakage_gate["passed"]:

        reasons.append(
            "One or more features reference target or "
            "future information."
        )

        return (
            "FAIL",
            reasons,
        )

    current_state = [
        audit
        for audit in audits
        if audit.family == "current_state"
    ]

    unresolved_current_state = [
        audit.feature
        for audit in current_state
        if audit.prediction_time_status
        == "REQUIRES_PRODUCTION_AVAILABILITY_CONFIRMATION"
    ]

    unresolved_other = [
        audit.feature
        for audit in audits
        if audit.prediction_time_status
        == "REQUIRES_DOCUMENTATION"
    ]

    if unresolved_current_state:

        reasons.append(
            (
                f"{len(unresolved_current_state)} current-state "
                "features require production availability "
                "documentation."
            )
        )

    if unresolved_other:

        reasons.append(
            (
                f"{len(unresolved_other)} features require "
                "additional production dependency documentation."
            )
        )

    if unresolved_current_state or unresolved_other:

        return (
            "PASS_WITH_DOCUMENTATION_REVIEW",
            reasons,
        )

    reasons.append(
        "All audited features have a prediction-time "
        "availability classification."
    )

    return (
        "PASS",
        reasons,
    )


# ============================================================================
# REPORT PERSISTENCE
# ============================================================================


def write_feature_csv(
    audits: list[FeatureAudit],
) -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    fieldnames = list(
        FeatureAudit.__dataclass_fields__.keys()
    )

    with FEATURE_CSV_OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for audit in audits:
            writer.writerow(
                asdict(audit)
            )


def write_summary_csv(
    audits: list[FeatureAudit],
) -> None:

    summary: dict[
        tuple[str, str],
        int,
    ] = {}

    for audit in audits:

        key = (
            audit.family,
            audit.prediction_time_status,
        )

        summary[key] = (
            summary.get(
                key,
                0,
            )
            + 1
        )

    with SUMMARY_CSV_OUTPUT.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "family",
                "prediction_time_status",
                "feature_count",
            ],
        )

        writer.writeheader()

        for (
            family,
            status,
        ), count in sorted(
            summary.items()
        ):

            writer.writerow(
                {
                    "family": family,
                    "prediction_time_status": status,
                    "feature_count": count,
                }
            )


def write_json_report(
    *,
    manifest: dict[str, Any],
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
    audits: list[FeatureAudit],
    leakage_gate: dict[str, Any],
    dataset_statistics: dict[str, Any],
    source_file_count: int,
    source_temporal_summary: dict[str, int],
    verdict: str,
    verdict_reasons: list[str],
) -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    family_counts: dict[str, int] = {}

    status_counts: dict[str, int] = {}

    confidence_counts: dict[str, int] = {}

    for audit in audits:

        family_counts[audit.family] = (
            family_counts.get(
                audit.family,
                0,
            )
            + 1
        )

        status_counts[
            audit.prediction_time_status
        ] = (
            status_counts.get(
                audit.prediction_time_status,
                0,
            )
            + 1
        )

        confidence_counts[
            audit.confidence
        ] = (
            confidence_counts.get(
                audit.confidence,
                0,
            )
            + 1
        )

    current_state = [
        audit
        for audit in audits
        if audit.family == "current_state"
    ]

    report = {
        "audit": {
            "name": (
                "Birmingham XGBoost Current-State "
                "Prediction-Time Availability Audit"
            ),
            "script": SCRIPT_NAME,
            "generated_at_utc": (
                datetime.utcnow()
                .isoformat()
                + "Z"
            ),
            "target": TARGET_COLUMN,
            "prediction_timestamp": "T",
            "forecast_horizon_minutes": 30,
        },
        "policy": {
            "train_dataset_loaded": True,
            "validation_dataset_loaded": True,
            "test_dataset_loaded": False,
            "xgboost_trained": False,
            "feature_pipeline_rebuilt": False,
            "persisted_datasets_modified": False,
        },
        "paths": {
            "processed_root": str(
                PROCESSED_ROOT
            ),
            "manifest": str(
                MANIFEST_PATH
            ),
            "training_dataset": str(
                TRAIN_PATH
            ),
            "validation_dataset": str(
                VALIDATION_PATH
            ),
            "test_dataset": str(
                TEST_PATH
            ),
        },
        "dataset": {
            "training_rows": len(train),
            "validation_rows": len(validation),
            "registered_feature_count": len(
                features
            ),
            "manifest_feature_count": len(
                manifest.get(
                    "feature_columns",
                    [],
                )
            ),
        },
        "dataset_statistics": dataset_statistics,
        "feature_family_counts": family_counts,
        "prediction_time_status_counts": status_counts,
        "confidence_counts": confidence_counts,
        "current_state_summary": (
            build_current_state_dependency_summary(
                audits
            )
        ),
        "source_analysis": {
            "ml_source_file_count": source_file_count,
            "negative_or_future_temporal_findings": (
                source_temporal_summary[
                    "future_findings"
                ]
            ),
            "target_reference_findings": (
                source_temporal_summary[
                    "target_findings"
                ]
            ),
            "historical_feature_findings": (
                source_temporal_summary[
                    "historical_findings"
                ]
            ),
        },
        "leakage_gate": leakage_gate,
        "verdict": {
            "status": verdict,
            "reasons": verdict_reasons,
        },
        "current_state_features": [
            asdict(audit)
            for audit in current_state
        ],
        "feature_audits": [
            asdict(audit)
            for audit in audits
        ],
    }

    JSON_OUTPUT.write_text(
        json.dumps(
            report,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )


# ============================================================================
# CONSOLE REPORTING
# ============================================================================


def print_feature_family_summary(
    audits: list[FeatureAudit],
) -> None:

    print_section(
        "FEATURE FAMILY SUMMARY"
    )

    family_counts: dict[str, int] = {}

    for audit in audits:

        family_counts[audit.family] = (
            family_counts.get(
                audit.family,
                0,
            )
            + 1
        )

    for family, count in sorted(
        family_counts.items()
    ):

        print_status(
            family,
            count,
        )


def print_prediction_status_summary(
    audits: list[FeatureAudit],
) -> None:

    print_section(
        "PREDICTION-TIME AVAILABILITY SUMMARY"
    )

    status_counts: dict[str, int] = {}

    for audit in audits:

        status = (
            audit.prediction_time_status
        )

        status_counts[status] = (
            status_counts.get(
                status,
                0,
            )
            + 1
        )

    for status, count in sorted(
        status_counts.items()
    ):

        print_status(
            status,
            count,
        )


def print_current_state_features(
    audits: list[FeatureAudit],
) -> None:

    print_section(
        "CURRENT-STATE FEATURE REVIEW"
    )

    current = [
        audit
        for audit in audits
        if audit.family == "current_state"
    ]

    if not current:
        print(
            "NO CURRENT-STATE FEATURES IDENTIFIED"
        )
        return

    for audit in current:
        print(
            f"  - {audit.feature}"
        )


def print_problem_features(
    audits: list[FeatureAudit],
) -> None:

    print_section(
        "FEATURES REQUIRING ATTENTION"
    )

    problems = [
        audit
        for audit in audits
        if audit.prediction_time_status
        in {
            "FAIL",
            "REQUIRES_PRODUCTION_AVAILABILITY_CONFIRMATION",
            "REQUIRES_DOCUMENTATION",
        }
    ]

    if not problems:
        print(
            "NO FEATURES REQUIRE ADDITIONAL REVIEW"
        )
        return

    for audit in problems:

        print(
            f"  - {audit.feature}"
        )

        print(
            f"      Status      : "
            f"{audit.prediction_time_status}"
        )

        print(
            f"      Dependency  : "
            f"{audit.current_state_dependency}"
        )

        print(
            f"      Rationale   : "
            f"{audit.rationale}"
        )

        print(
            f"      Action      : "
            f"{audit.production_action}"
        )


# ============================================================================
# ASSERTIONS
# ============================================================================


def run_final_assertions(
    *,
    features: list[str],
    audits: list[FeatureAudit],
    leakage_gate: dict[str, Any],
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    print_section(
        "FINAL ASSERTIONS"
    )

    checks: list[tuple[str, bool]] = []

    checks.append(
        (
            "Training dataset non-empty",
            len(train) > 0,
        )
    )

    checks.append(
        (
            "Validation dataset non-empty",
            len(validation) > 0,
        )
    )

    checks.append(
        (
            "Expected feature registry count",
            len(features)
            == EXPECTED_FEATURE_COUNT,
        )
    )

    checks.append(
        (
            "Audit row count equals feature count",
            len(audits)
            == len(features),
        )
    )

    checks.append(
        (
            "No duplicate audited features",
            len(
                {
                    audit.feature
                    for audit in audits
                }
            )
            == len(audits),
        )
    )

    checks.append(
        (
            "No confirmed target references",
            not leakage_gate[
                "target_reference_features"
            ],
        )
    )

    checks.append(
        (
            "No confirmed future references",
            not leakage_gate[
                "future_reference_features"
            ],
        )
    )

    checks.append(
        (
            "Test dataset not loaded",
            True,
        )
    )

    checks.append(
        (
            "No XGBoost training performed",
            True,
        )
    )

    checks.append(
        (
            "Persisted datasets not modified",
            True,
        )
    )

    for label, passed in checks:

        print_status(
            label,
            "PASS" if passed else "FAIL",
        )

        if not passed:
            raise AuditContractError(
                f"Final assertion failed: {label}"
            )


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:

    print_header(
        "SMARTPARK AI - BIRMINGHAM "
        "XGBOOST CURRENT-STATE AVAILABILITY AUDIT"
    )

    print()
    print(
        "Target:"
    )
    print(
        f"  {TARGET_COLUMN}"
    )

    print()
    print(
        "Audit policy:"
    )
    print(
        "  Inspect persisted train/validation feature datasets"
    )
    print(
        "  Inspect ML feature-generation source code"
    )
    print(
        "  Focus on prediction-time availability of current-state features"
    )
    print(
        "  Distinguish availability from temporal leakage"
    )
    print(
        "  Do NOT load test.parquet"
    )
    print(
        "  Do NOT train XGBoost"
    )
    print(
        "  Do NOT rebuild the feature pipeline"
    )
    print(
        "  Do NOT modify persisted datasets"
    )

    try:

        # ------------------------------------------------------------
        # Dataset files.
        # ------------------------------------------------------------

        validate_dataset_files()

        # ------------------------------------------------------------
        # Manifest.
        # ------------------------------------------------------------

        print_section(
            "LOADING FEATURE MANIFEST"
        )

        manifest = load_manifest()

        features = get_feature_registry(
            manifest
        )

        print_status(
            "Manifest",
            MANIFEST_PATH,
        )

        print_status(
            "Registered features",
            len(features),
        )

        # ------------------------------------------------------------
        # Dataset.
        # ------------------------------------------------------------

        train, validation = (
            load_persisted_datasets()
        )

        validate_feature_registry(
            train,
            validation,
            features,
        )

        # ------------------------------------------------------------
        # Target.
        # ------------------------------------------------------------

        print_section(
            "TARGET CONTRACT VALIDATION"
        )

        for name, dataframe in [
            ("Training", train),
            ("Validation", validation),
        ]:

            if TARGET_COLUMN not in dataframe.columns:
                raise AuditContractError(
                    f"{name} dataset does not contain "
                    f"{TARGET_COLUMN}."
                )

            target = pd.to_numeric(
                dataframe[
                    TARGET_COLUMN
                ],
                errors="coerce",
            )

            null_count = int(
                target.isna().sum()
            )

            if null_count:
                raise AuditContractError(
                    f"{name} target contains "
                    f"{null_count} null values."
                )

            print_status(
                f"{name} target rows",
                f"{len(target):,}",
            )

            print_status(
                f"{name} target nulls",
                null_count,
            )

            print_status(
                f"{name} target mean",
                f"{float(target.mean()):.6f}",
            )

            print_status(
                f"{name} target range",
                (
                    f"{float(target.min()):.6f}"
                    " -> "
                    f"{float(target.max()):.6f}"
                ),
            )

            if not np.isfinite(
                target.to_numpy(
                    dtype=float
                )
            ).all():
                raise AuditContractError(
                    f"{name} target contains "
                    "NaN or infinite values."
                )

        pass_line(
            "Target contract"
        )

        # ------------------------------------------------------------
        # Dataset feature inspection.
        # ------------------------------------------------------------

        print_section(
            "PERSISTED FEATURE DATASET INSPECTION"
        )

        dataset_statistics = (
            inspect_dataset_features(
                train,
                validation,
                features,
            )
        )

        print_status(
            "Training numeric features",
            dataset_statistics[
                "training_numeric_feature_count"
            ],
        )

        print_status(
            "Training non-numeric features",
            dataset_statistics[
                "training_non_numeric_feature_count"
            ],
        )

        print_status(
            "Training numeric NaN cells",
            dataset_statistics[
                "training_numeric_nan_cells"
            ],
        )

        print_status(
            "Training positive infinity cells",
            dataset_statistics[
                "training_positive_infinity_cells"
            ],
        )

        print_status(
            "Training negative infinity cells",
            dataset_statistics[
                "training_negative_infinity_cells"
            ],
        )

        print_status(
            "Validation numeric features",
            dataset_statistics[
                "validation_numeric_feature_count"
            ],
        )

        print_status(
            "Validation non-numeric features",
            dataset_statistics[
                "validation_non_numeric_feature_count"
            ],
        )

        print_status(
            "Validation numeric NaN cells",
            dataset_statistics[
                "validation_numeric_nan_cells"
            ],
        )

        print_status(
            "Validation positive infinity cells",
            dataset_statistics[
                "validation_positive_infinity_cells"
            ],
        )

        print_status(
            "Validation negative infinity cells",
            dataset_statistics[
                "validation_negative_infinity_cells"
            ],
        )

        # ------------------------------------------------------------
        # Source analysis.
        # ------------------------------------------------------------

        print_section(
            "SOURCE CODE DISCOVERY"
        )

        source_contents = read_source_files()

        print_status(
            "ML source files scanned",
            len(source_contents),
        )

        source_findings = (
            source_temporal_findings(
                source_contents
            )
        )

        source_temporal_summary = {
            "future_findings": len(
                source_findings[
                    "future"
                ]
            ),
            "target_findings": len(
                source_findings[
                    "target"
                ]
            ),
            "historical_findings": len(
                source_findings[
                    "historical"
                ]
            ),
        }

        print_section(
            "SOURCE TEMPORAL SIGNALS"
        )

        print_status(
            "Future / negative-shift findings",
            source_temporal_summary[
                "future_findings"
            ],
        )

        print_status(
            "Target-reference findings",
            source_temporal_summary[
                "target_findings"
            ],
        )

        print_status(
            "Historical feature findings",
            source_temporal_summary[
                "historical_findings"
            ],
        )

        # ------------------------------------------------------------
        # Feature-level audit.
        # ------------------------------------------------------------

        print_section(
            "BUILDING FEATURE-LEVEL AVAILABILITY AUDIT"
        )

        audits = build_feature_audit(
            features,
            source_contents,
        )

        print_feature_family_summary(
            audits
        )

        print_prediction_status_summary(
            audits
        )

        # ------------------------------------------------------------
        # Current state.
        # ------------------------------------------------------------

        print_current_state_features(
            audits
        )

        # ------------------------------------------------------------
        # Leakage gate.
        # ------------------------------------------------------------

        leakage_gate = run_leakage_gate(
            audits
        )

        print_section(
            "TEMPORAL / TARGET LEAKAGE GATE"
        )

        print_status(
            "Target-reference feature count",
            len(
                leakage_gate[
                    "target_reference_features"
                ]
            ),
        )

        print_status(
            "Future-reference feature count",
            len(
                leakage_gate[
                    "future_reference_features"
                ]
            ),
        )

        if leakage_gate["passed"]:

            print(
                "NO CONFIRMED TARGET OR FUTURE "
                "FEATURE REFERENCES"
            )

        else:

            print(
                "CONFIRMED LEAKAGE SIGNALS FOUND:"
            )

            for feature in leakage_gate[
                "confirmed_leakage_features"
            ]:
                print(
                    f"  - {feature}"
                )

        # ------------------------------------------------------------
        # Attention.
        # ------------------------------------------------------------

        print_problem_features(
            audits
        )

        # ------------------------------------------------------------
        # Final verdict.
        # ------------------------------------------------------------

        verdict, verdict_reasons = (
            determine_final_verdict(
                audits,
                leakage_gate,
            )
        )

        print_section(
            "PREDICTION-TIME AVAILABILITY CONTRACT"
        )

        print(
            "Prediction timestamp                         : T"
        )

        print(
            "Forecast horizon                             : 30 minutes"
        )

        print()
        print(
            "Allowed information:"
        )

        print(
            "  Information known at or before prediction "
            "timestamp T."
        )

        print()
        print(
            "Prohibited information:"
        )

        print(
            "  Any observation from T + epsilon through "
            "T + 30 minutes or later when it would not "
            "be known at prediction time."
        )

        print()
        print(
            "Current-state policy:"
        )

        print(
            "  Current-state features are not automatically "
            "considered leakage."
        )

        print(
            "  Their production source and freshness must "
            "be documented."
        )

        print_section(
            "FINAL AUDIT RESULT"
        )

        print_status(
            "Features audited",
            len(audits),
        )

        print_status(
            "Current-state features",
            sum(
                1
                for audit in audits
                if audit.family
                == "current_state"
            ),
        )

        print_status(
            "Historical/lag features",
            sum(
                1
                for audit in audits
                if audit.family
                == "historical_lag"
            ),
        )

        print_status(
            "Calendar features",
            sum(
                1
                for audit in audits
                if audit.family
                == "temporal_calendar"
            ),
        )

        print_status(
            "Confirmed target references",
            len(
                leakage_gate[
                    "target_reference_features"
                ]
            ),
        )

        print_status(
            "Confirmed future references",
            len(
                leakage_gate[
                    "future_reference_features"
                ]
            ),
        )

        print()
        print(
            f"TEMPORAL AVAILABILITY AUDIT VERDICT"
            f"  : {verdict}"
        )

        print()
        print(
            "Verdict reasons:"
        )

        for reason in verdict_reasons:

            print(
                f"  - {reason}"
            )

        # ------------------------------------------------------------
        # Persist reports.
        # ------------------------------------------------------------

        print_section(
            "PERSISTING AUDIT RESULTS"
        )

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        write_feature_csv(
            audits
        )

        write_summary_csv(
            audits
        )

        write_json_report(
            manifest=manifest,
            train=train,
            validation=validation,
            features=features,
            audits=audits,
            leakage_gate=leakage_gate,
            dataset_statistics=dataset_statistics,
            source_file_count=len(
                source_contents
            ),
            source_temporal_summary=(
                source_temporal_summary
            ),
            verdict=verdict,
            verdict_reasons=verdict_reasons,
        )

        print_status(
            "Output directory",
            OUTPUT_DIR,
        )

        print_status(
            "JSON report",
            JSON_OUTPUT,
        )

        print_status(
            "CSV feature audit",
            FEATURE_CSV_OUTPUT,
        )

        print_status(
            "CSV summary",
            SUMMARY_CSV_OUTPUT,
        )

        # ------------------------------------------------------------
        # Final assertions.
        # ------------------------------------------------------------

        run_final_assertions(
            features=features,
            audits=audits,
            leakage_gate=leakage_gate,
            train=train,
            validation=validation,
        )

        # ------------------------------------------------------------
        # Completion.
        # ------------------------------------------------------------

        print()
        print(
            "IMPORTANT:"
        )

        print(
            "  No persisted training, validation, or test "
            "dataset was modified."
        )

        print(
            "  Test dataset was NOT loaded."
        )

        print(
            "  No XGBoost model was trained."
        )

        print()

        if verdict == "FAIL":

            print(
                "CURRENT-STATE AVAILABILITY AUDIT FAILED."
            )

            print(
                "Resolve the reported dependency/leakage "
                "issues before proceeding."
            )

            return 1

        if (
            verdict
            == "PASS_WITH_DOCUMENTATION_REVIEW"
        ):

            print(
                "NO CONFIRMED TEMPORAL LEAKAGE WAS DETECTED."
            )

            print(
                "Current-state production availability "
                "documentation is still required."
            )

            print()
            print(
                "Do NOT treat this as unconditional production "
                "approval until the current-state source contract "
                "is documented."
            )

            return 0

        print(
            "CURRENT-STATE AVAILABILITY AUDIT PASSED."
        )

        print(
            "All audited feature dependencies have an "
            "established prediction-time classification."
        )

        return 0

    except (
        CurrentStateAvailabilityAuditError,
        FileNotFoundError,
        ValueError,
        TypeError,
    ) as exc:

        print()
        print("=" * 78)
        print(
            "BIRMINGHAM CURRENT-STATE AVAILABILITY AUDIT FAILED"
        )
        print("=" * 78)
        print()
        print(
            f"ERROR: {exc}"
        )
        print()
        print(
            "NO persisted datasets were modified."
        )
        print(
            "Test dataset was NOT loaded."
        )
        print(
            "No XGBoost model was trained."
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )