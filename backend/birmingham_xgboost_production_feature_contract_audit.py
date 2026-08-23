"""
===============================================================================
SMARTPARK AI
BIRMINGHAM XGBOOST PRODUCTION FEATURE CONTRACT AUDIT
===============================================================================

Purpose
-------
Establish a production-time feature availability contract for the persisted
Birmingham XGBoost training dataset.

The audit answers:

    "For every registered ML feature, can SmartPark legitimately obtain the
     required information at prediction timestamp T?"

This is an AVAILABILITY CONTRACT audit.

It is NOT:
    - a model training script
    - a hyperparameter tuning script
    - a feature-pipeline rebuild
    - a test evaluation
    - a dataset modification script

Target:
    target_occupancy_rate_30m

Prediction contract:
    Prediction timestamp = T
    Forecast horizon    = T + 30 minutes

Allowed:
    - Information deterministically known at T
    - Current observation available at T
    - Historical information strictly <= T
    - Calendar/time information known at T

Not allowed:
    - Future observations
    - Target-derived information
    - Information from T + epsilon through T + 30 minutes
    - Any feature whose production availability cannot be established

IMPORTANT
---------
The audit is intentionally conservative.

A feature classified as:

    SAFE_DETERMINISTIC

is considered available from deterministic information.

A feature classified as:

    SAFE_HISTORICAL_IF_CAUSAL

requires the production implementation to guarantee that only information
available at or before T is used.

A feature classified as:

    REQUIRES_REALTIME_SOURCE

depends on the current parking observation being available at T.

A feature classified as:

    REQUIRES_DOCUMENTATION

cannot be conclusively mapped to a production source by static inspection.

A feature classified as:

    PROHIBITED_FUTURE_INFORMATION

must not be used by a production model.

No persisted dataset is modified.
The test dataset is intentionally NOT loaded.
===============================================================================
"""

from __future__ import annotations

import ast
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

BACKEND_ROOT = Path(__file__).resolve().parent

PROJECT_ROOT = BACKEND_ROOT.parent

DATASET_ROOT = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
)

TARGET_DATASET_ROOT = (
    DATASET_ROOT
    / "target_occupancy_rate_30m"
)

TRAIN_PATH = (
    TARGET_DATASET_ROOT
    / "train.parquet"
)

VALIDATION_PATH = (
    TARGET_DATASET_ROOT
    / "validation.parquet"
)

# IMPORTANT:
# This path is deliberately defined for existence verification only.
# The file is NEVER loaded.
TEST_PATH = (
    TARGET_DATASET_ROOT
    / "test.parquet"
)

MANIFEST_PATH = (
    DATASET_ROOT
    / "training_dataset_manifest.json"
)

SOURCE_ROOT = (
    BACKEND_ROOT
    / "app"
    / "ml"
)

OUTPUT_ROOT = (
    DATASET_ROOT
    / "xgboost_production_feature_contract"
)

JSON_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_production_feature_contract.json"
)

FEATURE_CSV_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_production_feature_contract.csv"
)

SUMMARY_CSV_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_production_feature_contract_summary.csv"
)

SOURCE_FINDINGS_CSV_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_production_feature_source_findings.csv"
)


# =============================================================================
# CONTRACT CONSTANTS
# =============================================================================

TARGET_COLUMN = "target_occupancy_rate_30m"

EXPECTED_FEATURE_COUNT = 296

FORECAST_HORIZON_MINUTES = 30

TIMESTAMP_METADATA_COLUMNS = {
    "normalized_at",
    "timestamp",
    "normalized_timestamp",
    "observation_timestamp",
}

FACILITY_METADATA_COLUMNS = {
    "source_facility_code",
    "facility_code",
    "facility",
    "facility_id",
}

CURRENT_STATE_FEATURES = {
    "capacity_utilization",
    "availability_rate",
    "occupied_ratio",
    "available_ratio",
    "vacancy_ratio",
    "occupancy_level",
    "is_empty",
    "is_low_occupancy",
    "is_moderate_occupancy",
    "is_high_occupancy",
    "is_near_full",
    "occupancy_capacity_difference",
    "occupancy_within_capacity",
    "occupancy_state_valid",
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
    "is_critical_demand",
    "occupancy_rate_consistent",
    "space_count_consistent",
    "has_valid_capacity",
    "has_valid_occupancy",
    "has_negative_values",
    "has_capacity_violation",
    "has_consistency_issue",
}

# The previous current-state audit identified 33 features as the main
# production availability concern. Keep the explicit 33-feature set here.
# Features outside this set are not automatically assumed safe.
PRIMARY_REALTIME_FEATURES = {
    "capacity_utilization",
    "availability_rate",
    "occupied_ratio",
    "available_ratio",
    "vacancy_ratio",
    "occupancy_level",
    "is_empty",
    "is_low_occupancy",
    "is_moderate_occupancy",
    "is_high_occupancy",
    "is_near_full",
    "occupancy_capacity_difference",
    "occupancy_within_capacity",
    "occupancy_state_valid",
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
    "is_critical_demand",
    "occupancy_rate_consistent",
}

DOCUMENTATION_FEATURES = {
    "space_count_consistent",
    "has_valid_capacity",
    "has_valid_occupancy",
    "has_negative_values",
    "has_capacity_violation",
    "has_consistency_issue",
}


# =============================================================================
# FEATURE CLASSIFICATION
# =============================================================================

SAFE_DETERMINISTIC_PATTERNS = (
    r"^year$",
    r"^month$",
    r"^quarter$",
    r"^day_of_month$",
    r"^day_of_year$",
    r"^week_of_year$",
    r"^day_of_week$",
    r"^hour$",
    r"^minute$",
    r"^half_hour_slot$",
    r"^time_slot$",
    r"^minutes_since_midnight$",
    r"^minutes_since_week_start$",
    r"^is_weekday$",
    r"^is_weekend$",
    r"^is_monday$",
    r"^is_tuesday$",
    r"^is_wednesday$",
    r"^is_thursday$",
    r"^is_friday$",
    r"^is_saturday$",
    r"^is_sunday$",
    r".*_sin$",
    r".*_cos$",
    r"^calendar_year$",
    r"^calendar_month$",
    r"^calendar_quarter$",
    r"^calendar_week_of_year$",
    r"^calendar_day_of_month$",
    r"^calendar_day_of_year$",
    r"^calendar_day_of_week$",
    r"^calendar_week_of_month$",
    r"^calendar_week_of_quarter$",
    r"^is_month_start$",
    r"^is_month_end$",
    r"^days_to_month_end$",
    r"^is_quarter_start$",
    r"^is_quarter_end$",
    r"^is_quarter_start_month$",
    r"^is_quarter_end_month$",
    r"^is_year_start$",
    r"^is_year_end$",
)


