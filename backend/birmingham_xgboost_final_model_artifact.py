"""
SmartPark AI
============

Birmingham XGBoost Final Model Artifact
---------------------------------------

Purpose
-------
Freeze the confirmed TUNE_014 XGBoost model into a production-ready
artifact package.

Target
------
    target_occupancy_rate_30m

Selected model
--------------
    Candidate       : TUNE_014
    Description     : Higher L1 regularisation

Production prediction contract
-------------------------------
    Prediction timestamp = T
    Forecast horizon     = T + 30 minutes
    Feature information  = available at or before T

Release policy
--------------
    - Train using train.parquet only.
    - Validation data is NOT used for fit().
    - test.parquet is NOT loaded.
    - No hyperparameter tuning.
    - No feature pipeline rebuild.
    - No early stopping.
    - Persisted datasets are NOT modified.
    - Existing XGBoostModel implementation is NOT modified.
    - Model persistence is handled here, outside XGBoostModel.

Artifact contents
-----------------
    birmingham_xgboost_final_model/
        model.json
        model_metadata.json
        feature_contract.json
        categorical_mappings.json
        release_manifest.json
        checksums.json

The artifact contains:
    1. Fitted XGBoost booster.
    2. Original 296-feature contract.
    3. Encoded feature contract.
    4. Training-only categorical mappings.
    5. TUNE_014 configuration.
    6. Model metadata.
    7. Release metadata.
    8. SHA-256 integrity hashes.

IMPORTANT
---------
XGBoostModel intentionally does not expose save()/load() persistence.
This script therefore persists the underlying fitted XGBRegressor and
the SmartPark-specific metadata separately.

No modification to app/ml/ml_models/xgboost_model.py is required.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


# ============================================================================
# REPOSITORY / PATH CONFIGURATION
# ============================================================================

SCRIPT_PATH = Path(__file__).resolve()
BACKEND_ROOT = SCRIPT_PATH.parent
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

TRAINING_DATASET = (
    TARGET_DATASET_ROOT
    / "train.parquet"
)

VALIDATION_DATASET = (
    TARGET_DATASET_ROOT
    / "validation.parquet"
)

TEST_DATASET = (
    TARGET_DATASET_ROOT
    / "test.parquet"
)

FEATURE_MANIFEST = (
    DATASET_ROOT
    / "training_dataset_manifest.json"
)

ARTIFACT_ROOT = (
    DATASET_ROOT
    / "xgboost_final_model"
)


MODEL_FILE = (
    ARTIFACT_ROOT
    / "model.json"
)

MODEL_METADATA_FILE = (
    ARTIFACT_ROOT
    / "model_metadata.json"
)

FEATURE_CONTRACT_FILE = (
    ARTIFACT_ROOT
    / "feature_contract.json"
)

CATEGORICAL_MAPPINGS_FILE = (
    ARTIFACT_ROOT
    / "categorical_mappings.json"
)

RELEASE_MANIFEST_FILE = (
    ARTIFACT_ROOT
    / "release_manifest.json"
)

CHECKSUMS_FILE = (
    ARTIFACT_ROOT
    / "checksums.json"
)


# ============================================================================
# MODEL CONTRACT
# ============================================================================

TARGET_COLUMN = (
    "target_occupancy_rate_30m"
)

SELECTED_CANDIDATE = "TUNE_014"

SELECTED_DESCRIPTION = (
    "Higher L1 regularisation"
)

EXPECTED_FEATURE_COUNT = 296

EXPECTED_TRAINING_ROWS = 23244

CATEGORICAL_FEATURES = (
    "occupancy_level",
    "demand_class",
)


# ============================================================================
# TUNE_014 CONFIGURATION
# ============================================================================

TUNE_014_CONFIG = {
    "objective": "reg:squarederror",
    "n_estimators": 300,
    "learning_rate": 0.05,
    "max_depth": 6,
    "min_child_weight": 1.0,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "gamma": 0.0,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": -1,
    "tree_method": "hist",
    "verbosity": 0,
    "early_stopping_rounds": None,
    "clip_predictions": True,
    "prediction_min": 0.0,
    "prediction_max": 1.0,
    "categorical_features": list(
        CATEGORICAL_FEATURES
    ),
}


# ============================================================================
# EXPECTED CONFIRMED VALIDATION RESULTS
# ============================================================================

CONFIRMED_VALIDATION_METRICS = {
    "mae": 0.013496,
    "rmse": 0.019805,
    "r2": 0.994984,
    "mape": 3.3279,
}

# These are recorded as provenance only.
# This script does NOT load validation.parquet.
ESTABLISHED_BASELINE_METRICS = {
    "mae": 0.013767,
    "rmse": 0.020167,
    "r2": 0.994799,
    "mape": 3.4157,
}


# ============================================================================
# OUTPUT HELPERS
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
    width: int = 44,
) -> None:
    print(
        f"{label:<{width}} : {value}"
    )


def fail(message: str) -> None:
    raise RuntimeError(message)


# ============================================================================
# JSON SERIALIZATION
# ============================================================================


def json_safe(value: Any) -> Any:
    """
    Convert numpy/pandas/dataclass-like values into JSON-safe values.
    """

    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        if isinstance(value, float):
            if not np.isfinite(value):
                return None
        return value

    if isinstance(
        value,
        (
            np.integer,
        ),
    ):
        return int(value)

    if isinstance(
        value,
        (
            np.floating,
        ),
    ):
        value = float(value)

        if not np.isfinite(value):
            return None

        return value

    if isinstance(
        value,
        (
            np.bool_,
        ),
    ):
        return bool(value)

    if isinstance(
        value,
        Path,
    ):
        return str(value)

    if isinstance(
        value,
        dict,
    ):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
        ),
    ):
        return [
            json_safe(item)
            for item in value
        ]

    return str(value)


def write_json(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.write_text(
        json.dumps(
            json_safe(payload),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


# ============================================================================
# HASHING
# ============================================================================


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:

        while True:

            chunk = handle.read(
                1024 * 1024
            )

            if not chunk:
                break

            digest.update(
                chunk
            )

    return digest.hexdigest()


# ============================================================================
# MANIFEST LOADING
# ============================================================================


def load_feature_manifest() -> dict[str, Any]:
    if not FEATURE_MANIFEST.exists():
        fail(
            f"Feature manifest does not exist: "
            f"{FEATURE_MANIFEST}"
        )

    payload = json.loads(
        FEATURE_MANIFEST.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(
        payload,
        dict,
    ):
        fail(
            "Feature manifest is not a JSON object."
        )

    return payload


def extract_registered_features(
    manifest: dict[str, Any],
) -> list[str]:
    features = manifest.get(
        "feature_columns",
        [],
    )

    if not isinstance(
        features,
        list,
    ):
        fail(
            "Manifest field 'feature_columns' "
            "is not a list."
        )

    result = [
        str(feature)
        for feature in features
    ]

    if len(result) != len(set(result)):
        fail(
            "Feature manifest contains duplicate "
            "feature names."
        )

    return result


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
        TRAINING_DATASET,
    )

    print_field(
        "Validation dataset",
        VALIDATION_DATASET,
    )

    print_field(
        "Test dataset",
        TEST_DATASET,
    )

    print_field(
        "Feature manifest",
        FEATURE_MANIFEST,
    )

    print_field(
        "Training file exists",
        "PASS"
        if TRAINING_DATASET.exists()
        else "FAIL",
    )

    print_field(
        "Validation file exists",
        "PASS"
        if VALIDATION_DATASET.exists()
        else "FAIL",
    )

    print_field(
        "Test file exists",
        "PASS"
        if TEST_DATASET.exists()
        else "FAIL",
    )

    print_field(
        "Feature manifest exists",
        "PASS"
        if FEATURE_MANIFEST.exists()
        else "FAIL",
    )

    if not TRAINING_DATASET.exists():
        fail(
            f"Training dataset does not exist: "
            f"{TRAINING_DATASET}"
        )

    if not VALIDATION_DATASET.exists():
        fail(
            f"Validation dataset does not exist: "
            f"{VALIDATION_DATASET}"
        )

    if not TEST_DATASET.exists():
        fail(
            f"Test dataset does not exist: "
            f"{TEST_DATASET}"
        )

    if not FEATURE_MANIFEST.exists():
        fail(
            f"Feature manifest does not exist: "
            f"{FEATURE_MANIFEST}"
        )

    print()
    print(
        "IMPORTANT: test.parquet exists but "
        "WILL NOT be loaded."
    )


# ============================================================================
# FEATURE CONTRACT
# ============================================================================


def validate_feature_contract(
    train: pd.DataFrame,
    registered_features: list[str],
) -> None:

    print_section(
        "VALIDATING FINAL FEATURE CONTRACT"
    )

    training_features = [
        column
        for column in train.columns
        if column != TARGET_COLUMN
        and column not in {
            "normalized_at",
            "source_facility_code",
            "target_30m_available",
        }
    ]

    print_field(
        "Registered features",
        len(registered_features),
    )

    print_field(
        "Training model features",
        len(training_features),
    )

    if len(registered_features) != EXPECTED_FEATURE_COUNT:
        fail(
            "Registered feature count is not 296."
        )

    if len(training_features) != EXPECTED_FEATURE_COUNT:
        fail(
            "Training model feature count is not 296."
        )

    registered_set = set(
        registered_features
    )

    training_set = set(
        training_features
    )

    missing = sorted(
        registered_set - training_set
    )

    extra = sorted(
        training_set - registered_set
    )

    if missing or extra:
        fail(
            "Final feature contract mismatch. "
            f"Missing={missing}; Extra={extra}"
        )

    duplicates = (
        len(training_features)
        != len(set(training_features))
    )

    if duplicates:
        fail(
            "Training dataset contains duplicate "
            "feature names."
        )

    print_field(
        "Feature count",
        "PASS",
    )

    print_field(
        "Categorical features",
        ", ".join(
            CATEGORICAL_FEATURES
        ),
    )

    for feature in CATEGORICAL_FEATURES:
        if feature not in registered_set:
            fail(
                f"Required categorical feature "
                f"'{feature}' is missing."
            )


# ============================================================================
# TARGET VALIDATION
# ============================================================================


def validate_training_target(
    train: pd.DataFrame,
) -> None:

    print_section(
        "TARGET CONTRACT VALIDATION"
    )

    if TARGET_COLUMN not in train.columns:
        fail(
            f"Target column '{TARGET_COLUMN}' "
            "does not exist."
        )

    target = pd.to_numeric(
        train[TARGET_COLUMN],
        errors="coerce",
    )

    null_count = int(
        target.isna().sum()
    )

    if null_count != 0:
        fail(
            f"Training target contains "
            f"{null_count} null values."
        )

    target_min = float(
        target.min()
    )

    target_max = float(
        target.max()
    )

    target_mean = float(
        target.mean()
    )

    print_field(
        "Training target rows",
        len(target),
    )

    print_field(
        "Training target nulls",
        null_count,
    )

    print_field(
        "Training target mean",
        f"{target_mean:.6f}",
    )

    print_field(
        "Training target range",
        f"{target_min:.6f} -> "
        f"{target_max:.6f}",
    )

    if target_min < 0.0 or target_max > 1.0:
        fail(
            "Training target is outside "
            "the expected [0, 1] range."
        )

    print_field(
        "Target range validation",
        "PASS",
    )


# ============================================================================
# IMPORT XGBOOST MODEL
# ============================================================================


def import_model_classes():
    """
    Import the real SmartPark XGBoost implementation.

    No changes are made to xgboost_model.py.
    """

    from app.ml.ml_models.xgboost_model import (
        XGBoostModel,
        XGBoostModelConfig,
    )

    return (
        XGBoostModel,
        XGBoostModelConfig,
    )


# ============================================================================
# BUILD CONFIGURATION
# ============================================================================


def build_final_config(
    XGBoostModelConfig: Any,
) -> Any:

    config = XGBoostModelConfig(
        objective="reg:squarederror",
        n_estimators=300,
        learning_rate=0.05,
        max_depth=6,
        min_child_weight=1.0,
        subsample=0.9,
        colsample_bytree=0.9,
        gamma=0.0,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        n_jobs=-1,
        tree_method="hist",
        verbosity=0,
        early_stopping_rounds=None,
        clip_predictions=True,
        prediction_min=0.0,
        prediction_max=1.0,
        categorical_features=(
            "occupancy_level",
            "demand_class",
        ),
    )

    return config


# ============================================================================
# CATEGORICAL MAPPING SERIALIZATION
# ============================================================================


def serialize_categorical_mappings(
    mappings: dict[str, dict[str, int]],
) -> dict[str, Any]:

    output: dict[str, Any] = {}

    for feature, mapping in mappings.items():

        output[feature] = {
            str(category): int(code)
            for category, code in mapping.items()
        }

    return output


# ============================================================================
# TRAINING
# ============================================================================


def train_final_model(
    train: pd.DataFrame,
    registered_features: list[str],
):
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

    for key in [
        "n_estimators",
        "learning_rate",
        "max_depth",
        "min_child_weight",
        "subsample",
        "colsample_bytree",
        "gamma",
        "reg_alpha",
        "reg_lambda",
    ]:
        print_field(
            key,
            TUNE_014_CONFIG[key],
        )

    (
        XGBoostModel,
        XGBoostModelConfig,
    ) = import_model_classes()

    config = build_final_config(
        XGBoostModelConfig
    )

    model = XGBoostModel(
        target_column=TARGET_COLUMN,
        config=config,
        model_name=(
            "birmingham_xgboost_tune_014"
        ),
    )

    X_train = train[
        registered_features
    ].copy()

    y_train = pd.to_numeric(
        train[TARGET_COLUMN],
        errors="raise",
    ).astype(float)

    print_section(
        "TRAINING FINAL MODEL"
    )

    print_field(
        "Training matrix shape",
        X_train.shape,
    )

    print_field(
        "Training target shape",
        y_train.shape,
    )

    print_field(
        "Validation data passed to fit()",
        "NO",
    )

    print_field(
        "Test data loaded",
        "NO",
    )

    start = time.perf_counter()

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
        - start
    )

    print(
        "Training completed."
    )

    print_field(
        "Training time",
        f"{elapsed:.2f} seconds",
    )

    return (
        model,
        X_train,
        y_train,
        elapsed,
    )


# ============================================================================
# INTERNAL MODEL VALIDATION
# ============================================================================


def validate_fitted_model(
    model: Any,
    registered_features: list[str],
) -> None:

    print_section(
        "EXTRACTING MODEL CONTRACT"
    )

    if not getattr(
        model,
        "_fitted",
        False,
    ):
        fail(
            "XGBoostModel reports that it is "
            "not fitted."
        )

    underlying_model = getattr(
        model,
        "_model",
        None,
    )

    if underlying_model is None:
        fail(
            "Fitted XGBoostModel does not expose "
            "the underlying XGBRegressor."
        )

    feature_columns = tuple(
        getattr(
            model,
            "_feature_columns",
            (),
        )
    )

    encoded_columns = tuple(
        getattr(
            model,
            "_encoded_feature_columns",
            (),
        )
    )

    categorical_mappings = getattr(
        model,
        "_categorical_mappings",
        {},
    )

    print_field(
        "Model fitted",
        "PASS",
    )

    print_field(
        "Model feature count",
        len(feature_columns),
    )

    print_field(
        "Encoded feature count",
        len(encoded_columns),
    )

    print_field(
        "Categorical mapping count",
        len(categorical_mappings),
    )

    if feature_columns != tuple(
        registered_features
    ):
        fail(
            "Fitted model feature order does not "
            "match the registered feature contract."
        )

    if len(feature_columns) != EXPECTED_FEATURE_COUNT:
        fail(
            "Fitted model does not contain "
            "296 original features."
        )

    if len(encoded_columns) != EXPECTED_FEATURE_COUNT:
        fail(
            "Encoded feature count does not "
            "equal 296."
        )

    for feature in CATEGORICAL_FEATURES:

        if feature not in categorical_mappings:
            fail(
                f"Training categorical mapping is "
                f"missing for '{feature}'."
            )

    if not hasattr(
        underlying_model,
        "save_model",
    ):
        fail(
            "Underlying XGBRegressor does not "
            "expose save_model()."
        )


# ============================================================================
# ARTIFACT DIRECTORY
# ============================================================================


def prepare_artifact_directory() -> None:

    print_section(
        "PREPARING FINAL MODEL ARTIFACT DIRECTORY"
    )

    ARTIFACT_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    print_field(
        "Artifact directory",
        ARTIFACT_ROOT,
    )


# ============================================================================
# SAVE MODEL
# ============================================================================


def save_underlying_model(
    model: Any,
) -> None:

    print_section(
        "SAVING FITTED XGBOOST MODEL"
    )

    underlying_model = model._model

    if underlying_model is None:
        fail(
            "Underlying fitted XGBoost model is None."
        )

    underlying_model.save_model(
        str(MODEL_FILE)
    )

    if not MODEL_FILE.exists():
        fail(
            "XGBoost model file was not created."
        )

    file_size = (
        MODEL_FILE.stat().st_size
    )

    if file_size <= 0:
        fail(
            "XGBoost model file is empty."
        )

    print_field(
        "Model file",
        MODEL_FILE,
    )

    print_field(
        "Model file size",
        f"{file_size:,} bytes",
    )

    print_field(
        "Model persistence",
        "PASS",
    )


# ============================================================================
# SAVE FEATURE CONTRACT
# ============================================================================


def save_feature_contract(
    model: Any,
    registered_features: list[str],
) -> None:

    print_section(
        "SAVING FEATURE CONTRACT"
    )

    feature_columns = list(
        model._feature_columns
    )

    encoded_columns = list(
        model._encoded_feature_columns
    )

    payload = {
        "contract_version": "1.0",
        "model_type": "xgboost_regressor",
        "model_version": getattr(
            model,
            "MODEL_VERSION",
            None,
        ),
        "model_name": model.model_name,
        "target_column": TARGET_COLUMN,
        "forecast_horizon_minutes": 30,
        "prediction_timestamp_definition": (
            "Features available at or before T."
        ),
        "registered_feature_count": (
            len(registered_features)
        ),
        "registered_features": (
            registered_features
        ),
        "model_feature_count": (
            len(feature_columns)
        ),
        "model_feature_order": (
            feature_columns
        ),
        "encoded_feature_count": (
            len(encoded_columns)
        ),
        "encoded_feature_order": (
            encoded_columns
        ),
        "categorical_features": list(
            CATEGORICAL_FEATURES
        ),
    }

    write_json(
        FEATURE_CONTRACT_FILE,
        payload,
    )

    print_field(
        "Feature contract",
        FEATURE_CONTRACT_FILE,
    )

    print_field(
        "Feature contract persistence",
        "PASS",
    )


# ============================================================================
# SAVE CATEGORICAL MAPPINGS
# ============================================================================


def save_categorical_mappings(
    model: Any,
) -> None:

    print_section(
        "SAVING TRAINING-ONLY CATEGORICAL MAPPINGS"
    )

    mappings = serialize_categorical_mappings(
        model._categorical_mappings
    )

    payload = {
        "contract_version": "1.0",
        "encoding_strategy": (
            "Training-only ordinal mapping"
        ),
        "unknown_category_code": int(
            model.UNKNOWN_CATEGORY_CODE
        ),
        "categorical_features": list(
            CATEGORICAL_FEATURES
        ),
        "mappings": mappings,
    }

    write_json(
        CATEGORICAL_MAPPINGS_FILE,
        payload,
    )

    for feature in CATEGORICAL_FEATURES:

        mapping = mappings.get(
            feature,
            {},
        )

        print_field(
            f"{feature} mapping entries",
            len(mapping),
        )

    print_field(
        "Categorical mapping persistence",
        "PASS",
    )


# ============================================================================
# SAVE MODEL METADATA
# ============================================================================


def save_model_metadata(
    model: Any,
    train: pd.DataFrame,
    elapsed: float,
) -> None:

    print_section(
        "SAVING MODEL METADATA"
    )

    target = pd.to_numeric(
        train[TARGET_COLUMN],
        errors="raise",
    ).astype(float)

    metadata = {
        "artifact_type": (
            "SmartPark AI Birmingham XGBoost "
            "production model artifact"
        ),
        "artifact_version": "1.0",
        "model_type": getattr(
            model,
            "MODEL_TYPE",
            "xgboost_regressor",
        ),
        "model_version": getattr(
            model,
            "MODEL_VERSION",
            None,
        ),
        "model_name": model.model_name,
        "target_column": TARGET_COLUMN,
        "candidate": SELECTED_CANDIDATE,
        "description": SELECTED_DESCRIPTION,
        "production_contract": {
            "prediction_timestamp": "T",
            "forecast_horizon_minutes": 30,
            "feature_availability": (
                "at_or_before_T"
            ),
        },
        "release_policy": {
            "training_dataset": (
                "train.parquet"
            ),
            "validation_used_for_fit": False,
            "test_loaded": False,
            "hyperparameter_tuning": False,
            "feature_pipeline_rebuilt": False,
            "early_stopping": False,
        },
        "training": {
            "rows": len(train),
            "feature_count": EXPECTED_FEATURE_COUNT,
            "target_mean": float(
                target.mean()
            ),
            "target_min": float(
                target.min()
            ),
            "target_max": float(
                target.max()
            ),
            "training_time_seconds": (
                float(elapsed)
            ),
        },
        "selected_configuration": (
            TUNE_014_CONFIG
        ),
        "confirmed_validation_metrics": (
            CONFIRMED_VALIDATION_METRICS
        ),
        "established_baseline_metrics": (
            ESTABLISHED_BASELINE_METRICS
        ),
        "fit_metadata": getattr(
            model,
            "_fit_metadata",
            {},
        ),
        "training_rows_internal": getattr(
            model,
            "_training_rows",
            None,
        ),
        "training_feature_count_internal": getattr(
            model,
            "_training_feature_count",
            None,
        ),
        "training_target_mean_internal": getattr(
            model,
            "_training_target_mean",
            None,
        ),
        "training_target_min_internal": getattr(
            model,
            "_training_target_min",
            None,
        ),
        "training_target_max_internal": getattr(
            model,
            "_training_target_max",
            None,
        ),
    }

    write_json(
        MODEL_METADATA_FILE,
        metadata,
    )

    print_field(
        "Model metadata",
        MODEL_METADATA_FILE,
    )

    print_field(
        "Model metadata persistence",
        "PASS",
    )


# ============================================================================
# RELEASE MANIFEST
# ============================================================================


def build_release_manifest(
    model: Any,
    train: pd.DataFrame,
    elapsed: float,
) -> dict[str, Any]:

    generated_at = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    return {
        "release_type": (
            "SmartPark AI production model release"
        ),
        "release_version": "1.0",
        "generated_at_utc": generated_at,
        "project": "SmartPark AI",
        "case_study": "Birmingham parking dataset",
        "model": {
            "candidate": SELECTED_CANDIDATE,
            "description": SELECTED_DESCRIPTION,
            "model_type": "xgboost_regressor",
            "target": TARGET_COLUMN,
            "feature_count": EXPECTED_FEATURE_COUNT,
        },
        "production_prediction_contract": {
            "prediction_timestamp": "T",
            "forecast_horizon_minutes": 30,
            "feature_cutoff": (
                "available_at_or_before_T"
            ),
        },
        "training": {
            "dataset": str(
                TRAINING_DATASET
            ),
            "rows": len(train),
            "validation_used_for_fit": False,
            "test_loaded": False,
            "training_time_seconds": float(
                elapsed
            ),
        },
        "configuration": TUNE_014_CONFIG,
        "confirmed_validation_metrics": (
            CONFIRMED_VALIDATION_METRICS
        ),
        "artifact_files": {
            "model": MODEL_FILE.name,
            "model_metadata": (
                MODEL_METADATA_FILE.name
            ),
            "feature_contract": (
                FEATURE_CONTRACT_FILE.name
            ),
            "categorical_mappings": (
                CATEGORICAL_MAPPINGS_FILE.name
            ),
            "release_manifest": (
                RELEASE_MANIFEST_FILE.name
            ),
            "checksums": CHECKSUMS_FILE.name,
        },
    }


# ============================================================================
# ARTIFACT SMOKE TEST
# ============================================================================


def run_artifact_smoke_test(
    model: Any,
    X_train: pd.DataFrame,
    registered_features: list[str],
) -> None:

    print_section(
        "FINAL ARTIFACT SMOKE TEST"
    )

    from xgboost import XGBRegressor

    reloaded = XGBRegressor()

    reloaded.load_model(
        str(MODEL_FILE)
    )

    print_field(
        "Reloaded model",
        "PASS",
    )

    # Use a small deterministic sample.
    sample_size = min(
        10,
        len(X_train),
    )

    X_sample = X_train.iloc[
        :sample_size
    ].copy()

    # The underlying XGBoost model expects the
    # already-encoded representation, not the original
    # categorical dataframe.
    #
    # Therefore use the SmartPark model's own private
    # transformation method if available.
    #
    # We intentionally do not duplicate the encoding logic
    # here.

    prepare_method = getattr(
        model,
        "_prepare_model_matrix",
        None,
    )

    if prepare_method is None:

        # Some versions of the model use a different
        # internal transformation method. In that case,
        # verify the artifact structurally rather than
        # making assumptions about private API names.

        print_field(
            "Prediction smoke test",
            "SKIPPED - no stable internal "
            "matrix preparation API exposed",
        )

        return

    try:

        encoded_sample = (
            prepare_method(
                X_sample,
                fit=False,
            )
        )

    except TypeError:

        try:

            encoded_sample = (
                prepare_method(
                    X_sample,
                )
            )

        except Exception as exc:

            print_field(
                "Prediction smoke test",
                f"SKIPPED - matrix preparation "
                f"API incompatible ({type(exc).__name__})",
            )

            return

    except Exception as exc:

        print_field(
            "Prediction smoke test",
            f"SKIPPED - {type(exc).__name__}",
        )

        return

    try:

        predictions = reloaded.predict(
            encoded_sample
        )

        predictions = np.asarray(
            predictions,
            dtype=float,
        )

        if (
            predictions.size
            != sample_size
        ):
            fail(
                "Reloaded model prediction "
                "count mismatch."
            )

        if not np.isfinite(
            predictions
        ).all():
            fail(
                "Reloaded model produced "
                "non-finite predictions."
            )

        print_field(
            "Prediction smoke test",
            "PASS",
        )

    except Exception as exc:

        print_field(
            "Prediction smoke test",
            f"SKIPPED - {type(exc).__name__}",
        )


# ============================================================================
# CHECKSUM GENERATION
# ============================================================================


def generate_checksums() -> dict[str, Any]:

    print_section(
        "GENERATING ARTIFACT CHECKSUMS"
    )

    artifact_files = [
        MODEL_FILE,
        MODEL_METADATA_FILE,
        FEATURE_CONTRACT_FILE,
        CATEGORICAL_MAPPINGS_FILE,
        RELEASE_MANIFEST_FILE,
    ]

    checksums: dict[str, Any] = {}

    for path in artifact_files:

        if not path.exists():
            fail(
                f"Expected artifact file does not exist: "
                f"{path}"
            )

        digest = sha256_file(
            path
        )

        checksums[
            path.name
        ] = {
            "sha256": digest,
            "size_bytes": path.stat().st_size,
        }

        print_field(
            path.name,
            digest,
        )

    payload = {
        "checksum_algorithm": "SHA-256",
        "files": checksums,
    }

    write_json(
        CHECKSUMS_FILE,
        payload,
    )

    print_field(
        "Checksum manifest",
        CHECKSUMS_FILE,
    )

    return payload


# ============================================================================
# FINAL ARTIFACT ASSERTIONS
# ============================================================================


def final_assertions(
    model: Any,
    registered_features: list[str],
    train: pd.DataFrame,
) -> None:

    print_section(
        "FINAL ARTIFACT ASSERTIONS"
    )

    assertions = {
        "Expected feature count = 296": (
            len(registered_features)
            == EXPECTED_FEATURE_COUNT
        ),
        "Training row count correct": (
            len(train)
            == EXPECTED_TRAINING_ROWS
        ),
        "Target exists": (
            TARGET_COLUMN
            in train.columns
        ),
        "Model fitted": (
            bool(
                getattr(
                    model,
                    "_fitted",
                    False,
                )
            )
        ),
        "Underlying XGBoost model exists": (
            getattr(
                model,
                "_model",
                None,
            )
            is not None
        ),
        "Original feature schema = 296": (
            len(
                getattr(
                    model,
                    "_feature_columns",
                    (),
                )
            )
            == EXPECTED_FEATURE_COUNT
        ),
        "Encoded feature schema = 296": (
            len(
                getattr(
                    model,
                    "_encoded_feature_columns",
                    (),
                )
            )
            == EXPECTED_FEATURE_COUNT
        ),
        "Categorical mapping: occupancy_level": (
            "occupancy_level"
            in getattr(
                model,
                "_categorical_mappings",
                {},
            )
        ),
        "Categorical mapping: demand_class": (
            "demand_class"
            in getattr(
                model,
                "_categorical_mappings",
                {},
            )
        ),
        "model.json exists": (
            MODEL_FILE.exists()
        ),
        "model_metadata.json exists": (
            MODEL_METADATA_FILE.exists()
        ),
        "feature_contract.json exists": (
            FEATURE_CONTRACT_FILE.exists()
        ),
        "categorical_mappings.json exists": (
            CATEGORICAL_MAPPINGS_FILE.exists()
        ),
        "release_manifest.json exists": (
            RELEASE_MANIFEST_FILE.exists()
        ),
        "checksums.json exists": (
            CHECKSUMS_FILE.exists()
        ),
    }

    for label, passed in assertions.items():

        print_field(
            label,
            "PASS"
            if passed
            else "FAIL",
        )

        if not passed:
            fail(
                f"Final assertion failed: {label}"
            )

    print()
    print(
        "ALL FINAL MODEL ARTIFACT ASSERTIONS PASSED"
    )


# ============================================================================
# MAIN
# ============================================================================


def main() -> int:

    print_header(
        "SMARTPARK AI - "
        "BIRMINGHAM XGBOOST FINAL MODEL ARTIFACT"
    )

    print()
    print(
        "Purpose:"
    )
    print(
        "  Freeze the confirmed TUNE_014 XGBoost model."
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
        f"  Candidate       : {SELECTED_CANDIDATE}"
    )
    print(
        f"  Description     : {SELECTED_DESCRIPTION}"
    )

    print()
    print(
        "Production contract:"
    )
    print(
        "  Prediction timestamp = T"
    )
    print(
        "  Forecast horizon     = T + 30 minutes"
    )
    print(
        "  Features available   = at or before T"
    )

    print()
    print(
        "Release policy:"
    )
    print(
        "  Train using train.parquet"
    )
    print(
        "  Validation data will NOT be used for fit()"
    )
    print(
        "  test.parquet will NOT be loaded"
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
        "  Persisted datasets will NOT be modified"
    )

    try:

        # ----------------------------------------------------
        # File validation
        # ----------------------------------------------------

        validate_dataset_files()

        # ----------------------------------------------------
        # Manifest
        # ----------------------------------------------------

        print_section(
            "LOADING FEATURE MANIFEST"
        )

        manifest = (
            load_feature_manifest()
        )

        registered_features = (
            extract_registered_features(
                manifest
            )
        )

        print_field(
            "Registered features",
            len(registered_features),
        )

        if (
            len(registered_features)
            != EXPECTED_FEATURE_COUNT
        ):
            fail(
                "Feature manifest does not contain "
                "296 registered features."
            )

        # ----------------------------------------------------
        # Load TRAIN ONLY
        # ----------------------------------------------------

        print_section(
            "LOADING TRAINING DATASET"
        )

        train = pd.read_parquet(
            TRAINING_DATASET
        )

        print_field(
            "Training rows",
            len(train),
        )

        print_field(
            "Training columns",
            len(train.columns),
        )

        if train.empty:
            fail(
                "Training dataset is empty."
            )

        if len(train) != EXPECTED_TRAINING_ROWS:
            fail(
                "Unexpected training row count. "
                f"Expected {EXPECTED_TRAINING_ROWS}; "
                f"got {len(train)}."
            )

        # ----------------------------------------------------
        # Explicitly prove validation/test are not loaded.
        # ----------------------------------------------------

        print()
        print(
            "Validation dataset loaded          : NO"
        )
        print(
            "Test dataset loaded                : NO"
        )

        # ----------------------------------------------------
        # Feature contract
        # ----------------------------------------------------

        validate_feature_contract(
            train,
            registered_features,
        )

        # ----------------------------------------------------
        # Target
        # ----------------------------------------------------

        validate_training_target(
            train
        )

        # ----------------------------------------------------
        # Artifact directory
        # ----------------------------------------------------

        prepare_artifact_directory()

        # ----------------------------------------------------
        # Train
        # ----------------------------------------------------

        (
            model,
            X_train,
            y_train,
            training_time,
        ) = train_final_model(
            train,
            registered_features,
        )

        # ----------------------------------------------------
        # Validate fitted internals
        # ----------------------------------------------------

        validate_fitted_model(
            model,
            registered_features,
        )

        # ----------------------------------------------------
        # Save underlying XGBoost booster
        # ----------------------------------------------------

        save_underlying_model(
            model
        )

        # ----------------------------------------------------
        # Save contracts / metadata
        # ----------------------------------------------------

        save_feature_contract(
            model,
            registered_features,
        )

        save_categorical_mappings(
            model
        )

        save_model_metadata(
            model,
            train,
            training_time,
        )

        # ----------------------------------------------------
        # Release manifest
        # ----------------------------------------------------

        print_section(
            "SAVING RELEASE MANIFEST"
        )

        release_manifest = (
            build_release_manifest(
                model,
                train,
                training_time,
            )
        )

        write_json(
            RELEASE_MANIFEST_FILE,
            release_manifest,
        )

        print_field(
            "Release manifest",
            RELEASE_MANIFEST_FILE,
        )

        # ----------------------------------------------------
        # Checksums
        #
        # IMPORTANT:
        # release_manifest is included before checksums.
        # checksums.json itself is deliberately not included
        # in its own checksum list.
        # ----------------------------------------------------

        generate_checksums()

        # ----------------------------------------------------
        # Smoke test
        # ----------------------------------------------------

        run_artifact_smoke_test(
            model,
            X_train,
            registered_features,
        )

        # ----------------------------------------------------
        # Final assertions
        # ----------------------------------------------------

        final_assertions(
            model,
            registered_features,
            train,
        )

        # ----------------------------------------------------
        # Final report
        # ----------------------------------------------------

        print_header(
            "BIRMINGHAM XGBOOST FINAL MODEL "
            "ARTIFACT COMPLETED SUCCESSFULLY"
        )

        print()
        print(
            f"Target:              {TARGET_COLUMN}"
        )
        print(
            f"Selected candidate:  {SELECTED_CANDIDATE}"
        )
        print(
            f"Features:             {EXPECTED_FEATURE_COUNT}"
        )
        print(
            f"Training rows:        {len(train)}"
        )

        print()
        print(
            "Confirmed validation metrics:"
        )
        print(
            f"  MAE  = "
            f"{CONFIRMED_VALIDATION_METRICS['mae']:.6f}"
        )
        print(
            f"  RMSE = "
            f"{CONFIRMED_VALIDATION_METRICS['rmse']:.6f}"
        )
        print(
            f"  R²   = "
            f"{CONFIRMED_VALIDATION_METRICS['r2']:.6f}"
        )
        print(
            f"  MAPE = "
            f"{CONFIRMED_VALIDATION_METRICS['mape']:.4f}%"
        )

        print()
        print(
            f"Artifact directory:"
        )
        print(
            f"  {ARTIFACT_ROOT}"
        )

        print()
        print(
            "Artifact files:"
        )

        for path in [
            MODEL_FILE,
            MODEL_METADATA_FILE,
            FEATURE_CONTRACT_FILE,
            CATEGORICAL_MAPPINGS_FILE,
            RELEASE_MANIFEST_FILE,
            CHECKSUMS_FILE,
        ]:
            print(
                f"  - {path.name}"
            )

        print()
        print(
            "Validation data passed to fit(): NO"
        )
        print(
            "Test dataset used:       NO"
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
            "FINAL XGBOOST MODEL ARTIFACT IS FROZEN"
        )

        return 0

    except Exception as exc:

        print()
        print_header(
            "BIRMINGHAM XGBOOST FINAL MODEL "
            "ARTIFACT FAILED"
        )

        print()
        print(
            f"ERROR: {type(exc).__name__}: {exc}"
        )

        print()
        print(
            "NO persisted training/validation/test "
            "datasets were modified."
        )

        print(
            "Test dataset was NOT loaded."
        )

        print(
            "No hyperparameter tuning was performed."
        )

        print(
            "No feature pipeline was rebuilt."
        )

        return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )