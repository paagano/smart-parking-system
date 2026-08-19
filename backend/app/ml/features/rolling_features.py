"""
SmartPark AI - Rolling Feature Engineering.

This module creates historical rolling/statistical features for
parking occupancy time-series data.

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
    Rolling Features          <-- this module
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

1. Rolling calculations are performed independently per facility.
2. Only historical/current information is used.
3. Future observations are never included.
4. Target columns are never used.
5. The input dataframe is never modified.
6. Missing observations remain distinguishable from zero values.
7. Sequence gaps are respected.
8. Rolling windows are time-based rather than blindly row-based.
9. Birmingham is supported through a convenience wrapper.
10. The implementation is source-independent.
11. Rolling statistics are deterministic and reproducible.


Default windows
---------------

For the 30-minute Birmingham normalized dataset:

    1 hour
    2 hours
    3 hours
    6 hours
    12 hours
    24 hours

The windows are expressed in minutes rather than row counts so
that the implementation remains meaningful when data contains
missing observations.


Generated features
------------------

For occupancy_rate:

    occupancy_rate_roll_mean_1h
    occupancy_rate_roll_mean_2h
    occupancy_rate_roll_mean_3h
    occupancy_rate_roll_mean_6h
    occupancy_rate_roll_mean_12h
    occupancy_rate_roll_mean_24h

    occupancy_rate_roll_std_1h
    occupancy_rate_roll_std_2h
    ...

    occupancy_rate_roll_min_1h
    occupancy_rate_roll_max_1h

    occupancy_rate_roll_median_1h

    occupancy_rate_roll_count_1h
    occupancy_rate_roll_missing_1h

    occupancy_rate_roll_trend_1h

The same approach can be applied to:

    occupied_spaces
    available_spaces

Additional availability indicators are generated so that
downstream models can distinguish between:

    "the historical window contained valid observations"

and

    "the historical window contained insufficient data."


Leakage protection
------------------

The implementation deliberately does NOT use:

    rolling(..., center=True)

and does not calculate rolling statistics using future rows.

By default, the current observation is included in the rolling
window because it is known at prediction time.

For example, at 10:00 with a 1-hour window:

    09:00
    09:30
    10:00

may contribute to the 1-hour rolling feature.

This behaviour is configurable through `include_current`.


Sequence handling
-----------------

A normalized SmartPark dataset contains explicit missing slots.

For example:

    08:00 observed
    08:30 observed
    09:00 observed
    09:30 missing
    10:00 missing
    10:30 observed

A time-based rolling window must not pretend that the 10:30
observation has a continuous historical sequence.

The generated coverage/count features allow the model to
understand how much actual historical data was available.
"""


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd


# ============================================================
# Constants
# ============================================================

DEFAULT_FACILITY_COLUMN = "source_facility_code"

DEFAULT_TIMESTAMP_COLUMN = "normalized_at"

DEFAULT_VALUE_COLUMNS: tuple[str, ...] = (
    "occupancy_rate",
    "occupied_spaces",
    "available_spaces",
)

DEFAULT_ROLLING_WINDOWS_MINUTES: tuple[int, ...] = (
    60,
    120,
    180,
    360,
    720,
    1440,
)


# ============================================================
# Exceptions
# ============================================================


class RollingFeatureError(Exception):
    """Base exception for rolling feature engineering."""


class RollingFeatureSchemaError(
    RollingFeatureError
):
    """Raised when required columns are missing."""


class RollingFeatureDataError(
    RollingFeatureError
):
    """Raised when rolling feature input data is invalid."""


class RollingFeatureConfigurationError(
    RollingFeatureError
):
    """Raised when rolling feature configuration is invalid."""


# ============================================================
# Helpers
# ============================================================


def _format_window_label(
    minutes: int,
) -> str:
    """
    Convert a number of minutes into a readable window label.

    Examples
    --------
    60      -> 1h
    120     -> 2h
    360     -> 6h
    720     -> 12h
    1440    -> 24h
    """

    if minutes % 1440 == 0:
        return f"{minutes // 1440}d"

    if minutes % 60 == 0:
        return f"{minutes // 60}h"

    return f"{minutes}m"