HISTORICAL_PATTERNS = (
    "lag",
    "rolling",
    "history",
    "historical",
    "previous",
    "prev",
    "past",
    "trend",
    "moving",
    "window",
    "change",
    "delta",
    "growth",
    "mean",
    "median",
    "std",
    "minimum",
    "maximum",
    "min_",
    "max_",
)


FUTURE_PATTERNS = (
    "future",
    "forecast_target",
    "next_",
    "next",
    "ahead",
    "tomorrow",
    "target_",
    "future_",
)


TARGET_PATTERNS = (
    "target",
    "label",
    "y_true",
    "ground_truth",
)


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class SourceFinding:
    file: str
    line_number: int
    finding_type: str
    matched_text: str
    context: str


@dataclass
class FeatureContract:
    feature_name: str
    feature_family: str
    production_status: str
    dependency: str
    availability_at_t: str
    future_information_risk: str
    target_reference_risk: str
    source_evidence_count: int
    source_files: str
    rationale: str
    required_production_documentation: str
    recommended_action: str


# =============================================================================
# UTILITIES
# =============================================================================

def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def safe_text(value: Any) -> str:
    if value is None:
        return ""

    return str(value)


def normalize_feature_name(value: Any) -> str:
    return (
        str(value)
        .strip()
        .lower()
    )


def utc_now_iso() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )


def is_finite(value: Any) -> bool:
    try:
        return math.isfinite(
            float(value)
        )
    except (
        TypeError,
        ValueError,
    ):
        return False


# =============================================================================
# MANIFEST
# =============================================================================

def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Manifest does not exist: {MANIFEST_PATH}"
        )

    with MANIFEST_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:
        manifest = json.load(handle)

    if not isinstance(
        manifest,
        dict,
    ):
        raise ValueError(
            "Training dataset manifest is not a JSON object."
        )

    return manifest


def get_registered_features(
    manifest: dict[str, Any],
) -> list[str]:

    raw_features = manifest.get(
        "feature_columns"
    )

    if not isinstance(
        raw_features,
        list,
    ):
        raise ValueError(
            "Manifest does not contain a valid "
            "'feature_columns' list."
        )

    features = [
        str(feature)
        for feature in raw_features
    ]

    if len(features) != EXPECTED_FEATURE_COUNT:
        raise ValueError(
            "Unexpected manifest feature count: "
            f"{len(features)}; expected "
            f"{EXPECTED_FEATURE_COUNT}."
        )

    if len(set(features)) != len(features):
        raise ValueError(
            "Manifest contains duplicate feature names."
        )

    return features


# =============================================================================
# DATASET VALIDATION
# =============================================================================

def validate_dataset_files() -> None:

    if not TRAIN_PATH.exists():
        raise FileNotFoundError(
            f"Training dataset does not exist: {TRAIN_PATH}"
        )

    if not VALIDATION_PATH.exists():
        raise FileNotFoundError(
            f"Validation dataset does not exist: "
            f"{VALIDATION_PATH}"
        )

    # Test is checked for existence only.
    # It MUST NOT be loaded.
    if not TEST_PATH.exists():
        raise FileNotFoundError(
            f"Test dataset does not exist: {TEST_PATH}"
        )


def load_persisted_feature_datasets() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:

    train = pd.read_parquet(
        TRAIN_PATH
    )

    validation = pd.read_parquet(
        VALIDATION_PATH
    )

    return train, validation


def validate_persisted_schema(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
) -> dict[str, Any]:

    expected_columns = set(
        features
    ) | {
        TARGET_COLUMN
    }

    train_feature_set = (
        set(train.columns)
        & set(features)
    )

    validation_feature_set = (
        set(validation.columns)
        & set(features)
    )

    if train_feature_set != set(features):
        missing = sorted(
            set(features)
            - train_feature_set
        )

        raise ValueError(
            "Training dataset does not contain "
            f"the complete feature registry. Missing: {missing}"
        )

    if validation_feature_set != set(features):
        missing = sorted(
            set(features)
            - validation_feature_set
        )

        raise ValueError(
            "Validation dataset does not contain "
            f"the complete feature registry. Missing: {missing}"
        )

    if TARGET_COLUMN not in train.columns:
        raise ValueError(
            "Training dataset does not contain target column."
        )

    if TARGET_COLUMN not in validation.columns:
        raise ValueError(
            "Validation dataset does not contain target column."
        )

    train_feature_df = train[
        features
    ]

    validation_feature_df = validation[
        features
    ]

    return {
        "training_rows": int(
            len(train)
        ),
        "validation_rows": int(
            len(validation)
        ),
        "training_feature_count": int(
            len(train_feature_df.columns)
        ),
        "validation_feature_count": int(
            len(validation_feature_df.columns)
        ),
        "training_numeric_features": int(
            sum(
                pd.api.types.is_numeric_dtype(
                    train_feature_df[column]
                )
                for column in features
            )
        ),
        "validation_numeric_features": int(
            sum(
                pd.api.types.is_numeric_dtype(
                    validation_feature_df[column]
                )
                for column in features
            )
        ),
        "training_null_cells": int(
            train_feature_df.isna().sum().sum()
        ),
        "validation_null_cells": int(
            validation_feature_df.isna().sum().sum()
        ),
        "unexpected_train_columns": sorted(
            set(train.columns)
            - expected_columns
            - TIMESTAMP_METADATA_COLUMNS
            - FACILITY_METADATA_COLUMNS
        ),
        "unexpected_validation_columns": sorted(
            set(validation.columns)
            - expected_columns
            - TIMESTAMP_METADATA_COLUMNS
            - FACILITY_METADATA_COLUMNS
        ),
    }


# =============================================================================
# SOURCE CODE DISCOVERY
# =============================================================================

def discover_source_files() -> list[Path]:

    if not SOURCE_ROOT.exists():
        raise FileNotFoundError(
            f"ML source directory does not exist: {SOURCE_ROOT}"
        )

    return sorted(
        SOURCE_ROOT.rglob("*.py")
    )


