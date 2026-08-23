"""
SMARTPARK AI
Birmingham XGBoost Feature Lineage Audit

Purpose
-------
Trace the registered Birmingham XGBoost features back to the ML feature
generation source code and establish a conservative temporal lineage
contract.

This is a DIAGNOSTIC / AUDIT script.

It does NOT:

    - modify train.parquet
    - modify validation.parquet
    - modify test.parquet
    - load test.parquet
    - train XGBoost
    - tune XGBoost
    - rebuild the feature pipeline
    - regenerate the persisted dataset
    - alter the feature manifest

Production prediction contract
------------------------------
Prediction timestamp = T
Forecast horizon     = T + 30 minutes

Every production feature must be generated exclusively from information
available at or before T.

Important distinction
---------------------
Target construction legitimately uses future observations. For example:

    occupancy.shift(-1)

may be completely valid when constructing:

    target_occupancy_rate_30m

because that future observation is the label.

The same operation would be leakage if it were used to construct an
input feature.

Therefore this audit explicitly separates:

    TARGET_GENERATION
    FEATURE_GENERATION
    OTHER / INFRASTRUCTURE

Output
------
The script writes:

    datasets/processed/birmingham/
        xgboost_feature_lineage/
            birmingham_xgboost_feature_lineage.json
            birmingham_xgboost_feature_lineage_features.csv
            birmingham_xgboost_feature_lineage_source_findings.csv
            birmingham_xgboost_feature_lineage_summary.csv

"""

from __future__ import annotations

import ast
import csv
import json
import math
import re
import sys
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

TARGET_COLUMNS = {
    "target_occupancy_rate_30m",
    "target_occupancy_rate_1h",
    "target_occupancy_rate_2h",
    "target_tomorrow_morning_demand",
    "target_tomorrow_morning_rate",
    "target_tomorrow_morning_timestamp",
}

TARGET_AVAILABILITY_COLUMNS = {
    "target_30m_available",
    "target_1h_available",
    "target_2h_available",
    "target_tomorrow_morning_available",
    "target_eligible",
    "target_exclusion_reason",
}

METADATA_COLUMNS = {
    "source_facility_code",
    "normalized_at",
}

DATASET_NON_FEATURE_COLUMNS = (
    TARGET_COLUMNS
    | TARGET_AVAILABILITY_COLUMNS
    | METADATA_COLUMNS
)

EXPECTED_FEATURE_COUNT = 296

PRODUCTION_HORIZON_MINUTES = 30

SOURCE_ROOT_RELATIVE = Path("app") / "ml"

OUTPUT_RELATIVE = (
    Path("datasets")
    / "processed"
    / "birmingham"
    / "xgboost_feature_lineage"
)

MANIFEST_RELATIVE = (
    Path("datasets")
    / "processed"
    / "birmingham"
    / "training_dataset_manifest.json"
)

TRAIN_RELATIVE = (
    Path("datasets")
    / "processed"
    / "birmingham"
    / "target_occupancy_rate_30m"
    / "train.parquet"
)

VALIDATION_RELATIVE = (
    Path("datasets")
    / "processed"
    / "birmingham"
    / "target_occupancy_rate_30m"
    / "validation.parquet"
)

TEST_RELATIVE = (
    Path("datasets")
    / "processed"
    / "birmingham"
    / "target_occupancy_rate_30m"
    / "test.parquet"
)


# ============================================================================
# EXCEPTIONS
# ============================================================================


class FeatureLineageAuditError(RuntimeError):
    """Base exception for the feature lineage audit."""


class AuditDataError(FeatureLineageAuditError):
    """Raised when persisted dataset contracts are invalid."""


class AuditSourceError(FeatureLineageAuditError):
    """Raised when source-code analysis cannot be completed."""


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass
class SourceFinding:
    file: str
    line: int
    finding_type: str
    context: str
    source_expression: str
    likely_context: str
    feature_candidates: list[str] = field(default_factory=list)
    temporal_direction: str = "UNKNOWN"
    target_context: bool = False
    feature_context: bool = False


@dataclass
class FeatureLineageRecord:
    feature: str

    present_in_training: bool = False
    present_in_validation: bool = False

    dtype_training: str = ""
    dtype_validation: str = ""

    null_count_training: int = 0
    null_count_validation: int = 0

    family: str = "other"

    source_evidence_count: int = 0
    source_files: list[str] = field(default_factory=list)
    source_lines: list[int] = field(default_factory=list)

    source_expressions: list[str] = field(default_factory=list)
    source_operations: list[str] = field(default_factory=list)

    candidate_source_columns: list[str] = field(default_factory=list)

    has_shift: bool = False
    has_negative_shift: bool = False
    has_positive_shift: bool = False

    has_rolling: bool = False
    has_centered_rolling: bool = False

    has_expanding: bool = False
    has_diff: bool = False
    has_pct_change: bool = False

    has_forward_operation: bool = False
    has_future_named_signal: bool = False

    target_context_evidence: bool = False
    feature_context_evidence: bool = False

    temporal_direction: str = "UNKNOWN"

    causal_assessment: str = "UNKNOWN"

    production_verdict: str = "REQUIRES_CAUSAL_REVIEW"

    notes: list[str] = field(default_factory=list)


@dataclass
class AuditSummary:
    repository_root: str

    registered_features: int
    training_features: int
    validation_features: int

    source_files_scanned: int
    source_findings: int

    historical_features: int
    current_state_features: int
    temporal_calendar_features: int
    other_features: int

    source_evidence_features: int
    no_source_evidence_features: int

    negative_shift_features: int
    centered_rolling_features: int
    forward_operation_features: int

    target_context_findings: int
    feature_context_future_findings: int
    unresolved_future_findings: int

    confirmed_leakage_features: int
    potential_leakage_features: int
    causal_review_features: int
    provisionally_safe_features: int

    verdict: str


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


def print_status(label: str, value: Any) -> None:
    print(f"{label:<44}: {value}")


def print_pass(label: str, passed: bool) -> None:
    print(
        f"{label:<44}: "
        f"{'PASS' if passed else 'FAIL'}"
    )


def print_warning(label: str) -> None:
    print(f"WARNING: {label}")


# ============================================================================
# PATH DISCOVERY
# ============================================================================


def discover_repository_root() -> Path:
    """
    Locate the SmartPark AI repository root.

    Expected project structure:

        smart-parking-system/
        ├── backend/
        │   ├── app/
        │   └── birmingham_xgboost_feature_lineage_audit.py
        │
        └── datasets/
            └── processed/
                └── birmingham/

    The audit script itself lives under backend/.
    Therefore the repository root is normally the parent
    directory of backend/.
    """

    script_path = Path(__file__).resolve()

    backend_root = script_path.parent
    repository_root = backend_root.parent

    expected_backend_app = (
        backend_root / "app"
    )

    expected_datasets = (
        repository_root / "datasets"
    )

    if (
        expected_backend_app.is_dir()
        and expected_datasets.is_dir()
    ):
        return repository_root

    # ------------------------------------------------------------
    # Defensive fallback.
    #
    # Walk upward looking for the actual project structure.
    # ------------------------------------------------------------

    current = script_path.parent

    for candidate in [
        current,
        *current.parents,
    ]:

        if (
            (candidate / "backend" / "app").is_dir()
            and (candidate / "datasets").is_dir()
        ):
            return candidate

        if (
            (candidate / "app").is_dir()
            and (candidate / "datasets").is_dir()
        ):
            return candidate

    raise FeatureLineageAuditError(
        "Unable to determine SmartPark AI repository root. "
        f"Script location: {script_path}"
    )


def resolve_paths() -> dict[str, Path]:
    
    repository_root = discover_repository_root()

    backend_root = (
        repository_root / "backend"
    )

    source_root = (
        backend_root / "app" / "ml"
    )

    return {
        "repository_root": repository_root,
        "backend_root": backend_root,
        "source_root": source_root,

        "manifest": (
            repository_root
            / "datasets"
            / "processed"
            / "birmingham"
            / "training_dataset_manifest.json"
        ),

        "train": (
            repository_root
            / "datasets"
            / "processed"
            / "birmingham"
            / "target_occupancy_rate_30m"
            / "train.parquet"
        ),

        "validation": (
            repository_root
            / "datasets"
            / "processed"
            / "birmingham"
            / "target_occupancy_rate_30m"
            / "validation.parquet"
        ),

        "test": (
            repository_root
            / "datasets"
            / "processed"
            / "birmingham"
            / "target_occupancy_rate_30m"
            / "test.parquet"
        ),

        "output": (
            repository_root
            / "datasets"
            / "processed"
            / "birmingham"
            / "xgboost_feature_lineage"
        ),
    }


# ============================================================================
# FILE VALIDATION
# ============================================================================


def validate_dataset_files(paths: dict[str, Path]) -> None:

    print_section("DATASET FILE VALIDATION")

    print_status(
        "Repository root",
        paths["repository_root"],
    )

    print_status(
        "Training dataset",
        paths["train"],
    )

    print_status(
        "Validation dataset",
        paths["validation"],
    )

    print_status(
        "Test dataset",
        paths["test"],
    )

    print_status(
        "Feature manifest",
        paths["manifest"],
    )

    required = [
        ("Training file exists", paths["train"]),
        ("Validation file exists", paths["validation"]),
        ("Test file exists", paths["test"]),
        ("Manifest exists", paths["manifest"]),
    ]

    for label, path in required:

        exists = path.exists()

        print_pass(
            label,
            exists,
        )

        if not exists:
            raise AuditDataError(
                f"Required file does not exist: {path}"
            )

    print()
    print("Test dataset exists but will NOT be loaded.")


# ============================================================================
# MANIFEST
# ============================================================================


def load_manifest(
    path: Path,
) -> dict[str, Any]:

    print_section("LOADING FEATURE MANIFEST")

    print_status(
        "Manifest",
        path,
    )

    try:

        manifest = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )

    except Exception as exc:

        raise AuditDataError(
            f"Unable to read feature manifest: {path}"
        ) from exc

    registered = [
        str(feature)
        for feature in manifest.get(
            "feature_columns",
            [],
        )
    ]

    print_status(
        "Registered features",
        len(registered),
    )

    if not registered:

        raise AuditDataError(
            "Feature manifest contains no feature_columns."
        )

    return manifest


# ============================================================================
# DATASET LOADING
# ============================================================================


def load_persisted_datasets(
    paths: dict[str, Path],
) -> tuple[pd.DataFrame, pd.DataFrame]:

    print_section("LOADING PERSISTED DATASETS")

    print("Loading training dataset...")

    train = pd.read_parquet(
        paths["train"]
    )

    print("Loading validation dataset...")

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
        raise AuditDataError(
            "Training dataset is empty."
        )

    if validation.empty:
        raise AuditDataError(
            "Validation dataset is empty."
        )

    return train, validation


# ============================================================================
# FEATURE REGISTRY
# ============================================================================


def derive_dataset_model_features(
    dataframe: pd.DataFrame,
    registered: set[str],
) -> list[str]:

    """
    Derive model features by intersecting persisted columns with the
    registered feature contract.

    This intentionally avoids treating metadata and target diagnostic
    columns as model features.
    """

    return [
        str(column)
        for column in dataframe.columns
        if str(column) in registered
    ]