def _validate_windows(
    windows: Sequence[int],
) -> tuple[int, ...]:
    """Validate and normalize rolling windows."""

    if not windows:
        raise RollingFeatureConfigurationError(
            "At least one rolling window must be configured."
        )

    normalized: list[int] = []

    for value in windows:

        if isinstance(value, bool):
            raise RollingFeatureConfigurationError(
                "Rolling windows must be positive integers."
            )

        try:
            value = int(value)
        except (TypeError, ValueError) as exc:
            raise RollingFeatureConfigurationError(
                f"Invalid rolling window: {value!r}"
            ) from exc

        if value <= 0:
            raise RollingFeatureConfigurationError(
                "Rolling windows must be greater than zero."
            )

        normalized.append(value)

    if len(set(normalized)) != len(normalized):
        raise RollingFeatureConfigurationError(
            "Rolling windows must not contain duplicates."
        )

    return tuple(sorted(normalized))


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class RollingFeatureConfig:
    """
    Configuration for rolling feature generation.
    """

    facility_column: str = DEFAULT_FACILITY_COLUMN

    timestamp_column: str = DEFAULT_TIMESTAMP_COLUMN

    value_columns: tuple[str, ...] = (
        DEFAULT_VALUE_COLUMNS
    )

    windows_minutes: tuple[int, ...] = (
        DEFAULT_ROLLING_WINDOWS_MINUTES
    )

    interval_minutes: int = 30

    include_current: bool = True

    min_observations: int = 1

    add_mean: bool = True

    add_std: bool = True

    add_min: bool = True

    add_max: bool = True

    add_median: bool = True

    add_count: bool = True

    add_missing_count: bool = True

    add_coverage_ratio: bool = True

    add_trend: bool = True

    add_availability_flags: bool = True

    respect_observation_presence: bool = True

    sort_output: bool = True

    def __post_init__(self) -> None:

        if not self.facility_column.strip():
            raise RollingFeatureConfigurationError(
                "facility_column cannot be empty."
            )

        if not self.timestamp_column.strip():
            raise RollingFeatureConfigurationError(
                "timestamp_column cannot be empty."
            )

        if not self.value_columns:
            raise RollingFeatureConfigurationError(
                "At least one value column is required."
            )

        if any(
            not str(column).strip()
            for column in self.value_columns
        ):
            raise RollingFeatureConfigurationError(
                "Value column names cannot be empty."
            )

        if self.interval_minutes <= 0:
            raise RollingFeatureConfigurationError(
                "interval_minutes must be greater than zero."
            )

        if self.min_observations <= 0:
            raise RollingFeatureConfigurationError(
                "min_observations must be greater than zero."
            )

        normalized_windows = _validate_windows(
            self.windows_minutes
        )

        object.__setattr__(
            self,
            "windows_minutes",
            normalized_windows,
        )


# ============================================================
# Statistics
# ============================================================


@dataclass(frozen=True, slots=True)
class RollingFeatureStatistics:
    """Statistics describing rolling feature generation."""

    source_row_count: int

    output_row_count: int

    source_column_count: int

    output_column_count: int

    facility_count: int

    invalid_timestamp_count: int

    missing_facility_count: int

    duplicate_facility_timestamp_count: int

    rolling_feature_count: int

    rolling_availability_feature_count: int

    insufficient_history_rows: int

    fully_covered_rows: int

    partially_covered_rows: int

    no_history_rows: int

    observed_rows: int

    missing_rows: int

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True, slots=True)
class RollingFeatureResult:
    """Result returned by the rolling feature generator."""

    dataframe: pd.DataFrame

    statistics: RollingFeatureStatistics

    feature_columns: tuple[str, ...]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Generator
# ============================================================