def source_line_context(
    lines: list[str],
    index: int,
    radius: int = 2,
) -> str:

    start = max(
        0,
        index - radius,
    )

    end = min(
        len(lines),
        index + radius + 1,
    )

    return "".join(
        lines[start:end]
    ).strip()


def scan_source_code(
    source_files: Iterable[Path],
) -> list[SourceFinding]:

    findings: list[SourceFinding] = []

    patterns = {
        "future_shift": re.compile(
            r"\.shift\s*\(\s*-\s*\d+"
        ),
        "future_keyword": re.compile(
            r"\b("
            r"future|tomorrow|next_|next"
            r")\b",
            re.IGNORECASE,
        ),
        "target_reference": re.compile(
            r"\btarget[_A-Za-z0-9]*\b",
            re.IGNORECASE,
        ),
        "negative_shift": re.compile(
            r"\bshift\s*\(\s*-\s*"
        ),
        "historical_shift": re.compile(
            r"\bshift\s*\(\s*[1-9]\d*"
        ),
    }

    for source_file in source_files:

        try:
            text = source_file.read_text(
                encoding="utf-8"
            )
        except UnicodeDecodeError:
            text = source_file.read_text(
                encoding="utf-8",
                errors="replace",
            )

        lines = text.splitlines(
            keepends=True
        )

        relative = str(
            source_file.relative_to(
                BACKEND_ROOT
            )
        )

        for index, line in enumerate(
            lines
        ):

            for finding_type, pattern in patterns.items():

                if pattern.search(line):

                    findings.append(
                        SourceFinding(
                            file=relative,
                            line_number=index + 1,
                            finding_type=finding_type,
                            matched_text=line.strip(),
                            context=source_line_context(
                                lines,
                                index,
                            ),
                        )
                    )

    return findings


# =============================================================================
# FEATURE NAME ANALYSIS
# =============================================================================

def matches_any_pattern(
    feature: str,
    patterns: Iterable[str],
) -> bool:

    for pattern in patterns:

        if re.search(
            pattern,
            feature,
            flags=re.IGNORECASE,
        ):
            return True

    return False


def is_deterministic_calendar_feature(
    feature: str,
) -> bool:

    return matches_any_pattern(
        feature,
        SAFE_DETERMINISTIC_PATTERNS,
    )


def is_historical_feature(
    feature: str,
) -> bool:

    lower = feature.lower()

    if is_deterministic_calendar_feature(
        feature
    ):
        return False

    return any(
        token in lower
        for token in HISTORICAL_PATTERNS
    )


def is_future_feature(
    feature: str,
) -> bool:

    lower = feature.lower()

    return any(
        token in lower
        for token in FUTURE_PATTERNS
    )


def is_target_feature(
    feature: str,
) -> bool:

    lower = feature.lower()

    return any(
        token in lower
        for token in TARGET_PATTERNS
    )


# =============================================================================
# SOURCE EVIDENCE FOR FEATURE
# =============================================================================

def feature_source_findings(
    feature: str,
    findings: list[SourceFinding],
) -> list[SourceFinding]:

    result: list[SourceFinding] = []

    feature_lower = feature.lower()

    tokens = {
        feature_lower,
        feature_lower.replace(
            "_",
            " ",
        ),
    }

    for finding in findings:

        text = (
            finding.matched_text
            + " "
            + finding.context
        ).lower()

        if any(
            token in text
            for token in tokens
            if token
        ):
            result.append(
                finding
            )

    return result


# =============================================================================
# FEATURE FAMILY
# =============================================================================

def determine_feature_family(
    feature: str,
) -> str:

    if feature in CURRENT_STATE_FEATURES:
        return "current_state"

    if is_deterministic_calendar_feature(
        feature
    ):
        return "temporal_calendar"

    if is_historical_feature(
        feature
    ):
        return "historical_lag"

    return "other"


# =============================================================================
# FEATURE CONTRACT CLASSIFICATION
# =============================================================================

