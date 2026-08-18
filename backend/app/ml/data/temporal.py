"""
SmartPark AI - Temporal Data Audit.

This module audits the temporal characteristics of the canonical
ML dataset before resampling and feature engineering.

IMPORTANT
---------

This module is READ-ONLY.

It does NOT:

    - resample observations
    - interpolate values
    - forward-fill values
    - backward-fill values
    - create ML targets
    - engineer predictive features
    - modify the input DataFrame

Its purpose is to answer:

    1. How frequently are observations recorded?
    2. Is the data regularly sampled?
    3. How much data exists per facility?
    4. What is the temporal coverage?
    5. Where are the gaps?
    6. Are facilities sufficiently continuous for LSTM?
    7. Is a 30-minute modelling grid appropriate?

This audit should be completed before temporal normalization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import pandas as pd


# ============================================================
# Canonical column names
# ============================================================


FACILITY_COLUMN = "source_facility_code"
TIMESTAMP_COLUMN = "observed_at"
OCCUPANCY_COLUMN = "occupied_spaces"
OCCUPANCY_RATE_COLUMN = "occupancy_rate"
CAPACITY_COLUMN = "total_spaces"


# ============================================================
# Exceptions
# ============================================================


class TemporalAuditError(Exception):
    """Base exception for temporal audit errors."""


class TemporalAuditSchemaError(
    TemporalAuditError
):
    """Raised when required columns are missing."""


class TemporalAuditDataError(
    TemporalAuditError
):
    """Raised when temporal data cannot be analysed."""


# ============================================================
# Facility temporal statistics
# ============================================================


@dataclass(frozen=True, slots=True)
class FacilityTemporalStatistics:
    """
    Temporal statistics for one parking facility.
    """

    facility_code: str

    observation_count: int

    first_observation: pd.Timestamp

    last_observation: pd.Timestamp

    coverage_days: float

    coverage_hours: float

    mean_interval_minutes: float | None

    median_interval_minutes: float | None

    min_interval_minutes: float | None

    max_interval_minutes: float | None

    std_interval_minutes: float | None

    interval_count: int

    intervals_0_to_15_minutes: int

    intervals_15_to_30_minutes: int

    intervals_30_to_45_minutes: int

    intervals_45_to_60_minutes: int

    intervals_over_60_minutes: int

    intervals_over_120_minutes: int

    exact_30_minute_intervals: int

    approximately_30_minute_intervals: int

    duplicate_timestamps: int

    unique_calendar_days: int

    weekday_observations: int

    weekend_observations: int

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )


# ============================================================
# Global temporal statistics
# ============================================================


@dataclass(frozen=True, slots=True)
class TemporalAuditStatistics:
    """
    Overall temporal statistics for the complete dataset.
    """

    total_rows: int

    facility_count: int

    first_observation: pd.Timestamp

    last_observation: pd.Timestamp

    coverage_days: float

    coverage_hours: float

    mean_interval_minutes: float | None

    median_interval_minutes: float | None

    min_interval_minutes: float | None

    max_interval_minutes: float | None

    std_interval_minutes: float | None

    total_intervals: int

    intervals_0_to_15_minutes: int

    intervals_15_to_30_minutes: int

    intervals_30_to_45_minutes: int

    intervals_45_to_60_minutes: int

    intervals_over_60_minutes: int

    intervals_over_120_minutes: int

    exact_30_minute_intervals: int

    approximately_30_minute_intervals: int

    duplicate_timestamps: int

    unique_calendar_days: int

    weekday_observations: int

    weekend_observations: int

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )


# ============================================================
# Temporal audit result
# ============================================================


@dataclass(frozen=True, slots=True)
class TemporalAuditResult:
    """
    Complete temporal audit result.
    """

    overall: TemporalAuditStatistics

    facilities: tuple[FacilityTemporalStatistics, ...]

    interval_distribution: pd.DataFrame

    facility_summary: pd.DataFrame

    daily_summary: pd.DataFrame

    warnings: tuple[str, ...] = ()

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class TemporalAuditConfig:
    """
    Configuration for the temporal audit.
    """

    facility_column: str = FACILITY_COLUMN

    timestamp_column: str = TIMESTAMP_COLUMN

    target_interval_minutes: int = 30

    approximate_interval_tolerance_minutes: int = 10

    large_gap_threshold_minutes: int = 60

    very_large_gap_threshold_minutes: int = 120

    def __post_init__(self) -> None:
        if self.target_interval_minutes <= 0:
            raise ValueError(
                "target_interval_minutes must be greater than zero."
            )

        if (
            self.approximate_interval_tolerance_minutes
            < 0
        ):
            raise ValueError(
                "approximate_interval_tolerance_minutes "
                "cannot be negative."
            )

        if self.large_gap_threshold_minutes <= 0:
            raise ValueError(
                "large_gap_threshold_minutes must be greater "
                "than zero."
            )

        if self.very_large_gap_threshold_minutes <= 0:
            raise ValueError(
                "very_large_gap_threshold_minutes must be "
                "greater than zero."
            )


# ============================================================
# Temporal Auditor
# ============================================================


class TemporalAuditor:
    """
    Audits temporal properties of a canonical ML dataset.

    The input DataFrame is never modified.
    """

    def __init__(
        self,
        config: TemporalAuditConfig | None = None,
    ) -> None:

        self._config = (
            config
            if config is not None
            else TemporalAuditConfig()
        )

    # ========================================================
    # Public API
    # ========================================================

    def audit(
        self,
        dataframe: pd.DataFrame,
    ) -> TemporalAuditResult:
        """
        Perform the complete temporal audit.
        """

        self._validate_schema(
            dataframe,
        )

        working = dataframe.copy(
            deep=True,
        )

        working[
            self._config.timestamp_column
        ] = pd.to_datetime(
            working[
                self._config.timestamp_column
            ],
            errors="coerce",
        )

        if working[
            self._config.timestamp_column
        ].isna().any():
            raise TemporalAuditDataError(
                "Temporal audit cannot proceed because "
                "the dataset contains invalid timestamps."
            )

        working = working.sort_values(
            by=[
                self._config.facility_column,
                self._config.timestamp_column,
            ],
            kind="stable",
        ).reset_index(
            drop=True,
        )

        facility_statistics = []

        interval_records = []

        for facility_code, facility_df in (
            working.groupby(
                self._config.facility_column,
                sort=True,
            )
        ):
            facility_df = facility_df.copy()

            statistics, intervals = (
                self._audit_facility(
                    facility_code=str(
                        facility_code
                    ),
                    dataframe=facility_df,
                )
            )

            facility_statistics.append(
                statistics
            )

            if not intervals.empty:
                interval_records.append(
                    intervals
                )

        overall = self._build_overall_statistics(
            working,
            facility_statistics,
        )

        interval_distribution = (
            self._build_interval_distribution(
                interval_records
            )
        )

        facility_summary = (
            self._build_facility_summary(
                facility_statistics
            )
        )

        daily_summary = (
            self._build_daily_summary(
                working
            )
        )

        warnings = (
            self._generate_warnings(
                overall,
                facility_statistics,
            )
        )

        return TemporalAuditResult(
            overall=overall,
            facilities=tuple(
                facility_statistics
            ),
            interval_distribution=(
                interval_distribution
            ),
            facility_summary=facility_summary,
            daily_summary=daily_summary,
            warnings=tuple(warnings),
            metadata={
                "target_interval_minutes": (
                    self._config
                    .target_interval_minutes
                ),
                "approximate_tolerance_minutes": (
                    self._config
                    .approximate_interval_tolerance_minutes
                ),
            },
        )

    # ========================================================
    # Schema validation
    # ========================================================

    def _validate_schema(
        self,
        dataframe: pd.DataFrame,
    ) -> None:
        """
        Validate required temporal columns.
        """

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise TemporalAuditDataError(
                "Temporal audit requires a pandas DataFrame."
            )

        required_columns = {
            self._config.facility_column,
            self._config.timestamp_column,
        }

        missing = (
            required_columns
            - set(dataframe.columns)
        )

        if missing:
            raise TemporalAuditSchemaError(
                "Temporal audit is missing required columns: "
                f"{', '.join(sorted(missing))}"
            )

        if dataframe.empty:
            raise TemporalAuditDataError(
                "Cannot perform temporal audit on an empty dataset."
            )

    # ========================================================
    # Facility audit
    # ========================================================

    def _audit_facility(
        self,
        *,
        facility_code: str,
        dataframe: pd.DataFrame,
    ) -> tuple[
        FacilityTemporalStatistics,
        pd.DataFrame,
    ]:
        """
        Audit one facility.
        """

        timestamps = (
            dataframe[
                self._config.timestamp_column
            ]
            .sort_values()
        )

        observation_count = len(
            timestamps
        )

        first_observation = (
            timestamps.iloc[0]
        )

        last_observation = (
            timestamps.iloc[-1]
        )

        coverage = (
            last_observation
            - first_observation
        )

        coverage_days = (
            coverage.total_seconds()
            / 86400.0
        )

        coverage_hours = (
            coverage.total_seconds()
            / 3600.0
        )

        intervals = (
            timestamps
            .diff()
            .dropna()
            .dt.total_seconds()
            .div(60.0)
        )

        interval_frame = (
            self._build_interval_frame(
                facility_code=facility_code,
                timestamps=timestamps,
                intervals=intervals,
            )
        )

        duplicate_timestamps = int(
            timestamps.duplicated(
                keep=False
            ).sum()
        )

        unique_days = int(
            timestamps.dt.date.nunique()
        )

        weekday_observations = int(
            (
                timestamps.dt.dayofweek
                < 5
            ).sum()
        )

        weekend_observations = int(
            (
                timestamps.dt.dayofweek
                >= 5
            ).sum()
        )

        statistics = (
            self._build_facility_statistics(
                facility_code=facility_code,
                dataframe=dataframe,
                timestamps=timestamps,
                intervals=intervals,
                coverage_days=coverage_days,
                coverage_hours=coverage_hours,
                duplicate_timestamps=(
                    duplicate_timestamps
                ),
                unique_days=unique_days,
                weekday_observations=(
                    weekday_observations
                ),
                weekend_observations=(
                    weekend_observations
                ),
            )
        )

        return statistics, interval_frame

    # ========================================================
    # Interval frame
    # ========================================================

    def _build_interval_frame(
        self,
        *,
        facility_code: str,
        timestamps: pd.Series,
        intervals: pd.Series,
    ) -> pd.DataFrame:
        """
        Build row-level interval information.

        This is diagnostic information only.
        """

        if intervals.empty:
            return pd.DataFrame(
                columns=[
                    "facility_code",
                    "observed_at",
                    "previous_observed_at",
                    "interval_minutes",
                ]
            )

        previous = timestamps.shift(1)

        frame = pd.DataFrame(
            {
                "facility_code": facility_code,
                "observed_at": timestamps.iloc[1:]
                .to_numpy(),
                "previous_observed_at": previous.iloc[
                    1:
                ].to_numpy(),
                "interval_minutes": intervals.to_numpy(),
            }
        )

        return frame.reset_index(
            drop=True
        )

    # ========================================================
    # Facility statistics
    # ========================================================

    def _build_facility_statistics(
        self,
        *,
        facility_code: str,
        dataframe: pd.DataFrame,
        timestamps: pd.Series,
        intervals: pd.Series,
        coverage_days: float,
        coverage_hours: float,
        duplicate_timestamps: int,
        unique_days: int,
        weekday_observations: int,
        weekend_observations: int,
    ) -> FacilityTemporalStatistics:
        """
        Construct statistics for one facility.
        """

        return FacilityTemporalStatistics(
            facility_code=facility_code,
            observation_count=len(
                dataframe
            ),
            first_observation=timestamps.iloc[
                0
            ],
            last_observation=timestamps.iloc[
                -1
            ],
            coverage_days=coverage_days,
            coverage_hours=coverage_hours,
            mean_interval_minutes=(
                float(intervals.mean())
                if not intervals.empty
                else None
            ),
            median_interval_minutes=(
                float(intervals.median())
                if not intervals.empty
                else None
            ),
            min_interval_minutes=(
                float(intervals.min())
                if not intervals.empty
                else None
            ),
            max_interval_minutes=(
                float(intervals.max())
                if not intervals.empty
                else None
            ),
            std_interval_minutes=(
                float(intervals.std())
                if len(intervals) > 1
                else None
            ),
            interval_count=len(
                intervals
            ),
            intervals_0_to_15_minutes=int(
                (
                    intervals < 15
                ).sum()
            ),
            intervals_15_to_30_minutes=int(
                (
                    (intervals >= 15)
                    & (intervals < 30)
                ).sum()
            ),
            intervals_30_to_45_minutes=int(
                (
                    (intervals >= 30)
                    & (intervals < 45)
                ).sum()
            ),
            intervals_45_to_60_minutes=int(
                (
                    (intervals >= 45)
                    & (intervals < 60)
                ).sum()
            ),
            intervals_over_60_minutes=int(
                (
                    intervals >= self._config
                    .large_gap_threshold_minutes
                ).sum()
            ),
            intervals_over_120_minutes=int(
                (
                    intervals >= self._config
                    .very_large_gap_threshold_minutes
                ).sum()
            ),
            exact_30_minute_intervals=int(
                (
                    intervals
                    == self._config
                    .target_interval_minutes
                ).sum()
            ),
            approximately_30_minute_intervals=int(
                (
                    (
                        intervals
                        - self._config
                        .target_interval_minutes
                    ).abs()
                    <= self._config
                    .approximate_interval_tolerance_minutes
                ).sum()
            ),
            duplicate_timestamps=(
                duplicate_timestamps
            ),
            unique_calendar_days=unique_days,
            weekday_observations=(
                weekday_observations
            ),
            weekend_observations=(
                weekend_observations
            ),
        )

    # ========================================================
    # Overall statistics
    # ========================================================

    def _build_overall_statistics(
        self,
        dataframe: pd.DataFrame,
        facilities: list[
            FacilityTemporalStatistics
        ],
    ) -> TemporalAuditStatistics:
        """
        Construct overall dataset statistics.
        """

        timestamps = (
            dataframe[
                self._config.timestamp_column
            ]
        )

        first_observation = (
            timestamps.min()
        )

        last_observation = (
            timestamps.max()
        )

        coverage = (
            last_observation
            - first_observation
        )

        coverage_days = (
            coverage.total_seconds()
            / 86400.0
        )

        coverage_hours = (
            coverage.total_seconds()
            / 3600.0
        )

        # Aggregate facility-level intervals.
        interval_series = []

        for facility in facilities:
            if (
                facility.interval_count
                > 0
            ):
                interval_series.extend(
                    self._facility_interval_values(
                        dataframe,
                        facility.facility_code,
                    )
                )

        intervals = pd.Series(
            interval_series,
            dtype="float64",
        )

        return TemporalAuditStatistics(
            total_rows=len(dataframe),
            facility_count=len(facilities),
            first_observation=(
                first_observation
            ),
            last_observation=(
                last_observation
            ),
            coverage_days=coverage_days,
            coverage_hours=coverage_hours,
            mean_interval_minutes=(
                float(intervals.mean())
                if not intervals.empty
                else None
            ),
            median_interval_minutes=(
                float(intervals.median())
                if not intervals.empty
                else None
            ),
            min_interval_minutes=(
                float(intervals.min())
                if not intervals.empty
                else None
            ),
            max_interval_minutes=(
                float(intervals.max())
                if not intervals.empty
                else None
            ),
            std_interval_minutes=(
                float(intervals.std())
                if len(intervals) > 1
                else None
            ),
            total_intervals=len(
                intervals
            ),
            intervals_0_to_15_minutes=int(
                (
                    intervals < 15
                ).sum()
            ),
            intervals_15_to_30_minutes=int(
                (
                    (intervals >= 15)
                    & (intervals < 30)
                ).sum()
            ),
            intervals_30_to_45_minutes=int(
                (
                    (intervals >= 30)
                    & (intervals < 45)
                ).sum()
            ),
            intervals_45_to_60_minutes=int(
                (
                    (intervals >= 45)
                    & (intervals < 60)
                ).sum()
            ),
            intervals_over_60_minutes=int(
                (
                    intervals
                    >= self._config
                    .large_gap_threshold_minutes
                ).sum()
            ),
            intervals_over_120_minutes=int(
                (
                    intervals
                    >= self._config
                    .very_large_gap_threshold_minutes
                ).sum()
            ),
            exact_30_minute_intervals=int(
                (
                    intervals
                    == self._config
                    .target_interval_minutes
                ).sum()
            ),
            approximately_30_minute_intervals=int(
                (
                    (
                        intervals
                        - self._config
                        .target_interval_minutes
                    ).abs()
                    <= self._config
                    .approximate_interval_tolerance_minutes
                ).sum()
            ),
            duplicate_timestamps=int(
                dataframe[
                    [
                        self._config
                        .facility_column,
                        self._config
                        .timestamp_column,
                    ]
                ]
                .duplicated(
                    keep=False
                )
                .sum()
            ),
            unique_calendar_days=int(
                timestamps.dt.date.nunique()
            ),
            weekday_observations=int(
                (
                    timestamps.dt.dayofweek
                    < 5
                ).sum()
            ),
            weekend_observations=int(
                (
                    timestamps.dt.dayofweek
                    >= 5
                ).sum()
            ),
            metadata={
                "facility_statistics": len(
                    facilities
                ),
            },
        )

    # ========================================================
    # Facility interval extraction
    # ========================================================

    def _facility_interval_values(
        self,
        dataframe: pd.DataFrame,
        facility_code: str,
    ) -> list[float]:
        """
        Extract interval values for one facility.
        """

        facility_df = dataframe.loc[
            dataframe[
                self._config.facility_column
            ].astype(str)
            == facility_code
        ]

        timestamps = (
            facility_df[
                self._config.timestamp_column
            ]
            .sort_values()
        )

        return (
            timestamps
            .diff()
            .dropna()
            .dt.total_seconds()
            .div(60.0)
            .tolist()
        )

    # ========================================================
    # Interval distribution
    # ========================================================

    def _build_interval_distribution(
        self,
        interval_records: list[pd.DataFrame],
    ) -> pd.DataFrame:
        """
        Produce interval distribution statistics.
        """

        if not interval_records:
            return pd.DataFrame(
                columns=[
                    "interval_minutes",
                    "observation_count",
                    "percentage",
                ]
            )

        combined = pd.concat(
            interval_records,
            ignore_index=True,
        )

        distribution = (
            combined[
                "interval_minutes"
            ]
            .round(2)
            .value_counts()
            .sort_index()
            .rename(
                "observation_count"
            )
            .reset_index()
        )

        distribution.columns = [
            "interval_minutes",
            "observation_count",
        ]

        total = (
            distribution[
                "observation_count"
            ].sum()
        )

        if total > 0:
            distribution[
                "percentage"
            ] = (
                distribution[
                    "observation_count"
                ]
                / total
                * 100.0
            )
        else:
            distribution[
                "percentage"
            ] = 0.0

        return distribution

    # ========================================================
    # Facility summary
    # ========================================================

    @staticmethod
    def _build_facility_summary(
        facilities: list[
            FacilityTemporalStatistics
        ],
    ) -> pd.DataFrame:
        """
        Convert facility statistics to a DataFrame.
        """

        records = []

        for facility in facilities:
            records.append(
                {
                    "facility_code": (
                        facility.facility_code
                    ),
                    "observation_count": (
                        facility.observation_count
                    ),
                    "first_observation": (
                        facility.first_observation
                    ),
                    "last_observation": (
                        facility.last_observation
                    ),
                    "coverage_days": (
                        facility.coverage_days
                    ),
                    "coverage_hours": (
                        facility.coverage_hours
                    ),
                    "mean_interval_minutes": (
                        facility.mean_interval_minutes
                    ),
                    "median_interval_minutes": (
                        facility.median_interval_minutes
                    ),
                    "min_interval_minutes": (
                        facility.min_interval_minutes
                    ),
                    "max_interval_minutes": (
                        facility.max_interval_minutes
                    ),
                    "std_interval_minutes": (
                        facility.std_interval_minutes
                    ),
                    "interval_count": (
                        facility.interval_count
                    ),
                    "intervals_0_to_15_minutes": (
                        facility
                        .intervals_0_to_15_minutes
                    ),
                    "intervals_15_to_30_minutes": (
                        facility
                        .intervals_15_to_30_minutes
                    ),
                    "intervals_30_to_45_minutes": (
                        facility
                        .intervals_30_to_45_minutes
                    ),
                    "intervals_45_to_60_minutes": (
                        facility
                        .intervals_45_to_60_minutes
                    ),
                    "intervals_over_60_minutes": (
                        facility
                        .intervals_over_60_minutes
                    ),
                    "intervals_over_120_minutes": (
                        facility
                        .intervals_over_120_minutes
                    ),
                    "exact_30_minute_intervals": (
                        facility
                        .exact_30_minute_intervals
                    ),
                    "approximately_30_minute_intervals": (
                        facility
                        .approximately_30_minute_intervals
                    ),
                    "duplicate_timestamps": (
                        facility
                        .duplicate_timestamps
                    ),
                    "unique_calendar_days": (
                        facility
                        .unique_calendar_days
                    ),
                    "weekday_observations": (
                        facility
                        .weekday_observations
                    ),
                    "weekend_observations": (
                        facility
                        .weekend_observations
                    ),
                }
            )

        return pd.DataFrame(
            records
        )

    # ========================================================
    # Daily summary
    # ========================================================

    def _build_daily_summary(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Build observation counts by facility and date.

        This helps identify days with sparse or missing data.
        """

        working = dataframe[
            [
                self._config.facility_column,
                self._config.timestamp_column,
            ]
        ].copy()

        working["date"] = (
            working[
                self._config.timestamp_column
            ].dt.date
        )

        summary = (
            working
            .groupby(
                [
                    self._config.facility_column,
                    "date",
                ],
                as_index=False,
            )
            .size()
            .rename(
                columns={
                    "size": "observation_count",
                    self._config
                    .facility_column: (
                        "facility_code"
                    ),
                }
            )
        )

        return summary

    # ========================================================
    # Warnings
    # ========================================================

    def _generate_warnings(
        self,
        overall: TemporalAuditStatistics,
        facilities: list[
            FacilityTemporalStatistics
        ],
    ) -> list[str]:
        """
        Generate human-readable temporal warnings.

        These are observations, not automatic decisions.
        """

        warnings: list[str] = []

        if (
            overall.median_interval_minutes
            is not None
            and abs(
                overall.median_interval_minutes
                - self._config
                .target_interval_minutes
            )
            > self._config
            .approximate_interval_tolerance_minutes
        ):
            warnings.append(
                "The median observation interval differs "
                "materially from the proposed "
                f"{self._config.target_interval_minutes}-minute "
                "modelling interval."
            )

        if (
            overall.intervals_over_60_minutes
            > 0
        ):
            warnings.append(
                "The dataset contains intervals longer "
                "than 60 minutes."
            )

        if (
            overall.intervals_over_120_minutes
            > 0
        ):
            warnings.append(
                "The dataset contains intervals longer "
                "than 120 minutes. These may require special "
                "treatment during temporal normalization."
            )

        if (
            overall.weekend_observations
            == 0
        ):
            warnings.append(
                "No weekend observations were found."
            )

        if (
            overall.approximately_30_minute_intervals
            > 0
            and overall.total_intervals > 0
        ):
            percentage = (
                overall
                .approximately_30_minute_intervals
                / overall.total_intervals
                * 100.0
            )

            warnings.append(
                f"{percentage:.2f}% of intervals fall within "
                f"±{self._config.approximate_interval_tolerance_minutes} "
                "minutes of the target 30-minute interval."
            )

        sparse_facilities = [
            facility.facility_code
            for facility in facilities
            if facility.observation_count < 100
        ]

        if sparse_facilities:
            warnings.append(
                "Some facilities contain fewer than "
                "100 observations: "
                + ", ".join(
                    sparse_facilities[:10]
                )
                + (
                    "..."
                    if len(sparse_facilities) > 10
                    else ""
                )
            )

        return warnings


# ============================================================
# Convenience function
# ============================================================


def audit_temporal_dataset(
    dataframe: pd.DataFrame,
    *,
    target_interval_minutes: int = 30,
    approximate_interval_tolerance_minutes: int = 10,
    large_gap_threshold_minutes: int = 60,
    very_large_gap_threshold_minutes: int = 120,
) -> TemporalAuditResult:
    """
    Convenience function for auditing a canonical dataset.

    Example
    -------

        result = audit_temporal_dataset(
            dataframe,
        )
    """

    config = TemporalAuditConfig(
        target_interval_minutes=(
            target_interval_minutes
        ),
        approximate_interval_tolerance_minutes=(
            approximate_interval_tolerance_minutes
        ),
        large_gap_threshold_minutes=(
            large_gap_threshold_minutes
        ),
        very_large_gap_threshold_minutes=(
            very_large_gap_threshold_minutes
        ),
    )

    auditor = TemporalAuditor(
        config=config,
    )

    return auditor.audit(
        dataframe,
    )


# ============================================================
# Convenience function: Birmingham
# ============================================================


def audit_birmingham_temporal(
    *,
    dataset_root: str = "../datasets/raw",
) -> TemporalAuditResult:
    """
    Load Birmingham through the existing ingestion pipeline
    and perform the temporal audit.

    No temporal transformation is performed.
    """

    from app.ml.data.ingestion import (
        ingest_birmingham_dataset,
    )

    ingestion_result = (
        ingest_birmingham_dataset(
            dataset_root=dataset_root,
        )
    )

    return audit_temporal_dataset(
        ingestion_result.dataframe,
    )


# ============================================================
# Public API
# ============================================================


__all__ = [
    # Constants
    "FACILITY_COLUMN",
    "TIMESTAMP_COLUMN",
    "OCCUPANCY_COLUMN",
    "OCCUPANCY_RATE_COLUMN",
    "CAPACITY_COLUMN",

    # Exceptions
    "TemporalAuditError",
    "TemporalAuditSchemaError",
    "TemporalAuditDataError",

    # Configuration
    "TemporalAuditConfig",

    # Statistics/results
    "FacilityTemporalStatistics",
    "TemporalAuditStatistics",
    "TemporalAuditResult",

    # Main auditor
    "TemporalAuditor",

    # Convenience functions
    "audit_temporal_dataset",
    "audit_birmingham_temporal",
]