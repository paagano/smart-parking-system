"""
SmartPark AI - ML Dataset Audit.

This module audits the supervised-learning dataset produced by
dataset_builder.py before feature engineering and model training.

Pipeline position:

    Raw Data
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
    ML Dataset Builder
        |
        v
    DATASET AUDIT              <-- THIS MODULE
        |
        v
    Feature Engineering
        |
        v
    Model Training


The audit is intentionally separated from transformation and
dataset construction.

Responsibilities
----------------

This module answers questions such as:

- How much usable training data exists?
- How much usable data exists for each prediction horizon?
- Which facilities have sufficient observations?
- Which facilities are sparse?
- What proportion of observations are usable?
- Why are targets unavailable?
- What is the occupancy distribution?
- How does coverage vary by hour?
- How does coverage vary by facility?
- How does coverage vary by date?
- Are there suspicious occupancy values?
- Are there duplicate facility/timestamp records?
- Is the dataset suitable for feature engineering/model training?

This module DOES NOT:

- modify the dataset
- fill missing values
- interpolate observations
- remove outliers
- train models
- engineer ML features
- split train/test data
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

import numpy as np
import pandas as pd


# ============================================================
# Canonical columns
# ============================================================

FACILITY_COLUMN = "source_facility_code"

TIMESTAMP_COLUMN = "normalized_at"

OCCUPANCY_RATE_COLUMN = "occupancy_rate"

TOTAL_SPACES_COLUMN = "total_spaces"

OCCUPIED_SPACES_COLUMN = "occupied_spaces"

AVAILABLE_SPACES_COLUMN = "available_spaces"

OBSERVATION_PRESENT_COLUMN = "observation_present"

SEQUENCE_BREAK_COLUMN = "sequence_break"

IS_OPERATIONAL_GAP_COLUMN = "is_operational_gap"

IS_DATA_GAP_COLUMN = "is_data_gap"

QUALITY_STATUS_COLUMN = "quality_status"


# ============================================================
# Target columns
# ============================================================

TARGET_30M_COLUMN = "target_occupancy_rate_30m"

TARGET_1H_COLUMN = "target_occupancy_rate_1h"

TARGET_2H_COLUMN = "target_occupancy_rate_2h"

TARGET_TOMORROW_MORNING_COLUMN = (
    "target_tomorrow_morning_demand"
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

TARGET_ELIGIBLE_COLUMN = "target_eligible"

TARGET_EXCLUSION_REASON_COLUMN = (
    "target_exclusion_reason"
)


# ============================================================
# Audit status
# ============================================================


class AuditStatus(str, Enum):
    """Overall audit outcome."""

    PASS = "PASS"

    PASS_WITH_WARNINGS = (
        "PASS_WITH_WARNINGS"
    )

    FAIL = "FAIL"


class FindingSeverity(str, Enum):
    """Severity of an audit finding."""

    INFO = "INFO"

    WARNING = "WARNING"

    ERROR = "ERROR"

    CRITICAL = "CRITICAL"


# ============================================================
# Exceptions
# ============================================================


class DatasetAuditError(Exception):
    """Base dataset audit exception."""


class DatasetAuditSchemaError(
    DatasetAuditError
):
    """Raised when required columns are missing."""


class DatasetAuditDataError(
    DatasetAuditError
):
    """Raised when the dataset is structurally invalid."""


class DatasetAuditConfigurationError(
    DatasetAuditError
):
    """Raised when audit configuration is invalid."""


# ============================================================
# Configuration
# ============================================================


@dataclass(frozen=True, slots=True)
class DatasetAuditConfig:
    """
    Configuration controlling dataset audit thresholds.

    These thresholds are deliberately conservative.

    They do NOT automatically remove data.

    They only determine whether the audit reports warnings
    or errors.
    """

    interval_minutes: int = 30

    minimum_facility_observations: int = 100

    minimum_facility_target_30m: int = 50

    minimum_facility_target_1h: int = 50

    minimum_facility_target_2h: int = 50

    minimum_facility_tomorrow_targets: int = 50

    minimum_target_coverage_ratio: float = 0.20

    minimum_observed_ratio: float = 0.20

    minimum_occupancy_rate: float = 0.0

    maximum_occupancy_rate: float = 1.0

    suspicious_occupancy_threshold: float = 1.0

    max_duplicate_facility_timestamp_rows: int = 0

    fail_on_invalid_timestamps: bool = True

    fail_on_invalid_occupancy: bool = True

    warn_on_sparse_facilities: bool = True

    warn_on_low_target_coverage: bool = True

    warn_on_high_missingness: bool = True

    def __post_init__(self) -> None:

        if self.interval_minutes <= 0:
            raise DatasetAuditConfigurationError(
                "interval_minutes must be greater than zero."
            )

        integer_fields = {
            "minimum_facility_observations": (
                self.minimum_facility_observations
            ),
            "minimum_facility_target_30m": (
                self.minimum_facility_target_30m
            ),
            "minimum_facility_target_1h": (
                self.minimum_facility_target_1h
            ),
            "minimum_facility_target_2h": (
                self.minimum_facility_target_2h
            ),
            "minimum_facility_tomorrow_targets": (
                self.minimum_facility_tomorrow_targets
            ),
            "max_duplicate_facility_timestamp_rows": (
                self.max_duplicate_facility_timestamp_rows
            ),
        }

        for name, value in integer_fields.items():

            if value < 0:

                raise DatasetAuditConfigurationError(
                    f"{name} must not be negative."
                )

        if not (
            0.0
            <= self.minimum_target_coverage_ratio
            <= 1.0
        ):
            raise DatasetAuditConfigurationError(
                "minimum_target_coverage_ratio must "
                "be between 0 and 1."
            )

        if not (
            0.0
            <= self.minimum_observed_ratio
            <= 1.0
        ):
            raise DatasetAuditConfigurationError(
                "minimum_observed_ratio must "
                "be between 0 and 1."
            )

        if (
            self.maximum_occupancy_rate
            < self.minimum_occupancy_rate
        ):
            raise DatasetAuditConfigurationError(
                "maximum_occupancy_rate must be "
                "greater than or equal to "
                "minimum_occupancy_rate."
            )


# ============================================================
# Findings
# ============================================================


@dataclass(frozen=True, slots=True)
class AuditFinding:
    """Individual audit finding."""

    code: str

    severity: FindingSeverity

    message: str

    count: int = 0

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Overall dataset summary
# ============================================================


@dataclass(frozen=True, slots=True)
class DatasetSummary:
    """High-level dataset statistics."""

    row_count: int

    column_count: int

    facility_count: int

    observed_row_count: int

    missing_row_count: int

    operational_gap_count: int

    data_gap_count: int

    sequence_break_count: int

    target_eligible_count: int

    target_eligible_ratio: float

    coverage_start: pd.Timestamp | None

    coverage_end: pd.Timestamp | None

    calendar_days: int

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Facility audit
# ============================================================


@dataclass(frozen=True, slots=True)
class FacilityAudit:
    """Audit statistics for one parking facility."""

    facility_code: str

    row_count: int

    observed_count: int

    missing_count: int

    observed_ratio: float

    target_30m_count: int

    target_1h_count: int

    target_2h_count: int

    target_tomorrow_morning_count: int

    target_30m_ratio: float

    target_1h_ratio: float

    target_2h_ratio: float

    target_tomorrow_morning_ratio: float

    target_eligible_count: int

    minimum_occupancy_rate: float | None

    maximum_occupancy_rate: float | None

    mean_occupancy_rate: float | None

    median_occupancy_rate: float | None

    standard_deviation_occupancy_rate: float | None

    first_observation: pd.Timestamp | None

    last_observation: pd.Timestamp | None

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Target audit
# ============================================================


@dataclass(frozen=True, slots=True)
class TargetAudit:
    """Audit statistics for one target horizon."""

    horizon: str

    target_column: str

    availability_column: str

    total_rows: int

    available_count: int

    unavailable_count: int

    availability_ratio: float

    minimum_value: float | None

    maximum_value: float | None

    mean_value: float | None

    median_value: float | None

    standard_deviation: float | None

    p05: float | None

    p25: float | None

    p75: float | None

    p95: float | None

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Hourly coverage
# ============================================================


@dataclass(frozen=True, slots=True)
class HourlyCoverage:
    """Coverage statistics by hour of day."""

    hour: int

    total_rows: int

    observed_rows: int

    missing_rows: int

    observed_ratio: float

    target_30m_rows: int

    target_1h_rows: int

    target_2h_rows: int

    target_tomorrow_rows: int


# ============================================================
# Daily coverage
# ============================================================


@dataclass(frozen=True, slots=True)
class DailyCoverage:
    """Coverage statistics by calendar date."""

    date: pd.Timestamp

    total_rows: int

    observed_rows: int

    missing_rows: int

    observed_ratio: float

    target_30m_rows: int

    target_1h_rows: int

    target_2h_rows: int

    target_tomorrow_rows: int


# ============================================================
# Audit report
# ============================================================


@dataclass(frozen=True, slots=True)
class DatasetAuditReport:
    """Complete audit report."""

    status: AuditStatus

    summary: DatasetSummary

    facilities: tuple[
        FacilityAudit,
        ...
    ]

    targets: tuple[
        TargetAudit,
        ...
    ]

    hourly_coverage: tuple[
        HourlyCoverage,
        ...
    ]

    daily_coverage: tuple[
        DailyCoverage,
        ...
    ]

    findings: tuple[
        AuditFinding,
        ...
    ]

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )

    @property
    def finding_count(self) -> int:
        return len(self.findings)

    @property
    def warning_count(self) -> int:
        return sum(
            finding.severity
            == FindingSeverity.WARNING
            for finding in self.findings
        )

    @property
    def error_count(self) -> int:
        return sum(
            finding.severity
            == FindingSeverity.ERROR
            for finding in self.findings
        )

    @property
    def critical_count(self) -> int:
        return sum(
            finding.severity
            == FindingSeverity.CRITICAL
            for finding in self.findings
        )

    @property
    def ready_for_feature_engineering(
        self,
    ) -> bool:

        return self.status in {
            AuditStatus.PASS,
            AuditStatus.PASS_WITH_WARNINGS,
        }


# ============================================================
# Audit result
# ============================================================


@dataclass(frozen=True, slots=True)
class DatasetAuditResult:
    """Result returned by DatasetAuditor."""

    dataframe: pd.DataFrame

    report: DatasetAuditReport

    metadata: Mapping[str, Any] = field(
        default_factory=dict
    )


# ============================================================
# Auditor
# ============================================================


class DatasetAuditor:
    """
    Audit the supervised ML dataset.

    The auditor is read-only.

    The original dataframe is never modified.
    """

    def __init__(
        self,
        config: DatasetAuditConfig | None = None,
    ) -> None:

        self._config = (
            config
            if config is not None
            else DatasetAuditConfig()
        )

    # ========================================================
    # Public API
    # ========================================================

    def audit(
        self,
        dataframe: pd.DataFrame,
    ) -> DatasetAuditResult:

        self._validate_schema(
            dataframe
        )

        working = self._prepare_dataframe(
            dataframe
        )

        findings: list[
            AuditFinding
        ] = []

        summary = (
            self._build_summary(
                working
            )
        )

        facilities = (
            self._audit_facilities(
                working,
                findings,
            )
        )

        targets = (
            self._audit_targets(
                working,
                findings,
            )
        )

        hourly_coverage = (
            self._audit_hourly_coverage(
                working
            )
        )

        daily_coverage = (
            self._audit_daily_coverage(
                working
            )
        )

        self._check_duplicates(
            working,
            findings,
        )

        self._check_timestamps(
            working,
            findings,
        )

        self._check_occupancy(
            working,
            findings,
        )

        self._check_target_consistency(
            working,
            findings,
        )

        self._check_dataset_readiness(
            summary,
            facilities,
            targets,
            findings,
        )

        status = self._determine_status(
            findings
        )

        report = DatasetAuditReport(
            status=status,
            summary=summary,
            facilities=tuple(
                facilities
            ),
            targets=tuple(
                targets
            ),
            hourly_coverage=tuple(
                hourly_coverage
            ),
            daily_coverage=tuple(
                daily_coverage
            ),
            findings=tuple(
                findings
            ),
            metadata={
                "auditor": (
                    "SmartPark AI DatasetAuditor"
                ),
                "interval_minutes": (
                    self._config.interval_minutes
                ),
                "read_only": True,
                "feature_engineering_applied": False,
                "data_modified": False,
            },
        )

        return DatasetAuditResult(
            dataframe=dataframe.copy(
                deep=True
            ),
            report=report,
            metadata={
                "ready_for_feature_engineering": (
                    report.ready_for_feature_engineering
                )
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

            raise DatasetAuditDataError(
                "DatasetAuditor requires a pandas DataFrame."
            )

        if dataframe.empty:

            raise DatasetAuditDataError(
                "Cannot audit an empty dataset."
            )

        required_columns = {
            FACILITY_COLUMN,
            TIMESTAMP_COLUMN,
            OCCUPANCY_RATE_COLUMN,
            OBSERVATION_PRESENT_COLUMN,
            SEQUENCE_BREAK_COLUMN,
            IS_OPERATIONAL_GAP_COLUMN,
            IS_DATA_GAP_COLUMN,
            TARGET_30M_AVAILABLE_COLUMN,
            TARGET_1H_AVAILABLE_COLUMN,
            TARGET_2H_AVAILABLE_COLUMN,
            TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN,
            TARGET_ELIGIBLE_COLUMN,
        }

        missing = (
            required_columns
            - set(dataframe.columns)
        )

        if missing:

            raise DatasetAuditSchemaError(
                "ML dataset is missing required "
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

        result[
            TIMESTAMP_COLUMN
        ] = pd.to_datetime(
            result[
                TIMESTAMP_COLUMN
            ],
            errors="coerce",
        )

        result[
            FACILITY_COLUMN
        ] = (
            result[
                FACILITY_COLUMN
            ]
            .astype("string")
            .str.strip()
        )

        result[
            OCCUPANCY_RATE_COLUMN
        ] = pd.to_numeric(
            result[
                OCCUPANCY_RATE_COLUMN
            ],
            errors="coerce",
        )

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

            result[column] = (
                result[column]
                .fillna(False)
                .astype(bool)
            )

        return result

    # ========================================================
    # Dataset summary
    # ========================================================

    def _build_summary(
        self,
        dataframe: pd.DataFrame,
    ) -> DatasetSummary:

        observed = (
            dataframe[
                OBSERVATION_PRESENT_COLUMN
            ]
        )

        total = len(
            dataframe
        )

        observed_count = int(
            observed.sum()
        )

        missing_count = (
            total
            - observed_count
        )

        coverage_start = (
            dataframe[
                TIMESTAMP_COLUMN
            ].min()
        )

        coverage_end = (
            dataframe[
                TIMESTAMP_COLUMN
            ].max()
        )

        if (
            coverage_start is not None
            and pd.notna(coverage_start)
            and coverage_end is not None
            and pd.notna(coverage_end)
        ):

            calendar_days = int(
                (
                    coverage_end.normalize()
                    - coverage_start.normalize()
                ).days
                + 1
            )

        else:

            calendar_days = 0

        target_eligible = (
            dataframe[
                TARGET_ELIGIBLE_COLUMN
            ]
        )

        target_eligible_count = int(
            target_eligible.sum()
        )

        target_eligible_ratio = (
            target_eligible_count / total
            if total
            else 0.0
        )

        return DatasetSummary(
            row_count=total,
            column_count=int(
                dataframe.shape[1]
            ),
            facility_count=int(
                dataframe[
                    FACILITY_COLUMN
                ].nunique()
            ),
            observed_row_count=(
                observed_count
            ),
            missing_row_count=(
                missing_count
            ),
            operational_gap_count=int(
                dataframe[
                    IS_OPERATIONAL_GAP_COLUMN
                ].sum()
            ),
            data_gap_count=int(
                dataframe[
                    IS_DATA_GAP_COLUMN
                ].sum()
            ),
            sequence_break_count=int(
                dataframe[
                    SEQUENCE_BREAK_COLUMN
                ].sum()
            ),
            target_eligible_count=(
                target_eligible_count
            ),
            target_eligible_ratio=(
                target_eligible_ratio
            ),
            coverage_start=coverage_start,
            coverage_end=coverage_end,
            calendar_days=calendar_days,
            metadata={
                "observed_ratio": (
                    observed_count / total
                    if total
                    else 0.0
                ),
                "missing_ratio": (
                    missing_count / total
                    if total
                    else 0.0
                ),
            },
        )

    # ========================================================
    # Facility audit
    # ========================================================

    def _audit_facilities(
        self,
        dataframe: pd.DataFrame,
        findings: list[AuditFinding],
    ) -> list[FacilityAudit]:

        audits: list[
            FacilityAudit
        ] = []

        for (
            facility_code,
            facility_df,
        ) in dataframe.groupby(
            FACILITY_COLUMN,
            sort=True,
        ):

            total = len(
                facility_df
            )

            observed = (
                facility_df[
                    OBSERVATION_PRESENT_COLUMN
                ]
            )

            observed_count = int(
                observed.sum()
            )

            missing_count = (
                total
                - observed_count
            )

            observed_ratio = (
                observed_count / total
                if total
                else 0.0
            )

            target_30m = int(
                facility_df[
                    TARGET_30M_AVAILABLE_COLUMN
                ].sum()
            )

            target_1h = int(
                facility_df[
                    TARGET_1H_AVAILABLE_COLUMN
                ].sum()
            )

            target_2h = int(
                facility_df[
                    TARGET_2H_AVAILABLE_COLUMN
                ].sum()
            )

            target_tomorrow = int(
                facility_df[
                    TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN
                ].sum()
            )

            eligible = int(
                facility_df[
                    TARGET_ELIGIBLE_COLUMN
                ].sum()
            )

            occupancy = facility_df.loc[
                observed
                & facility_df[
                    OCCUPANCY_RATE_COLUMN
                ].notna(),
                OCCUPANCY_RATE_COLUMN,
            ]

            if occupancy.empty:

                minimum = None
                maximum = None
                mean = None
                median = None
                std = None

            else:

                minimum = float(
                    occupancy.min()
                )

                maximum = float(
                    occupancy.max()
                )

                mean = float(
                    occupancy.mean()
                )

                median = float(
                    occupancy.median()
                )

                std = float(
                    occupancy.std(
                        ddof=1
                    )
                ) if len(
                    occupancy
                ) > 1 else 0.0

            first_observation = (
                facility_df[
                    TIMESTAMP_COLUMN
                ].min()
            )

            last_observation = (
                facility_df[
                    TIMESTAMP_COLUMN
                ].max()
            )

            audit = FacilityAudit(
                facility_code=str(
                    facility_code
                ),
                row_count=total,
                observed_count=(
                    observed_count
                ),
                missing_count=(
                    missing_count
                ),
                observed_ratio=(
                    observed_ratio
                ),
                target_30m_count=(
                    target_30m
                ),
                target_1h_count=(
                    target_1h
                ),
                target_2h_count=(
                    target_2h
                ),
                target_tomorrow_morning_count=(
                    target_tomorrow
                ),
                target_30m_ratio=(
                    target_30m / total
                    if total
                    else 0.0
                ),
                target_1h_ratio=(
                    target_1h / total
                    if total
                    else 0.0
                ),
                target_2h_ratio=(
                    target_2h / total
                    if total
                    else 0.0
                ),
                target_tomorrow_morning_ratio=(
                    target_tomorrow / total
                    if total
                    else 0.0
                ),
                target_eligible_count=(
                    eligible
                ),
                minimum_occupancy_rate=(
                    minimum
                ),
                maximum_occupancy_rate=(
                    maximum
                ),
                mean_occupancy_rate=(
                    mean
                ),
                median_occupancy_rate=(
                    median
                ),
                standard_deviation_occupancy_rate=(
                    std
                ),
                first_observation=(
                    first_observation
                ),
                last_observation=(
                    last_observation
                ),
                metadata={
                    "observed_percentage": (
                        observed_ratio * 100.0
                    ),
                },
            )

            audits.append(
                audit
            )

            # ------------------------------------------------
            # Sparse facility
            # ------------------------------------------------

            if (
                self._config
                .warn_on_sparse_facilities
                and (
                    total
                    < self._config
                    .minimum_facility_observations
                    or observed_count
                    < self._config
                    .minimum_facility_observations
                )
            ):

                findings.append(
                    AuditFinding(
                        code=(
                            "SPARSE_FACILITY"
                        ),
                        severity=(
                            FindingSeverity.WARNING
                        ),
                        message=(
                            f"Facility '{facility_code}' "
                            "has insufficient observations "
                            "for robust model training."
                        ),
                        count=1,
                        metadata={
                            "facility": str(
                                facility_code
                            ),
                            "rows": total,
                            "observed": (
                                observed_count
                            ),
                        },
                    )
                )

            # ------------------------------------------------
            # Low target coverage
            # ------------------------------------------------

            target_checks = [
                (
                    "30M",
                    target_30m,
                    self._config
                    .minimum_facility_target_30m,
                ),
                (
                    "1H",
                    target_1h,
                    self._config
                    .minimum_facility_target_1h,
                ),
                (
                    "2H",
                    target_2h,
                    self._config
                    .minimum_facility_target_2h,
                ),
                (
                    "TOMORROW_MORNING",
                    target_tomorrow,
                    self._config
                    .minimum_facility_tomorrow_targets,
                ),
            ]

            for (
                horizon,
                count,
                minimum,
            ) in target_checks:

                if (
                    count < minimum
                ):

                    findings.append(
                        AuditFinding(
                            code=(
                                "LOW_FACILITY_TARGET_COVERAGE"
                            ),
                            severity=(
                                FindingSeverity.WARNING
                            ),
                            message=(
                                f"Facility '{facility_code}' "
                                f"has only {count} usable "
                                f"{horizon} targets."
                            ),
                            count=count,
                            metadata={
                                "facility": str(
                                    facility_code
                                ),
                                "horizon": horizon,
                                "minimum_required": (
                                    minimum
                                ),
                            },
                        )
                    )

        return audits

    # ========================================================
    # Target audit
    # ========================================================

    def _audit_targets(
        self,
        dataframe: pd.DataFrame,
        findings: list[AuditFinding],
    ) -> list[TargetAudit]:

        definitions = [
            (
                "30m",
                TARGET_30M_COLUMN,
                TARGET_30M_AVAILABLE_COLUMN,
            ),
            (
                "1h",
                TARGET_1H_COLUMN,
                TARGET_1H_AVAILABLE_COLUMN,
            ),
            (
                "2h",
                TARGET_2H_COLUMN,
                TARGET_2H_AVAILABLE_COLUMN,
            ),
            (
                "tomorrow_morning",
                TARGET_TOMORROW_MORNING_COLUMN,
                TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN,
            ),
        ]

        audits: list[
            TargetAudit
        ] = []

        total = len(
            dataframe
        )

        for (
            horizon,
            target_column,
            availability_column,
        ) in definitions:

            available = (
                dataframe[
                    availability_column
                ]
                .fillna(False)
                .astype(bool)
            )

            target_values = pd.to_numeric(
                dataframe.loc[
                    available,
                    target_column,
                ],
                errors="coerce",
            ).dropna()

            available_count = int(
                available.sum()
            )

            unavailable_count = (
                total
                - available_count
            )

            ratio = (
                available_count / total
                if total
                else 0.0
            )

            if target_values.empty:

                minimum = None
                maximum = None
                mean = None
                median = None
                std = None
                p05 = None
                p25 = None
                p75 = None
                p95 = None

            else:

                minimum = float(
                    target_values.min()
                )

                maximum = float(
                    target_values.max()
                )

                mean = float(
                    target_values.mean()
                )

                median = float(
                    target_values.median()
                )

                std = float(
                    target_values.std(
                        ddof=1
                    )
                ) if len(
                    target_values
                ) > 1 else 0.0

                p05 = float(
                    target_values.quantile(
                        0.05
                    )
                )

                p25 = float(
                    target_values.quantile(
                        0.25
                    )
                )

                p75 = float(
                    target_values.quantile(
                        0.75
                    )
                )

                p95 = float(
                    target_values.quantile(
                        0.95
                    )
                )

            audit = TargetAudit(
                horizon=horizon,
                target_column=target_column,
                availability_column=(
                    availability_column
                ),
                total_rows=total,
                available_count=(
                    available_count
                ),
                unavailable_count=(
                    unavailable_count
                ),
                availability_ratio=(
                    ratio
                ),
                minimum_value=minimum,
                maximum_value=maximum,
                mean_value=mean,
                median_value=median,
                standard_deviation=std,
                p05=p05,
                p25=p25,
                p75=p75,
                p95=p95,
                metadata={
                    "coverage_percentage": (
                        ratio * 100.0
                    ),
                },
            )

            audits.append(
                audit
            )

            if (
                self._config
                .warn_on_low_target_coverage
                and ratio
                < self._config
                .minimum_target_coverage_ratio
            ):

                findings.append(
                    AuditFinding(
                        code=(
                            "LOW_TARGET_COVERAGE"
                        ),
                        severity=(
                            FindingSeverity.WARNING
                        ),
                        message=(
                            f"{horizon} target coverage "
                            f"is {ratio:.2%}, below the "
                            f"configured threshold of "
                            f"{self._config.minimum_target_coverage_ratio:.2%}."
                        ),
                        count=(
                            unavailable_count
                        ),
                        metadata={
                            "horizon": horizon,
                            "available": (
                                available_count
                            ),
                            "total": total,
                        },
                    )
                )

        return audits

    # ========================================================
    # Hourly coverage
    # ========================================================

    def _audit_hourly_coverage(
        self,
        dataframe: pd.DataFrame,
    ) -> list[HourlyCoverage]:

        working = dataframe.copy(
            deep=True
        )

        working[
            "_hour"
        ] = working[
            TIMESTAMP_COLUMN
        ].dt.hour

        results: list[
            HourlyCoverage
        ] = []

        for hour in range(24):

            subset = working.loc[
                working["_hour"] == hour
            ]

            total = len(
                subset
            )

            observed = int(
                subset[
                    OBSERVATION_PRESENT_COLUMN
                ].sum()
            )

            results.append(
                HourlyCoverage(
                    hour=hour,
                    total_rows=total,
                    observed_rows=observed,
                    missing_rows=(
                        total - observed
                    ),
                    observed_ratio=(
                        observed / total
                        if total
                        else 0.0
                    ),
                    target_30m_rows=int(
                        subset[
                            TARGET_30M_AVAILABLE_COLUMN
                        ].sum()
                    ),
                    target_1h_rows=int(
                        subset[
                            TARGET_1H_AVAILABLE_COLUMN
                        ].sum()
                    ),
                    target_2h_rows=int(
                        subset[
                            TARGET_2H_AVAILABLE_COLUMN
                        ].sum()
                    ),
                    target_tomorrow_rows=int(
                        subset[
                            TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN
                        ].sum()
                    ),
                )
            )

        return results

    # ========================================================
    # Daily coverage
    # ========================================================

    def _audit_daily_coverage(
        self,
        dataframe: pd.DataFrame,
    ) -> list[DailyCoverage]:

        working = dataframe.copy(
            deep=True
        )

        working[
            "_date"
        ] = working[
            TIMESTAMP_COLUMN
        ].dt.normalize()

        results: list[
            DailyCoverage
        ] = []

        for (
            date,
            subset,
        ) in working.groupby(
            "_date",
            sort=True,
        ):

            total = len(
                subset
            )

            observed = int(
                subset[
                    OBSERVATION_PRESENT_COLUMN
                ].sum()
            )

            results.append(
                DailyCoverage(
                    date=date,
                    total_rows=total,
                    observed_rows=observed,
                    missing_rows=(
                        total - observed
                    ),
                    observed_ratio=(
                        observed / total
                        if total
                        else 0.0
                    ),
                    target_30m_rows=int(
                        subset[
                            TARGET_30M_AVAILABLE_COLUMN
                        ].sum()
                    ),
                    target_1h_rows=int(
                        subset[
                            TARGET_1H_AVAILABLE_COLUMN
                        ].sum()
                    ),
                    target_2h_rows=int(
                        subset[
                            TARGET_2H_AVAILABLE_COLUMN
                        ].sum()
                    ),
                    target_tomorrow_rows=int(
                        subset[
                            TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN
                        ].sum()
                    ),
                )
            )

        return results

    # ========================================================
    # Duplicate check
    # ========================================================

    def _check_duplicates(
        self,
        dataframe: pd.DataFrame,
        findings: list[AuditFinding],
    ) -> None:

        duplicate_mask = (
            dataframe[
                [
                    FACILITY_COLUMN,
                    TIMESTAMP_COLUMN,
                ]
            ]
            .duplicated(
                keep=False
            )
        )

        count = int(
            duplicate_mask.sum()
        )

        if (
            count
            > self._config
            .max_duplicate_facility_timestamp_rows
        ):

            findings.append(
                AuditFinding(
                    code=(
                        "DUPLICATE_FACILITY_TIMESTAMP"
                    ),
                    severity=(
                        FindingSeverity.ERROR
                    ),
                    message=(
                        f"Dataset contains {count} "
                        "rows participating in duplicate "
                        "facility/timestamp groups."
                    ),
                    count=count,
                )
            )

    # ========================================================
    # Timestamp checks
    # ========================================================

    def _check_timestamps(
        self,
        dataframe: pd.DataFrame,
        findings: list[AuditFinding],
    ) -> None:

        invalid = int(
            dataframe[
                TIMESTAMP_COLUMN
            ].isna().sum()
        )

        if invalid:

            severity = (
                FindingSeverity.ERROR
                if self._config
                .fail_on_invalid_timestamps
                else FindingSeverity.WARNING
            )

            findings.append(
                AuditFinding(
                    code=(
                        "INVALID_TIMESTAMP"
                    ),
                    severity=severity,
                    message=(
                        f"Dataset contains {invalid} "
                        "invalid normalized timestamps."
                    ),
                    count=invalid,
                )
            )

    # ========================================================
    # Occupancy checks
    # ========================================================

    def _check_occupancy(
        self,
        dataframe: pd.DataFrame,
        findings: list[AuditFinding],
    ) -> None:

        observed = (
            dataframe[
                OBSERVATION_PRESENT_COLUMN
            ]
        )

        occupancy = pd.to_numeric(
            dataframe.loc[
                observed,
                OCCUPANCY_RATE_COLUMN,
            ],
            errors="coerce",
        )

        invalid_numeric = int(
            occupancy.isna().sum()
        )

        if invalid_numeric:

            severity = (
                FindingSeverity.ERROR
                if self._config
                .fail_on_invalid_occupancy
                else FindingSeverity.WARNING
            )

            findings.append(
                AuditFinding(
                    code=(
                        "INVALID_OCCUPANCY_RATE"
                    ),
                    severity=severity,
                    message=(
                        f"{invalid_numeric} observed "
                        "rows contain invalid occupancy rates."
                    ),
                    count=invalid_numeric,
                )
            )

        finite = occupancy[
            np.isfinite(
                occupancy
            )
        ]

        below_minimum = int(
            (
                finite
                < self._config
                .minimum_occupancy_rate
            ).sum()
        )

        above_maximum = int(
            (
                finite
                > self._config
                .maximum_occupancy_rate
            ).sum()
        )

        if below_minimum:

            findings.append(
                AuditFinding(
                    code=(
                        "OCCUPANCY_BELOW_MINIMUM"
                    ),
                    severity=(
                        FindingSeverity.ERROR
                    ),
                    message=(
                        f"{below_minimum} occupancy "
                        "rates are below the configured "
                        "minimum."
                    ),
                    count=below_minimum,
                )
            )

        if above_maximum:

            findings.append(
                AuditFinding(
                    code=(
                        "OCCUPANCY_ABOVE_MAXIMUM"
                    ),
                    severity=(
                        FindingSeverity.ERROR
                    ),
                    message=(
                        f"{above_maximum} occupancy "
                        "rates exceed the configured "
                        "maximum."
                    ),
                    count=above_maximum,
                )
            )

    # ========================================================
    # Target consistency
    # ========================================================

    def _check_target_consistency(
        self,
        dataframe: pd.DataFrame,
        findings: list[AuditFinding],
    ) -> None:

        definitions = [
            (
                TARGET_30M_AVAILABLE_COLUMN,
                TARGET_30M_COLUMN,
            ),
            (
                TARGET_1H_AVAILABLE_COLUMN,
                TARGET_1H_COLUMN,
            ),
            (
                TARGET_2H_AVAILABLE_COLUMN,
                TARGET_2H_COLUMN,
            ),
            (
                TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN,
                TARGET_TOMORROW_MORNING_COLUMN,
            ),
        ]

        for (
            availability_column,
            target_column,
        ) in definitions:

            available = (
                dataframe[
                    availability_column
                ]
                .fillna(False)
                .astype(bool)
            )

            missing_target = (
                dataframe[
                    target_column
                ].isna()
            )

            inconsistent_available = int(
                (
                    available
                    & missing_target
                ).sum()
            )

            inconsistent_unavailable = int(
                (
                    ~available
                    & ~missing_target
                ).sum()
            )

            if inconsistent_available:

                findings.append(
                    AuditFinding(
                        code=(
                            "TARGET_AVAILABILITY_MISMATCH"
                        ),
                        severity=(
                            FindingSeverity.ERROR
                        ),
                        message=(
                            f"{availability_column} marks "
                            f"{inconsistent_available} rows "
                            "as available although the target "
                            "value is missing."
                        ),
                        count=(
                            inconsistent_available
                        ),
                        metadata={
                            "availability_column": (
                                availability_column
                            ),
                            "target_column": (
                                target_column
                            ),
                        },
                    )
                )

            if inconsistent_unavailable:

                findings.append(
                    AuditFinding(
                        code=(
                            "TARGET_VALUE_WITHOUT_AVAILABILITY"
                        ),
                        severity=(
                            FindingSeverity.ERROR
                        ),
                        message=(
                            f"{target_column} contains "
                            f"{inconsistent_unavailable} "
                            "values marked as unavailable."
                        ),
                        count=(
                            inconsistent_unavailable
                        ),
                        metadata={
                            "availability_column": (
                                availability_column
                            ),
                            "target_column": (
                                target_column
                            ),
                        },
                    )
                )

    # ========================================================
    # Readiness checks
    # ========================================================

    def _check_dataset_readiness(
        self,
        summary: DatasetSummary,
        facilities: list[FacilityAudit],
        targets: list[TargetAudit],
        findings: list[AuditFinding],
    ) -> None:

        if summary.row_count == 0:

            findings.append(
                AuditFinding(
                    code=(
                        "EMPTY_DATASET"
                    ),
                    severity=(
                        FindingSeverity.CRITICAL
                    ),
                    message=(
                        "The ML dataset contains no rows."
                    ),
                )
            )

            return

        observed_ratio = (
            summary.observed_row_count
            / summary.row_count
        )

        if (
            observed_ratio
            < self._config
            .minimum_observed_ratio
        ):

            findings.append(
                AuditFinding(
                    code=(
                        "LOW_OBSERVED_RATIO"
                    ),
                    severity=(
                        FindingSeverity.WARNING
                    ),
                    message=(
                        f"Observed-row ratio is "
                        f"{observed_ratio:.2%}, below "
                        f"the configured threshold of "
                        f"{self._config.minimum_observed_ratio:.2%}."
                    ),
                    count=(
                        summary.observed_row_count
                    ),
                )
            )

        # ----------------------------------------------------
        # Identify facilities with no usable target at all.
        # ----------------------------------------------------

        targetless_facilities = [
            facility.facility_code
            for facility in facilities
            if facility.target_eligible_count == 0
        ]

        if targetless_facilities:

            findings.append(
                AuditFinding(
                    code=(
                        "TARGETLESS_FACILITY"
                    ),
                    severity=(
                        FindingSeverity.WARNING
                    ),
                    message=(
                        f"{len(targetless_facilities)} "
                        "facilities have no target-eligible "
                        "rows."
                    ),
                    count=len(
                        targetless_facilities
                    ),
                    metadata={
                        "facilities": (
                            targetless_facilities
                        ),
                    },
                )
            )

        # ----------------------------------------------------
        # Target distribution.
        # ----------------------------------------------------

        if summary.target_eligible_count == 0:

            findings.append(
                AuditFinding(
                    code=(
                        "NO_SUPERVISED_TARGETS"
                    ),
                    severity=(
                        FindingSeverity.CRITICAL
                    ),
                    message=(
                        "No supervised-learning targets "
                        "are available."
                    ),
                )
            )

        # ----------------------------------------------------
        # High missingness.
        # ----------------------------------------------------

        missing_ratio = (
            summary.missing_row_count
            / summary.row_count
        )

        if (
            self._config
            .warn_on_high_missingness
            and missing_ratio > 0.80
        ):

            findings.append(
                AuditFinding(
                    code=(
                        "HIGH_TEMPORAL_MISSINGNESS"
                    ),
                    severity=(
                        FindingSeverity.WARNING
                    ),
                    message=(
                        f"{missing_ratio:.2%} of normalized "
                        "time slots contain no observation."
                    ),
                    count=(
                        summary.missing_row_count
                    ),
                )
            )

    # ========================================================
    # Determine overall status
    # ========================================================

    @staticmethod
    def _determine_status(
        findings: list[AuditFinding],
    ) -> AuditStatus:

        if any(
            finding.severity
            == FindingSeverity.CRITICAL
            for finding in findings
        ):

            return AuditStatus.FAIL

        if any(
            finding.severity
            == FindingSeverity.ERROR
            for finding in findings
        ):

            return AuditStatus.FAIL

        if any(
            finding.severity
            == FindingSeverity.WARNING
            for finding in findings
        ):

            return (
                AuditStatus
                .PASS_WITH_WARNINGS
            )

        return AuditStatus.PASS


# ============================================================
# Convenience API
# ============================================================


def audit_ml_dataset(
    dataframe: pd.DataFrame,
    *,
    config: DatasetAuditConfig | None = None,
) -> DatasetAuditResult:
    """
    Audit an already-built ML dataset.
    """

    auditor = DatasetAuditor(
        config=config
    )

    return auditor.audit(
        dataframe
    )


# ============================================================
# Birmingham convenience API
# ============================================================


def audit_birmingham_ml_dataset(
    *,
    dataset_root: str = "../datasets/raw",
    config: DatasetAuditConfig | None = None,
):
    """
    Build and audit the Birmingham ML dataset.

    This is a convenience function for development and
    validation.

    Production code can separately call:

        build_birmingham_ml_dataset()
        audit_ml_dataset()
    """

    from app.ml.data.dataset_builder import (
        build_birmingham_ml_dataset,
    )

    dataset_result = (
        build_birmingham_ml_dataset(
            dataset_root=dataset_root
        )
    )

    audit_result = audit_ml_dataset(
        dataset_result.dataframe,
        config=config,
    )

    return audit_result


# ============================================================
# Human-readable report helper
# ============================================================


def format_audit_summary(
    report: DatasetAuditReport,
) -> str:
    """
    Generate a concise human-readable audit summary.

    Useful from the command line.
    """

    lines: list[str] = []

    lines.append(
        "=================================================="
    )

    lines.append(
        "SMARTPARK AI - ML DATASET AUDIT"
    )

    lines.append(
        "=================================================="
    )

    lines.append(
        f"Status: {report.status.value}"
    )

    lines.append(
        f"Rows: {report.summary.row_count:,}"
    )

    lines.append(
        f"Columns: {report.summary.column_count:,}"
    )

    lines.append(
        f"Facilities: {report.summary.facility_count:,}"
    )

    lines.append(
        f"Observed rows: "
        f"{report.summary.observed_row_count:,}"
    )

    lines.append(
        f"Missing rows: "
        f"{report.summary.missing_row_count:,}"
    )

    lines.append(
        f"Target eligible: "
        f"{report.summary.target_eligible_count:,} "
        f"({report.summary.target_eligible_ratio:.2%})"
    )

    lines.append("")

    lines.append(
        "TARGET COVERAGE"
    )

    lines.append(
        "--------------------------------------------------"
    )

    for target in report.targets:

        lines.append(
            f"{target.horizon:20s} "
            f"{target.available_count:8,d} / "
            f"{target.total_rows:8,d} "
            f"({target.availability_ratio:.2%})"
        )

    lines.append("")

    lines.append(
        "FACILITIES"
    )

    lines.append(
        "--------------------------------------------------"
    )

    for facility in report.facilities:

        lines.append(
            f"{facility.facility_code:25s} "
            f"observed={facility.observed_count:5,d} "
            f"30m={facility.target_30m_count:5,d} "
            f"1h={facility.target_1h_count:5,d} "
            f"2h={facility.target_2h_count:5,d}"
        )

    lines.append("")

    lines.append(
        "FINDINGS"
    )

    lines.append(
        "--------------------------------------------------"
    )

    if not report.findings:

        lines.append(
            "No findings."
        )

    else:

        for finding in report.findings:

            lines.append(
                f"[{finding.severity.value:8s}] "
                f"{finding.code}: "
                f"{finding.message}"
            )

    lines.append("")

    lines.append(
        "=================================================="
    )

    lines.append(
        f"Ready for feature engineering: "
        f"{report.ready_for_feature_engineering}"
    )

    lines.append(
        "=================================================="
    )

    return "\n".join(
        lines
    )


# ============================================================
# Public API
# ============================================================

# ============================================================
# Public API
# ============================================================

__all__ = [
    # Columns
    "FACILITY_COLUMN",
    "TIMESTAMP_COLUMN",
    "OCCUPANCY_RATE_COLUMN",
    "TOTAL_SPACES_COLUMN",
    "OCCUPIED_SPACES_COLUMN",
    "AVAILABLE_SPACES_COLUMN",
    "OBSERVATION_PRESENT_COLUMN",
    "SEQUENCE_BREAK_COLUMN",
    "IS_OPERATIONAL_GAP_COLUMN",
    "IS_DATA_GAP_COLUMN",
    "QUALITY_STATUS_COLUMN",

    # Targets
    "TARGET_30M_COLUMN",
    "TARGET_1H_COLUMN",
    "TARGET_2H_COLUMN",
    "TARGET_TOMORROW_MORNING_COLUMN",

    # Availability
    "TARGET_30M_AVAILABLE_COLUMN",
    "TARGET_1H_AVAILABLE_COLUMN",
    "TARGET_2H_AVAILABLE_COLUMN",
    "TARGET_TOMORROW_MORNING_AVAILABLE_COLUMN",
    "TARGET_ELIGIBLE_COLUMN",
    "TARGET_EXCLUSION_REASON_COLUMN",

    # Enums
    "AuditStatus",
    "FindingSeverity",

    # Exceptions
    "DatasetAuditError",
    "DatasetAuditSchemaError",
    "DatasetAuditDataError",
    "DatasetAuditConfigurationError",

    # Configuration
    "DatasetAuditConfig",

    # Result structures
    "AuditFinding",
    "DatasetSummary",
    "FacilityAudit",
    "TargetAudit",
    "HourlyCoverage",
    "DailyCoverage",
    "DatasetAuditReport",
    "DatasetAuditResult",

    # Auditor
    "DatasetAuditor",

    # Convenience functions
    "audit_ml_dataset",
    "audit_birmingham_ml_dataset",
    "format_audit_summary",
]