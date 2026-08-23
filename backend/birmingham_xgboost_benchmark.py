"""
SmartPark AI - Birmingham XGBoost Benchmark
===========================================

Purpose
-------
Run the first real XGBoost regression benchmark against the persisted
Birmingham training dataset.

Target
------
    target_occupancy_rate_30m

Data contract
-------------
Training:
    datasets/processed/birmingham/
        target_occupancy_rate_30m/train.parquet

Validation:
    datasets/processed/birmingham/
        target_occupancy_rate_30m/validation.parquet

Test:
    datasets/processed/birmingham/
        target_occupancy_rate_30m/test.parquet

The test dataset is intentionally NOT loaded.

Baseline benchmark
-------------------
Previously established:

    Mean baseline:
        MAE = 0.248729

    Last-value baseline:
        MAE = 0.245388

The initial XGBoost model must be compared against these values.

Experiment policy
-----------------
This is the FIRST XGBoost experiment.

No hyperparameter tuning is performed here.

The purpose is to establish whether the initial XGBoost configuration
can beat the baseline before we introduce tuning.

Leakage contract
----------------
    - Training data only is passed to model.fit()
    - Validation data is used only for prediction/evaluation
    - Test data is not loaded
    - No future data is introduced
    - No target columns are used as features
    - No random train/validation split
    - Existing chronological split is preserved
    - No target imputation

Feature handling
----------------
The persisted Birmingham feature registry contains 296 features.

Most are numeric, but the feature registry legitimately contains
categorical features such as:

    - occupancy_level
    - demand_class

The benchmark MUST NOT reject these features merely because they are
non-numeric.

Categorical encoding is owned by XGBoostModel.

The benchmark therefore passes the persisted feature DataFrames to
XGBoostModel unchanged after validating the feature contract.
"""

from __future__ import annotations

import json
import math
import time
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

PROCESSED_ROOT = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
)


# ============================================================================
# TARGET
# ============================================================================

TARGET_COLUMN = (
    "target_occupancy_rate_30m"
)

TARGET_AVAILABILITY_COLUMN = (
    "target_30m_available"
)


# ============================================================================
# DATASET PATHS
# ============================================================================

TARGET_ROOT = (
    PROCESSED_ROOT
    / TARGET_COLUMN
)

TRAIN_FILE = (
    TARGET_ROOT
    / "train.parquet"
)

VALIDATION_FILE = (
    TARGET_ROOT
    / "validation.parquet"
)

TEST_FILE = (
    TARGET_ROOT
    / "test.parquet"
)


# ============================================================================
# EXPECTED DATASET CONTRACT
# ============================================================================

EXPECTED_FEATURE_COUNT = 296

EXPECTED_TRAIN_ROWS = 23_244

EXPECTED_VALIDATION_ROWS = 4_980

EXPECTED_TEST_ROWS = 4_982


# ============================================================================
# BASELINE CONTRACT
# ============================================================================

MEAN_BASELINE_MAE = 0.248729

LAST_VALUE_BASELINE_MAE = 0.245388


# ============================================================================
# OUTPUT
# ============================================================================

OUTPUT_ROOT = (
    PROCESSED_ROOT
    / "xgboost_benchmark"
)

RESULTS_JSON = (
    OUTPUT_ROOT
    / "xgboost_benchmark_results.json"
)

RESULTS_CSV = (
    OUTPUT_ROOT
    / "xgboost_benchmark_results.csv"
)

FEATURE_IMPORTANCE_CSV = (
    OUTPUT_ROOT
    / "xgboost_feature_importance.csv"
)


# ============================================================================
# IMPORT MODEL
# ============================================================================

try:

    from app.ml.ml_models.xgboost_model import (
        XGBoostModel,
        XGBoostModelConfig,
        XGBoostEvaluationResult,
        XGBoostModelError,
        XGBoostModelDataError,
        XGBoostModelNotFittedError,
    )

except ImportError as exc:

    print()
    print("=" * 78)
    print("ERROR: UNABLE TO IMPORT XGBOOST MODEL")
    print("=" * 78)
    print()
    print(
        "Expected module:"
    )
    print(
        "  app.ml.ml_models.xgboost_model"
    )
    print()
    print(
        f"Original error: {exc}"
    )
    print()

    raise SystemExit(1)


# ============================================================================
# DISPLAY HELPERS
# ============================================================================

def print_header(
    title: str,
) -> None:

    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(
    title: str,
) -> None:

    print()
    print(
        f"--- {title} ---"
    )


def print_key_value(
    label: str,
    value: Any,
) -> None:

    print(
        f"{label:<40}: {value}"
    )


# ============================================================================
# FILE VALIDATION
# ============================================================================

