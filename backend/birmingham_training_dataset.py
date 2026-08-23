"""
SmartPark AI
Birmingham Target-Specific Training Dataset Builder
=====================================================

Purpose
-------
Construct target-specific supervised-learning datasets from the
completed Birmingham feature pipeline output.

This module intentionally sits AFTER:

    Birmingham Dataset Builder
            ↓
    Feature Pipeline
            ↓
    Target Audit
            ↓
    THIS MODULE
            ↓
    Model Training

Design principles
-----------------
1. One supervised dataset per prediction target.
2. Target values are NEVER imputed.
3. Rows without an available target are excluded from that target's
   training dataset only.
4. Feature values are never allowed to use future information.
5. Chronological train/validation/test splitting.
6. No random shuffling.
7. Facility-level diagnostics are preserved.
8. NIA North is NOT silently removed.
9. Source data is never modified in-place.
10. Strong structural and leakage validation.
11. Persisted training datasets contain only approved features plus the
    current target and traceability columns.
12. Persisted datasets are accompanied by a machine-readable manifest
    with schema, split, leakage and checksum information.

Current Birmingham targets
--------------------------
- target_occupancy_rate_30m
- target_occupancy_rate_1h
- target_occupancy_rate_2h
- target_tomorrow_morning_demand

Expected feature pipeline
-------------------------
The builder expects the completed feature pipeline to provide:

    result.dataframe
    result.feature_columns
    result.target_columns
    result.target_availability_columns
    result.metadata_columns
    result.metadata

The Birmingham dataset builder is used by default to construct the
source dataset when no feature dataframe is supplied directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


# ============================================================================
# Constants
# ============================================================================

BIRMINGHAM_SOURCE_NAME = "BIRMINGHAM"

DEFAULT_DATASET_ROOT = "../datasets/raw"

# Persisted, model-ready training datasets are stored here.
# This path is relative to the backend/ working directory.
DEFAULT_PROCESSED_DATASET_ROOT = "../datasets/processed"

FACILITY_COLUMN = "source_facility_code"
TIMESTAMP_COLUMN = "normalized_at"

DEFAULT_TARGET_COLUMNS: tuple[str, ...] = (
    "target_occupancy_rate_30m",
    "target_occupancy_rate_1h",
    "target_occupancy_rate_2h",
    "target_tomorrow_morning_demand",
)

DEFAULT_TARGET_AVAILABILITY_COLUMNS: tuple[str, ...] = (
    "target_30m_available",
    "target_1h_available",
    "target_2h_available",
    "target_tomorrow_morning_available",
)

DEFAULT_TARGET_TO_AVAILABILITY: dict[str, str] = {
    "target_occupancy_rate_30m":
        "target_30m_available",

    "target_occupancy_rate_1h":
        "target_1h_available",

    "target_occupancy_rate_2h":
        "target_2h_available",

    "target_tomorrow_morning_demand":
        "target_tomorrow_morning_available",
}

DEFAULT_SPLIT_RATIOS: tuple[float, float, float] = (
    0.70,
    0.15,
    0.15,
)


# ============================================================================
# Exceptions
# ============================================================================


class TrainingDatasetError(Exception):
    """Base exception for training dataset construction."""


class TrainingDatasetDataError(TrainingDatasetError):
    """Raised when source data violates structural expectations."""


class TrainingDatasetLeakageError(TrainingDatasetError):
    """Raised when a leakage contract is violated."""


# ============================================================================
# Dataclasses
# ============================================================================


@dataclass(frozen=True)
class TrainingDatasetConfig:
    """
    Configuration for target-specific supervised dataset construction.
    """

    facility_column: str = FACILITY_COLUMN

    timestamp_column: str = TIMESTAMP_COLUMN

    target_columns: tuple[str, ...] = (
        DEFAULT_TARGET_COLUMNS
    )

    target_availability_columns: tuple[str, ...] = (
        DEFAULT_TARGET_AVAILABILITY_COLUMNS
    )

    target_to_availability: Mapping[str, str] = field(
        default_factory=lambda: dict(
            DEFAULT_TARGET_TO_AVAILABILITY
        )
    )

    train_ratio: float = 0.70

    validation_ratio: float = 0.15

    test_ratio: float = 0.15

    require_target_availability_flag: bool = True

    require_finite_target: bool = True

    require_target_range: bool = True

    target_minimum: float = 0.0

    target_maximum: float = 1.0

    sort_by_time: bool = True

    preserve_original_index: bool = False

    fail_on_duplicate_rows: bool = True

    fail_on_leakage: bool = True

    expected_source_name: str = BIRMINGHAM_SOURCE_NAME

    def __post_init__(self) -> None:
        total = (
            self.train_ratio
            + self.validation_ratio
            + self.test_ratio
        )

        if not np.isclose(
            total,
            1.0,
            atol=1e-9,
        ):
            raise ValueError(
                "Train/validation/test ratios must sum to 1.0. "
                f"Received {total}."
            )

        if (
            self.train_ratio <= 0
            or self.validation_ratio <= 0
            or self.test_ratio <= 0
        ):
            raise ValueError(
                "Train, validation and test ratios must all be > 0."
            )

        if not self.target_columns:
            raise ValueError(
                "At least one target column is required."
            )


@dataclass(frozen=True)
class TrainingSplitResult:
    """
    One chronological train/validation/test split.
    """

    target_column: str

    dataframe: pd.DataFrame

    train: pd.DataFrame

    validation: pd.DataFrame

    test: pd.DataFrame

    feature_columns: tuple[str, ...]

    target_column_name: str

    facility_column: str

    timestamp_column: str

    train_end_timestamp: pd.Timestamp | None

    validation_end_timestamp: pd.Timestamp | None

    test_end_timestamp: pd.Timestamp | None

    statistics: Mapping[str, Any]

    metadata: Mapping[str, Any]


@dataclass(frozen=True)
class BirminghamTrainingDatasetResult:
    """
    Complete collection of target-specific training datasets.
    """

    source_dataframe: pd.DataFrame

    target_datasets: Mapping[
        str,
        TrainingSplitResult,
    ]

    feature_columns: tuple[str, ...]

    target_columns: tuple[str, ...]

    target_availability_columns: tuple[str, ...]

    metadata_columns: tuple[str, ...]

    statistics: Mapping[str, Any]

    metadata: Mapping[str, Any]


# ============================================================================
# Utility functions
# ============================================================================


def _as_tuple(
    values: Sequence[str],
) -> tuple[str, ...]:
    return tuple(values)


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None

    try:
        value = float(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if not np.isfinite(value):
        return None

    return value


def _timestamp_min(
    dataframe: pd.DataFrame,
    column: str,
) -> pd.Timestamp | None:

    if dataframe.empty:
        return None

    values = pd.to_datetime(
        dataframe[column],
        errors="coerce",
    ).dropna()

    if values.empty:
        return None

    return values.min()


def _timestamp_max(
    dataframe: pd.DataFrame,
    column: str,
) -> pd.Timestamp | None:

    if dataframe.empty:
        return None

    values = pd.to_datetime(
        dataframe[column],
        errors="coerce",
    ).dropna()

    if values.empty:
        return None

    return values.max()


# ============================================================================
# Training Dataset Builder
# ============================================================================


class BirminghamTrainingDatasetBuilder:
    """
    Build target-specific chronological supervised-learning datasets.
    """

    def __init__(
        self,
        *,
        config: TrainingDatasetConfig | None = None,
    ) -> None:

        self.config = (
            config
            or TrainingDatasetConfig()
        )

    # ----------------------------------------------------------------------
    # Public API
    # ----------------------------------------------------------------------

    def build(
        self,
        dataframe: pd.DataFrame,
        *,
        feature_columns: Sequence[str],
        metadata_columns: Sequence[str] = (),
    ) -> BirminghamTrainingDatasetResult:
        """
        Build all target-specific supervised datasets.
        """

        self._validate_source(
            dataframe,
            feature_columns=feature_columns,
        )

        source = dataframe.copy(
            deep=True
        )

        if self.config.sort_by_time:
            source = self._sort_source(
                source
            )

        target_datasets: dict[
            str,
            TrainingSplitResult,
        ] = {}

        for target_column in (
            self.config.target_columns
        ):

            target_datasets[target_column] = (
                self._build_target_dataset(
                    source,
                    target_column=target_column,
                    feature_columns=feature_columns,
                )
            )

        statistics = (
            self._build_overall_statistics(
                source,
                target_datasets,
            )
        )

        metadata = {
            "source_name":
                self.config.expected_source_name,

            "facility_column":
                self.config.facility_column,

            "timestamp_column":
                self.config.timestamp_column,

            "target_columns":
                tuple(self.config.target_columns),

            "target_availability_columns":
                tuple(
                    self.config.target_availability_columns
                ),

            "target_to_availability":
                dict(self.config.target_to_availability),

            "train_ratio":
                self.config.train_ratio,

            "validation_ratio":
                self.config.validation_ratio,

            "test_ratio":
                self.config.test_ratio,

            "chronological_split":
                True,

            "random_shuffle":
                False,

            "target_imputation":
                False,

            "target_specific_training_sets":
                True,

            "future_data_used":
                False,

            "target_data_used_as_feature":
                False,

            "cross_facility_data_used":
                False,

            "forward_lookup_used":
                False,

            "centered_windows_used":
                False,

            "source_data_modified":
                False,
        }

        return BirminghamTrainingDatasetResult(
            source_dataframe=source,
            target_datasets=target_datasets,
            feature_columns=_as_tuple(
                feature_columns
            ),
            target_columns=_as_tuple(
                self.config.target_columns
            ),
            target_availability_columns=_as_tuple(
                self.config.target_availability_columns
            ),
            metadata_columns=_as_tuple(
                metadata_columns
            ),
            statistics=statistics,
            metadata=metadata,
        )

    # ----------------------------------------------------------------------
    # Source validation
    # ----------------------------------------------------------------------

    def _validate_source(
        self,
        dataframe: pd.DataFrame,
        *,
        feature_columns: Sequence[str],
    ) -> None:

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise TrainingDatasetDataError(
                "Expected pandas DataFrame."
            )

        if dataframe.empty:
            raise TrainingDatasetDataError(
                "Training dataset source is empty."
            )

        required_columns = {
            self.config.facility_column,
            self.config.timestamp_column,
            *self.config.target_columns,
        }

        if (
            self.config.require_target_availability_flag
        ):
            required_columns.update(
                self.config.target_availability_columns
            )

        missing = sorted(
            column
            for column in required_columns
            if column not in dataframe.columns
        )

        if missing:
            raise TrainingDatasetDataError(
                "Source dataframe is missing required columns: "
                f"{missing}"
            )

        missing_features = [
            column
            for column in feature_columns
            if column not in dataframe.columns
        ]

        if missing_features:
            raise TrainingDatasetDataError(
                "Feature columns missing from source dataframe: "
                f"{missing_features}"
            )

        timestamp_values = pd.to_datetime(
            dataframe[
                self.config.timestamp_column
            ],
            errors="coerce",
        )

        if timestamp_values.isna().any():
            count = int(
                timestamp_values.isna().sum()
            )

            raise TrainingDatasetDataError(
                "Source dataframe contains "
                f"{count} invalid timestamps."
            )

        if dataframe[
            self.config.facility_column
        ].isna().any():

            raise TrainingDatasetDataError(
                "Source dataframe contains missing "
                "facility identifiers."
            )

        if self.config.fail_on_duplicate_rows:

            duplicates = dataframe.duplicated(
                subset=[
                    self.config.facility_column,
                    self.config.timestamp_column,
                ]
            )

            duplicate_count = int(
                duplicates.sum()
            )

            if duplicate_count:

                raise TrainingDatasetDataError(
                    "Duplicate facility/timestamp rows detected: "
                    f"{duplicate_count}"
                )

    # ----------------------------------------------------------------------
    # Sorting
    # ----------------------------------------------------------------------

    def _sort_source(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:

        return (
            dataframe
            .sort_values(
                by=[
                    self.config.timestamp_column,
                    self.config.facility_column,
                ],
                kind="mergesort",
            )
            .copy()
        )

    # ----------------------------------------------------------------------
    # Target dataset
    # ----------------------------------------------------------------------

    def _build_target_dataset(
        self,
        source: pd.DataFrame,
        *,
        target_column: str,
        feature_columns: Sequence[str],
    ) -> TrainingSplitResult:

        availability_column = (
            self.config.target_to_availability.get(
                target_column
            )
        )

        if (
            self.config.require_target_availability_flag
            and not availability_column
        ):

            raise TrainingDatasetDataError(
                "No target availability mapping configured "
                f"for '{target_column}'."
            )

        eligibility = (
            self._build_target_eligibility_mask(
                source,
                target_column=target_column,
                availability_column=availability_column,
            )
        )

        eligible = (
            source.loc[
                eligibility
            ]
            .copy()
        )

        if self.config.sort_by_time:

            eligible = (
                eligible
                .sort_values(
                    by=[
                        self.config.timestamp_column,
                        self.config.facility_column,
                    ],
                    kind="mergesort",
                )
                .copy()
            )

        if eligible.empty:

            raise TrainingDatasetDataError(
                "No eligible rows available for target "
                f"'{target_column}'."
            )

        train, validation, test = (
            self._chronological_split(
                eligible
            )
        )

        self._validate_split(
            train,
            validation,
            test,
            target_column=target_column,
        )

        statistics = (
            self._build_target_statistics(
                source,
                eligible,
                train,
                validation,
                test,
                target_column=target_column,
                availability_column=availability_column,
            )
        )

        metadata = {
            "target_column":
                target_column,

            "availability_column":
                availability_column,

            "chronological_split":
                True,

            "random_shuffle":
                False,

            "target_imputation":
                False,

            "future_data_used":
                False,

            "target_data_used_as_feature":
                False,

            "cross_facility_data_used":
                False,

            "forward_lookup_used":
                False,

            "centered_windows_used":
                False,
        }

        return TrainingSplitResult(
            target_column=target_column,
            dataframe=eligible,
            train=train,
            validation=validation,
            test=test,
            feature_columns=_as_tuple(
                feature_columns
            ),
            target_column_name=target_column,
            facility_column=self.config.facility_column,
            timestamp_column=self.config.timestamp_column,
            train_end_timestamp=_timestamp_max(
                train,
                self.config.timestamp_column,
            ),
            validation_end_timestamp=_timestamp_max(
                validation,
                self.config.timestamp_column,
            ),
            test_end_timestamp=_timestamp_max(
                test,
                self.config.timestamp_column,
            ),
            statistics=statistics,
            metadata=metadata,
        )

    # ----------------------------------------------------------------------
    # Eligibility
    # ----------------------------------------------------------------------

    def _build_target_eligibility_mask(
        self,
        source: pd.DataFrame,
        *,
        target_column: str,
        availability_column: str | None,
    ) -> pd.Series:

        mask = pd.Series(
            True,
            index=source.index,
            dtype=bool,
        )

        target_values = pd.to_numeric(
            source[target_column],
            errors="coerce",
        )

        mask &= target_values.notna()

        if self.config.require_finite_target:

            mask &= np.isfinite(
                target_values.fillna(
                    np.nan
                )
            )

        if (
            self.config.require_target_range
        ):

            mask &= (
                target_values
                >= self.config.target_minimum
            )

            mask &= (
                target_values
                <= self.config.target_maximum
            )

        if (
            self.config.require_target_availability_flag
            and availability_column is not None
        ):

            availability = (
                source[
                    availability_column
                ]
                .astype("boolean")
                .fillna(False)
            )

            mask &= availability

        return mask

    # ----------------------------------------------------------------------
    # Chronological split
    # ----------------------------------------------------------------------

    def _chronological_split(
        self,
        dataframe: pd.DataFrame,
    ) -> tuple[
        pd.DataFrame,
        pd.DataFrame,
        pd.DataFrame,
    ]:

        if dataframe.empty:
            raise TrainingDatasetDataError(
                "Cannot split an empty dataframe."
            )

        dataframe = (
            dataframe
            .sort_values(
                by=[
                    self.config.timestamp_column,
                    self.config.facility_column,
                ],
                kind="mergesort",
            )
            .copy()
        )

        row_count = len(dataframe)

        if row_count < 3:

            raise TrainingDatasetDataError(
                "At least 3 eligible rows are required "
                "for train/validation/test splitting. "
                f"Received {row_count}."
            )

        train_end = int(
            np.floor(
                row_count
                * self.config.train_ratio
            )
        )

        validation_end = (
            train_end
            + int(
                np.floor(
                    row_count
                    * self.config.validation_ratio
                )
            )
        )

        train_end = max(
            1,
            min(
                train_end,
                row_count - 2,
            ),
        )

        validation_end = max(
            train_end + 1,
            min(
                validation_end,
                row_count - 1,
            ),
        )

        train = (
            dataframe
            .iloc[
                :train_end
            ]
            .copy()
        )

        validation = (
            dataframe
            .iloc[
                train_end:validation_end
            ]
            .copy()
        )

        test = (
            dataframe
            .iloc[
                validation_end:
            ]
            .copy()
        )

        return (
            train,
            validation,
            test,
        )

    # ----------------------------------------------------------------------
    # Split validation
    # ----------------------------------------------------------------------

    def _validate_split(
        self,
        train: pd.DataFrame,
        validation: pd.DataFrame,
        test: pd.DataFrame,
        *,
        target_column: str,
    ) -> None:

        if train.empty:
            raise TrainingDatasetDataError(
                f"Training split is empty for '{target_column}'."
            )

        if validation.empty:
            raise TrainingDatasetDataError(
                f"Validation split is empty for '{target_column}'."
            )

        if test.empty:
            raise TrainingDatasetDataError(
                f"Test split is empty for '{target_column}'."
            )

        train_max = _timestamp_max(
            train,
            self.config.timestamp_column,
        )

        validation_min = _timestamp_min(
            validation,
            self.config.timestamp_column,
        )

        validation_max = _timestamp_max(
            validation,
            self.config.timestamp_column,
        )

        test_min = _timestamp_min(
            test,
            self.config.timestamp_column,
        )

        if (
            train_max is not None
            and validation_min is not None
            and train_max > validation_min
        ):

            raise TrainingDatasetDataError(
                f"Chronological split violation for "
                f"'{target_column}': training data extends "
                "beyond validation data."
            )

        if (
            validation_max is not None
            and test_min is not None
            and validation_max > test_min
        ):

            raise TrainingDatasetDataError(
                f"Chronological split violation for "
                f"'{target_column}': validation data extends "
                "beyond test data."
            )

        # --------------------------------------------------------------
        # No overlapping facility/timestamp rows across splits
        # --------------------------------------------------------------

        key = [
            self.config.facility_column,
            self.config.timestamp_column,
        ]

        train_keys = set(
            map(
                tuple,
                train[key].to_numpy(),
            )
        )

        validation_keys = set(
            map(
                tuple,
                validation[key].to_numpy(),
            )
        )

        test_keys = set(
            map(
                tuple,
                test[key].to_numpy(),
            )
        )

        if train_keys & validation_keys:

            raise TrainingDatasetDataError(
                f"Train/validation row overlap detected "
                f"for '{target_column}'."
            )

        if train_keys & test_keys:

            raise TrainingDatasetDataError(
                f"Train/test row overlap detected "
                f"for '{target_column}'."
            )

        if validation_keys & test_keys:

            raise TrainingDatasetDataError(
                f"Validation/test row overlap detected "
                f"for '{target_column}'."
            )

    # ----------------------------------------------------------------------
    # Target statistics
    # ----------------------------------------------------------------------

    def _build_target_statistics(
        self,
        source: pd.DataFrame,
        eligible: pd.DataFrame,
        train: pd.DataFrame,
        validation: pd.DataFrame,
        test: pd.DataFrame,
        *,
        target_column: str,
        availability_column: str | None,
    ) -> dict[str, Any]:

        source_target = pd.to_numeric(
            source[target_column],
            errors="coerce",
        )

        eligible_target = pd.to_numeric(
            eligible[target_column],
            errors="coerce",
        )

        facility_stats: dict[str, dict[str, Any]] = {}

        for facility, group in eligible.groupby(
            self.config.facility_column,
            sort=True,
        ):

            values = pd.to_numeric(
                group[target_column],
                errors="coerce",
            ).dropna()

            facility_stats[str(facility)] = {
                "rows":
                    int(len(group)),

                "usable_rows":
                    int(len(values)),

                "usable_pct":
                    round(
                        (
                            len(values)
                            / len(
                                source[
                                    source[
                                        self.config.facility_column
                                    ]
                                    == facility
                                ]
                            )
                        )
                        * 100,
                        2,
                    )
                    if len(
                        source[
                            source[
                                self.config.facility_column
                            ]
                            == facility
                        ]
                    )
                    else 0.0,

                "minimum":
                    _safe_float(
                        values.min()
                    )
                    if not values.empty
                    else None,

                "maximum":
                    _safe_float(
                        values.max()
                    )
                    if not values.empty
                    else None,

                "mean":
                    _safe_float(
                        values.mean()
                    )
                    if not values.empty
                    else None,
            }

        return {
            "source_rows":
                int(len(source)),

            "eligible_rows":
                int(len(eligible)),

            "excluded_rows":
                int(
                    len(source)
                    - len(eligible)
                ),

            "eligible_pct":
                round(
                    (
                        len(eligible)
                        / len(source)
                    )
                    * 100,
                    2,
                ),

            "train_rows":
                int(len(train)),

            "validation_rows":
                int(len(validation)),

            "test_rows":
                int(len(test)),

            "train_pct":
                round(
                    len(train)
                    / len(eligible)
                    * 100,
                    2,
                ),

            "validation_pct":
                round(
                    len(validation)
                    / len(eligible)
                    * 100,
                    2,
                ),

            "test_pct":
                round(
                    len(test)
                    / len(eligible)
                    * 100,
                    2,
                ),

            "minimum":
                _safe_float(
                    eligible_target.min()
                ),

            "maximum":
                _safe_float(
                    eligible_target.max()
                ),

            "mean":
                _safe_float(
                    eligible_target.mean()
                ),

            "median":
                _safe_float(
                    eligible_target.median()
                ),

            "std":
                _safe_float(
                    eligible_target.std()
                ),

            "source_non_null_target_rows":
                int(
                    source_target.notna().sum()
                ),

            "availability_column":
                availability_column,

            "facility_statistics":
                facility_stats,

            "train_start":
                _timestamp_min(
                    train,
                    self.config.timestamp_column,
                ),

            "train_end":
                _timestamp_max(
                    train,
                    self.config.timestamp_column,
                ),

            "validation_start":
                _timestamp_min(
                    validation,
                    self.config.timestamp_column,
                ),

            "validation_end":
                _timestamp_max(
                    validation,
                    self.config.timestamp_column,
                ),

            "test_start":
                _timestamp_min(
                    test,
                    self.config.timestamp_column,
                ),

            "test_end":
                _timestamp_max(
                    test,
                    self.config.timestamp_column,
                ),
        }

    # ----------------------------------------------------------------------
    # Overall statistics
    # ----------------------------------------------------------------------

    def _build_overall_statistics(
        self,
        source: pd.DataFrame,
        target_datasets: Mapping[
            str,
            TrainingSplitResult,
        ],
    ) -> dict[str, Any]:

        all_target_eligible_rows = {
            target:
                result.statistics[
                    "eligible_rows"
                ]
            for target, result
            in target_datasets.items()
        }

        all_target_train_rows = {
            target:
                result.statistics[
                    "train_rows"
                ]
            for target, result
            in target_datasets.items()
        }

        all_target_validation_rows = {
            target:
                result.statistics[
                    "validation_rows"
                ]
            for target, result
            in target_datasets.items()
        }

        all_target_test_rows = {
            target:
                result.statistics[
                    "test_rows"
                ]
            for target, result
            in target_datasets.items()
        }

        common_target_mask = pd.Series(
            True,
            index=source.index,
            dtype=bool,
        )

        for target in (
            self.config.target_columns
        ):

            availability_column = (
                self.config.target_to_availability.get(
                    target
                )
            )

            target_values = pd.to_numeric(
                source[target],
                errors="coerce",
            )

            common_target_mask &= (
                target_values.notna()
            )

            if (
                self.config.require_target_availability_flag
                and availability_column
            ):

                common_target_mask &= (
                    source[
                        availability_column
                    ]
                    .astype("boolean")
                    .fillna(False)
                )

        return {
            "source_row_count":
                int(len(source)),

            "facility_count":
                int(
                    source[
                        self.config.facility_column
                    ]
                    .nunique()
                ),

            "target_count":
                len(
                    self.config.target_columns
                ),

            "eligible_rows_by_target":
                all_target_eligible_rows,

            "train_rows_by_target":
                all_target_train_rows,

            "validation_rows_by_target":
                all_target_validation_rows,

            "test_rows_by_target":
                all_target_test_rows,

            "rows_with_all_targets_available":
                int(
                    common_target_mask.sum()
                ),

            "all_target_availability_pct":
                round(
                    (
                        common_target_mask.sum()
                        / len(source)
                    )
                    * 100,
                    2,
                ),

            "future_data_used":
                False,

            "target_data_used_as_feature":
                False,

            "cross_facility_data_used":
                False,

            "forward_lookup_used":
                False,

            "centered_windows_used":
                False,

            "random_shuffle":
                False,

            "target_imputation":
                False,

            "chronological_split":
                True,
        }


# ============================================================================
# Result validation
# ============================================================================


def validate_training_dataset(
    result: BirminghamTrainingDatasetResult,
) -> dict[str, Any]:
    """
    Validate a completed Birmingham training dataset result.
    """

    errors: list[str] = []
    warnings: list[str] = []

    if result.source_dataframe.empty:

        errors.append(
            "Source dataframe is empty."
        )

    # ------------------------------------------------------------------
    # Feature existence
    # ------------------------------------------------------------------

    missing_features = [
        column
        for column in result.feature_columns
        if column not in result.source_dataframe.columns
    ]

    if missing_features:

        errors.append(
            "Missing feature columns: "
            f"{missing_features}"
        )

    # ------------------------------------------------------------------
    # Target existence
    # ------------------------------------------------------------------

    for target in result.target_columns:

        if target not in result.source_dataframe.columns:

            errors.append(
                f"Missing target column: {target}"
            )

    # ------------------------------------------------------------------
    # Leakage contract
    # ------------------------------------------------------------------

    leakage_flags = (
        "future_data_used",
        "target_data_used_as_feature",
        "cross_facility_data_used",
        "forward_lookup_used",
        "centered_windows_used",
    )

    for flag in leakage_flags:

        if result.metadata.get(
            flag,
            False,
        ):

            errors.append(
                f"Leakage contract violation: "
                f"{flag}=True"
            )

    # ------------------------------------------------------------------
    # Target-specific validation
    # ------------------------------------------------------------------

    for target, split_result in (
        result.target_datasets.items()
    ):

        train = split_result.train
        validation = split_result.validation
        test = split_result.test

        if train.empty:
            errors.append(
                f"{target}: training split is empty."
            )

        if validation.empty:
            errors.append(
                f"{target}: validation split is empty."
            )

        if test.empty:
            errors.append(
                f"{target}: test split is empty."
            )

        target_values = pd.to_numeric(
            split_result.dataframe[target],
            errors="coerce",
        )

        if target_values.isna().any():

            errors.append(
                f"{target}: eligible dataset contains "
                "null target values."
            )

        if not np.isfinite(
            target_values.to_numpy(
                dtype="float64"
            )
        ).all():

            errors.append(
                f"{target}: eligible dataset contains "
                "non-finite target values."
            )

        if (
            target_values.min()
            < 0.0
            or target_values.max()
            > 1.0
        ):

            errors.append(
                f"{target}: target values outside "
                "[0, 1]."
            )

        # --------------------------------------------------------------
        # Chronological checks
        # --------------------------------------------------------------

        train_end = _timestamp_max(
            train,
            result.metadata[
                "timestamp_column"
            ],
        )

        validation_start = _timestamp_min(
            validation,
            result.metadata[
                "timestamp_column"
            ],
        )

        validation_end = _timestamp_max(
            validation,
            result.metadata[
                "timestamp_column"
            ],
        )

        test_start = _timestamp_min(
            test,
            result.metadata[
                "timestamp_column"
            ],
        )

        if (
            train_end is not None
            and validation_start is not None
            and train_end > validation_start
        ):

            errors.append(
                f"{target}: train/validation chronological "
                "ordering violation."
            )

        if (
            validation_end is not None
            and test_start is not None
            and validation_end > test_start
        ):

            errors.append(
                f"{target}: validation/test chronological "
                "ordering violation."
            )

        # --------------------------------------------------------------
        # Target leakage into feature set
        # --------------------------------------------------------------

        overlap = [
            column
            for column in split_result.feature_columns
            if column == target
            or column.startswith(
                "target_"
            )
        ]

        if overlap:

            errors.append(
                f"{target}: target-related columns found "
                f"in feature set: {overlap}"
            )

    # ------------------------------------------------------------------
    # Informational warnings
    # ------------------------------------------------------------------

    for target, split_result in (
        result.target_datasets.items()
    ):

        eligible_rows = (
            split_result.statistics[
                "eligible_rows"
            ]
        )

        if eligible_rows < 1000:

            warnings.append(
                f"{target}: only "
                f"{eligible_rows:,} eligible rows."
            )

    return {
        "valid":
            not errors,

        "errors":
            errors,

        "warnings":
            warnings,

        "source_rows":
            len(result.source_dataframe),

        "facility_count":
            result.statistics[
                "facility_count"
            ],

        "target_count":
            result.statistics[
                "target_count"
            ],

        "target_datasets":
            len(
                result.target_datasets
            ),

        "future_data_used":
            result.metadata.get(
                "future_data_used",
                False,
            ),

        "target_data_used_as_feature":
            result.metadata.get(
                "target_data_used_as_feature",
                False,
            ),

        "cross_facility_data_used":
            result.metadata.get(
                "cross_facility_data_used",
                False,
            ),

        "forward_lookup_used":
            result.metadata.get(
                "forward_lookup_used",
                False,
            ),

        "centered_windows_used":
            result.metadata.get(
                "centered_windows_used",
                False,
            ),
    }


# ============================================================================
# Convenience builder
# ============================================================================


def build_birmingham_training_datasets(
    *,
    feature_dataframe: pd.DataFrame | None = None,
    feature_columns: Sequence[str] | None = None,
    metadata_columns: Sequence[str] = (),
    dataset_root: str | Path = DEFAULT_DATASET_ROOT,
    config: TrainingDatasetConfig | None = None,
) -> BirminghamTrainingDatasetResult:
    """
    Build Birmingham target-specific training datasets.

    Preferred usage
    ---------------
    Pass the already-generated Birmingham feature pipeline dataframe.

    Example
    -------
        result = build_birmingham_training_datasets(
            feature_dataframe=pipeline_result.dataframe,
            feature_columns=pipeline_result.feature_columns,
            metadata_columns=pipeline_result.metadata_columns,
        )

    Convenience usage
    ------------------
    If feature_dataframe is omitted, this function will:

        1. Build Birmingham ML dataset.
        2. Run the complete feature pipeline.
        3. Build target-specific training datasets.

    This convenience mode is useful for an end-to-end smoke test.
    """

    if feature_dataframe is None:

        from app.ml.data.dataset_builder import (
            build_birmingham_ml_dataset,
        )

        from app.ml.features.feature_pipeline import (
            build_birmingham_feature_pipeline,
        )

        pipeline_result = (
            build_birmingham_feature_pipeline(
                dataset_root=str(
                    dataset_root
                )
            )
        )

        feature_dataframe = (
            pipeline_result.dataframe
        )

        feature_columns = (
            pipeline_result.feature_columns
        )

        metadata_columns = (
            pipeline_result.metadata_columns
        )

    if feature_columns is None:

        raise TrainingDatasetDataError(
            "feature_columns must be supplied when "
            "feature_dataframe is supplied directly."
        )

    builder = (
        BirminghamTrainingDatasetBuilder(
            config=config
        )
    )

    result = builder.build(
        feature_dataframe,
        feature_columns=feature_columns,
        metadata_columns=metadata_columns,
    )

    validation = (
        validate_training_dataset(
            result
        )
    )

    if not validation["valid"]:

        raise TrainingDatasetError(
            "Birmingham training dataset validation failed: "
            f"{validation['errors']}"
        )

    return result




# ============================================================================
# Persistence / Export
# ============================================================================


def _json_safe(value: Any) -> Any:
    """Convert common pandas/numpy values into JSON-safe primitives."""

    if isinstance(value, (pd.Timestamp, pd.Timedelta)):
        return value.isoformat()

    if isinstance(value, np.generic):
        value = value.item()

    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]

    if value is pd.NA:
        return None

    if isinstance(value, float) and not np.isfinite(value):
        return None

    return value


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 checksum of a persisted dataset file."""

    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _training_export_columns(
    result: BirminghamTrainingDatasetResult,
    *,
    target: str,
) -> tuple[str, ...]:
    """
    Return the safe column contract for one target-specific persisted dataset.

    Persisted training data intentionally contains:
      - the approved ML features;
      - facility/timestamp identifiers for traceability;
      - only the current target; and
      - its availability flag for auditability.

    Other target columns are deliberately excluded so that a downstream
    trainer cannot accidentally consume another prediction target as a feature.
    """

    availability_column = result.metadata.get(
        "target_to_availability",
    )

    if isinstance(availability_column, Mapping):
        availability_column = availability_column.get(target)
    else:
        availability_column = DEFAULT_TARGET_TO_AVAILABILITY.get(target)

    columns: list[str] = [
        *result.feature_columns,
        result.metadata["facility_column"],
        result.metadata["timestamp_column"],
        target,
    ]

    if availability_column:
        columns.append(str(availability_column))

    # Preserve order while protecting against accidental duplicate names.
    return tuple(dict.fromkeys(columns))