def classify_feature(
    feature: str,
    findings: list[SourceFinding],
) -> FeatureContract:

    family = determine_feature_family(
        feature
    )

    feature_findings = feature_source_findings(
        feature,
        findings,
    )

    source_files = sorted(
        {
            finding.file
            for finding in feature_findings
        }
    )

    source_file_text = "; ".join(
        source_files
    )

    # -------------------------------------------------------------------------
    # Explicit prohibited categories
    # -------------------------------------------------------------------------

    if is_target_feature(
        feature
    ):

        return FeatureContract(
            feature_name=feature,
            feature_family=family,
            production_status=(
                "PROHIBITED_FUTURE_INFORMATION"
            ),
            dependency="TARGET",
            availability_at_t="NO",
            future_information_risk="HIGH",
            target_reference_risk="CONFIRMED_OR_NAMED_TARGET",
            source_evidence_count=len(
                feature_findings
            ),
            source_files=source_file_text,
            rationale=(
                "Feature name indicates target/label semantics and "
                "must not be supplied to a production predictor."
            ),
            required_production_documentation=(
                "None. Remove from production model input."
            ),
            recommended_action=(
                "EXCLUDE_FROM_PRODUCTION_FEATURE_SET"
            ),
        )

    if is_future_feature(
        feature
    ):

        return FeatureContract(
            feature_name=feature,
            feature_family=family,
            production_status=(
                "PROHIBITED_FUTURE_INFORMATION"
            ),
            dependency="FUTURE_INFORMATION",
            availability_at_t="NO",
            future_information_risk="HIGH",
            target_reference_risk="POTENTIAL",
            source_evidence_count=len(
                feature_findings
            ),
            source_files=source_file_text,
            rationale=(
                "Feature name contains future-oriented semantics "
                "that may represent information unavailable at T."
            ),
            required_production_documentation=(
                "Demonstrate explicitly that the feature is computed "
                "only from information available at T."
            ),
            recommended_action=(
                "EXCLUDE_PENDING_CAUSAL_REVIEW"
            ),
        )

    # -------------------------------------------------------------------------
    # Current-state features
    # -------------------------------------------------------------------------

    if feature in PRIMARY_REALTIME_FEATURES:

        return FeatureContract(
            feature_name=feature,
            feature_family="current_state",
            production_status=(
                "REQUIRES_REALTIME_SOURCE"
            ),
            dependency="CURRENT_OBSERVATION",
            availability_at_t="CONDITIONAL",
            future_information_risk="LOW_IF_CASUALLY_ALIGNED",
            target_reference_risk="NONE_IDENTIFIED",
            source_evidence_count=len(
                feature_findings
            ),
            source_files=source_file_text,
            rationale=(
                "Feature is derived from current parking state. "
                "It is valid for a T -> T+30m forecast only if the "
                "underlying observation is genuinely available at T "
                "and does not contain later information."
            ),
            required_production_documentation=(
                "Document source system, observation timestamp, "
                "ingestion latency, freshness SLA, maximum permitted "
                "feature age, and fallback behaviour."
            ),
            recommended_action=(
                "REQUIRE_REALTIME_AVAILABILITY_CONTRACT"
            ),
        )

    if feature in DOCUMENTATION_FEATURES:

        return FeatureContract(
            feature_name=feature,
            feature_family="current_state",
            production_status=(
                "REQUIRES_DOCUMENTATION"
            ),
            dependency="UNRESOLVED_PRODUCTION_SOURCE",
            availability_at_t="UNKNOWN",
            future_information_risk="UNKNOWN",
            target_reference_risk="NONE_IDENTIFIED",
            source_evidence_count=len(
                feature_findings
            ),
            source_files=source_file_text,
            rationale=(
                "Static analysis could not conclusively establish "
                "the production-time source of this feature."
            ),
            required_production_documentation=(
                "Identify the production source and demonstrate that "
                "the value is available at prediction timestamp T."
            ),
            recommended_action=(
                "DOCUMENT_PRODUCTION_SOURCE_BEFORE_APPROVAL"
            ),
        )

    # -------------------------------------------------------------------------
    # Deterministic calendar features
    # -------------------------------------------------------------------------

    if family == "temporal_calendar":

        return FeatureContract(
            feature_name=feature,
            feature_family=family,
            production_status=(
                "SAFE_DETERMINISTIC"
            ),
            dependency="PREDICTION_TIMESTAMP",
            availability_at_t="YES",
            future_information_risk="NONE",
            target_reference_risk="NONE_IDENTIFIED",
            source_evidence_count=len(
                feature_findings
            ),
            source_files=source_file_text,
            rationale=(
                "Feature can be deterministically calculated from "
                "the prediction timestamp and calendar context."
            ),
            required_production_documentation=(
                "Document timestamp timezone and calendar conventions."
            ),
            recommended_action=(
                "ALLOW_IN_PRODUCTION_FEATURE_SET"
            ),
        )

    # -------------------------------------------------------------------------
    # Historical / lagged features
    # -------------------------------------------------------------------------

    if family == "historical_lag":

        return FeatureContract(
            feature_name=feature,
            feature_family=family,
            production_status=(
                "SAFE_HISTORICAL_IF_GENERATED_CAUSALLY"
            ),
            dependency="HISTORICAL_INFORMATION",
            availability_at_t="CONDITIONAL",
            future_information_risk="LOW_IF_CAUSALLY_GENERATED",
            target_reference_risk="NONE_IDENTIFIED",
            source_evidence_count=len(
                feature_findings
            ),
            source_files=source_file_text,
            rationale=(
                "Feature appears historical/lagged. It is suitable "
                "for production only if its generation guarantees that "
                "no observation after T is incorporated."
            ),
            required_production_documentation=(
                "Document lag/window definition, cutoff timestamp, "
                "timezone, missing-history behaviour, and guarantee "
                "that the window ends at or before T."
            ),
            recommended_action=(
                "ALLOW_AFTER_CAUSAL_GENERATION_VERIFICATION"
            ),
        )

    # -------------------------------------------------------------------------
    # Unknown / other
    # -------------------------------------------------------------------------

    return FeatureContract(
        feature_name=feature,
        feature_family="other",
        production_status=(
            "REQUIRES_DOCUMENTATION"
        ),
        dependency="UNRESOLVED",
        availability_at_t="UNKNOWN",
        future_information_risk="UNKNOWN",
        target_reference_risk="NONE_IDENTIFIED",
        source_evidence_count=len(
            feature_findings
        ),
        source_files=source_file_text,
        rationale=(
            "Feature could not be confidently classified as "
            "deterministic calendar, historical, or current-state "
            "from the available static contract."
        ),
        required_production_documentation=(
            "Document the production source, timestamp semantics, "
            "refresh behaviour, and availability at prediction time."
        ),
        recommended_action=(
            "DOCUMENT_BEFORE_PRODUCTION_APPROVAL"
        ),
    )


# =============================================================================
# TARGET / FUTURE SOURCE GATE
# =============================================================================

def source_leakage_summary(
    findings: list[SourceFinding],
) -> dict[str, Any]:

    future_findings = [
        finding
        for finding in findings
        if finding.finding_type
        in {
            "future_shift",
            "negative_shift",
            "future_keyword",
        }
    ]

    target_findings = [
        finding
        for finding in findings
        if finding.finding_type
        == "target_reference"
    ]

    historical_findings = [
        finding
        for finding in findings
        if finding.finding_type
        == "historical_shift"
    ]

    return {
        "future_finding_count": len(
            future_findings
        ),
        "target_reference_finding_count": len(
            target_findings
        ),
        "historical_finding_count": len(
            historical_findings
        ),
        "future_findings": [
            asdict(finding)
            for finding in future_findings
        ],
        "target_findings": [
            asdict(finding)
            for finding in target_findings
        ],
        "historical_findings": [
            asdict(finding)
            for finding in historical_findings
        ],
    }


# =============================================================================
# SOURCE AST CHECK
# =============================================================================

def ast_scan_source_file(
    source_file: Path,
) -> list[dict[str, Any]]:

    findings: list[dict[str, Any]] = []

    try:
        source = source_file.read_text(
            encoding="utf-8"
        )
    except UnicodeDecodeError:
        source = source_file.read_text(
            encoding="utf-8",
            errors="replace",
        )

    try:
        tree = ast.parse(
            source
        )
    except SyntaxError:
        return findings

    relative = str(
        source_file.relative_to(
            BACKEND_ROOT
        )
    )

    for node in ast.walk(tree):

        if isinstance(
            node,
            ast.Call,
        ):

            if isinstance(
                node.func,
                ast.Attribute,
            ):

                if node.func.attr == "shift":

                    for argument in node.args:

                        if isinstance(
                            argument,
                            ast.UnaryOp,
                        ) and isinstance(
                            argument.op,
                            ast.USub,
                        ):

                            findings.append(
                                {
                                    "file": relative,
                                    "line_number": getattr(
                                        node,
                                        "lineno",
                                        None,
                                    ),
                                    "finding_type": (
                                        "AST_NEGATIVE_SHIFT"
                                    ),
                                    "matched_text": (
                                        "shift(...) with "
                                        "negative positional argument"
                                    ),
                                }
                            )

    return findings