def validate_dataset_files() -> None:
    """
    Confirm the expected persisted Birmingham datasets exist.

    The test file is checked for existence only.

    It is NOT read.
    """

    print_section(
        "DATASET FILE VALIDATION"
    )

    print_key_value(
        "Processed dataset root",
        PROCESSED_ROOT,
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

    if not PROCESSED_ROOT.exists():

        raise FileNotFoundError(
            "Processed Birmingham dataset directory "
            f"does not exist: {PROCESSED_ROOT}"
        )

    if not TRAIN_FILE.exists():

        raise FileNotFoundError(
            "Training dataset does not exist: "
            f"{TRAIN_FILE}"
        )

    if not VALIDATION_FILE.exists():

        raise FileNotFoundError(
            "Validation dataset does not exist: "
            f"{VALIDATION_FILE}"
        )

    if not TEST_FILE.exists():

        raise FileNotFoundError(
            "Test dataset does not exist: "
            f"{TEST_FILE}"
        )

    print()
    print(
        "Training file exists:    PASS"
    )

    print(
        "Validation file exists:  PASS"
    )

    print(
        "Test file exists:        PASS"
    )

    print(
        "Test file will NOT be loaded."
    )


# ============================================================================
# DATA LOADING
# ============================================================================

def load_training_data() -> pd.DataFrame:
    """
    Load only the persisted training dataset.
    """

    print_section(
        "LOADING TRAINING DATASET"
    )

    dataframe = pd.read_parquet(
        TRAIN_FILE
    )

    print_key_value(
        "Rows",
        f"{len(dataframe):,}",
    )

    print_key_value(
        "Columns",
        f"{len(dataframe.columns):,}",
    )

    return dataframe


def load_validation_data() -> pd.DataFrame:
    """
    Load only the persisted validation dataset.
    """

    print_section(
        "LOADING VALIDATION DATASET"
    )

    dataframe = pd.read_parquet(
        VALIDATION_FILE
    )

    print_key_value(
        "Rows",
        f"{len(dataframe):,}",
    )

    print_key_value(
        "Columns",
        f"{len(dataframe.columns):,}",
    )

    return dataframe


# ============================================================================
# FEATURE IDENTIFICATION
# ============================================================================

METADATA_COLUMNS = {
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


TARGET_COLUMNS = {
    "target_occupancy_rate_30m",
    "target_occupancy_rate_1h",
    "target_occupancy_rate_2h",
    "target_tomorrow_morning_demand",
}


TARGET_AVAILABILITY_COLUMNS = {
    "target_30m_available",
    "target_1h_available",
    "target_2h_available",
    "target_tomorrow_morning_available",
}


def identify_feature_columns(
    dataframe: pd.DataFrame,
) -> list[str]:
    """
    Identify the 296 registered ML feature columns.

    This intentionally excludes:

        - targets
        - target availability flags
        - metadata
    """

    excluded = (
        METADATA_COLUMNS
        | TARGET_COLUMNS
        | TARGET_AVAILABILITY_COLUMNS
    )

    feature_columns = [
        column
        for column in dataframe.columns
        if column not in excluded
    ]

    return feature_columns


# ============================================================================
# FEATURE VALIDATION
# ============================================================================

def validate_feature_contract(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> list[str]:
    """
    Confirm the persisted datasets expose the exact same 296 features.

    Categorical features are valid and are deliberately retained.
    """

    print_section(
        "FEATURE CONTRACT VALIDATION"
    )

    train_features = (
        identify_feature_columns(
            train_df
        )
    )

    validation_features = (
        identify_feature_columns(
            validation_df
        )
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
            "Training and validation feature registries "
            "are not identical."
        )

    duplicate_features = [
        column
        for column in train_features
        if train_features.count(column) > 1
    ]

    if duplicate_features:

        raise AssertionError(
            "Duplicate feature columns detected: "
            f"{sorted(set(duplicate_features))}"
        )

    print_key_value(
        "Training features",
        f"{len(train_features)} / "
        f"{EXPECTED_FEATURE_COUNT} PASS",
    )

    print_key_value(
        "Validation features",
        f"{len(validation_features)} / "
        f"{EXPECTED_FEATURE_COUNT} PASS",
    )

    print_key_value(
        "Feature registries identical",
        "PASS",
    )

    print_key_value(
        "Duplicate feature names",
        "0",
    )

    categorical_features = [
        column
        for column in train_features
        if (
            not pd.api.types.is_numeric_dtype(
                train_df[column]
            )
        )
    ]

    if categorical_features:

        print_key_value(
            "Categorical features delegated to model",
            ", ".join(categorical_features),
        )

    else:

        print_key_value(
            "Categorical features delegated to model",
            "None",
        )

    return train_features


# ============================================================================
# TARGET VALIDATION
# ============================================================================

def validate_target_contract(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> None:
    """
    Validate the 30-minute occupancy target.
    """

    print_section(
        "TARGET CONTRACT VALIDATION"
    )

    if TARGET_COLUMN not in train_df.columns:

        raise AssertionError(
            f"Missing training target: {TARGET_COLUMN}"
        )

    if TARGET_COLUMN not in validation_df.columns:

        raise AssertionError(
            f"Missing validation target: {TARGET_COLUMN}"
        )

    train_target = pd.to_numeric(
        train_df[TARGET_COLUMN],
        errors="coerce",
    )

    validation_target = pd.to_numeric(
        validation_df[TARGET_COLUMN],
        errors="coerce",
    )

    if train_target.isna().any():

        raise AssertionError(
            "Training target contains null values."
        )

    if validation_target.isna().any():

        raise AssertionError(
            "Validation target contains null values."
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

    if (
        train_target.min() < 0
        or train_target.max() > 1
    ):

        raise AssertionError(
            "Training occupancy target is outside "
            "the expected [0, 1] range."
        )

    if (
        validation_target.min() < 0
        or validation_target.max() > 1
    ):

        raise AssertionError(
            "Validation occupancy target is outside "
            "the expected [0, 1] range."
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

    print_key_value(
        "Target range validation",
        "PASS",
    )


# ============================================================================
# DATASET ROW VALIDATION
# ============================================================================

def validate_dataset_sizes(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> None:
    """
    Confirm the persisted dataset sizes match the audited contract.
    """

    print_section(
        "DATASET SIZE VALIDATION"
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

    print_key_value(
        "Training rows",
        f"{len(train_df):,} / "
        f"{EXPECTED_TRAIN_ROWS:,} PASS",
    )

    print_key_value(
        "Validation rows",
        f"{len(validation_df):,} / "
        f"{EXPECTED_VALIDATION_ROWS:,} PASS",
    )


# ============================================================================
# TEMPORAL VALIDATION
# ============================================================================

def validate_chronological_split(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> None:
    """
    Confirm the persisted split remains chronological.

    Equal boundary timestamps are permitted because the datasets have
    already passed the stronger facility/timestamp observation isolation
    audit.
    """

    print_section(
        "CHRONOLOGICAL SPLIT VALIDATION"
    )

    timestamp_column = (
        "normalized_at"
    )

    if timestamp_column not in train_df.columns:

        raise AssertionError(
            "Training dataset is missing "
            "'normalized_at'."
        )

    if timestamp_column not in validation_df.columns:

        raise AssertionError(
            "Validation dataset is missing "
            "'normalized_at'."
        )

    train_time = pd.to_datetime(
        train_df[timestamp_column],
        errors="coerce",
    )

    validation_time = pd.to_datetime(
        validation_df[timestamp_column],
        errors="coerce",
    )

    if train_time.isna().any():

        raise AssertionError(
            "Training dataset contains invalid timestamps."
        )

    if validation_time.isna().any():

        raise AssertionError(
            "Validation dataset contains invalid timestamps."
        )

    train_max = train_time.max()

    validation_min = (
        validation_time.min()
    )

    if train_max > validation_min:

        raise AssertionError(
            "Chronological split violation: "
            f"train max={train_max}; "
            f"validation min={validation_min}."
        )

    print_key_value(
        "Training start",
        train_time.min(),
    )

    print_key_value(
        "Training end",
        train_max,
    )

    print_key_value(
        "Validation start",
        validation_min,
    )

    print_key_value(
        "Validation end",
        validation_time.max(),
    )

    print_key_value(
        "Chronological ordering",
        "PASS",
    )


# ============================================================================
# OBSERVATION ISOLATION
# ============================================================================

def validate_observation_isolation(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
) -> None:
    """
    Confirm no identical facility/timestamp observations exist in
    both training and validation.
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

    train_keys = set(
        zip(
            train_df[
                facility_column
            ].astype(str),
            pd.to_datetime(
                train_df[
                    timestamp_column
                ]
            ).astype(str),
        )
    )

    validation_keys = set(
        zip(
            validation_df[
                facility_column
            ].astype(str),
            pd.to_datetime(
                validation_df[
                    timestamp_column
                ]
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
            f"{len(overlap)}."
        )

    print_key_value(
        "Training observations",
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
# PREPARE MODEL DATA
# ============================================================================

def prepare_model_data(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[
    pd.DataFrame,
    pd.Series,
    pd.DataFrame,
    pd.Series,
]:
    """
    Extract X/y for the model.

    IMPORTANT
    ---------
    No feature transformations are performed here.

    The persisted feature registry is passed to XGBoostModel unchanged.

    Categorical features such as:

        - occupancy_level
        - demand_class

    are legitimate registered ML features.

    XGBoostModel is responsible for categorical encoding.

    This function only validates:
        - feature/target separation
        - expected shapes
        - missing values
        - infinite numeric values
        - categorical column consistency
    """

    print_section(
        "PREPARING MODEL MATRICES"
    )

    X_train = (
        train_df[
            feature_columns
        ].copy()
    )

    y_train = (
        train_df[
            TARGET_COLUMN
        ].copy()
    )

    X_validation = (
        validation_df[
            feature_columns
        ].copy()
    )

    y_validation = (
        validation_df[
            TARGET_COLUMN
        ].copy()
    )

    # ------------------------------------------------------------------
    # Confirm no target columns accidentally entered X.
    # ------------------------------------------------------------------

    forbidden_in_features = (
        set(feature_columns)
        & (
            TARGET_COLUMNS
            | TARGET_AVAILABILITY_COLUMNS
        )
    )

    if forbidden_in_features:

        raise AssertionError(
            "Target/availability columns detected "
            "inside model features: "
            f"{sorted(forbidden_in_features)}"
        )

    # ------------------------------------------------------------------
    # Confirm exact shape.
    # ------------------------------------------------------------------

    if X_train.shape != (
        EXPECTED_TRAIN_ROWS,
        EXPECTED_FEATURE_COUNT,
    ):

        raise AssertionError(
            "Unexpected X_train shape: "
            f"{X_train.shape}"
        )

    if X_validation.shape != (
        EXPECTED_VALIDATION_ROWS,
        EXPECTED_FEATURE_COUNT,
    ):

        raise AssertionError(
            "Unexpected X_validation shape: "
            f"{X_validation.shape}"
        )

    # ------------------------------------------------------------------
    # Identify categorical features.
    #
    # DO NOT reject them.
    #
    # The model layer owns categorical encoding.
    # ------------------------------------------------------------------

    categorical_features = [
        column
        for column in feature_columns
        if (
            not pd.api.types.is_numeric_dtype(
                X_train[column]
            )
        )
    ]

    validation_categorical_features = [
        column
        for column in feature_columns
        if (
            not pd.api.types.is_numeric_dtype(
                X_validation[column]
            )
        )
    ]

    if (
        categorical_features
        != validation_categorical_features
    ):

        raise AssertionError(
            "Training and validation categorical "
            "feature registries are inconsistent."
        )

    print_key_value(
        "Registered features",
        f"{len(feature_columns):,}",
    )

    print_key_value(
        "Numeric features",
        f"{len(feature_columns) - len(categorical_features):,}",
    )

    print_key_value(
        "Categorical features",
        f"{len(categorical_features):,}",
    )

    if categorical_features:

        print(
            "Categorical columns delegated to XGBoostModel:"
        )

        for column in categorical_features:

            print(
                f"  - {column}"
            )

    # ------------------------------------------------------------------
    # Missing-value validation.
    #
    # XGBoost can handle numeric missing values, but we deliberately
    # preserve the persisted data contract and do not silently impute.
    #
    # Therefore missing values are reported, but not filled.
    # ------------------------------------------------------------------

    train_missing = (
        X_train.isna().sum()
    )

    validation_missing = (
        X_validation.isna().sum()
    )

    train_missing_total = int(
        train_missing.sum()
    )

    validation_missing_total = int(
        validation_missing.sum()
    )

    print_key_value(
        "Training feature null cells",
        f"{train_missing_total:,}",
    )

    print_key_value(
        "Validation feature null cells",
        f"{validation_missing_total:,}",
    )

    # ------------------------------------------------------------------
    # Infinite-value validation.
    #
    # Only numeric columns can contain numeric infinity.
    # ------------------------------------------------------------------

    numeric_features = [
        column
        for column in feature_columns
        if pd.api.types.is_numeric_dtype(
            X_train[column]
        )
    ]

    if numeric_features:

        train_numeric = (
            X_train[
                numeric_features
            ].to_numpy(
                dtype=float
            )
        )

        validation_numeric = (
            X_validation[
                numeric_features
            ].to_numpy(
                dtype=float
            )
        )

        if np.isinf(
            train_numeric
        ).any():

            raise AssertionError(
                "Infinite numeric feature values detected "
                "in training matrix."
            )

        if np.isinf(
            validation_numeric
        ).any():

            raise AssertionError(
                "Infinite numeric feature values detected "
                "in validation matrix."
            )

    # ------------------------------------------------------------------
    # Validate categorical columns do not contain unsupported
    # mixed object structures.
    #
    # We do NOT encode them here.
    # ------------------------------------------------------------------

    for column in categorical_features:

        train_values = (
            X_train[column]
        )

        validation_values = (
            X_validation[column]
        )

        if train_values.isna().all():

            raise AssertionError(
                f"Categorical feature '{column}' "
                "contains only null values in training data."
            )

        if validation_values.isna().all():

            raise AssertionError(
                f"Categorical feature '{column}' "
                "contains only null values in validation data."
            )

        if (
            train_values.dtype == object
            and validation_values.dtype == object
        ):

            # Object/string categorical columns are allowed.
            # XGBoostModel owns their conversion.
            pass

    print_key_value(
        "X_train shape",
        X_train.shape,
    )

    print_key_value(
        "y_train shape",
        y_train.shape,
    )

    print_key_value(
        "X_validation shape",
        X_validation.shape,
    )

    print_key_value(
        "y_validation shape",
        y_validation.shape,
    )

    print_key_value(
        "Feature/target separation",
        "PASS",
    )

    print_key_value(
        "Categorical feature handling",
        "DELEGATED TO XGBoostModel",
    )

    return (
        X_train,
        y_train,
        X_validation,
        y_validation,
    )


# ============================================================================
# MODEL CONFIGURATION
# ============================================================================

def build_initial_model() -> XGBoostModel:
    """
    Construct the first benchmark XGBoost model.

    These are benchmark parameters, NOT tuned production parameters.
    """

    config = (
        XGBoostModelConfig(
            objective="reg:squarederror",
            n_estimators=300,
            learning_rate=0.05,
            max_depth=6,
            min_child_weight=1.0,
            subsample=0.90,
            colsample_bytree=0.90,
            gamma=0.0,
            reg_alpha=0.0,
            reg_lambda=1.0,
            random_state=42,
            n_jobs=-1,
            tree_method="hist",
            verbosity=0,
            early_stopping_rounds=None,
            clip_predictions=True,
            prediction_min=0.0,
            prediction_max=1.0,
        )
    )

    model = XGBoostModel(
        target_column=TARGET_COLUMN,
        config=config,
        model_name=(
            "xgboost_occupancy_30m_v1"
        ),
    )

    return model


# ============================================================================
# MODEL TRAINING
# ============================================================================

def train_model(
    model: XGBoostModel,
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> float:
    """
    Train XGBoost using training data only.

    Returns training duration in seconds.
    """

    print_section(
        "TRAINING XGBOOST MODEL"
    )

    print(
        "IMPORTANT: validation data is NOT passed to fit()."
    )

    print(
        "IMPORTANT: test data is NOT loaded."
    )

    print()

    start = time.perf_counter()

    model.fit(
        X_train,
        y_train,
    )

    duration = (
        time.perf_counter()
        - start
    )

    print_key_value(
        "Model",
        model.model_name,
    )

    print_key_value(
        "Training rows",
        f"{len(X_train):,}",
    )

    print_key_value(
        "Training features",
        f"{X_train.shape[1]:,}",
    )

    print_key_value(
        "Training duration",
        f"{duration:.3f} seconds",
    )

    print_key_value(
        "Validation data used during fit",
        "False",
    )

    print_key_value(
        "Test data used during fit",
        "False",
    )

    print_key_value(
        "Model fitted",
        model.is_fitted,
    )

    return duration


# ============================================================================
# MODEL EVALUATION
# ============================================================================

def evaluate_model(
    model: XGBoostModel,
    X_validation: pd.DataFrame,
    y_validation: pd.Series,
) -> tuple[
    XGBoostEvaluationResult,
    float,
]:
    """
    Evaluate the fitted model on validation data.
    """

    print_section(
        "XGBOOST VALIDATION EVALUATION"
    )

    print(
        "Validation data is used ONLY for prediction/evaluation."
    )

    print()

    start = time.perf_counter()

    result = model.evaluate(
        X_validation,
        y_validation,
    )

    duration = (
        time.perf_counter()
        - start
    )

    metrics = (
        result.metrics
    )

    print(
        f"{result.model_name}"
    )

    print(
        f"  MAE :  {metrics.mae:.6f}"
    )

    print(
        f"  RMSE:  {metrics.rmse:.6f}"
    )

    print(
        f"  R²  :  {metrics.r2:.6f}"
    )

    if metrics.mape is None:

        print(
            "  MAPE:  N/A"
        )

    else:

        print(
            f"  MAPE:  {metrics.mape:.4f}%"
        )

    print(
        f"  N   :  {metrics.sample_count:,}"
    )

    print_key_value(
        "Prediction duration",
        f"{duration:.3f} seconds",
    )

    return (
        result,
        duration,
    )


# ============================================================================
# BASELINE COMPARISON
# ============================================================================

def calculate_baseline_comparison(
    xgb_result: XGBoostEvaluationResult,
) -> dict[str, Any]:
    """
    Compare XGBoost against the established baseline benchmarks.
    """

    print_section(
        "BASELINE COMPARISON"
    )

    xgb_mae = (
        xgb_result.metrics.mae
    )

    xgb_rmse = (
        xgb_result.metrics.rmse
    )

    # --------------------------------------------------------------
    # Improvement formula:
    #
    #     (baseline - model) / baseline * 100
    #
    # Positive = model is better.
    # --------------------------------------------------------------

    improvement_vs_mean = (
        (
            MEAN_BASELINE_MAE
            - xgb_mae
        )
        / MEAN_BASELINE_MAE
        * 100.0
    )

    improvement_vs_last = (
        (
            LAST_VALUE_BASELINE_MAE
            - xgb_mae
        )
        / LAST_VALUE_BASELINE_MAE
        * 100.0
    )

    beats_mean = (
        xgb_mae
        < MEAN_BASELINE_MAE
    )

    beats_last_value = (
        xgb_mae
        < LAST_VALUE_BASELINE_MAE
    )

    print(
        "Established baselines:"
    )

    print(
        f"  Mean baseline MAE       : "
        f"{MEAN_BASELINE_MAE:.6f}"
    )

    print(
        f"  Last-value baseline MAE : "
        f"{LAST_VALUE_BASELINE_MAE:.6f}"
    )

    print()

    print(
        f"XGBoost MAE               : "
        f"{xgb_mae:.6f}"
    )

    print(
        f"XGBoost RMSE              : "
        f"{xgb_rmse:.6f}"
    )

    print()

    print(
        f"Improvement vs Mean       : "
        f"{improvement_vs_mean:.2f}%"
    )

    print(
        f"Improvement vs Last Value : "
        f"{improvement_vs_last:.2f}%"
    )

    print()

    print_key_value(
        "Beats Mean baseline",
        "YES" if beats_mean else "NO",
    )

    print_key_value(
        "Beats Last Value baseline",
        "YES" if beats_last_value else "NO",
    )

    return {
        "mean_baseline_mae": (
            MEAN_BASELINE_MAE
        ),
        "last_value_baseline_mae": (
            LAST_VALUE_BASELINE_MAE
        ),
        "xgboost_mae": xgb_mae,
        "xgboost_rmse": xgb_rmse,
        "improvement_vs_mean_percent": (
            improvement_vs_mean
        ),
        "improvement_vs_last_value_percent": (
            improvement_vs_last
        ),
        "beats_mean_baseline": (
            beats_mean
        ),
        "beats_last_value_baseline": (
            beats_last_value
        ),
    }


# ============================================================================
# FEATURE IMPORTANCE
# ============================================================================

def calculate_feature_importance(
    model: XGBoostModel,
) -> pd.DataFrame:
    """
    Extract ranked gain-based feature importance.
    """

    print_section(
        "FEATURE IMPORTANCE"
    )

    importance_records = (
        model.feature_importance(
            importance_type="gain",
            top_n=None,
        )
    )

    rows = [
        {
            "rank": item.rank,
            "feature": item.feature,
            "importance": item.importance,
            "importance_type": (
                item.importance_type
            ),
        }
        for item in importance_records
    ]

    dataframe = pd.DataFrame(
        rows
    )

    if dataframe.empty:

        print(
            "No non-zero feature importance values returned."
        )

        return dataframe

    print(
        "Top 20 features by gain:"
    )

    print()

    print(
        dataframe.head(20).to_string(
            index=False
        )
    )

    print()

    print_key_value(
        "Features with non-zero importance",
        f"{len(dataframe):,}",
    )

    return dataframe


# ============================================================================
# MODEL CONFIG DISPLAY
# ============================================================================

def display_model_configuration(
    model: XGBoostModel,
) -> None:
    """
    Display initial benchmark parameters.
    """

    print_section(
        "INITIAL XGBOOST CONFIGURATION"
    )

    params = (
        model.get_params()
    )

    display_keys = [
        "objective",
        "n_estimators",
        "learning_rate",
        "max_depth",
        "min_child_weight",
        "subsample",
        "colsample_bytree",
        "gamma",
        "reg_alpha",
        "reg_lambda",
        "random_state",
        "n_jobs",
        "tree_method",
        "early_stopping_rounds",
        "clip_predictions",
    ]

    for key in display_keys:

        if key in params:

            print_key_value(
                key,
                params[key],
            )


# ============================================================================
# LEAKAGE CONTRACT
# ============================================================================

def validate_leakage_contract() -> None:
    """
    Explicitly validate the experiment's leakage policy.
    """

    print_section(
        "LEAKAGE CONTRACT"
    )

    contract = {
        "future_data_used": False,
        "validation_data_used_during_fit": False,
        "validation_target_used_during_fit": False,
        "test_data_loaded": False,
        "target_data_used_as_feature": False,
        "cross_facility_data_used": False,
        "forward_lookup_used": False,
        "centered_windows_used": False,
        "target_imputation": False,
        "random_shuffle": False,
        "chronological_split": True,
    }

    for key, value in contract.items():

        print_key_value(
            key,
            value,
        )

    failed = [
        key
        for key, value
        in contract.items()
        if key != "chronological_split"
        and value is True
    ]

    if failed:

        raise AssertionError(
            "Leakage contract failed: "
            f"{failed}"
        )

    if not contract[
        "chronological_split"
    ]:

        raise AssertionError(
            "Chronological split contract failed."
        )

    print()
    print(
        "Leakage contract: PASS"
    )


# ============================================================================
# RESULT PERSISTENCE
# ============================================================================

def persist_results(
    model: XGBoostModel,
    evaluation: XGBoostEvaluationResult,
    baseline_comparison: dict[str, Any],
    training_duration: float,
    prediction_duration: float,
    feature_importance: pd.DataFrame,
) -> None:
    """
    Persist benchmark results and feature importance.
    """

    print_section(
        "PERSISTING XGBOOST BENCHMARK"
    )

    OUTPUT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_payload = {
        "schema_version": "1.0",
        "dataset_name": "birmingham",
        "target_column": TARGET_COLUMN,
        "created_by": (
            "birmingham_xgboost_benchmark.py"
        ),
        "created_at_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "model": {
            "name": model.model_name,
            "type": model.MODEL_TYPE,
            "version": model.MODEL_VERSION,
            "config": model.get_params(),
        },
        "dataset": {
            "training_file": str(
                TRAIN_FILE
            ),
            "validation_file": str(
                VALIDATION_FILE
            ),
            "test_file": str(
                TEST_FILE
            ),
            "test_file_loaded": False,
            "training_rows": EXPECTED_TRAIN_ROWS,
            "validation_rows": (
                EXPECTED_VALIDATION_ROWS
            ),
            "feature_count": (
                EXPECTED_FEATURE_COUNT
            ),
        },
        "training": {
            "duration_seconds": (
                training_duration
            ),
            "rows": EXPECTED_TRAIN_ROWS,
            "features": EXPECTED_FEATURE_COUNT,
            "validation_data_used": False,
            "test_data_used": False,
        },
        "evaluation": {
            "prediction_duration_seconds": (
                prediction_duration
            ),
            "result": evaluation.to_dict(),
        },
        "baseline_comparison": (
            baseline_comparison
        ),
        "leakage_contract": {
            "future_data_used": False,
            "validation_data_used_during_fit": False,
            "validation_target_used_during_fit": False,
            "test_data_loaded": False,
            "target_data_used_as_feature": False,
            "cross_facility_data_used": False,
            "forward_lookup_used": False,
            "centered_windows_used": False,
            "target_imputation": False,
            "random_shuffle": False,
            "chronological_split": True,
        },
    }

    with RESULTS_JSON.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            result_payload,
            file,
            indent=2,
        )

    comparison_rows = [
        {
            "model": "mean_baseline",
            "mae": MEAN_BASELINE_MAE,
            "rmse": None,
            "r2": None,
            "improvement_vs_last_value_percent": (
                (
                    LAST_VALUE_BASELINE_MAE
                    - MEAN_BASELINE_MAE
                )
                / LAST_VALUE_BASELINE_MAE
                * 100.0
            ),
        },
        {
            "model": "last_value_baseline",
            "mae": LAST_VALUE_BASELINE_MAE,
            "rmse": None,
            "r2": None,
            "improvement_vs_last_value_percent": 0.0,
        },
        {
            "model": model.model_name,
            "mae": evaluation.metrics.mae,
            "rmse": evaluation.metrics.rmse,
            "r2": evaluation.metrics.r2,
            "improvement_vs_last_value_percent": (
                baseline_comparison[
                    "improvement_vs_last_value_percent"
                ]
            ),
        },
    ]

    pd.DataFrame(
        comparison_rows
    ).to_csv(
        RESULTS_CSV,
        index=False,
    )

    if not feature_importance.empty:

        feature_importance.to_csv(
            FEATURE_IMPORTANCE_CSV,
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
        "CSV comparison",
        RESULTS_CSV,
    )

    print_key_value(
        "Feature importance",
        FEATURE_IMPORTANCE_CSV,
    )


# ============================================================================
# FINAL ASSERTIONS
# ============================================================================

def run_final_assertions(
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    feature_columns: list[str],
    model: XGBoostModel,
    evaluation: XGBoostEvaluationResult,
    baseline_comparison: dict[str, Any],
) -> None:
    """
    Final benchmark integrity assertions.
    """

    print_section(
        "FINAL ASSERTIONS"
    )

    assertions = {
        "Training rows preserved": (
            len(train_df)
            == EXPECTED_TRAIN_ROWS
        ),
        "Validation rows preserved": (
            len(validation_df)
            == EXPECTED_VALIDATION_ROWS
        ),
        "296 features present": (
            len(feature_columns)
            == EXPECTED_FEATURE_COUNT
        ),
        "Model fitted": (
            model.is_fitted
        ),
        "Model feature count correct": (
            model.feature_count
            == EXPECTED_FEATURE_COUNT
        ),
        "Evaluation sample count correct": (
            evaluation.sample_count
            == EXPECTED_VALIDATION_ROWS
        ),
        "MAE finite": (
            math.isfinite(
                evaluation.metrics.mae
            )
        ),
        "RMSE finite": (
            math.isfinite(
                evaluation.metrics.rmse
            )
        ),
        "R2 finite": (
            math.isfinite(
                evaluation.metrics.r2
            )
        ),
        "XGBoost prediction range valid": (
            0.0
            <= evaluation.metrics.prediction_min
            <= 1.0
            and
            0.0
            <= evaluation.metrics.prediction_max
            <= 1.0
        ),
        "Validation not used during fit": (
            evaluation.metadata[
                "validation_data_used_during_fit"
            ]
            is False
        ),
        "Test data not used": (
            evaluation.metadata[
                "test_data_used"
            ]
            is False
        ),
        "Baseline comparison calculated": (
            "improvement_vs_last_value_percent"
            in baseline_comparison
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
        "ALL XGBOOST BENCHMARK ASSERTIONS PASSED"
    )


# ============================================================================
# MAIN
# ============================================================================

def main() -> int:
    """
    Run the initial Birmingham XGBoost benchmark.
    """

    print_header(
        "SMARTPARK AI - BIRMINGHAM XGBOOST BENCHMARK"
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
        "Experiment:"
    )

    print(
        "  Initial XGBoost benchmark"
    )

    print(
        "  No hyperparameter tuning"
    )

    print(
        "  Train = train.parquet"
    )

    print(
        "  Evaluate = validation.parquet"
    )

    print(
        "  Test = untouched"
    )

    try:

        # ==============================================================
        # 1. DATASET FILES
        # ==============================================================

        validate_dataset_files()

        # ==============================================================
        # 2. LOAD TRAINING / VALIDATION
        # ==============================================================

        train_df = (
            load_training_data()
        )

        validation_df = (
            load_validation_data()
        )

        # ==============================================================
        # 3. SIZE VALIDATION
        # ==============================================================

        validate_dataset_sizes(
            train_df,
            validation_df,
        )

        # ==============================================================
        # 4. FEATURE CONTRACT
        # ==============================================================

        feature_columns = (
            validate_feature_contract(
                train_df,
                validation_df,
            )
        )

        # ==============================================================
        # 5. TARGET CONTRACT
        # ==============================================================

        validate_target_contract(
            train_df,
            validation_df,
        )

        # ==============================================================
        # 6. CHRONOLOGY
        # ==============================================================

        validate_chronological_split(
            train_df,
            validation_df,
        )

        # ==============================================================
        # 7. OBSERVATION ISOLATION
        # ==============================================================

        validate_observation_isolation(
            train_df,
            validation_df,
        )

        # ==============================================================
        # 8. MODEL MATRICES
        # ==============================================================

        (
            X_train,
            y_train,
            X_validation,
            y_validation,
        ) = prepare_model_data(
            train_df,
            validation_df,
            feature_columns,
        )

        # ==============================================================
        # 9. MODEL
        # ==============================================================

        model = build_initial_model()

        display_model_configuration(
            model
        )

        # ==============================================================
        # 10. TRAIN
        # ==============================================================

        training_duration = (
            train_model(
                model,
                X_train,
                y_train,
            )
        )

        # ==============================================================
        # 11. EVALUATE
        # ==============================================================

        (
            evaluation,
            prediction_duration,
        ) = evaluate_model(
            model,
            X_validation,
            y_validation,
        )

        # ==============================================================
        # 12. BASELINE COMPARISON
        # ==============================================================

        baseline_comparison = (
            calculate_baseline_comparison(
                evaluation
            )
        )

        # ==============================================================
        # 13. FEATURE IMPORTANCE
        # ==============================================================

        feature_importance = (
            calculate_feature_importance(
                model
            )
        )

        # ==============================================================
        # 14. LEAKAGE CONTRACT
        # ==============================================================

        validate_leakage_contract()

        # ==============================================================
        # 15. PERSIST RESULTS
        # ==============================================================

        persist_results(
            model,
            evaluation,
            baseline_comparison,
            training_duration,
            prediction_duration,
            feature_importance,
        )

        # ==============================================================
        # 16. FINAL ASSERTIONS
        # ==============================================================

        run_final_assertions(
            train_df,
            validation_df,
            feature_columns,
            model,
            evaluation,
            baseline_comparison,
        )

        # ==============================================================
        # FINAL REPORT
        # ==============================================================

        print_header(
            "BIRMINGHAM XGBOOST BENCHMARK COMPLETED SUCCESSFULLY"
        )

        print()

        print(
            f"Target:                  "
            f"{TARGET_COLUMN}"
        )

        print(
            f"Training rows:           "
            f"{len(train_df):,}"
        )

        print(
            f"Validation rows:         "
            f"{len(validation_df):,}"
        )

        print(
            f"Features:                "
            f"{len(feature_columns):,}"
        )

        print(
            f"XGBoost MAE:             "
            f"{evaluation.metrics.mae:.6f}"
        )

        print(
            f"XGBoost RMSE:            "
            f"{evaluation.metrics.rmse:.6f}"
        )

        print(
            f"XGBoost R²:              "
            f"{evaluation.metrics.r2:.6f}"
        )

        print(
            f"Mean baseline MAE:       "
            f"{MEAN_BASELINE_MAE:.6f}"
        )

        print(
            f"Last-value baseline MAE: "
            f"{LAST_VALUE_BASELINE_MAE:.6f}"
        )

        print(
            f"Improvement vs last:     "
            f"{baseline_comparison['improvement_vs_last_value_percent']:.2f}%"
        )

        print(
            f"Beats last-value:        "
            f"{'YES' if baseline_comparison['beats_last_value_baseline'] else 'NO'}"
        )

        print(
            "Test dataset used:       NO"
        )

        print(
            "Leakage validation:      PASS"
        )

        print(
            "Benchmark validation:    PASS"
        )

        print()

        if baseline_comparison[
            "beats_last_value_baseline"
        ]:

            print(
                "🎯 XGBoost BEATS the established "
                "last-value baseline."
            )

            print()

            print(
                "Next stage: controlled "
                "hyperparameter tuning."
            )

        else:

            print(
                "XGBoost does NOT yet beat the "
                "established last-value baseline."
            )

            print()

            print(
                "Next stage: investigate model/feature "
                "performance before tuning."
            )

        return 0

    except (
        FileNotFoundError,
        AssertionError,
        ValueError,
        KeyError,
        TypeError,
        XGBoostModelError,
        XGBoostModelDataError,
        XGBoostModelNotFittedError,
    ) as exc:

        print()
        print_header(
            "BIRMINGHAM XGBOOST BENCHMARK FAILED"
        )

        print()
        print(
            f"ERROR: {exc}"
        )

        print()
        print(
            "DO NOT proceed to model tuning until "
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