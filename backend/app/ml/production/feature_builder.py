"""
SmartPark AI - Production Feature Builder
==========================================

Builds production-time ML features from operational parking
observations stored in the SmartPark database.

Architecture
------------

    occupancy_observations
            |
            v
    ProductionFeatureBuilder
            |
            +--> canonicalise operational observations
            |
            +--> build 30-minute production timeline
            |
            +--> preserve missing historical observations
            |
            +--> mark sequence / data gaps
            |
            v
       FeaturePipeline
            |
            +--> temporal features
            +--> calendar features
            +--> occupancy features
            +--> demand features
            +--> lag features
            +--> rolling features
            |
            v
       296 model features
            |
            v
       ProductionFeatureResult

Important
---------

This module DOES NOT:

    - train XGBoost
    - load Birmingham training datasets
    - load train.parquet
    - load validation.parquet
    - load test.parquet
    - perform model selection
    - perform hyperparameter tuning
    - create prediction targets
    - use future observations
    - interpolate occupancy
    - forward-fill occupancy
    - backward-fill occupancy

It prepares CURRENT and HISTORICAL operational observations for
production inference.

The existing feature pipeline remains the single source of truth
for feature engineering.

Production model contract
--------------------------

The current production XGBoost model expects the established
296-feature contract.

The builder therefore:

    1. Creates the canonical production observation schema.
    2. Creates a regular 30-minute timeline per facility.
    3. Preserves missing historical observations.
    4. Marks missing/sequence information explicitly.
    5. Runs the existing FeaturePipeline.
    6. Returns only the requested inference row(s) and features.

The production builder deliberately does NOT generate supervised
learning targets.

The current XGBoost production target is:

    target_occupancy_rate_30m

The target itself is NOT created here.

"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd

from app.ml.features.feature_pipeline import (
    FeaturePipeline,
    FeaturePipelineConfig,
)


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_FACILITY_COLUMN = "source_facility_code"
DEFAULT_TIMESTAMP_COLUMN = "normalized_at"

DEFAULT_SOURCE_TIMESTAMP_COLUMN = "source_observed_at"

DEFAULT_TOTAL_SPACES_COLUMN = "total_spaces"
DEFAULT_OCCUPIED_SPACES_COLUMN = "occupied_spaces"
DEFAULT_AVAILABLE_SPACES_COLUMN = "available_spaces"
DEFAULT_OCCUPANCY_RATE_COLUMN = "occupancy_rate"

DEFAULT_OBSERVATION_PRESENT_COLUMN = "observation_present"

DEFAULT_GAP_STATUS_COLUMN = "gap_status"
DEFAULT_SEQUENCE_BREAK_COLUMN = "sequence_break"
DEFAULT_OPERATIONAL_GAP_COLUMN = "is_operational_gap"
DEFAULT_DATA_GAP_COLUMN = "is_data_gap"
DEFAULT_SEQUENCE_ELIGIBLE_COLUMN = "is_eligible_for_sequence"

DEFAULT_QUALITY_STATUS_COLUMN = "quality_status"
DEFAULT_QUALITY_FLAGS_COLUMN = "quality_flags"

DEFAULT_SOURCE_COLUMN = "source"

DEFAULT_INTERVAL_MINUTES = 30

# The existing lag and rolling feature contracts extend to 24 hours.
DEFAULT_REQUIRED_HISTORY_HOURS = 24

# Production XGBoost feature contract.
EXPECTED_PRODUCTION_FEATURE_COUNT = 296

# Categorical features preserved as labels until the production inference
# layer applies the frozen categorical mappings.
PRODUCTION_CATEGORICAL_FEATURES = (
    "occupancy_level",
    "demand_class",
)

# Current locked production target.
CURRENT_TARGET_HORIZON = "30m"

CURRENT_TARGET_COLUMN = "target_occupancy_rate_30m"


# ============================================================================
# EXCEPTIONS
# ============================================================================


class ProductionFeatureBuilderError(ValueError):
    """Base exception for production feature-builder errors."""


class ProductionFeatureConfigurationError(
    ProductionFeatureBuilderError
):
    """Raised when production feature-builder configuration is invalid."""


class ProductionFeatureDataError(
    ProductionFeatureBuilderError
):
    """Raised when operational observation data is invalid."""


class ProductionFeatureContractError(
    ProductionFeatureBuilderError
):
    """Raised when the production feature contract is violated."""


# ============================================================================
# CONFIGURATION
# ============================================================================


@dataclass(frozen=True, slots=True)
class ProductionFeatureBuilderConfig:
    """
    Configuration for production feature construction.

    SmartPark AI uses a 30-minute modelling interval.

    Historical requirements
    -----------------------

    The current feature contract includes:

        - 30-minute lag
        - 1-hour lag
        - 2-hour lag
        - 3-hour lag
        - 6-hour lag
        - 12-hour lag
        - 24-hour lag

    Rolling windows also extend to 24 hours.

    Therefore production inference requires sufficient historical
    observations to construct these features.
    """

    facility_column: str = DEFAULT_FACILITY_COLUMN

    timestamp_column: str = DEFAULT_TIMESTAMP_COLUMN

    source_timestamp_column: str = (
        DEFAULT_SOURCE_TIMESTAMP_COLUMN
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

    occupancy_rate_column: str = (
        DEFAULT_OCCUPANCY_RATE_COLUMN
    )

    observation_present_column: str = (
        DEFAULT_OBSERVATION_PRESENT_COLUMN
    )

    gap_status_column: str = (
        DEFAULT_GAP_STATUS_COLUMN
    )

    sequence_break_column: str = (
        DEFAULT_SEQUENCE_BREAK_COLUMN
    )

    operational_gap_column: str = (
        DEFAULT_OPERATIONAL_GAP_COLUMN
    )

    data_gap_column: str = (
        DEFAULT_DATA_GAP_COLUMN
    )

    sequence_eligible_column: str = (
        DEFAULT_SEQUENCE_ELIGIBLE_COLUMN
    )

    quality_status_column: str = (
        DEFAULT_QUALITY_STATUS_COLUMN
    )

    quality_flags_column: str = (
        DEFAULT_QUALITY_FLAGS_COLUMN
    )

    source_column: str = (
        DEFAULT_SOURCE_COLUMN
    )

    interval_minutes: int = (
        DEFAULT_INTERVAL_MINUTES
    )

    required_history_hours: int = (
        DEFAULT_REQUIRED_HISTORY_HOURS
    )

    expected_feature_count: int = (
        EXPECTED_PRODUCTION_FEATURE_COUNT
    )

    strict_feature_count: bool = True

    strict_timestamp_alignment: bool = True

    allow_empty_history: bool = False

    require_current_observation: bool = True

    preserve_source_timestamp: bool = True

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:

        if not self.facility_column:
            raise ProductionFeatureConfigurationError(
                "facility_column cannot be empty."
            )

        if not self.timestamp_column:
            raise ProductionFeatureConfigurationError(
                "timestamp_column cannot be empty."
            )

        if self.interval_minutes <= 0:
            raise ProductionFeatureConfigurationError(
                "interval_minutes must be greater than zero."
            )

        if self.required_history_hours <= 0:
            raise ProductionFeatureConfigurationError(
                "required_history_hours must be greater than zero."
            )

        if self.expected_feature_count <= 0:
            raise ProductionFeatureConfigurationError(
                "expected_feature_count must be greater than zero."
            )


# ============================================================================
# RESULT OBJECTS
# ============================================================================


@dataclass(frozen=True, slots=True)
class ProductionFeatureStatistics:
    """
    Statistics generated during production feature construction.
    """

    input_row_count: int

    canonical_row_count: int

    timeline_row_count: int

    output_row_count: int

    facility_count: int

    observed_row_count: int

    missing_row_count: int

    sequence_break_count: int

    data_gap_row_count: int

    operational_gap_row_count: int

    feature_count: int

    invalid_timestamp_count: int

    missing_required_feature_count: int

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


@dataclass(frozen=True, slots=True)
class ProductionFeatureResult:
    """
    Complete production feature-building result.

    ``dataframe`` contains the complete production feature dataframe.

    ``inference_dataframe`` contains the row(s) intended for model
    inference.

    ``feature_columns`` contains ONLY model input features.

    No supervised-learning targets are created by this module.
    """

    dataframe: pd.DataFrame

    inference_dataframe: pd.DataFrame

    feature_columns: tuple[str, ...]

    statistics: ProductionFeatureStatistics

    metadata: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================================
# PRODUCTION FEATURE BUILDER
# ============================================================================


class ProductionFeatureBuilder:
    """
    Build model-ready production features from operational observations.

    The builder reuses the existing SmartPark FeaturePipeline rather than
    duplicating feature-generation logic.

    Example
    -------

        builder = ProductionFeatureBuilder()

        result = builder.build(
            observations,
            facility_code="BHMBCCMKT01",
        )

        X = result.inference_dataframe[
            list(result.feature_columns)
        ]

    """

    def __init__(
        self,
        config: ProductionFeatureBuilderConfig | None = None,
    ) -> None:

        self._config = (
            config
            or ProductionFeatureBuilderConfig()
        )

        # Build the production FeaturePipeline once and reuse it.
        #
        # The production builder deliberately owns the production
        # configuration of the existing FeaturePipeline, while the
        # FeaturePipeline itself remains the single source of truth for
        # feature engineering.
        self._pipeline = self._create_feature_pipeline()

    # ========================================================================
    # FEATURE PIPELINE
    # ========================================================================

    def _create_feature_pipeline(self) -> FeaturePipeline:
        """
        Create the canonical production ``FeaturePipeline``.

        Production inference deliberately uses the existing SmartPark
        ``FeaturePipeline`` rather than duplicating feature-engineering
        logic in this builder.  The configuration here mirrors the
        production contract used by the original builder implementation:

        - no supervised-learning targets
        - no target-availability/support columns
        - temporal, calendar, occupancy, demand, lag and rolling features
        - strict leakage validation
        - strict row validation
        - source-column preservation
        - duplicate-feature protection
        - feature/target overlap protection

        The frozen XGBoost model currently expects 296 model features.
        The resulting feature list is validated after transformation by
        ``_validate_feature_contract``.
        """

        pipeline_config = FeaturePipelineConfig(
            timestamp_column=(
                self._config.timestamp_column
            ),
            facility_column=(
                self._config.facility_column
            ),
            target_columns=(),
            target_availability_columns=(),
            target_support_columns=(),
            include_temporal=True,
            include_calendar=True,
            include_occupancy=True,
            include_demand=True,
            include_lag=True,
            include_rolling=True,
            strict_leakage_validation=True,
            strict_row_validation=True,
            preserve_row_order=True,
            preserve_source_columns=True,
            fail_on_duplicate_features=True,
            fail_on_feature_target_overlap=True,
            fail_on_feature_metadata_overlap=False,
            metadata={
                "source_name": "SMARTPARK_OPERATIONAL",
                "production_inference": True,
                "target_generation": False,
            },
        )

        return FeaturePipeline(
            config=pipeline_config
        )


    # ========================================================================
    # PROPERTIES
    # ========================================================================

    @property
    def config(
        self,
    ) -> ProductionFeatureBuilderConfig:

        return self._config

    @property
    def pipeline(
        self,
    ) -> FeaturePipeline:

        return self._pipeline

    # ========================================================================
    # PUBLIC API
    # ========================================================================

    def build(
        self,
        observations: pd.DataFrame,
        *,
        facility_code: str | None = None,
        inference_at: pd.Timestamp | datetime | None = None,
    ) -> ProductionFeatureResult:
        """
        Build production features from operational observations.

        Parameters
        ----------
        observations:
            Operational observation dataframe.

        facility_code:
            Optional facility code. When supplied, only observations
            for that facility are used.

        inference_at:
            Optional prediction timestamp.

            When supplied, only data available at or before this
            timestamp is used.

        Returns
        -------
        ProductionFeatureResult
        """

        self._validate_input_dataframe(
            observations
        )

        input_row_count = len(
            observations
        )

        canonical = self._canonicalise_observations(
            observations
        )

        if facility_code is not None:

            facility_code = str(
                facility_code
            ).strip()

            if not facility_code:
                raise ProductionFeatureDataError(
                    "facility_code cannot be empty."
                )

            canonical = canonical.loc[
                canonical[
                    self._config.facility_column
                ].astype(str)
                == facility_code
            ].copy()

            if canonical.empty:
                raise ProductionFeatureDataError(
                    "No operational observations found "
                    f"for facility '{facility_code}'."
                )

        inference_timestamp = (
            self._normalise_inference_timestamp(
                inference_at
            )
        )

        if inference_timestamp is not None:

            canonical = canonical.loc[
                canonical[
                    self._config.timestamp_column
                ]
                <= inference_timestamp
            ].copy()

            if canonical.empty:
                raise ProductionFeatureDataError(
                    "No operational observations exist "
                    "at or before the requested inference "
                    "timestamp."
                )

        timeline = self._build_production_timeline(
            canonical
        )

        if timeline.empty:

            if not self._config.allow_empty_history:

                raise ProductionFeatureDataError(
                    "Production feature timeline is empty."
                )

        # ------------------------------------------------------------
        # Identify inference timestamp.
        #
        # If the caller did not provide one, use the latest
        # available normalized timestamp.
        # ------------------------------------------------------------

        if inference_timestamp is None:

            inference_timestamp = pd.Timestamp(
                timeline[
                    self._config.timestamp_column
                ].max()
            )

        # ------------------------------------------------------------
        # The current observation must exist for production
        # inference.
        # ------------------------------------------------------------

        if self._config.require_current_observation:

            current_rows = timeline.loc[
                timeline[
                    self._config.timestamp_column
                ]
                == inference_timestamp
            ]

            if current_rows.empty:

                raise ProductionFeatureDataError(
                    "No observation slot exists at the requested "
                    "inference timestamp: "
                    f"{inference_timestamp}."
                )

        # ------------------------------------------------------------
        # Run the existing production FeaturePipeline.
        #
        # The pipeline is created once in __init__ through
        # _create_feature_pipeline() and reused for every build call.
        # This keeps the production feature configuration centralised
        # and avoids silently creating a different pipeline per request.
        #
        # IMPORTANT:
        #
        # Production inference has NO supervised targets.
        # ------------------------------------------------------------

        pipeline_result = self._pipeline.transform(
            timeline
        )

        feature_columns = tuple(
            pipeline_result.feature_columns
        )

        # ------------------------------------------------------------
        # Normalise non-categorical model features to numeric dtypes.
        #
        # The existing FeaturePipeline may return some ordinal/code
        # features (for example demand_class_code) as object/string
        # dtype even though their values are numeric. The production
        # XGBoost contract treats only occupancy_level and demand_class
        # as categorical labels. Every other model feature must
        # therefore be numeric before inference.
        #
        # We do NOT encode or alter the two frozen categorical labels
        # here. ProductionXGBoostInference owns that mapping using the
        # persisted categorical_mappings.json artifact.
        # ------------------------------------------------------------

        normalised_feature_dataframe = (
            self._normalise_model_feature_dtypes(
                pipeline_result.dataframe,
                feature_columns,
            )
        )

        production_dataframe = normalised_feature_dataframe

        # ------------------------------------------------------------
        # Extract inference row BEFORE strict model-input validation.
        #
        # The complete production dataframe intentionally contains
        # historical DATA_GAP rows. Those rows may legitimately have
        # null categorical values such as demand_class because there is
        # no observation at that historical slot.
        #
        # The frozen XGBoost model contract applies to the actual row
        # sent to inference, not to every historical row used to build
        # lag/rolling features.
        # ------------------------------------------------------------

        inference_dataframe = (
            production_dataframe.loc[
                production_dataframe[
                    self._config.timestamp_column
                ]
                == inference_timestamp
            ]
            .copy()
        )

        if inference_dataframe.empty:

            raise ProductionFeatureDataError(
                "Feature pipeline did not produce an "
                "inference row for timestamp "
                f"{inference_timestamp}."
            )

        # ------------------------------------------------------------
        # Validate the frozen model contract ONLY against the actual
        # inference row.
        #
        # Historical feature rows may legitimately contain missing
        # values because production gaps are preserved explicitly.
        # Those rows are used only to construct historical features
        # and are never passed directly to XGBoost.
        # ------------------------------------------------------------

        self._validate_feature_contract(
            inference_dataframe,
            feature_columns,
        )

        # ------------------------------------------------------------
        # Validate current observation.
        # ------------------------------------------------------------

        if self._config.require_current_observation:

            current_observed = (
                inference_dataframe[
                    self._config.observation_present_column
                ]
                .fillna(False)
                .astype(bool)
            )

            if not bool(
                current_observed.any()
            ):

                raise ProductionFeatureDataError(
                    "The requested inference timestamp does "
                    "not contain a current operational observation."
                )

        # ------------------------------------------------------------
        # Statistics.
        # ------------------------------------------------------------

        statistics = (
            self._build_statistics(
                input_row_count=input_row_count,
                canonical=canonical,
                timeline=timeline,
                result=production_dataframe,
                feature_columns=feature_columns,
            )
        )

        metadata = {
            "builder_name": (
                "SmartPark AI Production Feature Builder"
            ),
            "source_name": (
                "SMARTPARK_OPERATIONAL"
            ),
            "production_inference": True,
            "interval_minutes": (
                self._config.interval_minutes
            ),
            "required_history_hours": (
                self._config.required_history_hours
            ),
            "inference_at": (
                inference_timestamp.isoformat()
            ),
            "feature_count": len(
                feature_columns
            ),
            "expected_feature_count": (
                self._config.expected_feature_count
            ),
            "target_column": (
                CURRENT_TARGET_COLUMN
            ),
            "target_horizon": (
                CURRENT_TARGET_HORIZON
            ),
            "future_data_used": False,
            "target_data_used": False,
            "cross_facility_data_used": False,
            "forward_lookup_used": False,
            "centered_windows_used": False,
            **self._config.metadata,
        }

        # ------------------------------------------------------------
        # Preserve production metadata on dataframe.
        # ------------------------------------------------------------

        pipeline_result.dataframe.attrs.update(
            metadata
        )

        inference_dataframe.attrs.update(
            metadata
        )

        return ProductionFeatureResult(
            dataframe=(
                production_dataframe
            ),
            inference_dataframe=(
                inference_dataframe
            ),
            feature_columns=feature_columns,
            statistics=statistics,
            metadata=metadata,
        )

    # ========================================================================
    # CANONICALISATION
    # ========================================================================

    def _canonicalise_observations(
        self,
        observations: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Convert operational observation data into the canonical
        dataframe expected by the ML feature pipeline.

        Expected operational source columns
        ------------------------------------

            facility_id OR source_facility_code
            observed_at OR normalized_at
            total_spaces
            occupied_spaces
            available_spaces
            occupancy_rate
            source
            quality_status
            quality_flags

        The method intentionally does not calculate engineered
        features.
        """

        dataframe = observations.copy(
            deep=True
        )

        # ------------------------------------------------------------
        # Facility identifier
        # ------------------------------------------------------------

        if (
            self._config.facility_column
            not in dataframe.columns
        ):

            if "facility_code" in dataframe.columns:

                dataframe[
                    self._config.facility_column
                ] = dataframe[
                    "facility_code"
                ].astype(str)

            elif "facility_id" in dataframe.columns:

                # A numeric facility_id is NOT a substitute for
                # source_facility_code unless explicitly supplied
                # by the operational query.
                #
                # We preserve it as a string rather than silently
                # pretending that the ID is a facility code.

                dataframe[
                    self._config.facility_column
                ] = dataframe[
                    "facility_id"
                ].astype(str)

            else:

                raise ProductionFeatureDataError(
                    "Operational observations must contain "
                    "source_facility_code, facility_code, "
                    "or facility_id."
                )

        dataframe[
            self._config.facility_column
        ] = (
            dataframe[
                self._config.facility_column
            ]
            .astype(str)
            .str.strip()
        )

        # ------------------------------------------------------------
        # Timestamp
        # ------------------------------------------------------------

        if (
            self._config.timestamp_column
            not in dataframe.columns
        ):

            if "observed_at" in dataframe.columns:

                dataframe[
                    self._config.timestamp_column
                ] = dataframe[
                    "observed_at"
                ]

            elif (
                self._config.source_timestamp_column
                in dataframe.columns
            ):

                dataframe[
                    self._config.timestamp_column
                ] = dataframe[
                    self._config.source_timestamp_column
                ]

            else:

                raise ProductionFeatureDataError(
                    "Operational observations must contain "
                    "observed_at or normalized_at."
                )

        # ------------------------------------------------------------------
        # Production modelling timestamp
        #
        # The database/service layer may provide timezone-aware UTC
        # timestamps. The existing FeaturePipeline operates on the
        # canonical modelling timestamp representation used by the
        # training feature pipeline.
        #
        # Therefore:
        #   DB/API timestamp -> UTC -> timezone-naive modelling timestamp
        #
        # The original source timestamp is preserved separately.
        # ------------------------------------------------------------------

        dataframe[
            self._config.timestamp_column
        ] = pd.to_datetime(
            dataframe[
                self._config.timestamp_column
            ],
            errors="coerce",
            utc=True,
        ).dt.tz_localize(None)

        invalid_timestamps = int(
            dataframe[
                self._config.timestamp_column
            ].isna().sum()
        )

        if invalid_timestamps:

            raise ProductionFeatureDataError(
                "Operational observations contain "
                f"{invalid_timestamps} invalid timestamps."
            )

        # ------------------------------------------------------------
        # Preserve source timestamp where available.
        # ------------------------------------------------------------

        if self._config.preserve_source_timestamp:

            if (
                self._config.source_timestamp_column
                not in dataframe.columns
            ):

                if "observed_at" in observations.columns:

                    dataframe[
                        self._config.source_timestamp_column
                    ] = pd.to_datetime(
                        observations[
                            "observed_at"
                        ],
                        errors="coerce",
                    )

                else:

                    dataframe[
                        self._config.source_timestamp_column
                    ] = dataframe[
                        self._config.timestamp_column
                    ]

        # ------------------------------------------------------------
        # Numeric occupancy fields.
        # ------------------------------------------------------------

        required_numeric_columns = (
            self._config.total_spaces_column,
            self._config.occupied_spaces_column,
            self._config.available_spaces_column,
        )

        missing_numeric = [
            column
            for column in required_numeric_columns
            if column not in dataframe.columns
        ]

        if missing_numeric:

            raise ProductionFeatureDataError(
                "Operational observations are missing "
                f"required occupancy columns: {missing_numeric}"
            )

        for column in required_numeric_columns:

            dataframe[column] = pd.to_numeric(
                dataframe[column],
                errors="coerce",
            )

        # ------------------------------------------------------------
        # Occupancy rate.
        #
        # Prefer persisted occupancy_rate when supplied.
        # Otherwise calculate it from occupied / total.
        # ------------------------------------------------------------

        if (
            self._config.occupancy_rate_column
            not in dataframe.columns
        ):

            dataframe[
                self._config.occupancy_rate_column
            ] = np.where(
                dataframe[
                    self._config.total_spaces_column
                ] > 0,
                dataframe[
                    self._config.occupied_spaces_column
                ]
                / dataframe[
                    self._config.total_spaces_column
                ],
                np.nan,
            )

        else:

            dataframe[
                self._config.occupancy_rate_column
            ] = pd.to_numeric(
                dataframe[
                    self._config.occupancy_rate_column
                ],
                errors="coerce",
            )

        # ------------------------------------------------------------
        # Observation presence.
        # ------------------------------------------------------------

        if (
            self._config.observation_present_column
            not in dataframe.columns
        ):

            dataframe[
                self._config.observation_present_column
            ] = True

        else:

            dataframe[
                self._config.observation_present_column
            ] = (
                dataframe[
                    self._config.observation_present_column
                ]
                .fillna(False)
                .astype(bool)
            )

        # ------------------------------------------------------------
        # Quality status.
        # ------------------------------------------------------------

        if (
            self._config.quality_status_column
            not in dataframe.columns
        ):

            dataframe[
                self._config.quality_status_column
            ] = "VALID"

        # ------------------------------------------------------------
        # Quality flags.
        # ------------------------------------------------------------

        if (
            self._config.quality_flags_column
            not in dataframe.columns
        ):

            dataframe[
                self._config.quality_flags_column
            ] = [[] for _ in range(
                len(dataframe)
            )]

        # ------------------------------------------------------------
        # Source.
        # ------------------------------------------------------------

        if (
            self._config.source_column
            not in dataframe.columns
        ):

            dataframe[
                self._config.source_column
            ] = "SMARTPARK"

        # ------------------------------------------------------------
        # Remove duplicate facility/timestamp observations.
        #
        # The database itself has:
        #
        #     UNIQUE(facility_id, observed_at)
        #
        # but production feature construction may receive a joined
        # dataframe. We fail rather than silently choose a record.
        # ------------------------------------------------------------

        duplicate_mask = dataframe.duplicated(
            subset=[
                self._config.facility_column,
                self._config.timestamp_column,
            ],
            keep=False,
        )

        if duplicate_mask.any():

            duplicate_count = int(
                duplicate_mask.sum()
            )

            raise ProductionFeatureDataError(
                "Duplicate operational observations detected "
                "for the same facility/timestamp. "
                f"Duplicate rows: {duplicate_count}."
            )

        # ------------------------------------------------------------
        # Sort by facility and timestamp.
        # ------------------------------------------------------------

        dataframe = dataframe.sort_values(
            by=[
                self._config.facility_column,
                self._config.timestamp_column,
            ],
            kind="mergesort",
        ).reset_index(
            drop=True
        )

        return dataframe

    # ========================================================================
    # PRODUCTION TIMELINE
    # ========================================================================

    def _build_production_timeline(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Build a regular 30-minute production timeline.

        Missing observations are represented explicitly instead of
        being forward-filled or interpolated.

        This is important because the existing lag and rolling
        feature generators distinguish:

            actual observation

        from:

            missing historical observation.
        """

        if dataframe.empty:

            return dataframe.copy()

        interval = pd.Timedelta(
            minutes=self._config.interval_minutes
        )

        frames: list[pd.DataFrame] = []

        for facility_code, group in dataframe.groupby(
            self._config.facility_column,
            sort=False,
        ):

            group = group.sort_values(
                self._config.timestamp_column,
                kind="mergesort",
            ).copy()

            if group.empty:
                continue

            timestamps = pd.to_datetime(
                group[
                    self._config.timestamp_column
                ]
            )

            # --------------------------------------------------------
            # Production data should already represent the canonical
            # 30-minute SmartPark modelling interval.
            #
            # We deliberately do not silently round timestamps here.
            # --------------------------------------------------------

            if self._config.strict_timestamp_alignment:

                offsets = (
                    (
                        timestamps
                        - timestamps.dt.normalize()
                    )
                    .dt.total_seconds()
                    / 60.0
                )

                aligned_minutes = (
                    offsets
                    % self._config.interval_minutes
                )

                # Allow exact slot alignment only.
                misaligned = ~np.isclose(
                    aligned_minutes.to_numpy(),
                    0.0,
                    atol=1e-9,
                )

                if bool(
                    np.any(misaligned)
                ):

                    bad_rows = group.loc[
                        misaligned,
                        [
                            self._config.facility_column,
                            self._config.timestamp_column,
                        ],
                    ]

                    sample = (
                        bad_rows.head(5)
                        .to_dict(
                            orient="records"
                        )
                    )

                    raise ProductionFeatureDataError(
                        "Operational timestamps are not aligned "
                        f"to the {self._config.interval_minutes}-minute "
                        "production modelling interval. "
                        f"Facility={facility_code!r}; "
                        f"sample={sample}"
                    )

            start = timestamps.min()
            end = timestamps.max()

            full_index = pd.date_range(
                start=start,
                end=end,
                freq=interval,
            )

            group_indexed = (
                group
                .set_index(
                    self._config.timestamp_column
                )
                .reindex(full_index)
            )

            group_indexed.index.name = (
                self._config.timestamp_column
            )

            group_indexed[
                self._config.facility_column
            ] = facility_code

            # --------------------------------------------------------
            # Determine which rows actually came from the database.
            # --------------------------------------------------------

            existing_mask = (
                group_indexed[
                    self._config.observation_present_column
                ]
                .fillna(False)
                .astype(bool)
            )

            group_indexed[
                self._config.observation_present_column
            ] = existing_mask

            # --------------------------------------------------------
            # Missing observations remain missing.
            #
            # We do NOT forward-fill occupancy.
            # --------------------------------------------------------

            missing_mask = ~existing_mask

            numeric_columns = (
                self._config.total_spaces_column,
                self._config.occupied_spaces_column,
                self._config.available_spaces_column,
                self._config.occupancy_rate_column,
            )

            for column in numeric_columns:

                if column in group_indexed.columns:

                    group_indexed.loc[
                        missing_mask,
                        column,
                    ] = np.nan

            # --------------------------------------------------------
            # Metadata for missing slots.
            # --------------------------------------------------------

            group_indexed[
                self._config.data_gap_column
            ] = missing_mask

            group_indexed[
                self._config.operational_gap_column
            ] = False

            group_indexed[
                self._config.sequence_eligible_column
            ] = existing_mask

            group_indexed[
                self._config.sequence_break_column
            ] = False

            group_indexed[
                self._config.gap_status_column
            ] = np.where(
                existing_mask,
                "CONTINUOUS",
                "DATA_GAP",
            )

            # --------------------------------------------------------
            # The first slot is a sequence boundary.
            #
            # This prevents historical calculations from implicitly
            # crossing into an unknown period before the loaded
            # production history.
            # --------------------------------------------------------

            if len(
                group_indexed
            ) > 0:

                group_indexed.iloc[
                    0,
                    group_indexed.columns.get_loc(
                        self._config.sequence_break_column
                    ),
                ] = True

                group_indexed.iloc[
                    0,
                    group_indexed.columns.get_loc(
                        self._config.gap_status_column
                    ),
                ] = "START"

            # --------------------------------------------------------
            # Missing slots following a gap start a new sequence.
            # --------------------------------------------------------

            if len(
                group_indexed
            ) > 1:

                observed = (
                    group_indexed[
                        self._config.observation_present_column
                    ]
                    .fillna(False)
                    .astype(bool)
                )

                previous_observed = (
                    observed.shift(
                        1,
                        fill_value=False,
                    )
                )

                sequence_break_mask = (
                    observed
                    & ~previous_observed
                )

                # First row already handled.
                sequence_break_mask.iloc[
                    0
                ] = True

                group_indexed.loc[
                    sequence_break_mask,
                    self._config.sequence_break_column,
                ] = True

            frames.append(
                group_indexed.reset_index()
            )

        if not frames:

            return pd.DataFrame()

        result = pd.concat(
            frames,
            axis=0,
            ignore_index=True,
        )

        result = result.sort_values(
            by=[
                self._config.facility_column,
                self._config.timestamp_column,
            ],
            kind="mergesort",
        ).reset_index(
            drop=True
        )

        # ------------------------------------------------------------
        # Normalize boolean metadata.
        # ------------------------------------------------------------

        boolean_columns = (
            self._config.observation_present_column,
            self._config.sequence_break_column,
            self._config.operational_gap_column,
            self._config.data_gap_column,
            self._config.sequence_eligible_column,
        )

        for column in boolean_columns:

            if column in result.columns:

                result[column] = (
                    result[column]
                    .fillna(False)
                    .astype(bool)
                )

        # ------------------------------------------------------------
        # Missing source values should NOT be given artificial
        # operational values.
        # ------------------------------------------------------------

        result[
            self._config.source_column
        ] = (
            result[
                self._config.source_column
            ]
            .fillna("SMARTPARK")
        )

        result[
            self._config.quality_status_column
        ] = (
            result[
                self._config.quality_status_column
            ]
            .fillna("MISSING")
        )

        return result

    # ========================================================================
    # INFERENCE TIMESTAMP
    # ========================================================================

    def _normalise_inference_timestamp(
        self,
        inference_at: pd.Timestamp | datetime | None,
    ) -> pd.Timestamp | None:
        """
        Normalize the caller's inference timestamp.

        Production inference must happen on the 30-minute modelling
        grid.

        The external service/database contract may use timezone-aware
        UTC timestamps. Internally, the feature pipeline receives
        a UTC-naive modelling timestamp so that timestamp operations
        remain consistent with the training feature pipeline.
        """

        if inference_at is None:
            return None

        try:
            timestamp = pd.Timestamp(inference_at)
        except Exception as exc:
            raise ProductionFeatureDataError(
                "inference_at is invalid."
            ) from exc

        if pd.isna(timestamp):
            raise ProductionFeatureDataError(
                "inference_at is invalid."
            )

        # --------------------------------------------------------------
        # Normalize timezone-aware timestamps to UTC and then remove
        # timezone information for the internal modelling timestamp.
        # --------------------------------------------------------------

        if timestamp.tzinfo is not None:
            timestamp = (
                timestamp
                .tz_convert("UTC")
                .tz_localize(None)
            )

        # --------------------------------------------------------------
        # Production inference must align to the modelling grid.
        # --------------------------------------------------------------

        if self._config.strict_timestamp_alignment:

            minutes = (
                timestamp.hour * 60
                + timestamp.minute
            )

            if (
                minutes
                % self._config.interval_minutes
                != 0
                or timestamp.second != 0
                or timestamp.microsecond != 0
            ):
                raise ProductionFeatureDataError(
                    "inference_at must align with the "
                    f"{self._config.interval_minutes}-minute "
                    "production modelling interval. "
                    f"Received: {timestamp}."
                )

        return timestamp

    # ========================================================================
    # FEATURE CONTRACT
    # ========================================================================

    def _normalise_model_feature_dtypes(
        self,
        dataframe: pd.DataFrame,
        feature_columns: Sequence[str],
    ) -> pd.DataFrame:
        """
        Normalise production model feature dtypes.

        The frozen production contract has exactly two categorical
        label features: ``occupancy_level`` and ``demand_class``.
        ProductionXGBoostInference applies the persisted categorical
        mappings to those two columns.

        Every other registered model feature is required to be numeric.
        Some FeaturePipeline transformations can produce numeric-looking
        code columns such as ``demand_class_code`` with pandas ``object``
        dtype. Those values must be converted to numeric before the
        production feature contract is validated.

        Invalid non-numeric values are rejected rather than silently
        converted into NaN. No feature engineering, imputation,
        interpolation, forward-fill, or future-data access is performed.
        """

        if not isinstance(dataframe, pd.DataFrame):
            raise ProductionFeatureContractError(
                "Production feature pipeline did not return a pandas DataFrame."
            )

        result = dataframe.copy()

        categorical_features = set(
            PRODUCTION_CATEGORICAL_FEATURES
        )

        numeric_feature_columns = [
            column
            for column in feature_columns
            if column not in categorical_features
        ]

        for column in numeric_feature_columns:
            if column not in result.columns:
                raise ProductionFeatureContractError(
                    "Production feature dataframe is missing "
                    f"registered model feature '{column}'."
                )

            series = result[column]

            if pd.api.types.is_numeric_dtype(series):
                try:
                    result[column] = pd.to_numeric(
                        series,
                        errors="raise",
                    )
                except (TypeError, ValueError) as exc:
                    raise ProductionFeatureContractError(
                        "Unable to normalise numeric production feature "
                        f"'{column}'."
                    ) from exc
                continue

            # Numeric-looking strings/objects such as
            # demand_class_code = "2" are legitimate numeric model
            # values and must become numeric before XGBoost inference.
            converted = pd.to_numeric(
                series,
                errors="coerce",
            )

            invalid_mask = series.notna() & converted.isna()

            if bool(invalid_mask.any()):
                invalid_values = (
                    series.loc[invalid_mask]
                    .astype(str)
                    .drop_duplicates()
                    .head(10)
                    .tolist()
                )

                raise ProductionFeatureContractError(
                    "Production model feature "
                    f"'{column}' contains non-numeric values "
                    f"outside the frozen categorical contract: "
                    f"{invalid_values}"
                )

            result[column] = converted

        return result

    def _validate_feature_contract(
        self,
        dataframe: pd.DataFrame,
        feature_columns: Sequence[str],
    ) -> None:
        """
        Validate the production feature contract.

        The current locked XGBoost model expects 296 features.
        """

        if not feature_columns:

            raise ProductionFeatureContractError(
                "Production feature pipeline returned zero "
                "model features."
            )

        missing_features = [
            column
            for column in feature_columns
            if column not in dataframe.columns
        ]

        if missing_features:

            raise ProductionFeatureContractError(
                "Production feature dataframe is missing "
                f"registered model features: {missing_features}"
            )

        duplicate_features = [
            column
            for column in dict.fromkeys(
                feature_columns
            )
            if feature_columns.count(
                column
            ) > 1
        ]

        if duplicate_features:

            raise ProductionFeatureContractError(
                "Duplicate production feature columns detected: "
                f"{duplicate_features}"
            )

        if (
            self._config.strict_feature_count
            and len(feature_columns)
            != self._config.expected_feature_count
        ):

            raise ProductionFeatureContractError(
                "Production feature-count contract violated. "
                f"Expected "
                f"{self._config.expected_feature_count} "
                f"features but received "
                f"{len(feature_columns)}."
            )

        # ------------------------------------------------------------
        # Validate model inputs.
        #
        # IMPORTANT: occupancy_level and demand_class are frozen
        # categorical model features. They remain labels here and are
        # encoded by ProductionXGBoostInference using the persisted
        # categorical_mappings.json artifact.
        # ------------------------------------------------------------

        feature_frame = dataframe[
            list(feature_columns)
        ]

        categorical_features = set(
            PRODUCTION_CATEGORICAL_FEATURES
        )

        numeric_feature_columns = [
            column
            for column in feature_frame.columns
            if column not in categorical_features
        ]

        non_numeric = [
            column
            for column in numeric_feature_columns
            if not pd.api.types.is_numeric_dtype(
                feature_frame[column]
            )
        ]

        if non_numeric:

            raise ProductionFeatureContractError(
                "Production model feature dataframe contains "
                "non-numeric features outside the frozen categorical "
                f"contract: {non_numeric}"
            )

        for column in categorical_features.intersection(
            set(feature_columns)
        ):

            if feature_frame[column].isna().any():
                raise ProductionFeatureContractError(
                    "Production categorical feature "
                    f"'{column}' contains null values."
                )

        # ------------------------------------------------------------
        # Ensure target columns never appear in production
        # model inputs.
        # ------------------------------------------------------------

        target_features = [
            column
            for column in feature_columns
            if column.startswith("target_")
        ]

        if target_features:

            raise ProductionFeatureContractError(
                "Target columns have entered the production "
                f"model feature set: {target_features}"
            )

        # ------------------------------------------------------------
        # Explicit leakage metadata.
        # ------------------------------------------------------------

        forbidden_flags = (
            "future_data_used",
            "target_data_used",
            "cross_facility_data_used",
            "forward_lookup_used",
            "centered_windows_used",
        )

        attrs = dataframe.attrs

        violations = [
            key
            for key in forbidden_flags
            if attrs.get(
                key,
                False,
            )
            is True
        ]

        if violations:

            raise ProductionFeatureContractError(
                "Production feature dataframe violates the "
                f"leakage contract: {violations}"
            )

    # ========================================================================
    # STATISTICS
    # ========================================================================

    def _build_statistics(
        self,
        *,
        input_row_count: int,
        canonical: pd.DataFrame,
        timeline: pd.DataFrame,
        result: pd.DataFrame,
        feature_columns: Sequence[str],
    ) -> ProductionFeatureStatistics:
        """
        Build production feature statistics.
        """

        observed_row_count = 0

        if (
            self._config.observation_present_column
            in timeline.columns
        ):

            observed_row_count = int(
                timeline[
                    self._config.observation_present_column
                ]
                .fillna(False)
                .astype(bool)
                .sum()
            )

        missing_row_count = (
            len(timeline)
            - observed_row_count
        )

        sequence_break_count = 0

        if (
            self._config.sequence_break_column
            in timeline.columns
        ):

            sequence_break_count = int(
                timeline[
                    self._config.sequence_break_column
                ]
                .fillna(False)
                .astype(bool)
                .sum()
            )

        data_gap_row_count = 0

        if (
            self._config.data_gap_column
            in timeline.columns
        ):

            data_gap_row_count = int(
                timeline[
                    self._config.data_gap_column
                ]
                .fillna(False)
                .astype(bool)
                .sum()
            )

        operational_gap_row_count = 0

        if (
            self._config.operational_gap_column
            in timeline.columns
        ):

            operational_gap_row_count = int(
                timeline[
                    self._config.operational_gap_column
                ]
                .fillna(False)
                .astype(bool)
                .sum()
            )

        invalid_timestamp_count = 0

        if (
            self._config.timestamp_column
            in result.columns
        ):

            invalid_timestamp_count = int(
                pd.to_datetime(
                    result[
                        self._config.timestamp_column
                    ],
                    errors="coerce",
                )
                .isna()
                .sum()
            )

        missing_required_feature_count = 0

        if feature_columns:

            missing_required_feature_count = int(
                sum(
                    column not in result.columns
                    for column in feature_columns
                )
            )

        facility_count = 0

        if (
            self._config.facility_column
            in timeline.columns
        ):

            facility_count = int(
                timeline[
                    self._config.facility_column
                ]
                .dropna()
                .astype(str)
                .nunique()
            )

        return ProductionFeatureStatistics(
            input_row_count=(
                input_row_count
            ),
            canonical_row_count=(
                len(canonical)
            ),
            timeline_row_count=(
                len(timeline)
            ),
            output_row_count=(
                len(result)
            ),
            facility_count=(
                facility_count
            ),
            observed_row_count=(
                observed_row_count
            ),
            missing_row_count=(
                missing_row_count
            ),
            sequence_break_count=(
                sequence_break_count
            ),
            data_gap_row_count=(
                data_gap_row_count
            ),
            operational_gap_row_count=(
                operational_gap_row_count
            ),
            feature_count=(
                len(feature_columns)
            ),
            invalid_timestamp_count=(
                invalid_timestamp_count
            ),
            missing_required_feature_count=(
                missing_required_feature_count
            ),
            metadata={
                "interval_minutes": (
                    self._config.interval_minutes
                ),
                "required_history_hours": (
                    self._config.required_history_hours
                ),
            },
        )

    # ========================================================================
    # INPUT VALIDATION
    # ========================================================================

    def _validate_input_dataframe(
        self,
        dataframe: pd.DataFrame,
    ) -> None:
        """
        Validate the raw operational dataframe.
        """

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):

            raise ProductionFeatureDataError(
                "observations must be a pandas DataFrame."
            )

        if dataframe.empty:

            raise ProductionFeatureDataError(
                "Operational observations dataframe is empty."
            )

        if dataframe.columns.duplicated().any():

            duplicates = (
                dataframe.columns[
                    dataframe.columns.duplicated()
                ]
                .tolist()
            )

            raise ProductionFeatureDataError(
                "Operational observations contain duplicate "
                f"columns: {duplicates}"
            )

        required_occupancy_columns = (
            self._config.total_spaces_column,
            self._config.occupied_spaces_column,
            self._config.available_spaces_column,
        )

        missing = [
            column
            for column in required_occupancy_columns
            if column not in dataframe.columns
        ]

        if missing:

            raise ProductionFeatureDataError(
                "Operational observations are missing "
                f"required columns: {missing}"
            )


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================


def build_production_features(
    observations: pd.DataFrame,
    *,
    facility_code: str | None = None,
    inference_at: pd.Timestamp | datetime | None = None,
    config: ProductionFeatureBuilderConfig | None = None,
) -> ProductionFeatureResult:
    """
    Convenience API for production feature construction.
    """

    builder = ProductionFeatureBuilder(
        config=config
    )

    return builder.build(
        observations,
        facility_code=facility_code,
        inference_at=inference_at,
    )


# ============================================================================
# PUBLIC EXPORTS
# ============================================================================


__all__ = [
    "ProductionFeatureBuilderError",
    "ProductionFeatureConfigurationError",
    "ProductionFeatureDataError",
    "ProductionFeatureContractError",
    "ProductionFeatureBuilderConfig",
    "ProductionFeatureStatistics",
    "ProductionFeatureResult",
    "ProductionFeatureBuilder",
    "build_production_features",
    "PRODUCTION_CATEGORICAL_FEATURES",
]