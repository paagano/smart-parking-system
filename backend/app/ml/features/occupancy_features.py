"""
SmartPark AI - Occupancy Feature Engineering.

This module creates features describing the current occupancy state
of a parking facility.

Pipeline position
-----------------

    ML Dataset
        |
        v
    Temporal Features
        |
        v
    Occupancy Features       <-- this module
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
2. The input dataframe is never modified.
3. No target columns are used.
4. No lag features are generated here.
5. No rolling features are generated here.
6. Raw occupancy values are preserved.
7. Derived ratios are bounded and numerically safe.
8. Capacity anomalies are flagged rather than silently hidden.
9. Zero-capacity facilities are handled safely.
10. The component is independent of Birmingham-specific data.
11. Features are deterministic and reproducible.


Primary features
----------------

Current state:

    occupied_spaces
    available_spaces
    total_spaces
    occupancy_rate

Derived state:

    capacity_utilization
    availability_rate
    occupied_ratio
    available_ratio
    vacancy_ratio

State classification:

    occupancy_level
    is_empty
    is_low_occupancy
    is_moderate_occupancy
    is_high_occupancy
    is_near_full

Quality / consistency:

    occupancy_capacity_difference
    occupancy_within_capacity
    occupancy_state_valid

The module intentionally does not calculate:

    lag_*
    rolling_*
    historical averages
    future targets
    predictions
"""


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

import numpy as np
import pandas as pd


# ============================================================
# Constants
# ============================================================

DEFAULT_TOTAL_SPACES_COLUMN = "total_spaces"
DEFAULT_OCCUPIED_SPACES_COLUMN = "occupied_spaces"
DEFAULT_AVAILABLE_SPACES_COLUMN = "available_spaces"
DEFAULT_OCCUPANCY_RATE_COLUMN = "occupancy_rate"


# ============================================================
# Feature columns
# ============================================================

OCCUPANCY_FEATURE_COLUMNS: tuple[str, ...] = (
    # Current state
    "occupied_spaces",
    "available_spaces",
    "total_spaces",
    "occupancy_rate",

    # Derived ratios
    "capacity_utilization",
    "availability_rate",
    "occupied_ratio",
    "available_ratio",
    "vacancy_ratio",

    # State classification
    "occupancy_level",
    "is_empty",
    "is_low_occupancy",
    "is_moderate_occupancy",
    "is_high_occupancy",
    "is_near_full",

    # Consistency / quality
    "occupancy_capacity_difference",
    "occupancy_within_capacity",
    "occupancy_state_valid",
)


# ============================================================
# Exceptions
# ============================================================


class OccupancyFeatureError(Exception):
    """Base exception for occupancy feature engineering."""


class OccupancyFeatureSchemaError(
    OccupancyFeatureError
):
    """Raised when required occupancy columns are missing."""


class OccupancyFeatureDataError(
    OccupancyFeatureError
):
    """Raised when occupancy data is invalid."""