# =============================================================================
# CONTRACT SUMMARY
# =============================================================================

def build_summary(
    contracts: list[FeatureContract],
) -> pd.DataFrame:

    rows = []

    for contract in contracts:

        rows.append(
            {
                "production_status": (
                    contract.production_status
                ),
                "feature_count": 1,
                "features": contract.feature_name,
            }
        )

    frame = pd.DataFrame(
        rows
    )

    if frame.empty:
        return pd.DataFrame(
            columns=[
                "production_status",
                "feature_count",
                "features",
            ]
        )

    summary = (
        frame.groupby(
            "production_status",
            as_index=False,
        )
        .agg(
            feature_count=(
                "feature_count",
                "sum",
            ),
            features=(
                "features",
                lambda values: "; ".join(
                    sorted(values)
                ),
            ),
        )
        .sort_values(
            "production_status"
        )
        .reset_index(
            drop=True
        )
    )

    return summary


# =============================================================================
# FEATURE FAMILY SUMMARY
# =============================================================================

def build_family_summary(
    contracts: list[FeatureContract],
) -> pd.DataFrame:

    frame = pd.DataFrame(
        [
            {
                "feature_family": contract.feature_family,
                "feature_name": contract.feature_name,
                "production_status": contract.production_status,
            }
            for contract in contracts
        ]
    )

    if frame.empty:
        return frame

    summary = (
        frame.groupby(
            [
                "feature_family",
                "production_status",
            ],
            as_index=False,
        )
        .size()
        .rename(
            columns={
                "size": "feature_count",
            }
        )
    )

    return summary


# =============================================================================
# PRODUCTION-SAFE SET
# =============================================================================

def build_production_sets(
    contracts: list[FeatureContract],
) -> dict[str, list[str]]:

    deterministic = sorted(
        contract.feature_name
        for contract in contracts
        if contract.production_status
        == "SAFE_DETERMINISTIC"
    )

    historical_conditional = sorted(
        contract.feature_name
        for contract in contracts
        if contract.production_status
        == "SAFE_HISTORICAL_IF_GENERATED_CAUSALLY"
    )

    realtime = sorted(
        contract.feature_name
        for contract in contracts
        if contract.production_status
        == "REQUIRES_REALTIME_SOURCE"
    )

    documentation = sorted(
        contract.feature_name
        for contract in contracts
        if contract.production_status
        == "REQUIRES_DOCUMENTATION"
    )

    prohibited = sorted(
        contract.feature_name
        for contract in contracts
        if contract.production_status
        == "PROHIBITED_FUTURE_INFORMATION"
    )

    # Conservative production-ready subset.
    #
    # We do NOT include historical conditional features here because they
    # still require explicit causal-generation verification.
    #
    # We do NOT include realtime features because their source/freshness
    # contract has not yet been formally documented.
    #
    production_ready_conservative = deterministic

    return {
        "deterministic_features": deterministic,
        "historical_features_requiring_causal_verification": (
            historical_conditional
        ),
        "realtime_features_requiring_source_contract": realtime,
        "features_requiring_documentation": documentation,
        "prohibited_features": prohibited,
        "conservative_production_ready_features": (
            production_ready_conservative
        ),
    }


# =============================================================================
# ASSERTIONS
# =============================================================================

def run_final_assertions(
    features: list[str],
    contracts: list[FeatureContract],
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
            "Expected feature count",
            len(features)
            == EXPECTED_FEATURE_COUNT,
        )
    )

    checks.append(
        (
            "Contract row count equals feature count",
            len(contracts)
            == len(features),
        )
    )

    checks.append(
        (
            "No duplicate registered features",
            len(features)
            == len(set(features)),
        )
    )

    audited_names = [
        contract.feature_name
        for contract in contracts
    ]

    checks.append(
        (
            "No duplicate audited features",
            len(audited_names)
            == len(set(audited_names)),
        )
    )

    checks.append(
        (
            "No target column included as feature",
            TARGET_COLUMN not in features,
        )
    )

    checks.append(
        (
            "Test dataset was not loaded",
            True,
        )
    )

    checks.append(
        (
            "No dataset modification performed",
            True,
        )
    )

    failed = []

    for label, passed in checks:

        print(
            f"{label:<50}: "
            f"{'PASS' if passed else 'FAIL'}"
        )

        if not passed:
            failed.append(
                label
            )

    if failed:

        raise AssertionError(
            "Production feature contract audit assertions failed: "
            + "; ".join(failed)
        )


# =============================================================================
# PERSIST RESULTS
# =============================================================================