def validate_feature_registry(
    manifest: dict[str, Any],
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> list[str]:

    print_section("FEATURE REGISTRY VALIDATION")

    registered = {
        str(feature)
        for feature in manifest.get(
            "feature_columns",
            [],
        )
    }

    train_features = set(
        derive_dataset_model_features(
            train,
            registered,
        )
    )

    validation_features = set(
        derive_dataset_model_features(
            validation,
            registered,
        )
    )

    train_pass = (
        train_features == registered
    )

    validation_pass = (
        validation_features == registered
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
        train_pass,
    )

    print_pass(
        "Validation feature registry",
        validation_pass,
    )

    print_pass(
        "Train/validation feature registry",
        identical,
    )

    if not train_pass:

        missing = sorted(
            registered - train_features
        )

        extra = sorted(
            train_features - registered
        )

        raise AuditDataError(
            "Training feature registry mismatch. "
            f"Missing={missing}; Extra={extra}"
        )

    if not validation_pass:

        missing = sorted(
            registered - validation_features
        )

        extra = sorted(
            validation_features - registered
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

    print()
    print(
        "Persisted non-feature / metadata columns excluded "
        "from lineage:"
    )

    excluded = sorted(
        set(train.columns)
        - registered
    )

    for column in excluded:
        print(
            f"  - {column}"
        )

    return sorted(registered)


# ============================================================================
# TARGET VALIDATION
# ============================================================================


def validate_target_contract(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    print_section("TARGET CONTRACT VALIDATION")

    for label, dataframe in [
        ("Training", train),
        ("Validation", validation),
    ]:

        if TARGET_COLUMN not in dataframe.columns:

            raise AuditDataError(
                f"{label} dataset does not contain "
                f"target column '{TARGET_COLUMN}'."
            )

        target = pd.to_numeric(
            dataframe[TARGET_COLUMN],
            errors="coerce",
        )

        null_count = int(
            target.isna().sum()
        )

        print_status(
            f"{label} target rows",
            f"{len(target):,}",
        )

        print_status(
            f"{label} target nulls",
            f"{null_count:,}",
        )

        if null_count:

            raise AuditDataError(
                f"{label} target contains null values."
            )

        print_status(
            f"{label} target mean",
            f"{float(target.mean()):.6f}",
        )

        print_status(
            f"{label} target range",
            (
                f"{float(target.min()):.6f}"
                " -> "
                f"{float(target.max()):.6f}"
            ),
        )

    print_status(
        "Target contract",
        "PASS",
    )


# ============================================================================
# SOURCE DISCOVERY
# ============================================================================


def discover_python_sources(
    source_root: Path,
) -> list[Path]:

    if not source_root.exists():

        raise AuditSourceError(
            f"ML source root does not exist: {source_root}"
        )

    files = sorted(
        source_root.rglob("*.py")
    )

    if not files:

        raise AuditSourceError(
            f"No Python source files found under: {source_root}"
        )

    return files


# ============================================================================
# SOURCE CLASSIFICATION
# ============================================================================


def classify_context(
    text: str,
) -> str:

    lowered = text.lower()

    target_tokens = [
        "target_occupancy",
        "target_30m",
        "target_1h",
        "target_2h",
        "future_occupancy",
        "future_observed",
        "target_valid",
        "target_column",
        "availability_column",
        "horizon",
        "future_",
    ]

    feature_tokens = [
        "feature",
        "rolling_features",
        "occupancy_features",
        "demand_features",
        "temporal_features",
        "feature_pipeline",
        "build_features",
        "derived_features",
    ]

    target_score = sum(
        1
        for token in target_tokens
        if token in lowered
    )

    feature_score = sum(
        1
        for token in feature_tokens
        if token in lowered
    )

    if target_score > feature_score and target_score > 0:
        return "TARGET_GENERATION"

    if feature_score > 0:
        return "FEATURE_GENERATION"

    return "OTHER"


def detect_temporal_operations(
    text: str,
) -> list[tuple[str, str]]:

    operations: list[tuple[str, str]] = []

    patterns = [
        (
            "NEGATIVE_SHIFT",
            r"\.shift\s*\(\s*-\s*\d+",
        ),
        (
            "POSITIVE_SHIFT",
            r"\.shift\s*\(\s*\+?\s*\d+",
        ),
        (
            "SHIFT",
            r"\.shift\s*\(",
        ),
        (
            "CENTERED_ROLLING",
            r"\.rolling\s*\([^)]*center\s*=\s*True",
        ),
        (
            "ROLLING",
            r"\.rolling\s*\(",
        ),
        (
            "EXPANDING",
            r"\.expanding\s*\(",
        ),
        (
            "DIFF",
            r"\.diff\s*\(",
        ),
        (
            "PCT_CHANGE",
            r"\.pct_change\s*\(",
        ),
        (
            "FORWARD_FILL",
            r"\.ffill\s*\(",
        ),
        (
            "BACKWARD_FILL",
            r"\.bfill\s*\(",
        ),
    ]

    for operation, pattern in patterns:

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):

            direction = "UNKNOWN"

            if operation == "NEGATIVE_SHIFT":
                direction = "FUTURE"

            elif operation in {
                "POSITIVE_SHIFT",
                "SHIFT",
            }:
                direction = "HISTORICAL_OR_UNKNOWN"

            elif operation == "CENTERED_ROLLING":
                direction = "BOTH_SIDES"

            elif operation in {
                "ROLLING",
                "EXPANDING",
                "DIFF",
                "PCT_CHANGE",
            }:
                direction = "HISTORICAL_OR_UNKNOWN"

            elif operation == "BACKWARD_FILL":
                direction = "POTENTIALLY_FUTURE"

            operations.append(
                (
                    operation,
                    direction,
                )
            )

    return operations


# ============================================================================
# FEATURE CANDIDATE EXTRACTION
# ============================================================================


def feature_name_variants(
    feature: str,
) -> set[str]:

    variants = {
        feature.lower(),
    }

    # Remove common family prefixes/suffixes.
    replacements = [
        "_rate",
        "_ratio",
        "_mean",
        "_median",
        "_std",
        "_min",
        "_max",
        "_sum",
        "_lag",
        "_rolling",
        "_history",
        "_historical",
    ]

    for replacement in replacements:

        if replacement in feature.lower():

            variants.add(
                feature.lower().replace(
                    replacement,
                    "",
                )
            )

    # Token-level forms.
    tokens = [
        token
        for token in re.split(
            r"[_\-]",
            feature.lower(),
        )
        if token
    ]

    if tokens:
        variants.add(
            "_".join(tokens)
        )

    return {
        variant
        for variant in variants
        if len(variant) >= 4
    }


def extract_source_column_candidates(
    text: str,
) -> list[str]:

    candidates: set[str] = set()

    patterns = [
        r"""result\s*\[\s*["']([^"']+)["']\s*\]""",
        r"""dataframe\s*\[\s*["']([^"']+)["']\s*\]""",
        r"""df\s*\[\s*["']([^"']+)["']\s*\]""",
        r"""data\s*\[\s*["']([^"']+)["']\s*\]""",
    ]

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE,
        ):

            candidates.add(
                match.group(1)
            )

    return sorted(candidates)


def find_feature_mentions(
    feature: str,
    text: str,
) -> bool:

    variants = feature_name_variants(
        feature
    )

    lowered = text.lower()

    for variant in variants:

        if variant in lowered:
            return True

    return False


# ============================================================================
# AST SOURCE ANALYSIS
# ============================================================================


class TemporalASTVisitor(ast.NodeVisitor):

    def __init__(
        self,
        *,
        source_path: Path,
        source_text: str,
    ) -> None:

        self.source_path = source_path
        self.source_text = source_text

        self.findings: list[SourceFinding] = []

        self.current_function: list[str] = []

        self.current_assignment_target: Optional[str] = None

    def _line_context(
        self,
        line: int,
    ) -> str:

        lines = self.source_text.splitlines()

        start = max(
            0,
            line - 2,
        )

        end = min(
            len(lines),
            line + 1,
        )

        return "\n".join(
            lines[start:end]
        )

    def _function_context(self) -> str:

        if not self.current_function:
            return ""

        return ".".join(
            self.current_function
        )

    def visit_FunctionDef(
        self,
        node: ast.FunctionDef,
    ) -> Any:

        self.current_function.append(
            node.name
        )

        self.generic_visit(node)

        self.current_function.pop()

    def visit_AsyncFunctionDef(
        self,
        node: ast.AsyncFunctionDef,
    ) -> Any:

        self.current_function.append(
            node.name
        )

        self.generic_visit(node)

        self.current_function.pop()

    def visit_Assign(
        self,
        node: ast.Assign,
    ) -> Any:

        target_names = []

        for target in node.targets:

            target_names.extend(
                extract_ast_names(target)
            )

        previous = (
            self.current_assignment_target
        )

        self.current_assignment_target = (
            target_names[0]
            if target_names
            else None
        )

        self._inspect_expression(
            node.value,
            node.lineno,
            target_names,
        )

        self.generic_visit(node.value)

        self.current_assignment_target = previous

    def visit_AnnAssign(
        self,
        node: ast.AnnAssign,
    ) -> Any:

        target_names = extract_ast_names(
            node.target
        )

        previous = (
            self.current_assignment_target
        )

        self.current_assignment_target = (
            target_names[0]
            if target_names
            else None
        )

        if node.value is not None:

            self._inspect_expression(
                node.value,
                node.lineno,
                target_names,
            )

            self.generic_visit(
                node.value
            )

        self.current_assignment_target = previous

    def _inspect_expression(
        self,
        node: ast.AST,
        line: int,
        target_names: list[str],
    ) -> None:

        expression = ast.get_source_segment(
            self.source_text,
            node,
        )

        if not expression:
            expression = ast.dump(
                node
            )

        operations = detect_temporal_operations(
            expression
        )

        if not operations:
            return

        context = classify_context(
            (
                self._function_context()
                + " "
                + expression
                + " "
                + " ".join(target_names)
            )
        )

        target_context = (
            context == "TARGET_GENERATION"
        )

        feature_context = (
            context == "FEATURE_GENERATION"
        )

        for operation, direction in operations:

            finding_type = operation

            self.findings.append(
                SourceFinding(
                    file=str(
                        self.source_path
                    ),
                    line=line,
                    finding_type=finding_type,
                    context=context,
                    source_expression=expression[:1000],
                    likely_context=(
                        self._function_context()
                    ),
                    feature_candidates=target_names,
                    temporal_direction=direction,
                    target_context=target_context,
                    feature_context=feature_context,
                )
            )


def extract_ast_names(
    node: ast.AST,
) -> list[str]:

    names: list[str] = []

    if isinstance(
        node,
        ast.Name,
    ):

        names.append(
            node.id
        )

    elif isinstance(
        node,
        ast.Attribute,
    ):

        names.append(
            node.attr
        )

    elif isinstance(
        node,
        ast.Subscript,
    ):

        if isinstance(
            node.value,
            ast.Name,
        ):

            names.append(
                node.value.id
            )

    elif isinstance(
        node,
        (ast.Tuple, ast.List),
    ):

        for element in node.elts:

            names.extend(
                extract_ast_names(
                    element
                )
            )

    return names


# ============================================================================
# SOURCE SCAN
# ============================================================================


def scan_source_files(
    source_files: list[Path],
    registered_features: list[str],
) -> tuple[
    list[SourceFinding],
    dict[str, list[SourceFinding]],
]:

    print_section("SOURCE CODE DISCOVERY")

    print_status(
        "ML source files scanned",
        len(source_files),
    )

    source_findings: list[SourceFinding] = []

    feature_findings: dict[
        str,
        list[SourceFinding],
    ] = {
        feature: []
        for feature in registered_features
    }

    for source_file in source_files:

        try:

            text = source_file.read_text(
                encoding="utf-8",
                errors="replace",
            )

        except Exception as exc:

            raise AuditSourceError(
                f"Unable to read source file: "
                f"{source_file}"
            ) from exc

        # ------------------------------------------------------------
        # AST analysis
        # ------------------------------------------------------------

        try:

            tree = ast.parse(
                text,
                filename=str(source_file),
            )

        except SyntaxError as exc:

            raise AuditSourceError(
                f"Unable to parse source file: "
                f"{source_file}: {exc}"
            ) from exc

        visitor = TemporalASTVisitor(
            source_path=source_file,
            source_text=text,
        )

        visitor.visit(tree)

        source_findings.extend(
            visitor.findings
        )

        # ------------------------------------------------------------
        # Feature-specific textual lineage.
        # ------------------------------------------------------------

        lines = text.splitlines()

        for index, line in enumerate(
            lines,
            start=1,
        ):

            lowered = line.lower()

            operations = detect_temporal_operations(
                line
            )

            source_columns = (
                extract_source_column_candidates(
                    line
                )
            )

            for feature in registered_features:

                if not find_feature_mentions(
                    feature,
                    line,
                ):
                    continue

                finding = SourceFinding(
                    file=str(source_file),
                    line=index,
                    finding_type=(
                        operations[0][0]
                        if operations
                        else "FEATURE_REFERENCE"
                    ),
                    context=classify_context(
                        line
                    ),
                    source_expression=line.strip()[:1000],
                    likely_context=line.strip(),
                    feature_candidates=[
                        feature
                    ],
                    temporal_direction=(
                        operations[0][1]
                        if operations
                        else "UNKNOWN"
                    ),
                    target_context=(
                        "target" in lowered
                        or "future_" in lowered
                    ),
                    feature_context=(
                        "feature" in lowered
                        or "rolling" in lowered
                        or "lag" in lowered
                    ),
                )

                if source_columns:
                    finding.feature_candidates.extend(
                        source_columns
                    )

                feature_findings[
                    feature
                ].append(
                    finding
                )

    return source_findings, feature_findings


# ============================================================================
# FEATURE FAMILY CLASSIFICATION
# ============================================================================


def classify_feature_family(
    feature: str,
) -> str:

    lowered = feature.lower()

    current_state_tokens = [
        "occupancy_level",
        "occupancy_ratio",
        "occupied_ratio",
        "available_ratio",
        "availability_rate",
        "availability_pressure",
        "capacity_utilization",
        "capacity_difference",
        "within_capacity",
        "vacancy_ratio",
        "remaining_capacity",
        "demand_level",
        "demand_pressure",
        "demand_class",
        "is_full",
        "zero_capacity",
        "low_availability",
        "critical_availability",
        "capacity_exceeded",
        "current_",
    ]

    temporal_tokens = [
        "hour",
        "minute",
        "day",
        "week",
        "month",
        "weekday",
        "weekend",
        "time_slot",
        "sin_",
        "cos_",
        "is_peak",
        "peak_period",
        "morning",
        "afternoon",
        "evening",
    ]

    historical_tokens = [
        "lag",
        "rolling",
        "history",
        "historical",
        "previous",
        "prior",
        "trend",
        "mean_",
        "std_",
        "median_",
        "min_",
        "max_",
        "sum_",
        "change",
        "delta",
        "growth",
        "volatility",
        "recent",
    ]

    if any(
        token in lowered
        for token in current_state_tokens
    ):
        return "current_state"

    if any(
        token in lowered
        for token in temporal_tokens
    ):
        return "temporal_calendar"

    if any(
        token in lowered
        for token in historical_tokens
    ):
        return "historical"

    return "other"


# ============================================================================
# CAUSAL ASSESSMENT
# ============================================================================


def assess_feature_causality(
    record: FeatureLineageRecord,
) -> None:

    future_feature_signal = (
        record.has_negative_shift
        or record.has_centered_rolling
        or record.has_forward_operation
    )

    target_only_future = (
        record.target_context_evidence
        and not record.feature_context_evidence
    )

    if future_feature_signal:

        record.causal_assessment = (
            "FUTURE_INFORMATION_SIGNAL"
        )

        record.production_verdict = (
            "POTENTIAL_LEAKAGE"
        )

        record.notes.append(
            "Feature lineage contains a "
            "future-oriented temporal operation."
        )

        return

    if target_only_future:

        record.causal_assessment = (
            "TARGET_CONTEXT_ONLY"
        )

        record.production_verdict = (
            "REQUIRES_CAUSAL_REVIEW"
        )

        record.notes.append(
            "Future-oriented source logic appears "
            "associated with target construction rather "
            "than direct feature construction."
        )

        return

    if record.source_evidence_count == 0:

        record.causal_assessment = (
            "NO_SOURCE_EVIDENCE"
        )

        record.production_verdict = (
            "REQUIRES_CAUSAL_REVIEW"
        )

        record.notes.append(
            "No sufficiently direct source-code lineage "
            "was identified."
        )

        return

    if (
        record.has_shift
        or record.has_rolling
        or record.has_expanding
        or record.has_diff
        or record.has_pct_change
    ):

        if (
            record.temporal_direction
            == "HISTORICAL"
        ):

            record.causal_assessment = (
                "HISTORICAL_OPERATION"
            )

            record.production_verdict = (
                "PROVISIONALLY_CAUSAL"
            )

            record.notes.append(
                "Source evidence indicates a historical "
                "temporal operation with no detected "
                "future direction."
            )

            return

    record.causal_assessment = (
        "SOURCE_REFERENCE_ONLY"
    )

    record.production_verdict = (
        "REQUIRES_CAUSAL_REVIEW"
    )

    record.notes.append(
        "Source reference exists, but static analysis "
        "does not prove the timestamp cutoff."
    )


# ============================================================================
# FEATURE LINEAGE CONSTRUCTION
# ============================================================================


def build_feature_lineage(
    registered_features: list[str],
    train: pd.DataFrame,
    validation: pd.DataFrame,
    feature_findings: dict[
        str,
        list[SourceFinding],
    ],
    source_findings: list[SourceFinding],
) -> list[FeatureLineageRecord]:

    print_section(
        "BUILDING FEATURE-LEVEL LINEAGE CONTRACT"
    )

    records: list[
        FeatureLineageRecord
    ] = []

    for feature in registered_features:

        record = FeatureLineageRecord(
            feature=feature,
            present_in_training=(
                feature in train.columns
            ),
            present_in_validation=(
                feature in validation.columns
            ),
        )

        if record.present_in_training:

            record.dtype_training = str(
                train[feature].dtype
            )

            record.null_count_training = int(
                train[feature].isna().sum()
            )

        if record.present_in_validation:

            record.dtype_validation = str(
                validation[feature].dtype
            )

            record.null_count_validation = int(
                validation[feature].isna().sum()
            )

        record.family = classify_feature_family(
            feature
        )

        findings = feature_findings.get(
            feature,
            [],
        )

        # ------------------------------------------------------------
        # Feature-specific textual findings.
        # ------------------------------------------------------------

        for finding in findings:

            record.source_evidence_count += 1

            record.source_files.append(
                finding.file
            )

            record.source_lines.append(
                finding.line
            )

            record.source_expressions.append(
                finding.source_expression
            )

            record.candidate_source_columns.extend(
                [
                    candidate
                    for candidate in finding.feature_candidates
                    if candidate != feature
                ]
            )

            record.target_context_evidence |= (
                finding.target_context
            )

            record.feature_context_evidence |= (
                finding.feature_context
            )

            operation = finding.finding_type

            if operation not in {
                "FEATURE_REFERENCE",
                "",
            }:

                record.source_operations.append(
                    operation
                )

            if operation == "SHIFT":
                record.has_shift = True

            elif operation == "NEGATIVE_SHIFT":
                record.has_shift = True
                record.has_negative_shift = True

            elif operation == "POSITIVE_SHIFT":
                record.has_shift = True
                record.has_positive_shift = True

            elif operation == "ROLLING":
                record.has_rolling = True

            elif operation == "CENTERED_ROLLING":
                record.has_rolling = True
                record.has_centered_rolling = True

            elif operation == "EXPANDING":
                record.has_expanding = True

            elif operation == "DIFF":
                record.has_diff = True

            elif operation == "PCT_CHANGE":
                record.has_pct_change = True

            elif operation in {
                "BACKWARD_FILL",
            }:
                record.has_forward_operation = True

            if finding.temporal_direction == "FUTURE":
                record.has_future_named_signal = True

        # ------------------------------------------------------------
        # Source-level future evidence that explicitly references
        # the feature.
        # ------------------------------------------------------------

        feature_variants = feature_name_variants(
            feature
        )

        for finding in source_findings:

            if finding.context != "FEATURE_GENERATION":
                continue

            expression_lower = (
                finding.source_expression.lower()
            )

            if not any(
                variant in expression_lower
                for variant in feature_variants
            ):
                continue

            if finding.finding_type == "NEGATIVE_SHIFT":

                record.has_negative_shift = True
                record.has_shift = True

            if finding.finding_type == "CENTERED_ROLLING":

                record.has_centered_rolling = True
                record.has_rolling = True

            if finding.finding_type in {
                "BACKWARD_FILL",
            }:

                record.has_forward_operation = True

            record.feature_context_evidence = True

        # ------------------------------------------------------------
        # Normalize unique lineage fields.
        # ------------------------------------------------------------

        record.source_files = sorted(
            set(record.source_files)
        )

        record.source_lines = sorted(
            set(record.source_lines)
        )

        record.source_operations = sorted(
            set(record.source_operations)
        )

        record.candidate_source_columns = sorted(
            set(record.candidate_source_columns)
        )

        record.source_expressions = list(
            dict.fromkeys(
                record.source_expressions
            )
        )

        # ------------------------------------------------------------
        # Determine temporal direction.
        # ------------------------------------------------------------

        if record.has_negative_shift:

            record.temporal_direction = (
                "FUTURE"
            )

        elif record.has_centered_rolling:

            record.temporal_direction = (
                "BOTH_SIDES"
            )

        elif (
            record.has_shift
            or record.has_rolling
            or record.has_expanding
            or record.has_diff
            or record.has_pct_change
        ):

            record.temporal_direction = (
                "HISTORICAL_OR_UNKNOWN"
            )

        else:

            record.temporal_direction = (
                "UNKNOWN"
            )

        assess_feature_causality(
            record
        )

        records.append(
            record
        )

    return records


# ============================================================================
# SOURCE FINDING SUMMARY
# ============================================================================


def print_temporal_source_summary(
    source_findings: list[SourceFinding],
) -> None:

    print_section(
        "SOURCE TEMPORAL LINEAGE SUMMARY"
    )

    operation_counts: dict[
        str,
        int,
    ] = {}

    for finding in source_findings:

        operation_counts[
            finding.finding_type
        ] = (
            operation_counts.get(
                finding.finding_type,
                0,
            )
            + 1
        )

    for operation in sorted(
        operation_counts
    ):

        print_status(
            operation,
            operation_counts[operation],
        )

    target_context = sum(
        1
        for finding in source_findings
        if finding.target_context
    )

    feature_context = sum(
        1
        for finding in source_findings
        if finding.feature_context
    )

    future_context = sum(
        1
        for finding in source_findings
        if finding.temporal_direction
        in {
            "FUTURE",
            "BOTH_SIDES",
            "POTENTIALLY_FUTURE",
        }
    )

    print_status(
        "Target-context temporal findings",
        target_context,
    )

    print_status(
        "Feature-context temporal findings",
        feature_context,
    )

    print_status(
        "Future-oriented source findings",
        future_context,
    )


# ============================================================================
# ASSERTIONS
# ============================================================================


def run_final_assertions(
    records: list[FeatureLineageRecord],
    registered_features: list[str],
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    print_section("FINAL ASSERTIONS")

    print_pass(
        "Training dataset non-empty",
        not train.empty,
    )

    print_pass(
        "Validation dataset non-empty",
        not validation.empty,
    )

    print_pass(
        "Expected feature count",
        len(registered_features)
        == EXPECTED_FEATURE_COUNT,
    )

    print_pass(
        "Lineage row count equals feature count",
        len(records)
        == len(registered_features),
    )

    feature_names = [
        record.feature
        for record in records
    ]

    print_pass(
        "No duplicate registered features",
        len(feature_names)
        == len(set(feature_names)),
    )

    print_pass(
        "All audited features present",
        all(
            record.present_in_training
            and record.present_in_validation
            for record in records
        ),
    )

    print_pass(
        "Target not included as registered feature",
        TARGET_COLUMN not in set(
            registered_features
        ),
    )


# ============================================================================
# SUMMARY
# ============================================================================


def build_summary(
    records: list[FeatureLineageRecord],
    source_findings: list[SourceFinding],
    paths: dict[str, Path],
) -> AuditSummary:

    historical = [
        record
        for record in records
        if record.family == "historical"
    ]

    current_state = [
        record
        for record in records
        if record.family == "current_state"
    ]

    temporal_calendar = [
        record
        for record in records
        if record.family == "temporal_calendar"
    ]

    other = [
        record
        for record in records
        if record.family == "other"
    ]

    source_evidence = [
        record
        for record in records
        if record.source_evidence_count > 0
    ]

    no_source_evidence = [
        record
        for record in records
        if record.source_evidence_count == 0
    ]

    negative_shift = [
        record
        for record in records
        if record.has_negative_shift
    ]

    centered_rolling = [
        record
        for record in records
        if record.has_centered_rolling
    ]

    forward_operations = [
        record
        for record in records
        if record.has_forward_operation
    ]

    target_context_findings = sum(
        1
        for finding in source_findings
        if finding.target_context
    )

    feature_context_future_findings = sum(
        1
        for finding in source_findings
        if (
            finding.feature_context
            and finding.temporal_direction
            in {
                "FUTURE",
                "BOTH_SIDES",
                "POTENTIALLY_FUTURE",
            }
        )
    )

    unresolved_future_findings = sum(
        1
        for finding in source_findings
        if (
            finding.temporal_direction
            in {
                "FUTURE",
                "BOTH_SIDES",
                "POTENTIALLY_FUTURE",
            }
            and not finding.target_context
        )
    )

    confirmed_leakage = [
        record
        for record in records
        if record.production_verdict
        == "CONFIRMED_LEAKAGE"
    ]

    potential_leakage = [
        record
        for record in records
        if record.production_verdict
        == "POTENTIAL_LEAKAGE"
    ]

    causal_review = [
        record
        for record in records
        if record.production_verdict
        == "REQUIRES_CAUSAL_REVIEW"
    ]

    provisionally_safe = [
        record
        for record in records
        if record.production_verdict
        == "PROVISIONALLY_CAUSAL"
    ]

    if confirmed_leakage:

        verdict = (
            "FAIL_POTENTIAL_TEMPORAL_LEAKAGE"
        )

    elif potential_leakage:

        verdict = (
            "REVIEW_POTENTIAL_TEMPORAL_LEAKAGE"
        )

    elif unresolved_future_findings:

        verdict = (
            "PASS_WITH_UNRESOLVED_SOURCE_REVIEW"
        )

    elif causal_review:

        verdict = (
            "PASS_WITH_CAUSAL_REVIEW"
        )

    else:

        verdict = (
            "PASS"
        )

    return AuditSummary(
        repository_root=str(
            paths["repository_root"]
        ),
        registered_features=len(records),
        training_features=len(records),
        validation_features=len(records),
        source_files_scanned=0,
        source_findings=len(source_findings),
        historical_features=len(historical),
        current_state_features=len(current_state),
        temporal_calendar_features=len(
            temporal_calendar
        ),
        other_features=len(other),
        source_evidence_features=len(
            source_evidence
        ),
        no_source_evidence_features=len(
            no_source_evidence
        ),
        negative_shift_features=len(
            negative_shift
        ),
        centered_rolling_features=len(
            centered_rolling
        ),
        forward_operation_features=len(
            forward_operations
        ),
        target_context_findings=(
            target_context_findings
        ),
        feature_context_future_findings=(
            feature_context_future_findings
        ),
        unresolved_future_findings=(
            unresolved_future_findings
        ),
        confirmed_leakage_features=len(
            confirmed_leakage
        ),
        potential_leakage_features=len(
            potential_leakage
        ),
        causal_review_features=len(
            causal_review
        ),
        provisionally_safe_features=len(
            provisionally_safe
        ),
        verdict=verdict,
    )


# ============================================================================
# CSV WRITERS
# ============================================================================


def write_feature_csv(
    path: Path,
    records: list[FeatureLineageRecord],
) -> None:

    fieldnames = [
        "feature",
        "family",
        "present_in_training",
        "present_in_validation",
        "dtype_training",
        "dtype_validation",
        "null_count_training",
        "null_count_validation",
        "source_evidence_count",
        "source_files",
        "source_lines",
        "source_operations",
        "source_expressions",
        "candidate_source_columns",
        "has_shift",
        "has_negative_shift",
        "has_positive_shift",
        "has_rolling",
        "has_centered_rolling",
        "has_expanding",
        "has_diff",
        "has_pct_change",
        "has_forward_operation",
        "has_future_named_signal",
        "target_context_evidence",
        "feature_context_evidence",
        "temporal_direction",
        "causal_assessment",
        "production_verdict",
        "notes",
        
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

        for record in records:

            row = asdict(
                record
            )

            for field_name in [
                "source_files",
                "source_lines",
                "source_operations",
                "candidate_source_columns",
                "notes",
            ]:

                row[field_name] = json.dumps(
                    row[field_name]
                )

            writer.writerow(row)


def write_source_findings_csv(
    path: Path,
    findings: list[SourceFinding],
) -> None:

    fieldnames = [
        "file",
        "line",
        "finding_type",
        "context",
        "source_expression",
        "likely_context",
        "feature_candidates",
        "temporal_direction",
        "target_context",
        "feature_context",
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

        for finding in findings:

            row = asdict(
                finding
            )

            row[
                "feature_candidates"
            ] = json.dumps(
                row["feature_candidates"]
            )

            writer.writerow(row)


def write_summary_csv(
    path: Path,
    summary: AuditSummary,
) -> None:

    data = asdict(
        summary
    )

    rows = [
        {
            "metric": key,
            "value": value,
        }
        for key, value in data.items()
    ]

    pd.DataFrame(
        rows
    ).to_csv(
        path,
        index=False,
    )


# ============================================================================
# JSON REPORT
# ============================================================================


def write_json_report(
    path: Path,
    summary: AuditSummary,
    records: list[FeatureLineageRecord],
    source_findings: list[SourceFinding],
    paths: dict[str, Path],
) -> None:

    report = {
        "audit_name": (
            "Birmingham XGBoost Feature Lineage Audit"
        ),
        "generated_at": datetime.now(timezone.utc).isoformat()
        + "Z",
        "production_contract": {
            "prediction_timestamp": "T",
            "forecast_horizon_minutes": (
                PRODUCTION_HORIZON_MINUTES
            ),
            "feature_information_boundary": (
                "available_at_or_before_T"
            ),
        },
        "audit_policy": {
            "train_loaded": True,
            "validation_loaded": True,
            "test_loaded": False,
            "xgboost_trained": False,
            "pipeline_rebuilt": False,
            "persisted_datasets_modified": False,
        },
        "paths": {
            key: str(value)
            for key, value in paths.items()
        },
        "summary": asdict(
            summary
        ),
        "features": [
            asdict(record)
            for record in records
        ],
        "source_findings": [
            asdict(finding)
            for finding in source_findings
        ],
    }

    path.write_text(
        json.dumps(
            report,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )


# ============================================================================
# CONSOLE REPORT
# ============================================================================


def print_feature_family_summary(
    records: list[FeatureLineageRecord],
) -> None:

    print_section(
        "FEATURE FAMILY SUMMARY"
    )

    families = {
        "historical": 0,
        "current_state": 0,
        "temporal_calendar": 0,
        "other": 0,
    }

    for record in records:

        families[
            record.family
        ] += 1

    print_status(
        "Historical features",
        families["historical"],
    )

    print_status(
        "Current-state features",
        families["current_state"],
    )

    print_status(
        "Temporal/calendar features",
        families["temporal_calendar"],
    )

    print_status(
        "Other features",
        families["other"],
    )


def print_lineage_summary(
    records: list[FeatureLineageRecord],
) -> None:

    print_section(
        "FEATURE LINEAGE SUMMARY"
    )

    source_evidence = sum(
        1
        for record in records
        if record.source_evidence_count > 0
    )

    no_source_evidence = sum(
        1
        for record in records
        if record.source_evidence_count == 0
    )

    negative_shift = sum(
        1
        for record in records
        if record.has_negative_shift
    )

    centered_rolling = sum(
        1
        for record in records
        if record.has_centered_rolling
    )

    forward = sum(
        1
        for record in records
        if record.has_forward_operation
    )

    provisionally_safe = sum(
        1
        for record in records
        if record.production_verdict
        == "PROVISIONALLY_CAUSAL"
    )

    potential = sum(
        1
        for record in records
        if record.production_verdict
        == "POTENTIAL_LEAKAGE"
    )

    review = sum(
        1
        for record in records
        if record.production_verdict
        == "REQUIRES_CAUSAL_REVIEW"
    )

    print_status(
        "Features with source evidence",
        source_evidence,
    )

    print_status(
        "Features without source evidence",
        no_source_evidence,
    )

    print_status(
        "Negative-shift features",
        negative_shift,
    )

    print_status(
        "Centered-rolling features",
        centered_rolling,
    )

    print_status(
        "Forward-operation features",
        forward,
    )

    print_status(
        "Provisionally causal features",
        provisionally_safe,
    )

    print_status(
        "Potential leakage features",
        potential,
    )

    print_status(
        "Features requiring causal review",
        review,
    )


def print_suspicious_features(
    records: list[FeatureLineageRecord],
) -> None:

    print_section(
        "SUSPICIOUS / REVIEW FEATURES"
    )

    suspicious = [
        record
        for record in records
        if (
            record.has_negative_shift
            or record.has_centered_rolling
            or record.has_forward_operation
            or record.production_verdict
            == "POTENTIAL_LEAKAGE"
        )
    ]

    if not suspicious:

        print(
            "No registered feature was automatically "
            "classified as potential temporal leakage."
        )

        return

    for record in suspicious:

        print()
        print(
            f"FEATURE: {record.feature}"
        )

        print(
            f"  Family              : {record.family}"
        )

        print(
            f"  Temporal direction  : "
            f"{record.temporal_direction}"
        )

        print(
            f"  Negative shift      : "
            f"{record.has_negative_shift}"
        )

        print(
            f"  Centered rolling    : "
            f"{record.has_centered_rolling}"
        )

        print(
            f"  Forward operation   : "
            f"{record.has_forward_operation}"
        )

        print(
            f"  Verdict             : "
            f"{record.production_verdict}"
        )


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:

    print_header(
        "SMARTPARK AI - BIRMINGHAM XGBOOST "
        "FEATURE LINEAGE AUDIT"
    )

    print()
    print("Target:")
    print(
        f"  {TARGET_COLUMN}"
    )

    print()
    print("Production prediction contract:")
    print("  Prediction timestamp = T")
    print("  Forecast horizon     = T + 30 minutes")
    print(
        "  Feature information  = available at or before T"
    )

    print()
    print("Audit policy:")
    print(
        "  Trace all registered model features to source code"
    )
    print(
        "  Inspect historical / lag / rolling lineage"
    )
    print(
        "  Identify source columns and temporal operations"
    )
    print(
        "  Distinguish target-generation future logic"
    )
    print(
        "  from feature-generation future logic"
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

    paths = resolve_paths()

    try:

        # ------------------------------------------------------------
        # Dataset validation.
        # ------------------------------------------------------------

        validate_dataset_files(
            paths
        )

        # ------------------------------------------------------------
        # Manifest.
        # ------------------------------------------------------------

        manifest = load_manifest(
            paths["manifest"]
        )

        # ------------------------------------------------------------
        # Datasets.
        # ------------------------------------------------------------

        train, validation = (
            load_persisted_datasets(
                paths
            )
        )

        # ------------------------------------------------------------
        # Feature registry.
        # ------------------------------------------------------------

        registered_features = (
            validate_feature_registry(
                manifest,
                train,
                validation,
            )
        )

        # ------------------------------------------------------------
        # Target.
        # ------------------------------------------------------------

        validate_target_contract(
            train,
            validation,
        )

        # ------------------------------------------------------------
        # Source discovery.
        # ------------------------------------------------------------

        print_section(
            "ML SOURCE CODE DISCOVERY"
        )

        source_files = discover_python_sources(
            paths["source_root"]
        )

        print_status(
            "ML source root",
            paths["source_root"],
        )

        print_status(
            "ML source files scanned",
            len(source_files),
        )

        # ------------------------------------------------------------
        # Source scan.
        # ------------------------------------------------------------

        print_section(
            "SOURCE TEMPORAL / FEATURE LINEAGE SCAN"
        )

        source_findings, feature_findings = (
            scan_source_files(
                source_files,
                registered_features,
            )
        )

        print_status(
            "Total source findings",
            len(source_findings),
        )

        # ------------------------------------------------------------
        # AST/source summary.
        # ------------------------------------------------------------

        print_temporal_source_summary(
            source_findings
        )

        # ------------------------------------------------------------
        # Feature lineage.
        # ------------------------------------------------------------

        records = build_feature_lineage(
            registered_features,
            train,
            validation,
            feature_findings,
            source_findings,
        )

        print_feature_family_summary(
            records
        )

        print_lineage_summary(
            records
        )

        # ------------------------------------------------------------
        # Assertions.
        # ------------------------------------------------------------

        run_final_assertions(
            records,
            registered_features,
            train,
            validation,
        )

        # ------------------------------------------------------------
        # Suspicious features.
        # ------------------------------------------------------------

        print_suspicious_features(
            records
        )

        # ------------------------------------------------------------
        # Summary.
        # ------------------------------------------------------------

        summary = build_summary(
            records,
            source_findings,
            paths,
        )

        summary.source_files_scanned = (
            len(source_files)
        )

        # ------------------------------------------------------------
        # Final result.
        # ------------------------------------------------------------

        print_section(
            "FINAL FEATURE LINEAGE RESULT"
        )

        print_status(
            "Features audited",
            summary.registered_features,
        )

        print_status(
            "Historical features",
            summary.historical_features,
        )

        print_status(
            "Current-state features",
            summary.current_state_features,
        )

        print_status(
            "Temporal/calendar features",
            summary.temporal_calendar_features,
        )

        print_status(
            "Other features",
            summary.other_features,
        )

        print_status(
            "Features with source evidence",
            summary.source_evidence_features,
        )

        print_status(
            "Features without source evidence",
            summary.no_source_evidence_features,
        )

        print_status(
            "Negative-shift features",
            summary.negative_shift_features,
        )

        print_status(
            "Centered-rolling features",
            summary.centered_rolling_features,
        )

        print_status(
            "Forward-operation features",
            summary.forward_operation_features,
        )

        print_status(
            "Target-context temporal findings",
            summary.target_context_findings,
        )

        print_status(
            "Feature-context future findings",
            summary.feature_context_future_findings,
        )

        print_status(
            "Unresolved future findings",
            summary.unresolved_future_findings,
        )

        print_status(
            "Potential leakage features",
            summary.potential_leakage_features,
        )

        print_status(
            "Features requiring causal review",
            summary.causal_review_features,
        )

        print_status(
            "Provisionally causal features",
            summary.provisionally_safe_features,
        )

        print()
        print(
            "PRODUCTION FEATURE LINEAGE VERDICT : "
            f"{summary.verdict}"
        )

        print()
        print(
            "Interpretation:"
        )

        if summary.confirmed_leakage_features > 0:

            print(
                "  - One or more features contain confirmed "
                "future-information signals."
            )

        elif summary.potential_leakage_features > 0:

            print(
                "  - One or more features require immediate "
                "temporal leakage investigation."
            )

        else:

            print(
                "  - No registered feature was automatically "
                "identified as temporal leakage."
            )

        if summary.causal_review_features > 0:

            print(
                "  - Features remain conditional where source "
                "lineage does not formally prove availability "
                "at prediction timestamp T."
            )

        if summary.unresolved_future_findings > 0:

            print(
                "  - Future-oriented source constructs remain "
                "outside clearly attributable target-generation "
                "logic and require engineering review."
            )

        # ------------------------------------------------------------
        # Persist outputs.
        # ------------------------------------------------------------

        print_section(
            "PERSISTING FEATURE LINEAGE RESULTS"
        )

        output_dir = paths["output"]

        output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        json_path = (
            output_dir
            / "birmingham_xgboost_feature_lineage.json"
        )

        feature_csv_path = (
            output_dir
            / "birmingham_xgboost_feature_lineage_features.csv"
        )

        source_csv_path = (
            output_dir
            / "birmingham_xgboost_feature_lineage_source_findings.csv"
        )

        summary_csv_path = (
            output_dir
            / "birmingham_xgboost_feature_lineage_summary.csv"
        )

        write_json_report(
            json_path,
            summary,
            records,
            source_findings,
            paths,
        )

        write_feature_csv(
            feature_csv_path,
            records,
        )

        write_source_findings_csv(
            source_csv_path,
            source_findings,
        )

        write_summary_csv(
            summary_csv_path,
            summary,
        )

        print_status(
            "Output directory",
            output_dir,
        )

        print_status(
            "JSON report",
            json_path,
        )

        print_status(
            "CSV feature lineage",
            feature_csv_path,
        )

        print_status(
            "CSV source findings",
            source_csv_path,
        )

        print_status(
            "CSV summary",
            summary_csv_path,
        )

        # ------------------------------------------------------------
        # Completion.
        # ------------------------------------------------------------

        print()

        if summary.verdict.startswith(
            "FAIL"
        ):

            print_header(
                "BIRMINGHAM FEATURE LINEAGE AUDIT "
                "FAILED"
            )

            print(
                "Potential temporal leakage was identified."
            )

            print(
                "DO NOT proceed to production approval "
                "until the affected feature lineage is reviewed."
            )

            return 2

        print_header(
            "BIRMINGHAM FEATURE LINEAGE AUDIT "
            "COMPLETED WITH REVIEW"
        )

        print(
            "No registered feature was automatically "
            "confirmed as future leakage."
        )

        print(
            "Features without formal causal lineage remain "
            "conditional for production approval."
        )

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
            "Feature lineage audit is ready for engineering review."
        )

        return 0

    except FeatureLineageAuditError as exc:

        print()
        print_header(
            "BIRMINGHAM FEATURE LINEAGE AUDIT FAILED"
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

        print()
        print_header(
            "BIRMINGHAM FEATURE LINEAGE AUDIT FAILED"
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
    raise SystemExit(
        main()
    )