def persist_birmingham_training_datasets(
    result: BirminghamTrainingDatasetResult,
    *,
    output_root: str | Path = DEFAULT_PROCESSED_DATASET_ROOT,
    dataset_name: str = "birmingham",
    overwrite: bool = True,
) -> dict[str, Any]:
    """
    Persist the validated Birmingham target-specific training datasets.

    Output layout
    --------------
    <output_root>/<dataset_name>/
        target_occupancy_rate_30m/
            train.parquet
            validation.parquet
            test.parquet
        target_occupancy_rate_1h/
            ...
        target_occupancy_rate_2h/
            ...
        target_tomorrow_morning_demand/
            ...
        training_dataset_manifest.json

    Each parquet file contains only the approved features plus the facility
    identifier, timestamp, the current target and its availability flag.
    Other targets are excluded from persisted training data by design.

    The function validates the in-memory result before writing anything and
    records SHA-256 checksums in the manifest for later integrity checks.
    """

    validation = validate_training_dataset(result)

    if not validation["valid"]:
        raise TrainingDatasetError(
            "Refusing to persist an invalid Birmingham training dataset: "
            f"{validation['errors']}"
        )

    try:
        import pyarrow  # noqa: F401
    except ImportError as exc:
        raise TrainingDatasetError(
            "Parquet persistence requires the 'pyarrow' package. "
            "Install it in the active virtual environment with "
            "'python -m pip install pyarrow' and rerun the export."
        ) from exc

    output_directory = (
        Path(output_root) / dataset_name
    ).resolve()

    output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    manifest_targets: dict[str, Any] = {}
    persisted_files: list[str] = []

    for target, split_result in result.target_datasets.items():

        target_directory = output_directory / target
        target_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        export_columns = _training_export_columns(
            result,
            target=target,
        )

        missing_columns = [
            column
            for column in export_columns
            if column not in split_result.dataframe.columns
        ]

        if missing_columns:
            raise TrainingDatasetDataError(
                f"Cannot persist '{target}': missing export columns "
                f"{missing_columns}"
            )

        split_frames = {
            "train": split_result.train,
            "validation": split_result.validation,
            "test": split_result.test,
        }

        target_manifest: dict[str, Any] = {
            "target_column": target,
            "availability_column": result.metadata.get(
                "target_to_availability",
                DEFAULT_TARGET_TO_AVAILABILITY,
            ).get(
                target,
                DEFAULT_TARGET_TO_AVAILABILITY.get(target),
            ),
            "feature_count": len(result.feature_columns),
            "export_column_count": len(export_columns),
            "feature_columns": list(result.feature_columns),
            "export_columns": list(export_columns),
            "splits": {},
        }

        for split_name, split_frame in split_frames.items():

            export_frame = (
                split_frame.loc[:, list(export_columns)]
                .copy()
            )

            output_file = (
                target_directory / f"{split_name}.parquet"
            )

            if output_file.exists() and not overwrite:
                raise TrainingDatasetError(
                    "Output file already exists and overwrite=False: "
                    f"{output_file}"
                )

            temporary_file = output_file.with_suffix(
                ".parquet.tmp"
            )

            if temporary_file.exists():
                temporary_file.unlink()

            export_frame.to_parquet(
                temporary_file,
                index=False,
                engine="pyarrow",
                compression="snappy",
            )

            temporary_file.replace(output_file)

            persisted_files.append(
                str(output_file)
            )

            target_manifest["splits"][split_name] = {
                "rows": len(export_frame),
                "columns": len(export_frame.columns),
                "path": str(output_file),
                "sha256": _sha256_file(output_file),
                "timestamp_min": _json_safe(
                    _timestamp_min(
                        export_frame,
                        result.metadata["timestamp_column"],
                    )
                ),
                "timestamp_max": _json_safe(
                    _timestamp_max(
                        export_frame,
                        result.metadata["timestamp_column"],
                    )
                ),
            }

        manifest_targets[target] = target_manifest

    manifest = {
        "schema_version": "1.0",
        "dataset_name": dataset_name,
        "source_name": BIRMINGHAM_SOURCE_NAME,
        "created_by": "birmingham_training_dataset.py",
        "storage_format": "parquet",
        "compression": "snappy",
        "feature_count": len(result.feature_columns),
        "target_count": len(result.target_columns),
        "target_availability_count": len(
            result.target_availability_columns
        ),
        "source_rows": len(result.source_dataframe),
        "facility_count": result.statistics["facility_count"],
        "feature_columns": list(result.feature_columns),
        "target_columns": list(result.target_columns),
        "target_availability_columns": list(
            result.target_availability_columns
        ),
        "facility_column": result.metadata["facility_column"],
        "timestamp_column": result.metadata["timestamp_column"],
        "split_policy": {
            "train_ratio": result.metadata["train_ratio"],
            "validation_ratio": result.metadata["validation_ratio"],
            "test_ratio": result.metadata["test_ratio"],
            "chronological_split": result.metadata["chronological_split"],
            "random_shuffle": result.metadata["random_shuffle"],
        },
        "leakage_contract": {
            "future_data_used": result.metadata["future_data_used"],
            "target_data_used_as_feature": result.metadata[
                "target_data_used_as_feature"
            ],
            "cross_facility_data_used": result.metadata[
                "cross_facility_data_used"
            ],
            "forward_lookup_used": result.metadata[
                "forward_lookup_used"
            ],
            "centered_windows_used": result.metadata[
                "centered_windows_used"
            ],
            "target_imputation": result.metadata["target_imputation"],
        },
        "targets": manifest_targets,
        "files": persisted_files,
        "statistics": _json_safe(result.statistics),
    }

    manifest_path = output_directory / "training_dataset_manifest.json"

    temporary_manifest = manifest_path.with_suffix(
        ".json.tmp"
    )

    temporary_manifest.write_text(
        json.dumps(
            _json_safe(manifest),
            indent=2,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    temporary_manifest.replace(manifest_path)

    return {
        "output_directory": str(output_directory),
        "manifest_path": str(manifest_path),
        "target_count": len(manifest_targets),
        "files": persisted_files,
        "manifest": manifest,
    }


# ============================================================================
# Reporting
# ============================================================================


def print_training_dataset_summary(
    result: BirminghamTrainingDatasetResult,
) -> None:
    """
    Print a concise but comprehensive training dataset summary.
    """

    print()
    print("=" * 78)
    print(
        "SMARTPARK AI - BIRMINGHAM TRAINING DATASET"
    )
    print("=" * 78)

    print()
    print("--- SOURCE ---")

    print(
        f"Rows:              "
        f"{len(result.source_dataframe):,}"
    )

    print(
        f"Facilities:        "
        f"{result.statistics['facility_count']}"
    )

    print(
        f"Features:          "
        f"{len(result.feature_columns)}"
    )

    print(
        f"Targets:           "
        f"{len(result.target_columns)}"
    )

    print()
    print("--- TARGET DATASETS ---")

    for target, split_result in (
        result.target_datasets.items()
    ):

        stats = split_result.statistics

        print()
        print(target)

        print(
            f"  Eligible:        "
            f"{stats['eligible_rows']:,}"
            f" / {stats['source_rows']:,}"
            f" ({stats['eligible_pct']:.2f}%)"
        )

        print(
            f"  Train:           "
            f"{stats['train_rows']:,}"
            f" ({stats['train_pct']:.2f}%)"
        )

        print(
            f"  Validation:      "
            f"{stats['validation_rows']:,}"
            f" ({stats['validation_pct']:.2f}%)"
        )

        print(
            f"  Test:            "
            f"{stats['test_rows']:,}"
            f" ({stats['test_pct']:.2f}%)"
        )

        print(
            f"  Target range:    "
            f"{stats['minimum']:.6f}"
            f" -> "
            f"{stats['maximum']:.6f}"
        )

        print(
            f"  Target mean:     "
            f"{stats['mean']:.6f}"
        )

        print(
            f"  Train end:       "
            f"{stats['train_end']}"
        )

        print(
            f"  Validation end:  "
            f"{stats['validation_end']}"
        )

    print()
    print("--- COMMON TARGET SUBSET ---")

    print(
        "Rows with all targets available: "
        f"{result.statistics['rows_with_all_targets_available']:,}"
    )

    print(
        "Percentage of source dataset: "
        f"{result.statistics['all_target_availability_pct']:.2f}%"
    )

    print()
    print("--- LEAKAGE CONTRACT ---")

    print(
        "Future data used:       "
        f"{result.metadata['future_data_used']}"
    )

    print(
        "Target data as feature: "
        f"{result.metadata['target_data_used_as_feature']}"
    )

    print(
        "Cross-facility data:    "
        f"{result.metadata['cross_facility_data_used']}"
    )

    print(
        "Forward lookup:         "
        f"{result.metadata['forward_lookup_used']}"
    )

    print(
        "Centered windows:       "
        f"{result.metadata['centered_windows_used']}"
    )

    print()
    print("--- SPLIT POLICY ---")

    print(
        "Chronological split:    "
        f"{result.metadata['chronological_split']}"
    )

    print(
        "Random shuffle:         "
        f"{result.metadata['random_shuffle']}"
    )

    print(
        "Target imputation:      "
        f"{result.metadata['target_imputation']}"
    )

    print()
    print("=" * 78)
    print(
        "BIRMINGHAM TRAINING DATASET BUILD COMPLETED"
    )
    print("=" * 78)
    print()


# ============================================================================
# CLI
# ============================================================================


def main() -> int:
    """
    Command-line entry point.
    """

    print()
    print("=" * 78)
    print(
        "SMARTPARK AI - BIRMINGHAM TRAINING DATASET BUILDER"
    )
    print("=" * 78)

    print()
    print("--- BUILDING COMPLETE BIRMINGHAM FEATURE DATASET ---")

    try:

        result = (
            build_birmingham_training_datasets()
        )

    except Exception as exc:

        print()
        print("BUILD FAILED")
        print(
            f"{type(exc).__name__}: {exc}"
        )

        return 1

    print_training_dataset_summary(
        result
    )

    print("--- VALIDATION ---")

    validation = (
        validate_training_dataset(
            result
        )
    )

    print(
        f"Valid:    "
        f"{validation['valid']}"
    )

    print(
        f"Errors:   "
        f"{validation['errors']}"
    )

    print(
        f"Warnings: "
        f"{validation['warnings']}"
    )

    if not validation["valid"]:

        return 1

    print()
    print(
        "ALL TRAINING DATASET VALIDATIONS PASSED"
    )

    print()
    print("--- PERSISTING PROCESSED TRAINING DATASETS ---")

    try:
        persistence = persist_birmingham_training_datasets(
            result,
            output_root=DEFAULT_PROCESSED_DATASET_ROOT,
            dataset_name="birmingham",
        )

    except Exception as exc:

        print()
        print("PERSISTENCE FAILED")
        print(
            f"{type(exc).__name__}: {exc}"
        )

        return 1

    print(
        f"Output directory: {persistence['output_directory']}"
    )
    print(
        f"Manifest:          {persistence['manifest_path']}"
    )
    print(
        f"Files persisted:   {len(persistence['files'])}"
    )

    print()
    print(
        "BIRMINGHAM TRAINING DATASETS PERSISTED SUCCESSFULLY"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )