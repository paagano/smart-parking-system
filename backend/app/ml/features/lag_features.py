"""
SmartPark AI - Lag Feature Engineering.

This module creates historical lag features for parking occupancy
time-series data.

Pipeline position
-----------------

    ML Dataset
        |
        v
    Temporal Features
        |
        v
    Occupancy Features
        |
        v
    Lag Features             <-- this module
        |
        v
    Rolling Features
        |
        v
    Demand Features
        |
        v
    Feature Pipeline
        |
        +-------------> XGBoost
        |
        +-------------> LSTM


Design principles
-----------------

1. Lag features are calculated independently per facility.
2. No future observations are used.
3. Target columns are never used.
4. The input dataframe is never modified.
5. Missing observations are preserved as missing.
6. Sequence breaks are respected.
7. Lags are based on actual chronological timestamps.
8. A lag is only considered valid when the requested historical
   timestamp exists in the expected time-series grid.
9. The implementation is source-independent.
10. Birmingham is only a convenience wrapper.
11. The module is deterministic and reproducible.

Default lags
------------

Because the Birmingham dataset is normalized to 30-minute
intervals, the default horizons are:

    30 minutes
    1 hour
    2 hours
    3 hours
    6 hours
    12 hours
    24 hours
    7 days

These translate to:

    1 slot
    2 slots
    4 slots
    6 slots
    12 slots
    24 slots
    48 slots
    336 slots

The actual timestamp arithmetic is used rather than relying only
on row offsets. This protects the implementation from irregular
data and missing rows.


Generated feature examples
--------------------------

    occupancy_rate_lag_30m
    occupancy_rate_lag_1h
    occupancy_rate_lag_2h
    occupancy_rate_lag_3h
    occupancy_rate_lag_6h
    occupancy_rate_lag_12h
    occupancy_rate_lag_24h
    occupancy_rate_lag_7d

    occupied_spaces_lag_30m
    occupied_spaces_lag_1h
    ...

    available_spaces_lag_30m
    available_spaces_lag_1h
    ...

Additional lag-validity indicators are generated:

    occupancy_rate_lag_30m_available
    occupancy_rate_lag_1h_available
    ...

These indicators allow downstream models to distinguish between:

    "historical occupancy was genuinely unavailable"

and

    "historical occupancy was zero."

This is important for a regularized time-series dataset.
"""


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


# ============================================================
# Constants
# ============================================================

DEFAULT_FACILITY_COLUMN = (
    "source_facility_code"
)

DEFAULT_TIMESTAMP_COLUMN = (
    "normalized_at"
)

DEFAULT_VALUE_COLUMNS: tuple[str, ...] = (
    "occupancy_rate",
    "occupied_spaces",
    "available_spaces",
)

DEFAULT_LAG_MINUTES: tuple[int, ...] = (
    30,
    60,
    120,
    180,
    360,
    720,
    1440,
    10080,
)


# ============================================================
# Exceptions
# ============================================================


class LagFeatureError(Exception):
    """Base exception for lag feature engineering."""


class LagFeatureSchemaError(
    LagFeatureError
):
    """Raised when required input columns are missing."""


class LagFeatureDataError(
    LagFeatureError
):
    """Raised when lag feature input data is invalid."""


class LagFeatureConfigurationError(
    LagFeatureError
):
    """Raised when lag configuration is invalid."""


# ============================================================
# Helper functions
# ============================================================


def _format_lag_label(
    minutes: int,
) -> str:
    """
    Convert minutes into a stable human-readable label.

    Examples
    --------
    30      -> 30m
    60      -> 1h
    120     -> 2h
    1440    -> 24h
    10080   -> 7d
    """

    if minutes % 10080 == 0:
        return f"{minutes // 10080}d"

    if minutes % 1440 == 0:
        return f"{minutes // 1440}d"

    if minutes % 60 == 0:
        return f"{minutes // 60}h"

    return f"{minutes}m"


