"""
SmartPark AI
Birmingham XGBoost Feature Causal Verification Audit

Purpose
-------
Perform a conservative, feature-by-feature causal availability audit
for the Birmingham target_occupancy_rate_30m XGBoost feature registry.

Production contract
-------------------
Prediction timestamp = T
Forecast horizon     = T + 30 minutes

A production feature must use information available at or before T.

This audit is intentionally conservative.

It does NOT attempt to prove causality merely because a feature name
contains words such as "lag", "rolling", "historical", etc.

Instead it combines:

1. Persisted feature registry
2. Existing feature-lineage audit artifacts
3. Actual ML source code
4. Source temporal operations
5. Feature naming signals
6. Target-generation context
7. Current-state classification

Important
---------
This script:

- DOES load train.parquet
- DOES load validation.parquet
- DOES NOT load test.parquet
- DOES NOT train XGBoost
- DOES NOT rebuild the feature pipeline
- DOES NOT modify persisted datasets

Outputs
-------
datasets/processed/birmingham/
    xgboost_feature_causal_verification/
        birmingham_xgboost_feature_causal_verification.json
        birmingham_xgboost_feature_causal_verification_features.csv
        birmingham_xgboost_feature_causal_verification_summary.csv
        birmingham_xgboost_feature_causal_verification_source_findings.csv

The audit is static/conservative.

A PRODUCTION_SAFE result means the available evidence supports
causal availability at T according to the rules implemented here.

It is not a substitute for production integration testing.
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


# ============================================================================
# CONSTANTS
# ============================================================================

TARGET_COLUMN = "target_occupancy_rate_30m"

FORECAST_HORIZON_MINUTES = 30

EXPECTED_FEATURE_COUNT = 296

PROJECT_NAME = "SmartPark AI"

BIRMINGHAM = "birmingham"

FEATURE_LINEAGE_DIRECTORY = (
    "xgboost_feature_lineage"
)

OUTPUT_DIRECTORY = (
    "xgboost_feature_causal_verification"
)

LINEAGE_FEATURE_FILE = (
    "birmingham_xgboost_feature_lineage_features.csv"
)

LINEAGE_SOURCE_FILE = (
    "birmingham_xgboost_feature_lineage_source_findings.csv"
)

LINEAGE_SUMMARY_FILE = (
    "birmingham_xgboost_feature_lineage_summary.csv"
)

MANIFEST_FILE = (
    "training_dataset_manifest.json"
)

TRAIN_FILE = "train.parquet"

VALIDATION_FILE = "validation.parquet"

TEST_FILE = "test.parquet"


# ============================================================================
# FEATURE CLASSIFICATION SIGNALS
# ============================================================================

CURRENT_STATE_FEATURE_NAMES = {
    "capacity_utilization",
    "availability_rate",
    "occupied_ratio",
    "available_ratio",
    "vacancy_ratio",
    "occupancy_level",
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
}


CURRENT_STATE_TOKENS = (
    "current",
    "occupancy",
    "occupied",
    "availability",
    "available",
    "vacancy",
    "capacity_utilization",
    "demand_pressure",
    "remaining_capacity",
    "is_full",
)


HISTORICAL_TOKENS = (
    "lag",
    "history",
    "historical",
    "rolling",
    "roll",
    "moving",
    "previous",
    "prior",
    "past",
    "recent",
    "trend",
    "momentum",
    "change",
    "delta",
    "difference",
    "diff",
    "pct_change",
    "growth",
)


TEMPORAL_TOKENS = (
    "hour",
    "minute",
    "day",
    "weekday",
    "week",
    "month",
    "year",
    "date",
    "time",
    "slot",
    "weekend",
    "holiday",
    "sin_",
    "cos_",
)


FUTURE_TOKENS = (
    "future",
    "forecast",
    "target",
    "next",
    "ahead",
    "lead",
    "forward",
    "tomorrow",
)


SOURCE_OPERATION_PATTERNS = {
    "SHIFT": re.compile(
        r"\.shift\s*\(",
        re.IGNORECASE,
    ),
    "ROLLING": re.compile(
        r"\.rolling\s*\(",
        re.IGNORECASE,
    ),
    "DIFF": re.compile(
        r"\.diff\s*\(",
        re.IGNORECASE,
    ),
    "PCT_CHANGE": re.compile(
        r"\.pct_change\s*\(",
        re.IGNORECASE,
    ),
    "EXPANDING": re.compile(
        r"\.expanding\s*\(",
        re.IGNORECASE,
    ),
    "EWMA": re.compile(
        r"\.ewm\s*\(",
        re.IGNORECASE,
    ),
}


NEGATIVE_SHIFT_PATTERN = re.compile(
    r"\.shift\s*\(\s*-\s*[\w\.\+\-\*\/]+",
    re.IGNORECASE,
)


POSITIVE_SHIFT_PATTERN = re.compile(
    r"\.shift\s*\(\s*\+?\s*\d+",
    re.IGNORECASE,
)


CENTERED_ROLLING_PATTERN = re.compile(
    r"\.rolling\s*\([^)]*center\s*=\s*True",
    re.IGNORECASE,
)


FORWARD_OPERATION_PATTERNS = (
    re.compile(
        r"\.shift\s*\(\s*-\s*",
        re.IGNORECASE,
    ),
    re.compile(
        r"\.lead\s*\(",
        re.IGNORECASE,
    ),
    re.compile(
        r"forward",
        re.IGNORECASE,
    ),
)


TARGET_CONTEXT_PATTERNS = (
    re.compile(
        r"target_occupancy_rate_30m",
        re.IGNORECASE,
    ),
    re.compile(
        r"target_occupancy_rate_1h",
        re.IGNORECASE,
    ),
    re.compile(
        r"target_occupancy_rate_2h",
        re.IGNORECASE,
    ),
    re.compile(
        r"future_occupancy",
        re.IGNORECASE,
    ),
    re.compile(
        r"target_valid",
        re.IGNORECASE,
    ),
    re.compile(
        r"future_observed",
        re.IGNORECASE,
    ),
)


# ============================================================================
# EXCEPTIONS
# ============================================================================


class CausalVerificationError(RuntimeError):
    """Base audit error."""


class CausalVerificationFileError(
    CausalVerificationError
):
    """Required file/path error."""


class CausalVerificationContractError(
    CausalVerificationError
):
    """Dataset or feature contract error."""


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class SourceFinding:
    file: str
    line_number: int
    operation: str
    context: str
    target_context: bool
    feature_context: bool
    future_or_forward: bool
    negative_shift: bool
    centered_rolling: bool
    expression: str


@dataclass
class FeatureCausalContract:
    feature: str
    feature_family: str

    training_dtype: str
    validation_dtype: str

    source_evidence_count: int
    source_files: list[str] = field(
        default_factory=list
    )
    source_lines: list[int] = field(
        default_factory=list
    )
    source_expressions: list[str] = field(
        default_factory=list
    )

    lineage_evidence: str = ""

    has_shift_operation: bool = False
    has_positive_shift: bool = False
    has_negative_shift: bool = False

    has_rolling_operation: bool = False
    has_centered_rolling: bool = False

    has_diff_operation: bool = False
    has_pct_change_operation: bool = False

    has_forward_operation: bool = False
    target_context: bool = False
    feature_context: bool = False

    current_state_feature: bool = False
    historical_feature: bool = False
    temporal_feature: bool = False

    source_information_cutoff: str = ""

    causal_reason: str = ""

    verdict: str = ""

    confidence: str = ""

    requires_realtime_contract: bool = False
    requires_causal_review: bool = False
    potential_leakage: bool = False


# ============================================================================
# PATH DISCOVERY
# ============================================================================


def discover_repository_root() -> Path:
    """
    Locate the SmartPark AI repository root.

    Actual structure:

        smart-parking-system/
        ├── backend/
        │   ├── app/
        │   └── birmingham_xgboost_feature_causal_verification.py
        │
        └── datasets/
            └── processed/
                └── birmingham/
    """

    script_path = Path(
        __file__
    ).resolve()

    backend_root = (
        script_path.parent
    )

    repository_root = (
        backend_root.parent
    )

    if (
        (backend_root / "app").is_dir()
        and
        (repository_root / "datasets").is_dir()
    ):
        return repository_root

    current = script_path.parent

    for candidate in [
        current,
        *current.parents,
    ]:

        if (
            (candidate / "backend" / "app").is_dir()
            and
            (candidate / "datasets").is_dir()
        ):
            return candidate

        if (
            (candidate / "app").is_dir()
            and
            (candidate / "datasets").is_dir()
        ):
            return candidate

    raise CausalVerificationFileError(
        "Unable to determine SmartPark AI repository root. "
        f"Script location: {script_path}"
    )


def resolve_paths() -> dict[str, Path]:

    repository_root = (
        discover_repository_root()
    )

    backend_root = (
        repository_root / "backend"
    )

    source_root = (
        backend_root / "app" / "ml"
    )

    birmingham_root = (
        repository_root
        / "datasets"
        / "processed"
        / BIRMINGHAM
    )

    target_root = (
        birmingham_root
        / "target_occupancy_rate_30m"
    )

    lineage_root = (
        birmingham_root
        / FEATURE_LINEAGE_DIRECTORY
    )

    output_root = (
        birmingham_root
        / OUTPUT_DIRECTORY
    )

    return {
        "repository_root": repository_root,
        "backend_root": backend_root,
        "source_root": source_root,
        "birmingham_root": birmingham_root,
        "train": target_root / TRAIN_FILE,
        "validation": target_root / VALIDATION_FILE,
        "test": target_root / TEST_FILE,
        "manifest": birmingham_root / MANIFEST_FILE,
        "lineage_root": lineage_root,
        "lineage_features": (
            lineage_root
            / LINEAGE_FEATURE_FILE
        ),
        "lineage_source": (
            lineage_root
            / LINEAGE_SOURCE_FILE
        ),
        "lineage_summary": (
            lineage_root
            / LINEAGE_SUMMARY_FILE
        ),
        "output": output_root,
    }


# ============================================================================
# DISPLAY HELPERS
# ============================================================================


def print_header(
    title: str,
) -> None:

    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(
    title: str,
) -> None:

    print()
    print(f"--- {title} ---")


def print_status(
    label: str,
    value: Any,
    width: int = 44,
) -> None:

    print(
        f"{label:<{width}} : {value}"
    )


def print_pass(
    label: str,
) -> None:

    print_status(
        label,
        "PASS",
    )


def print_fail(
    label: str,
) -> None:

    print_status(
        label,
        "FAIL",
    )


# ============================================================================
# FILE VALIDATION
# ============================================================================


def validate_required_files(
    paths: dict[str, Path],
) -> None:

    required = [
        "train",
        "validation",
        "test",
        "manifest",
        "lineage_features",
        "lineage_source",
    ]

    for key in required:

        path = paths[key]

        if not path.exists():

            raise CausalVerificationFileError(
                f"Required file does not exist: {path}"
            )

        if not path.is_file():

            raise CausalVerificationFileError(
                f"Required path is not a file: {path}"
            )


# ============================================================================
# MANIFEST
# ============================================================================


def load_manifest(
    path: Path,
) -> dict[str, Any]:

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:

            data = json.load(handle)

    except Exception as exc:

        raise CausalVerificationFileError(
            f"Unable to load manifest: {path}: {exc}"
        ) from exc

    if not isinstance(
        data,
        dict,
    ):

        raise CausalVerificationContractError(
            "Feature manifest must contain a JSON object."
        )

    return data


def extract_manifest_features(
    manifest: dict[str, Any],
) -> list[str]:

    features = manifest.get(
        "feature_columns",
        [],
    )

    if not isinstance(
        features,
        list,
    ):

        raise CausalVerificationContractError(
            "Manifest feature_columns must be a list."
        )

    normalized = [
        str(feature)
        for feature in features
    ]

    if len(
        normalized
    ) != len(
        set(normalized)
    ):

        duplicates = [
            feature
            for feature, count
            in Counter(normalized).items()
            if count > 1
        ]

        raise CausalVerificationContractError(
            "Duplicate features in manifest: "
            f"{duplicates}"
        )

    return normalized


# ============================================================================
# DATASET LOADING
# ============================================================================


def load_training_validation(
    paths: dict[str, Path],
) -> tuple[pd.DataFrame, pd.DataFrame]:

    print_section(
        "LOADING PERSISTED DATASETS"
    )

    print(
        "Loading training dataset..."
    )

    train = pd.read_parquet(
        paths["train"]
    )

    print(
        "Loading validation dataset..."
    )

    validation = pd.read_parquet(
        paths["validation"]
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

        raise CausalVerificationContractError(
            "Training dataset is empty."
        )

    if validation.empty:

        raise CausalVerificationContractError(
            "Validation dataset is empty."
        )

    return train, validation


# ============================================================================
# FEATURE REGISTRY
# ============================================================================


def identify_model_features(
    dataframe: pd.DataFrame,
    manifest_features: list[str],
) -> list[str]:

    missing = [
        feature
        for feature in manifest_features
        if feature not in dataframe.columns
    ]

    if missing:

        raise CausalVerificationContractError(
            "Persisted dataset is missing registered "
            f"features: {missing}"
        )

    return [
        feature
        for feature in manifest_features
    ]


def validate_feature_registry(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    manifest_features: list[str],
) -> None:

    train_features = identify_model_features(
        train,
        manifest_features,
    )

    validation_features = identify_model_features(
        validation,
        manifest_features,
    )

    if train_features != manifest_features:

        raise CausalVerificationContractError(
            "Training feature registry does not match manifest."
        )

    if validation_features != manifest_features:

        raise CausalVerificationContractError(
            "Validation feature registry does not match manifest."
        )

    print_section(
        "FEATURE REGISTRY VALIDATION"
    )

    print_status(
        "Registered features",
        len(manifest_features),
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
        "Training feature registry"
    )

    print_pass(
        "Validation feature registry"
    )

    print_pass(
        "Train/validation feature registry"
    )

    metadata_columns = [
        column
        for column in train.columns
        if column not in manifest_features
    ]

    print()
    print(
        "Persisted non-feature / metadata columns "
        "excluded from causal verification:"
    )

    for column in metadata_columns:

        print(
            f"  - {column}"
        )


# ============================================================================
# TARGET VALIDATION
# ============================================================================


def validate_target_contract(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> dict[str, Any]:

    print_section(
        "TARGET CONTRACT VALIDATION"
    )

    for name, dataframe in [
        ("Training", train),
        ("Validation", validation),
    ]:

        if TARGET_COLUMN not in dataframe.columns:

            raise CausalVerificationContractError(
                f"{name} dataset does not contain "
                f"target column '{TARGET_COLUMN}'."
            )

        target = pd.to_numeric(
            dataframe[TARGET_COLUMN],
            errors="coerce",
        )

        nulls = int(
            target.isna().sum()
        )

        if nulls:

            raise CausalVerificationContractError(
                f"{name} target contains {nulls} null values."
            )

        minimum = float(
            target.min()
        )

        maximum = float(
            target.max()
        )

        mean = float(
            target.mean()
        )

        print_status(
            f"{name} target rows",
            f"{len(target):,}",
        )

        print_status(
            f"{name} target nulls",
            nulls,
        )

        print_status(
            f"{name} target mean",
            f"{mean:.6f}",
        )

        print_status(
            f"{name} target range",
            f"{minimum:.6f} -> {maximum:.6f}",
        )

    print_pass(
        "Target contract"
    )

    return {
        "target_column": TARGET_COLUMN,
        "forecast_horizon_minutes": (
            FORECAST_HORIZON_MINUTES
        ),
    }


# ============================================================================
# SOURCE DISCOVERY
# ============================================================================


def discover_source_files(
    source_root: Path,
) -> list[Path]:

    if not source_root.exists():

        raise CausalVerificationFileError(
            f"ML source root does not exist: {source_root}"
        )

    files = sorted(
        path
        for path in source_root.rglob("*.py")
        if path.is_file()
    )

    if not files:

        raise CausalVerificationFileError(
            f"No Python source files found under: {source_root}"
        )

    return files


def read_source_files(
    source_files: list[Path],
    source_root: Path,
) -> dict[str, list[str]]:

    source = {}

    for path in source_files:

        relative = str(
            path.relative_to(
                source_root
            )
        )

        try:

            source[relative] = (
                path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                .splitlines()
            )

        except Exception as exc:

            raise CausalVerificationFileError(
                f"Unable to read source file {path}: {exc}"
            ) from exc

    return source


# ============================================================================
# SOURCE TEMPORAL SCANNING
# ============================================================================


def line_has_target_context(
    line: str,
) -> bool:

    return any(
        pattern.search(line)
        for pattern in TARGET_CONTEXT_PATTERNS
    )


def line_has_feature_context(
    line: str,
) -> bool:

    lower = line.lower()

    feature_tokens = (
        "feature",
        "features",
        "rolling",
        "lag",
        "historical",
        "occupancy",
        "availability",
        "demand",
        "pipeline",
    )

    return any(
        token in lower
        for token in feature_tokens
    )


def detect_operation(
    line: str,
) -> Optional[str]:

    for operation, pattern in (
        SOURCE_OPERATION_PATTERNS.items()
    ):

        if pattern.search(line):

            return operation

    return None


def scan_source_temporal_operations(
    source: dict[str, list[str]],
) -> list[SourceFinding]:

    findings: list[SourceFinding] = []

    for relative_path, lines in source.items():

        for index, line in enumerate(
            lines,
            start=1,
        ):

            operation = detect_operation(
                line
            )

            forward = any(
                pattern.search(line)
                for pattern
                in FORWARD_OPERATION_PATTERNS
            )

            negative_shift = bool(
                NEGATIVE_SHIFT_PATTERN.search(
                    line
                )
            )

            centered_rolling = bool(
                CENTERED_ROLLING_PATTERN.search(
                    line
                )
            )

            if (
                operation is None
                and not forward
                and not negative_shift
                and not centered_rolling
            ):

                continue

            target_context = (
                line_has_target_context(
                    line
                )
            )

            feature_context = (
                line_has_feature_context(
                    line
                )
            )

            if operation is None:

                if negative_shift:

                    operation = (
                        "NEGATIVE_SHIFT"
                    )

                elif centered_rolling:

                    operation = (
                        "CENTERED_ROLLING"
                    )

                else:

                    operation = (
                        "FUTURE_OR_FORWARD"
                    )

            findings.append(
                SourceFinding(
                    file=relative_path,
                    line_number=index,
                    operation=operation,
                    context=line.strip(),
                    target_context=target_context,
                    feature_context=feature_context,
                    future_or_forward=forward,
                    negative_shift=negative_shift,
                    centered_rolling=centered_rolling,
                    expression=line.strip(),
                )
            )

    return findings


# ============================================================================
# AST ANALYSIS
# ============================================================================


class TemporalASTVisitor(
    ast.NodeVisitor
):

    def __init__(
        self,
    ) -> None:

        self.findings: list[
            dict[str, Any]
        ] = []

    def visit_Call(
        self,
        node: ast.Call,
    ) -> Any:

        operation = None

        if isinstance(
            node.func,
            ast.Attribute,
        ):

            operation = node.func.attr

        if operation == "shift":

            negative = False
            positive = False

            if node.args:

                argument = node.args[0]

                if isinstance(
                    argument,
                    ast.UnaryOp,
                ) and isinstance(
                    argument.op,
                    ast.USub,
                ):

                    negative = True

                elif isinstance(
                    argument,
                    ast.Constant,
                ) and isinstance(
                    argument.value,
                    (int, float),
                ):

                    positive = (
                        argument.value >= 0
                    )

            self.findings.append(
                {
                    "operation": "SHIFT",
                    "negative": negative,
                    "positive": positive,
                    "line": node.lineno,
                }
            )

        elif operation == "rolling":

            centered = False

            for keyword in node.keywords:

                if keyword.arg == "center":

                    if isinstance(
                        keyword.value,
                        ast.Constant,
                    ):

                        centered = (
                            keyword.value.value
                            is True
                        )

            self.findings.append(
                {
                    "operation": "ROLLING",
                    "negative": False,
                    "positive": False,
                    "centered": centered,
                    "line": node.lineno,
                }
            )

        elif operation in {
            "diff",
            "pct_change",
            "expanding",
            "ewm",
        }:

            self.findings.append(
                {
                    "operation": operation.upper(),
                    "negative": False,
                    "positive": True,
                    "line": node.lineno,
                }
            )

        self.generic_visit(
            node
        )


def run_ast_analysis(
    source_files: list[Path],
    source_root: Path,
) -> list[dict[str, Any]]:

    findings = []

    for path in source_files:

        relative = str(
            path.relative_to(
                source_root
            )
        )

        try:

            text = path.read_text(
                encoding="utf-8",
                errors="replace",
            )

            tree = ast.parse(
                text,
                filename=str(path),
            )

        except (
            SyntaxError,
            OSError,
        ):

            continue

        visitor = TemporalASTVisitor()

        visitor.visit(
            tree
        )

        for finding in visitor.findings:

            finding = dict(
                finding
            )

            finding["file"] = (
                relative
            )

            findings.append(
                finding
            )

    return findings


# ============================================================================
# LINEAGE ARTIFACTS
# ============================================================================


def load_csv(
    path: Path,
) -> pd.DataFrame:

    try:

        return pd.read_csv(
            path
        )

    except Exception as exc:

        raise CausalVerificationFileError(
            f"Unable to load CSV {path}: {exc}"
        ) from exc


def find_column(
    dataframe: pd.DataFrame,
    candidates: Iterable[str],
) -> Optional[str]:

    columns = {
        str(column).strip().lower(): column
        for column in dataframe.columns
    }

    for candidate in candidates:

        key = candidate.lower()

        if key in columns:

            return columns[key]

    return None


def build_lineage_lookup(
    lineage_dataframe: pd.DataFrame,
) -> dict[str, dict[str, Any]]:

    feature_column = find_column(
        lineage_dataframe,
        (
            "feature",
            "feature_name",
            "column",
        ),
    )

    if feature_column is None:

        raise CausalVerificationContractError(
            "Lineage CSV does not contain a feature column."
        )

    lookup: dict[
        str,
        dict[str, Any]
    ] = {}

    for _, row in lineage_dataframe.iterrows():

        feature = str(
            row[feature_column]
        )

        lookup[feature] = {
            str(column): (
                ""
                if pd.isna(row[column])
                else row[column]
            )
            for column in lineage_dataframe.columns
        }

    return lookup


# ============================================================================
# FEATURE FAMILY CLASSIFICATION
# ============================================================================


def normalize_feature_name(
    feature: str,
) -> str:

    return (
        feature
        .strip()
        .lower()
    )


def is_current_state_feature(
    feature: str,
) -> bool:

    normalized = normalize_feature_name(
        feature
    )

    if normalized in CURRENT_STATE_FEATURE_NAMES:

        return True

    return any(
        token in normalized
        for token in CURRENT_STATE_TOKENS
    )


def is_historical_feature(
    feature: str,
) -> bool:

    normalized = normalize_feature_name(
        feature
    )

    return any(
        token in normalized
        for token in HISTORICAL_TOKENS
    )


def is_temporal_feature(
    feature: str,
) -> bool:

    normalized = normalize_feature_name(
        feature
    )

    return any(
        token in normalized
        for token in TEMPORAL_TOKENS
    )


def classify_feature_family(
    feature: str,
) -> str:

    if is_current_state_feature(
        feature
    ):

        return "current_state"

    if is_historical_feature(
        feature
    ):

        return "historical"

    if is_temporal_feature(
        feature
    ):

        return "temporal_calendar"

    return "other"


# ============================================================================
# SOURCE FEATURE MATCHING
# ============================================================================


def feature_name_tokens(
    feature: str,
) -> set[str]:

    return {
        token
        for token in re.split(
            r"[^a-zA-Z0-9]+",
            feature.lower(),
        )
        if token
    }


def source_line_matches_feature(
    feature: str,
    line: str,
) -> bool:

    normalized_feature = (
        feature.lower()
    )

    normalized_line = (
        line.lower()
    )

    if normalized_feature in normalized_line:

        return True

    tokens = feature_name_tokens(
        feature
    )

    if not tokens:

        return False

    meaningful_tokens = {
        token
        for token in tokens
        if len(token) >= 4
    }

    if not meaningful_tokens:

        return False

    matches = sum(
        1
        for token
        in meaningful_tokens
        if token in normalized_line
    )

    return matches >= max(
        1,
        min(
            2,
            len(meaningful_tokens),
        ),
    )


def find_feature_source_evidence(
    feature: str,
    source: dict[str, list[str]],
) -> list[tuple[str, int, str]]:

    evidence = []

    for relative_path, lines in source.items():

        for line_number, line in enumerate(
            lines,
            start=1,
        ):

            if source_line_matches_feature(
                feature,
                line,
            ):

                evidence.append(
                    (
                        relative_path,
                        line_number,
                        line.strip(),
                    )
                )

    return evidence


# ============================================================================
# TEMPORAL EVIDENCE AGGREGATION
# ============================================================================


def source_evidence_has_negative_shift(
    evidence: list[tuple[str, int, str]],
) -> bool:

    return any(
        NEGATIVE_SHIFT_PATTERN.search(
            expression
        )
        for _, _, expression
        in evidence
    )


def source_evidence_has_centered_rolling(
    evidence: list[tuple[str, int, str]],
) -> bool:

    return any(
        CENTERED_ROLLING_PATTERN.search(
            expression
        )
        for _, _, expression
        in evidence
    )


def source_evidence_has_shift(
    evidence: list[tuple[str, int, str]],
) -> bool:

    return any(
        re.search(
            r"\.shift\s*\(",
            expression,
            re.IGNORECASE,
        )
        for _, _, expression
        in evidence
    )


def source_evidence_has_rolling(
    evidence: list[tuple[str, int, str]],
) -> bool:

    return any(
        re.search(
            r"\.rolling\s*\(",
            expression,
            re.IGNORECASE,
        )
        for _, _, expression
        in evidence
    )


def source_evidence_has_diff(
    evidence: list[tuple[str, int, str]],
) -> bool:

    return any(
        re.search(
            r"\.diff\s*\(",
            expression,
            re.IGNORECASE,
        )
        for _, _, expression
        in evidence
    )


def source_evidence_has_pct_change(
    evidence: list[tuple[str, int, str]],
) -> bool:

    return any(
        re.search(
            r"\.pct_change\s*\(",
            expression,
            re.IGNORECASE,
        )
        for _, _, expression
        in evidence
    )


def source_evidence_has_forward_operation(
    evidence: list[tuple[str, int, str]],
) -> bool:

    return any(
        pattern.search(expression)
        for _, _, expression
        in evidence
        for pattern
        in FORWARD_OPERATION_PATTERNS
    )


def source_evidence_target_context(
    evidence: list[tuple[str, int, str]],
) -> bool:

    return any(
        line_has_target_context(
            expression
        )
        for _, _, expression
        in evidence
    )


# ============================================================================
# CAUSAL DECISION ENGINE
# ============================================================================


def determine_source_cutoff(
    contract: FeatureCausalContract,
) -> str:

    if contract.potential_leakage:

        return (
            "FUTURE_INFORMATION_DETECTED"
        )

    if contract.has_negative_shift:

        return (
            "AFTER_T"
        )

    if contract.has_centered_rolling:

        return (
            "UNKNOWN_CENTERED_WINDOW"
        )

    if contract.current_state_feature:

        return "T"

    if contract.has_positive_shift:

        return "T_MINUS_HISTORY"

    if (
        contract.has_shift_operation
        and not contract.has_negative_shift
    ):

        return "HISTORICAL_OR_CURRENT"

    if (
        contract.has_rolling_operation
        and not contract.has_centered_rolling
    ):

        return (
            "TRAILING_WINDOW_REQUIRES_SOURCE_VERIFICATION"
        )

    if contract.temporal_feature:

        return "T"

    if contract.feature_family == "other":

        return "UNKNOWN"

    return "UNKNOWN"


def determine_causal_verdict(
    contract: FeatureCausalContract,
) -> tuple[str, str, str]:

    # ------------------------------------------------------------
    # Hard leakage gates.
    # ------------------------------------------------------------

    if contract.has_negative_shift:

        return (
            "POTENTIAL_TEMPORAL_LEAKAGE",
            "HIGH",
            (
                "Feature-specific source evidence contains "
                "a negative shift, which can reference future "
                "observations relative to T."
            ),
        )

    if contract.has_centered_rolling:

        return (
            "POTENTIAL_TEMPORAL_LEAKAGE",
            "HIGH",
            (
                "Feature-specific source evidence contains "
                "centered rolling, which may include observations "
                "after prediction timestamp T."
            ),
        )

    if contract.has_forward_operation:

        if not contract.target_context:

            return (
                "POTENTIAL_TEMPORAL_LEAKAGE",
                "HIGH",
                (
                    "Forward-looking source operation was detected "
                    "outside clearly identified target-generation "
                    "context."
                ),
            )

    # ------------------------------------------------------------
    # Current-state features.
    # ------------------------------------------------------------

    if contract.current_state_feature:

        if contract.source_evidence_count == 0:

            return (
                "PRODUCTION_SAFE_REALTIME_CONTRACT",
                "LOW",
                (
                    "Feature appears to represent current state, "
                    "but no direct source expression was identified. "
                    "Production use requires a realtime source and "
                    "freshness contract."
                ),
            )

        return (
            "PRODUCTION_SAFE_REALTIME_CONTRACT",
            "MEDIUM",
            (
                "Feature is classified as current-state information. "
                "It is causally compatible with T if the production "
                "system supplies the current value at or before T. "
                "A realtime source/freshness SLA is required."
            ),
        )

    # ------------------------------------------------------------
    # Deterministic temporal/calendar features.
    # ------------------------------------------------------------

    if contract.temporal_feature:

        return (
            "PRODUCTION_SAFE",
            "MEDIUM",
            (
                "Feature is derived from the prediction timestamp "
                "or deterministic calendar information and therefore "
                "does not require future observations."
            ),
        )

    # ------------------------------------------------------------
    # Historical features.
    # ------------------------------------------------------------

    if contract.historical_feature:

        if contract.has_positive_shift:

            return (
                "PRODUCTION_SAFE",
                "HIGH",
                (
                    "Feature-specific source evidence indicates "
                    "a positive historical shift. The operation "
                    "references prior observations rather than "
                    "future observations."
                ),
            )

        if (
            contract.has_shift_operation
            and not contract.has_negative_shift
        ):

            return (
                "REQUIRES_CAUSAL_REVIEW",
                "MEDIUM",
                (
                    "Historical shift evidence exists, but the "
                    "available static evidence does not establish "
                    "the exact source timestamp cutoff."
                ),
            )

        if contract.has_rolling_operation:

            return (
                "REQUIRES_CAUSAL_REVIEW",
                "MEDIUM",
                (
                    "Rolling feature detected. The source does not "
                    "formally prove that the rolling window is "
                    "strictly trailing and available by T."
                ),
            )

        if (
            contract.has_diff_operation
            or contract.has_pct_change_operation
        ):

            return (
                "REQUIRES_CAUSAL_REVIEW",
                "MEDIUM",
                (
                    "Historical change operation detected. "
                    "Source-level timestamp semantics require "
                    "verification."
                ),
            )

        return (
            "REQUIRES_CAUSAL_REVIEW",
            "LOW",
            (
                "Feature appears historical by naming/family, "
                "but source-level evidence does not formally "
                "establish the information cutoff."
            ),
        )

    # ------------------------------------------------------------
    # Other features with source evidence.
    # ------------------------------------------------------------

    if contract.source_evidence_count > 0:

        if contract.target_context:

            return (
                "REQUIRES_CAUSAL_REVIEW",
                "LOW",
                (
                    "Source evidence intersects target-generation "
                    "context. No leakage was automatically confirmed, "
                    "but feature-specific causal separation requires "
                    "review."
                ),
            )

        return (
            "REQUIRES_CAUSAL_REVIEW",
            "LOW",
            (
                "Source evidence exists, but the static audit cannot "
                "establish the exact information availability cutoff."
            ),
        )

    # ------------------------------------------------------------
    # No evidence.
    # ------------------------------------------------------------

    return (
        "INSUFFICIENT_SOURCE_EVIDENCE",
        "LOW",
        (
            "No sufficiently reliable feature-specific source "
            "evidence was identified. Production approval cannot "
            "be established from the persisted feature alone."
        ),
    )


# ============================================================================
# FEATURE CONTRACT BUILDING
# ============================================================================


def build_feature_contract(
    feature: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    lineage_lookup: dict[str, dict[str, Any]],
    source: dict[str, list[str]],
) -> FeatureCausalContract:

    family = classify_feature_family(
        feature
    )

    evidence = find_feature_source_evidence(
        feature,
        source,
    )

    source_files = sorted(
        {
            item[0]
            for item in evidence
        }
    )

    source_lines = sorted(
        {
            int(item[1])
            for item in evidence
        }
    )

    source_expressions = [
        item[2]
        for item in evidence
    ]

    lineage = lineage_lookup.get(
        feature,
        {},
    )

    lineage_evidence = " | ".join(
        str(value)
        for key, value
        in lineage.items()
        if key.lower()
        not in {
            "feature",
            "feature_name",
            "column",
        }
        and str(value).strip()
        not in {
            "",
            "nan",
            "None",
        }
    )[:4000]

    contract = FeatureCausalContract(
        feature=feature,
        feature_family=family,

        training_dtype=str(
            train[feature].dtype
        ),

        validation_dtype=str(
            validation[feature].dtype
        ),

        source_evidence_count=len(
            evidence
        ),

        source_files=source_files,

        source_lines=source_lines,

        source_expressions=source_expressions[:100],

        lineage_evidence=lineage_evidence,

        has_shift_operation=(
            source_evidence_has_shift(
                evidence
            )
        ),

        has_positive_shift=(
            bool(
                POSITIVE_SHIFT_PATTERN.search(
                    "\n".join(
                        item[2]
                        for item in evidence
                    )
                )
            )
        ),

        has_negative_shift=(
            source_evidence_has_negative_shift(
                evidence
            )
        ),

        has_rolling_operation=(
            source_evidence_has_rolling(
                evidence
            )
        ),

        has_centered_rolling=(
            source_evidence_has_centered_rolling(
                evidence
            )
        ),

        has_diff_operation=(
            source_evidence_has_diff(
                evidence
            )
        ),

        has_pct_change_operation=(
            source_evidence_has_pct_change(
                evidence
            )
        ),

        has_forward_operation=(
            source_evidence_has_forward_operation(
                evidence
            )
        ),

        target_context=(
            source_evidence_target_context(
                evidence
            )
        ),

        feature_context=any(
            line_has_feature_context(
                item[2]
            )
            for item in evidence
        ),

        current_state_feature=(
            family == "current_state"
        ),

        historical_feature=(
            family == "historical"
        ),

        temporal_feature=(
            family == "temporal_calendar"
        ),
    )

    contract.potential_leakage = (
        contract.has_negative_shift
        or contract.has_centered_rolling
        or (
            contract.has_forward_operation
            and not contract.target_context
        )
    )

    contract.requires_realtime_contract = (
        contract.current_state_feature
    )

    contract.source_information_cutoff = (
        determine_source_cutoff(
            contract
        )
    )

    (
        contract.verdict,
        contract.confidence,
        contract.causal_reason,
    ) = determine_causal_verdict(
        contract
    )

    contract.requires_causal_review = (
        contract.verdict
        in {
            "REQUIRES_CAUSAL_REVIEW",
            "INSUFFICIENT_SOURCE_EVIDENCE",
            "PRODUCTION_SAFE_REALTIME_CONTRACT",
        }
    )

    return contract


# ============================================================================
# AST FEATURE-SPECIFIC CROSS CHECK
# ============================================================================


def build_ast_summary(
    ast_findings: list[dict[str, Any]],
) -> dict[str, Any]:

    return {
        "total": len(
            ast_findings
        ),

        "negative_shift": sum(
            1
            for finding
            in ast_findings
            if finding.get(
                "negative",
                False,
            )
        ),

        "centered_rolling": sum(
            1
            for finding
            in ast_findings
            if finding.get(
                "centered",
                False,
            )
        ),

        "shift": sum(
            1
            for finding
            in ast_findings
            if finding.get(
                "operation"
            ) == "SHIFT"
        ),

        "rolling": sum(
            1
            for finding
            in ast_findings
            if finding.get(
                "operation"
            ) == "ROLLING"
        ),
    }


# ============================================================================
# SUMMARY
# ============================================================================


def build_summary(
    contracts: list[FeatureCausalContract],
    source_findings: list[SourceFinding],
    ast_findings: list[dict[str, Any]],
) -> dict[str, Any]:

    verdict_counts = Counter(
        contract.verdict
        for contract in contracts
    )

    family_counts = Counter(
        contract.feature_family
        for contract in contracts
    )

    return {
        "features_audited": len(
            contracts
        ),

        "expected_features": (
            EXPECTED_FEATURE_COUNT
        ),

        "family_counts": dict(
            family_counts
        ),

        "verdict_counts": dict(
            verdict_counts
        ),

        "source_evidence_features": sum(
            1
            for contract
            in contracts
            if contract.source_evidence_count > 0
        ),

        "features_without_source_evidence": sum(
            1
            for contract
            in contracts
            if contract.source_evidence_count == 0
        ),

        "negative_shift_features": sum(
            1
            for contract
            in contracts
            if contract.has_negative_shift
        ),

        "centered_rolling_features": sum(
            1
            for contract
            in contracts
            if contract.has_centered_rolling
        ),

        "forward_operation_features": sum(
            1
            for contract
            in contracts
            if contract.has_forward_operation
            and not contract.target_context
        ),

        "potential_leakage_features": sum(
            1
            for contract
            in contracts
            if contract.potential_leakage
        ),

        "realtime_contract_features": sum(
            1
            for contract
            in contracts
            if contract.requires_realtime_contract
        ),

        "causal_review_features": sum(
            1
            for contract
            in contracts
            if contract.requires_causal_review
        ),

        "source_findings": len(
            source_findings
        ),

        "ast_findings": len(
            ast_findings
        ),

        "target_context_source_findings": sum(
            1
            for finding
            in source_findings
            if finding.target_context
        ),

        "feature_context_source_findings": sum(
            1
            for finding
            in source_findings
            if finding.feature_context
        ),

        "future_source_findings": sum(
            1
            for finding
            in source_findings
            if finding.future_or_forward
            or finding.negative_shift
            or finding.centered_rolling
        ),
    }


# ============================================================================
# VERDICT
# ============================================================================


def determine_overall_verdict(
    summary: dict[str, Any],
) -> tuple[str, list[str]]:

    reasons: list[str] = []

    leakage = summary[
        "potential_leakage_features"
    ]

    realtime = summary[
        "realtime_contract_features"
    ]

    review = summary[
        "causal_review_features"
    ]

    insufficient = summary[
        "features_without_source_evidence"
    ]

    if leakage > 0:

        reasons.append(
            f"{leakage} feature(s) contain potential "
            "future-looking operations."
        )

        return (
            "FAIL_POTENTIAL_TEMPORAL_LEAKAGE",
            reasons,
        )

    if realtime > 0:

        reasons.append(
            f"{realtime} current-state feature(s) require "
            "a production realtime source/freshness contract."
        )

    if insufficient > 0:

        reasons.append(
            f"{insufficient} feature(s) do not have sufficient "
            "feature-specific source evidence."
        )

    if review > 0:

        reasons.append(
            f"{review} feature(s) remain conditional because "
            "static source analysis does not formally prove "
            "their causal cutoff."
        )

    if not reasons:

        reasons.append(
            "All audited features satisfied the implemented "
            "static causal verification rules."
        )

        return (
            "PRODUCTION_CAUSALITY_APPROVED",
            reasons,
        )

    return (
        "PASS_WITH_CAUSAL_REVIEW",
        reasons,
    )


# ============================================================================
# PERSISTENCE
# ============================================================================


def json_safe(
    value: Any,
) -> Any:

    if isinstance(
        value,
        Path,
    ):

        return str(value)

    if isinstance(
        value,
        np.integer,
    ):

        return int(value)

    if isinstance(
        value,
        np.floating,
    ):

        return float(value)

    if isinstance(
        value,
        np.bool_,
    ):

        return bool(value)

    if isinstance(
        value,
        dict,
    ):

        return {
            str(key): json_safe(
                item
            )
            for key, item
            in value.items()
        }

    if isinstance(
        value,
        (list, tuple),
    ):

        return [
            json_safe(item)
            for item in value
        ]

    return value


def persist_json(
    path: Path,
    payload: dict[str, Any],
) -> None:

    with path.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            json_safe(payload),
            handle,
            indent=2,
            ensure_ascii=False,
        )


def persist_feature_csv(
    path: Path,
    contracts: list[FeatureCausalContract],
) -> None:

    rows = []

    for contract in contracts:

        row = asdict(
            contract
        )

        row["source_files"] = (
            " | ".join(
                contract.source_files
            )
        )

        row["source_lines"] = (
            " | ".join(
                str(line)
                for line
                in contract.source_lines
            )
        )

        row["source_expressions"] = (
            " || ".join(
                contract.source_expressions
            )
        )

        rows.append(
            row
        )

    if not rows:

        return

    fieldnames = list(
        rows[0].keys()
    )

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        for row in rows:

            writer.writerow(
                {
                    field: row.get(
                        field,
                        "",
                    )
                    for field in fieldnames
                }
            )


def persist_source_findings_csv(
    path: Path,
    findings: list[SourceFinding],
) -> None:

    fieldnames = [
        "file",
        "line_number",
        "operation",
        "context",
        "target_context",
        "feature_context",
        "future_or_forward",
        "negative_shift",
        "centered_rolling",
        "expression",
    ]

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        for finding in findings:

            row = asdict(
                finding
            )

            writer.writerow(
                {
                    field: row.get(
                        field,
                        "",
                    )
                    for field in fieldnames
                }
            )


def persist_summary_csv(
    path: Path,
    summary: dict[str, Any],
    verdict: str,
) -> None:

    rows = []

    for key, value in summary.items():

        if isinstance(
            value,
            dict,
        ):

            for nested_key, nested_value in (
                value.items()
            ):

                rows.append(
                    {
                        "metric": (
                            f"{key}.{nested_key}"
                        ),
                        "value": (
                            nested_value
                        ),
                    }
                )

        else:

            rows.append(
                {
                    "metric": key,
                    "value": value,
                }
            )

    rows.append(
        {
            "metric": "overall_verdict",
            "value": verdict,
        }
    )

    fieldnames = [
        "metric",
        "value",
    ]

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        writer.writerows(
            rows
        )


def persist_ast_csv(
    path: Path,
    findings: list[dict[str, Any]],
) -> None:

    fieldnames = [
        "file",
        "line",
        "operation",
        "negative",
        "positive",
        "centered",
    ]

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:

        writer = csv.DictWriter(
            handle,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()

        for finding in findings:

            writer.writerow(
                {
                    field: finding.get(
                        field,
                        "",
                    )
                    for field in fieldnames
                }
            )


# ============================================================================
# ASSERTIONS
# ============================================================================


def run_final_assertions(
    contracts: list[FeatureCausalContract],
    manifest_features: list[str],
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    print_section(
        "FINAL ASSERTIONS"
    )

    if train.empty:

        raise CausalVerificationContractError(
            "Training dataset is empty."
        )

    print_pass(
        "Training dataset non-empty"
    )

    if validation.empty:

        raise CausalVerificationContractError(
            "Validation dataset is empty."
        )

    print_pass(
        "Validation dataset non-empty"
    )

    if len(
        manifest_features
    ) != EXPECTED_FEATURE_COUNT:

        raise CausalVerificationContractError(
            "Unexpected registered feature count: "
            f"{len(manifest_features)}; "
            f"expected {EXPECTED_FEATURE_COUNT}."
        )

    print_pass(
        "Expected feature count"
    )

    if len(
        contracts
    ) != len(
        manifest_features
    ):

        raise CausalVerificationContractError(
            "Causal contract row count does not equal "
            "registered feature count."
        )

    print_pass(
        "Causal contract row count equals feature count"
    )

    contract_features = [
        contract.feature
        for contract in contracts
    ]

    if len(
        contract_features
    ) != len(
        set(contract_features)
    ):

        raise CausalVerificationContractError(
            "Duplicate audited feature names detected."
        )

    print_pass(
        "No duplicate audited features"
    )

    if set(
        contract_features
    ) != set(
        manifest_features
    ):

        raise CausalVerificationContractError(
            "Audited feature registry does not match manifest."
        )

    print_pass(
        "All audited features present"
    )

    if TARGET_COLUMN in set(
        manifest_features
    ):

        raise CausalVerificationContractError(
            "Target column is included as a model feature."
        )

    print_pass(
        "Target not included as registered feature"
    )

    # Test is deliberately checked only for existence.
    # It is never read.
    print_pass(
        "Test dataset was not loaded"
    )

    print_pass(
        "No persisted dataset modification performed"
    )


# ============================================================================
# CONSOLE REPORT
# ============================================================================


def print_feature_summary(
    summary: dict[str, Any],
) -> None:

    print_section(
        "FEATURE CAUSAL VERIFICATION SUMMARY"
    )

    family_counts = summary[
        "family_counts"
    ]

    verdict_counts = summary[
        "verdict_counts"
    ]

    print_status(
        "Features audited",
        summary[
            "features_audited"
        ],
    )

    print_status(
        "Features with source evidence",
        summary[
            "source_evidence_features"
        ],
    )

    print_status(
        "Features without source evidence",
        summary[
            "features_without_source_evidence"
        ],
    )

    print()

    print(
        "Feature families:"
    )

    for family, count in (
        sorted(
            family_counts.items()
        )
    ):

        print_status(
            f"  {family}",
            count,
            width=44,
        )

    print()

    print(
        "Causal verdicts:"
    )

    for verdict, count in (
        sorted(
            verdict_counts.items()
        )
    ):

        print_status(
            f"  {verdict}",
            count,
            width=44,
        )

    print()

    print_status(
        "Negative-shift features",
        summary[
            "negative_shift_features"
        ],
    )

    print_status(
        "Centered-rolling features",
        summary[
            "centered_rolling_features"
        ],
    )

    print_status(
        "Forward-operation features",
        summary[
            "forward_operation_features"
        ],
    )

    print_status(
        "Potential leakage features",
        summary[
            "potential_leakage_features"
        ],
    )

    print_status(
        "Realtime-contract features",
        summary[
            "realtime_contract_features"
        ],
    )

    print_status(
        "Features requiring causal review",
        summary[
            "causal_review_features"
        ],
    )


def print_review_features(
    contracts: list[FeatureCausalContract],
) -> None:

    review = [
        contract
        for contract in contracts
        if contract.verdict
        in {
            "POTENTIAL_TEMPORAL_LEAKAGE",
            "REQUIRES_CAUSAL_REVIEW",
            "INSUFFICIENT_SOURCE_EVIDENCE",
        }
    ]

    print_section(
        "FEATURES REQUIRING REVIEW"
    )

    if not review:

        print(
            "No feature requires causal review."
        )

        return

    grouped = defaultdict(
        list
    )

    for contract in review:

        grouped[
            contract.verdict
        ].append(
            contract
        )

    for verdict in sorted(
        grouped
    ):

        print()
        print(
            f"{verdict}: "
            f"{len(grouped[verdict])}"
        )

        for contract in (
            grouped[verdict][:40]
        ):

            print(
                f"  - {contract.feature}"
            )

        if len(
            grouped[verdict]
        ) > 40:

            print(
                "  ..."
                f" {len(grouped[verdict]) - 40}"
                " additional feature(s) in CSV report."
            )


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:

    print_header(
        "SMARTPARK AI - BIRMINGHAM XGBOOST "
        "FEATURE CAUSAL VERIFICATION AUDIT"
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
        "  Verify each registered feature individually"
    )

    print(
        "  Use existing feature-lineage artifacts"
    )

    print(
        "  Inspect actual ML source code"
    )

    print(
        "  Distinguish target-generation future logic"
        " from feature-generation future logic"
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

        # --------------------------------------------------------
        # Paths
        # --------------------------------------------------------

        paths = resolve_paths()

        print_section(
            "DATASET FILE VALIDATION"
        )

        print_status(
            "Repository root",
            paths[
                "repository_root"
            ],
        )

        print_status(
            "Training dataset",
            paths[
                "train"
            ],
        )

        print_status(
            "Validation dataset",
            paths[
                "validation"
            ],
        )

        print_status(
            "Test dataset",
            paths[
                "test"
            ],
        )

        print_status(
            "Feature manifest",
            paths[
                "manifest"
            ],
        )

        print_status(
            "Existing lineage feature CSV",
            paths[
                "lineage_features"
            ],
        )

        print_status(
            "Existing lineage source CSV",
            paths[
                "lineage_source"
            ],
        )

        validate_required_files(
            paths
        )

        print_pass(
            "Training file exists"
        )

        print_pass(
            "Validation file exists"
        )

        print_pass(
            "Test file exists"
        )

        print_pass(
            "Manifest exists"
        )

        print_pass(
            "Lineage feature artifact exists"
        )

        print_pass(
            "Lineage source artifact exists"
        )

        print()
        print(
            "Test dataset exists but will NOT be loaded."
        )

        # --------------------------------------------------------
        # Manifest
        # --------------------------------------------------------

        print_section(
            "LOADING FEATURE MANIFEST"
        )

        manifest = load_manifest(
            paths[
                "manifest"
            ]
        )

        manifest_features = (
            extract_manifest_features(
                manifest
            )
        )

        print_status(
            "Registered features",
            len(manifest_features),
        )

        # --------------------------------------------------------
        # Persisted data
        # --------------------------------------------------------

        train, validation = (
            load_training_validation(
                paths
            )
        )

        # --------------------------------------------------------
        # Feature registry
        # --------------------------------------------------------

        validate_feature_registry(
            train,
            validation,
            manifest_features,
        )

        # --------------------------------------------------------
        # Target
        # --------------------------------------------------------

        target_contract = (
            validate_target_contract(
                train,
                validation,
            )
        )

        # --------------------------------------------------------
        # Existing lineage artifacts
        # --------------------------------------------------------

        print_section(
            "LOADING EXISTING FEATURE-LINEAGE ARTIFACTS"
        )

        lineage_dataframe = load_csv(
            paths[
                "lineage_features"
            ]
        )

        source_dataframe = load_csv(
            paths[
                "lineage_source"
            ]
        )

        print_status(
            "Lineage feature rows",
            len(lineage_dataframe),
        )

        print_status(
            "Lineage source findings",
            len(source_dataframe),
        )

        lineage_lookup = (
            build_lineage_lookup(
                lineage_dataframe
            )
        )

        # --------------------------------------------------------
        # Source discovery
        # --------------------------------------------------------

        print_section(
            "ML SOURCE CODE DISCOVERY"
        )

        source_files = (
            discover_source_files(
                paths[
                    "source_root"
                ]
            )
        )

        print_status(
            "ML source root",
            paths[
                "source_root"
            ],
        )

        print_status(
            "ML source files scanned",
            len(source_files),
        )

        source = read_source_files(
            source_files,
            paths[
                "source_root"
            ],
        )

        # --------------------------------------------------------
        # Source temporal operations
        # --------------------------------------------------------

        print_section(
            "SOURCE TEMPORAL ANALYSIS"
        )

        source_findings = (
            scan_source_temporal_operations(
                source
            )
        )

        print_status(
            "Source temporal findings",
            len(source_findings),
        )

        operation_counts = Counter(
            finding.operation
            for finding in source_findings
        )

        for operation, count in (
            sorted(
                operation_counts.items()
            )
        ):

            print_status(
                f"  {operation}",
                count,
            )

        print_status(
            "Target-context findings",
            sum(
                1
                for finding
                in source_findings
                if finding.target_context
            ),
        )

        print_status(
            "Feature-context findings",
            sum(
                1
                for finding
                in source_findings
                if finding.feature_context
            ),
        )

        print_status(
            "Future-oriented source findings",
            sum(
                1
                for finding
                in source_findings
                if finding.future_or_forward
                or finding.negative_shift
                or finding.centered_rolling
            ),
        )

        # --------------------------------------------------------
        # AST
        # --------------------------------------------------------

        print_section(
            "AST TEMPORAL CROSS-CHECK"
        )

        ast_findings = run_ast_analysis(
            source_files,
            paths[
                "source_root"
            ],
        )

        ast_summary = build_ast_summary(
            ast_findings
        )

        print_status(
            "AST temporal findings",
            ast_summary[
                "total"
            ],
        )

        print_status(
            "AST shift findings",
            ast_summary[
                "shift"
            ],
        )

        print_status(
            "AST rolling findings",
            ast_summary[
                "rolling"
            ],
        )

        print_status(
            "AST negative shifts",
            ast_summary[
                "negative_shift"
            ],
        )

        print_status(
            "AST centered rolling",
            ast_summary[
                "centered_rolling"
            ],
        )

        # --------------------------------------------------------
        # Feature contracts
        # --------------------------------------------------------

        print_section(
            "BUILDING FEATURE-LEVEL CAUSAL CONTRACT"
        )

        contracts = []

        for feature in manifest_features:

            contract = build_feature_contract(
                feature=feature,
                train=train,
                validation=validation,
                lineage_lookup=lineage_lookup,
                source=source,
            )

            contracts.append(
                contract
            )

        print_status(
            "Feature contracts built",
            len(contracts),
        )

        # --------------------------------------------------------
        # Summary
        # --------------------------------------------------------

        summary = build_summary(
            contracts,
            source_findings,
            ast_findings,
        )

        print_feature_summary(
            summary
        )

        # --------------------------------------------------------
        # Overall verdict
        # --------------------------------------------------------

        verdict, reasons = (
            determine_overall_verdict(
                summary
            )
        )

        print_section(
            "FINAL FEATURE CAUSAL VERIFICATION RESULT"
        )

        print_status(
            "Features audited",
            summary[
                "features_audited"
            ],
        )

        print_status(
            "Historical features",
            summary[
                "family_counts"
            ].get(
                "historical",
                0,
            ),
        )

        print_status(
            "Current-state features",
            summary[
                "family_counts"
            ].get(
                "current_state",
                0,
            ),
        )

        print_status(
            "Temporal/calendar features",
            summary[
                "family_counts"
            ].get(
                "temporal_calendar",
                0,
            ),
        )

        print_status(
            "Other features",
            summary[
                "family_counts"
            ].get(
                "other",
                0,
            ),
        )

        print_status(
            "Potential leakage features",
            summary[
                "potential_leakage_features"
            ],
        )

        print_status(
            "Features requiring causal review",
            summary[
                "causal_review_features"
            ],
        )

        print()

        print(
            f"PRODUCTION FEATURE CAUSAL VERDICT : "
            f"{verdict}"
        )

        print()

        print(
            "Verdict reasons:"
        )

        for reason in reasons:

            print(
                f"  - {reason}"
            )

        print_review_features(
            contracts
        )

        # --------------------------------------------------------
        # Assertions
        # --------------------------------------------------------

        run_final_assertions(
            contracts=contracts,
            manifest_features=manifest_features,
            train=train,
            validation=validation,
        )

        # --------------------------------------------------------
        # Persistence
        # --------------------------------------------------------

        print_section(
            "PERSISTING CAUSAL VERIFICATION RESULTS"
        )

        output_directory = (
            paths[
                "output"
            ]
        )

        output_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        generated_at = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

        json_report = (
            output_directory
            / (
                "birmingham_xgboost_feature_"
                "causal_verification.json"
            )
        )

        feature_csv = (
            output_directory
            / (
                "birmingham_xgboost_feature_"
                "causal_verification_features.csv"
            )
        )

        source_csv = (
            output_directory
            / (
                "birmingham_xgboost_feature_"
                "causal_verification_source_findings.csv"
            )
        )

        summary_csv = (
            output_directory
            / (
                "birmingham_xgboost_feature_"
                "causal_verification_summary.csv"
            )
        )

        ast_csv = (
            output_directory
            / (
                "birmingham_xgboost_feature_"
                "causal_verification_ast_findings.csv"
            )
        )

        report = {
            "project": PROJECT_NAME,
            "audit": (
                "Birmingham XGBoost "
                "Feature Causal Verification"
            ),
            "generated_at": generated_at,
            "target": TARGET_COLUMN,
            "prediction_timestamp": "T",
            "forecast_horizon_minutes": (
                FORECAST_HORIZON_MINUTES
            ),
            "test_dataset_loaded": False,
            "xgboost_training_performed": False,
            "feature_pipeline_rebuilt": False,
            "persisted_datasets_modified": False,
            "repository_root": str(
                paths[
                    "repository_root"
                ]
            ),
            "training_dataset": str(
                paths[
                    "train"
                ]
            ),
            "validation_dataset": str(
                paths[
                    "validation"
                ]
            ),
            "test_dataset": str(
                paths[
                    "test"
                ]
            ),
            "manifest": str(
                paths[
                    "manifest"
                ]
            ),
            "lineage_feature_artifact": str(
                paths[
                    "lineage_features"
                ]
            ),
            "lineage_source_artifact": str(
                paths[
                    "lineage_source"
                ]
            ),
            "target_contract": (
                target_contract
            ),
            "source_files_scanned": len(
                source_files
            ),
            "source_temporal_findings": len(
                source_findings
            ),
            "ast_summary": ast_summary,
            "summary": summary,
            "overall_verdict": verdict,
            "verdict_reasons": reasons,
            "feature_contracts": [
                asdict(
                    contract
                )
                for contract
                in contracts
            ],
        }

        persist_json(
            json_report,
            report,
        )

        persist_feature_csv(
            feature_csv,
            contracts,
        )

        persist_source_findings_csv(
            source_csv,
            source_findings,
        )

        persist_summary_csv(
            summary_csv,
            summary,
            verdict,
        )

        persist_ast_csv(
            ast_csv,
            ast_findings,
        )

        print_status(
            "Output directory",
            output_directory,
        )

        print_status(
            "JSON report",
            json_report,
        )

        print_status(
            "CSV feature contract",
            feature_csv,
        )

        print_status(
            "CSV source findings",
            source_csv,
        )

        print_status(
            "CSV summary",
            summary_csv,
        )

        print_status(
            "CSV AST findings",
            ast_csv,
        )

        # --------------------------------------------------------
        # Final message
        # --------------------------------------------------------

        print_header(
            "BIRMINGHAM FEATURE CAUSAL VERIFICATION "
            "AUDIT COMPLETED"
        )

        if verdict == (
            "PRODUCTION_CAUSALITY_APPROVED"
        ):

            print(
                "All registered features satisfied the "
                "implemented static causal verification rules."
            )

        elif verdict == (
            "FAIL_POTENTIAL_TEMPORAL_LEAKAGE"
        ):

            print(
                "Potential temporal leakage was identified."
            )

        else:

            print(
                "No feature was automatically confirmed as "
                "future leakage."
            )

            print(
                "Features without formal causal proof remain "
                "conditional for production approval."
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
            "Feature causal verification is ready for "
            "engineering review."
        )

        return 0

    except CausalVerificationError as exc:

        print_header(
            "BIRMINGHAM FEATURE CAUSAL VERIFICATION "
            "AUDIT FAILED"
        )

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

        print_header(
            "BIRMINGHAM FEATURE CAUSAL VERIFICATION "
            "AUDIT FAILED"
        )

        print()
        print(
            f"UNEXPECTED ERROR: "
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


# ============================================================================
# ENTRY POINT
# ============================================================================


if __name__ == "__main__":
    sys.exit(
        main()
    )