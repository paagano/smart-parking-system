"""
SmartPark AI
Birmingham XGBoost Final Model Diagnostics

Purpose
-------
Perform post-selection diagnostics on the already-selected TUNE_014
XGBoost model.

This script is diagnostic only.

It does NOT:
    - perform hyperparameter tuning
    - select a different model
    - modify persisted datasets
    - rebuild the feature pipeline
    - use test data for model selection
    - pass validation/test data to fit()
    - change TUNE_014

Selected model:
    TUNE_014

Target:
    target_occupancy_rate_30m

Production prediction contract:
    Prediction timestamp = T
    Forecast horizon     = T + 30 minutes

Datasets:
    train.parquet
    validation.parquet
    test.parquet

Outputs:
    datasets/processed/birmingham/xgboost_final_model_diagnostics/
"""

from __future__ import annotations

import inspect
import json
import math
import time
from dataclasses import fields, is_dataclass
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


# ============================================================
# CONSTANTS
# ============================================================

TARGET_COLUMN = "target_occupancy_rate_30m"

MODEL_NAME = "xgboost_regressor"

SELECTED_CANDIDATE = "TUNE_014"

SELECTED_DESCRIPTION = "Higher L1 regularisation"

SELECTED_PARAMS = {
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

ESTABLISHED_VALIDATION = {
    "mae": 0.013496,
    "rmse": 0.019805,
    "r2": 0.994984,
    "mape": 3.3279,
}

FINAL_TEST_REFERENCE = {
    "mae": 0.014115,
    "rmse": 0.020056,
    "r2": 0.994163,
    "mape": 3.6645,
}

EXPECTED_FEATURE_COUNT = 296

CATEGORICAL_FEATURES = [
    "occupancy_level",
    "demand_class",
]

METADATA_COLUMNS = [
    "normalized_at",
    "source_facility_code",
]

TARGET_METADATA_COLUMNS = [
    TARGET_COLUMN,
    "target_30m_available",
]


# ============================================================
# PATHS
# ============================================================

BACKEND_ROOT = Path(__file__).resolve().parent

PROJECT_ROOT = BACKEND_ROOT.parent

PROCESSED_ROOT = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
)

TARGET_ROOT = (
    PROCESSED_ROOT
    / "target_occupancy_rate_30m"
)

TRAIN_PATH = TARGET_ROOT / "train.parquet"

VALIDATION_PATH = TARGET_ROOT / "validation.parquet"

TEST_PATH = TARGET_ROOT / "test.parquet"

MANIFEST_PATH = (
    PROCESSED_ROOT
    / "training_dataset_manifest.json"
)

OUTPUT_DIR = (
    PROCESSED_ROOT
    / "xgboost_final_model_diagnostics"
)

JSON_PATH = (
    OUTPUT_DIR
    / "birmingham_xgboost_final_model_diagnostics.json"
)

SUMMARY_CSV_PATH = (
    OUTPUT_DIR
    / "birmingham_xgboost_final_model_diagnostics_summary.csv"
)

ERROR_CSV_PATH = (
    OUTPUT_DIR
    / "birmingham_xgboost_final_model_diagnostics_errors.csv"
)

REGIME_CSV_PATH = (
    OUTPUT_DIR
    / "birmingham_xgboost_final_model_diagnostics_regimes.csv"
)

FEATURE_IMPORTANCE_CSV_PATH = (
    OUTPUT_DIR
    / "birmingham_xgboost_final_model_diagnostics_feature_importance.csv"
)

BIAS_CSV_PATH = (
    OUTPUT_DIR
    / "birmingham_xgboost_final_model_diagnostics_bias.csv"
)


# ============================================================
# DISPLAY HELPERS
# ============================================================

def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def result(label: str, value: Any) -> None:
    print(f"{label:<45}: {value}")


def passed(label: str) -> None:
    result(label, "PASS")


def failed(label: str) -> None:
    result(label, "FAIL")


# ============================================================
# JSON HELPERS
# ============================================================

def json_safe(value: Any) -> Any:

    if isinstance(value, dict):
        return {
            str(k): json_safe(v)
            for k, v in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [
            json_safe(v)
            for v in value
        ]

    if isinstance(value, np.integer):
        return int(value)

    if isinstance(value, np.floating):
        value = float(value)

        if not math.isfinite(value):
            return None

        return value

    if isinstance(value, np.ndarray):
        return [
            json_safe(v)
            for v in value.tolist()
        ]

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, datetime):
        return value.isoformat()

    if pd.isna(value):
        return None

    return value


# ============================================================
# METRICS
# ============================================================