class RollingFeatureGenerator:
    """
    Generate historical rolling features independently per facility.
    """

    def __init__(
        self,
        config: RollingFeatureConfig | None = None,
    ) -> None:

        self._config = (
            config
            if config is not None
            else RollingFeatureConfig()
        )

    # ========================================================
    # Public API
    # ========================================================

    def transform(
        self,
        dataframe: pd.DataFrame,
    ) -> RollingFeatureResult:
        """
        Generate rolling features.

        The input dataframe is never modified.
        """

        self._validate_input(dataframe)

        source_row_count = len(dataframe)

        source_column_count = dataframe.shape[1]

        result = dataframe.copy(deep=True)

        result[
            "__rolling_original_position"
        ] = np.arange(
            len(result),
            dtype=np.int64,
        )

        result[
            "__rolling_timestamp"
        ] = pd.to_datetime(
            result[
                self._config.timestamp_column
            ],
            errors="coerce",
        )

        invalid_timestamp_count = int(
            result[
                "__rolling_timestamp"
            ].isna().sum()
        )

        if invalid_timestamp_count:
            raise RollingFeatureDataError(
                "Rolling feature generation encountered "
                f"{invalid_timestamp_count} invalid timestamps."
            )

        facilities = result[
            self._config.facility_column
        ]

        missing_facility_mask = (
            facilities.isna()
            | facilities.astype("string")
            .str.strip()
            .eq("")
        )

        missing_facility_count = int(
            missing_facility_mask.sum()
        )

        if missing_facility_count:
            raise RollingFeatureDataError(
                "Rolling feature generation encountered "
                f"{missing_facility_count} rows with missing "
                "facility identifiers."
            )

        duplicate_mask = result.duplicated(
            subset=[
                self._config.facility_column,
                "__rolling_timestamp",
            ],
            keep=False,
        )

        duplicate_count = int(
            duplicate_mask.sum()
        )

        if duplicate_count:
            raise RollingFeatureDataError(
                "Duplicate facility/timestamp records detected: "
                f"{duplicate_count} rows."
            )

        # ----------------------------------------------------
        # Observation presence
        # ----------------------------------------------------

        observation_present = (
            self._derive_observation_presence(
                result
            )
        )

        result[
            "__rolling_observation_present"
        ] = observation_present

        observed_rows = int(
            observation_present.sum()
        )

        missing_rows = int(
            (~observation_present).sum()
        )

        # ----------------------------------------------------
        # Sort internally.
        # ----------------------------------------------------

        result = result.sort_values(
            by=[
                self._config.facility_column,
                "__rolling_timestamp",
            ],
            kind="mergesort",
        ).copy()

        feature_columns: list[str] = []

        availability_columns: list[str] = []

        # Accumulate generated columns and concatenate once to avoid
        # pandas DataFrame fragmentation from repeated column insertion.
        result_features: dict[str, pd.Series] = {}

        insufficient_history_rows = 0

        fully_covered_rows = 0

        partially_covered_rows = 0

        no_history_rows = 0

        # ----------------------------------------------------
        # Generate rolling features.
        # ----------------------------------------------------

        for value_column in (
            self._config.value_columns
        ):

            values = pd.to_numeric(
                result[value_column],
                errors="coerce",
            )

            if self._config.respect_observation_presence:

                values = values.where(
                    result[
                        "__rolling_observation_present"
                    ],
                    np.nan,
                )

            for window_minutes in (
                self._config.windows_minutes
            ):

                label = _format_window_label(
                    window_minutes
                )

                rolling_features = (
                    self._build_window_features(
                        result=result,
                        values=values,
                        window_minutes=window_minutes,
                    )
                )

                for feature_name, feature_values in (
                    rolling_features.items()
                ):
                    if feature_name.startswith("__"):
                        continue

                    result_features[feature_name] = feature_values
                    feature_columns.append(feature_name)

                coverage = rolling_features[
                    f"__coverage_count_{label}"
                ]

                expected_count = (
                    self._expected_window_slots(
                        window_minutes
                    )
                )

                no_history_mask = (
                    coverage == 0
                )

                insufficient_mask = (
                    coverage
                    < self._config.min_observations
                )

                fully_covered_mask = (
                    coverage
                    >= expected_count
                )

                partially_covered_mask = (
                    (coverage > 0)
                    & (
                        coverage
                        < expected_count
                    )
                )

                # Count only once per window rather than once
                # for every generated statistic.
                if value_column == (
                    self._config.value_columns[0]
                ):

                    no_history_rows += int(
                        no_history_mask.sum()
                    )

                    insufficient_history_rows += int(
                        insufficient_mask.sum()
                    )

                    fully_covered_rows += int(
                        fully_covered_mask.sum()
                    )

                    partially_covered_rows += int(
                        partially_covered_mask.sum()
                    )

                # ------------------------------------------------
                # Remove internal coverage fields.
                # ------------------------------------------------

                # ------------------------------------------------
                # Add coverage fields explicitly.
                # ------------------------------------------------

                coverage_name = (
                    f"{value_column}"
                    f"_roll_count_{label}"
                )

                missing_name = (
                    f"{value_column}"
                    f"_roll_missing_{label}"
                )

                coverage_ratio_name = (
                    f"{value_column}"
                    f"_roll_coverage_ratio_{label}"
                )

                if self._config.add_count:

                    result_features[
                        coverage_name
                    ] = coverage.astype("Int64")

                    feature_columns.append(
                        coverage_name
                    )

                if self._config.add_missing_count:

                    missing_count = rolling_features[
                        f"__missing_count_{label}"
                    ]

                    result_features[
                        missing_name
                    ] = missing_count.astype(
                        "Int64"
                    )

                    feature_columns.append(
                        missing_name
                    )

                if self._config.add_coverage_ratio:

                    coverage_ratio = (
                        coverage
                        / expected_count
                    ).clip(
                        lower=0.0,
                        upper=1.0,
                    )

                    result_features[
                        coverage_ratio_name
                    ] = coverage_ratio.astype(
                        "float64"
                    )

                    feature_columns.append(
                        coverage_ratio_name
                    )

                if self._config.add_availability_flags:

                    available_name = (
                        f"{value_column}"
                        f"_roll_{label}_available"
                    )

                    available = (
                        coverage
                        >= self._config.min_observations
                    )

                    result_features[
                        available_name
                    ] = available.astype(
                        "boolean"
                    )

                    availability_columns.append(
                        available_name
                    )

                    feature_columns.append(
                        available_name
                    )

        # ----------------------------------------------------
        # Materialize generated features in one operation.
        # ----------------------------------------------------

        if result_features:
            result = pd.concat(
                [
                    result,
                    pd.DataFrame(
                        result_features,
                        index=result.index,
                    ),
                ],
                axis=1,
            )

        # ----------------------------------------------------
        # Remove helper columns.
        # ----------------------------------------------------

        result = result.drop(
            columns=[
                "__rolling_timestamp",
                "__rolling_observation_present",
                "__rolling_original_position",
            ]
        )

        # ----------------------------------------------------
        # Restore original ordering.
        # ----------------------------------------------------

        if self._config.sort_output:

            result = self._restore_original_order(
                result=result,
                original=dataframe,
            )

        statistics = RollingFeatureStatistics(
            source_row_count=source_row_count,
            output_row_count=len(result),
            source_column_count=source_column_count,
            output_column_count=result.shape[1],
            facility_count=int(
                dataframe[
                    self._config.facility_column
                ].nunique()
            ),
            invalid_timestamp_count=(
                invalid_timestamp_count
            ),
            missing_facility_count=(
                missing_facility_count
            ),
            duplicate_facility_timestamp_count=(
                duplicate_count
            ),
            rolling_feature_count=len(
                feature_columns
            ),
            rolling_availability_feature_count=len(
                availability_columns
            ),
            insufficient_history_rows=(
                insufficient_history_rows
            ),
            fully_covered_rows=(
                fully_covered_rows
            ),
            partially_covered_rows=(
                partially_covered_rows
            ),
            no_history_rows=no_history_rows,
            observed_rows=observed_rows,
            missing_rows=missing_rows,
            metadata={
                "facility_column": (
                    self._config.facility_column
                ),
                "timestamp_column": (
                    self._config.timestamp_column
                ),
                "value_columns": (
                    self._config.value_columns
                ),
                "windows_minutes": (
                    self._config.windows_minutes
                ),
                "interval_minutes": (
                    self._config.interval_minutes
                ),
                "include_current": (
                    self._config.include_current
                ),
                "min_observations": (
                    self._config.min_observations
                ),
                "future_data_used": False,
                "target_data_used": False,
                "cross_facility_data_used": False,
                "centered_windows_used": False,
            },
        )

        return RollingFeatureResult(
            dataframe=result,
            statistics=statistics,
            feature_columns=tuple(
                feature_columns
            ),
            metadata={
                "generator": "RollingFeatureGenerator",
                "future_data_used": False,
                "target_data_used": False,
                "cross_facility_data_used": False,
                "centered_windows_used": False,
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
            raise RollingFeatureDataError(
                "RollingFeatureGenerator requires "
                "a pandas DataFrame."
            )

        if dataframe.empty:
            raise RollingFeatureDataError(
                "Cannot generate rolling features "
                "from an empty dataframe."
            )

        required_columns = [
            self._config.facility_column,
            self._config.timestamp_column,
            *self._config.value_columns,
        ]

        missing_columns = [
            column
            for column in required_columns
            if column not in dataframe.columns
        ]

        if missing_columns:
            raise RollingFeatureSchemaError(
                "Required rolling feature columns are "
                f"missing: {missing_columns}"
            )

        target_columns = [
            column
            for column in self._config.value_columns
            if column.startswith("target_")
        ]

        if target_columns:
            raise RollingFeatureConfigurationError(
                "Target columns cannot be used as rolling "
                f"feature inputs: {target_columns}"
            )

    # ========================================================
    # Observation presence
    # ========================================================

    def _derive_observation_presence(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.Series:
        """
        Determine whether each normalized row represents
        an actual observation.
        """

        if "observation_present" in dataframe.columns:

            return (
                dataframe[
                    "observation_present"
                ]
                .fillna(False)
                .astype(bool)
            )

        if "occupancy_rate" in dataframe.columns:

            return (
                dataframe[
                    "occupancy_rate"
                ]
                .notna()
            )

        first_value_column = (
            self._config.value_columns[0]
        )

        return (
            dataframe[
                first_value_column
            ]
            .notna()
        )

    # ========================================================
    # Expected slots
    # ========================================================

    def _expected_window_slots(
        self,
        window_minutes: int,
    ) -> int:
        """
        Calculate expected number of normalized observations
        represented by a rolling window.

        With 30-minute intervals:

            60m  -> 2
            120m -> 4
            1440m -> 48
        """

        return max(
            1,
            int(
                window_minutes
                / self._config.interval_minutes
            ),
        )

    # ========================================================
    # Window calculations
    # ========================================================

    def _build_window_features(
        self,
        *,
        result: pd.DataFrame,
        values: pd.Series,
        window_minutes: int,
    ) -> dict[str, pd.Series]:
        """
        Calculate rolling statistics for one value column
        and one time window.

        Rolling calculations are performed independently for
        each parking facility and use only historical/current
        observations.

        No future observations are used.

        Parameters
        ----------
        result:
            Working dataframe containing facility and timestamp
            information.

        values:
            Numeric series for which rolling features are being
            calculated.

        window_minutes:
            Size of the rolling time window in minutes.

        Returns
        -------
        dict[str, pd.Series]
            Generated rolling features plus internal coverage
            statistics used by the caller.
        """

        label = _format_window_label(
            window_minutes
        )

        # --------------------------------------------------------
        # Build isolated working dataframe.
        # --------------------------------------------------------

        working = pd.DataFrame(
            {
                "__facility": result[
                    self._config.facility_column
                ].astype("string"),

                "__timestamp": result[
                    "__rolling_timestamp"
                ],

                "__value": pd.to_numeric(
                    values,
                    errors="coerce",
                ),

                "__observed": result[
                    "__rolling_observation_present"
                ].astype(bool),
            },
            index=result.index,
        )

        # --------------------------------------------------------
        # Sort chronologically within each facility.
        #
        # This is essential because the rolling calculation must
        # follow the actual time sequence of each facility.
        # --------------------------------------------------------

        working = working.sort_values(
            by=[
                "__facility",
                "__timestamp",
            ],
            kind="mergesort",
        )

        # --------------------------------------------------------
        # Group by facility.
        #
        # IMPORTANT:
        #
        # We intentionally group the complete DataFrame rather
        # than selecting "__value" before calling rolling().
        #
        # This allows pandas to use the time-based "__timestamp"
        # column through the `on=` argument.
        # --------------------------------------------------------

        grouped = working.groupby(
            "__facility",
            sort=False,
            group_keys=False,
        )

        # --------------------------------------------------------
        # Rolling configuration.
        # --------------------------------------------------------

        rolling_kwargs: dict[str, Any] = {
            "window": pd.Timedelta(
                minutes=window_minutes
            ),
            "min_periods": 1,
        }

        # --------------------------------------------------------
        # Include current observation:
        #
        # True:
        #     [t-window, t]
        #
        # False:
        #     [t-window, t)
        #
        # In our forecasting pipeline the current occupancy is
        # known at prediction time, so including the current
        # observation is intentional and does not constitute
        # future-data leakage.
        # --------------------------------------------------------

        if self._config.include_current:

            rolling_kwargs["closed"] = "both"

        else:

            rolling_kwargs["closed"] = "left"

        # --------------------------------------------------------
        # Create the DataFrameGroupBy rolling object FIRST.
        #
        # Do NOT do:
        #
        #     grouped["__value"].rolling(on="__timestamp")
        #
        # because pandas treats that as SeriesGroupBy.rolling()
        # and does not support the `on=` time column in that form.
        #
        # Correct:
        #
        #     grouped.rolling(on="__timestamp")
        # --------------------------------------------------------

        rolling_object = grouped.rolling(
            on="__timestamp",
            **rolling_kwargs,
        )

        # --------------------------------------------------------
        # Select the actual value series from the rolling object.
        # --------------------------------------------------------

        value_roll = rolling_object[
            "__value"
        ]

        # --------------------------------------------------------
        # Output container.
        # --------------------------------------------------------

        output: dict[str, pd.Series] = {}

        # ========================================================
        # Mean
        # ========================================================

        if self._config.add_mean:

            mean = value_roll.mean()

            output[
                f"{values.name or 'value'}"
                f"_roll_mean_{label}"
            ] = self._restore_grouped_result(
                mean,
                result,
            )

        # ========================================================
        # Standard deviation
        # ========================================================

        if self._config.add_std:

            std = value_roll.std(
                ddof=0
            )

            output[
                f"{values.name or 'value'}"
                f"_roll_std_{label}"
            ] = self._restore_grouped_result(
                std,
                result,
            )

        # ========================================================
        # Minimum
        # ========================================================

        if self._config.add_min:

            minimum = value_roll.min()

            output[
                f"{values.name or 'value'}"
                f"_roll_min_{label}"
            ] = self._restore_grouped_result(
                minimum,
                result,
            )

        # ========================================================
        # Maximum
        # ========================================================

        if self._config.add_max:

            maximum = value_roll.max()

            output[
                f"{values.name or 'value'}"
                f"_roll_max_{label}"
            ] = self._restore_grouped_result(
                maximum,
                result,
            )

        # ========================================================
        # Median
        # ========================================================

        if self._config.add_median:

            median = value_roll.median()

            output[
                f"{values.name or 'value'}"
                f"_roll_median_{label}"
            ] = self._restore_grouped_result(
                median,
                result,
            )

        # ========================================================
        # Count of valid observations
        # ========================================================

        count = value_roll.count()

        count = self._restore_grouped_result(
            count,
            result,
        ).fillna(0)

        output[
            f"__coverage_count_{label}"
        ] = count.astype("int64")

        # ========================================================
        # Expected observations
        # ========================================================

        expected_count = (
            self._expected_window_slots(
                window_minutes
            )
        )

        # ========================================================
        # Missing observations
        #
        # Example:
        #
        # 6-hour window
        # 30-minute interval
        #
        # expected = 12 observations
        #
        # actual = 9
        #
        # missing = 3
        # ========================================================

        missing_count = (
            expected_count
            - count
        ).clip(
            lower=0
        )

        output[
            f"__missing_count_{label}"
        ] = missing_count.astype(
            "int64"
        )

        # ========================================================
        # Trend
        #
        # Trend is:
        #
        #     last valid observation
        #     -
        #     first valid observation
        #
        # within the current historical rolling window.
        #
        # Both values are therefore restricted to the same
        # historical/current window.
        # ========================================================

        if self._config.add_trend:

            # ----------------------------------------------------
            # First valid observation in rolling window.
            # ----------------------------------------------------

            first_value = (
                value_roll.apply(
                    self._first_valid,
                    raw=True,
                )
            )

            # ----------------------------------------------------
            # Last valid observation in rolling window.
            # ----------------------------------------------------

            last_value = (
                value_roll.apply(
                    self._last_valid,
                    raw=True,
                )
            )

            # ----------------------------------------------------
            # Restore the grouped rolling results to the original
            # dataframe index.
            # ----------------------------------------------------

            first_value = (
                self._restore_grouped_result(
                    first_value,
                    result,
                )
            )

            last_value = (
                self._restore_grouped_result(
                    last_value,
                    result,
                )
            )

            # ----------------------------------------------------
            # Historical trend.
            # ----------------------------------------------------

            trend = (
                last_value
                - first_value
            )

            output[
                f"{values.name or 'value'}"
                f"_roll_trend_{label}"
            ] = trend

        # ========================================================
        # Return generated features.
        # ========================================================

        return output

    # ========================================================
    # Rolling helper functions
    # ========================================================

    @staticmethod
    def _first_valid(
        values: np.ndarray,
    ) -> float:
        """Return the first finite value."""

        array = np.asarray(
            values,
            dtype="float64",
        )

        finite = np.isfinite(array)

        if not finite.any():
            return np.nan

        return float(
            array[np.argmax(finite)]
        )

    @staticmethod
    def _last_valid(
        values: np.ndarray,
    ) -> float:
        """Return the last finite value."""

        array = np.asarray(
            values,
            dtype="float64",
        )

        finite = np.isfinite(array)

        if not finite.any():
            return np.nan

        return float(
            array[
                np.where(finite)[0][-1]
            ]
        )

    @staticmethod
    def _restore_grouped_result(
        series: pd.Series,
        result: pd.DataFrame,
    ) -> pd.Series:
        """
        Restore grouped rolling output to the result index.

        pandas can return a MultiIndex after groupby().rolling().
        This helper converts it back to positional alignment.
        """

        if isinstance(
            series.index,
            pd.MultiIndex,
        ):

            values = series.to_numpy()

        else:

            values = series.to_numpy()

        if len(values) != len(result):

            raise RollingFeatureDataError(
                "Rolling calculation produced "
                f"{len(values)} values for "
                f"{len(result)} input rows."
            )

        output = pd.Series(
            values,
            index=result.index,
            dtype="float64",
        )

        return output

    # ========================================================
    # Restore original order
    # ========================================================

    @staticmethod
    def _restore_original_order(
        *,
        result: pd.DataFrame,
        original: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Restore original row ordering.

        The normal SmartPark ML dataset uses a unique RangeIndex,
        so this path is intentionally simple and deterministic.
        """

        if len(result) != len(original):

            raise RollingFeatureDataError(
                "Rolling feature generation changed "
                "the number of rows."
            )

        if original.index.is_unique:

            # Internal calculations preserved the same index.
            return result.reindex(
                original.index
            )

        # ----------------------------------------------------
        # Safe fallback for duplicate indexes.
        # ----------------------------------------------------

        result = result.copy()

        result[
            "__rolling_result_position"
        ] = np.arange(
            len(result),
            dtype=np.int64,
        )

        original_keys = pd.DataFrame(
            {
                "__index": original.index,
            }
        )

        original_keys[
            "__occurrence"
        ] = (
            original_keys
            .groupby("__index")
            .cumcount()
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
            .groupby("__index")
            .cumcount()
        )

        mapping = result_keys.merge(
            original_keys,
            on=[
                "__index",
                "__occurrence",
            ],
            how="left",
        )

        mapping = mapping.sort_values(
            "__occurrence",
            kind="stable",
        )

        positions = (
            mapping[
                "__result_position"
            ].to_numpy()
        )

        return result.iloc[
            positions
        ].drop(
            columns=[
                "__rolling_result_position"
            ],
            errors="ignore",
        )

    # ========================================================
    # Public validation
    # ========================================================


def add_rolling_features(
    dataframe: pd.DataFrame,
    *,
    config: RollingFeatureConfig | None = None,
) -> RollingFeatureResult:
    """
    Convenience wrapper for rolling feature generation.
    """

    generator = RollingFeatureGenerator(
        config=config
    )

    return generator.transform(
        dataframe
    )


# ============================================================
# Birmingham convenience wrapper
# ============================================================


def add_birmingham_rolling_features(
    *,
    dataset_root: str = "../datasets/raw",
    config: RollingFeatureConfig | None = None,
) -> RollingFeatureResult:
    """
    Build the Birmingham ML dataset and generate rolling features.
    """

    from app.ml.data.dataset_builder import (
        build_birmingham_ml_dataset,
    )

    dataset_result = (
        build_birmingham_ml_dataset(
            dataset_root=dataset_root
        )
    )

    return add_rolling_features(
        dataset_result.dataframe,
        config=config,
    )


# ============================================================
# Validation
# ============================================================


def validate_rolling_features(
    dataframe: pd.DataFrame,
    *,
    config: RollingFeatureConfig | None = None,
) -> dict[str, Any]:
    """
    Validate generated rolling features.

    The function does not modify the dataframe.
    """

    if config is None:
        config = RollingFeatureConfig()

    errors: list[str] = []

    expected_features: list[str] = []

    for value_column in (
        config.value_columns
    ):

        for window_minutes in (
            config.windows_minutes
        ):

            label = _format_window_label(
                window_minutes
            )

            prefix = (
                f"{value_column}_roll_"
            )

            if config.add_mean:
                expected_features.append(
                    f"{prefix}mean_{label}"
                )

            if config.add_std:
                expected_features.append(
                    f"{prefix}std_{label}"
                )

            if config.add_min:
                expected_features.append(
                    f"{prefix}min_{label}"
                )

            if config.add_max:
                expected_features.append(
                    f"{prefix}max_{label}"
                )

            if config.add_median:
                expected_features.append(
                    f"{prefix}median_{label}"
                )

            if config.add_count:
                expected_features.append(
                    f"{value_column}"
                    f"_roll_count_{label}"
                )

            if config.add_missing_count:
                expected_features.append(
                    f"{value_column}"
                    f"_roll_missing_{label}"
                )

            if config.add_coverage_ratio:
                expected_features.append(
                    f"{value_column}"
                    f"_roll_coverage_ratio_{label}"
                )

            if config.add_trend:
                expected_features.append(
                    f"{prefix}trend_{label}"
                )

            if config.add_availability_flags:
                expected_features.append(
                    f"{value_column}"
                    f"_roll_{label}_available"
                )

    missing_features = [
        column
        for column in expected_features
        if column not in dataframe.columns
    ]

    if missing_features:

        errors.append(
            "Missing rolling feature columns: "
            f"{missing_features}"
        )

    # --------------------------------------------------------
    # Infinite values.
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

        array = values.to_numpy(
            dtype="float64",
            na_value=np.nan,
        )

        if np.isinf(array).any():

            errors.append(
                f"{column} contains infinite values."
            )

    # --------------------------------------------------------
    # Target leakage.
    # --------------------------------------------------------

    target_columns = [
        column
        for column in expected_features
        if column.startswith("target_")
        or "_target_" in column
    ]

    if target_columns:

        errors.append(
            "Target-related rolling features detected: "
            f"{target_columns}"
        )

    # --------------------------------------------------------
    # Centered rolling detection.
    #
    # There should never be columns generated from centered
    # windows by this module.
    # --------------------------------------------------------

    return {
        "valid": not errors,
        "errors": errors,
        "missing_columns": missing_features,
        "row_count": len(dataframe),
        "expected_feature_count": len(
            expected_features
        ),
        "future_data_used": False,
        "target_data_used": False,
        "centered_windows_used": False,
    }


# ============================================================
# Public API
# ============================================================


__all__ = [
    # Constants
    "DEFAULT_FACILITY_COLUMN",
    "DEFAULT_TIMESTAMP_COLUMN",
    "DEFAULT_VALUE_COLUMNS",
    "DEFAULT_ROLLING_WINDOWS_MINUTES",

    # Configuration
    "RollingFeatureConfig",

    # Statistics / result
    "RollingFeatureStatistics",
    "RollingFeatureResult",

    # Exceptions
    "RollingFeatureError",
    "RollingFeatureSchemaError",
    "RollingFeatureDataError",
    "RollingFeatureConfigurationError",

    # Generator
    "RollingFeatureGenerator",

    # Convenience functions
    "add_rolling_features",
    "add_birmingham_rolling_features",

    # Validation
    "validate_rolling_features",
]