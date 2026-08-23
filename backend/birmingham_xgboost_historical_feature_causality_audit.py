"""
SMARTPARK AI
Birmingham XGBoost Historical Feature Causality Audit

Purpose
-------
Audit historical / lag / rolling / temporal-history features for causal
availability at prediction time.

Production prediction contract:

    Prediction timestamp = T
    Forecast horizon     = T + 30 minutes

Therefore every model feature X(T) must be computable using information
available at or before T.

This audit is intentionally conservative.

It DOES:
    - Inspect the persisted feature manifest.
    - Inspect train.parquet.
    - Inspect validation.parquet.
    - Inspect ML feature-generation source code.
    - Identify historical / lag / rolling features.
    - Search source code for feature-specific generation evidence.
    - Inspect AST-level temporal operations.
    - Detect negative shifts.
    - Detect centered rolling windows.
    - Detect suspicious forward-looking constructs.
    - Detect target references.
    - Produce a feature-level causality contract.
    - Persist JSON and CSV reports.

It DOES NOT:
    - Load test.parquet.
    - Train XGBoost.
    - Tune XGBoost.
    - Rebuild the feature pipeline.
    - Modify persisted datasets.
    - Modify application source code.
    - Automatically approve a feature merely because its name looks safe.

Important distinction
---------------------
The dataset builder legitimately uses future observations to construct
forecast TARGETS, for example:

    future_occupancy = occupancy.shift(-steps)

That does NOT automatically mean leakage.

This audit therefore distinguishes:

    TARGET_GENERATION_FUTURE_LOGIC
        from
    FEATURE_GENERATION_FUTURE_LOGIC

A negative shift used exclusively to construct the target is not classified
as feature leakage.

Authoritative production rule
-----------------------------
For a feature generated at prediction timestamp T:

    max(source_information_timestamp) <= T

Anything requiring information after T is prohibited.

Possible feature verdicts
-------------------------
    CAUSALLY_SAFE_BY_STATIC_EVIDENCE
    CAUSALLY_SAFE_WITH_BOUNDARY_ASSUMPTION
    REQUIRES_CAUSAL_REVIEW
    POTENTIAL_FUTURE_LEAKAGE
    CONFIRMED_FUTURE_LEAKAGE
    NO_SOURCE_EVIDENCE

The script is intentionally conservative. In particular, historical
features will normally require source-level verification before being
approved for production.

Usage
-----
From backend:

    python birmingham_xgboost_historical_feature_causality_audit.py

Expected repository layout:

    smart-parking-system/
    |
    +-- backend/
    |   +-- birmingham_xgboost_historical_feature_causality_audit.py
    |   +-- app/
    |       +-- ml/
    |
    +-- datasets/
        +-- processed/
            +-- birmingham/
                +-- training_dataset_manifest.json
                +-- target_occupancy_rate_30m/
                    +-- train.parquet
                    +-- validation.parquet
                    +-- test.parquet
"""

from __future__ import annotations

import ast
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd


# ============================================================
# CONSTANTS
# ============================================================

SCRIPT_NAME = (
    "birmingham_xgboost_historical_feature_causality_audit"
)

TARGET_COLUMN = "target_occupancy_rate_30m"

FORECAST_HORIZON_MINUTES = 30

EXPECTED_FEATURE_COUNT = 296

REPOSITORY_ROOT = (
    Path(__file__).resolve().parent.parent
)

BACKEND_ROOT = (
    Path(__file__).resolve().parent
)

DATASET_ROOT = (
    REPOSITORY_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
)

TARGET_DATASET_ROOT = (
    DATASET_ROOT
    / TARGET_COLUMN
)

TRAIN_PATH = (
    TARGET_DATASET_ROOT
    / "train.parquet"
)

VALIDATION_PATH = (
    TARGET_DATASET_ROOT
    / "validation.parquet"
)

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
    / "xgboost_historical_feature_causality"
)

JSON_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_historical_feature_causality.json"
)

FEATURE_CSV_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_historical_feature_causality_features.csv"
)

SOURCE_CSV_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_historical_feature_causality_source_findings.csv"
)

SUMMARY_CSV_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_historical_feature_causality_summary.csv"
)

AST_CSV_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_historical_feature_causality_ast_findings.csv"
)


# ============================================================
# FEATURE CLASSIFICATION TERMS
# ============================================================

HISTORICAL_NAME_PATTERNS = [
    r"(^|_)lag($|_)",
    r"(^|_)lags($|_)",
    r"(^|_)rolling($|_)",
    r"(^|_)roll($|_)",
    r"(^|_)historical($|_)",
    r"(^|_)history($|_)",
    r"(^|_)previous($|_)",
    r"(^|_)prev($|_)",
    r"(^|_)prior($|_)",
    r"(^|_)past($|_)",
    r"(^|_)trend($|_)",
    r"(^|_)momentum($|_)",
    r"(^|_)change($|_)",
    r"(^|_)delta($|_)",
    r"(^|_)growth($|_)",
    r"(^|_)moving($|_)",
    r"(^|_)expanding($|_)",
    r"(^|_)ewm($|_)",
    r"(^|_)ema($|_)",
    r"(^|_)std($|_)",
    r"(^|_)variance($|_)",
    r"(^|_)volatility($|_)",
    r"(^|_)min($|_)",
    r"(^|_)max($|_)",
    r"(^|_)mean($|_)",
    r"(^|_)median($|_)",
    r"(^|_)quantile($|_)",
]

HISTORICAL_KEYWORDS = {
    "lag",
    "lags",
    "rolling",
    "roll",
    "historical",
    "history",
    "previous",
    "prev",
    "prior",
    "past",
    "trend",
    "momentum",
    "change",
    "delta",
    "growth",
    "moving",
    "expanding",
    "ewm",
    "ema",
    "variance",
    "volatility",
    "median",
    "quantile",
}

TEMPORAL_OPERATION_NAMES = {
    "shift",
    "rolling",
    "expanding",
    "ewm",
    "diff",
    "pct_change",
    "resample",
    "asfreq",
    "merge_asof",
}

FUTURE_KEYWORDS = {
    "future",
    "forecast",
    "target",
    "lead",
    "ahead",
    "next",
    "horizon",
    "tomorrow",
}

TARGET_KEYWORDS = {
    "target",
    "future_occupancy",
    "target_occupancy_rate",
    "TARGET_30M_COLUMN",
    "TARGET_1H_COLUMN",
    "TARGET_2H_COLUMN",
}

FEATURE_GENERATION_FILE_HINTS = {
    "feature",
    "features",
    "rolling",
    "occupancy",
    "demand",
    "temporal",
    "pipeline",
}


# ============================================================
# DATA CLASSES
# ============================================================


@dataclass
class SourceFinding:
    """One source-code finding."""

    file: str
    line_number: int
    line_text: str
    finding_type: str
    severity: str
    feature: Optional[str] = None
    context: str = ""


@dataclass
class ASTFinding:
    """One AST-level temporal finding."""

    file: str
    line_number: int
    operation: str
    direction: str
    severity: str
    expression: str
    context: str = ""
    target_related: bool = False


@dataclass
class FeatureAudit:
    """Feature-level causal audit result."""

    feature: str
    feature_index: int

    classification: str

    train_present: bool
    validation_present: bool

    dtype_train: Optional[str]
    dtype_validation: Optional[str]

    train_null_count: int
    validation_null_count: int

    source_files: list[str] = field(
        default_factory=list
    )

    source_line_count: int = 0

    historical_name_signal: bool = False
    lag_signal: bool = False
    rolling_signal: bool = False
    trend_signal: bool = False

    feature_specific_future_signal: bool = False
    feature_specific_negative_shift: bool = False
    feature_specific_centered_rolling: bool = False
    feature_specific_forward_operation: bool = False

    target_reference_signal: bool = False

    causal_direction: str = (
        "UNKNOWN"
    )

    verdict: str = (
        "NO_SOURCE_EVIDENCE"
    )

    confidence: str = (
        "LOW"
    )

    reasons: list[str] = field(
        default_factory=list
    )

    recommended_action: str = ""


