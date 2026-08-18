"""
SmartPark AI - ML Data Loader Contracts and Registry.

This module defines the common interfaces and orchestration layer
for all SmartPark AI machine-learning data sources.

Supported source families
-------------------------

1. LOCAL / PUBLIC DATASETS

   Examples:
       datasets/raw/birmingham/dataset.csv
       datasets/raw/manchester/dataset.csv
       datasets/raw/barcelona/dataset.csv

2. EXTERNAL DATA SOURCES

   Examples:
       Supabase
       REST APIs
       Cloud storage
       Uploaded datasets

3. SMARTPARK OPERATIONAL DATA

   Examples:
       SmartPark PostgreSQL database
       occupancy_observations
       parking_sessions
       parking_reservations
       parking_facilities
       parking_zones
       parking_bays

Architecture
------------

                    DATA SOURCES
                         |
          +--------------+--------------+
          |              |              |
          v              v              v
        LOCAL         EXTERNAL       OPERATIONAL
          |              |              |
          v              v              v
       csv.py       supabase.py    database.py
          |              |              |
          +--------------+--------------+
                         |
                         v
                  LoadedDataset
                         |
                         v
                    Validation
                         |
                         v
                   Transformation
                         |
                         v
                 Canonical ML Dataset
                         |
                         v
                  Feature Engineering
                         |
                         v
                    ML Training

Design principle
----------------

The rest of the ML pipeline must not care where the data
originated.

All source adapters therefore return the same LoadedDataset
contract.

This module intentionally does NOT contain:

- CSV reading implementation
- Supabase SDK/API implementation
- SQLAlchemy query implementation
- data cleaning
- feature engineering
- model training
- forecasting
- persistence logic

Those responsibilities belong to the appropriate layers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


# ============================================================
# Source Types
# ============================================================


class DataSourceType(str, Enum):
    """
    Top-level ML data-source families.

    LOCAL
        Local/public datasets stored on the filesystem.

    EXTERNAL
        Data obtained from an external provider such as
        Supabase, an API, or cloud storage.

    OPERATIONAL
        Data obtained from the SmartPark operational database.
    """

    LOCAL = "local"
    EXTERNAL = "external"
    OPERATIONAL = "operational"


class ExternalProvider(str, Enum):
    """
    External data providers supported by the architecture.

    Not every provider needs to be implemented immediately.
    These values establish the extensibility point for future
    adapters.
    """

    SUPABASE = "supabase"
    API = "api"
    CLOUD = "cloud"
    UPLOADED = "uploaded"


class LocalDataFormat(str, Enum):
    """
    Formats supported by local dataset adapters.

    CSV is our first implementation.

    Additional formats can be added later without changing the
    source-family architecture.
    """

    CSV = "csv"
    PARQUET = "parquet"
    JSON = "json"


# ============================================================
# Exceptions
# ============================================================


class MLDataLoaderError(Exception):
    """
    Base exception for ML data-loader failures.
    """


class UnsupportedDataSourceError(MLDataLoaderError):
    """
    Raised when no loader exists for a requested source type.
    """


class UnsupportedExternalProviderError(MLDataLoaderError):
    """
    Raised when an external provider is not supported.
    """


class UnsupportedLocalFormatError(MLDataLoaderError):
    """
    Raised when a local dataset format is not supported.
    """


class DatasetConfigurationError(MLDataLoaderError):
    """
    Raised when a data-source configuration is invalid.
    """


class DatasetNotFoundError(MLDataLoaderError):
    """
    Raised when a requested dataset cannot be located.
    """


class DatasetReadError(MLDataLoaderError):
    """
    Raised when a dataset cannot be read.
    """


class DatasetSchemaError(MLDataLoaderError):
    """
    Raised when a dataset does not conform to the expected
    source schema.
    """


class EmptyDatasetError(MLDataLoaderError):
    """
    Raised when a loaded dataset contains no records.
    """


# ============================================================
# Dataset Metadata
# ============================================================


@dataclass(frozen=True, slots=True)
class DatasetMetadata:
    """
    Metadata describing a loaded dataset.

    This metadata travels with the DataFrame through the ML
    ingestion pipeline and provides traceability for experiments,
    audits, debugging and data-quality reporting.

    Attributes
    ----------
    source_type:
        Top-level source family.

    source_name:
        Human-readable name of the source.

    dataset_name:
        Logical name of the dataset.

    provider:
        Optional provider name, e.g. 'supabase'.

    location:
        Source location where applicable.

    row_count:
        Number of rows loaded.

    column_count:
        Number of columns loaded.

    columns:
        Names of the source columns.

    format:
        Source format, e.g. 'csv', 'supabase', 'postgresql'.

    metadata:
        Additional source-specific metadata.
    """

    source_type: DataSourceType
    source_name: str
    dataset_name: str
    provider: str | None
    location: str | None
    row_count: int
    column_count: int
    columns: tuple[str, ...]
    format: str | None
    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )


@dataclass(frozen=True, slots=True)
class LoadedDataset:
    """
    Common result returned by every source adapter.

    The downstream validation and transformation layers consume
    this object without needing to know whether the source was:

        - Birmingham CSV
        - Manchester CSV
        - Supabase
        - REST API
        - SmartPark PostgreSQL
        - another future source

    `dataframe` is intentionally typed as Any here so that this
    module does not force a hard dependency on pandas.

    Concrete adapters may return pandas DataFrames, provided
    they comply with the contract expected by the downstream
    ML data pipeline.
    """

    dataframe: Any
    metadata: DatasetMetadata


# ============================================================
# Data Source Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class DataSourceConfig:
    """
    Configuration describing which data source should be loaded.

    Examples
    --------

    Local Birmingham:

        DataSourceConfig(
            source_type=DataSourceType.LOCAL,
            dataset_name="birmingham",
            format=LocalDataFormat.CSV.value,
        )

    External Supabase:

        DataSourceConfig(
            source_type=DataSourceType.EXTERNAL,
            dataset_name="birmingham",
            provider=ExternalProvider.SUPABASE.value,
        )

    SmartPark operational database:

        DataSourceConfig(
            source_type=DataSourceType.OPERATIONAL,
            dataset_name="occupancy_observations",
        )
    """

    source_type: DataSourceType

    dataset_name: str

    provider: str | None = None

    location: str | None = None

    format: str | None = None

    options: Mapping[str, Any] = field(
        default_factory=dict,
    )

    def __post_init__(self) -> None:
        """
        Validate basic configuration requirements.
        """

        if not self.dataset_name.strip():
            raise DatasetConfigurationError(
                "dataset_name cannot be empty."
            )

        if self.source_type == DataSourceType.EXTERNAL:
            if not self.provider:
                raise DatasetConfigurationError(
                    "provider is required for external data sources."
                )


# ============================================================
# Base Loader Contract
# ============================================================


class DataSourceLoader(ABC):
    """
    Abstract contract implemented by every source adapter.

    A loader has one primary responsibility:

        source -> LoadedDataset

    It must not perform downstream ML processing.
    """

    @abstractmethod
    def load(
        self,
        config: DataSourceConfig,
    ) -> LoadedDataset:
        """
        Load data according to the supplied configuration.

        Parameters
        ----------
        config:
            Data-source configuration.

        Returns
        -------
        LoadedDataset
            Loaded source data plus metadata.
        """

        raise NotImplementedError


# ============================================================
# Source Family Contracts
# ============================================================


class LocalDataLoader(DataSourceLoader):
    """
    Contract for local/public dataset adapters.

    Examples:

        local/csv.py
        local/parquet.py
        local/json.py
    """

    @abstractmethod
    def load(
        self,
        config: DataSourceConfig,
    ) -> LoadedDataset:
        raise NotImplementedError


class ExternalDataLoader(DataSourceLoader):
    """
    Contract for external data-source adapters.

    Examples:

        external/supabase.py
        external/rest_api.py
        external/cloud.py
    """

    @abstractmethod
    def load(
        self,
        config: DataSourceConfig,
    ) -> LoadedDataset:
        raise NotImplementedError


class OperationalDataLoader(DataSourceLoader):
    """
    Contract for SmartPark operational-data adapters.

    Examples:

        operational/database.py
    """

    @abstractmethod
    def load(
        self,
        config: DataSourceConfig,
    ) -> LoadedDataset:
        raise NotImplementedError


# ============================================================
# Loader Registry
# ============================================================


class DataLoaderRegistry:
    """
    Registry of available source-family loaders.

    The registry allows the ML ingestion layer to select the
    appropriate adapter without knowing its implementation.

    Example
    -------

        registry = DataLoaderRegistry()

        registry.register(
            DataSourceType.LOCAL,
            local_loader,
        )

        loader = registry.get(
            DataSourceType.LOCAL,
        )
    """

    def __init__(self) -> None:
        self._loaders: dict[
            DataSourceType,
            DataSourceLoader,
        ] = {}

    def register(
        self,
        source_type: DataSourceType,
        loader: DataSourceLoader,
    ) -> None:
        """
        Register a loader for a source family.

        Registering another loader for the same source type
        replaces the existing implementation.
        """

        if not isinstance(
            loader,
            DataSourceLoader,
        ):
            raise TypeError(
                "loader must implement DataSourceLoader."
            )

        self._loaders[source_type] = loader

    def get(
        self,
        source_type: DataSourceType,
    ) -> DataSourceLoader:
        """
        Retrieve the loader registered for a source type.
        """

        try:
            return self._loaders[source_type]

        except KeyError as exc:
            raise UnsupportedDataSourceError(
                f"No loader registered for data source "
                f"'{source_type.value}'."
            ) from exc

    def has(
        self,
        source_type: DataSourceType,
    ) -> bool:
        """
        Return True if a loader is registered.
        """

        return source_type in self._loaders

    def available_sources(
        self,
    ) -> tuple[DataSourceType, ...]:
        """
        Return all registered source types.
        """

        return tuple(
            self._loaders.keys()
        )


# ============================================================
# Unified ML Dataset Loader
# ============================================================


class MLDatasetLoader:
    """
    Unified entry point for the SmartPark ML data pipeline.

    The caller does not need to know which source adapter is
    responsible for retrieving the data.

    Example
    -------

        dataset_loader = MLDatasetLoader(
            registry=registry,
        )

        dataset = dataset_loader.load(
            config,
        )
    """

    def __init__(
        self,
        registry: DataLoaderRegistry,
    ) -> None:
        self._registry = registry

    def load(
        self,
        config: DataSourceConfig,
    ) -> LoadedDataset:
        """
        Load a dataset using the registered source adapter.
        """

        loader = self._registry.get(
            config.source_type,
        )

        return loader.load(
            config,
        )


# ============================================================
# Configuration Factory Functions
# ============================================================


def build_local_config(
    dataset_name: str,
    *,
    format: str = LocalDataFormat.CSV.value,
    filename: str | None = None,
    location: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> DataSourceConfig:
    """
    Build configuration for a local/public dataset.

    Examples
    --------

    Birmingham:

        build_local_config(
            "birmingham",
        )

    Manchester:

        build_local_config(
            "manchester",
        )

    Parquet in the future:

        build_local_config(
            "birmingham",
            format="parquet",
        )
    """

    merged_options = (
        dict(options)
        if options
        else {}
    )

    if filename is not None:
        merged_options["filename"] = filename

    return DataSourceConfig(
        source_type=DataSourceType.LOCAL,
        dataset_name=dataset_name,
        location=location,
        format=format,
        options=merged_options,
    )


def build_external_config(
    dataset_name: str,
    *,
    provider: str,
    location: str | None = None,
    format: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> DataSourceConfig:
    """
    Build configuration for an external data source.

    Example:

        build_external_config(
            "birmingham",
            provider="supabase",
            options={
                "table": "birmingham_parking",
            },
        )
    """

    return DataSourceConfig(
        source_type=DataSourceType.EXTERNAL,
        dataset_name=dataset_name,
        provider=provider,
        location=location,
        format=format,
        options=(
            dict(options)
            if options
            else {}
        ),
    )


def build_supabase_config(
    dataset_name: str,
    *,
    table: str | None = None,
    location: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> DataSourceConfig:
    """
    Build configuration for a Supabase dataset.

    Example:

        config = build_supabase_config(
            "birmingham",
            table="birmingham_parking",
        )
    """

    merged_options = (
        dict(options)
        if options
        else {}
    )

    if table:
        merged_options["table"] = table

    return build_external_config(
        dataset_name,
        provider=ExternalProvider.SUPABASE.value,
        location=location,
        format="supabase",
        options=merged_options,
    )


def build_operational_config(
    dataset_name: str,
    *,
    location: str | None = None,
    options: Mapping[str, Any] | None = None,
) -> DataSourceConfig:
    """
    Build configuration for the SmartPark operational database.

    Examples:

        occupancy observations:

            build_operational_config(
                "occupancy_observations",
            )

        parking sessions:

            build_operational_config(
                "parking_sessions",
            )
    """

    return DataSourceConfig(
        source_type=DataSourceType.OPERATIONAL,
        dataset_name=dataset_name,
        provider="postgresql",
        location=location,
        format="postgresql",
        options=(
            dict(options)
            if options
            else {}
        ),
    )


# ============================================================
# Registry Factory
# ============================================================


def create_data_loader_registry(
    *,
    local_loader: LocalDataLoader | None = None,
    external_loader: ExternalDataLoader | None = None,
    operational_loader: OperationalDataLoader | None = None,
) -> DataLoaderRegistry:
    """
    Create and configure a DataLoaderRegistry.

    Source implementations are injected into the registry.

    This is important because loaders.py should not know how
    local CSV files, Supabase, or PostgreSQL are implemented.

    Example
    -------

        registry = create_data_loader_registry(
            local_loader=local_csv_loader,
            external_loader=supabase_loader,
            operational_loader=operational_loader,
        )
    """

    registry = DataLoaderRegistry()

    if local_loader is not None:
        registry.register(
            DataSourceType.LOCAL,
            local_loader,
        )

    if external_loader is not None:
        registry.register(
            DataSourceType.EXTERNAL,
            external_loader,
        )

    if operational_loader is not None:
        registry.register(
            DataSourceType.OPERATIONAL,
            operational_loader,
        )

    return registry


# ============================================================
# Convenience Function
# ============================================================


def load_ml_dataset(
    *,
    config: DataSourceConfig,
    registry: DataLoaderRegistry,
) -> LoadedDataset:
    """
    Convenience function for loading an ML dataset.

    Example
    -------

        config = build_local_config(
            "birmingham",
        )

        dataset = load_ml_dataset(
            config=config,
            registry=registry,
        )
    """

    loader = MLDatasetLoader(
        registry,
    )

    return loader.load(
        config,
    )


# ============================================================
# Public API
# ============================================================


__all__ = [
    # Source types
    "DataSourceType",
    "ExternalProvider",
    "LocalDataFormat",

    # Exceptions
    "MLDataLoaderError",
    "UnsupportedDataSourceError",
    "UnsupportedExternalProviderError",
    "UnsupportedLocalFormatError",
    "DatasetConfigurationError",
    "DatasetNotFoundError",
    "DatasetReadError",
    "DatasetSchemaError",
    "EmptyDatasetError",

    # Data structures
    "DatasetMetadata",
    "LoadedDataset",
    "DataSourceConfig",

    # Loader contracts
    "DataSourceLoader",
    "LocalDataLoader",
    "ExternalDataLoader",
    "OperationalDataLoader",

    # Registry
    "DataLoaderRegistry",
    "MLDatasetLoader",

    # Configuration helpers
    "build_local_config",
    "build_external_config",
    "build_supabase_config",
    "build_operational_config",

    # Registry factory
    "create_data_loader_registry",

    # Convenience API
    "load_ml_dataset",
]