"""
SmartPark AI - ML Dataset Builder.

Builds leakage-safe supervised-learning datasets from the
temporally normalized parking dataset.

Pipeline position:

    Data Source
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
    Temporal Normalization
        |
        v
    ML Dataset Builder          <-- THIS MODULE
        |
        v
    Feature Engineering
        |
        +----------------------+
        |                      |
        v                      v
     XGBoost                 LSTM
        |
        v
    Evaluation
        |
        v
    Forecasting


Responsibilities
----------------

This module:

- consumes temporally normalized parking observations
- builds supervised-learning targets
- creates 30-minute targets
- creates 1-hour targets
- creates 2-hour targets
- creates tomorrow-morning demand targets
- prevents targets from crossing invalid temporal gaps
- preserves missing observations
- records target availability
- records target exclusion reasons
- produces dataset statistics

This module deliberately does NOT:

- train models
- perform feature engineering
- scale features
- interpolate occupancy
- forward-fill occupancy
- backward-fill occupancy
- perform train/test splitting
- perform model selection

Those responsibilities belong to later stages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

import numpy as np
import pandas as pd


# ============================================================
# Canonical / normalized columns
# ============================================================

FACILITY_COLUMN = "source_facility_code"

TIMESTAMP_COLUMN = "normalized_at"

SOURCE_TIMESTAMP_COLUMN = "source_observed_at"

TOTAL_SPACES_COLUMN = "total_spaces"

OCCUPIED_SPACES_COLUMN = "occupied_spaces"

AVAILABLE_SPACES_COLUMN = "available_spaces"

OCCUPANCY_RATE_COLUMN = "occupancy_rate"

OBSERVATION_PRESENT_COLUMN = "observation_present"

GAP_STATUS_COLUMN = "gap_status"

SEQUENCE_BREAK_COLUMN = "sequence_break"

IS_OPERATIONAL_GAP_COLUMN = "is_operational_gap"

IS_DATA_GAP_COLUMN = "is_data_gap"

IS_ELIGIBLE_FOR_SEQUENCE_COLUMN = (
    "is_eligible_for_sequence"
)

# Optional quality column. The builder does not require this
# because quality filtering is already handled by earlier
# pipeline stages.
QUALITY_STATUS_COLUMN = "quality_status"


# ============================================================
# Target columns
# ============================================================

TARGET_30M_COLUMN = (
    "target_occupancy_rate_30m"
)

TARGET_1H_COLUMN = (
    "target_occupancy_rate_1h"
)

TARGET_2H_COLUMN = (
    "target_occupancy_rate_2h"
)

TARGET_TOMORROW_MORNING_COLUMN = (
    "target_tomorrow_morning_demand"
)

TARGET_TOMORROW_MORNING_RATE_COLUMN = (
    "target_tomorrow_morning_occupancy_rate"
)

TARGET_TOMORROW_MORNING_TIMESTAMP_COLUMN = (
    "target_tomorrow_morning_at"
)


# ============================================================
# Target availability columns
# ============================================================

TARGET_30M_AVAILABLE_COLUMN = (
    "target_30m_available"
)

TARGET_1H_AVAILABLE_COLUMN = (
    "target_1h_available"
)

TARGET_2H_AVAILABLE_COLUMN = (
    "target_2h_available"
)

TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN = (
    "target_tomorrow_morning_available"
)

TARGET_ELIGIBLE_COLUMN = (
    "target_eligible"
)

TARGET_EXCLUSION_REASON_COLUMN = (
    "target_exclusion_reason"
)


# ============================================================
# Enums
# ============================================================


class TargetHorizon(str, Enum):
    """Supported SmartPark prediction horizons."""

    MINUTES_30 = "30m"

    HOUR_1 = "1h"

    HOURS_2 = "2h"

    TOMORROW_MORNING = "tomorrow_morning"


class DatasetBuildStatus(str, Enum):
    """Overall dataset-build status."""

    SUCCESS = "SUCCESS"

    SUCCESS_WITH_WARNINGS = (
        "SUCCESS_WITH_WARNINGS"
    )

    FAILED = "FAILED"


class TargetExclusionReason(str, Enum):
    """Why a target cannot be used for training."""

    NONE = "NONE"

    CURRENT_OBSERVATION_MISSING = (
        "CURRENT_OBSERVATION_MISSING"
    )

    TARGET_OBSERVATION_MISSING = (
        "TARGET_OBSERVATION_MISSING"
    )

    TARGET_SEQUENCE_BREAK = (
        "TARGET_SEQUENCE_BREAK"
    )

    TARGET_OPERATIONAL_GAP = (
        "TARGET_OPERATIONAL_GAP"
    )

    TARGET_DATA_GAP = (
        "TARGET_DATA_GAP"
    )

    TARGET_OUTSIDE_DATASET = (
        "TARGET_OUTSIDE_DATASET"
    )

    TOMORROW_MORNING_UNAVAILABLE = (
        "TOMORROW_MORNING_UNAVAILABLE"
    )


# ============================================================
# Exceptions
# ============================================================


class MLDatasetBuilderError(Exception):
    """Base ML dataset builder exception."""


class MLDatasetSchemaError(
    MLDatasetBuilderError
):
    """Raised when the input schema is invalid."""


class MLDatasetConfigurationError(
    MLDatasetBuilderError
):
    """Raised when builder configuration is invalid."""


class MLDatasetDataError(
    MLDatasetBuilderError
):
    """Raised when the input data is invalid."""


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class MLDatasetBuilderConfig:
    """
    Configuration for supervised-learning dataset creation.

    SmartPark AI uses a 30-minute modelling interval.

    Required direct prediction horizons:

        +30 minutes
        +1 hour
        +2 hours

    Tomorrow morning is configurable and defaults to:

        08:00 - 10:00
    """

    interval_minutes: int = 30

    horizons_minutes: tuple[int, ...] = (
        30,
        60,
        120,
    )

    tomorrow_morning_start_hour: int = 8

    tomorrow_morning_start_minute: int = 0

    tomorrow_morning_end_hour: int = 10

    tomorrow_morning_end_minute: int = 0

    require_observed_current_value: bool = True

    require_observed_target_value: bool = True

    reject_operational_gap_targets: bool = True

    reject_data_gap_targets: bool = True

    reject_sequence_break_targets: bool = True

    exclude_quality_flagged_rows: bool = False

    minimum_tomorrow_morning_observations: int = 1

    tomorrow_morning_aggregation: str = "mean"

    def __post_init__(self) -> None:

        if self.interval_minutes <= 0:
            raise MLDatasetConfigurationError(
                "interval_minutes must be greater than zero."
            )

        if not self.horizons_minutes:
            raise MLDatasetConfigurationError(
                "At least one prediction horizon is required."
            )

        if any(
            horizon <= 0
            for horizon in self.horizons_minutes
        ):
            raise MLDatasetConfigurationError(
                "Prediction horizons must be positive."
            )

        required_horizons = {
            30,
            60,
            120,
        }

        configured_horizons = set(
            self.horizons_minutes
        )

        missing = (
            required_horizons
            - configured_horizons
        )

        if missing:
            raise MLDatasetConfigurationError(
                "SmartPark AI requires 30m, 1h and 2h "
                f"horizons. Missing: {sorted(missing)}"
            )

        if not 0 <= self.tomorrow_morning_start_hour <= 23:
            raise MLDatasetConfigurationError(
                "Tomorrow morning start hour must "
                "be between 0 and 23."
            )

        if not 0 <= self.tomorrow_morning_end_hour <= 23:
            raise MLDatasetConfigurationError(
                "Tomorrow morning end hour must "
                "be between 0 and 23."
            )

        if not 0 <= self.tomorrow_morning_start_minute <= 59:
            raise MLDatasetConfigurationError(
                "Tomorrow morning start minute must "
                "be between 0 and 59."
            )

        if not 0 <= self.tomorrow_morning_end_minute <= 59:
            raise MLDatasetConfigurationError(
                "Tomorrow morning end minute must "
                "be between 0 and 59."
            )

        start_minutes = (
            self.tomorrow_morning_start_hour * 60
            + self.tomorrow_morning_start_minute
        )

        end_minutes = (
            self.tomorrow_morning_end_hour * 60
            + self.tomorrow_morning_end_minute
        )

        if end_minutes <= start_minutes:
            raise MLDatasetConfigurationError(
                "Tomorrow morning end time must "
                "be later than the start time."
            )

        if self.minimum_tomorrow_morning_observations < 1:
            raise MLDatasetConfigurationError(
                "minimum_tomorrow_morning_observations "
                "must be at least 1."
            )

        if self.tomorrow_morning_aggregation not in {
            "mean",
            "max",
            "median",
        }:
            raise MLDatasetConfigurationError(
                "tomorrow_morning_aggregation must "
                "be one of: mean, max, median."
            )


# ============================================================
# Statistics
# ============================================================


@dataclass(frozen=True, slots=True)
class TargetStatistics:
    """Statistics for an individual prediction target."""

    horizon: str

    total_rows: int

    available_targets: int

    unavailable_targets: int

    availability_rate: float

    missing_target_count: int

    sequence_break_count: int

    operational_gap_count: int

    data_gap_count: int

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True, slots=True)
class MLDatasetStatistics:
    """Overall ML dataset statistics."""

    source_row_count: int

    final_row_count: int

    facility_count: int

    target_30m_available: int

    target_1h_available: int

    target_2h_available: int

    target_tomorrow_morning_available: int

    fully_supervised_rows: int

    partially_supervised_rows: int

    unsupervised_rows: int

    target_statistics: tuple[
        TargetStatistics,
        ...
    ]

    coverage_start: pd.Timestamp | None

    coverage_end: pd.Timestamp | None

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True, slots=True)
class MLDatasetResult:
    """Complete ML dataset build result."""

    dataframe: pd.DataFrame

    statistics: MLDatasetStatistics

    status: DatasetBuildStatus

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    @property
    def row_count(self) -> int:
        return len(self.dataframe)

    @property
    def facility_count(self) -> int:
        return self.statistics.facility_count


# ============================================================
# Builder
# ============================================================


class MLDatasetBuilder:
    """
    Build leakage-safe supervised-learning datasets.

    Important design rule:

        Future observations may be used to construct TARGETS.

        Future observations must NEVER be used to construct
        FEATURES.

    Feature engineering is intentionally deferred to the
    next stage.
    """

    def __init__(
        self,
        config: MLDatasetBuilderConfig | None = None,
    ) -> None:

        self._config = (
            config
            if config is not None
            else MLDatasetBuilderConfig()
        )

    # ========================================================
    # Public API
    # ========================================================

    def build(
        self,
        dataframe: pd.DataFrame,
    ) -> MLDatasetResult:
        """
        Build supervised-learning targets.

        The input must already be temporally normalized.
        """

        self._validate_schema(
            dataframe
        )

        working = self._prepare_dataframe(
            dataframe
        )

        frames: list[pd.DataFrame] = []

        for (
            facility_code,
            facility_dataframe,
        ) in working.groupby(
            FACILITY_COLUMN,
            sort=True,
        ):

            facility_result = (
                self._build_facility_dataset(
                    facility_code=str(
                        facility_code
                    ),
                    dataframe=facility_dataframe,
                )
            )

            frames.append(
                facility_result
            )

        if frames:

            result = pd.concat(
                frames,
                ignore_index=True,
            )

        else:

            result = working.copy(
                deep=True
            )

        result = self._finalize(
            result
        )

        statistics = (
            self._build_statistics(
                source=working,
                result=result,
            )
        )

        status = (
            DatasetBuildStatus.SUCCESS
        )

        if (
            statistics.unsupervised_rows > 0
        ):
            status = (
                DatasetBuildStatus
                .SUCCESS_WITH_WARNINGS
            )

        return MLDatasetResult(
            dataframe=result,
            statistics=statistics,
            status=status,
            metadata={
                "interval_minutes": (
                    self._config.interval_minutes
                ),
                "horizons_minutes": (
                    self._config.horizons_minutes
                ),
                "tomorrow_morning": {
                    "start": self._format_time(
                        self._config
                        .tomorrow_morning_start_hour,
                        self._config
                        .tomorrow_morning_start_minute,
                    ),
                    "end": self._format_time(
                        self._config
                        .tomorrow_morning_end_hour,
                        self._config
                        .tomorrow_morning_end_minute,
                    ),
                },
                "feature_engineering": False,
                "train_test_split": False,
                "scaling": False,
                "interpolation": False,
                "data_leakage_prevention": True,
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
            raise MLDatasetDataError(
                "MLDatasetBuilder requires a pandas DataFrame."
            )

        if dataframe.empty:
            raise MLDatasetDataError(
                "Cannot build an ML dataset from an empty DataFrame."
            )

        required_columns = {
            FACILITY_COLUMN,
            TIMESTAMP_COLUMN,
            OCCUPANCY_RATE_COLUMN,
            OBSERVATION_PRESENT_COLUMN,
            SEQUENCE_BREAK_COLUMN,
            IS_OPERATIONAL_GAP_COLUMN,
            IS_DATA_GAP_COLUMN,
        }

        missing = (
            required_columns
            - set(dataframe.columns)
        )

        if missing:
            raise MLDatasetSchemaError(
                "Temporal dataset is missing required "
                f"columns: {sorted(missing)}"
            )

    # ========================================================
    # Preparation
    # ========================================================

    def _prepare_dataframe(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:

        result = dataframe.copy(
            deep=True
        )

        # ----------------------------------------------------
        # Timestamp
        # ----------------------------------------------------

        result[
            TIMESTAMP_COLUMN
        ] = pd.to_datetime(
            result[
                TIMESTAMP_COLUMN
            ],
            errors="coerce",
        )

        if result[
            TIMESTAMP_COLUMN
        ].isna().any():

            raise MLDatasetDataError(
                "Dataset contains invalid normalized timestamps."
            )

        # ----------------------------------------------------
        # Facility
        # ----------------------------------------------------

        result[
            FACILITY_COLUMN
        ] = (
            result[
                FACILITY_COLUMN
            ]
            .astype("string")
            .str.strip()
        )

        if result[
            FACILITY_COLUMN
        ].isna().any():

            raise MLDatasetDataError(
                "Dataset contains null facility identifiers."
            )

        # ----------------------------------------------------
        # Occupancy
        # ----------------------------------------------------

        result[
            OCCUPANCY_RATE_COLUMN
        ] = pd.to_numeric(
            result[
                OCCUPANCY_RATE_COLUMN
            ],
            errors="coerce",
        )

        # ----------------------------------------------------
        # Boolean columns
        #
        # Explicit conversion is important because pandas
        # shift() can introduce NaN and therefore convert a
        # boolean Series into a float/object representation.
        # ----------------------------------------------------

        for column in [
            OBSERVATION_PRESENT_COLUMN,
            SEQUENCE_BREAK_COLUMN,
            IS_OPERATIONAL_GAP_COLUMN,
            IS_DATA_GAP_COLUMN,
        ]:

            result[column] = (
                result[column]
                .fillna(False)
                .astype(bool)
            )

        # ----------------------------------------------------
        # Sort deterministically.
        # ----------------------------------------------------

        result = result.sort_values(
            [
                FACILITY_COLUMN,
                TIMESTAMP_COLUMN,
            ],
            kind="stable",
        ).reset_index(
            drop=True
        )

        # ----------------------------------------------------
        # Detect duplicate facility/timestamp combinations.
        #
        # Temporal normalization should normally already have
        # prevented this, but the ML boundary should fail safely
        # rather than silently create ambiguous targets.
        # ----------------------------------------------------

        duplicate_mask = (
            result[
                [
                    FACILITY_COLUMN,
                    TIMESTAMP_COLUMN,
                ]
            ]
            .duplicated(
                keep=False
            )
        )

        if duplicate_mask.any():

            duplicate_count = int(
                duplicate_mask.sum()
            )

            raise MLDatasetDataError(
                "Temporal dataset contains "
                f"{duplicate_count} duplicate facility/timestamp "
                "rows. ML target generation requires one row per "
                "facility per normalized timestamp."
            )

        return result

    # ========================================================
    # Facility dataset
    # ========================================================

    def _build_facility_dataset(
        self,
        *,
        facility_code: str,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:

        result = dataframe.copy(
            deep=True
        )

        result = result.sort_values(
            TIMESTAMP_COLUMN,
            kind="stable",
        ).reset_index(
            drop=True
        )

        # ----------------------------------------------------
        # Initialize target columns.
        # ----------------------------------------------------

        result[
            TARGET_30M_COLUMN
        ] = np.nan

        result[
            TARGET_1H_COLUMN
        ] = np.nan

        result[
            TARGET_2H_COLUMN
        ] = np.nan

        result[
            TARGET_TOMORROW_MORNING_COLUMN
        ] = np.nan

        result[
            TARGET_TOMORROW_MORNING_RATE_COLUMN
        ] = np.nan

        result[
            TARGET_TOMORROW_MORNING_TIMESTAMP_COLUMN
        ] = pd.NaT

        # ----------------------------------------------------
        # Availability flags.
        # ----------------------------------------------------

        result[
            TARGET_30M_AVAILABLE_COLUMN
        ] = False

        result[
            TARGET_1H_AVAILABLE_COLUMN
        ] = False

        result[
            TARGET_2H_AVAILABLE_COLUMN
        ] = False

        result[
            TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN
        ] = False

        # ----------------------------------------------------
        # General target eligibility.
        # ----------------------------------------------------

        result[
            TARGET_ELIGIBLE_COLUMN
        ] = False

        result[
            TARGET_EXCLUSION_REASON_COLUMN
        ] = (
            TargetExclusionReason.NONE.value
        )

        # ----------------------------------------------------
        # Direct horizons.
        # ----------------------------------------------------

        result = self._build_horizon_targets(
            result,
            minutes=30,
            target_column=TARGET_30M_COLUMN,
            availability_column=(
                TARGET_30M_AVAILABLE_COLUMN
            ),
        )

        result = self._build_horizon_targets(
            result,
            minutes=60,
            target_column=TARGET_1H_COLUMN,
            availability_column=(
                TARGET_1H_AVAILABLE_COLUMN
            ),
        )

        result = self._build_horizon_targets(
            result,
            minutes=120,
            target_column=TARGET_2H_COLUMN,
            availability_column=(
                TARGET_2H_AVAILABLE_COLUMN
            ),
        )

        # ----------------------------------------------------
        # Tomorrow morning.
        # ----------------------------------------------------

        result = (
            self._build_tomorrow_morning_target(
                result
            )
        )

        # ----------------------------------------------------
        # A row is target-eligible if at least one target is
        # available.
        #
        # We deliberately do NOT require all four targets.
        # This allows separate training datasets later:
        #
        #   XGBoost 30m
        #   XGBoost 1h
        #   XGBoost 2h
        #   Tomorrow morning
        #
        # Each model can use its own eligible subset.
        # ----------------------------------------------------

        result[
            TARGET_ELIGIBLE_COLUMN
        ] = (
            result[
                TARGET_30M_AVAILABLE_COLUMN
            ]
            | result[
                TARGET_1H_AVAILABLE_COLUMN
            ]
            | result[
                TARGET_2H_AVAILABLE_COLUMN
            ]
            | result[
                TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN
            ]
        )

        return result

    # ========================================================
    # Direct horizon targets
    # ========================================================

    def _build_horizon_targets(
        self,
        dataframe: pd.DataFrame,
        *,
        minutes: int,
        target_column: str,
        availability_column: str,
    ) -> pd.DataFrame:

        result = dataframe.copy(
            deep=True
        )

        interval = (
            self._config.interval_minutes
        )

        if minutes % interval != 0:
            raise MLDatasetConfigurationError(
                f"Horizon {minutes} minutes is not "
                f"compatible with the {interval}-minute "
                "modelling interval."
            )

        steps = (
            minutes // interval
        )

        observation_present = (
            result[
                OBSERVATION_PRESENT_COLUMN
            ]
            .fillna(False)
            .astype(bool)
        )

        occupancy = result[
            OCCUPANCY_RATE_COLUMN
        ]

        sequence_break = (
            result[
                SEQUENCE_BREAK_COLUMN
            ]
            .fillna(False)
            .astype(bool)
        )

        operational_gap = (
            result[
                IS_OPERATIONAL_GAP_COLUMN
            ]
            .fillna(False)
            .astype(bool)
        )

        data_gap = (
            result[
                IS_DATA_GAP_COLUMN
            ]
            .fillna(False)
            .astype(bool)
        )

        # ----------------------------------------------------
        # Future values.
        #
        # IMPORTANT:
        #
        # shift() introduces NaN at the end of the facility
        # series. Every boolean result is explicitly converted
        # back to boolean.
        # ----------------------------------------------------

        future_occupancy = (
            occupancy.shift(
                -steps
            )
        )

        future_observed = (
            observation_present
            .shift(
                -steps
            )
            .fillna(False)
            .astype(bool)
        )

        future_sequence_break = (
            sequence_break
            .shift(
                -steps
            )
            .fillna(True)
            .astype(bool)
        )

        future_operational_gap = (
            operational_gap
            .shift(
                -steps
            )
            .fillna(True)
            .astype(bool)
        )

        future_data_gap = (
            data_gap
            .shift(
                -steps
            )
            .fillna(True)
            .astype(bool)
        )

        # ----------------------------------------------------
        # Current observation validity.
        # ----------------------------------------------------

        current_valid = (
            observation_present
            & occupancy.notna()
        )

        if (
            self._config
            .exclude_quality_flagged_rows
            and QUALITY_STATUS_COLUMN
            in result.columns
        ):

            current_valid = (
                current_valid
                & result[
                    QUALITY_STATUS_COLUMN
                ]
                .fillna("FLAGGED")
                .eq("CLEAN")
            )

        # ----------------------------------------------------
        # Target validity.
        # ----------------------------------------------------

        target_valid = (
            current_valid
            & future_observed
            & future_occupancy.notna()
        )

        if (
            self._config
            .reject_sequence_break_targets
        ):

            target_valid = (
                target_valid
                & ~future_sequence_break
            )

        if (
            self._config
            .reject_operational_gap_targets
        ):

            target_valid = (
                target_valid
                & ~future_operational_gap
            )

        if (
            self._config
            .reject_data_gap_targets
        ):

            target_valid = (
                target_valid
                & ~future_data_gap
            )

        # ----------------------------------------------------
        # Assign target.
        # ----------------------------------------------------

        result.loc[
            target_valid,
            target_column,
        ] = future_occupancy[
            target_valid
        ].astype(float)

        result.loc[
            target_valid,
            availability_column,
        ] = True

        # ----------------------------------------------------
        # Build precise exclusion reason.
        #
        # Priority:
        #
        # 1. current observation missing
        # 2. target outside dataset
        # 3. target observation missing
        # 4. target sequence break
        # 5. operational gap
        # 6. data gap
        # 7. none
        # ----------------------------------------------------

        reason = self._build_horizon_reasons(
            result=result,
            steps=steps,
            current_valid=current_valid,
            future_occupancy=future_occupancy,
            future_observed=future_observed,
            future_sequence_break=(
                future_sequence_break
            ),
            future_operational_gap=(
                future_operational_gap
            ),
            future_data_gap=(
                future_data_gap
            ),
        )

        # ----------------------------------------------------
        # Only overwrite the reason if this horizon produced
        # a more meaningful reason.
        #
        # The reason column is primarily diagnostic. Individual
        # target availability columns remain authoritative.
        # ----------------------------------------------------

        self._apply_exclusion_reason(
            result,
            reason,
        )

        return result

    # ========================================================
    # Horizon exclusion reasons
    # ========================================================

    def _build_horizon_reasons(
        self,
        *,
        result: pd.DataFrame,
        steps: int,
        current_valid: pd.Series,
        future_occupancy: pd.Series,
        future_observed: pd.Series,
        future_sequence_break: pd.Series,
        future_operational_gap: pd.Series,
        future_data_gap: pd.Series,
    ) -> pd.Series:

        reason = pd.Series(
            TargetExclusionReason.NONE.value,
            index=result.index,
            dtype="string",
        )

        # ----------------------------------------------------
        # Current observation unavailable.
        # ----------------------------------------------------

        reason.loc[
            ~current_valid
        ] = (
            TargetExclusionReason
            .CURRENT_OBSERVATION_MISSING
            .value
        )

        # ----------------------------------------------------
        # Determine whether a future position actually exists.
        # ----------------------------------------------------

        future_index = (
            np.arange(
                len(result)
            )
            + steps
        )

        outside_dataset = (
            future_index
            >= len(result)
        )

        outside_mask = (
            current_valid
            & pd.Series(
                outside_dataset,
                index=result.index,
            )
        )

        reason.loc[
            outside_mask
        ] = (
            TargetExclusionReason
            .TARGET_OUTSIDE_DATASET
            .value
        )

        # ----------------------------------------------------
        # Future observation unavailable.
        # ----------------------------------------------------

        target_missing = (
            current_valid
            & ~outside_mask
            & ~future_observed
        )

        reason.loc[
            target_missing
        ] = (
            TargetExclusionReason
            .TARGET_OBSERVATION_MISSING
            .value
        )

        # ----------------------------------------------------
        # Sequence break.
        # ----------------------------------------------------

        sequence_invalid = (
            current_valid
            & ~outside_mask
            & future_observed
            & future_sequence_break
        )

        if (
            self._config
            .reject_sequence_break_targets
        ):

            reason.loc[
                sequence_invalid
            ] = (
                TargetExclusionReason
                .TARGET_SEQUENCE_BREAK
                .value
            )

        # ----------------------------------------------------
        # Operational gap.
        # ----------------------------------------------------

        operational_invalid = (
            current_valid
            & ~outside_mask
            & future_observed
            & ~future_sequence_break
            & future_operational_gap
        )

        if (
            self._config
            .reject_operational_gap_targets
        ):

            reason.loc[
                operational_invalid
            ] = (
                TargetExclusionReason
                .TARGET_OPERATIONAL_GAP
                .value
            )

        # ----------------------------------------------------
        # Data gap.
        # ----------------------------------------------------

        data_invalid = (
            current_valid
            & ~outside_mask
            & future_observed
            & ~future_sequence_break
            & ~future_operational_gap
            & future_data_gap
        )

        if (
            self._config
            .reject_data_gap_targets
        ):

            reason.loc[
                data_invalid
            ] = (
                TargetExclusionReason
                .TARGET_DATA_GAP
                .value
            )

        return reason

    # ========================================================
    # Apply diagnostic exclusion reason
    # ========================================================

    def _apply_exclusion_reason(
        self,
        dataframe: pd.DataFrame,
        reason: pd.Series,
    ) -> None:

        current = (
            dataframe[
                TARGET_EXCLUSION_REASON_COLUMN
            ]
            .fillna(
                TargetExclusionReason.NONE.value
            )
            .astype("string")
        )

        # Preserve an already meaningful reason.
        meaningful_current = (
            current
            != TargetExclusionReason.NONE.value
        )

        replace_mask = (
            ~meaningful_current
            & (
                reason
                != TargetExclusionReason.NONE.value
            )
        )

        dataframe.loc[
            replace_mask,
            TARGET_EXCLUSION_REASON_COLUMN,
        ] = reason[
            replace_mask
        ]

    # ========================================================
    # Tomorrow morning target
    # ========================================================

    def _build_tomorrow_morning_target(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:

        result = dataframe.copy(
            deep=True
        )

        timestamp = result[
            TIMESTAMP_COLUMN
        ]

        occupancy = result[
            OCCUPANCY_RATE_COLUMN
        ]

        observed = (
            result[
                OBSERVATION_PRESENT_COLUMN
            ]
            .fillna(False)
            .astype(bool)
        )

        sequence_break = (
            result[
                SEQUENCE_BREAK_COLUMN
            ]
            .fillna(False)
            .astype(bool)
        )

        operational_gap = (
            result[
                IS_OPERATIONAL_GAP_COLUMN
            ]
            .fillna(False)
            .astype(bool)
        )

        data_gap = (
            result[
                IS_DATA_GAP_COLUMN
            ]
            .fillna(False)
            .astype(bool)
        )

        # ----------------------------------------------------
        # Morning window.
        # ----------------------------------------------------

        start_minutes = (
            self._config
            .tomorrow_morning_start_hour
            * 60
            + self._config
            .tomorrow_morning_start_minute
        )

        end_minutes = (
            self._config
            .tomorrow_morning_end_hour
            * 60
            + self._config
            .tomorrow_morning_end_minute
        )

        time_minutes = (
            timestamp.dt.hour * 60
            + timestamp.dt.minute
        )

        is_morning = (
            time_minutes >= start_minutes
        ) & (
            time_minutes < end_minutes
        )

        # ----------------------------------------------------
        # Valid morning observations.
        # ----------------------------------------------------

        valid_morning = (
            is_morning
            & observed
            & occupancy.notna()
            & ~sequence_break
        )

        if (
            self._config
            .reject_operational_gap_targets
        ):

            valid_morning = (
                valid_morning
                & ~operational_gap
            )

        if (
            self._config
            .reject_data_gap_targets
        ):

            valid_morning = (
                valid_morning
                & ~data_gap
            )

        if not valid_morning.any():

            result[
                TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN
            ] = False

            return result

        # ----------------------------------------------------
        # Work with a compact target dataframe.
        # ----------------------------------------------------

        morning = pd.DataFrame(
            {
                "_date": timestamp.dt.normalize(),
                "_occupancy": occupancy,
            },
            index=result.index,
        )

        morning = morning.loc[
            valid_morning
        ]

        # ----------------------------------------------------
        # Aggregate.
        # ----------------------------------------------------

        grouped = (
            morning.groupby(
                "_date",
                sort=True,
            )[
                "_occupancy"
            ]
        )

        if (
            self._config
            .tomorrow_morning_aggregation
            == "mean"
        ):

            morning_values = (
                grouped.mean()
            )

        elif (
            self._config
            .tomorrow_morning_aggregation
            == "max"
        ):

            morning_values = (
                grouped.max()
            )

        else:

            morning_values = (
                grouped.median()
            )

        morning_counts = (
            grouped.count()
        )

        # ----------------------------------------------------
        # Tomorrow's date.
        # ----------------------------------------------------

        current_dates = (
            timestamp.dt.normalize()
        )

        target_dates = (
            current_dates
            + pd.Timedelta(days=1)
        )

        target_values = (
            target_dates.map(
                morning_values
            )
        )

        target_counts = (
            target_dates.map(
                morning_counts
            )
        )

        target_available = (
            observed
            & occupancy.notna()
            & target_values.notna()
            & target_counts.ge(
                self._config
                .minimum_tomorrow_morning_observations
            )
        )

        # ----------------------------------------------------
        # Assign target.
        # ----------------------------------------------------

        result.loc[
            target_available,
            TARGET_TOMORROW_MORNING_COLUMN,
        ] = target_values[
            target_available
        ].astype(float)

        result.loc[
            target_available,
            TARGET_TOMORROW_MORNING_RATE_COLUMN,
        ] = target_values[
            target_available
        ].astype(float)

        result.loc[
            target_available,
            TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN,
        ] = True

        result.loc[
            target_available,
            TARGET_TOMORROW_MORNING_TIMESTAMP_COLUMN,
        ] = (
            target_dates[
                target_available
            ]
            + pd.Timedelta(
                minutes=start_minutes
            )
        )

        # ----------------------------------------------------
        # Mark unavailable tomorrow-morning targets.
        # ----------------------------------------------------

        unavailable = (
            observed
            & ~target_available
        )

        result.loc[
            unavailable,
            TARGET_EXCLUSION_REASON_COLUMN,
        ] = (
            TargetExclusionReason
            .TOMORROW_MORNING_UNAVAILABLE
            .value
        )

        return result

    # ========================================================
    # Finalization
    # ========================================================

    def _finalize(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:

        result = dataframe.copy(
            deep=True
        )

        result = result.sort_values(
            [
                FACILITY_COLUMN,
                TIMESTAMP_COLUMN,
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
            TARGET_30M_AVAILABLE_COLUMN,
            TARGET_1H_AVAILABLE_COLUMN,
            TARGET_2H_AVAILABLE_COLUMN,
            TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN,
            TARGET_ELIGIBLE_COLUMN,
        ]

        for column in boolean_columns:

            if column in result.columns:

                result[column] = (
                    result[column]
                    .fillna(False)
                    .astype(bool)
                )

        # ----------------------------------------------------
        # Numeric target columns.
        # ----------------------------------------------------

        numeric_target_columns = [
            TARGET_30M_COLUMN,
            TARGET_1H_COLUMN,
            TARGET_2H_COLUMN,
            TARGET_TOMORROW_MORNING_COLUMN,
            TARGET_TOMORROW_MORNING_RATE_COLUMN,
        ]

        for column in numeric_target_columns:

            if column in result.columns:

                result[column] = pd.to_numeric(
                    result[column],
                    errors="coerce",
                ).astype(float)

        # ----------------------------------------------------
        # Timestamp target.
        # ----------------------------------------------------

        if (
            TARGET_TOMORROW_MORNING_TIMESTAMP_COLUMN
            in result.columns
        ):

            result[
                TARGET_TOMORROW_MORNING_TIMESTAMP_COLUMN
            ] = pd.to_datetime(
                result[
                    TARGET_TOMORROW_MORNING_TIMESTAMP_COLUMN
                ],
                errors="coerce",
            )

        # ----------------------------------------------------
        # Reason.
        # ----------------------------------------------------

        result[
            TARGET_EXCLUSION_REASON_COLUMN
        ] = (
            result[
                TARGET_EXCLUSION_REASON_COLUMN
            ]
            .fillna(
                TargetExclusionReason.NONE.value
            )
            .astype("string")
        )

        # ----------------------------------------------------
        # Keep targets together at the end.
        # ----------------------------------------------------

        target_columns = [
            TARGET_30M_COLUMN,
            TARGET_1H_COLUMN,
            TARGET_2H_COLUMN,
            TARGET_TOMORROW_MORNING_COLUMN,
            TARGET_TOMORROW_MORNING_RATE_COLUMN,
            TARGET_TOMORROW_MORNING_TIMESTAMP_COLUMN,
            TARGET_30M_AVAILABLE_COLUMN,
            TARGET_1H_AVAILABLE_COLUMN,
            TARGET_2H_AVAILABLE_COLUMN,
            TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN,
            TARGET_ELIGIBLE_COLUMN,
            TARGET_EXCLUSION_REASON_COLUMN,
        ]

        existing_target_columns = [
            column
            for column in target_columns
            if column in result.columns
        ]

        base_columns = [
            column
            for column in result.columns
            if column not in existing_target_columns
        ]

        return result[
            base_columns
            + existing_target_columns
        ]

    # ========================================================
    # Statistics
    # ========================================================

    def _build_statistics(
        self,
        *,
        source: pd.DataFrame,
        result: pd.DataFrame,
    ) -> MLDatasetStatistics:

        target_statistics: list[
            TargetStatistics
        ] = []

        target_definitions = [
            (
                TargetHorizon.MINUTES_30.value,
                TARGET_30M_AVAILABLE_COLUMN,
            ),
            (
                TargetHorizon.HOUR_1.value,
                TARGET_1H_AVAILABLE_COLUMN,
            ),
            (
                TargetHorizon.HOURS_2.value,
                TARGET_2H_AVAILABLE_COLUMN,
            ),
            (
                TargetHorizon.TOMORROW_MORNING.value,
                TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN,
            ),
        ]

        for (
            horizon,
            availability_column,
        ) in target_definitions:

            available = (
                result[
                    availability_column
                ]
                .fillna(False)
                .astype(bool)
            )

            total = len(result)

            available_count = int(
                available.sum()
            )

            unavailable_count = (
                total
                - available_count
            )

            availability_rate = (
                available_count / total
                if total
                else 0.0
            )

            target_statistics.append(
                TargetStatistics(
                    horizon=horizon,
                    total_rows=total,
                    available_targets=(
                        available_count
                    ),
                    unavailable_targets=(
                        unavailable_count
                    ),
                    availability_rate=(
                        availability_rate
                    ),
                    missing_target_count=(
                        unavailable_count
                    ),
                    sequence_break_count=int(
                        result[
                            SEQUENCE_BREAK_COLUMN
                        ].sum()
                    ),
                    operational_gap_count=int(
                        result[
                            IS_OPERATIONAL_GAP_COLUMN
                        ].sum()
                    ),
                    data_gap_count=int(
                        result[
                            IS_DATA_GAP_COLUMN
                        ].sum()
                    ),
                    metadata={
                        "availability_percentage": (
                            availability_rate * 100.0
                        ),
                    },
                )
            )

        availability_columns = [
            TARGET_30M_AVAILABLE_COLUMN,
            TARGET_1H_AVAILABLE_COLUMN,
            TARGET_2H_AVAILABLE_COLUMN,
            TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN,
        ]

        availability_matrix = (
            result[
                availability_columns
            ]
            .fillna(False)
            .astype(bool)
        )

        available_target_count = (
            availability_matrix.sum(
                axis=1
            )
        )

        target_count = len(
            availability_columns
        )

        fully_supervised = int(
            available_target_count.eq(
                target_count
            ).sum()
        )

        partially_supervised = int(
            (
                available_target_count.gt(0)
                & available_target_count.lt(
                    target_count
                )
            ).sum()
        )

        unsupervised = int(
            available_target_count.eq(0).sum()
        )

        return MLDatasetStatistics(
            source_row_count=len(
                source
            ),
            final_row_count=len(
                result
            ),
            facility_count=int(
                result[
                    FACILITY_COLUMN
                ].nunique()
            ),
            target_30m_available=int(
                result[
                    TARGET_30M_AVAILABLE_COLUMN
                ].sum()
            ),
            target_1h_available=int(
                result[
                    TARGET_1H_AVAILABLE_COLUMN
                ].sum()
            ),
            target_2h_available=int(
                result[
                    TARGET_2H_AVAILABLE_COLUMN
                ].sum()
            ),
            target_tomorrow_morning_available=int(
                result[
                    TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN
                ].sum()
            ),
            fully_supervised_rows=(
                fully_supervised
            ),
            partially_supervised_rows=(
                partially_supervised
            ),
            unsupervised_rows=(
                unsupervised
            ),
            target_statistics=tuple(
                target_statistics
            ),
            coverage_start=(
                result[
                    TIMESTAMP_COLUMN
                ].min()
            ),
            coverage_end=(
                result[
                    TIMESTAMP_COLUMN
                ].max()
            ),
            metadata={
                "feature_engineering_applied": False,
                "train_test_split_applied": False,
                "scaling_applied": False,
                "interpolation_applied": False,
                "future_features_used": False,
                "target_leakage_protection": True,
            },
        )

    # ========================================================
    # Utilities
    # ========================================================

    @staticmethod
    def _format_time(
        hour: int,
        minute: int,
    ) -> str:

        return f"{hour:02d}:{minute:02d}"


# ============================================================
# Convenience API
# ============================================================


def build_ml_dataset(
    dataframe: pd.DataFrame,
    *,
    interval_minutes: int = 30,
    tomorrow_morning_start_hour: int = 8,
    tomorrow_morning_start_minute: int = 0,
    tomorrow_morning_end_hour: int = 10,
    tomorrow_morning_end_minute: int = 0,
) -> MLDatasetResult:
    """
    Build an ML dataset from an already normalized dataframe.
    """

    config = MLDatasetBuilderConfig(
        interval_minutes=interval_minutes,
        tomorrow_morning_start_hour=(
            tomorrow_morning_start_hour
        ),
        tomorrow_morning_start_minute=(
            tomorrow_morning_start_minute
        ),
        tomorrow_morning_end_hour=(
            tomorrow_morning_end_hour
        ),
        tomorrow_morning_end_minute=(
            tomorrow_morning_end_minute
        ),
    )

    builder = MLDatasetBuilder(
        config=config
    )

    return builder.build(
        dataframe
    )


# ============================================================
# Birmingham convenience API
# ============================================================


def build_birmingham_ml_dataset(
    *,
    dataset_root: str = "../datasets/raw",
    tomorrow_morning_start_hour: int = 8,
    tomorrow_morning_start_minute: int = 0,
    tomorrow_morning_end_hour: int = 10,
    tomorrow_morning_end_minute: int = 0,
) -> MLDatasetResult:
    """
    Execute the Birmingham ML data pipeline:

        Birmingham raw CSV
                |
                v
        ingestion
                |
                v
        temporal normalization
                |
                v
        ML dataset builder
    """

    from app.ml.data.temporal_normalizer import (
        normalize_birmingham_temporal,
    )

    normalized = (
        normalize_birmingham_temporal(
            dataset_root=dataset_root,
        )
    )

    return build_ml_dataset(
        normalized.dataframe,
        tomorrow_morning_start_hour=(
            tomorrow_morning_start_hour
        ),
        tomorrow_morning_start_minute=(
            tomorrow_morning_start_minute
        ),
        tomorrow_morning_end_hour=(
            tomorrow_morning_end_hour
        ),
        tomorrow_morning_end_minute=(
            tomorrow_morning_end_minute
        ),
    )


# ============================================================
# Public API
# ============================================================

__all__ = [
    # Canonical columns
    "FACILITY_COLUMN",
    "TIMESTAMP_COLUMN",
    "SOURCE_TIMESTAMP_COLUMN",
    "TOTAL_SPACES_COLUMN",
    "OCCUPIED_SPACES_COLUMN",
    "AVAILABLE_SPACES_COLUMN",
    "OCCUPANCY_RATE_COLUMN",
    "OBSERVATION_PRESENT_COLUMN",
    "GAP_STATUS_COLUMN",
    "SEQUENCE_BREAK_COLUMN",
    "IS_OPERATIONAL_GAP_COLUMN",
    "IS_DATA_GAP_COLUMN",
    "IS_ELIGIBLE_FOR_SEQUENCE_COLUMN",
    "QUALITY_STATUS_COLUMN",

    # Targets
    "TARGET_30M_COLUMN",
    "TARGET_1H_COLUMN",
    "TARGET_2H_COLUMN",
    "TARGET_TOMORROW_MORNING_COLUMN",
    "TARGET_TOMORROW_MORNING_RATE_COLUMN",
    "TARGET_TOMORROW_MORNING_TIMESTAMP_COLUMN",

    # Availability
    "TARGET_30M_AVAILABLE_COLUMN",
    "TARGET_1H_AVAILABLE_COLUMN",
    "TARGET_2H_AVAILABLE_COLUMN",
    "TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN",
    "TARGET_ELIGIBLE_COLUMN",
    "TARGET_EXCLUSION_REASON_COLUMN",

    # Enums
    "TargetHorizon",
    "DatasetBuildStatus",
    "TargetExclusionReason",

    # Exceptions
    "MLDatasetBuilderError",
    "MLDatasetSchemaError",
    "MLDatasetConfigurationError",
    "MLDatasetDataError",

    # Configuration
    "MLDatasetBuilderConfig",

    # Statistics
    "TargetStatistics",
    "MLDatasetStatistics",

    # Result
    "MLDatasetResult",

    # Builder
    "MLDatasetBuilder",

    # Convenience
    "build_ml_dataset",
    "build_birmingham_ml_dataset",
]