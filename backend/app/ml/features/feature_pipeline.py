"""
SmartPark AI - Feature Engineering Pipeline
============================================

Central orchestration layer for the SmartPark AI feature-engineering
stack.

Feature families
----------------

    temporal_features.py
        Timestamp-derived features.

    calendar_features.py
        Calendar/date-context features.

    occupancy_features.py
        Current occupancy and capacity features.

    demand_features.py
        Current demand-pressure features.

    lag_features.py
        Historical point-in-time features.

    rolling_features.py
        Historical rolling-window features.

This module DOES NOT independently calculate model features.

Its responsibilities are:

    1. Build/receive the ML dataset.
    2. Apply feature families in a deterministic order.
    3. Preserve source rows.
    4. Preserve row order.
    5. Prevent target leakage.
    6. Prevent future-data leakage.
    7. Prevent cross-facility contamination.
    8. Verify feature uniqueness.
    9. Verify expected columns.
   10. Separate model features from metadata and targets.
   11. Produce a final model-ready dataframe.
   12. Expose detailed pipeline statistics.

Leakage contract
----------------

The pipeline must satisfy:

    future_data_used       == False
    target_data_used       == False
    cross_facility_data    == False
    forward_lookup_used    == False
    centered_windows_used  == False

Important
---------

Target columns are intentionally RETAINED in the final dataframe
for supervised learning.

They are NOT included in:

    - feature_columns
    - model input columns
    - feature engineering calculations

This distinction is critical.

The pipeline therefore produces:

    result.dataframe
        Complete ML dataset + engineered features + targets.

    result.feature_columns
        Columns that may be supplied to a model.

    result.target_columns
        Supervised learning targets.

    result.metadata_columns
        Identifiers, timestamps and operational metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import numpy as np
import pandas as pd

from app.ml.data.dataset_builder import (
    build_birmingham_ml_dataset,
)

from app.ml.features.temporal_features import (
    TemporalFeatureConfig,
    TemporalFeatureResult,
    add_temporal_features,
)

from app.ml.features.calendar_features import (
    CalendarFeatureConfig,
    CalendarFeatureResult,
    add_calendar_features,
)

from app.ml.features.occupancy_features import (
    OccupancyFeatureConfig,
    OccupancyFeatureResult,
    add_occupancy_features,
)

from app.ml.features.demand_features import (
    DemandFeatureConfig,
    DemandFeatureResult,
    add_demand_features,
)

from app.ml.features.lag_features import (
    LagFeatureConfig,
    LagFeatureResult,
    add_lag_features,
)

from app.ml.features.rolling_features import (
    RollingFeatureConfig,
    RollingFeatureResult,
    add_rolling_features,
)


# ============================================================
# Constants
# ============================================================


DEFAULT_TIMESTAMP_COLUMN = (
    "normalized_at"
)

DEFAULT_FACILITY_COLUMN = (
    "source_facility_code"
)


# ------------------------------------------------------------
# Target columns.
#
# These are targets, NOT model input features.
# ------------------------------------------------------------

DEFAULT_TARGET_COLUMNS = (
    "target_occupancy_rate_30m",
    "target_occupancy_rate_1h",
    "target_occupancy_rate_2h",
    "target_tomorrow_morning_demand",
)


DEFAULT_TARGET_AVAILABILITY_COLUMNS = (
    "target_30m_available",
    "target_1h_available",
    "target_2h_available",
    "target_tomorrow_morning_available",
)


DEFAULT_TARGET_SUPPORT_COLUMNS = (
    "target_exclusion_reason",
)


# ------------------------------------------------------------
# Operational / metadata columns.
# ------------------------------------------------------------

DEFAULT_METADATA_COLUMNS = (
    "source_facility_code",
    "normalized_at",
    "observation_present",
    "gap_status",
    "is_operational_gap",
    "is_data_gap",
    "sequence_break",
    "is_eligible_for_sequence",
    "quality_status",
    "quality_flags",
    "source",
)


# ============================================================
# Exceptions
# ============================================================


class FeaturePipelineError(
    ValueError
):
    """Base exception for feature pipeline errors."""


class FeaturePipelineConfigurationError(
    FeaturePipelineError
):
    """Raised when pipeline configuration is invalid."""


class FeaturePipelineDataError(
    FeaturePipelineError
):
    """Raised when pipeline input is invalid."""


class FeaturePipelineLeakageError(
    FeaturePipelineError
):
    """Raised when a feature family violates the leakage contract."""


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True)
class FeaturePipelineConfig:
    """
    Configuration for the complete feature pipeline.
    """

    timestamp_column: str = (
        DEFAULT_TIMESTAMP_COLUMN
    )

    facility_column: str = (
        DEFAULT_FACILITY_COLUMN
    )

    target_columns: tuple[str, ...] = (
        DEFAULT_TARGET_COLUMNS
    )

    target_availability_columns: tuple[
        str, ...
    ] = (
        DEFAULT_TARGET_AVAILABILITY_COLUMNS
    )

    target_support_columns: tuple[
        str, ...
    ] = (
        DEFAULT_TARGET_SUPPORT_COLUMNS
    )

    metadata_columns: tuple[
        str, ...
    ] = (
        DEFAULT_METADATA_COLUMNS
    )

    include_temporal: bool = True

    include_calendar: bool = True

    include_occupancy: bool = True

    include_demand: bool = True

    include_lag: bool = True

    include_rolling: bool = True

    strict_leakage_validation: bool = True

    strict_row_validation: bool = True

    preserve_row_order: bool = True

    preserve_source_columns: bool = True

    fail_on_duplicate_features: bool = True

    fail_on_feature_target_overlap: bool = True

    fail_on_feature_metadata_overlap: bool = False

    temporal_config: TemporalFeatureConfig | None = None

    calendar_config: CalendarFeatureConfig | None = None

    occupancy_config: OccupancyFeatureConfig | None = None

    demand_config: DemandFeatureConfig | None = None

    lag_config: LagFeatureConfig | None = None

    rolling_config: RollingFeatureConfig | None = None

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:

        if not self.timestamp_column:
            raise FeaturePipelineConfigurationError(
                "timestamp_column cannot be empty."
            )

        if not self.facility_column:
            raise FeaturePipelineConfigurationError(
                "facility_column cannot be empty."
            )

        if (
            len(
                set(self.target_columns)
            )
            != len(self.target_columns)
        ):

            raise FeaturePipelineConfigurationError(
                "target_columns contains duplicates."
            )

        if (
            len(
                set(
                    self.target_availability_columns
                )
            )
            != len(
                self.target_availability_columns
            )
        ):

            raise FeaturePipelineConfigurationError(
                "target_availability_columns contains duplicates."
            )

        if (
            len(
                set(
                    self.metadata_columns
                )
            )
            != len(
                self.metadata_columns
            )
        ):

            raise FeaturePipelineConfigurationError(
                "metadata_columns contains duplicates."
            )


# ============================================================
# Statistics
# ============================================================


@dataclass(frozen=True)
class FeaturePipelineStatistics:
    """
    Complete pipeline statistics.
    """

    source_row_count: int

    final_row_count: int

    source_column_count: int

    final_column_count: int

    feature_count: int

    target_count: int

    target_availability_count: int

    metadata_column_count: int

    temporal_feature_count: int

    calendar_feature_count: int

    occupancy_feature_count: int

    demand_feature_count: int

    lag_feature_count: int

    rolling_feature_count: int

    duplicate_feature_count: int

    invalid_timestamp_count: int

    missing_feature_count: int

    facility_count: int

    observed_row_count: int

    missing_row_count: int

    fully_supervised_rows: int

    partially_supervised_rows: int

    unsupervised_rows: int

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Result
# ============================================================


@dataclass(frozen=True)
class FeaturePipelineResult:
    """
    Complete feature-engineering result.
    """

    dataframe: pd.DataFrame

    feature_columns: tuple[str, ...]

    target_columns: tuple[str, ...]

    target_availability_columns: tuple[
        str, ...
    ]

    metadata_columns: tuple[str, ...]

    statistics: FeaturePipelineStatistics

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    temporal_result: TemporalFeatureResult | None = None

    calendar_result: CalendarFeatureResult | None = None

    occupancy_result: OccupancyFeatureResult | None = None

    demand_result: DemandFeatureResult | None = None

    lag_result: LagFeatureResult | None = None

    rolling_result: RollingFeatureResult | None = None

    dataset_result: Any | None = None


# ============================================================
# Pipeline
# ============================================================


class FeaturePipeline:
    """
    Orchestrate all SmartPark AI feature families.

    The pipeline is intentionally deterministic and leakage-aware.
    """

    def __init__(
        self,
        config: FeaturePipelineConfig | None = None,
    ) -> None:

        self._config = (
            config
            or FeaturePipelineConfig()
        )

    # ========================================================
    # Properties
    # ========================================================

    @property
    def config(
        self,
    ) -> FeaturePipelineConfig:

        return self._config

    # ========================================================
    # Transform
    # ========================================================

    def transform(
        self,
        dataframe: pd.DataFrame,
    ) -> FeaturePipelineResult:
        """
        Run the complete feature pipeline on an existing ML
        dataset dataframe.
        """

        self._validate_input(
            dataframe
        )

        config = self._config

        source_row_count = len(
            dataframe
        )

        source_column_count = len(
            dataframe.columns
        )

        original_index = (
            dataframe.index.copy()
        )

        original_columns = tuple(
            dataframe.columns
        )

        # ----------------------------------------------------
        # Never mutate caller's dataframe.
        # ----------------------------------------------------

        result = dataframe.copy(
            deep=True
        )

        # ------------------------------------------------------------
        # Canonical source dataframe.
        #
        # Every feature family operates independently against this
        # canonical ML dataset. Generated features are merged into
        # `result` only after each family completes.
        #
        # This prevents feature-family output columns from becoming
        # accidental input columns for another feature family.
        # ------------------------------------------------------------

        canonical_input = dataframe.copy(
            deep=True
        )

        # ====================================================
        # Feature-family results
        # ====================================================

        temporal_result = None
        calendar_result = None
        occupancy_result = None
        demand_result = None
        lag_result = None
        rolling_result = None

        temporal_columns: tuple[
            str, ...
        ] = ()

        calendar_columns: tuple[
            str, ...
        ] = ()

        occupancy_columns: tuple[
            str, ...
        ] = ()

        demand_columns: tuple[
            str, ...
        ] = ()

        lag_columns: tuple[
            str, ...
        ] = ()

        rolling_columns: tuple[
            str, ...
        ] = ()

        # ====================================================
        # Feature-family isolation
        # ====================================================
        #
        # Every feature family receives the same canonical ML
        # dataset. A family's generated features are merged into
        # `result` only after that family has completed and passed
        # validation.
        #
        # This prevents generated columns from one family becoming
        # accidental input columns for another family. In particular,
        # calendar indicators such as `is_weekday` must not be
        # presented as pre-existing demand-feature inputs.
        # ====================================================

        # ====================================================
        # 1. Temporal
        # ====================================================

        if config.include_temporal:

            temporal_result = (
                add_temporal_features(
                    canonical_input,
                    config=(
                        config.temporal_config
                    ),
                )
            )

            self._validate_family_result(
                family_name="temporal",
                source=canonical_input,
                family_result=(
                    temporal_result
                ),
            )

            temporal_columns = self._merge_family_features(
                result=result,
                family_name="temporal",
                family_result=temporal_result,
            )

        # ====================================================
        # 2. Calendar
        # ====================================================

        if config.include_calendar:

            calendar_result = (
                add_calendar_features(
                    canonical_input,
                    config=(
                        config.calendar_config
                    ),
                )
            )

            self._validate_family_result(
                family_name="calendar",
                source=canonical_input,
                family_result=(
                    calendar_result
                ),
            )

            calendar_columns = self._merge_family_features(
                result=result,
                family_name="calendar",
                family_result=calendar_result,
                exclude_columns={
                    "is_weekday",
                    "is_weekend",
                    "is_monday",
                    "is_tuesday",
                    "is_wednesday",
                    "is_thursday",
                    "is_friday",
                    "is_saturday",
                    "is_sunday",
                },
            )


        # ====================================================
        # 3. Occupancy
        # ====================================================

        if config.include_occupancy:

            occupancy_result = (
                add_occupancy_features(
                    canonical_input,
                    config=(
                        config.occupancy_config
                    ),
                )
            )

            self._validate_family_result(
                family_name="occupancy",
                source=canonical_input,
                family_result=(
                    occupancy_result
                ),
            )

            occupancy_columns = self._merge_family_features(
                result=result,
                family_name="occupancy",
                family_result=occupancy_result,
                exclude_columns={
                    "occupied_spaces",
                    "available_spaces",
                    "total_spaces",
                    "occupancy_rate",
                },
            )

        # ====================================================
        # 4. Demand
        # ====================================================

        if config.include_demand:

            demand_result = (
                add_demand_features(
                    canonical_input,
                    config=(
                        config.demand_config
                    ),
                )
            )

            self._validate_family_result(
                family_name="demand",
                source=canonical_input,
                family_result=(
                    demand_result
                ),
            )

            demand_columns = self._merge_family_features(
                result=result,
                family_name="demand",
                family_result=demand_result,
                exclude_columns={
                    "availability_rate",
                    "capacity_utilization",
                    "is_near_full",
                },
            )

        # ====================================================
        # 5. Lag
        # ====================================================

        if config.include_lag:

            lag_result = (
                add_lag_features(
                    canonical_input,
                    config=(
                        config.lag_config
                    ),
                )
            )

            self._validate_family_result(
                family_name="lag",
                source=canonical_input,
                family_result=(
                    lag_result
                ),
            )

            lag_columns = self._merge_family_features(
                result=result,
                family_name="lag",
                family_result=lag_result,
            )


        # ====================================================
        # 6. Rolling
        # ====================================================

        if config.include_rolling:

            rolling_result = (
                add_rolling_features(
                    canonical_input,
                    config=(
                        config.rolling_config
                    ),
                )
            )

            self._validate_family_result(
                family_name="rolling",
                source=canonical_input,
                family_result=(
                    rolling_result
                ),
            )

            rolling_columns = self._merge_family_features(
                result=result,
                family_name="rolling",
                family_result=rolling_result,
            )


        # ====================================================
        # Final structural validation
        # ====================================================

        if config.preserve_row_order:

            if not result.index.equals(
                original_index
            ):

                raise FeaturePipelineDataError(
                    "Feature pipeline changed "
                    "the dataframe index/order."
                )

        if len(result) != source_row_count:

            raise FeaturePipelineDataError(
                "Feature pipeline changed row count: "
                f"{source_row_count} -> "
                f"{len(result)}."
            )

        # ====================================================
        # Feature registry
        # ====================================================

        family_feature_groups = (
            temporal_columns,
            calendar_columns,
            occupancy_columns,
            demand_columns,
            lag_columns,
            rolling_columns,
        )

        feature_columns = tuple(
            column
            for group in family_feature_groups
            for column in group
        )

        # ----------------------------------------------------
        # Duplicate feature detection.
        # ----------------------------------------------------

        duplicate_features = (
            self._find_duplicates(
                feature_columns
            )
        )

        if (
            duplicate_features
            and config.fail_on_duplicate_features
        ):

            raise FeaturePipelineError(
                "Duplicate feature columns detected: "
                f"{duplicate_features}"
            )

        # ----------------------------------------------------
        # Ensure every feature exists.
        # ----------------------------------------------------

        missing_features = [
            column
            for column in feature_columns
            if column not in result.columns
        ]

        if missing_features:

            raise FeaturePipelineDataError(
                "Feature columns missing from final "
                f"dataframe: {missing_features}"
            )

        # ====================================================
        # Target validation
        # ====================================================

        target_columns = tuple(
            column
            for column in config.target_columns
            if column in result.columns
        )

        target_availability_columns = tuple(
            column
            for column in (
                config.target_availability_columns
            )
            if column in result.columns
        )

        # ----------------------------------------------------
        # Required target columns should normally exist.
        # ----------------------------------------------------

        missing_targets = [
            column
            for column in config.target_columns
            if column not in result.columns
        ]

        if missing_targets:

            raise FeaturePipelineDataError(
                "Expected target columns are missing: "
                f"{missing_targets}"
            )

        # ----------------------------------------------------
        # Feature / target overlap.
        # ----------------------------------------------------

        feature_target_overlap = (
            set(feature_columns)
            & set(target_columns)
        )

        if (
            feature_target_overlap
            and config.fail_on_feature_target_overlap
        ):

            raise FeaturePipelineLeakageError(
                "Feature columns overlap target columns: "
                f"{sorted(feature_target_overlap)}"
            )

        # ====================================================
        # Metadata registry
        # ====================================================

        metadata_columns = []

        for column in config.metadata_columns:

            if column in result.columns:

                metadata_columns.append(
                    column
                )

        # Add target-support columns to metadata.
        #
        # These describe target availability/exclusion but are
        # not model inputs.
        # ----------------------------------------------------

        for column in (
            config.target_support_columns
        ):

            if column in result.columns:

                if column not in metadata_columns:

                    metadata_columns.append(
                        column
                    )

        metadata_columns = tuple(
            metadata_columns
        )

        # ----------------------------------------------------
        # Feature / metadata overlap.
        # ----------------------------------------------------

        feature_metadata_overlap = (
            set(feature_columns)
            & set(metadata_columns)
        )

        if (
            feature_metadata_overlap
            and config.fail_on_feature_metadata_overlap
        ):

            raise FeaturePipelineError(
                "Feature columns overlap metadata columns: "
                f"{sorted(feature_metadata_overlap)}"
            )

        # ====================================================
        # Final feature list cleanup
        # ====================================================

        feature_columns = tuple(
            dict.fromkeys(
                feature_columns
            )
        )

        # ====================================================
        # Row-level supervision statistics
        # ====================================================

        availability_columns = [
            column
            for column in (
                target_availability_columns
            )
            if column in result.columns
        ]

        if availability_columns:

            availability_frame = (
                result[
                    availability_columns
                ]
                .fillna(False)
                .astype(bool)
            )

            target_available_count = (
                availability_frame.sum(
                    axis=1
                )
            )

            fully_supervised_rows = int(
                (
                    target_available_count
                    == len(
                        availability_columns
                    )
                ).sum()
            )

            partially_supervised_rows = int(
                (
                    (
                        target_available_count
                        > 0
                    )
                    & (
                        target_available_count
                        < len(
                            availability_columns
                        )
                    )
                ).sum()
            )

            unsupervised_rows = int(
                (
                    target_available_count
                    == 0
                ).sum()
            )

        else:

            fully_supervised_rows = 0
            partially_supervised_rows = 0
            unsupervised_rows = (
                len(result)
            )

        # ====================================================
        # Observation statistics
        # ====================================================

        if (
            "observation_present"
            in result.columns
        ):

            observed_row_count = int(
                result[
                    "observation_present"
                ]
                .fillna(False)
                .astype(bool)
                .sum()
            )

        else:

            observed_row_count = 0

        missing_row_count = (
            len(result)
            - observed_row_count
        )

        # ====================================================
        # Timestamp validation
        # ====================================================

        timestamp_values = pd.to_datetime(
            result[
                config.timestamp_column
            ],
            errors="coerce",
        )

        invalid_timestamp_count = int(
            timestamp_values.isna().sum()
        )

        # ====================================================
        # Facility count
        # ====================================================

        facility_count = int(
            result[
                config.facility_column
            ]
            .dropna()
            .astype(str)
            .nunique()
        )

        # ====================================================
        # Final metadata
        # ====================================================

        metadata = {
            "pipeline_name":
                "SmartPark AI Feature Pipeline",

            "feature_family":
                "pipeline",

            "source_name":
                "BIRMINGHAM",

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

            "historical_only_features":
                True,

            "row_count_preserved":
                len(result)
                == source_row_count,

            "row_order_preserved":
                result.index.equals(
                    original_index
                ),

            "source_columns_preserved":
                all(
                    column in result.columns
                    for column
                    in original_columns
                ),

            "feature_count":
                len(feature_columns),

            "target_count":
                len(target_columns),

            "target_availability_count":
                len(
                    target_availability_columns
                ),

            "feature_groups": {
                "temporal":
                    temporal_columns,

                "calendar":
                    calendar_columns,

                "occupancy":
                    occupancy_columns,

                "demand":
                    demand_columns,

                "lag":
                    lag_columns,

                "rolling":
                    rolling_columns,
            },

            "strict_leakage_validation":
                config.strict_leakage_validation,

            **config.metadata,
        }

        # Preserve the leakage contract on the dataframe itself so
        # validate_feature_pipeline(result.dataframe) can audit the
        # completed pipeline without requiring the wrapper object.
        result.attrs.update(
            {
                "future_data_used":
                    metadata["future_data_used"],
                "target_data_used":
                    metadata["target_data_used"],
                "cross_facility_data_used":
                    metadata["cross_facility_data_used"],
                "forward_lookup_used":
                    metadata["forward_lookup_used"],
                "centered_windows_used":
                    metadata["centered_windows_used"],
            }
        )

        # ====================================================
        # Pipeline leakage validation
        # ====================================================

        if config.strict_leakage_validation:

            self._validate_pipeline_leakage(
                metadata=metadata,
                family_results=(
                    temporal_result,
                    calendar_result,
                    occupancy_result,
                    demand_result,
                    lag_result,
                    rolling_result,
                ),
            )

        # ====================================================
        # Statistics
        # ====================================================

        statistics = (
            FeaturePipelineStatistics(
                source_row_count=
                    source_row_count,

                final_row_count=
                    len(result),

                source_column_count=
                    source_column_count,

                final_column_count=
                    len(result.columns),

                feature_count=
                    len(feature_columns),

                target_count=
                    len(target_columns),

                target_availability_count=
                    len(
                        target_availability_columns
                    ),

                metadata_column_count=
                    len(metadata_columns),

                temporal_feature_count=
                    len(temporal_columns),

                calendar_feature_count=
                    len(calendar_columns),

                occupancy_feature_count=
                    len(occupancy_columns),

                demand_feature_count=
                    len(demand_columns),

                lag_feature_count=
                    len(lag_columns),

                rolling_feature_count=
                    len(rolling_columns),

                duplicate_feature_count=
                    len(duplicate_features),

                invalid_timestamp_count=
                    invalid_timestamp_count,

                missing_feature_count=
                    len(missing_features),

                facility_count=
                    facility_count,

                observed_row_count=
                    observed_row_count,

                missing_row_count=
                    missing_row_count,

                fully_supervised_rows=
                    fully_supervised_rows,

                partially_supervised_rows=
                    partially_supervised_rows,

                unsupervised_rows=
                    unsupervised_rows,

                metadata=metadata,
            )
        )

        return FeaturePipelineResult(
            dataframe=result,

            feature_columns=(
                feature_columns
            ),

            target_columns=(
                target_columns
            ),

            target_availability_columns=(
                target_availability_columns
            ),

            metadata_columns=(
                metadata_columns
            ),

            statistics=statistics,

            metadata=metadata,

            temporal_result=(
                temporal_result
            ),

            calendar_result=(
                calendar_result
            ),

            occupancy_result=(
                occupancy_result
            ),

            demand_result=(
                demand_result
            ),

            lag_result=(
                lag_result
            ),

            rolling_result=(
                rolling_result
            ),

            dataset_result=None,
        )

    # ========================================================
    # Dataset transform
    # ========================================================

    def transform_birmingham(
        self,
        *,
        dataset_root: str = "../datasets/raw",
        dataset_name: str = "birmingham",
    ) -> FeaturePipelineResult:
        """
        Build the Birmingham ML dataset and run the complete
        feature pipeline.
        """

        dataset_result = (
            build_birmingham_ml_dataset(
                dataset_root=dataset_root,
                dataset_name=dataset_name,
            )
        )

        result = self.transform(
            dataset_result.dataframe
        )

        # Rebuild result with dataset_result attached.
        return FeaturePipelineResult(
            dataframe=result.dataframe,

            feature_columns=(
                result.feature_columns
            ),

            target_columns=(
                result.target_columns
            ),

            target_availability_columns=(
                result.target_availability_columns
            ),

            metadata_columns=(
                result.metadata_columns
            ),

            statistics=result.statistics,

            metadata={
                **result.metadata,
                "dataset_status":
                    dataset_result.status.value,
                "dataset_statistics":
                    dataset_result.statistics,
            },

            temporal_result=(
                result.temporal_result
            ),

            calendar_result=(
                result.calendar_result
            ),

            occupancy_result=(
                result.occupancy_result
            ),

            demand_result=(
                result.demand_result
            ),

            lag_result=(
                result.lag_result
            ),

            rolling_result=(
                result.rolling_result
            ),

            dataset_result=(
                dataset_result
            ),
        )

    # ========================================================
    # Feature merge
    # ========================================================

    @staticmethod
    def _merge_family_features(
        *,
        result: pd.DataFrame,
        family_name: str,
        family_result: Any,
        exclude_columns: set[str] | None = None,
        allowed_existing_columns: set[str] | None = None,
    ) -> tuple[str, ...]:
        """
        Merge only newly generated feature columns from one feature
        family into the accumulating pipeline dataframe.

        Source columns already present in ``result`` are never copied
        into the pipeline feature registry. ``exclude_columns`` is
        used for intentional source-column exclusions.
        """

        if family_result is None:
            raise FeaturePipelineDataError(
                f"{family_name} feature generator returned None."
            )

        family_dataframe = getattr(
            family_result,
            "dataframe",
            None,
        )

        if not isinstance(family_dataframe, pd.DataFrame):
            raise FeaturePipelineDataError(
                f"{family_name} feature generator did not return "
                "a valid DataFrame."
            )

        raw_feature_columns = tuple(
            getattr(
                family_result,
                "feature_columns",
                (),
            )
        )

        exclude_columns = set(
            exclude_columns or ()
        )
        allowed_existing_columns = set(
            allowed_existing_columns or ()
        )

        feature_columns = tuple(
            column
            for column in raw_feature_columns
            if column not in exclude_columns
        )

        missing_family_columns = [
            column
            for column in feature_columns
            if column not in family_dataframe.columns
        ]

        if missing_family_columns:
            raise FeaturePipelineDataError(
                f"{family_name} feature generator returned "
                "missing feature columns: "
                f"{missing_family_columns}"
            )

        duplicate_columns = [
            column
            for column in feature_columns
            if (
                column in result.columns
                and column not in allowed_existing_columns
            )
        ]

        if duplicate_columns:
            raise FeaturePipelineError(
                f"{family_name} feature family attempted "
                "to overwrite existing dataframe columns: "
                f"{duplicate_columns}"
            )

        # Existing columns explicitly allowed by the caller are not
        # registered as newly added pipeline features.
        feature_columns = tuple(
            column
            for column in feature_columns
            if column not in allowed_existing_columns
        )

        if not feature_columns:
            return ()

        family_features = family_dataframe.loc[
            :,
            list(feature_columns),
        ].copy()

        # Add the whole family in one operation to avoid pandas
        # fragmentation caused by repeated column insertion.
        result.loc[:, list(feature_columns)] = (
            family_features.to_numpy()
        )

        return feature_columns

    # ========================================================
    # Family validation
    # ========================================================

    def _validate_family_result(
        self,
        *,
        family_name: str,
        source: pd.DataFrame,
        family_result: Any,
    ) -> None:
        """
        Verify a feature-family result before passing it to the
        next stage.
        """

        if not isinstance(
            family_result.dataframe,
            pd.DataFrame,
        ):

            raise FeaturePipelineDataError(
                f"{family_name} feature generator "
                "did not return a DataFrame."
            )

        # ----------------------------------------------------
        # Row preservation.
        # ----------------------------------------------------

        if len(
            family_result.dataframe
        ) != len(source):

            raise FeaturePipelineDataError(
                f"{family_name} feature generator "
                "changed row count: "
                f"{len(source)} -> "
                f"{len(family_result.dataframe)}."
            )

        # ----------------------------------------------------
        # Index preservation.
        # ----------------------------------------------------

        if not family_result.dataframe.index.equals(
            source.index
        ):

            raise FeaturePipelineDataError(
                f"{family_name} feature generator "
                "changed dataframe index/order."
            )

        # ----------------------------------------------------
        # Feature existence.
        # ----------------------------------------------------

        missing = [
            column
            for column
            in family_result.feature_columns
            if column
            not in family_result.dataframe.columns
        ]

        if missing:

            raise FeaturePipelineDataError(
                f"{family_name} feature generator "
                f"returned missing feature columns: "
                f"{missing}"
            )

        # ----------------------------------------------------
        # Leakage metadata.
        # ----------------------------------------------------

        metadata = getattr(
            family_result,
            "metadata",
            {},
        ) or {}

        if not self._config.strict_leakage_validation:
            return

        forbidden_flags = (
            "future_data_used",
            "target_data_used",
            "cross_facility_data_used",
            "forward_lookup_used",
            "centered_windows_used",
        )

        violations = [
            key
            for key in forbidden_flags
            if metadata.get(
                key,
                False,
            )
            is True
        ]

        if violations:

            raise FeaturePipelineLeakageError(
                f"{family_name} feature family "
                "violates leakage contract: "
                f"{violations}"
            )

    # ========================================================
    # Pipeline leakage validation
    # ========================================================

    def _validate_pipeline_leakage(
        self,
        *,
        metadata: dict[str, Any],
        family_results: Iterable[Any],
    ) -> None:
        """
        Validate leakage metadata across the entire pipeline.
        """

        pipeline_forbidden_flags = (
            "future_data_used",
            "target_data_used",
            "cross_facility_data_used",
            "forward_lookup_used",
            "centered_windows_used",
        )

        violations = [
            key
            for key in pipeline_forbidden_flags
            if metadata.get(
                key,
                False,
            )
            is True
        ]

        if violations:

            raise FeaturePipelineLeakageError(
                "Pipeline leakage contract violated: "
                f"{violations}"
            )

        # ----------------------------------------------------
        # Recheck every feature family.
        # ----------------------------------------------------

        for family_result in (
            family_results
        ):

            if family_result is None:
                continue

            family_metadata = getattr(
                family_result,
                "metadata",
                {},
            ) or {}

            family_violations = [
                key
                for key in pipeline_forbidden_flags
                if family_metadata.get(
                    key,
                    False,
                )
                is True
            ]

            if family_violations:

                raise FeaturePipelineLeakageError(
                    "Feature-family leakage detected: "
                    f"{family_violations}"
                )

    # ========================================================
    # Input validation
    # ========================================================

    def _validate_input(
        self,
        dataframe: pd.DataFrame,
    ) -> None:
        """
        Validate pipeline input.
        """

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):

            raise FeaturePipelineDataError(
                "Feature pipeline input must "
                "be a pandas DataFrame."
            )

        if dataframe.empty:

            raise FeaturePipelineDataError(
                "Feature pipeline input is empty."
            )

        required_columns = (
            self._config.timestamp_column,
            self._config.facility_column,
        )

        missing_columns = [
            column
            for column in required_columns
            if column not in dataframe.columns
        ]

        if missing_columns:

            raise FeaturePipelineDataError(
                "Feature pipeline input is missing "
                f"required columns: {missing_columns}"
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

            raise FeaturePipelineDataError(
                "Feature pipeline input contains "
                f"duplicate columns: {duplicates}"
            )

    # ========================================================
    # Duplicate helper
    # ========================================================

    @staticmethod
    def _find_duplicates(
        columns: Iterable[str],
    ) -> tuple[str, ...]:
        """
        Find duplicate column names while preserving order.
        """

        seen: set[str] = set()

        duplicates: list[str] = []

        for column in columns:

            if column in seen:

                duplicates.append(
                    column
                )

            else:

                seen.add(
                    column
                )

        return tuple(
            duplicates
        )


# ============================================================
# Expected feature columns
# ============================================================


def expected_pipeline_feature_columns(
    config: FeaturePipelineConfig | None = None,
) -> tuple[str, ...]:
    """
    Return the expected feature columns for a configured
    pipeline.

    This helper runs the individual feature generators on a
    tiny synthetic dataframe so the pipeline's public feature
    registry remains aligned with the actual generators.

    It is intended primarily for inspection and testing.
    """

    config = (
        config
        or FeaturePipelineConfig()
    )

    # --------------------------------------------------------
    # Minimal canonical dataset.
    # --------------------------------------------------------

    sample = pd.DataFrame(
        {
            "source_facility_code": [
                "TEST"
            ],

            "normalized_at": pd.to_datetime(
                [
                    "2024-01-02 08:00:00"
                ]
            ),

            "observation_present": [
                True
            ],

            "gap_status": [
                "CONTINUOUS"
            ],

            "is_operational_gap": [
                False
            ],

            "is_data_gap": [
                False
            ],

            "sequence_break": [
                False
            ],

            "is_eligible_for_sequence": [
                True
            ],

            "quality_status": [
                "CLEAN"
            ],

            "quality_flags": [
                []
            ],

            "source": [
                "TEST"
            ],

            "total_spaces": [
                100
            ],

            "occupied_spaces": [
                50
            ],

            "available_spaces": [
                50
            ],

            "occupancy_rate": [
                0.5
            ],

            "target_occupancy_rate_30m": [
                0.55
            ],

            "target_occupancy_rate_1h": [
                0.60
            ],

            "target_occupancy_rate_2h": [
                0.65
            ],

            "target_tomorrow_morning_demand": [
                0.45
            ],

            "target_30m_available": [
                True
            ],

            "target_1h_available": [
                True
            ],

            "target_2h_available": [
                True
            ],

            "target_tomorrow_morning_available": [
                True
            ],

            "target_exclusion_reason": [
                "NONE"
            ],
        }
    )

    generator = FeaturePipeline(
        config=config
    )

    result = generator.transform(
        sample
    )

    return result.feature_columns


# ============================================================
# Validation
# ============================================================


def validate_feature_pipeline(
    dataframe: pd.DataFrame,
    *,
    config: FeaturePipelineConfig | None = None,
) -> dict[str, Any]:
    """
    Validate a final pipeline dataframe.

    This function does not regenerate features. It validates
    structural properties and the leakage contract.
    """

    config = (
        config
        or FeaturePipelineConfig()
    )

    errors: list[str] = []
    warnings: list[str] = []

    # --------------------------------------------------------
    # Basic validation.
    # --------------------------------------------------------

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
            "row_count": 0,
            "feature_count": 0,
            "target_count": 0,
            "future_data_used": False,
            "target_data_used": False,
            "cross_facility_data_used": False,
            "forward_lookup_used": False,
            "centered_windows_used": False,
        }

    # --------------------------------------------------------
    # Required structural columns.
    # --------------------------------------------------------

    required_columns = (
        config.timestamp_column,
        config.facility_column,
        *config.target_columns,
    )

    missing_required = [
        column
        for column in required_columns
        if column not in dataframe.columns
    ]

    if missing_required:

        errors.append(
            "Missing required pipeline columns: "
            f"{missing_required}"
        )

    # --------------------------------------------------------
    # Duplicate columns.
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
    # Timestamp.
    # --------------------------------------------------------

    if (
        config.timestamp_column
        in dataframe.columns
    ):

        timestamp = pd.to_datetime(
            dataframe[
                config.timestamp_column
            ],
            errors="coerce",
        )

        invalid_timestamp_count = int(
            timestamp.isna().sum()
        )

        if invalid_timestamp_count:

            errors.append(
                "Timestamp column contains "
                f"{invalid_timestamp_count} "
                "invalid value(s)."
            )

    else:

        invalid_timestamp_count = 0

    # --------------------------------------------------------
    # Facility.
    # --------------------------------------------------------

    if (
        config.facility_column
        in dataframe.columns
    ):

        missing_facility_count = int(
            dataframe[
                config.facility_column
            ]
            .isna()
            .sum()
        )

        if missing_facility_count:

            warnings.append(
                "Facility column contains "
                f"{missing_facility_count} "
                "missing value(s)."
            )

    # --------------------------------------------------------
    # Feature columns.
    #
    # We identify feature columns from the feature-family
    # naming conventions used by this pipeline.
    # --------------------------------------------------------

    excluded = set(
        config.metadata_columns
        + config.target_columns
        + config.target_availability_columns
        + config.target_support_columns
    )

    feature_columns = tuple(
        column
        for column in dataframe.columns
        if column not in excluded
    )

    # --------------------------------------------------------
    # Leakage by target-name contamination.
    # --------------------------------------------------------

    target_overlap = [
        column
        for column in feature_columns
        if column in set(
            config.target_columns
        )
        or column in set(
            config.target_availability_columns
        )
        or column in set(
            config.target_support_columns
        )
    ]

    if target_overlap:

        errors.append(
            "Feature columns overlap target/support "
            f"columns: {target_overlap}"
        )

    # --------------------------------------------------------
    # NaN / infinity audit for numeric features.
    # --------------------------------------------------------

    numeric_feature_columns = [
        column
        for column in feature_columns
        if pd.api.types.is_numeric_dtype(
            dataframe[column]
        )
    ]

    infinite_feature_columns: list[
        str
    ] = []

    for column in (
        numeric_feature_columns
    ):

        values = pd.to_numeric(
            dataframe[column],
            errors="coerce",
        )

        finite_values = values.dropna()

        if finite_values.empty:
            continue

        if np.isinf(
            finite_values.to_numpy(
                dtype="float64"
            )
        ).any():

            infinite_feature_columns.append(
                column
            )

    if infinite_feature_columns:

        errors.append(
            "Numeric feature columns contain "
            "infinite values: "
            f"{infinite_feature_columns}"
        )

    # --------------------------------------------------------
    # Leakage metadata.
    #
    # A normal dataframe does not itself contain leakage
    # metadata unless produced by this pipeline. Therefore,
    # these values are taken from explicit dataframe attributes
    # when available.
    # --------------------------------------------------------

    dataframe_metadata = getattr(
        dataframe,
        "attrs",
        {},
    ) or {}

    future_data_used = bool(
        dataframe_metadata.get(
            "future_data_used",
            False,
        )
    )

    target_data_used = bool(
        dataframe_metadata.get(
            "target_data_used",
            False,
        )
    )

    cross_facility_data_used = bool(
        dataframe_metadata.get(
            "cross_facility_data_used",
            False,
        )
    )

    forward_lookup_used = bool(
        dataframe_metadata.get(
            "forward_lookup_used",
            False,
        )
    )

    centered_windows_used = bool(
        dataframe_metadata.get(
            "centered_windows_used",
            False,
        )
    )

    if future_data_used:

        errors.append(
            "Pipeline metadata indicates future "
            "data was used."
        )

    if target_data_used:

        errors.append(
            "Pipeline metadata indicates target "
            "data was used."
        )

    if cross_facility_data_used:

        errors.append(
            "Pipeline metadata indicates cross-facility "
            "data was used."
        )

    if forward_lookup_used:

        errors.append(
            "Pipeline metadata indicates forward "
            "lookup was used."
        )

    if centered_windows_used:

        errors.append(
            "Pipeline metadata indicates centered "
            "windows were used."
        )

    # --------------------------------------------------------
    # Result.
    # --------------------------------------------------------

    return {
        "valid":
            not errors,

        "errors":
            errors,

        "warnings":
            warnings,

        "row_count":
            len(dataframe),

        "column_count":
            len(dataframe.columns),

        "feature_count":
            len(feature_columns),

        "target_count":
            len(
                [
                    column
                    for column
                    in config.target_columns
                    if column
                    in dataframe.columns
                ]
            ),

        "metadata_column_count":
            len(
                [
                    column
                    for column
                    in config.metadata_columns
                    if column
                    in dataframe.columns
                ]
            ),

        "invalid_timestamp_count":
            invalid_timestamp_count,

        "infinite_feature_columns":
            infinite_feature_columns,

        "future_data_used":
            future_data_used,

        "target_data_used":
            target_data_used,

        "cross_facility_data_used":
            cross_facility_data_used,

        "forward_lookup_used":
            forward_lookup_used,

        "centered_windows_used":
            centered_windows_used,
    }


# ============================================================
# Convenience API
# ============================================================


def build_feature_pipeline(
    dataframe: pd.DataFrame,
    *,
    config: FeaturePipelineConfig | None = None,
) -> FeaturePipelineResult:
    """
    Run the feature pipeline against an existing ML dataframe.
    """

    pipeline = FeaturePipeline(
        config=config
    )

    return pipeline.transform(
        dataframe
    )


def build_birmingham_feature_pipeline(
    *,
    dataset_root: str = "../datasets/raw",
    dataset_name: str = "birmingham",
    config: FeaturePipelineConfig | None = None,
) -> FeaturePipelineResult:
    """
    Build the Birmingham ML dataset and run the complete
    SmartPark AI feature pipeline.
    """

    pipeline = FeaturePipeline(
        config=config
    )

    return pipeline.transform_birmingham(
        dataset_root=dataset_root,
        dataset_name=dataset_name,
    )


# ============================================================
# Public exports
# ============================================================


__all__ = [
    "FeaturePipelineError",
    "FeaturePipelineConfigurationError",
    "FeaturePipelineDataError",
    "FeaturePipelineLeakageError",
    "FeaturePipelineConfig",
    "FeaturePipelineStatistics",
    "FeaturePipelineResult",
    "FeaturePipeline",
    "expected_pipeline_feature_columns",
    "validate_feature_pipeline",
    "build_feature_pipeline",
    "build_birmingham_feature_pipeline",
]