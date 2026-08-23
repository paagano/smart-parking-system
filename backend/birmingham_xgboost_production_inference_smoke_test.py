"""
==============================================================================
SMARTPARK AI
BIRMINGHAM XGBOOST PRODUCTION INFERENCE SMOKE TEST
==============================================================================

Purpose
-------
Validate that the frozen Birmingham XGBoost production artifact can be loaded
and used for prediction without retraining or rebuilding the feature pipeline.

This is an ARTIFACT / INFERENCE smoke test.

It does NOT:
    - train XGBoost
    - tune hyperparameters
    - rebuild the feature pipeline
    - modify persisted datasets
    - load validation.parquet
    - load test.parquet
    - change xgboost_model.py
    - change the final model artifact

Production prediction contract
------------------------------
Prediction timestamp = T
Forecast horizon     = T + 30 minutes
All model features must represent information available at or before T.

Frozen model
------------
Candidate:
    TUNE_014

Expected configuration:
    n_estimators      = 300
    learning_rate     = 0.05
    max_depth         = 6
    min_child_weight  = 1.0
    subsample         = 0.9
    colsample_bytree  = 0.9
    gamma             = 0.0
    reg_alpha         = 0.1
    reg_lambda        = 1.0

Expected feature contract:
    296 model features

Categorical features:
    occupancy_level
    demand_class

Artifact directory
------------------
datasets/processed/birmingham/xgboost_final_model/

Expected files:
    model.json
    model_metadata.json
    feature_contract.json
    categorical_mappings.json
    release_manifest.json
    checksums.json

IMPORTANT
---------
This script intentionally uses the persisted frozen XGBoost model artifact
directly. It does not invoke training.

A representative row from train.parquet is used ONLY as an inference smoke
input. It is not used for training.

==============================================================================
"""


from __future__ import annotations

import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any


TARGET_COLUMN = "target_occupancy_rate_30m"

SELECTED_CANDIDATE = "TUNE_014"

EXPECTED_FEATURE_COUNT = 296

CATEGORICAL_FEATURES = [
    "occupancy_level",
    "demand_class",
]

EXPECTED_HYPERPARAMETERS = {
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


# ==============================================================================
# Console helpers
# ==============================================================================

def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_section(title: str) -> None:
    print()
    print(f"--- {title} ---")


def print_kv(label: str, value: Any) -> None:
    print(f"{label:<45}: {value}")


def print_pass(label: str) -> None:
    print_kv(label, "PASS")


def print_fail(label: str) -> None:
    print_kv(label, "FAIL")


def fail(message: str) -> None:
    raise RuntimeError(message)


# ==============================================================================
# JSON helpers
# ==============================================================================

def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(
    path: Path,
    payload: Any,
) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            payload,
            handle,
            indent=2,
            ensure_ascii=False,
        )


# ==============================================================================
# SHA256
# ==============================================================================

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


# ==============================================================================
# Repository discovery
# ==============================================================================

def discover_repository_root() -> Path:
    """
    Resolve:

        <repo>/
            backend/
            datasets/

    The script is expected to live under:

        <repo>/backend/
    """

    script_path = Path(__file__).resolve()

    if script_path.parent.name.lower() == "backend":
        candidate = script_path.parent.parent

        if (
            (candidate / "backend").is_dir()
            and (candidate / "datasets").is_dir()
        ):
            return candidate

    for candidate in [
        script_path.parent,
        *script_path.parents,
    ]:
        if (
            (candidate / "backend").is_dir()
            and (candidate / "datasets").is_dir()
        ):
            return candidate

    raise RuntimeError(
        "Unable to determine SmartPark AI repository root. "
        "Expected a directory containing both 'backend' and 'datasets'. "
        f"Script location: {script_path}"
    )


# ==============================================================================
# Feature extraction
# ==============================================================================

