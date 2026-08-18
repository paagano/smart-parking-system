"""
SmartPark AI - ML Data Validation.

This module provides the validation layer for the SmartPark AI
machine-learning data pipeline.

The validator sits between the source loaders and the
transformation/ingestion layers:

    DATA SOURCE
         |
         v
      LOADER
         |
         v
    LoadedDataset
         |
         v
     VALIDATOR        <-- this module
         |
         v
    TRANSFORMER
         |
         v
  CANONICAL ML DATA
         |
         v
 FEATURE ENGINEERING
         |
         v
    ML TRAINING

Supported source families
-------------------------

The validator is designed to work with data originating from:

    1. Local/public datasets
       - Birmingham
       - Manchester
       - Barcelona
       - etc.

    2. External sources
       - Supabase
       - REST APIs
       - Cloud sources
       - Uploaded datasets

    3. SmartPark operational data
       - PostgreSQL
       - occupancy observations
       - parking sessions
       - reservations
       - etc.

Validation philosophy
---------------------

The validator DOES:

    - verify required columns
    - identify missing values
    - identify duplicate records
    - validate numeric fields
    - validate occupancy/capacity relationships
    - validate timestamps
    - identify invalid records
    - produce structured quality reports
    - preserve the original source DataFrame

The validator DOES NOT:

    - silently modify source data
    - drop invalid records
    - impute missing values
    - calculate final ML features
    - write to PostgreSQL
    - train models

Those responsibilities belong to downstream components.

Important
---------

Validation is deliberately separated from transformation.

For example:

    Occupancy = 600
    Capacity  = 500

The validator reports:

    OCCUPANCY_EXCEEDS_CAPACITY

It does NOT automatically change 600 to 500.

This preserves data lineage and allows us to decide later,
based on the actual audit results, how each issue should be
handled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

import pandas as pd

from app.ml.data.loaders import (
    DataSourceType,
    LoadedDataset,
)


# ============================================================
# Validation Severity
# ============================================================


class ValidationSeverity(str, Enum):
    """
    Severity of a validation finding.

    INFO
        Informational finding. Does not normally make a record
        unusable.

    WARNING
        Potential data-quality issue requiring investigation.

    ERROR
        Invalid record/value that should normally be excluded
        from a training-ready dataset unless explicitly handled.

    CRITICAL
        Serious structural/source failure that may prevent the
        dataset from being safely used.
    """

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# ============================================================
# Validation Codes
# ============================================================


class ValidationCode(str, Enum):
    """
    Standard validation codes used throughout the ML data layer.
    """

    # Dataset-level
    DATASET_EMPTY = "DATASET_EMPTY"
    REQUIRED_COLUMN_MISSING = "REQUIRED_COLUMN_MISSING"
    DUPLICATE_RECORD = "DUPLICATE_RECORD"

    # Identifier
    NULL_FACILITY_CODE = "NULL_FACILITY_CODE"
    EMPTY_FACILITY_CODE = "EMPTY_FACILITY_CODE"

    # Capacity
    NULL_CAPACITY = "NULL_CAPACITY"
    INVALID_CAPACITY = "INVALID_CAPACITY"
    ZERO_CAPACITY = "ZERO_CAPACITY"
    NEGATIVE_CAPACITY = "NEGATIVE_CAPACITY"

    # Occupancy
    NULL_OCCUPANCY = "NULL_OCCUPANCY"
    INVALID_OCCUPANCY = "INVALID_OCCUPANCY"
    NEGATIVE_OCCUPANCY = "NEGATIVE_OCCUPANCY"
    OCCUPANCY_EXCEEDS_CAPACITY = (
        "OCCUPANCY_EXCEEDS_CAPACITY"
    )

    # Timestamp
    NULL_TIMESTAMP = "NULL_TIMESTAMP"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"

    # Temporal
    DUPLICATE_FACILITY_TIMESTAMP = (
        "DUPLICATE_FACILITY_TIMESTAMP"
    )

    # General
    UNEXPECTED_DATA_TYPE = "UNEXPECTED_DATA_TYPE"


# ============================================================
# Validation Finding
# ============================================================


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """
    Represents one category of validation problem.

    Attributes
    ----------
    code:
        Standard validation code.

    severity:
        Severity of the finding.

    message:
        Human-readable explanation.

    count:
        Number of affected records.

    columns:
        Relevant source columns.

    sample_indices:
        Sample DataFrame indices affected by the issue.

    metadata:
        Additional diagnostic information.
    """

    code: ValidationCode

    severity: ValidationSeverity

    message: str

    count: int

    columns: tuple[str, ...] = ()

    sample_indices: tuple[Any, ...] = ()

    metadata: Mapping[str, Any] = field(
        default_factory=dict,
    )


# ============================================================
# Validation Report
# ============================================================


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """
    Complete validation result for a loaded dataset.

    The report is immutable after creation and can therefore be
    safely passed between pipeline components.

    Attributes
    ----------
    dataset_name:
        Name of the dataset being validated.

    source_type:
        Source family.

    row_count:
        Total number of rows examined.

    column_count:
        Total number of columns examined.

    findings:
        Individual validation findings.

    valid:
        Whether the dataset passed the validation criteria.

    invalid_row_count:
        Number of rows affected by ERROR/CRITICAL findings.

    warning_count:
        Number of warning findings.

    error_count:
        Number of error findings.

    critical_count:
        Number of critical findings.
    """

    dataset_name: str

    source_type: DataSourceType

    row_count: int

    column_count: int

    findings: tuple[ValidationFinding, ...]

    valid: bool

    invalid_row_count: int

    warning_count: int

    error_count: int

    critical_count: int

    @property
    def has_errors(self) -> bool:
        """
        Return True when at least one ERROR finding exists.
        """

        return self.error_count > 0

    @property
    def has_critical_findings(self) -> bool:
        """
        Return True when at least one CRITICAL finding exists.
        """

        return self.critical_count > 0

    @property
    def has_warnings(self) -> bool:
        """
        Return True when at least one WARNING finding exists.
        """

        return self.warning_count > 0

    @property
    def finding_codes(self) -> tuple[str, ...]:
        """
        Return all finding codes in the report.
        """

        return tuple(
            finding.code.value
            for finding in self.findings
        )


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """
    Combines the original loaded dataset with its validation
    report.

    The DataFrame is intentionally preserved unchanged.
    """

    dataset: LoadedDataset

    report: ValidationReport


# ============================================================
# Validation Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class DatasetValidationConfig:
    """
    Configuration controlling validation behaviour.

    Required columns
    ----------------

    For Birmingham:

        SystemCodeNumber
        Capacity
        Occupancy
        LastUpdated

    Key columns
    -----------

    facility_column:
        Facility/source location identifier.

    capacity_column:
        Total parking capacity.

    occupancy_column:
        Occupied spaces.

    timestamp_column:
        Observation timestamp.

    duplicate_key_columns
        Columns used to identify duplicate observations.

    fail_on_errors
        Whether ERROR findings make the overall report invalid.

    fail_on_warnings
        Whether WARNING findings make the overall report invalid.

    sample_size
        Maximum number of sample row indices retained per finding.
    """

    required_columns: frozenset[str]

    facility_column: str | None = None

    capacity_column: str | None = None

    occupancy_column: str | None = None

    timestamp_column: str | None = None

    duplicate_key_columns: tuple[str, ...] = ()

    fail_on_errors: bool = True

    fail_on_warnings: bool = False

    sample_size: int = 10

    def __post_init__(self) -> None:
        """
        Validate configuration itself.
        """

        if self.sample_size < 1:
            raise ValueError(
                "sample_size must be at least 1."
            )


# ============================================================
# Birmingham Validation Configuration
# ============================================================


BIRMINGHAM_VALIDATION_CONFIG = (
    DatasetValidationConfig(
        required_columns=frozenset(
            {
                "SystemCodeNumber",
                "Capacity",
                "Occupancy",
                "LastUpdated",
            }
        ),
        facility_column="SystemCodeNumber",
        capacity_column="Capacity",
        occupancy_column="Occupancy",
        timestamp_column="LastUpdated",
        duplicate_key_columns=(
            "SystemCodeNumber",
            "LastUpdated",
        ),
        fail_on_errors=True,
        fail_on_warnings=False,
        sample_size=10,
    )
)


# ============================================================
# Validator
# ============================================================


class DatasetValidator:
    """
    Generic dataset validator.

    Validation is performed without modifying the source
    DataFrame.

    Example
    -------

        validator = DatasetValidator(
            BIRMINGHAM_VALIDATION_CONFIG
        )

        result = validator.validate(
            loaded_dataset
        )

        print(result.report.valid)
    """

    def __init__(
        self,
        config: DatasetValidationConfig,
    ) -> None:
        self._config = config

    # ========================================================
    # Public API
    # ========================================================

    def validate(
        self,
        dataset: LoadedDataset,
    ) -> ValidationResult:
        """
        Validate a loaded dataset.

        The original DataFrame is never modified.

        Returns
        -------
        ValidationResult
            Original dataset + validation report.
        """

        dataframe = dataset.dataframe

        findings: list[ValidationFinding] = []

        # ----------------------------------------------------
        # Basic structure
        # ----------------------------------------------------

        findings.extend(
            self._validate_dataset_structure(
                dataframe,
            )
        )

        # If required columns are missing, subsequent
        # column-level checks may not be possible.
        missing_columns = (
            self._missing_required_columns(
                dataframe,
            )
        )

        if missing_columns:
            findings.append(
                ValidationFinding(
                    code=ValidationCode.REQUIRED_COLUMN_MISSING,
                    severity=ValidationSeverity.CRITICAL,
                    message=(
                        "Required dataset columns are missing: "
                        f"{', '.join(missing_columns)}."
                    ),
                    count=len(missing_columns),
                    columns=tuple(missing_columns),
                    metadata={
                        "missing_columns": tuple(
                            missing_columns
                        )
                    },
                )
            )

            return self._build_result(
                dataset,
                findings,
            )

        # ----------------------------------------------------
        # Column-level checks
        # ----------------------------------------------------

        findings.extend(
            self._validate_facility_column(
                dataframe,
            )
        )

        findings.extend(
            self._validate_capacity_column(
                dataframe,
            )
        )

        findings.extend(
            self._validate_occupancy_column(
                dataframe,
            )
        )

        findings.extend(
            self._validate_timestamp_column(
                dataframe,
            )
        )

        # ----------------------------------------------------
        # Duplicate checks
        # ----------------------------------------------------

        findings.extend(
            self._validate_duplicate_records(
                dataframe,
            )
        )

        # ----------------------------------------------------
        # Business relationship checks
        # ----------------------------------------------------

        findings.extend(
            self._validate_occupancy_capacity_relationship(
                dataframe,
            )
        )

        # ----------------------------------------------------
        # Facility/timestamp uniqueness
        # ----------------------------------------------------

        findings.extend(
            self._validate_facility_timestamp_uniqueness(
                dataframe,
            )
        )

        return self._build_result(
            dataset,
            findings,
        )

    # ========================================================
    # Dataset structure
    # ========================================================

    def _validate_dataset_structure(
        self,
        dataframe: pd.DataFrame,
    ) -> list[ValidationFinding]:
        """
        Validate basic DataFrame structure.
        """

        findings: list[ValidationFinding] = []

        if dataframe.empty:
            findings.append(
                ValidationFinding(
                    code=ValidationCode.DATASET_EMPTY,
                    severity=ValidationSeverity.CRITICAL,
                    message=(
                        "Dataset contains no records."
                    ),
                    count=0,
                )
            )

        return findings

    # ========================================================
    # Required columns
    # ========================================================

    def _missing_required_columns(
        self,
        dataframe: pd.DataFrame,
    ) -> list[str]:
        """
        Return required columns that are missing.
        """

        actual_columns = {
            str(column)
            for column in dataframe.columns
        }

        return sorted(
            self._config.required_columns
            - actual_columns
        )

    # ========================================================
    # Facility validation
    # ========================================================

    def _validate_facility_column(
        self,
        dataframe: pd.DataFrame,
    ) -> list[ValidationFinding]:
        """
        Validate facility/source identifier values.
        """

        column = self._config.facility_column

        if not column:
            return []

        series = dataframe[column]

        findings: list[ValidationFinding] = []

        null_mask = series.isna()

        if null_mask.any():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.NULL_FACILITY_CODE,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Column '{column}' contains "
                        "null facility identifiers."
                    ),
                    count=int(null_mask.sum()),
                    columns=(column,),
                    sample_indices=self._sample_indices(
                        dataframe,
                        null_mask,
                    ),
                )
            )

        # Convert only for checking. We do not modify the
        # original DataFrame.
        string_series = series.astype(
            "string"
        )

        empty_mask = (
            string_series
            .fillna("")
            .str.strip()
            .eq("")
        )

        if empty_mask.any():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.EMPTY_FACILITY_CODE,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Column '{column}' contains "
                        "empty facility identifiers."
                    ),
                    count=int(empty_mask.sum()),
                    columns=(column,),
                    sample_indices=self._sample_indices(
                        dataframe,
                        empty_mask,
                    ),
                )
            )

        return findings

    # ========================================================
    # Capacity validation
    # ========================================================

    def _validate_capacity_column(
        self,
        dataframe: pd.DataFrame,
    ) -> list[ValidationFinding]:
        """
        Validate capacity values.
        """

        column = self._config.capacity_column

        if not column:
            return []

        series = dataframe[column]

        findings: list[ValidationFinding] = []

        null_mask = series.isna()

        if null_mask.any():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.NULL_CAPACITY,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Column '{column}' contains "
                        "null capacity values."
                    ),
                    count=int(null_mask.sum()),
                    columns=(column,),
                    sample_indices=self._sample_indices(
                        dataframe,
                        null_mask,
                    ),
                )
            )

        numeric = pd.to_numeric(
            series,
            errors="coerce",
        )

        invalid_numeric_mask = (
            numeric.isna()
            & ~null_mask
        )

        if invalid_numeric_mask.any():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.INVALID_CAPACITY,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Column '{column}' contains "
                        "non-numeric capacity values."
                    ),
                    count=int(
                        invalid_numeric_mask.sum()
                    ),
                    columns=(column,),
                    sample_indices=self._sample_indices(
                        dataframe,
                        invalid_numeric_mask,
                    ),
                )
            )

        negative_mask = (
            numeric < 0
        )

        if negative_mask.any():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.NEGATIVE_CAPACITY,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Column '{column}' contains "
                        "negative capacity values."
                    ),
                    count=int(
                        negative_mask.sum()
                    ),
                    columns=(column,),
                    sample_indices=self._sample_indices(
                        dataframe,
                        negative_mask,
                    ),
                )
            )

        zero_mask = (
            numeric == 0
        )

        if zero_mask.any():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.ZERO_CAPACITY,
                    severity=ValidationSeverity.WARNING,
                    message=(
                        f"Column '{column}' contains "
                        "zero-capacity observations."
                    ),
                    count=int(
                        zero_mask.sum()
                    ),
                    columns=(column,),
                    sample_indices=self._sample_indices(
                        dataframe,
                        zero_mask,
                    ),
                )
            )

        return findings

    # ========================================================
    # Occupancy validation
    # ========================================================

    def _validate_occupancy_column(
        self,
        dataframe: pd.DataFrame,
    ) -> list[ValidationFinding]:
        """
        Validate occupancy values.
        """

        column = self._config.occupancy_column

        if not column:
            return []

        series = dataframe[column]

        findings: list[ValidationFinding] = []

        null_mask = series.isna()

        if null_mask.any():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.NULL_OCCUPANCY,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Column '{column}' contains "
                        "null occupancy values."
                    ),
                    count=int(null_mask.sum()),
                    columns=(column,),
                    sample_indices=self._sample_indices(
                        dataframe,
                        null_mask,
                    ),
                )
            )

        numeric = pd.to_numeric(
            series,
            errors="coerce",
        )

        invalid_numeric_mask = (
            numeric.isna()
            & ~null_mask
        )

        if invalid_numeric_mask.any():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.INVALID_OCCUPANCY,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Column '{column}' contains "
                        "non-numeric occupancy values."
                    ),
                    count=int(
                        invalid_numeric_mask.sum()
                    ),
                    columns=(column,),
                    sample_indices=self._sample_indices(
                        dataframe,
                        invalid_numeric_mask,
                    ),
                )
            )

        negative_mask = (
            numeric < 0
        )

        if negative_mask.any():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.NEGATIVE_OCCUPANCY,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Column '{column}' contains "
                        "negative occupancy values."
                    ),
                    count=int(
                        negative_mask.sum()
                    ),
                    columns=(column,),
                    sample_indices=self._sample_indices(
                        dataframe,
                        negative_mask,
                    ),
                )
            )

        return findings

    # ========================================================
    # Occupancy / Capacity relationship
    # ========================================================

    def _validate_occupancy_capacity_relationship(
        self,
        dataframe: pd.DataFrame,
    ) -> list[ValidationFinding]:
        """
        Validate:

            Occupancy <= Capacity

        This is one of the most important domain rules for
        parking occupancy data.

        The validator reports violations but does not modify
        the values.
        """

        capacity_column = (
            self._config.capacity_column
        )

        occupancy_column = (
            self._config.occupancy_column
        )

        if not capacity_column or not occupancy_column:
            return []

        capacity = pd.to_numeric(
            dataframe[capacity_column],
            errors="coerce",
        )

        occupancy = pd.to_numeric(
            dataframe[occupancy_column],
            errors="coerce",
        )

        comparison_mask = (
            capacity.notna()
            & occupancy.notna()
            & (occupancy > capacity)
        )

        if not comparison_mask.any():
            return []

        return [
            ValidationFinding(
                code=(
                    ValidationCode
                    .OCCUPANCY_EXCEEDS_CAPACITY
                ),
                severity=ValidationSeverity.ERROR,
                message=(
                    f"Occupancy exceeds capacity in "
                    f"{int(comparison_mask.sum())} "
                    "observation(s)."
                ),
                count=int(
                    comparison_mask.sum()
                ),
                columns=(
                    capacity_column,
                    occupancy_column,
                ),
                sample_indices=self._sample_indices(
                    dataframe,
                    comparison_mask,
                ),
            )
        ]

    # ========================================================
    # Timestamp validation
    # ========================================================

    def _validate_timestamp_column(
        self,
        dataframe: pd.DataFrame,
    ) -> list[ValidationFinding]:
        """
        Validate timestamp values.

        The original column is NOT converted in place.

        Parsing is performed on a temporary Series only.
        """

        column = self._config.timestamp_column

        if not column:
            return []

        series = dataframe[column]

        findings: list[ValidationFinding] = []

        null_mask = series.isna()

        if null_mask.any():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.NULL_TIMESTAMP,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Column '{column}' contains "
                        "null timestamps."
                    ),
                    count=int(null_mask.sum()),
                    columns=(column,),
                    sample_indices=self._sample_indices(
                        dataframe,
                        null_mask,
                    ),
                )
            )

        parsed = pd.to_datetime(
            series,
            errors="coerce",
        )

        invalid_mask = (
            parsed.isna()
            & ~null_mask
        )

        if invalid_mask.any():
            findings.append(
                ValidationFinding(
                    code=ValidationCode.INVALID_TIMESTAMP,
                    severity=ValidationSeverity.ERROR,
                    message=(
                        f"Column '{column}' contains "
                        "timestamps that cannot be parsed."
                    ),
                    count=int(
                        invalid_mask.sum()
                    ),
                    columns=(column,),
                    sample_indices=self._sample_indices(
                        dataframe,
                        invalid_mask,
                    ),
                )
            )

        return findings

    # ========================================================
    # Duplicate records
    # ========================================================

    def _validate_duplicate_records(
        self,
        dataframe: pd.DataFrame,
    ) -> list[ValidationFinding]:
        """
        Identify exact duplicate rows.

        Exact duplicates are checked separately from the
        facility/timestamp uniqueness rule.
        """

        duplicate_mask = dataframe.duplicated(
            keep=False,
        )

        if not duplicate_mask.any():
            return []

        duplicate_count = int(
            duplicate_mask.sum()
        )

        return [
            ValidationFinding(
                code=ValidationCode.DUPLICATE_RECORD,
                severity=ValidationSeverity.WARNING,
                message=(
                    f"Dataset contains "
                    f"{duplicate_count} rows that "
                    "belong to exact duplicate groups."
                ),
                count=duplicate_count,
                columns=tuple(
                    str(column)
                    for column in dataframe.columns
                ),
                sample_indices=self._sample_indices(
                    dataframe,
                    duplicate_mask,
                ),
            )
        ]

    # ========================================================
    # Facility/timestamp uniqueness
    # ========================================================

    def _validate_facility_timestamp_uniqueness(
        self,
        dataframe: pd.DataFrame,
    ) -> list[ValidationFinding]:
        """
        Identify multiple observations for the same facility
        at the same timestamp.

        This is particularly important because our SmartPark
        occupancy_observations table has a uniqueness rule on:

            facility_id + observed_at
        """

        key_columns = (
            self._config.duplicate_key_columns
        )

        if not key_columns:
            return []

        if any(
            column not in dataframe.columns
            for column in key_columns
        ):
            return []

        duplicate_mask = dataframe.duplicated(
            subset=list(key_columns),
            keep=False,
        )

        if not duplicate_mask.any():
            return []

        duplicate_count = int(
            duplicate_mask.sum()
        )

        return [
            ValidationFinding(
                code=(
                    ValidationCode
                    .DUPLICATE_FACILITY_TIMESTAMP
                ),
                severity=ValidationSeverity.ERROR,
                message=(
                    "Multiple observations exist for the "
                    "same facility and timestamp."
                ),
                count=duplicate_count,
                columns=tuple(key_columns),
                sample_indices=self._sample_indices(
                    dataframe,
                    duplicate_mask,
                ),
            )
        ]

    # ========================================================
    # Utility
    # ========================================================

    def _sample_indices(
        self,
        dataframe: pd.DataFrame,
        mask: pd.Series,
    ) -> tuple[Any, ...]:
        """
        Return a limited sample of affected DataFrame indices.
        """

        indices = dataframe.index[mask]

        return tuple(
            indices[: self._config.sample_size]
            .tolist()
        )

    # ========================================================
    # Result construction
    # ========================================================

    def _build_result(
        self,
        dataset: LoadedDataset,
        findings: Iterable[ValidationFinding],
    ) -> ValidationResult:
        """
        Build a ValidationResult from findings.
        """

        findings_tuple = tuple(findings)

        warning_count = sum(
            1
            for finding in findings_tuple
            if finding.severity
            == ValidationSeverity.WARNING
        )

        error_count = sum(
            1
            for finding in findings_tuple
            if finding.severity
            == ValidationSeverity.ERROR
        )

        critical_count = sum(
            1
            for finding in findings_tuple
            if finding.severity
            == ValidationSeverity.CRITICAL
        )

        invalid_indices: set[Any] = set()

        for finding in findings_tuple:
            if finding.severity in {
                ValidationSeverity.ERROR,
                ValidationSeverity.CRITICAL,
            }:
                invalid_indices.update(
                    finding.sample_indices
                )

        # The sampled invalid indices above are useful for
        # diagnostics but cannot represent the exact total
        # invalid-row count when the sample size is limited.
        #
        # Therefore we expose the number of rows represented
        # by the validation findings conservatively here.
        #
        # The transformation layer will later calculate the
        # exact row-level quality mask.
        invalid_row_count = len(
            invalid_indices
        )

        has_error = (
            error_count > 0
        )

        has_critical = (
            critical_count > 0
        )

        valid = True

        if has_critical:
            valid = False

        if (
            self._config.fail_on_errors
            and has_error
        ):
            valid = False

        if (
            self._config.fail_on_warnings
            and warning_count > 0
        ):
            valid = False

        report = ValidationReport(
            dataset_name=dataset.metadata.dataset_name,
            source_type=dataset.metadata.source_type,
            row_count=len(dataset.dataframe),
            column_count=len(dataset.dataframe.columns),
            findings=findings_tuple,
            valid=valid,
            invalid_row_count=invalid_row_count,
            warning_count=warning_count,
            error_count=error_count,
            critical_count=critical_count,
        )

        return ValidationResult(
            dataset=dataset,
            report=report,
        )


# ============================================================
# Convenience Validators
# ============================================================


def validate_birmingham_dataset(
    dataset: LoadedDataset,
) -> ValidationResult:
    """
    Validate a Birmingham dataset using the standard Birmingham
    validation rules.

    Example
    -------

        result = validate_birmingham_dataset(
            loaded_dataset
        )

        if not result.report.valid:
            ...
    """

    validator = DatasetValidator(
        BIRMINGHAM_VALIDATION_CONFIG,
    )

    return validator.validate(
        dataset,
    )


def create_validator(
    config: DatasetValidationConfig,
) -> DatasetValidator:
    """
    Create a DatasetValidator from a configuration.
    """

    return DatasetValidator(
        config,
    )


# ============================================================
# Public API
# ============================================================


__all__ = [
    # Enums
    "ValidationSeverity",
    "ValidationCode",

    # Findings / reports
    "ValidationFinding",
    "ValidationReport",
    "ValidationResult",

    # Configuration
    "DatasetValidationConfig",
    "BIRMINGHAM_VALIDATION_CONFIG",

    # Validator
    "DatasetValidator",

    # Convenience functions
    "validate_birmingham_dataset",
    "create_validator",
]