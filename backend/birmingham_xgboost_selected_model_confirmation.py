"""
SMARTPARK AI
Birmingham XGBoost Selected Model Confirmation

Purpose
-------
Confirm the selected XGBoost hyperparameter configuration identified by
birmingham_xgboost_hyperparameter_tuning.py.

Selected candidate:
    TUNE_014 - Higher L1 regularisation

This script intentionally does NOT:
    - perform hyperparameter tuning
    - search another parameter grid
    - rebuild the feature pipeline
    - modify persisted datasets
    - load test.parquet
    - evaluate test.parquet
    - use validation data during model fitting

The confirmation model is trained on train.parquet only and evaluated
against validation.parquet only.

Selected configuration
----------------------
    n_estimators      = 300
    learning_rate     = 0.05
    max_depth         = 6
    min_child_weight  = 1.0
    subsample         = 0.9
    colsample_bytree  = 0.9
    gamma             = 0.0
    reg_alpha         = 0.1
    reg_lambda        = 1.0

Established baseline
--------------------
    MAE  = 0.013767
    RMSE = 0.020167
    R2   = 0.994799
    MAPE = 3.4157%

Expected confirmation result
----------------------------
    MAE  approximately 0.013496
    RMSE approximately 0.019805
    R2   approximately 0.994984
    MAPE approximately 3.3279%

Important
---------
Small numerical differences can occur depending on environment,
XGBoost version, threading and execution conditions. The script therefore
uses explicit tolerances rather than requiring bit-for-bit equality.
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)

from app.ml.ml_models.xgboost_model import (
    XGBoostModel,
    XGBoostModelConfig,
)


# ============================================================================
# Configuration
# ============================================================================

TARGET_COLUMN = "target_occupancy_rate_30m"

EXPECTED_FEATURE_COUNT = 296

TRAINING_ROWS_EXPECTED = 23_244
VALIDATION_ROWS_EXPECTED = 4_980

# ---------------------------------------------------------------------------
# Established baseline
# ---------------------------------------------------------------------------

BASELINE_MAE = 0.013767
BASELINE_RMSE = 0.020167
BASELINE_R2 = 0.994799
BASELINE_MAPE = 3.4157

# ---------------------------------------------------------------------------
# TUNE_014 expected validation metrics
# ---------------------------------------------------------------------------

EXPECTED_MAE = 0.013496
EXPECTED_RMSE = 0.019805
EXPECTED_R2 = 0.994984
EXPECTED_MAPE = 3.3279

# ---------------------------------------------------------------------------
# Numerical confirmation tolerances.
#
# These are intentionally tight enough to catch an unexpected model
# configuration while allowing small numerical/environment differences.
# ---------------------------------------------------------------------------

MAE_TOLERANCE = 0.00010
RMSE_TOLERANCE = 0.00010
R2_TOLERANCE = 0.00010
MAPE_TOLERANCE = 0.05

# ---------------------------------------------------------------------------
# Repository paths
# ---------------------------------------------------------------------------

SCRIPT_PATH = Path(__file__).resolve()

# backend/
BACKEND_ROOT = SCRIPT_PATH.parent

# smart-parking-system/
REPOSITORY_ROOT = BACKEND_ROOT.parent

DATASET_ROOT = (
    REPOSITORY_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
)

TARGET_DATASET_ROOT = (
    DATASET_ROOT
    / "target_occupancy_rate_30m"
)

TRAIN_PATH = (
    TARGET_DATASET_ROOT
    / "train.parquet"
)

VALIDATION_PATH = (
    TARGET_DATASET_ROOT
    / "validation.parquet"
)

# IMPORTANT:
# This path is displayed and validated for existence, but the file is
# deliberately NEVER loaded.
TEST_PATH = (
    TARGET_DATASET_ROOT
    / "test.parquet"
)

MANIFEST_PATH = (
    DATASET_ROOT
    / "training_dataset_manifest.json"
)

OUTPUT_DIR = (
    DATASET_ROOT
    / "xgboost_selected_model_confirmation"
)

JSON_OUTPUT = (
    OUTPUT_DIR
    / "birmingham_xgboost_selected_model_confirmation.json"
)

CSV_OUTPUT = (
    OUTPUT_DIR
    / "birmingham_xgboost_selected_model_confirmation.csv"
)


# ============================================================================
# Selected model configuration
# ============================================================================

SELECTED_CANDIDATE_ID = "TUNE_014"

SELECTED_DESCRIPTION = (
    "Higher L1 regularisation"
)


SELECTED_PARAMETERS: dict[str, Any] = {
    "n_estimators": 300,
    "learning_rate": 0.05,
    "max_depth": 6,
    "min_child_weight": 1.0,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "gamma": 0.0,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
}


# ============================================================================
# Dataclasses
# ============================================================================

@dataclass
class Metrics:
    mae: float
    rmse: float
    r2: float
    mape: float
    n: int


@dataclass
class ConfirmationResult:
    candidate_id: str
    description: str
    parameters: dict[str, Any]

    training_rows: int
    validation_rows: int
    feature_count: int

    baseline: Metrics
    confirmation: Metrics

    mae_change: float
    mae_improvement_pct: float

    rmse_change: float
    rmse_improvement_pct: float

    r2_change: float
    r2_improvement_pct: float

    mape_change: float
    mape_improvement_pct: float

    expected_mae: float
    expected_rmse: float
    expected_r2: float
    expected_mape: float

    expected_metrics_within_tolerance: bool
    confirmation_better_than_baseline_mae: bool
    confirmation_better_than_baseline_rmse: bool
    confirmation_better_than_baseline_r2: bool
    confirmation_better_than_baseline_mape: bool

    test_dataset_loaded: bool
    validation_passed_to_fit: bool
    feature_pipeline_rebuilt: bool
    hyperparameter_tuning_performed: bool
    persisted_datasets_modified: bool

    execution_seconds: float

    verdict: str


# ============================================================================
# Utility functions
# ============================================================================

def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_field(label: str, value: Any) -> None:
    print(f"{label:<44}: {value}")


def assert_condition(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


def ensure_finite(
    name: str,
    value: float,
) -> float:

    value = float(value)

    if not math.isfinite(value):
        raise ValueError(
            f"{name} is not finite: {value}"
        )

    return value


def calculate_mape(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> float:
    """
    Calculate MAPE while excluding zero actual values.

    This follows the same practical definition used by the tuning
    confirmation experiment.
    """

    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    y_pred = np.asarray(
        y_pred,
        dtype=float,
    )

    non_zero = (
        np.abs(y_true) > 1e-12
    )

    if not np.any(non_zero):
        return float("nan")

    percentage_errors = (
        np.abs(
            (
                y_true[non_zero]
                - y_pred[non_zero]
            )
            / y_true[non_zero]
        )
        * 100.0
    )

    return float(
        np.mean(
            percentage_errors
        )
    )


def calculate_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> Metrics:

    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    y_pred = np.asarray(
        y_pred,
        dtype=float,
    )

    if len(y_true) != len(y_pred):
        raise ValueError(
            "Prediction/target length mismatch: "
            f"{len(y_true)} != {len(y_pred)}"
        )

    if not np.isfinite(y_pred).all():
        raise ValueError(
            "Model predictions contain "
            "non-finite values."
        )

    mae = ensure_finite(
        "MAE",
        mean_absolute_error(
            y_true,
            y_pred,
        ),
    )

    rmse = ensure_finite(
        "RMSE",
        np.sqrt(
            mean_squared_error(
                y_true,
                y_pred,
            )
        ),
    )

    r2 = ensure_finite(
        "R2",
        r2_score(
            y_true,
            y_pred,
        ),
    )

    mape = ensure_finite(
        "MAPE",
        calculate_mape(
            y_true,
            y_pred,
        ),
    )

    return Metrics(
        mae=mae,
        rmse=rmse,
        r2=r2,
        mape=mape,
        n=len(y_true),
    )


def improvement_percentage(
    baseline: float,
    current: float,
    *,
    lower_is_better: bool,
) -> float:

    if baseline == 0:
        return 0.0

    if lower_is_better:
        improvement = (
            baseline - current
        )
    else:
        improvement = (
            current - baseline
        )

    return float(
        (improvement / baseline)
        * 100.0
    )


def metric_change(
    baseline: float,
    current: float,
) -> float:
    return float(
        current - baseline
    )


# ============================================================================
# Repository / dataset validation
# ============================================================================

def validate_paths() -> None:

    print("--- DATASET FILE VALIDATION ---")

    print_field(
        "Processed dataset root",
        str(DATASET_ROOT),
    )

    print_field(
        "Training dataset",
        str(TRAIN_PATH),
    )

    print_field(
        "Validation dataset",
        str(VALIDATION_PATH),
    )

    print_field(
        "Test dataset",
        str(TEST_PATH),
    )

    print_field(
        "Feature manifest",
        str(MANIFEST_PATH),
    )

    print_field(
        "Training file exists",
        "PASS"
        if TRAIN_PATH.exists()
        else "FAIL",
    )

    print_field(
        "Validation file exists",
        "PASS"
        if VALIDATION_PATH.exists()
        else "FAIL",
    )

    print_field(
        "Test file exists",
        "PASS"
        if TEST_PATH.exists()
        else "FAIL",
    )

    print_field(
        "Feature manifest exists",
        "PASS"
        if MANIFEST_PATH.exists()
        else "FAIL",
    )

    assert_condition(
        TRAIN_PATH.is_file(),
        f"Training dataset does not exist: {TRAIN_PATH}",
    )

    assert_condition(
        VALIDATION_PATH.is_file(),
        f"Validation dataset does not exist: "
        f"{VALIDATION_PATH}",
    )

    assert_condition(
        TEST_PATH.is_file(),
        f"Test dataset does not exist: {TEST_PATH}",
    )

    assert_condition(
        MANIFEST_PATH.is_file(),
        f"Feature manifest does not exist: "
        f"{MANIFEST_PATH}",
    )

    print()
    print(
        "IMPORTANT: test.parquet exists but will NOT "
        "be loaded."
    )


# ============================================================================
# Feature manifest
# ============================================================================

def load_feature_manifest() -> list[str]:

    print()
    print("--- LOADING FEATURE MANIFEST ---")

    with MANIFEST_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:

        manifest = json.load(
            handle
        )

    feature_columns = manifest.get(
        "feature_columns",
        [],
    )

    if not isinstance(
        feature_columns,
        list,
    ):
        raise ValueError(
            "Manifest feature_columns is not a list."
        )

    feature_columns = [
        str(column)
        for column in feature_columns
    ]

    print_field(
        "Manifest",
        str(MANIFEST_PATH),
    )

    print_field(
        "Registered features",
        len(feature_columns),
    )

    assert_condition(
        len(feature_columns)
        == EXPECTED_FEATURE_COUNT,
        "Expected exactly "
        f"{EXPECTED_FEATURE_COUNT} "
        "registered features, found "
        f"{len(feature_columns)}.",
    )

    assert_condition(
        len(feature_columns)
        == len(set(feature_columns)),
        "Feature manifest contains duplicate "
        "feature names.",
    )

    assert_condition(
        TARGET_COLUMN
        not in feature_columns,
        "Target column is incorrectly included "
        "in registered features.",
    )

    return feature_columns


# ============================================================================
# Dataset loading
# ============================================================================

def load_dataset(
    path: Path,
    description: str,
) -> pd.DataFrame:

    print()
    print(
        f"--- LOADING {description.upper()} DATASET ---"
    )

    dataframe = pd.read_parquet(
        path
    )

    print_field(
        f"{description} rows",
        len(dataframe),
    )

    print_field(
        f"{description} columns",
        len(dataframe.columns),
    )

    return dataframe


# ============================================================================
# Feature contract validation
# ============================================================================

def validate_feature_contract(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    feature_columns: list[str],
) -> None:

    print()
    print("--- FEATURE CONTRACT VALIDATION ---")

    train_features = [
        column
        for column in feature_columns
        if column in train.columns
    ]

    validation_features = [
        column
        for column in feature_columns
        if column in validation.columns
    ]

    train_missing = sorted(
        set(feature_columns)
        - set(train.columns)
    )

    validation_missing = sorted(
        set(feature_columns)
        - set(validation.columns)
    )

    train_extra_model_features = sorted(
        set(train_features)
        - set(feature_columns)
    )

    validation_extra_model_features = sorted(
        set(validation_features)
        - set(feature_columns)
    )

    print_field(
        "Registered features",
        len(feature_columns),
    )

    print_field(
        "Training feature registry",
        "PASS"
        if not train_missing
        else f"FAIL: {train_missing}",
    )

    print_field(
        "Validation feature registry",
        "PASS"
        if not validation_missing
        else f"FAIL: {validation_missing}",
    )

    print_field(
        "Train/validation feature registry",
        "IDENTICAL"
        if train_features == validation_features
        else "FAIL",
    )

    print_field(
        "Duplicate feature names",
        len(feature_columns)
        - len(set(feature_columns)),
    )

    print_field(
        "Categorical features delegated to model",
        "occupancy_level, demand_class",
    )

    assert_condition(
        not train_missing,
        "Training dataset is missing registered "
        f"features: {train_missing}",
    )

    assert_condition(
        not validation_missing,
        "Validation dataset is missing registered "
        f"features: {validation_missing}",
    )

    assert_condition(
        train_features == validation_features,
        "Training and validation feature registries "
        "are not identical.",
    )

    assert_condition(
        not train_extra_model_features,
        "Unexpected additional model features "
        f"in training dataset: "
        f"{train_extra_model_features}",
    )

    assert_condition(
        not validation_extra_model_features,
        "Unexpected additional model features "
        f"in validation dataset: "
        f"{validation_extra_model_features}",
    )

    assert_condition(
        TARGET_COLUMN not in feature_columns,
        "Target column appears in feature registry.",
    )


# ============================================================================
# Target validation
# ============================================================================

def validate_target_contract(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    print()
    print("--- TARGET CONTRACT VALIDATION ---")

    assert_condition(
        TARGET_COLUMN in train.columns,
        f"Training dataset does not contain "
        f"target '{TARGET_COLUMN}'.",
    )

    assert_condition(
        TARGET_COLUMN in validation.columns,
        f"Validation dataset does not contain "
        f"target '{TARGET_COLUMN}'.",
    )

    y_train = pd.to_numeric(
        train[TARGET_COLUMN],
        errors="coerce",
    )

    y_validation = pd.to_numeric(
        validation[TARGET_COLUMN],
        errors="coerce",
    )

    train_nulls = int(
        y_train.isna().sum()
    )

    validation_nulls = int(
        y_validation.isna().sum()
    )

    print_field(
        "Training target rows",
        len(y_train),
    )

    print_field(
        "Validation target rows",
        len(y_validation),
    )

    print_field(
        "Training target nulls",
        train_nulls,
    )

    print_field(
        "Validation target nulls",
        validation_nulls,
    )

    print_field(
        "Training target mean",
        f"{y_train.mean():.6f}",
    )

    print_field(
        "Validation target mean",
        f"{y_validation.mean():.6f}",
    )

    print_field(
        "Training target range",
        f"{y_train.min():.6f} -> "
        f"{y_train.max():.6f}",
    )

    print_field(
        "Validation target range",
        f"{y_validation.min():.6f} -> "
        f"{y_validation.max():.6f}",
    )

    print_field(
        "Target range validation",
        "PASS"
        if (
            y_train.between(0.0, 1.0).all()
            and y_validation.between(
                0.0,
                1.0,
            ).all()
        )
        else "FAIL",
    )

    assert_condition(
        train_nulls == 0,
        "Training target contains null values.",
    )

    assert_condition(
        validation_nulls == 0,
        "Validation target contains null values.",
    )

    assert_condition(
        y_train.between(
            0.0,
            1.0,
        ).all(),
        "Training target contains values "
        "outside [0, 1].",
    )

    assert_condition(
        y_validation.between(
            0.0,
            1.0,
        ).all(),
        "Validation target contains values "
        "outside [0, 1].",
    )


# ============================================================================
# Chronological validation
# ============================================================================

def find_timestamp_column(
    dataframe: pd.DataFrame,
) -> str | None:

    candidates = [
        "normalized_at",
        "timestamp",
        "event_timestamp",
        "observation_timestamp",
        "datetime",
        "date_time",
    ]

    for candidate in candidates:

        if candidate in dataframe.columns:
            return candidate

    return None


def validate_chronological_split(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    print()
    print("--- CHRONOLOGICAL SPLIT VALIDATION ---")

    train_timestamp_column = (
        find_timestamp_column(train)
    )

    validation_timestamp_column = (
        find_timestamp_column(validation)
    )

    if (
        train_timestamp_column is None
        or validation_timestamp_column is None
    ):
        print_field(
            "Timestamp validation",
            "NOT AVAILABLE",
        )

        return

    train_timestamps = pd.to_datetime(
        train[
            train_timestamp_column
        ],
        errors="coerce",
    )

    validation_timestamps = pd.to_datetime(
        validation[
            validation_timestamp_column
        ],
        errors="coerce",
    )

    assert_condition(
        not train_timestamps.isna().any(),
        "Training timestamps contain invalid values.",
    )

    assert_condition(
        not validation_timestamps.isna().any(),
        "Validation timestamps contain invalid values.",
    )

    train_start = train_timestamps.min()
    train_end = train_timestamps.max()

    validation_start = validation_timestamps.min()
    validation_end = validation_timestamps.max()

    print_field(
        "Training start",
        train_start,
    )

    print_field(
        "Training end",
        train_end,
    )

    print_field(
        "Validation start",
        validation_start,
    )

    print_field(
        "Validation end",
        validation_end,
    )

    chronological = (
        train_end <= validation_start
    )

    print_field(
        "Chronological ordering",
        "PASS"
        if chronological
        else "FAIL",
    )

    assert_condition(
        chronological,
        "Training and validation datasets are not "
        "chronologically ordered.",
    )


# ============================================================================
# Observation isolation
# ============================================================================

def validate_observation_isolation(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    print()
    print("--- TRAIN / VALIDATION OBSERVATION ISOLATION ---")

    timestamp_column_train = (
        find_timestamp_column(train)
    )

    timestamp_column_validation = (
        find_timestamp_column(validation)
    )

    facility_candidates = [
        "source_facility_code",
        "facility_code",
        "facility_id",
        "car_park_id",
    ]

    facility_column_train = next(
        (
            column
            for column in facility_candidates
            if column in train.columns
        ),
        None,
    )

    facility_column_validation = next(
        (
            column
            for column in facility_candidates
            if column in validation.columns
        ),
        None,
    )

    if (
        timestamp_column_train is None
        or timestamp_column_validation is None
        or facility_column_train is None
        or facility_column_validation is None
    ):
        print_field(
            "Observation isolation",
            "NOT AVAILABLE",
        )

        return

    train_keys = pd.MultiIndex.from_arrays(
        [
            train[
                facility_column_train
            ].astype(str),
            pd.to_datetime(
                train[
                    timestamp_column_train
                ]
            ),
        ],
        names=[
            "facility",
            "timestamp",
        ],
    )

    validation_keys = pd.MultiIndex.from_arrays(
        [
            validation[
                facility_column_validation
            ].astype(str),
            pd.to_datetime(
                validation[
                    timestamp_column_validation
                ]
            ),
        ],
        names=[
            "facility",
            "timestamp",
        ],
    )

    overlap = train_keys.intersection(
        validation_keys
    )

    print_field(
        "Training observations",
        len(train),
    )

    print_field(
        "Validation observations",
        len(validation),
    )

    print_field(
        "Train ∩ Validation",
        len(overlap),
    )

    print_field(
        "Observation isolation",
        "PASS"
        if len(overlap) == 0
        else "FAIL",
    )

    assert_condition(
        len(overlap) == 0,
        "Training and validation contain overlapping "
        "facility/timestamp observations.",
    )


# ============================================================================
# Model configuration
# ============================================================================

def build_selected_model() -> XGBoostModel:

    print()
    print("--- BUILDING SELECTED XGBOOST MODEL ---")

    print_field(
        "Candidate",
        SELECTED_CANDIDATE_ID,
    )

    print_field(
        "Description",
        SELECTED_DESCRIPTION,
    )

    for parameter, value in SELECTED_PARAMETERS.items():
        print_field(
            parameter,
            value,
        )

    # ------------------------------------------------------------------------
    # IMPORTANT
    #
    # We deliberately construct the model directly from TUNE_014.
    # No tuning occurs in this script.
    #
    # XGBoostModelConfig may contain additional project-specific defaults.
    # We override only the parameters selected during tuning.
    # ------------------------------------------------------------------------

    config = XGBoostModelConfig(
        n_estimators=SELECTED_PARAMETERS[
            "n_estimators"
        ],
        learning_rate=SELECTED_PARAMETERS[
            "learning_rate"
        ],
        max_depth=SELECTED_PARAMETERS[
            "max_depth"
        ],
        min_child_weight=SELECTED_PARAMETERS[
            "min_child_weight"
        ],
        subsample=SELECTED_PARAMETERS[
            "subsample"
        ],
        colsample_bytree=SELECTED_PARAMETERS[
            "colsample_bytree"
        ],
        gamma=SELECTED_PARAMETERS[
            "gamma"
        ],
        reg_alpha=SELECTED_PARAMETERS[
            "reg_alpha"
        ],
        reg_lambda=SELECTED_PARAMETERS[
            "reg_lambda"
        ],
    )

    model = XGBoostModel(
        target_column=TARGET_COLUMN,
        config=config,
        model_name=(
            "xgboost_birmingham_tune_014_confirmation"
        ),
    )

    return model


# ============================================================================
# Matrix preparation
# ============================================================================

def prepare_model_matrices(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[
    pd.DataFrame,
    pd.Series,
    pd.DataFrame,
    pd.Series,
]:
    """
    Prepare raw feature matrices for the selected XGBoost model.

    IMPORTANT:
        - Do NOT call XGBoostModel._prepare_model_matrix().
        - Do NOT manually encode categorical features.
        - XGBoostModel.fit() owns categorical mapping/encoding.
        - Only registered model features are returned.
    """

    print()
    print("--- PREPARING MODEL MATRICES ---")

    X_train = train[feature_columns].copy()

    X_validation = validation[feature_columns].copy()

    y_train = pd.to_numeric(
        train[TARGET_COLUMN],
        errors="raise",
    )

    y_validation = pd.to_numeric(
        validation[TARGET_COLUMN],
        errors="raise",
    )

    print_field(
        "Registered features",
        len(feature_columns),
    )

    print_field(
        "Training matrix shape",
        X_train.shape,
    )

    print_field(
        "Validation matrix shape",
        X_validation.shape,
    )

    print_field(
        "Training target shape",
        y_train.shape,
    )

    print_field(
        "Validation target shape",
        y_validation.shape,
    )

    assert_condition(
        X_train.shape[1] == EXPECTED_FEATURE_COUNT,
        "Training matrix does not contain exactly "
        f"{EXPECTED_FEATURE_COUNT} features.",
    )

    assert_condition(
        X_validation.shape[1] == EXPECTED_FEATURE_COUNT,
        "Validation matrix does not contain exactly "
        f"{EXPECTED_FEATURE_COUNT} features.",
    )

    assert_condition(
        X_train.shape[0] == len(y_train),
        "Training feature/target row count mismatch.",
    )

    assert_condition(
        X_validation.shape[0] == len(y_validation),
        "Validation feature/target row count mismatch.",
    )

    # Explicitly verify that train and validation have identical
    # feature ordering.
    assert_condition(
        list(X_train.columns) == list(X_validation.columns),
        "Training and validation feature ordering differs.",
    )

    print_field(
        "Feature/target separation",
        "PASS",
    )

    print_field(
        "Feature ordering",
        "IDENTICAL",
    )

    print_field(
        "Categorical preprocessing",
        "DELEGATED TO XGBoostModel.fit()",
    )

    return (
        X_train,
        y_train,
        X_validation,
        y_validation,
    )


# ============================================================================
# Model training
# ============================================================================

def train_selected_model(
    model: XGBoostModel,
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> float:

    print()
    print("--- TRAINING SELECTED MODEL ---")

    print(
        "Validation passed to fit()                : NO"
    )

    print(
        "Test data loaded                          : NO"
    )

    print()
    print("Training XGBoost...")

    start = time.perf_counter()

    # IMPORTANT:
    # Only training data enters fit().
    model.fit(
        X_train,
        y_train,
    )

    elapsed = (
        time.perf_counter()
        - start
    )

    print(
        f"Training completed in {elapsed:.2f} seconds."
    )

    return elapsed


# ============================================================================
# Validation evaluation
# ============================================================================

def evaluate_validation(
    model: XGBoostModel,
    X_validation: pd.DataFrame,
    y_validation: pd.Series,
) -> tuple[np.ndarray, Metrics]:

    print()
    print(
        "--- GENERATING VALIDATION PREDICTIONS ---"
    )

    predictions = model.predict(
        X_validation
    )

    predictions = np.asarray(
        predictions,
        dtype=float,
    )

    if len(predictions) != len(y_validation):
        raise ValueError(
            "Validation prediction count does not "
            "match validation target count."
        )

    if not np.isfinite(predictions).all():
        raise ValueError(
            "Validation predictions contain "
            "non-finite values."
        )

    metrics = calculate_metrics(
        y_validation.to_numpy(
            dtype=float
        ),
        predictions,
    )

    print()
    print("Validation metrics:")

    print(
        f"  MAE :  {metrics.mae:.6f}"
    )

    print(
        f"  RMSE:  {metrics.rmse:.6f}"
    )

    print(
        f"  R²  :  {metrics.r2:.6f}"
    )

    print(
        f"  MAPE:  {metrics.mape:.4f}%"
    )

    print(
        f"  N   :  {metrics.n}"
    )

    return (
        predictions,
        metrics,
    )


# ============================================================================
# Confirmation comparison
# ============================================================================

def compare_with_baseline(
    metrics: Metrics,
) -> ConfirmationResult:

    print()
    print("--- CONFIRMATION VS ESTABLISHED BASELINE ---")

    mae_change = metric_change(
        BASELINE_MAE,
        metrics.mae,
    )

    rmse_change = metric_change(
        BASELINE_RMSE,
        metrics.rmse,
    )

    r2_change = metric_change(
        BASELINE_R2,
        metrics.r2,
    )

    mape_change = metric_change(
        BASELINE_MAPE,
        metrics.mape,
    )

    mae_improvement_pct = (
        improvement_percentage(
            BASELINE_MAE,
            metrics.mae,
            lower_is_better=True,
        )
    )

    rmse_improvement_pct = (
        improvement_percentage(
            BASELINE_RMSE,
            metrics.rmse,
            lower_is_better=True,
        )
    )

    r2_improvement_pct = (
        improvement_percentage(
            BASELINE_R2,
            metrics.r2,
            lower_is_better=False,
        )
    )

    mape_improvement_pct = (
        improvement_percentage(
            BASELINE_MAPE,
            metrics.mape,
            lower_is_better=True,
        )
    )

    print()
    print(
        f"Baseline MAE                              : "
        f"{BASELINE_MAE:.6f}"
    )

    print(
        f"Confirmation MAE                         : "
        f"{metrics.mae:.6f}"
    )

    print(
        f"MAE change                               : "
        f"{mae_change:+.6f}"
    )

    print(
        f"MAE improvement %                       : "
        f"{mae_improvement_pct:+.2f}%"
    )

    print(
        f"Baseline RMSE                            : "
        f"{BASELINE_RMSE:.6f}"
    )

    print(
        f"Confirmation RMSE                       : "
        f"{metrics.rmse:.6f}"
    )

    print(
        f"RMSE change                              : "
        f"{rmse_change:+.6f}"
    )

    print(
        f"RMSE improvement %                      : "
        f"{rmse_improvement_pct:+.2f}%"
    )

    print(
        f"Baseline R²                              : "
        f"{BASELINE_R2:.6f}"
    )

    print(
        f"Confirmation R²                         : "
        f"{metrics.r2:.6f}"
    )

    print(
        f"R² change                                : "
        f"{r2_change:+.6f}"
    )

    print(
        f"R² improvement %                        : "
        f"{r2_improvement_pct:+.2f}%"
    )

    print(
        f"Baseline MAPE                            : "
        f"{BASELINE_MAPE:.4f}%"
    )

    print(
        f"Confirmation MAPE                       : "
        f"{metrics.mape:.4f}%"
    )

    print(
        f"MAPE change                              : "
        f"{mape_change:+.4f}"
    )

    print(
        f"MAPE improvement %                      : "
        f"{mape_improvement_pct:+.2f}%"
    )

    expected_metrics_within_tolerance = (
        abs(metrics.mae - EXPECTED_MAE)
        <= MAE_TOLERANCE
        and
        abs(metrics.rmse - EXPECTED_RMSE)
        <= RMSE_TOLERANCE
        and
        abs(metrics.r2 - EXPECTED_R2)
        <= R2_TOLERANCE
        and
        abs(metrics.mape - EXPECTED_MAPE)
        <= MAPE_TOLERANCE
    )

    confirmation_better_than_baseline_mae = (
        metrics.mae < BASELINE_MAE
    )

    confirmation_better_than_baseline_rmse = (
        metrics.rmse < BASELINE_RMSE
    )

    confirmation_better_than_baseline_r2 = (
        metrics.r2 > BASELINE_R2
    )

    confirmation_better_than_baseline_mape = (
        metrics.mape < BASELINE_MAPE
    )

    print()
    print(
        "Expected TUNE_014 metrics tolerance check:"
    )

    print(
        "  MAE within tolerance                  : "
        f"{'PASS' if abs(metrics.mae - EXPECTED_MAE) <= MAE_TOLERANCE else 'FAIL'}"
    )

    print(
        "  RMSE within tolerance                 : "
        f"{'PASS' if abs(metrics.rmse - EXPECTED_RMSE) <= RMSE_TOLERANCE else 'FAIL'}"
    )

    print(
        "  R² within tolerance                   : "
        f"{'PASS' if abs(metrics.r2 - EXPECTED_R2) <= R2_TOLERANCE else 'FAIL'}"
    )

    print(
        "  MAPE within tolerance                 : "
        f"{'PASS' if abs(metrics.mape - EXPECTED_MAPE) <= MAPE_TOLERANCE else 'FAIL'}"
    )

    return ConfirmationResult(
        candidate_id=SELECTED_CANDIDATE_ID,
        description=SELECTED_DESCRIPTION,
        parameters=SELECTED_PARAMETERS.copy(),

        training_rows=TRAINING_ROWS_EXPECTED,
        validation_rows=VALIDATION_ROWS_EXPECTED,
        feature_count=EXPECTED_FEATURE_COUNT,

        baseline=Metrics(
            mae=BASELINE_MAE,
            rmse=BASELINE_RMSE,
            r2=BASELINE_R2,
            mape=BASELINE_MAPE,
            n=VALIDATION_ROWS_EXPECTED,
        ),

        confirmation=metrics,

        mae_change=mae_change,
        mae_improvement_pct=mae_improvement_pct,

        rmse_change=rmse_change,
        rmse_improvement_pct=rmse_improvement_pct,

        r2_change=r2_change,
        r2_improvement_pct=r2_improvement_pct,

        mape_change=mape_change,
        mape_improvement_pct=mape_improvement_pct,

        expected_mae=EXPECTED_MAE,
        expected_rmse=EXPECTED_RMSE,
        expected_r2=EXPECTED_R2,
        expected_mape=EXPECTED_MAPE,

        expected_metrics_within_tolerance=(
            expected_metrics_within_tolerance
        ),

        confirmation_better_than_baseline_mae=(
            confirmation_better_than_baseline_mae
        ),

        confirmation_better_than_baseline_rmse=(
            confirmation_better_than_baseline_rmse
        ),

        confirmation_better_than_baseline_r2=(
            confirmation_better_than_baseline_r2
        ),

        confirmation_better_than_baseline_mape=(
            confirmation_better_than_baseline_mape
        ),

        test_dataset_loaded=False,
        validation_passed_to_fit=False,
        feature_pipeline_rebuilt=False,
        hyperparameter_tuning_performed=False,
        persisted_datasets_modified=False,

        execution_seconds=0.0,

        verdict="PENDING",
    )


# ============================================================================
# Persistence
# ============================================================================

def persist_results(
    result: ConfirmationResult,
) -> None:

    print()
    print("--- PERSISTING CONFIRMATION RESULTS ---")

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "audit": {
            "audit_name": (
                "Birmingham XGBoost "
                "Selected Model Confirmation"
            ),
            "target": TARGET_COLUMN,
            "candidate_id": (
                SELECTED_CANDIDATE_ID
            ),
            "description": (
                SELECTED_DESCRIPTION
            ),
            "prediction_contract": {
                "prediction_timestamp": "T",
                "forecast_horizon": (
                    "T + 30 minutes"
                ),
                "feature_information": (
                    "available at or before T"
                ),
            },
            "generated_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
        },

        "selected_parameters": (
            SELECTED_PARAMETERS
        ),

        "baseline": asdict(
            result.baseline
        ),

        "confirmation": asdict(
            result.confirmation
        ),

        "comparison": {
            "mae_change": (
                result.mae_change
            ),
            "mae_improvement_pct": (
                result.mae_improvement_pct
            ),
            "rmse_change": (
                result.rmse_change
            ),
            "rmse_improvement_pct": (
                result.rmse_improvement_pct
            ),
            "r2_change": (
                result.r2_change
            ),
            "r2_improvement_pct": (
                result.r2_improvement_pct
            ),
            "mape_change": (
                result.mape_change
            ),
            "mape_improvement_pct": (
                result.mape_improvement_pct
            ),
        },

        "expected_metrics": {
            "mae": EXPECTED_MAE,
            "rmse": EXPECTED_RMSE,
            "r2": EXPECTED_R2,
            "mape": EXPECTED_MAPE,
        },

        "verification": {
            "expected_metrics_within_tolerance": (
                result.expected_metrics_within_tolerance
            ),
            "better_than_baseline_mae": (
                result.confirmation_better_than_baseline_mae
            ),
            "better_than_baseline_rmse": (
                result.confirmation_better_than_baseline_rmse
            ),
            "better_than_baseline_r2": (
                result.confirmation_better_than_baseline_r2
            ),
            "better_than_baseline_mape": (
                result.confirmation_better_than_baseline_mape
            ),
        },

        "experiment_controls": {
            "validation_passed_to_fit": False,
            "test_dataset_loaded": False,
            "test_dataset_passed_to_fit": False,
            "feature_pipeline_rebuilt": False,
            "hyperparameter_tuning_performed": False,
            "persisted_datasets_modified": False,
            "early_stopping": False,
        },

        "result": {
            "verdict": result.verdict,
            "execution_seconds": (
                result.execution_seconds
            ),
        },
    }

    with JSON_OUTPUT.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            payload,
            handle,
            indent=2,
            default=str,
        )

    csv_row = {
        "candidate_id": (
            result.candidate_id
        ),
        "description": (
            result.description
        ),
        "feature_count": (
            result.feature_count
        ),
        "training_rows": (
            result.training_rows
        ),
        "validation_rows": (
            result.validation_rows
        ),

        "n_estimators": (
            SELECTED_PARAMETERS[
                "n_estimators"
            ]
        ),
        "learning_rate": (
            SELECTED_PARAMETERS[
                "learning_rate"
            ]
        ),
        "max_depth": (
            SELECTED_PARAMETERS[
                "max_depth"
            ]
        ),
        "min_child_weight": (
            SELECTED_PARAMETERS[
                "min_child_weight"
            ]
        ),
        "subsample": (
            SELECTED_PARAMETERS[
                "subsample"
            ]
        ),
        "colsample_bytree": (
            SELECTED_PARAMETERS[
                "colsample_bytree"
            ]
        ),
        "gamma": (
            SELECTED_PARAMETERS[
                "gamma"
            ]
        ),
        "reg_alpha": (
            SELECTED_PARAMETERS[
                "reg_alpha"
            ]
        ),
        "reg_lambda": (
            SELECTED_PARAMETERS[
                "reg_lambda"
            ]
        ),

        "baseline_mae": (
            result.baseline.mae
        ),
        "confirmation_mae": (
            result.confirmation.mae
        ),
        "mae_change": (
            result.mae_change
        ),
        "mae_improvement_pct": (
            result.mae_improvement_pct
        ),

        "baseline_rmse": (
            result.baseline.rmse
        ),
        "confirmation_rmse": (
            result.confirmation.rmse
        ),
        "rmse_change": (
            result.rmse_change
        ),
        "rmse_improvement_pct": (
            result.rmse_improvement_pct
        ),

        "baseline_r2": (
            result.baseline.r2
        ),
        "confirmation_r2": (
            result.confirmation.r2
        ),
        "r2_change": (
            result.r2_change
        ),
        "r2_improvement_pct": (
            result.r2_improvement_pct
        ),

        "baseline_mape": (
            result.baseline.mape
        ),
        "confirmation_mape": (
            result.confirmation.mape
        ),
        "mape_change": (
            result.mape_change
        ),
        "mape_improvement_pct": (
            result.mape_improvement_pct
        ),

        "expected_metrics_within_tolerance": (
            result.expected_metrics_within_tolerance
        ),

        "test_dataset_loaded": (
            result.test_dataset_loaded
        ),
        "validation_passed_to_fit": (
            result.validation_passed_to_fit
        ),
        "feature_pipeline_rebuilt": (
            result.feature_pipeline_rebuilt
        ),
        "hyperparameter_tuning_performed": (
            result.hyperparameter_tuning_performed
        ),
        "persisted_datasets_modified": (
            result.persisted_datasets_modified
        ),

        "execution_seconds": (
            result.execution_seconds
        ),

        "verdict": result.verdict,
    }

    pd.DataFrame(
        [csv_row]
    ).to_csv(
        CSV_OUTPUT,
        index=False,
    )

    print_field(
        "Output directory",
        str(OUTPUT_DIR),
    )

    print_field(
        "JSON report",
        str(JSON_OUTPUT),
    )

    print_field(
        "CSV confirmation",
        str(CSV_OUTPUT),
    )


# ============================================================================
# Final assertions
# ============================================================================

def run_final_assertions(
    result: ConfirmationResult,
) -> None:

    print()
    print("--- FINAL ASSERTIONS ---")

    assertions = [
        (
            "Expected feature count = 296",
            result.feature_count
            == EXPECTED_FEATURE_COUNT,
        ),
        (
            "Training row count correct",
            result.training_rows
            == TRAINING_ROWS_EXPECTED,
        ),
        (
            "Validation row count correct",
            result.validation_rows
            == VALIDATION_ROWS_EXPECTED,
        ),
        (
            "Validation data never passed to fit()",
            result.validation_passed_to_fit
            is False,
        ),
        (
            "Test dataset never loaded",
            result.test_dataset_loaded
            is False,
        ),
        (
            "Feature pipeline not rebuilt",
            result.feature_pipeline_rebuilt
            is False,
        ),
        (
            "Hyperparameter tuning not performed",
            result.hyperparameter_tuning_performed
            is False,
        ),
        (
            "Persisted datasets not modified",
            result.persisted_datasets_modified
            is False,
        ),
        (
            "Confirmation MAE finite",
            math.isfinite(
                result.confirmation.mae
            ),
        ),
        (
            "Confirmation RMSE finite",
            math.isfinite(
                result.confirmation.rmse
            ),
        ),
        (
            "Confirmation R² finite",
            math.isfinite(
                result.confirmation.r2
            ),
        ),
        (
            "Confirmation MAPE finite",
            math.isfinite(
                result.confirmation.mape
            ),
        ),
    ]

    for description, passed in assertions:

        print_field(
            description,
            "PASS"
            if passed
            else "FAIL",
        )

        assert_condition(
            passed,
            description,
        )

    # ------------------------------------------------------------------------
    # We require the selected model to beat the baseline on the primary
    # selection metric (MAE).
    # ------------------------------------------------------------------------

    print_field(
        "Confirmation improves MAE over baseline",
        "PASS"
        if result.confirmation_better_than_baseline_mae
        else "FAIL",
    )

    assert_condition(
        result.confirmation_better_than_baseline_mae,
        "TUNE_014 confirmation does not improve "
        "MAE over the established baseline.",
    )

    # ------------------------------------------------------------------------
    # The expected metrics check is a reproducibility diagnostic.
    # We treat a mismatch as a hard failure because this script is intended
    # to confirm that the exact selected configuration reproduces the tuning
    # result.
    # ------------------------------------------------------------------------

    print_field(
        "Confirmation metrics within expected tolerance",
        "PASS"
        if result.expected_metrics_within_tolerance
        else "FAIL",
    )

    assert_condition(
        result.expected_metrics_within_tolerance,
        "Confirmation metrics differ materially from "
        "the recorded TUNE_014 tuning result. "
        "Investigate model configuration, XGBoost version, "
        "randomness, or preprocessing before proceeding "
        "to test evaluation.",
    )

    print()
    print(
        "ALL SELECTED MODEL CONFIRMATION ASSERTIONS PASSED"
    )


# ============================================================================
# Main
# ============================================================================

def main() -> int:

    print_header(
        "SMARTPARK AI - "
        "BIRMINGHAM XGBOOST SELECTED MODEL "
        "CONFIRMATION"
    )

    print()
    print("Target:")
    print(
        f"  {TARGET_COLUMN}"
    )

    print()
    print("Selected model:")
    print(
        f"  Candidate              : "
        f"{SELECTED_CANDIDATE_ID}"
    )
    print(
        f"  Description            : "
        f"{SELECTED_DESCRIPTION}"
    )

    print()
    print("Experiment:")
    print(
        "  Confirm selected TUNE_014 configuration"
    )
    print(
        "  Train = train.parquet"
    )
    print(
        "  Evaluate = validation.parquet"
    )
    print(
        "  Test dataset untouched"
    )
    print(
        "  No hyperparameter tuning"
    )
    print(
        "  No feature pipeline rebuild"
    )
    print(
        "  No early stopping"
    )
    print(
        "  Validation data never passed to fit()"
    )

    print()
    print("Established baseline:")
    print(
        f"  MAE  = {BASELINE_MAE:.6f}"
    )
    print(
        f"  RMSE = {BASELINE_RMSE:.6f}"
    )
    print(
        f"  R²   = {BASELINE_R2:.6f}"
    )
    print(
        f"  MAPE = {BASELINE_MAPE:.4f}%"
    )

    start_time = time.perf_counter()

    try:

        # --------------------------------------------------------------------
        # 1. Validate files.
        # --------------------------------------------------------------------

        validate_paths()

        # --------------------------------------------------------------------
        # 2. Load manifest.
        # --------------------------------------------------------------------

        feature_columns = (
            load_feature_manifest()
        )

        # --------------------------------------------------------------------
        # 3. Load ONLY train and validation.
        #
        # test.parquet is intentionally never passed to read_parquet().
        # --------------------------------------------------------------------

        train = load_dataset(
            TRAIN_PATH,
            "Training",
        )

        validation = load_dataset(
            VALIDATION_PATH,
            "Validation",
        )

        assert_condition(
            len(train)
            == TRAINING_ROWS_EXPECTED,
            "Unexpected training row count: "
            f"{len(train)}",
        )

        assert_condition(
            len(validation)
            == VALIDATION_ROWS_EXPECTED,
            "Unexpected validation row count: "
            f"{len(validation)}",
        )

        # --------------------------------------------------------------------
        # 4. Feature contract.
        # --------------------------------------------------------------------

        validate_feature_contract(
            train,
            validation,
            feature_columns,
        )

        # --------------------------------------------------------------------
        # 5. Target contract.
        # --------------------------------------------------------------------

        validate_target_contract(
            train,
            validation,
        )

        # --------------------------------------------------------------------
        # 6. Chronological split.
        # --------------------------------------------------------------------

        validate_chronological_split(
            train,
            validation,
        )

        # --------------------------------------------------------------------
        # 7. Observation isolation.
        # --------------------------------------------------------------------

        validate_observation_isolation(
            train,
            validation,
        )

        # --------------------------------------------------------------------
        # 8. Build selected model.
        # --------------------------------------------------------------------

        model = build_selected_model()

        # --------------------------------------------------------------------
        # 9. Prepare matrices.
        # --------------------------------------------------------------------

        (
            X_train,
            y_train,
            X_validation,
            y_validation,
        ) = prepare_model_matrices(
            train,
            validation,
            feature_columns,
        )

        # --------------------------------------------------------------------
        # 10. Train ONLY on training data.
        # --------------------------------------------------------------------

        training_seconds = (
            train_selected_model(
                model,
                X_train,
                y_train,
            )
        )

        # --------------------------------------------------------------------
        # 11. Evaluate ONLY on validation.
        # --------------------------------------------------------------------

        (
            _predictions,
            confirmation_metrics,
        ) = evaluate_validation(
            model,
            X_validation,
            y_validation,
        )

        # --------------------------------------------------------------------
        # 12. Compare against baseline.
        # --------------------------------------------------------------------

        result = compare_with_baseline(
            confirmation_metrics
        )

        result.execution_seconds = (
            time.perf_counter()
            - start_time
        )

        result.verdict = (
            "CONFIRMED_SELECTED_MODEL"
        )

        # --------------------------------------------------------------------
        # 13. Persist.
        # --------------------------------------------------------------------

        persist_results(
            result
        )

        # --------------------------------------------------------------------
        # 14. Assertions.
        # --------------------------------------------------------------------

        run_final_assertions(
            result
        )

        print_header(
            "BIRMINGHAM XGBOOST SELECTED MODEL "
            "CONFIRMATION COMPLETED SUCCESSFULLY"
        )

        print()
        print(
            f"Target:              "
            f"{TARGET_COLUMN}"
        )

        print(
            f"Selected candidate:  "
            f"{SELECTED_CANDIDATE_ID}"
        )

        print(
            f"Features:             "
            f"{EXPECTED_FEATURE_COUNT}"
        )

        print(
            f"Training rows:        "
            f"{TRAINING_ROWS_EXPECTED}"
        )

        print(
            f"Validation rows:      "
            f"{VALIDATION_ROWS_EXPECTED}"
        )

        print()
        print("Confirmed validation metrics:")

        print(
            f"  MAE  = "
            f"{confirmation_metrics.mae:.6f}"
        )

        print(
            f"  RMSE = "
            f"{confirmation_metrics.rmse:.6f}"
        )

        print(
            f"  R²   = "
            f"{confirmation_metrics.r2:.6f}"
        )

        print(
            f"  MAPE = "
            f"{confirmation_metrics.mape:.4f}%"
        )

        print()
        print(
            f"Training time:       "
            f"{training_seconds:.2f} seconds"
        )

        print()
        print(
            "Test dataset used:       NO"
        )

        print(
            "Validation used for fit: NO"
        )

        print(
            "Hyperparameter tuning:   NO"
        )

        print(
            "Feature pipeline rebuilt: NO"
        )

        print(
            "Persisted datasets modified: NO"
        )

        print()
        print(
            "SELECTED XGBOOST MODEL IS CONFIRMED"
        )

        print()
        print(
            "IMPORTANT:"
        )

        print(
            "The selected model is now eligible for "
            "final untouched test evaluation."
        )

        return 0

    except KeyboardInterrupt:

        print()
        print(
            "Confirmation interrupted by user."
        )

        return 130

    except Exception as exc:

        print()
        print_header(
            "BIRMINGHAM XGBOOST SELECTED MODEL "
            "CONFIRMATION FAILED"
        )

        print()
        print(
            f"ERROR: {type(exc).__name__}: {exc}"
        )

        print()
        print(
            "NO persisted datasets were modified."
        )

        print(
            "Test dataset was NOT loaded."
        )

        print(
            "No final test evaluation was performed."
        )

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )