"""
SMARTPARK AI
Birmingham XGBoost Feature Leakage / Temporal Availability Audit

Purpose
-------
Audit the 296 registered Birmingham ML features for:

1. Future-data references.
2. Target-derived features.
3. Forward-looking / centered windows.
4. Negative pandas shifts.
5. Suspicious temporal transformations.
6. Current-state dependencies.
7. Feature availability at prediction timestamp.
8. Feature lineage in the actual ML feature-generation source code.

IMPORTANT
---------
This script is READ-ONLY.

It does NOT:
    - modify train.parquet
    - modify validation.parquet
    - modify test.parquet
    - rebuild the Birmingham feature pipeline
    - train XGBoost
    - tune XGBoost
    - modify the manifest

The audit is intentionally conservative.

A feature is not automatically declared safe merely because its
name looks safe. The script combines:

    persisted feature registry
            +
    source-code lineage search
            +
    temporal dependency heuristics
            +
    target/future-reference detection

Ambiguous features are reported for manual review rather than silently
declared safe.

Target:
    target_occupancy_rate_30m
"""

from __future__ import annotations

import ast
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd


# ============================================================================
# PATHS
# ============================================================================

BACKEND_ROOT = Path(__file__).resolve().parent

PROJECT_ROOT = BACKEND_ROOT.parent

DATASETS_ROOT = (
    PROJECT_ROOT
    / "datasets"
)

PROCESSED_BIRMINGHAM_ROOT = (
    DATASETS_ROOT
    / "processed"
    / "birmingham"
)

MANIFEST_PATH = (
    PROCESSED_BIRMINGHAM_ROOT
    / "training_dataset_manifest.json"
)

TRAIN_PATH = (
    PROCESSED_BIRMINGHAM_ROOT
    / "target_occupancy_rate_30m"
    / "train.parquet"
)

VALIDATION_PATH = (
    PROCESSED_BIRMINGHAM_ROOT
    / "target_occupancy_rate_30m"
    / "validation.parquet"
)

TEST_PATH = (
    PROCESSED_BIRMINGHAM_ROOT
    / "target_occupancy_rate_30m"
    / "test.parquet"
)

OUTPUT_ROOT = (
    PROCESSED_BIRMINGHAM_ROOT
    / "xgboost_temporal_leakage_audit"
)

JSON_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_temporal_leakage_audit.json"
)

CSV_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_temporal_leakage_audit.csv"
)


# ============================================================================
# AUDIT CONTRACT
# ============================================================================

TARGET_COLUMN = (
    "target_occupancy_rate_30m"
)

EXPECTED_FEATURE_COUNT = 296

METADATA_COLUMNS = {
    "source_facility_code",
    "normalized_at",
}

KNOWN_CATEGORICAL_FEATURES = {
    "occupancy_level",
    "demand_class",
}


# ============================================================================
# SOURCE DIRECTORIES
# ============================================================================

FEATURE_SOURCE_DIRECTORIES = [
    BACKEND_ROOT
    / "app"
    / "ml"
    / "features",

    BACKEND_ROOT
    / "app"
    / "ml"
    / "data",
]


# ============================================================================
# FEATURE CLASSIFICATION
# ============================================================================


class FeatureClassification:
    TEMPORAL = "temporal_calendar"
    HISTORICAL_LAG = "historical_lag"
    ROLLING_HISTORICAL = "rolling_historical"
    STATIC_FACILITY = "static_facility"
    CURRENT_STATE = "current_state"
    TARGET_DERIVED = "target_derived"
    FUTURE_DERIVED = "future_derived"
    AMBIGUOUS = "ambiguous"
    OTHER = "other"


class RiskLevel:
    SAFE = "SAFE"
    REVIEW = "REVIEW"
    LEAKAGE = "LEAKAGE"


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class SourceEvidence:
    file: str
    line_number: int
    line: str
    matched_patterns: list[str] = field(
        default_factory=list
    )


@dataclass
class FeatureAudit:
    feature: str

    classification: str

    risk_level: str

    registered: bool = True

    metadata_column: bool = False

    numeric_training: Optional[bool] = None

    numeric_validation: Optional[bool] = None

    training_null_count: Optional[int] = None

    validation_null_count: Optional[int] = None

    future_reference_detected: bool = False

    target_reference_detected: bool = False

    negative_shift_detected: bool = False

    forward_window_detected: bool = False

    centered_window_detected: bool = False

    expanding_window_detected: bool = False

    rolling_operation_detected: bool = False

    lag_operation_detected: bool = False

    current_state_indicator: bool = False

    source_evidence_count: int = 0

    source_files: list[str] = field(
        default_factory=list
    )

    source_evidence: list[SourceEvidence] = field(
        default_factory=list
    )

    reasons: list[str] = field(
        default_factory=list
    )

    manual_review_required: bool = False


# ============================================================================
# AUDIT STATE
# ============================================================================


@dataclass
class AuditState:

    manifest_loaded: bool = False

    parquet_loaded: bool = False

    manifest_feature_count: int = 0

    training_rows: int = 0

    validation_rows: int = 0

    test_loaded: bool = False

    source_files_scanned: int = 0

    features_audited: int = 0

    safe_features: int = 0

    review_features: int = 0

    leakage_features: int = 0

    checks_executed: int = 0

    checks_passed: int = 0

    checks_failed: int = 0

    warnings: int = 0


# ============================================================================
# PRINT HELPERS
# ============================================================================


def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def print_check(
    label: str,
    passed: bool,
) -> None:

    status = (
        "PASS"
        if passed
        else "FAIL"
    )

    print(
        f"{label:<52}: {status}"
    )


# ============================================================================
# CHECK ACCOUNTING
# ============================================================================


def register_check(
    state: AuditState,
    passed: bool,
) -> None:

    state.checks_executed += 1

    if passed:
        state.checks_passed += 1
    else:
        state.checks_failed += 1


# ============================================================================
# MANIFEST
# ============================================================================


def load_manifest() -> dict[str, Any]:

    if not MANIFEST_PATH.exists():

        raise FileNotFoundError(
            "Training dataset manifest does not exist: "
            f"{MANIFEST_PATH}"
        )

    with MANIFEST_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:

        manifest = json.load(
            handle
        )

    if not isinstance(
        manifest,
        dict,
    ):

        raise ValueError(
            "Training dataset manifest must contain "
            "a JSON object."
        )

    return manifest


