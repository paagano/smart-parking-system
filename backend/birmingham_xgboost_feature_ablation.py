"""
SmartPark AI
Birmingham XGBoost Feature Ablation Experiment

Purpose
-------
Determine how much predictive performance is contributed by
current-state parking features versus the remaining historical,
temporal, and contextual features.

IMPORTANT EXPERIMENT CONTRACT
-----------------------------
1. Uses ONLY persisted Birmingham training datasets.
2. Uses train.parquet for model fitting.
3. Uses validation.parquet for evaluation.
4. NEVER loads test.parquet.
5. Does NOT rebuild the feature pipeline.
6. Does NOT modify any persisted datasets.
7. Does NOT modify XGBoostModel.
8. Uses the existing 296-feature registry from the persisted
   training dataset manifest.
9. Categorical features remain delegated to XGBoostModel.
10. The same XGBoost configuration is used for both experiments.
11. Validation data is NEVER passed to model.fit().
12. No hyperparameter tuning is performed.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PROCESSED_ROOT = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
)

TARGET_NAME = "target_occupancy_rate_30m"

TRAIN_PATH = (
    PROCESSED_ROOT
    / TARGET_NAME
    / "train.parquet"
)

VALIDATION_PATH = (
    PROCESSED_ROOT
    / TARGET_NAME
    / "validation.parquet"
)

TEST_PATH = (
    PROCESSED_ROOT
    / TARGET_NAME
    / "test.parquet"
)

MANIFEST_PATH = (
    PROCESSED_ROOT
    / "training_dataset_manifest.json"
)

OUTPUT_DIR = (
    PROCESSED_ROOT
    / "xgboost_feature_ablation"
)

RESULTS_JSON = (
    OUTPUT_DIR
    / "xgboost_feature_ablation_results.json"
)

RESULTS_CSV = (
    OUTPUT_DIR
    / "xgboost_feature_ablation_results.csv"
)


# ============================================================================
# CURRENT-STATE FEATURE CONTRACT
# ============================================================================

CURRENT_STATE_FEATURES: tuple[str, ...] = (
    "capacity_utilization",
    "availability_rate",
    "occupied_ratio",
    "available_ratio",
    "vacancy_ratio",
    "occupancy_level",
    "occupancy_capacity_difference",
    "occupancy_within_capacity",
    "occupancy_state_valid",
    "demand_level",
    "calculated_demand_level",
    "demand_pressure",
    "demand_excess_pressure",
    "remaining_capacity_ratio",
    "availability_pressure",
    "is_low_availability",
    "is_critical_availability",
    "is_full",
    "is_zero_capacity",
    "is_capacity_exceeded",
    "demand_class",
    "demand_class_code",
    "is_low_demand",
    "is_moderate_demand",
    "is_high_demand",
    "is_very_high_demand",
)


# ============================================================================
# DATA CLASSES
# ============================================================================


@dataclass(frozen=True)
class ExperimentResult:
    experiment_name: str
    description: str

    feature_count: int
    categorical_feature_count: int

    training_rows: int
    validation_rows: int

    mae: float
    rmse: float
    r2: float
    mape: float

    target_mean_training: float
    target_mean_validation: float

    prediction_min: float
    prediction_max: float

    training_fit_validation_used: bool
    test_dataset_used: bool

    leakage_contract_passed: bool


# ============================================================================
# PRINTING HELPERS
# ============================================================================


def section(title: str) -> None:
    print()
    print("--- " + title + " ---")


def print_check(
    label: str,
    passed: bool,
) -> None:
    print(
        f"{label:<45}: "
        f"{'PASS' if passed else 'FAIL'}"
    )


# ============================================================================
# MANIFEST
# ============================================================================


def load_manifest() -> dict[str, Any]:
    if not MANIFEST_PATH.exists():
        raise RuntimeError(
            "Training dataset manifest does not exist: "
            f"{MANIFEST_PATH}"
        )

    with MANIFEST_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:
        manifest = json.load(handle)

    return manifest


# ============================================================================
# DATASET LOADING
# ============================================================================


def validate_dataset_files() -> None:
    section("DATASET FILE VALIDATION")

    print(
        f"Processed dataset root                  : "
        f"{PROCESSED_ROOT}"
    )

    print(
        f"Training dataset                        : "
        f"{TRAIN_PATH}"
    )

    print(
        f"Validation dataset                      : "
        f"{VALIDATION_PATH}"
    )

    print(
        f"Test dataset                            : "
        f"{TEST_PATH}"
    )

    train_exists = TRAIN_PATH.exists()
    validation_exists = VALIDATION_PATH.exists()
    test_exists = TEST_PATH.exists()

    print_check(
        "Training file exists",
        train_exists,
    )

    print_check(
        "Validation file exists",
        validation_exists,
    )

    print_check(
        "Test file exists",
        test_exists,
    )

    if not train_exists:
        raise RuntimeError(
            "Training dataset does not exist."
        )

    if not validation_exists:
        raise RuntimeError(
            "Validation dataset does not exist."
        )

    if not test_exists:
        raise RuntimeError(
            "Test dataset is missing. "
            "The ablation experiment requires the "
            "persisted test dataset to remain available, "
            "although it will NOT be loaded."
        )

    print(
        "Test dataset will NOT be loaded."
    )


def load_training_and_validation() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:
    section("LOADING TRAINING DATASET")

    train = pd.read_parquet(
        TRAIN_PATH
    )

    print(
        f"Rows                                    : "
        f"{len(train):,}"
    )

    print(
        f"Columns                                 : "
        f"{len(train.columns):,}"
    )

    section("LOADING VALIDATION DATASET")

    validation = pd.read_parquet(
        VALIDATION_PATH
    )

    print(
        f"Rows                                    : "
        f"{len(validation):,}"
    )

    print(
        f"Columns                                 : "
        f"{len(validation.columns):,}"
    )

    return train, validation


# ============================================================================
# FEATURE CONTRACT
# ============================================================================


def get_registered_features(
    manifest: dict[str, Any],
) -> list[str]:

    features = manifest.get(
        "feature_columns"
    )

    if not isinstance(
        features,
        list,
    ):
        raise RuntimeError(
            "Manifest does not contain a valid "
            "'feature_columns' list."
        )

    return [
        str(column)
        for column in features
    ]


def validate_feature_registry(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    registered_features: list[str],
) -> None:

    section("FEATURE REGISTRY VALIDATION")

    print(
        f"Registered features                     : "
        f"{len(registered_features)}"
    )

    train_features = [
        column
        for column in train.columns
        if column not in {
            TARGET_NAME,
        }
        and column in registered_features
    ]

    validation_features = [
        column
        for column in validation.columns
        if column not in {
            TARGET_NAME,
        }
        and column in registered_features
    ]

    train_registry_ok = (
        set(train_features)
        == set(registered_features)
    )

    validation_registry_ok = (
        set(validation_features)
        == set(registered_features)
    )

    print_check(
        "Training feature registry",
        train_registry_ok,
    )

    print_check(
        "Validation feature registry",
        validation_registry_ok,
    )

    if not train_registry_ok:
        missing = sorted(
            set(registered_features)
            - set(train_features)
        )

        extra = sorted(
            set(train_features)
            - set(registered_features)
        )

        raise RuntimeError(
            "Training feature registry mismatch. "
            f"Missing={missing}; Extra={extra}"
        )

    if not validation_registry_ok:
        missing = sorted(
            set(registered_features)
            - set(validation_features)
        )

        extra = sorted(
            set(validation_features)
            - set(registered_features)
        )

        raise RuntimeError(
            "Validation feature registry mismatch. "
            f"Missing={missing}; Extra={extra}"
        )

    if len(
        registered_features
    ) != len(
        set(registered_features)
    ):
        raise RuntimeError(
            "Manifest feature registry contains "
            "duplicate feature names."
        )

    print(
        "Train/validation feature registry     : "
        "IDENTICAL"
    )


# ============================================================================
# TARGET VALIDATION
# ============================================================================


def validate_target(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    section("TARGET CONTRACT VALIDATION")

    if TARGET_NAME not in train.columns:
        raise RuntimeError(
            f"Target column '{TARGET_NAME}' "
            "is missing from training dataset."
        )

    if TARGET_NAME not in validation.columns:
        raise RuntimeError(
            f"Target column '{TARGET_NAME}' "
            "is missing from validation dataset."
        )

    y_train = train[TARGET_NAME]
    y_validation = validation[TARGET_NAME]

    print(
        f"Training target rows                    : "
        f"{len(y_train):,}"
    )

    print(
        f"Validation target rows                  : "
        f"{len(y_validation):,}"
    )

    print(
        f"Training target nulls                   : "
        f"{int(y_train.isna().sum()):,}"
    )

    print(
        f"Validation target nulls                 : "
        f"{int(y_validation.isna().sum()):,}"
    )

    if y_train.isna().any():
        raise RuntimeError(
            "Training target contains null values."
        )

    if y_validation.isna().any():
        raise RuntimeError(
            "Validation target contains null values."
        )

    train_min = float(y_train.min())
    train_max = float(y_train.max())

    validation_min = float(
        y_validation.min()
    )
    validation_max = float(
        y_validation.max()
    )

    print(
        f"Training target mean                    : "
        f"{float(y_train.mean()):.6f}"
    )

    print(
        f"Validation target mean                  : "
        f"{float(y_validation.mean()):.6f}"
    )

    print(
        f"Training target range                   : "
        f"{train_min:.6f} -> {train_max:.6f}"
    )

    print(
        f"Validation target range                 : "
        f"{validation_min:.6f} -> "
        f"{validation_max:.6f}"
    )

    target_range_ok = (
        train_min >= 0.0
        and train_max <= 1.0
        and validation_min >= 0.0
        and validation_max <= 1.0
    )

    print_check(
        "Target range validation",
        target_range_ok,
    )

    if not target_range_ok:
        raise RuntimeError(
            "Target values fall outside expected "
            "occupancy range [0, 1]."
        )


# ============================================================================
# TEMPORAL VALIDATION
# ============================================================================


def identify_timestamp_column(
    dataframe: pd.DataFrame,
) -> str | None:

    candidates = (
        "normalized_at",
        "timestamp",
        "observation_timestamp",
        "observed_at",
        "datetime",
        "date_time",
    )

    for column in candidates:
        if column in dataframe.columns:
            return column

    return None


def validate_chronology(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    section("CHRONOLOGICAL SPLIT VALIDATION")

    timestamp_column = identify_timestamp_column(
        train
    )

    if timestamp_column is None:
        print(
            "Timestamp column not available in "
            "benchmark feature registry."
        )
        print(
            "Chronological validation delegated to "
            "persisted dataset integrity audit."
        )
        return

    train_time = pd.to_datetime(
        train[timestamp_column],
        errors="coerce",
    )

    validation_time = pd.to_datetime(
        validation[timestamp_column],
        errors="coerce",
    )

    if train_time.isna().any():
        raise RuntimeError(
            "Training timestamp column contains "
            "unparseable values."
        )

    if validation_time.isna().any():
        raise RuntimeError(
            "Validation timestamp column contains "
            "unparseable values."
        )

    train_min = train_time.min()
    train_max = train_time.max()

    validation_min = validation_time.min()
    validation_max = validation_time.max()

    print(
        f"Training start                          : "
        f"{train_min}"
    )

    print(
        f"Training end                            : "
        f"{train_max}"
    )

    print(
        f"Validation start                        : "
        f"{validation_min}"
    )

    print(
        f"Validation end                          : "
        f"{validation_max}"
    )

    chronological = (
        train_max <= validation_min
    )

    print_check(
        "Chronological ordering",
        chronological,
    )

    if not chronological:
        raise RuntimeError(
            "Training and validation datasets "
            "are not chronologically ordered."
        )


# ============================================================================
# OBSERVATION ISOLATION
# ============================================================================


def build_observation_keys(
    dataframe: pd.DataFrame,
) -> pd.Series:

    timestamp_column = identify_timestamp_column(
        dataframe
    )

    if (
        timestamp_column is not None
        and "source_facility_code" in dataframe.columns
    ):
        timestamp = pd.to_datetime(
            dataframe[timestamp_column],
            errors="coerce",
        ).astype("string")

        facility = dataframe[
            "source_facility_code"
        ].astype("string")

        return (
            facility
            + "|"
            + timestamp
        )

    if timestamp_column is not None:

        timestamp = pd.to_datetime(
            dataframe[timestamp_column],
            errors="coerce",
        ).astype("string")

        return timestamp

    return pd.Series(
        dataframe.index.astype(str),
        index=dataframe.index,
    )


def validate_observation_isolation(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    section(
        "TRAIN / VALIDATION OBSERVATION ISOLATION"
    )

    train_keys = set(
        build_observation_keys(train)
    )

    validation_keys = set(
        build_observation_keys(validation)
    )

    overlap = (
        train_keys
        & validation_keys
    )

    print(
        f"Training observations                   : "
        f"{len(train_keys):,}"
    )

    print(
        f"Validation observations                 : "
        f"{len(validation_keys):,}"
    )

    print(
        f"Train ∩ Validation                      : "
        f"{len(overlap):,}"
    )

    isolated = len(overlap) == 0

    print_check(
        "Observation isolation",
        isolated,
    )

    if not isolated:
        raise RuntimeError(
            "Training and validation datasets contain "
            "overlapping observation keys."
        )


# ============================================================================
# CURRENT-STATE FEATURE ANALYSIS
# ============================================================================


def determine_ablation_features(
    registered_features: list[str],
) -> tuple[list[str], list[str]]:

    current_state_present = [
        feature
        for feature in CURRENT_STATE_FEATURES
        if feature in registered_features
    ]

    retained_features = [
        feature
        for feature in registered_features
        if feature not in current_state_present
    ]

    return (
        current_state_present,
        retained_features,
    )


def print_ablation_contract(
    registered_features: list[str],
    removed_features: list[str],
    retained_features: list[str],
) -> None:

    section(
        "FEATURE ABLATION CONTRACT"
    )

    print(
        f"Original feature count                 : "
        f"{len(registered_features)}"
    )

    print(
        f"Current-state features identified      : "
        f"{len(removed_features)}"
    )

    print(
        f"Retained feature count                 : "
        f"{len(retained_features)}"
    )

    print()
    print(
        "Current-state features removed:"
    )

    for feature in removed_features:
        print(
            f"  - {feature}"
        )

    print()

    print(
        "No persisted dataset will be modified."
    )


# ============================================================================
# MODEL CONFIGURATION
# ============================================================================


def build_model(
    *,
    categorical_features: list[str],
) -> XGBoostModel:

    config = XGBoostModelConfig(
        objective="reg:squarederror",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        tree_method="hist",
        early_stopping_rounds=None,
        clip_predictions=True,
        categorical_features=tuple(
            categorical_features
        ),
    )

    return XGBoostModel(
        target_column=TARGET_NAME,
        config=config,
        model_name="xgboost_ablation",
    )


# ============================================================================
# MODEL MATRIX
# ============================================================================


def prepare_features(
    dataframe: pd.DataFrame,
    feature_columns: list[str],
) -> pd.DataFrame:

    missing = [
        column
        for column in feature_columns
        if column not in dataframe.columns
    ]

    if missing:
        raise RuntimeError(
            "Dataset is missing required feature "
            f"columns: {missing}"
        )

    result = dataframe[
        feature_columns
    ].copy()

    return result


def validate_feature_types(
    dataframe: pd.DataFrame,
    categorical_features: list[str],
) -> None:
    """
    Validate the feature dataframe before handing it to XGBoostModel.

    Contract:
    - Configured categorical columns may be non-numeric.
    - Numeric columns may contain NaN because XGBoost supports
      missing numeric values natively.
    - Positive/negative infinity is NOT permitted.
    - Other non-numeric columns are rejected.
    """

    categorical_set = set(
        categorical_features
    )

    non_numeric = [
        column
        for column in dataframe.columns
        if column not in categorical_set
        and not pd.api.types.is_numeric_dtype(
            dataframe[column]
        )
    ]

    if non_numeric:
        raise RuntimeError(
            "Non-numeric non-categorical features found: "
            f"{non_numeric}"
        )

    numeric_columns = [
        column
        for column in dataframe.columns
        if column not in categorical_set
    ]

    if not numeric_columns:
        return

    numeric_values = dataframe[
        numeric_columns
    ].to_numpy(
        dtype=float
    )

    infinite_mask = np.isinf(
        numeric_values
    )

    if infinite_mask.any():

        positions = np.argwhere(
            infinite_mask
        )

        offending_columns = sorted(
            {
                str(
                    numeric_columns[
                        int(position[1])
                    ]
                )
                for position in positions
            }
        )

        raise RuntimeError(
            "Positive/negative infinite values found "
            "in numeric model features: "
            f"{offending_columns}"
        )


# ============================================================================
# METRICS
# ============================================================================


def calculate_metrics(
    y_true: np.ndarray,
    predictions: np.ndarray,
) -> dict[str, float]:

    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    predictions = np.asarray(
        predictions,
        dtype=float,
    )

    errors = (
        predictions
        - y_true
    )

    mae = float(
        np.mean(
            np.abs(errors)
        )
    )

    rmse = float(
        np.sqrt(
            np.mean(
                errors ** 2
            )
        )
    )

    denominator = float(
        np.sum(
            (y_true - np.mean(y_true))
            ** 2
        )
    )

    if denominator == 0.0:
        r2 = 0.0
    else:
        r2 = float(
            1.0
            - (
                np.sum(
                    errors ** 2
                )
                / denominator
            )
        )

    non_zero = (
        np.abs(y_true)
        > 1e-12
    )

    if non_zero.any():
        mape = float(
            np.mean(
                np.abs(
                    (
                        y_true[non_zero]
                        - predictions[non_zero]
                    )
                    / y_true[non_zero]
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
        "sample_count": int(
            len(y_true)
        ),
    }


# ============================================================================
# SINGLE EXPERIMENT
# ============================================================================


def run_experiment(
    *,
    experiment_name: str,
    description: str,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    feature_columns: list[str],
    categorical_features: list[str],
) -> ExperimentResult:

    print()
    print(
        "=" * 78
    )

    print(
        f"EXPERIMENT: {experiment_name}"
    )

    print(
        "=" * 78
    )

    print(
        f"Description                             : "
        f"{description}"
    )

    print(
        f"Feature count                           : "
        f"{len(feature_columns)}"
    )

    print(
        f"Categorical feature count               : "
        f"{len(categorical_features)}"
    )

    X_train = prepare_features(
        train,
        feature_columns,
    )

    X_validation = prepare_features(
        validation,
        feature_columns,
    )

    y_train = train[
        TARGET_NAME
    ].to_numpy(
        dtype=float
    )

    y_validation = validation[
        TARGET_NAME
    ].to_numpy(
        dtype=float
    )

    validate_feature_types(
        X_train,
        categorical_features,
    )

    validate_feature_types(
        X_validation,
        categorical_features,
    )

    print(
        f"X_train shape                           : "
        f"{X_train.shape}"
    )

    print(
        f"X_validation shape                      : "
        f"{X_validation.shape}"
    )

    print(
        "Validation data passed to fit()         : "
        "NO"
    )

    print(
        "Test data loaded                        : "
        "NO"
    )

    model = build_model(
        categorical_features=(
            categorical_features
        ),
    )

    print()
    print(
        "Training XGBoost..."
    )

    model.fit(
        X_train,
        y_train,
    )

    print(
        "Training completed."
    )

    print()
    print(
        "Generating validation predictions..."
    )

    predictions = model.predict(
        X_validation
    )

    predictions = np.asarray(
        predictions,
        dtype=float,
    )

    if not np.isfinite(
        predictions
    ).all():

        raise RuntimeError(
            "Model produced NaN or infinite "
            "predictions."
        )

    metrics = calculate_metrics(
        y_validation,
        predictions,
    )

    print()
    print(
        "Validation metrics:"
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
        f"  N   :  {metrics['sample_count']:,}"
    )

    return ExperimentResult(
        experiment_name=experiment_name,
        description=description,
        feature_count=len(
            feature_columns
        ),
        categorical_feature_count=len(
            categorical_features
        ),
        training_rows=len(train),
        validation_rows=len(validation),
        mae=metrics["mae"],
        rmse=metrics["rmse"],
        r2=metrics["r2"],
        mape=metrics["mape"],
        target_mean_training=float(
            train[TARGET_NAME].mean()
        ),
        target_mean_validation=float(
            validation[TARGET_NAME].mean()
        ),
        prediction_min=float(
            predictions.min()
        ),
        prediction_max=float(
            predictions.max()
        ),
        training_fit_validation_used=False,
        test_dataset_used=False,
        leakage_contract_passed=True,
    )


# ============================================================================
# COMPARISON
# ============================================================================


def print_comparison(
    results: list[ExperimentResult],
) -> None:

    section(
        "ABLATION COMPARISON"
    )

    rows = [
        {
            "experiment": result.experiment_name,
            "features": result.feature_count,
            "MAE": result.mae,
            "RMSE": result.rmse,
            "R2": result.r2,
            "MAPE": result.mape,
        }
        for result in results
    ]

    dataframe = pd.DataFrame(
        rows
    )

    print(
        dataframe.to_string(
            index=False
        )
    )

    if len(results) >= 2:

        baseline = results[0]
        ablated = results[1]

        mae_change = (
            ablated.mae
            - baseline.mae
        )

        rmse_change = (
            ablated.rmse
            - baseline.rmse
        )

        r2_change = (
            ablated.r2
            - baseline.r2
        )

        print()
        print(
            "ABLATION EFFECT"
        )

        print(
            f"MAE change                              : "
            f"{mae_change:+.6f}"
        )

        print(
            f"RMSE change                             : "
            f"{rmse_change:+.6f}"
        )

        print(
            f"R² change                               : "
            f"{r2_change:+.6f}"
        )

        if baseline.mae != 0.0:

            mae_percentage = (
                mae_change
                / baseline.mae
                * 100.0
            )

            print(
                f"MAE percentage change                  : "
                f"{mae_percentage:+.2f}%"
            )

        if baseline.r2 != 0.0:

            r2_percentage = (
                r2_change
                / abs(baseline.r2)
                * 100.0
            )

            print(
                f"R² relative change                     : "
                f"{r2_percentage:+.2f}%"
            )


# ============================================================================
# PERSISTENCE
# ============================================================================


def persist_results(
    *,
    results: list[ExperimentResult],
    registered_features: list[str],
    removed_features: list[str],
    retained_features: list[str],
) -> None:

    section(
        "PERSISTING ABLATION RESULTS"
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    result_dicts = [
        asdict(result)
        for result in results
    ]

    payload = {
        "experiment": {
            "name": (
                "Birmingham XGBoost "
                "Current-State Feature Ablation"
            ),
            "target": TARGET_NAME,
            "training_file": str(
                TRAIN_PATH
            ),
            "validation_file": str(
                VALIDATION_PATH
            ),
            "test_file_loaded": False,
            "feature_pipeline_rebuilt": False,
            "hyperparameter_tuning": False,
        },
        "feature_contract": {
            "registered_feature_count": len(
                registered_features
            ),
            "removed_current_state_features": (
                removed_features
            ),
            "removed_current_state_feature_count": (
                len(removed_features)
            ),
            "retained_feature_count": len(
                retained_features
            ),
        },
        "results": result_dicts,
    }

    with RESULTS_JSON.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            payload,
            handle,
            indent=2,
            default=str,
        )

    dataframe = pd.DataFrame(
        result_dicts
    )

    dataframe.to_csv(
        RESULTS_CSV,
        index=False,
    )

    print(
        f"Output directory                      : "
        f"{OUTPUT_DIR}"
    )

    print(
        f"JSON results                           : "
        f"{RESULTS_JSON}"
    )

    print(
        f"CSV results                            : "
        f"{RESULTS_CSV}"
    )


# ============================================================================
# FINAL ASSERTIONS
# ============================================================================


def run_final_assertions(
    *,
    results: list[ExperimentResult],
    registered_features: list[str],
    removed_features: list[str],
    retained_features: list[str],
) -> None:

    section(
        "FINAL ASSERTIONS"
    )

    assertions: list[
        tuple[str, bool]
    ] = []

    assertions.append(
        (
            "Two ablation experiments executed",
            len(results) == 2,
        )
    )

    assertions.append(
        (
            "Original feature registry has 296 features",
            len(registered_features) == 296,
        )
    )

    assertions.append(
        (
            "Ablated feature set is smaller",
            len(retained_features)
            < len(registered_features),
        )
    )

    assertions.append(
        (
            "No duplicate registered features",
            len(registered_features)
            == len(set(registered_features)),
        )
    )

    assertions.append(
        (
            "No overlap between removed and retained features",
            not (
                set(removed_features)
                & set(retained_features)
            ),
        )
    )

    assertions.append(
        (
            "All experiment feature counts populated",
            all(
                result.feature_count > 0
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "All training row counts populated",
            all(
                result.training_rows > 0
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "All validation row counts populated",
            all(
                result.validation_rows > 0
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "All MAE values finite",
            all(
                math.isfinite(
                    result.mae
                )
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "All RMSE values finite",
            all(
                math.isfinite(
                    result.rmse
                )
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "All R² values finite",
            all(
                math.isfinite(
                    result.r2
                )
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "All predictions remained finite",
            all(
                math.isfinite(
                    result.prediction_min
                )
                and math.isfinite(
                    result.prediction_max
                )
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "Validation data never used during fit",
            all(
                not result.training_fit_validation_used
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "Test dataset never used",
            all(
                not result.test_dataset_used
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "Leakage contract passed",
            all(
                result.leakage_contract_passed
                for result in results
            ),
        )
    )

    failed = False

    for label, passed in assertions:

        print_check(
            label,
            passed,
        )

        if not passed:
            failed = True

    if failed:
        raise RuntimeError(
            "One or more ablation experiment "
            "assertions failed."
        )

    print()
    print(
        "ALL XGBOOST FEATURE ABLATION "
        "ASSERTIONS PASSED"
    )


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:

    print()
    print(
        "=" * 78
    )

    print(
        "SMARTPARK AI - BIRMINGHAM "
        "XGBOOST FEATURE ABLATION"
    )

    print(
        "=" * 78
    )

    print()
    print(
        "Target:"
    )

    print(
        f"  {TARGET_NAME}"
    )

    print()
    print(
        "Experiment:"
    )

    print(
        "  Compare XGBoost with all registered "
        "features against an ablated model"
    )

    print(
        "  Remove current-state-derived feature family"
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

    print(
        "  No hyperparameter tuning"
    )

    print(
        "  No feature pipeline rebuild"
    )

    try:

        validate_dataset_files()

        manifest = load_manifest()

        train, validation = (
            load_training_and_validation()
        )

        registered_features = (
            get_registered_features(
                manifest
            )
        )

        validate_feature_registry(
            train,
            validation,
            registered_features,
        )

        validate_target(
            train,
            validation,
        )

        validate_chronology(
            train,
            validation,
        )

        validate_observation_isolation(
            train,
            validation,
        )

        (
            removed_features,
            retained_features,
        ) = determine_ablation_features(
            registered_features
        )

        print_ablation_contract(
            registered_features,
            removed_features,
            retained_features,
        )

        if not removed_features:
            raise RuntimeError(
                "No current-state features were found "
                "in the registered feature set. "
                "Ablation cannot proceed."
            )

        # --------------------------------------------------------------
        # Experiment A
        # --------------------------------------------------------------

        all_categorical_features = [
            feature
            for feature in (
                "occupancy_level",
                "demand_class",
            )
            if feature in registered_features
        ]

        baseline_result = run_experiment(
            experiment_name=(
                "xgboost_all_features"
            ),
            description=(
                "XGBoost using all 296 registered "
                "ML features."
            ),
            train=train,
            validation=validation,
            feature_columns=registered_features,
            categorical_features=(
                all_categorical_features
            ),
        )

        # --------------------------------------------------------------
        # Experiment B
        # --------------------------------------------------------------

        ablated_categorical_features = [
            feature
            for feature in all_categorical_features
            if feature in retained_features
        ]

        ablated_result = run_experiment(
            experiment_name=(
                "xgboost_without_current_state_features"
            ),
            description=(
                "XGBoost after removing features "
                "directly derived from current "
                "parking occupancy/availability state."
            ),
            train=train,
            validation=validation,
            feature_columns=retained_features,
            categorical_features=(
                ablated_categorical_features
            ),
        )

        results = [
            baseline_result,
            ablated_result,
        ]

        print_comparison(
            results
        )

        persist_results(
            results=results,
            registered_features=(
                registered_features
            ),
            removed_features=(
                removed_features
            ),
            retained_features=(
                retained_features
            ),
        )

        run_final_assertions(
            results=results,
            registered_features=(
                registered_features
            ),
            removed_features=(
                removed_features
            ),
            retained_features=(
                retained_features
            ),
        )

        print()
        print(
            "=" * 78
        )

        print(
            "BIRMINGHAM XGBOOST FEATURE ABLATION "
            "COMPLETED SUCCESSFULLY"
        )

        print(
            "=" * 78
        )

        print()
        print(
            f"Target:              {TARGET_NAME}"
        )

        print(
            f"Full feature set:    "
            f"{len(registered_features)}"
        )

        print(
            f"Current-state removed: "
            f"{len(removed_features)}"
        )

        print(
            f"Ablated feature set: "
            f"{len(retained_features)}"
        )

        print(
            "Training dataset:    train.parquet"
        )

        print(
            "Validation dataset:  validation.parquet"
        )

        print(
            "Test dataset used:   NO"
        )

        print(
            "Feature pipeline:    NOT rebuilt"
        )

        print(
            "Tuning:              NO"
        )

        print()
        print(
            "Feature ablation results are ready "
            "for interpretation."
        )

        return 0

    except Exception as exc:

        print()
        print(
            "=" * 78
        )

        print(
            "BIRMINGHAM XGBOOST FEATURE ABLATION FAILED"
        )

        print(
            "=" * 78
        )

        print()
        print(
            f"ERROR: {exc}"
        )

        print()
        print(
            "NO persisted training datasets were modified."
        )

        print(
            "DO NOT proceed to feature conclusions "
            "until the reported issue is resolved."
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )