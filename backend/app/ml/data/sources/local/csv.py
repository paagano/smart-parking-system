"""
SmartPark AI - Local CSV Data Source.

This module implements the local/public CSV dataset adapter
used by the SmartPark AI ML data-ingestion pipeline.

Supported dataset structure
----------------------------

    datasets/
    └── raw/
        ├── birmingham/
        │   └── dataset.csv
        │
        ├── manchester/
        │   └── dataset.csv
        │
        └── barcelona/
            └── dataset.csv

The adapter is dataset-agnostic. It does not contain special
logic for Birmingham, Manchester, Barcelona, etc.

Responsibilities
----------------

This module is responsible for:

- resolving local dataset files
- validating that the requested file exists
- reading CSV files
- handling common CSV encodings
- detecting empty files
- returning a LoadedDataset
- collecting basic source metadata

This module does NOT:

- clean data
- remove duplicates
- calculate occupancy rates
- validate occupancy business rules
- engineer ML features
- write to PostgreSQL
- train ML models

Those responsibilities belong to downstream ML components.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.ml.data.loaders import (
    DataSourceConfig,
    DataSourceType,
    DatasetMetadata,
    DatasetNotFoundError,
    DatasetReadError,
    EmptyDatasetError,
    LocalDataFormat,
    LocalDataLoader,
    LoadedDataset,
)


# ============================================================
# Local CSV Loader
# ============================================================


class CSVDataLoader(LocalDataLoader):
    """
    Concrete loader for local CSV datasets.

    The loader is intentionally generic and can load any
    dataset stored under the configured local dataset root.

    Example
    -------

        datasets/raw/birmingham/dataset.csv

    can be loaded using:

        config = DataSourceConfig(
            source_type=DataSourceType.LOCAL,
            dataset_name="birmingham",
            format="csv",
        )

    No Birmingham-specific logic exists in this class.
    """

    DEFAULT_FILENAME = "dataset.csv"

    SUPPORTED_ENCODINGS: tuple[str, ...] = (
        "utf-8-sig",
        "utf-8",
        "cp1252",
    )

    # --------------------------------------------------------
    # Constructor
    # --------------------------------------------------------

    def __init__(
        self,
        dataset_root: str | Path,
    ) -> None:
        """
        Initialize the local CSV loader.

        Parameters
        ----------
        dataset_root:
            Root directory containing the local datasets.

        Example
        -------

            ../datasets/raw

        With:

            dataset_name="birmingham"

        the loader resolves:

            ../datasets/raw/birmingham/dataset.csv
        """

        self._dataset_root = Path(
            dataset_root
        ).expanduser()

    # --------------------------------------------------------
    # Public properties
    # --------------------------------------------------------

    @property
    def dataset_root(self) -> Path:
        """
        Return the configured local dataset root.
        """

        return self._dataset_root

    # --------------------------------------------------------
    # Main load method
    # --------------------------------------------------------

    def load(
        self,
        config: DataSourceConfig,
    ) -> LoadedDataset:
        """
        Load a local CSV dataset.

        Parameters
        ----------
        config:
            Data-source configuration created using
            DataSourceConfig or build_local_config().

        Returns
        -------
        LoadedDataset
            Loaded pandas DataFrame together with metadata.

        Raises
        ------
        DatasetNotFoundError
            If the dataset directory or file does not exist.

        DatasetReadError
            If the CSV cannot be read.

        EmptyDatasetError
            If the CSV contains no rows.

        ValueError
            If an unsupported format is requested.
        """

        self._validate_config(
            config,
        )

        dataset_path = self._resolve_dataset_path(
            config,
        )

        dataframe, encoding = self._read_csv(
            dataset_path,
        )

        self._validate_not_empty(
            dataframe,
            dataset_path,
        )

        metadata = self._build_metadata(
            dataframe=dataframe,
            config=config,
            dataset_path=dataset_path,
            encoding=encoding,
        )

        return LoadedDataset(
            dataframe=dataframe,
            metadata=metadata,
        )

    # ========================================================
    # Configuration validation
    # ========================================================

    @staticmethod
    def _validate_config(
        config: DataSourceConfig,
    ) -> None:
        """
        Validate that the supplied configuration is appropriate
        for the local CSV loader.
        """

        if config.source_type != DataSourceType.LOCAL:
            raise ValueError(
                "CSVDataLoader requires "
                "source_type=DataSourceType.LOCAL."
            )

        if not config.dataset_name.strip():
            raise ValueError(
                "dataset_name cannot be empty."
            )

        requested_format = (
            config.format
            or LocalDataFormat.CSV.value
        )

        if requested_format.lower() != (
            LocalDataFormat.CSV.value
        ):
            raise ValueError(
                "CSVDataLoader only supports the CSV format. "
                f"Received: '{requested_format}'."
            )

    # ========================================================
    # Dataset path resolution
    # ========================================================

    def _resolve_dataset_path(
        self,
        config: DataSourceConfig,
    ) -> Path:
        """
        Resolve the physical CSV path for a dataset.

        Standard structure:

            <dataset_root>/
                <dataset_name>/
                    dataset.csv

        Example:

            ../datasets/raw/
                birmingham/
                    dataset.csv
        """

        dataset_directory = (
            self._dataset_root
            / config.dataset_name
        )

        if not dataset_directory.exists():
            raise DatasetNotFoundError(
                "Local dataset directory does not exist: "
                f"{dataset_directory}"
            )

        if not dataset_directory.is_dir():
            raise DatasetNotFoundError(
                "Local dataset path is not a directory: "
                f"{dataset_directory}"
            )

        filename = self._get_filename(
            config,
        )

        dataset_path = (
            dataset_directory
            / filename
        )

        if not dataset_path.exists():
            raise DatasetNotFoundError(
                "Local CSV dataset file does not exist: "
                f"{dataset_path}"
            )

        if not dataset_path.is_file():
            raise DatasetNotFoundError(
                "Local CSV dataset path is not a file: "
                f"{dataset_path}"
            )

        return dataset_path

    # ========================================================
    # Filename handling
    # ========================================================

    @staticmethod
    def _get_filename(
        config: DataSourceConfig,
    ) -> str:
        """
        Determine the dataset filename.

        The default is:

            dataset.csv

        A different filename can be supplied through:

            config.options["filename"]
        """

        filename = config.options.get(
            "filename",
            CSVDataLoader.DEFAULT_FILENAME,
        )

        if not isinstance(
            filename,
            str,
        ):
            raise ValueError(
                "The local CSV filename must be a string."
            )

        filename = filename.strip()

        if not filename:
            raise ValueError(
                "The local CSV filename cannot be empty."
            )

        # Prevent accidental path traversal through the
        # filename option.
        filename_path = Path(filename)

        if (
            filename_path.is_absolute()
            or ".." in filename_path.parts
        ):
            raise ValueError(
                "Dataset filename must be a filename within "
                "the configured dataset directory."
            )

        return filename

    # ========================================================
    # CSV reading
    # ========================================================

    def _read_csv(
        self,
        dataset_path: Path,
    ) -> tuple[pd.DataFrame, str]:
        """
        Read a CSV file using supported encoding fallbacks.

        We deliberately do not perform data transformations here.

        The raw values are preserved as much as possible so that
        the validation and transformation layers can make the
        appropriate decisions later.
        """

        last_decode_error: UnicodeDecodeError | None = None

        for encoding in self.SUPPORTED_ENCODINGS:
            try:
                dataframe = pd.read_csv(
                    dataset_path,
                    encoding=encoding,
                )

                return dataframe, encoding

            except UnicodeDecodeError as exc:
                last_decode_error = exc
                continue

            except pd.errors.EmptyDataError as exc:
                raise DatasetReadError(
                    f"CSV file is empty: "
                    f"{dataset_path}"
                ) from exc

            except pd.errors.ParserError as exc:
                raise DatasetReadError(
                    "Unable to parse CSV dataset "
                    f"'{dataset_path}': {exc}"
                ) from exc

            except OSError as exc:
                raise DatasetReadError(
                    "Unable to access CSV dataset "
                    f"'{dataset_path}': {exc}"
                ) from exc

        raise DatasetReadError(
            "Unable to decode CSV dataset "
            f"'{dataset_path}' using supported encodings: "
            f"{', '.join(self.SUPPORTED_ENCODINGS)}"
        ) from last_decode_error

    # ========================================================
    # Dataset validation
    # ========================================================

    @staticmethod
    def _validate_not_empty(
        dataframe: pd.DataFrame,
        dataset_path: Path,
    ) -> None:
        """
        Ensure that the dataset contains at least one row.

        This is a structural check only.

        Business/data-quality validation is performed by
        validators.py.
        """

        if dataframe.empty:
            raise EmptyDatasetError(
                "Local CSV dataset contains no records: "
                f"{dataset_path}"
            )

    # ========================================================
    # Metadata
    # ========================================================

    @staticmethod
    def _build_metadata(
        *,
        dataframe: pd.DataFrame,
        config: DataSourceConfig,
        dataset_path: Path,
        encoding: str,
    ) -> DatasetMetadata:
        """
        Build metadata describing the loaded dataset.
        """

        return DatasetMetadata(
            source_type=DataSourceType.LOCAL,
            source_name="LOCAL_DATASET",
            dataset_name=config.dataset_name,
            provider=None,
            location=str(
                dataset_path.resolve()
            ),
            row_count=len(dataframe),
            column_count=len(dataframe.columns),
            columns=tuple(
                str(column)
                for column in dataframe.columns
            ),
            format=LocalDataFormat.CSV.value,
            metadata={
                "encoding": encoding,
                "filename": dataset_path.name,
                "dataset_root": str(
                    dataset_path.parent.parent.resolve()
                ),
            },
        )

    # ========================================================
    # Dataset discovery
    # ========================================================

    def list_datasets(self) -> tuple[str, ...]:
        """
        Return the names of available local datasets.

        Example
        -------

        If:

            datasets/raw/
                birmingham/
                manchester/
                barcelona/

        exists, this returns:

            (
                "barcelona",
                "birmingham",
                "manchester",
            )

        Only directories are returned. A directory is considered
        a candidate dataset location.

        This method does not validate that every directory
        actually contains dataset.csv.
        """

        if not self._dataset_root.exists():
            return ()

        if not self._dataset_root.is_dir():
            return ()

        return tuple(
            sorted(
                path.name
                for path in self._dataset_root.iterdir()
                if path.is_dir()
            )
        )

    # ========================================================
    # Dataset existence check
    # ========================================================

    def dataset_exists(
        self,
        dataset_name: str,
        *,
        filename: str = DEFAULT_FILENAME,
    ) -> bool:
        """
        Check whether a local dataset exists.

        This method does not load the dataset.

        Example:

            loader.dataset_exists("birmingham")

        Returns:

            True
        """

        try:
            path = (
                self._dataset_root
                / dataset_name
                / filename
            )

            return (
                path.exists()
                and path.is_file()
            )

        except (
            OSError,
            ValueError,
        ):
            return False


# ============================================================
# Convenience factory
# ============================================================


def create_csv_loader(
    dataset_root: str | Path,
) -> CSVDataLoader:
    """
    Create a local CSV data loader.

    Example
    -------

        loader = create_csv_loader(
            "../datasets/raw"
        )
    """

    return CSVDataLoader(
        dataset_root=dataset_root,
    )


# ============================================================
# Convenience function
# ============================================================


def load_local_csv(
    *,
    dataset_root: str | Path,
    dataset_name: str,
    filename: str = CSVDataLoader.DEFAULT_FILENAME,
    options: dict[str, Any] | None = None,
) -> LoadedDataset:
    """
    Convenience function for directly loading a local CSV.

    This is useful for tests and small scripts.

    Example
    -------

        dataset = load_local_csv(
            dataset_root="../datasets/raw",
            dataset_name="birmingham",
        )

        print(dataset.dataframe.head())
    """

    merged_options = (
        dict(options)
        if options
        else {}
    )

    merged_options["filename"] = filename

    config = DataSourceConfig(
        source_type=DataSourceType.LOCAL,
        dataset_name=dataset_name,
        format=LocalDataFormat.CSV.value,
        options=merged_options,
    )

    loader = CSVDataLoader(
        dataset_root=dataset_root,
    )

    return loader.load(
        config,
    )


# ============================================================
# Public API
# ============================================================


__all__ = [
    "CSVDataLoader",
    "create_csv_loader",
    "load_local_csv",
]