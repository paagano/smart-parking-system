"""
SmartPark AI - ML Data Transformation Layer.

This module transforms source datasets into the canonical dataset
used by the SmartPark AI machine-learning pipeline.

Pipeline position
-----------------

    DATA SOURCE
         |
         v
       LOADER
         |
         v
    LoadedDataset
         |
         v
     VALIDATOR
         |
         v
 ValidationResult
         |
         v
    TRANSFORMER
         |
         v
 Canonical ML Dataset
         |
         v
 FEATURE ENGINEERING
         |
         v
  MODEL DATASET
         |
         +-------------------+
         |                   |
         v                   v
      XGBoost              LSTM
         |                   |
         +---------+---------+
                   |
                   v
            MODEL EVALUATION
                   |
                   v
              FORECASTING


Design principles
-----------------

1. Never mutate the source DataFrame.

2. Never silently modify raw measurements.

3. Separate validation from transformation.

4. Preserve data-quality lineage.

5. Produce a source-independent canonical schema.

6. Keep source-specific rules inside source-specific
   configurations.

7. Make transformations deterministic and reproducible.

8. Preserve anomalies that may contain useful information,
   while explicitly flagging them.

Birmingham source schema
------------------------

    SystemCodeNumber
    Capacity
    Occupancy
    LastUpdated


Canonical ML schema
-------------------

    source_facility_code
    observed_at
    total_spaces
    occupied_spaces
    available_spaces
    raw_occupancy_rate
    occupancy_rate
    source
    quality_flags
    quality_status


Birmingham transformation policy
---------------------------------

Exact duplicates:

    Remove redundant copies and retain the first occurrence.

Negative occupancy:

    Remove from ML-ready data.

Occupancy > capacity:

    Retain the observation.

    Preserve the original occupancy.

    Flag:

        CAPACITY_EXCEEDED

    Preserve raw occupancy rate.

    Bound ML occupancy_rate to [0, 1].

Invalid timestamps:

    Remove from ML-ready data.

Zero capacity:

    Preserve the observation only if otherwise valid, but
    occupancy rate becomes NaN because no meaningful rate can
    be calculated.

Canonical output:

    Only canonical columns are exposed in the final DataFrame.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

import pandas as pd

from app.ml.data.loaders import (
    LoadedDataset,
)
from app.ml.data.validators import (
    ValidationResult,
)


# ============================================================
# Canonical Schema
# ============================================================


class CanonicalColumn(str, Enum):
    """
    Canonical SmartPark ML dataset columns.
    """

    SOURCE_FACILITY_CODE = "source_facility_code"
    OBSERVED_AT = "observed_at"
    TOTAL_SPACES = "total_spaces"
    OCCUPIED_SPACES = "occupied_spaces"
    AVAILABLE_SPACES = "available_spaces"
    RAW_OCCUPANCY_RATE = "raw_occupancy_rate"
    OCCUPANCY_RATE = "occupancy_rate"
    SOURCE = "source"
    QUALITY_FLAGS = "quality_flags"
    QUALITY_STATUS = "quality_status"


CANONICAL_COLUMNS: tuple[str, ...] = (
    CanonicalColumn.SOURCE_FACILITY_CODE.value,
    CanonicalColumn.OBSERVED_AT.value,
    CanonicalColumn.TOTAL_SPACES.value,
    CanonicalColumn.OCCUPIED_SPACES.value,
    CanonicalColumn.AVAILABLE_SPACES.value,
    CanonicalColumn.RAW_OCCUPANCY_RATE.value,
    CanonicalColumn.OCCUPANCY_RATE.value,
    CanonicalColumn.SOURCE.value,
    CanonicalColumn.QUALITY_FLAGS.value,
    CanonicalColumn.QUALITY_STATUS.value,
)


# ============================================================
# Quality Status
# ============================================================


class QualityStatus(str, Enum):
    """
    Overall quality state of a canonical observation.
    """

    CLEAN = "CLEAN"
    FLAGGED = "FLAGGED"


class QualityFlag(str, Enum):
    """
    Machine-readable data-quality flags.
    """

    CAPACITY_EXCEEDED = "CAPACITY_EXCEEDED"


# ============================================================
# Exceptions
# ============================================================


class MLTransformationError(Exception):
    """Base exception for ML transformation errors."""


class TransformationConfigurationError(
    MLTransformationError
):
    """Raised when transformation configuration is invalid."""


class TransformationSchemaError(
    MLTransformationError
):
    """Raised when required source columns are missing."""


class TransformationDataError(
    MLTransformationError
):
    """Raised when source data cannot be safely transformed."""


class EmptyTransformedDatasetError(
    MLTransformationError
):
    """Raised when no usable records remain after transformation."""


# ============================================================
# Transformation Statistics
# ============================================================


@dataclass(frozen=True, slots=True)
class TransformationStatistics:
    """
    Complete audit statistics for one transformation run.
    """

    source_row_count: int

    duplicate_groups: int

    duplicate_rows_in_groups: int

    duplicate_rows_removed: int

    negative_occupancy_rows_removed: int

    capacity_exceeded_rows_retained: int

    invalid_timestamp_rows_removed: int

    invalid_numeric_rows_removed: int

    zero_capacity_rows_retained: int

    final_row_count: int

    source_column_count: int

    final_column_count: int

    source_name: str

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    @property
    def total_rows_removed(self) -> int:
        """
        Total number of source rows removed.
        """

        return (
            self.duplicate_rows_removed
            + self.negative_occupancy_rows_removed
            + self.invalid_timestamp_rows_removed
            + self.invalid_numeric_rows_removed
        )

    @property
    def retention_rate(self) -> float:
        """
        Percentage of source records retained.
        """

        if self.source_row_count == 0:
            return 0.0

        return (
            self.final_row_count
            / self.source_row_count
        )

    @property
    def removal_rate(self) -> float:
        """
        Percentage of source records removed.
        """

        if self.source_row_count == 0:
            return 0.0

        return 1.0 - self.retention_rate


# ============================================================
# Transformation Result
# ============================================================


@dataclass(frozen=True, slots=True)
class TransformationResult:
    """
    Complete result of a transformation operation.
    """

    dataframe: pd.DataFrame

    statistics: TransformationStatistics

    source_dataset: LoadedDataset

    validation_result: ValidationResult | None = None


# ============================================================
# Transformation Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class TransformationConfig:
    """
    Source-to-canonical transformation configuration.
    """

    source_facility_column: str

    timestamp_column: str

    capacity_column: str

    occupancy_column: str

    source_name: str

    remove_exact_duplicates: bool = True

    remove_negative_occupancy: bool = True

    retain_capacity_exceeded: bool = True

    clip_occupancy_rate: bool = True

    remove_invalid_timestamps: bool = True

    remove_invalid_numeric_rows: bool = True

    retain_zero_capacity: bool = True

    sort_output: bool = True

    def __post_init__(self) -> None:
        """
        Validate transformation configuration.
        """

        fields = (
            self.source_facility_column,
            self.timestamp_column,
            self.capacity_column,
            self.occupancy_column,
            self.source_name,
        )

        if any(
            not isinstance(value, str)
            or not value.strip()
            for value in fields
        ):
            raise TransformationConfigurationError(
                "Transformation configuration contains "
                "an empty or invalid field."
            )


# ============================================================
# Birmingham Configuration
# ============================================================


BIRMINGHAM_TRANSFORMATION_CONFIG = (
    TransformationConfig(
        source_facility_column="SystemCodeNumber",
        timestamp_column="LastUpdated",
        capacity_column="Capacity",
        occupancy_column="Occupancy",
        source_name="BIRMINGHAM",
        remove_exact_duplicates=True,
        remove_negative_occupancy=True,
        retain_capacity_exceeded=True,
        clip_occupancy_rate=True,
        remove_invalid_timestamps=True,
        remove_invalid_numeric_rows=True,
        retain_zero_capacity=True,
        sort_output=True,
    )
)


# ============================================================
# Main Transformer
# ============================================================


class DatasetTransformer:
    """
    Generic source-to-canonical ML transformer.

    The source DataFrame is copied before transformation and is
    never modified in-place.
    """

    def __init__(
        self,
        config: TransformationConfig,
    ) -> None:
        self._config = config

    # ========================================================
    # Public API
    # ========================================================

    def transform(
        self,
        dataset: LoadedDataset,
        *,
        validation_result: ValidationResult | None = None,
    ) -> TransformationResult:
        """
        Transform a LoadedDataset into the canonical ML schema.
        """

        dataframe = self._copy_source_dataframe(
            dataset,
        )

        source_row_count = len(dataframe)

        source_column_count = len(
            dataframe.columns
        )

        self._validate_source_schema(
            dataframe,
        )

        # ----------------------------------------------------
        # Step 1: Exact duplicate analysis/removal
        # ----------------------------------------------------

        (
            dataframe,
            duplicate_groups,
            duplicate_rows_in_groups,
            duplicate_rows_removed,
        ) = self._remove_exact_duplicates(
            dataframe,
        )

        # ----------------------------------------------------
        # Step 2: Timestamp transformation
        # ----------------------------------------------------

        (
            dataframe,
            invalid_timestamp_count,
        ) = self._transform_timestamp(
            dataframe,
        )

        # ----------------------------------------------------
        # Step 3: Numeric transformation
        # ----------------------------------------------------

        (
            dataframe,
            invalid_numeric_count,
        ) = self._transform_numeric_columns(
            dataframe,
        )

        # ----------------------------------------------------
        # Step 4: Remove negative occupancy
        # ----------------------------------------------------

        (
            dataframe,
            negative_occupancy_count,
        ) = self._remove_negative_occupancy(
            dataframe,
        )

        # ----------------------------------------------------
        # Step 5: Handle capacity-exceeded observations
        # ----------------------------------------------------

        (
            dataframe,
            capacity_exceeded_count,
        ) = self._identify_capacity_exceeded(
            dataframe,
        )

        # ----------------------------------------------------
        # Step 6: Handle zero-capacity observations
        # ----------------------------------------------------

        (
            dataframe,
            zero_capacity_count,
        ) = self._handle_zero_capacity(
            dataframe,
        )

        # ----------------------------------------------------
        # Step 7: Build canonical schema
        # ----------------------------------------------------

        dataframe = self._build_canonical_dataset(
            dataframe,
        )

        # ----------------------------------------------------
        # Step 8: Quality metadata
        # ----------------------------------------------------

        dataframe = self._build_quality_metadata(
            dataframe,
        )

        # ----------------------------------------------------
        # Step 9: Enforce canonical schema
        # ----------------------------------------------------

        dataframe = self._select_canonical_columns(
            dataframe,
        )

        # ----------------------------------------------------
        # Step 10: Deterministic sorting
        # ----------------------------------------------------

        if self._config.sort_output:
            dataframe = self._sort_output(
                dataframe,
            )

        # ----------------------------------------------------
        # Step 11: Final integrity checks
        # ----------------------------------------------------

        self._validate_transformed_dataset(
            dataframe,
        )

        statistics = TransformationStatistics(
            source_row_count=source_row_count,
            duplicate_groups=duplicate_groups,
            duplicate_rows_in_groups=(
                duplicate_rows_in_groups
            ),
            duplicate_rows_removed=(
                duplicate_rows_removed
            ),
            negative_occupancy_rows_removed=(
                negative_occupancy_count
            ),
            capacity_exceeded_rows_retained=(
                capacity_exceeded_count
            ),
            invalid_timestamp_rows_removed=(
                invalid_timestamp_count
            ),
            invalid_numeric_rows_removed=(
                invalid_numeric_count
            ),
            zero_capacity_rows_retained=(
                zero_capacity_count
            ),
            final_row_count=len(dataframe),
            source_column_count=source_column_count,
            final_column_count=len(
                dataframe.columns
            ),
            source_name=self._config.source_name,
            metadata={
                "canonical_columns": CANONICAL_COLUMNS,
            },
        )

        return TransformationResult(
            dataframe=dataframe,
            statistics=statistics,
            source_dataset=dataset,
            validation_result=validation_result,
        )

    # ========================================================
    # Defensive source copy
    # ========================================================

    @staticmethod
    def _copy_source_dataframe(
        dataset: LoadedDataset,
    ) -> pd.DataFrame:
        """
        Return a deep copy of the source DataFrame.
        """

        if not isinstance(
            dataset.dataframe,
            pd.DataFrame,
        ):
            raise TransformationDataError(
                "Loaded dataset does not contain "
                "a pandas DataFrame."
            )

        return dataset.dataframe.copy(
            deep=True,
        )

    # ========================================================
    # Source schema
    # ========================================================

    def _validate_source_schema(
        self,
        dataframe: pd.DataFrame,
    ) -> None:
        """
        Ensure all required source columns exist.
        """

        required = {
            self._config.source_facility_column,
            self._config.timestamp_column,
            self._config.capacity_column,
            self._config.occupancy_column,
        }

        missing = sorted(
            required - set(dataframe.columns)
        )

        if missing:
            raise TransformationSchemaError(
                "Required transformation columns are missing: "
                f"{', '.join(missing)}"
            )

    # ========================================================
    # Duplicate analysis/removal
    # ========================================================

    def _remove_exact_duplicates(
        self,
        dataframe: pd.DataFrame,
    ) -> tuple[
        pd.DataFrame,
        int,
        int,
        int,
    ]:
        """
        Analyze and remove exact duplicate rows.

        Returns
        -------

        transformed_dataframe,
        duplicate_groups,
        duplicate_rows_in_groups,
        duplicate_rows_removed

        Example
        -------

        A
        A
        A

        gives:

            duplicate_groups = 1
            rows_in_groups = 3
            rows_removed = 2
        """

        if not self._config.remove_exact_duplicates:
            return dataframe, 0, 0, 0

        duplicate_mask = dataframe.duplicated(
            keep=False,
        )

        duplicate_rows_in_groups = int(
            duplicate_mask.sum()
        )

        if duplicate_rows_in_groups == 0:
            return dataframe, 0, 0, 0

        duplicate_groups = int(
            dataframe.loc[
                duplicate_mask
            ].duplicated(
                keep="first",
            ).sum()
        )

        # The above expression gives the number of redundant
        # rows across the duplicate subset. We calculate the
        # actual duplicate groups separately below to avoid
        # ambiguity.

        duplicate_group_frame = (
            dataframe.loc[
                duplicate_mask
            ]
        )

        duplicate_group_ids = (
            duplicate_group_frame
            .apply(
                lambda row: tuple(
                    row.tolist()
                ),
                axis=1,
            )
        )

        duplicate_groups = int(
            duplicate_group_ids.nunique()
        )

        redundant_mask = dataframe.duplicated(
            keep="first",
        )

        duplicate_rows_removed = int(
            redundant_mask.sum()
        )

        transformed = dataframe.loc[
            ~redundant_mask
        ].copy()

        return (
            transformed,
            duplicate_groups,
            duplicate_rows_in_groups,
            duplicate_rows_removed,
        )

    # ========================================================
    # Timestamp
    # ========================================================

    def _transform_timestamp(
        self,
        dataframe: pd.DataFrame,
    ) -> tuple[
        pd.DataFrame,
        int,
    ]:
        """
        Parse source timestamps into observed_at.
        """

        source_column = (
            self._config.timestamp_column
        )

        parsed = pd.to_datetime(
            dataframe[source_column],
            errors="coerce",
        )

        invalid_mask = parsed.isna()

        invalid_count = int(
            invalid_mask.sum()
        )

        transformed = dataframe.copy()

        transformed[
            CanonicalColumn.OBSERVED_AT.value
        ] = parsed

        if (
            self._config.remove_invalid_timestamps
            and invalid_count > 0
        ):
            transformed = transformed.loc[
                ~invalid_mask
            ].copy()

        return transformed, invalid_count

    # ========================================================
    # Numeric conversion
    # ========================================================

    def _transform_numeric_columns(
        self,
        dataframe: pd.DataFrame,
    ) -> tuple[
        pd.DataFrame,
        int,
    ]:
        """
        Convert capacity and occupancy to numeric values.

        Rows where either required numeric value cannot be
        interpreted are removed when configured.
        """

        transformed = dataframe.copy()

        capacity = pd.to_numeric(
            transformed[
                self._config.capacity_column
            ],
            errors="coerce",
        )

        occupancy = pd.to_numeric(
            transformed[
                self._config.occupancy_column
            ],
            errors="coerce",
        )

        invalid_mask = (
            capacity.isna()
            | occupancy.isna()
        )

        invalid_count = int(
            invalid_mask.sum()
        )

        transformed[
            CanonicalColumn.TOTAL_SPACES.value
        ] = capacity

        transformed[
            CanonicalColumn.OCCUPIED_SPACES.value
        ] = occupancy

        if (
            self._config.remove_invalid_numeric_rows
            and invalid_count > 0
        ):
            transformed = transformed.loc[
                ~invalid_mask
            ].copy()

        return transformed, invalid_count

    # ========================================================
    # Negative occupancy
    # ========================================================

    def _remove_negative_occupancy(
        self,
        dataframe: pd.DataFrame,
    ) -> tuple[
        pd.DataFrame,
        int,
    ]:
        """
        Remove physically impossible negative occupancy.
        """

        occupancy = dataframe[
            CanonicalColumn.OCCUPIED_SPACES.value
        ]

        negative_mask = (
            occupancy < 0
        )

        negative_count = int(
            negative_mask.sum()
        )

        if (
            not self._config.remove_negative_occupancy
            or negative_count == 0
        ):
            return dataframe, 0

        transformed = dataframe.loc[
            ~negative_mask
        ].copy()

        return transformed, negative_count

    # ========================================================
    # Capacity exceeded
    # ========================================================

    def _identify_capacity_exceeded(
        self,
        dataframe: pd.DataFrame,
    ) -> tuple[
        pd.DataFrame,
        int,
    ]:
        """
        Identify observations where occupancy exceeds capacity.

        The actual source measurement is preserved.
        """

        capacity = dataframe[
            CanonicalColumn.TOTAL_SPACES.value
        ]

        occupancy = dataframe[
            CanonicalColumn.OCCUPIED_SPACES.value
        ]

        exceeded_mask = (
            capacity.notna()
            & occupancy.notna()
            & (occupancy > capacity)
        )

        count = int(
            exceeded_mask.sum()
        )

        transformed = dataframe.copy()

        transformed["_capacity_exceeded"] = (
            exceeded_mask
        )

        if (
            not self._config.retain_capacity_exceeded
            and count > 0
        ):
            transformed = transformed.loc[
                ~exceeded_mask
            ].copy()

        return transformed, count

    # ========================================================
    # Zero capacity
    # ========================================================

    def _handle_zero_capacity(
        self,
        dataframe: pd.DataFrame,
    ) -> tuple[
        pd.DataFrame,
        int,
    ]:
        """
        Handle zero-capacity observations.

        We retain them by default because removing records
        without inspecting the source semantics would be
        premature.

        Occupancy rate becomes NaN for zero capacity.
        """

        capacity = dataframe[
            CanonicalColumn.TOTAL_SPACES.value
        ]

        zero_mask = (
            capacity == 0
        )

        zero_count = int(
            zero_mask.sum()
        )

        if (
            self._config.retain_zero_capacity
            or zero_count == 0
        ):
            return dataframe, zero_count

        transformed = dataframe.loc[
            ~zero_mask
        ].copy()

        return transformed, zero_count

    # ========================================================
    # Canonical dataset
    # ========================================================

    def _build_canonical_dataset(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Build canonical source-independent fields.
        """

        transformed = dataframe.copy()

        # ----------------------------------------------------
        # Facility
        # ----------------------------------------------------

        transformed[
            CanonicalColumn.SOURCE_FACILITY_CODE.value
        ] = (
            transformed[
                self._config.source_facility_column
            ]
            .astype("string")
            .str.strip()
        )

        # ----------------------------------------------------
        # Available spaces
        # ----------------------------------------------------

        transformed[
            CanonicalColumn.AVAILABLE_SPACES.value
        ] = (
            transformed[
                CanonicalColumn.TOTAL_SPACES.value
            ]
            - transformed[
                CanonicalColumn.OCCUPIED_SPACES.value
            ]
        )

        # ----------------------------------------------------
        # Raw occupancy rate
        # ----------------------------------------------------

        transformed[
            CanonicalColumn.RAW_OCCUPANCY_RATE.value
        ] = self._calculate_raw_occupancy_rate(
            transformed,
        )

        # ----------------------------------------------------
        # ML occupancy rate
        # ----------------------------------------------------

        transformed[
            CanonicalColumn.OCCUPANCY_RATE.value
        ] = self._calculate_ml_occupancy_rate(
            transformed,
        )

        # ----------------------------------------------------
        # Source
        # ----------------------------------------------------

        transformed[
            CanonicalColumn.SOURCE.value
        ] = self._config.source_name

        return transformed

    # ========================================================
    # Raw occupancy rate
    # ========================================================

    @staticmethod
    def _calculate_raw_occupancy_rate(
        dataframe: pd.DataFrame,
    ) -> pd.Series:
        """
        Calculate the unbounded occupancy rate.

            occupied_spaces / total_spaces

        Capacity-exceeded observations therefore produce rates
        greater than 1.0.

        Zero-capacity observations produce NaN.
        """

        capacity = dataframe[
            CanonicalColumn.TOTAL_SPACES.value
        ]

        occupancy = dataframe[
            CanonicalColumn.OCCUPIED_SPACES.value
        ]

        rate = occupancy.div(
            capacity,
        )

        return rate.replace(
            [
                float("inf"),
                float("-inf"),
            ],
            pd.NA,
        )

    # ========================================================
    # ML occupancy rate
    # ========================================================

    def _calculate_ml_occupancy_rate(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.Series:
        """
        Calculate the bounded occupancy rate used by ML.

        Raw:

            occupied / capacity

        ML:

            clipped to [0, 1]
        """

        raw_rate = dataframe[
            CanonicalColumn.RAW_OCCUPANCY_RATE.value
        ]

        if not self._config.clip_occupancy_rate:
            return raw_rate

        return raw_rate.clip(
            lower=0.0,
            upper=1.0,
        )

    # ========================================================
    # Quality metadata
    # ========================================================

    def _build_quality_metadata(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Build quality flags and quality status.
        """

        transformed = dataframe.copy()

        flags: list[list[str]] = []

        exceeded = transformed[
            "_capacity_exceeded"
        ]

        for value in exceeded:
            row_flags: list[str] = []

            if bool(value):
                row_flags.append(
                    QualityFlag.CAPACITY_EXCEEDED.value
                )

            flags.append(
                row_flags
            )

        transformed[
            CanonicalColumn.QUALITY_FLAGS.value
        ] = flags

        transformed[
            CanonicalColumn.QUALITY_STATUS.value
        ] = [
            (
                QualityStatus.FLAGGED.value
                if row_flags
                else QualityStatus.CLEAN.value
            )
            for row_flags in flags
        ]

        transformed = transformed.drop(
            columns=[
                "_capacity_exceeded",
            ],
            errors="ignore",
        )

        return transformed

    # ========================================================
    # Canonical-only projection
    # ========================================================

    @staticmethod
    def _select_canonical_columns(
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Return ONLY the canonical ML columns.

        This is a critical boundary in the ML pipeline.

        After this method, downstream components must not need
        to know whether the source was Birmingham, Manchester,
        Supabase, or SmartPark PostgreSQL.
        """

        missing = (
            set(CANONICAL_COLUMNS)
            - set(dataframe.columns)
        )

        if missing:
            raise TransformationSchemaError(
                "Cannot produce canonical dataset. "
                "Missing columns: "
                f"{', '.join(sorted(missing))}"
            )

        return dataframe.loc[
            :,
            list(CANONICAL_COLUMNS),
        ].copy()

    # ========================================================
    # Sorting
    # ========================================================

    @staticmethod
    def _sort_output(
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Sort by facility and observation timestamp.
        """

        return (
            dataframe
            .sort_values(
                by=[
                    CanonicalColumn
                    .SOURCE_FACILITY_CODE.value,
                    CanonicalColumn
                    .OBSERVED_AT.value,
                ],
                kind="stable",
            )
            .reset_index(
                drop=True,
            )
        )

    # ========================================================
    # Final integrity validation
    # ========================================================

    @staticmethod
    def _validate_transformed_dataset(
        dataframe: pd.DataFrame,
    ) -> None:
        """
        Perform final integrity checks on the canonical dataset.
        """

        if dataframe.empty:
            raise EmptyTransformedDatasetError(
                "Transformation produced no usable records."
            )

        # ----------------------------------------------------
        # Exact schema
        # ----------------------------------------------------

        actual_columns = tuple(
            dataframe.columns
        )

        if actual_columns != CANONICAL_COLUMNS:
            raise TransformationSchemaError(
                "Canonical DataFrame schema mismatch.\n"
                f"Expected: {CANONICAL_COLUMNS}\n"
                f"Actual:   {actual_columns}"
            )

        # ----------------------------------------------------
        # Required values
        # ----------------------------------------------------

        if dataframe[
            CanonicalColumn.SOURCE_FACILITY_CODE.value
        ].isna().any():
            raise TransformationDataError(
                "Canonical dataset contains null "
                "facility identifiers."
            )

        if dataframe[
            CanonicalColumn.OBSERVED_AT.value
        ].isna().any():
            raise TransformationDataError(
                "Canonical dataset contains null "
                "observation timestamps."
            )

        if dataframe[
            CanonicalColumn.TOTAL_SPACES.value
        ].isna().any():
            raise TransformationDataError(
                "Canonical dataset contains null "
                "capacity values."
            )

        if dataframe[
            CanonicalColumn.OCCUPIED_SPACES.value
        ].isna().any():
            raise TransformationDataError(
                "Canonical dataset contains null "
                "occupancy values."
            )

        # ----------------------------------------------------
        # Physical occupancy rules
        # ----------------------------------------------------

        if (
            dataframe[
                CanonicalColumn.OCCUPIED_SPACES.value
            ] < 0
        ).any():
            raise TransformationDataError(
                "Canonical dataset contains negative "
                "occupancy values."
            )

        # ----------------------------------------------------
        # ML occupancy-rate bounds
        # ----------------------------------------------------

        occupancy_rate = dataframe[
            CanonicalColumn.OCCUPANCY_RATE.value
        ]

        finite_rates = occupancy_rate.dropna()

        if (
            (finite_rates < 0).any()
            or (finite_rates > 1).any()
        ):
            raise TransformationDataError(
                "Canonical occupancy_rate contains values "
                "outside [0, 1]."
            )

        # ----------------------------------------------------
        # Source field
        # ----------------------------------------------------

        source_values = (
            dataframe[
                CanonicalColumn.SOURCE.value
            ]
            .dropna()
            .astype(str)
            .str.strip()
        )

        if source_values.empty:
            raise TransformationDataError(
                "Canonical dataset contains no source values."
            )

        # ----------------------------------------------------
        # Quality status
        # ----------------------------------------------------

        valid_statuses = {
            QualityStatus.CLEAN.value,
            QualityStatus.FLAGGED.value,
        }

        actual_statuses = set(
            dataframe[
                CanonicalColumn.QUALITY_STATUS.value
            ]
            .dropna()
            .astype(str)
        )

        unexpected_statuses = (
            actual_statuses
            - valid_statuses
        )

        if unexpected_statuses:
            raise TransformationDataError(
                "Unexpected quality status values: "
                f"{sorted(unexpected_statuses)}"
            )

    # ========================================================
    # Representation
    # ========================================================

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"source='{self._config.source_name}', "
            f"facility_column="
            f"'{self._config.source_facility_column}', "
            f"timestamp_column="
            f"'{self._config.timestamp_column}')"
        )


# ============================================================
# Birmingham Transformer
# ============================================================


class BirminghamDatasetTransformer(
    DatasetTransformer,
):
    """
    Transformer for the Birmingham public parking dataset.
    """

    def __init__(self) -> None:
        super().__init__(
            BIRMINGHAM_TRANSFORMATION_CONFIG,
        )


# ============================================================
# Factory
# ============================================================


def create_transformer(
    config: TransformationConfig,
) -> DatasetTransformer:
    """
    Create a generic DatasetTransformer.
    """

    return DatasetTransformer(
        config,
    )


# ============================================================
# Birmingham Convenience Function
# ============================================================


def transform_birmingham_dataset(
    dataset: LoadedDataset,
    *,
    validation_result: ValidationResult | None = None,
) -> TransformationResult:
    """
    Transform a Birmingham dataset into the canonical
    SmartPark ML dataset.
    """

    transformer = BirminghamDatasetTransformer()

    return transformer.transform(
        dataset,
        validation_result=validation_result,
    )


# ============================================================
# Validate + Transform Convenience Pipeline
# ============================================================


def validate_and_transform_birmingham(
    dataset: LoadedDataset,
) -> TransformationResult:
    """
    Run Birmingham validation followed by transformation.

    This convenience function is useful for experiments and
    integration tests.

    Validation and transformation remain independently usable.
    """

    from app.ml.data.validators import (
        validate_birmingham_dataset,
    )

    validation_result = (
        validate_birmingham_dataset(
            dataset,
        )
    )

    return transform_birmingham_dataset(
        dataset,
        validation_result=validation_result,
    )


# ============================================================
# Public API
# ============================================================


__all__ = [
    # Schema
    "CanonicalColumn",
    "CANONICAL_COLUMNS",

    # Quality
    "QualityStatus",
    "QualityFlag",

    # Exceptions
    "MLTransformationError",
    "TransformationConfigurationError",
    "TransformationSchemaError",
    "TransformationDataError",
    "EmptyTransformedDatasetError",

    # Results
    "TransformationStatistics",
    "TransformationResult",

    # Configuration
    "TransformationConfig",
    "BIRMINGHAM_TRANSFORMATION_CONFIG",

    # Transformers
    "DatasetTransformer",
    "BirminghamDatasetTransformer",

    # Factories
    "create_transformer",

    # Convenience
    "transform_birmingham_dataset",
    "validate_and_transform_birmingham",
]