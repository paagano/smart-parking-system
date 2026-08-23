"""
SMARTPARK AI
Birmingham XGBoost Model-Matrix Diagnostic

Purpose
-------
Diagnose the exact point at which non-finite values may appear
between the persisted Birmingham Parquet datasets and the
XGBoost model matrix.

IMPORTANT
---------
This script:

- DOES NOT modify any dataset.
- DOES NOT modify the model.
- DOES NOT train XGBoost.
- DOES NOT load the test dataset.
- DOES NOT rebuild the feature pipeline.

It loads the persisted training and validation datasets and
passes them through the same validation / categorical encoding /
matrix preparation path used by XGBoostModel.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.ml.ml_models.xgboost_model import (
    XGBoostModel,
    XGBoostModelConfig,
)


# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATASET_ROOT = (
    PROJECT_ROOT
    / "datasets"
    / "processed"
    / "birmingham"
)

TARGET_NAME = "target_occupancy_rate_30m"

TRAIN_FILE = (
    DATASET_ROOT
    / TARGET_NAME
    / "train.parquet"
)

VALIDATION_FILE = (
    DATASET_ROOT
    / TARGET_NAME
    / "validation.parquet"
)


EXPECTED_FEATURE_COUNT = 296

CATEGORICAL_FEATURES = (
    "occupancy_level",
    "demand_class",
)


# ---------------------------------------------------------------------------
# DISPLAY HELPERS
# ---------------------------------------------------------------------------


def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def section(title: str) -> None:
    print()
    print(f"--- {title} ---")


# ---------------------------------------------------------------------------
# DATASET LOADING
# ---------------------------------------------------------------------------


def load_dataset(
    path: Path,
) -> pd.DataFrame:

    if not path.exists():
        raise FileNotFoundError(
            f"Dataset file does not exist: {path}"
        )

    return pd.read_parquet(path)


# ---------------------------------------------------------------------------
# FEATURE / TARGET SEPARATION
# ---------------------------------------------------------------------------


def separate_features_and_target(
    dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.Series]:

    if TARGET_NAME not in dataframe.columns:
        raise ValueError(
            f"Target column '{TARGET_NAME}' "
            "was not found."
        )

    feature_columns = [
        column
        for column in dataframe.columns
        if column != TARGET_NAME
    ]

    features = dataframe[
        feature_columns
    ].copy()

    target = dataframe[
        TARGET_NAME
    ].copy()

    return features, target


# ---------------------------------------------------------------------------
# DATAFRAME DIAGNOSTIC
# ---------------------------------------------------------------------------


def inspect_dataframe(
    name: str,
    dataframe: pd.DataFrame,
) -> None:

    section(f"{name} DATAFRAME")

    print(
        f"Rows                    : {len(dataframe):,}"
    )

    print(
        f"Columns                 : {len(dataframe.columns):,}"
    )

    numeric_columns = [
        column
        for column in dataframe.columns
        if pd.api.types.is_numeric_dtype(
            dataframe[column]
        )
    ]

    non_numeric_columns = [
        column
        for column in dataframe.columns
        if column not in numeric_columns
    ]

    print(
        f"Numeric columns         : "
        f"{len(numeric_columns):,}"
    )

    print(
        f"Non-numeric columns     : "
        f"{len(non_numeric_columns):,}"
    )

    if non_numeric_columns:
        print()
        print("Non-numeric columns:")

        for column in non_numeric_columns:
            print(
                f"  - {column}: "
                f"{dataframe[column].dtype}"
            )

    if numeric_columns:

        numeric_values = dataframe[
            numeric_columns
        ].to_numpy(
            dtype=float
        )

        nan_count = int(
            np.isnan(
                numeric_values
            ).sum()
        )

        pos_inf_count = int(
            np.isposinf(
                numeric_values
            ).sum()
        )

        neg_inf_count = int(
            np.isneginf(
                numeric_values
            ).sum()
        )

        print()
        print(
            f"Numeric NaN cells       : "
            f"{nan_count:,}"
        )

        print(
            f"Positive infinity      : "
            f"{pos_inf_count:,}"
        )

        print(
            f"Negative infinity      : "
            f"{neg_inf_count:,}"
        )

        infinite_mask = (
            np.isinf(
                numeric_values
            )
        )

        if infinite_mask.any():

            print()
            print(
                "OFFENDING FEATURES:"
            )

            positions = np.argwhere(
                infinite_mask
            )

            offending_columns = {}

            for row_position, column_position in positions:

                column = str(
                    dataframe.columns[
                        int(column_position)
                    ]
                )

                if column not in offending_columns:
                    offending_columns[column] = {
                        "positive": 0,
                        "negative": 0,
                    }

                value = numeric_values[
                    int(row_position),
                    int(column_position),
                ]

                if np.isposinf(value):
                    offending_columns[
                        column
                    ]["positive"] += 1

                elif np.isneginf(value):
                    offending_columns[
                        column
                    ]["negative"] += 1

            for column, counts in (
                offending_columns.items()
            ):

                print(
                    f"  {column}"
                    f" | +inf={counts['positive']:,}"
                    f" | -inf={counts['negative']:,}"
                )


# ---------------------------------------------------------------------------
# MODEL-MATRIX DIAGNOSTIC
# ---------------------------------------------------------------------------


def inspect_model_matrix(
    model: XGBoostModel,
    name: str,
    features: pd.DataFrame,
) -> None:

    section(
        f"{name} MODEL MATRIX DIAGNOSTIC"
    )

    print(
        "Calling XGBoostModel._validate_dataframe()..."
    )

    dataframe = model._validate_dataframe(
        features
    )

    print(
        "PASS"
    )

    print(
        "Calling XGBoostModel._validate_feature_schema()..."
    )

    dataframe = (
        model._validate_feature_schema(
            dataframe
        )
    )

    print(
        "PASS"
    )

    print(
        "Calling XGBoostModel._validate_numeric_features()..."
    )

    model._validate_numeric_features(
        dataframe
    )

    print(
        "PASS"
    )

    print()
    print(
        "Raw feature matrix before "
        "categorical encoding:"
    )

    inspect_dataframe(
        "RAW FEATURES",
        dataframe,
    )

    print()
    print(
        "Fitting categorical mappings "
        "using supplied dataset..."
    )

    model._fit_categorical_mappings(
        dataframe
    )

    print(
        "PASS"
    )

    print()
    print(
        "Encoding categorical features..."
    )

    encoded = (
        model._encode_categorical_features(
            dataframe
        )
    )

    print(
        "PASS"
    )

    inspect_dataframe(
        "AFTER CATEGORICAL ENCODING",
        encoded,
    )

    print()
    print(
        "Running final model-matrix "
        "numeric validation manually..."
    )

    numeric_columns = [
        column
        for column in encoded.columns
        if pd.api.types.is_numeric_dtype(
            encoded[column]
        )
    ]

    non_numeric_columns = [
        column
        for column in encoded.columns
        if column not in numeric_columns
    ]

    print(
        f"Numeric columns         : "
        f"{len(numeric_columns):,}"
    )

    print(
        f"Non-numeric columns     : "
        f"{len(non_numeric_columns):,}"
    )

    if non_numeric_columns:

        print()
        print(
            "NON-NUMERIC COLUMNS REMAIN:"
        )

        for column in non_numeric_columns:
            print(
                f"  - {column}"
            )

        raise RuntimeError(
            "Non-numeric columns remain "
            "after categorical encoding."
        )

    numeric_values = encoded[
        numeric_columns
    ].to_numpy(
        dtype=float
    )

    infinite_mask = np.isinf(
        numeric_values
    )

    print(
        f"Positive infinity      : "
        f"{int(np.isposinf(numeric_values).sum()):,}"
    )

    print(
        f"Negative infinity      : "
        f"{int(np.isneginf(numeric_values).sum()):,}"
    )

    print(
        f"NaN cells              : "
        f"{int(np.isnan(numeric_values).sum()):,}"
    )

    if infinite_mask.any():

        print()
        print(
            "!!! INFINITY DETECTED "
            "IN MODEL MATRIX !!!"
        )

        positions = np.argwhere(
            infinite_mask
        )

        offending = {}

        for row_position, column_position in positions:

            column = str(
                encoded.columns[
                    int(column_position)
                ]
            )

            if column not in offending:
                offending[column] = []

            value = numeric_values[
                int(row_position),
                int(column_position),
            ]

            offending[column].append(
                (
                    int(row_position),
                    float(value),
                )
            )

        print()

        for column, entries in offending.items():

            print(
                f"Feature: {column}"
            )

            print(
                f"Occurrences: {len(entries):,}"
            )

            for row_index, value in entries[:10]:

                print(
                    f"  row={row_index:,}"
                    f" value={value}"
                )

            if len(entries) > 10:
                print(
                    f"  ... "
                    f"{len(entries) - 10:,} "
                    "additional occurrences"
                )

        raise RuntimeError(
            f"Model matrix contains "
            f"infinite values in "
            f"{len(offending)} feature(s)."
        )

    print()
    print(
        "MODEL MATRIX FINITE-VALUE CHECK: PASS"
    )

    print()
    print(
        "Calling XGBoostModel._prepare_model_matrix()..."
    )

    prepared = (
        model._prepare_model_matrix(
            features
        )
    )

    print(
        "PASS"
    )

    inspect_dataframe(
        "FINAL PREPARED MATRIX",
        prepared,
    )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------


def main() -> int:

    banner(
        "SMARTPARK AI - BIRMINGHAM "
        "XGBOOST MODEL-MATRIX DIAGNOSTIC"
    )

    print()
    print(
        "IMPORTANT:"
    )

    print(
        "This diagnostic does NOT train XGBoost."
    )

    print(
        "This diagnostic does NOT modify persisted datasets."
    )

    print(
        "This diagnostic does NOT load the test dataset."
    )

    print(
        "This diagnostic reproduces the model's "
        "matrix-preparation path."
    )

    print()
    print(
        f"Training file:"
    )

    print(
        f"  {TRAIN_FILE}"
    )

    print()
    print(
        f"Validation file:"
    )

    print(
        f"  {VALIDATION_FILE}"
    )

    # ------------------------------------------------------------------
    # LOAD
    # ------------------------------------------------------------------

    section(
        "LOADING PERSISTED DATASETS"
    )

    train = load_dataset(
        TRAIN_FILE
    )

    validation = load_dataset(
        VALIDATION_FILE
    )

    print(
        f"Training rows             : "
        f"{len(train):,}"
    )

    print(
        f"Validation rows           : "
        f"{len(validation):,}"
    )

    # ------------------------------------------------------------------
    # SEPARATE
    # ------------------------------------------------------------------

    train_features, train_target = (
        separate_features_and_target(
            train
        )
    )

    validation_features, validation_target = (
        separate_features_and_target(
            validation
        )
    )

    # ------------------------------------------------------------------
    # BASIC INSPECTION
    # ------------------------------------------------------------------

    inspect_dataframe(
        "TRAINING FEATURES",
        train_features,
    )

    inspect_dataframe(
        "VALIDATION FEATURES",
        validation_features,
    )

    # ------------------------------------------------------------------
    # CONFIG
    # ------------------------------------------------------------------

    section(
        "BUILDING XGBOOST MODEL CONFIGURATION"
    )

    config = XGBoostModelConfig(
        categorical_features=(
            CATEGORICAL_FEATURES
        )
    )

    print(
        "Categorical features:"
    )

    for column in CATEGORICAL_FEATURES:
        print(
            f"  - {column}"
        )

    # ------------------------------------------------------------------
    # TRAINING-MATRIX PATH
    # ------------------------------------------------------------------

    model = XGBoostModel(
        config=config
    )

    inspect_model_matrix(
        model,
        "TRAINING",
        train_features,
    )

    # ------------------------------------------------------------------
    # VALIDATION-MATRIX PATH
    # ------------------------------------------------------------------

    section(
        "VALIDATION MODEL-MATRIX PATH"
    )

    validation_model = XGBoostModel(
        config=config
    )

    # Fit categorical mappings on TRAINING
    # ONLY, exactly as the real model does.
    validation_model._fit_categorical_mappings(
        train_features
    )

    print(
        "Categorical mappings fitted "
        "from TRAINING data only."
    )

    prepared_validation = (
        validation_model._prepare_model_matrix(
            validation_features
        )
    )

    inspect_dataframe(
        "VALIDATION PREPARED MATRIX",
        prepared_validation,
    )

    # ------------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------------

    banner(
        "BIRMINGHAM XGBOOST "
        "MODEL-MATRIX DIAGNOSTIC COMPLETED"
    )

    print()
    print(
        "Persisted training data:     CLEAN"
    )

    print(
        "Persisted validation data:   CLEAN"
    )

    print(
        "Categorical encoding:        COMPLETED"
    )

    print(
        "Training model matrix:       FINITE"
    )

    print(
        "Validation model matrix:     FINITE"
    )

    print()
    print(
        "The XGBoost model matrix is "
        "ready for further investigation."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )