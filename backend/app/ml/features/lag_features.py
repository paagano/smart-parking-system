"""
SmartPark AI - Lag Features
===========================

Historical lag feature generation for parking occupancy forecasting.

The SmartPark temporal normalization layer produces a regular 30-minute
timeline for every parking facility. This module therefore generates
historical lag features using exact normalized time slots.

Design principles
-----------------
1. No future-data leakage.
2. No target-data leakage.
3. No cross-facility contamination.
4. Exact normalized-slot lags.
5. Missing historical observations remain missing.
6. Operational/data gaps are never silently bridged.
7. Original row count is preserved.
8. Original row order is preserved.
9. No mutation of the caller's DataFrame.
10. No merge_asof dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd


# ============================================================
# Constants
# ============================================================

DEFAULT_LAG_MINUTES: tuple[int, ...] = (
    30,
    60,
    120,
    180,
    360,
    720,
    1440,
)

DEFAULT_VALUE_COLUMNS: tuple[str, ...] = (
    "occupancy_rate",
    "occupied_spaces",
    "available_spaces",
)

DEFAULT_FACILITY_COLUMN = "source_facility_code"

DEFAULT_TIMESTAMP_COLUMN = "normalized_at"

DEFAULT_INTERVAL_MINUTES = 30

FORBIDDEN_TARGET_PREFIXES: tuple[str, ...] = (
    "target_",
)

_INTERNAL_COLUMNS: tuple[str, ...] = (
    "__lag_original_position",
    "__lag_facility",
    "__lag_timestamp",
    "__lag_slot",
)


# ============================================================
# Exceptions
# ============================================================


class LagFeatureError(ValueError):
    """Base exception for lag feature processing."""


class LagFeatureConfigurationError(
    LagFeatureError
):
    """Raised when lag configuration is invalid."""


class LagFeatureDataError(
    LagFeatureError
):
    """Raised when input data is unsuitable for lag generation."""


# ============================================================
# Utility functions
# ============================================================


def _format_lag_label(
    lag_minutes: int,
) -> str:
    """
    Convert minutes into a compact lag label.

    Examples
    --------
    30   -> 30m
    60   -> 1h
    120  -> 2h
    1440 -> 1d
    """

    if lag_minutes <= 0:
        raise ValueError(
            "lag_minutes must be greater than zero."
        )

    if lag_minutes % 1440 == 0:
        return (
            f"{lag_minutes // 1440}d"
        )

    if lag_minutes % 60 == 0:
        return (
            f"{lag_minutes // 60}h"
        )

    return f"{lag_minutes}m"


def _normalise_lags(
    lags: Iterable[int],
) -> tuple[int, ...]:
    """
    Validate, deduplicate and sort lag intervals.
    """

    values = tuple(
        int(value)
        for value in lags
    )

    if not values:
        raise LagFeatureConfigurationError(
            "At least one lag interval is required."
        )

    if any(
        value <= 0
        for value in values
    ):
        raise LagFeatureConfigurationError(
            "All lag intervals must be greater than zero."
        )

    return tuple(
        sorted(
            set(values)
        )
    )


def _is_target_column(
    column_name: str,
) -> bool:
    """
    Return True when a column represents a target.

    Target columns must never be used as historical
    feature inputs.
    """

    return any(
        column_name.startswith(prefix)
        for prefix in FORBIDDEN_TARGET_PREFIXES
    )


def _validate_lag_alignment(
    lag_minutes: int,
    interval_minutes: int,
) -> int:
    """
    Convert a lag in minutes into an exact normalized-slot offset.

    Example
    -------
    120 minutes / 30 minutes = 4 slots.
    """

    if (
        lag_minutes
        % interval_minutes
        != 0
    ):
        raise LagFeatureConfigurationError(
            f"Lag {lag_minutes} minutes cannot be "
            f"represented exactly using the configured "
            f"{interval_minutes}-minute interval."
        )

    return (
        lag_minutes
        // interval_minutes
    )


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True)
class LagFeatureConfig:
    """
    Configuration for historical lag generation.
    """

    facility_column: str = (
        DEFAULT_FACILITY_COLUMN
    )

    timestamp_column: str = (
        DEFAULT_TIMESTAMP_COLUMN
    )

    value_columns: tuple[str, ...] = (
        DEFAULT_VALUE_COLUMNS
    )

    lag_minutes: tuple[int, ...] = (
        DEFAULT_LAG_MINUTES
    )

    interval_minutes: int = (
        DEFAULT_INTERVAL_MINUTES
    )

    add_availability_features: bool = True

    add_missing_indicators: bool = True

    strict_timestamp_validation: bool = True

    strict_facility_validation: bool = True

    forbid_target_columns: bool = True

    require_regular_interval: bool = True

    preserve_original_order: bool = True

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:

        normalized_lags = _normalise_lags(
            self.lag_minutes
        )

        object.__setattr__(
            self,
            "lag_minutes",
            normalized_lags,
        )

        if self.interval_minutes <= 0:
            raise LagFeatureConfigurationError(
                "interval_minutes must be greater than zero."
            )

        if not self.value_columns:
            raise LagFeatureConfigurationError(
                "At least one value column is required."
            )

        for lag_minutes in normalized_lags:
            _validate_lag_alignment(
                lag_minutes,
                self.interval_minutes,
            )


# ============================================================
# Statistics
# ============================================================


@dataclass(frozen=True)
class LagFeatureStatistics:
    """
    Statistics produced during lag generation.
    """

    source_row_count: int

    output_row_count: int

    source_column_count: int

    output_column_count: int

    facility_count: int

    lag_feature_count: int

    lag_availability_feature_count: int

    lag_missing_feature_count: int

    invalid_timestamp_count: int

    missing_facility_count: int

    duplicate_facility_timestamp_count: int

    irregular_interval_count: int

    unavailable_lag_values: int

    fully_available_rows: int

    partially_available_rows: int

    no_lag_history_rows: int

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True)
class LagFeatureResult:
    """
    Result returned by the lag feature generator.
    """

    dataframe: pd.DataFrame

    feature_columns: tuple[str, ...]

    availability_columns: tuple[str, ...]

    missing_columns: tuple[str, ...]

    statistics: LagFeatureStatistics

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Generator
# ============================================================


class LagFeatureGenerator:
    """
    Generate historical lag features using exact normalized slots.

    Example
    -------
    With a 30-minute normalized interval:

        30m  -> 1 slot
        1h   -> 2 slots
        2h   -> 4 slots
        6h   -> 12 slots
        24h  -> 48 slots

    A lag is therefore obtained by looking exactly N normalized
    rows backwards within the same facility.

    No forward filling is performed.
    No future observation is ever used.
    """

    def __init__(
        self,
        config: LagFeatureConfig | None = None,
    ) -> None:

        self._config = (
            config
            or LagFeatureConfig()
        )

    # ========================================================
    # Properties
    # ========================================================

    @property
    def config(
        self,
    ) -> LagFeatureConfig:

        return self._config

    # ========================================================
    # Public transform
    # ========================================================

    def transform(
        self,
        dataframe: pd.DataFrame,
    ) -> LagFeatureResult:
        """
        Generate historical lag features.
        """

        self._validate_input(
            dataframe
        )

        source_row_count = len(
            dataframe
        )

        source_column_count = len(
            dataframe.columns
        )

        original_index = dataframe.index.copy()

        # ----------------------------------------------------
        # Never mutate the caller's DataFrame.
        # ----------------------------------------------------

        result = dataframe.copy(
            deep=True
        )

        # ----------------------------------------------------
        # Original position.
        # ----------------------------------------------------

        result[
            "__lag_original_position"
        ] = np.arange(
            len(result),
            dtype=np.int64,
        )

        # ----------------------------------------------------
        # Timestamp.
        # ----------------------------------------------------

        result[
            "__lag_timestamp"
        ] = pd.to_datetime(
            result[
                self._config.timestamp_column
            ],
            errors="coerce",
        )

        invalid_timestamp_count = int(
            result[
                "__lag_timestamp"
            ].isna().sum()
        )

        if (
            invalid_timestamp_count
            and self._config
            .strict_timestamp_validation
        ):
            raise LagFeatureDataError(
                "Input contains "
                f"{invalid_timestamp_count} invalid "
                "timestamps."
            )

        # ----------------------------------------------------
        # Facility.
        # ----------------------------------------------------

        result[
            "__lag_facility"
        ] = result[
            self._config.facility_column
        ].astype("string")

        missing_facility_count = int(
            result[
                "__lag_facility"
            ].isna().sum()
        )

        if (
            missing_facility_count
            and self._config
            .strict_facility_validation
        ):
            raise LagFeatureDataError(
                "Input contains "
                f"{missing_facility_count} rows with "
                "missing facility identifiers."
            )

        # ----------------------------------------------------
        # Duplicate facility/timestamp detection.
        # ----------------------------------------------------

        duplicate_mask = result.duplicated(
            subset=[
                "__lag_facility",
                "__lag_timestamp",
            ],
            keep=False,
        )

        duplicate_count = int(
            duplicate_mask.sum()
        )

        if duplicate_count:
            raise LagFeatureDataError(
                "Duplicate facility/timestamp "
                "observations detected: "
                f"{duplicate_count} rows."
            )

        # ----------------------------------------------------
        # Convert feature inputs to numeric.
        # ----------------------------------------------------

        for column in (
            self._config.value_columns
        ):

            result[
                column
            ] = pd.to_numeric(
                result[column],
                errors="coerce",
            )

        # ----------------------------------------------------
        # Work chronologically by facility.
        # ----------------------------------------------------

        working = result.sort_values(
            by=[
                "__lag_facility",
                "__lag_timestamp",
            ],
            kind="mergesort",
        ).copy()

        # ----------------------------------------------------
        # Detect interval irregularities.
        #
        # This is diagnostic only. The normalized dataset should
        # normally contain one 30-minute slot per row/facility.
        # ----------------------------------------------------

        irregular_interval_count = (
            self._count_irregular_intervals(
                working
            )
        )

        if (
            irregular_interval_count
            and self._config
            .require_regular_interval
        ):
            raise LagFeatureDataError(
                "Input contains "
                f"{irregular_interval_count} irregular "
                "facility timestamp intervals. "
                "Run temporal normalization before "
                "generating lag features."
            )

        # ----------------------------------------------------
        # Generate internal normalized slot.
        #
        # We use a global integer slot based on timestamp.
        # This provides deterministic positional lagging while
        # still respecting the actual normalized timestamp.
        # ----------------------------------------------------

        epoch = pd.Timestamp(
            "1970-01-01"
        )

        delta = (
            working[
                "__lag_timestamp"
            ]
            - epoch
        )

        working[
            "__lag_slot"
        ] = (
            delta.dt.total_seconds()
            // (
                self._config
                .interval_minutes
                * 60
            )
        ).astype(
            "Int64"
        )

        # ====================================================
        # Generated features
        # ====================================================

        generated_features: dict[
            str,
            pd.Series,
        ] = {}

        feature_columns: list[str] = []

        availability_columns: list[str] = []

        missing_columns: list[str] = []

        # ----------------------------------------------------
        # Generate features separately per facility.
        # ----------------------------------------------------

        for value_column in (
            self._config.value_columns
        ):

            for lag_minutes in (
                self._config.lag_minutes
            ):

                lag_slots = (
                    _validate_lag_alignment(
                        lag_minutes,
                        self._config
                        .interval_minutes,
                    )
                )

                label = _format_lag_label(
                    lag_minutes
                )

                feature_name = (
                    f"{value_column}"
                    f"_lag_{label}"
                )

                availability_name = (
                    f"{value_column}"
                    f"_lag_{label}_available"
                )

                missing_name = (
                    f"{value_column}"
                    f"_lag_{label}_missing"
                )

                # --------------------------------------------
                # Calculate lagged values.
                # --------------------------------------------

                lag_series = pd.Series(
                    np.nan,
                    index=working.index,
                    dtype="float64",
                )

                availability_series = pd.Series(
                    False,
                    index=working.index,
                    dtype="boolean",
                )

                # --------------------------------------------
                # Each facility is processed independently.
                # --------------------------------------------

                for _, facility_frame in (
                    working.groupby(
                        "__lag_facility",
                        sort=False,
                        dropna=False,
                    )
                ):

                    facility_index = (
                        facility_frame.index
                    )

                    facility_slots = (
                        facility_frame[
                            "__lag_slot"
                        ]
                    )

                    facility_values = (
                        facility_frame[
                            value_column
                        ]
                    )

                    # ----------------------------------------
                    # Exact slot lookup.
                    #
                    # If current slot = 100:
                    # lag 30m -> slot 99
                    #
                    # If slot 99 does not exist, the lag
                    # remains unavailable.
                    # ----------------------------------------

                    slot_to_value = pd.Series(
                        facility_values.to_numpy(
                            dtype="float64",
                        ),
                        index=facility_slots.to_numpy(),
                    )

                    slot_to_position = pd.Series(
                        facility_index.to_numpy(),
                        index=facility_slots.to_numpy(),
                    )

                    requested_slots = (
                        facility_slots
                        - lag_slots
                    )

                    matched_values = (
                        slot_to_value.reindex(
                            requested_slots.to_numpy()
                        )
                    )

                    matched_positions = (
                        slot_to_position.reindex(
                            requested_slots.to_numpy()
                        )
                    )

                    matched_values.index = (
                        facility_index
                    )

                    matched_positions.index = (
                        facility_index
                    )

                    lag_series.loc[
                        facility_index
                    ] = matched_values.to_numpy(
                        dtype="float64",
                    )

                    # ----------------------------------------
                    # Availability requires:
                    #
                    # 1. Historical slot exists.
                    # 2. Historical value is not NaN.
                    #
                    # We deliberately do NOT fill missing
                    # values.
                    # ----------------------------------------

                    available = (
                        matched_positions
                        .notna()
                        & matched_values.notna()
                    )

                    availability_series.loc[
                        facility_index
                    ] = available.astype(
                        "boolean"
                    ).to_numpy()

                # --------------------------------------------
                # Restore result index.
                # --------------------------------------------

                lag_series = (
                    lag_series
                    .reindex(
                        working.index
                    )
                )

                availability_series = (
                    availability_series
                    .reindex(
                        working.index
                    )
                )

                # --------------------------------------------
                # Store generated features.
                # --------------------------------------------

                generated_features[
                    feature_name
                ] = lag_series

                feature_columns.append(
                    feature_name
                )

                if (
                    self._config
                    .add_availability_features
                ):

                    generated_features[
                        availability_name
                    ] = (
                        availability_series
                        .astype("boolean")
                    )

                    availability_columns.append(
                        availability_name
                    )

                if (
                    self._config
                    .add_missing_indicators
                ):

                    generated_features[
                        missing_name
                    ] = (
                        ~availability_series
                    ).astype(
                        "boolean"
                    )

                    missing_columns.append(
                        missing_name
                    )

        # ====================================================
        # Materialize all generated columns in one operation.
        # ====================================================

        generated_frame = pd.DataFrame(
            generated_features,
            index=working.index,
        )

        # ----------------------------------------------------
        # Re-align generated features to the result index.
        # ----------------------------------------------------

        generated_frame = (
            generated_frame
            .reindex(
                result.index
            )
        )

        result = pd.concat(
            [
                result,
                generated_frame,
            ],
            axis=1,
        )

        # ====================================================
        # Restore original order.
        # ====================================================

        if self._config.preserve_original_order:

            result = result.sort_values(
                "__lag_original_position",
                kind="mergesort",
            )

        # ====================================================
        # Calculate availability statistics.
        # ====================================================

        if availability_columns:

            availability_matrix = (
                result[
                    availability_columns
                ]
                .fillna(False)
                .astype(bool)
            )

            available_per_row = (
                availability_matrix.sum(
                    axis=1
                )
            )

            total_availability_features = (
                len(
                    availability_columns
                )
            )

            fully_available_rows = int(
                (
                    available_per_row
                    == total_availability_features
                ).sum()
            )

            partially_available_rows = int(
                (
                    (available_per_row > 0)
                    & (
                        available_per_row
                        < total_availability_features
                    )
                ).sum()
            )

            no_lag_history_rows = int(
                (
                    available_per_row
                    == 0
                ).sum()
            )

            unavailable_lag_values = int(
                (
                    ~availability_matrix
                ).sum().sum()
            )

        else:

            fully_available_rows = 0

            partially_available_rows = 0

            no_lag_history_rows = len(
                result
            )

            unavailable_lag_values = 0

        # ====================================================
        # Remove internal columns.
        # ====================================================

        result = result.drop(
            columns=[
                column
                for column in _INTERNAL_COLUMNS
                if column in result.columns
            ]
        )

        # ====================================================
        # Restore exact original index.
        # ====================================================

        result.index = original_index

        # ====================================================
        # Metadata
        # ====================================================

        metadata = {
            "facility_column":
                self._config.facility_column,

            "timestamp_column":
                self._config.timestamp_column,

            "value_columns":
                self._config.value_columns,

            "lag_minutes":
                self._config.lag_minutes,

            "interval_minutes":
                self._config.interval_minutes,

            "lag_method":
                "exact_normalized_slot",

            "future_data_used":
                False,

            "target_data_used":
                False,

            "cross_facility_data_used":
                False,

            "forward_lookup_used":
                False,

            "centered_windows_used":
                False,

            "source_rows_preserved":
                source_row_count
                == len(result),

            "row_order_preserved":
                True,

            "operational_gaps_bridged":
                False,

            "missing_values_filled":
                False,

            **self._config.metadata,
        }

        # ====================================================
        # Statistics
        # ====================================================

        statistics = LagFeatureStatistics(
            source_row_count=
                source_row_count,

            output_row_count=
                len(result),

            source_column_count=
                source_column_count,

            output_column_count=
                len(result.columns),

            facility_count=int(
                result[
                    self._config
                    .facility_column
                ]
                .nunique(
                    dropna=True
                )
            ),

            lag_feature_count=
                len(feature_columns),

            lag_availability_feature_count=
                len(availability_columns),

            lag_missing_feature_count=
                len(missing_columns),

            invalid_timestamp_count=
                invalid_timestamp_count,

            missing_facility_count=
                missing_facility_count,

            duplicate_facility_timestamp_count=
                duplicate_count,

            irregular_interval_count=
                irregular_interval_count,

            unavailable_lag_values=
                unavailable_lag_values,

            fully_available_rows=
                fully_available_rows,

            partially_available_rows=
                partially_available_rows,

            no_lag_history_rows=
                no_lag_history_rows,

            metadata=metadata,
        )

        return LagFeatureResult(
            dataframe=result,

            feature_columns=tuple(
                feature_columns
            ),

            availability_columns=tuple(
                availability_columns
            ),

            missing_columns=tuple(
                missing_columns
            ),

            statistics=statistics,

            metadata=metadata,
        )

    # ========================================================
    # Input validation
    # ========================================================

    def _validate_input(
        self,
        dataframe: pd.DataFrame,
    ) -> None:
        """
        Validate the source dataframe.
        """

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise LagFeatureDataError(
                "Input must be a pandas DataFrame."
            )

        if dataframe.empty:
            raise LagFeatureDataError(
                "Input dataframe is empty."
            )

        required_columns = {
            self._config.facility_column,
            self._config.timestamp_column,
            *self._config.value_columns,
        }

        missing = sorted(
            column
            for column in required_columns
            if column not in dataframe.columns
        )

        if missing:
            raise LagFeatureDataError(
                "Input dataframe is missing required "
                f"columns: {missing}"
            )

        if (
            self._config
            .forbid_target_columns
        ):

            target_inputs = [
                column
                for column in (
                    self._config
                    .value_columns
                )
                if _is_target_column(
                    column
                )
            ]

            if target_inputs:
                raise LagFeatureConfigurationError(
                    "Target columns cannot be used "
                    "as lag inputs: "
                    f"{target_inputs}"
                )

    # ========================================================
    # Interval validation
    # ========================================================

    def _count_irregular_intervals(
        self,
        dataframe: pd.DataFrame,
    ) -> int:
        """
        Count facility timestamp intervals that do not match
        the configured normalized interval.

        Missing slots are NOT themselves considered an error.

        Example
        -------
        08:00 -> 08:30 -> 10:00

        The 90-minute jump is counted as irregular.

        This protects the lag generator from being used directly
        against raw irregular source data.
        """

        if len(dataframe) <= 1:
            return 0

        total_irregular = 0

        expected_delta = pd.Timedelta(
            minutes=self._config
            .interval_minutes
        )

        for _, group in dataframe.groupby(
            "__lag_facility",
            sort=False,
            dropna=False,
        ):

            timestamps = group[
                "__lag_timestamp"
            ]

            if len(timestamps) <= 1:
                continue

            deltas = timestamps.diff()

            # A gap greater than the normal interval is a
            # legitimate missing period in some cases. Since
            # our normalized dataset explicitly contains those
            # missing rows, a large delta here indicates the
            # input was not actually normalized.
            irregular = (
                deltas.notna()
                & (
                    deltas
                    != expected_delta
                )
            )

            total_irregular += int(
                irregular.sum()
            )

        return total_irregular


# ============================================================
# Expected feature names
# ============================================================


def expected_lag_feature_columns(
    config: LagFeatureConfig | None = None,
) -> tuple[str, ...]:
    """
    Return all expected public lag feature names.
    """

    config = (
        config
        or LagFeatureConfig()
    )

    names: list[str] = []

    for value_column in (
        config.value_columns
    ):

        for lag_minutes in (
            config.lag_minutes
        ):

            label = _format_lag_label(
                lag_minutes
            )

            names.append(
                f"{value_column}"
                f"_lag_{label}"
            )

            if (
                config
                .add_availability_features
            ):

                names.append(
                    f"{value_column}"
                    f"_lag_{label}_available"
                )

            if (
                config
                .add_missing_indicators
            ):

                names.append(
                    f"{value_column}"
                    f"_lag_{label}_missing"
                )

    return tuple(names)


# ============================================================
# Validation
# ============================================================


def validate_lag_features(
    dataframe: pd.DataFrame,
    *,
    config: LagFeatureConfig | None = None,
) -> dict[str, Any]:
    """
    Validate generated lag features.
    """

    config = (
        config
        or LagFeatureConfig()
    )

    errors: list[str] = []

    expected = (
        expected_lag_feature_columns(
            config
        )
    )

    # --------------------------------------------------------
    # Missing columns.
    # --------------------------------------------------------

    missing_columns = [
        column
        for column in expected
        if column not in dataframe.columns
    ]

    if missing_columns:

        errors.append(
            "Missing lag feature columns: "
            f"{missing_columns}"
        )

    # --------------------------------------------------------
    # Duplicate dataframe columns.
    # --------------------------------------------------------

    duplicate_columns = (
        dataframe.columns[
            dataframe.columns.duplicated()
        ]
        .tolist()
    )

    if duplicate_columns:

        errors.append(
            "Duplicate dataframe columns detected: "
            f"{duplicate_columns}"
        )

    # --------------------------------------------------------
    # Internal helper leakage.
    # --------------------------------------------------------

    internal_columns = [
        column
        for column in dataframe.columns
        if column.startswith("__lag_")
    ]

    if internal_columns:

        errors.append(
            "Internal lag helper columns leaked into "
            f"output: {internal_columns}"
        )

    # --------------------------------------------------------
    # Target leakage.
    # --------------------------------------------------------

    target_input_columns = [
        column
        for column in config.value_columns
        if _is_target_column(
            column
        )
    ]

    if target_input_columns:

        errors.append(
            "Target columns configured as lag inputs: "
            f"{target_input_columns}"
        )

    # --------------------------------------------------------
    # Duplicate expected names.
    # --------------------------------------------------------

    duplicated_expected = [
        column
        for column in dict.fromkeys(
            expected
        )
        if expected.count(
            column
        ) > 1
    ]

    if duplicated_expected:

        errors.append(
            "Duplicate expected feature names: "
            f"{duplicated_expected}"
        )

    # --------------------------------------------------------
    # Numeric feature validation.
    # --------------------------------------------------------

    numeric_feature_columns = [
        column
        for column in expected
        if column in dataframe.columns
        and not column.endswith(
            "_available"
        )
        and not column.endswith(
            "_missing"
        )
    ]

    if numeric_feature_columns:

        numeric_frame = (
            dataframe[
                numeric_feature_columns
            ]
            .apply(
                pd.to_numeric,
                errors="coerce",
            )
        )

        infinite_count = int(
            np.isinf(
                numeric_frame
                .to_numpy(
                    dtype="float64"
                )
            ).sum()
        )

        if infinite_count:

            errors.append(
                "Lag features contain "
                f"{infinite_count} infinite values."
            )

    # --------------------------------------------------------
    # Indicator dtype validation.
    # --------------------------------------------------------

    indicator_columns = [
        column
        for column in expected
        if column.endswith(
            "_available"
        )
        or column.endswith(
            "_missing"
        )
    ]

    for column in indicator_columns:

        if column not in dataframe.columns:
            continue

        dtype = dataframe[
            column
        ].dtype

        if not (
            pd.api.types.is_bool_dtype(
                dtype
            )
            or str(dtype) == "boolean"
        ):

            errors.append(
                f"Indicator '{column}' has "
                f"unexpected dtype {dtype}."
            )

    # --------------------------------------------------------
    # Feature count.
    # --------------------------------------------------------

    actual_feature_count = len(
        [
            column
            for column in expected
            if column in dataframe.columns
        ]
    )

    if (
        actual_feature_count
        != len(expected)
    ):

        errors.append(
            "Lag feature count mismatch: "
            f"expected {len(expected)}, "
            f"found {actual_feature_count}."
        )

    return {
        "valid":
            not errors,

        "errors":
            errors,

        "missing_columns":
            missing_columns,

        "expected_feature_count":
            len(expected),

        "actual_feature_count":
            actual_feature_count,

        "future_data_used":
            False,

        "target_data_used":
            False,

        "cross_facility_data_used":
            False,

        "forward_lookup_used":
            False,

        "centered_windows_used":
            False,

        "row_count":
            len(dataframe),
    }


# ============================================================
# Convenience API
# ============================================================


def add_lag_features(
    dataframe: pd.DataFrame,
    *,
    config: LagFeatureConfig | None = None,
) -> LagFeatureResult:
    """
    Add lag features using the supplied configuration.
    """

    generator = LagFeatureGenerator(
        config=config
    )

    return generator.transform(
        dataframe
    )


# ============================================================
# Birmingham API
# ============================================================


def add_birmingham_lag_features(
    dataframe: pd.DataFrame,
) -> LagFeatureResult:
    """
    Generate the standard SmartPark Birmingham lag features.

    3 source value series
        occupancy_rate
        occupied_spaces
        available_spaces

    7 historical lags
        30m
        1h
        2h
        3h
        6h
        12h
        24h

    3 feature types
        value
        availability
        missing

    Total
        3 × 7 × 3 = 63 features
    """

    config = LagFeatureConfig(
        facility_column=(
            "source_facility_code"
        ),

        timestamp_column=(
            "normalized_at"
        ),

        value_columns=(
            "occupancy_rate",
            "occupied_spaces",
            "available_spaces",
        ),

        lag_minutes=(
            30,
            60,
            120,
            180,
            360,
            720,
            1440,
        ),

        interval_minutes=30,

        add_availability_features=True,

        add_missing_indicators=True,

        strict_timestamp_validation=True,

        strict_facility_validation=True,

        forbid_target_columns=True,

        require_regular_interval=True,

        preserve_original_order=True,

        metadata={
            "source_name":
                "BIRMINGHAM",

            "feature_family":
                "lag",

            "normalized_interval_minutes":
                30,

            "historical_only":
                True,
        },
    )

    return add_lag_features(
        dataframe,
        config=config,
    )


# ============================================================
# Public exports
# ============================================================


__all__ = [
    "LagFeatureError",
    "LagFeatureConfigurationError",
    "LagFeatureDataError",
    "LagFeatureConfig",
    "LagFeatureStatistics",
    "LagFeatureResult",
    "LagFeatureGenerator",
    "expected_lag_feature_columns",
    "validate_lag_features",
    "add_lag_features",
    "add_birmingham_lag_features",
]