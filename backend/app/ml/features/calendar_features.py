"""
SmartPark AI - Calendar Features
================================

Calendar-based feature engineering for parking demand forecasting.

This module derives calendar context exclusively from the observation
timestamp. It deliberately does NOT use:

    - occupancy observations
    - target columns
    - future timestamps
    - future observations
    - facility-level historical values

The purpose is to provide models such as XGBoost and LSTM with
calendar context that is known at prediction time.

Examples of generated information include:

    year
    month
    quarter
    week_of_year
    day_of_month
    day_of_year
    day_of_week
    hour
    minute
    weekday/weekend
    month boundaries
    quarter boundaries
    cyclic calendar encodings

Design principles
-----------------
1. Timestamp-only feature generation.
2. No future-data leakage.
3. No target-data leakage.
4. No occupancy-data dependency.
5. No row removal.
6. Original row order preserved.
7. Original index preserved.
8. Deterministic output.
9. Explicit metadata describing leakage controls.
10. Pandas nullable dtypes where appropriate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# ============================================================
# Constants
# ============================================================

DEFAULT_TIMESTAMP_COLUMN = "normalized_at"

DEFAULT_FEATURE_PREFIX = ""

_INTERNAL_TIMESTAMP_COLUMN = (
    "__calendar_timestamp"
)


# ============================================================
# Exceptions
# ============================================================


class CalendarFeatureError(ValueError):
    """Base exception for calendar feature processing."""


class CalendarFeatureConfigurationError(
    CalendarFeatureError
):
    """Raised when calendar configuration is invalid."""


class CalendarFeatureDataError(
    CalendarFeatureError
):
    """Raised when input data is unsuitable."""


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True)
class CalendarFeatureConfig:
    """
    Configuration for calendar feature generation.
    """

    timestamp_column: str = (
        DEFAULT_TIMESTAMP_COLUMN
    )

    feature_prefix: str = (
        DEFAULT_FEATURE_PREFIX
    )

    add_year: bool = True

    add_month: bool = True

    add_quarter: bool = True

    add_week_of_year: bool = True

    add_day_of_month: bool = True

    add_day_of_year: bool = True

    add_day_of_week: bool = True

    add_week_of_month: bool = True

    add_week_of_quarter: bool = True

    add_weekday_weekend: bool = True

    add_month_boundaries: bool = True

    add_quarter_boundaries: bool = True

    add_year_boundaries: bool = True

    add_cyclic_features: bool = True

    strict_timestamp_validation: bool = True

    preserve_original_order: bool = True

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:

        if not self.timestamp_column:
            raise CalendarFeatureConfigurationError(
                "timestamp_column cannot be empty."
            )

        if self.feature_prefix is None:
            raise CalendarFeatureConfigurationError(
                "feature_prefix cannot be None."
            )


# ============================================================
# Statistics
# ============================================================


@dataclass(frozen=True)
class CalendarFeatureStatistics:
    """
    Statistics generated during calendar feature creation.
    """

    source_row_count: int

    output_row_count: int

    source_column_count: int

    output_column_count: int

    feature_count: int

    invalid_timestamp_count: int

    unique_dates: int

    unique_months: int

    unique_quarters: int

    unique_weekdays: int

    weekday_row_count: int

    weekend_row_count: int

    minimum_timestamp: pd.Timestamp | None

    maximum_timestamp: pd.Timestamp | None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True)
class CalendarFeatureResult:
    """
    Result returned by the calendar feature generator.
    """

    dataframe: pd.DataFrame

    feature_columns: tuple[str, ...]

    statistics: CalendarFeatureStatistics

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Utility functions
# ============================================================


def _prefixed_name(
    prefix: str,
    name: str,
) -> str:
    """
    Apply an optional feature prefix.
    """

    if not prefix:
        return name

    return f"{prefix}{name}"


def _safe_sin(
    value: pd.Series,
    period: float,
) -> pd.Series:
    """
    Cyclic sine encoding.
    """

    return pd.Series(
        np.sin(
            2.0
            * np.pi
            * value.astype(float)
            / period
        ),
        index=value.index,
        dtype="float64",
    )


def _safe_cos(
    value: pd.Series,
    period: float,
) -> pd.Series:
    """
    Cyclic cosine encoding.
    """

    return pd.Series(
        np.cos(
            2.0
            * np.pi
            * value.astype(float)
            / period
        ),
        index=value.index,
        dtype="float64",
    )


# ============================================================
# Generator
# ============================================================


class CalendarFeatureGenerator:
    """
    Generate calendar-derived features from a timestamp.

    Only the supplied timestamp is used.

    No occupancy or target information is consumed.
    """

    def __init__(
        self,
        config: CalendarFeatureConfig | None = None,
    ) -> None:

        self._config = (
            config
            or CalendarFeatureConfig()
        )

    # ========================================================
    # Properties
    # ========================================================

    @property
    def config(
        self,
    ) -> CalendarFeatureConfig:

        return self._config

    # ========================================================
    # Public transform
    # ========================================================

    def transform(
        self,
        dataframe: pd.DataFrame,
    ) -> CalendarFeatureResult:
        """
        Generate calendar features.

        The source dataframe is never modified in-place.
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
        # Copy source data.
        # ----------------------------------------------------

        result = dataframe.copy(
            deep=True
        )

        # ----------------------------------------------------
        # Parse timestamp.
        # ----------------------------------------------------

        timestamp = pd.to_datetime(
            result[
                self._config.timestamp_column
            ],
            errors="coerce",
        )

        invalid_timestamp_count = int(
            timestamp.isna().sum()
        )

        if (
            invalid_timestamp_count
            and self._config
            .strict_timestamp_validation
        ):
            raise CalendarFeatureDataError(
                "Input contains "
                f"{invalid_timestamp_count} invalid "
                "timestamps in column "
                f"'{self._config.timestamp_column}'."
            )

        # ----------------------------------------------------
        # Build feature series.
        # ----------------------------------------------------

        generated: dict[
            str,
            pd.Series,
        ] = {}

        feature_columns: list[str] = []

        prefix = (
            self._config.feature_prefix
        )

        # ====================================================
        # Basic calendar components
        # ====================================================

        if self._config.add_year:

            name = _prefixed_name(
                prefix,
                "calendar_year",
            )

            generated[name] = (
                timestamp.dt.year
                .astype("Int64")
            )

            feature_columns.append(name)

        if self._config.add_month:

            name = _prefixed_name(
                prefix,
                "calendar_month",
            )

            generated[name] = (
                timestamp.dt.month
                .astype("Int64")
            )

            feature_columns.append(name)

        if self._config.add_quarter:

            name = _prefixed_name(
                prefix,
                "calendar_quarter",
            )

            generated[name] = (
                timestamp.dt.quarter
                .astype("Int64")
            )

            feature_columns.append(name)

        if self._config.add_week_of_year:

            name = _prefixed_name(
                prefix,
                "calendar_week_of_year",
            )

            # ISO week number.
            generated[name] = (
                timestamp.dt.isocalendar()
                .week
                .astype("Int64")
            )

            feature_columns.append(name)

        if self._config.add_day_of_month:

            name = _prefixed_name(
                prefix,
                "calendar_day_of_month",
            )

            generated[name] = (
                timestamp.dt.day
                .astype("Int64")
            )

            feature_columns.append(name)

        if self._config.add_day_of_year:

            name = _prefixed_name(
                prefix,
                "calendar_day_of_year",
            )

            generated[name] = (
                timestamp.dt.dayofyear
                .astype("Int64")
            )

            feature_columns.append(name)

        if self._config.add_day_of_week:

            name = _prefixed_name(
                prefix,
                "calendar_day_of_week",
            )

            # Monday = 0 ... Sunday = 6.
            generated[name] = (
                timestamp.dt.dayofweek
                .astype("Int64")
            )

            feature_columns.append(name)

        # ====================================================
        # Week of month
        # ====================================================

        if self._config.add_week_of_month:

            # Week number within the month.
            #
            # This is intentionally derived from the date
            # rather than using a rolling operation.
            day = timestamp.dt.day

            week_of_month = (
                (
                    day
                    - 1
                )
                // 7
            ) + 1

            name = _prefixed_name(
                prefix,
                "calendar_week_of_month",
            )

            generated[name] = (
                week_of_month
                .astype("Int64")
            )

            feature_columns.append(name)

        # ====================================================
        # Week of quarter
        # ====================================================

        if self._config.add_week_of_quarter:

            quarter_start_month = (
                (
                    (
                        timestamp.dt.quarter
                        - 1
                    )
                    * 3
                )
                + 1
            )

            quarter_start = pd.to_datetime(
                {
                    "year":
                        timestamp.dt.year,

                    "month":
                        quarter_start_month,

                    "day":
                        1,
                },
                errors="coerce",
            )

            days_since_quarter_start = (
                (
                    timestamp.dt.normalize()
                    - quarter_start
                )
                .dt.days
            )

            week_of_quarter = (
                days_since_quarter_start
                // 7
            ) + 1

            name = _prefixed_name(
                prefix,
                "calendar_week_of_quarter",
            )

            generated[name] = (
                week_of_quarter
                .astype("Int64")
            )

            feature_columns.append(name)

        # ====================================================
        # Weekday / weekend
        # ====================================================

        if self._config.add_weekday_weekend:

            day_of_week = (
                timestamp.dt.dayofweek
            )

            is_weekday = (
                day_of_week < 5
            )

            is_weekend = (
                day_of_week >= 5
            )

            weekday_name = _prefixed_name(
                prefix,
                "is_weekday",
            )

            weekend_name = _prefixed_name(
                prefix,
                "is_weekend",
            )

            generated[
                weekday_name
            ] = is_weekday.astype(
                "boolean"
            )

            generated[
                weekend_name
            ] = is_weekend.astype(
                "boolean"
            )

            feature_columns.extend(
                [
                    weekday_name,
                    weekend_name,
                ]
            )

            # Explicit weekday flags.
            weekday_names = (
                (
                    "is_monday",
                    0,
                ),
                (
                    "is_tuesday",
                    1,
                ),
                (
                    "is_wednesday",
                    2,
                ),
                (
                    "is_thursday",
                    3,
                ),
                (
                    "is_friday",
                    4,
                ),
                (
                    "is_saturday",
                    5,
                ),
                (
                    "is_sunday",
                    6,
                ),
            )

            for name_suffix, value in (
                weekday_names
            ):

                name = _prefixed_name(
                    prefix,
                    name_suffix,
                )

                generated[name] = (
                    day_of_week
                    == value
                ).astype(
                    "boolean"
                )

                feature_columns.append(
                    name
                )

        # ====================================================
        # Month boundaries
        # ====================================================

        if self._config.add_month_boundaries:

            month_start = (
                timestamp.dt.is_month_start
            )

            month_end = (
                timestamp.dt.is_month_end
            )

            name_start = _prefixed_name(
                prefix,
                "is_month_start",
            )

            name_end = _prefixed_name(
                prefix,
                "is_month_end",
            )

            generated[
                name_start
            ] = month_start.astype(
                "boolean"
            )

            generated[
                name_end
            ] = month_end.astype(
                "boolean"
            )

            feature_columns.extend(
                [
                    name_start,
                    name_end,
                ]
            )

            # Days remaining in month.
            month_end_date = (
                timestamp
                + pd.offsets.MonthEnd(0)
            ).dt.normalize()

            days_to_month_end = (
                month_end_date
                - timestamp.dt.normalize()
            ).dt.days

            name = _prefixed_name(
                prefix,
                "days_to_month_end",
            )

            generated[name] = (
                days_to_month_end
                .astype("Int64")
            )

            feature_columns.append(name)

        # ====================================================
        # Quarter boundaries
        # ====================================================

        if self._config.add_quarter_boundaries:

            month = timestamp.dt.month

            is_quarter_start_month = (
                month.isin(
                    [
                        1,
                        4,
                        7,
                        10,
                    ]
                )
            )

            is_quarter_end_month = (
                month.isin(
                    [
                        3,
                        6,
                        9,
                        12,
                    ]
                )
            )

            quarter_start_date = (
                pd.to_datetime(
                    {
                        "year":
                            timestamp.dt.year,

                        "month":
                            (
                                (
                                    timestamp.dt.quarter
                                    - 1
                                )
                                * 3
                            )
                            + 1,

                        "day":
                            1,
                    },
                    errors="coerce",
                )
            )

            quarter_end_date = (
                quarter_start_date
                + pd.offsets.QuarterEnd(
                    0
                )
            )

            name = _prefixed_name(
                prefix,
                "is_quarter_start",
            )

            generated[name] = (
                timestamp.dt.normalize()
                == quarter_start_date
            ).astype(
                "boolean"
            )

            feature_columns.append(name)

            name = _prefixed_name(
                prefix,
                "is_quarter_end",
            )

            generated[name] = (
                timestamp.dt.normalize()
                == quarter_end_date
            ).astype(
                "boolean"
            )

            feature_columns.append(name)

            name = _prefixed_name(
                prefix,
                "is_quarter_start_month",
            )

            generated[name] = (
                is_quarter_start_month
                .astype("boolean")
            )

            feature_columns.append(name)

            name = _prefixed_name(
                prefix,
                "is_quarter_end_month",
            )

            generated[name] = (
                is_quarter_end_month
                .astype("boolean")
            )

            feature_columns.append(name)

        # ====================================================
        # Year boundaries
        # ====================================================

        if self._config.add_year_boundaries:

            is_year_start = (
                timestamp.dt.is_year_start
            )

            is_year_end = (
                timestamp.dt.is_year_end
            )

            name = _prefixed_name(
                prefix,
                "is_year_start",
            )

            generated[name] = (
                is_year_start.astype(
                    "boolean"
                )
            )

            feature_columns.append(name)

            name = _prefixed_name(
                prefix,
                "is_year_end",
            )

            generated[name] = (
                is_year_end.astype(
                    "boolean"
                )
            )

            feature_columns.append(name)

        # ====================================================
        # Cyclic calendar encodings
        # ====================================================

        if self._config.add_cyclic_features:

            # ------------------------------------------------
            # Month
            # ------------------------------------------------

            month = (
                timestamp.dt.month
                .astype(float)
            )

            name = _prefixed_name(
                prefix,
                "calendar_month_sin",
            )

            generated[name] = _safe_sin(
                month - 1,
                12,
            )

            feature_columns.append(name)

            name = _prefixed_name(
                prefix,
                "calendar_month_cos",
            )

            generated[name] = _safe_cos(
                month - 1,
                12,
            )

            feature_columns.append(name)

            # ------------------------------------------------
            # Day of week
            # ------------------------------------------------

            day_of_week = (
                timestamp.dt.dayofweek
                .astype(float)
            )

            name = _prefixed_name(
                prefix,
                "calendar_day_of_week_sin",
            )

            generated[name] = _safe_sin(
                day_of_week,
                7,
            )

            feature_columns.append(name)

            name = _prefixed_name(
                prefix,
                "calendar_day_of_week_cos",
            )

            generated[name] = _safe_cos(
                day_of_week,
                7,
            )

            feature_columns.append(name)

            # ------------------------------------------------
            # Day of year.
            #
            # Use 365.25 to avoid an artificial discontinuity
            # across the year boundary.
            # ------------------------------------------------

            day_of_year = (
                timestamp.dt.dayofyear
                .astype(float)
            )

            name = _prefixed_name(
                prefix,
                "calendar_day_of_year_sin",
            )

            generated[name] = _safe_sin(
                day_of_year - 1,
                365.25,
            )

            feature_columns.append(name)

            name = _prefixed_name(
                prefix,
                "calendar_day_of_year_cos",
            )

            generated[name] = _safe_cos(
                day_of_year - 1,
                365.25,
            )

            feature_columns.append(name)

            # ------------------------------------------------
            # Quarter
            # ------------------------------------------------

            quarter = (
                timestamp.dt.quarter
                .astype(float)
            )

            name = _prefixed_name(
                prefix,
                "calendar_quarter_sin",
            )

            generated[name] = _safe_sin(
                quarter - 1,
                4,
            )

            feature_columns.append(name)

            name = _prefixed_name(
                prefix,
                "calendar_quarter_cos",
            )

            generated[name] = _safe_cos(
                quarter - 1,
                4,
            )

            feature_columns.append(name)

        # ====================================================
        # Materialize generated columns
        # ====================================================

        generated_frame = pd.DataFrame(
            generated,
            index=result.index,
        )

        result = pd.concat(
            [
                result,
                generated_frame,
            ],
            axis=1,
        )

        # ====================================================
        # Preserve original order
        # ====================================================

        if self._config.preserve_original_order:

            result = result.loc[
                original_index
            ]

        # ====================================================
        # Statistics
        # ====================================================

        valid_timestamp = (
            timestamp.dropna()
        )

        if valid_timestamp.empty:

            minimum_timestamp = None

            maximum_timestamp = None

            unique_dates = 0

            unique_months = 0

            unique_quarters = 0

            unique_weekdays = 0

            weekday_row_count = 0

            weekend_row_count = 0

        else:

            minimum_timestamp = (
                valid_timestamp.min()
            )

            maximum_timestamp = (
                valid_timestamp.max()
            )

            unique_dates = int(
                valid_timestamp.dt
                .normalize()
                .nunique()
            )

            unique_months = int(
                valid_timestamp.dt
                .to_period("M")
                .nunique()
            )

            unique_quarters = int(
                valid_timestamp.dt
                .to_period("Q")
                .nunique()
            )

            unique_weekdays = int(
                valid_timestamp.dt
                .dayofweek
                .nunique()
            )

            weekday_row_count = int(
                (
                    valid_timestamp.dt
                    .dayofweek
                    < 5
                ).sum()
            )

            weekend_row_count = int(
                (
                    valid_timestamp.dt
                    .dayofweek
                    >= 5
                ).sum()
            )

        # ====================================================
        # Metadata
        # ====================================================

        metadata = {
            "timestamp_column":
                self._config.timestamp_column,

            "feature_prefix":
                self._config.feature_prefix,

            "future_data_used":
                False,

            "target_data_used":
                False,

            "occupancy_data_used":
                False,

            "historical_values_used":
                False,

            "external_data_used":
                False,

            "row_count_preserved":
                len(result)
                == source_row_count,

            "row_order_preserved":
                True,

            "data_modified":
                False,

            "timestamp_only":
                True,

            "deterministic":
                True,

            **self._config.metadata,
        }

        statistics = CalendarFeatureStatistics(
            source_row_count=
                source_row_count,

            output_row_count=
                len(result),

            source_column_count=
                source_column_count,

            output_column_count=
                len(result.columns),

            feature_count=
                len(feature_columns),

            invalid_timestamp_count=
                invalid_timestamp_count,

            unique_dates=
                unique_dates,

            unique_months=
                unique_months,

            unique_quarters=
                unique_quarters,

            unique_weekdays=
                unique_weekdays,

            weekday_row_count=
                weekday_row_count,

            weekend_row_count=
                weekend_row_count,

            minimum_timestamp=
                minimum_timestamp,

            maximum_timestamp=
                maximum_timestamp,

            metadata=metadata,
        )

        return CalendarFeatureResult(
            dataframe=result,

            feature_columns=tuple(
                feature_columns
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
        Validate source dataframe.
        """

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise CalendarFeatureDataError(
                "Input must be a pandas DataFrame."
            )

        if dataframe.empty:
            raise CalendarFeatureDataError(
                "Input dataframe is empty."
            )

        if (
            self._config.timestamp_column
            not in dataframe.columns
        ):
            raise CalendarFeatureDataError(
                "Required timestamp column "
                f"'{self._config.timestamp_column}' "
                "is missing."
            )

        if (
            dataframe.columns
            .duplicated()
            .any()
        ):
            duplicates = (
                dataframe.columns[
                    dataframe.columns
                    .duplicated()
                ]
                .tolist()
            )

            raise CalendarFeatureDataError(
                "Duplicate input columns detected: "
                f"{duplicates}"
            )

    # ========================================================
    # Public metadata
    # ========================================================

    def leakage_metadata(
        self,
    ) -> dict[str, Any]:
        """
        Return explicit leakage metadata.
        """

        return {
            "future_data_used":
                False,

            "target_data_used":
                False,

            "occupancy_data_used":
                False,

            "historical_values_used":
                False,

            "external_data_used":
                False,

            "timestamp_only":
                True,

            "centered_windows_used":
                False,

            "forward_lookup_used":
                False,
        }


# ============================================================
# Expected feature columns
# ============================================================


def expected_calendar_feature_columns(
    config: CalendarFeatureConfig | None = None,
) -> tuple[str, ...]:
    """
    Return the expected calendar feature names.
    """

    config = (
        config
        or CalendarFeatureConfig()
    )

    prefix = (
        config.feature_prefix
    )

    names: list[str] = []

    def add(name: str) -> None:
        names.append(
            _prefixed_name(
                prefix,
                name,
            )
        )

    if config.add_year:
        add("calendar_year")

    if config.add_month:
        add("calendar_month")

    if config.add_quarter:
        add("calendar_quarter")

    if config.add_week_of_year:
        add("calendar_week_of_year")

    if config.add_day_of_month:
        add("calendar_day_of_month")

    if config.add_day_of_year:
        add("calendar_day_of_year")

    if config.add_day_of_week:
        add("calendar_day_of_week")

    if config.add_week_of_month:
        add("calendar_week_of_month")

    if config.add_week_of_quarter:
        add("calendar_week_of_quarter")

    if config.add_weekday_weekend:

        add("is_weekday")

        add("is_weekend")

        for name in (
            "is_monday",
            "is_tuesday",
            "is_wednesday",
            "is_thursday",
            "is_friday",
            "is_saturday",
            "is_sunday",
        ):
            add(name)

    if config.add_month_boundaries:

        add("is_month_start")

        add("is_month_end")

        add("days_to_month_end")

    if config.add_quarter_boundaries:

        add("is_quarter_start")

        add("is_quarter_end")

        add("is_quarter_start_month")

        add("is_quarter_end_month")

    if config.add_year_boundaries:

        add("is_year_start")

        add("is_year_end")

    if config.add_cyclic_features:

        add("calendar_month_sin")

        add("calendar_month_cos")

        add("calendar_day_of_week_sin")

        add("calendar_day_of_week_cos")

        add("calendar_day_of_year_sin")

        add("calendar_day_of_year_cos")

        add("calendar_quarter_sin")

        add("calendar_quarter_cos")

    return tuple(names)


# ============================================================
# Validation
# ============================================================


def validate_calendar_features(
    dataframe: pd.DataFrame,
    *,
    config: CalendarFeatureConfig | None = None,
) -> dict[str, Any]:
    """
    Validate generated calendar features.
    """

    config = (
        config
        or CalendarFeatureConfig()
    )

    errors: list[str] = []

    expected = (
        expected_calendar_feature_columns(
            config
        )
    )

    # --------------------------------------------------------
    # Missing columns
    # --------------------------------------------------------

    missing_columns = [
        column
        for column in expected
        if column not in dataframe.columns
    ]

    if missing_columns:

        errors.append(
            "Missing calendar feature columns: "
            f"{missing_columns}"
        )

    # --------------------------------------------------------
    # Duplicate columns
    # --------------------------------------------------------

    duplicate_columns = (
        dataframe.columns[
            dataframe.columns
            .duplicated()
        ]
        .tolist()
    )

    if duplicate_columns:

        errors.append(
            "Duplicate dataframe columns detected: "
            f"{duplicate_columns}"
        )

    # --------------------------------------------------------
    # Internal helper leakage
    # --------------------------------------------------------

    internal_columns = [
        column
        for column in dataframe.columns
        if column.startswith("__calendar_")
    ]

    if internal_columns:

        errors.append(
            "Internal calendar columns leaked into "
            f"output: {internal_columns}"
        )

    # --------------------------------------------------------
    # Feature count
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
            "Calendar feature count mismatch: "
            f"expected {len(expected)}, "
            f"found {actual_feature_count}."
        )

    # --------------------------------------------------------
    # Numeric columns
    # --------------------------------------------------------

    numeric_suffixes = (
        "calendar_year",
        "calendar_month",
        "calendar_quarter",
        "calendar_week_of_year",
        "calendar_day_of_month",
        "calendar_day_of_year",
        "calendar_day_of_week",
        "calendar_week_of_month",
        "calendar_week_of_quarter",
        "days_to_month_end",
    )

    numeric_columns = [
        column
        for column in expected
        if column in dataframe.columns
        and any(
            column.endswith(
                suffix
            )
            for suffix in numeric_suffixes
        )
    ]

    for column in numeric_columns:

        numeric = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

        if np.isinf(
            numeric.to_numpy(
                dtype="float64",
            )
        ).any():

            errors.append(
                f"Calendar feature '{column}' "
                "contains infinite values."
            )

    # --------------------------------------------------------
    # Cyclic feature range validation
    # --------------------------------------------------------

    cyclic_columns = [
        column
        for column in expected
        if column in dataframe.columns
        and (
            column.endswith("_sin")
            or column.endswith("_cos")
        )
    ]

    for column in cyclic_columns:

        values = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

        valid_values = (
            values.dropna()
        )

        if not valid_values.empty:

            if (
                valid_values.min()
                < -1.000001
                or valid_values.max()
                > 1.000001
            ):

                errors.append(
                    f"Cyclic feature '{column}' "
                    "contains values outside "
                    "the expected [-1, 1] range."
                )

    # --------------------------------------------------------
    # Boolean feature validation
    # --------------------------------------------------------

    boolean_columns = [
        column
        for column in expected
        if column in dataframe.columns
        and (
            column.startswith(
                "is_"
            )
            or column.endswith(
                "is_weekday"
            )
            or column.endswith(
                "is_weekend"
            )
        )
    ]

    for column in boolean_columns:

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
                f"Boolean calendar feature "
                f"'{column}' has unexpected "
                f"dtype {dtype}."
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

        "row_count":
            len(dataframe),

        "future_data_used":
            False,

        "target_data_used":
            False,

        "occupancy_data_used":
            False,

        "historical_values_used":
            False,

        "external_data_used":
            False,

        "timestamp_only":
            True,

        "centered_windows_used":
            False,

        "forward_lookup_used":
            False,
    }


# ============================================================
# Convenience API
# ============================================================


def add_calendar_features(
    dataframe: pd.DataFrame,
    *,
    config: CalendarFeatureConfig | None = None,
) -> CalendarFeatureResult:
    """
    Add calendar features using the supplied configuration.
    """

    generator = CalendarFeatureGenerator(
        config=config
    )

    return generator.transform(
        dataframe
    )


# ============================================================
# Birmingham API
# ============================================================


def add_birmingham_calendar_features(
    dataframe: pd.DataFrame,
) -> CalendarFeatureResult:
    """
    Generate the standard SmartPark Birmingham calendar
    feature set.
    """

    config = CalendarFeatureConfig(
        timestamp_column=(
            "normalized_at"
        ),

        feature_prefix="",

        add_year=True,

        add_month=True,

        add_quarter=True,

        add_week_of_year=True,

        add_day_of_month=True,

        add_day_of_year=True,

        add_day_of_week=True,

        add_week_of_month=True,

        add_week_of_quarter=True,

        add_weekday_weekend=True,

        add_month_boundaries=True,

        add_quarter_boundaries=True,

        add_year_boundaries=True,

        add_cyclic_features=True,

        strict_timestamp_validation=True,

        preserve_original_order=True,

        metadata={
            "source_name":
                "BIRMINGHAM",

            "feature_family":
                "calendar",

            "timestamp_only":
                True,
        },
    )

    return add_calendar_features(
        dataframe,
        config=config,
    )


# ============================================================
# Public exports
# ============================================================


__all__ = [
    "CalendarFeatureError",
    "CalendarFeatureConfigurationError",
    "CalendarFeatureDataError",
    "CalendarFeatureConfig",
    "CalendarFeatureStatistics",
    "CalendarFeatureResult",
    "CalendarFeatureGenerator",
    "expected_calendar_feature_columns",
    "validate_calendar_features",
    "add_calendar_features",
    "add_birmingham_calendar_features",
]