def _validate_lag_minutes(
    lag_minutes: Sequence[int],
) -> tuple[int, ...]:
    """
    Validate and normalize lag definitions.
    """

    if not lag_minutes:

        raise LagFeatureConfigurationError(
            "At least one lag horizon must be configured."
        )

    normalized: list[int] = []

    for value in lag_minutes:

        if isinstance(value, bool):

            raise LagFeatureConfigurationError(
                "Lag horizons must be positive integers."
            )

        try:
            value = int(value)

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise LagFeatureConfigurationError(
                f"Invalid lag horizon: {value!r}"
            ) from exc

        if value <= 0:

            raise LagFeatureConfigurationError(
                "Lag horizons must be greater than zero."
            )

        normalized.append(value)

    if len(set(normalized)) != len(normalized):

        raise LagFeatureConfigurationError(
            "Lag horizons must not contain duplicates."
        )

    return tuple(
        sorted(normalized)
    )


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class LagFeatureConfig:
    """
    Configuration for lag feature generation.

    Parameters
    ----------
    facility_column:
        Column identifying the parking facility.

    timestamp_column:
        Chronological timestamp column.

    value_columns:
        Numeric time-series columns from which lag features
        should be generated.

    lag_minutes:
        Historical lag horizons in minutes.

    interval_minutes:
        Expected temporal interval of the normalized dataset.

    require_exact_timestamp:
        When True, the lagged timestamp must exist exactly in
        the facility's normalized time series.

    respect_sequence_breaks:
        When True, lag values are invalidated when the source
        observation belongs to a broken sequence.

    respect_observation_presence:
        When True, a missing observation cannot be used as a
        valid lag value.

    add_availability_flags:
        Whether to add *_available columns.

    add_age_features:
        Whether to add lag-age information.

    include_current_value_columns:
        Whether current values should be included in the
        generated feature list.

        Normally False because the input dataset already contains
        current-state features.

    allow_duplicate_timestamps:
        Whether duplicate facility/timestamp records are allowed.

    sort_output:
        Whether to return rows sorted by facility and timestamp.
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

    interval_minutes: int = 30

    require_exact_timestamp: bool = True

    respect_sequence_breaks: bool = True

    respect_observation_presence: bool = True

    add_availability_flags: bool = True

    add_age_features: bool = False

    include_current_value_columns: bool = False

    allow_duplicate_timestamps: bool = False

    sort_output: bool = True

    def __post_init__(self) -> None:

        if not self.facility_column.strip():

            raise LagFeatureConfigurationError(
                "facility_column cannot be empty."
            )

        if not self.timestamp_column.strip():

            raise LagFeatureConfigurationError(
                "timestamp_column cannot be empty."
            )

        if not self.value_columns:

            raise LagFeatureConfigurationError(
                "At least one value column is required."
            )

        if any(
            not str(column).strip()
            for column in self.value_columns
        ):

            raise LagFeatureConfigurationError(
                "Value column names cannot be empty."
            )

        if self.interval_minutes <= 0:

            raise LagFeatureConfigurationError(
                "interval_minutes must be greater than zero."
            )

        normalized_lags = _validate_lag_minutes(
            self.lag_minutes
        )

        object.__setattr__(
            self,
            "lag_minutes",
            normalized_lags,
        )


# ============================================================
# Statistics
# ============================================================


@dataclass(frozen=True, slots=True)
class LagFeatureStatistics:
    """Statistics describing lag feature generation."""

    source_row_count: int

    output_row_count: int

    source_column_count: int

    output_column_count: int

    facility_count: int

    duplicate_facility_timestamp_count: int

    invalid_timestamp_count: int

    missing_facility_count: int

    lag_feature_count: int

    lag_available_feature_count: int

    total_lag_requests: int

    successful_lag_requests: int

    unavailable_lag_requests: int

    sequence_break_rows: int

    observed_rows: int

    missing_rows: int

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True, slots=True)
class LagFeatureResult:
    """
    Result returned by the lag feature generator.
    """

    dataframe: pd.DataFrame

    statistics: LagFeatureStatistics

    feature_columns: tuple[str, ...]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Generator
# ============================================================


class LagFeatureGenerator:
    """
    Generate historical lag features independently per facility.

    The implementation uses timestamp-based lookup rather than
    blind DataFrame shifting.

    This is important because the normalized SmartPark dataset
    contains missing observations.
    """

    def __init__(
        self,
        config: LagFeatureConfig | None = None,
    ) -> None:

        self._config = (
            config
            if config is not None
            else LagFeatureConfig()
        )

    # ========================================================
    # Public API
    # ========================================================

    def transform(
        self,
        dataframe: pd.DataFrame,
    ) -> LagFeatureResult:
        """
        Generate lag features.

        The input dataframe is never modified.
        """

        self._validate_input(
            dataframe
        )

        source_row_count = len(
            dataframe
        )

        source_column_count = (
            dataframe.shape[1]
        )

        result = dataframe.copy(
            deep=True
        )

        # ----------------------------------------------------
        # Preserve original ordering when requested.
        # ----------------------------------------------------

        result[
            "__lag_original_order"
        ] = np.arange(
            len(result),
            dtype=np.int64,
        )

        # ----------------------------------------------------
        # Normalize timestamp locally.
        # ----------------------------------------------------

        result[
            "__lag_timestamp"
        ] = pd.to_datetime(
            result[
                self._config
                .timestamp_column
            ],
            errors="coerce",
        )

        invalid_timestamp_count = int(
            result[
                "__lag_timestamp"
            ].isna().sum()
        )

        if invalid_timestamp_count:

            raise LagFeatureDataError(
                "Lag feature generation encountered "
                f"{invalid_timestamp_count} invalid "
                "timestamps."
            )

        # ----------------------------------------------------
        # Normalize facility identifiers.
        # ----------------------------------------------------

        facility_series = result[
            self._config
            .facility_column
        ]

        missing_facility_mask = (
            facility_series.isna()
            | (
                facility_series
                .astype("string")
                .str.strip()
                .eq("")
            )
        )

        missing_facility_count = int(
            missing_facility_mask.sum()
        )

        if missing_facility_count:

            raise LagFeatureDataError(
                "Lag feature generation encountered "
                f"{missing_facility_count} rows with "
                "missing facility identifiers."
            )

        # ----------------------------------------------------
        # Check duplicate facility/timestamp pairs.
        # ----------------------------------------------------

        duplicate_mask = result.duplicated(
            subset=[
                self._config
                .facility_column,
                "__lag_timestamp",
            ],
            keep=False,
        )

        duplicate_count = int(
            duplicate_mask.sum()
        )

        if (
            duplicate_count
            and not self._config
            .allow_duplicate_timestamps
        ):

            raise LagFeatureDataError(
                "Duplicate facility/timestamp records "
                f"detected: {duplicate_count} rows."
            )

        # ----------------------------------------------------
        # Sort internally.
        # ----------------------------------------------------

        result = result.sort_values(
            by=[
                self._config
                .facility_column,
                "__lag_timestamp",
            ],
            kind="mergesort",
        ).copy()

        # ----------------------------------------------------
        # Determine observation presence.
        # ----------------------------------------------------

        observation_present = (
            self._derive_observation_presence(
                result
            )
        )

        result[
            "__lag_observation_present"
        ] = observation_present

        # ----------------------------------------------------
        # Sequence-break information.
        # ----------------------------------------------------

        sequence_break = (
            self._derive_sequence_break(
                result
            )
        )

        result[
            "__lag_sequence_break"
        ] = sequence_break

        sequence_break_rows = int(
            sequence_break.sum()
        )

        observed_rows = int(
            observation_present.sum()
        )

        missing_rows = int(
            (~observation_present).sum()
        )

        # ----------------------------------------------------
        # Generate lag features.
        # ----------------------------------------------------

        feature_columns: list[str] = []

        lag_available_columns: list[str] = []

        total_lag_requests = 0

        successful_lag_requests = 0

        unavailable_lag_requests = 0

        for value_column in (
            self._config.value_columns
        ):

            value_series = pd.to_numeric(
                result[value_column],
                errors="coerce",
            )

            for lag_minutes in (
                self._config.lag_minutes
            ):

                label = _format_lag_label(
                    lag_minutes
                )

                feature_name = (
                    f"{value_column}_lag_{label}"
                )

                available_name = (
                    f"{feature_name}_available"
                )

                lag_values, available = (
                    self._build_single_lag(
                        result=result,
                        value_series=value_series,
                        lag_minutes=lag_minutes,
                    )
                )

                result[
                    feature_name
                ] = lag_values

                feature_columns.append(
                    feature_name
                )

                total_lag_requests += (
                    len(result)
                )

                successful_count = int(
                    available.sum()
                )

                successful_lag_requests += (
                    successful_count
                )

                unavailable_lag_requests += (
                    len(result)
                    - successful_count
                )

                if (
                    self._config
                    .add_availability_flags
                ):

                    result[
                        available_name
                    ] = available.astype(
                        "boolean"
                    )

                    lag_available_columns.append(
                        available_name
                    )

                    feature_columns.append(
                        available_name
                    )

                if (
                    self._config
                    .add_age_features
                ):

                    age_name = (
                        f"{feature_name}_age_minutes"
                    )

                    age_values = (
                        self._build_lag_age(
                            result=result,
                            lag_minutes=(
                                lag_minutes
                            ),
                            available=available,
                        )
                    )

                    result[
                        age_name
                    ] = age_values

                    feature_columns.append(
                        age_name
                    )

        # ----------------------------------------------------
        # Remove internal columns.
        # ----------------------------------------------------

        result = result.drop(
            columns=[
                "__lag_timestamp",
                "__lag_observation_present",
                "__lag_sequence_break",
                "__lag_original_order",
            ]
        )

        # ----------------------------------------------------
        # Restore original ordering if requested.
        #
        # Because the helper column has already been dropped,
        # sorting by the original index is safest when the
        # original index is unique.
        # ----------------------------------------------------

        if self._config.sort_output:

            result = self._restore_order(
                result,
                dataframe,
            )

        # ----------------------------------------------------
        # Statistics.
        # ----------------------------------------------------

        statistics = LagFeatureStatistics(
            source_row_count=(
                source_row_count
            ),
            output_row_count=len(
                result
            ),
            source_column_count=(
                source_column_count
            ),
            output_column_count=(
                result.shape[1]
            ),
            facility_count=int(
                dataframe[
                    self._config
                    .facility_column
                ].nunique()
            ),
            duplicate_facility_timestamp_count=(
                duplicate_count
            ),
            invalid_timestamp_count=(
                invalid_timestamp_count
            ),
            missing_facility_count=(
                missing_facility_count
            ),
            lag_feature_count=len(
                feature_columns
            ),
            lag_available_feature_count=len(
                lag_available_columns
            ),
            total_lag_requests=(
                total_lag_requests
            ),
            successful_lag_requests=(
                successful_lag_requests
            ),
            unavailable_lag_requests=(
                unavailable_lag_requests
            ),
            sequence_break_rows=(
                sequence_break_rows
            ),
            observed_rows=(
                observed_rows
            ),
            missing_rows=(
                missing_rows
            ),
            metadata={
                "facility_column": (
                    self._config
                    .facility_column
                ),
                "timestamp_column": (
                    self._config
                    .timestamp_column
                ),
                "value_columns": (
                    self._config
                    .value_columns
                ),
                "lag_minutes": (
                    self._config
                    .lag_minutes
                ),
                "interval_minutes": (
                    self._config
                    .interval_minutes
                ),
                "require_exact_timestamp": (
                    self._config
                    .require_exact_timestamp
                ),
                "respect_sequence_breaks": (
                    self._config
                    .respect_sequence_breaks
                ),
                "respect_observation_presence": (
                    self._config
                    .respect_observation_presence
                ),
                "future_data_used": False,
                "target_data_used": False,
                "cross_facility_data_used": False,
            },
        )

        return LagFeatureResult(
            dataframe=result,
            statistics=statistics,
            feature_columns=tuple(
                feature_columns
            ),
            metadata={
                "generator": (
                    "LagFeatureGenerator"
                ),
                "future_data_used": False,
                "target_data_used": False,
                "cross_facility_data_used": False,
            },
        )

    # ========================================================
    # Input validation
    # ========================================================

    def _validate_input(
        self,
        dataframe: pd.DataFrame,
    ) -> None:

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):

            raise LagFeatureDataError(
                "LagFeatureGenerator requires "
                "a pandas DataFrame."
            )

        if dataframe.empty:

            raise LagFeatureDataError(
                "Cannot generate lag features "
                "from an empty dataframe."
            )

        required_columns = [
            self._config
            .facility_column,
            self._config
            .timestamp_column,
            *self._config.value_columns,
        ]

        missing_columns = [
            column
            for column in required_columns
            if column not in dataframe.columns
        ]

        if missing_columns:

            raise LagFeatureSchemaError(
                "Required lag feature columns are "
                f"missing: {missing_columns}"
            )

        # ----------------------------------------------------
        # Protect against accidental target usage.
        # ----------------------------------------------------

        target_prefixes = (
            "target_",
        )

        target_columns = [
            column
            for column in self._config.value_columns
            if any(
                column.startswith(prefix)
                for prefix in target_prefixes
            )
        ]

        if target_columns:

            raise LagFeatureConfigurationError(
                "Target columns cannot be used as lag "
                f"values: {target_columns}"
            )

    # ========================================================
    # Observation presence
    # ========================================================

    def _derive_observation_presence(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.Series:
        """
        Determine whether a normalized time slot contains
        an actual observation.

        Preferred source:

            observation_present

        Fallback:

            occupancy_rate.notna()
        """

        if "observation_present" in dataframe.columns:

            values = dataframe[
                "observation_present"
            ]

            return (
                values
                .fillna(False)
                .astype(bool)
            )

        if (
            "occupancy_rate"
            in dataframe.columns
        ):

            return (
                dataframe[
                    "occupancy_rate"
                ]
                .notna()
            )

        first_value_column = (
            self._config
            .value_columns[0]
        )

        return (
            dataframe[
                first_value_column
            ]
            .notna()
        )

    # ========================================================
    # Sequence breaks
    # ========================================================

    def _derive_sequence_break(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.Series:
        """
        Determine whether a row starts a broken temporal sequence.

        A sequence is continuous when the timestamp difference
        from the previous row for the same facility equals the
        configured interval.

        Missing rows therefore naturally create sequence breaks.
        """

        timestamps = dataframe[
            "__lag_timestamp"
        ]

        facilities = dataframe[
            self._config
            .facility_column
        ]

        previous_timestamp = (
            timestamps.groupby(
                facilities,
                sort=False,
            ).shift(1)
        )

        previous_facility = (
            facilities.groupby(
                facilities,
                sort=False,
            ).shift(1)
        )

        time_delta = (
            timestamps
            - previous_timestamp
        )

        expected_delta = pd.Timedelta(
            minutes=self._config
            .interval_minutes
        )

        same_facility = (
            facilities.astype("string")
            == previous_facility.astype("string")
        )

        continuous = (
            same_facility
            & (
                time_delta
                == expected_delta
            )
        )

        # First row of every facility is a sequence start,
        # rather than a sequence break.
        sequence_break = (
            ~continuous
            & previous_timestamp.notna()
        )

        return sequence_break.astype(bool)

    # ========================================================
    # Single lag
    # ========================================================

    def _build_single_lag(
        self,
        *,
        result: pd.DataFrame,
        value_series: pd.Series,
        lag_minutes: int,
    ) -> tuple[pd.Series, pd.Series]:
        """
        Build one facility-specific historical lag.

        Timestamp lookup is used rather than DataFrame.shift().
        """

        lag_delta = pd.Timedelta(
            minutes=lag_minutes
        )

        current_timestamp = (
            result[
                "__lag_timestamp"
            ]
        )

        facilities = (
            result[
                self._config
                .facility_column
            ]
        )

        lookup_frame = pd.DataFrame(
            {
                "__facility": (
                    facilities.astype("string")
                ),
                "__timestamp": (
                    current_timestamp
                ),
                "__value": value_series,
                "__observation_present": (
                    result[
                        "__lag_observation_present"
                    ]
                ),
                "__sequence_break": (
                    result[
                        "__lag_sequence_break"
                    ]
                ),
            },
            index=result.index,
        )

        # ----------------------------------------------------
        # Construct historical lookup timestamp.
        # ----------------------------------------------------

        lookup_frame[
            "__lag_timestamp"
        ] = (
            lookup_frame[
                "__timestamp"
            ]
            - lag_delta
        )

        # ----------------------------------------------------
        # Build lookup table.
        # ----------------------------------------------------

        historical = lookup_frame[
            [
                "__facility",
                "__timestamp",
                "__value",
                "__observation_present",
                "__sequence_break",
            ]
        ].copy()

        historical = historical.rename(
            columns={
                "__timestamp": (
                    "__historical_timestamp"
                ),
                "__value": (
                    "__historical_value"
                ),
                "__observation_present": (
                    "__historical_observation_present"
                ),
                "__sequence_break": (
                    "__historical_sequence_break"
                ),
            }
        )

        # ----------------------------------------------------
        # Merge historical observation onto current rows.
        # ----------------------------------------------------

        current = lookup_frame[
            [
                "__facility",
                "__lag_timestamp",
            ]
        ].copy()

        current[
            "__row_identifier"
        ] = np.arange(
            len(current),
            dtype=np.int64,
        )

        merged = current.merge(
            historical,
            left_on=[
                "__facility",
                "__lag_timestamp",
            ],
            right_on=[
                "__facility",
                "__historical_timestamp",
            ],
            how="left",
            sort=False,
        )

        # ----------------------------------------------------
        # Restore deterministic row order.
        # ----------------------------------------------------

        merged = merged.sort_values(
            "__row_identifier",
            kind="mergesort",
        )

        historical_available = (
            merged[
                "__historical_value"
            ].notna()
        )

        if (
            self._config
            .respect_observation_presence
        ):

            historical_available &= (
                merged[
                    "__historical_observation_present"
                ]
                .fillna(False)
                .astype(bool)
            )

        if (
            self._config
            .respect_sequence_breaks
        ):

            historical_available &= ~(
                merged[
                    "__historical_sequence_break"
                ]
                .fillna(False)
                .astype(bool)
            )

        if (
            self._config
            .require_exact_timestamp
        ):

            # The merge itself is exact. This explicit condition
            # makes the intent obvious and protects the behaviour
            # if the implementation changes later.
            historical_available &= (
                merged[
                    "__historical_timestamp"
                ].notna()
            )

        lag_values = (
            merged[
                "__historical_value"
            ]
            .where(
                historical_available,
                np.nan,
            )
            .reset_index(drop=True)
        )

        availability = (
            historical_available
            .astype(bool)
            .reset_index(drop=True)
        )

        lag_values.index = result.index

        availability.index = result.index

        return (
            lag_values,
            availability,
        )

    # ========================================================
    # Lag age
    # ========================================================

    def _build_lag_age(
        self,
        *,
        result: pd.DataFrame,
        lag_minutes: int,
        available: pd.Series,
    ) -> pd.Series:
        """
        Build the age of the requested historical observation.

        For exact normalized timestamps this will normally equal
        the requested lag.

        The feature is optional and disabled by default.
        """

        values = pd.Series(
            np.nan,
            index=result.index,
            dtype="float64",
        )

        values.loc[
            available
        ] = float(lag_minutes)

        return values

    # ========================================================
    # Restore order
    # ========================================================

    @staticmethod
    def _restore_order(
        result: pd.DataFrame,
        original: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Restore the original row order.

        The implementation handles both unique and duplicate
        indexes.
        """

        if len(result) != len(original):

            raise LagFeatureDataError(
                "Lag feature generation changed the "
                "number of rows."
            )

        # If index is unique, reindex is sufficient.
        if original.index.is_unique:

            return result.reindex(
                original.index
            )

        # For duplicate indexes, use positional restoration.
        # This is uncommon for the ML dataset but is safer.
        result = result.copy()

        result[
            "__restore_position"
        ] = np.arange(
            len(result),
            dtype=np.int64,
        )

        # Since the internal sorting was based on facility/time,
        # the positional order no longer corresponds to original
        # order. Therefore use the original index occurrence mapping.
        original_keys = pd.DataFrame(
            {
                "__index": original.index,
                "__position": np.arange(
                    len(original),
                    dtype=np.int64,
                ),
            }
        )

        result_keys = pd.DataFrame(
            {
                "__index": result.index,
                "__result_position": np.arange(
                    len(result),
                    dtype=np.int64,
                ),
            }
        )

        result_keys[
            "__occurrence"
        ] = (
            result_keys
            .groupby(
                "__index",
                sort=False,
            )
            .cumcount()
        )

        original_keys[
            "__occurrence"
        ] = (
            original_keys
            .groupby(
                "__index",
                sort=False,
            )
            .cumcount()
        )

        mapping = result_keys.merge(
            original_keys,
            on=[
                "__index",
                "__occurrence",
            ],
            how="left",
            sort=False,
        )

        mapping = mapping.sort_values(
            "__position"
        )

        ordered_positions = (
            mapping[
                "__result_position"
            ].to_numpy()
        )

        result = result.iloc[
            ordered_positions
        ].copy()

        result = result.drop(
            columns=[
                "__restore_position"
            ],
            errors="ignore",
        )

        return result


