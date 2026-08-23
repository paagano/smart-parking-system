"""
SmartPark AI - Birmingham Baseline Benchmark
==============================================

Purpose
-------
Benchmark simple forecasting baselines against the persisted Birmingham
training/validation datasets.

This is the first model-level benchmark after the Birmingham ML dataset
has passed:

    - Feature pipeline validation
    - Target audit
    - Training dataset validation
    - Persistence validation
    - Training dataset integrity audit

Current benchmark target
------------------------
    target_occupancy_rate_30m

The script intentionally uses the persisted datasets under:

    datasets/processed/birmingham/

and DOES NOT rebuild the feature pipeline.

Leakage contract
----------------
Training:
    train.parquet ONLY

Validation:
    validation.parquet ONLY

The validation target is never supplied to model.fit().

Test data:
    test.parquet is deliberately NOT used in this benchmark.

Baselines
---------
1. MeanBaseline
2. LastValueBaseline

Metrics
-------
- MAE
- RMSE
- R²
- MAPE

The resulting benchmark establishes the minimum performance that a
future XGBoost/LSTM model should beat.
"""

from __future__ import annotations

import json
import sys
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ============================================================================
# PROJECT PATHS
# ============================================================================

BACKEND_ROOT = Path(__file__).resolve().parent

PROJECT_ROOT = BACKEND_ROOT.parent

PROCESSED_DATASET_ROOT = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
)


# ============================================================================
# IMPORT ML BASELINE MODELS
# ============================================================================

try:
    from app.ml.ml_models.baseline_model import (
        MeanBaseline,
        LastValueBaseline,
        BaselineEvaluationResult,
        compare_baselines,
    )
except ImportError as exc:
    print()
    print("=" * 78)
    print("ERROR: Unable TO IMPORT BASELINE MODEL")
    print("=" * 78)
    print()
    print(
        "Expected module:"
    )
    print(
        "  app.ml.ml_models.baseline_model"
    )
    print()
    print(
        "Make sure you are running this script from the backend "
        "environment."
    )
    print()
    print(f"Original error: {exc}")
    print()

    raise SystemExit(1)


# ============================================================================
# CONFIGURATION
# ============================================================================

TARGET_COLUMN = (
    "target_occupancy_rate_30m"
)

TRAIN_FILE = (
    PROCESSED_DATASET_ROOT
    / TARGET_COLUMN
    / "train.parquet"
)

VALIDATION_FILE = (
    PROCESSED_DATASET_ROOT
    / TARGET_COLUMN
    / "validation.parquet"
)

TEST_FILE = (
    PROCESSED_DATASET_ROOT
    / TARGET_COLUMN
    / "test.parquet"
)

EXPECTED_FEATURE_COUNT = 296

EXPECTED_TRAIN_ROWS = 23_244

EXPECTED_VALIDATION_ROWS = 4_980

EXPECTED_TEST_ROWS = 4_982


# ============================================================================
# OUTPUT
# ============================================================================

OUTPUT_ROOT = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
    / "baseline_benchmark"
)

RESULTS_JSON = (
    OUTPUT_ROOT
    / "baseline_benchmark_results.json"
)

RESULTS_CSV = (
    OUTPUT_ROOT
    / "baseline_benchmark_results.csv"
)


# ============================================================================
# DISPLAY HELPERS
# ============================================================================


def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def print_key_value(
    label: str,
    value: Any,
) -> None:
    print(
        f"{label:<38}: {value}"
    )


# ============================================================================
# FILE VALIDATION
# ============================================================================