class OccupancyFeatureConfigurationError(
    OccupancyFeatureError
):
    """Raised when occupancy feature configuration is invalid."""


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class OccupancyFeatureConfig:
    """
    Configuration for occupancy feature generation.

    Parameters
    ----------
    total_spaces_column:
        Column containing facility capacity.

    occupied_spaces_column:
        Column containing currently occupied spaces.

    available_spaces_column:
        Column containing currently available spaces.

    occupancy_rate_column:
        Existing occupancy-rate column.

    derive_occupancy_rate:
        Whether to calculate occupancy rate from occupied/capacity
        rather than relying exclusively on the existing column.

    preserve_existing_occupancy_rate:
        If True and an existing occupancy_rate column exists,
        preserve it as the canonical source value.

    occupancy_rate_tolerance:
        Numerical tolerance used when checking consistency between
        occupancy_rate and occupied_spaces / total_spaces.

    low_occupancy_threshold:
        Upper bound for the LOW occupancy classification.

    moderate_occupancy_threshold:
        Upper bound for MODERATE occupancy classification.

    high_occupancy_threshold:
        Lower bound for HIGH occupancy classification.

    near_full_threshold:
        Threshold at which a facility is considered near full.

    clip_derived_rates:
        Whether derived ratios should be clipped to [0, 1].

    zero_capacity_policy:
        Behaviour when total_spaces is zero.

        Supported values:

            "nan"
            "error"
            "zero"

    add_quality_features:
        Whether consistency/quality features are added.

    preserve_index:
        Whether the input index should be preserved.
    """

    total_spaces_column: str = (
        DEFAULT_TOTAL_SPACES_COLUMN
    )

    occupied_spaces_column: str = (
        DEFAULT_OCCUPIED_SPACES_COLUMN
    )

    available_spaces_column: str = (
        DEFAULT_AVAILABLE_SPACES_COLUMN
    )

    occupancy_rate_column: str = (
        DEFAULT_OCCUPANCY_RATE_COLUMN
    )

    derive_occupancy_rate: bool = True

    preserve_existing_occupancy_rate: bool = True

    occupancy_rate_tolerance: float = 1e-6

    low_occupancy_threshold: float = 0.25

    moderate_occupancy_threshold: float = 0.60

    high_occupancy_threshold: float = 0.80

    near_full_threshold: float = 0.90

    clip_derived_rates: bool = True

    zero_capacity_policy: str = "nan"

    add_quality_features: bool = True

    preserve_index: bool = True

    def __post_init__(self) -> None:

        column_names = (
            self.total_spaces_column,
            self.occupied_spaces_column,
            self.available_spaces_column,
            self.occupancy_rate_column,
        )

        if any(
            not str(column).strip()
            for column in column_names
        ):

            raise OccupancyFeatureConfigurationError(
                "Occupancy column names cannot be empty."
            )

        if self.occupancy_rate_tolerance < 0:

            raise OccupancyFeatureConfigurationError(
                "occupancy_rate_tolerance cannot be negative."
            )

        thresholds = (
            self.low_occupancy_threshold,
            self.moderate_occupancy_threshold,
            self.high_occupancy_threshold,
            self.near_full_threshold,
        )

        if any(
            threshold < 0 or threshold > 1
            for threshold in thresholds
        ):

            raise OccupancyFeatureConfigurationError(
                "Occupancy thresholds must be between 0 and 1."
            )

        if not (
            self.low_occupancy_threshold
            <= self.moderate_occupancy_threshold
            <= self.high_occupancy_threshold
            <= self.near_full_threshold
        ):

            raise OccupancyFeatureConfigurationError(
                "Occupancy thresholds must be monotonically "
                "increasing."
            )

        if self.zero_capacity_policy not in {
            "nan",
            "error",
            "zero",
        }:

            raise OccupancyFeatureConfigurationError(
                "zero_capacity_policy must be one of: "
                "'nan', 'error', 'zero'."
            )


# ============================================================
# Statistics
# ============================================================


@dataclass(frozen=True, slots=True)
class OccupancyFeatureStatistics:
    """Statistics describing occupancy feature generation."""

    source_row_count: int

    output_row_count: int

    source_column_count: int

    output_column_count: int

    invalid_total_spaces_count: int

    invalid_occupied_spaces_count: int

    invalid_available_spaces_count: int

    invalid_occupancy_rate_count: int

    zero_capacity_count: int

    negative_occupancy_count: int

    occupancy_exceeds_capacity_count: int

    availability_inconsistency_count: int

    occupancy_rate_inconsistency_count: int

    valid_state_count: int

    invalid_state_count: int

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True, slots=True)
class OccupancyFeatureResult:
    """
    Result returned by the occupancy feature generator.
    """

    dataframe: pd.DataFrame

    statistics: OccupancyFeatureStatistics

    feature_columns: tuple[str, ...]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Generator
# ============================================================