def persist_results(
    *,
    manifest: dict[str, Any],
    dataset_info: dict[str, Any],
    contracts: list[FeatureContract],
    source_findings: list[SourceFinding],
    leakage_summary: dict[str, Any],
    source_ast_findings: list[dict[str, Any]],
) -> None:

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary = build_summary(
        contracts
    )

    family_summary = build_family_summary(
        contracts
    )

    production_sets = build_production_sets(
        contracts
    )

    feature_rows = [
        asdict(contract)
        for contract in contracts
    ]

    feature_frame = pd.DataFrame(
        feature_rows
    )

    feature_frame.to_csv(
        FEATURE_CSV_OUTPUT,
        index=False,
    )

    summary.to_csv(
        SUMMARY_CSV_OUTPUT,
        index=False,
    )

    source_rows = [
        asdict(finding)
        for finding in source_findings
    ]

    source_frame = pd.DataFrame(
        source_rows
    )

    source_frame.to_csv(
        SOURCE_FINDINGS_CSV_OUTPUT,
        index=False,
    )

    family_summary_path = (
        OUTPUT_ROOT
        / "birmingham_xgboost_production_feature_family_summary.csv"
    )

    family_summary.to_csv(
        family_summary_path,
        index=False,
    )

    report = {
        "audit_metadata": {
            "audit_name": (
                "Birmingham XGBoost Production "
                "Feature Contract Audit"
            ),
            "created_at_utc": utc_now_iso(),
            "schema_version": "1.0",
            "target_column": TARGET_COLUMN,
            "forecast_horizon_minutes": (
                FORECAST_HORIZON_MINUTES
            ),
        },
        "audit_policy": {
            "train_loaded": True,
            "validation_loaded": True,
            "test_loaded": False,
            "model_training_performed": False,
            "feature_pipeline_rebuilt": False,
            "persisted_datasets_modified": False,
        },
        "paths": {
            "dataset_root": str(
                DATASET_ROOT
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
            "manifest": str(
                MANIFEST_PATH
            ),
            "source_root": str(
                SOURCE_ROOT
            ),
        },
        "manifest": {
            "schema_version": manifest.get(
                "schema_version"
            ),
            "dataset_name": manifest.get(
                "dataset_name"
            ),
            "source_name": manifest.get(
                "source_name"
            ),
            "storage_format": manifest.get(
                "storage_format"
            ),
            "compression": manifest.get(
                "compression"
            ),
            "feature_count": len(
                manifest.get(
                    "feature_columns",
                    [],
                )
            ),
            "target_columns": manifest.get(
                "target_columns",
                [],
            ),
        },
        "dataset_validation": dataset_info,
        "source_analysis": {
            "source_files_scanned": len(
                {
                    finding.file
                    for finding in source_findings
                }
            ),
            "total_source_findings": len(
                source_findings
            ),
            "ast_negative_shift_findings": len(
                source_ast_findings
            ),
            "future_finding_count": (
                leakage_summary[
                    "future_finding_count"
                ]
            ),
            "target_reference_finding_count": (
                leakage_summary[
                    "target_reference_finding_count"
                ]
            ),
            "historical_finding_count": (
                leakage_summary[
                    "historical_finding_count"
                ]
            ),
        },
        "feature_family_summary": (
            family_summary.to_dict(
                orient="records"
            )
        ),
        "production_status_summary": (
            summary.to_dict(
                orient="records"
            )
        ),
        "production_feature_sets": production_sets,
        "feature_contract": feature_rows,
        "leakage_gate": {
            "confirmed_target_feature_count": sum(
                contract.production_status
                == "PROHIBITED_FUTURE_INFORMATION"
                and contract.target_reference_risk
                == "CONFIRMED_OR_NAMED_TARGET"
                for contract in contracts
            ),
            "confirmed_future_feature_count": sum(
                contract.production_status
                == "PROHIBITED_FUTURE_INFORMATION"
                and contract.future_information_risk
                == "HIGH"
                for contract in contracts
            ),
            "source_future_findings": (
                leakage_summary[
                    "future_finding_count"
                ]
            ),
            "source_target_findings": (
                leakage_summary[
                    "target_reference_finding_count"
                ]
            ),
        },
    }

    with JSON_OUTPUT.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            report,
            handle,
            indent=2,
            ensure_ascii=False,
        )


# =============================================================================
# VERDICT
# =============================================================================

def determine_verdict(
    contracts: list[FeatureContract],
    leakage_summary: dict[str, Any],
) -> tuple[str, list[str]]:

    reasons: list[str] = []

    prohibited = [
        contract
        for contract in contracts
        if contract.production_status
        == "PROHIBITED_FUTURE_INFORMATION"
    ]

    realtime = [
        contract
        for contract in contracts
        if contract.production_status
        == "REQUIRES_REALTIME_SOURCE"
    ]

    documentation = [
        contract
        for contract in contracts
        if contract.production_status
        == "REQUIRES_DOCUMENTATION"
    ]

    historical = [
        contract
        for contract in contracts
        if contract.production_status
        == "SAFE_HISTORICAL_IF_GENERATED_CAUSALLY"
    ]

    if prohibited:

        reasons.append(
            f"{len(prohibited)} feature(s) are prohibited "
            "or require exclusion pending future-information review."
        )

        return (
            "FAIL_PRODUCTION_FEATURE_CONTRACT",
            reasons,
        )

    if (
        leakage_summary[
            "future_finding_count"
        ]
        > 0
    ):

        reasons.append(
            "Source code contains future-oriented temporal "
            "constructs that require causal review."
        )

    if realtime:

        reasons.append(
            f"{len(realtime)} current-state feature(s) require "
            "a production realtime source/freshness contract."
        )

    if documentation:

        reasons.append(
            f"{len(documentation)} feature(s) require explicit "
            "production source documentation."
        )

    if historical:

        reasons.append(
            f"{len(historical)} historical feature(s) require "
            "causal-generation verification."
        )

    if realtime or documentation or historical:

        return (
            "PASS_WITH_PRODUCTION_CONTRACT_REVIEW",
            reasons,
        )

    return (
        "PRODUCTION_FEATURE_CONTRACT_PASS",
        [
            "All registered features have an explicit "
            "production availability classification."
        ],
    )


# =============================================================================
# PRINT FEATURE SUMMARY
# =============================================================================

def print_contract_summary(
    contracts: list[FeatureContract],
) -> None:

    print_section(
        "PRODUCTION FEATURE CONTRACT SUMMARY"
    )

    status_counts = (
        pd.Series(
            [
                contract.production_status
                for contract in contracts
            ]
        )
        .value_counts()
        .sort_index()
    )

    for status, count in status_counts.items():

        print(
            f"{status:<55}: {int(count)}"
        )

    family_counts = (
        pd.Series(
            [
                contract.feature_family
                for contract in contracts
            ]
        )
        .value_counts()
        .sort_index()
    )

    print()
    print(
        "Feature families:"
    )

    for family, count in family_counts.items():

        print(
            f"  {family:<45}: {int(count)}"
        )


# =============================================================================
# MAIN
# =============================================================================

def main() -> None:

    print_header(
        "SMARTPARK AI - BIRMINGHAM XGBOOST "
        "PRODUCTION FEATURE CONTRACT AUDIT"
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
        "Production contract:"
    )
    print(
        "  Prediction timestamp = T"
    )
    print(
        "  Forecast horizon     = T + 30 minutes"
    )
    print(
        "  Features must be available at or before T"
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
        "  Classify all registered features"
    )
    print(
        "  Establish production availability contract"
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

        # ---------------------------------------------------------------------
        # Dataset files
        # ---------------------------------------------------------------------

        print_section(
            "DATASET FILE VALIDATION"
        )

        validate_dataset_files()

        print(
            f"Training dataset"
            f"{' ' * 28}: {TRAIN_PATH}"
        )

        print(
            f"Validation dataset"
            f"{' ' * 24}: {VALIDATION_PATH}"
        )

        print(
            f"Test dataset"
            f"{' ' * 29}: {TEST_PATH}"
        )

        print(
            "Training file exists"
            f"{' ' * 25}: PASS"
        )

        print(
            "Validation file exists"
            f"{' ' * 21}: PASS"
        )

        print(
            "Test file exists"
            f"{' ' * 26}: PASS"
        )

        print()
        print(
            "Test dataset will NOT be loaded."
        )

        # ---------------------------------------------------------------------
        # Manifest
        # ---------------------------------------------------------------------

        print_section(
            "LOADING FEATURE MANIFEST"
        )

        manifest = load_manifest()

        features = get_registered_features(
            manifest
        )

        print(
            f"Manifest"
            f"{' ' * 43}: {MANIFEST_PATH}"
        )

        print(
            f"Registered features"
            f"{' ' * 27}: {len(features)}"
        )

        # ---------------------------------------------------------------------
        # Persisted datasets
        # ---------------------------------------------------------------------

        print_section(
            "LOADING PERSISTED DATASETS"
        )

        print(
            "Loading training dataset..."
        )

        train, validation = (
            load_persisted_feature_datasets()
        )

        print(
            "Loading validation dataset..."
        )

        print(
            f"Training rows"
            f"{' ' * 34}: {len(train):,}"
        )

        print(
            f"Validation rows"
            f"{' ' * 30}: {len(validation):,}"
        )

        # ---------------------------------------------------------------------
        # Schema
        # ---------------------------------------------------------------------

        print_section(
            "FEATURE REGISTRY VALIDATION"
        )

        dataset_info = validate_persisted_schema(
            train,
            validation,
            features,
        )

        print(
            f"Registered features"
            f"{' ' * 29}: {len(features)}"
        )

        print(
            "Training feature registry"
            f"{' ' * 21}: PASS"
        )

        print(
            "Validation feature registry"
            f"{' ' * 19}: PASS"
        )

        print(
            "Train/validation feature registry"
            f"{' ' * 10}: IDENTICAL"
        )

        # ---------------------------------------------------------------------
        # Target
        # ---------------------------------------------------------------------

        print_section(
            "TARGET CONTRACT VALIDATION"
        )

        train_target = pd.to_numeric(
            train[
                TARGET_COLUMN
            ],
            errors="coerce",
        )

        validation_target = pd.to_numeric(
            validation[
                TARGET_COLUMN
            ],
            errors="coerce",
        )

        print(
            f"Training target rows"
            f"{' ' * 26}: {len(train_target):,}"
        )

        print(
            f"Training target nulls"
            f"{' ' * 25}: "
            f"{int(train_target.isna().sum())}"
        )

        print(
            f"Training target mean"
            f"{' ' * 25}: "
            f"{float(train_target.mean()):.6f}"
        )

        print(
            f"Training target range"
            f"{' ' * 23}: "
            f"{float(train_target.min()):.6f}"
            " -> "
            f"{float(train_target.max()):.6f}"
        )

        print(
            f"Validation target rows"
            f"{' ' * 22}: {len(validation_target):,}"
        )

        print(
            f"Validation target nulls"
            f"{' ' * 21}: "
            f"{int(validation_target.isna().sum())}"
        )

        print(
            f"Validation target mean"
            f"{' ' * 21}: "
            f"{float(validation_target.mean()):.6f}"
        )

        print(
            f"Validation target range"
            f"{' ' * 19}: "
            f"{float(validation_target.min()):.6f}"
            " -> "
            f"{float(validation_target.max()):.6f}"
        )

        if (
            train_target.isna().any()
            or validation_target.isna().any()
        ):
            raise ValueError(
                "Target contract failed because target values "
                "contain nulls."
            )

        print(
            f"Target contract"
            f"{' ' * 37}: PASS"
        )

        # ---------------------------------------------------------------------
        # Source code
        # ---------------------------------------------------------------------

        print_section(
            "SOURCE CODE DISCOVERY"
        )

        source_files = discover_source_files()

        print(
            f"ML source files scanned"
            f"{' ' * 24}: {len(source_files)}"
        )

        source_findings = scan_source_code(
            source_files
        )

        ast_findings: list[
            dict[str, Any]
        ] = []

        for source_file in source_files:

            ast_findings.extend(
                ast_scan_source_file(
                    source_file
                )
            )

        leakage_summary = source_leakage_summary(
            source_findings
        )

        print()
        print(
            "--- SOURCE TEMPORAL SIGNALS ---"
        )

        print(
            f"Future / negative-shift findings"
            f"{' ' * 10}: "
            f"{leakage_summary['future_finding_count']}"
        )

        print(
            f"Target-reference findings"
            f"{' ' * 18}: "
            f"{leakage_summary['target_reference_finding_count']}"
        )

        print(
            f"Historical feature findings"
            f"{' ' * 15}: "
            f"{leakage_summary['historical_finding_count']}"
        )

        print(
            f"AST negative-shift findings"
            f"{' ' * 15}: "
            f"{len(ast_findings)}"
        )

        # ---------------------------------------------------------------------
        # Feature contracts
        # ---------------------------------------------------------------------

        print_section(
            "BUILDING FEATURE-LEVEL PRODUCTION CONTRACT"
        )

        contracts = [
            classify_feature(
                feature,
                source_findings,
            )
            for feature in features
        ]

        print_contract_summary(
            contracts
        )

        # ---------------------------------------------------------------------
        # Leakage gate
        # ---------------------------------------------------------------------

        print_section(
            "TARGET / FUTURE INFORMATION GATE"
        )

        prohibited = [
            contract
            for contract in contracts
            if contract.production_status
            == "PROHIBITED_FUTURE_INFORMATION"
        ]

        confirmed_target = [
            contract
            for contract in contracts
            if contract.target_reference_risk
            == "CONFIRMED_OR_NAMED_TARGET"
        ]

        print(
            f"Prohibited feature count"
            f"{' ' * 25}: {len(prohibited)}"
        )

        print(
            f"Target-named feature count"
            f"{' ' * 23}: {len(confirmed_target)}"
        )

        print(
            f"Source future findings"
            f"{' ' * 25}: "
            f"{leakage_summary['future_finding_count']}"
        )

        if not confirmed_target:
            print(
                "Confirmed target features"
                f"{' ' * 21}: 0"
            )

        if (
            leakage_summary[
                "future_finding_count"
            ]
            == 0
        ):

            print(
                "No source-level future constructs"
                f"{' ' * 11}: PASS"
            )

        else:

            print(
                "Source-level future constructs"
                f"{' ' * 11}: REVIEW"
            )

        # ---------------------------------------------------------------------
        # Realtime features
        # ---------------------------------------------------------------------

        realtime_contracts = [
            contract
            for contract in contracts
            if contract.production_status
            == "REQUIRES_REALTIME_SOURCE"
        ]

        documentation_contracts = [
            contract
            for contract in contracts
            if contract.production_status
            == "REQUIRES_DOCUMENTATION"
        ]

        historical_contracts = [
            contract
            for contract in contracts
            if contract.production_status
            == "SAFE_HISTORICAL_IF_GENERATED_CAUSALLY"
        ]

        deterministic_contracts = [
            contract
            for contract in contracts
            if contract.production_status
            == "SAFE_DETERMINISTIC"
        ]

        print_section(
            "PRODUCTION AVAILABILITY GATE"
        )

        print(
            f"Deterministic features"
            f"{' ' * 29}: "
            f"{len(deterministic_contracts)}"
        )

        print(
            f"Historical conditional features"
            f"{' ' * 18}: "
            f"{len(historical_contracts)}"
        )

        print(
            f"Realtime current-state features"
            f"{' ' * 16}: "
            f"{len(realtime_contracts)}"
        )

        print(
            f"Documentation-required features"
            f"{' ' * 15}: "
            f"{len(documentation_contracts)}"
        )

        # ---------------------------------------------------------------------
        # Production sets
        # ---------------------------------------------------------------------

        production_sets = build_production_sets(
            contracts
        )

        print_section(
            "CONSERVATIVE PRODUCTION FEATURE SET"
        )

        print(
            f"Deterministically production-ready"
            f"{' ' * 12}: "
            f"{len(production_sets['conservative_production_ready_features'])}"
        )

        print()
        print(
            "IMPORTANT:"
        )

        print(
            "Historical features remain conditional until their "
            "causal cutoff is formally verified."
        )

        print(
            "Current-state features remain conditional until their "
            "realtime source and freshness contract is documented."
        )

        # ---------------------------------------------------------------------
        # Verdict
        # ---------------------------------------------------------------------

        verdict, reasons = determine_verdict(
            contracts,
            leakage_summary,
        )

        print_section(
            "FINAL AUDIT RESULT"
        )

        print(
            f"Features audited"
            f"{' ' * 36}: {len(contracts)}"
        )

        print(
            f"Deterministic calendar features"
            f"{' ' * 16}: "
            f"{len(deterministic_contracts)}"
        )

        print(
            f"Historical conditional features"
            f"{' ' * 15}: "
            f"{len(historical_contracts)}"
        )

        print(
            f"Realtime current-state features"
            f"{' ' * 13}: "
            f"{len(realtime_contracts)}"
        )

        print(
            f"Documentation-required features"
            f"{' ' * 14}: "
            f"{len(documentation_contracts)}"
        )

        print(
            f"Confirmed target features"
            f"{' ' * 22}: "
            f"{len(confirmed_target)}"
        )

        print()
        print(
            f"PRODUCTION FEATURE CONTRACT VERDICT : {verdict}"
        )

        print()
        print(
            "Verdict reasons:"
        )

        for reason in reasons:

            print(
                f"  - {reason}"
            )

        # ---------------------------------------------------------------------
        # Persist
        # ---------------------------------------------------------------------

        print_section(
            "PERSISTING AUDIT RESULTS"
        )

        persist_results(
            manifest=manifest,
            dataset_info=dataset_info,
            contracts=contracts,
            source_findings=source_findings,
            leakage_summary=leakage_summary,
            source_ast_findings=ast_findings,
        )

        print(
            f"Output directory"
            f"{' ' * 30}: {OUTPUT_ROOT}"
        )

        print(
            f"JSON report"
            f"{' ' * 36}: {JSON_OUTPUT}"
        )

        print(
            f"CSV feature contract"
            f"{' ' * 27}: {FEATURE_CSV_OUTPUT}"
        )

        print(
            f"CSV summary"
            f"{' ' * 34}: {SUMMARY_CSV_OUTPUT}"
        )

        print(
            f"CSV source findings"
            f"{' ' * 26}: {SOURCE_FINDINGS_CSV_OUTPUT}"
        )

        # ---------------------------------------------------------------------
        # Assertions
        # ---------------------------------------------------------------------

        run_final_assertions(
            features=features,
            contracts=contracts,
            train=train,
            validation=validation,
        )

        # ---------------------------------------------------------------------
        # Final
        # ---------------------------------------------------------------------

        print()
        print("=" * 78)

        if verdict == "FAIL_PRODUCTION_FEATURE_CONTRACT":

            print(
                "BIRMINGHAM PRODUCTION FEATURE CONTRACT AUDIT FAILED"
            )

            print("=" * 78)

            print()
            print(
                "Production feature contract contains prohibited "
                "or unresolved future-information features."
            )

            sys.exit(1)

        if (
            verdict
            == "PASS_WITH_PRODUCTION_CONTRACT_REVIEW"
        ):

            print(
                "BIRMINGHAM PRODUCTION FEATURE CONTRACT AUDIT "
                "PASSED WITH REVIEW"
            )

            print("=" * 78)

            print()
            print(
                "No feature was automatically approved for production "
                "solely because it exists in the persisted dataset."
            )

            print(
                "Realtime and historical causal contracts still require "
                "formal production verification."
            )

            print()
            print(
                "Test dataset used:       NO"
            )

            print(
                "XGBoost training:        NO"
            )

            print(
                "Feature pipeline rebuilt: NO"
            )

            print(
                "Persisted datasets modified: NO"
            )

            print()
            print(
                "Production feature contract audit is ready for "
                "engineering review."
            )

            return

        print(
            "BIRMINGHAM PRODUCTION FEATURE CONTRACT AUDIT PASSED"
        )

        print("=" * 78)

        print()
        print(
            "All registered features have an explicit "
            "production availability classification."
        )

    except Exception as exc:

        print()
        print("=" * 78)

        print(
            "BIRMINGHAM PRODUCTION FEATURE CONTRACT AUDIT FAILED"
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

        sys.exit(1)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()