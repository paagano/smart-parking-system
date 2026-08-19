"""
SmartPark AI - Temporal Feature Engineering.

This module creates time-based features from the canonical ML dataset.

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
    Lag Features
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

1. No future information is used.
2. The original dataframe is never modified.
3. Timestamp handling is explicit and deterministic.
4. Cyclical encoding is used for periodic temporal variables.
5. Feature names are stable and documented.
6. Missing timestamps are handled safely.
7. The transformer is reusable for both historical training data
   and future inference data.
8. The module does not perform model-specific transformations.
9. The module does not perform target generation.
10. The module does not perform train/test splitting.


Temporal features
-----------------

Calendar:

    year
    month
    quarter
    day_of_month
    day_of_year
    week_of_year
    day_of_week

Time:

    hour
    minute
    half_hour_slot
    time_slot

Boolean:

    is_weekday
    is_weekend
    is_monday
    is_tuesday
    is_wednesday
    is_thursday
    is_friday
    is_saturday
    is_sunday

Cyclical:

    hour_sin
    hour_cos
    day_of_week_sin
    day_of_week_cos
    day_of_year_sin
    day_of_year_cos
    month_sin
    month_cos

Operationally useful:

    minutes_since_midnight
    minutes_since_week_start
    week_of_year
    iso_year
"""


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


# ============================================================
# Constants
# ============================================================

DEFAULT_TIMESTAMP_COLUMN = "normalized_at"


# ============================================================
# Feature names
# ============================================================

TEMPORAL_FEATURE_COLUMNS: tuple[str, ...] = (
    # Calendar
    "year",
    "month",
    "quarter",
    "day_of_month",
    "day_of_year",
    "week_of_year",
    "day_of_week",

    # Time
    "hour",
    "minute",
    "half_hour_slot",
    "time_slot",
    "minutes_since_midnight",
    "minutes_since_week_start",

    # Boolean
    "is_weekday",
    "is_weekend",
    "is_monday",
    "is_tuesday",
    "is_wednesday",
    "is_thursday",
    "is_friday",
    "is_saturday",
    "is_sunday",

    # Cyclical
    "hour_sin",
    "hour_cos",
    "day_of_week_sin",
    "day_of_week_cos",
    "day_of_year_sin",
    "day_of_year_cos",
    "month_sin",
    "month_cos",
)


# ============================================================
# Exceptions
# ============================================================


class TemporalFeatureError(Exception):
    """Base exception for temporal feature engineering."""


class TemporalFeatureSchemaError(
    TemporalFeatureError
):
    """Raised when the input dataset does not contain required columns."""


class TemporalFeatureDataError(
    TemporalFeatureError
):
    """Raised when temporal data is invalid."""


class TemporalFeatureConfigurationError(
    TemporalFeatureError
):
    """Raised when temporal feature configuration is invalid."""


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class TemporalFeatureConfig:
    """
    Configuration for temporal feature generation.

    Parameters
    ----------
    timestamp_column:
        Name of the timestamp column in the input dataframe.

    include_calendar_features:
        Include calendar-derived features.

    include_time_features:
        Include time-of-day features.

    include_weekday_flags:
        Include individual weekday boolean features.

    include_cyclical_features:
        Include sine/cosine encodings.

    interval_minutes:
        Expected normalized observation interval.

        SmartPark currently uses a 30-minute interval.

    time_slot_origin:
        First time slot. Normally midnight.

    add_original_timestamp:
        Whether to retain the original timestamp column.

    coerce_timestamp:
        Whether strings should be converted to pandas timestamps.

    sort_by_timestamp:
        Whether the generated dataframe should be sorted
        chronologically.

    preserve_index:
        Whether the original dataframe index should be preserved.
    """

    timestamp_column: str = (
        DEFAULT_TIMESTAMP_COLUMN
    )

    include_calendar_features: bool = True

    include_time_features: bool = True

    include_weekday_flags: bool = True

    include_cyclical_features: bool = True

    interval_minutes: int = 30

    time_slot_origin: int = 0

    add_original_timestamp: bool = True

    coerce_timestamp: bool = True

    sort_by_timestamp: bool = False

    preserve_index: bool = True

    def __post_init__(self) -> None:

        if not self.timestamp_column.strip():

            raise TemporalFeatureConfigurationError(
                "timestamp_column cannot be empty."
            )

        if self.interval_minutes <= 0:

            raise TemporalFeatureConfigurationError(
                "interval_minutes must be greater than zero."
            )

        if (
            1440
            % self.interval_minutes
            != 0
        ):

            raise TemporalFeatureConfigurationError(
                "interval_minutes must divide evenly "
                "into 24 hours."
            )

        if not (
            0
            <= self.time_slot_origin
            < 1440
        ):

            raise TemporalFeatureConfigurationError(
                "time_slot_origin must be between "
                "0 and 1439."
            )