class OccupancyFeatureGenerator:
    """
    Generate current-state occupancy features.

    This generator does not inspect future observations and does
    not use target columns.

    It is therefore safe to execute before the train/test split
    as part of deterministic feature construction, provided that
    downstream historical features are calculated without leakage.
    """

    def __init__(
        self,
        config: OccupancyFeatureConfig | None = None,
    ) -> None:

        self._config = (
            config
            if config is not None
            else OccupancyFeatureConfig()
        )

    # ========================================================
    # Public API
    # ========================================================

    def transform(
        self,
        dataframe: pd.DataFrame,
    ) -> OccupancyFeatureResult:
        """
        Generate occupancy features.

        The input dataframe is never modified.
        """

        self._validate_input(dataframe)

        source_row_count = len(dataframe)

        source_column_count = dataframe.shape[1]

        result = dataframe.copy(
            deep=True
        )

        # ----------------------------------------------------
        # Convert source values to numeric representations.
        # ----------------------------------------------------

        total_spaces = self._to_numeric(
            result[
                self._config.total_spaces_column
            ]
        )

        occupied_spaces = self._to_numeric(
            result[
                self._config.occupied_spaces_column
            ]
        )

        available_spaces = self._to_numeric(
            result[
                self._config.available_spaces_column
            ]
        )

        existing_occupancy_rate = (
            self._to_numeric(
                result[
                    self._config
                    .occupancy_rate_column
                ]
            )
        )

        # ----------------------------------------------------
        # Source validity checks.
        # ----------------------------------------------------

        invalid_total_spaces_count = int(
            total_spaces.isna().sum()
        )

        invalid_occupied_spaces_count = int(
            occupied_spaces.isna().sum()
        )

        invalid_available_spaces_count = int(
            available_spaces.isna().sum()
        )

        invalid_occupancy_rate_count = int(
            existing_occupancy_rate.isna().sum()
        )

        zero_capacity_mask = (
            total_spaces == 0
        )

        zero_capacity_count = int(
            zero_capacity_mask.sum()
        )

        negative_occupancy_mask = (
            occupied_spaces < 0
        )

        negative_occupancy_count = int(
            negative_occupancy_mask.sum()
        )

        occupancy_exceeds_capacity_mask = (
            occupied_spaces
            > total_spaces
        )

        occupancy_exceeds_capacity_count = int(
            occupancy_exceeds_capacity_mask.sum()
        )

        # ----------------------------------------------------
        # Current-state columns.
        #
        # We explicitly assign numeric values so downstream
        # model pipelines receive predictable dtypes.
        # ----------------------------------------------------

        result[
            "total_spaces"
        ] = total_spaces

        result[
            "occupied_spaces"
        ] = occupied_spaces

        result[
            "available_spaces"
        ] = available_spaces

        # ----------------------------------------------------
        # Determine canonical occupancy rate.
        # ----------------------------------------------------

        calculated_occupancy_rate = (
            self._safe_divide(
                occupied_spaces,
                total_spaces,
            )
        )

        if (
            self._config
            .preserve_existing_occupancy_rate
            and self._config
            .occupancy_rate_column
            in result.columns
        ):

            occupancy_rate = (
                existing_occupancy_rate.copy()
            )

            if self._config.derive_occupancy_rate:

                occupancy_rate = (
                    occupancy_rate
                    .where(
                        occupancy_rate.notna(),
                        calculated_occupancy_rate,
                    )
                )

        elif self._config.derive_occupancy_rate:

            occupancy_rate = (
                calculated_occupancy_rate
            )

        else:

            occupancy_rate = (
                existing_occupancy_rate
            )

        if self._config.clip_derived_rates:

            occupancy_rate = (
                occupancy_rate.clip(
                    lower=0.0,
                    upper=1.0,
                )
            )

        result[
            "occupancy_rate"
        ] = occupancy_rate.astype(
            "float64"
        )

        # ----------------------------------------------------
        # Derived ratios.
        # ----------------------------------------------------

        capacity_utilization = (
            calculated_occupancy_rate
        )

        availability_rate = (
            self._safe_divide(
                available_spaces,
                total_spaces,
            )
        )

        occupied_ratio = (
            self._safe_divide(
                occupied_spaces,
                total_spaces,
            )
        )

        available_ratio = (
            availability_rate.copy()
        )

        vacancy_ratio = (
            available_ratio.copy()
        )

        if self._config.clip_derived_rates:

            capacity_utilization = (
                capacity_utilization.clip(
                    0.0,
                    1.0,
                )
            )

            availability_rate = (
                availability_rate.clip(
                    0.0,
                    1.0,
                )
            )

            occupied_ratio = (
                occupied_ratio.clip(
                    0.0,
                    1.0,
                )
            )

            available_ratio = (
                available_ratio.clip(
                    0.0,
                    1.0,
                )
            )

            vacancy_ratio = (
                vacancy_ratio.clip(
                    0.0,
                    1.0,
                )
            )

        result[
            "capacity_utilization"
        ] = capacity_utilization

        result[
            "availability_rate"
        ] = availability_rate

        result[
            "occupied_ratio"
        ] = occupied_ratio

        result[
            "available_ratio"
        ] = available_ratio

        result[
            "vacancy_ratio"
        ] = vacancy_ratio

        # ----------------------------------------------------
        # Occupancy classification.
        # ----------------------------------------------------

        result[
            "occupancy_level"
        ] = self._classify_occupancy(
            occupancy_rate
        )

        result[
            "is_empty"
        ] = (
            occupancy_rate
            <= 0.0
        )

        result[
            "is_low_occupancy"
        ] = (
            occupancy_rate
            <= self._config
            .low_occupancy_threshold
        )

        result[
            "is_moderate_occupancy"
        ] = (
            (
                occupancy_rate
                > self._config
                .low_occupancy_threshold
            )
            & (
                occupancy_rate
                <= self._config
                .moderate_occupancy_threshold
            )
        )

        result[
            "is_high_occupancy"
        ] = (
            occupancy_rate
            >= self._config
            .high_occupancy_threshold
        )

        result[
            "is_near_full"
        ] = (
            occupancy_rate
            >= self._config
            .near_full_threshold
        )

        # ----------------------------------------------------
        # State consistency checks.
        # ----------------------------------------------------

        occupancy_capacity_difference = (
            occupied_spaces
            + available_spaces
            - total_spaces
        )

        availability_inconsistency_mask = (
            occupancy_capacity_difference
            .abs()
            > self._config
            .occupancy_rate_tolerance
        )

        availability_inconsistency_count = int(
            availability_inconsistency_mask.sum()
        )

        calculated_vs_existing_difference = (
            calculated_occupancy_rate
            - existing_occupancy_rate
        )

        occupancy_rate_inconsistency_mask = (
            calculated_vs_existing_difference
            .abs()
            > self._config
            .occupancy_rate_tolerance
        )

        # Do not count cases where either side is unavailable.
        occupancy_rate_inconsistency_mask = (
            occupancy_rate_inconsistency_mask
            & calculated_occupancy_rate.notna()
            & existing_occupancy_rate.notna()
        )

        occupancy_rate_inconsistency_count = int(
            occupancy_rate_inconsistency_mask.sum()
        )

        valid_state_mask = (
            total_spaces.notna()
            & occupied_spaces.notna()
            & available_spaces.notna()
            & (total_spaces >= 0)
            & (occupied_spaces >= 0)
            & (available_spaces >= 0)
            & ~zero_capacity_mask
            & ~negative_occupancy_mask
            & ~occupancy_exceeds_capacity_mask
            & ~availability_inconsistency_mask
        )

        invalid_state_mask = (
            ~valid_state_mask
        )

        if self._config.add_quality_features:

            result[
                "occupancy_capacity_difference"
            ] = (
                occupancy_capacity_difference
            )

            result[
                "occupancy_within_capacity"
            ] = (
                ~occupancy_exceeds_capacity_mask
            )

            result[
                "occupancy_state_valid"
            ] = valid_state_mask

        # ----------------------------------------------------
        # Zero-capacity policy.
        # ----------------------------------------------------

        if zero_capacity_count:

            if (
                self._config
                .zero_capacity_policy
                == "error"
            ):

                raise OccupancyFeatureDataError(
                    f"Found {zero_capacity_count} "
                    "rows with zero capacity."
                )

            if (
                self._config
                .zero_capacity_policy
                == "zero"
            ):

                zero_mask = (
                    total_spaces == 0
                )

                for column in (
                    "capacity_utilization",
                    "availability_rate",
                    "occupied_ratio",
                    "available_ratio",
                    "vacancy_ratio",
                    "occupancy_rate",
                ):

                    if column in result.columns:

                        result.loc[
                            zero_mask,
                            column,
                        ] = 0.0

        # ----------------------------------------------------
        # Collect generated feature columns.
        # ----------------------------------------------------

        generated_columns = tuple(
            column
            for column in OCCUPANCY_FEATURE_COLUMNS
            if column in result.columns
        )

        statistics = (
            OccupancyFeatureStatistics(
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
                invalid_total_spaces_count=(
                    invalid_total_spaces_count
                ),
                invalid_occupied_spaces_count=(
                    invalid_occupied_spaces_count
                ),
                invalid_available_spaces_count=(
                    invalid_available_spaces_count
                ),
                invalid_occupancy_rate_count=(
                    invalid_occupancy_rate_count
                ),
                zero_capacity_count=(
                    zero_capacity_count
                ),
                negative_occupancy_count=(
                    negative_occupancy_count
                ),
                occupancy_exceeds_capacity_count=(
                    occupancy_exceeds_capacity_count
                ),
                availability_inconsistency_count=(
                    availability_inconsistency_count
                ),
                occupancy_rate_inconsistency_count=(
                    occupancy_rate_inconsistency_count
                ),
                valid_state_count=int(
                    valid_state_mask.sum()
                ),
                invalid_state_count=int(
                    invalid_state_mask.sum()
                ),
                metadata={
                    "future_data_used": False,
                    "target_data_used": False,
                    "lag_features_used": False,
                    "rolling_features_used": False,
                    "feature_count": len(
                        generated_columns
                    ),
                    "zero_capacity_policy": (
                        self._config
                        .zero_capacity_policy
                    ),
                    "clip_derived_rates": (
                        self._config
                        .clip_derived_rates
                    ),
                },
            )
        )

        return OccupancyFeatureResult(
            dataframe=result,
            statistics=statistics,
            feature_columns=(
                generated_columns
            ),
            metadata={
                "generator": (
                    "OccupancyFeatureGenerator"
                ),
                "future_data_used": False,
                "target_data_used": False,
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

            raise OccupancyFeatureDataError(
                "OccupancyFeatureGenerator requires "
                "a pandas DataFrame."
            )

        if dataframe.empty:

            raise OccupancyFeatureDataError(
                "Cannot generate occupancy features "
                "from an empty dataframe."
            )

        required_columns = (
            self._config.total_spaces_column,
            self._config.occupied_spaces_column,
            self._config.available_spaces_column,
        )

        missing_columns = [
            column
            for column in required_columns
            if column not in dataframe.columns
        ]

        if missing_columns:

            raise OccupancyFeatureSchemaError(
                "Required occupancy columns are missing: "
                f"{missing_columns}"
            )

        if (
            self._config
            .preserve_existing_occupancy_rate
            and self._config
            .occupancy_rate_column
            not in dataframe.columns
            and not self._config.derive_occupancy_rate
        ):

            raise OccupancyFeatureSchemaError(
                "occupancy_rate column is required when "
                "derive_occupancy_rate=False."
            )

    # ========================================================
    # Numeric conversion
    # ========================================================

    @staticmethod
    def _to_numeric(
        series: pd.Series,
    ) -> pd.Series:

        return pd.to_numeric(
            series,
            errors="coerce",
        )

    # ========================================================
    # Safe division
    # ========================================================

    @staticmethod
    def _safe_divide(
        numerator: pd.Series,
        denominator: pd.Series,
    ) -> pd.Series:
        """
        Divide safely.

        Division by zero produces NaN rather than infinity.
        """

        numerator = pd.to_numeric(
            numerator,
            errors="coerce",
        )

        denominator = pd.to_numeric(
            denominator,
            errors="coerce",
        )

        result = pd.Series(
            np.nan,
            index=numerator.index,
            dtype="float64",
        )

        valid = (
            denominator.notna()
            & numerator.notna()
            & (denominator != 0)
        )

        result.loc[valid] = (
            numerator.loc[valid]
            / denominator.loc[valid]
        )

        return result

    # ========================================================
    # Occupancy classification
    # ========================================================

    def _classify_occupancy(
        self,
        occupancy_rate: pd.Series,
    ) -> pd.Series:
        """
        Classify occupancy into deterministic levels.

        Levels:

            EMPTY
            LOW
            MODERATE
            HIGH
            NEAR_FULL
            UNKNOWN
        """

        conditions = [
            occupancy_rate <= 0.0,

            (
                (occupancy_rate > 0.0)
                & (
                    occupancy_rate
                    <= self._config
                    .low_occupancy_threshold
                )
            ),

            (
                (
                    occupancy_rate
                    > self._config
                    .low_occupancy_threshold
                )
                & (
                    occupancy_rate
                    <= self._config
                    .moderate_occupancy_threshold
                )
            ),

            (
                (
                    occupancy_rate
                    > self._config
                    .moderate_occupancy_threshold
                )
                & (
                    occupancy_rate
                    < self._config
                    .high_occupancy_threshold
                )
            ),

            (
                occupancy_rate
                >= self._config
                .high_occupancy_threshold
            ),
        ]

        choices = [
            "EMPTY",
            "LOW",
            "MODERATE",
            "HIGH",
            "NEAR_FULL",
        ]

        classified = np.select(
            conditions,
            choices,
            default="UNKNOWN",
        )

        return pd.Series(
            classified,
            index=occupancy_rate.index,
            dtype="string",
        )


# ============================================================
# Convenience function
# ============================================================


def add_occupancy_features(
    dataframe: pd.DataFrame,
    *,
    config: OccupancyFeatureConfig | None = None,
) -> OccupancyFeatureResult:
    """
    Convenience wrapper around OccupancyFeatureGenerator.
    """

    generator = OccupancyFeatureGenerator(
        config=config
    )

    return generator.transform(
        dataframe
    )


# ============================================================
# Birmingham convenience function
# ============================================================


def add_birmingham_occupancy_features(
    *,
    dataset_root: str = "../datasets/raw",
    config: OccupancyFeatureConfig | None = None,
) -> OccupancyFeatureResult:
    """
    Build the Birmingham ML dataset and add occupancy features.

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

    return add_occupancy_features(
        dataset_result.dataframe,
        config=config,
    )


# ============================================================
# Validation helper
# ============================================================


def validate_occupancy_features(
    dataframe: pd.DataFrame,
    *,
    occupancy_rate_tolerance: float = 1e-6,
) -> dict[str, Any]:
    """
    Validate generated occupancy features.

    The function does not modify the dataframe.
    """

    required_columns = {
        "total_spaces",
        "occupied_spaces",
        "available_spaces",
        "occupancy_rate",
        "capacity_utilization",
        "availability_rate",
        "occupied_ratio",
        "available_ratio",
        "vacancy_ratio",
        "occupancy_level",
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
                    "Missing required occupancy "
                    f"features: {missing_columns}"
                )
            ],
        }

    errors: list[str] = []

    # --------------------------------------------------------
    # Numeric columns
    # --------------------------------------------------------

    numeric_columns = (
        "total_spaces",
        "occupied_spaces",
        "available_spaces",
        "occupancy_rate",
        "capacity_utilization",
        "availability_rate",
        "occupied_ratio",
        "available_ratio",
        "vacancy_ratio",
    )

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
    # Rate bounds
    # --------------------------------------------------------

    rate_columns = (
        "occupancy_rate",
        "capacity_utilization",
        "availability_rate",
        "occupied_ratio",
        "available_ratio",
        "vacancy_ratio",
    )

    for column in rate_columns:

        values = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

        valid_values = values.dropna()

        if (
            (valid_values < -occupancy_rate_tolerance)
            | (
                valid_values
                > 1.0
                + occupancy_rate_tolerance
            )
        ).any():

            errors.append(
                f"{column} contains values outside [0, 1]."
            )

    # --------------------------------------------------------
    # Capacity consistency
    # --------------------------------------------------------

    total = pd.to_numeric(
        dataframe["total_spaces"],
        errors="coerce",
    )

    occupied = pd.to_numeric(
        dataframe["occupied_spaces"],
        errors="coerce",
    )

    available = pd.to_numeric(
        dataframe["available_spaces"],
        errors="coerce",
    )

    difference = (
        occupied
        + available
        - total
    )

    inconsistent = (
        difference.abs()
        > occupancy_rate_tolerance
    )

    if inconsistent.any():

        errors.append(
            "occupied_spaces + available_spaces "
            "does not equal total_spaces for "
            f"{int(inconsistent.sum())} row(s)."
        )

    # --------------------------------------------------------
    # Capacity bounds
    # --------------------------------------------------------

    negative_occupied = (
        occupied < 0
    )

    if negative_occupied.any():

        errors.append(
            "occupied_spaces contains negative values."
        )

    exceeds_capacity = (
        occupied > total
    )

    if exceeds_capacity.any():

        errors.append(
            "occupied_spaces exceeds total_spaces "
            f"for {int(exceeds_capacity.sum())} row(s)."
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
    "OccupancyFeatureConfig",

    # Statistics/results
    "OccupancyFeatureStatistics",
    "OccupancyFeatureResult",

    # Exceptions
    "OccupancyFeatureError",
    "OccupancyFeatureSchemaError",
    "OccupancyFeatureDataError",
    "OccupancyFeatureConfigurationError",

    # Generator
    "OccupancyFeatureGenerator",

    # Constants
    "DEFAULT_TOTAL_SPACES_COLUMN",
    "DEFAULT_OCCUPIED_SPACES_COLUMN",
    "DEFAULT_AVAILABLE_SPACES_COLUMN",
    "DEFAULT_OCCUPANCY_RATE_COLUMN",
    "OCCUPANCY_FEATURE_COLUMNS",

    # Convenience functions
    "add_occupancy_features",
    "add_birmingham_occupancy_features",

    # Validation
    "validate_occupancy_features",
]