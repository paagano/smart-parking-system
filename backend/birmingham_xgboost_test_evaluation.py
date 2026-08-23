"""
SmartPark AI
Birmingham XGBoost Final Test Evaluation

Purpose
-------
Evaluate the already-established Birmingham XGBoost configuration against
the completely untouched Birmingham test dataset.

This script is a FINAL EVALUATION script.

It deliberately does NOT:

    - rebuild the feature pipeline
    - modify persisted datasets
    - tune hyperparameters
    - use validation data during model fitting
    - use test data during model fitting
    - perform early stopping
    - fit categorical mappings using validation/test data
    - shuffle observations
    - impute target values
    - use metadata columns as ML features

Evaluation protocol
-------------------

                    TRAIN
                      |
                      | fit()
                      v
                  XGBoost
                    /   \
                   /     \
                  v       v
           VALIDATION    TEST
           comparison    FINAL RESULT

The test dataset remains completely untouched until after the model
has been fitted on the training dataset.

Target
------
    target_occupancy_rate_30m

Expected feature registry
--------------------------
    296 registered ML features

Expected persisted columns
---------------------------
    296 features
    +
    1 target
    +
    metadata columns

Important metadata columns discovered in the persisted Birmingham
datasets include:

    source_facility_code
    normalized_at

These are deliberately NOT passed to XGBoost.

Categorical ML features
-----------------------
    occupancy_level
    demand_class

These are delegated to XGBoostModel for training-only categorical
mapping.

Output
------
    datasets/processed/birmingham/xgboost_test_evaluation/

        birmingham_xgboost_test_evaluation_results.json
        birmingham_xgboost_test_evaluation_results.csv
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from app.ml.ml_models.xgboost_model import (
    XGBoostModel,
    XGBoostModelConfig,
)


# =====================================================================
# PATHS
# =====================================================================

BACKEND_ROOT = Path(__file__).resolve().parent

PROJECT_ROOT = BACKEND_ROOT.parent

DATASET_ROOT = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
)

TARGET_NAME = (
    "target_occupancy_rate_30m"
)

TARGET_DATASET_ROOT = (
    DATASET_ROOT
    / TARGET_NAME
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
    / "xgboost_test_evaluation"
)

JSON_OUTPUT = (
    OUTPUT_DIR
    / "birmingham_xgboost_test_evaluation_results.json"
)

CSV_OUTPUT = (
    OUTPUT_DIR
    / "birmingham_xgboost_test_evaluation_results.csv"
)


# =====================================================================
# CONTRACTS
# =====================================================================

EXPECTED_FEATURE_COUNT = 296

EXPECTED_TRAIN_ROWS = 23_244

EXPECTED_VALIDATION_ROWS = 4_980

EXPECTED_TEST_ROWS = 4_982

EXPECTED_TARGET_MIN = 0.0

EXPECTED_TARGET_MAX = 1.0

TIMESTAMP_COLUMN = "normalized_at"

FACILITY_COLUMN = "source_facility_code"

CATEGORICAL_FEATURES = (
    "occupancy_level",
    "demand_class",
)


# =====================================================================
# BASELINE REFERENCE
# =====================================================================

# These are the previously completed validation benchmark results.
#
# They are reference values only.
#
# They are NOT used for fitting the XGBoost model.

BASELINE_VALIDATION_RESULTS = {
    "mean_baseline": {
        "mae": 0.248729,
        "rmse": 0.285593,
        "r2": -0.042971,
        "mape": 81.682969,
        "sample_count": 4_980,
    },
    "last_value_baseline": {
        "mae": 0.245388,
        "rmse": 0.279782,
        "r2": -0.000955,
        "mape": 89.120066,
        "sample_count": 4_980,
    },
}


# =====================================================================
# XGBOOST CONFIGURATION
# =====================================================================

# This configuration corresponds to the initial benchmark.
#
# No tuning is performed here.

XGBOOST_CONFIG = XGBoostModelConfig(
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
    categorical_features=CATEGORICAL_FEATURES,
)


# =====================================================================
# DATA STRUCTURES
# =====================================================================


@dataclass
class DatasetSummary:
    name: str
    path: str
    rows: int
    columns: int
    feature_count: int
    target_count: int
    minimum_timestamp: Optional[str]
    maximum_timestamp: Optional[str]
    target_mean: float
    target_min: float
    target_max: float
    target_nulls: int
    feature_null_cells: int


@dataclass
class EvaluationMetrics:
    model_name: str
    dataset_name: str
    mae: float
    rmse: float
    r2: float
    mape: float
    sample_count: int
    prediction_min: float
    prediction_max: float
    prediction_mean: float


@dataclass
class GeneralizationMetrics:
    validation_mae: float
    test_mae: float
    mae_absolute_change: float
    mae_percentage_change: float

    validation_rmse: float
    test_rmse: float
    rmse_absolute_change: float
    rmse_percentage_change: float

    validation_r2: float
    test_r2: float
    r2_absolute_change: float
    r2_percentage_change: float

    validation_mape: float
    test_mape: float
    mape_absolute_change: float
    mape_percentage_change: float


# =====================================================================
# PRINTING HELPERS
# =====================================================================


def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def print_status(
    label: str,
    status: str,
) -> None:
    print(
        f"{label:<42}: {status}"
    )


def print_metric(
    label: str,
    value: Any,
) -> None:
    print(
        f"{label:<42}: {value}"
    )


# =====================================================================
# GENERAL VALIDATION
# =====================================================================


def require_file(
    path: Path,
    description: str,
) -> None:

    if not path.exists():
        raise FileNotFoundError(
            f"{description} does not exist: {path}"
        )

    if not path.is_file():
        raise FileNotFoundError(
            f"{description} is not a file: {path}"
        )


def load_manifest() -> dict[str, Any]:

    require_file(
        MANIFEST_PATH,
        "Training dataset manifest",
    )

    with MANIFEST_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:

        manifest = json.load(handle)

    return manifest


def validate_manifest(
    manifest: dict[str, Any],
) -> list[str]:

    errors: list[str] = []

    feature_columns = manifest.get(
        "feature_columns",
        [],
    )

    target_columns = manifest.get(
        "target_columns",
        [],
    )

    if len(feature_columns) != EXPECTED_FEATURE_COUNT:

        errors.append(
            "Manifest feature count mismatch: "
            f"expected {EXPECTED_FEATURE_COUNT}, "
            f"got {len(feature_columns)}."
        )

    if TARGET_NAME not in target_columns:

        errors.append(
            f"Target '{TARGET_NAME}' is not present "
            "in manifest target_columns."
        )

    return errors


# =====================================================================
# DATASET LOADING
# =====================================================================


def load_dataset(
    path: Path,
) -> pd.DataFrame:

    require_file(
        path,
        f"Dataset file {path.name}",
    )

    dataframe = pd.read_parquet(
        path,
        engine="pyarrow",
    )

    if not isinstance(
        dataframe,
        pd.DataFrame,
    ):
        raise TypeError(
            f"Expected pandas DataFrame from {path}."
        )

    return dataframe


# =====================================================================
# FEATURE REGISTRY
# =====================================================================


def get_feature_columns(
    manifest: dict[str, Any],
) -> list[str]:

    feature_columns = manifest.get(
        "feature_columns",
        [],
    )

    return [
        str(column)
        for column in feature_columns
    ]


def validate_feature_registry(
    dataframe: pd.DataFrame,
    feature_columns: list[str],
    dataset_name: str,
) -> None:

    missing = [
        column
        for column in feature_columns
        if column not in dataframe.columns
    ]

    if missing:

        raise ValueError(
            f"{dataset_name} is missing registered "
            f"features: {missing}"
        )

    duplicate_features = (
        pd.Index(feature_columns)
        .duplicated()
    )

    if duplicate_features.any():

        duplicates = (
            pd.Index(feature_columns)[
                duplicate_features
            ]
            .tolist()
        )

        raise ValueError(
            f"Duplicate registered features: {duplicates}"
        )


# =====================================================================
# TARGET VALIDATION
# =====================================================================


def validate_target(
    dataframe: pd.DataFrame,
    dataset_name: str,
) -> None:

    if TARGET_NAME not in dataframe.columns:

        raise ValueError(
            f"{dataset_name} does not contain "
            f"target column '{TARGET_NAME}'."
        )

    target = pd.to_numeric(
        dataframe[TARGET_NAME],
        errors="coerce",
    )

    null_count = int(
        target.isna().sum()
    )

    if null_count:

        raise ValueError(
            f"{dataset_name} contains "
            f"{null_count} null target values."
        )

    values = target.to_numpy(
        dtype=float,
    )

    if not np.isfinite(values).all():

        raise ValueError(
            f"{dataset_name} target contains "
            "NaN or infinite values."
        )

    minimum = float(
        np.min(values)
    )

    maximum = float(
        np.max(values)
    )

    if (
        minimum < EXPECTED_TARGET_MIN
        or maximum > EXPECTED_TARGET_MAX
    ):

        raise ValueError(
            f"{dataset_name} target outside "
            f"expected range "
            f"[{EXPECTED_TARGET_MIN}, "
            f"{EXPECTED_TARGET_MAX}]: "
            f"{minimum} -> {maximum}"
        )


# =====================================================================
# TIMESTAMP VALIDATION
# =====================================================================


def validate_timestamps(
    dataframe: pd.DataFrame,
    dataset_name: str,
) -> pd.Series:

    if TIMESTAMP_COLUMN not in dataframe.columns:

        raise ValueError(
            f"{dataset_name} does not contain "
            f"timestamp column '{TIMESTAMP_COLUMN}'."
        )

    timestamps = pd.to_datetime(
        dataframe[TIMESTAMP_COLUMN],
        errors="coerce",
    )

    if timestamps.isna().any():

        raise ValueError(
            f"{dataset_name} contains invalid "
            "timestamps."
        )

    return timestamps


def validate_chronological_relationship(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> None:

    train_timestamps = validate_timestamps(
        train,
        "Training",
    )

    validation_timestamps = validate_timestamps(
        validation,
        "Validation",
    )

    test_timestamps = validate_timestamps(
        test,
        "Test",
    )

    train_max = train_timestamps.max()

    validation_min = validation_timestamps.min()

    validation_max = validation_timestamps.max()

    test_min = test_timestamps.min()

    test_max = test_timestamps.max()

    print()
    print(
        f"Training start"
        f"                          : "
        f"{train_timestamps.min()}"
    )

    print(
        f"Training end"
        f"                            : "
        f"{train_max}"
    )

    print(
        f"Validation start"
        f"                        : "
        f"{validation_min}"
    )

    print(
        f"Validation end"
        f"                          : "
        f"{validation_max}"
    )

    print(
        f"Test start"
        f"                                : "
        f"{test_min}"
    )

    print(
        f"Test end"
        f"                                  : "
        f"{test_max}"
    )

    # The persisted split builder uses boundary timestamps
    # consistently. Equality is therefore acceptable.

    if train_max > validation_min:

        raise ValueError(
            "Training data extends beyond the beginning "
            "of validation data."
        )

    if validation_max > test_min:

        raise ValueError(
            "Validation data extends beyond the beginning "
            "of test data."
        )

    print_status(
        "Chronological ordering",
        "PASS",
    )


# =====================================================================
# OBSERVATION ISOLATION
# =====================================================================


def build_observation_keys(
    dataframe: pd.DataFrame,
) -> set[tuple[str, pd.Timestamp]]:

    if FACILITY_COLUMN not in dataframe.columns:

        raise ValueError(
            f"Required observation key column "
            f"'{FACILITY_COLUMN}' not found."
        )

    timestamps = pd.to_datetime(
        dataframe[TIMESTAMP_COLUMN],
        errors="coerce",
    )

    facilities = (
        dataframe[FACILITY_COLUMN]
        .astype("string")
        .fillna("<NULL>")
    )

    return set(
        zip(
            facilities.astype(str),
            timestamps,
        )
    )


def validate_observation_isolation(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
) -> None:

    train_keys = build_observation_keys(
        train
    )

    validation_keys = build_observation_keys(
        validation
    )

    test_keys = build_observation_keys(
        test
    )

    train_validation = (
        train_keys
        & validation_keys
    )

    validation_test = (
        validation_keys
        & test_keys
    )

    train_test = (
        train_keys
        & test_keys
    )

    print()
    print(
        f"Train observations"
        f"                    : "
        f"{len(train_keys):,}"
    )

    print(
        f"Validation observations"
        f"               : "
        f"{len(validation_keys):,}"
    )

    print(
        f"Test observations"
        f"                     : "
        f"{len(test_keys):,}"
    )

    print(
        f"Train ∩ Validation"
        f"                    : "
        f"{len(train_validation):,}"
    )

    print(
        f"Validation ∩ Test"
        f"                      : "
        f"{len(validation_test):,}"
    )

    print(
        f"Train ∩ Test"
        f"                            : "
        f"{len(train_test):,}"
    )

    if train_validation:

        raise ValueError(
            "Training and validation observation "
            "keys overlap."
        )

    if validation_test:

        raise ValueError(
            "Validation and test observation "
            "keys overlap."
        )

    if train_test:

        raise ValueError(
            "Training and test observation "
            "keys overlap."
        )

    print_status(
        "Observation isolation",
        "PASS",
    )


# =====================================================================
# FEATURE DATAFRAME PREPARATION
# =====================================================================


def prepare_features(
    dataframe: pd.DataFrame,
    feature_columns: list[str],
) -> pd.DataFrame:

    features = dataframe[
        feature_columns
    ].copy()

    return features


def validate_feature_types(
    features: pd.DataFrame,
    dataset_name: str,
) -> None:

    categorical = set(
        CATEGORICAL_FEATURES
    )

    allowed_non_numeric = []

    non_numeric = []

    for column in features.columns:

        if column in categorical:
            allowed_non_numeric.append(
                column
            )
            continue

        if not pd.api.types.is_numeric_dtype(
            features[column]
        ):
            non_numeric.append(
                column
            )

    if non_numeric:

        raise ValueError(
            f"{dataset_name} contains non-numeric "
            "features that are not configured as "
            f"categorical: {non_numeric}"
        )

    print(
        f"{dataset_name} numeric features"
        f"                    : "
        f"{len(features.columns) - len(allowed_non_numeric)}"
    )

    print(
        f"{dataset_name} categorical features"
        f"                : "
        f"{len(allowed_non_numeric)}"
    )


def validate_infinite_numeric_values(
    features: pd.DataFrame,
    dataset_name: str,
) -> None:

    numeric_columns = [
        column
        for column in features.columns
        if pd.api.types.is_numeric_dtype(
            features[column]
        )
    ]

    if not numeric_columns:
        return

    numeric_values = (
        features[numeric_columns]
        .to_numpy(
            dtype=float
        )
    )

    infinite_mask = np.isinf(
        numeric_values
    )

    count = int(
        infinite_mask.sum()
    )

    print(
        f"{dataset_name} infinite numeric cells"
        f"               : "
        f"{count:,}"
    )

    if count:

        offending_columns = sorted(
            {
                str(
                    numeric_columns[
                        int(position[1])
                    ]
                )
                for position in np.argwhere(
                    infinite_mask
                )
            }
        )

        raise ValueError(
            f"{dataset_name} contains infinite "
            f"numeric values in: "
            f"{offending_columns}"
        )


# =====================================================================
# METRICS
# =====================================================================


def calculate_mae(
    y_true: np.ndarray,
    predictions: np.ndarray,
) -> float:

    return float(
        np.mean(
            np.abs(
                y_true
                - predictions
            )
        )
    )


def calculate_rmse(
    y_true: np.ndarray,
    predictions: np.ndarray,
) -> float:

    return float(
        np.sqrt(
            np.mean(
                np.square(
                    y_true
                    - predictions
                )
            )
        )
    )


def calculate_r2(
    y_true: np.ndarray,
    predictions: np.ndarray,
) -> float:

    residual_sum = float(
        np.sum(
            np.square(
                y_true
                - predictions
            )
        )
    )

    total_sum = float(
        np.sum(
            np.square(
                y_true
                - np.mean(y_true)
            )
        )
    )

    if total_sum == 0.0:

        return float("nan")

    return float(
        1.0
        - (
            residual_sum
            / total_sum
        )
    )


def calculate_mape(
    y_true: np.ndarray,
    predictions: np.ndarray,
) -> float:

    # The target can contain zero occupancy.
    #
    # Therefore zero actual values are excluded from MAPE
    # rather than introducing division-by-zero.

    non_zero = (
        np.abs(y_true) > 1e-12
    )

    if not non_zero.any():

        return float("nan")

    return float(
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


def evaluate_predictions(
    *,
    model_name: str,
    dataset_name: str,
    y_true: np.ndarray,
    predictions: np.ndarray,
) -> EvaluationMetrics:

    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    predictions = np.asarray(
        predictions,
        dtype=float,
    )

    if len(y_true) != len(predictions):

        raise ValueError(
            "Prediction/target length mismatch: "
            f"{len(predictions)} vs {len(y_true)}"
        )

    if not np.isfinite(
        y_true
    ).all():

        raise ValueError(
            "Ground-truth target contains "
            "non-finite values."
        )

    if not np.isfinite(
        predictions
    ).all():

        raise ValueError(
            "Predictions contain "
            "non-finite values."
        )

    return EvaluationMetrics(
        model_name=model_name,
        dataset_name=dataset_name,
        mae=calculate_mae(
            y_true,
            predictions,
        ),
        rmse=calculate_rmse(
            y_true,
            predictions,
        ),
        r2=calculate_r2(
            y_true,
            predictions,
        ),
        mape=calculate_mape(
            y_true,
            predictions,
        ),
        sample_count=len(y_true),
        prediction_min=float(
            np.min(predictions)
        ),
        prediction_max=float(
            np.max(predictions)
        ),
        prediction_mean=float(
            np.mean(predictions)
        ),
    )


# =====================================================================
# GENERALIZATION
# =====================================================================


def percentage_change(
    old: float,
    new: float,
) -> float:

    if abs(old) < 1e-15:

        return float("nan")

    return float(
        (
            (new - old)
            / abs(old)
        )
        * 100.0
    )


def build_generalization_metrics(
    validation_metrics: EvaluationMetrics,
    test_metrics: EvaluationMetrics,
) -> GeneralizationMetrics:

    return GeneralizationMetrics(
        validation_mae=validation_metrics.mae,
        test_mae=test_metrics.mae,
        mae_absolute_change=(
            test_metrics.mae
            - validation_metrics.mae
        ),
        mae_percentage_change=percentage_change(
            validation_metrics.mae,
            test_metrics.mae,
        ),
        validation_rmse=validation_metrics.rmse,
        test_rmse=test_metrics.rmse,
        rmse_absolute_change=(
            test_metrics.rmse
            - validation_metrics.rmse
        ),
        rmse_percentage_change=percentage_change(
            validation_metrics.rmse,
            test_metrics.rmse,
        ),
        validation_r2=validation_metrics.r2,
        test_r2=test_metrics.r2,
        r2_absolute_change=(
            test_metrics.r2
            - validation_metrics.r2
        ),
        r2_percentage_change=percentage_change(
            validation_metrics.r2,
            test_metrics.r2,
        ),
        validation_mape=validation_metrics.mape,
        test_mape=test_metrics.mape,
        mape_absolute_change=(
            test_metrics.mape
            - validation_metrics.mape
        ),
        mape_percentage_change=percentage_change(
            validation_metrics.mape,
            test_metrics.mape,
        ),
    )


# =====================================================================
# DATASET SUMMARY
# =====================================================================


def build_dataset_summary(
    name: str,
    path: Path,
    dataframe: pd.DataFrame,
    feature_columns: list[str],
) -> DatasetSummary:

    timestamps = validate_timestamps(
        dataframe,
        name,
    )

    target = pd.to_numeric(
        dataframe[TARGET_NAME],
        errors="coerce",
    )

    feature_null_cells = int(
        dataframe[
            feature_columns
        ]
        .isna()
        .sum()
        .sum()
    )

    return DatasetSummary(
        name=name,
        path=str(path),
        rows=len(dataframe),
        columns=len(dataframe.columns),
        feature_count=len(feature_columns),
        target_count=1,
        minimum_timestamp=str(
            timestamps.min()
        ),
        maximum_timestamp=str(
            timestamps.max()
        ),
        target_mean=float(
            target.mean()
        ),
        target_min=float(
            target.min()
        ),
        target_max=float(
            target.max()
        ),
        target_nulls=int(
            target.isna().sum()
        ),
        feature_null_cells=feature_null_cells,
    )


# =====================================================================
# MODEL CONFIGURATION DISPLAY
# =====================================================================


def print_model_configuration() -> None:

    print_section(
        "XGBOOST FINAL EVALUATION CONFIGURATION"
    )

    config = XGBOOST_CONFIG

    print_metric(
        "objective",
        config.objective,
    )

    print_metric(
        "n_estimators",
        config.n_estimators,
    )

    print_metric(
        "learning_rate",
        config.learning_rate,
    )

    print_metric(
        "max_depth",
        config.max_depth,
    )

    print_metric(
        "min_child_weight",
        config.min_child_weight,
    )

    print_metric(
        "subsample",
        config.subsample,
    )

    print_metric(
        "colsample_bytree",
        config.colsample_bytree,
    )

    print_metric(
        "gamma",
        config.gamma,
    )

    print_metric(
        "reg_alpha",
        config.reg_alpha,
    )

    print_metric(
        "reg_lambda",
        config.reg_lambda,
    )

    print_metric(
        "random_state",
        config.random_state,
    )

    print_metric(
        "n_jobs",
        config.n_jobs,
    )

    print_metric(
        "tree_method",
        config.tree_method,
    )

    print_metric(
        "early_stopping_rounds",
        config.early_stopping_rounds,
    )

    print_metric(
        "clip_predictions",
        config.clip_predictions,
    )

    print_metric(
        "categorical_features",
        ", ".join(
            CATEGORICAL_FEATURES
        ),
    )


# =====================================================================
# MODEL TRAINING
# =====================================================================


def train_model(
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> XGBoostModel:

    print_section(
        "TRAINING FINAL XGBOOST MODEL"
    )

    print(
        "IMPORTANT: validation data is NOT passed "
        "to fit()."
    )

    print(
        "IMPORTANT: test data is NOT passed "
        "to fit()."
    )

    print(
        "IMPORTANT: no hyperparameter tuning "
        "is performed."
    )

    model = XGBoostModel(
        target_column=TARGET_NAME,
        config=XGBOOST_CONFIG,
        model_name=(
            "birmingham_xgboost_"
            "target_occupancy_rate_30m"
        ),
    )

    model.fit(
        X_train,
        y_train,
    )

    print(
        "Training completed successfully."
    )

    return model


# =====================================================================
# MODEL PREDICTION
# =====================================================================


def predict(
    model: XGBoostModel,
    features: pd.DataFrame,
    dataset_name: str,
) -> np.ndarray:

    print(
        f"Generating {dataset_name.lower()} "
        "predictions..."
    )

    predictions = model.predict(
        features
    )

    predictions = np.asarray(
        predictions,
        dtype=float,
    )

    if not np.isfinite(
        predictions
    ).all():

        raise ValueError(
            f"{dataset_name} predictions contain "
            "NaN or infinite values."
        )

    return predictions


# =====================================================================
# RESULT PERSISTENCE
# =====================================================================


def make_json_serializable(
    value: Any,
) -> Any:

    if isinstance(
        value,
        dict,
    ):

        return {
            str(key): make_json_serializable(
                item
            )
            for key, item in value.items()
        }

    if isinstance(
        value,
        list,
    ):

        return [
            make_json_serializable(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        tuple,
    ):

        return [
            make_json_serializable(
                item
            )
            for item in value
        ]

    if isinstance(
        value,
        np.integer,
    ):

        return int(value)

    if isinstance(
        value,
        np.floating,
    ):

        value = float(value)

        if not math.isfinite(value):

            return None

        return value

    if isinstance(
        value,
        float,
    ):

        if not math.isfinite(value):

            return None

        return value

    return value


def persist_results(
    *,
    train_summary: DatasetSummary,
    validation_summary: DatasetSummary,
    test_summary: DatasetSummary,
    validation_metrics: EvaluationMetrics,
    test_metrics: EvaluationMetrics,
    generalization: GeneralizationMetrics,
    model: XGBoostModel,
) -> None:

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    model_metadata = {}

    if hasattr(
        model,
        "get_fit_metadata",
    ):

        try:

            model_metadata = (
                model.get_fit_metadata()
            )

        except Exception:
            model_metadata = {}

    results = {
        "schema_version": "1.0",
        "evaluation_name": (
            "birmingham_xgboost_test_evaluation"
        ),
        "target": TARGET_NAME,
        "protocol": {
            "train_dataset_used_for_fit": True,
            "validation_dataset_used_for_fit": False,
            "test_dataset_used_for_fit": False,
            "validation_used_for_tuning": False,
            "test_used_for_tuning": False,
            "feature_pipeline_rebuilt": False,
            "hyperparameter_tuning": False,
            "early_stopping": False,
            "random_shuffle": False,
            "test_dataset_touched_only_for_final_evaluation": True,
        },
        "feature_contract": {
            "registered_feature_count": (
                EXPECTED_FEATURE_COUNT
            ),
            "categorical_features": list(
                CATEGORICAL_FEATURES
            ),
            "metadata_columns_excluded": [
                FACILITY_COLUMN,
                TIMESTAMP_COLUMN,
            ],
        },
        "model_configuration": {
            key: value
            for key, value in vars(
                XGBOOST_CONFIG
            ).items()
            if not key.startswith("_")
        },
        "datasets": {
            "train": asdict(
                train_summary
            ),
            "validation": asdict(
                validation_summary
            ),
            "test": asdict(
                test_summary
            ),
        },
        "validation_metrics": asdict(
            validation_metrics
        ),
        "test_metrics": asdict(
            test_metrics
        ),
        "generalization": asdict(
            generalization
        ),
        "previous_baseline_validation": (
            BASELINE_VALIDATION_RESULTS
        ),
        "model_fit_metadata": model_metadata,
    }

    results = make_json_serializable(
        results
    )

    with JSON_OUTPUT.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            results,
            handle,
            indent=2,
        )

    rows = [
        {
            "model_name": validation_metrics.model_name,
            "dataset": "validation",
            "mae": validation_metrics.mae,
            "rmse": validation_metrics.rmse,
            "r2": validation_metrics.r2,
            "mape": validation_metrics.mape,
            "sample_count": validation_metrics.sample_count,
            "prediction_min": validation_metrics.prediction_min,
            "prediction_max": validation_metrics.prediction_max,
            "prediction_mean": validation_metrics.prediction_mean,
        },
        {
            "model_name": test_metrics.model_name,
            "dataset": "test",
            "mae": test_metrics.mae,
            "rmse": test_metrics.rmse,
            "r2": test_metrics.r2,
            "mape": test_metrics.mape,
            "sample_count": test_metrics.sample_count,
            "prediction_min": test_metrics.prediction_min,
            "prediction_max": test_metrics.prediction_max,
            "prediction_mean": test_metrics.prediction_mean,
        },
    ]

    pd.DataFrame(
        rows
    ).to_csv(
        CSV_OUTPUT,
        index=False,
    )


# =====================================================================
# FINAL ASSERTIONS
# =====================================================================


def run_final_assertions(
    *,
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    feature_columns: list[str],
    validation_metrics: EvaluationMetrics,
    test_metrics: EvaluationMetrics,
    validation_predictions: np.ndarray,
    test_predictions: np.ndarray,
) -> None:

    print_section(
        "FINAL ASSERTIONS"
    )

    assertions = [
        (
            "Training dataset non-empty",
            len(train) > 0,
        ),
        (
            "Validation dataset non-empty",
            len(validation) > 0,
        ),
        (
            "Test dataset non-empty",
            len(test) > 0,
        ),
        (
            "Expected feature count",
            len(feature_columns)
            == EXPECTED_FEATURE_COUNT,
        ),
        (
            "Training row count",
            len(train)
            == EXPECTED_TRAIN_ROWS,
        ),
        (
            "Validation row count",
            len(validation)
            == EXPECTED_VALIDATION_ROWS,
        ),
        (
            "Test row count",
            len(test)
            == EXPECTED_TEST_ROWS,
        ),
        (
            "Validation predictions finite",
            np.isfinite(
                validation_predictions
            ).all(),
        ),
        (
            "Test predictions finite",
            np.isfinite(
                test_predictions
            ).all(),
        ),
        (
            "Validation MAE finite",
            math.isfinite(
                validation_metrics.mae
            ),
        ),
        (
            "Validation RMSE finite",
            math.isfinite(
                validation_metrics.rmse
            ),
        ),
        (
            "Validation R² finite",
            math.isfinite(
                validation_metrics.r2
            ),
        ),
        (
            "Test MAE finite",
            math.isfinite(
                test_metrics.mae
            ),
        ),
        (
            "Test RMSE finite",
            math.isfinite(
                test_metrics.rmse
            ),
        ),
        (
            "Test R² finite",
            math.isfinite(
                test_metrics.r2
            ),
        ),
        (
            "Test MAPE finite",
            math.isfinite(
                test_metrics.mape
            ),
        ),
    ]

    failures = []

    for label, passed in assertions:

        if passed:

            print_status(
                label,
                "PASS",
            )

        else:

            print_status(
                label,
                "FAIL",
            )

            failures.append(
                label
            )

    if failures:

        raise AssertionError(
            "Final evaluation assertions failed: "
            + ", ".join(failures)
        )

    print()
    print(
        "ALL FINAL TEST EVALUATION ASSERTIONS PASSED"
    )


# =====================================================================
# MAIN
# =====================================================================


def main() -> int:

    print_header(
        "SMARTPARK AI - BIRMINGHAM XGBOOST FINAL TEST EVALUATION"
    )

    print()
    print("Target:")
    print(
        f"  {TARGET_NAME}"
    )

    print()
    print("Evaluation policy:")
    print(
        "  Train XGBoost on train.parquet only"
    )
    print(
        "  Validation used for comparison only"
    )
    print(
        "  Test used ONLY for final evaluation"
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
        "  No persisted dataset modification"
    )

    # ---------------------------------------------------------------
    # File validation
    # ---------------------------------------------------------------

    print_section(
        "DATASET FILE VALIDATION"
    )

    print(
        f"Processed dataset root"
        f"                  : "
        f"{DATASET_ROOT}"
    )

    print(
        f"Training dataset"
        f"                        : "
        f"{TRAIN_PATH}"
    )

    print(
        f"Validation dataset"
        f"                      : "
        f"{VALIDATION_PATH}"
    )

    print(
        f"Test dataset"
        f"                            : "
        f"{TEST_PATH}"
    )

    require_file(
        TRAIN_PATH,
        "Training dataset",
    )

    require_file(
        VALIDATION_PATH,
        "Validation dataset",
    )

    require_file(
        TEST_PATH,
        "Test dataset",
    )

    print_status(
        "Training file exists",
        "PASS",
    )

    print_status(
        "Validation file exists",
        "PASS",
    )

    print_status(
        "Test file exists",
        "PASS",
    )

    # ---------------------------------------------------------------
    # Manifest
    # ---------------------------------------------------------------

    print_section(
        "MANIFEST VALIDATION"
    )

    manifest = load_manifest()

    manifest_errors = validate_manifest(
        manifest
    )

    if manifest_errors:

        for error in manifest_errors:
            print(
                f"ERROR: {error}"
            )

        raise ValueError(
            "Manifest validation failed."
        )

    feature_columns = get_feature_columns(
        manifest
    )

    print_metric(
        "Registered feature count",
        len(feature_columns),
    )

    print_metric(
        "Target",
        TARGET_NAME,
    )

    print_status(
        "Manifest contract",
        "PASS",
    )

    # ---------------------------------------------------------------
    # Load datasets
    # ---------------------------------------------------------------

    print_section(
        "LOADING TRAINING DATASET"
    )

    train = load_dataset(
        TRAIN_PATH
    )

    print(
        f"Rows"
        f"                                    : "
        f"{len(train):,}"
    )

    print(
        f"Columns"
        f"                                 : "
        f"{len(train.columns):,}"
    )

    print_section(
        "LOADING VALIDATION DATASET"
    )

    validation = load_dataset(
        VALIDATION_PATH
    )

    print(
        f"Rows"
        f"                                    : "
        f"{len(validation):,}"
    )

    print(
        f"Columns"
        f"                                 : "
        f"{len(validation.columns):,}"
    )

    print_section(
        "LOADING TEST DATASET"
    )

    print(
        "IMPORTANT: Test data is now being loaded "
        "ONLY because model fitting has not started."
    )

    test = load_dataset(
        TEST_PATH
    )

    print(
        f"Rows"
        f"                                    : "
        f"{len(test):,}"
    )

    print(
        f"Columns"
        f"                                 : "
        f"{len(test.columns):,}"
    )

    # ---------------------------------------------------------------
    # Structure validation
    # ---------------------------------------------------------------

    print_section(
        "DATASET STRUCTURE VALIDATION"
    )

    validate_feature_registry(
        train,
        feature_columns,
        "Training dataset",
    )

    validate_feature_registry(
        validation,
        feature_columns,
        "Validation dataset",
    )

    validate_feature_registry(
        test,
        feature_columns,
        "Test dataset",
    )

    print_status(
        "Training feature registry",
        "PASS",
    )

    print_status(
        "Validation feature registry",
        "PASS",
    )

    print_status(
        "Test feature registry",
        "PASS",
    )

    if (
        train[feature_columns].columns.tolist()
        != validation[feature_columns].columns.tolist()
        or
        train[feature_columns].columns.tolist()
        != test[feature_columns].columns.tolist()
    ):

        raise ValueError(
            "Train/validation/test feature registries "
            "are not identical."
        )

    print_status(
        "Train/validation/test feature registry",
        "IDENTICAL",
    )

    # ---------------------------------------------------------------
    # Target validation
    # ---------------------------------------------------------------

    print_section(
        "TARGET CONTRACT VALIDATION"
    )

    validate_target(
        train,
        "Training dataset",
    )

    validate_target(
        validation,
        "Validation dataset",
    )

    validate_target(
        test,
        "Test dataset",
    )

    for name, dataframe in (
        ("Training", train),
        ("Validation", validation),
        ("Test", test),
    ):

        target = pd.to_numeric(
            dataframe[TARGET_NAME],
            errors="coerce",
        )

        print(
            f"{name} target rows"
            f"                    : "
            f"{len(target):,}"
        )

        print(
            f"{name} target nulls"
            f"                   : "
            f"{int(target.isna().sum()):,}"
        )

        print(
            f"{name} target mean"
            f"                    : "
            f"{target.mean():.6f}"
        )

        print(
            f"{name} target range"
            f"                   : "
            f"{target.min():.6f} -> "
            f"{target.max():.6f}"
        )

    print_status(
        "Target range validation",
        "PASS",
    )

    # ---------------------------------------------------------------
    # Chronological validation
    # ---------------------------------------------------------------

    print_section(
        "CHRONOLOGICAL SPLIT VALIDATION"
    )

    validate_chronological_relationship(
        train,
        validation,
        test,
    )

    # ---------------------------------------------------------------
    # Observation isolation
    # ---------------------------------------------------------------

    print_section(
        "CROSS-SPLIT OBSERVATION ISOLATION"
    )

    validate_observation_isolation(
        train,
        validation,
        test,
    )

    # ---------------------------------------------------------------
    # Feature preparation
    # ---------------------------------------------------------------

    print_section(
        "PREPARING MODEL MATRICES"
    )

    X_train = prepare_features(
        train,
        feature_columns,
    )

    X_validation = prepare_features(
        validation,
        feature_columns,
    )

    X_test = prepare_features(
        test,
        feature_columns,
    )

    y_train = pd.to_numeric(
        train[TARGET_NAME],
        errors="coerce",
    )

    y_validation = pd.to_numeric(
        validation[TARGET_NAME],
        errors="coerce",
    )

    y_test = pd.to_numeric(
        test[TARGET_NAME],
        errors="coerce",
    )

    print_metric(
        "Registered features",
        len(feature_columns),
    )

    print_metric(
        "Training matrix shape",
        X_train.shape,
    )

    print_metric(
        "Validation matrix shape",
        X_validation.shape,
    )

    print_metric(
        "Test matrix shape",
        X_test.shape,
    )

    print(
        "Metadata columns excluded from model matrix:"
    )

    print(
        f"  - {FACILITY_COLUMN}"
    )

    print(
        f"  - {TIMESTAMP_COLUMN}"
    )

    print(
        "Categorical features delegated to XGBoostModel:"
    )

    for column in CATEGORICAL_FEATURES:
        print(
            f"  - {column}"
        )

    validate_feature_types(
        X_train,
        "Training",
    )

    validate_feature_types(
        X_validation,
        "Validation",
    )

    validate_feature_types(
        X_test,
        "Test",
    )

    validate_infinite_numeric_values(
        X_train,
        "Training",
    )

    validate_infinite_numeric_values(
        X_validation,
        "Validation",
    )

    validate_infinite_numeric_values(
        X_test,
        "Test",
    )

    print_status(
        "Feature/target separation",
        "PASS",
    )

    # ---------------------------------------------------------------
    # Configuration
    # ---------------------------------------------------------------

    print_model_configuration()

    # ---------------------------------------------------------------
    # CRITICAL: MODEL FIT
    #
    # At this point all datasets are loaded, but ONLY X_train/y_train
    # are passed into fit().
    # ---------------------------------------------------------------

    model = train_model(
        X_train,
        y_train,
    )

    # ---------------------------------------------------------------
    # Validation evaluation
    # ---------------------------------------------------------------

    print_section(
        "VALIDATION EVALUATION"
    )

    print(
        "Validation is used only for prediction/evaluation."
    )

    validation_predictions = predict(
        model,
        X_validation,
        "Validation",
    )

    validation_metrics = evaluate_predictions(
        model_name="xgboost",
        dataset_name="validation",
        y_true=y_validation.to_numpy(
            dtype=float
        ),
        predictions=validation_predictions,
    )

    print()
    print(
        "Validation metrics:"
    )

    print(
        f"  MAE :  {validation_metrics.mae:.6f}"
    )

    print(
        f"  RMSE:  {validation_metrics.rmse:.6f}"
    )

    print(
        f"  R²  :  {validation_metrics.r2:.6f}"
    )

    print(
        f"  MAPE:  {validation_metrics.mape:.4f}%"
    )

    print(
        f"  N   :  {validation_metrics.sample_count:,}"
    )

    # ---------------------------------------------------------------
    # FINAL TEST EVALUATION
    # ---------------------------------------------------------------

    print_header(
        "FINAL UNTOUCHED TEST EVALUATION"
    )

    print(
        "The model has already been fitted."
    )

    print(
        "No test data was supplied to fit()."
    )

    print(
        "No test data was used for tuning."
    )

    print(
        "Generating final test predictions..."
    )

    test_predictions = predict(
        model,
        X_test,
        "Test",
    )

    test_metrics = evaluate_predictions(
        model_name="xgboost",
        dataset_name="test",
        y_true=y_test.to_numpy(
            dtype=float
        ),
        predictions=test_predictions,
    )

    print()
    print(
        "FINAL TEST METRICS:"
    )

    print(
        f"  MAE :  {test_metrics.mae:.6f}"
    )

    print(
        f"  RMSE:  {test_metrics.rmse:.6f}"
    )

    print(
        f"  R²  :  {test_metrics.r2:.6f}"
    )

    print(
        f"  MAPE:  {test_metrics.mape:.4f}%"
    )

    print(
        f"  N   :  {test_metrics.sample_count:,}"
    )

    # ---------------------------------------------------------------
    # Generalization
    # ---------------------------------------------------------------

    generalization = (
        build_generalization_metrics(
            validation_metrics,
            test_metrics,
        )
    )

    print_section(
        "VALIDATION -> TEST GENERALIZATION"
    )

    print(
        f"Validation MAE"
        f"                         : "
        f"{generalization.validation_mae:.6f}"
    )

    print(
        f"Test MAE"
        f"                              : "
        f"{generalization.test_mae:.6f}"
    )

    print(
        f"MAE change"
        f"                             : "
        f"{generalization.mae_absolute_change:+.6f}"
    )

    print(
        f"MAE percentage change"
        f"                     : "
        f"{generalization.mae_percentage_change:+.2f}%"
    )

    print()

    print(
        f"Validation RMSE"
        f"                       : "
        f"{generalization.validation_rmse:.6f}"
    )

    print(
        f"Test RMSE"
        f"                            : "
        f"{generalization.test_rmse:.6f}"
    )

    print(
        f"RMSE change"
        f"                           : "
        f"{generalization.rmse_absolute_change:+.6f}"
    )

    print(
        f"RMSE percentage change"
        f"                   : "
        f"{generalization.rmse_percentage_change:+.2f}%"
    )

    print()

    print(
        f"Validation R²"
        f"                         : "
        f"{generalization.validation_r2:.6f}"
    )

    print(
        f"Test R²"
        f"                              : "
        f"{generalization.test_r2:.6f}"
    )

    print(
        f"R² change"
        f"                             : "
        f"{generalization.r2_absolute_change:+.6f}"
    )

    print(
        f"R² relative change"
        f"                     : "
        f"{generalization.r2_percentage_change:+.2f}%"
    )

    print()

    print(
        f"Validation MAPE"
        f"                       : "
        f"{generalization.validation_mape:.4f}%"
    )

    print(
        f"Test MAPE"
        f"                            : "
        f"{generalization.test_mape:.4f}%"
    )

    print(
        f"MAPE change"
        f"                           : "
        f"{generalization.mape_absolute_change:+.4f} "
        "percentage points"
    )

    print(
        f"MAPE percentage change"
        f"                   : "
        f"{generalization.mape_percentage_change:+.2f}%"
    )

    # ---------------------------------------------------------------
    # Baseline context
    # ---------------------------------------------------------------

    print_section(
        "BASELINE CONTEXT"
    )

    print(
        "Previously established validation baselines:"
    )

    print(
        f"  Mean baseline MAE"
        f"                     : "
        f"{BASELINE_VALIDATION_RESULTS['mean_baseline']['mae']:.6f}"
    )

    print(
        f"  Last-value baseline MAE"
        f"               : "
        f"{BASELINE_VALIDATION_RESULTS['last_value_baseline']['mae']:.6f}"
    )

    print()

    print(
        "XGBoost validation MAE"
        f"                   : "
        f"{validation_metrics.mae:.6f}"
    )

    print(
        "XGBoost test MAE"
        f"                       : "
        f"{test_metrics.mae:.6f}"
    )

    # ---------------------------------------------------------------
    # Persist results
    # ---------------------------------------------------------------

    print_section(
        "PERSISTING TEST EVALUATION RESULTS"
    )

    print(
        f"Output directory"
        f"                      : "
        f"{OUTPUT_DIR}"
    )

    persist_results(
        train_summary=build_dataset_summary(
            "train",
            TRAIN_PATH,
            train,
            feature_columns,
        ),
        validation_summary=build_dataset_summary(
            "validation",
            VALIDATION_PATH,
            validation,
            feature_columns,
        ),
        test_summary=build_dataset_summary(
            "test",
            TEST_PATH,
            test,
            feature_columns,
        ),
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        generalization=generalization,
        model=model,
    )

    print(
        f"JSON results"
        f"                          : "
        f"{JSON_OUTPUT}"
    )

    print(
        f"CSV results"
        f"                           : "
        f"{CSV_OUTPUT}"
    )

    # ---------------------------------------------------------------
    # Final assertions
    # ---------------------------------------------------------------

    run_final_assertions(
        train=train,
        validation=validation,
        test=test,
        feature_columns=feature_columns,
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        validation_predictions=validation_predictions,
        test_predictions=test_predictions,
    )

    # ---------------------------------------------------------------
    # Final summary
    # ---------------------------------------------------------------

    print_header(
        "BIRMINGHAM XGBOOST FINAL TEST EVALUATION COMPLETED"
    )

    print(
        f"Target:"
        f"              {TARGET_NAME}"
    )

    print(
        f"Training rows:"
        f"       {len(train):,}"
    )

    print(
        f"Validation rows:"
        f"     {len(validation):,}"
    )

    print(
        f"Test rows:"
        f"           {len(test):,}"
    )

    print(
        f"Features:"
        f"            {len(feature_columns)}"
    )

    print()
    print(
        "FINAL TEST PERFORMANCE"
    )

    print(
        f"  MAE :  {test_metrics.mae:.6f}"
    )

    print(
        f"  RMSE:  {test_metrics.rmse:.6f}"
    )

    print(
        f"  R²  :  {test_metrics.r2:.6f}"
    )

    print(
        f"  MAPE:  {test_metrics.mape:.4f}%"
    )

    print()
    print(
        "Evaluation integrity:"
    )

    print(
        "  ✓ Model fitted on training data only"
    )

    print(
        "  ✓ Validation data not used during fit"
    )

    print(
        "  ✓ Test data not used during fit"
    )

    print(
        "  ✓ No hyperparameter tuning"
    )

    print(
        "  ✓ No feature pipeline rebuild"
    )

    print(
        "  ✓ No persisted dataset modification"
    )

    print(
        "  ✓ Chronological ordering validated"
    )

    print(
        "  ✓ Cross-split observation isolation validated"
    )

    print()
    print(
        "Birmingham XGBoost final test evaluation "
        "is complete."
    )

    return 0


# =====================================================================
# ENTRY POINT
# =====================================================================


if __name__ == "__main__":

    try:

        raise SystemExit(
            main()
        )

    except KeyboardInterrupt:

        print()
        print(
            "Evaluation interrupted by user."
        )

        raise SystemExit(130)

    except Exception as exc:

        print_header(
            "BIRMINGHAM XGBOOST FINAL TEST EVALUATION FAILED"
        )

        print(
            f"ERROR: {exc}"
        )

        print()
        print(
            "No persisted training, validation, or "
            "test datasets were modified."
        )

        print(
            "The final test result should NOT be "
            "used until the reported error is resolved."
        )

        raise SystemExit(1)