def validate_manifest(
    manifest: dict[str, Any],
    state: AuditState,
) -> list[str]:

    print_section(
        "MANIFEST VALIDATION"
    )

    feature_columns = manifest.get(
        "feature_columns",
        [],
    )

    target_columns = manifest.get(
        "target_columns",
        [],
    )

    state.manifest_loaded = True

    state.manifest_feature_count = (
        len(feature_columns)
    )

    print(
        f"Schema version                       : "
        f"{manifest.get('schema_version')}"
    )

    print(
        f"Dataset name                         : "
        f"{manifest.get('dataset_name')}"
    )

    print(
        f"Source name                          : "
        f"{manifest.get('source_name')}"
    )

    print(
        f"Registered feature count              : "
        f"{len(feature_columns)}"
    )

    print(
        f"Target count                         : "
        f"{len(target_columns)}"
    )

    print(
        f"Target                                : "
        f"{TARGET_COLUMN}"
    )

    register_check(
        state,
        len(feature_columns)
        == EXPECTED_FEATURE_COUNT,
    )

    print_check(
        "Expected 296 registered features",
        len(feature_columns)
        == EXPECTED_FEATURE_COUNT,
    )

    register_check(
        state,
        TARGET_COLUMN in target_columns,
    )

    print_check(
        "30-minute target registered",
        TARGET_COLUMN in target_columns,
    )

    duplicates = [
        feature
        for feature in set(feature_columns)
        if feature_columns.count(feature) > 1
    ]

    register_check(
        state,
        not duplicates,
    )

    print_check(
        "No duplicate feature names",
        not duplicates,
    )

    return [
        str(feature)
        for feature in feature_columns
    ]


# ============================================================================
# PARQUET VALIDATION
# ============================================================================


