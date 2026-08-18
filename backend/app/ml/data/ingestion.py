"""
SmartPark AI - ML Data Ingestion Orchestration.

This module provides the orchestration layer between:

    DATA SOURCES
        |
        v
    SOURCE LOADERS
        |
        v
    VALIDATION
        |
        v
    TRANSFORMATION
        |
        v
    CANONICAL ML DATASET

The ingestion layer deliberately does NOT contain source-specific
loading logic.

Source-specific logic belongs under:

    app/ml/data/sources/

For example:

    sources/
    ├── local/
    │   ├── __init__.py
    │   └── csv.py
    │
    ├── external/
    │   ├── __init__.py
    │   └── supabase.py
    │
    └── operational/
        ├── __init__.py
        └── database.py

Current implementation
----------------------

Birmingham public dataset:

    Local filesystem
        |
        v
    CSVDataLoader
        |
        v
    DatasetValidator
        |
        v
    BirminghamDatasetTransformer
        |
        v
    Canonical ML Dataset

Future implementations
-----------------------

The same orchestration layer will support:

    LOCAL
        Birmingham
        Manchester
        Barcelona
        etc.

    EXTERNAL
        Supabase
        REST API
        Cloud storage
        Uploaded datasets
        etc.

    OPERATIONAL
        SmartPark PostgreSQL
        Parking sessions
        Reservations
        Occupancy observations
        etc.

Important architectural boundary
--------------------------------

Downstream ML components should consume the canonical output
from this module.

They should NOT need to know whether the original data came from:

    Birmingham CSV
    Supabase
    REST API
    SmartPark PostgreSQL

That source independence is one of the key architectural
objectives of the SmartPark AI ML module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from app.ml.data.loaders import (
    DataSourceType,
    LoadedDataset,
)
from app.ml.data.validators import (
    DatasetValidator,
    ValidationResult,
    validate_birmingham_dataset,
)
from app.ml.data.transformers import (
    TransformationResult,
    transform_birmingham_dataset,
)


# ============================================================
# Ingestion Stage
# ============================================================


class IngestionStage(str, Enum):
    """
    Stage reached by the ingestion pipeline.
    """

    INITIALIZED = "INITIALIZED"
    LOADED = "LOADED"
    VALIDATED = "VALIDATED"
    TRANSFORMED = "TRANSFORMED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


# ============================================================
# Ingestion Status
# ============================================================


class IngestionStatus(str, Enum):
    """
    Overall status of an ingestion operation.
    """

    SUCCESS = "SUCCESS"
    SUCCESS_WITH_WARNINGS = "SUCCESS_WITH_WARNINGS"
    FAILED = "FAILED"


# ============================================================
# Ingestion Exceptions
# ============================================================


class MLIngestionError(Exception):
    """
    Base exception for ML ingestion failures.
    """


class IngestionConfigurationError(
    MLIngestionError
):
    """
    Raised when ingestion configuration is invalid.
    """


class IngestionLoadError(
    MLIngestionError
):
    """
    Raised when the configured source cannot be loaded.
    """


class IngestionValidationError(
    MLIngestionError
):
    """
    Raised when validation prevents ingestion from continuing.
    """


class IngestionTransformationError(
    MLIngestionError
):
    """
    Raised when canonical transformation fails.
    """


# ============================================================
# Ingestion Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class IngestionConfig:
    """
    Configuration for one ingestion operation.

    Parameters
    ----------
    source_type:
        Source category.

    dataset_name:
        Logical dataset name.

    fail_on_validation_errors:
        If True, validation errors prevent transformation.

        If False, the transformer may continue where the
        transformation policy permits it.

    fail_on_validation_critical:
        Critical validation findings always stop ingestion
        when this is True.

    metadata:
        Optional caller-defined metadata.

    Examples
    --------

    Birmingham:

        IngestionConfig(
            source_type=DataSourceType.LOCAL,
            dataset_name="birmingham",
        )
    """

    source_type: DataSourceType

    dataset_name: str

    fail_on_validation_errors: bool = False

    fail_on_validation_critical: bool = True

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        """
        Validate ingestion configuration.
        """

        if not self.dataset_name.strip():
            raise IngestionConfigurationError(
                "dataset_name cannot be empty."
            )


# ============================================================
# Ingestion Result
# ============================================================


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """
    Complete result of an ML ingestion operation.

    Attributes
    ----------
    status:
        Overall ingestion status.

    stage:
        Final pipeline stage reached.

    dataset:
        Original loaded dataset.

    validation:
        Validation result.

    transformation:
        Transformation result.

    dataframe:
        Final canonical ML DataFrame.

    metadata:
        Ingestion metadata.
    """

    status: IngestionStatus

    stage: IngestionStage

    dataset: LoadedDataset

    validation: ValidationResult

    transformation: TransformationResult

    dataframe: pd.DataFrame

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )

    @property
    def row_count(self) -> int:
        """
        Number of canonical ML records.
        """

        return len(self.dataframe)

    @property
    def column_count(self) -> int:
        """
        Number of canonical ML columns.
        """

        return len(self.dataframe.columns)

    @property
    def has_validation_warnings(self) -> bool:
        """
        Whether validation produced warnings.
        """

        return (
            self.validation.report.warning_count > 0
        )

    @property
    def has_validation_errors(self) -> bool:
        """
        Whether validation produced errors.
        """

        return (
            self.validation.report.error_count > 0
        )

    @property
    def has_critical_findings(self) -> bool:
        """
        Whether validation produced critical findings.
        """

        return (
            self.validation.report.critical_count > 0
        )


# ============================================================
# Ingestion Orchestrator
# ============================================================


class MLDataIngestion:
    """
    Main ML data ingestion orchestrator.

    This class coordinates:

        loader
        validator
        transformer

    It does not contain source-specific parsing logic.
    """

    def __init__(
        self,
        *,
        config: IngestionConfig,
    ) -> None:
        self._config = config

    # ========================================================
    # Public API
    # ========================================================

    def ingest_birmingham(
        self,
        *,
        dataset_root: str | Path = "../datasets/raw",
    ) -> IngestionResult:
        """
        Ingest the Birmingham public parking dataset.

        Pipeline:

            CSV loader
                |
                v
            validation
                |
                v
            Birmingham transformation
                |
                v
            canonical dataset
        """

        self._ensure_local_source()

        try:
            dataset = self._load_birmingham(
                dataset_root=dataset_root,
            )
        except Exception as exc:
            raise IngestionLoadError(
                "Failed to load Birmingham dataset."
            ) from exc

        validation = self._validate_birmingham(
            dataset,
        )

        self._enforce_validation_policy(
            validation,
        )

        try:
            transformation = (
                transform_birmingham_dataset(
                    dataset,
                    validation_result=validation,
                )
            )
        except Exception as exc:
            raise IngestionTransformationError(
                "Failed to transform Birmingham dataset."
            ) from exc

        return self._build_result(
            dataset=dataset,
            validation=validation,
            transformation=transformation,
        )

    # ========================================================
    # Generic dispatch
    # ========================================================

    def ingest(
        self,
        *,
        dataset_root: str | Path | None = None,
    ) -> IngestionResult:
        """
        Dispatch ingestion according to configured source.

        Currently supported:

            LOCAL + birmingham

        Future sources will be added without changing the
        public ingestion contract.
        """

        source_type = self._config.source_type

        dataset_name = (
            self._config.dataset_name
            .strip()
            .lower()
        )

        if (
            source_type == DataSourceType.LOCAL
            and dataset_name == "birmingham"
        ):
            if dataset_root is None:
                dataset_root = "../datasets/raw"

            return self.ingest_birmingham(
                dataset_root=dataset_root,
            )

        raise IngestionConfigurationError(
            "Unsupported ingestion source/dataset: "
            f"source_type={source_type!r}, "
            f"dataset_name={dataset_name!r}"
        )

    # ========================================================
    # Birmingham loader
    # ========================================================

    @staticmethod
    def _load_birmingham(
        *,
        dataset_root: str | Path,
    ) -> LoadedDataset:
        """
        Load Birmingham using the local CSV source adapter.

        Import is kept inside the method to avoid forcing all
        future source dependencies to load when only another
        source is being used.
        """

        from app.ml.data.sources.local.csv import (
            load_local_csv,
        )

        return load_local_csv(
            dataset_root=dataset_root,
            dataset_name="birmingham",
        )

    # ========================================================
    # Birmingham validator
    # ========================================================

    @staticmethod
    def _validate_birmingham(
        dataset: LoadedDataset,
    ) -> ValidationResult:
        """
        Validate the Birmingham dataset.
        """

        return validate_birmingham_dataset(
            dataset,
        )

    # ========================================================
    # Validation policy
    # ========================================================

    def _enforce_validation_policy(
        self,
        validation: ValidationResult,
    ) -> None:
        """
        Decide whether validation findings should prevent
        transformation.

        Important:

        Validation errors do not automatically mean the source
        dataset cannot be transformed.

        Some known issues are intentionally handled by the
        transformation policy.

        For example, Birmingham contains:

            negative occupancy
            exact duplicates
            occupancy > capacity

        The transformer has explicit policies for these.

        Critical findings remain capable of stopping ingestion.
        """

        report = validation.report

        if (
            self._config.fail_on_validation_critical
            and report.critical_count > 0
        ):
            raise IngestionValidationError(
                "Critical validation findings prevent "
                "ingestion."
            )

        if (
            self._config.fail_on_validation_errors
            and report.error_count > 0
        ):
            raise IngestionValidationError(
                "Validation errors prevent ingestion "
                "under the configured policy."
            )

    # ========================================================
    # Result builder
    # ========================================================

    def _build_result(
        self,
        *,
        dataset: LoadedDataset,
        validation: ValidationResult,
        transformation: TransformationResult,
    ) -> IngestionResult:
        """
        Build the final IngestionResult.
        """

        status = self._determine_status(
            validation,
        )

        return IngestionResult(
            status=status,
            stage=IngestionStage.COMPLETED,
            dataset=dataset,
            validation=validation,
            transformation=transformation,
            dataframe=transformation.dataframe,
            metadata={
                "source_type": (
                    self._config.source_type.value
                ),
                "dataset_name": (
                    self._config.dataset_name
                ),
                **dict(self._config.metadata),
            },
        )

    # ========================================================
    # Status determination
    # ========================================================

    @staticmethod
    def _determine_status(
        validation: ValidationResult,
    ) -> IngestionStatus:
        """
        Determine final ingestion status.

        SUCCESS
            No warnings or errors.

        SUCCESS_WITH_WARNINGS
            Validation produced findings, but the ingestion
            completed successfully according to transformation
            policy.

        FAILED
            Reserved for future use where a pipeline can return
            a result object rather than raising an exception.
        """

        report = validation.report

        if (
            report.warning_count > 0
            or report.error_count > 0
            or report.critical_count > 0
        ):
            return IngestionStatus.SUCCESS_WITH_WARNINGS

        return IngestionStatus.SUCCESS

    # ========================================================
    # Source guard
    # ========================================================

    def _ensure_local_source(self) -> None:
        """
        Ensure the configured source is LOCAL for Birmingham.
        """

        if (
            self._config.source_type
            != DataSourceType.LOCAL
        ):
            raise IngestionConfigurationError(
                "Birmingham ingestion requires "
                "DataSourceType.LOCAL."
            )

    # ========================================================
    # Representation
    # ========================================================

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"source_type="
            f"'{self._config.source_type.value}', "
            f"dataset="
            f"'{self._config.dataset_name}')"
        )


# ============================================================
# Convenience Factory
# ============================================================


def create_ingestion_pipeline(
    *,
    source_type: DataSourceType,
    dataset_name: str,
    fail_on_validation_errors: bool = False,
    fail_on_validation_critical: bool = True,
    metadata: Mapping[str, Any] | None = None,
) -> MLDataIngestion:
    """
    Create an MLDataIngestion pipeline.

    Example
    -------

        ingestion = create_ingestion_pipeline(
            source_type=DataSourceType.LOCAL,
            dataset_name="birmingham",
        )

        result = ingestion.ingest(
            dataset_root="../datasets/raw",
        )
    """

    config = IngestionConfig(
        source_type=source_type,
        dataset_name=dataset_name,
        fail_on_validation_errors=(
            fail_on_validation_errors
        ),
        fail_on_validation_critical=(
            fail_on_validation_critical
        ),
        metadata=metadata or {},
    )

    return MLDataIngestion(
        config=config,
    )


# ============================================================
# Birmingham Convenience Function
# ============================================================


def ingest_birmingham_dataset(
    *,
    dataset_root: str | Path = "../datasets/raw",
) -> IngestionResult:
    """
    Convenience function for Birmingham ingestion.

    This is the simplest public entry point for the current
    Birmingham pipeline.

    Example
    -------

        result = ingest_birmingham_dataset()

        df = result.dataframe
    """

    ingestion = create_ingestion_pipeline(
        source_type=DataSourceType.LOCAL,
        dataset_name="birmingham",
    )

    return ingestion.ingest(
        dataset_root=dataset_root,
    )


# ============================================================
# Public API
# ============================================================


__all__ = [
    # Enums
    "IngestionStage",
    "IngestionStatus",

    # Exceptions
    "MLIngestionError",
    "IngestionConfigurationError",
    "IngestionLoadError",
    "IngestionValidationError",
    "IngestionTransformationError",

    # Configuration/results
    "IngestionConfig",
    "IngestionResult",

    # Main orchestrator
    "MLDataIngestion",

    # Factories/convenience
    "create_ingestion_pipeline",
    "ingest_birmingham_dataset",
]