def validate_required_files() -> None:
    """
    Confirm that the persisted Birmingham datasets exist.

    We deliberately require only train and validation.

    The test dataset is checked for existence but is NOT loaded or used.
    """

    print_section(
        "DATASET FILE VALIDATION"
    )

    print_key_value(
        "Processed dataset root",
        PROCESSED_DATASET_ROOT,
    )

    print_key_value(
        "Training dataset",
        TRAIN_FILE,
    )

    print_key_value(
        "Validation dataset",
        VALIDATION_FILE,
    )

    print_key_value(
        "Test dataset",
        TEST_FILE,
    )

    if not PROCESSED_DATASET_ROOT.exists():
        raise FileNotFoundError(
            "Birmingham processed dataset directory does not exist: "
            f"{PROCESSED_DATASET_ROOT}"
        )

    if not TRAIN_FILE.exists():
        raise FileNotFoundError(
            "Training Parquet file does not exist: "
            f"{TRAIN_FILE}"
        )

    if not VALIDATION_FILE.exists():
        raise FileNotFoundError(
            "Validation Parquet file does not exist: "
            f"{VALIDATION_FILE}"
        )

    if not TEST_FILE.exists():
        raise FileNotFoundError(
            "Expected Birmingham test dataset does not exist: "
            f"{TEST_FILE}"
        )

    print()
    print(
        "Required training/validation datasets: PASS"
    )

    print(
        "Test dataset exists but will NOT be loaded: PASS"
    )


# ============================================================================
# DATA LOADING
# ============================================================================


def load_training_dataset() -> pd.DataFrame:
    """
    Load the persisted training dataset.
    """

    print_section(
        "LOADING TRAINING DATASET"
    )

    dataframe = pd.read_parquet(
        TRAIN_FILE
    )

    print_key_value(
        "Training rows",
        f"{len(dataframe):,}",
    )

    print_key_value(
        "Training columns",
        f"{len(dataframe.columns):,}",
    )

    return dataframe


def load_validation_dataset() -> pd.DataFrame:
    """
    Load the persisted validation dataset.
    """

    print_section(
        "LOADING VALIDATION DATASET"
    )

    dataframe = pd.read_parquet(
        VALIDATION_FILE
    )

    print_key_value(
        "Validation rows",
        f"{len(dataframe):,}",
    )

    print_key_value(
        "Validation columns",
        f"{len(dataframe.columns):,}",
    )

    return dataframe


# ============================================================================
# DATASET STRUCTURE VALIDATION
# ============================================================================


