"""
SmartPark AI - Demand Features
==============================

Demand-oriented feature engineering for parking forecasting.

This module derives demand-state and parking-pressure features from
the CURRENT canonical parking observation only.

The module deliberately does NOT use:

    - target columns
    - future observations
    - lag features
    - rolling features
    - centered windows
    - forward lookups
    - cross-facility information
    - external data

This separation is intentional.

Feature families
----------------

occupancy_features.py
    Describes the current occupancy measurement.

demand_features.py
    Describes the current demand/pressure state.

lag_features.py
    Provides historical point-in-time observations.

rolling_features.py
    Provides historical aggregate behaviour.

temporal_features.py
    Provides time-of-day and timestamp context.

calendar_features.py
    Provides calendar context.

Design principles
-----------------

1. Current-observation only.
2. No target leakage.
3. No future-data leakage.
4. No historical lookup.
5. No cross-facility contamination.
6. No row removal.
7. Original row order preserved.
8. Deterministic output.
9. Explicit leakage metadata.
10. Safe handling of zero capacity.
11. Safe handling of missing values.
12. Safe handling of capacity violations.
13. Explicit demand-state classification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd


# ============================================================
# Constants
# ============================================================

DEFAULT_OCCUPANCY_RATE_COLUMN = (
    "occupancy_rate"
)

DEFAULT_TOTAL_SPACES_COLUMN = (
    "total_spaces"
)

DEFAULT_OCCUPIED_SPACES_COLUMN = (
    "occupied_spaces"
)

DEFAULT_AVAILABLE_SPACES_COLUMN = (
    "available_spaces"
)


# Demand-state thresholds.
#
# These thresholds are deliberately configuration-driven rather
# than hard-coded into the transformation logic.
#
# The interpretation is:
#
#   0.00 - < 0.25  LOW
#   0.25 - < 0.50  MODERATE
#   0.50 - < 0.75  HIGH
#   0.75 - < 0.90  VERY_HIGH
#   0.90 - 1.00   CRITICAL
#
# Values above 1.0 are retained as CAPACITY_EXCEEDED rather
# than silently forced into the normal demand bands.

DEFAULT_LOW_THRESHOLD = 0.25
DEFAULT_MODERATE_THRESHOLD = 0.50
DEFAULT_HIGH_THRESHOLD = 0.75
DEFAULT_VERY_HIGH_THRESHOLD = 0.90


# ============================================================
# Exceptions
# ============================================================


class DemandFeatureError(ValueError):
    """Base exception for demand feature processing."""


class DemandFeatureConfigurationError(
    DemandFeatureError
):
    """Raised when demand configuration is invalid."""


class DemandFeatureDataError(
    DemandFeatureError
):
    """Raised when input data is unsuitable."""


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True)
class DemandFeatureConfig:
    """
    Configuration for demand feature generation.
    """

    occupancy_rate_column: str = (
        DEFAULT_OCCUPANCY_RATE_COLUMN
    )

    total_spaces_column: str = (
        DEFAULT_TOTAL_SPACES_COLUMN
    )

    occupied_spaces_column: str = (
        DEFAULT_OCCUPIED_SPACES_COLUMN
    )

    available_spaces_column: str = (
        DEFAULT_AVAILABLE_SPACES_COLUMN
    )

    feature_prefix: str = ""

    low_threshold: float = (
        DEFAULT_LOW_THRESHOLD
    )

    moderate_threshold: float = (
        DEFAULT_MODERATE_THRESHOLD
    )

    high_threshold: float = (
        DEFAULT_HIGH_THRESHOLD
    )

    very_high_threshold: float = (
        DEFAULT_VERY_HIGH_THRESHOLD
    )

    near_full_threshold: float = 0.90

    full_threshold: float = 1.00

    low_availability_threshold: float = 0.10

    critical_availability_threshold: float = 0.05

    add_demand_level: bool = True

    add_demand_pressure: bool = True

    add_availability_pressure: bool = True

    add_capacity_state: bool = True

    add_demand_classification: bool = True

    add_binary_indicators: bool = True

    add_consistency_features: bool = True

    strict_validation: bool = True

    preserve_original_order: bool = True

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:

        if not self.occupancy_rate_column:
            raise DemandFeatureConfigurationError(
                "occupancy_rate_column cannot be empty."
            )

        if not self.total_spaces_column:
            raise DemandFeatureConfigurationError(
                "total_spaces_column cannot be empty."
            )

        if not self.occupied_spaces_column:
            raise DemandFeatureConfigurationError(
                "occupied_spaces_column cannot be empty."
            )

        if not self.available_spaces_column:
            raise DemandFeatureConfigurationError(
                "available_spaces_column cannot be empty."
            )

        thresholds = (
            self.low_threshold,
            self.moderate_threshold,
            self.high_threshold,
            self.very_high_threshold,
        )

        if not all(
            np.isfinite(x)
            for x in thresholds
        ):
            raise DemandFeatureConfigurationError(
                "Demand thresholds must be finite."
            )

        if not (
            0.0
            <= self.low_threshold
            < self.moderate_threshold
            < self.high_threshold
            < self.very_high_threshold
            <= 1.0
        ):
            raise DemandFeatureConfigurationError(
                "Demand thresholds must satisfy "
                "0 <= low < moderate < high < very_high <= 1."
            )

        for name, value in (
            (
                "near_full_threshold",
                self.near_full_threshold,
            ),
            (
                "full_threshold",
                self.full_threshold,
            ),
            (
                "low_availability_threshold",
                self.low_availability_threshold,
            ),
            (
                "critical_availability_threshold",
                self.critical_availability_threshold,
            ),
        ):

            if not np.isfinite(value):
                raise DemandFeatureConfigurationError(
                    f"{name} must be finite."
                )

            if not 0.0 <= value <= 1.0:
                raise DemandFeatureConfigurationError(
                    f"{name} must be between 0 and 1."
                )

        if (
            self.low_availability_threshold
            < self.critical_availability_threshold
        ):
            raise DemandFeatureConfigurationError(
                "critical_availability_threshold "
                "must be <= low_availability_threshold."
            )


# ============================================================
# Statistics
# ============================================================


@dataclass(frozen=True)
class DemandFeatureStatistics:
    """
    Statistics generated during demand feature creation.
    """

    source_row_count: int

    output_row_count: int

    source_column_count: int

    output_column_count: int

    feature_count: int

    invalid_occupancy_rate_count: int

    missing_occupancy_rate_count: int

    zero_capacity_count: int

    positive_capacity_count: int

    negative_capacity_count: int

    negative_occupied_count: int

    negative_available_count: int

    capacity_exceeded_count: int

    mathematically_inconsistent_count: int

    valid_demand_rows: int

    low_demand_count: int

    moderate_demand_count: int

    high_demand_count: int

    very_high_demand_count: int

    critical_demand_count: int

    missing_demand_classification_count: int

    low_availability_count: int

    critical_availability_count: int

    near_full_count: int

    full_count: int

    minimum_occupancy_rate: float | None

    maximum_occupancy_rate: float | None

    mean_occupancy_rate: float | None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True)
class DemandFeatureResult:
    """
    Result returned by demand feature generation.
    """

    dataframe: pd.DataFrame

    feature_columns: tuple[str, ...]

    statistics: DemandFeatureStatistics

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Utility
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


def _numeric_series(
    dataframe: pd.DataFrame,
    column: str,
) -> pd.Series:
    """
    Convert a source column to numeric safely.
    """

    return pd.to_numeric(
        dataframe[column],
        errors="coerce",
    ).astype("float64")


# ============================================================
# Generator
# ============================================================


class DemandFeatureGenerator:
    """
    Generate demand-state features from current observations.

    No historical or future observations are consulted.
    """

    def __init__(
        self,
        config: DemandFeatureConfig | None = None,
    ) -> None:

        self._config = (
            config
            or DemandFeatureConfig()
        )

    # ========================================================
    # Properties
    # ========================================================

    @property
    def config(
        self,
    ) -> DemandFeatureConfig:

        return self._config

    # ========================================================
    # Transform
    # ========================================================

    def transform(
        self,
        dataframe: pd.DataFrame,
    ) -> DemandFeatureResult:
        """
        Generate demand features.

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

        original_index = (
            dataframe.index.copy()
        )

        result = dataframe.copy(
            deep=True
        )

        config = self._config

        # ----------------------------------------------------
        # Current canonical values.
        # ----------------------------------------------------

        occupancy_rate = _numeric_series(
            result,
            config.occupancy_rate_column,
        )

        total_spaces = _numeric_series(
            result,
            config.total_spaces_column,
        )

        occupied_spaces = _numeric_series(
            result,
            config.occupied_spaces_column,
        )

        available_spaces = _numeric_series(
            result,
            config.available_spaces_column,
        )

        # ----------------------------------------------------
        # Basic validity masks.
        # ----------------------------------------------------

        valid_occupancy = (
            occupancy_rate.notna()
        )

        valid_capacity = (
            total_spaces.notna()
            & (
                total_spaces > 0
            )
        )

        zero_capacity = (
            total_spaces.eq(0)
        )

        negative_capacity = (
            total_spaces < 0
        )

        negative_occupied = (
            occupied_spaces < 0
        )

        negative_available = (
            available_spaces < 0
        )

        missing_occupancy = (
            occupancy_rate.isna()
        )

        invalid_occupancy_rate = (
            occupancy_rate.notna()
            & (
                (
                    occupancy_rate < 0
                )
                | (
                    occupancy_rate > 1
                )
            )
        )

        capacity_exceeded = (
            valid_capacity
            & occupied_spaces.notna()
            & (
                occupied_spaces
                > total_spaces
            )
        )

        # ----------------------------------------------------
        # Mathematically inconsistent occupancy.
        #
        # A valid parking record should satisfy:
        #
        #   occupied + available = capacity
        #
        # We allow a tiny floating-point tolerance.
        # ----------------------------------------------------

        consistency_tolerance = 1e-9

        mathematically_inconsistent = (
            total_spaces.notna()
            & occupied_spaces.notna()
            & available_spaces.notna()
            & (
                np.abs(
                    (
                        occupied_spaces
                        + available_spaces
                    )
                    - total_spaces
                )
                > consistency_tolerance
            )
        )

        # ----------------------------------------------------
        # Recalculate safe ratios from current observation.
        #
        # We deliberately do NOT fill zero-capacity ratios with
        # zero. Zero capacity means the ratio is undefined.
        # ----------------------------------------------------

        safe_capacity = total_spaces.where(
            total_spaces > 0
        )

        calculated_occupancy_rate = (
            occupied_spaces
            / safe_capacity
        )

        calculated_occupancy_rate = (
            calculated_occupancy_rate
            .replace(
                [
                    np.inf,
                    -np.inf,
                ],
                np.nan,
            )
        )

        calculated_availability_rate = (
            available_spaces
            / safe_capacity
        )

        calculated_availability_rate = (
            calculated_availability_rate
            .replace(
                [
                    np.inf,
                    -np.inf,
                ],
                np.nan,
            )
        )

        # ====================================================
        # Generated feature container
        # ====================================================

        generated: dict[
            str,
            pd.Series,
        ] = {}

        feature_columns: list[str] = []

        def add_feature(
            name: str,
            series: pd.Series,
        ) -> None:

            feature_name = _prefixed_name(
                config.feature_prefix,
                name,
            )

            generated[
                feature_name
            ] = series

            feature_columns.append(
                feature_name
            )

        # ====================================================
        # Demand level
        # ====================================================

        if config.add_demand_level:

            # Use the canonical occupancy rate as the primary
            # demand-level signal.
            #
            # This preserves any upstream quality handling and
            # avoids silently replacing the canonical value.
            add_feature(
                "demand_level",
                occupancy_rate,
            )

            # Independent calculation is retained as a
            # diagnostic feature.
            add_feature(
                "calculated_demand_level",
                calculated_occupancy_rate,
            )

        # ====================================================
        # Demand pressure
        # ====================================================

        if config.add_demand_pressure:

            # Pressure is represented by the current occupancy
            # relative to usable capacity.
            #
            # We do not clip this value because capacity
            # violations are useful information and are already
            # explicitly represented by flags below.
            add_feature(
                "demand_pressure",
                calculated_occupancy_rate,
            )

            # Excess demand pressure.
            #
            # Normal values are zero.
            # Capacity violations retain their positive excess.
            excess_pressure = (
                calculated_occupancy_rate
                - 1.0
            ).clip(
                lower=0
            )

            add_feature(
                "demand_excess_pressure",
                excess_pressure,
            )

            # Remaining capacity pressure.
            #
            # Higher values mean more parking pressure.
            remaining_pressure = (
                1.0
                - calculated_occupancy_rate
            )

            remaining_pressure = (
                remaining_pressure
                .where(
                    valid_capacity
                )
            )

            add_feature(
                "remaining_capacity_ratio",
                remaining_pressure,
            )

        # ====================================================
        # Availability pressure
        # ====================================================

        if config.add_availability_pressure:

            add_feature(
                "availability_rate",
                calculated_availability_rate,
            )

            availability_pressure = (
                1.0
                - calculated_availability_rate
            )

            availability_pressure = (
                availability_pressure
                .where(
                    valid_capacity
                )
            )

            add_feature(
                "availability_pressure",
                availability_pressure,
            )

            low_availability = (
                calculated_availability_rate
                .notna()
                & (
                    calculated_availability_rate
                    <= config.low_availability_threshold
                )
            )

            critical_availability = (
                calculated_availability_rate
                .notna()
                & (
                    calculated_availability_rate
                    <= config.critical_availability_threshold
                )
            )

            add_feature(
                "is_low_availability",
                low_availability.astype(
                    "boolean"
                ),
            )

            add_feature(
                "is_critical_availability",
                critical_availability.astype(
                    "boolean"
                ),
            )

        # ====================================================
        # Capacity state
        # ====================================================

        if config.add_capacity_state:

            add_feature(
                "capacity_utilization",
                calculated_occupancy_rate,
            )

            near_full = (
                calculated_occupancy_rate.notna()
                & (
                    calculated_occupancy_rate
                    >= config.near_full_threshold
                )
            )

            full = (
                calculated_occupancy_rate.notna()
                & (
                    calculated_occupancy_rate
                    >= config.full_threshold
                )
            )

            add_feature(
                "is_near_full",
                near_full.astype(
                    "boolean"
                ),
            )

            add_feature(
                "is_full",
                full.astype(
                    "boolean"
                ),
            )

            add_feature(
                "is_zero_capacity",
                zero_capacity.astype(
                    "boolean"
                ),
            )

            add_feature(
                "is_capacity_exceeded",
                capacity_exceeded.astype(
                    "boolean"
                ),
            )

        # ====================================================
        # Demand classification
        # ====================================================

        if config.add_demand_classification:

            demand_class = pd.Series(
                pd.NA,
                index=result.index,
                dtype="string",
            )

            demand_class.loc[
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    < config.low_threshold
                )
            ] = "LOW"

            demand_class.loc[
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.low_threshold
                )
                & (
                    occupancy_rate
                    < config.moderate_threshold
                )
            ] = "MODERATE"

            demand_class.loc[
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.moderate_threshold
                )
                & (
                    occupancy_rate
                    < config.high_threshold
                )
            ] = "HIGH"

            demand_class.loc[
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.high_threshold
                )
                & (
                    occupancy_rate
                    < config.very_high_threshold
                )
            ] = "VERY_HIGH"

            demand_class.loc[
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.very_high_threshold
                )
                & (
                    occupancy_rate
                    <= 1.0
                )
            ] = "CRITICAL"

            demand_class.loc[
                capacity_exceeded
            ] = "CAPACITY_EXCEEDED"

            add_feature(
                "demand_class",
                demand_class,
            )

            # Ordinal representation.
            #
            # This is useful for tree-based models and avoids
            # requiring the model to infer an arbitrary ordering
            # from string labels.
            demand_level_code = (
                pd.Series(
                    pd.NA,
                    index=result.index,
                    dtype="Int64",
                )
            )

            demand_level_code.loc[
                demand_class.eq("LOW")
            ] = 0

            demand_level_code.loc[
                demand_class.eq("MODERATE")
            ] = 1

            demand_level_code.loc[
                demand_class.eq("HIGH")
            ] = 2

            demand_level_code.loc[
                demand_class.eq("VERY_HIGH")
            ] = 3

            demand_level_code.loc[
                demand_class.eq("CRITICAL")
            ] = 4

            demand_level_code.loc[
                demand_class.eq(
                    "CAPACITY_EXCEEDED"
                )
            ] = 5

            add_feature(
                "demand_class_code",
                demand_level_code,
            )

        # ====================================================
        # Binary demand indicators
        # ====================================================

        if config.add_binary_indicators:

            is_low = (
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    < config.low_threshold
                )
            )

            is_moderate = (
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.low_threshold
                )
                & (
                    occupancy_rate
                    < config.moderate_threshold
                )
            )

            is_high = (
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.moderate_threshold
                )
                & (
                    occupancy_rate
                    < config.high_threshold
                )
            )

            is_very_high = (
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.high_threshold
                )
                & (
                    occupancy_rate
                    < config.very_high_threshold
                )
            )

            is_critical = (
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.very_high_threshold
                )
                & (
                    occupancy_rate
                    <= 1.0
                )
            )

            for name, series in (
                (
                    "is_low_demand",
                    is_low,
                ),
                (
                    "is_moderate_demand",
                    is_moderate,
                ),
                (
                    "is_high_demand",
                    is_high,
                ),
                (
                    "is_very_high_demand",
                    is_very_high,
                ),
                (
                    "is_critical_demand",
                    is_critical,
                ),
            ):

                add_feature(
                    name,
                    series.astype(
                        "boolean"
                    ),
                )

        # ====================================================
        # Consistency features
        # ====================================================

        if config.add_consistency_features:

            # Whether occupancy rate agrees with the
            # independently calculated occupied/capacity ratio.
            occupancy_consistent = (
                occupancy_rate.notna()
                & calculated_occupancy_rate.notna()
                & (
                    np.abs(
                        occupancy_rate
                        - calculated_occupancy_rate
                    )
                    <= consistency_tolerance
                )
            )

            add_feature(
                "occupancy_rate_consistent",
                occupancy_consistent.astype(
                    "boolean"
                ),
            )

            add_feature(
                "space_count_consistent",
                (
                    ~mathematically_inconsistent
                    & total_spaces.notna()
                    & occupied_spaces.notna()
                    & available_spaces.notna()
                ).astype(
                    "boolean"
                ),
            )

            add_feature(
                "has_valid_capacity",
                valid_capacity.astype(
                    "boolean"
                ),
            )

            add_feature(
                "has_valid_occupancy",
                (
                    valid_occupancy
                    & ~invalid_occupancy_rate
                ).astype(
                    "boolean"
                ),
            )

            add_feature(
                "has_negative_values",
                (
                    negative_capacity
                    | negative_occupied
                    | negative_available
                ).astype(
                    "boolean"
                ),
            )

            add_feature(
                "has_capacity_violation",
                capacity_exceeded.astype(
                    "boolean"
                ),
            )

            add_feature(
                "has_consistency_issue",
                (
                    mathematically_inconsistent
                    | invalid_occupancy_rate
                    | negative_capacity
                    | negative_occupied
                    | negative_available
                    | capacity_exceeded
                ).astype(
                    "boolean"
                ),
            )

        # ====================================================
        # Materialize
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

        # ----------------------------------------------------
        # Preserve original row order.
        # ----------------------------------------------------

        if config.preserve_original_order:

            result = result.loc[
                original_index
            ]

        # ====================================================
        # Statistics
        # ====================================================

        valid_rates = (
            occupancy_rate[
                occupancy_rate.notna()
                & ~invalid_occupancy_rate
            ]
        )

        if valid_rates.empty:

            minimum_occupancy_rate = None

            maximum_occupancy_rate = None

            mean_occupancy_rate = None

        else:

            minimum_occupancy_rate = float(
                valid_rates.min()
            )

            maximum_occupancy_rate = float(
                valid_rates.max()
            )

            mean_occupancy_rate = float(
                valid_rates.mean()
            )

        low_demand_count = int(
            (
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    < config.low_threshold
                )
            ).sum()
        )

        moderate_demand_count = int(
            (
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.low_threshold
                )
                & (
                    occupancy_rate
                    < config.moderate_threshold
                )
            ).sum()
        )

        high_demand_count = int(
            (
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.moderate_threshold
                )
                & (
                    occupancy_rate
                    < config.high_threshold
                )
            ).sum()
        )

        very_high_demand_count = int(
            (
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.high_threshold
                )
                & (
                    occupancy_rate
                    < config.very_high_threshold
                )
            ).sum()
        )

        critical_demand_count = int(
            (
                occupancy_rate.notna()
                & (
                    occupancy_rate
                    >= config.very_high_threshold
                )
                & (
                    occupancy_rate
                    <= 1.0
                )
            ).sum()
        )

        low_availability_count = int(
            (
                calculated_availability_rate.notna()
                & (
                    calculated_availability_rate
                    <= config.low_availability_threshold
                )
            ).sum()
        )

        critical_availability_count = int(
            (
                calculated_availability_rate.notna()
                & (
                    calculated_availability_rate
                    <= config.critical_availability_threshold
                )
            ).sum()
        )

        near_full_count = int(
            (
                calculated_occupancy_rate.notna()
                & (
                    calculated_occupancy_rate
                    >= config.near_full_threshold
                )
            ).sum()
        )

        full_count = int(
            (
                calculated_occupancy_rate.notna()
                & (
                    calculated_occupancy_rate
                    >= config.full_threshold
                )
            ).sum()
        )

        valid_demand_rows = int(
            (
                occupancy_rate.notna()
                & ~invalid_occupancy_rate
                & valid_capacity
            ).sum()
        )

        missing_demand_classification_count = int(
            (
                occupancy_rate.isna()
                | invalid_occupancy_rate
                | negative_capacity
            ).sum()
        )

        # ====================================================
        # Metadata
        # ====================================================

        metadata = {
            "feature_family":
                "demand",

            "source_name":
                "BIRMINGHAM",

            "future_data_used":
                False,

            "target_data_used":
                False,

            "historical_values_used":
                False,

            "cross_facility_data_used":
                False,

            "forward_lookup_used":
                False,

            "centered_windows_used":
                False,

            "rolling_windows_used":
                False,

            "lag_features_used":
                False,

            "external_data_used":
                False,

            "current_observation_only":
                True,

            "source_rows_preserved":
                len(result)
                == source_row_count,

            "row_order_preserved":
                True,

            "data_modified":
                False,

            "zero_capacity_safe":
                True,

            "capacity_violations_retained":
                True,

            "missing_values_filled":
                False,

            "thresholds": {
                "low":
                    config.low_threshold,

                "moderate":
                    config.moderate_threshold,

                "high":
                    config.high_threshold,

                "very_high":
                    config.very_high_threshold,

                "near_full":
                    config.near_full_threshold,

                "full":
                    config.full_threshold,

                "low_availability":
                    config.low_availability_threshold,

                "critical_availability":
                    config.critical_availability_threshold,
            },

            **config.metadata,
        }

        statistics = DemandFeatureStatistics(
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

            invalid_occupancy_rate_count=
                int(
                    invalid_occupancy_rate.sum()
                ),

            missing_occupancy_rate_count=
                int(
                    missing_occupancy.sum()
                ),

            zero_capacity_count=
                int(
                    zero_capacity.sum()
                ),

            positive_capacity_count=
                int(
                    valid_capacity.sum()
                ),

            negative_capacity_count=
                int(
                    negative_capacity.sum()
                ),

            negative_occupied_count=
                int(
                    negative_occupied.sum()
                ),

            negative_available_count=
                int(
                    negative_available.sum()
                ),

            capacity_exceeded_count=
                int(
                    capacity_exceeded.sum()
                ),

            mathematically_inconsistent_count=
                int(
                    mathematically_inconsistent.sum()
                ),

            valid_demand_rows=
                valid_demand_rows,

            low_demand_count=
                low_demand_count,

            moderate_demand_count=
                moderate_demand_count,

            high_demand_count=
                high_demand_count,

            very_high_demand_count=
                very_high_demand_count,

            critical_demand_count=
                critical_demand_count,

            missing_demand_classification_count=
                missing_demand_classification_count,

            low_availability_count=
                low_availability_count,

            critical_availability_count=
                critical_availability_count,

            near_full_count=
                near_full_count,

            full_count=
                full_count,

            minimum_occupancy_rate=
                minimum_occupancy_rate,

            maximum_occupancy_rate=
                maximum_occupancy_rate,

            mean_occupancy_rate=
                mean_occupancy_rate,

            metadata=metadata,
        )

        return DemandFeatureResult(
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
        Validate the source dataframe.
        """

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise DemandFeatureDataError(
                "Input must be a pandas DataFrame."
            )

        if dataframe.empty:
            raise DemandFeatureDataError(
                "Input dataframe is empty."
            )

        required_columns = (
            self._config
            .occupancy_rate_column,
            self._config
            .total_spaces_column,
            self._config
            .occupied_spaces_column,
            self._config
            .available_spaces_column,
        )

        missing_columns = [
            column
            for column in required_columns
            if column not in dataframe.columns
        ]

        if missing_columns:

            raise DemandFeatureDataError(
                "Missing required demand columns: "
                f"{missing_columns}"
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

            raise DemandFeatureDataError(
                "Duplicate input columns detected: "
                f"{duplicates}"
            )


# ============================================================
# Expected feature columns
# ============================================================


def expected_demand_feature_columns(
    config: DemandFeatureConfig | None = None,
) -> tuple[str, ...]:
    """
    Return expected demand feature names.
    """

    config = (
        config
        or DemandFeatureConfig()
    )

    names: list[str] = []

    def add(
        name: str,
    ) -> None:

        names.append(
            _prefixed_name(
                config.feature_prefix,
                name,
            )
        )

    if config.add_demand_level:

        add(
            "demand_level"
        )

        add(
            "calculated_demand_level"
        )

    if config.add_demand_pressure:

        add(
            "demand_pressure"
        )

        add(
            "demand_excess_pressure"
        )

        add(
            "remaining_capacity_ratio"
        )

    if config.add_availability_pressure:

        add(
            "availability_rate"
        )

        add(
            "availability_pressure"
        )

        add(
            "is_low_availability"
        )

        add(
            "is_critical_availability"
        )

    if config.add_capacity_state:

        add(
            "capacity_utilization"
        )

        add(
            "is_near_full"
        )

        add(
            "is_full"
        )

        add(
            "is_zero_capacity"
        )

        add(
            "is_capacity_exceeded"
        )

    if config.add_demand_classification:

        add(
            "demand_class"
        )

        add(
            "demand_class_code"
        )

    if config.add_binary_indicators:

        add(
            "is_low_demand"
        )

        add(
            "is_moderate_demand"
        )

        add(
            "is_high_demand"
        )

        add(
            "is_very_high_demand"
        )

        add(
            "is_critical_demand"
        )

    if config.add_consistency_features:

        add(
            "occupancy_rate_consistent"
        )

        add(
            "space_count_consistent"
        )

        add(
            "has_valid_capacity"
        )

        add(
            "has_valid_occupancy"
        )

        add(
            "has_negative_values"
        )

        add(
            "has_capacity_violation"
        )

        add(
            "has_consistency_issue"
        )

    return tuple(names)


# ============================================================
# Validation
# ============================================================


def validate_demand_features(
    dataframe: pd.DataFrame,
    *,
    config: DemandFeatureConfig | None = None,
) -> dict[str, Any]:
    """
    Validate generated demand features.

    Validation is capacity-aware.

    Normal observations must satisfy the expected [0, 1]
    bounds for availability-related ratios.

    Capacity-violation observations are intentionally retained
    by the feature generator. For those rows, mathematically
    expected out-of-range availability values are permitted and
    are validated against the capacity-violation state instead
    of being incorrectly reported as feature-generation errors.

    The validator does NOT modify the dataframe.
    """

    config = (
        config
        or DemandFeatureConfig()
    )

    errors: list[str] = []
    warnings: list[str] = []

    expected = (
        expected_demand_feature_columns(
            config
        )
    )

    # ========================================================
    # Basic dataframe validation
    # ========================================================

    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):

        return {
            "valid": False,
            "errors": [
                "Input must be a pandas DataFrame."
            ],
            "warnings": [],
            "missing_columns": [],
            "expected_feature_count": len(
                expected
            ),
            "actual_feature_count": 0,
            "row_count": 0,
            "future_data_used": False,
            "target_data_used": False,
            "historical_values_used": False,
            "cross_facility_data_used": False,
            "forward_lookup_used": False,
            "centered_windows_used": False,
            "rolling_windows_used": False,
            "lag_features_used": False,
            "current_observation_only": True,
        }

    # ========================================================
    # Missing columns
    # ========================================================

    missing_columns = [
        column
        for column in expected
        if column not in dataframe.columns
    ]

    if missing_columns:

        errors.append(
            "Missing demand feature columns: "
            f"{missing_columns}"
        )

    # ========================================================
    # Duplicate columns
    # ========================================================

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

    # ========================================================
    # Capacity-violation mask
    #
    # These rows are intentionally retained by the feature
    # generator.
    # ========================================================

    capacity_violation_column = (
        _prefixed_name(
            config.feature_prefix,
            "is_capacity_exceeded",
        )
    )

    if (
        capacity_violation_column
        in dataframe.columns
    ):

        capacity_violation = (
            dataframe[
                capacity_violation_column
            ]
            .fillna(False)
            .astype(bool)
        )

    else:

        # If the indicator is missing, treat all rows as
        # normal for the purpose of ratio validation.
        #
        # The missing feature itself will already be reported
        # above.
        capacity_violation = pd.Series(
            False,
            index=dataframe.index,
            dtype=bool,
        )

    normal_rows = (
        ~capacity_violation
    )

    violation_rows = (
        capacity_violation
    )

    # ========================================================
    # Numeric features
    # ========================================================

    numeric_feature_names = (
        "demand_level",
        "calculated_demand_level",
        "demand_pressure",
        "demand_excess_pressure",
        "remaining_capacity_ratio",
        "availability_rate",
        "availability_pressure",
        "capacity_utilization",
        "demand_class_code",
    )

    for base_name in (
        numeric_feature_names
    ):

        column = _prefixed_name(
            config.feature_prefix,
            base_name,
        )

        if column not in dataframe.columns:
            continue

        values = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

        finite_values = values.dropna()

        if finite_values.empty:
            continue

        # ----------------------------------------------------
        # Infinite values are never acceptable.
        # ----------------------------------------------------

        if np.isinf(
            finite_values.to_numpy(
                dtype="float64"
            )
        ).any():

            errors.append(
                f"Demand feature '{column}' "
                "contains infinite values."
            )

    # ========================================================
    # Ratio bounds
    #
    # IMPORTANT:
    #
    # Normal observations:
    #     0 <= ratio <= 1
    #
    # Capacity violations:
    #     mathematically expected out-of-range values are
    #     permitted, because occupied_spaces > total_spaces
    #     can legitimately produce:
    #
    #         availability_rate < 0
    #
    #         remaining_capacity_ratio < 0
    #
    #         availability_pressure > 1
    #
    # We therefore validate the two populations separately.
    # ========================================================

    bounded_ratio_columns = (
        "availability_rate",
        "remaining_capacity_ratio",
        "availability_pressure",
    )

    for base_name in (
        bounded_ratio_columns
    ):

        column = _prefixed_name(
            config.feature_prefix,
            base_name,
        )

        if column not in dataframe.columns:
            continue

        values = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

        # ----------------------------------------------------
        # Normal rows must remain within [0, 1].
        # ----------------------------------------------------

        normal_values = (
            values.loc[
                normal_rows
            ]
            .dropna()
        )

        if not normal_values.empty:

            invalid_normal = (
                (
                    normal_values
                    < -1e-9
                )
                | (
                    normal_values
                    > 1.000000001
                )
            )

            invalid_count = int(
                invalid_normal.sum()
            )

            if invalid_count > 0:

                errors.append(
                    f"Demand feature '{column}' "
                    f"contains {invalid_count} "
                    "normal observation(s) "
                    "outside [0, 1]."
                )

        # ----------------------------------------------------
        # Capacity-violation rows.
        #
        # Do NOT simply apply [0,1] here.
        #
        # Instead, verify that any out-of-range values are
        # actually associated with the known capacity
        # violation.
        # ----------------------------------------------------

        violation_values = (
            values.loc[
                violation_rows
            ]
            .dropna()
        )

        if violation_values.empty:
            continue

        # ----------------------------------------------------
        # There should not be impossible NaN/inf behaviour.
        # Infinite values were already checked above.
        #
        # Out-of-range values are permitted here.
        # ----------------------------------------------------

        if base_name in {
            "availability_rate",
            "remaining_capacity_ratio",
        }:

            negative_count = int(
                (
                    violation_values
                    < -1e-9
                ).sum()
            )

            if negative_count > 0:

                warnings.append(
                    f"Demand feature '{column}' "
                    f"contains {negative_count} "
                    "negative value(s) on retained "
                    "capacity-violation rows."
                )

        elif (
            base_name
            == "availability_pressure"
        ):

            elevated_count = int(
                (
                    violation_values
                    > 1.000000001
                ).sum()
            )

            if elevated_count > 0:

                warnings.append(
                    f"Demand feature '{column}' "
                    f"contains {elevated_count} "
                    "value(s) above 1 on retained "
                    "capacity-violation rows."
                )

    # ========================================================
    # Capacity-violation consistency
    #
    # Every row marked as capacity exceeded should actually
    # satisfy:
    #
    #     occupied_spaces > total_spaces
    #
    # This prevents the indicator itself from becoming
    # internally inconsistent.
    # ========================================================

    occupied_column = (
        config.occupied_spaces_column
    )

    capacity_column = (
        config.total_spaces_column
    )

    if (
        occupied_column
        in dataframe.columns
        and capacity_column
        in dataframe.columns
        and capacity_violation_column
        in dataframe.columns
    ):

        occupied_values = pd.to_numeric(
            dataframe[
                occupied_column
            ],
            errors="coerce",
        )

        capacity_values = pd.to_numeric(
            dataframe[
                capacity_column
            ],
            errors="coerce",
        )

        expected_capacity_violation = (
            occupied_values.notna()
            & capacity_values.notna()
            & (
                occupied_values
                > capacity_values
            )
        )

        mismatch = (
            capacity_violation
            != expected_capacity_violation
        )

        mismatch_count = int(
            mismatch.sum()
        )

        if mismatch_count > 0:

            errors.append(
                "Capacity-violation indicator "
                f"'{capacity_violation_column}' "
                f"does not agree with occupied/capacity "
                f"values for {mismatch_count} row(s)."
            )

    # ========================================================
    # Boolean feature dtypes
    # ========================================================

    boolean_bases = [
        name
        for name in expected
        if name.startswith(
            _prefixed_name(
                config.feature_prefix,
                "is_",
            )
        )
        or name.startswith(
            _prefixed_name(
                config.feature_prefix,
                "has_",
            )
        )
        or name.endswith(
            "consistent"
        )
        or name.endswith(
            "consistency_issue"
        )
    ]

    for column in boolean_bases:

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
                f"Demand indicator '{column}' "
                f"has unexpected dtype {dtype}."
            )

    # ========================================================
    # Classification validation
    # ========================================================

    class_column = _prefixed_name(
        config.feature_prefix,
        "demand_class",
    )

    if class_column in dataframe.columns:

        valid_classes = {
            "LOW",
            "MODERATE",
            "HIGH",
            "VERY_HIGH",
            "CRITICAL",
            "CAPACITY_EXCEEDED",
        }

        observed_classes = set(
            dataframe[
                class_column
            ]
            .dropna()
            .astype(str)
            .unique()
        )

        unexpected_classes = (
            observed_classes
            - valid_classes
        )

        if unexpected_classes:

            errors.append(
                "Unexpected demand classes: "
                f"{sorted(unexpected_classes)}"
            )

        # ----------------------------------------------------
        # Capacity violations should be classified as
        # CAPACITY_EXCEEDED.
        # ----------------------------------------------------

        if (
            capacity_violation_column
            in dataframe.columns
        ):

            incorrectly_classified = (
                capacity_violation
                & dataframe[
                    class_column
                ].fillna(
                    "__MISSING__"
                ).ne(
                    "CAPACITY_EXCEEDED"
                )
            )

            incorrectly_classified_count = int(
                incorrectly_classified.sum()
            )

            if (
                incorrectly_classified_count
                > 0
            ):

                errors.append(
                    "Capacity-violation rows must "
                    "have demand_class='CAPACITY_EXCEEDED'. "
                    f"Found {incorrectly_classified_count} "
                    "incorrectly classified row(s)."
                )

    # ========================================================
    # Classification / capacity summary
    # ========================================================

    capacity_violation_count = int(
        capacity_violation.sum()
    )

    normal_row_count = int(
        normal_rows.sum()
    )

    # ========================================================
    # Leakage contract
    # ========================================================

    return {
        "valid":
            not errors,

        "errors":
            errors,

        "warnings":
            warnings,

        "missing_columns":
            missing_columns,

        "expected_feature_count":
            len(expected),

        "actual_feature_count":
            len(
                [
                    column
                    for column in expected
                    if column
                    in dataframe.columns
                ]
            ),

        "row_count":
            len(dataframe),

        "normal_row_count":
            normal_row_count,

        "capacity_violation_count":
            capacity_violation_count,

        "future_data_used":
            False,

        "target_data_used":
            False,

        "historical_values_used":
            False,

        "cross_facility_data_used":
            False,

        "forward_lookup_used":
            False,

        "centered_windows_used":
            False,

        "rolling_windows_used":
            False,

        "lag_features_used":
            False,

        "current_observation_only":
            True,
    }


# ============================================================
# Convenience API
# ============================================================


def add_demand_features(
    dataframe: pd.DataFrame,
    *,
    config: DemandFeatureConfig | None = None,
) -> DemandFeatureResult:
    """
    Add demand features using the supplied configuration.
    """

    generator = DemandFeatureGenerator(
        config=config
    )

    return generator.transform(
        dataframe
    )


# ============================================================
# Birmingham API
# ============================================================


def add_birmingham_demand_features(
    dataframe: pd.DataFrame,
) -> DemandFeatureResult:
    """
    Generate the standard Birmingham demand feature set.
    """

    config = DemandFeatureConfig(
        occupancy_rate_column=(
            "occupancy_rate"
        ),

        total_spaces_column=(
            "total_spaces"
        ),

        occupied_spaces_column=(
            "occupied_spaces"
        ),

        available_spaces_column=(
            "available_spaces"
        ),

        feature_prefix="",

        low_threshold=0.25,

        moderate_threshold=0.50,

        high_threshold=0.75,

        very_high_threshold=0.90,

        near_full_threshold=0.90,

        full_threshold=1.00,

        low_availability_threshold=0.10,

        critical_availability_threshold=0.05,

        add_demand_level=True,

        add_demand_pressure=True,

        add_availability_pressure=True,

        add_capacity_state=True,

        add_demand_classification=True,

        add_binary_indicators=True,

        add_consistency_features=True,

        strict_validation=True,

        preserve_original_order=True,

        metadata={
            "source_name":
                "BIRMINGHAM",

            "feature_family":
                "demand",

            "current_observation_only":
                True,
        },
    )

    return add_demand_features(
        dataframe,
        config=config,
    )


# ============================================================
# Public exports
# ============================================================


__all__ = [
    "DemandFeatureError",
    "DemandFeatureConfigurationError",
    "DemandFeatureDataError",
    "DemandFeatureConfig",
    "DemandFeatureStatistics",
    "DemandFeatureResult",
    "DemandFeatureGenerator",
    "expected_demand_feature_columns",
    "validate_demand_features",
    "add_demand_features",
    "add_birmingham_demand_features",
]