def load_training_and_validation(
    state: AuditState,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    print_section(
        "LOADING PERSISTED DATASETS"
    )

    if not TRAIN_PATH.exists():

        raise FileNotFoundError(
            f"Training dataset not found: "
            f"{TRAIN_PATH}"
        )

    if not VALIDATION_PATH.exists():

        raise FileNotFoundError(
            f"Validation dataset not found: "
            f"{VALIDATION_PATH}"
        )

    train = pd.read_parquet(
        TRAIN_PATH
    )

    validation = pd.read_parquet(
        VALIDATION_PATH
    )

    state.parquet_loaded = True

    state.training_rows = len(
        train
    )

    state.validation_rows = len(
        validation
    )

    print(
        f"Training rows                         : "
        f"{len(train):,}"
    )

    print(
        f"Validation rows                       : "
        f"{len(validation):,}"
    )

    print(
        f"Test dataset loaded                   : NO"
    )

    register_check(
        state,
        len(train) > 0,
    )

    print_check(
        "Training dataset non-empty",
        len(train) > 0,
    )

    register_check(
        state,
        len(validation) > 0,
    )

    print_check(
        "Validation dataset non-empty",
        len(validation) > 0,
    )

    return train, validation


# ============================================================================
# SOURCE FILE DISCOVERY
# ============================================================================


def discover_source_files() -> list[Path]:

    files: list[Path] = []

    for directory in FEATURE_SOURCE_DIRECTORIES:

        if not directory.exists():
            continue

        files.extend(
            directory.rglob("*.py")
        )

    unique = sorted(
        set(
            path.resolve()
            for path in files
        )
    )

    return unique


# ============================================================================
# SOURCE INDEX
# ============================================================================


@dataclass
class SourceLine:

    path: Path
    line_number: int
    text: str


def build_source_index(
    source_files: Iterable[Path],
) -> list[SourceLine]:

    index: list[SourceLine] = []

    for path in source_files:

        try:

            lines = path.read_text(
                encoding="utf-8",
                errors="replace",
            ).splitlines()

        except OSError:

            continue

        for number, line in enumerate(
            lines,
            start=1,
        ):

            index.append(
                SourceLine(
                    path=path,
                    line_number=number,
                    text=line,
                )
            )

    return index


# ============================================================================
# SOURCE PATTERNS
# ============================================================================


NEGATIVE_SHIFT_PATTERN = re.compile(
    r"""
    \.shift\s*\(
    \s*-
    """,
    re.IGNORECASE | re.VERBOSE,
)

SHIFT_NEGATIVE_ARGUMENT_PATTERN = re.compile(
    r"""
    shift
    \s*\(
    [^)]*-
    \d+
    """,
    re.IGNORECASE | re.VERBOSE,
)

CENTERED_ROLLING_PATTERN = re.compile(
    r"""
    \.rolling
    \s*\(
    [^)]*
    center
    \s*=
    \s*True
    """,
    re.IGNORECASE | re.VERBOSE,
)

FORWARD_LOOKING_WORD_PATTERN = re.compile(
    r"""
    (
        future
        |
        forward
        |
        lead
        |
        lookahead
        |
        next[_\s-]?
        |
        tomorrow
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

TARGET_PATTERN = re.compile(
    r"""
    (
        target_
        |
        TARGET_
        |
        y_true
        |
        target_column
        |
        target_columns
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

ROLLING_PATTERN = re.compile(
    r"""
    \.rolling\s*\(
    """,
    re.IGNORECASE | re.VERBOSE,
)

EXPANDING_PATTERN = re.compile(
    r"""
    \.expanding\s*\(
    """,
    re.IGNORECASE | re.VERBOSE,
)

LAG_PATTERN = re.compile(
    r"""
    (
        \.shift\s*\(
        |
        lag
        |
        previous
        |
        prior
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


# ============================================================================
# FEATURE NAME HEURISTICS
# ============================================================================


TEMPORAL_FEATURE_PATTERNS = [
    "year",
    "month",
    "quarter",
    "day_of_month",
    "day_of_year",
    "day_of_week",
    "week_of_year",
    "week_of_month",
    "week_of_quarter",
    "hour",
    "minute",
    "time_slot",
    "minutes_since",
    "calendar_",
    "is_weekday",
    "is_weekend",
    "is_monday",
    "is_tuesday",
    "is_wednesday",
    "is_thursday",
    "is_friday",
    "is_saturday",
    "is_sunday",
    "_sin",
    "_cos",
]

HISTORICAL_PATTERNS = [
    "lag_",
    "previous_",
    "prior_",
    "past_",
    "history_",
    "historical_",
    "rolling_",
    "rolling",
]

STATIC_FACILITY_PATTERNS = [
    "capacity",
    "spaces",
    "facility_type",
    "facility_category",
]

CURRENT_STATE_PATTERNS = [
    "occupancy_rate",
    "occupied_ratio",
    "available_ratio",
    "availability_rate",
    "vacancy_ratio",
    "capacity_utilization",
    "occupancy_level",
    "demand_level",
    "demand_pressure",
    "remaining_capacity",
    "availability_pressure",
    "is_low_occupancy",
    "is_moderate_occupancy",
    "is_high_occupancy",
    "is_near_full",
    "is_low_availability",
    "is_critical_availability",
    "is_full",
    "is_capacity_exceeded",
    "demand_class",
]


def classify_feature_name(
    feature: str,
) -> str:

    lower = feature.lower()

    if (
        "target" in lower
        or lower.startswith("future_")
        or lower.startswith("next_")
    ):

        return FeatureClassification.TARGET_DERIVED

    if any(
        pattern in lower
        for pattern in TEMPORAL_FEATURE_PATTERNS
    ):

        return FeatureClassification.TEMPORAL

    if any(
        pattern in lower
        for pattern in HISTORICAL_PATTERNS
    ):

        return FeatureClassification.HISTORICAL_LAG

    if any(
        pattern in lower
        for pattern in STATIC_FACILITY_PATTERNS
    ):

        return FeatureClassification.STATIC_FACILITY

    if any(
        pattern in lower
        for pattern in CURRENT_STATE_PATTERNS
    ):

        return FeatureClassification.CURRENT_STATE

    return FeatureClassification.OTHER


# ============================================================================
# SOURCE SEARCH
# ============================================================================


def feature_related_evidence(
    feature: str,
    source_index: list[SourceLine],
) -> list[SourceEvidence]:

    evidence: list[SourceEvidence] = []

    escaped = re.escape(
        feature
    )

    feature_pattern = re.compile(
        rf"""
        (?<![A-Za-z0-9_])
        {escaped}
        (?![A-Za-z0-9_])
        """,
        re.IGNORECASE | re.VERBOSE,
    )

    for source_line in source_index:

        if not feature_pattern.search(
            source_line.text
        ):
            continue

        matched_patterns: list[str] = []

        if (
            NEGATIVE_SHIFT_PATTERN.search(
                source_line.text
            )
            or SHIFT_NEGATIVE_ARGUMENT_PATTERN.search(
                source_line.text
            )
        ):

            matched_patterns.append(
                "negative_shift"
            )

        if (
            CENTERED_ROLLING_PATTERN.search(
                source_line.text
            )
        ):

            matched_patterns.append(
                "centered_rolling"
            )

        if (
            FORWARD_LOOKING_WORD_PATTERN.search(
                source_line.text
            )
        ):

            matched_patterns.append(
                "future_keyword"
            )

        if (
            TARGET_PATTERN.search(
                source_line.text
            )
        ):

            matched_patterns.append(
                "target_keyword"
            )

        if (
            ROLLING_PATTERN.search(
                source_line.text
            )
        ):

            matched_patterns.append(
                "rolling_operation"
            )

        if (
            EXPANDING_PATTERN.search(
                source_line.text
            )
        ):

            matched_patterns.append(
                "expanding_operation"
            )

        if (
            LAG_PATTERN.search(
                source_line.text
            )
        ):

            matched_patterns.append(
                "lag_operation"
            )

        evidence.append(
            SourceEvidence(
                file=str(
                    source_line.path
                ),
                line_number=(
                    source_line.line_number
                ),
                line=(
                    source_line.text.strip()
                ),
                matched_patterns=(
                    matched_patterns
                ),
            )
        )

    return evidence


# ============================================================================
# SOURCE-WIDE TEMPORAL ANALYSIS
# ============================================================================


@dataclass
class SourceTemporalSignals:

    negative_shift_lines: list[SourceEvidence] = field(
        default_factory=list
    )

    centered_rolling_lines: list[SourceEvidence] = field(
        default_factory=list
    )

    future_keyword_lines: list[SourceEvidence] = field(
        default_factory=list
    )

    target_keyword_lines: list[SourceEvidence] = field(
        default_factory=list
    )

    expanding_lines: list[SourceEvidence] = field(
        default_factory=list
    )


def scan_source_temporal_signals(
    source_index: list[SourceLine],
) -> SourceTemporalSignals:

    signals = SourceTemporalSignals()

    for source_line in source_index:

        text = source_line.text

        if (
            NEGATIVE_SHIFT_PATTERN.search(
                text
            )
            or SHIFT_NEGATIVE_ARGUMENT_PATTERN.search(
                text
            )
        ):

            signals.negative_shift_lines.append(
                SourceEvidence(
                    file=str(
                        source_line.path
                    ),
                    line_number=(
                        source_line.line_number
                    ),
                    line=text.strip(),
                    matched_patterns=[
                        "negative_shift"
                    ],
                )
            )

        if (
            CENTERED_ROLLING_PATTERN.search(
                text
            )
        ):

            signals.centered_rolling_lines.append(
                SourceEvidence(
                    file=str(
                        source_line.path
                    ),
                    line_number=(
                        source_line.line_number
                    ),
                    line=text.strip(),
                    matched_patterns=[
                        "centered_rolling"
                    ],
                )
            )

        if (
            FORWARD_LOOKING_WORD_PATTERN.search(
                text
            )
        ):

            signals.future_keyword_lines.append(
                SourceEvidence(
                    file=str(
                        source_line.path
                    ),
                    line_number=(
                        source_line.line_number
                    ),
                    line=text.strip(),
                    matched_patterns=[
                        "future_keyword"
                    ],
                )
            )

        if (
            TARGET_PATTERN.search(
                text
            )
        ):

            signals.target_keyword_lines.append(
                SourceEvidence(
                    file=str(
                        source_line.path
                    ),
                    line_number=(
                        source_line.line_number
                    ),
                    line=text.strip(),
                    matched_patterns=[
                        "target_keyword"
                    ],
                )
            )

        if (
            EXPANDING_PATTERN.search(
                text
            )
        ):

            signals.expanding_lines.append(
                SourceEvidence(
                    file=str(
                        source_line.path
                    ),
                    line_number=(
                        source_line.line_number
                    ),
                    line=text.strip(),
                    matched_patterns=[
                        "expanding_operation"
                    ],
                )
            )

    return signals


# ============================================================================
# FEATURE AUDIT
# ============================================================================


def audit_feature(
    feature: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    source_index: list[SourceLine],
) -> FeatureAudit:

    classification = (
        classify_feature_name(
            feature
        )
    )

    metadata = (
        feature
        in METADATA_COLUMNS
    )

    audit = FeatureAudit(
        feature=feature,
        classification=classification,
        risk_level=RiskLevel.SAFE,
        metadata_column=metadata,
    )

    if feature in train.columns:

        audit.numeric_training = (
            pd.api.types.is_numeric_dtype(
                train[feature]
            )
        )

        audit.training_null_count = int(
            train[feature].isna().sum()
        )

    else:

        audit.reasons.append(
            "Feature is registered in the manifest "
            "but is absent from training data."
        )

        audit.risk_level = (
            RiskLevel.LEAKAGE
        )

    if feature in validation.columns:

        audit.numeric_validation = (
            pd.api.types.is_numeric_dtype(
                validation[feature]
            )
        )

        audit.validation_null_count = int(
            validation[feature].isna().sum()
        )

    else:

        audit.reasons.append(
            "Feature is registered in the manifest "
            "but is absent from validation data."
        )

        audit.risk_level = (
            RiskLevel.LEAKAGE
        )

    evidence = feature_related_evidence(
        feature,
        source_index,
    )

    audit.source_evidence = evidence

    audit.source_evidence_count = len(
        evidence
    )

    audit.source_files = sorted(
        {
            item.file
            for item in evidence
        }
    )

    for item in evidence:

        patterns = set(
            item.matched_patterns
        )

        if "negative_shift" in patterns:

            audit.negative_shift_detected = True

        if "centered_rolling" in patterns:

            audit.centered_window_detected = True

        if "future_keyword" in patterns:

            audit.forward_window_detected = True

        if "target_keyword" in patterns:

            audit.target_reference_detected = True

        if "rolling_operation" in patterns:

            audit.rolling_operation_detected = True

        if "lag_operation" in patterns:

            audit.lag_operation_detected = True

        if "expanding_operation" in patterns:

            audit.expanding_window_detected = True

    audit.current_state_indicator = (
        classification
        == FeatureClassification.CURRENT_STATE
    )

    # ------------------------------------------------------------------
    # Risk determination
    # ------------------------------------------------------------------

    if audit.negative_shift_detected:

        audit.future_reference_detected = True

        audit.risk_level = (
            RiskLevel.LEAKAGE
        )

        audit.reasons.append(
            "Feature lineage contains a negative shift, "
            "which can reference a future observation."
        )

    if audit.centered_window_detected:

        audit.future_reference_detected = True

        audit.risk_level = (
            RiskLevel.LEAKAGE
        )

        audit.reasons.append(
            "Feature lineage contains a centered rolling "
            "window that may include future observations."
        )

    if audit.target_reference_detected:

        audit.risk_level = (
            RiskLevel.LEAKAGE
        )

        audit.reasons.append(
            "Feature lineage contains target-related "
            "references."
        )

    # ------------------------------------------------------------------
    # Future-looking names are not automatically leakage.
    #
    # The source evidence is what determines whether the
    # feature actually uses future data.
    # ------------------------------------------------------------------

    if (
        audit.forward_window_detected
        and audit.risk_level
        != RiskLevel.LEAKAGE
    ):

        audit.manual_review_required = True

        audit.risk_level = (
            RiskLevel.REVIEW
        )

        audit.reasons.append(
            "Feature lineage contains future/forward-looking "
            "terminology and requires manual temporal review."
        )

    # ------------------------------------------------------------------
    # Current-state features are not automatically leakage.
    # ------------------------------------------------------------------

    if (
        audit.current_state_indicator
        and audit.risk_level
        == RiskLevel.SAFE
    ):

        audit.manual_review_required = True

        audit.risk_level = (
            RiskLevel.REVIEW
        )

        audit.reasons.append(
            "Feature represents current parking state. "
            "Its validity depends on whether current state "
            "is genuinely available at prediction time."
        )

    # ------------------------------------------------------------------
    # Features with no recognizable lineage are conservative REVIEW.
    # ------------------------------------------------------------------

    if (
        not audit.source_evidence
        and audit.risk_level
        == RiskLevel.SAFE
        and not metadata
    ):

        audit.manual_review_required = True

        audit.risk_level = (
            RiskLevel.REVIEW
        )

        audit.reasons.append(
            "No direct feature-generation source reference "
            "was found. Manual lineage review is required."
        )

    # ------------------------------------------------------------------
    # Static and calendar features are normally safe if no leakage
    # signal was detected.
    # ------------------------------------------------------------------

    if (
        audit.risk_level
        == RiskLevel.SAFE
    ):

        if classification == (
            FeatureClassification.TEMPORAL
        ):

            audit.reasons.append(
                "Calendar/temporal feature with no detected "
                "future dependency."
            )

        elif classification == (
            FeatureClassification.HISTORICAL_LAG
        ):

            audit.reasons.append(
                "Historical/lag feature with no detected "
                "future dependency."
            )

        elif classification == (
            FeatureClassification.STATIC_FACILITY
        ):

            audit.reasons.append(
                "Static facility feature with no detected "
                "future dependency."
            )

        else:

            audit.manual_review_required = True

            audit.risk_level = (
                RiskLevel.REVIEW
            )

            audit.reasons.append(
                "Feature could not be confidently classified "
                "as a safe temporal dependency."
            )

    return audit


# ============================================================================
# SOURCE AST ANALYSIS
# ============================================================================


@dataclass
class ASTTemporalFinding:

    file: str

    line_number: int

    finding_type: str

    source: str


def ast_scan_file(
    path: Path,
) -> list[ASTTemporalFinding]:

    findings: list[ASTTemporalFinding] = []

    try:

        source = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        tree = ast.parse(
            source,
            filename=str(path),
        )

    except (
        OSError,
        SyntaxError,
    ):

        return findings

    for node in ast.walk(tree):

        # --------------------------------------------------------------
        # Detect .shift(...)
        # --------------------------------------------------------------

        if isinstance(
            node,
            ast.Call,
        ):

            if (
                isinstance(
                    node.func,
                    ast.Attribute,
                )
                and node.func.attr == "shift"
            ):

                for argument in node.args:

                    if isinstance(
                        argument,
                        ast.UnaryOp,
                    ) and isinstance(
                        argument.op,
                        ast.USub,
                    ):

                        findings.append(
                            ASTTemporalFinding(
                                file=str(path),
                                line_number=(
                                    node.lineno
                                ),
                                finding_type=(
                                    "negative_shift"
                                ),
                                source=(
                                    ast.get_source_segment(
                                        source,
                                        node,
                                    )
                                    or ""
                                ).strip(),
                            )
                        )

        # --------------------------------------------------------------
        # Detect rolling(center=True)
        # --------------------------------------------------------------

        if isinstance(
            node,
            ast.Call,
        ):

            if (
                isinstance(
                    node.func,
                    ast.Attribute,
                )
                and node.func.attr == "rolling"
            ):

                for keyword in node.keywords:

                    if (
                        keyword.arg
                        == "center"
                    ):

                        if (
                            isinstance(
                                keyword.value,
                                ast.Constant,
                            )
                            and keyword.value.value
                            is True
                        ):

                            findings.append(
                                ASTTemporalFinding(
                                    file=str(path),
                                    line_number=(
                                        node.lineno
                                    ),
                                    finding_type=(
                                        "centered_rolling"
                                    ),
                                    source=(
                                        ast.get_source_segment(
                                            source,
                                            node,
                                        )
                                        or ""
                                    ).strip(),
                                )
                            )

        # --------------------------------------------------------------
        # Detect expanding()
        # --------------------------------------------------------------

        if isinstance(
            node,
            ast.Call,
        ):

            if (
                isinstance(
                    node.func,
                    ast.Attribute,
                )
                and node.func.attr
                == "expanding"
            ):

                findings.append(
                    ASTTemporalFinding(
                        file=str(path),
                        line_number=(
                            node.lineno
                        ),
                        finding_type=(
                            "expanding_window"
                        ),
                        source=(
                            ast.get_source_segment(
                                source,
                                node,
                            )
                            or ""
                        ).strip(),
                    )
                )

    return findings


def run_ast_source_scan(
    source_files: list[Path],
) -> list[ASTTemporalFinding]:

    findings: list[ASTTemporalFinding] = []

    for path in source_files:

        findings.extend(
            ast_scan_file(
                path
            )
        )

    return findings


# ============================================================================
# DATASET FEATURE TYPE AUDIT
# ============================================================================


def audit_dataset_feature_types(
    features: list[str],
    train: pd.DataFrame,
    validation: pd.DataFrame,
    state: AuditState,
) -> None:

    print_section(
        "PERSISTED FEATURE TYPE VALIDATION"
    )

    missing_train = [
        feature
        for feature in features
        if feature not in train.columns
    ]

    missing_validation = [
        feature
        for feature in features
        if feature not in validation.columns
    ]

    print(
        f"Registered features                  : "
        f"{len(features)}"
    )

    print(
        f"Missing from training                : "
        f"{len(missing_train)}"
    )

    print(
        f"Missing from validation              : "
        f"{len(missing_validation)}"
    )

    register_check(
        state,
        not missing_train,
    )

    print_check(
        "All registered features in training",
        not missing_train,
    )

    register_check(
        state,
        not missing_validation,
    )

    print_check(
        "All registered features in validation",
        not missing_validation,
    )


# ============================================================================
# FEATURE AUDIT SUMMARY
# ============================================================================


def summarize_feature_audits(
    audits: list[FeatureAudit],
    state: AuditState,
) -> None:

    print_section(
        "FEATURE CLASSIFICATION SUMMARY"
    )

    classifications: dict[str, int] = {}

    for audit in audits:

        classifications[
            audit.classification
        ] = (
            classifications.get(
                audit.classification,
                0,
            )
            + 1
        )

    for classification in [
        FeatureClassification.TEMPORAL,
        FeatureClassification.HISTORICAL_LAG,
        FeatureClassification.ROLLING_HISTORICAL,
        FeatureClassification.STATIC_FACILITY,
        FeatureClassification.CURRENT_STATE,
        FeatureClassification.TARGET_DERIVED,
        FeatureClassification.FUTURE_DERIVED,
        FeatureClassification.AMBIGUOUS,
        FeatureClassification.OTHER,
    ]:

        print(
            f"{classification:<38}: "
            f"{classifications.get(classification, 0)}"
        )

    state.features_audited = len(
        audits
    )

    state.safe_features = sum(
        audit.risk_level
        == RiskLevel.SAFE
        for audit in audits
    )

    state.review_features = sum(
        audit.risk_level
        == RiskLevel.REVIEW
        for audit in audits
    )

    state.leakage_features = sum(
        audit.risk_level
        == RiskLevel.LEAKAGE
        for audit in audits
    )


# ============================================================================
# LEAKAGE SIGNAL SUMMARY
# ============================================================================


def print_leakage_signal_summary(
    audits: list[FeatureAudit],
    ast_findings: list[ASTTemporalFinding],
) -> None:

    print_section(
        "TEMPORAL LEAKAGE SIGNAL SUMMARY"
    )

    negative_shift_features = [
        audit.feature
        for audit in audits
        if audit.negative_shift_detected
    ]

    target_features = [
        audit.feature
        for audit in audits
        if audit.target_reference_detected
    ]

    future_features = [
        audit.feature
        for audit in audits
        if audit.future_reference_detected
    ]

    centered_features = [
        audit.feature
        for audit in audits
        if audit.centered_window_detected
    ]

    current_state_features = [
        audit.feature
        for audit in audits
        if audit.current_state_indicator
    ]

    print(
        f"Features with negative-shift evidence  : "
        f"{len(negative_shift_features)}"
    )

    print(
        f"Features with target-reference evidence : "
        f"{len(target_features)}"
    )

    print(
        f"Features with future-reference evidence  : "
        f"{len(future_features)}"
    )

    print(
        f"Features with centered-window evidence   : "
        f"{len(centered_features)}"
    )

    print(
        f"Current-state features                  : "
        f"{len(current_state_features)}"
    )

    print(
        f"AST negative-shift findings             : "
        f"{sum(
            item.finding_type == 'negative_shift'
            for item in ast_findings
        )}"
    )

    print(
        f"AST centered-window findings            : "
        f"{sum(
            item.finding_type == 'centered_rolling'
            for item in ast_findings
        )}"
    )


# ============================================================================
# CURRENT-STATE REVIEW
# ============================================================================


def print_current_state_features(
    audits: list[FeatureAudit],
) -> None:

    current_state = [
        audit
        for audit in audits
        if audit.current_state_indicator
    ]

    print_section(
        "CURRENT-STATE FEATURE REVIEW"
    )

    if not current_state:

        print(
            "No current-state features identified."
        )

        return

    for audit in current_state:

        print(
            f"  - {audit.feature}"
        )


# ============================================================================
# SUSPICIOUS FEATURES
# ============================================================================


def print_review_features(
    audits: list[FeatureAudit],
) -> None:

    review = [
        audit
        for audit in audits
        if audit.risk_level
        == RiskLevel.REVIEW
    ]

    leakage = [
        audit
        for audit in audits
        if audit.risk_level
        == RiskLevel.LEAKAGE
    ]

    print_section(
        "FEATURES REQUIRING MANUAL REVIEW"
    )

    if not review:

        print(
            "None."
        )

    else:

        for audit in review:

            print(
                f"  - {audit.feature}"
            )

            for reason in audit.reasons:

                print(
                    f"      Reason: {reason}"
                )

    print_section(
        "FEATURES WITH POTENTIAL LEAKAGE"
    )

    if not leakage:

        print(
            "NONE DETECTED"
        )

    else:

        for audit in leakage:

            print(
                f"  - {audit.feature}"
            )

            for reason in audit.reasons:

                print(
                    f"      Reason: {reason}"
                )


# ============================================================================
# SOURCE EVIDENCE REPORT
# ============================================================================


def print_source_evidence(
    audits: list[FeatureAudit],
    maximum_features: int = 30,
) -> None:

    interesting = [
        audit
        for audit in audits
        if audit.negative_shift_detected
        or audit.target_reference_detected
        or audit.centered_window_detected
        or audit.forward_window_detected
    ]

    print_section(
        "INTERESTING SOURCE LINEAGE EVIDENCE"
    )

    if not interesting:

        print(
            "No feature-specific suspicious lineage "
            "evidence detected."
        )

        return

    for audit in interesting[
        :maximum_features
    ]:

        print()
        print(
            f"FEATURE: {audit.feature}"
        )

        for evidence in audit.source_evidence:

            if not evidence.matched_patterns:
                continue

            print(
                f"  {evidence.file}:"
                f"{evidence.line_number}"
            )

            print(
                f"      {evidence.line}"
            )

            print(
                "      Signals: "
                + ", ".join(
                    evidence.matched_patterns
                )
            )


# ============================================================================
# JSON SERIALIZATION
# ============================================================================


def evidence_to_dict(
    evidence: SourceEvidence,
) -> dict[str, Any]:

    return asdict(
        evidence
    )


def audit_to_dict(
    audit: FeatureAudit,
) -> dict[str, Any]:

    result = asdict(
        audit
    )

    result["source_evidence"] = [
        evidence_to_dict(
            evidence
        )
        for evidence in audit.source_evidence
    ]

    return result


def ast_finding_to_dict(
    finding: ASTTemporalFinding,
) -> dict[str, Any]:

    return asdict(
        finding
    )


# ============================================================================
# PERSIST RESULTS
# ============================================================================


def persist_results(
    *,
    manifest: dict[str, Any],
    audits: list[FeatureAudit],
    ast_findings: list[ASTTemporalFinding],
    state: AuditState,
    source_files: list[Path],
) -> None:

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    safe_features = [
        audit.feature
        for audit in audits
        if audit.risk_level
        == RiskLevel.SAFE
    ]

    review_features = [
        audit.feature
        for audit in audits
        if audit.risk_level
        == RiskLevel.REVIEW
    ]

    leakage_features = [
        audit.feature
        for audit in audits
        if audit.risk_level
        == RiskLevel.LEAKAGE
    ]

    result = {
        "audit_name": (
            "birmingham_xgboost_temporal_leakage_audit"
        ),
        "audit_version": "1.0",
        "created_at_utc": (
            datetime.utcnow().isoformat()
            + "Z"
        ),
        "target_column": TARGET_COLUMN,
        "expected_feature_count": (
            EXPECTED_FEATURE_COUNT
        ),
        "manifest": {
            "schema_version": (
                manifest.get(
                    "schema_version"
                )
            ),
            "dataset_name": (
                manifest.get(
                    "dataset_name"
                )
            ),
            "source_name": (
                manifest.get(
                    "source_name"
                )
            ),
            "feature_count": len(
                manifest.get(
                    "feature_columns",
                    [],
                )
            ),
        },
        "dataset": {
            "training_rows": (
                state.training_rows
            ),
            "validation_rows": (
                state.validation_rows
            ),
            "test_loaded": False,
        },
        "source_scan": {
            "directories": [
                str(path)
                for path in FEATURE_SOURCE_DIRECTORIES
            ],
            "files_scanned": [
                str(path)
                for path in source_files
            ],
            "file_count": len(
                source_files
            ),
        },
        "summary": {
            "features_audited": len(
                audits
            ),
            "safe_features": len(
                safe_features
            ),
            "review_features": len(
                review_features
            ),
            "potential_leakage_features": len(
                leakage_features
            ),
            "negative_shift_features": [
                audit.feature
                for audit in audits
                if audit.negative_shift_detected
            ],
            "target_reference_features": [
                audit.feature
                for audit in audits
                if audit.target_reference_detected
            ],
            "centered_window_features": [
                audit.feature
                for audit in audits
                if audit.centered_window_detected
            ],
            "current_state_features": [
                audit.feature
                for audit in audits
                if audit.current_state_indicator
            ],
        },
        "ast_temporal_findings": [
            ast_finding_to_dict(
                finding
            )
            for finding in ast_findings
        ],
        "features": [
            audit_to_dict(
                audit
            )
            for audit in audits
        ],
        "checks": {
            "executed": (
                state.checks_executed
            ),
            "passed": (
                state.checks_passed
            ),
            "failed": (
                state.checks_failed
            ),
        },
    }

    with JSON_OUTPUT.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            result,
            handle,
            indent=2,
            default=str,
        )

    # ------------------------------------------------------------------
    # CSV
    # ------------------------------------------------------------------

    rows: list[dict[str, Any]] = []

    for audit in audits:

        rows.append(
            {
                "feature": audit.feature,
                "classification": (
                    audit.classification
                ),
                "risk_level": (
                    audit.risk_level
                ),
                "metadata_column": (
                    audit.metadata_column
                ),
                "numeric_training": (
                    audit.numeric_training
                ),
                "numeric_validation": (
                    audit.numeric_validation
                ),
                "training_null_count": (
                    audit.training_null_count
                ),
                "validation_null_count": (
                    audit.validation_null_count
                ),
                "future_reference_detected": (
                    audit.future_reference_detected
                ),
                "target_reference_detected": (
                    audit.target_reference_detected
                ),
                "negative_shift_detected": (
                    audit.negative_shift_detected
                ),
                "forward_window_detected": (
                    audit.forward_window_detected
                ),
                "centered_window_detected": (
                    audit.centered_window_detected
                ),
                "expanding_window_detected": (
                    audit.expanding_window_detected
                ),
                "rolling_operation_detected": (
                    audit.rolling_operation_detected
                ),
                "lag_operation_detected": (
                    audit.lag_operation_detected
                ),
                "current_state_indicator": (
                    audit.current_state_indicator
                ),
                "source_evidence_count": (
                    audit.source_evidence_count
                ),
                "source_files": (
                    ";".join(
                        audit.source_files
                    )
                ),
                "manual_review_required": (
                    audit.manual_review_required
                ),
                "reasons": (
                    " | ".join(
                        audit.reasons
                    )
                ),
            }
        )

    dataframe = pd.DataFrame(
        rows
    )

    dataframe.to_csv(
        CSV_OUTPUT,
        index=False,
    )

    print_section(
        "PERSISTING AUDIT RESULTS"
    )

    print(
        f"Output directory                      : "
        f"{OUTPUT_ROOT}"
    )

    print(
        f"JSON report                            : "
        f"{JSON_OUTPUT}"
    )

    print(
        f"CSV feature audit                      : "
        f"{CSV_OUTPUT}"
    )


# ============================================================================
# FINAL VERDICT
# ============================================================================


def calculate_final_verdict(
    audits: list[FeatureAudit],
    ast_findings: list[ASTTemporalFinding],
) -> tuple[str, list[str]]:

    failures: list[str] = []

    leakage_features = [
        audit
        for audit in audits
        if audit.risk_level
        == RiskLevel.LEAKAGE
    ]

    if leakage_features:

        failures.append(
            "Potential feature leakage detected in "
            f"{len(leakage_features)} registered feature(s)."
        )

    # --------------------------------------------------------------
    # AST findings are contextual.
    #
    # A negative shift can legitimately be used for target creation.
    # Therefore the presence of a negative shift in source code is NOT
    # by itself sufficient to declare model feature leakage.
    # --------------------------------------------------------------

    for finding in ast_findings:

        if finding.finding_type == (
            "centered_rolling"
        ):

            failures.append(
                "Centered rolling window detected in "
                f"{finding.file}:{finding.line_number}."
            )

    if failures:

        return (
            "FAIL",
            failures,
        )

    review_features = [
        audit
        for audit in audits
        if audit.risk_level
        == RiskLevel.REVIEW
    ]

    if review_features:

        return (
            "REVIEW_REQUIRED",
            [
                "No confirmed feature leakage was detected, "
                "but "
                f"{len(review_features)} feature(s) require "
                "manual temporal-availability review."
            ],
        )

    return (
        "PASS",
        [],
    )


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:

    state = AuditState()

    print_header(
        "SMARTPARK AI - BIRMINGHAM XGBOOST "
        "FEATURE LEAKAGE / TEMPORAL AVAILABILITY AUDIT"
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
        "  Read persisted feature registry"
    )
    print(
        "  Inspect actual ML feature-generation source code"
    )
    print(
        "  Detect future/forward-looking references"
    )
    print(
        "  Detect target-derived feature references"
    )
    print(
        "  Detect negative shifts"
    )
    print(
        "  Detect centered rolling windows"
    )
    print(
        "  Assess current-state feature risk"
    )
    print(
        "  Do NOT modify persisted datasets"
    )
    print(
        "  Do NOT train XGBoost"
    )
    print(
        "  Do NOT load test.parquet"
    )

    try:

        # ==============================================================
        # 1. PATH VALIDATION
        # ==============================================================

        print_section(
            "PATH VALIDATION"
        )

        print(
            f"Processed dataset root                 : "
            f"{PROCESSED_BIRMINGHAM_ROOT}"
        )

        print(
            f"Manifest                              : "
            f"{MANIFEST_PATH}"
        )

        print(
            f"Training dataset                      : "
            f"{TRAIN_PATH}"
        )

        print(
            f"Validation dataset                    : "
            f"{VALIDATION_PATH}"
        )

        print(
            f"Test dataset                          : "
            f"{TEST_PATH}"
        )

        register_check(
            state,
            MANIFEST_PATH.exists(),
        )

        print_check(
            "Manifest exists",
            MANIFEST_PATH.exists(),
        )

        register_check(
            state,
            TRAIN_PATH.exists(),
        )

        print_check(
            "Training dataset exists",
            TRAIN_PATH.exists(),
        )

        register_check(
            state,
            VALIDATION_PATH.exists(),
        )

        print_check(
            "Validation dataset exists",
            VALIDATION_PATH.exists(),
        )

        # ==============================================================
        # 2. MANIFEST
        # ==============================================================

        print_section(
            "LOADING MANIFEST"
        )

        manifest = load_manifest()

        print(
            "Manifest loaded successfully."
        )

        features = validate_manifest(
            manifest,
            state,
        )

        # ==============================================================
        # 3. DATA
        # ==============================================================

        train, validation = (
            load_training_and_validation(
                state
            )
        )

        # ==============================================================
        # 4. TARGET SEPARATION
        # ==============================================================

        print_section(
            "TARGET / FEATURE SEPARATION"
        )

        for dataframe_name, dataframe in [
            ("training", train),
            ("validation", validation),
        ]:

            register_check(
                state,
                TARGET_COLUMN
                in dataframe.columns,
            )

            print_check(
                f"{dataframe_name.capitalize()} target exists",
                TARGET_COLUMN
                in dataframe.columns,
            )

        # ==============================================================
        # 5. FEATURE REGISTRY
        # ==============================================================

        print_section(
            "FEATURE REGISTRY VALIDATION"
        )

        audit_dataset_feature_types(
            features,
            train,
            validation,
            state,
        )

        # ==============================================================
        # 6. SOURCE FILES
        # ==============================================================

        print_section(
            "DISCOVERING FEATURE-GENERATION SOURCE"
        )

        source_files = discover_source_files()

        state.source_files_scanned = len(
            source_files
        )

        print(
            f"Python source files discovered       : "
            f"{len(source_files)}"
        )

        for path in source_files:

            print(
                f"  - {path}"
            )

        register_check(
            state,
            len(source_files) > 0,
        )

        print_check(
            "ML source files discovered",
            len(source_files) > 0,
        )

        source_index = (
            build_source_index(
                source_files
            )
        )

        print(
            f"Source lines indexed                  : "
            f"{len(source_index):,}"
        )

        # ==============================================================
        # 7. AST SCAN
        # ==============================================================

        print_section(
            "AST TEMPORAL SOURCE ANALYSIS"
        )

        ast_findings = (
            run_ast_source_scan(
                source_files
            )
        )

        print(
            f"AST temporal findings                 : "
            f"{len(ast_findings)}"
        )

        negative_shift_ast = [
            item
            for item in ast_findings
            if item.finding_type
            == "negative_shift"
        ]

        centered_ast = [
            item
            for item in ast_findings
            if item.finding_type
            == "centered_rolling"
        ]

        expanding_ast = [
            item
            for item in ast_findings
            if item.finding_type
            == "expanding_window"
        ]

        print(
            f"Negative shift findings               : "
            f"{len(negative_shift_ast)}"
        )

        print(
            f"Centered rolling findings             : "
            f"{len(centered_ast)}"
        )

        print(
            f"Expanding window findings             : "
            f"{len(expanding_ast)}"
        )

        # ==============================================================
        # 8. FEATURE-BY-FEATURE AUDIT
        # ==============================================================

        print_section(
            "AUDITING REGISTERED FEATURES"
        )

        audits: list[FeatureAudit] = []

        for index, feature in enumerate(
            features,
            start=1,
        ):

            audit = audit_feature(
                feature,
                train,
                validation,
                source_index,
            )

            audits.append(
                audit
            )

            print(
                f"[{index:03d}/{len(features):03d}] "
                f"{feature:<45} "
                f"{audit.risk_level:<8} "
                f"{audit.classification}"
            )

        # ==============================================================
        # 9. SUMMARY
        # ==============================================================

        summarize_feature_audits(
            audits,
            state,
        )

        print_leakage_signal_summary(
            audits,
            ast_findings,
        )

        print_current_state_features(
            audits
        )

        print_review_features(
            audits
        )

        print_source_evidence(
            audits
        )

        # ==============================================================
        # 10. PERSIST
        # ==============================================================

        persist_results(
            manifest=manifest,
            audits=audits,
            ast_findings=ast_findings,
            state=state,
            source_files=source_files,
        )

        # ==============================================================
        # 11. FINAL VERDICT
        # ==============================================================

        verdict, reasons = (
            calculate_final_verdict(
                audits,
                ast_findings,
            )
        )

        print_section(
            "FINAL AUDIT RESULT"
        )

        print(
            f"Features audited                       : "
            f"{len(audits)}"
        )

        print(
            f"Confirmed SAFE                         : "
            f"{state.safe_features}"
        )

        print(
            f"Requires REVIEW                        : "
            f"{state.review_features}"
        )

        print(
            f"Potential LEAKAGE                      : "
            f"{state.leakage_features}"
        )

        print(
            f"Checks executed                        : "
            f"{state.checks_executed}"
        )

        print(
            f"Checks passed                          : "
            f"{state.checks_passed}"
        )

        print(
            f"Checks failed                          : "
            f"{state.checks_failed}"
        )

        print()
        print(
            f"LEAKAGE AUDIT VERDICT                  : "
            f"{verdict}"
        )

        if reasons:

            print()
            print(
                "Verdict reasons:"
            )

            for reason in reasons:

                print(
                    f"  - {reason}"
                )

        # ==============================================================
        # Important interpretation
        # ==============================================================

        print()
        print(
            "IMPORTANT:"
        )

        print(
            "A negative shift used exclusively during target "
            "construction is not automatically model-feature leakage."
        )

        print(
            "The purpose of this audit is to determine whether "
            "future information enters the 296-feature model matrix."
        )

        print(
            "Current-state features are explicitly treated as "
            "REVIEW items unless their prediction-time availability "
            "can be established."
        )

        print()
        print(
            "No persisted training, validation, or test dataset "
            "was modified."
        )

        print(
            "Test dataset was NOT loaded."
        )

        print_header(
            "BIRMINGHAM FEATURE LEAKAGE / TEMPORAL "
            "AVAILABILITY AUDIT COMPLETED"
        )

        if verdict == "FAIL":

            print()
            print(
                "DO NOT proceed to hyperparameter tuning."
            )

            print(
                "Resolve the reported potential leakage first."
            )

            return 1

        if verdict == "REVIEW_REQUIRED":

            print()
            print(
                "No confirmed leakage was automatically detected."
            )

            print(
                "Manual temporal-availability review is still "
                "required before declaring the feature set clean."
            )

            return 2

        print()
        print(
            "Feature leakage audit passed."
        )

        print(
            "The registered feature set contains no "
            "automatically detected future-data leakage."
        )

        return 0

    except Exception as exc:

        print()
        print_header(
            "BIRMINGHAM FEATURE LEAKAGE / TEMPORAL "
            "AVAILABILITY AUDIT FAILED"
        )

        print()
        print(
            f"ERROR: {exc}"
        )

        print()
        print(
            "No persisted training, validation, or test "
            "dataset was modified."
        )

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )