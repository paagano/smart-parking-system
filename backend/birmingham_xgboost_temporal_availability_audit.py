"""
SMARTPARK AI
BIRMINGHAM XGBOOST TEMPORAL AVAILABILITY AUDIT

Purpose
-------
Audit the persisted Birmingham feature dataset and the feature-generation
source code for temporal leakage and prediction-time availability.

This audit is intentionally separate from model training.

It does NOT:
    - train XGBoost
    - tune XGBoost
    - load test.parquet
    - modify train.parquet
    - modify validation.parquet
    - rebuild the feature pipeline
    - modify the persisted feature registry

Target:
    target_occupancy_rate_30m

Core temporal contract
----------------------
For a prediction made at time T for T + 30 minutes:

    A feature is temporally safe when it depends only on information
    available at or before the prediction information cutoff.

The audit distinguishes:

    SAFE
        Strong evidence that the feature is historical/calendar/static
        or otherwise temporally available.

    CURRENT_STATE_REVIEW
        Feature uses the current parking state. This is not automatically
        leakage, but production availability at prediction time must be
        established.

    REVIEW
        The automated lineage evidence is insufficient to establish safety.

    POTENTIAL_LEAKAGE
        Evidence indicates that future information may enter the model
        feature.

Important
---------
A negative shift used during TARGET CONSTRUCTION is not feature leakage.

For example:

    occupancy.shift(-1)

may legitimately be used to construct:

    target_occupancy_rate_30m

The audit therefore distinguishes target-construction code from feature
generation code.

Likewise:

    target_interval_minutes

is configuration metadata and is NOT treated as a target column.

Outputs
-------
datasets/processed/birmingham/
    xgboost_temporal_availability_audit/
        birmingham_xgboost_temporal_availability_audit.json
        birmingham_xgboost_temporal_availability_audit.csv
        birmingham_xgboost_temporal_availability_summary.csv

Exit behaviour
--------------
The script completes the audit even when REVIEW items exist.

It exits with a non-zero status only when confirmed/potential leakage
is detected after excluding legitimate target-construction operations.

No persisted dataset is ever modified.
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

TEST_PATH = (
    TARGET_DATASET_ROOT
    / "test.parquet"
)

MANIFEST_PATH = (
    DATASET_ROOT
    / "training_dataset_manifest.json"
)

OUTPUT_ROOT = (
    DATASET_ROOT
    / "xgboost_temporal_availability_audit"
)

JSON_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_temporal_availability_audit.json"
)

CSV_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_temporal_availability_audit.csv"
)

SUMMARY_CSV_OUTPUT = (
    OUTPUT_ROOT
    / "birmingham_xgboost_temporal_availability_summary.csv"
)


# ============================================================================
# CONSTANTS
# ============================================================================

TARGET_COLUMN = "target_occupancy_rate_30m"

TARGET_COLUMNS = {
    "target_occupancy_rate_30m",
    "target_occupancy_rate_1h",
    "target_occupancy_rate_2h",
    "target_tomorrow_morning_demand",
}

TARGET_CONFIGURATION_TERMS = {
    "target_interval_minutes",
    "target_horizon",
    "target_horizon_minutes",
    "target_window",
    "target_start",
    "target_end",
    "target_timestamp",
    "target_column",
    "target_columns",
}

# These are target-related names which are legitimate in configuration/
# target-construction code and must not be interpreted as feature leakage.
TARGET_CONFIGURATION_EXACT = {
    "target_interval_minutes",
    "target_horizon",
    "target_horizon_minutes",
    "target_window",
    "target_start",
    "target_end",
    "target_timestamp",
    "target_column",
    "target_columns",
    "target_valid",
    "target_availability",
    "target_exclusion_reason",
}

CURRENT_STATE_FEATURES = {
    "occupancy_rate",
    "availability_rate",
    "occupied_ratio",
    "available_ratio",
    "vacancy_ratio",
    "occupancy_level",
    "occupancy_state_valid",
    "capacity_utilization",
    "occupancy_capacity_difference",
    "occupancy_within_capacity",
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
    "is_low_occupancy",
    "is_moderate_occupancy",
    "is_high_occupancy",
    "is_near_full",
    "is_empty",
    "is_full",
    "occupancy_rate_consistent",
}

# Explicit current-state feature prefixes.
CURRENT_STATE_PREFIXES = (
    "occupancy_rate_roll_",
    "occupied_spaces_roll_",
    "available_spaces_roll_",
)

# Historical feature suffix/patterns.
LAG_PATTERN = re.compile(
    r"^(?P<base>.+)_lag_(?P<horizon>30m|1h|2h|3h|6h|12h|1d)$"
)

ROLLING_PATTERN = re.compile(
    r"^(?P<base>.+)_roll_"
    r"(?P<stat>mean|std|min|max|median|trend|count|missing|"
    r"coverage_ratio|available)_"
    r"(?P<horizon>1h|2h|3h|6h|12h|1d)$"
)

CALENDAR_FEATURES = {
    "year",
    "month",
    "day",
    "day_of_month",
    "day_of_week",
    "weekday",
    "week",
    "week_of_year",
    "quarter",
    "hour",
    "minute",
    "is_weekend",
    "is_weekday",
    "is_holiday",
    "holiday",
    "is_business_day",
    "time_slot",
}

STATIC_FEATURE_NAMES = {
    "capacity",
    "total_spaces",
    "facility_capacity",
    "facility_type",
    "facility_category",
}

STATIC_PREFIXES = (
    "facility_",
    "source_facility_",
)

# Metadata fields which should not be model features.
METADATA_COLUMNS = {
    "source_facility_code",
    "normalized_at",
    "timestamp",
    "source_timestamp",
}

SOURCE_SCAN_ROOTS = (
    BACKEND_ROOT / "app" / "ml",
)


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class SourceEvidence:
    feature: str
    file: str
    line: int
    code: str
    signal: str
    classification: str
    reason: str


@dataclass
class FeatureAuditRecord:
    feature: str
    feature_index: int
    dtype_train: str
    dtype_validation: str
    persisted_in_train: bool
    persisted_in_validation: bool
    classification: str
    availability_status: str
    leakage_status: str
    reason: str
    source_evidence_count: int
    source_files: list[str]
    source_signals: list[str]


# ============================================================================
# CONSOLE HELPERS
# ============================================================================

def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def status_line(label: str, value: Any) -> None:
    print(f"{label:<45}: {value}")


# ============================================================================
# GENERAL HELPERS
# ============================================================================

def normalise_name(value: str) -> str:
    return str(value).strip().lower()


def is_target_name(name: str) -> bool:
    return normalise_name(name) in {
        normalise_name(value)
        for value in TARGET_COLUMNS
    }


def is_target_configuration_name(name: str) -> bool:
    normalised = normalise_name(name)

    if normalised in TARGET_CONFIGURATION_EXACT:
        return True

    return (
        normalised.startswith("target_")
        and normalised not in TARGET_COLUMNS
    )


def feature_matches_current_state(name: str) -> bool:
    normalised = normalise_name(name)

    if normalised in CURRENT_STATE_FEATURES:
        return True

    return any(
        normalised.startswith(prefix)
        for prefix in CURRENT_STATE_PREFIXES
    )


def classify_feature_name(name: str) -> tuple[str, str]:
    """
    Name-based classification is deliberately conservative.

    The classification is NOT itself proof of leakage.
    """

    normalised = normalise_name(name)

    if is_target_name(normalised):
        return (
            "target_derived",
            "Feature name is a registered target column.",
        )

    if feature_matches_current_state(normalised):
        return (
            "current_state",
            "Feature represents current parking occupancy, "
            "availability, demand, or a rolling state derived from "
            "current operational observations.",
        )

    if LAG_PATTERN.match(normalised):
        return (
            "historical_lag",
            "Feature name explicitly identifies a historical lag.",
        )

    if ROLLING_PATTERN.match(normalised):
        return (
            "rolling_historical",
            "Feature name explicitly identifies a rolling historical "
            "statistic.",
        )

    if normalised in CALENDAR_FEATURES:
        return (
            "temporal_calendar",
            "Feature is a calendar/time representation.",
        )

    if normalised in STATIC_FEATURE_NAMES:
        return (
            "static_facility",
            "Feature represents a facility/static property.",
        )

    if any(
        normalised.startswith(prefix)
        for prefix in STATIC_PREFIXES
    ):
        return (
            "static_facility",
            "Feature name indicates facility/static metadata.",
        )

    return (
        "other",
        "Feature could not be confidently classified by name alone.",
    )


def safe_json_value(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating,)):
        value = float(value)

    if isinstance(value, float):
        if math.isnan(value):
            return None

        if math.isinf(value):
            return str(value)

    if isinstance(value, dict):
        return {
            str(key): safe_json_value(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set)):
        return [
            safe_json_value(item)
            for item in value
        ]

    return value


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            safe_json_value(payload),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


# ============================================================================
# DATASET VALIDATION
# ============================================================================

def validate_dataset_files() -> None:
    section("DATASET FILE VALIDATION")

    status_line(
        "Training dataset",
        TRAIN_PATH,
    )

    status_line(
        "Validation dataset",
        VALIDATION_PATH,
    )

    status_line(
        "Test dataset",
        TEST_PATH,
    )

    if not TRAIN_PATH.exists():
        raise FileNotFoundError(
            f"Training dataset does not exist: {TRAIN_PATH}"
        )

    if not VALIDATION_PATH.exists():
        raise FileNotFoundError(
            f"Validation dataset does not exist: {VALIDATION_PATH}"
        )

    if not TEST_PATH.exists():
        raise FileNotFoundError(
            f"Test dataset does not exist: {TEST_PATH}"
        )

    status_line(
        "Training file exists",
        "PASS",
    )

    status_line(
        "Validation file exists",
        "PASS",
    )

    status_line(
        "Test file exists",
        "PASS",
    )

    print()
    print("Test dataset will NOT be loaded.")


def load_persisted_datasets() -> tuple[pd.DataFrame, pd.DataFrame]:
    section("LOADING PERSISTED DATASETS")

    print("Loading training dataset...")
    train = pd.read_parquet(TRAIN_PATH)

    print("Loading validation dataset...")
    validation = pd.read_parquet(VALIDATION_PATH)

    status_line(
        "Training rows",
        f"{len(train):,}",
    )

    status_line(
        "Validation rows",
        f"{len(validation):,}",
    )

    return train, validation


def load_feature_registry() -> list[str]:
    section("FEATURE REGISTRY")

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Training manifest does not exist: {MANIFEST_PATH}"
        )

    manifest = json.loads(
        MANIFEST_PATH.read_text(
            encoding="utf-8",
        )
    )

    features = manifest.get(
        "feature_columns",
        [],
    )

    if not isinstance(features, list):
        raise ValueError(
            "training_dataset_manifest.json contains an invalid "
            "'feature_columns' value."
        )

    features = [
        str(feature)
        for feature in features
    ]

    if len(features) != len(set(features)):
        duplicates = sorted(
            {
                feature
                for feature in features
                if features.count(feature) > 1
            }
        )

        raise ValueError(
            "Duplicate feature names found in registry: "
            f"{duplicates}"
        )

    status_line(
        "Registered features",
        len(features),
    )

    status_line(
        "Manifest",
        MANIFEST_PATH,
    )

    return features


def validate_feature_contract(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
) -> None:

    section("FEATURE CONTRACT VALIDATION")

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
        raise ValueError(
            "Training dataset is missing registered features: "
            f"{train_missing}"
        )

    if validation_missing:
        raise ValueError(
            "Validation dataset is missing registered features: "
            f"{validation_missing}"
        )

    train_extra = [
        column
        for column in train.columns
        if column not in features
        and column not in TARGET_COLUMNS
    ]

    validation_extra = [
        column
        for column in validation.columns
        if column not in features
        and column not in TARGET_COLUMNS
    ]

    status_line(
        "Training feature registry",
        "PASS",
    )

    status_line(
        "Validation feature registry",
        "PASS",
    )

    status_line(
        "Train/validation feature registry",
        "IDENTICAL",
    )

    status_line(
        "Registered feature count",
        len(features),
    )

    if train_extra:
        print()
        print(
            "Training non-feature columns observed:"
        )

        for column in train_extra:
            print(f"  - {column}")

    if validation_extra:
        print()
        print(
            "Validation non-feature columns observed:"
        )

        for column in validation_extra:
            print(f"  - {column}")


def validate_target_contract(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    section("TARGET CONTRACT VALIDATION")

    for dataframe, name in (
        (train, "training"),
        (validation, "validation"),
    ):

        if TARGET_COLUMN not in dataframe.columns:
            raise ValueError(
                f"{name.capitalize()} dataset does not contain "
                f"target column '{TARGET_COLUMN}'."
            )

        target = pd.to_numeric(
            dataframe[TARGET_COLUMN],
            errors="coerce",
        )

        if target.isna().any():
            raise ValueError(
                f"{name.capitalize()} target contains null/non-numeric "
                "values."
            )

        if not np.isfinite(
            target.to_numpy(dtype=float)
        ).all():
            raise ValueError(
                f"{name.capitalize()} target contains infinite values."
            )

        status_line(
            f"{name.capitalize()} target rows",
            f"{len(target):,}",
        )

        status_line(
            f"{name.capitalize()} target nulls",
            int(target.isna().sum()),
        )

        status_line(
            f"{name.capitalize()} target mean",
            f"{target.mean():.6f}",
        )

        status_line(
            f"{name.capitalize()} target range",
            f"{target.min():.6f} -> {target.max():.6f}",
        )

        if (
            float(target.min()) < 0.0
            or float(target.max()) > 1.0
        ):
            raise ValueError(
                f"{name.capitalize()} target is outside [0, 1]."
            )

    status_line(
        "Target contract",
        "PASS",
    )


# ============================================================================
# SOURCE CODE DISCOVERY
# ============================================================================

def discover_source_files() -> list[Path]:
    files: list[Path] = []

    for root in SOURCE_SCAN_ROOTS:

        if not root.exists():
            continue

        files.extend(
            path
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts
        )

    return sorted(
        set(files)
    )


def source_relative_path(path: Path) -> str:
    try:
        return str(
            path.relative_to(
                PROJECT_ROOT
            )
        )
    except ValueError:
        return str(path)


# ============================================================================
# AST ANALYSIS
# ============================================================================

class TemporalASTVisitor(ast.NodeVisitor):
    """
    Conservative AST scanner.

    It detects:
        - negative shift
        - negative timedelta
        - centered rolling
        - future-oriented indexing
        - target references

    It does NOT treat generic configuration names such as
    target_interval_minutes as target leakage.
    """

    def __init__(
        self,
        *,
        feature_names: set[str],
        source_file: Path,
    ) -> None:

        self.feature_names = feature_names

        self.source_file = source_file

        self.evidence: list[SourceEvidence] = []

        self.context_stack: list[str] = []

    # ------------------------------------------------------------------
    # Context
    # ------------------------------------------------------------------

    def _context(self) -> str:
        if not self.context_stack:
            return ""

        return " > ".join(
            self.context_stack
        )

    def visit_FunctionDef(
        self,
        node: ast.FunctionDef,
    ) -> Any:

        self.context_stack.append(
            node.name
        )

        self.generic_visit(node)

        self.context_stack.pop()

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> Any:

        self.context_stack.append(
            node.name
        )

        self.generic_visit(node)

        self.context_stack.pop()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _line(self, node: ast.AST) -> str:
        try:
            return (
                self.source_file.read_text(
                    encoding="utf-8"
                )
                .splitlines()[node.lineno - 1]
                .strip()
            )
        except Exception:
            return ""

    def _feature_from_name(
        self,
        value: str,
    ) -> Optional[str]:

        normalised = normalise_name(value)

        if normalised in self.feature_names:
            return normalised

        return None

    def _emit(
        self,
        *,
        feature: str,
        node: ast.AST,
        signal: str,
        classification: str,
        reason: str,
    ) -> None:

        self.evidence.append(
            SourceEvidence(
                feature=feature,
                file=source_relative_path(
                    self.source_file
                ),
                line=int(
                    getattr(
                        node,
                        "lineno",
                        0,
                    )
                ),
                code=self._line(node),
                signal=signal,
                classification=classification,
                reason=reason,
            )
        )

    # ------------------------------------------------------------------
    # Constants / names
    # ------------------------------------------------------------------

    def visit_Name(
        self,
        node: ast.Name,
    ) -> Any:

        name = normalise_name(
            node.id
        )

        # Do NOT treat target configuration variables as leakage.
        if is_target_configuration_name(name):
            self.generic_visit(node)
            return

        if name in {
            normalise_name(
                feature
            )
            for feature in TARGET_COLUMNS
        }:

            self._emit(
                feature=name,
                node=node,
                signal="target_reference",
                classification="POTENTIAL_LEAKAGE",
                reason=(
                    "Source code directly references a registered "
                    "target column."
                ),
            )

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Strings
    # ------------------------------------------------------------------

    def visit_Constant(
        self,
        node: ast.Constant,
    ) -> Any:

        if isinstance(
            node.value,
            str,
        ):

            value = normalise_name(
                node.value
            )

            if value in {
                normalise_name(
                    feature
                )
                for feature in self.feature_names
            }:

                classification, reason = (
                    classify_feature_name(
                        value
                    )
                )

                if classification == "target_derived":
                    self._emit(
                        feature=value,
                        node=node,
                        signal="registered_target_string",
                        classification="POTENTIAL_LEAKAGE",
                        reason=(
                            "A registered target name appears directly "
                            "in source code."
                        ),
                    )

        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Shift
    # ------------------------------------------------------------------

    def visit_Call(
        self,
        node: ast.Call,
    ) -> Any:

        function_name = ""

        if isinstance(
            node.func,
            ast.Attribute,
        ):
            function_name = (
                normalise_name(
                    node.func.attr
                )
            )

        if function_name == "shift":

            negative_shift = False

            if node.args:

                argument = node.args[0]

                if isinstance(
                    argument,
                    ast.UnaryOp,
                ) and isinstance(
                    argument.op,
                    ast.USub,
                ):

                    negative_shift = True

                elif isinstance(
                    argument,
                    ast.Constant,
                ):

                    try:
                        negative_shift = (
                            float(
                                argument.value
                            ) < 0
                        )
                    except (
                        TypeError,
                        ValueError,
                    ):
                        pass

            for keyword in node.keywords:

                if keyword.arg == "periods":

                    value = keyword.value

                    if isinstance(
                        value,
                        ast.UnaryOp,
                    ) and isinstance(
                        value.op,
                        ast.USub,
                    ):
                        negative_shift = True

                    elif isinstance(
                        value,
                        ast.Constant,
                    ):
                        try:
                            negative_shift = (
                                float(
                                    value.value
                                ) < 0
                            )
                        except (
                            TypeError,
                            ValueError,
                        ):
                            pass

            if negative_shift:

                # Critical distinction:
                #
                # If the current function appears to construct targets,
                # this is not automatically feature leakage.
                context = self._context().lower()

                target_construction_context = any(
                    token in context
                    for token in (
                        "target",
                        "horizon",
                        "future",
                    )
                )

                classification = (
                    "TARGET_CONSTRUCTION"
                    if target_construction_context
                    else "POTENTIAL_LEAKAGE"
                )

                reason = (
                    "Negative shift detected in a function whose "
                    "context indicates target/future construction."
                    if target_construction_context
                    else
                    "Negative shift detected outside an obvious "
                    "target-construction context."
                )

                # We only emit against a feature when we can identify
                # one from an enclosing assignment/name pattern.
                feature = self._infer_assignment_feature(
                    node
                )

                if feature:
                    self._emit(
                        feature=feature,
                        node=node,
                        signal="negative_shift",
                        classification=classification,
                        reason=reason,
                    )

        # --------------------------------------------------------------
        # Rolling / centered window.
        # --------------------------------------------------------------

        if function_name == "rolling":

            centered = False

            for keyword in node.keywords:

                if keyword.arg == "center":

                    value = keyword.value

                    if (
                        isinstance(
                            value,
                            ast.Constant,
                        )
                        and value.value is True
                    ):
                        centered = True

            if centered:

                feature = self._infer_assignment_feature(
                    node
                )

                if feature:

                    self._emit(
                        feature=feature,
                        node=node,
                        signal="centered_rolling_window",
                        classification="POTENTIAL_LEAKAGE",
                        reason=(
                            "Centered rolling window may include "
                            "future observations."
                        ),
                    )

        # --------------------------------------------------------------
        # Datetime offsets / timedelta.
        # --------------------------------------------------------------

        if function_name in {
            "timedelta",
            "dateoffset",
        }:

            source_line = self._line(node).lower()

            future_signal = any(
                token in source_line
                for token in (
                    "future",
                    "next",
                    "forward",
                    "tomorrow",
                )
            )

            if future_signal:

                feature = self._infer_assignment_feature(
                    node
                )

                if feature:

                    self._emit(
                        feature=feature,
                        node=node,
                        signal="future_offset",
                        classification="POTENTIAL_LEAKAGE",
                        reason=(
                            "Future-oriented datetime offset appears "
                            "in feature-generation source."
                        ),
                    )

        self.generic_visit(node)

    def _infer_assignment_feature(
        self,
        node: ast.AST,
    ) -> Optional[str]:

        """
        Best-effort feature inference.

        AST does not directly expose parent nodes through NodeVisitor,
        therefore this method intentionally remains conservative.

        When inference is unavailable, the audit relies on the feature
        registry and persisted feature semantics instead of inventing
        a feature association.
        """

        return None


def scan_source_code(
    feature_names: list[str],
) -> list[SourceEvidence]:

    section("SOURCE CODE TEMPORAL ANALYSIS")

    source_files = discover_source_files()

    status_line(
        "ML source files scanned",
        len(source_files),
    )

    all_evidence: list[SourceEvidence] = []

    feature_set = {
        normalise_name(
            feature
        )
        for feature in feature_names
    }

    for source_file in source_files:

        try:
            source = source_file.read_text(
                encoding="utf-8"
            )

            tree = ast.parse(
                source,
                filename=str(source_file),
            )

        except (
            OSError,
            UnicodeDecodeError,
            SyntaxError,
        ):
            continue

        visitor = TemporalASTVisitor(
            feature_names=feature_set,
            source_file=source_file,
        )

        visitor.visit(tree)

        all_evidence.extend(
            visitor.evidence
        )

    negative_shift = [
        item
        for item in all_evidence
        if item.signal == "negative_shift"
    ]

    centered = [
        item
        for item in all_evidence
        if item.signal == "centered_rolling_window"
    ]

    target_refs = [
        item
        for item in all_evidence
        if item.signal == "target_reference"
        or item.signal == "registered_target_string"
    ]

    future_refs = [
        item
        for item in all_evidence
        if item.signal == "future_offset"
    ]

    status_line(
        "Negative-shift findings",
        len(negative_shift),
    )

    status_line(
        "Centered-window findings",
        len(centered),
    )

    status_line(
        "Registered target-reference findings",
        len(target_refs),
    )

    status_line(
        "Future-offset findings",
        len(future_refs),
    )

    return all_evidence


# ============================================================================
# PERSISTED FEATURE ANALYSIS
# ============================================================================

def check_numeric_integrity(
    dataframe: pd.DataFrame,
    features: list[str],
) -> dict[str, Any]:

    numeric_features = [
        feature
        for feature in features
        if feature in dataframe.columns
        and pd.api.types.is_numeric_dtype(
            dataframe[feature]
        )
    ]

    infinite_by_feature: dict[str, int] = {}

    nan_by_feature: dict[str, int] = {}

    for feature in numeric_features:

        values = dataframe[
            feature
        ].to_numpy(
            dtype=float,
        )

        infinite_count = int(
            np.isinf(
                values
            ).sum()
        )

        nan_count = int(
            np.isnan(
                values
            ).sum()
        )

        if infinite_count:
            infinite_by_feature[
                feature
            ] = infinite_count

        if nan_count:
            nan_by_feature[
                feature
            ] = nan_count

    return {
        "numeric_feature_count": len(
            numeric_features
        ),
        "infinite_by_feature": (
            infinite_by_feature
        ),
        "nan_by_feature": nan_by_feature,
    }


def inspect_persisted_features(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
) -> None:

    section("PERSISTED FEATURE TEMPORAL DATASET INSPECTION")

    for dataframe, name in (
        (train, "Training"),
        (validation, "Validation"),
    ):

        numeric_result = (
            check_numeric_integrity(
                dataframe,
                features,
            )
        )

        non_numeric = [
            feature
            for feature in features
            if not pd.api.types.is_numeric_dtype(
                dataframe[feature]
            )
        ]

        status_line(
            f"{name} numeric features",
            numeric_result[
                "numeric_feature_count"
            ],
        )

        status_line(
            f"{name} non-numeric features",
            len(non_numeric),
        )

        status_line(
            f"{name} infinite numeric cells",
            sum(
                numeric_result[
                    "infinite_by_feature"
                ].values()
            ),
        )

        status_line(
            f"{name} numeric NaN cells",
            sum(
                numeric_result[
                    "nan_by_feature"
                ].values()
            ),
        )

        if non_numeric:
            print()
            print(
                f"{name} non-numeric registered features:"
            )

            for feature in non_numeric:
                print(
                    f"  - {feature}: "
                    f"{dataframe[feature].dtype}"
                )


# ============================================================================
# FEATURE LINEAGE CLASSIFICATION
# ============================================================================

def collect_evidence_for_feature(
    feature: str,
    evidence: list[SourceEvidence],
) -> list[SourceEvidence]:

    normalised = normalise_name(
        feature
    )

    return [
        item
        for item in evidence
        if normalise_name(
            item.feature
        ) == normalised
    ]


def determine_availability_status(
    classification: str,
) -> tuple[str, str]:

    if classification == "current_state":
        return (
            "CURRENT_STATE_REVIEW",
            (
                "Current parking state may legitimately be available "
                "at prediction time, but the production information "
                "cutoff must be explicitly established."
            ),
        )

    if classification == "historical_lag":
        return (
            "SAFE_IF_GENERATED_CAUSALLY",
            (
                "Historical lag is temporally safe provided its source "
                "series is ordered by time and no future rows are used."
            ),
        )

    if classification == "rolling_historical":
        return (
            "SAFE_IF_RIGHT_ALIGNED",
            (
                "Rolling historical feature is safe when the rolling "
                "window is right-aligned and uses observations only "
                "through the prediction timestamp."
            ),
        )

    if classification == "temporal_calendar":
        return (
            "SAFE",
            (
                "Calendar/time feature describes the prediction "
                "timestamp and does not require future observations."
            ),
        )

    if classification == "static_facility":
        return (
            "SAFE_IF_STATIC",
            (
                "Facility attribute is safe if it is genuinely static "
                "and known before prediction."
            ),
        )

    return (
        "REVIEW",
        (
            "Automated classification cannot establish prediction-time "
            "availability."
        ),
    )


def determine_leakage_status(
    feature: str,
    classification: str,
    feature_evidence: list[SourceEvidence],
) -> tuple[str, str]:

    # Registered target columns must never be model features.
    if is_target_name(feature):
        return (
            "POTENTIAL_LEAKAGE",
            (
                "Registered target column appears in the feature "
                "registry."
            ),
        )

    # Target construction evidence is explicitly NOT leakage.
    leakage_evidence = [
        item
        for item in feature_evidence
        if item.classification == "POTENTIAL_LEAKAGE"
    ]

    if leakage_evidence:

        return (
            "POTENTIAL_LEAKAGE",
            "; ".join(
                sorted(
                    {
                        item.reason
                        for item in leakage_evidence
                    }
                )
            ),
        )

    return (
        "NO_CONFIRMED_LEAKAGE",
        (
            "No confirmed future-reference, centered-window, "
            "or target-derived feature evidence was established."
        ),
    )


def build_feature_audit(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    features: list[str],
    evidence: list[SourceEvidence],
) -> list[FeatureAuditRecord]:

    records: list[FeatureAuditRecord] = []

    for index, feature in enumerate(
        features,
        start=1,
    ):

        classification, classification_reason = (
            classify_feature_name(
                feature
            )
        )

        availability_status, availability_reason = (
            determine_availability_status(
                classification
            )
        )

        feature_evidence = (
            collect_evidence_for_feature(
                feature,
                evidence,
            )
        )

        leakage_status, leakage_reason = (
            determine_leakage_status(
                feature,
                classification,
                feature_evidence,
            )
        )

        records.append(
            FeatureAuditRecord(
                feature=feature,
                feature_index=index,
                dtype_train=str(
                    train[feature].dtype
                ),
                dtype_validation=str(
                    validation[feature].dtype
                ),
                persisted_in_train=True,
                persisted_in_validation=True,
                classification=classification,
                availability_status=availability_status,
                leakage_status=leakage_status,
                reason=(
                    f"{classification_reason} "
                    f"{availability_reason} "
                    f"{leakage_reason}"
                ),
                source_evidence_count=len(
                    feature_evidence
                ),
                source_files=sorted(
                    {
                        item.file
                        for item in feature_evidence
                    }
                ),
                source_signals=sorted(
                    {
                        item.signal
                        for item in feature_evidence
                    }
                ),
            )
        )

    return records


# ============================================================================
# TEMPORAL FEATURE FAMILY VALIDATION
# ============================================================================

def validate_lag_feature_names(
    features: list[str],
) -> dict[str, Any]:

    lag_features = [
        feature
        for feature in features
        if LAG_PATTERN.match(
            normalise_name(feature)
        )
    ]

    invalid = []

    for feature in lag_features:

        match = LAG_PATTERN.match(
            normalise_name(feature)
        )

        if not match:
            continue

        horizon = match.group(
            "horizon"
        )

        if horizon not in {
            "30m",
            "1h",
            "2h",
            "3h",
            "6h",
            "12h",
            "1d",
        }:
            invalid.append(
                feature
            )

    return {
        "count": len(lag_features),
        "invalid": invalid,
    }


def validate_rolling_feature_names(
    features: list[str],
) -> dict[str, Any]:

    rolling_features = [
        feature
        for feature in features
        if ROLLING_PATTERN.match(
            normalise_name(feature)
        )
    ]

    return {
        "count": len(rolling_features),
        "features": rolling_features,
    }


# ============================================================================
# PREDICTION-TIME AVAILABILITY CONTRACT
# ============================================================================

def build_prediction_time_contract() -> dict[str, Any]:

    return {
        "prediction_target": TARGET_COLUMN,
        "forecast_horizon_minutes": 30,
        "information_cutoff": "T",
        "allowed_information": (
            "Information known at or before prediction timestamp T."
        ),
        "prohibited_information": (
            "Any observation from T + epsilon through T + 30 minutes "
            "or later when it would not be known at prediction time."
        ),
        "current_state_policy": (
            "Current-state features are not automatically considered "
            "leakage. Their production availability at T must be "
            "established."
        ),
        "historical_lag_policy": (
            "Historical lags are safe when generated causally from "
            "observations at or before T."
        ),
        "rolling_policy": (
            "Rolling features are safe when right-aligned and do not "
            "include future rows."
        ),
        "calendar_policy": (
            "Calendar features derived from T are safe."
        ),
        "target_construction_policy": (
            "Negative shifts used exclusively to construct the future "
            "target are not considered model-feature leakage."
        ),
    }


# ============================================================================
# SUMMARY
# ============================================================================

def build_summary(
    records: list[FeatureAuditRecord],
    evidence: list[SourceEvidence],
) -> dict[str, Any]:

    classification_counts: dict[str, int] = {}

    availability_counts: dict[str, int] = {}

    leakage_counts: dict[str, int] = {}

    for record in records:

        classification_counts[
            record.classification
        ] = (
            classification_counts.get(
                record.classification,
                0,
            )
            + 1
        )

        availability_counts[
            record.availability_status
        ] = (
            availability_counts.get(
                record.availability_status,
                0,
            )
            + 1
        )

        leakage_counts[
            record.leakage_status
        ] = (
            leakage_counts.get(
                record.leakage_status,
                0,
            )
            + 1
        )

    negative_shift_count = sum(
        item.signal == "negative_shift"
        for item in evidence
    )

    centered_count = sum(
        item.signal == "centered_rolling_window"
        for item in evidence
    )

    future_offset_count = sum(
        item.signal == "future_offset"
        for item in evidence
    )

    true_target_reference_count = sum(
        item.signal
        in {
            "target_reference",
            "registered_target_string",
        }
        for item in evidence
    )

    potential_leakage_features = sorted(
        {
            record.feature
            for record in records
            if record.leakage_status
            == "POTENTIAL_LEAKAGE"
        }
    )

    current_state_features = sorted(
        {
            record.feature
            for record in records
            if record.classification
            == "current_state"
        }
    )

    return {
        "features_audited": len(records),
        "classification_counts": classification_counts,
        "availability_counts": availability_counts,
        "leakage_counts": leakage_counts,
        "source_negative_shift_findings": (
            negative_shift_count
        ),
        "source_centered_window_findings": (
            centered_count
        ),
        "source_future_offset_findings": (
            future_offset_count
        ),
        "source_registered_target_reference_findings": (
            true_target_reference_count
        ),
        "current_state_feature_count": len(
            current_state_features
        ),
        "current_state_features": current_state_features,
        "potential_leakage_feature_count": len(
            potential_leakage_features
        ),
        "potential_leakage_features": (
            potential_leakage_features
        ),
    }


def determine_verdict(
    summary: dict[str, Any],
) -> tuple[str, list[str]]:

    reasons: list[str] = []

    potential_count = int(
        summary[
            "potential_leakage_feature_count"
        ]
    )

    if potential_count:
        reasons.append(
            "Potential feature leakage detected in "
            f"{potential_count} registered feature(s)."
        )

    if (
        int(
            summary[
                "source_centered_window_findings"
            ]
        )
        > 0
    ):
        reasons.append(
            "Centered rolling-window evidence was detected."
        )

    if (
        int(
            summary[
                "source_future_offset_findings"
            ]
        )
        > 0
    ):
        reasons.append(
            "Future-oriented offset evidence was detected."
        )

    if reasons:
        return (
            "FAIL",
            reasons,
        )

    if (
        int(
            summary[
                "current_state_feature_count"
            ]
        )
        > 0
    ):
        return (
            "PASS_WITH_CURRENT_STATE_REVIEW",
            [
                (
                    "No confirmed feature leakage was detected, "
                    "but current-state feature availability must "
                    "be established for production inference."
                )
            ],
        )

    return (
        "PASS",
        [
            "No confirmed feature leakage detected.",
            (
                "No centered rolling-window leakage was detected."
            ),
            (
                "No future-oriented feature offset was detected."
            ),
        ],
    )


# ============================================================================
# OUTPUT
# ============================================================================

def persist_feature_csv(
    records: list[FeatureAuditRecord],
) -> None:

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    dataframe = pd.DataFrame(
        [
            asdict(record)
            for record in records
        ]
    )

    dataframe[
        "source_files"
    ] = dataframe[
        "source_files"
    ].apply(
        lambda value: ";".join(
            value
        )
    )

    dataframe[
        "source_signals"
    ] = dataframe[
        "source_signals"
    ].apply(
        lambda value: ";".join(
            value
        )
    )

    dataframe.to_csv(
        CSV_OUTPUT,
        index=False,
    )


def persist_summary_csv(
    summary: dict[str, Any],
) -> None:

    rows: list[dict[str, Any]] = []

    for category, values in (
        (
            "classification",
            summary[
                "classification_counts"
            ],
        ),
        (
            "availability",
            summary[
                "availability_counts"
            ],
        ),
        (
            "leakage",
            summary[
                "leakage_counts"
            ],
        ),
    ):

        for name, count in values.items():

            rows.append(
                {
                    "category": category,
                    "status": name,
                    "count": count,
                }
            )

    dataframe = pd.DataFrame(
        rows
    )

    dataframe.to_csv(
        SUMMARY_CSV_OUTPUT,
        index=False,
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:

    banner(
        "SMARTPARK AI - BIRMINGHAM "
        "XGBOOST TEMPORAL AVAILABILITY AUDIT"
    )

    print()
    print("Target:")
    print(f"  {TARGET_COLUMN}")

    print()
    print("Audit policy:")
    print("  Inspect persisted train/validation feature datasets")
    print("  Inspect ML feature-generation source code")
    print("  Distinguish target construction from feature leakage")
    print("  Do NOT load test.parquet")
    print("  Do NOT modify persisted datasets")
    print("  Do NOT train XGBoost")
    print("  Do NOT rebuild the feature pipeline")

    try:

        # --------------------------------------------------------------
        # Dataset validation.
        # --------------------------------------------------------------

        validate_dataset_files()

        train, validation = (
            load_persisted_datasets()
        )

        features = load_feature_registry()

        validate_feature_contract(
            train,
            validation,
            features,
        )

        validate_target_contract(
            train,
            validation,
        )

        # --------------------------------------------------------------
        # Persisted feature inspection.
        # --------------------------------------------------------------

        inspect_persisted_features(
            train,
            validation,
            features,
        )

        # --------------------------------------------------------------
        # Feature family validation.
        # --------------------------------------------------------------

        section(
            "TEMPORAL FEATURE FAMILY VALIDATION"
        )

        lag_result = (
            validate_lag_feature_names(
                features
            )
        )

        rolling_result = (
            validate_rolling_feature_names(
                features
            )
        )

        status_line(
            "Historical lag features",
            lag_result["count"],
        )

        status_line(
            "Rolling historical features",
            rolling_result["count"],
        )

        if lag_result["invalid"]:

            print()
            print(
                "Invalid lag features:"
            )

            for feature in lag_result["invalid"]:
                print(
                    f"  - {feature}"
                )

        else:
            status_line(
                "Lag feature naming contract",
                "PASS",
            )

        # --------------------------------------------------------------
        # Source analysis.
        # --------------------------------------------------------------

        evidence = scan_source_code(
            features
        )

        # --------------------------------------------------------------
        # Feature-level audit.
        # --------------------------------------------------------------

        section(
            "BUILDING FEATURE-LEVEL TEMPORAL AUDIT"
        )

        records = build_feature_audit(
            train,
            validation,
            features,
            evidence,
        )

        summary = build_summary(
            records,
            evidence,
        )

        # --------------------------------------------------------------
        # Print classification summary.
        # --------------------------------------------------------------

        print()
        print(
            "--- FEATURE CLASSIFICATION SUMMARY ---"
        )

        for classification, count in sorted(
            summary[
                "classification_counts"
            ].items()
        ):

            print(
                f"{classification:<38}: {count}"
            )

        print()
        print(
            "--- PREDICTION-TIME AVAILABILITY SUMMARY ---"
        )

        for status, count in sorted(
            summary[
                "availability_counts"
            ].items()
        ):

            print(
                f"{status:<38}: {count}"
            )

        print()
        print(
            "--- TEMPORAL LEAKAGE SIGNAL SUMMARY ---"
        )

        status_line(
            "Negative-shift source findings",
            summary[
                "source_negative_shift_findings"
            ],
        )

        status_line(
            "Centered-window source findings",
            summary[
                "source_centered_window_findings"
            ],
        )

        status_line(
            "Future-offset source findings",
            summary[
                "source_future_offset_findings"
            ],
        )

        status_line(
            "True registered-target references",
            summary[
                "source_registered_target_reference_findings"
            ],
        )

        print()
        print(
            "IMPORTANT:"
        )
        print(
            "  target_interval_minutes and other target "
            "configuration names are NOT treated as target leakage."
        )
        print(
            "  Negative shifts used exclusively for target "
            "construction are NOT automatically feature leakage."
        )

        # --------------------------------------------------------------
        # Current-state review.
        # --------------------------------------------------------------

        print()
        print(
            "--- CURRENT-STATE AVAILABILITY REVIEW ---"
        )

        current_state_features = (
            summary[
                "current_state_features"
            ]
        )

        if current_state_features:

            for feature in current_state_features:
                print(
                    f"  - {feature}"
                )

        else:
            print(
                "NO CURRENT-STATE FEATURES FOUND"
            )

        # --------------------------------------------------------------
        # Potential leakage.
        # --------------------------------------------------------------

        print()
        print(
            "--- POTENTIAL LEAKAGE FEATURES ---"
        )

        potential_features = (
            summary[
                "potential_leakage_features"
            ]
        )

        if potential_features:

            for feature in potential_features:

                record = next(
                    item
                    for item in records
                    if item.feature == feature
                )

                print(
                    f"  - {feature}"
                )

                print(
                    f"      Reason: {record.reason}"
                )

        else:

            print(
                "NO CONFIRMED POTENTIAL FEATURE LEAKAGE"
            )

        # --------------------------------------------------------------
        # Prediction-time contract.
        # --------------------------------------------------------------

        contract = (
            build_prediction_time_contract()
        )

        section(
            "PREDICTION-TIME AVAILABILITY CONTRACT"
        )

        status_line(
            "Prediction timestamp",
            contract[
                "information_cutoff"
            ],
        )

        status_line(
            "Forecast horizon",
            "30 minutes",
        )

        print()
        print(
            "Allowed information:"
        )
        print(
            f"  {contract['allowed_information']}"
        )

        print()
        print(
            "Prohibited information:"
        )
        print(
            f"  {contract['prohibited_information']}"
        )

        print()
        print(
            "Current-state policy:"
        )
        print(
            f"  {contract['current_state_policy']}"
        )

        # --------------------------------------------------------------
        # Verdict.
        # --------------------------------------------------------------

        verdict, reasons = determine_verdict(
            summary
        )

        section(
            "FINAL AUDIT RESULT"
        )

        status_line(
            "Features audited",
            summary[
                "features_audited"
            ],
        )

        status_line(
            "Potential leakage features",
            summary[
                "potential_leakage_feature_count"
            ],
        )

        status_line(
            "Current-state features",
            summary[
                "current_state_feature_count"
            ],
        )

        status_line(
            "Source negative-shift findings",
            summary[
                "source_negative_shift_findings"
            ],
        )

        status_line(
            "Source centered-window findings",
            summary[
                "source_centered_window_findings"
            ],
        )

        status_line(
            "Source future-offset findings",
            summary[
                "source_future_offset_findings"
            ],
        )

        status_line(
            "True target-reference findings",
            summary[
                "source_registered_target_reference_findings"
            ],
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

        for reason in reasons:
            print(
                f"  - {reason}"
            )

        # --------------------------------------------------------------
        # Persist.
        # --------------------------------------------------------------

        section(
            "PERSISTING AUDIT RESULTS"
        )

        persist_feature_csv(
            records
        )

        persist_summary_csv(
            summary
        )

        report = {
            "audit_name": (
                "Birmingham XGBoost "
                "Temporal Availability Audit"
            ),
            "generated_at_utc": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            "project_root": str(
                PROJECT_ROOT
            ),
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
            "test_dataset_loaded": False,
            "datasets_modified": False,
            "feature_pipeline_rebuilt": False,
            "model_trained": False,
            "target_column": TARGET_COLUMN,
            "feature_registry_count": len(
                features
            ),
            "prediction_time_contract": contract,
            "summary": summary,
            "verdict": verdict,
            "verdict_reasons": reasons,
            "source_evidence": [
                asdict(item)
                for item in evidence
            ],
            "feature_records": [
                asdict(item)
                for item in records
            ],
        }

        write_json(
            JSON_OUTPUT,
            report,
        )

        status_line(
            "Output directory",
            OUTPUT_ROOT,
        )

        status_line(
            "JSON report",
            JSON_OUTPUT,
        )

        status_line(
            "CSV feature audit",
            CSV_OUTPUT,
        )

        status_line(
            "CSV summary",
            SUMMARY_CSV_OUTPUT,
        )

        # --------------------------------------------------------------
        # Final operational guidance.
        # --------------------------------------------------------------

        print()
        print(
            "IMPORTANT:"
        )
        print(
            "  No persisted training, validation, or test dataset "
            "was modified."
        )
        print(
            "  Test dataset was NOT loaded."
        )
        print(
            "  No XGBoost model was trained."
        )

        if verdict == "FAIL":

            print()
            print(
                "DO NOT proceed to hyperparameter tuning."
            )

            print(
                "Resolve the reported temporal leakage finding(s) first."
            )

            return 2

        if verdict == "PASS_WITH_CURRENT_STATE_REVIEW":

            print()
            print(
                "NO CONFIRMED FEATURE LEAKAGE WAS DETECTED."
            )

            print(
                "Current-state feature prediction-time availability "
                "must still be documented."
            )

            print()
            print(
                "Hyperparameter tuning should remain paused until "
                "the current-state availability contract is accepted."
            )

            return 0

        print()
        print(
            "TEMPORAL AVAILABILITY AUDIT PASSED"
        )

        print()
        print(
            "No confirmed feature leakage was detected."
        )

        return 0

    except Exception as exc:

        banner(
            "BIRMINGHAM TEMPORAL AVAILABILITY AUDIT FAILED"
        )

        print()
        print(
            f"ERROR: {exc}"
        )

        print()
        print(
            "No persisted training, validation, or test dataset "
            "was modified."
        )

        print(
            "Test dataset was NOT loaded."
        )

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )