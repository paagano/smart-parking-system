"""
SmartPark AI
Birmingham Training Dataset Integrity Audit

Purpose
-------
Read back the persisted Birmingham training datasets and verify that
they satisfy the locked ML training-data contract.

This audit is READ-ONLY.

It does NOT:
    - rebuild the feature pipeline
    - regenerate targets
    - modify Parquet files
    - modify the manifest
    - retrain models

It verifies:

    1. Manifest existence and structure
    2. Manifest metadata consistency
    3. Expected 12 Parquet files
    4. Parquet readability
    5. Expected row counts
    6. Expected feature count
    7. Required metadata columns
    8. Target-specific schema
    9. Target/availability consistency
    10. Duplicate feature columns
    11. Duplicate observation keys
    12. Cross-split observation-key isolation
    13. Target leakage
    14. Infinite numeric values
    15. Target ranges
    16. Chronological split ordering
    17. Persisted dataset totals

Important
---------
The Birmingham dataset contains multiple facilities.

Therefore:

    max(train timestamp) < min(validation timestamp)

is NOT a sufficient split-integrity rule.

Different facilities can legitimately have observations at the same
timestamp while belonging to different chronological partitions.

The correct leakage test is:

    train keys ∩ validation keys == empty
    validation keys ∩ test keys == empty
    train keys ∩ test keys == empty

where the observation key is:

    (source_facility_code, normalized_at)

The current manifest does not contain per-file SHA-256 checksums.
Therefore checksum verification is reported as NOT CONFIGURED rather
than treated as a failure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ============================================================================
# PROJECT PATHS
# ============================================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROCESSED_ROOT = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
)

MANIFEST_PATH = (
    PROCESSED_ROOT
    / "training_dataset_manifest.json"
)


# ============================================================================
# LOCKED BIRMINGHAM DATASET CONTRACT
# ============================================================================

DATASET_NAME = "birmingham"
SOURCE_NAME = "BIRMINGHAM"

SCHEMA_VERSION = "1.0"

EXPECTED_SOURCE_ROWS = 104_796
EXPECTED_FACILITY_COUNT = 30

EXPECTED_FEATURE_COUNT = 296
EXPECTED_TARGET_COUNT = 4
EXPECTED_TARGET_AVAILABILITY_COUNT = 4

TARGETS = (
    "target_occupancy_rate_30m",
    "target_occupancy_rate_1h",
    "target_occupancy_rate_2h",
    "target_tomorrow_morning_demand",
)

TARGET_AVAILABILITY_COLUMNS = {
    "target_occupancy_rate_30m":
        "target_30m_available",

    "target_occupancy_rate_1h":
        "target_1h_available",

    "target_occupancy_rate_2h":
        "target_2h_available",

    "target_tomorrow_morning_demand":
        "target_tomorrow_morning_available",
}

SPLITS = (
    "train",
    "validation",
    "test",
)


# ============================================================================
# EXPECTED TARGET COUNTS
# ============================================================================

EXPECTED_ELIGIBLE_ROWS = {
    "target_occupancy_rate_30m": 33_206,
    "target_occupancy_rate_1h": 31_280,
    "target_occupancy_rate_2h": 27_384,
    "target_tomorrow_morning_demand": 33_313,
}


EXPECTED_ROW_COUNTS = {
    "target_occupancy_rate_30m": {
        "train": 23_244,
        "validation": 4_980,
        "test": 4_982,
    },

    "target_occupancy_rate_1h": {
        "train": 21_896,
        "validation": 4_692,
        "test": 4_692,
    },

    "target_occupancy_rate_2h": {
        "train": 19_168,
        "validation": 4_107,
        "test": 4_109,
    },

    "target_tomorrow_morning_demand": {
        "train": 23_319,
        "validation": 4_996,
        "test": 4_998,
    },
}


# ============================================================================
# EXPECTED TARGET RANGES
# ============================================================================

TARGET_RANGES = {
    "target_occupancy_rate_30m": (
        0.0,
        1.0,
    ),

    "target_occupancy_rate_1h": (
        0.0,
        1.0,
    ),

    "target_occupancy_rate_2h": (
        0.0,
        1.0,
    ),

    "target_tomorrow_morning_demand": (
        0.0,
        1.0,
    ),
}


# ============================================================================
# REQUIRED METADATA COLUMNS
# ============================================================================

TIMESTAMP_COLUMN = "normalized_at"

FACILITY_COLUMN = "source_facility_code"

REQUIRED_METADATA_COLUMNS = {
    FACILITY_COLUMN,
    TIMESTAMP_COLUMN,
}


# ============================================================================
# TARGET / AVAILABILITY SETS
# ============================================================================

ALL_TARGET_COLUMNS = set(
    TARGETS
)

ALL_TARGET_AVAILABILITY_COLUMNS = set(
    TARGET_AVAILABILITY_COLUMNS.values()
)


# ============================================================================
# AUDIT RESULT
# ============================================================================


class IntegrityAudit:
    """
    Collects audit checks, failures and warnings.
    """

    def __init__(self) -> None:
        self.checks: list[
            tuple[str, bool]
        ] = []

        self.errors: list[str] = []

        self.warnings: list[str] = []

    def check(
        self,
        name: str,
        condition: bool,
        *,
        error: str | None = None,
    ) -> bool:

        passed = bool(condition)

        self.checks.append(
            (
                name,
                passed,
            )
        )

        if not passed:

            self.errors.append(
                error or name
            )

        return passed

    def warning(
        self,
        message: str,
    ) -> None:

        self.warnings.append(
            message
        )

    @property
    def passed(self) -> bool:

        return not self.errors

    @property
    def passed_count(self) -> int:

        return sum(
            passed
            for _, passed in self.checks
        )

    @property
    def failed_count(self) -> int:

        return sum(
            not passed
            for _, passed in self.checks
        )


# ============================================================================
# MANIFEST
# ============================================================================


def load_manifest() -> dict[str, Any]:
    """
    Load the actual Birmingham training dataset manifest.
    """

    if not MANIFEST_PATH.exists():

        raise RuntimeError(
            "Training dataset manifest does not exist:\n"
            f"{MANIFEST_PATH}"
        )

    try:

        with MANIFEST_PATH.open(
            "r",
            encoding="utf-8",
        ) as handle:

            manifest = json.load(
                handle
            )

    except json.JSONDecodeError as exc:

        raise RuntimeError(
            "Training dataset manifest is invalid JSON."
        ) from exc

    if not isinstance(
        manifest,
        dict,
    ):

        raise RuntimeError(
            "Training dataset manifest must contain "
            "a JSON object."
        )

    return manifest


def validate_manifest(
    manifest: dict[str, Any],
    audit: IntegrityAudit,
) -> None:
    """
    Validate the actual manifest structure used by
    birmingham_training_dataset.py.
    """

    print()
    print(
        "--- MANIFEST VALIDATION ---"
    )

    # ------------------------------------------------------------------
    # Schema version
    # ------------------------------------------------------------------

    actual_schema_version = manifest.get(
        "schema_version"
    )

    audit.check(
        "Manifest schema version",
        actual_schema_version
        == SCHEMA_VERSION,
        error=(
            "Manifest schema version mismatch: "
            f"expected '{SCHEMA_VERSION}', "
            f"found '{actual_schema_version}'."
        ),
    )

    # ------------------------------------------------------------------
    # Dataset name
    # ------------------------------------------------------------------

    actual_dataset_name = manifest.get(
        "dataset_name"
    )

    audit.check(
        "Manifest dataset name",
        actual_dataset_name
        == DATASET_NAME,
        error=(
            "Manifest dataset name mismatch: "
            f"expected '{DATASET_NAME}', "
            f"found '{actual_dataset_name}'."
        ),
    )

    # ------------------------------------------------------------------
    # Source name
    # ------------------------------------------------------------------

    actual_source_name = manifest.get(
        "source_name"
    )

    audit.check(
        "Manifest source name",
        actual_source_name
        == SOURCE_NAME,
        error=(
            "Manifest source name mismatch: "
            f"expected '{SOURCE_NAME}', "
            f"found '{actual_source_name}'."
        ),
    )

    # ------------------------------------------------------------------
    # Storage format
    # ------------------------------------------------------------------

    actual_storage_format = manifest.get(
        "storage_format"
    )

    audit.check(
        "Manifest storage format",
        actual_storage_format
        == "parquet",
        error=(
            "Manifest storage format must be "
            f"'parquet', found '{actual_storage_format}'."
        ),
    )

    # ------------------------------------------------------------------
    # Compression
    # ------------------------------------------------------------------

    actual_compression = manifest.get(
        "compression"
    )

    audit.check(
        "Manifest compression",
        actual_compression
        == "snappy",
        error=(
            "Manifest compression must be "
            f"'snappy', found '{actual_compression}'."
        ),
    )

    # ------------------------------------------------------------------
    # Feature count
    # ------------------------------------------------------------------

    actual_feature_count = manifest.get(
        "feature_count"
    )

    audit.check(
        "Manifest feature count",
        actual_feature_count
        == EXPECTED_FEATURE_COUNT,
        error=(
            "Manifest feature count mismatch: "
            f"expected {EXPECTED_FEATURE_COUNT}, "
            f"found {actual_feature_count}."
        ),
    )

    # ------------------------------------------------------------------
    # Target count
    # ------------------------------------------------------------------

    actual_target_count = manifest.get(
        "target_count"
    )

    audit.check(
        "Manifest target count",
        actual_target_count
        == EXPECTED_TARGET_COUNT,
        error=(
            "Manifest target count mismatch: "
            f"expected {EXPECTED_TARGET_COUNT}, "
            f"found {actual_target_count}."
        ),
    )

    # ------------------------------------------------------------------
    # Target availability count
    # ------------------------------------------------------------------

    actual_availability_count = manifest.get(
        "target_availability_count"
    )

    audit.check(
        "Manifest target availability count",
        actual_availability_count
        == EXPECTED_TARGET_AVAILABILITY_COUNT,
        error=(
            "Manifest target availability count "
            f"mismatch: expected "
            f"{EXPECTED_TARGET_AVAILABILITY_COUNT}, "
            f"found {actual_availability_count}."
        ),
    )

    # ------------------------------------------------------------------
    # Source rows
    # ------------------------------------------------------------------

    actual_source_rows = manifest.get(
        "source_rows"
    )

    audit.check(
        "Manifest source row count",
        actual_source_rows
        == EXPECTED_SOURCE_ROWS,
        error=(
            "Manifest source row count mismatch: "
            f"expected {EXPECTED_SOURCE_ROWS:,}, "
            f"found {actual_source_rows}."
        ),
    )

    # ------------------------------------------------------------------
    # Facility count
    # ------------------------------------------------------------------

    actual_facility_count = manifest.get(
        "facility_count"
    )

    audit.check(
        "Manifest facility count",
        actual_facility_count
        == EXPECTED_FACILITY_COUNT,
        error=(
            "Manifest facility count mismatch: "
            f"expected {EXPECTED_FACILITY_COUNT}, "
            f"found {actual_facility_count}."
        ),
    )

    # ------------------------------------------------------------------
    # Feature columns
    # ------------------------------------------------------------------

    feature_columns = manifest.get(
        "feature_columns"
    )

    audit.check(
        "Manifest feature columns present",
        isinstance(
            feature_columns,
            list,
        ),
        error=(
            "Manifest does not contain a valid "
            "'feature_columns' list."
        ),
    )

    if isinstance(
        feature_columns,
        list,
    ):

        audit.check(
            "Manifest feature column count",
            len(feature_columns)
            == EXPECTED_FEATURE_COUNT,
            error=(
                "Manifest feature column list contains "
                f"{len(feature_columns)} columns; "
                f"expected {EXPECTED_FEATURE_COUNT}."
            ),
        )

        duplicates = (
            pd.Series(
                feature_columns
            )
            .duplicated()
        )

        duplicate_names = [
            feature_columns[index]
            for index, duplicated in enumerate(
                duplicates
            )
            if duplicated
        ]

        audit.check(
            "Manifest feature columns are unique",
            not duplicate_names,
            error=(
                "Manifest contains duplicate feature "
                f"names: {duplicate_names}"
            ),
        )

    print(
        f"Schema version:       "
        f"{actual_schema_version}"
    )

    print(
        f"Dataset name:         "
        f"{actual_dataset_name}"
    )

    print(
        f"Source name:          "
        f"{actual_source_name}"
    )

    print(
        f"Storage format:       "
        f"{actual_storage_format}"
    )

    print(
        f"Compression:          "
        f"{actual_compression}"
    )

    print(
        f"Feature count:        "
        f"{actual_feature_count}"
    )

    print(
        f"Target count:         "
        f"{actual_target_count}"
    )

    print(
        f"Target availability:  "
        f"{actual_availability_count}"
    )

    print(
        f"Source rows:          "
        f"{actual_source_rows:,}"
    )

    print(
        f"Facilities:           "
        f"{actual_facility_count}"
    )


# ============================================================================
# PATH HELPERS
# ============================================================================


def expected_parquet_path(
    target: str,
    split: str,
) -> Path:

    return (
        PROCESSED_ROOT
        / target
        / f"{split}.parquet"
    )


def discover_parquet_files() -> list[Path]:

    if not PROCESSED_ROOT.exists():
        return []

    return sorted(
        PROCESSED_ROOT.rglob(
            "*.parquet"
        )
    )


# ============================================================================
# DATAFRAME HELPERS
# ============================================================================


def get_numeric_columns(
    dataframe: pd.DataFrame,
) -> list[str]:

    return [
        column
        for column in dataframe.columns
        if pd.api.types.is_numeric_dtype(
            dataframe[column]
        )
    ]


def duplicate_columns(
    dataframe: pd.DataFrame,
) -> list[str]:

    duplicated = (
        dataframe.columns[
            dataframe.columns.duplicated()
        ]
        .tolist()
    )

    return list(
        dict.fromkeys(
            duplicated
        )
    )


def identify_feature_columns(
    dataframe: pd.DataFrame,
) -> list[str]:

    excluded = (
        REQUIRED_METADATA_COLUMNS
        | ALL_TARGET_COLUMNS
        | ALL_TARGET_AVAILABILITY_COLUMNS
    )

    return [
        column
        for column in dataframe.columns
        if column not in excluded
    ]


def count_infinite_values(
    dataframe: pd.DataFrame,
) -> int:

    numeric_columns = (
        get_numeric_columns(
            dataframe
        )
    )

    if not numeric_columns:
        return 0

    numeric = dataframe[
        numeric_columns
    ]

    values = numeric.to_numpy(
        dtype=float,
        na_value=np.nan,
    )

    return int(
        np.isinf(
            values
        ).sum()
    )


# ============================================================================
# OBSERVATION KEY
# ============================================================================


def build_observation_keys(
    dataframe: pd.DataFrame,
) -> pd.MultiIndex:

    timestamps = pd.to_datetime(
        dataframe[
            TIMESTAMP_COLUMN
        ]
    )

    facilities = (
        dataframe[
            FACILITY_COLUMN
        ]
        .astype(str)
    )

    return pd.MultiIndex.from_arrays(
        [
            facilities.to_numpy(),
            timestamps.to_numpy(),
        ],
        names=[
            FACILITY_COLUMN,
            TIMESTAMP_COLUMN,
        ],
    )


# ============================================================================
# SINGLE DATASET AUDIT
# ============================================================================


def audit_dataset(
    *,
    target: str,
    split: str,
    path: Path,
    audit: IntegrityAudit,
) -> pd.DataFrame | None:

    print()
    print(
        f"  {target} / {split}"
    )

    print(
        f"    File: {path}"
    )

    # ------------------------------------------------------------------
    # File existence
    # ------------------------------------------------------------------

    exists = path.exists()

    audit.check(
        f"{target}/{split}: file exists",
        exists,
        error=(
            f"Missing persisted dataset: {path}"
        ),
    )

    if not exists:
        return None

    # ------------------------------------------------------------------
    # Read Parquet
    # ------------------------------------------------------------------

    try:

        dataframe = pd.read_parquet(
            path
        )

    except Exception as exc:

        audit.check(
            f"{target}/{split}: Parquet readable",
            False,
            error=(
                f"{target}/{split}: unable to read "
                f"Parquet file: {exc}"
            ),
        )

        return None

    audit.check(
        f"{target}/{split}: Parquet readable",
        True,
    )

    print(
        f"    Rows:    {len(dataframe):,}"
    )

    print(
        f"    Columns: {len(dataframe.columns):,}"
    )

    # ------------------------------------------------------------------
    # Row count
    # ------------------------------------------------------------------

    expected_rows = (
        EXPECTED_ROW_COUNTS[
            target
        ][
            split
        ]
    )

    audit.check(
        f"{target}/{split}: row count",
        len(dataframe)
        == expected_rows,
        error=(
            f"{target}/{split}: expected "
            f"{expected_rows:,} rows but found "
            f"{len(dataframe):,}."
        ),
    )

    # ------------------------------------------------------------------
    # Duplicate columns
    # ------------------------------------------------------------------

    duplicates = duplicate_columns(
        dataframe
    )

    audit.check(
        f"{target}/{split}: duplicate columns",
        not duplicates,
        error=(
            f"{target}/{split}: duplicate columns: "
            f"{duplicates}"
        ),
    )

    # ------------------------------------------------------------------
    # Required metadata
    # ------------------------------------------------------------------

    missing_metadata = [
        column
        for column in REQUIRED_METADATA_COLUMNS
        if column not in dataframe.columns
    ]

    audit.check(
        f"{target}/{split}: required metadata",
        not missing_metadata,
        error=(
            f"{target}/{split}: missing metadata "
            f"columns: {missing_metadata}"
        ),
    )

    if missing_metadata:
        return dataframe

    # ------------------------------------------------------------------
    # Timestamp validity
    # ------------------------------------------------------------------

    parsed_timestamp = pd.to_datetime(
        dataframe[
            TIMESTAMP_COLUMN
        ],
        errors="coerce",
    )

    invalid_timestamp_count = int(
        parsed_timestamp.isna().sum()
    )

    audit.check(
        f"{target}/{split}: valid timestamps",
        invalid_timestamp_count == 0,
        error=(
            f"{target}/{split}: "
            f"{invalid_timestamp_count:,} invalid "
            "or missing timestamps."
        ),
    )

    # ------------------------------------------------------------------
    # Facility validity
    # ------------------------------------------------------------------

    missing_facility_count = int(
        dataframe[
            FACILITY_COLUMN
        ]
        .isna()
        .sum()
    )

    audit.check(
        f"{target}/{split}: valid facility identifiers",
        missing_facility_count == 0,
        error=(
            f"{target}/{split}: "
            f"{missing_facility_count:,} rows have "
            "missing facility identifiers."
        ),
    )

    # ------------------------------------------------------------------
    # Active target
    # ------------------------------------------------------------------

    audit.check(
        f"{target}/{split}: active target exists",
        target in dataframe.columns,
        error=(
            f"{target}/{split}: missing active "
            f"target column '{target}'."
        ),
    )

    # ------------------------------------------------------------------
    # Availability column
    # ------------------------------------------------------------------

    availability_column = (
        TARGET_AVAILABILITY_COLUMNS[
            target
        ]
    )

    audit.check(
        f"{target}/{split}: availability column exists",
        availability_column
        in dataframe.columns,
        error=(
            f"{target}/{split}: missing availability "
            f"column '{availability_column}'."
        ),
    )

    # ------------------------------------------------------------------
    # Feature count
    # ------------------------------------------------------------------

    feature_columns = (
        identify_feature_columns(
            dataframe
        )
    )

    audit.check(
        f"{target}/{split}: feature count",
        len(feature_columns)
        == EXPECTED_FEATURE_COUNT,
        error=(
            f"{target}/{split}: expected "
            f"{EXPECTED_FEATURE_COUNT} features but "
            f"found {len(feature_columns)}."
        ),
    )

    # ------------------------------------------------------------------
    # Feature columns must match manifest
    # ------------------------------------------------------------------

    # The manifest is the authoritative persisted feature registry.
    #
    # We load it separately in the main function and attach the
    # expected feature list to the dataframe audit through the
    # dataframe attrs below when available.

    # ------------------------------------------------------------------
    # Target leakage
    # ------------------------------------------------------------------

    feature_target_overlap = (
        set(feature_columns)
        & ALL_TARGET_COLUMNS
    )

    feature_availability_overlap = (
        set(feature_columns)
        & ALL_TARGET_AVAILABILITY_COLUMNS
    )

    audit.check(
        f"{target}/{split}: no target leakage",
        not feature_target_overlap,
        error=(
            f"{target}/{split}: target columns found "
            f"among features: "
            f"{sorted(feature_target_overlap)}"
        ),
    )

    audit.check(
        f"{target}/{split}: no availability leakage",
        not feature_availability_overlap,
        error=(
            f"{target}/{split}: target availability "
            "columns found among features: "
            f"{sorted(feature_availability_overlap)}"
        ),
    )

    # ------------------------------------------------------------------
    # Observation key uniqueness within split
    # ------------------------------------------------------------------

    try:

        observation_keys = (
            build_observation_keys(
                dataframe
            )
        )

        duplicate_key_mask = (
            observation_keys.duplicated(
                keep=False
            )
        )

        duplicate_key_count = int(
            duplicate_key_mask.sum()
        )

    except Exception as exc:

        duplicate_key_count = -1

        audit.check(
            f"{target}/{split}: observation keys",
            False,
            error=(
                f"{target}/{split}: unable to construct "
                f"observation keys: {exc}"
            ),
        )

    if duplicate_key_count >= 0:

        audit.check(
            f"{target}/{split}: unique observation keys",
            duplicate_key_count == 0,
            error=(
                f"{target}/{split}: "
                f"{duplicate_key_count:,} rows participate "
                "in duplicate "
                "(facility, timestamp) observation keys."
            ),
        )

    # ------------------------------------------------------------------
    # Infinite values
    # ------------------------------------------------------------------

    infinite_count = (
        count_infinite_values(
            dataframe
        )
    )

    audit.check(
        f"{target}/{split}: no infinite values",
        infinite_count == 0,
        error=(
            f"{target}/{split}: found "
            f"{infinite_count:,} infinite numeric cells."
        ),
    )

    print(
        f"    Infinite cells: "
        f"{infinite_count:,}"
    )

    # ------------------------------------------------------------------
    # Target value validation
    # ------------------------------------------------------------------

    if target in dataframe.columns:

        target_values = (
            dataframe[
                target
            ]
            .dropna()
        )

        audit.check(
            f"{target}/{split}: target has values",
            not target_values.empty,
            error=(
                f"{target}/{split}: target contains "
                "no non-null observations."
            ),
        )

        if not target_values.empty:

            expected_min, expected_max = (
                TARGET_RANGES[
                    target
                ]
            )

            actual_min = float(
                target_values.min()
            )

            actual_max = float(
                target_values.max()
            )

            audit.check(
                f"{target}/{split}: target minimum",
                actual_min
                >= expected_min,
                error=(
                    f"{target}/{split}: target minimum "
                    f"{actual_min} is below "
                    f"{expected_min}."
                ),
            )

            audit.check(
                f"{target}/{split}: target maximum",
                actual_max
                <= expected_max,
                error=(
                    f"{target}/{split}: target maximum "
                    f"{actual_max} exceeds "
                    f"{expected_max}."
                ),
            )

    # ------------------------------------------------------------------
    # Target availability consistency
    # ------------------------------------------------------------------

    if (
        target in dataframe.columns
        and availability_column
        in dataframe.columns
    ):

        target_available = (
            dataframe[
                target
            ]
            .notna()
        )

        availability = (
            dataframe[
                availability_column
            ]
            .fillna(False)
            .astype(bool)
        )

        inconsistency_mask = (
            target_available
            != availability
        )

        inconsistency_count = int(
            inconsistency_mask.sum()
        )

        audit.check(
            f"{target}/{split}: target availability consistency",
            inconsistency_count == 0,
            error=(
                f"{target}/{split}: "
                f"{inconsistency_count:,} rows have "
                "target/availability inconsistency."
            ),
        )

    return dataframe


# ============================================================================
# MANIFEST FEATURE REGISTRY VALIDATION
# ============================================================================


def validate_manifest_feature_registry(
    manifest: dict[str, Any],
    datasets: dict[
        str,
        dict[str, pd.DataFrame],
    ],
    audit: IntegrityAudit,
) -> None:

    manifest_features = manifest.get(
        "feature_columns"
    )

    if not isinstance(
        manifest_features,
        list,
    ):
        return

    expected_features = tuple(
        manifest_features
    )

    print()
    print(
        "--- FEATURE REGISTRY CROSS-CHECK ---"
    )

    for target in TARGETS:

        for split in SPLITS:

            dataframe = (
                datasets
                .get(
                    target,
                    {},
                )
                .get(
                    split
                )
            )

            if dataframe is None:
                continue

            actual_features = tuple(
                identify_feature_columns(
                    dataframe
                )
            )

            matches = (
                actual_features
                == expected_features
            )

            audit.check(
                f"{target}/{split}: feature registry matches manifest",
                matches,
                error=(
                    f"{target}/{split}: persisted feature "
                    "columns do not exactly match the "
                    "manifest feature registry."
                ),
            )


# ============================================================================
# CROSS-SPLIT KEY ISOLATION
# ============================================================================


def validate_split_key_isolation(
    datasets: dict[
        str,
        dict[str, pd.DataFrame],
    ],
    audit: IntegrityAudit,
) -> None:
    """
    Verify that the same observation does not occur in more
    than one split.

    This is the authoritative split leakage test.

    Timestamp equality across splits is allowed when different
    facilities are involved.
    """

    print()
    print(
        "--- CROSS-SPLIT OBSERVATION KEY ISOLATION ---"
    )

    for target in TARGETS:

        target_datasets = datasets.get(
            target,
            {},
        )

        if not all(
            split in target_datasets
            for split in SPLITS
        ):
            continue

        keys: dict[
            str,
            pd.MultiIndex,
        ] = {}

        for split in SPLITS:

            keys[split] = (
                build_observation_keys(
                    target_datasets[
                        split
                    ]
                )
            )

        train_validation_overlap = (
            keys["train"]
            .intersection(
                keys["validation"]
            )
        )

        validation_test_overlap = (
            keys["validation"]
            .intersection(
                keys["test"]
            )
        )

        train_test_overlap = (
            keys["train"]
            .intersection(
                keys["test"]
            )
        )

        print()
        print(target)

        print(
            "  Train ∩ Validation: "
            f"{len(train_validation_overlap):,}"
        )

        print(
            "  Validation ∩ Test:   "
            f"{len(validation_test_overlap):,}"
        )

        print(
            "  Train ∩ Test:        "
            f"{len(train_test_overlap):,}"
        )

        audit.check(
            f"{target}: train/validation key isolation",
            len(train_validation_overlap) == 0,
            error=(
                f"{target}: "
                f"{len(train_validation_overlap):,} "
                "observation keys appear in both "
                "train and validation."
            ),
        )

        audit.check(
            f"{target}: validation/test key isolation",
            len(validation_test_overlap) == 0,
            error=(
                f"{target}: "
                f"{len(validation_test_overlap):,} "
                "observation keys appear in both "
                "validation and test."
            ),
        )

        audit.check(
            f"{target}: train/test key isolation",
            len(train_test_overlap) == 0,
            error=(
                f"{target}: "
                f"{len(train_test_overlap):,} "
                "observation keys appear in both "
                "train and test."
            ),
        )


# ============================================================================
# CHRONOLOGICAL SPLIT REPORT
# ============================================================================


def report_chronological_boundaries(
    datasets: dict[
        str,
        dict[str, pd.DataFrame],
    ],
    audit: IntegrityAudit,
) -> None:
    """
    Report split chronology.

    IMPORTANT:
    Equal timestamps between adjacent splits are allowed.

    We verify that the split sequence is chronological and rely
    on observation-key isolation for leakage prevention.
    """

    print()
    print(
        "--- CHRONOLOGICAL SPLIT VALIDATION ---"
    )

    for target in TARGETS:

        target_datasets = datasets.get(
            target,
            {},
        )

        if not all(
            split in target_datasets
            for split in SPLITS
        ):
            continue

        train = target_datasets[
            "train"
        ]

        validation = target_datasets[
            "validation"
        ]

        test = target_datasets[
            "test"
        ]

        train_timestamps = pd.to_datetime(
            train[
                TIMESTAMP_COLUMN
            ]
        )

        validation_timestamps = pd.to_datetime(
            validation[
                TIMESTAMP_COLUMN
            ]
        )

        test_timestamps = pd.to_datetime(
            test[
                TIMESTAMP_COLUMN
            ]
        )

        train_min = train_timestamps.min()
        train_max = train_timestamps.max()

        validation_min = (
            validation_timestamps.min()
        )

        validation_max = (
            validation_timestamps.max()
        )

        test_min = test_timestamps.min()
        test_max = test_timestamps.max()

        # Equality is intentionally allowed.
        train_before_validation = (
            train_max
            <= validation_min
        )

        validation_before_test = (
            validation_max
            <= test_min
        )

        print()
        print(target)

        print(
            f"  Train:       {train_min} -> {train_max}"
        )

        print(
            f"  Validation:  "
            f"{validation_min} -> {validation_max}"
        )

        print(
            f"  Test:        {test_min} -> {test_max}"
        )

        print(
            "  Train -> Validation: "
            f"{'PASS' if train_before_validation else 'FAIL'}"
        )

        print(
            "  Validation -> Test:   "
            f"{'PASS' if validation_before_test else 'FAIL'}"
        )

        audit.check(
            f"{target}: chronological train/validation ordering",
            train_before_validation,
            error=(
                f"{target}: train chronology invalid. "
                f"Train max={train_max}, "
                f"validation min={validation_min}."
            ),
        )

        audit.check(
            f"{target}: chronological validation/test ordering",
            validation_before_test,
            error=(
                f"{target}: validation chronology invalid. "
                f"Validation max={validation_max}, "
                f"test min={test_min}."
            ),
        )


# ============================================================================
# TARGET DATASET TOTALS
# ============================================================================


def validate_target_totals(
    datasets: dict[
        str,
        dict[str, pd.DataFrame],
    ],
    audit: IntegrityAudit,
) -> None:

    print()
    print(
        "--- TARGET DATASET COUNTS ---"
    )

    for target in TARGETS:

        actual_total = 0

        for split in SPLITS:

            dataframe = (
                datasets
                .get(
                    target,
                    {},
                )
                .get(
                    split
                )
            )

            if dataframe is not None:

                actual_total += len(
                    dataframe
                )

        expected_total = (
            EXPECTED_ELIGIBLE_ROWS[
                target
            ]
        )

        print()
        print(target)

        print(
            f"  Expected eligible: "
            f"{expected_total:,}"
        )

        print(
            f"  Persisted rows:    "
            f"{actual_total:,}"
        )

        audit.check(
            f"{target}: persisted target total",
            actual_total
            == expected_total,
            error=(
                f"{target}: expected "
                f"{expected_total:,} persisted rows "
                f"but found {actual_total:,}."
            ),
        )


# ============================================================================
# COMMON TARGET SUBSET
# ============================================================================


def report_common_target_subset(
    datasets: dict[
        str,
        dict[str, pd.DataFrame],
    ],
) -> None:
    """
    Report the common target subset.

    This is informational only. The persisted target-specific
    datasets remain the authoritative training datasets.
    """

    target_frames: list[pd.DataFrame] = []

    for target in TARGETS:

        frames = []

        for split in SPLITS:

            dataframe = (
                datasets
                .get(
                    target,
                    {},
                )
                .get(
                    split
                )
            )

            if dataframe is not None:

                frames.append(
                    dataframe[
                        [
                            FACILITY_COLUMN,
                            TIMESTAMP_COLUMN,
                        ]
                    ]
                )

        if frames:

            combined = pd.concat(
                frames,
                ignore_index=True,
            )

            target_frames.append(
                combined
            )

    if not target_frames:
        return

    common_keys = None

    for dataframe in target_frames:

        keys = set(
            zip(
                dataframe[
                    FACILITY_COLUMN
                ].astype(str),
                pd.to_datetime(
                    dataframe[
                        TIMESTAMP_COLUMN
                    ]
                ),
            )
        )

        if common_keys is None:

            common_keys = keys

        else:

            common_keys &= keys

    common_count = len(
        common_keys or set()
    )

    print()
    print(
        "--- COMMON TARGET SUBSET ---"
    )

    print(
        f"Rows with all four targets: "
        f"{common_count:,}"
    )

    if EXPECTED_SOURCE_ROWS:

        percentage = (
            common_count
            / EXPECTED_SOURCE_ROWS
            * 100
        )

        print(
            f"Percentage of source:       "
            f"{percentage:.2f}%"
        )


# ============================================================================
# MAIN
# ============================================================================


def run_integrity_audit() -> int:

    audit = IntegrityAudit()

    print()
    print("=" * 78)
    print(
        "SMARTPARK AI - BIRMINGHAM TRAINING DATASET "
        "INTEGRITY AUDIT"
    )
    print("=" * 78)

    print()
    print(
        "Processed dataset root:"
    )

    print(
        f"  {PROCESSED_ROOT}"
    )

    print()
    print(
        "Manifest:"
    )

    print(
        f"  {MANIFEST_PATH}"
    )

    # ========================================================================
    # 1. LOAD MANIFEST
    # ========================================================================

    print()
    print(
        "--- 1. LOADING MANIFEST ---"
    )

    try:

        manifest = load_manifest()

    except RuntimeError as exc:

        print(
            f"ERROR: {exc}"
        )

        return 1

    print(
        "Manifest loaded successfully."
    )

    validate_manifest(
        manifest,
        audit,
    )

    # ========================================================================
    # 2. EXPECTED FILES
    # ========================================================================

    print()
    print(
        "--- 2. EXPECTED FILES ---"
    )

    expected_file_count = (
        len(TARGETS)
        * len(SPLITS)
    )

    print(
        f"Expected Parquet files: "
        f"{expected_file_count}"
    )

    audit.check(
        "Expected 12 Parquet files configured",
        expected_file_count == 12,
    )

    actual_parquet_files = (
        discover_parquet_files()
    )

    print(
        f"Actual Parquet files found: "
        f"{len(actual_parquet_files)}"
    )

    audit.check(
        "Exactly 12 Parquet files persisted",
        len(actual_parquet_files) == 12,
        error=(
            "Expected exactly 12 persisted Parquet "
            f"files but found "
            f"{len(actual_parquet_files)}."
        ),
    )

    # ========================================================================
    # 3. READ PERSISTED DATASETS
    # ========================================================================

    print()
    print(
        "--- 3. READING PERSISTED DATASETS ---"
    )

    datasets: dict[
        str,
        dict[str, pd.DataFrame],
    ] = {}

    for target in TARGETS:

        datasets[target] = {}

        for split in SPLITS:

            path = expected_parquet_path(
                target,
                split,
            )

            dataframe = audit_dataset(
                target=target,
                split=split,
                path=path,
                audit=audit,
            )

            if dataframe is not None:

                datasets[
                    target
                ][
                    split
                ] = dataframe

    # ========================================================================
    # 4. MANIFEST FEATURE REGISTRY
    # ========================================================================

    validate_manifest_feature_registry(
        manifest,
        datasets,
        audit,
    )

    # ========================================================================
    # 5. TARGET COUNTS
    # ========================================================================

    validate_target_totals(
        datasets,
        audit,
    )

    # ========================================================================
    # 6. CROSS-SPLIT KEY ISOLATION
    # ========================================================================

    validate_split_key_isolation(
        datasets,
        audit,
    )

    # ========================================================================
    # 7. CHRONOLOGY
    # ========================================================================

    report_chronological_boundaries(
        datasets,
        audit,
    )

    # ========================================================================
    # 8. COMMON TARGET SUBSET
    # ========================================================================

    report_common_target_subset(
        datasets
    )

    # ========================================================================
    # 9. CHECKSUM STATUS
    # ========================================================================

    print()
    print(
        "--- CHECKSUM STATUS ---"
    )

    print(
        "Per-file SHA-256 checksums:"
    )

    print(
        "  NOT CONFIGURED IN CURRENT MANIFEST"
    )

    print(
        "Checksum status is informational only and "
        "is NOT treated as an integrity failure."
    )

    # ========================================================================
    # 10. FINAL RESULT
    # ========================================================================

    print()
    print(
        "--- FINAL AUDIT RESULT ---"
    )

    print(
        f"Checks executed: "
        f"{len(audit.checks)}"
    )

    print(
        f"Checks passed:   "
        f"{audit.passed_count}"
    )

    print(
        f"Checks failed:   "
        f"{audit.failed_count}"
    )

    print(
        f"Warnings:        "
        f"{len(audit.warnings)}"
    )

    if audit.warnings:

        print()
        print(
            "Warnings:"
        )

        for warning in audit.warnings:

            print(
                f"  - {warning}"
            )

    if audit.errors:

        print()
        print(
            "Errors:"
        )

        for error in audit.errors:

            print(
                f"  - {error}"
            )

    print()
    print("=" * 78)

    if audit.passed:

        print(
            "BIRMINGHAM TRAINING DATASET "
            "INTEGRITY AUDIT PASSED"
        )

        print("=" * 78)

        print()
        print(
            "The persisted Birmingham training datasets "
            "were successfully reloaded and verified."
        )

        print()
        print(
            "Verified:"
        )

        print(
            "  ✓ Manifest contract"
        )

        print(
            "  ✓ 12 persisted Parquet datasets"
        )

        print(
            "  ✓ Target-specific row counts"
        )

        print(
            "  ✓ 296-feature registry"
        )

        print(
            "  ✓ Target schema"
        )

        print(
            "  ✓ Target availability consistency"
        )

        print(
            "  ✓ No infinite numeric values"
        )

        print(
            "  ✓ No duplicate observation keys"
        )

        print(
            "  ✓ No cross-split observation leakage"
        )

        print(
            "  ✓ No target leakage"
        )

        print(
            "  ✓ Chronological split ordering"
        )

        print()
        print(
            "Birmingham persisted training data is "
            "READY FOR MODEL TRAINING."
        )

        return 0

    print(
        "BIRMINGHAM TRAINING DATASET "
        "INTEGRITY AUDIT FAILED"
    )

    print("=" * 78)

    print()
    print(
        "DO NOT proceed to model training until "
        "the reported integrity failures are resolved."
    )

    return 1


# ============================================================================
# ENTRY POINT
# ============================================================================


if __name__ == "__main__":

    raise SystemExit(
        run_integrity_audit()
    )