# ============================================================
# Convenience function
# ============================================================


def add_lag_features(
    dataframe: pd.DataFrame,
    *,
    config: LagFeatureConfig | None = None,
) -> LagFeatureResult:
    """
    Convenience wrapper around LagFeatureGenerator.
    """

    generator = LagFeatureGenerator(
        config=config
    )

    return generator.transform(
        dataframe
    )


# ============================================================
# Birmingham convenience function
# ============================================================


def add_birmingham_lag_features(
    *,
    dataset_root: str = "../datasets/raw",
    config: LagFeatureConfig | None = None,
) -> LagFeatureResult:
    """
    Build the Birmingham ML dataset and add lag features.

    Intended for development and pipeline validation.
    """

    from app.ml.data.dataset_builder import (
        build_birmingham_ml_dataset,
    )

    dataset_result = (
        build_birmingham_ml_dataset(
            dataset_root=dataset_root
        )
    )

    return add_lag_features(
        dataset_result.dataframe,
        config=config,
    )


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

    The function does not modify the dataframe.
    """

    if config is None:

        config = LagFeatureConfig()

    errors: list[str] = []

    required_columns = {
        config.facility_column,
        config.timestamp_column,
        *config.value_columns,
    }

    missing_input_columns = sorted(
        required_columns
        - set(dataframe.columns)
    )

    if missing_input_columns:

        return {
            "valid": False,
            "errors": [
                "Missing required input columns: "
                f"{missing_input_columns}"
            ],
            "missing_columns": (
                missing_input_columns
            ),
        }

    expected_features: list[str] = []

    for value_column in (
        config.value_columns
    ):

        for lag_minutes in (
            config.lag_minutes
        ):

            label = _format_lag_label(
                lag_minutes
            )

            feature_name = (
                f"{value_column}_lag_{label}"
            )

            expected_features.append(
                feature_name
            )

            if config.add_availability_flags:

                expected_features.append(
                    f"{feature_name}_available"
                )

            if config.add_age_features:

                expected_features.append(
                    f"{feature_name}_age_minutes"
                )

    missing_features = [
        column
        for column in expected_features
        if column not in dataframe.columns
    ]

    if missing_features:

        errors.append(
            "Missing generated lag features: "
            f"{missing_features}"
        )

    # --------------------------------------------------------
    # Check for infinite values.
    # --------------------------------------------------------

    numeric_columns = [
        column
        for column in expected_features
        if column in dataframe.columns
        and pd.api.types.is_numeric_dtype(
            dataframe[column]
        )
    ]

    for column in numeric_columns:

        values = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

        if np.isinf(
            values.to_numpy(
                dtype="float64",
                na_value=np.nan,
            )
        ).any():

            errors.append(
                f"{column} contains infinite values."
            )

    # --------------------------------------------------------
    # Check row count.
    # --------------------------------------------------------

    row_count = len(dataframe)

    # --------------------------------------------------------
    # Check that lag features are not target columns.
    # --------------------------------------------------------

    target_like_columns = [
        column
        for column in expected_features
        if column.startswith("target_")
    ]

    if target_like_columns:

        errors.append(
            "Target columns were generated as lag "
            f"features: {target_like_columns}"
        )

    return {
        "valid": not errors,
        "errors": errors,
        "missing_columns": missing_features,
        "row_count": row_count,
        "expected_feature_count": len(
            expected_features
        ),
    }


# ============================================================
# Public API
# ============================================================


__all__ = [
    # Configuration
    "LagFeatureConfig",

    # Statistics/results
    "LagFeatureStatistics",
    "LagFeatureResult",

    # Exceptions
    "LagFeatureError",
    "LagFeatureSchemaError",
    "LagFeatureDataError",
    "LagFeatureConfigurationError",

    # Generator
    "LagFeatureGenerator",

    # Constants
    "DEFAULT_FACILITY_COLUMN",
    "DEFAULT_TIMESTAMP_COLUMN",
    "DEFAULT_VALUE_COLUMNS",
    "DEFAULT_LAG_MINUTES",

    # Convenience functions
    "add_lag_features",
    "add_birmingham_lag_features",

    # Validation
    "validate_lag_features",
]