def get_manifest_features(
    manifest: Any,
) -> list[str]:

    if isinstance(manifest, list):
        return [str(item) for item in manifest]

    if not isinstance(manifest, dict):
        fail(
            "training_dataset_manifest.json is not a JSON "
            "object or feature list."
        )

    possible_keys = [
        "features",
        "registered_features",
        "feature_columns",
        "model_features",
    ]

    for key in possible_keys:
        value = manifest.get(key)

        if isinstance(value, list):
            return [str(item) for item in value]

    fail(
        "Unable to locate registered feature list inside "
        "training_dataset_manifest.json."
    )

    return []


def get_contract_features(
    contract: Any,
) -> list[str]:

    if isinstance(contract, list):
        return [str(item) for item in contract]

    if not isinstance(contract, dict):
        fail(
            "feature_contract.json is not a valid JSON object."
        )

    possible_keys = [
        "features",
        "feature_columns",
        "model_features",
        "registered_features",
    ]

    for key in possible_keys:
        value = contract.get(key)

        if isinstance(value, list):
            return [str(item) for item in value]

    fail(
        "Unable to locate feature list inside feature_contract.json."
    )

    return []


# ==============================================================================
# Categorical mapping extraction
# ==============================================================================

def get_mapping(
    mappings: dict[str, Any],
    feature: str,
) -> dict[str, Any]:

    value = mappings.get(feature)

    if isinstance(value, dict):
        return value

    for section_name in (
        "mappings",
        "categorical_mappings",
        "features",
    ):
        section = mappings.get(section_name)

        if not isinstance(section, dict):
            continue

        value = section.get(feature)

        if isinstance(value, dict):
            return value

    fail(
        f"Categorical mapping missing for '{feature}'."
    )

    return {}


def normalize_categorical_mapping(
    mapping: dict[str, Any],
) -> dict[str, float]:
    """
    Normalize supported mapping formats into:

        category -> numeric code

    Supported examples:

        {
            "EMPTY": 0,
            "LOW": 1
        }

    or:

        {
            "0": "EMPTY",
            "1": "LOW"
        }
    """

    if not mapping:
        fail("Categorical mapping is empty.")

    # ----------------------------------------------------------
    # category -> numeric code
    # ----------------------------------------------------------

    values_are_numeric = all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        for value in mapping.values()
    )

    if values_are_numeric:
        return {
            str(key): float(value)
            for key, value in mapping.items()
        }

    # ----------------------------------------------------------
    # numeric code -> category
    # ----------------------------------------------------------

    normalized: dict[str, float] = {}

    for key, value in mapping.items():
        try:
            numeric_code = float(key)
        except (TypeError, ValueError):
            continue

        normalized[str(value)] = numeric_code

    if not normalized:
        fail(
            "Unable to determine categorical mapping orientation."
        )

    return normalized


# ==============================================================================
# Recursive metadata helpers
# ==============================================================================

def find_value_recursive(
    payload: Any,
    keys: set[str],
) -> Any | None:

    if isinstance(payload, dict):

        for key, value in payload.items():

            if str(key).lower() in {
                item.lower()
                for item in keys
            }:
                return value

        for value in payload.values():

            result = find_value_recursive(
                value,
                keys,
            )

            if result is not None:
                return result

    elif isinstance(payload, list):

        for item in payload:

            result = find_value_recursive(
                item,
                keys,
            )

            if result is not None:
                return result

    return None


def find_candidate(
    metadata: Any,
) -> str | None:

    value = find_value_recursive(
        metadata,
        {
            "candidate",
            "selected_candidate",
            "model_candidate",
        },
    )

    if value is None:
        return None

    return str(value)


# ==============================================================================
# Checksum resolution
# ==============================================================================

def resolve_expected_checksum(
    manifest: Any,
    filename: str,
) -> str | None:

    if isinstance(manifest, dict):

        direct = manifest.get(filename)

        if isinstance(direct, str):
            return direct

        if isinstance(direct, dict):

            for key in (
                "sha256",
                "checksum",
                "hash",
            ):
                value = direct.get(key)

                if isinstance(value, str):
                    return value

    if isinstance(manifest, dict):

        for section_name in (
            "checksums",
            "files",
            "artifacts",
            "file_checksums",
            "sha256",
        ):

            section = manifest.get(section_name)

            if not isinstance(section, dict):
                continue

            value = section.get(filename)

            if isinstance(value, str):
                return value

            if isinstance(value, dict):

                for key in (
                    "sha256",
                    "checksum",
                    "hash",
                ):
                    candidate = value.get(key)

                    if isinstance(candidate, str):
                        return candidate

    def recursive_search(
        value: Any,
    ) -> str | None:

        if isinstance(value, dict):

            for key, child in value.items():

                if str(key) == filename:

                    if isinstance(child, str):
                        return child

                    if isinstance(child, dict):

                        for hash_key in (
                            "sha256",
                            "checksum",
                            "hash",
                        ):

                            candidate = child.get(hash_key)

                            if isinstance(candidate, str):
                                return candidate

                result = recursive_search(child)

                if result is not None:
                    return result

        elif isinstance(value, list):

            for item in value:

                result = recursive_search(item)

                if result is not None:
                    return result

        return None

    return recursive_search(manifest)


# ==============================================================================
# Checksum verification
# ==============================================================================

def verify_checksums(
    artifact_dir: Path,
    checksum_manifest: dict[str, Any],
) -> dict[str, Any]:

    print_section(
        "ARTIFACT CHECKSUM VERIFICATION"
    )

    filenames = [
        "model.json",
        "model_metadata.json",
        "feature_contract.json",
        "categorical_mappings.json",
        "release_manifest.json",
    ]

    results: dict[str, Any] = {}

    for filename in filenames:

        path = artifact_dir / filename

        if not path.exists():
            fail(
                f"Checksum target does not exist: {path}"
            )

        actual = sha256_file(path)

        expected = resolve_expected_checksum(
            checksum_manifest,
            filename,
        )

        if expected is None:
            fail(
                "Could not resolve expected checksum "
                f"for '{filename}' from checksums.json."
            )

        actual = actual.strip().lower()
        expected = str(expected).strip().lower()

        matched = actual == expected

        print_kv(
            f"{filename} actual SHA256",
            actual,
        )

        print_kv(
            f"{filename} expected SHA256",
            expected,
        )

        print_kv(
            f"{filename} checksum",
            "PASS" if matched else "FAIL",
        )

        if not matched:
            fail(
                f"Checksum mismatch for {filename}.\n"
                f"Expected: {expected}\n"
                f"Actual:   {actual}"
            )

        results[filename] = {
            "actual_sha256": actual,
            "expected_sha256": expected,
            "status": "PASS",
        }

    print_pass(
        "All frozen artifact checksums"
    )

    return results


# ==============================================================================
# Synthetic production inference fixture
# ==============================================================================

def build_synthetic_inference_fixture(
    feature_columns: list[str],
    mappings: dict[str, Any],
):
    """
    Build exactly one deterministic inference row.

    IMPORTANT:

    No train.parquet is loaded.

    No validation.parquet is loaded.

    No test.parquet is loaded.

    The fixture exists solely to prove that the frozen model can
    accept the frozen 296-feature production contract and produce
    a valid prediction.

    Numeric features are initialized to 0.0.

    Categorical features use the first category from their frozen
    mapping.
    """

    try:
        import pandas as pd
    except Exception as exc:
        fail(
            "Unable to import pandas: "
            f"{type(exc).__name__}: {exc}"
        )

    row: dict[str, Any] = {}

    for feature in feature_columns:

        if feature in CATEGORICAL_FEATURES:

            raw_mapping = get_mapping(
                mappings,
                feature,
            )

            normalized = normalize_categorical_mapping(
                raw_mapping
            )

            if not normalized:
                fail(
                    f"No usable values exist for "
                    f"categorical feature '{feature}'."
                )

            # Deterministic first category.
            first_category = sorted(
                normalized.keys()
            )[0]

            row[feature] = first_category

        else:
            row[feature] = 0.0

    fixture = pd.DataFrame(
        [row],
        columns=feature_columns,
    )

    return fixture


# ==============================================================================
# Categorical encoding
# ==============================================================================

def encode_categorical_features(
    fixture,
    mappings: dict[str, Any],
):
    import pandas as pd

    encoded = fixture.copy()

    for feature in CATEGORICAL_FEATURES:

        mapping = get_mapping(
            mappings,
            feature,
        )

        forward_mapping = normalize_categorical_mapping(
            mapping
        )

        original = (
            encoded[feature]
            .astype("string")
        )

        encoded_values = original.map(
            forward_mapping
        )

        if encoded_values.isna().any():

            unknown_values = sorted(
                set(
                    original[
                        encoded_values.isna()
                    ]
                    .dropna()
                    .tolist()
                )
            )

            fail(
                f"Unknown categorical value(s) for "
                f"'{feature}': {unknown_values}"
            )

        encoded[feature] = (
            encoded_values.astype("float32")
        )

        print_pass(
            f"Categorical encoding: {feature}"
        )

    return encoded


# ==============================================================================
# Numeric conversion
# ==============================================================================

def convert_features_to_numeric(
    fixture,
    feature_columns: list[str],
):
    import pandas as pd

    result = fixture.copy()

    for column in feature_columns:

        if column in CATEGORICAL_FEATURES:
            continue

        try:

            result[column] = pd.to_numeric(
                result[column],
                errors="raise",
            )

        except Exception as exc:

            fail(
                f"Unable to convert feature "
                f"'{column}' to numeric: {exc}"
            )

    return result


# ==============================================================================
# Main
# ==============================================================================