# ============================================================
# Statistics
# ============================================================


@dataclass(frozen=True, slots=True)
class TemporalFeatureStatistics:
    """Statistics describing generated temporal features."""

    source_row_count: int

    output_row_count: int

    source_column_count: int

    output_column_count: int

    timestamp_column: str

    invalid_timestamp_count: int

    unique_dates: int

    unique_hours: int

    unique_weekdays: int

    minimum_timestamp: pd.Timestamp | None

    maximum_timestamp: pd.Timestamp | None

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True, slots=True)
class TemporalFeatureResult:
    """
    Result returned by the temporal feature generator.
    """

    dataframe: pd.DataFrame

    statistics: TemporalFeatureStatistics

    feature_columns: tuple[str, ...]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Temporal Feature Generator
# ============================================================


class TemporalFeatureGenerator:
    """
    Generate deterministic temporal features.

    The generator is intentionally stateless with respect to
    the dataset. This is important for ML reproducibility.

    It does not learn anything from the target or from future
    observations.

    Example
    -------

        generator = TemporalFeatureGenerator()

        result = generator.transform(
            dataframe
        )

        features = result.dataframe
    """

    def __init__(
        self,
        config: TemporalFeatureConfig | None = None,
    ) -> None:

        self._config = (
            config
            if config is not None
            else TemporalFeatureConfig()
        )

    # ========================================================
    # Public API
    # ========================================================

    def transform(
        self,
        dataframe: pd.DataFrame,
    ) -> TemporalFeatureResult:
        """
        Generate temporal features.

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

        timestamp = self._prepare_timestamp(
            result[
                self._config.timestamp_column
            ]
        )

        invalid_timestamp_count = int(
            timestamp.isna().sum()
        )

        if invalid_timestamp_count:

            raise TemporalFeatureDataError(
                f"Input contains "
                f"{invalid_timestamp_count} invalid "
                "timestamps."
            )

        if self._config.sort_by_timestamp:

            result = result.assign(
                _temporal_timestamp=timestamp
            )

            result = result.sort_values(
                "_temporal_timestamp",
                kind="mergesort",
            )

            timestamp = result[
                "_temporal_timestamp"
            ]

            result = result.drop(
                columns=[
                    "_temporal_timestamp"
                ]
            )

        # ----------------------------------------------------
        # Generate feature groups
        # ----------------------------------------------------

        if (
            self._config
            .include_calendar_features
        ):

            result = (
                self._add_calendar_features(
                    result,
                    timestamp,
                )
            )

        if (
            self._config
            .include_time_features
        ):

            result = (
                self._add_time_features(
                    result,
                    timestamp,
                )
            )

        if (
            self._config
            .include_weekday_flags
        ):

            result = (
                self._add_weekday_features(
                    result,
                    timestamp,
                )
            )

        if (
            self._config
            .include_cyclical_features
        ):

            result = (
                self._add_cyclical_features(
                    result,
                    timestamp,
                )
            )

        generated_columns = tuple(
            column
            for column in TEMPORAL_FEATURE_COLUMNS
            if column in result.columns
        )

        minimum_timestamp = (
            timestamp.min()
        )

        maximum_timestamp = (
            timestamp.max()
        )

        unique_dates = int(
            timestamp.dt.normalize()
            .nunique()
        )

        unique_hours = int(
            timestamp.dt.hour.nunique()
        )

        unique_weekdays = int(
            timestamp.dt.dayofweek.nunique()
        )

        statistics = (
            TemporalFeatureStatistics(
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
                timestamp_column=(
                    self._config
                    .timestamp_column
                ),
                invalid_timestamp_count=(
                    invalid_timestamp_count
                ),
                unique_dates=unique_dates,
                unique_hours=unique_hours,
                unique_weekdays=(
                    unique_weekdays
                ),
                minimum_timestamp=(
                    minimum_timestamp
                ),
                maximum_timestamp=(
                    maximum_timestamp
                ),
                metadata={
                    "interval_minutes": (
                        self._config
                        .interval_minutes
                    ),
                    "feature_count": len(
                        generated_columns
                    ),
                    "future_data_used": False,
                    "target_data_used": False,
                    "data_modified": False,
                },
            )
        )

        return TemporalFeatureResult(
            dataframe=result,
            statistics=statistics,
            feature_columns=(
                generated_columns
            ),
            metadata={
                "generator": (
                    "TemporalFeatureGenerator"
                ),
                "future_data_used": False,
                "target_data_used": False,
            },
        )

    # ========================================================
    # Validation
    # ========================================================

    def _validate_input(
        self,
        dataframe: pd.DataFrame,
    ) -> None:

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):

            raise TemporalFeatureDataError(
                "TemporalFeatureGenerator requires "
                "a pandas DataFrame."
            )

        if dataframe.empty:

            raise TemporalFeatureDataError(
                "Cannot generate temporal features "
                "from an empty dataframe."
            )

        timestamp_column = (
            self._config.timestamp_column
        )

        if (
            timestamp_column
            not in dataframe.columns
        ):

            raise TemporalFeatureSchemaError(
                "Required timestamp column "
                f"'{timestamp_column}' "
                "was not found."
            )

    # ========================================================
    # Timestamp preparation
    # ========================================================

    def _prepare_timestamp(
        self,
        series: pd.Series,
    ) -> pd.Series:
        """
        Convert timestamp values into pandas datetime.

        We deliberately avoid silently repairing invalid
        timestamps.
        """

        if pd.api.types.is_datetime64_any_dtype(
            series
        ):

            timestamp = series.copy()

        elif self._config.coerce_timestamp:

            timestamp = pd.to_datetime(
                series,
                errors="coerce",
            )

        else:

            raise TemporalFeatureDataError(
                "Timestamp column is not datetime-like "
                "and timestamp coercion is disabled."
            )

        # ----------------------------------------------------
        # Normalise timezone representation.
        #
        # We do not arbitrarily convert naive timestamps
        # to a timezone. Birmingham historical data is
        # treated as a naive local historical dataset.
        #
        # If timezone-aware data is supplied, we retain
        # the timezone-aware representation.
        # ----------------------------------------------------

        return timestamp

    # ========================================================
    # Calendar features
    # ========================================================

    def _add_calendar_features(
        self,
        dataframe: pd.DataFrame,
        timestamp: pd.Series,
    ) -> pd.DataFrame:

        dataframe["year"] = (
            timestamp.dt.year.astype(
                "int16"
            )
        )

        dataframe["month"] = (
            timestamp.dt.month.astype(
                "int8"
            )
        )

        dataframe["quarter"] = (
            timestamp.dt.quarter.astype(
                "int8"
            )
        )

        dataframe["day_of_month"] = (
            timestamp.dt.day.astype(
                "int8"
            )
        )

        dataframe["day_of_year"] = (
            timestamp.dt.dayofyear.astype(
                "int16"
            )
        )

        dataframe["week_of_year"] = (
            timestamp.dt.isocalendar()
            .week.astype("int16")
        )

        dataframe["day_of_week"] = (
            timestamp.dt.dayofweek.astype(
                "int8"
            )
        )

        return dataframe

    # ========================================================
    # Time features
    # ========================================================

    def _add_time_features(
        self,
        dataframe: pd.DataFrame,
        timestamp: pd.Series,
    ) -> pd.DataFrame:

        hour = timestamp.dt.hour

        minute = timestamp.dt.minute

        dataframe["hour"] = (
            hour.astype("int8")
        )

        dataframe["minute"] = (
            minute.astype("int8")
        )

        # ----------------------------------------------------
        # Half-hour slot.
        #
        # 00:00 -> 0
        # 00:30 -> 1
        # 01:00 -> 2
        # ...
        # 23:30 -> 47
        # ----------------------------------------------------

        dataframe[
            "half_hour_slot"
        ] = (
            (
                hour * 60
                + minute
            )
            // self._config.interval_minutes
        ).astype("int16")

        # ----------------------------------------------------
        # Generic time slot.
        #
        # This allows us to change the interval later.
        # ----------------------------------------------------

        minutes_since_midnight = (
            hour * 60
            + minute
        )

        dataframe[
            "minutes_since_midnight"
        ] = (
            minutes_since_midnight
            .astype("int16")
        )

        dataframe[
            "time_slot"
        ] = (
            (
                minutes_since_midnight
                - self._config
                .time_slot_origin
            )
            // self._config
            .interval_minutes
        ).astype("int16")

        # ----------------------------------------------------
        # Minutes since Monday 00:00.
        #
        # Useful for modelling weekly patterns.
        # ----------------------------------------------------

        dataframe[
            "minutes_since_week_start"
        ] = (
            timestamp.dt.dayofweek * 1440
            + minutes_since_midnight
        ).astype("int32")

        return dataframe

    # ========================================================
    # Weekday features
    # ========================================================

    def _add_weekday_features(
        self,
        dataframe: pd.DataFrame,
        timestamp: pd.Series,
    ) -> pd.DataFrame:

        day_of_week = (
            timestamp.dt.dayofweek
        )

        dataframe[
            "is_weekday"
        ] = (
            day_of_week < 5
        )

        dataframe[
            "is_weekend"
        ] = (
            day_of_week >= 5
        )

        dataframe[
            "is_monday"
        ] = (
            day_of_week == 0
        )

        dataframe[
            "is_tuesday"
        ] = (
            day_of_week == 1
        )

        dataframe[
            "is_wednesday"
        ] = (
            day_of_week == 2
        )

        dataframe[
            "is_thursday"
        ] = (
            day_of_week == 3
        )

        dataframe[
            "is_friday"
        ] = (
            day_of_week == 4
        )

        dataframe[
            "is_saturday"
        ] = (
            day_of_week == 5
        )

        dataframe[
            "is_sunday"
        ] = (
            day_of_week == 6
        )

        return dataframe

    # ========================================================
    # Cyclical features
    # ========================================================

    def _add_cyclical_features(
        self,
        dataframe: pd.DataFrame,
        timestamp: pd.Series,
    ) -> pd.DataFrame:

        # ----------------------------------------------------
        # Hour of day
        #
        # 23:30 should be mathematically close to 00:00.
        # ----------------------------------------------------

        minutes_since_midnight = (
            timestamp.dt.hour * 60
            + timestamp.dt.minute
        )

        seconds_per_day = (
            24 * 60
        )

        hour_angle = (
            2.0
            * np.pi
            * minutes_since_midnight
            / seconds_per_day
        )

        dataframe[
            "hour_sin"
        ] = np.sin(
            hour_angle
        )

        dataframe[
            "hour_cos"
        ] = np.cos(
            hour_angle
        )

        # ----------------------------------------------------
        # Day of week
        #
        # Monday = 0
        # Sunday = 6
        # ----------------------------------------------------

        day_of_week = (
            timestamp.dt.dayofweek
        )

        day_angle = (
            2.0
            * np.pi
            * day_of_week
            / 7.0
        )

        dataframe[
            "day_of_week_sin"
        ] = np.sin(
            day_angle
        )

        dataframe[
            "day_of_week_cos"
        ] = np.cos(
            day_angle
        )

        # ----------------------------------------------------
        # Day of year
        #
        # We use 365/366 dynamically so leap years are
        # represented correctly.
        # ----------------------------------------------------

        day_of_year = (
            timestamp.dt.dayofyear
        )

        days_in_year = np.where(
            timestamp.dt.is_leap_year,
            366.0,
            365.0,
        )

        day_of_year_angle = (
            2.0
            * np.pi
            * (
                day_of_year
                - 1
            )
            / days_in_year
        )

        dataframe[
            "day_of_year_sin"
        ] = np.sin(
            day_of_year_angle
        )

        dataframe[
            "day_of_year_cos"
        ] = np.cos(
            day_of_year_angle
        )

        # ----------------------------------------------------
        # Month
        #
        # January = 1 ... December = 12
        # ----------------------------------------------------

        month = (
            timestamp.dt.month
        )

        month_angle = (
            2.0
            * np.pi
            * (
                month - 1
            )
            / 12.0
        )

        dataframe[
            "month_sin"
        ] = np.sin(
            month_angle
        )

        dataframe[
            "month_cos"
        ] = np.cos(
            month_angle
        )

        return dataframe


# ============================================================
# Convenience function
# ============================================================


def add_temporal_features(
    dataframe: pd.DataFrame,
    *,
    config: TemporalFeatureConfig | None = None,
) -> TemporalFeatureResult:
    """
    Convenience wrapper around TemporalFeatureGenerator.
    """

    generator = TemporalFeatureGenerator(
        config=config
    )

    return generator.transform(
        dataframe
    )


# ============================================================
# Birmingham convenience function
# ============================================================


def add_birmingham_temporal_features(
    *,
    dataset_root: str = "../datasets/raw",
    config: TemporalFeatureConfig | None = None,
):
    """
    Build the Birmingham ML dataset and add temporal features.

    This function is primarily intended for development,
    experimentation and pipeline validation.

    The core feature generator remains independent of the
    Birmingham data source.
    """

    from app.ml.data.dataset_builder import (
        build_birmingham_ml_dataset,
    )

    dataset_result = (
        build_birmingham_ml_dataset(
            dataset_root=dataset_root
        )
    )

    return add_temporal_features(
        dataset_result.dataframe,
        config=config,
    )


# ============================================================
# Feature validation helpers
# ============================================================


def validate_temporal_features(
    dataframe: pd.DataFrame,
    *,
    timestamp_column: str = DEFAULT_TIMESTAMP_COLUMN,
    interval_minutes: int = 30,
) -> dict[str, Any]:
    """
    Validate generated temporal features.

    This performs deterministic sanity checks without changing
    the dataframe.

    Returns
    -------
    dict
        Validation results.
    """

    required_columns = {
        timestamp_column,
        "hour",
        "minute",
        "half_hour_slot",
        "day_of_week",
        "hour_sin",
        "hour_cos",
        "day_of_week_sin",
        "day_of_week_cos",
    }

    missing_columns = sorted(
        required_columns
        - set(dataframe.columns)
    )

    if missing_columns:

        return {
            "valid": False,
            "missing_columns": (
                missing_columns
            ),
            "errors": [
                (
                    "Missing required temporal "
                    f"features: {missing_columns}"
                )
            ],
        }

    errors: list[str] = []

    timestamp = pd.to_datetime(
        dataframe[
            timestamp_column
        ],
        errors="coerce",
    )

    if timestamp.isna().any():

        errors.append(
            "Timestamp column contains "
            "invalid values."
        )

    # --------------------------------------------------------
    # Hour
    # --------------------------------------------------------

    if not dataframe[
        "hour"
    ].between(
        0,
        23,
    ).all():

        errors.append(
            "hour contains values outside "
            "the range 0-23."
        )

    # --------------------------------------------------------
    # Minute
    # --------------------------------------------------------

    if not dataframe[
        "minute"
    ].between(
        0,
        59,
    ).all():

        errors.append(
            "minute contains values outside "
            "the range 0-59."
        )

    # --------------------------------------------------------
    # Day of week
    # --------------------------------------------------------

    if not dataframe[
        "day_of_week"
    ].between(
        0,
        6,
    ).all():

        errors.append(
            "day_of_week contains values outside "
            "the range 0-6."
        )

    # --------------------------------------------------------
    # Cyclical values
    # --------------------------------------------------------

    cyclical_columns = [
        "hour_sin",
        "hour_cos",
        "day_of_week_sin",
        "day_of_week_cos",
    ]

    for column in cyclical_columns:

        values = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

        if values.isna().any():

            errors.append(
                f"{column} contains NaN values."
            )

        if (
            np.abs(values)
            > 1.0000001
        ).any():

            errors.append(
                f"{column} contains values "
                "outside [-1, 1]."
            )

    # --------------------------------------------------------
    # Interval consistency
    # --------------------------------------------------------

    if interval_minutes > 0:

        expected_slots = (
            (
                timestamp.dt.hour * 60
                + timestamp.dt.minute
            )
            // interval_minutes
        )

        actual_slots = pd.to_numeric(
            dataframe[
                "half_hour_slot"
            ],
            errors="coerce",
        )

        if not (
            expected_slots
            .astype("int64")
            .equals(
                actual_slots
                .astype("int64")
            )
        ):

            errors.append(
                "half_hour_slot does not match "
                "the configured interval."
            )

    return {
        "valid": not errors,
        "missing_columns": [],
        "errors": errors,
        "row_count": len(
            dataframe
        ),
    }


# ============================================================
# Public API
# ============================================================


__all__ = [
    # Configuration
    "TemporalFeatureConfig",

    # Statistics/results
    "TemporalFeatureStatistics",
    "TemporalFeatureResult",

    # Exceptions
    "TemporalFeatureError",
    "TemporalFeatureSchemaError",
    "TemporalFeatureDataError",
    "TemporalFeatureConfigurationError",

    # Generator
    "TemporalFeatureGenerator",

    # Constants
    "DEFAULT_TIMESTAMP_COLUMN",
    "TEMPORAL_FEATURE_COLUMNS",

    # Convenience functions
    "add_temporal_features",
    "add_birmingham_temporal_features",

    # Validation
    "validate_temporal_features",
]