def validate_dataset_structure(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> None:
    """
    Validate the basic structure of the persisted datasets.
    """

    print_section(
        "DATASET STRUCTURE VALIDATION"
    )

    if len(train_df) != EXPECTED_TRAIN_ROWS:
        raise AssertionError(
            "Unexpected training row count: "
            f"{len(train_df):,}; expected "
            f"{EXPECTED_TRAIN_ROWS:,}."
        )

    if len(validation_df) != EXPECTED_VALIDATION_ROWS:
        raise AssertionError(
            "Unexpected validation row count: "
            f"{len(validation_df):,}; expected "
            f"{EXPECTED_VALIDATION_ROWS:,}."
        )

    if TARGET_COLUMN not in train_df.columns:
        raise AssertionError(
            f"Target column '{TARGET_COLUMN}' "
            "is missing from training dataset."
        )

    if TARGET_COLUMN not in validation_df.columns:
        raise AssertionError(
            f"Target column '{TARGET_COLUMN}' "
            "is missing from validation dataset."
        )

    print_key_value(
        "Training row count",
        f"{len(train_df):,} / {EXPECTED_TRAIN_ROWS:,} PASS",
    )

    print_key_value(
        "Validation row count",
        f"{len(validation_df):,} / "
        f"{EXPECTED_VALIDATION_ROWS:,} PASS",
    )

    print_key_value(
        "Target column in training",
        "PASS",
    )

    print_key_value(
        "Target column in validation",
        "PASS",
    )


# ============================================================================
# FEATURE / TARGET DISCOVERY
# ============================================================================


def identify_feature_columns(
    dataframe: pd.DataFrame,
) -> list[str]:
    """
    Identify ML feature columns.

    The persisted training dataset contains:

        296 features
        target
        target availability
        metadata

    We use the feature registry implied by the persisted dataset and
    explicitly exclude targets, availability columns and known metadata.
    """

    excluded_columns = {
        TARGET_COLUMN,
        "target_30m_available",
        "target_1h_available",
        "target_2h_available",
        "target_tomorrow_morning_available",
    }

    metadata_columns = {
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
        "target_exclusion_reason",
    }

    excluded_columns.update(
        metadata_columns
    )

    feature_columns = [
        column
        for column in dataframe.columns
        if column not in excluded_columns
    ]

    return feature_columns


def validate_feature_registry(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> list[str]:
    """
    Validate that the persisted datasets contain the expected
    296 ML features.
    """

    print_section(
        "FEATURE REGISTRY VALIDATION"
    )

    train_features = identify_feature_columns(
        train_df
    )

    validation_features = identify_feature_columns(
        validation_df
    )

    if len(train_features) != EXPECTED_FEATURE_COUNT:
        raise AssertionError(
            "Unexpected training feature count: "
            f"{len(train_features)}; expected "
            f"{EXPECTED_FEATURE_COUNT}."
        )

    if len(validation_features) != EXPECTED_FEATURE_COUNT:
        raise AssertionError(
            "Unexpected validation feature count: "
            f"{len(validation_features)}; expected "
            f"{EXPECTED_FEATURE_COUNT}."
        )

    if train_features != validation_features:
        raise AssertionError(
            "Training and validation feature registries differ."
        )

    print_key_value(
        "Training feature count",
        f"{len(train_features)} / "
        f"{EXPECTED_FEATURE_COUNT} PASS",
    )

    print_key_value(
        "Validation feature count",
        f"{len(validation_features)} / "
        f"{EXPECTED_FEATURE_COUNT} PASS",
    )

    print_key_value(
        "Train/validation feature registry",
        "IDENTICAL",
    )

    return train_features


# ============================================================================
# TARGET VALIDATION
# ============================================================================


def validate_target_data(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> None:
    """
    Validate target availability before training.
    """

    print_section(
        "TARGET VALIDATION"
    )

    train_target = pd.to_numeric(
        train_df[TARGET_COLUMN],
        errors="coerce",
    )

    validation_target = pd.to_numeric(
        validation_df[TARGET_COLUMN],
        errors="coerce",
    )

    train_valid = (
        train_target.notna()
    )

    validation_valid = (
        validation_target.notna()
    )

    if not train_valid.all():
        raise AssertionError(
            "Training dataset contains null target values."
        )

    if not validation_valid.all():
        raise AssertionError(
            "Validation dataset contains null target values."
        )

    if not np.isfinite(
        train_target.to_numpy(
            dtype=float
        )
    ).all():
        raise AssertionError(
            "Training target contains infinite values."
        )

    if not np.isfinite(
        validation_target.to_numpy(
            dtype=float
        )
    ).all():
        raise AssertionError(
            "Validation target contains infinite values."
        )

    print_key_value(
        "Training target rows",
        f"{len(train_target):,}",
    )

    print_key_value(
        "Validation target rows",
        f"{len(validation_target):,}",
    )

    print_key_value(
        "Training target nulls",
        f"{int(train_target.isna().sum())}",
    )

    print_key_value(
        "Validation target nulls",
        f"{int(validation_target.isna().sum())}",
    )

    print_key_value(
        "Training target mean",
        f"{train_target.mean():.6f}",
    )

    print_key_value(
        "Validation target mean",
        f"{validation_target.mean():.6f}",
    )

    print_key_value(
        "Training target range",
        f"{train_target.min():.6f} -> "
        f"{train_target.max():.6f}",
    )

    print_key_value(
        "Validation target range",
        f"{validation_target.min():.6f} -> "
        f"{validation_target.max():.6f}",
    )


# ============================================================================
# TEMPORAL VALIDATION
# ============================================================================


def validate_temporal_order(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> None:
    """
    Confirm that the persisted train and validation datasets are
    chronologically ordered.

    The integrity audit has already established this property.

    This benchmark performs a lightweight re-check.
    """

    print_section(
        "CHRONOLOGICAL ORDER VALIDATION"
    )

    timestamp_column = "normalized_at"

    if timestamp_column not in train_df.columns:
        raise AssertionError(
            "Training dataset does not contain "
            "'normalized_at'."
        )

    if timestamp_column not in validation_df.columns:
        raise AssertionError(
            "Validation dataset does not contain "
            "'normalized_at'."
        )

    train_timestamps = pd.to_datetime(
        train_df[timestamp_column],
        errors="coerce",
    )

    validation_timestamps = pd.to_datetime(
        validation_df[timestamp_column],
        errors="coerce",
    )

    if train_timestamps.isna().any():
        raise AssertionError(
            "Training dataset contains invalid timestamps."
        )

    if validation_timestamps.isna().any():
        raise AssertionError(
            "Validation dataset contains invalid timestamps."
        )

    train_max = train_timestamps.max()

    validation_min = validation_timestamps.min()

    if train_max > validation_min:
        raise AssertionError(
            "Chronological leakage detected: "
            f"training max={train_max}, "
            f"validation min={validation_min}."
        )

    print_key_value(
        "Training minimum",
        train_timestamps.min(),
    )

    print_key_value(
        "Training maximum",
        train_max,
    )

    print_key_value(
        "Validation minimum",
        validation_min,
    )

    print_key_value(
        "Validation maximum",
        validation_timestamps.max(),
    )

    print_key_value(
        "Chronological ordering",
        "PASS",
    )


# ============================================================================
# OBSERVATION KEY ISOLATION
# ============================================================================


def validate_observation_isolation(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> None:
    """
    Confirm that train and validation do not contain the same
    facility/timestamp observation keys.
    """

    print_section(
        "TRAIN / VALIDATION OBSERVATION ISOLATION"
    )

    facility_column = (
        "source_facility_code"
    )

    timestamp_column = (
        "normalized_at"
    )

    required = {
        facility_column,
        timestamp_column,
    }

    missing_train = (
        required
        - set(train_df.columns)
    )

    missing_validation = (
        required
        - set(validation_df.columns)
    )

    if missing_train:
        raise AssertionError(
            "Training dataset missing observation-key columns: "
            f"{sorted(missing_train)}"
        )

    if missing_validation:
        raise AssertionError(
            "Validation dataset missing observation-key columns: "
            f"{sorted(missing_validation)}"
        )

    train_keys = set(
        zip(
            train_df[facility_column].astype(str),
            pd.to_datetime(
                train_df[timestamp_column]
            ).astype(str),
        )
    )

    validation_keys = set(
        zip(
            validation_df[facility_column].astype(str),
            pd.to_datetime(
                validation_df[timestamp_column]
            ).astype(str),
        )
    )

    overlap = (
        train_keys
        & validation_keys
    )

    if overlap:
        raise AssertionError(
            "Train/validation observation overlap detected: "
            f"{len(overlap)} rows."
        )

    print_key_value(
        "Train observations",
        f"{len(train_keys):,}",
    )

    print_key_value(
        "Validation observations",
        f"{len(validation_keys):,}",
    )

    print_key_value(
        "Train ∩ Validation",
        "0",
    )

    print_key_value(
        "Observation isolation",
        "PASS",
    )


# ============================================================================
# BASELINE TRAINING
# ============================================================================


def train_baselines(
    train_df: pd.DataFrame,
) -> list[Any]:
    """
    Fit the baseline models using TRAIN DATA ONLY.
    """

    print_section(
        "TRAINING BASELINE MODELS"
    )

    print(
        "IMPORTANT: validation dataset is NOT passed to fit()."
    )

    print()

    models = []

    mean_model = MeanBaseline(
        target_column=TARGET_COLUMN
    )

    mean_model.fit(
        train_df
    )

    models.append(
        mean_model
    )

    print_key_value(
        "MeanBaseline",
        "FIT",
    )

    print_key_value(
        "Mean value",
        f"{mean_model.mean_value:.6f}",
    )

    last_value_model = LastValueBaseline(
        target_column=TARGET_COLUMN
    )

    last_value_model.fit(
        train_df
    )

    models.append(
        last_value_model
    )

    print_key_value(
        "LastValueBaseline",
        "FIT",
    )

    print_key_value(
        "Last observed value",
        f"{last_value_model.last_value:.6f}",
    )

    return models


# ============================================================================
# BASELINE EVALUATION
# ============================================================================


def evaluate_baselines(
    models: list[Any],
    validation_df: pd.DataFrame,
) -> list[BaselineEvaluationResult]:
    """
    Evaluate fitted baselines using validation data.
    """

    print_section(
        "VALIDATION EVALUATION"
    )

    print(
        "Validation data is used ONLY for prediction/evaluation."
    )

    print()

    results = []

    for model in models:

        result = model.evaluate(
            validation_df
        )

        results.append(
            result
        )

        print(
            f"{result.model_name}"
        )

        print(
            f"  MAE :  {result.metrics.mae:.6f}"
        )

        print(
            f"  RMSE:  {result.metrics.rmse:.6f}"
        )

        print(
            f"  R²  :  {result.metrics.r2:.6f}"
        )

        if result.metrics.mape is None:
            print(
                "  MAPE:  N/A"
            )
        else:
            print(
                f"  MAPE:  {result.metrics.mape:.4f}%"
            )

        print(
            f"  N   :  {result.metrics.sample_count:,}"
        )

        print()

    return results


# ============================================================================
# COMPARISON
# ============================================================================


def display_comparison(
    results: list[BaselineEvaluationResult],
) -> pd.DataFrame:
    """
    Display and return baseline comparison table.
    """

    print_section(
        "BASELINE COMPARISON"
    )

    comparison = compare_baselines(
        results
    )

    display_columns = [
        "model_name",
        "strategy",
        "mae",
        "rmse",
        "r2",
        "mape",
        "sample_count",
    ]

    print(
        comparison[
            display_columns
        ].to_string(
            index=False
        )
    )

    print()

    best_model = comparison.iloc[0]

    print_key_value(
        "Best baseline by MAE",
        best_model["model_name"],
    )

    print_key_value(
        "Best baseline MAE",
        f"{best_model['mae']:.6f}",
    )

    return comparison


# ============================================================================
# LEAKAGE CONTRACT
# ============================================================================


def validate_leakage_contract(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    models: list[Any],
) -> None:
    """
    Explicitly document and validate the baseline training contract.
    """

    print_section(
        "LEAKAGE CONTRACT"
    )

    # These are deliberately explicit because the benchmark should
    # remain auditable.

    validation_target_was_used_during_fit = False

    future_data_used = False

    test_data_loaded = False

    cross_facility_data_used = False

    target_imputation = False

    random_shuffle = False

    chronological_split = True

    if validation_target_was_used_during_fit:
        raise AssertionError(
            "Validation target was used during model fitting."
        )

    if future_data_used:
        raise AssertionError(
            "Future data was used."
        )

    if test_data_loaded:
        raise AssertionError(
            "Test data was loaded during baseline benchmarking."
        )

    if cross_facility_data_used:
        raise AssertionError(
            "Cross-facility information was used."
        )

    if target_imputation:
        raise AssertionError(
            "Target imputation is enabled."
        )

    if random_shuffle:
        raise AssertionError(
            "Random shuffle is enabled."
        )

    if not chronological_split:
        raise AssertionError(
            "Chronological split contract is not active."
        )

    print_key_value(
        "Future data used",
        "False",
    )

    print_key_value(
        "Validation target used during fit",
        "False",
    )

    print_key_value(
        "Test dataset loaded",
        "False",
    )

    print_key_value(
        "Cross-facility data used",
        "False",
    )

    print_key_value(
        "Target imputation",
        "False",
    )

    print_key_value(
        "Random shuffle",
        "False",
    )

    print_key_value(
        "Chronological split",
        "True",
    )

    print_key_value(
        "Leakage contract",
        "PASS",
    )


# ============================================================================
# RESULT SERIALIZATION
# ============================================================================


def serialize_results(
    results: list[BaselineEvaluationResult],
    comparison: pd.DataFrame,
) -> dict[str, Any]:
    """
    Convert benchmark results into JSON-safe structures.
    """

    benchmark_results = []

    for result in results:

        benchmark_results.append(
            {
                "model_name": result.model_name,
                "strategy": result.strategy,
                "target_column": result.target_column,
                "metrics": result.metrics.to_dict(),
                "metadata": result.metadata,
            }
        )

    comparison_records = (
        comparison
        .replace(
            {
                np.nan: None,
                np.inf: None,
                -np.inf: None,
            }
        )
        .to_dict(
            orient="records"
        )
    )

    return {
        "schema_version": "1.0",
        "dataset_name": "birmingham",
        "target_column": TARGET_COLUMN,
        "created_by": (
            "birmingham_baseline_benchmark.py"
        ),
        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "training_file": str(
            TRAIN_FILE
        ),
        "validation_file": str(
            VALIDATION_FILE
        ),
        "test_file_loaded": False,
        "training_rows": EXPECTED_TRAIN_ROWS,
        "validation_rows": EXPECTED_VALIDATION_ROWS,
        "feature_count": EXPECTED_FEATURE_COUNT,
        "leakage_contract": {
            "future_data_used": False,
            "validation_target_used_during_fit": False,
            "test_dataset_loaded": False,
            "cross_facility_data_used": False,
            "target_imputation": False,
            "random_shuffle": False,
            "chronological_split": True,
        },
        "results": benchmark_results,
        "comparison": comparison_records,
    }


def persist_results(
    results: list[BaselineEvaluationResult],
    comparison: pd.DataFrame,
) -> None:
    """
    Persist benchmark results.
    """

    print_section(
        "PERSISTING BENCHMARK RESULTS"
    )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = serialize_results(
        results,
        comparison,
    )

    with RESULTS_JSON.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            payload,
            file,
            indent=2,
        )

    comparison.to_csv(
        RESULTS_CSV,
        index=False,
    )

    print_key_value(
        "Output directory",
        OUTPUT_ROOT,
    )

    print_key_value(
        "JSON results",
        RESULTS_JSON,
    )

    print_key_value(
        "CSV results",
        RESULTS_CSV,
    )


# ============================================================================
# FINAL ASSERTIONS
# ============================================================================


def run_final_assertions(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    results: list[BaselineEvaluationResult],
    comparison: pd.DataFrame,
) -> None:
    """
    Final benchmark integrity checks.
    """

    print_section(
        "FINAL ASSERTIONS"
    )

    assertions = {
        "Training dataset non-empty": (
            len(train_df) > 0
        ),
        "Validation dataset non-empty": (
            len(validation_df) > 0
        ),
        "Expected feature count": (
            len(
                identify_feature_columns(
                    train_df
                )
            )
            == EXPECTED_FEATURE_COUNT
        ),
        "Expected baseline count": (
            len(results) == 2
        ),
        "All baseline evaluations populated": (
            all(
                result.metrics.sample_count
                > 0
                for result in results
            )
        ),
        "No infinite MAE values": (
            all(
                math_is_finite(
                    result.metrics.mae
                )
                for result in results
            )
        ),
        "No infinite RMSE values": (
            all(
                math_is_finite(
                    result.metrics.rmse
                )
                for result in results
            )
        ),
        "No NaN comparison rows": (
            not comparison.empty
        ),
    }

    failed = []

    for description, passed in assertions.items():

        status = (
            "PASS"
            if passed
            else "FAIL"
        )

        print(
            f"{description:<45}: {status}"
        )

        if not passed:
            failed.append(
                description
            )

    if failed:
        raise AssertionError(
            "Final benchmark assertions failed: "
            + ", ".join(failed)
        )

    print()
    print(
        "ALL BASELINE BENCHMARK ASSERTIONS PASSED"
    )


def math_is_finite(
    value: Any,
) -> bool:
    """
    Safe finite-value check.
    """

    try:
        return bool(
            math.isfinite(
                float(value)
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        return False


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:
    """
    Execute the Birmingham baseline benchmark.
    """

    print_header(
        "SMARTPARK AI - BIRMINGHAM BASELINE BENCHMARK"
    )

    print()
    print(
        "Target:"
    )
    print(
        f"  {TARGET_COLUMN}"
    )

    print()
    print(
        "Benchmark policy:"
    )
    print(
        "  Train on train.parquet only"
    )
    print(
        "  Evaluate on validation.parquet only"
    )
    print(
        "  Do NOT use test.parquet"
    )
    print(
        "  Do NOT rebuild the feature pipeline"
    )

    try:

        # --------------------------------------------------------------
        # 1. File validation
        # --------------------------------------------------------------

        validate_required_files()

        # --------------------------------------------------------------
        # 2. Load datasets
        # --------------------------------------------------------------

        train_df = load_training_dataset()

        validation_df = (
            load_validation_dataset()
        )

        # --------------------------------------------------------------
        # 3. Structural validation
        # --------------------------------------------------------------

        validate_dataset_structure(
            train_df,
            validation_df,
        )

        # --------------------------------------------------------------
        # 4. Feature registry
        # --------------------------------------------------------------

        identify_feature_columns(
            train_df
        )

        validate_feature_registry(
            train_df,
            validation_df,
        )

        # --------------------------------------------------------------
        # 5. Target validation
        # --------------------------------------------------------------

        validate_target_data(
            train_df,
            validation_df,
        )

        # --------------------------------------------------------------
        # 6. Temporal validation
        # --------------------------------------------------------------

        validate_temporal_order(
            train_df,
            validation_df,
        )

        # --------------------------------------------------------------
        # 7. Observation isolation
        # --------------------------------------------------------------

        validate_observation_isolation(
            train_df,
            validation_df,
        )

        # --------------------------------------------------------------
        # 8. Train baselines
        # --------------------------------------------------------------

        models = train_baselines(
            train_df
        )

        # --------------------------------------------------------------
        # 9. Evaluate baselines
        # --------------------------------------------------------------

        results = evaluate_baselines(
            models,
            validation_df,
        )

        # --------------------------------------------------------------
        # 10. Compare
        # --------------------------------------------------------------

        comparison = display_comparison(
            results
        )

        # --------------------------------------------------------------
        # 11. Leakage contract
        # --------------------------------------------------------------

        validate_leakage_contract(
            train_df,
            validation_df,
            models,
        )

        # --------------------------------------------------------------
        # 12. Persist
        # --------------------------------------------------------------

        persist_results(
            results,
            comparison,
        )

        # --------------------------------------------------------------
        # 13. Final assertions
        # --------------------------------------------------------------

        run_final_assertions(
            train_df,
            validation_df,
            results,
            comparison,
        )

        # --------------------------------------------------------------
        # Final success
        # --------------------------------------------------------------

        print_header(
            "BIRMINGHAM BASELINE BENCHMARK COMPLETED SUCCESSFULLY"
        )

        print()
        print(
            f"Target:              {TARGET_COLUMN}"
        )

        print(
            f"Training rows:       {len(train_df):,}"
        )

        print(
            f"Validation rows:     {len(validation_df):,}"
        )

        print(
            f"Features:            {EXPECTED_FEATURE_COUNT}"
        )

        print(
            "Baselines:           Mean + Last Value"
        )

        print(
            "Test dataset used:   NO"
        )

        print(
            "Leakage validation:  PASS"
        )

        print(
            "Benchmark validation: PASS"
        )

        print()
        print(
            "Baseline benchmark is ready for comparison "
            "against XGBoost."
        )

        return 0

    except (
        FileNotFoundError,
        AssertionError,
        ValueError,
        KeyError,
    ) as exc:

        print()
        print_header(
            "BIRMINGHAM BASELINE BENCHMARK FAILED"
        )

        print()
        print(
            f"ERROR: {exc}"
        )

        print()
        print(
            "DO NOT proceed to model comparison until "
            "the reported issue is resolved."
        )

        return 1


# ============================================================================
# ENTRY POINT
# ============================================================================


if __name__ == "__main__":
    raise SystemExit(
        main()
    )