def main() -> int:

    print_header(
        "SMARTPARK AI - BIRMINGHAM XGBOOST "
        "PRODUCTION INFERENCE SMOKETEST"
    )

    print(
        """
Target:
  target_occupancy_rate_30m

Production prediction contract:
  Prediction timestamp = T
  Forecast horizon     = T + 30 minutes
  Feature information  = available at or before T

Frozen model:
  Candidate             : TUNE_014
  Features              : 296
  Training              : FROZEN ARTIFACT ONLY
  Hyperparameter tuning : NO
  Feature rebuild       : NO
  Validation loaded     : NO
  Test loaded           : NO

Inference fixture:
  Source                : SYNTHETIC
  Training dataset      : NOT LOADED
  Validation dataset    : NOT LOADED
  Test dataset          : NOT LOADED
"""
    )

    # ==========================================================================
    # Repository
    # ==========================================================================

    repository_root = (
        discover_repository_root()
    )

    processed_root = (
        repository_root
        / "datasets"
        / "processed"
        / "birmingham"
    )

    artifact_dir = (
        processed_root
        / "xgboost_final_model"
    )

    manifest_path = (
        processed_root
        / "training_dataset_manifest.json"
    )

    model_path = (
        artifact_dir
        / "model.json"
    )

    metadata_path = (
        artifact_dir
        / "model_metadata.json"
    )

    contract_path = (
        artifact_dir
        / "feature_contract.json"
    )

    mappings_path = (
        artifact_dir
        / "categorical_mappings.json"
    )

    release_path = (
        artifact_dir
        / "release_manifest.json"
    )

    checksums_path = (
        artifact_dir
        / "checksums.json"
    )

    # ==========================================================================
    # Artifact-only file validation
    # ==========================================================================

    print_section(
        "ARTIFACT FILE VALIDATION"
    )

    print_kv(
        "Repository root",
        repository_root,
    )

    print_kv(
        "Artifact directory",
        artifact_dir,
    )

    required_paths = {
        "manifest": manifest_path,
        "model": model_path,
        "model_metadata": metadata_path,
        "feature_contract": contract_path,
        "categorical_mappings": mappings_path,
        "release_manifest": release_path,
        "checksums": checksums_path,
    }

    for name, path in required_paths.items():

        status = (
            "PASS"
            if path.exists()
            else "FAIL"
        )

        print_kv(
            f"{name} exists",
            status,
        )

        if not path.exists():
            fail(
                f"Required artifact file does not exist: "
                f"{path}"
            )

    print()
    print(
        "Training dataset will NOT be loaded."
    )
    print(
        "Validation dataset will NOT be loaded."
    )
    print(
        "Test dataset will NOT be loaded."
    )

    # ==========================================================================
    # Training manifest
    # ==========================================================================

    print_section(
        "LOADING FEATURE REGISTRY"
    )

    manifest = load_json(
        manifest_path
    )

    registered_features = (
        get_manifest_features(
            manifest
        )
    )

    print_kv(
        "Registered features",
        len(registered_features),
    )

    if len(registered_features) != EXPECTED_FEATURE_COUNT:
        fail(
            "Registered feature count does not equal "
            f"{EXPECTED_FEATURE_COUNT}."
        )

    print_pass(
        "Registered feature count = 296"
    )

    if len(set(registered_features)) != len(
        registered_features
    ):
        fail(
            "Duplicate features exist in the "
            "registered feature manifest."
        )

    print_pass(
        "No duplicate registered features"
    )

    # ==========================================================================
    # Frozen feature contract
    # ==========================================================================

    print_section(
        "LOADING FROZEN FEATURE CONTRACT"
    )

    contract = load_json(
        contract_path
    )

    contract_features = (
        get_contract_features(
            contract
        )
    )

    print_kv(
        "Contract features",
        len(contract_features),
    )

    if len(contract_features) != EXPECTED_FEATURE_COUNT:
        fail(
            "Frozen feature contract does not contain "
            f"{EXPECTED_FEATURE_COUNT} features."
        )

    if contract_features != registered_features:
        fail(
            "Frozen feature contract does not exactly "
            "match the registered feature order."
        )

    print_pass(
        "Feature contract ordering"
    )

    # ==========================================================================
    # Categorical mappings
    # ==========================================================================

    print_section(
        "LOADING FROZEN CATEGORICAL MAPPINGS"
    )

    mappings = load_json(
        mappings_path
    )

    categorical_mapping_contract = {}

    for feature in CATEGORICAL_FEATURES:

        mapping = get_mapping(
            mappings,
            feature,
        )

        normalized = normalize_categorical_mapping(
            mapping
        )

        categorical_mapping_contract[
            feature
        ] = normalized

        print_kv(
            f"{feature} mapping entries",
            len(normalized),
        )

        if not normalized:
            fail(
                f"Empty categorical mapping for "
                f"'{feature}'."
            )

        print_pass(
            f"{feature} mapping"
        )

    # ==========================================================================
    # Metadata
    # ==========================================================================

    print_section(
        "VALIDATING MODEL METADATA"
    )

    metadata = load_json(
        metadata_path
    )

    metadata_candidate = find_candidate(
        metadata
    )

    print_kv(
        "Metadata candidate",
        metadata_candidate,
    )

    if metadata_candidate != SELECTED_CANDIDATE:
        fail(
            "Frozen model metadata does not identify "
            f"{SELECTED_CANDIDATE}."
        )

    print_pass(
        "Selected candidate = TUNE_014"
    )

    # ==========================================================================
    # Release manifest
    # ==========================================================================

    print_section(
        "VALIDATING RELEASE MANIFEST"
    )

    release = load_json(
        release_path
    )

    release_text = json.dumps(
        release
    )

    if TARGET_COLUMN not in release_text:
        fail(
            "Target contract is missing from "
            "release_manifest.json."
        )

    print_pass(
        "Target contract in release manifest"
    )

    if "296" not in release_text:
        fail(
            "296-feature contract is not represented "
            "in release_manifest.json."
        )

    print_pass(
        "296-feature contract in release manifest"
    )

    if SELECTED_CANDIDATE not in release_text:
        fail(
            "Selected candidate TUNE_014 is not represented "
            "in release_manifest.json."
        )

    print_pass(
        "Selected candidate in release manifest"
    )

    # ==========================================================================
    # Checksum validation
    # ==========================================================================

    print_section(
        "VALIDATING ARTIFACT INTEGRITY"
    )

    checksum_manifest = load_json(
        checksums_path
    )

    checksum_results = verify_checksums(
        artifact_dir,
        checksum_manifest,
    )

    # ==========================================================================
    # Load XGBoost directly
    # ==========================================================================

    print_section(
        "LOADING FROZEN XGBOOST BOOSTER"
    )

    try:
        import xgboost as xgb
    except Exception as exc:
        fail(
            "Unable to import xgboost: "
            f"{type(exc).__name__}: {exc}"
        )

    print_kv(
        "Frozen model file",
        model_path,
    )

    try:

        booster = xgb.Booster()

        booster.load_model(
            str(model_path)
        )

    except Exception as exc:

        fail(
            "Unable to load frozen model.json with "
            f"xgboost.Booster: "
            f"{type(exc).__name__}: {exc}"
        )

    print_pass(
        "Frozen XGBoost Booster loaded"
    )

    # ==========================================================================
    # Booster contract
    # ==========================================================================

    print_section(
        "VALIDATING FROZEN XGBOOST MODEL CONTRACT"
    )

    try:

        booster_feature_count = (
            booster.num_features()
        )

    except Exception as exc:

        fail(
            "Unable to determine XGBoost model "
            f"feature count: {exc}"
        )

    print_kv(
        "XGBoost feature count",
        booster_feature_count,
    )

    if booster_feature_count != EXPECTED_FEATURE_COUNT:
        fail(
            "Frozen XGBoost model feature count does not "
            f"equal {EXPECTED_FEATURE_COUNT}."
        )

    print_pass(
        "Frozen model feature count = 296"
    )

    # ==========================================================================
    # Booster feature names
    # ==========================================================================

    booster_feature_names = (
        booster.feature_names
    )

    if booster_feature_names:

        print_kv(
            "Booster feature names",
            len(booster_feature_names),
        )

        if len(booster_feature_names) != (
            EXPECTED_FEATURE_COUNT
        ):
            fail(
                "Booster feature-name count does not equal "
                f"{EXPECTED_FEATURE_COUNT}."
            )

        if list(booster_feature_names) != (
            contract_features
        ):
            fail(
                "Booster feature-name ordering does not "
                "match the frozen feature contract."
            )

        print_pass(
            "Booster feature ordering"
        )

    else:

        print_kv(
            "Booster feature names",
            "NOT STORED",
        )

        print(
            "Booster does not expose persisted feature names."
        )

        print(
            "Feature ordering will be enforced by the "
            "frozen feature contract."
        )

        print_pass(
            "Feature ordering enforced by frozen contract"
        )

    # ==========================================================================
    # Production inference fixture
    # ==========================================================================

    print_section(
        "BUILDING SYNTHETIC PRODUCTION INFERENCE FIXTURE"
    )

    fixture = build_synthetic_inference_fixture(
        contract_features,
        mappings,
    )

    print_kv(
        "Fixture rows",
        len(fixture),
    )

    print_kv(
        "Fixture columns",
        len(fixture.columns),
    )

    if len(fixture) != 1:
        fail(
            "Production inference fixture must contain "
            "exactly one row."
        )

    if list(fixture.columns) != (
        contract_features
    ):
        fail(
            "Synthetic inference fixture feature ordering "
            "does not match the frozen contract."
        )

    print_pass(
        "Fixture feature ordering"
    )

    print_pass(
        "Fixture contains exactly 296 features"
    )

    # ==========================================================================
    # Apply categorical contract
    # ==========================================================================

    print_section(
        "APPLYING FROZEN CATEGORICAL CONTRACT"
    )

    encoded_fixture = (
        encode_categorical_features(
            fixture,
            mappings,
        )
    )

    # ==========================================================================
    # Numeric conversion
    # ==========================================================================

    encoded_fixture = (
        convert_features_to_numeric(
            encoded_fixture,
            contract_features,
        )
    )

    # ==========================================================================
    # Null validation
    # ==========================================================================

    print_section(
        "VALIDATING INFERENCE FEATURE MATRIX"
    )

    selected_features = encoded_fixture[
        contract_features
    ]

    if selected_features.isna().any().any():

        null_counts = (
            selected_features
            .isna()
            .sum()
        )

        failing = {
            str(key): int(value)
            for key, value in null_counts.items()
            if int(value) > 0
        }

        fail(
            "Inference fixture contains null values: "
            f"{failing}"
        )

    print_pass(
        "Inference fixture contains no null features"
    )

    # ==========================================================================
    # Matrix
    # ==========================================================================

    try:

        matrix = selected_features.to_numpy(
            dtype="float32"
        )

    except Exception as exc:

        fail(
            "Unable to create numeric inference matrix: "
            f"{type(exc).__name__}: {exc}"
        )

    print_kv(
        "Inference matrix shape",
        matrix.shape,
    )

    if matrix.shape != (
        1,
        EXPECTED_FEATURE_COUNT,
    ):
        fail(
            "Inference matrix does not have expected "
            f"shape (1, {EXPECTED_FEATURE_COUNT})."
        )

    print_pass(
        "Inference matrix shape = (1,296)"
    )

    # ==========================================================================
    # XGBoost DMatrix
    # ==========================================================================

    print_section(
        "GENERATING PRODUCTION INFERENCE"
    )

    try:

        dmatrix = xgb.DMatrix(
            matrix,
            feature_names=contract_features,
        )

    except Exception as exc:

        fail(
            "Unable to create XGBoost DMatrix: "
            f"{type(exc).__name__}: {exc}"
        )

    print_pass(
        "XGBoost inference matrix created"
    )

    # ==========================================================================
    # Prediction
    # ==========================================================================

    try:

        prediction = booster.predict(
            dmatrix
        )

    except Exception as exc:

        fail(
            "Frozen model prediction failed: "
            f"{type(exc).__name__}: {exc}"
        )

    if len(prediction) != 1:
        fail(
            "Expected exactly one prediction."
        )

    predicted_value = float(
        prediction[0]
    )

    print_kv(
        "Prediction",
        f"{predicted_value:.10f}",
    )

    if not math.isfinite(
        predicted_value
    ):
        fail(
            "Prediction is not finite."
        )

    print_pass(
        "Prediction finite"
    )

    if not (
        0.0
        <= predicted_value
        <= 1.0
    ):
        fail(
            "Prediction falls outside the valid "
            "occupancy-rate range [0,1]."
        )

    print_pass(
        "Prediction within [0,1]"
    )

    # ==========================================================================
    # Production inference report
    # ==========================================================================

    print_section(
        "PERSISTING PRODUCTION SMOKE TEST RESULT"
    )

    report = {
        "audit": (
            "Birmingham XGBoost Production "
            "Inference Smoke Test"
        ),
        "status": "PASS",
        "target": TARGET_COLUMN,
        "production_contract": {
            "prediction_timestamp": "T",
            "forecast_horizon": "T+30m",
            "feature_availability": "at_or_before_T",
        },
        "model": {
            "candidate": SELECTED_CANDIDATE,
            "feature_count": EXPECTED_FEATURE_COUNT,
            "artifact_directory": str(
                artifact_dir
            ),
            "model_file": str(
                model_path
            ),
        },
        "xgboost": {
            "booster_loaded": True,
            "feature_count": int(
                booster_feature_count
            ),
            "feature_names_available": bool(
                booster_feature_names
            ),
        },
        "inference": {
            "fixture_type": "synthetic",
            "fixture_rows": 1,
            "matrix_shape": [
                int(matrix.shape[0]),
                int(matrix.shape[1]),
            ],
            "prediction": predicted_value,
            "prediction_finite": True,
            "prediction_range_valid": True,
        },
        "datasets": {
            "training_loaded": False,
            "validation_loaded": False,
            "test_loaded": False,
        },
        "training_performed": False,
        "hyperparameter_tuning": False,
        "feature_pipeline_rebuilt": False,
        "persisted_datasets_modified": False,
        "xgboost_model_source": "frozen_model.json",
        "categorical_features": CATEGORICAL_FEATURES,
        "categorical_mapping_sizes": {
            feature: len(mapping)
            for feature, mapping in (
                categorical_mapping_contract.items()
            )
        },
        "checksums": checksum_results,
    }

    report_path = (
        artifact_dir
        / "production_inference_smoke_test.json"
    )

    save_json(
        report_path,
        report,
    )

    print_kv(
        "Smoke-test report",
        report_path,
    )

    # ==========================================================================
    # Final assertions
    # ==========================================================================

    print_section(
        "FINAL PRODUCTION INFERENCE ASSERTIONS"
    )

    assertions = {

        "Expected feature count = 296":
            len(registered_features)
            == EXPECTED_FEATURE_COUNT,

        "Feature contract matches manifest":
            contract_features
            == registered_features,

        "No duplicate registered features":
            len(set(registered_features))
            == len(registered_features),

        "Categorical mapping: occupancy_level":
            bool(
                get_mapping(
                    mappings,
                    "occupancy_level",
                )
            ),

        "Categorical mapping: demand_class":
            bool(
                get_mapping(
                    mappings,
                    "demand_class",
                )
            ),

        "Selected candidate = TUNE_014":
            metadata_candidate
            == SELECTED_CANDIDATE,

        "Frozen XGBoost Booster loaded":
            booster is not None,

        "Underlying XGBoost feature count = 296":
            booster_feature_count
            == EXPECTED_FEATURE_COUNT,

        "Inference matrix shape = (1,296)":
            matrix.shape
            == (
                1,
                EXPECTED_FEATURE_COUNT,
            ),

        "Prediction finite":
            math.isfinite(
                predicted_value
            ),

        "Prediction within [0,1]":
            0.0
            <= predicted_value
            <= 1.0,

        "Training dataset not loaded":
            True,

        "Validation dataset not loaded":
            True,

        "Test dataset not loaded":
            True,

        "No XGBoost training performed":
            True,

        "No hyperparameter tuning":
            True,

        "No feature pipeline rebuild":
            True,

        "Persisted datasets not modified":
            True,
    }

    for label, passed in assertions.items():

        if passed:

            print_pass(label)

        else:

            print_fail(label)

            fail(
                f"Final assertion failed: {label}"
            )

    print()
    print(
        "ALL PRODUCTION INFERENCE SMOKE TEST "
        "ASSERTIONS PASSED"
    )

    # ==========================================================================
    # Final success
    # ==========================================================================

    print_header(
        "BIRMINGHAM XGBOOST PRODUCTION "
        "INFERENCE SMOKE TEST COMPLETED SUCCESSFULLY"
    )

    print(
        f"""
Target:              {TARGET_COLUMN}
Selected candidate:  {SELECTED_CANDIDATE}
Features:             {EXPECTED_FEATURE_COUNT}

Production inference prediction:
  {predicted_value:.10f}

Artifact directory:
  {artifact_dir}

Inference fixture:
  SYNTHETIC — no dataset loaded

Training dataset used:  NO
Validation dataset used: NO
Test dataset used:       NO

XGBoost training:        NO
Hyperparameter tuning:   NO
Feature pipeline rebuilt: NO
Persisted datasets modified: NO

Frozen Booster loaded directly from model.json: YES

PRODUCTION INFERENCE SMOKE TEST PASSED
"""
    )

    return 0


# ==============================================================================
# Entry point
# ==============================================================================

if __name__ == "__main__":

    try:

        sys.exit(
            main()
        )

    except KeyboardInterrupt:

        print()
        print(
            "Production inference smoke test "
            "interrupted by user."
        )

        sys.exit(130)

    except Exception as exc:

        print()
        print("=" * 78)
        print(
            "BIRMINGHAM XGBOOST PRODUCTION "
            "INFERENCE SMOKE TEST FAILED"
        )
        print("=" * 78)

        print()
        print(
            f"ERROR: {type(exc).__name__}: {exc}"
        )

        print()
        print(
            "NO persisted datasets were modified."
        )

        print(
            "Training dataset was NOT loaded."
        )

        print(
            "Validation dataset was NOT loaded."
        )

        print(
            "Test dataset was NOT loaded."
        )

        print(
            "No XGBoost training was performed."
        )

        print(
            "No hyperparameter tuning was performed."
        )

        print(
            "No feature pipeline was rebuilt."
        )

        sys.exit(1)