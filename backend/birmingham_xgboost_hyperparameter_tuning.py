"""
SMARTPARK AI
Birmingham XGBoost Hyperparameter Tuning

Purpose
-------
Controlled hyperparameter tuning for the Birmingham
30-minute occupancy forecasting model.

Target:
    target_occupancy_rate_30m

Experimental contract
---------------------
TRAIN:
    train.parquet

VALIDATION:
    validation.parquet

TEST:
    test.parquet exists but is NEVER loaded.

Important:
    - No feature pipeline rebuild.
    - No test-set inspection.
    - No validation data passed to XGBoost.fit().
    - No early stopping.
    - Same feature registry as the established baseline.
    - Same categorical handling through XGBoostModel.
    - random_state remains 42.
    - Every candidate is trained independently.
    - Results are persisted for reproducibility.

Baseline
--------
MAE  = 0.013767
RMSE = 0.020167
R2   = 0.994799
MAPE = 3.4157%

The tuning objective is validation MAE.

The baseline is included as an explicit comparison row.
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
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

# ---------------------------------------------------------------------
# Repository / application imports
# ---------------------------------------------------------------------

from app.ml.ml_models.xgboost_model import (
    XGBoostModel,
    XGBoostModelConfig,
)


# =====================================================================
# CONSTANTS
# =====================================================================

TARGET_COLUMN = "target_occupancy_rate_30m"

RANDOM_STATE = 42

EXPECTED_FEATURE_COUNT = 296

EXPECTED_TRAIN_ROWS = 23_244
EXPECTED_VALIDATION_ROWS = 4_980

BASELINE_MAE = 0.013767
BASELINE_RMSE = 0.020167
BASELINE_R2 = 0.994799
BASELINE_MAPE = 3.4157

CATEGORICAL_FEATURES = (
    "occupancy_level",
    "demand_class",
)


# =====================================================================
# PATHS
# =====================================================================

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
    / TARGET_COLUMN
)

TRAIN_FILE = (
    TARGET_DATASET_ROOT
    / "train.parquet"
)

VALIDATION_FILE = (
    TARGET_DATASET_ROOT
    / "validation.parquet"
)

TEST_FILE = (
    TARGET_DATASET_ROOT
    / "test.parquet"
)

MANIFEST_FILE = (
    DATASET_ROOT
    / "training_dataset_manifest.json"
)

OUTPUT_DIR = (
    DATASET_ROOT
    / "xgboost_hyperparameter_tuning"
)

RESULTS_JSON = (
    OUTPUT_DIR
    / "birmingham_xgboost_hyperparameter_tuning.json"
)

RESULTS_CSV = (
    OUTPUT_DIR
    / "birmingham_xgboost_hyperparameter_tuning.csv"
)

SUMMARY_CSV = (
    OUTPUT_DIR
    / "birmingham_xgboost_hyperparameter_tuning_summary.csv"
)


# =====================================================================
# DATA STRUCTURES
# =====================================================================

@dataclass(frozen=True)
class TuningCandidate:
    """
    One deterministic XGBoost hyperparameter configuration.
    """

    candidate_id: str

    description: str

    n_estimators: int

    learning_rate: float

    max_depth: int

    min_child_weight: float

    subsample: float

    colsample_bytree: float

    gamma: float

    reg_alpha: float

    reg_lambda: float


@dataclass
class TuningResult:
    """
    Persisted result for one tuning candidate.
    """

    candidate_id: str

    description: str

    status: str

    feature_count: int

    training_rows: int

    validation_rows: int

    validation_data_passed_to_fit: bool

    test_data_loaded: bool

    test_data_passed_to_fit: bool

    n_estimators: int

    learning_rate: float

    max_depth: int

    min_child_weight: float

    subsample: float

    colsample_bytree: float

    gamma: float

    reg_alpha: float

    reg_lambda: float

    mae: float | None = None

    rmse: float | None = None

    r2: float | None = None

    mape: float | None = None

    improvement_vs_baseline_mae: float | None = None

    improvement_vs_baseline_mae_pct: float | None = None

    improvement_vs_baseline_rmse: float | None = None

    improvement_vs_baseline_r2: float | None = None

    training_seconds: float | None = None

    prediction_seconds: float | None = None

    error: str | None = None


# =====================================================================
# OUTPUT HELPERS
# =====================================================================

def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def print_metric(
    label: str,
    value: Any,
) -> None:
    print(
        f"{label:<42}: {value}"
    )


# =====================================================================
# VALIDATION HELPERS
# =====================================================================

def require_file(
    path: Path,
    description: str,
) -> None:

    exists = path.exists()

    print_metric(
        f"{description} exists",
        "PASS" if exists else "FAIL",
    )

    if not exists:
        raise FileNotFoundError(
            f"Required file does not exist: {path}"
        )


def validate_dataset_files() -> None:

    print_section(
        "DATASET FILE VALIDATION"
    )

    print_metric(
        "Processed dataset root",
        str(DATASET_ROOT),
    )

    print_metric(
        "Training dataset",
        str(TRAIN_FILE),
    )

    print_metric(
        "Validation dataset",
        str(VALIDATION_FILE),
    )

    print_metric(
        "Test dataset",
        str(TEST_FILE),
    )

    print_metric(
        "Feature manifest",
        str(MANIFEST_FILE),
    )

    require_file(
        TRAIN_FILE,
        "Training file",
    )

    require_file(
        VALIDATION_FILE,
        "Validation file",
    )

    # We intentionally check existence only.
    #
    # The test dataset MUST NOT be loaded.
    require_file(
        TEST_FILE,
        "Test file",
    )

    require_file(
        MANIFEST_FILE,
        "Feature manifest",
    )

    print()
    print(
        "IMPORTANT: test.parquet exists but will NOT be loaded."
    )


# =====================================================================
# MANIFEST
# =====================================================================

def load_feature_manifest() -> dict[str, Any]:

    print_section(
        "LOADING FEATURE MANIFEST"
    )

    with MANIFEST_FILE.open(
        "r",
        encoding="utf-8",
    ) as handle:

        manifest = json.load(handle)

    feature_columns = manifest.get(
        "feature_columns",
        [],
    )

    print_metric(
        "Manifest",
        str(MANIFEST_FILE),
    )

    print_metric(
        "Registered features",
        len(feature_columns),
    )

    if len(feature_columns) != EXPECTED_FEATURE_COUNT:
        raise ValueError(
            "Unexpected feature count in manifest: "
            f"{len(feature_columns)}; "
            f"expected {EXPECTED_FEATURE_COUNT}."
        )

    if len(feature_columns) != len(
        set(feature_columns)
    ):
        raise ValueError(
            "Manifest contains duplicate feature names."
        )

    if TARGET_COLUMN in feature_columns:
        raise ValueError(
            f"Target column '{TARGET_COLUMN}' "
            "must not be a registered model feature."
        )

    return manifest


# =====================================================================
# DATASET LOADING
# =====================================================================

def load_datasets() -> tuple[
    pd.DataFrame,
    pd.DataFrame,
]:

    print_section(
        "LOADING TRAINING DATASET"
    )

    train = pd.read_parquet(
        TRAIN_FILE
    )

    print_metric(
        "Training rows",
        len(train),
    )

    print_metric(
        "Training columns",
        len(train.columns),
    )

    print_section(
        "LOADING VALIDATION DATASET"
    )

    validation = pd.read_parquet(
        VALIDATION_FILE
    )

    print_metric(
        "Validation rows",
        len(validation),
    )

    print_metric(
        "Validation columns",
        len(validation.columns),
    )

    # --------------------------------------------------------------
    # Dataset size contract.
    # --------------------------------------------------------------

    if len(train) != EXPECTED_TRAIN_ROWS:
        raise ValueError(
            "Unexpected training row count: "
            f"{len(train)}; "
            f"expected {EXPECTED_TRAIN_ROWS}."
        )

    if len(validation) != EXPECTED_VALIDATION_ROWS:
        raise ValueError(
            "Unexpected validation row count: "
            f"{len(validation)}; "
            f"expected {EXPECTED_VALIDATION_ROWS}."
        )

    return train, validation


# =====================================================================
# FEATURE CONTRACT
# =====================================================================

def get_model_features(
    dataframe: pd.DataFrame,
    manifest: dict[str, Any],
) -> list[str]:

    registered = [
        str(column)
        for column in manifest.get(
            "feature_columns",
            [],
        )
    ]

    available = set(
        dataframe.columns
    )

    missing = [
        column
        for column in registered
        if column not in available
    ]

    if missing:
        raise ValueError(
            "Dataset is missing registered model "
            f"features: {missing}"
        )

    return registered


def validate_feature_contract(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    manifest: dict[str, Any],
) -> list[str]:

    print_section(
        "FEATURE CONTRACT VALIDATION"
    )

    train_features = get_model_features(
        train,
        manifest,
    )

    validation_features = get_model_features(
        validation,
        manifest,
    )

    print_metric(
        "Registered features",
        len(train_features),
    )

    print_metric(
        "Training feature registry",
        "PASS",
    )

    print_metric(
        "Validation feature registry",
        "PASS",
    )

    if train_features != validation_features:
        raise ValueError(
            "Training and validation feature registries "
            "are not identical."
        )

    print_metric(
        "Train/validation feature registry",
        "IDENTICAL",
    )

    if len(train_features) != EXPECTED_FEATURE_COUNT:
        raise ValueError(
            "Unexpected model feature count: "
            f"{len(train_features)}."
        )

    duplicate_features = (
        len(train_features)
        != len(set(train_features))
    )

    print_metric(
        "Duplicate feature names",
        1 if duplicate_features else 0,
    )

    if duplicate_features:
        raise ValueError(
            "Duplicate model feature names detected."
        )

    categorical_missing = [
        column
        for column in CATEGORICAL_FEATURES
        if column not in train_features
    ]

    if categorical_missing:
        raise ValueError(
            "Configured categorical features are missing "
            f"from feature registry: {categorical_missing}"
        )

    print_metric(
        "Categorical features delegated to model",
        ", ".join(CATEGORICAL_FEATURES),
    )

    return train_features


# =====================================================================
# TARGET CONTRACT
# =====================================================================

def validate_target_contract(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    print_section(
        "TARGET CONTRACT VALIDATION"
    )

    if TARGET_COLUMN not in train.columns:
        raise ValueError(
            f"Training dataset does not contain "
            f"target '{TARGET_COLUMN}'."
        )

    if TARGET_COLUMN not in validation.columns:
        raise ValueError(
            f"Validation dataset does not contain "
            f"target '{TARGET_COLUMN}'."
        )

    y_train = pd.to_numeric(
        train[TARGET_COLUMN],
        errors="coerce",
    )

    y_validation = pd.to_numeric(
        validation[TARGET_COLUMN],
        errors="coerce",
    )

    if y_train.isna().any():
        raise ValueError(
            "Training target contains null/non-numeric values."
        )

    if y_validation.isna().any():
        raise ValueError(
            "Validation target contains null/non-numeric values."
        )

    print_metric(
        "Training target rows",
        len(y_train),
    )

    print_metric(
        "Validation target rows",
        len(y_validation),
    )

    print_metric(
        "Training target mean",
        f"{y_train.mean():.6f}",
    )

    print_metric(
        "Validation target mean",
        f"{y_validation.mean():.6f}",
    )

    print_metric(
        "Training target range",
        f"{y_train.min():.6f} -> {y_train.max():.6f}",
    )

    print_metric(
        "Validation target range",
        f"{y_validation.min():.6f} -> {y_validation.max():.6f}",
    )

    if not (
        ((y_train >= 0.0) & (y_train <= 1.0)).all()
    ):
        raise ValueError(
            "Training target contains values outside [0, 1]."
        )

    if not (
        ((y_validation >= 0.0) & (y_validation <= 1.0)).all()
    ):
        raise ValueError(
            "Validation target contains values outside [0, 1]."
        )

    print_metric(
        "Target range validation",
        "PASS",
    )


# =====================================================================
# CHRONOLOGICAL CONTRACT
# =====================================================================

def find_timestamp_column(
    dataframe: pd.DataFrame,
) -> str | None:

    candidates = (
        "normalized_at",
        "timestamp",
        "observation_timestamp",
        "datetime",
        "date_time",
    )

    for candidate in candidates:

        if candidate in dataframe.columns:
            return candidate

    return None


def validate_chronological_split(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    print_section(
        "CHRONOLOGICAL SPLIT VALIDATION"
    )

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

        print_metric(
            "Timestamp validation",
            "SKIPPED - timestamp column unavailable",
        )

        return

    train_timestamp = pd.to_datetime(
        train[
            train_timestamp_column
        ],
        errors="coerce",
    )

    validation_timestamp = pd.to_datetime(
        validation[
            validation_timestamp_column
        ],
        errors="coerce",
    )

    if train_timestamp.isna().any():
        raise ValueError(
            "Training timestamps contain invalid values."
        )

    if validation_timestamp.isna().any():
        raise ValueError(
            "Validation timestamps contain invalid values."
        )

    train_start = train_timestamp.min()
    train_end = train_timestamp.max()

    validation_start = validation_timestamp.min()
    validation_end = validation_timestamp.max()

    print_metric(
        "Training start",
        train_start,
    )

    print_metric(
        "Training end",
        train_end,
    )

    print_metric(
        "Validation start",
        validation_start,
    )

    print_metric(
        "Validation end",
        validation_end,
    )

    if validation_start < train_end:
        raise ValueError(
            "Validation period begins before the end "
            "of the training period."
        )

    print_metric(
        "Chronological ordering",
        "PASS",
    )


# =====================================================================
# OBSERVATION ISOLATION
# =====================================================================

def validate_observation_isolation(
    train: pd.DataFrame,
    validation: pd.DataFrame,
) -> None:

    print_section(
        "TRAIN / VALIDATION OBSERVATION ISOLATION"
    )

    train_timestamp_column = (
        find_timestamp_column(train)
    )

    validation_timestamp_column = (
        find_timestamp_column(validation)
    )

    train_facility_column = (
        "source_facility_code"
        if "source_facility_code" in train.columns
        else None
    )

    validation_facility_column = (
        "source_facility_code"
        if "source_facility_code" in validation.columns
        else None
    )

    if not all(
        (
            train_timestamp_column,
            validation_timestamp_column,
            train_facility_column,
            validation_facility_column,
        )
    ):

        print_metric(
            "Observation isolation",
            "SKIPPED - facility/timestamp columns unavailable",
        )

        return

    train_keys = set(
        zip(
            train[
                train_facility_column
            ].astype(str),
            pd.to_datetime(
                train[
                    train_timestamp_column
                ]
            ).astype(str),
        )
    )

    validation_keys = set(
        zip(
            validation[
                validation_facility_column
            ].astype(str),
            pd.to_datetime(
                validation[
                    validation_timestamp_column
                ]
            ).astype(str),
        )
    )

    overlap = (
        train_keys
        & validation_keys
    )

    print_metric(
        "Training observations",
        len(train),
    )

    print_metric(
        "Validation observations",
        len(validation),
    )

    print_metric(
        "Train ∩ Validation",
        len(overlap),
    )

    if overlap:
        raise ValueError(
            "Training and validation contain overlapping "
            "facility/timestamp observations."
        )

    print_metric(
        "Observation isolation",
        "PASS",
    )


# =====================================================================
# FEATURE MATRIX
# =====================================================================

def build_model_matrices(
    train: pd.DataFrame,
    validation: pd.DataFrame,
    feature_columns: list[str],
) -> tuple[
    pd.DataFrame,
    pd.Series,
    pd.DataFrame,
    pd.Series,
]:

    print_section(
        "PREPARING MODEL MATRICES"
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

    print_metric(
        "Registered features",
        len(feature_columns),
    )

    numeric_features = [
        column
        for column in feature_columns
        if column not in CATEGORICAL_FEATURES
    ]

    print_metric(
        "Numeric features",
        len(numeric_features),
    )

    print_metric(
        "Categorical features",
        len(CATEGORICAL_FEATURES),
    )

    print_metric(
        "X_train shape",
        X_train.shape,
    )

    print_metric(
        "y_train shape",
        y_train.shape,
    )

    print_metric(
        "X_validation shape",
        X_validation.shape,
    )

    print_metric(
        "y_validation shape",
        y_validation.shape,
    )

    print_metric(
        "Feature/target separation",
        "PASS",
    )

    return (
        X_train,
        y_train,
        X_validation,
        y_validation,
    )


# =====================================================================
# CANDIDATE GRID
# =====================================================================

def build_candidates() -> list[TuningCandidate]:

    """
    Controlled, deliberately small tuning grid.

    The baseline is represented separately and is NOT retrained
    here. It is included in the persisted comparison.

    The grid is designed to investigate:

        1. Tree complexity
        2. Learning rate / number of estimators
        3. Sampling
        4. Regularisation

    The total number of candidates is intentionally limited.
    """

    candidates: list[TuningCandidate] = []

    candidate_number = 1

    def add(
        description: str,
        *,
        n_estimators: int,
        learning_rate: float,
        max_depth: int,
        min_child_weight: float,
        subsample: float,
        colsample_bytree: float,
        gamma: float,
        reg_alpha: float,
        reg_lambda: float,
    ) -> None:

        nonlocal candidate_number

        candidates.append(
            TuningCandidate(
                candidate_id=(
                    f"TUNE_{candidate_number:03d}"
                ),
                description=description,
                n_estimators=n_estimators,
                learning_rate=learning_rate,
                max_depth=max_depth,
                min_child_weight=min_child_weight,
                subsample=subsample,
                colsample_bytree=colsample_bytree,
                gamma=gamma,
                reg_alpha=reg_alpha,
                reg_lambda=reg_lambda,
            )
        )

        candidate_number += 1

    # --------------------------------------------------------------
    # Baseline-neighbourhood tree complexity.
    # --------------------------------------------------------------

    add(
        "Shallower trees",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=4,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    add(
        "Baseline-depth trees",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    add(
        "Deeper trees",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=8,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    add(
        "Higher minimum child weight",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=5.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    add(
        "Strong minimum child weight",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=10.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    # --------------------------------------------------------------
    # Learning-rate / estimator combinations.
    # --------------------------------------------------------------

    add(
        "Lower learning rate",
        n_estimators=500,
        learning_rate=0.03,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    add(
        "Higher learning rate",
        n_estimators=200,
        learning_rate=0.08,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    add(
        "Moderate learning rate",
        n_estimators=250,
        learning_rate=0.06,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    # --------------------------------------------------------------
    # Sampling.
    # --------------------------------------------------------------

    add(
        "Lower row subsampling",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.75,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    add(
        "Higher row subsampling",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=1.0,
        subsample=1.0,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    add(
        "Lower column subsampling",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.75,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    add(
        "Full column sampling",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=1.0,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    # --------------------------------------------------------------
    # Regularisation.
    # --------------------------------------------------------------

    add(
        "Higher gamma",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.1,
        reg_alpha=0.0,
        reg_lambda=1.0,
    )

    add(
        "Higher L1 regularisation",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.1,
        reg_lambda=1.0,
    )

    add(
        "Higher L2 regularisation",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=5.0,
    )

    # --------------------------------------------------------------
    # Balanced regularised candidate.
    # --------------------------------------------------------------

    add(
        "Balanced regularised model",
        n_estimators=350,
        learning_rate=0.04,
        max_depth=6,
        min_child_weight=3.0,
        subsample=0.85,
        colsample_bytree=0.85,
        gamma=0.05,
        reg_alpha=0.05,
        reg_lambda=2.0,
    )

    return candidates


# =====================================================================
# XGBOOST MODEL CONFIGURATION
# =====================================================================

def build_model(
    candidate: TuningCandidate,
) -> XGBoostModel:

    config = XGBoostModelConfig(
        n_estimators=(
            candidate.n_estimators
        ),
        learning_rate=(
            candidate.learning_rate
        ),
        max_depth=(
            candidate.max_depth
        ),
        min_child_weight=(
            candidate.min_child_weight
        ),
        subsample=(
            candidate.subsample
        ),
        colsample_bytree=(
            candidate.colsample_bytree
        ),
        gamma=(
            candidate.gamma
        ),
        reg_alpha=(
            candidate.reg_alpha
        ),
        reg_lambda=(
            candidate.reg_lambda
        ),
        random_state=RANDOM_STATE,
        n_jobs=-1,
        tree_method="hist",
        early_stopping_rounds=None,
        clip_predictions=True,
        categorical_features=(
            list(CATEGORICAL_FEATURES)
        ),
    )

    return XGBoostModel(
        target_column=TARGET_COLUMN,
        config=config,
        model_name=(
            f"xgboost_tuning_"
            f"{candidate.candidate_id.lower()}"
        ),
    )


# =====================================================================
# METRICS
# =====================================================================

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

    non_zero = (
        np.abs(y_true)
        > 1e-12
    )

    if not non_zero.any():
        return float("nan")

    return float(
        np.mean(
            np.abs(
                (
                    y_true[non_zero]
                    - y_pred[non_zero]
                )
                / y_true[non_zero]
            )
        )
        * 100.0
    )


def validate_predictions(
    predictions: np.ndarray,
) -> None:

    if predictions.size == 0:
        raise ValueError(
            "Model returned zero predictions."
        )

    if not np.isfinite(
        predictions
    ).all():
        raise ValueError(
            "Model produced non-finite predictions."
        )


# =====================================================================
# BASELINE RESULT
# =====================================================================

def baseline_result() -> TuningResult:

    return TuningResult(
        candidate_id="BASELINE",
        description=(
            "Established initial XGBoost benchmark"
        ),
        status="BASELINE_REFERENCE",
        feature_count=EXPECTED_FEATURE_COUNT,
        training_rows=EXPECTED_TRAIN_ROWS,
        validation_rows=EXPECTED_VALIDATION_ROWS,
        validation_data_passed_to_fit=False,
        test_data_loaded=False,
        test_data_passed_to_fit=False,
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.0,
        reg_lambda=1.0,
        mae=BASELINE_MAE,
        rmse=BASELINE_RMSE,
        r2=BASELINE_R2,
        mape=BASELINE_MAPE,
        improvement_vs_baseline_mae=0.0,
        improvement_vs_baseline_mae_pct=0.0,
        improvement_vs_baseline_rmse=0.0,
        improvement_vs_baseline_r2=0.0,
        training_seconds=0.0,
        prediction_seconds=0.0,
    )


# =====================================================================
# CANDIDATE EXECUTION
# =====================================================================

def run_candidate(
    candidate: TuningCandidate,
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_validation: pd.DataFrame,
    y_validation: pd.Series,
) -> TuningResult:

    print_header(
        f"CANDIDATE {candidate.candidate_id}"
    )

    print_metric(
        "Description",
        candidate.description,
    )

    print_metric(
        "n_estimators",
        candidate.n_estimators,
    )

    print_metric(
        "learning_rate",
        candidate.learning_rate,
    )

    print_metric(
        "max_depth",
        candidate.max_depth,
    )

    print_metric(
        "min_child_weight",
        candidate.min_child_weight,
    )

    print_metric(
        "subsample",
        candidate.subsample,
    )

    print_metric(
        "colsample_bytree",
        candidate.colsample_bytree,
    )

    print_metric(
        "gamma",
        candidate.gamma,
    )

    print_metric(
        "reg_alpha",
        candidate.reg_alpha,
    )

    print_metric(
        "reg_lambda",
        candidate.reg_lambda,
    )

    print_metric(
        "Validation passed to fit()",
        "NO",
    )

    print_metric(
        "Test data loaded",
        "NO",
    )

    model = build_model(
        candidate
    )

    result = TuningResult(
        candidate_id=candidate.candidate_id,
        description=candidate.description,
        status="RUNNING",
        feature_count=X_train.shape[1],
        training_rows=len(X_train),
        validation_rows=len(X_validation),
        validation_data_passed_to_fit=False,
        test_data_loaded=False,
        test_data_passed_to_fit=False,
        n_estimators=candidate.n_estimators,
        learning_rate=candidate.learning_rate,
        max_depth=candidate.max_depth,
        min_child_weight=candidate.min_child_weight,
        subsample=candidate.subsample,
        colsample_bytree=candidate.colsample_bytree,
        gamma=candidate.gamma,
        reg_alpha=candidate.reg_alpha,
        reg_lambda=candidate.reg_lambda,
    )

    # --------------------------------------------------------------
    # TRAIN
    # --------------------------------------------------------------

    print()
    print(
        "Training XGBoost..."
    )

    train_start = time.perf_counter()

    try:

        # IMPORTANT:
        #
        # Validation data is deliberately NOT passed to fit().
        #
        model.fit(
            X_train,
            y_train,
        )

    except Exception as exc:

        result.status = "FAILED"
        result.error = (
            f"{type(exc).__name__}: {exc}"
        )

        return result

    train_elapsed = (
        time.perf_counter()
        - train_start
    )

    result.training_seconds = (
        train_elapsed
    )

    print(
        f"Training completed in "
        f"{train_elapsed:.2f} seconds."
    )

    # --------------------------------------------------------------
    # PREDICT
    # --------------------------------------------------------------

    print()
    print(
        "Generating validation predictions..."
    )

    prediction_start = time.perf_counter()

    try:

        predictions = model.predict(
            X_validation
        )

    except Exception as exc:

        result.status = "FAILED"
        result.error = (
            f"{type(exc).__name__}: {exc}"
        )

        return result

    prediction_elapsed = (
        time.perf_counter()
        - prediction_start
    )

    result.prediction_seconds = (
        prediction_elapsed
    )

    predictions = np.asarray(
        predictions,
        dtype=float,
    )

    validate_predictions(
        predictions
    )

    # --------------------------------------------------------------
    # METRICS
    # --------------------------------------------------------------

    y_true = np.asarray(
        y_validation,
        dtype=float,
    )

    mae = float(
        mean_absolute_error(
            y_true,
            predictions,
        )
    )

    rmse = float(
        math.sqrt(
            mean_squared_error(
                y_true,
                predictions,
            )
        )
    )

    r2 = float(
        r2_score(
            y_true,
            predictions,
        )
    )

    mape = calculate_mape(
        y_true,
        predictions,
    )

    result.mae = mae
    result.rmse = rmse
    result.r2 = r2
    result.mape = mape

    # --------------------------------------------------------------
    # Baseline comparison.
    #
    # Lower MAE/RMSE is better.
    # Higher R² is better.
    # --------------------------------------------------------------

    result.improvement_vs_baseline_mae = (
        BASELINE_MAE - mae
    )

    result.improvement_vs_baseline_mae_pct = (
        (
            BASELINE_MAE - mae
        )
        / BASELINE_MAE
        * 100.0
    )

    result.improvement_vs_baseline_rmse = (
        BASELINE_RMSE - rmse
    )

    result.improvement_vs_baseline_r2 = (
        r2 - BASELINE_R2
    )

    result.status = "COMPLETED"

    print()
    print(
        "Validation metrics:"
    )

    print_metric(
        "MAE",
        f"{mae:.6f}",
    )

    print_metric(
        "RMSE",
        f"{rmse:.6f}",
    )

    print_metric(
        "R²",
        f"{r2:.6f}",
    )

    print_metric(
        "MAPE",
        f"{mape:.4f}%",
    )

    print()
    print(
        "Comparison with baseline:"
    )

    print_metric(
        "MAE improvement",
        f"{result.improvement_vs_baseline_mae:+.6f}",
    )

    print_metric(
        "MAE improvement %",
        f"{result.improvement_vs_baseline_mae_pct:+.2f}%",
    )

    print_metric(
        "RMSE improvement",
        f"{result.improvement_vs_baseline_rmse:+.6f}",
    )

    print_metric(
        "R² improvement",
        f"{result.improvement_vs_baseline_r2:+.6f}",
    )

    return result


# =====================================================================
# RESULT VALIDATION
# =====================================================================

def validate_result(
    result: TuningResult,
) -> None:

    if result.status != "COMPLETED":
        return

    metrics = (
        result.mae,
        result.rmse,
        result.r2,
        result.mape,
    )

    if any(
        value is None
        for value in metrics
    ):
        raise ValueError(
            f"Candidate {result.candidate_id} "
            "completed without all metrics."
        )

    if not all(
        np.isfinite(
            float(value)
        )
        for value in metrics
        if value is not None
    ):
        raise ValueError(
            f"Candidate {result.candidate_id} "
            "contains non-finite metrics."
        )

    if result.validation_data_passed_to_fit:
        raise ValueError(
            f"Candidate {result.candidate_id} "
            "violated validation isolation."
        )

    if result.test_data_loaded:
        raise ValueError(
            f"Candidate {result.candidate_id} "
            "loaded test data."
        )

    if result.test_data_passed_to_fit:
        raise ValueError(
            f"Candidate {result.candidate_id} "
            "passed test data to fit()."
        )


# =====================================================================
# RANKING
# =====================================================================

def rank_results(
    results: list[TuningResult],
) -> list[TuningResult]:

    completed = [
        result
        for result in results
        if result.status == "COMPLETED"
    ]

    return sorted(
        completed,
        key=lambda result: (
            float(
                result.mae
            ),
            float(
                result.rmse
            ),
            -float(
                result.r2
            ),
        ),
    )


# =====================================================================
# PERSISTENCE
# =====================================================================

def persist_results(
    results: list[TuningResult],
) -> None:

    print_section(
        "PERSISTING TUNING RESULTS"
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    generated_at = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    ranked = rank_results(
        results
    )

    best = (
        ranked[0]
        if ranked
        else None
    )

    payload = {
        "experiment": (
            "Birmingham XGBoost "
            "hyperparameter tuning"
        ),
        "generated_at": generated_at,
        "target": TARGET_COLUMN,
        "train_file": str(TRAIN_FILE),
        "validation_file": str(VALIDATION_FILE),
        "test_file": str(TEST_FILE),
        "test_data_loaded": False,
        "validation_data_passed_to_fit": False,
        "early_stopping_used": False,
        "feature_count": EXPECTED_FEATURE_COUNT,
        "training_rows": EXPECTED_TRAIN_ROWS,
        "validation_rows": EXPECTED_VALIDATION_ROWS,
        "random_state": RANDOM_STATE,
        "objective": "reg:squarederror",
        "selection_metric": "validation_mae",
        "baseline": asdict(
            baseline_result()
        ),
        "candidate_count": len(
            [
                result
                for result in results
                if result.candidate_id != "BASELINE"
            ]
        ),
        "completed_candidate_count": len(
            ranked
        ),
        "failed_candidate_count": len(
            [
                result
                for result in results
                if result.status == "FAILED"
            ]
        ),
        "best_candidate": (
            asdict(best)
            if best is not None
            else None
        ),
        "results": [
            asdict(result)
            for result in results
        ],
    }

    with RESULTS_JSON.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            payload,
            handle,
            indent=2,
        )

    dataframe = pd.DataFrame(
        [
            asdict(result)
            for result in results
        ]
    )

    dataframe.to_csv(
        RESULTS_CSV,
        index=False,
    )

    summary_rows: list[dict[str, Any]] = []

    for rank, result in enumerate(
        ranked,
        start=1,
    ):

        summary_rows.append(
            {
                "rank": rank,
                "candidate_id": (
                    result.candidate_id
                ),
                "description": (
                    result.description
                ),
                "mae": result.mae,
                "rmse": result.rmse,
                "r2": result.r2,
                "mape": result.mape,
                "mae_improvement_vs_baseline": (
                    result.improvement_vs_baseline_mae
                ),
                "mae_improvement_vs_baseline_pct": (
                    result.improvement_vs_baseline_mae_pct
                ),
                "rmse_improvement_vs_baseline": (
                    result.improvement_vs_baseline_rmse
                ),
                "r2_improvement_vs_baseline": (
                    result.improvement_vs_baseline_r2
                ),
                "training_seconds": (
                    result.training_seconds
                ),
                "max_depth": result.max_depth,
                "min_child_weight": (
                    result.min_child_weight
                ),
                "learning_rate": (
                    result.learning_rate
                ),
                "n_estimators": (
                    result.n_estimators
                ),
                "subsample": (
                    result.subsample
                ),
                "colsample_bytree": (
                    result.colsample_bytree
                ),
                "gamma": result.gamma,
                "reg_alpha": result.reg_alpha,
                "reg_lambda": result.reg_lambda,
            }
        )

    pd.DataFrame(
        summary_rows
    ).to_csv(
        SUMMARY_CSV,
        index=False,
    )

    print_metric(
        "Output directory",
        str(OUTPUT_DIR),
    )

    print_metric(
        "JSON results",
        str(RESULTS_JSON),
    )

    print_metric(
        "CSV results",
        str(RESULTS_CSV),
    )

    print_metric(
        "CSV ranked summary",
        str(SUMMARY_CSV),
    )


# =====================================================================
# FINAL ASSERTIONS
# =====================================================================

def final_assertions(
    results: list[TuningResult],
) -> None:

    print_section(
        "FINAL ASSERTIONS"
    )

    candidate_results = [
        result
        for result in results
        if result.candidate_id != "BASELINE"
    ]

    completed = [
        result
        for result in candidate_results
        if result.status == "COMPLETED"
    ]

    failed = [
        result
        for result in candidate_results
        if result.status == "FAILED"
    ]

    assertions: list[
        tuple[str, bool]
    ] = []

    assertions.append(
        (
            "At least one tuning candidate executed",
            len(candidate_results) > 0,
        )
    )

    assertions.append(
        (
            "At least one tuning candidate completed",
            len(completed) > 0,
        )
    )

    assertions.append(
        (
            "Expected feature count = 296",
            all(
                result.feature_count
                == EXPECTED_FEATURE_COUNT
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "Training row count correct",
            all(
                result.training_rows
                == EXPECTED_TRAIN_ROWS
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "Validation row count correct",
            all(
                result.validation_rows
                == EXPECTED_VALIDATION_ROWS
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "Validation data never passed to fit()",
            all(
                not result.validation_data_passed_to_fit
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "Test dataset never loaded",
            all(
                not result.test_data_loaded
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "Test data never passed to fit()",
            all(
                not result.test_data_passed_to_fit
                for result in results
            ),
        )
    )

    assertions.append(
        (
            "Completed metrics are finite",
            all(
                (
                    result.status != "COMPLETED"
                    or (
                        result.mae is not None
                        and result.rmse is not None
                        and result.r2 is not None
                        and result.mape is not None
                        and np.isfinite(result.mae)
                        and np.isfinite(result.rmse)
                        and np.isfinite(result.r2)
                        and np.isfinite(result.mape)
                    )
                )
                for result in results
            ),
        )
    )

    for label, passed in assertions:

        print_metric(
            label,
            "PASS" if passed else "FAIL",
        )

        if not passed:
            raise AssertionError(
                label
            )

    print_metric(
        "Completed candidates",
        len(completed),
    )

    print_metric(
        "Failed candidates",
        len(failed),
    )

    print()
    print(
        "ALL XGBOOST HYPERPARAMETER TUNING "
        "ASSERTIONS PASSED"
    )


# =====================================================================
# MAIN
# =====================================================================

def main() -> None:

    print_header(
        "SMARTPARK AI - "
        "BIRMINGHAM XGBOOST HYPERPARAMETER TUNING"
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
        "  Controlled XGBoost hyperparameter tuning"
    )
    print(
        "  No feature pipeline rebuild"
    )
    print(
        "  No hyperparameter search outside defined grid"
    )
    print(
        "  Validation used for evaluation only"
    )
    print(
        "  No early stopping"
    )
    print(
        "  Test dataset untouched"
    )

    print()
    print(
        "Established baseline:"
    )
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

    try:

        # ----------------------------------------------------------
        # Dataset contract.
        # ----------------------------------------------------------

        validate_dataset_files()

        # ----------------------------------------------------------
        # Manifest.
        # ----------------------------------------------------------

        manifest = load_feature_manifest()

        # ----------------------------------------------------------
        # Load ONLY train and validation.
        # ----------------------------------------------------------

        train, validation = load_datasets()

        # ----------------------------------------------------------
        # Feature contract.
        # ----------------------------------------------------------

        feature_columns = (
            validate_feature_contract(
                train,
                validation,
                manifest,
            )
        )

        # ----------------------------------------------------------
        # Target contract.
        # ----------------------------------------------------------

        validate_target_contract(
            train,
            validation,
        )

        # ----------------------------------------------------------
        # Chronological contract.
        # ----------------------------------------------------------

        validate_chronological_split(
            train,
            validation,
        )

        # ----------------------------------------------------------
        # Observation isolation.
        # ----------------------------------------------------------

        validate_observation_isolation(
            train,
            validation,
        )

        # ----------------------------------------------------------
        # Model matrices.
        # ----------------------------------------------------------

        (
            X_train,
            y_train,
            X_validation,
            y_validation,
        ) = build_model_matrices(
            train,
            validation,
            feature_columns,
        )

        # ----------------------------------------------------------
        # Candidate grid.
        # ----------------------------------------------------------

        candidates = build_candidates()

        print_section(
            "TUNING CANDIDATE GRID"
        )

        print_metric(
            "Baseline reference",
            "BASELINE",
        )

        print_metric(
            "Candidate count",
            len(candidates),
        )

        print()

        for candidate in candidates:

            print(
                f"  {candidate.candidate_id}: "
                f"{candidate.description}"
            )

        # ----------------------------------------------------------
        # Results begin with baseline reference.
        # ----------------------------------------------------------

        results: list[TuningResult] = [
            baseline_result()
        ]

        # ----------------------------------------------------------
        # Execute candidates sequentially.
        #
        # Sequential execution makes the experiment easier to audit
        # and prevents hidden parallel model state.
        # ----------------------------------------------------------

        for index, candidate in enumerate(
            candidates,
            start=1,
        ):

            print()
            print(
                f"[{index}/{len(candidates)}] "
                f"Running {candidate.candidate_id}"
            )

            result = run_candidate(
                candidate,
                X_train,
                y_train,
                X_validation,
                y_validation,
            )

            validate_result(
                result
            )

            results.append(
                result
            )

        # ----------------------------------------------------------
        # Ranking.
        # ----------------------------------------------------------

        print_header(
            "TUNING RESULTS RANKING"
        )

        ranked = rank_results(
            results
        )

        if not ranked:
            raise RuntimeError(
                "No tuning candidate completed successfully."
            )

        print(
            f"{'Rank':<6}"
            f"{'Candidate':<15}"
            f"{'MAE':>12}"
            f"{'RMSE':>12}"
            f"{'R²':>12}"
            f"{'MAPE':>12}"
        )

        print(
            "-" * 69
        )

        for rank, result in enumerate(
            ranked,
            start=1,
        ):

            print(
                f"{rank:<6}"
                f"{result.candidate_id:<15}"
                f"{result.mae:>12.6f}"
                f"{result.rmse:>12.6f}"
                f"{result.r2:>12.6f}"
                f"{result.mape:>11.4f}%"
            )

        # ----------------------------------------------------------
        # Best candidate.
        # ----------------------------------------------------------

        best = ranked[0]

        print_header(
            "BEST TUNING CANDIDATE"
        )

        print_metric(
            "Candidate",
            best.candidate_id,
        )

        print_metric(
            "Description",
            best.description,
        )

        print_metric(
            "MAE",
            f"{best.mae:.6f}",
        )

        print_metric(
            "RMSE",
            f"{best.rmse:.6f}",
        )

        print_metric(
            "R²",
            f"{best.r2:.6f}",
        )

        print_metric(
            "MAPE",
            f"{best.mape:.4f}%",
        )

        print()
        print(
            "Best candidate parameters:"
        )

        print_metric(
            "n_estimators",
            best.n_estimators,
        )

        print_metric(
            "learning_rate",
            best.learning_rate,
        )

        print_metric(
            "max_depth",
            best.max_depth,
        )

        print_metric(
            "min_child_weight",
            best.min_child_weight,
        )

        print_metric(
            "subsample",
            best.subsample,
        )

        print_metric(
            "colsample_bytree",
            best.colsample_bytree,
        )

        print_metric(
            "gamma",
            best.gamma,
        )

        print_metric(
            "reg_alpha",
            best.reg_alpha,
        )

        print_metric(
            "reg_lambda",
            best.reg_lambda,
        )

        # ----------------------------------------------------------
        # Baseline comparison.
        # ----------------------------------------------------------

        print()
        print(
            "Best candidate vs established baseline:"
        )

        print_metric(
            "MAE change",
            f"{best.mae - BASELINE_MAE:+.6f}",
        )

        print_metric(
            "MAE improvement %",
            f"{best.improvement_vs_baseline_mae_pct:+.2f}%",
        )

        print_metric(
            "RMSE change",
            f"{best.rmse - BASELINE_RMSE:+.6f}",
        )

        print_metric(
            "R² change",
            f"{best.r2 - BASELINE_R2:+.6f}",
        )

        # ----------------------------------------------------------
        # Persist.
        # ----------------------------------------------------------

        persist_results(
            results
        )

        # ----------------------------------------------------------
        # Assertions.
        # ----------------------------------------------------------

        final_assertions(
            results
        )

        # ----------------------------------------------------------
        # Final message.
        # ----------------------------------------------------------

        print()
        print_header(
            "BIRMINGHAM XGBOOST "
            "HYPERPARAMETER TUNING COMPLETED"
        )

        print(
            "Target:              "
            f"{TARGET_COLUMN}"
        )

        print(
            "Features:            "
            f"{EXPECTED_FEATURE_COUNT}"
        )

        print(
            "Training rows:       "
            f"{EXPECTED_TRAIN_ROWS}"
        )

        print(
            "Validation rows:     "
            f"{EXPECTED_VALIDATION_ROWS}"
        )

        print(
            "Candidates executed: "
            f"{len(candidates)}"
        )

        print(
            "Test dataset used:   NO"
        )

        print(
            "Early stopping:      NO"
        )

        print(
            "Pipeline rebuilt:    NO"
        )

        print()
        print(
            "The best candidate has been identified "
            "against the validation set."
        )

        print()
        print(
            "IMPORTANT:"
        )

        print(
            "The best candidate is NOT yet the final "
            "production model."
        )

        print(
            "Do not evaluate test.parquet yet."
        )

    except KeyboardInterrupt:

        print()
        print_header(
            "BIRMINGHAM XGBOOST TUNING INTERRUPTED"
        )

        print(
            "Experiment interrupted by user."
        )

        print(
            "No test data was loaded."
        )

        sys.exit(130)

    except Exception as exc:

        print()
        print_header(
            "BIRMINGHAM XGBOOST HYPERPARAMETER "
            "TUNING FAILED"
        )

        print(
            f"ERROR: {type(exc).__name__}: {exc}"
        )

        print()
        print(
            "NO persisted training datasets were modified."
        )

        print(
            "Test dataset was NOT loaded."
        )

        print(
            "No final production model was selected."
        )

        sys.exit(1)


if __name__ == "__main__":
    main()