# ============================================================
# EXCEPTIONS
# ============================================================


class AuditError(Exception):
    """Base audit exception."""


class AuditConfigurationError(AuditError):
    """Configuration / path error."""


class AuditDataError(AuditError):
    """Dataset integrity error."""


class AuditSourceError(AuditError):
    """Source inspection error."""


# ============================================================
# PRINTING HELPERS
# ============================================================


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
    width: int = 42,
) -> None:
    print(
        f"{label:<{width}}: {value}"
    )


def print_pass(
    label: str,
    passed: bool,
) -> None:
    print_status(
        label,
        "PASS" if passed else "FAIL",
    )


def fail(
    message: str,
) -> None:
    raise AuditError(message)


# ============================================================
# PATH VALIDATION
# ============================================================


def validate_paths() -> None:
    print_section(
        "DATASET FILE VALIDATION"
    )

    print_status(
        "Repository root",
        REPOSITORY_ROOT,
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

    print_status(
        "Feature manifest",
        MANIFEST_PATH,
    )

    print_pass(
        "Training file exists",
        TRAIN_PATH.exists(),
    )

    print_pass(
        "Validation file exists",
        VALIDATION_PATH.exists(),
    )

    print_pass(
        "Test file exists",
        TEST_PATH.exists(),
    )

    print_pass(
        "Manifest exists",
        MANIFEST_PATH.exists(),
    )

    if not TRAIN_PATH.exists():
        raise AuditConfigurationError(
            f"Training dataset does not exist: "
            f"{TRAIN_PATH}"
        )

    if not VALIDATION_PATH.exists():
        raise AuditConfigurationError(
            f"Validation dataset does not exist: "
            f"{VALIDATION_PATH}"
        )

    if not TEST_PATH.exists():
        raise AuditConfigurationError(
            f"Test dataset does not exist: "
            f"{TEST_PATH}"
        )

    if not MANIFEST_PATH.exists():
        raise AuditConfigurationError(
            f"Feature manifest does not exist: "
            f"{MANIFEST_PATH}"
        )

    print()
    print(
        "Test dataset exists but will NOT be loaded."
    )


# ============================================================
# MANIFEST LOADING
# ============================================================


def load_manifest() -> dict[str, Any]:
    print_section(
        "LOADING FEATURE MANIFEST"
    )

    try:
        with MANIFEST_PATH.open(
            "r",
            encoding="utf-8",
        ) as handle:
            manifest = json.load(handle)
    except Exception as exc:
        raise AuditDataError(
            f"Unable to load feature manifest: "
            f"{exc}"
        ) from exc

    if not isinstance(
        manifest,
        dict,
    ):
        raise AuditDataError(
            "Feature manifest is not a JSON object."
        )

    feature_columns = (
        manifest.get(
            "feature_columns",
            [],
        )
    )

    if not isinstance(
        feature_columns,
        list,
    ):
        raise AuditDataError(
            "Manifest feature_columns is not a list."
        )

    features = [
        str(feature)
        for feature in feature_columns
    ]

    print_status(
        "Manifest",
        MANIFEST_PATH,
    )

    print_status(
        "Registered features",
        len(features),
    )

    if len(features) != EXPECTED_FEATURE_COUNT:
        print(
            "WARNING: Manifest feature count differs "
            f"from expected {EXPECTED_FEATURE_COUNT}."
        )

    duplicates = [
        feature
        for feature, count
        in Counter(features).items()
        if count > 1
    ]

    if duplicates:
        raise AuditDataError(
            "Duplicate features in manifest: "
            f"{duplicates}"
        )

    return manifest


# ============================================================
# DATASET LOADING
# ============================================================


def load_persisted_datasets() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    print_section(
        "LOADING PERSISTED DATASETS"
    )

    print("Loading training dataset...")

    train = pd.read_parquet(
        TRAIN_PATH
    )

    print("Loading validation dataset...")

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

    if train.empty:
        raise AuditDataError(
            "Training dataset is empty."
        )

    if validation.empty:
        raise AuditDataError(
            "Validation dataset is empty."
        )

    return train, validation


# ============================================================
# FEATURE REGISTRY VALIDATION
# ============================================================


def validate_feature_registry(
    manifest: dict[str, Any],
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> list[str]:

    print_section(
        "FEATURE REGISTRY VALIDATION"
    )

    registered = [
        str(feature)
        for feature in manifest.get(
            "feature_columns",
            [],
        )
    ]

    # --------------------------------------------------------
    # Columns persisted in the ML dataset that are not part
    # of the registered model feature contract.
    #
    # These are intentionally excluded from the ML feature
    # registry comparison.
    # --------------------------------------------------------

    known_non_feature_columns = {
        "source_facility_code",
        "normalized_at",
        "target_30m_available",
        "target_1h_available",
        "target_2h_available",
        "target_tomorrow_morning_available",
        "target_eligible",
        "target_exclusion_reason",
    }

    # --------------------------------------------------------
    # Target columns from manifest.
    # --------------------------------------------------------

    manifest_target_columns = {
        str(column)
        for column in manifest.get(
            "target_columns",
            [],
        )
    }

    # --------------------------------------------------------
    # All columns that are explicitly not model features.
    # --------------------------------------------------------

    excluded_columns = (
        known_non_feature_columns
        | manifest_target_columns
        | {
            TARGET_COLUMN,
        }
    )

    # --------------------------------------------------------
    # Derive actual model features from persisted datasets.
    # --------------------------------------------------------

    train_features = [
        str(column)
        for column in train.columns
        if column not in excluded_columns
    ]

    validation_features = [
        str(column)
        for column in validation.columns
        if column not in excluded_columns
    ]

    # --------------------------------------------------------
    # Dataset columns that were excluded from the model
    # feature comparison.
    # --------------------------------------------------------

    train_excluded = sorted(
        {
            str(column)
            for column in train.columns
            if column in excluded_columns
        }
    )

    validation_excluded = sorted(
        {
            str(column)
            for column in validation.columns
            if column in excluded_columns
        }
    )

    # --------------------------------------------------------
    # Registry comparison.
    # --------------------------------------------------------

    train_registry_pass = (
        set(train_features)
        == set(registered)
    )

    validation_registry_pass = (
        set(validation_features)
        == set(registered)
    )

    identical = (
        train_features == validation_features
    )

    print_status(
        "Registered features",
        len(registered),
    )

    print_status(
        "Training model features",
        len(train_features),
    )

    print_status(
        "Validation model features",
        len(validation_features),
    )

    print_pass(
        "Training feature registry",
        train_registry_pass,
    )

    print_pass(
        "Validation feature registry",
        validation_registry_pass,
    )

    print_pass(
        "Train/validation feature registry",
        identical,
    )

    # --------------------------------------------------------
    # Explicitly report excluded persisted columns.
    # --------------------------------------------------------

    print()

    print(
        "Persisted non-feature / metadata columns excluded "
        "from registry comparison:"
    )

    for column in sorted(
        set(
            train_excluded
            + validation_excluded
        )
    ):
        print(
            f"  - {column}"
        )

    # --------------------------------------------------------
    # Diagnose mismatches.
    # --------------------------------------------------------

    if not train_registry_pass:

        missing = sorted(
            set(registered)
            - set(train_features)
        )

        extra = sorted(
            set(train_features)
            - set(registered)
        )

        raise AuditDataError(
            "Training feature registry mismatch. "
            f"Missing={missing}; Extra={extra}"
        )

    if not validation_registry_pass:

        missing = sorted(
            set(registered)
            - set(validation_features)
        )

        extra = sorted(
            set(validation_features)
            - set(registered)
        )

        raise AuditDataError(
            "Validation feature registry mismatch. "
            f"Missing={missing}; Extra={extra}"
        )

    if not identical:

        raise AuditDataError(
            "Training and validation model feature "
            "registries are not identical."
        )

    return registered


# ============================================================
# TARGET VALIDATION
# ============================================================


def validate_targets(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    print_section(
        "TARGET CONTRACT VALIDATION"
    )

    if TARGET_COLUMN not in train.columns:
        raise AuditDataError(
            f"Target column '{TARGET_COLUMN}' "
            "is missing from training dataset."
        )

    if TARGET_COLUMN not in validation.columns:
        raise AuditDataError(
            f"Target column '{TARGET_COLUMN}' "
            "is missing from validation dataset."
        )

    train_target = pd.to_numeric(
        train[TARGET_COLUMN],
        errors="coerce",
    )

    validation_target = pd.to_numeric(
        validation[TARGET_COLUMN],
        errors="coerce",
    )

    train_nulls = int(
        train_target.isna().sum()
    )

    validation_nulls = int(
        validation_target.isna().sum()
    )

    print_status(
        "Training target rows",
        f"{len(train_target):,}",
    )

    print_status(
        "Training target nulls",
        train_nulls,
    )

    print_status(
        "Training target mean",
        f"{train_target.mean():.6f}",
    )

    print_status(
        "Training target range",
        (
            f"{train_target.min():.6f} -> "
            f"{train_target.max():.6f}"
        ),
    )

    print_status(
        "Validation target rows",
        f"{len(validation_target):,}",
    )

    print_status(
        "Validation target nulls",
        validation_nulls,
    )

    print_status(
        "Validation target mean",
        f"{validation_target.mean():.6f}",
    )

    print_status(
        "Validation target range",
        (
            f"{validation_target.min():.6f} -> "
            f"{validation_target.max():.6f}"
        ),
    )

    if train_nulls:
        raise AuditDataError(
            "Training target contains null values."
        )

    if validation_nulls:
        raise AuditDataError(
            "Validation target contains null values."
        )

    print_status(
        "Target contract",
        "PASS",
    )


# ============================================================
# SOURCE FILE DISCOVERY
# ============================================================


def discover_source_files() -> list[Path]:
    if not SOURCE_ROOT.exists():
        raise AuditSourceError(
            f"ML source root does not exist: "
            f"{SOURCE_ROOT}"
        )

    files = sorted(
        path
        for path in SOURCE_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    )

    if not files:
        raise AuditSourceError(
            f"No Python source files found under "
            f"{SOURCE_ROOT}"
        )

    print_section(
        "SOURCE CODE DISCOVERY"
    )

    print_status(
        "ML source root",
        SOURCE_ROOT,
    )

    print_status(
        "ML source files scanned",
        len(files),
    )

    return files


# ============================================================
# SOURCE READING
# ============================================================


def read_source_file(
    path: Path,
) -> list[str]:

    try:
        return path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except Exception as exc:
        raise AuditSourceError(
            f"Unable to read source file "
            f"{path}: {exc}"
        ) from exc


# ============================================================
# FEATURE NAME CLASSIFICATION
# ============================================================


def classify_feature_name(
    feature: str,
) -> tuple[
    str,
    dict[str, bool],
]:

    lower = feature.lower()

    signals = {
        "historical_name_signal": False,
        "lag_signal": False,
        "rolling_signal": False,
        "trend_signal": False,
    }

    if any(
        re.search(
            pattern,
            lower,
        )
        for pattern in HISTORICAL_NAME_PATTERNS
    ):
        signals[
            "historical_name_signal"
        ] = True

    lag_terms = {
        "lag",
        "lags",
        "previous",
        "prev",
        "prior",
    }

    rolling_terms = {
        "rolling",
        "roll",
        "moving",
        "ewm",
        "ema",
        "expanding",
    }

    trend_terms = {
        "trend",
        "momentum",
        "change",
        "delta",
        "growth",
        "volatility",
        "variance",
        "std",
    }

    tokens = set(
        re.split(
            r"[_\W]+",
            lower,
        )
    )

    if tokens & lag_terms:
        signals["lag_signal"] = True

    if tokens & rolling_terms:
        signals["rolling_signal"] = True

    if tokens & trend_terms:
        signals["trend_signal"] = True

    if signals[
        "lag_signal"
    ] or signals[
        "rolling_signal"
    ] or signals[
        "trend_signal"
    ]:
        classification = "historical"

    elif signals[
        "historical_name_signal"
    ]:
        classification = "historical"

    else:
        classification = "non_historical"

    return classification, signals


# ============================================================
# FEATURE-SPECIFIC SOURCE SEARCH
# ============================================================


def source_feature_search(
    feature: str,
    source_files: list[Path],
) -> tuple[
    list[SourceFinding],
    list[ASTFinding],
]:

    findings: list[SourceFinding] = []
    ast_findings: list[ASTFinding] = []

    feature_pattern = re.compile(
        rf"\b{re.escape(feature)}\b"
    )

    for path in source_files:

        lines = read_source_file(path)

        matching_lines: list[int] = []

        for index, line in enumerate(
            lines,
            start=1,
        ):
            if feature_pattern.search(line):
                matching_lines.append(index)

        if not matching_lines:
            continue

        for line_number in matching_lines:

            line = lines[
                line_number - 1
            ]

            lower = line.lower()

            if any(
                keyword in lower
                for keyword in [
                    "shift(-",
                    "shift ( -",
                    "shift(-",
                    "lead(",
                    "center=true",
                    "center = true",
                    "future",
                    "ahead",
                    "next",
                ]
            ):
                findings.append(
                    SourceFinding(
                        file=str(path),
                        line_number=line_number,
                        line_text=line.strip(),
                        finding_type=(
                            "FEATURE_SPECIFIC_FUTURE_SIGNAL"
                        ),
                        severity="HIGH",
                        feature=feature,
                        context=(
                            "Feature-specific source "
                            "line contains a future-oriented "
                            "construct."
                        ),
                    )
                )

            elif any(
                operation in lower
                for operation in [
                    ".shift(",
                    ".rolling(",
                    ".expanding(",
                    ".ewm(",
                    ".diff(",
                    ".pct_change(",
                ]
            ):
                findings.append(
                    SourceFinding(
                        file=str(path),
                        line_number=line_number,
                        line_text=line.strip(),
                        finding_type=(
                            "FEATURE_SPECIFIC_TEMPORAL_OPERATION"
                        ),
                        severity="MEDIUM",
                        feature=feature,
                        context=(
                            "Feature-specific source "
                            "line contains a temporal "
                            "operation."
                        ),
                    )
                )

            else:
                findings.append(
                    SourceFinding(
                        file=str(path),
                        line_number=line_number,
                        line_text=line.strip(),
                        finding_type=(
                            "FEATURE_SOURCE_REFERENCE"
                        ),
                        severity="INFO",
                        feature=feature,
                        context=(
                            "Feature name occurs in "
                            "ML source code."
                        ),
                    )
                )

        try:
            tree = ast.parse(
                "\n".join(lines),
                filename=str(path),
            )
        except SyntaxError:
            continue

        ast_findings.extend(
            extract_ast_findings(
                tree=tree,
                path=path,
                feature=feature,
                lines=lines,
                matching_lines=matching_lines,
            )
        )

    return findings, ast_findings


# ============================================================
# AST TEMPORAL ANALYSIS
# ============================================================


def expression_text(
    node: ast.AST,
    lines: list[str],
) -> str:

    try:
        text = ast.get_source_segment(
            "\n".join(lines),
            node,
        )

        if text:
            return text.strip()
    except Exception:
        pass

    return ""


def get_numeric_constant(
    node: ast.AST,
) -> Optional[float]:

    if isinstance(
        node,
        ast.Constant,
    ) and isinstance(
        node.value,
        (int, float),
    ):
        return float(
            node.value
        )

    if isinstance(
        node,
        ast.UnaryOp,
    ) and isinstance(
        node.op,
        (
            ast.USub,
            ast.UAdd,
        ),
    ):
        if isinstance(
            node.operand,
            ast.Constant,
        ) and isinstance(
            node.operand.value,
            (int, float),
        ):
            value = float(
                node.operand.value
            )

            if isinstance(
                node.op,
                ast.USub,
            ):
                return -value

            return value

    return None


def call_name(
    node: ast.Call,
) -> str:

    function = node.func

    if isinstance(
        function,
        ast.Attribute,
    ):
        return function.attr

    if isinstance(
        function,
        ast.Name,
    ):
        return function.id

    return ""


def extract_ast_findings(
    tree: ast.AST,
    path: Path,
    feature: Optional[str],
    lines: list[str],
    matching_lines: list[int],
) -> list[ASTFinding]:

    results: list[ASTFinding] = []

    matching_set = set(
        matching_lines
    )

    for node in ast.walk(tree):

        if not isinstance(
            node,
            ast.Call,
        ):
            continue

        operation = call_name(
            node
        )

        if operation not in TEMPORAL_OPERATION_NAMES:
            continue

        line_number = (
            getattr(
                node,
                "lineno",
                0,
            )
        )

        expression = expression_text(
            node,
            lines,
        )

        target_related = any(
            keyword.lower()
            in expression.lower()
            for keyword in TARGET_KEYWORDS
        )

        relevant_to_feature = (
            feature is None
            or line_number in matching_set
            or (
                feature.lower()
                in expression.lower()
            )
        )

        if not relevant_to_feature:
            continue

        direction = "UNKNOWN"
        severity = "INFO"

        # ----------------------------------------------------
        # shift()
        # ----------------------------------------------------

        if operation == "shift":

            shift_value: Optional[
                float
            ] = None

            if node.args:
                shift_value = (
                    get_numeric_constant(
                        node.args[0]
                    )
                )

            if shift_value is None:

                for keyword in node.keywords:
                    if keyword.arg == "periods":
                        shift_value = (
                            get_numeric_constant(
                                keyword.value
                            )
                        )

            if shift_value is not None:

                if shift_value < 0:
                    direction = (
                        "FUTURE"
                    )

                    severity = (
                        "HIGH"
                    )

                elif shift_value > 0:
                    direction = (
                        "HISTORICAL"
                    )

                    severity = (
                        "LOW"
                    )

                else:
                    direction = (
                        "CURRENT"
                    )

            else:
                direction = (
                    "DYNAMIC"
                )

                severity = (
                    "MEDIUM"
                )

        # ----------------------------------------------------
        # rolling()
        # ----------------------------------------------------

        elif operation == "rolling":

            center_value: Optional[
                bool
            ] = None

            for keyword in node.keywords:

                if keyword.arg == "center":

                    if isinstance(
                        keyword.value,
                        ast.Constant,
                    ) and isinstance(
                        keyword.value.value,
                        bool,
                    ):
                        center_value = (
                            keyword.value.value
                        )

            if center_value is True:

                direction = (
                    "CENTERED"
                )

                severity = (
                    "HIGH"
                )

            else:

                direction = (
                    "TRAILING_OR_DEFAULT"
                )

                severity = (
                    "LOW"
                )

        # ----------------------------------------------------
        # expanding / EWM
        # ----------------------------------------------------

        elif operation in {
            "expanding",
            "ewm",
        }:

            direction = (
                "HISTORICAL_OR_CURRENT"
            )

            severity = (
                "LOW"
            )

        # ----------------------------------------------------
        # diff / pct_change
        # ----------------------------------------------------

        elif operation in {
            "diff",
            "pct_change",
        }:

            direction = (
                "HISTORICAL_OR_CURRENT"
            )

            severity = (
                "LOW"
            )

        # ----------------------------------------------------
        # resampling
        # ----------------------------------------------------

        elif operation in {
            "resample",
            "asfreq",
            "merge_asof",
        }:

            direction = (
                "TIME_ALIGNMENT"
            )

            severity = (
                "MEDIUM"
            )

        results.append(
            ASTFinding(
                file=str(path),
                line_number=line_number,
                operation=operation,
                direction=direction,
                severity=severity,
                expression=expression,
                context=(
                    "Target-related source"
                    if target_related
                    else "Feature-generation source"
                ),
                target_related=target_related,
            )
        )

    return results


# ============================================================
# GLOBAL SOURCE TEMPORAL ANALYSIS
# ============================================================


def scan_global_ast_findings(
    source_files: list[Path],
) -> list[ASTFinding]:

    results: list[ASTFinding] = []

    for path in source_files:

        lines = read_source_file(
            path
        )

        try:
            tree = ast.parse(
                "\n".join(lines),
                filename=str(path),
            )
        except SyntaxError:
            continue

        results.extend(
            extract_ast_findings(
                tree=tree,
                path=path,
                feature=None,
                lines=lines,
                matching_lines=[],
            )
        )

    return results


# ============================================================
# GLOBAL SOURCE TEXT FINDINGS
# ============================================================


def scan_global_source_findings(
    source_files: list[Path],
) -> list[SourceFinding]:

    findings: list[
        SourceFinding
    ] = []

    future_patterns = [
        (
            r"\.shift\s*\(\s*-\s*",
            "NEGATIVE_SHIFT",
            "HIGH",
        ),
        (
            r"\bshift\s*\(\s*-\s*",
            "NEGATIVE_SHIFT",
            "HIGH",
        ),
        (
            r"\bcenter\s*=\s*True\b",
            "CENTERED_ROLLING",
            "HIGH",
        ),
        (
            r"\bmerge_asof\s*\(",
            "MERGE_ASOF",
            "MEDIUM",
        ),
        (
            r"\blead\s*\(",
            "LEAD_OPERATION",
            "HIGH",
        ),
        (
            r"\bfuture_[A-Za-z0-9_]+",
            "FUTURE_NAMED_VARIABLE",
            "MEDIUM",
        ),
    ]

    compiled = [
        (
            re.compile(
                pattern,
                re.IGNORECASE,
            ),
            finding_type,
            severity,
        )
        for pattern,
        finding_type,
        severity in future_patterns
    ]

    for path in source_files:

        lines = read_source_file(
            path
        )

        for line_number, line in enumerate(
            lines,
            start=1,
        ):

            for (
                regex,
                finding_type,
                severity,
            ) in compiled:

                if regex.search(line):

                    lower = line.lower()

                    target_related = (
                        any(
                            keyword.lower()
                            in lower
                            for keyword
                            in TARGET_KEYWORDS
                        )
                        or "target" in lower
                    )

                    findings.append(
                        SourceFinding(
                            file=str(path),
                            line_number=line_number,
                            line_text=line.strip(),
                            finding_type=finding_type,
                            severity=severity,
                            feature=None,
                            context=(
                                "Likely target-generation "
                                "context"
                                if target_related
                                else
                                "Requires causal review"
                            ),
                        )
                    )

    return findings


# ============================================================
# SOURCE CONTEXT CLASSIFICATION
# ============================================================


def is_target_generation_context(
    source_finding: SourceFinding,
    lines: list[str],
) -> bool:

    start = max(
        0,
        source_finding.line_number - 10,
    )

    end = min(
        len(lines),
        source_finding.line_number + 10,
    )

    context = "\n".join(
        lines[start:end]
    ).lower()

    target_terms = [
        "target_column",
        "target_30m",
        "target_1h",
        "target_2h",
        "future_occupancy",
        "target_valid",
        "availability_column",
        "target_occupancy_rate",
        "target_tomorrow",
    ]

    return any(
        term in context
        for term in target_terms
    )


# ============================================================
# FEATURE AUDIT BUILDING
# ============================================================


def build_feature_audits(
    registered_features: list[str],
    train: pd.DataFrame,
    validation: pd.DataFrame,
    source_files: list[Path],
    global_ast_findings: list[ASTFinding],
) -> tuple[
    list[FeatureAudit],
    list[SourceFinding],
    list[ASTFinding],
]:

    feature_audits: list[
        FeatureAudit
    ] = []

    all_source_findings: list[
        SourceFinding
    ] = []

    all_feature_ast_findings: list[
        ASTFinding
    ] = []

    for index, feature in enumerate(
        registered_features,
        start=1,
    ):

        classification, signals = (
            classify_feature_name(
                feature
            )
        )

        if classification != "historical":
            continue

        feature_source_findings, (
            feature_ast_findings
        ) = source_feature_search(
            feature=feature,
            source_files=source_files,
        )

        all_source_findings.extend(
            feature_source_findings
        )

        all_feature_ast_findings.extend(
            feature_ast_findings
        )

        train_series = train.get(
            feature
        )

        validation_series = (
            validation.get(feature)
        )

        train_present = (
            train_series is not None
        )

        validation_present = (
            validation_series is not None
        )

        dtype_train = (
            str(train_series.dtype)
            if train_present
            else None
        )

        dtype_validation = (
            str(validation_series.dtype)
            if validation_present
            else None
        )

        train_null_count = (
            int(train_series.isna().sum())
            if train_present
            else 0
        )

        validation_null_count = (
            int(
                validation_series.isna().sum()
            )
            if validation_present
            else 0
        )

        feature_future_findings = [
            finding
            for finding in feature_source_findings
            if finding.finding_type
            == "FEATURE_SPECIFIC_FUTURE_SIGNAL"
        ]

        feature_negative_shift = any(
            "shift(-"
            in finding.line_text.replace(
                " ",
                "",
            )
            for finding
            in feature_future_findings
        )

        feature_centered = any(
            "center=true"
            in finding.line_text.replace(
                " ",
                "",
            ).lower()
            for finding
            in feature_future_findings
        )

        feature_forward_operation = any(
            any(
                term in finding.line_text.lower()
                for term in [
                    "lead(",
                    "future",
                    "ahead",
                    "next",
                ]
            )
            for finding
            in feature_future_findings
        )

        target_reference = any(
            any(
                keyword.lower()
                in finding.line_text.lower()
                for keyword in TARGET_KEYWORDS
            )
            for finding
            in feature_source_findings
        )

        source_files_for_feature = sorted(
            {
                finding.file
                for finding
                in feature_source_findings
            }
        )

        reasons: list[str] = []

        if not source_files_for_feature:
            reasons.append(
                "No direct source-code reference to "
                "the registered feature name was found."
            )

        if feature_negative_shift:
            reasons.append(
                "Feature-specific source evidence "
                "contains a negative shift."
            )

        if feature_centered:
            reasons.append(
                "Feature-specific source evidence "
                "contains centered rolling logic."
            )

        if feature_forward_operation:
            reasons.append(
                "Feature-specific source evidence "
                "contains a forward-looking construct."
            )

        if target_reference:
            reasons.append(
                "Feature-specific source evidence "
                "contains target-related terminology."
            )

        if (
            signals["lag_signal"]
            and source_files_for_feature
        ):
            reasons.append(
                "Feature name indicates lag/history "
                "and source evidence exists."
            )

        if (
            signals["rolling_signal"]
            and source_files_for_feature
        ):
            reasons.append(
                "Feature name indicates rolling/window "
                "calculation and source evidence exists."
            )

        if (
            signals["trend_signal"]
            and source_files_for_feature
        ):
            reasons.append(
                "Feature name indicates historical "
                "change/trend calculation."
            )

        # ----------------------------------------------------
        # Determine causal direction.
        # ----------------------------------------------------

        causal_direction = (
            "UNKNOWN"
        )

        relevant_ast = [
            finding
            for finding
            in feature_ast_findings
        ]

        if any(
            finding.direction == "FUTURE"
            for finding
            in relevant_ast
        ):
            causal_direction = (
                "FUTURE"
            )

        elif any(
            finding.direction == "CENTERED"
            for finding
            in relevant_ast
        ):
            causal_direction = (
                "CENTERED"
            )

        elif any(
            finding.direction
            in {
                "HISTORICAL",
                "HISTORICAL_OR_CURRENT",
                "TRAILING_OR_DEFAULT",
            }
            for finding
            in relevant_ast
        ):
            causal_direction = (
                "HISTORICAL_OR_CURRENT"
            )

        elif feature_source_findings:
            causal_direction = (
                "SOURCE_REFERENCE_ONLY"
            )

        # ----------------------------------------------------
        # Conservative verdict.
        # ----------------------------------------------------

        if feature_negative_shift:

            verdict = (
                "POTENTIAL_FUTURE_LEAKAGE"
            )

            confidence = "HIGH"

            reasons.append(
                "Negative temporal shift appears "
                "feature-specific and requires immediate "
                "causal verification."
            )

            recommended_action = (
                "Trace the exact feature-generation "
                "expression and prove that the negative "
                "shift is not part of feature construction."
            )

        elif feature_centered:

            verdict = (
                "POTENTIAL_FUTURE_LEAKAGE"
            )

            confidence = "HIGH"

            recommended_action = (
                "Verify that the centered window does not "
                "include observations after prediction time T."
            )

        elif feature_forward_operation:

            verdict = (
                "REQUIRES_CAUSAL_REVIEW"
            )

            confidence = "MEDIUM"

            recommended_action = (
                "Trace the forward-looking construct "
                "to determine whether it belongs to target "
                "construction or feature construction."
            )

        elif not source_files_for_feature:

            verdict = (
                "NO_SOURCE_EVIDENCE"
            )

            confidence = "LOW"

            recommended_action = (
                "Locate the feature-generation implementation "
                "and document its temporal source boundary."
            )

        elif causal_direction in {
            "HISTORICAL",
            "HISTORICAL_OR_CURRENT",
        }:

            verdict = (
                "CAUSALLY_SAFE_WITH_BOUNDARY_ASSUMPTION"
            )

            confidence = "MEDIUM"

            reasons.append(
                "Static source evidence indicates "
                "historical/current temporal direction, "
                "but source-level timestamp causality has "
                "not been formally proven."
            )

            recommended_action = (
                "Verify source timestamps and prove "
                "max(source_timestamp) <= prediction_timestamp."
            )

        else:

            verdict = (
                "REQUIRES_CAUSAL_REVIEW"
            )

            confidence = "LOW"

            recommended_action = (
                "Trace the feature calculation to its "
                "source observations and establish its "
                "temporal cutoff."
            )

        feature_audits.append(
            FeatureAudit(
                feature=feature,
                feature_index=index,
                classification=classification,
                train_present=train_present,
                validation_present=validation_present,
                dtype_train=dtype_train,
                dtype_validation=dtype_validation,
                train_null_count=train_null_count,
                validation_null_count=(
                    validation_null_count
                ),
                source_files=source_files_for_feature,
                source_line_count=len(
                    feature_source_findings
                ),
                historical_name_signal=(
                    signals[
                        "historical_name_signal"
                    ]
                ),
                lag_signal=(
                    signals["lag_signal"]
                ),
                rolling_signal=(
                    signals["rolling_signal"]
                ),
                trend_signal=(
                    signals["trend_signal"]
                ),
                feature_specific_future_signal=(
                    bool(feature_future_findings)
                ),
                feature_specific_negative_shift=(
                    feature_negative_shift
                ),
                feature_specific_centered_rolling=(
                    feature_centered
                ),
                feature_specific_forward_operation=(
                    feature_forward_operation
                ),
                target_reference_signal=(
                    target_reference
                ),
                causal_direction=(
                    causal_direction
                ),
                verdict=verdict,
                confidence=confidence,
                reasons=reasons,
                recommended_action=(
                    recommended_action
                ),
            )
        )

    return (
        feature_audits,
        all_source_findings,
        all_feature_ast_findings,
    )


# ============================================================
# GLOBAL FUTURE FINDING CLASSIFICATION
# ============================================================


def classify_global_future_findings(
    global_source_findings: list[SourceFinding],
) -> dict[str, int]:

    counts = Counter()

    for finding in global_source_findings:

        if finding.finding_type in {
            "NEGATIVE_SHIFT",
            "LEAD_OPERATION",
            "CENTERED_ROLLING",
        }:

            counts[
                finding.finding_type
            ] += 1

        elif finding.finding_type in {
            "FUTURE_NAMED_VARIABLE",
        }:

            counts[
                "FUTURE_NAMED_VARIABLE"
            ] += 1

        elif finding.finding_type in {
            "MERGE_ASOF",
        }:

            counts[
                "MERGE_ASOF"
            ] += 1

    return dict(counts)


# ============================================================
# TARGET VS FEATURE FUTURE LOGIC
# ============================================================


def determine_target_future_context(
    global_source_findings: list[SourceFinding],
) -> tuple[
    int,
    int,
]:

    target_context_count = 0
    unresolved_count = 0

    for finding in global_source_findings:

        if finding.finding_type not in {
            "NEGATIVE_SHIFT",
            "CENTERED_ROLLING",
            "LEAD_OPERATION",
            "FUTURE_NAMED_VARIABLE",
        }:
            continue

        try:
            path = Path(
                finding.file
            )

            lines = read_source_file(
                path
            )

            if is_target_generation_context(
                finding,
                lines,
            ):
                target_context_count += 1
            else:
                unresolved_count += 1

        except Exception:
            unresolved_count += 1

    return (
        target_context_count,
        unresolved_count,
    )


# ============================================================
# SUMMARY
# ============================================================


def build_summary(
    feature_audits: list[FeatureAudit],
    global_ast_findings: list[ASTFinding],
    global_source_findings: list[SourceFinding],
) -> dict[str, Any]:

    verdict_counts = Counter(
        audit.verdict
        for audit in feature_audits
    )

    direction_counts = Counter(
        audit.causal_direction
        for audit in feature_audits
    )

    feature_future_count = sum(
        audit.feature_specific_future_signal
        for audit in feature_audits
    )

    feature_negative_shift_count = sum(
        audit.feature_specific_negative_shift
        for audit in feature_audits
    )

    feature_centered_count = sum(
        audit.feature_specific_centered_rolling
        for audit in feature_audits
    )

    feature_forward_count = sum(
        audit.feature_specific_forward_operation
        for audit in feature_audits
    )

    ast_future_count = sum(
        finding.direction == "FUTURE"
        for finding in global_ast_findings
    )

    ast_centered_count = sum(
        finding.direction == "CENTERED"
        for finding in global_ast_findings
    )

    target_related_ast_count = sum(
        finding.target_related
        for finding in global_ast_findings
    )

    (
        target_future_source_count,
        unresolved_future_source_count,
    ) = determine_target_future_context(
        global_source_findings
    )

    return {
        "historical_features_audited": len(
            feature_audits
        ),
        "verdict_counts": dict(
            verdict_counts
        ),
        "causal_direction_counts": dict(
            direction_counts
        ),
        "feature_specific_future_signal_count": (
            int(feature_future_count)
        ),
        "feature_specific_negative_shift_count": (
            int(feature_negative_shift_count)
        ),
        "feature_specific_centered_rolling_count": (
            int(feature_centered_count)
        ),
        "feature_specific_forward_operation_count": (
            int(feature_forward_count)
        ),
        "ast_future_operation_count": (
            int(ast_future_count)
        ),
        "ast_centered_operation_count": (
            int(ast_centered_count)
        ),
        "target_related_ast_finding_count": (
            int(target_related_ast_count)
        ),
        "source_future_findings_in_target_context": (
            int(target_future_source_count)
        ),
        "source_future_findings_requiring_review": (
            int(unresolved_future_source_count)
        ),
    }


# ============================================================
# FINAL VERDICT
# ============================================================


def calculate_final_verdict(
    feature_audits: list[FeatureAudit],
    summary: dict[str, Any],
) -> tuple[
    str,
    list[str],
]:

    reasons: list[str] = []

    confirmed = [
        audit
        for audit in feature_audits
        if audit.verdict
        == "CONFIRMED_FUTURE_LEAKAGE"
    ]

    potential = [
        audit
        for audit in feature_audits
        if audit.verdict
        == "POTENTIAL_FUTURE_LEAKAGE"
    ]

    review = [
        audit
        for audit in feature_audits
        if audit.verdict
        in {
            "REQUIRES_CAUSAL_REVIEW",
            "NO_SOURCE_EVIDENCE",
            "CAUSALLY_SAFE_WITH_BOUNDARY_ASSUMPTION",
        }
    ]

    if confirmed:

        reasons.append(
            f"{len(confirmed)} historical feature(s) "
            "were classified as confirmed future leakage."
        )

        return (
            "FAIL_CONFIRMED_FUTURE_LEAKAGE",
            reasons,
        )

    if potential:

        reasons.append(
            f"{len(potential)} historical feature(s) "
            "contain feature-specific future-oriented "
            "signals and require immediate review."
        )

        reasons.append(
            "No feature is approved for production until "
            "the suspicious temporal construct is resolved."
        )

        return (
            "FAIL_REQUIRES_LEAKAGE_REMEDIATION",
            reasons,
        )

    if review:

        reasons.append(
            f"{len(review)} historical feature(s) remain "
            "conditional because static source analysis "
            "does not formally prove their causal cutoff."
        )

        reasons.append(
            "Historical feature approval requires proof "
            "that source information is available at or "
            "before prediction timestamp T."
        )

        if summary[
            "source_future_findings_requiring_review"
        ]:
            reasons.append(
                f"{summary['source_future_findings_requiring_review']} "
                "source-level future construct(s) remain "
                "unresolved outside clearly identifiable "
                "target-generation context."
            )

        return (
            "PASS_WITH_CAUSAL_REVIEW",
            reasons,
        )

    return (
        "PASS_CAUSALLY_VERIFIED",
        [
            "All audited historical features have "
            "sufficient static causal evidence."
        ],
    )


# ============================================================
# JSON SERIALIZATION
# ============================================================


def write_json(
    *,
    manifest: dict[str, Any],
    feature_audits: list[FeatureAudit],
    summary: dict[str, Any],
    global_source_findings: list[SourceFinding],
    global_ast_findings: list[ASTFinding],
    verdict: str,
    verdict_reasons: list[str],
) -> None:

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "audit_metadata": {
            "script": SCRIPT_NAME,
            "generated_at_utc": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            "target_column": TARGET_COLUMN,
            "forecast_horizon_minutes": (
                FORECAST_HORIZON_MINUTES
            ),
            "prediction_timestamp_contract": (
                "Features must be available at or before T."
            ),
            "test_dataset_loaded": False,
            "xgboost_training_performed": False,
            "feature_pipeline_rebuilt": False,
            "persisted_datasets_modified": False,
        },
        "paths": {
            "training": str(
                TRAIN_PATH
            ),
            "validation": str(
                VALIDATION_PATH
            ),
            "test": str(
                TEST_PATH
            ),
            "manifest": str(
                MANIFEST_PATH
            ),
            "source_root": str(
                SOURCE_ROOT
            ),
        },
        "manifest_summary": {
            "registered_feature_count": len(
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
        "summary": summary,
        "final_verdict": verdict,
        "verdict_reasons": verdict_reasons,
        "features": [
            asdict(audit)
            for audit in feature_audits
        ],
        "source_findings": [
            asdict(finding)
            for finding in global_source_findings
        ],
        "ast_findings": [
            asdict(finding)
            for finding in global_ast_findings
        ],
    }

    with JSON_OUTPUT.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            payload,
            handle,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# CSV WRITERS
# ============================================================


def write_feature_csv(
    feature_audits: list[FeatureAudit],
) -> None:

    fields = [
        "feature",
        "feature_index",
        "classification",
        "train_present",
        "validation_present",
        "dtype_train",
        "dtype_validation",
        "train_null_count",
        "validation_null_count",
        "source_files",
        "source_line_count",
        "historical_name_signal",
        "lag_signal",
        "rolling_signal",
        "trend_signal",
        "feature_specific_future_signal",
        "feature_specific_negative_shift",
        "feature_specific_centered_rolling",
        "feature_specific_forward_operation",
        "target_reference_signal",
        "causal_direction",
        "verdict",
        "confidence",
        "reasons",
        "recommended_action",
    ]

    with FEATURE_CSV_OUTPUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        for audit in feature_audits:

            row = asdict(
                audit
            )

            row["source_files"] = (
                " | ".join(
                    audit.source_files
                )
            )

            row["reasons"] = (
                " | ".join(
                    audit.reasons
                )
            )

            writer.writerow(
                {
                    field: row.get(
                        field
                    )
                    for field in fields
                }
            )


def write_source_csv(
    source_findings: list[SourceFinding],
) -> None:

    fields = [
        "file",
        "line_number",
        "line_text",
        "finding_type",
        "severity",
        "feature",
        "context",
    ]

    with SOURCE_CSV_OUTPUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        for finding in source_findings:

            writer.writerow(
                asdict(
                    finding
                )
            )


def write_ast_csv(
    ast_findings: list[ASTFinding],
) -> None:

    fields = [
        "file",
        "line_number",
        "operation",
        "direction",
        "severity",
        "expression",
        "context",
        "target_related",
    ]

    with AST_CSV_OUTPUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fields,
        )

        writer.writeheader()

        for finding in ast_findings:

            writer.writerow(
                asdict(
                    finding
                )
            )


def write_summary_csv(
    summary: dict[str, Any],
    verdict: str,
    verdict_reasons: list[str],
) -> None:

    rows: list[dict[str, Any]] = []

    for key, value in summary.items():

        if isinstance(
            value,
            dict,
        ):
            for child_key, child_value in (
                value.items()
            ):

                rows.append(
                    {
                        "category": key,
                        "metric": child_key,
                        "value": child_value,
                    }
                )

        else:

            rows.append(
                {
                    "category": "summary",
                    "metric": key,
                    "value": value,
                }
            )

    rows.append(
        {
            "category": "final_verdict",
            "metric": "verdict",
            "value": verdict,
        }
    )

    for index, reason in enumerate(
        verdict_reasons,
        start=1,
    ):

        rows.append(
            {
                "category": "final_verdict",
                "metric": f"reason_{index}",
                "value": reason,
            }
        )

    with SUMMARY_CSV_OUTPUT.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "category",
                "metric",
                "value",
            ],
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


# ============================================================
# CONSOLE REPORT
# ============================================================


def print_feature_summary(
    feature_audits: list[FeatureAudit],
) -> None:

    verdict_counts = Counter(
        audit.verdict
        for audit in feature_audits
    )

    direction_counts = Counter(
        audit.causal_direction
        for audit in feature_audits
    )

    print_section(
        "HISTORICAL FEATURE CLASSIFICATION"
    )

    print_status(
        "Historical features identified",
        len(feature_audits),
    )

    print()

    print(
        "Causal direction:"
    )

    for direction, count in sorted(
        direction_counts.items()
    ):
        print(
            f"  {direction:<42} : {count}"
        )

    print()

    print(
        "Feature verdicts:"
    )

    for verdict, count in sorted(
        verdict_counts.items()
    ):
        print(
            f"  {verdict:<42} : {count}"
        )


def print_temporal_summary(
    summary: dict[str, Any],
) -> None:

    print_section(
        "TEMPORAL OPERATION SUMMARY"
    )

    print_status(
        "Feature-specific future signals",
        summary[
            "feature_specific_future_signal_count"
        ],
    )

    print_status(
        "Feature-specific negative shifts",
        summary[
            "feature_specific_negative_shift_count"
        ],
    )

    print_status(
        "Feature-specific centered rolling",
        summary[
            "feature_specific_centered_rolling_count"
        ],
    )

    print_status(
        "Feature-specific forward operations",
        summary[
            "feature_specific_forward_operation_count"
        ],
    )

    print_status(
        "AST future operations",
        summary[
            "ast_future_operation_count"
        ],
    )

    print_status(
        "AST centered operations",
        summary[
            "ast_centered_operation_count"
        ],
    )

    print_status(
        "Target-related AST findings",
        summary[
            "target_related_ast_finding_count"
        ],
    )

    print_status(
        "Future constructs in target context",
        summary[
            "source_future_findings_in_target_context"
        ],
    )

    print_status(
        "Future constructs requiring review",
        summary[
            "source_future_findings_requiring_review"
        ],
    )


def print_suspicious_features(
    feature_audits: list[FeatureAudit],
) -> None:

    suspicious = [
        audit
        for audit in feature_audits
        if audit.verdict
        in {
            "POTENTIAL_FUTURE_LEAKAGE",
            "CONFIRMED_FUTURE_LEAKAGE",
        }
    ]

    print_section(
        "SUSPICIOUS HISTORICAL FEATURES"
    )

    if not suspicious:

        print(
            "No historical feature was automatically "
            "classified as confirmed leakage."
        )

        print(
            "This does NOT mean all historical features "
            "are production-approved."
        )

        return

    for audit in suspicious:

        print()
        print(
            f"  {audit.feature}"
        )

        print(
            f"    Verdict     : {audit.verdict}"
        )

        print(
            f"    Direction   : {audit.causal_direction}"
        )

        print(
            f"    Confidence  : {audit.confidence}"
        )

        for reason in audit.reasons:

            print(
                f"    Reason      : {reason}"
            )


def print_final_report(
    feature_audits: list[FeatureAudit],
    summary: dict[str, Any],
    verdict: str,
    verdict_reasons: list[str],
) -> None:

    print_section(
        "FINAL CAUSALITY AUDIT RESULT"
    )

    print_status(
        "Historical features audited",
        len(feature_audits),
    )

    print_status(
        "Potential future leakage features",
        sum(
            audit.verdict
            == "POTENTIAL_FUTURE_LEAKAGE"
            for audit in feature_audits
        ),
    )

    print_status(
        "Confirmed future leakage features",
        sum(
            audit.verdict
            == "CONFIRMED_FUTURE_LEAKAGE"
            for audit in feature_audits
        ),
    )

    print_status(
        "Features requiring causal review",
        sum(
            audit.verdict
            in {
                "REQUIRES_CAUSAL_REVIEW",
                "NO_SOURCE_EVIDENCE",
                "CAUSALLY_SAFE_WITH_BOUNDARY_ASSUMPTION",
            }
            for audit in feature_audits
        ),
    )

    print()
    print(
        f"PRODUCTION CAUSALITY VERDICT : {verdict}"
    )

    print()

    print(
        "Verdict reasons:"
    )

    for reason in verdict_reasons:

        print(
            f"  - {reason}"
        )

    print()

    print(
        "IMPORTANT:"
    )

    print(
        "A future-oriented construct used exclusively "
        "for forecast TARGET construction is not by itself "
        "feature leakage."
    )

    print(
        "Historical features remain conditional until "
        "their source timestamp boundary is formally verified."
    )


# ============================================================
# FINAL ASSERTIONS
# ============================================================


def run_final_assertions(
    registered_features: list[str],
    train: pd.DataFrame,
    validation: pd.DataFrame,
    feature_audits: list[FeatureAudit],
) -> None:

    print_section(
        "FINAL ASSERTIONS"
    )

    train_non_empty = (
        not train.empty
    )

    validation_non_empty = (
        not validation.empty
    )

    expected_count = (
        len(registered_features)
        == EXPECTED_FEATURE_COUNT
    )

    audit_features_unique = (
        len(
            {
                audit.feature
                for audit in feature_audits
            }
        )
        == len(feature_audits)
    )

    target_not_feature = (
        TARGET_COLUMN
        not in registered_features
    )

    all_present = all(
        audit.train_present
        and audit.validation_present
        for audit in feature_audits
    )

    print_pass(
        "Training dataset non-empty",
        train_non_empty,
    )

    print_pass(
        "Validation dataset non-empty",
        validation_non_empty,
    )

    print_pass(
        "Expected feature count",
        expected_count,
    )

    print_pass(
        "No duplicate audited historical features",
        audit_features_unique,
    )

    print_pass(
        "Target not included as registered feature",
        target_not_feature,
    )

    print_pass(
        "All audited historical features present",
        all_present,
    )

    if not train_non_empty:
        raise AuditDataError(
            "Training dataset is empty."
        )

    if not validation_non_empty:
        raise AuditDataError(
            "Validation dataset is empty."
        )

    if not audit_features_unique:
        raise AuditDataError(
            "Duplicate historical feature audit rows."
        )

    if not target_not_feature:
        raise AuditDataError(
            "Target column is incorrectly registered "
            "as a feature."
        )

    if not all_present:
        raise AuditDataError(
            "One or more audited historical features "
            "are missing from train/validation."
        )


# ============================================================
# MAIN
# ============================================================


def main() -> int:

    print_header(
        "SMARTPARK AI - BIRMINGHAM XGBOOST "
        "HISTORICAL FEATURE CAUSALITY AUDIT"
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
        "Production prediction contract:"
    )
    print(
        "  Prediction timestamp = T"
    )
    print(
        "  Forecast horizon     = T + 30 minutes"
    )
    print(
        "  Feature information  = available at or before T"
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
        "  Identify historical / lag / rolling features"
    )
    print(
        "  Perform source-level temporal analysis"
    )
    print(
        "  Distinguish target-generation future logic "
        "from feature-generation future logic"
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

        # ----------------------------------------------------
        # Paths
        # ----------------------------------------------------

        validate_paths()

        # ----------------------------------------------------
        # Manifest
        # ----------------------------------------------------

        manifest = load_manifest()

        # ----------------------------------------------------
        # Datasets
        # ----------------------------------------------------

        train, validation = (
            load_persisted_datasets()
        )

        # ----------------------------------------------------
        # Registry
        # ----------------------------------------------------

        registered_features = (
            validate_feature_registry(
                manifest,
                train,
                validation,
            )
        )

        # ----------------------------------------------------
        # Target
        # ----------------------------------------------------

        validate_targets(
            train,
            validation,
        )

        # ----------------------------------------------------
        # Source files
        # ----------------------------------------------------

        source_files = (
            discover_source_files()
        )

        # ----------------------------------------------------
        # Global AST scan
        # ----------------------------------------------------

        print_section(
            "AST TEMPORAL ANALYSIS"
        )

        global_ast_findings = (
            scan_global_ast_findings(
                source_files
            )
        )

        print_status(
            "AST temporal findings",
            len(global_ast_findings),
        )

        # ----------------------------------------------------
        # Global source scan
        # ----------------------------------------------------

        print_section(
            "SOURCE TEMPORAL SIGNAL SCAN"
        )

        global_source_findings = (
            scan_global_source_findings(
                source_files
            )
        )

        print_status(
            "Source temporal findings",
            len(global_source_findings),
        )

        global_signal_counts = (
            classify_global_future_findings(
                global_source_findings
            )
        )

        for key, value in sorted(
            global_signal_counts.items()
        ):

            print_status(
                key,
                value,
            )

        # ----------------------------------------------------
        # Feature-level audit
        # ----------------------------------------------------

        print_section(
            "BUILDING HISTORICAL FEATURE CAUSALITY CONTRACT"
        )

        (
            feature_audits,
            feature_source_findings,
            feature_ast_findings,
        ) = build_feature_audits(
            registered_features=(
                registered_features
            ),
            train=train,
            validation=validation,
            source_files=source_files,
            global_ast_findings=(
                global_ast_findings
            ),
        )

        print_status(
            "Historical features identified",
            len(feature_audits),
        )

        print_status(
            "Feature-specific source findings",
            len(feature_source_findings),
        )

        print_status(
            "Feature-specific AST findings",
            len(feature_ast_findings),
        )

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        summary = build_summary(
            feature_audits=feature_audits,
            global_ast_findings=(
                global_ast_findings
            ),
            global_source_findings=(
                global_source_findings
            ),
        )

        # ----------------------------------------------------
        # Final verdict
        # ----------------------------------------------------

        (
            verdict,
            verdict_reasons,
        ) = calculate_final_verdict(
            feature_audits=feature_audits,
            summary=summary,
        )

        # ----------------------------------------------------
        # Assertions
        # ----------------------------------------------------

        run_final_assertions(
            registered_features=(
                registered_features
            ),
            train=train,
            validation=validation,
            feature_audits=feature_audits,
        )

        # ----------------------------------------------------
        # Console report
        # ----------------------------------------------------

        print_feature_summary(
            feature_audits
        )

        print_temporal_summary(
            summary
        )

        print_suspicious_features(
            feature_audits
        )

        print_final_report(
            feature_audits=feature_audits,
            summary=summary,
            verdict=verdict,
            verdict_reasons=verdict_reasons,
        )

        # ----------------------------------------------------
        # Persist results
        # ----------------------------------------------------

        print_section(
            "PERSISTING CAUSALITY AUDIT RESULTS"
        )

        write_json(
            manifest=manifest,
            feature_audits=feature_audits,
            summary=summary,
            global_source_findings=(
                global_source_findings
            ),
            global_ast_findings=(
                global_ast_findings
            ),
            verdict=verdict,
            verdict_reasons=verdict_reasons,
        )

        write_feature_csv(
            feature_audits
        )

        write_source_csv(
            (
                global_source_findings
                + feature_source_findings
            )
        )

        write_ast_csv(
            (
                global_ast_findings
                + feature_ast_findings
            )
        )

        write_summary_csv(
            summary=summary,
            verdict=verdict,
            verdict_reasons=verdict_reasons,
        )

        print_status(
            "Output directory",
            OUTPUT_ROOT,
        )

        print_status(
            "JSON report",
            JSON_OUTPUT,
        )

        print_status(
            "CSV feature contract",
            FEATURE_CSV_OUTPUT,
        )

        print_status(
            "CSV source findings",
            SOURCE_CSV_OUTPUT,
        )

        print_status(
            "CSV summary",
            SUMMARY_CSV_OUTPUT,
        )

        print_status(
            "CSV AST findings",
            AST_CSV_OUTPUT,
        )

        # ----------------------------------------------------
        # Completion
        # ----------------------------------------------------

        print()
        print("=" * 78)

        if verdict == (
            "FAIL_CONFIRMED_FUTURE_LEAKAGE"
        ):

            print(
                "BIRMINGHAM HISTORICAL FEATURE "
                "CAUSALITY AUDIT FAILED"
            )

            print("=" * 78)

            print()
            print(
                "Confirmed future leakage was detected."
            )

            print(
                "DO NOT proceed to production feature "
                "approval until leakage is remediated."
            )

            return 2

        if verdict == (
            "FAIL_REQUIRES_LEAKAGE_REMEDIATION"
        ):

            print(
                "BIRMINGHAM HISTORICAL FEATURE "
                "CAUSALITY AUDIT REQUIRES REMEDIATION"
            )

            print("=" * 78)

            print()
            print(
                "Potential future leakage was detected "
                "in one or more historical features."
            )

            print(
                "DO NOT approve affected features "
                "for production."
            )

            return 2

        if verdict == (
            "PASS_WITH_CAUSAL_REVIEW"
        ):

            print(
                "BIRMINGHAM HISTORICAL FEATURE "
                "CAUSALITY AUDIT PASSED WITH REVIEW"
            )

            print("=" * 78)

            print()
            print(
                "No historical feature was automatically "
                "classified as confirmed future leakage."
            )

            print(
                "However, causal timestamp verification "
                "is still required before production approval."
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
                "Historical feature causality audit "
                "is ready for engineering review."
            )

            return 0

        print(
            "BIRMINGHAM HISTORICAL FEATURE "
            "CAUSALITY AUDIT PASSED"
        )

        print("=" * 78)

        print()
        print(
            "All audited historical features have "
            "sufficient static causal evidence."
        )

        print(
            "Formal production approval may proceed "
            "subject to the remaining feature-contract gates."
        )

        return 0

    except (
        AuditError,
        ValueError,
        KeyError,
        OSError,
        ImportError,
    ) as exc:

        print()
        print("=" * 78)

        print(
            "BIRMINGHAM HISTORICAL FEATURE "
            "CAUSALITY AUDIT FAILED"
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

    except Exception as exc:

        print()
        print("=" * 78)

        print(
            "BIRMINGHAM HISTORICAL FEATURE "
            "CAUSALITY AUDIT FAILED"
        )

        print("=" * 78)

        print()
        print(
            "UNEXPECTED ERROR:"
        )

        print(
            f"{type(exc).__name__}: {exc}"
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


# ============================================================
# ENTRY POINT
# ============================================================


if __name__ == "__main__":
    sys.exit(
        main()
    )