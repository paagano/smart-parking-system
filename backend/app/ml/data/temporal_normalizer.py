"""
SmartPark AI - Temporal Normalization.

This module converts the canonical irregular parking-observation
dataset into a regular temporal representation suitable for
machine-learning dataset construction.

Pipeline position
-----------------

    Source
      |
      v
    Loader
      |
      v
    Validation
      |
      v
    Transformation
      |
      v
    Canonical Dataset
      |
      v
    Temporal Normalization
      |
      v
    ML Dataset Builder
      |
      +------------+
      |            |
      v            v
    XGBoost       LSTM


Design principles
-----------------

1. Use a configurable canonical modelling interval.
   SmartPark AI defaults to 30 minutes.

2. Align source observations to the nearest canonical slot.

3. Never blindly interpolate observations.

4. Never forward-fill or backward-fill observations.

5. Never manufacture parking occupancy values.

6. Process every facility independently.

7. Preserve source timestamps for provenance.

8. Explicitly represent missing slots.

9. Distinguish normal inactivity from unexpected gaps.

10. Explicitly identify sequence boundaries for LSTM.

11. Preserve sparse facilities for downstream eligibility
    assessment instead of deleting them here.

12. Keep temporal normalization independent of the data source.

13. Do not perform ML feature engineering in this module.

14. Do not create prediction targets in this module.

15. Do not perform train/validation/test splitting here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

import numpy as np
import pandas as pd


# ============================================================
# Canonical columns
# ============================================================

FACILITY_COLUMN = "source_facility_code"
TIMESTAMP_COLUMN = "observed_at"

TOTAL_SPACES_COLUMN = "total_spaces"
OCCUPIED_SPACES_COLUMN = "occupied_spaces"
AVAILABLE_SPACES_COLUMN = "available_spaces"

RAW_OCCUPANCY_RATE_COLUMN = "raw_occupancy_rate"
OCCUPANCY_RATE_COLUMN = "occupancy_rate"

SOURCE_COLUMN = "source"
QUALITY_FLAGS_COLUMN = "quality_flags"
QUALITY_STATUS_COLUMN = "quality_status"


# ============================================================
# Normalized columns
# ============================================================

NORMALIZED_TIMESTAMP_COLUMN = "normalized_at"

SOURCE_OBSERVED_AT_COLUMN = "source_observed_at"

OBSERVATION_PRESENT_COLUMN = "observation_present"

OBSERVATION_COUNT_COLUMN = "source_observation_count"

TIME_DISTANCE_MINUTES_COLUMN = (
    "source_time_distance_minutes"
)

ALIGNMENT_STATUS_COLUMN = "alignment_status"

GAP_STATUS_COLUMN = "gap_status"

GAP_SLOT_COUNT_COLUMN = "gap_slot_count"

SEQUENCE_BREAK_COLUMN = "sequence_break"

NORMALIZATION_METHOD_COLUMN = (
    "normalization_method"
)

IS_OPERATIONAL_GAP_COLUMN = "is_operational_gap"

IS_DATA_GAP_COLUMN = "is_data_gap"

IS_LONG_GAP_COLUMN = "is_long_gap"

IS_VERY_LONG_GAP_COLUMN = "is_very_long_gap"

IS_ELIGIBLE_FOR_SEQUENCE_COLUMN = (
    "is_eligible_for_sequence"
)


# ============================================================
# Enums
# ============================================================


class AlignmentStatus(str, Enum):
    """
    Describes how a source observation was mapped to the
    canonical temporal grid.
    """

    EXACT = "EXACT"

    ALIGNED = "ALIGNED"

    MISSING = "MISSING"


class GapStatus(str, Enum):
    """
    Describes the temporal state of a normalized slot.
    """

    START = "START"

    CONTINUOUS = "CONTINUOUS"

    SHORT_GAP = "SHORT_GAP"

    LONG_GAP = "LONG_GAP"

    VERY_LONG_GAP = "VERY_LONG_GAP"

    OPERATIONAL_GAP = "OPERATIONAL_GAP"

    MISSING = "MISSING"


class NormalizationMethod(str, Enum):
    """
    Describes how a normalized row was created.
    """

    SOURCE_OBSERVATION = "SOURCE_OBSERVATION"

    NEAREST_SOURCE_OBSERVATION = (
        "NEAREST_SOURCE_OBSERVATION"
    )

    MISSING_SLOT = "MISSING_SLOT"


# ============================================================
# Exceptions
# ============================================================


class TemporalNormalizationError(Exception):
    """Base temporal normalization exception."""


class TemporalNormalizationSchemaError(
    TemporalNormalizationError
):
    """Raised when required canonical columns are missing."""


class TemporalNormalizationDataError(
    TemporalNormalizationError
):
    """Raised when the input temporal data is invalid."""


class TemporalNormalizationConfigurationError(
    TemporalNormalizationError
):
    """Raised when configuration is invalid."""


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class TemporalNormalizationConfig:
    """
    Temporal normalization configuration.

    Default SmartPark AI policy:

        Target interval:
            30 minutes

        Alignment tolerance:
            15 minutes

        Long gap:
            > 60 minutes

        Very long gap:
            > 120 minutes

    Operational inactivity
    ----------------------

    The Birmingham dataset does not necessarily provide
    24-hour observations for every facility.

    Therefore we do NOT assume that every missing slot is
    a sensor/data failure.

    The operational inactivity thresholds define the
    expected reporting window using the observed daily
    reporting pattern of each facility.

    By default, operational-gap detection is enabled.
    """

    target_interval_minutes: int = 30

    alignment_tolerance_minutes: int = 15

    long_gap_threshold_minutes: int = 60

    very_long_gap_threshold_minutes: int = 120

    include_empty_slots: bool = True

    allow_multiple_source_observations_per_slot: bool = False

    preserve_source_columns: bool = True

    detect_operational_gaps: bool = True

    operational_window_quantile: float = 0.05

    minimum_observations_for_operational_profile: int = 20

    # Maximum gap that can still be treated as a normal
    # operational inactivity period.
    operational_gap_minimum_minutes: int = 120

    def __post_init__(self) -> None:

        if self.target_interval_minutes <= 0:
            raise TemporalNormalizationConfigurationError(
                "target_interval_minutes must be greater than zero."
            )

        if self.alignment_tolerance_minutes < 0:
            raise TemporalNormalizationConfigurationError(
                "alignment_tolerance_minutes cannot be negative."
            )

        if (
            self.alignment_tolerance_minutes
            > self.target_interval_minutes / 2
        ):
            raise TemporalNormalizationConfigurationError(
                "alignment_tolerance_minutes cannot exceed "
                "half of target_interval_minutes."
            )

        if (
            self.long_gap_threshold_minutes
            <= self.target_interval_minutes
        ):
            raise TemporalNormalizationConfigurationError(
                "long_gap_threshold_minutes must be greater "
                "than target_interval_minutes."
            )

        if (
            self.very_long_gap_threshold_minutes
            <= self.long_gap_threshold_minutes
        ):
            raise TemporalNormalizationConfigurationError(
                "very_long_gap_threshold_minutes must be greater "
                "than long_gap_threshold_minutes."
            )

        if not 0 <= (
            self.operational_window_quantile
        ) <= 1:
            raise TemporalNormalizationConfigurationError(
                "operational_window_quantile must be between "
                "0 and 1."
            )

        if (
            self.minimum_observations_for_operational_profile
            < 1
        ):
            raise TemporalNormalizationConfigurationError(
                "minimum_observations_for_operational_profile "
                "must be at least 1."
            )

        if (
            self.operational_gap_minimum_minutes
            < self.target_interval_minutes
        ):
            raise TemporalNormalizationConfigurationError(
                "operational_gap_minimum_minutes must be at "
                "least the target interval."
            )


# ============================================================
# Operational profile
# ============================================================


@dataclass(frozen=True, slots=True)
class OperationalProfile:
    """
    Estimated reporting window for one facility.

    This is deliberately conservative.

    It is used only to classify missing slots and is NOT
    used to manufacture occupancy values.
    """

    facility_code: str

    earliest_reporting_minute: int

    latest_reporting_minute: int

    observation_count: int

    enabled: bool

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )


# ============================================================
# Facility statistics
# ============================================================


@dataclass(frozen=True, slots=True)
class FacilityNormalizationStatistics:
    """
    Normalization statistics for one facility.
    """

    facility_code: str

    source_row_count: int

    normalized_row_count: int

    observed_slots: int

    missing_slots: int

    exact_alignments: int

    nearest_alignments: int

    source_observations_outside_tolerance: int

    duplicate_source_slots: int

    continuous_slots: int

    short_gap_slots: int

    long_gap_slots: int

    very_long_gap_slots: int

    operational_gap_slots: int

    data_gap_slots: int

    sequence_breaks: int

    first_normalized_at: pd.Timestamp | None

    last_normalized_at: pd.Timestamp | None

    operational_profile: OperationalProfile | None

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )


# ============================================================
# Overall statistics
# ============================================================


@dataclass(frozen=True, slots=True)
class TemporalNormalizationStatistics:
    """
    Overall temporal normalization statistics.
    """

    source_row_count: int

    normalized_row_count: int

    facility_count: int

    observed_slots: int

    missing_slots: int

    exact_alignments: int

    nearest_alignments: int

    source_observations_outside_tolerance: int

    duplicate_source_slots: int

    continuous_slots: int

    short_gap_slots: int

    long_gap_slots: int

    very_long_gap_slots: int

    operational_gap_slots: int

    data_gap_slots: int

    sequence_breaks: int

    coverage_start: pd.Timestamp | None

    coverage_end: pd.Timestamp | None

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True, slots=True)
class TemporalNormalizationResult:
    """
    Complete temporal normalization result.
    """

    dataframe: pd.DataFrame

    statistics: TemporalNormalizationStatistics

    facilities: tuple[
        FacilityNormalizationStatistics,
        ...
    ]

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    @property
    def row_count(self) -> int:
        return len(self.dataframe)

    @property
    def facility_count(self) -> int:
        return self.statistics.facility_count

    @property
    def missing_row_count(self) -> int:
        return self.statistics.missing_slots


# ============================================================
# Temporal Normalizer
# ============================================================


class TemporalNormalizer:
    """
    Normalize canonical parking observations onto a regular
    temporal grid.

    The default grid is 30 minutes.

    Important:

        This class never interpolates occupancy.

        This class never forward-fills occupancy.

        This class never backward-fills occupancy.

    Missing values therefore remain genuine missing values.
    """

    def __init__(
        self,
        config: TemporalNormalizationConfig | None = None,
    ) -> None:

        self._config = (
            config
            if config is not None
            else TemporalNormalizationConfig()
        )

    # ========================================================
    # Public API
    # ========================================================

    def normalize(
        self,
        dataframe: pd.DataFrame,
    ) -> TemporalNormalizationResult:
        """
        Normalize the canonical dataset.
        """

        self._validate_schema(
            dataframe
        )

        working = self._prepare_dataframe(
            dataframe
        )

        normalized_frames: list[
            pd.DataFrame
        ] = []

        facility_statistics: list[
            FacilityNormalizationStatistics
        ] = []

        for (
            facility_code,
            facility_dataframe,
        ) in working.groupby(
            FACILITY_COLUMN,
            sort=True,
        ):

            normalized, statistics = (
                self._normalize_facility(
                    facility_code=str(
                        facility_code
                    ),
                    dataframe=facility_dataframe,
                )
            )

            normalized_frames.append(
                normalized
            )

            facility_statistics.append(
                statistics
            )

        if normalized_frames:

            normalized_dataframe = (
                pd.concat(
                    normalized_frames,
                    ignore_index=True,
                )
            )

        else:

            normalized_dataframe = (
                self._empty_output_dataframe()
            )

        normalized_dataframe = (
            self._finalize_dataframe(
                normalized_dataframe
            )
        )

        statistics = (
            self._build_overall_statistics(
                source_dataframe=working,
                normalized_dataframe=(
                    normalized_dataframe
                ),
                facilities=facility_statistics,
            )
        )

        return TemporalNormalizationResult(
            dataframe=normalized_dataframe,
            statistics=statistics,
            facilities=tuple(
                facility_statistics
            ),
            metadata={
                "target_interval_minutes": (
                    self._config
                    .target_interval_minutes
                ),
                "alignment_tolerance_minutes": (
                    self._config
                    .alignment_tolerance_minutes
                ),
                "interpolation_used": False,
                "forward_fill_used": False,
                "backward_fill_used": False,
                "operational_gap_detection": (
                    self._config
                    .detect_operational_gaps
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

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise TemporalNormalizationDataError(
                "Temporal normalization requires a "
                "pandas DataFrame."
            )

        if dataframe.empty:
            raise TemporalNormalizationDataError(
                "Cannot normalize an empty dataset."
            )

        required = {
            FACILITY_COLUMN,
            TIMESTAMP_COLUMN,
            TOTAL_SPACES_COLUMN,
            OCCUPIED_SPACES_COLUMN,
            AVAILABLE_SPACES_COLUMN,
            OCCUPANCY_RATE_COLUMN,
        }

        missing = (
            required
            - set(dataframe.columns)
        )

        if missing:
            raise TemporalNormalizationSchemaError(
                "Canonical dataset is missing required "
                "columns: "
                + ", ".join(
                    sorted(missing)
                )
            )

    # ========================================================
    # Data preparation
    # ========================================================

    def _prepare_dataframe(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:

        working = dataframe.copy(
            deep=True
        )

        working[
            TIMESTAMP_COLUMN
        ] = pd.to_datetime(
            working[
                TIMESTAMP_COLUMN
            ],
            errors="coerce",
        )

        invalid_timestamps = int(
            working[
                TIMESTAMP_COLUMN
            ].isna().sum()
        )

        if invalid_timestamps:
            raise TemporalNormalizationDataError(
                f"Dataset contains "
                f"{invalid_timestamps} invalid timestamps."
            )

        working[
            FACILITY_COLUMN
        ] = (
            working[
                FACILITY_COLUMN
            ]
            .astype("string")
            .str.strip()
        )

        missing_facilities = int(
            working[
                FACILITY_COLUMN
            ].isna().sum()
        )

        if missing_facilities:
            raise TemporalNormalizationDataError(
                f"Dataset contains "
                f"{missing_facilities} missing facility codes."
            )

        empty_facilities = int(
            (
                working[
                    FACILITY_COLUMN
                ]
                .str.len()
                .eq(0)
            ).sum()
        )

        if empty_facilities:
            raise TemporalNormalizationDataError(
                f"Dataset contains "
                f"{empty_facilities} empty facility codes."
            )

        working = working.sort_values(
            [
                FACILITY_COLUMN,
                TIMESTAMP_COLUMN,
            ],
            kind="stable",
        ).reset_index(
            drop=True
        )

        return working

    # ========================================================
    # Facility normalization
    # ========================================================

    def _normalize_facility(
        self,
        *,
        facility_code: str,
        dataframe: pd.DataFrame,
    ) -> tuple[
        pd.DataFrame,
        FacilityNormalizationStatistics,
    ]:

        source = dataframe.copy(
            deep=True
        )

        source = source.sort_values(
            TIMESTAMP_COLUMN,
            kind="stable",
        ).reset_index(
            drop=True
        )

        operational_profile = (
            self._build_operational_profile(
                facility_code=facility_code,
                source=source,
            )
        )

        # ----------------------------------------------------
        # Assign nearest canonical slot.
        # ----------------------------------------------------

        source[
            NORMALIZED_TIMESTAMP_COLUMN
        ] = self._round_to_grid(
            source[
                TIMESTAMP_COLUMN
            ]
        )

        source[
            TIME_DISTANCE_MINUTES_COLUMN
        ] = (
            (
                source[
                    TIMESTAMP_COLUMN
                ]
                - source[
                    NORMALIZED_TIMESTAMP_COLUMN
                ]
            )
            .abs()
            .dt.total_seconds()
            .div(60.0)
        )

        source[
            ALIGNMENT_STATUS_COLUMN
        ] = np.where(
            source[
                TIME_DISTANCE_MINUTES_COLUMN
            ].eq(0),
            AlignmentStatus.EXACT.value,
            np.where(
                source[
                    TIME_DISTANCE_MINUTES_COLUMN
                ]
                <= self._config
                .alignment_tolerance_minutes,
                AlignmentStatus.ALIGNED.value,
                AlignmentStatus.MISSING.value,
            ),
        )

        outside_tolerance = int(
            (
                source[
                    ALIGNMENT_STATUS_COLUMN
                ]
                == AlignmentStatus.MISSING.value
            ).sum()
        )

        eligible = source.loc[
            source[
                ALIGNMENT_STATUS_COLUMN
            ]
            != AlignmentStatus.MISSING.value
        ].copy()

        # ----------------------------------------------------
        # Collision handling.
        # ----------------------------------------------------

        duplicate_source_slots = int(
            eligible.duplicated(
                subset=[
                    NORMALIZED_TIMESTAMP_COLUMN
                ],
                keep=False,
            ).sum()
        )

        if not self._config.allow_multiple_source_observations_per_slot:

            eligible = (
                eligible.sort_values(
                    [
                        NORMALIZED_TIMESTAMP_COLUMN,
                        TIME_DISTANCE_MINUTES_COLUMN,
                        TIMESTAMP_COLUMN,
                    ],
                    kind="stable",
                )
                .drop_duplicates(
                    subset=[
                        NORMALIZED_TIMESTAMP_COLUMN
                    ],
                    keep="first",
                )
                .reset_index(
                    drop=True
                )
            )

        # ----------------------------------------------------
        # Build canonical grid.
        # ----------------------------------------------------

        if eligible.empty:

            normalized = (
                self._build_empty_facility_grid(
                    source
                )
            )

        else:

            normalized = (
                self._build_facility_grid(
                    source=source,
                    eligible=eligible,
                )
            )

        # ----------------------------------------------------
        # Attach operational profile.
        # ----------------------------------------------------

        normalized[
            "operational_profile_enabled"
        ] = (
            operational_profile.enabled
            if operational_profile
            else False
        )

        # ----------------------------------------------------
        # Classify temporal gaps.
        # ----------------------------------------------------

        normalized = (
            self._assign_gap_status(
                normalized
            )
        )

        normalized = (
            self._classify_operational_gaps(
                normalized,
                operational_profile,
            )
        )

        # ----------------------------------------------------
        # Sequence eligibility/boundaries.
        # ----------------------------------------------------

        normalized = (
            self._assign_sequence_boundaries(
                normalized
            )
        )

        # ----------------------------------------------------
        # Statistics.
        # ----------------------------------------------------

        statistics = (
            self._build_facility_statistics(
                facility_code=facility_code,
                source=source,
                normalized=normalized,
                outside_tolerance=(
                    outside_tolerance
                ),
                duplicate_source_slots=(
                    duplicate_source_slots
                ),
                operational_profile=(
                    operational_profile
                ),
            )
        )

        return normalized, statistics

    # ========================================================
    # Grid rounding
    # ========================================================

    def _round_to_grid(
        self,
        timestamps: pd.Series,
    ) -> pd.Series:

        frequency = (
            f"{self._config.target_interval_minutes}min"
        )

        return timestamps.dt.round(
            frequency
        )

    # ========================================================
    # Facility grid
    # ========================================================

    def _build_facility_grid(
        self,
        *,
        source: pd.DataFrame,
        eligible: pd.DataFrame,
    ) -> pd.DataFrame:

        start = eligible[
            NORMALIZED_TIMESTAMP_COLUMN
        ].min()

        end = eligible[
            NORMALIZED_TIMESTAMP_COLUMN
        ].max()

        frequency = (
            f"{self._config.target_interval_minutes}min"
        )

        if self._config.include_empty_slots:

            grid = pd.DataFrame(
                {
                    NORMALIZED_TIMESTAMP_COLUMN: (
                        pd.date_range(
                            start=start,
                            end=end,
                            freq=frequency,
                        )
                    )
                }
            )

        else:

            grid = pd.DataFrame(
                {
                    NORMALIZED_TIMESTAMP_COLUMN: (
                        eligible[
                            NORMALIZED_TIMESTAMP_COLUMN
                        ]
                        .sort_values()
                        .unique()
                    )
                }
            )

        source_for_merge = (
            eligible.copy()
        )

        source_for_merge[
            SOURCE_OBSERVED_AT_COLUMN
        ] = source_for_merge[
            TIMESTAMP_COLUMN
        ]

        columns = [
            NORMALIZED_TIMESTAMP_COLUMN,
            SOURCE_OBSERVED_AT_COLUMN,
            TOTAL_SPACES_COLUMN,
            OCCUPIED_SPACES_COLUMN,
            AVAILABLE_SPACES_COLUMN,
            RAW_OCCUPANCY_RATE_COLUMN,
            OCCUPANCY_RATE_COLUMN,
            SOURCE_COLUMN,
            QUALITY_FLAGS_COLUMN,
            QUALITY_STATUS_COLUMN,
            TIME_DISTANCE_MINUTES_COLUMN,
            ALIGNMENT_STATUS_COLUMN,
        ]

        available_columns = [
            column
            for column in columns
            if column in source_for_merge.columns
        ]

        source_for_merge = (
            source_for_merge[
                available_columns
            ]
        )

        normalized = grid.merge(
            source_for_merge,
            on=NORMALIZED_TIMESTAMP_COLUMN,
            how="left",
            sort=True,
        )

        normalized[
            FACILITY_COLUMN
        ] = str(
            source[
                FACILITY_COLUMN
            ].iloc[0]
        )

        normalized[
            OBSERVATION_PRESENT_COLUMN
        ] = normalized[
            OCCUPIED_SPACES_COLUMN
        ].notna()

        normalized[
            OBSERVATION_COUNT_COLUMN
        ] = np.where(
            normalized[
                OBSERVATION_PRESENT_COLUMN
            ],
            1,
            0,
        )

        normalized[
            ALIGNMENT_STATUS_COLUMN
        ] = normalized[
            ALIGNMENT_STATUS_COLUMN
        ].fillna(
            AlignmentStatus.MISSING.value
        )

        normalized[
            NORMALIZATION_METHOD_COLUMN
        ] = np.where(
            normalized[
                ALIGNMENT_STATUS_COLUMN
            ].eq(
                AlignmentStatus.EXACT.value
            ),
            NormalizationMethod
            .SOURCE_OBSERVATION
            .value,
            np.where(
                normalized[
                    ALIGNMENT_STATUS_COLUMN
                ].eq(
                    AlignmentStatus.ALIGNED.value
                ),
                NormalizationMethod
                .NEAREST_SOURCE_OBSERVATION
                .value,
                NormalizationMethod
                .MISSING_SLOT
                .value,
            ),
        )

        return normalized

    # ========================================================
    # Empty facility grid
    # ========================================================

    def _build_empty_facility_grid(
        self,
        source: pd.DataFrame,
    ) -> pd.DataFrame:

        start = source[
            TIMESTAMP_COLUMN
        ].min()

        end = source[
            TIMESTAMP_COLUMN
        ].max()

        frequency = (
            f"{self._config.target_interval_minutes}min"
        )

        grid = pd.DataFrame(
            {
                NORMALIZED_TIMESTAMP_COLUMN: (
                    pd.date_range(
                        start=start.floor(
                            frequency
                        ),
                        end=end.ceil(
                            frequency
                        ),
                        freq=frequency,
                    )
                )
            }
        )

        grid[
            FACILITY_COLUMN
        ] = str(
            source[
                FACILITY_COLUMN
            ].iloc[0]
        )

        for column in [
            SOURCE_OBSERVED_AT_COLUMN,
            TOTAL_SPACES_COLUMN,
            OCCUPIED_SPACES_COLUMN,
            AVAILABLE_SPACES_COLUMN,
            RAW_OCCUPANCY_RATE_COLUMN,
            OCCUPANCY_RATE_COLUMN,
            SOURCE_COLUMN,
            QUALITY_FLAGS_COLUMN,
            QUALITY_STATUS_COLUMN,
            TIME_DISTANCE_MINUTES_COLUMN,
        ]:

            grid[column] = np.nan

        grid[
            OBSERVATION_PRESENT_COLUMN
        ] = False

        grid[
            OBSERVATION_COUNT_COLUMN
        ] = 0

        grid[
            ALIGNMENT_STATUS_COLUMN
        ] = AlignmentStatus.MISSING.value

        grid[
            NORMALIZATION_METHOD_COLUMN
        ] = (
            NormalizationMethod
            .MISSING_SLOT
            .value
        )

        return grid

    # ========================================================
    # Operational profile
    # ========================================================

    def _build_operational_profile(
        self,
        *,
        facility_code: str,
        source: pd.DataFrame,
    ) -> OperationalProfile | None:
        """
        Build a conservative daily reporting profile.

        We use the empirical distribution of observed times.

        The profile does not fill or alter data.

        It only helps classify missing periods.
        """

        observation_count = len(
            source
        )

        if (
            not self._config
            .detect_operational_gaps
        ):
            return OperationalProfile(
                facility_code=facility_code,
                earliest_reporting_minute=0,
                latest_reporting_minute=(
                    23 * 60 + 59
                ),
                observation_count=(
                    observation_count
                ),
                enabled=False,
                metadata={
                    "reason": (
                        "Operational gap detection disabled."
                    )
                },
            )

        if (
            observation_count
            < self._config
            .minimum_observations_for_operational_profile
        ):
            return OperationalProfile(
                facility_code=facility_code,
                earliest_reporting_minute=0,
                latest_reporting_minute=(
                    23 * 60 + 59
                ),
                observation_count=(
                    observation_count
                ),
                enabled=False,
                metadata={
                    "reason": (
                        "Insufficient observations to establish "
                        "a reliable operational profile."
                    )
                },
            )

        timestamps = (
            source[
                TIMESTAMP_COLUMN
            ]
        )

        minutes_since_midnight = (
            timestamps.dt.hour * 60
            + timestamps.dt.minute
            + (
                timestamps.dt.second
                / 60.0
            )
        )

        quantile = (
            self._config
            .operational_window_quantile
        )

        lower = int(
            np.floor(
                minutes_since_midnight.quantile(
                    quantile
                )
            )
        )

        upper = int(
            np.ceil(
                minutes_since_midnight.quantile(
                    1 - quantile
                )
            )
        )

        return OperationalProfile(
            facility_code=facility_code,
            earliest_reporting_minute=lower,
            latest_reporting_minute=upper,
            observation_count=observation_count,
            enabled=True,
            metadata={
                "quantile": quantile,
                "earliest_time": (
                    self._minutes_to_hhmm(
                        lower
                    )
                ),
                "latest_time": (
                    self._minutes_to_hhmm(
                        upper
                    )
                ),
            },
        )

    # ========================================================
    # Gap classification
    # ========================================================

    def _assign_gap_status(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:

        result = dataframe.copy(
            deep=True
        )

        timestamps = result[
            NORMALIZED_TIMESTAMP_COLUMN
        ]

        previous_timestamp = (
            timestamps.shift(1)
        )

        previous_observed = (
            result[
                OBSERVATION_PRESENT_COLUMN
            ]
            .shift(1)
            .fillna(False)
        )

        current_observed = (
            result[
                OBSERVATION_PRESENT_COLUMN
            ]
        )

        delta_minutes = (
            (
                timestamps
                - previous_timestamp
            )
            .dt.total_seconds()
            .div(60.0)
        )

        expected_interval = (
            self._config
            .target_interval_minutes
        )

        gap_status = pd.Series(
            GapStatus.MISSING.value,
            index=result.index,
            dtype="string",
        )

        first_row = (
            previous_timestamp.isna()
        )

        gap_status.loc[
            first_row
            & current_observed
        ] = GapStatus.START.value

        continuous = (
            ~first_row
            & current_observed
            & previous_observed
            & delta_minutes.eq(
                expected_interval
            )
        )

        gap_status.loc[
            continuous
        ] = GapStatus.CONTINUOUS.value

        missing = (
            ~current_observed
        )

        gap_status.loc[
            missing
        ] = GapStatus.MISSING.value

        missing_after_observation = (
            missing
            & previous_observed
        )

        short_gap = (
            missing_after_observation
            & (
                delta_minutes
                <= self._config
                .long_gap_threshold_minutes
            )
        )

        long_gap = (
            missing_after_observation
            & (
                delta_minutes
                > self._config
                .long_gap_threshold_minutes
            )
            & (
                delta_minutes
                <= self._config
                .very_long_gap_threshold_minutes
            )
        )

        very_long_gap = (
            missing_after_observation
            & (
                delta_minutes
                > self._config
                .very_long_gap_threshold_minutes
            )
        )

        gap_status.loc[
            short_gap
        ] = GapStatus.SHORT_GAP.value

        gap_status.loc[
            long_gap
        ] = GapStatus.LONG_GAP.value

        gap_status.loc[
            very_long_gap
        ] = GapStatus.VERY_LONG_GAP.value

        result[
            GAP_STATUS_COLUMN
        ] = gap_status

        result[
            GAP_SLOT_COUNT_COLUMN
        ] = np.where(
            missing_after_observation,
            np.maximum(
                (
                    delta_minutes
                    / expected_interval
                )
                .round()
                .fillna(0)
                .astype(int)
                - 1,
                0,
            ),
            0,
        )

        return result

    # ========================================================
    # Operational gap classification
    # ========================================================

    def _classify_operational_gaps(
        self,
        dataframe: pd.DataFrame,
        profile: OperationalProfile | None,
    ) -> pd.DataFrame:
        """
        Distinguish expected operational inactivity from
        potential data gaps.

        Important limitation:

        A temporal dataset alone cannot prove that a facility
        was physically closed.

        Therefore this is a conservative classification based
        on the facility's observed reporting window.

        It is metadata for downstream ML decisions, not truth
        about facility operations.
        """

        result = dataframe.copy(
            deep=True
        )

        result[
            IS_OPERATIONAL_GAP_COLUMN
        ] = False

        result[
            IS_DATA_GAP_COLUMN
        ] = False

        result[
            IS_LONG_GAP_COLUMN
        ] = (
            result[
                GAP_STATUS_COLUMN
            ].isin(
                [
                    GapStatus.LONG_GAP.value,
                    GapStatus.VERY_LONG_GAP.value,
                ]
            )
        )

        result[
            IS_VERY_LONG_GAP_COLUMN
        ] = (
            result[
                GAP_STATUS_COLUMN
            ].eq(
                GapStatus.VERY_LONG_GAP.value
            )
        )

        if (
            profile is None
            or not profile.enabled
        ):

            result[
                IS_DATA_GAP_COLUMN
            ] = (
                ~result[
                    OBSERVATION_PRESENT_COLUMN
                ]
                & ~result[
                    GAP_STATUS_COLUMN
                ].eq(
                    GapStatus.START.value
                )
            )

            return result

        timestamps = (
            result[
                NORMALIZED_TIMESTAMP_COLUMN
            ]
        )

        minutes_since_midnight = (
            timestamps.dt.hour * 60
            + timestamps.dt.minute
        )

        outside_operational_window = (
            (
                minutes_since_midnight
                < profile
                .earliest_reporting_minute
            )
            |
            (
                minutes_since_midnight
                > profile
                .latest_reporting_minute
            )
        )

        missing = ~result[
            OBSERVATION_PRESENT_COLUMN
        ]

        operational_gap = (
            missing
            & outside_operational_window
        )

        result[
            IS_OPERATIONAL_GAP_COLUMN
        ] = operational_gap

        result[
            IS_DATA_GAP_COLUMN
        ] = (
            missing
            & ~operational_gap
        )

        # ----------------------------------------------------
        # Change the displayed status for clearly operational
        # missing slots.
        # ----------------------------------------------------

        result.loc[
            operational_gap,
            GAP_STATUS_COLUMN,
        ] = GapStatus.OPERATIONAL_GAP.value

        return result

    # ========================================================
    # Sequence boundaries
    # ========================================================

    def _assign_sequence_boundaries(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Mark boundaries where an LSTM sequence must not cross.

        A sequence can only use observed values.

        Long gaps, very long gaps and operational gaps are
        treated as boundaries.

        The first observation is also a boundary.
        """

        result = dataframe.copy(
            deep=True
        )

        result[
            SEQUENCE_BREAK_COLUMN
        ] = False

        result[
            IS_ELIGIBLE_FOR_SEQUENCE_COLUMN
        ] = result[
            OBSERVATION_PRESENT_COLUMN
        ]

        # ----------------------------------------------------
        # First row.
        # ----------------------------------------------------

        if not result.empty:

            result.loc[
                result.index[0],
                SEQUENCE_BREAK_COLUMN,
            ] = True

        # ----------------------------------------------------
        # Current row begins a new sequence after any gap.
        # ----------------------------------------------------

        current_status = result[
            GAP_STATUS_COLUMN
        ]

        previous_status = (
            current_status.shift(1)
        )

        previous_breaking = (
            previous_status.isin(
                [
                    GapStatus.LONG_GAP.value,
                    GapStatus.VERY_LONG_GAP.value,
                    GapStatus.OPERATIONAL_GAP.value,
                ]
            )
        )

        current_observed = (
            result[
                OBSERVATION_PRESENT_COLUMN
            ]
        )

        starts_after_gap = (
            current_observed
            & previous_breaking
        )

        result.loc[
            starts_after_gap,
            SEQUENCE_BREAK_COLUMN,
        ] = True

        # ----------------------------------------------------
        # Current missing slot.
        #
        # It cannot itself be part of an occupancy sequence.
        # ----------------------------------------------------

        result.loc[
            ~current_observed,
            IS_ELIGIBLE_FOR_SEQUENCE_COLUMN,
        ] = False

        # ----------------------------------------------------
        # Explicit long-gap rows.
        # ----------------------------------------------------

        result.loc[
            current_status.isin(
                [
                    GapStatus.LONG_GAP.value,
                    GapStatus.VERY_LONG_GAP.value,
                    GapStatus.OPERATIONAL_GAP.value,
                ]
            ),
            SEQUENCE_BREAK_COLUMN,
        ] = True

        return result

    # ========================================================
    # Facility statistics
    # ========================================================

    def _build_facility_statistics(
        self,
        *,
        facility_code: str,
        source: pd.DataFrame,
        normalized: pd.DataFrame,
        outside_tolerance: int,
        duplicate_source_slots: int,
        operational_profile: OperationalProfile | None,
    ) -> FacilityNormalizationStatistics:

        observed = normalized[
            OBSERVATION_PRESENT_COLUMN
        ]

        gap_status = normalized[
            GAP_STATUS_COLUMN
        ]

        return FacilityNormalizationStatistics(
            facility_code=facility_code,
            source_row_count=len(
                source
            ),
            normalized_row_count=len(
                normalized
            ),
            observed_slots=int(
                observed.sum()
            ),
            missing_slots=int(
                (~observed).sum()
            ),
            exact_alignments=int(
                (
                    normalized[
                        ALIGNMENT_STATUS_COLUMN
                    ]
                    == AlignmentStatus.EXACT.value
                ).sum()
            ),
            nearest_alignments=int(
                (
                    normalized[
                        ALIGNMENT_STATUS_COLUMN
                    ]
                    == AlignmentStatus.ALIGNED.value
                ).sum()
            ),
            source_observations_outside_tolerance=(
                outside_tolerance
            ),
            duplicate_source_slots=(
                duplicate_source_slots
            ),
            continuous_slots=int(
                (
                    gap_status
                    == GapStatus.CONTINUOUS.value
                ).sum()
            ),
            short_gap_slots=int(
                (
                    gap_status
                    == GapStatus.SHORT_GAP.value
                ).sum()
            ),
            long_gap_slots=int(
                (
                    gap_status
                    == GapStatus.LONG_GAP.value
                ).sum()
            ),
            very_long_gap_slots=int(
                (
                    gap_status
                    == GapStatus.VERY_LONG_GAP.value
                ).sum()
            ),
            operational_gap_slots=int(
                (
                    gap_status
                    == GapStatus.OPERATIONAL_GAP.value
                ).sum()
            ),
            data_gap_slots=int(
                normalized[
                    IS_DATA_GAP_COLUMN
                ].sum()
            ),
            sequence_breaks=int(
                normalized[
                    SEQUENCE_BREAK_COLUMN
                ].sum()
            ),
            first_normalized_at=(
                normalized[
                    NORMALIZED_TIMESTAMP_COLUMN
                ].min()
                if not normalized.empty
                else None
            ),
            last_normalized_at=(
                normalized[
                    NORMALIZED_TIMESTAMP_COLUMN
                ].max()
                if not normalized.empty
                else None
            ),
            operational_profile=(
                operational_profile
            ),
            metadata={
                "target_interval_minutes": (
                    self._config
                    .target_interval_minutes
                ),
            },
        )

    # ========================================================
    # Overall statistics
    # ========================================================

    def _build_overall_statistics(
        self,
        *,
        source_dataframe: pd.DataFrame,
        normalized_dataframe: pd.DataFrame,
        facilities: list[
            FacilityNormalizationStatistics
        ],
    ) -> TemporalNormalizationStatistics:

        observed = normalized_dataframe[
            OBSERVATION_PRESENT_COLUMN
        ]

        return TemporalNormalizationStatistics(
            source_row_count=len(
                source_dataframe
            ),
            normalized_row_count=len(
                normalized_dataframe
            ),
            facility_count=len(
                facilities
            ),
            observed_slots=int(
                observed.sum()
            ),
            missing_slots=int(
                (~observed).sum()
            ),
            exact_alignments=int(
                (
                    normalized_dataframe[
                        ALIGNMENT_STATUS_COLUMN
                    ]
                    == AlignmentStatus.EXACT.value
                ).sum()
            ),
            nearest_alignments=int(
                (
                    normalized_dataframe[
                        ALIGNMENT_STATUS_COLUMN
                    ]
                    == AlignmentStatus.ALIGNED.value
                ).sum()
            ),
            source_observations_outside_tolerance=int(
                sum(
                    facility
                    .source_observations_outside_tolerance
                    for facility in facilities
                )
            ),
            duplicate_source_slots=int(
                sum(
                    facility
                    .duplicate_source_slots
                    for facility in facilities
                )
            ),
            continuous_slots=int(
                (
                    normalized_dataframe[
                        GAP_STATUS_COLUMN
                    ]
                    == GapStatus.CONTINUOUS.value
                ).sum()
            ),
            short_gap_slots=int(
                (
                    normalized_dataframe[
                        GAP_STATUS_COLUMN
                    ]
                    == GapStatus.SHORT_GAP.value
                ).sum()
            ),
            long_gap_slots=int(
                (
                    normalized_dataframe[
                        GAP_STATUS_COLUMN
                    ]
                    == GapStatus.LONG_GAP.value
                ).sum()
            ),
            very_long_gap_slots=int(
                (
                    normalized_dataframe[
                        GAP_STATUS_COLUMN
                    ]
                    == GapStatus.VERY_LONG_GAP.value
                ).sum()
            ),
            operational_gap_slots=int(
                (
                    normalized_dataframe[
                        GAP_STATUS_COLUMN
                    ]
                    == GapStatus.OPERATIONAL_GAP.value
                ).sum()
            ),
            data_gap_slots=int(
                normalized_dataframe[
                    IS_DATA_GAP_COLUMN
                ].sum()
            ),
            sequence_breaks=int(
                normalized_dataframe[
                    SEQUENCE_BREAK_COLUMN
                ].sum()
            ),
            coverage_start=(
                normalized_dataframe[
                    NORMALIZED_TIMESTAMP_COLUMN
                ].min()
            ),
            coverage_end=(
                normalized_dataframe[
                    NORMALIZED_TIMESTAMP_COLUMN
                ].max()
            ),
            metadata={
                "interpolation_used": False,
                "forward_fill_used": False,
                "backward_fill_used": False,
                "operational_gap_detection": (
                    self._config
                    .detect_operational_gaps
                ),
            },
        )

    # ========================================================
    # Finalize
    # ========================================================

    def _finalize_dataframe(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:

        if dataframe.empty:
            return self._empty_output_dataframe()

        result = dataframe.copy(
            deep=True
        )

        result = result.sort_values(
            [
                FACILITY_COLUMN,
                NORMALIZED_TIMESTAMP_COLUMN,
            ],
            kind="stable",
        ).reset_index(
            drop=True
        )

        # ----------------------------------------------------
        # Boolean columns.
        # ----------------------------------------------------

        boolean_columns = [
            OBSERVATION_PRESENT_COLUMN,
            SEQUENCE_BREAK_COLUMN,
            IS_OPERATIONAL_GAP_COLUMN,
            IS_DATA_GAP_COLUMN,
            IS_LONG_GAP_COLUMN,
            IS_VERY_LONG_GAP_COLUMN,
            IS_ELIGIBLE_FOR_SEQUENCE_COLUMN,
            "operational_profile_enabled",
        ]

        for column in boolean_columns:

            if column in result.columns:

                result[column] = (
                    result[column]
                    .fillna(False)
                    .astype(bool)
                )

        # ----------------------------------------------------
        # Integer fields.
        # ----------------------------------------------------

        for column in [
            OBSERVATION_COUNT_COLUMN,
            GAP_SLOT_COUNT_COLUMN,
        ]:

            if column in result.columns:

                result[column] = (
                    pd.to_numeric(
                        result[column],
                        errors="coerce",
                    )
                    .fillna(0)
                    .astype("int64")
                )

        # ----------------------------------------------------
        # Occupancy/capacity values.
        # ----------------------------------------------------

        for column in [
            TOTAL_SPACES_COLUMN,
            OCCUPIED_SPACES_COLUMN,
            AVAILABLE_SPACES_COLUMN,
        ]:

            if column in result.columns:

                result[column] = (
                    pd.to_numeric(
                        result[column],
                        errors="coerce",
                    )
                    .astype("Int64")
                )

        # ----------------------------------------------------
        # Status fields.
        # ----------------------------------------------------

        for column in [
            ALIGNMENT_STATUS_COLUMN,
            GAP_STATUS_COLUMN,
            NORMALIZATION_METHOD_COLUMN,
        ]:

            if column in result.columns:

                result[column] = (
                    result[column]
                    .astype("string")
                )

        # ----------------------------------------------------
        # Final column ordering.
        # ----------------------------------------------------

        preferred_order = [
            FACILITY_COLUMN,
            NORMALIZED_TIMESTAMP_COLUMN,
            SOURCE_OBSERVED_AT_COLUMN,
            TOTAL_SPACES_COLUMN,
            OCCUPIED_SPACES_COLUMN,
            AVAILABLE_SPACES_COLUMN,
            RAW_OCCUPANCY_RATE_COLUMN,
            OCCUPANCY_RATE_COLUMN,
            OBSERVATION_PRESENT_COLUMN,
            OBSERVATION_COUNT_COLUMN,
            TIME_DISTANCE_MINUTES_COLUMN,
            ALIGNMENT_STATUS_COLUMN,
            GAP_STATUS_COLUMN,
            GAP_SLOT_COUNT_COLUMN,
            IS_OPERATIONAL_GAP_COLUMN,
            IS_DATA_GAP_COLUMN,
            IS_LONG_GAP_COLUMN,
            IS_VERY_LONG_GAP_COLUMN,
            SEQUENCE_BREAK_COLUMN,
            IS_ELIGIBLE_FOR_SEQUENCE_COLUMN,
            NORMALIZATION_METHOD_COLUMN,
            "operational_profile_enabled",
            SOURCE_COLUMN,
            QUALITY_FLAGS_COLUMN,
            QUALITY_STATUS_COLUMN,
        ]

        ordered = [
            column
            for column in preferred_order
            if column in result.columns
        ]

        remaining = [
            column
            for column in result.columns
            if column not in ordered
        ]

        return result[
            ordered + remaining
        ]

    # ========================================================
    # Empty output
    # ========================================================

    @staticmethod
    def _empty_output_dataframe() -> pd.DataFrame:

        return pd.DataFrame(
            columns=[
                FACILITY_COLUMN,
                NORMALIZED_TIMESTAMP_COLUMN,
                SOURCE_OBSERVED_AT_COLUMN,
                TOTAL_SPACES_COLUMN,
                OCCUPIED_SPACES_COLUMN,
                AVAILABLE_SPACES_COLUMN,
                RAW_OCCUPANCY_RATE_COLUMN,
                OCCUPANCY_RATE_COLUMN,
                OBSERVATION_PRESENT_COLUMN,
                OBSERVATION_COUNT_COLUMN,
                TIME_DISTANCE_MINUTES_COLUMN,
                ALIGNMENT_STATUS_COLUMN,
                GAP_STATUS_COLUMN,
                GAP_SLOT_COUNT_COLUMN,
                IS_OPERATIONAL_GAP_COLUMN,
                IS_DATA_GAP_COLUMN,
                IS_LONG_GAP_COLUMN,
                IS_VERY_LONG_GAP_COLUMN,
                SEQUENCE_BREAK_COLUMN,
                IS_ELIGIBLE_FOR_SEQUENCE_COLUMN,
                NORMALIZATION_METHOD_COLUMN,
                "operational_profile_enabled",
                SOURCE_COLUMN,
                QUALITY_FLAGS_COLUMN,
                QUALITY_STATUS_COLUMN,
            ]
        )

    # ========================================================
    # Utilities
    # ========================================================

    @staticmethod
    def _minutes_to_hhmm(
        minutes: int,
    ) -> str:

        minutes = max(
            0,
            min(
                minutes,
                23 * 60 + 59,
            ),
        )

        hour = minutes // 60
        minute = minutes % 60

        return f"{hour:02d}:{minute:02d}"


# ============================================================
# Convenience API
# ============================================================


def normalize_temporal_dataset(
    dataframe: pd.DataFrame,
    *,
    target_interval_minutes: int = 30,
    alignment_tolerance_minutes: int = 15,
    long_gap_threshold_minutes: int = 60,
    very_long_gap_threshold_minutes: int = 120,
    include_empty_slots: bool = True,
    detect_operational_gaps: bool = True,
) -> TemporalNormalizationResult:
    """
    Normalize a canonical dataset onto the SmartPark AI
    temporal modelling grid.
    """

    config = TemporalNormalizationConfig(
        target_interval_minutes=(
            target_interval_minutes
        ),
        alignment_tolerance_minutes=(
            alignment_tolerance_minutes
        ),
        long_gap_threshold_minutes=(
            long_gap_threshold_minutes
        ),
        very_long_gap_threshold_minutes=(
            very_long_gap_threshold_minutes
        ),
        include_empty_slots=(
            include_empty_slots
        ),
        detect_operational_gaps=(
            detect_operational_gaps
        ),
    )

    normalizer = TemporalNormalizer(
        config=config
    )

    return normalizer.normalize(
        dataframe
    )


# ============================================================
# Birmingham convenience API
# ============================================================


def normalize_birmingham_temporal(
    *,
    dataset_root: str = "../datasets/raw",
) -> TemporalNormalizationResult:
    """
    Convenience pipeline:

        Birmingham source
            ↓
        ingestion
            ↓
        canonical dataset
            ↓
        temporal normalization
    """

    from app.ml.data.ingestion import (
        ingest_birmingham_dataset,
    )

    ingestion = (
        ingest_birmingham_dataset(
            dataset_root=dataset_root,
        )
    )

    return normalize_temporal_dataset(
        ingestion.dataframe
    )


# ============================================================
# Public API
# ============================================================

__all__ = [
    # Canonical columns
    "FACILITY_COLUMN",
    "TIMESTAMP_COLUMN",
    "TOTAL_SPACES_COLUMN",
    "OCCUPIED_SPACES_COLUMN",
    "AVAILABLE_SPACES_COLUMN",
    "RAW_OCCUPANCY_RATE_COLUMN",
    "OCCUPANCY_RATE_COLUMN",
    "SOURCE_COLUMN",
    "QUALITY_FLAGS_COLUMN",
    "QUALITY_STATUS_COLUMN",

    # Normalized columns
    "NORMALIZED_TIMESTAMP_COLUMN",
    "SOURCE_OBSERVED_AT_COLUMN",
    "OBSERVATION_PRESENT_COLUMN",
    "OBSERVATION_COUNT_COLUMN",
    "TIME_DISTANCE_MINUTES_COLUMN",
    "ALIGNMENT_STATUS_COLUMN",
    "GAP_STATUS_COLUMN",
    "GAP_SLOT_COUNT_COLUMN",
    "SEQUENCE_BREAK_COLUMN",
    "NORMALIZATION_METHOD_COLUMN",
    "IS_OPERATIONAL_GAP_COLUMN",
    "IS_DATA_GAP_COLUMN",
    "IS_LONG_GAP_COLUMN",
    "IS_VERY_LONG_GAP_COLUMN",
    "IS_ELIGIBLE_FOR_SEQUENCE_COLUMN",

    # Enums
    "AlignmentStatus",
    "GapStatus",
    "NormalizationMethod",

    # Exceptions
    "TemporalNormalizationError",
    "TemporalNormalizationSchemaError",
    "TemporalNormalizationDataError",
    "TemporalNormalizationConfigurationError",

    # Configuration
    "TemporalNormalizationConfig",

    # Operational profile
    "OperationalProfile",

    # Statistics
    "FacilityNormalizationStatistics",
    "TemporalNormalizationStatistics",

    # Result
    "TemporalNormalizationResult",

    # Main class
    "TemporalNormalizer",

    # Convenience functions
    "normalize_temporal_dataset",
    "normalize_birmingham_temporal",
]