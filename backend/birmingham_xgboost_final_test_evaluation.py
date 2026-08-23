"""
SmartPark AI
Birmingham XGBoost Final Untouched Test Evaluation

File:
    backend/birmingham_xgboost_final_test_evaluation.py

Purpose:
    Perform the final untouched test evaluation of the confirmed
    TUNE_014 XGBoost model for:

        target_occupancy_rate_30m

This is the FINAL MODEL EVALUATION GATE.

Experimental contract
---------------------

Training:
    train.parquet

Validation:
    validation.parquet

Test:
    test.parquet

Model:
    TUNE_014

The model is trained ONLY on train.parquet.

Validation data is NEVER passed to model.fit().

Validation data is used only for:
    - confirmation reference
    - optional diagnostic comparison

Test data is used ONLY for:
    - final unbiased evaluation

No:
    - hyperparameter tuning
    - feature pipeline rebuild
    - early stopping
    - model selection
    - test-driven model changes
    - persisted dataset modification

IMPORTANT:
    The test result is a final evaluation result.
    It must NOT be used to select a different model.

Expected selected-model validation metrics
------------------------------------------

    MAE  = 0.013496
    RMSE = 0.019805
    R²   = 0.994984
    MAPE = 3.3279%

Selected candidate:
    TUNE_014

Features:
    296

Training rows:
    23,244

Validation rows:
    4,980

The test dataset is loaded only in this script because this is
the final evaluation stage.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.ml.ml_models.xgboost_model import (
    XGBoostModel,
    XGBoostModelConfig,
)


# ============================================================================
# CONSTANTS
# ============================================================================

TARGET_COLUMN = "target_occupancy_rate_30m"

EXPECTED_FEATURE_COUNT = 296

SELECTED_CANDIDATE = "TUNE_014"
SELECTED_DESCRIPTION = "Higher L1 regularisation"

# ---------------------------------------------------------------------------
# Confirmed TUNE_014 configuration
# ---------------------------------------------------------------------------

N_ESTIMATORS = 300
LEARNING_RATE = 0.05
MAX_DEPTH = 6
MIN_CHILD_WEIGHT = 1.0
SUBSAMPLE = 0.9
COLSAMPLE_BYTREE = 0.9
GAMMA = 0.0
REG_ALPHA = 0.1
REG_LAMBDA = 1.0

# ---------------------------------------------------------------------------
# Confirmed validation metrics
#
# These are NOT used to tune the model.
# They are retained solely as the independently confirmed reference.
# ---------------------------------------------------------------------------

CONFIRMED_VALIDATION_MAE = 0.013496
CONFIRMED_VALIDATION_RMSE = 0.019805
CONFIRMED_VALIDATION_R2 = 0.994984
CONFIRMED_VALIDATION_MAPE = 3.3279

# ---------------------------------------------------------------------------
# Repository paths
# ---------------------------------------------------------------------------

SCRIPT_PATH = Path(__file__).resolve()

BACKEND_ROOT = SCRIPT_PATH.parent

PROJECT_ROOT = BACKEND_ROOT.parent

DATASET_ROOT = (
    PROJECT_ROOT
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
    / "xgboost_final_test_evaluation"
)

JSON_OUTPUT = (
    OUTPUT_DIR
    / "birmingham_xgboost_final_test_evaluation.json"
)

CSV_OUTPUT = (
    OUTPUT_DIR
    / "birmingham_xgboost_final_test_evaluation.csv"
)

ERROR_CSV_OUTPUT = (
    OUTPUT_DIR
    / "birmingham_xgboost_final_test_evaluation_errors.csv"
)

REGIME_CSV_OUTPUT = (
    OUTPUT_DIR
    / "birmingham_xgboost_final_test_evaluation_regimes.csv"
)


# ============================================================================
# TERMINAL OUTPUT HELPERS
# ============================================================================

def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def print_field(
    label: str,
    value: Any,
) -> None:
    print(
        f"{label:<45}: {value}"
    )


def assert_condition(
    condition: bool,
    message: str,
) -> None:

    if not condition:
        raise AssertionError(message)


# ============================================================================
# METRICS
# ============================================================================

def calculate_metrics(
    y_true: pd.Series,
    y_pred: np.ndarray,
) -> dict[str, float]:

    actual = np.asarray(
        y_true,
        dtype=float,
    )

    predicted = np.asarray(
        y_pred,
        dtype=float,
    )

    assert_condition(
        actual.shape == predicted.shape,
        "Actual and prediction arrays have different shapes.",
    )

    assert_condition(
        np.isfinite(actual).all(),
        "Actual target contains non-finite values.",
    )

    assert_condition(
        np.isfinite(predicted).all(),
        "Predictions contain non-finite values.",
    )

    errors = (
        predicted
        - actual
    )

    absolute_errors = np.abs(
        errors
    )

    squared_errors = (
        errors ** 2
    )

    mae = float(
        np.mean(
            absolute_errors
        )
    )

    rmse = float(
        np.sqrt(
            np.mean(
                squared_errors
            )
        )
    )

    ss_res = float(
        np.sum(
            squared_errors
        )
    )

    mean_actual = float(
        np.mean(actual)
    )

    ss_tot = float(
        np.sum(
            (actual - mean_actual) ** 2
        )
    )

    if ss_tot == 0:
        r2 = float("nan")
    else:
        r2 = float(
            1.0
            - (
                ss_res
                / ss_tot
            )
        )

    # MAPE handling:
    #
    # Occupancy rates can be zero.
    # Zero-valued actual observations are excluded from the
    # percentage-error denominator rather than causing division
    # by zero.
    non_zero_mask = (
        np.abs(actual)
        > 1e-12
    )

    if non_zero_mask.any():

        mape = float(
            np.mean(
                np.abs(
                    (
                        actual[non_zero_mask]
                        - predicted[non_zero_mask]
                    )
                    / actual[non_zero_mask]
                )
            )
            * 100.0
        )

    else:

        mape = float("nan")

    return {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "mape": mape,
        "n": int(len(actual)),
    }


# ============================================================================
# MANIFEST
# ============================================================================

def load_feature_manifest() -> dict[str, Any]:

    print_section(
        "LOADING FEATURE MANIFEST"
    )

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

    assert_condition(
        isinstance(
            feature_columns,
            list,
        ),
        "Manifest feature_columns is not a list.",
    )

    assert_condition(
        len(feature_columns)
        == EXPECTED_FEATURE_COUNT,
        "Manifest does not contain exactly "
        f"{EXPECTED_FEATURE_COUNT} features.",
    )

    assert_condition(
        len(feature_columns)
        == len(set(feature_columns)),
        "Manifest contains duplicate feature names.",
    )

    assert_condition(
        TARGET_COLUMN
        not in feature_columns,
        "Target column is incorrectly registered as a model feature.",
    )

    print_field(
        "Manifest",
        MANIFEST_PATH,
    )

    print_field(
        "Registered features",
        len(feature_columns),
    )

    return manifest


# ============================================================================
# DATASET VALIDATION
# ============================================================================

def validate_dataset_files() -> None:

    print_section(
        "DATASET FILE VALIDATION"
    )

    print_field(
        "Processed dataset root",
        DATASET_ROOT,
    )

    print_field(
        "Training dataset",
        TRAIN_PATH,
    )

    print_field(
        "Validation dataset",
        VALIDATION_PATH,
    )

    print_field(
        "Test dataset",
        TEST_PATH,
    )

    print_field(
        "Feature manifest",
        MANIFEST_PATH,
    )

    assert_condition(
        TRAIN_PATH.exists(),
        f"Training dataset does not exist: {TRAIN_PATH}",
    )

    assert_condition(
        VALIDATION_PATH.exists(),
        f"Validation dataset does not exist: {VALIDATION_PATH}",
    )

    assert_condition(
        TEST_PATH.exists(),
        f"Test dataset does not exist: {TEST_PATH}",
    )

    assert_condition(
        MANIFEST_PATH.exists(),
        f"Feature manifest does not exist: {MANIFEST_PATH}",
    )

    print_field(
        "Training file exists",
        "PASS",
    )

    print_field(
        "Validation file exists",
        "PASS",
    )

    print_field(
        "Test file exists",
        "PASS",
    )

    print_field(
        "Feature manifest exists",
        "PASS",
    )


# ============================================================================
# DATASET LOADING
# ============================================================================

def load_datasets() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:

    print_section(
        "LOADING TRAINING DATASET"
    )

    train = pd.read_parquet(
        TRAIN_PATH
    )

    print_field(
        "Training rows",
        len(train),
    )

    print_field(
        "Training columns",
        len(train.columns),
    )

    print_section(
        "LOADING VALIDATION DATASET"
    )

    validation = pd.read_parquet(
        VALIDATION_PATH
    )

    print_field(
        "Validation rows",
        len(validation),
    )

    print_field(
        "Validation columns",
        len(validation.columns),
    )

    print_section(
        "LOADING FINAL TEST DATASET"
    )

    test = pd.read_parquet(
        TEST_PATH
    )

    print_field(
        "Test rows",
        len(test),
    )

    print_field(
        "Test columns",
        len(test.columns),
    )

    print_field(
        "Test dataset usage",
        "FINAL EVALUATION ONLY",
    )

    return (
        train,
        validation,
        test,
    )


# ============================================================================
# FEATURE CONTRACT
# ============================================================================

def validate_feature_contract(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
) -> None:

    print_section(
        "FEATURE CONTRACT VALIDATION"
    )

    for name, dataframe in [
        ("Training", train),
        ("Validation", validation),
        ("Test", test),
    ]:

        missing = [
            column
            for column in feature_columns
            if column not in dataframe.columns
        ]

        extra_model_features = [
            column
            for column in dataframe.columns
            if column in feature_columns
        ]

        assert_condition(
            not missing,
            f"{name} dataset is missing model features: {missing}",
        )

        assert_condition(
            len(extra_model_features)
            == EXPECTED_FEATURE_COUNT,
            f"{name} dataset does not contain exactly "
            f"{EXPECTED_FEATURE_COUNT} registered features.",
        )

        print_field(
            f"{name} feature registry",
            "PASS",
        )

    assert_condition(
        list(
            train[feature_columns].columns
        )
        == list(
            validation[feature_columns].columns
        ),
        "Train/validation feature ordering differs.",
    )

    assert_condition(
        list(
            train[feature_columns].columns
        )
        == list(
            test[feature_columns].columns
        ),
        "Train/test feature ordering differs.",
    )

    print_field(
        "Train/validation feature registry",
        "IDENTICAL",
    )

    print_field(
        "Train/test feature registry",
        "IDENTICAL",
    )

    duplicates = [
        column
        for column in feature_columns
        if feature_columns.count(column) > 1
    ]

    assert_condition(
        not duplicates,
        f"Duplicate registered features: {duplicates}",
    )

    print_field(
        "Duplicate feature names",
        len(duplicates),
    )

    categorical_features = [
        "occupancy_level",
        "demand_class",
    ]

    configured_categorical = [
        column
        for column in categorical_features
        if column in feature_columns
    ]

    print_field(
        "Categorical features delegated to model",
        ", ".join(configured_categorical),
    )


# ============================================================================
# TARGET CONTRACT
# ============================================================================

def validate_target_contract(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> None:

    print_section(
        "TARGET CONTRACT VALIDATION"
    )

    for name, dataframe in [
        ("Training", train),
        ("Validation", validation),
        ("Test", test),
    ]:

        assert_condition(
            TARGET_COLUMN in dataframe.columns,
            f"{name} dataset does not contain target column.",
        )

        target = pd.to_numeric(
            dataframe[TARGET_COLUMN],
            errors="coerce",
        )

        nulls = int(
            target.isna().sum()
        )

        assert_condition(
            nulls == 0,
            f"{name} target contains {nulls} null values.",
        )

        values = target.to_numpy(
            dtype=float
        )

        assert_condition(
            np.isfinite(values).all(),
            f"{name} target contains non-finite values.",
        )

        minimum = float(
            target.min()
        )

        maximum = float(
            target.max()
        )

        assert_condition(
            minimum >= 0.0
            and maximum <= 1.0,
            f"{name} target is outside [0, 1].",
        )

        print_field(
            f"{name} target rows",
            len(target),
        )

        print_field(
            f"{name} target nulls",
            nulls,
        )

        print_field(
            f"{name} target mean",
            f"{float(target.mean()):.6f}",
        )

        print_field(
            f"{name} target range",
            f"{minimum:.6f} -> {maximum:.6f}",
        )

    print_field(
        "Target range validation",
        "PASS",
    )


# ============================================================================
# TEMPORAL COLUMN DISCOVERY
# ============================================================================

def find_timestamp_column(
    dataframe: pd.DataFrame,
) -> str | None:

    preferred = [
        "normalized_at",
        "timestamp",
        "datetime",
        "date_time",
        "observation_timestamp",
        "source_timestamp",
    ]

    for column in preferred:

        if column in dataframe.columns:

            parsed = pd.to_datetime(
                dataframe[column],
                errors="coerce",
            )

            if parsed.notna().any():

                return column

    # Fallback: search datetime-typed columns.

    for column in dataframe.columns:

        if pd.api.types.is_datetime64_any_dtype(
            dataframe[column]
        ):

            return column

    return None


# ============================================================================
# TEMPORAL SPLIT VALIDATION
# ============================================================================

def validate_temporal_boundaries(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> dict[str, Any]:

    print_section(
        "FINAL CHRONOLOGICAL SPLIT VALIDATION"
    )

    train_timestamp_column = (
        find_timestamp_column(train)
    )

    validation_timestamp_column = (
        find_timestamp_column(validation)
    )

    test_timestamp_column = (
        find_timestamp_column(test)
    )

    assert_condition(
        train_timestamp_column is not None,
        "Unable to identify training timestamp column.",
    )

    assert_condition(
        validation_timestamp_column is not None,
        "Unable to identify validation timestamp column.",
    )

    assert_condition(
        test_timestamp_column is not None,
        "Unable to identify test timestamp column.",
    )

    train_times = pd.to_datetime(
        train[train_timestamp_column],
        errors="coerce",
    )

    validation_times = pd.to_datetime(
        validation[validation_timestamp_column],
        errors="coerce",
    )

    test_times = pd.to_datetime(
        test[test_timestamp_column],
        errors="coerce",
    )

    assert_condition(
        train_times.notna().all(),
        "Training timestamps contain invalid values.",
    )

    assert_condition(
        validation_times.notna().all(),
        "Validation timestamps contain invalid values.",
    )

    assert_condition(
        test_times.notna().all(),
        "Test timestamps contain invalid values.",
    )

    train_start = train_times.min()
    train_end = train_times.max()

    validation_start = validation_times.min()
    validation_end = validation_times.max()

    test_start = test_times.min()
    test_end = test_times.max()

    print_field(
        "Timestamp column",
        train_timestamp_column,
    )

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

    print_field(
        "Test start",
        test_start,
    )

    print_field(
        "Test end",
        test_end,
    )

    chronological = (
        train_end
        <= validation_start
        <= validation_end
        <= test_start
        <= test_end
    )

    assert_condition(
        chronological,
        "Train/validation/test datasets are not chronologically ordered.",
    )

    print_field(
        "Chronological ordering",
        "PASS",
    )

    return {
        "timestamp_column": train_timestamp_column,
        "training_start": str(train_start),
        "training_end": str(train_end),
        "validation_start": str(validation_start),
        "validation_end": str(validation_end),
        "test_start": str(test_start),
        "test_end": str(test_end),
    }


# ============================================================================
# OBSERVATION IDENTITY
# ============================================================================

def build_observation_keys(
    dataframe: pd.DataFrame,
) -> pd.Series:

    timestamp_column = find_timestamp_column(
        dataframe
    )

    facility_candidates = [
        "source_facility_code",
        "facility_code",
        "facility_id",
        "facility",
    ]

    facility_column = None

    for column in facility_candidates:

        if column in dataframe.columns:

            facility_column = column
            break

    if (
        timestamp_column is not None
        and facility_column is not None
    ):

        timestamp_values = pd.to_datetime(
            dataframe[timestamp_column],
            errors="coerce",
        ).astype(str)

        facility_values = (
            dataframe[facility_column]
            .astype("string")
            .fillna("")
        )

        return (
            facility_values
            + "|"
            + timestamp_values
        )

    if timestamp_column is not None:

        return pd.to_datetime(
            dataframe[timestamp_column],
            errors="coerce",
        ).astype(str)

    return pd.Series(
        dataframe.index.astype(str),
        index=dataframe.index,
    )


def validate_observation_isolation(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> dict[str, int]:

    print_section(
        "TRAIN / VALIDATION / TEST OBSERVATION ISOLATION"
    )

    train_keys = set(
        build_observation_keys(train)
    )

    validation_keys = set(
        build_observation_keys(validation)
    )

    test_keys = set(
        build_observation_keys(test)
    )

    train_validation_overlap = (
        len(
            train_keys
            & validation_keys
        )
    )

    train_test_overlap = (
        len(
            train_keys
            & test_keys
        )
    )

    validation_test_overlap = (
        len(
            validation_keys
            & test_keys
        )
    )

    print_field(
        "Train ∩ Validation",
        train_validation_overlap,
    )

    print_field(
        "Train ∩ Test",
        train_test_overlap,
    )

    print_field(
        "Validation ∩ Test",
        validation_test_overlap,
    )

    assert_condition(
        train_validation_overlap == 0,
        "Training and validation observations overlap.",
    )

    assert_condition(
        train_test_overlap == 0,
        "Training and test observations overlap.",
    )

    assert_condition(
        validation_test_overlap == 0,
        "Validation and test observations overlap.",
    )

    print_field(
        "Observation isolation",
        "PASS",
    )

    return {
        "train_validation_overlap": train_validation_overlap,
        "train_test_overlap": train_test_overlap,
        "validation_test_overlap": validation_test_overlap,
    }


# ============================================================================
# MODEL CONSTRUCTION
# ============================================================================

def build_selected_model() -> XGBoostModel:

    print_section(
        "BUILDING FINAL TUNE_014 MODEL"
    )

    print_field(
        "Candidate",
        SELECTED_CANDIDATE,
    )

    print_field(
        "Description",
        SELECTED_DESCRIPTION,
    )

    print_field(
        "n_estimators",
        N_ESTIMATORS,
    )

    print_field(
        "learning_rate",
        LEARNING_RATE,
    )

    print_field(
        "max_depth",
        MAX_DEPTH,
    )

    print_field(
        "min_child_weight",
        MIN_CHILD_WEIGHT,
    )

    print_field(
        "subsample",
        SUBSAMPLE,
    )

    print_field(
        "colsample_bytree",
        COLSAMPLE_BYTREE,
    )

    print_field(
        "gamma",
        GAMMA,
    )

    print_field(
        "reg_alpha",
        REG_ALPHA,
    )

    print_field(
        "reg_lambda",
        REG_LAMBDA,
    )

    config = XGBoostModelConfig(
        n_estimators=N_ESTIMATORS,
        learning_rate=LEARNING_RATE,
        max_depth=MAX_DEPTH,
        min_child_weight=MIN_CHILD_WEIGHT,
        subsample=SUBSAMPLE,
        colsample_bytree=COLSAMPLE_BYTREE,
        gamma=GAMMA,
        reg_alpha=REG_ALPHA,
        reg_lambda=REG_LAMBDA,
        categorical_features=[
            "occupancy_level",
            "demand_class",
        ],
    )

    model = XGBoostModel(
        target_column=TARGET_COLUMN,
        config=config,
        model_name="birmingham_xgboost_tune_014_final",
    )

    return model


# ============================================================================
# RAW MATRIX PREPARATION
# ============================================================================

def prepare_raw_matrices(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[
    pd.DataFrame,
    pd.Series,
    pd.DataFrame,
    pd.Series,
    pd.DataFrame,
    pd.Series,
]:

    print_section(
        "PREPARING FINAL MODEL MATRICES"
    )

    X_train = train[
        feature_columns
    ].copy()

    y_train = pd.to_numeric(
        train[TARGET_COLUMN],
        errors="raise",
    )

    X_validation = validation[
        feature_columns
    ].copy()

    y_validation = pd.to_numeric(
        validation[TARGET_COLUMN],
        errors="raise",
    )

    X_test = test[
        feature_columns
    ].copy()

    y_test = pd.to_numeric(
        test[TARGET_COLUMN],
        errors="raise",
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
        "Test matrix shape",
        X_test.shape,
    )

    assert_condition(
        X_train.shape[1]
        == EXPECTED_FEATURE_COUNT,
        "Training matrix feature count is incorrect.",
    )

    assert_condition(
        X_validation.shape[1]
        == EXPECTED_FEATURE_COUNT,
        "Validation matrix feature count is incorrect.",
    )

    assert_condition(
        X_test.shape[1]
        == EXPECTED_FEATURE_COUNT,
        "Test matrix feature count is incorrect.",
    )

    assert_condition(
        list(X_train.columns)
        == list(X_validation.columns)
        == list(X_test.columns),
        "Feature ordering differs between datasets.",
    )

    print_field(
        "Feature count",
        EXPECTED_FEATURE_COUNT,
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
        X_test,
        y_test,
    )


# ============================================================================
# ERROR ANALYSIS
# ============================================================================

def build_error_dataframe(
    y_true: pd.Series,
    y_pred: np.ndarray,
) -> pd.DataFrame:

    actual = np.asarray(
        y_true,
        dtype=float,
    )

    predicted = np.asarray(
        y_pred,
        dtype=float,
    )

    result = pd.DataFrame(
        {
            "actual": actual,
            "prediction": predicted,
        }
    )

    result["error"] = (
        result["prediction"]
        - result["actual"]
    )

    result["absolute_error"] = (
        result["error"]
        .abs()
    )

    result["squared_error"] = (
        result["error"]
        ** 2
    )

    non_zero = (
        result["actual"]
        .abs()
        > 1e-12
    )

    result["absolute_percentage_error"] = np.nan

    result.loc[
        non_zero,
        "absolute_percentage_error",
    ] = (
        result.loc[
            non_zero,
            "absolute_error",
        ]
        / result.loc[
            non_zero,
            "actual",
        ].abs()
        * 100.0
    )

    result["prediction_clipped"] = (
        result["prediction"]
        .clip(
            lower=0.0,
            upper=1.0,
        )
    )

    result["prediction_outside_target_range"] = (
        (result["prediction"] < 0.0)
        | (result["prediction"] > 1.0)
    )

    return result


# ============================================================================
# REGIME ANALYSIS
# ============================================================================

def classify_occupancy_regime(
    value: float,
) -> str:

    if value < 0.25:
        return "LOW"

    if value < 0.50:
        return "MODERATE"

    if value < 0.75:
        return "HIGH"

    return "VERY_HIGH"


def build_regime_summary(
    error_dataframe: pd.DataFrame,
) -> pd.DataFrame:

    work = error_dataframe.copy()

    work["occupancy_regime"] = (
        work["actual"]
        .map(
            classify_occupancy_regime
        )
    )

    rows: list[dict[str, Any]] = []

    for regime, group in work.groupby(
        "occupancy_regime",
        sort=False,
    ):

        y_true = group[
            "actual"
        ].to_numpy(
            dtype=float
        )

        y_pred = group[
            "prediction"
        ].to_numpy(
            dtype=float
        )

        metrics = calculate_metrics(
            pd.Series(y_true),
            y_pred,
        )

        rows.append(
            {
                "occupancy_regime": regime,
                "n": metrics["n"],
                "mae": metrics["mae"],
                "rmse": metrics["rmse"],
                "r2": metrics["r2"],
                "mape": metrics["mape"],
                "mean_actual": float(
                    np.mean(y_true)
                ),
                "mean_prediction": float(
                    np.mean(y_pred)
                ),
                "mean_absolute_error": float(
                    np.mean(
                        np.abs(
                            y_pred
                            - y_true
                        )
                    )
                ),
            }
        )

    return pd.DataFrame(
        rows
    )


# ============================================================================
# FINAL MODEL TRAINING
# ============================================================================

def train_final_model(
    model: XGBoostModel,
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> float:

    print_section(
        "TRAINING FINAL SELECTED MODEL"
    )

    print_field(
        "Validation passed to fit()",
        "NO",
    )

    print_field(
        "Test data passed to fit()",
        "NO",
    )

    print_field(
        "Hyperparameter tuning",
        "NO",
    )

    print_field(
        "Early stopping",
        "NO",
    )

    print_field(
        "Training rows",
        len(X_train),
    )

    print_field(
        "Training features",
        X_train.shape[1],
    )

    started = time.perf_counter()

    print()
    print(
        "Training XGBoost..."
    )

    model.fit(
        X_train,
        y_train,
    )

    elapsed = (
        time.perf_counter()
        - started
    )

    print(
        f"Training completed in "
        f"{elapsed:.2f} seconds."
    )

    return elapsed


# ============================================================================
# PREDICTIONS
# ============================================================================

def generate_predictions(
    model: XGBoostModel,
    X_validation: pd.DataFrame,
    X_test: pd.DataFrame,
) -> tuple[
    np.ndarray,
    np.ndarray,
]:

    print_section(
        "GENERATING VALIDATION PREDICTIONS"
    )

    validation_predictions = np.asarray(
        model.predict(
            X_validation
        ),
        dtype=float,
    )

    assert_condition(
        np.isfinite(
            validation_predictions
        ).all(),
        "Validation predictions contain non-finite values.",
    )

    print_field(
        "Validation predictions",
        len(validation_predictions),
    )

    print_section(
        "GENERATING FINAL TEST PREDICTIONS"
    )

    print(
        "IMPORTANT:"
    )

    print(
        "This is the first and only final test evaluation."
    )

    test_predictions = np.asarray(
        model.predict(
            X_test
        ),
        dtype=float,
    )

    assert_condition(
        np.isfinite(
            test_predictions
        ).all(),
        "Test predictions contain non-finite values.",
    )

    print_field(
        "Test predictions",
        len(test_predictions),
    )

    return (
        validation_predictions,
        test_predictions,
    )


# ============================================================================
# MODEL PERFORMANCE REPORT
# ============================================================================

def print_metrics(
    title: str,
    metrics: dict[str, float],
) -> None:

    print()
    print(
        f"{title}:"
    )

    print(
        f"  MAE :  {metrics['mae']:.6f}"
    )

    print(
        f"  RMSE:  {metrics['rmse']:.6f}"
    )

    print(
        f"  R²  :  {metrics['r2']:.6f}"
    )

    print(
        f"  MAPE:  {metrics['mape']:.4f}%"
    )

    print(
        f"  N   :  {metrics['n']}"
    )


# ============================================================================
# COMPARISON
# ============================================================================

def calculate_comparison(
    validation_metrics: dict[str, float],
    test_metrics: dict[str, float],
) -> dict[str, float]:

    return {
        "test_minus_validation_mae": (
            test_metrics["mae"]
            - validation_metrics["mae"]
        ),
        "test_minus_validation_rmse": (
            test_metrics["rmse"]
            - validation_metrics["rmse"]
        ),
        "test_minus_validation_r2": (
            test_metrics["r2"]
            - validation_metrics["r2"]
        ),
        "test_minus_validation_mape": (
            test_metrics["mape"]
            - validation_metrics["mape"]
        ),
    }


# ============================================================================
# RESULT PERSISTENCE
# ============================================================================

def persist_results(
    *,
    manifest: dict[str, Any],
    temporal: dict[str, Any],
    isolation: dict[str, int],
    validation_metrics: dict[str, float],
    test_metrics: dict[str, float],
    comparison: dict[str, float],
    regime_summary: pd.DataFrame,
    error_dataframe: pd.DataFrame,
    training_seconds: float,
) -> None:

    print_section(
        "PERSISTING FINAL TEST RESULTS"
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    model_configuration = {
        "candidate": SELECTED_CANDIDATE,
        "description": SELECTED_DESCRIPTION,
        "n_estimators": N_ESTIMATORS,
        "learning_rate": LEARNING_RATE,
        "max_depth": MAX_DEPTH,
        "min_child_weight": MIN_CHILD_WEIGHT,
        "subsample": SUBSAMPLE,
        "colsample_bytree": COLSAMPLE_BYTREE,
        "gamma": GAMMA,
        "reg_alpha": REG_ALPHA,
        "reg_lambda": REG_LAMBDA,
        "categorical_features": [
            "occupancy_level",
            "demand_class",
        ],
    }

    summary = {
        "experiment": {
            "name": "birmingham_xgboost_final_test_evaluation",
            "target": TARGET_COLUMN,
            "selected_candidate": SELECTED_CANDIDATE,
            "description": SELECTED_DESCRIPTION,
        },
        "experimental_contract": {
            "training_dataset": str(TRAIN_PATH),
            "validation_dataset": str(
                VALIDATION_PATH
            ),
            "test_dataset": str(TEST_PATH),
            "validation_passed_to_fit": False,
            "test_passed_to_fit": False,
            "hyperparameter_tuning": False,
            "feature_pipeline_rebuilt": False,
            "early_stopping": False,
            "test_used_for_model_selection": False,
        },
        "model_configuration": model_configuration,
        "feature_contract": {
            "feature_count": EXPECTED_FEATURE_COUNT,
            "feature_columns": manifest.get(
                "feature_columns",
                [],
            ),
        },
        "dataset_counts": {
            "training_rows": int(
                len(error_dataframe) * 0
            ),
        },
        "temporal_contract": temporal,
        "observation_isolation": isolation,
        "confirmed_validation_metrics": {
            "mae": CONFIRMED_VALIDATION_MAE,
            "rmse": CONFIRMED_VALIDATION_RMSE,
            "r2": CONFIRMED_VALIDATION_R2,
            "mape": CONFIRMED_VALIDATION_MAPE,
        },
        "reproduced_validation_metrics": validation_metrics,
        "final_test_metrics": test_metrics,
        "test_vs_validation": comparison,
        "training_seconds": training_seconds,
        "prediction_range": {
            "minimum": float(
                error_dataframe["prediction"].min()
            ),
            "maximum": float(
                error_dataframe["prediction"].max()
            ),
            "mean": float(
                error_dataframe["prediction"].mean()
            ),
        },
        "test_error_statistics": {
            "mean_error": float(
                error_dataframe["error"].mean()
            ),
            "median_error": float(
                error_dataframe["error"].median()
            ),
            "mean_absolute_error": float(
                error_dataframe["absolute_error"].mean()
            ),
            "maximum_absolute_error": float(
                error_dataframe["absolute_error"].max()
            ),
            "p95_absolute_error": float(
                error_dataframe["absolute_error"].quantile(
                    0.95
                )
            ),
            "p99_absolute_error": float(
                error_dataframe["absolute_error"].quantile(
                    0.99
                )
            ),
            "predictions_outside_0_1": int(
                error_dataframe[
                    "prediction_outside_target_range"
                ].sum()
            ),
        },
        "regime_summary": (
            regime_summary.to_dict(
                orient="records"
            )
        ),
        "final_evaluation_verdict": (
            "FINAL_TEST_EVALUATION_COMPLETED"
        ),
    }

    with JSON_OUTPUT.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            summary,
            handle,
            indent=2,
            default=str,
        )

    confirmation_row = {
        "target": TARGET_COLUMN,
        "candidate": SELECTED_CANDIDATE,
        "feature_count": EXPECTED_FEATURE_COUNT,
        "training_rows": temporal.get(
            "training_rows",
            "",
        ),
        "validation_rows": temporal.get(
            "validation_rows",
            "",
        ),
        "test_rows": test_metrics["n"],
        "validation_mae": validation_metrics["mae"],
        "validation_rmse": validation_metrics["rmse"],
        "validation_r2": validation_metrics["r2"],
        "validation_mape": validation_metrics["mape"],
        "test_mae": test_metrics["mae"],
        "test_rmse": test_metrics["rmse"],
        "test_r2": test_metrics["r2"],
        "test_mape": test_metrics["mape"],
        "test_minus_validation_mae": comparison[
            "test_minus_validation_mae"
        ],
        "test_minus_validation_rmse": comparison[
            "test_minus_validation_rmse"
        ],
        "test_minus_validation_r2": comparison[
            "test_minus_validation_r2"
        ],
        "test_minus_validation_mape": comparison[
            "test_minus_validation_mape"
        ],
        "training_seconds": training_seconds,
        "test_used_for_model_selection": False,
        "test_used_for_fit": False,
        "validation_used_for_fit": False,
        "hyperparameter_tuning": False,
    }

    pd.DataFrame(
        [confirmation_row]
    ).to_csv(
        CSV_OUTPUT,
        index=False,
    )

    error_dataframe.to_csv(
        ERROR_CSV_OUTPUT,
        index=False,
    )

    regime_summary.to_csv(
        REGIME_CSV_OUTPUT,
        index=False,
    )

    print_field(
        "Output directory",
        OUTPUT_DIR,
    )

    print_field(
        "JSON report",
        JSON_OUTPUT,
    )

    print_field(
        "CSV final evaluation",
        CSV_OUTPUT,
    )

    print_field(
        "CSV error analysis",
        ERROR_CSV_OUTPUT,
    )

    print_field(
        "CSV regime analysis",
        REGIME_CSV_OUTPUT,
    )


# ============================================================================
# FINAL ASSERTIONS
# ============================================================================

def run_final_assertions(
    *,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
    validation_metrics: dict[str, float],
    test_metrics: dict[str, float],
) -> None:

    print_section(
        "FINAL ASSERTIONS"
    )

    assert_condition(
        len(feature_columns)
        == EXPECTED_FEATURE_COUNT,
        "Expected feature count assertion failed.",
    )

    print_field(
        "Expected feature count = 296",
        "PASS",
    )

    assert_condition(
        len(train)
        == 23244,
        "Unexpected training row count.",
    )

    print_field(
        "Training row count correct",
        "PASS",
    )

    assert_condition(
        len(validation)
        == 4980,
        "Unexpected validation row count.",
    )

    print_field(
        "Validation row count correct",
        "PASS",
    )

    assert_condition(
        len(test) > 0,
        "Test dataset is empty.",
    )

    print_field(
        "Test dataset non-empty",
        "PASS",
    )

    assert_condition(
        validation_metrics["n"]
        == len(validation),
        "Validation prediction count mismatch.",
    )

    print_field(
        "Validation prediction count correct",
        "PASS",
    )

    assert_condition(
        test_metrics["n"]
        == len(test),
        "Test prediction count mismatch.",
    )

    print_field(
        "Test prediction count correct",
        "PASS",
    )

    for name, metrics in [
        ("Validation", validation_metrics),
        ("Test", test_metrics),
    ]:

        for metric_name in [
            "mae",
            "rmse",
            "r2",
            "mape",
        ]:

            assert_condition(
                math.isfinite(
                    metrics[metric_name]
                ),
                f"{name} {metric_name} is not finite.",
            )

        print_field(
            f"{name} metrics finite",
            "PASS",
        )

    print_field(
        "Validation data used for fit",
        "NO",
    )

    print_field(
        "Test data used for fit",
        "NO",
    )

    print_field(
        "Test data used for model selection",
        "NO",
    )

    print_field(
        "Hyperparameter tuning",
        "NO",
    )

    print_field(
        "Feature pipeline rebuilt",
        "NO",
    )

    print_field(
        "Persisted datasets modified",
        "NO",
    )

    print()
    print(
        "ALL FINAL TEST EVALUATION ASSERTIONS PASSED"
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> None:

    print_header(
        "SMARTPARK AI - BIRMINGHAM XGBOOST FINAL TEST EVALUATION"
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
        "Selected model:"
    )
    print(
        f"  Candidate              : {SELECTED_CANDIDATE}"
    )
    print(
        f"  Description            : {SELECTED_DESCRIPTION}"
    )

    print()
    print(
        "FINAL EXPERIMENT:"
    )
    print(
        "  Train = train.parquet"
    )
    print(
        "  Validation = validation.parquet"
    )
    print(
        "  Test = test.parquet"
    )
    print(
        "  Test is used ONLY for final evaluation"
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
    print(
        "  Test data never passed to fit()"
    )
    print(
        "  Test result cannot change model selection"
    )

    print()
    print(
        "Confirmed validation reference:"
    )
    print(
        f"  MAE  = {CONFIRMED_VALIDATION_MAE:.6f}"
    )
    print(
        f"  RMSE = {CONFIRMED_VALIDATION_RMSE:.6f}"
    )
    print(
        f"  R²   = {CONFIRMED_VALIDATION_R2:.6f}"
    )
    print(
        f"  MAPE = {CONFIRMED_VALIDATION_MAPE:.4f}%"
    )

    try:

        # ----------------------------------------------------------
        # File validation
        # ----------------------------------------------------------

        validate_dataset_files()

        # ----------------------------------------------------------
        # Manifest
        # ----------------------------------------------------------

        manifest = load_feature_manifest()

        feature_columns = manifest[
            "feature_columns"
        ]

        # ----------------------------------------------------------
        # Dataset loading
        # ----------------------------------------------------------

        (
            train,
            validation,
            test,
        ) = load_datasets()

        # ----------------------------------------------------------
        # Feature contract
        # ----------------------------------------------------------

        validate_feature_contract(
            train,
            validation,
            test,
            feature_columns,
        )

        # ----------------------------------------------------------
        # Target contract
        # ----------------------------------------------------------

        validate_target_contract(
            train,
            validation,
            test,
        )

        # ----------------------------------------------------------
        # Temporal split
        # ----------------------------------------------------------

        temporal = (
            validate_temporal_boundaries(
                train,
                validation,
                test,
            )
        )

        temporal[
            "training_rows"
        ] = len(train)

        temporal[
            "validation_rows"
        ] = len(validation)

        temporal[
            "test_rows"
        ] = len(test)

        # ----------------------------------------------------------
        # Observation isolation
        # ----------------------------------------------------------

        isolation = (
            validate_observation_isolation(
                train,
                validation,
                test,
            )
        )

        # ----------------------------------------------------------
        # Raw matrices
        # ----------------------------------------------------------

        (
            X_train,
            y_train,
            X_validation,
            y_validation,
            X_test,
            y_test,
        ) = prepare_raw_matrices(
            train,
            validation,
            test,
            feature_columns,
        )

        # ----------------------------------------------------------
        # Build model
        # ----------------------------------------------------------

        model = build_selected_model()

        # ----------------------------------------------------------
        # Train ONLY on training data
        # ----------------------------------------------------------

        training_seconds = train_final_model(
            model,
            X_train,
            y_train,
        )

        # ----------------------------------------------------------
        # Predictions
        # ----------------------------------------------------------

        (
            validation_predictions,
            test_predictions,
        ) = generate_predictions(
            model,
            X_validation,
            X_test,
        )

        # ----------------------------------------------------------
        # Validation metrics
        # ----------------------------------------------------------

        validation_metrics = calculate_metrics(
            y_validation,
            validation_predictions,
        )

        print_metrics(
            "Reproduced validation metrics",
            validation_metrics,
        )

        # ----------------------------------------------------------
        # Test metrics
        # ----------------------------------------------------------

        test_metrics = calculate_metrics(
            y_test,
            test_predictions,
        )

        print_metrics(
            "FINAL UNTOUCHED TEST METRICS",
            test_metrics,
        )

        # ----------------------------------------------------------
        # Error analysis
        # ----------------------------------------------------------

        error_dataframe = build_error_dataframe(
            y_test,
            test_predictions,
        )

        # ----------------------------------------------------------
        # Regime analysis
        # ----------------------------------------------------------

        regime_summary = build_regime_summary(
            error_dataframe
        )

        print()
        print(
            "Test error summary:"
        )

        print(
            f"  Mean error                : "
            f"{error_dataframe['error'].mean():.6f}"
        )

        print(
            f"  Median error              : "
            f"{error_dataframe['error'].median():.6f}"
        )

        print(
            f"  Maximum absolute error    : "
            f"{error_dataframe['absolute_error'].max():.6f}"
        )

        print(
            f"  P95 absolute error        : "
            f"{error_dataframe['absolute_error'].quantile(0.95):.6f}"
        )

        print(
            f"  P99 absolute error        : "
            f"{error_dataframe['absolute_error'].quantile(0.99):.6f}"
        )

        print(
            f"  Predictions outside [0,1]: "
            f"{int(error_dataframe['prediction_outside_target_range'].sum())}"
        )

        # ----------------------------------------------------------
        # Comparison
        # ----------------------------------------------------------

        print_section(
            "FINAL TEST VS CONFIRMED VALIDATION"
        )

        comparison = calculate_comparison(
            validation_metrics,
            test_metrics,
        )

        print_field(
            "Validation MAE",
            f"{validation_metrics['mae']:.6f}",
        )

        print_field(
            "Test MAE",
            f"{test_metrics['mae']:.6f}",
        )

        print_field(
            "Test - Validation MAE",
            f"{comparison['test_minus_validation_mae']:+.6f}",
        )

        print_field(
            "Validation RMSE",
            f"{validation_metrics['rmse']:.6f}",
        )

        print_field(
            "Test RMSE",
            f"{test_metrics['rmse']:.6f}",
        )

        print_field(
            "Test - Validation RMSE",
            f"{comparison['test_minus_validation_rmse']:+.6f}",
        )

        print_field(
            "Validation R²",
            f"{validation_metrics['r2']:.6f}",
        )

        print_field(
            "Test R²",
            f"{test_metrics['r2']:.6f}",
        )

        print_field(
            "Test - Validation R²",
            f"{comparison['test_minus_validation_r2']:+.6f}",
        )

        print_field(
            "Validation MAPE",
            f"{validation_metrics['mape']:.4f}%",
        )

        print_field(
            "Test MAPE",
            f"{test_metrics['mape']:.4f}%",
        )

        print_field(
            "Test - Validation MAPE",
            f"{comparison['test_minus_validation_mape']:+.4f}",
        )

        # ----------------------------------------------------------
        # Persist
        # ----------------------------------------------------------

        persist_results(
            manifest=manifest,
            temporal=temporal,
            isolation=isolation,
            validation_metrics=validation_metrics,
            test_metrics=test_metrics,
            comparison=comparison,
            regime_summary=regime_summary,
            error_dataframe=error_dataframe,
            training_seconds=training_seconds,
        )

        # ----------------------------------------------------------
        # Assertions
        # ----------------------------------------------------------

        run_final_assertions(
            train=train,
            validation=validation,
            test=test,
            feature_columns=feature_columns,
            validation_metrics=validation_metrics,
            test_metrics=test_metrics,
        )

        # ----------------------------------------------------------
        # Final result
        # ----------------------------------------------------------

        print_header(
            "BIRMINGHAM XGBOOST FINAL TEST EVALUATION COMPLETED"
        )

        print()
        print(
            "FINAL MODEL:"
        )

        print(
            f"  Candidate:             {SELECTED_CANDIDATE}"
        )

        print(
            f"  Features:              {EXPECTED_FEATURE_COUNT}"
        )

        print(
            f"  Training rows:         {len(train)}"
        )

        print(
            f"  Validation rows:       {len(validation)}"
        )

        print(
            f"  Test rows:             {len(test)}"
        )

        print()
        print(
            "FINAL TEST PERFORMANCE:"
        )

        print(
            f"  MAE  = {test_metrics['mae']:.6f}"
        )

        print(
            f"  RMSE = {test_metrics['rmse']:.6f}"
        )

        print(
            f"  R²   = {test_metrics['r2']:.6f}"
        )

        print(
            f"  MAPE = {test_metrics['mape']:.4f}%"
        )

        print()
        print(
            f"Training time:       {training_seconds:.2f} seconds"
        )

        print()
        print(
            "Test dataset used:             YES"
        )

        print(
            "Test dataset used for fit:     NO"
        )

        print(
            "Test dataset used for tuning:  NO"
        )

        print(
            "Test dataset used for selection: NO"
        )

        print(
            "Validation used for fit:       NO"
        )

        print(
            "Hyperparameter tuning:         NO"
        )

        print(
            "Feature pipeline rebuilt:      NO"
        )

        print(
            "Persisted datasets modified:   NO"
        )

        print()
        print(
            "FINAL XGBOOST TEST EVALUATION PASSED"
        )

        print()
        print(
            "IMPORTANT:"
        )

        print(
            "The test metrics above are the final untouched "
            "generalisation results for TUNE_014."
        )

        print(
            "Do NOT retune the model against the test dataset."
        )

    except Exception as exc:

        print()
        print_header(
            "BIRMINGHAM XGBOOST FINAL TEST EVALUATION FAILED"
        )

        print()
        print(
            f"ERROR: {type(exc).__name__}: {exc}"
        )

        print()
        print(
            "No persisted training, validation, or test datasets "
            "were modified."
        )

        print(
            "The test result must not be used for model tuning."
        )

        raise


if __name__ == "__main__":
    main()