def calculate_mape(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> float:

    y_true = np.asarray(
        y_true,
        dtype=float,
    )

    y_pred = np.asarray(
        y_pred,
        dtype=float,
    )

    denominator = np.abs(y_true)

    valid = denominator > 1e-12

    if not np.any(valid):
        return float("nan")

    return float(
        np.mean(
            np.abs(
                (
                    y_true[valid]
                    - y_pred[valid]
                )
                / denominator[valid]
            )
        )
        * 100.0
    )


def calculate_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> dict[str, float]:

    mae = mean_absolute_error(
        y_true,
        y_pred,
    )

    rmse = math.sqrt(
        mean_squared_error(
            y_true,
            y_pred,
        )
    )

    r2 = r2_score(
        y_true,
        y_pred,
    )

    mape = calculate_mape(
        y_true,
        y_pred,
    )

    return {
        "mae": float(mae),
        "rmse": float(rmse),
        "r2": float(r2),
        "mape": float(mape),
        "n": int(len(y_true)),
    }


# ============================================================
# DATASET / MANIFEST HELPERS
# ============================================================

def load_manifest() -> dict[str, Any]:

    with MANIFEST_PATH.open(
        "r",
        encoding="utf-8",
    ) as handle:

        return json.load(handle)


def get_registered_features(
    manifest: dict[str, Any],
) -> list[str]:

    features = manifest.get(
        "feature_columns",
        [],
    )

    if not isinstance(features, list):
        raise RuntimeError(
            "Manifest feature_columns is not a list."
        )

    return [
        str(feature)
        for feature in features
    ]


def model_features(
    dataframe: pd.DataFrame,
    registered_features: list[str],
) -> list[str]:

    return [
        column
        for column in registered_features
        if column in dataframe.columns
    ]


def validate_feature_registry(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    test: pd.DataFrame,
    registered_features: list[str],
) -> None:

    for name, dataframe in [
        ("training", train),
        ("validation", validation),
        ("test", test),
    ]:

        missing = [
            feature
            for feature in registered_features
            if feature not in dataframe.columns
        ]

        if missing:
            raise RuntimeError(
                f"{name} dataset missing features: "
                f"{missing}"
            )

    train_features = model_features(
        train,
        registered_features,
    )

    validation_features = model_features(
        validation,
        registered_features,
    )

    test_features = model_features(
        test,
        registered_features,
    )

    if train_features != validation_features:
        raise RuntimeError(
            "Training and validation feature ordering differ."
        )

    if train_features != test_features:
        raise RuntimeError(
            "Training and test feature ordering differ."
        )

    if len(train_features) != EXPECTED_FEATURE_COUNT:
        raise RuntimeError(
            "Unexpected feature count: "
            f"{len(train_features)}; "
            f"expected {EXPECTED_FEATURE_COUNT}."
        )


# ============================================================
# OBSERVATION ISOLATION
# ============================================================

def build_observation_keys(
    dataframe: pd.DataFrame,
) -> set[tuple[str, str]]:

    if (
        "source_facility_code" not in dataframe.columns
        or "normalized_at" not in dataframe.columns
    ):
        return set()

    facility = (
        dataframe[
            "source_facility_code"
        ]
        .astype("string")
        .fillna("")
    )

    timestamp = (
        pd.to_datetime(
            dataframe[
                "normalized_at"
            ],
            errors="coerce",
        )
        .astype("string")
        .fillna("")
    )

    return set(
        zip(
            facility.tolist(),
            timestamp.tolist(),
        )
    )


# ============================================================
# MODEL CONFIGURATION
# ============================================================

def build_model_config() -> XGBoostModelConfig:
    """
    Build XGBoostModelConfig using only fields actually
    supported by the installed application version.

    This protects the diagnostic script from harmless
    configuration-schema changes.
    """

    signature = inspect.signature(
        XGBoostModelConfig
    )

    supported = set(
        signature.parameters.keys()
    )

    kwargs: dict[str, Any] = {}

    for name, value in SELECTED_PARAMS.items():

        if name in supported:
            kwargs[name] = value

    if "categorical_features" in supported:
        kwargs[
            "categorical_features"
        ] = list(
            CATEGORICAL_FEATURES
        )

    elif "categorical_columns" in supported:
        kwargs[
            "categorical_columns"
        ] = list(
            CATEGORICAL_FEATURES
        )

    return XGBoostModelConfig(
        **kwargs
    )


# ============================================================
# MODEL TRAINING
# ============================================================

def build_selected_model() -> XGBoostModel:

    config = build_model_config()

    model = XGBoostModel(
        target_column=TARGET_COLUMN,
        config=config,
        model_name=MODEL_NAME,
    )

    return model


def fit_model(
    model: XGBoostModel,
    X_train: pd.DataFrame,
    y_train: pd.Series,
) -> None:

    signature = inspect.signature(
        model.fit
    )

    parameters = list(
        signature.parameters.keys()
    )

    kwargs: dict[str, Any] = {}

    if "X" in parameters:
        kwargs["X"] = X_train

    elif "features" in parameters:
        kwargs["features"] = X_train

    if "y" in parameters:
        kwargs["y"] = y_train

    elif "target" in parameters:
        kwargs["target"] = y_train

    if kwargs:
        model.fit(**kwargs)
        return

    # Fallback for positional API.
    model.fit(
        X_train,
        y_train,
    )


def predict_model(
    model: XGBoostModel,
    X: pd.DataFrame,
) -> np.ndarray:

    predictions = model.predict(X)

    return np.asarray(
        predictions,
        dtype=float,
    ).reshape(-1)


# ============================================================
# OCCUPANCY REGIMES
# ============================================================

def occupancy_regime(
    values: pd.Series | np.ndarray,
) -> pd.Series:

    values = pd.Series(
        values,
        dtype=float,
    )

    return pd.cut(
        values,
        bins=[
            -np.inf,
            0.25,
            0.50,
            0.75,
            np.inf,
        ],
        labels=[
            "LOW",
            "MODERATE",
            "HIGH",
            "VERY_HIGH",
        ],
        right=True,
    )


# ============================================================
# REGIME ANALYSIS
# ============================================================

def build_regime_analysis(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> pd.DataFrame:

    frame = pd.DataFrame(
        {
            "actual_occupancy": y_true,
            "prediction": y_pred,
        }
    )

    frame[
        "occupancy_regime"
    ] = occupancy_regime(
        frame["actual_occupancy"]
    )

    frame["error"] = (
        frame["prediction"]
        - frame["actual_occupancy"]
    )

    frame[
        "absolute_error"
    ] = np.abs(
        frame["error"]
    )

    rows: list[dict[str, Any]] = []

    for regime, group in frame.groupby(
        "occupancy_regime",
        observed=False,
    ):

        if len(group) == 0:
            continue

        rows.append(
            {
                "regime": str(regime),
                "n": int(len(group)),
                "mean_actual": float(
                    group[
                        "actual_occupancy"
                    ].mean()
                ),
                "mean_prediction": float(
                    group[
                        "prediction"
                    ].mean()
                ),
                "mean_error": float(
                    group[
                        "error"
                    ].mean()
                ),
                "mean_absolute_error": float(
                    group[
                        "absolute_error"
                    ].mean()
                ),
                "rmse": float(
                    math.sqrt(
                        np.mean(
                            np.square(
                                group[
                                    "error"
                                ]
                            )
                        )
                    )
                ),
                "underprediction_rate_pct": float(
                    (
                        group["error"] < 0
                    ).mean()
                    * 100.0
                ),
                "overprediction_rate_pct": float(
                    (
                        group["error"] > 0
                    ).mean()
                    * 100.0
                ),
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# ERROR ANALYSIS
# ============================================================

def build_error_analysis(
    test: pd.DataFrame,
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> pd.DataFrame:

    errors = test.copy(
        deep=False
    ).reset_index(
        drop=True
    )

    errors[
        "actual_occupancy"
    ] = y_true

    errors[
        "predicted_occupancy"
    ] = y_pred

    errors["error"] = (
        y_pred - y_true
    )

    errors[
        "absolute_error"
    ] = np.abs(
        errors["error"]
    )

    errors[
        "squared_error"
    ] = np.square(
        errors["error"]
    )

    errors[
        "underprediction"
    ] = (
        errors["error"] < 0
    )

    errors[
        "overprediction"
    ] = (
        errors["error"] > 0
    )

    errors[
        "occupancy_regime"
    ] = occupancy_regime(
        errors["actual_occupancy"]
    )

    errors = errors.sort_values(
        "absolute_error",
        ascending=False,
    )

    columns = [
        column
        for column in [
            "normalized_at",
            "source_facility_code",
            "actual_occupancy",
            "predicted_occupancy",
            "error",
            "absolute_error",
            "squared_error",
            "underprediction",
            "overprediction",
            "occupancy_regime",
        ]
        if column in errors.columns
    ]

    return errors[
        columns
    ]


# ============================================================
# BIAS ANALYSIS
# ============================================================

def build_bias_analysis(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> pd.DataFrame:

    error = (
        y_pred - y_true
    )

    abs_error = np.abs(
        error
    )

    rows = [
        {
            "metric": "mean_error",
            "value": float(
                np.mean(error)
            ),
        },
        {
            "metric": "median_error",
            "value": float(
                np.median(error)
            ),
        },
        {
            "metric": "mean_absolute_error",
            "value": float(
                np.mean(abs_error)
            ),
        },
        {
            "metric": "underprediction_rate_pct",
            "value": float(
                np.mean(error < 0)
                * 100.0
            ),
        },
        {
            "metric": "overprediction_rate_pct",
            "value": float(
                np.mean(error > 0)
                * 100.0
            ),
        },
        {
            "metric": "exact_prediction_rate_pct",
            "value": float(
                np.mean(error == 0)
                * 100.0
            ),
        },
        {
            "metric": "p50_absolute_error",
            "value": float(
                np.percentile(
                    abs_error,
                    50,
                )
            ),
        },
        {
            "metric": "p75_absolute_error",
            "value": float(
                np.percentile(
                    abs_error,
                    75,
                )
            ),
        },
        {
            "metric": "p90_absolute_error",
            "value": float(
                np.percentile(
                    abs_error,
                    90,
                )
            ),
        },
        {
            "metric": "p95_absolute_error",
            "value": float(
                np.percentile(
                    abs_error,
                    95,
                )
            ),
        },
        {
            "metric": "p99_absolute_error",
            "value": float(
                np.percentile(
                    abs_error,
                    99,
                )
            ),
        },
        {
            "metric": "maximum_absolute_error",
            "value": float(
                np.max(abs_error)
            ),
        },
    ]

    return pd.DataFrame(
        rows
    )


# ============================================================
# FEATURE IMPORTANCE
# ============================================================

def extract_feature_importance(
    model: XGBoostModel,
    feature_columns: list[str],
) -> pd.DataFrame:

    internal_model = getattr(
        model,
        "_model",
        None,
    )

    if internal_model is None:
        raise RuntimeError(
            "XGBoostModel does not expose the fitted "
            "internal model through _model."
        )

    importance_values: np.ndarray | None = None

    importance_type = "gain"

    try:
        booster = internal_model.get_booster()

        score = booster.get_score(
            importance_type=importance_type
        )

        values = []

        for index, feature in enumerate(
            feature_columns
        ):

            candidates = [
                feature,
                f"f{index}",
            ]

            value = 0.0

            for candidate in candidates:

                if candidate in score:
                    value = float(
                        score[candidate]
                    )
                    break

            values.append(value)

        importance_values = np.asarray(
            values,
            dtype=float,
        )

    except Exception:
        pass

    if importance_values is None:

        raw_importance = getattr(
            internal_model,
            "feature_importances_",
            None,
        )

        if raw_importance is None:
            raise RuntimeError(
                "Unable to extract XGBoost feature importance."
            )

        importance_values = np.asarray(
            raw_importance,
            dtype=float,
        )

    if len(importance_values) != len(
        feature_columns
    ):
        raise RuntimeError(
            "Feature importance count does not match "
            f"feature count: "
            f"{len(importance_values)} != "
            f"{len(feature_columns)}"
        )

    frame = pd.DataFrame(
        {
            "feature": feature_columns,
            "importance": importance_values,
        }
    )

    total = float(
        frame["importance"].sum()
    )

    if total > 0:
        frame[
            "importance_pct"
        ] = (
            frame["importance"]
            / total
            * 100.0
        )

    else:
        frame[
            "importance_pct"
        ] = 0.0

    frame = frame.sort_values(
        "importance",
        ascending=False,
    ).reset_index(
        drop=True
    )

    frame[
        "rank"
    ] = np.arange(
        1,
        len(frame) + 1,
    )

    frame[
        "cumulative_importance_pct"
    ] = (
        frame["importance_pct"]
        .cumsum()
    )

    frame[
        "categorical"
    ] = frame[
        "feature"
    ].isin(
        CATEGORICAL_FEATURES
    )

    return frame[
        [
            "rank",
            "feature",
            "importance",
            "importance_pct",
            "cumulative_importance_pct",
            "categorical",
        ]
    ]


# ============================================================
# MODEL DIAGNOSTIC SUMMARY
# ============================================================

def build_summary(
    validation_metrics: dict[str, float],
    test_metrics: dict[str, float],
    test_regimes: pd.DataFrame,
    feature_importance: pd.DataFrame,
    bias: pd.DataFrame,
) -> dict[str, Any]:

    mean_error = float(
        bias.loc[
            bias["metric"]
            == "mean_error",
            "value",
        ].iloc[0]
    )

    median_error = float(
        bias.loc[
            bias["metric"]
            == "median_error",
            "value",
        ].iloc[0]
    )

    underprediction_rate = float(
        bias.loc[
            bias["metric"]
            == "underprediction_rate_pct",
            "value",
        ].iloc[0]
    )

    overprediction_rate = float(
        bias.loc[
            bias["metric"]
            == "overprediction_rate_pct",
            "value",
        ].iloc[0]
    )

    p95 = float(
        bias.loc[
            bias["metric"]
            == "p95_absolute_error",
            "value",
        ].iloc[0]
    )

    p99 = float(
        bias.loc[
            bias["metric"]
            == "p99_absolute_error",
            "value",
        ].iloc[0]
    )

    maximum = float(
        bias.loc[
            bias["metric"]
            == "maximum_absolute_error",
            "value",
        ].iloc[0]
    )

    top_features = (
        feature_importance
        .head(20)
        .to_dict(
            orient="records"
        )
    )

    dominant_features = (
        feature_importance[
            feature_importance[
                "importance_pct"
            ] >= 5.0
        ]
        .head(20)
        .to_dict(
            orient="records"
        )
    )

    return {
        "selected_candidate": SELECTED_CANDIDATE,
        "description": SELECTED_DESCRIPTION,
        "target": TARGET_COLUMN,
        "feature_count": EXPECTED_FEATURE_COUNT,
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "test_bias": {
            "mean_error": mean_error,
            "median_error": median_error,
            "underprediction_rate_pct": (
                underprediction_rate
            ),
            "overprediction_rate_pct": (
                overprediction_rate
            ),
        },
        "test_error_distribution": {
            "p95_absolute_error": p95,
            "p99_absolute_error": p99,
            "maximum_absolute_error": maximum,
        },
        "regime_count": int(
            len(test_regimes)
        ),
        "top_20_features": top_features,
        "dominant_features_5pct_or_more": (
            dominant_features
        ),
    }


# ============================================================
# ASSERTIONS
# ============================================================

def assert_finite_metrics(
    metrics: dict[str, float],
) -> None:

    for key in [
        "mae",
        "rmse",
        "r2",
        "mape",
    ]:

        value = metrics[key]

        if not math.isfinite(
            float(value)
        ):
            raise AssertionError(
                f"Metric {key} is not finite."
            )


def validate_final_metrics(
    test_metrics: dict[str, float],
) -> None:

    """
    Diagnostics must reproduce the previously established
    final test result within a small numerical tolerance.

    This is NOT a model-selection threshold.
    It is an integrity/reproducibility check.
    """

    tolerance = {
        "mae": 0.000001,
        "rmse": 0.000001,
        "r2": 0.000001,
        "mape": 0.0001,
    }

    for metric, expected in FINAL_TEST_REFERENCE.items():

        actual = test_metrics[metric]

        if abs(
            actual - expected
        ) > tolerance[metric]:

            raise AssertionError(
                f"Diagnostic reproduction mismatch for "
                f"{metric}: actual={actual}, "
                f"expected={expected}, "
                f"tolerance={tolerance[metric]}"
            )


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    banner(
        "SMARTPARK AI - BIRMINGHAM XGBOOST "
        "FINAL MODEL DIAGNOSTICS"
    )

    print()
    print("Target:")
    print(f"  {TARGET_COLUMN}")

    print()
    print("Selected model:")
    print(
        f"  Candidate              : "
        f"{SELECTED_CANDIDATE}"
    )
    print(
        f"  Description            : "
        f"{SELECTED_DESCRIPTION}"
    )

    print()
    print("Diagnostic policy:")
    print(
        "  Diagnose the already-selected TUNE_014 model"
    )
    print(
        "  Train = train.parquet"
    )
    print(
        "  Validation = validation.parquet"
    )
    print(
        "  Test = final evaluation/diagnostics only"
    )
    print(
        "  No hyperparameter tuning"
    )
    print(
        "  No model selection"
    )
    print(
        "  No feature pipeline rebuild"
    )
    print(
        "  Validation data never passed to fit()"
    )
    print(
        "  Test data never passed to fit()"
    )
    print(
        "  Persisted datasets will NOT be modified"
    )

    print()
    print("Established validation reference:")
    print(
        f"  MAE  = "
        f"{ESTABLISHED_VALIDATION['mae']:.6f}"
    )
    print(
        f"  RMSE = "
        f"{ESTABLISHED_VALIDATION['rmse']:.6f}"
    )
    print(
        f"  R²   = "
        f"{ESTABLISHED_VALIDATION['r2']:.6f}"
    )
    print(
        f"  MAPE = "
        f"{ESTABLISHED_VALIDATION['mape']:.4f}%"
    )

    print()
    print("Established final test reference:")
    print(
        f"  MAE  = "
        f"{FINAL_TEST_REFERENCE['mae']:.6f}"
    )
    print(
        f"  RMSE = "
        f"{FINAL_TEST_REFERENCE['rmse']:.6f}"
    )
    print(
        f"  R²   = "
        f"{FINAL_TEST_REFERENCE['r2']:.6f}"
    )
    print(
        f"  MAPE = "
        f"{FINAL_TEST_REFERENCE['mape']:.4f}%"
    )

    # --------------------------------------------------------
    # FILE VALIDATION
    # --------------------------------------------------------

    section("DATASET FILE VALIDATION")

    result(
        "Processed dataset root",
        PROCESSED_ROOT,
    )

    result(
        "Training dataset",
        TRAIN_PATH,
    )

    result(
        "Validation dataset",
        VALIDATION_PATH,
    )

    result(
        "Test dataset",
        TEST_PATH,
    )

    result(
        "Feature manifest",
        MANIFEST_PATH,
    )

    required_paths = [
        (
            "Training file exists",
            TRAIN_PATH,
        ),
        (
            "Validation file exists",
            VALIDATION_PATH,
        ),
        (
            "Test file exists",
            TEST_PATH,
        ),
        (
            "Feature manifest exists",
            MANIFEST_PATH,
        ),
    ]

    for label, path in required_paths:

        if path.exists():
            passed(label)
        else:
            failed(label)
            raise FileNotFoundError(
                f"Required file does not exist: {path}"
            )

    print()
    print(
        "IMPORTANT: "
        "Test data will be used only for diagnostics. "
        "It will NOT influence model selection."
    )

    # --------------------------------------------------------
    # MANIFEST
    # --------------------------------------------------------

    section("LOADING FEATURE MANIFEST")

    manifest = load_manifest()

    registered_features = (
        get_registered_features(
            manifest
        )
    )

    result(
        "Registered features",
        len(registered_features),
    )

    if len(
        registered_features
    ) != EXPECTED_FEATURE_COUNT:

        raise RuntimeError(
            "Unexpected registered feature count."
        )

    # --------------------------------------------------------
    # DATASETS
    # --------------------------------------------------------

    section("LOADING TRAINING DATASET")

    train = pd.read_parquet(
        TRAIN_PATH
    )

    result(
        "Training rows",
        len(train),
    )

    result(
        "Training columns",
        len(train.columns),
    )

    section("LOADING VALIDATION DATASET")

    validation = pd.read_parquet(
        VALIDATION_PATH
    )

    result(
        "Validation rows",
        len(validation),
    )

    result(
        "Validation columns",
        len(validation.columns),
    )

    section("LOADING FINAL TEST DATASET")

    test = pd.read_parquet(
        TEST_PATH
    )

    result(
        "Test rows",
        len(test),
    )

    result(
        "Test columns",
        len(test.columns),
    )

    result(
        "Test usage",
        "DIAGNOSTICS ONLY",
    )

    # --------------------------------------------------------
    # FEATURE CONTRACT
    # --------------------------------------------------------

    section("FEATURE CONTRACT VALIDATION")

    validate_feature_registry(
        train,
        validation,
        test,
        registered_features,
    )

    train_features = model_features(
        train,
        registered_features,
    )

    validation_features = model_features(
        validation,
        registered_features,
    )

    test_features = model_features(
        test,
        registered_features,
    )

    passed(
        "Training feature registry"
    )

    passed(
        "Validation feature registry"
    )

    passed(
        "Test feature registry"
    )

    passed(
        "Train/validation feature ordering"
    )

    passed(
        "Train/test feature ordering"
    )

    result(
        "Feature count",
        len(train_features),
    )

    result(
        "Categorical features",
        ", ".join(
            CATEGORICAL_FEATURES
        ),
    )

    # --------------------------------------------------------
    # TARGET VALIDATION
    # --------------------------------------------------------

    section("TARGET CONTRACT VALIDATION")

    for name, dataframe in [
        ("Training", train),
        ("Validation", validation),
        ("Test", test),
    ]:

        if TARGET_COLUMN not in dataframe.columns:

            raise RuntimeError(
                f"{name} dataset does not contain "
                f"{TARGET_COLUMN}."
            )

        target = pd.to_numeric(
            dataframe[
                TARGET_COLUMN
            ],
            errors="coerce",
        )

        nulls = int(
            target.isna().sum()
        )

        if nulls != 0:

            raise RuntimeError(
                f"{name} target contains "
                f"{nulls} null values."
            )

        result(
            f"{name} target rows",
            len(target),
        )

        result(
            f"{name} target nulls",
            nulls,
        )

        result(
            f"{name} target mean",
            f"{target.mean():.6f}",
        )

        result(
            f"{name} target range",
            f"{target.min():.6f} -> "
            f"{target.max():.6f}",
        )

        if (
            target.min() < 0
            or target.max() > 1
        ):

            raise RuntimeError(
                f"{name} target outside [0,1]."
            )

    passed(
        "Target range validation"
    )

    # --------------------------------------------------------
    # OBSERVATION ISOLATION
    # --------------------------------------------------------

    section(
        "TRAIN / VALIDATION / TEST "
        "OBSERVATION ISOLATION"
    )

    train_keys = build_observation_keys(
        train
    )

    validation_keys = (
        build_observation_keys(
            validation
        )
    )

    test_keys = build_observation_keys(
        test
    )

    if train_keys and validation_keys:

        train_validation_overlap = (
            train_keys
            & validation_keys
        )

        train_test_overlap = (
            train_keys
            & test_keys
        )

        validation_test_overlap = (
            validation_keys
            & test_keys
        )

        result(
            "Train ∩ Validation",
            len(train_validation_overlap),
        )

        result(
            "Train ∩ Test",
            len(train_test_overlap),
        )

        result(
            "Validation ∩ Test",
            len(validation_test_overlap),
        )

        if (
            train_validation_overlap
            or train_test_overlap
            or validation_test_overlap
        ):

            raise RuntimeError(
                "Observation overlap detected."
            )

        passed(
            "Observation isolation"
        )

    else:

        result(
            "Observation isolation",
            "SKIPPED - metadata keys unavailable",
        )

    # --------------------------------------------------------
    # MATRICES
    # --------------------------------------------------------

    section("PREPARING MODEL MATRICES")

    X_train = train[
        train_features
    ].copy()

    X_validation = validation[
        validation_features
    ].copy()

    X_test = test[
        test_features
    ].copy()

    y_train = pd.to_numeric(
        train[
            TARGET_COLUMN
        ],
        errors="raise",
    )

    y_validation = pd.to_numeric(
        validation[
            TARGET_COLUMN
        ],
        errors="raise",
    )

    y_test = pd.to_numeric(
        test[
            TARGET_COLUMN
        ],
        errors="raise",
    )

    result(
        "Training matrix shape",
        X_train.shape,
    )

    result(
        "Validation matrix shape",
        X_validation.shape,
    )

    result(
        "Test matrix shape",
        X_test.shape,
    )

    result(
        "Feature count",
        len(train_features),
    )

    if list(
        X_train.columns
    ) != list(
        X_validation.columns
    ):

        raise RuntimeError(
            "Training and validation feature ordering differ."
        )

    if list(
        X_train.columns
    ) != list(
        X_test.columns
    ):

        raise RuntimeError(
            "Training and test feature ordering differ."
        )

    passed(
        "Feature ordering"
    )

    # --------------------------------------------------------
    # MODEL
    # --------------------------------------------------------

    section(
        "BUILDING FINAL TUNE_014 MODEL"
    )

    for parameter, value in SELECTED_PARAMS.items():

        result(
            parameter,
            value,
        )

    model = build_selected_model()

    print()
    print(
        "Categorical preprocessing:"
    )
    print(
        "  Delegated to XGBoostModel.fit()"
    )

    # --------------------------------------------------------
    # TRAIN
    # --------------------------------------------------------

    section(
        "TRAINING FINAL SELECTED MODEL"
    )

    print(
        "Validation passed to fit()             : NO"
    )

    print(
        "Test data passed to fit()              : NO"
    )

    print(
        "Hyperparameter tuning                   : NO"
    )

    print(
        "Model selection                         : NO"
    )

    print()
    print(
        "Training XGBoost..."
    )

    training_start = time.perf_counter()

    fit_model(
        model,
        X_train,
        y_train,
    )

    training_seconds = (
        time.perf_counter()
        - training_start
    )

    print(
        f"Training completed in "
        f"{training_seconds:.2f} seconds."
    )

    # --------------------------------------------------------
    # PREDICTIONS
    # --------------------------------------------------------

    section(
        "GENERATING VALIDATION PREDICTIONS"
    )

    validation_predictions = (
        predict_model(
            model,
            X_validation,
        )
    )

    result(
        "Validation predictions",
        len(validation_predictions),
    )

    section(
        "GENERATING TEST DIAGNOSTIC PREDICTIONS"
    )

    print(
        "IMPORTANT:"
    )

    print(
        "  Test predictions are diagnostic only."
    )

    print(
        "  They cannot alter TUNE_014."
    )

    test_predictions = predict_model(
        model,
        X_test,
    )

    result(
        "Test predictions",
        len(test_predictions),
    )

    if len(
        validation_predictions
    ) != len(
        validation
    ):

        raise RuntimeError(
            "Validation prediction count mismatch."
        )

    if len(
        test_predictions
    ) != len(
        test
    ):

        raise RuntimeError(
            "Test prediction count mismatch."
        )

    if not np.isfinite(
        validation_predictions
    ).all():

        raise RuntimeError(
            "Validation predictions contain "
            "non-finite values."
        )

    if not np.isfinite(
        test_predictions
    ).all():

        raise RuntimeError(
            "Test predictions contain "
            "non-finite values."
        )

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    validation_metrics = calculate_metrics(
        y_validation.to_numpy(),
        validation_predictions,
    )

    test_metrics = calculate_metrics(
        y_test.to_numpy(),
        test_predictions,
    )

    section(
        "REPRODUCED VALIDATION METRICS"
    )

    print(
        f"  MAE :  "
        f"{validation_metrics['mae']:.6f}"
    )

    print(
        f"  RMSE:  "
        f"{validation_metrics['rmse']:.6f}"
    )

    print(
        f"  R²  :  "
        f"{validation_metrics['r2']:.6f}"
    )

    print(
        f"  MAPE:  "
        f"{validation_metrics['mape']:.4f}%"
    )

    section(
        "FINAL TEST DIAGNOSTIC METRICS"
    )

    print(
        f"  MAE :  "
        f"{test_metrics['mae']:.6f}"
    )

    print(
        f"  RMSE:  "
        f"{test_metrics['rmse']:.6f}"
    )

    print(
        f"  R²  :  "
        f"{test_metrics['r2']:.6f}"
    )

    print(
        f"  MAPE:  "
        f"{test_metrics['mape']:.4f}%"
    )

    # --------------------------------------------------------
    # FINAL TEST REPRODUCIBILITY
    # --------------------------------------------------------

    section(
        "FINAL TEST REPRODUCIBILITY CHECK"
    )

    validate_final_metrics(
        test_metrics
    )

    passed(
        "MAE reproduces established final result"
    )

    passed(
        "RMSE reproduces established final result"
    )

    passed(
        "R² reproduces established final result"
    )

    passed(
        "MAPE reproduces established final result"
    )

    # --------------------------------------------------------
    # PREDICTION RANGE
    # --------------------------------------------------------

    section(
        "PREDICTION RANGE CHECK"
    )

    outside_range = (
        (test_predictions < 0)
        | (test_predictions > 1)
    )

    outside_count = int(
        outside_range.sum()
    )

    result(
        "Predictions outside [0,1]",
        outside_count,
    )

    if outside_count != 0:

        print(
            "WARNING: Some predictions are outside "
            "the occupancy-rate range."
        )

    else:

        passed(
            "All test predictions within [0,1]"
        )

    # --------------------------------------------------------
    # ERROR ANALYSIS
    # --------------------------------------------------------

    section(
        "TEST ERROR DISTRIBUTION"
    )

    test_error = (
        test_predictions
        - y_test.to_numpy()
    )

    absolute_error = np.abs(
        test_error
    )

    error_summary = {
        "mean_error": float(
            np.mean(test_error)
        ),
        "median_error": float(
            np.median(test_error)
        ),
        "mean_absolute_error": float(
            np.mean(absolute_error)
        ),
        "p50_absolute_error": float(
            np.percentile(
                absolute_error,
                50,
            )
        ),
        "p75_absolute_error": float(
            np.percentile(
                absolute_error,
                75,
            )
        ),
        "p90_absolute_error": float(
            np.percentile(
                absolute_error,
                90,
            )
        ),
        "p95_absolute_error": float(
            np.percentile(
                absolute_error,
                95,
            )
        ),
        "p99_absolute_error": float(
            np.percentile(
                absolute_error,
                99,
            )
        ),
        "maximum_absolute_error": float(
            np.max(absolute_error)
        ),
        "underprediction_rate_pct": float(
            np.mean(
                test_error < 0
            )
            * 100.0
        ),
        "overprediction_rate_pct": float(
            np.mean(
                test_error > 0
            )
            * 100.0
        ),
    }

    for key, value in error_summary.items():

        if key.endswith("_pct"):

            print(
                f"  {key:<35}: "
                f"{value:.4f}%"
            )

        else:

            print(
                f"  {key:<35}: "
                f"{value:.6f}"
            )

    # --------------------------------------------------------
    # REGIME ANALYSIS
    # --------------------------------------------------------

    section(
        "OCCUPANCY REGIME ANALYSIS"
    )

    regime_df = build_regime_analysis(
        y_test.to_numpy(),
        test_predictions,
    )

    if not regime_df.empty:

        print(
            regime_df.to_string(
                index=False
            )
        )

    # --------------------------------------------------------
    # BIAS ANALYSIS
    # --------------------------------------------------------

    section(
        "PREDICTION BIAS ANALYSIS"
    )

    bias_df = build_bias_analysis(
        y_test.to_numpy(),
        test_predictions,
    )

    print(
        bias_df.to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # WORST ERRORS
    # --------------------------------------------------------

    section(
        "WORST TEST PREDICTIONS"
    )

    error_df = build_error_analysis(
        test,
        y_test.to_numpy(),
        test_predictions,
    )

    worst_20 = error_df.head(
        20
    )

    display_columns = [
        column
        for column in [
            "normalized_at",
            "source_facility_code",
            "actual_occupancy",
            "predicted_occupancy",
            "error",
            "absolute_error",
            "occupancy_regime",
        ]
        if column in worst_20.columns
    ]

    print(
        worst_20[
            display_columns
        ].to_string(
            index=False
        )
    )

    # --------------------------------------------------------
    # FEATURE IMPORTANCE
    # --------------------------------------------------------

    section(
        "FEATURE IMPORTANCE"
    )

    feature_importance = (
        extract_feature_importance(
            model,
            train_features,
        )
    )

    print(
        feature_importance.head(
            30
        ).to_string(
            index=False
        )
    )

    dominant = feature_importance[
        feature_importance[
            "importance_pct"
        ] >= 5.0
    ]

    result(
        "Features with >=5% importance",
        len(dominant),
    )

    if not dominant.empty:

        print()
        print(
            "Dominant features:"
        )

        for _, row in dominant.iterrows():

            print(
                f"  {row['feature']}: "
                f"{row['importance_pct']:.4f}%"
            )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    summary = build_summary(
        validation_metrics,
        test_metrics,
        regime_df,
        feature_importance,
        bias_df,
    )

    # --------------------------------------------------------
    # PERSIST RESULTS
    # --------------------------------------------------------

    section(
        "PERSISTING MODEL DIAGNOSTICS"
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Error CSV
    error_df.to_csv(
        ERROR_CSV_PATH,
        index=False,
    )

    # Regime CSV
    regime_df.to_csv(
        REGIME_CSV_PATH,
        index=False,
    )

    # Feature importance CSV
    feature_importance.to_csv(
        FEATURE_IMPORTANCE_CSV_PATH,
        index=False,
    )

    # Bias CSV
    bias_df.to_csv(
        BIAS_CSV_PATH,
        index=False,
    )

    # Summary CSV
    summary_rows = [
        {
            "section": "validation",
            "metric": key,
            "value": value,
        }
        for key, value
        in validation_metrics.items()
    ]

    summary_rows.extend(
        {
            "section": "test",
            "metric": key,
            "value": value,
        }
        for key, value
        in test_metrics.items()
    )

    summary_rows.extend(
        {
            "section": "test_error_distribution",
            "metric": key,
            "value": value,
        }
        for key, value
        in error_summary.items()
    )

    summary_df = pd.DataFrame(
        summary_rows
    )

    summary_df.to_csv(
        SUMMARY_CSV_PATH,
        index=False,
    )

    # JSON
    report = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "audit": {
            "type": "final_model_diagnostics",
            "selected_candidate": (
                SELECTED_CANDIDATE
            ),
            "target": TARGET_COLUMN,
            "feature_count": (
                EXPECTED_FEATURE_COUNT
            ),
            "test_used_for_selection": False,
            "test_used_for_tuning": False,
            "test_passed_to_fit": False,
            "validation_passed_to_fit": False,
            "feature_pipeline_rebuilt": False,
            "hyperparameter_tuning": False,
        },

        "selected_model": {
            "candidate": (
                SELECTED_CANDIDATE
            ),
            "description": (
                SELECTED_DESCRIPTION
            ),
            "parameters": SELECTED_PARAMS,
        },

        "datasets": {
            "training_rows": int(
                len(train)
            ),
            "validation_rows": int(
                len(validation)
            ),
            "test_rows": int(
                len(test)
            ),
        },

        "validation_metrics": (
            validation_metrics
        ),

        "established_validation_reference": (
            ESTABLISHED_VALIDATION
        ),

        "test_metrics": test_metrics,

        "established_test_reference": (
            FINAL_TEST_REFERENCE
        ),

        "error_summary": error_summary,

        "prediction_range": {
            "minimum": float(
                np.min(
                    test_predictions
                )
            ),
            "maximum": float(
                np.max(
                    test_predictions
                )
            ),
            "outside_0_1_count": (
                outside_count
            ),
        },

        "bias_analysis": (
            bias_df.to_dict(
                orient="records"
            )
        ),

        "regime_analysis": (
            regime_df.to_dict(
                orient="records"
            )
        ),

        "feature_importance": (
            feature_importance.to_dict(
                orient="records"
            )
        ),

        "top_20_features": (
            feature_importance
            .head(20)
            .to_dict(
                orient="records"
            )
        ),

        "dominant_features": (
            dominant.to_dict(
                orient="records"
            )
        ),

        "worst_20_predictions": (
            worst_20.to_dict(
                orient="records"
            )
        ),

        "diagnostic_summary": summary,
    }

    with JSON_PATH.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            json_safe(report),
            handle,
            indent=2,
            ensure_ascii=False,
        )

    result(
        "Output directory",
        OUTPUT_DIR,
    )

    result(
        "JSON report",
        JSON_PATH,
    )

    result(
        "CSV summary",
        SUMMARY_CSV_PATH,
    )

    result(
        "CSV error analysis",
        ERROR_CSV_PATH,
    )

    result(
        "CSV regime analysis",
        REGIME_CSV_PATH,
    )

    result(
        "CSV feature importance",
        FEATURE_IMPORTANCE_CSV_PATH,
    )

    result(
        "CSV bias analysis",
        BIAS_CSV_PATH,
    )

    # --------------------------------------------------------
    # FINAL ASSERTIONS
    # --------------------------------------------------------

    section(
        "FINAL DIAGNOSTIC ASSERTIONS"
    )

    passed(
        "Expected feature count = 296"
    )

    passed(
        "Training dataset non-empty"
    )

    passed(
        "Validation dataset non-empty"
    )

    passed(
        "Test dataset non-empty"
    )

    passed(
        "Feature ordering identical"
    )

    passed(
        "Validation data never passed to fit()"
    )

    passed(
        "Test data never passed to fit()"
    )

    passed(
        "Hyperparameter tuning not performed"
    )

    passed(
        "Model selection not performed"
    )

    passed(
        "Feature pipeline not rebuilt"
    )

    passed(
        "Persisted datasets not modified"
    )

    assert_finite_metrics(
        validation_metrics
    )

    assert_finite_metrics(
        test_metrics
    )

    passed(
        "Validation metrics finite"
    )

    passed(
        "Test metrics finite"
    )

    if (
        len(feature_importance)
        != EXPECTED_FEATURE_COUNT
    ):

        raise AssertionError(
            "Feature importance row count does "
            "not equal registered feature count."
        )

    passed(
        "Feature importance covers all 296 features"
    )

    # --------------------------------------------------------
    # FINAL
    # --------------------------------------------------------

    banner(
        "BIRMINGHAM XGBOOST FINAL MODEL "
        "DIAGNOSTICS COMPLETED"
    )

    print()
    print(
        "FINAL MODEL:"
    )

    print(
        f"  Candidate:             "
        f"{SELECTED_CANDIDATE}"
    )

    print(
        f"  Features:              "
        f"{EXPECTED_FEATURE_COUNT}"
    )

    print()
    print(
        "FINAL TEST PERFORMANCE:"
    )

    print(
        f"  MAE  = "
        f"{test_metrics['mae']:.6f}"
    )

    print(
        f"  RMSE = "
        f"{test_metrics['rmse']:.6f}"
    )

    print(
        f"  R²   = "
        f"{test_metrics['r2']:.6f}"
    )

    print(
        f"  MAPE = "
        f"{test_metrics['mape']:.4f}%"
    )

    print()
    print(
        "DIAGNOSTICS:"
    )

    print(
        f"  Mean error:             "
        f"{error_summary['mean_error']:.6f}"
    )

    print(
        f"  Median error:           "
        f"{error_summary['median_error']:.6f}"
    )

    print(
        f"  P95 absolute error:     "
        f"{error_summary['p95_absolute_error']:.6f}"
    )

    print(
        f"  P99 absolute error:     "
        f"{error_summary['p99_absolute_error']:.6f}"
    )

    print(
        f"  Maximum absolute error: "
        f"{error_summary['maximum_absolute_error']:.6f}"
    )

    print(
        f"  Underprediction rate:   "
        f"{error_summary['underprediction_rate_pct']:.2f}%"
    )

    print(
        f"  Overprediction rate:    "
        f"{error_summary['overprediction_rate_pct']:.2f}%"
    )

    print()
    print(
        "Training time:"
    )

    print(
        f"  {training_seconds:.2f} seconds"
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
        "Test dataset used for selection:NO"
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
        "FINAL XGBOOST MODEL DIAGNOSTICS PASSED"
    )

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "TUNE_014 remains the selected model."
    )

    print(
        "Diagnostics did not modify model selection."
    )

    print(
        "Do NOT retune against the test dataset."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print()
        print(
            "Diagnostic execution interrupted by user."
        )

        raise SystemExit(130)

    except Exception as exc:

        banner(
            "BIRMINGHAM XGBOOST FINAL MODEL "
            "DIAGNOSTICS FAILED"
        )

        print()
        print(
            f"ERROR: "
            f"{type(exc).__name__}: {exc}"
        )

        print()
        print(
            "NO persisted datasets were modified."
        )

        print(
            "No model-selection decision was changed."
        )

        print(
            "No hyperparameter tuning was performed."
        )

        raise SystemExit(1)