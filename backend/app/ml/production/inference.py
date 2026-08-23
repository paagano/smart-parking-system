"""
SmartPark AI - Production XGBoost Inference
============================================

Production inference layer for the frozen Birmingham XGBoost model.

Architecture
------------

    occupancy_observations
            |
            v
    ProductionFeatureBuilder
            |
            v
       296 features
            |
            v
    ProductionXGBoostInference
            |
            v
       Frozen TUNE_014
            |
            v
    target_occupancy_rate_30m
            |
            v
       Forecast response


IMPORTANT PRODUCTION CONTRACT
-----------------------------

Prediction timestamp:
    T

Forecast horizon:
    T + 30 minutes

Feature availability:
    Every feature supplied to this module must represent information
    available at or before T.

This module:

    - DOES load the frozen XGBoost artifact.
    - DOES perform production inference.
    - DOES apply the frozen feature ordering.
    - DOES apply the frozen categorical mappings.
    - DOES validate the frozen model contract.
    - DOES NOT train XGBoost.
    - DOES NOT tune hyperparameters.
    - DOES NOT load train.parquet.
    - DOES NOT load validation.parquet.
    - DOES NOT load test.parquet.
    - DOES NOT rebuild the feature pipeline.
    - DOES NOT access PostgreSQL directly.
    - DOES NOT modify xgboost_model.py.
    - DOES NOT modify the frozen artifact.

The database/observation layer belongs to:
    app.ml.production.observation_ingestion

Feature construction belongs to:
    app.ml.production.feature_builder

End-to-end orchestration belongs to:
    app.ml.production.service
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

try:
    import xgboost as xgb
except ImportError as exc:
    raise ImportError(
        "XGBoost is required for SmartPark AI production inference. "
        "Install it with: python -m pip install xgboost"
    ) from exc


# ============================================================================
# Production constants
# ============================================================================

TARGET_COLUMN = "target_occupancy_rate_30m"

SELECTED_CANDIDATE = "TUNE_014"

EXPECTED_FEATURE_COUNT = 296

FORECAST_HORIZON_MINUTES = 30

CATEGORICAL_FEATURES: tuple[str, ...] = (
    "occupancy_level",
    "demand_class",
)

UNKNOWN_CATEGORY_CODE = -1

PREDICTION_MIN = 0.0
PREDICTION_MAX = 1.0


# ============================================================================
# Exceptions
# ============================================================================


class ProductionInferenceError(Exception):
    """Base exception for production inference errors."""


class ProductionArtifactError(
    ProductionInferenceError
):
    """Raised when the frozen model artifact is invalid."""


class ProductionFeatureContractError(
    ProductionInferenceError
):
    """Raised when the inference feature contract is invalid."""


class ProductionInferenceDataError(
    ProductionInferenceError
):
    """Raised when inference input data is invalid."""


# ============================================================================
# Result contract
# ============================================================================


@dataclass(frozen=True, slots=True)
class ProductionPrediction:
    """
    Production XGBoost prediction result.

    Attributes
    ----------
    prediction:
        Predicted occupancy rate at T + 30 minutes.

    prediction_timestamp:
        Timestamp at which the prediction is made.

    forecast_timestamp:
        Timestamp represented by the prediction.

    forecast_horizon_minutes:
        Forecast horizon. Fixed at 30 minutes for the current model.

    model_candidate:
        Frozen model candidate, TUNE_014.

    target_column:
        Model target.

    feature_count:
        Number of features supplied to the frozen model.

    """

    prediction: float
    prediction_timestamp: pd.Timestamp
    forecast_timestamp: pd.Timestamp
    forecast_horizon_minutes: int
    model_candidate: str
    target_column: str
    feature_count: int

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe representation."""

        return {
            "prediction": self.prediction,
            "prediction_timestamp": (
                self.prediction_timestamp.isoformat()
            ),
            "forecast_timestamp": (
                self.forecast_timestamp.isoformat()
            ),
            "forecast_horizon_minutes": (
                self.forecast_horizon_minutes
            ),
            "model_candidate": self.model_candidate,
            "target_column": self.target_column,
            "feature_count": self.feature_count,
        }


# ============================================================================
# Utility functions
# ============================================================================


def _load_json(
    path: Path,
) -> Any:
    """Load a JSON file."""

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            return json.load(handle)

    except FileNotFoundError as exc:
        raise ProductionArtifactError(
            f"Required artifact file does not exist: {path}"
        ) from exc

    except json.JSONDecodeError as exc:
        raise ProductionArtifactError(
            f"Invalid JSON artifact: {path}"
        ) from exc


def _sha256_file(
    path: Path,
) -> str:
    """Calculate SHA256 for a file."""

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

            digest.update(chunk)

    return digest.hexdigest()


def _resolve_expected_checksum(
    manifest: Any,
    filename: str,
) -> str | None:
    """
    Resolve an expected checksum from the release checksum manifest.

    Supports the artifact layouts already used by SmartPark AI.
    """

    if not isinstance(
        manifest,
        dict,
    ):
        return None

    # ------------------------------------------------------------
    # Direct mapping
    # ------------------------------------------------------------

    direct = manifest.get(
        filename
    )

    if isinstance(
        direct,
        str,
    ):
        return direct

    if isinstance(
        direct,
        dict,
    ):

        for key in (
            "sha256",
            "checksum",
            "hash",
        ):

            value = direct.get(
                key
            )

            if isinstance(
                value,
                str,
            ):
                return value

    # ------------------------------------------------------------
    # Known container sections
    # ------------------------------------------------------------

    for section_name in (
        "checksums",
        "files",
        "artifacts",
        "file_checksums",
        "sha256",
    ):

        section = manifest.get(
            section_name
        )

        if not isinstance(
            section,
            dict,
        ):
            continue

        value = section.get(
            filename
        )

        if isinstance(
            value,
            str,
        ):
            return value

        if isinstance(
            value,
            dict,
        ):

            for key in (
                "sha256",
                "checksum",
                "hash",
            ):

                candidate = value.get(
                    key
                )

                if isinstance(
                    candidate,
                    str,
                ):
                    return candidate

    # ------------------------------------------------------------
    # Recursive fallback
    # ------------------------------------------------------------

    def recursive_search(
        value: Any,
    ) -> str | None:

        if isinstance(
            value,
            dict,
        ):

            for key, child in value.items():

                if str(key) == filename:

                    if isinstance(
                        child,
                        str,
                    ):
                        return child

                    if isinstance(
                        child,
                        dict,
                    ):

                        for hash_key in (
                            "sha256",
                            "checksum",
                            "hash",
                        ):

                            candidate = child.get(
                                hash_key
                            )

                            if isinstance(
                                candidate,
                                str,
                            ):
                                return candidate

                result = recursive_search(
                    child
                )

                if result is not None:
                    return result

        elif isinstance(
            value,
            list,
        ):

            for child in value:

                result = recursive_search(
                    child
                )

                if result is not None:
                    return result

        return None

    return recursive_search(
        manifest
    )


def _extract_feature_list(
    contract: Any,
) -> list[str]:
    """
    Extract the frozen feature list from feature_contract.json.

    The artifact contract is expected to contain the registered
    296 feature names.
    """

    if isinstance(
        contract,
        list,
    ):

        features = contract

    elif isinstance(
        contract,
        dict,
    ):

        features = None

        for key in (
            "features",
            "feature_columns",
            "registered_features",
            "model_features",
            "columns",
        ):

            candidate = contract.get(
                key
            )

            if isinstance(
                candidate,
                list,
            ):

                features = candidate
                break

        if features is None:
            raise ProductionFeatureContractError(
                "Unable to locate feature list in "
                "feature_contract.json."
            )

    else:

        raise ProductionFeatureContractError(
            "feature_contract.json has an unsupported structure."
        )

    normalized = [
        str(feature)
        for feature in features
    ]

    if not normalized:
        raise ProductionFeatureContractError(
            "Frozen feature contract is empty."
        )

    if len(normalized) != len(
        set(normalized)
    ):
        raise ProductionFeatureContractError(
            "Frozen feature contract contains duplicate names."
        )

    return normalized


def _extract_mapping(
    mappings: Any,
    feature: str,
) -> dict[str, int]:
    """
    Extract a categorical mapping from categorical_mappings.json.

    Supports both:

        {
            "occupancy_level": {
                "LOW": 0,
                ...
            }
        }

    and common wrapped structures.
    """

    if not isinstance(
        mappings,
        dict,
    ):
        raise ProductionArtifactError(
            "categorical_mappings.json must contain an object."
        )

    # ------------------------------------------------------------
    # Direct feature mapping
    # ------------------------------------------------------------

    direct = mappings.get(
        feature
    )

    if isinstance(
        direct,
        dict,
    ):

        return _normalize_mapping(
            direct,
            feature,
        )

    # ------------------------------------------------------------
    # Common wrappers
    # ------------------------------------------------------------

    for section_name in (
        "mappings",
        "categorical_mappings",
        "features",
    ):

        section = mappings.get(
            section_name
        )

        if not isinstance(
            section,
            dict,
        ):
            continue

        candidate = section.get(
            feature
        )

        if isinstance(
            candidate,
            dict,
        ):

            return _normalize_mapping(
                candidate,
                feature,
            )

    # ------------------------------------------------------------
    # Recursive fallback
    # ------------------------------------------------------------

    def recursive_find(
        value: Any,
    ) -> dict[str, int] | None:

        if isinstance(
            value,
            dict,
        ):

            for key, child in value.items():

                if str(key) == feature:

                    if isinstance(
                        child,
                        dict,
                    ):
                        return _normalize_mapping(
                            child,
                            feature,
                        )

                result = recursive_find(
                    child
                )

                if result is not None:
                    return result

        return None

    result = recursive_find(
        mappings
    )

    if result is None:
        raise ProductionArtifactError(
            f"No categorical mapping found for '{feature}'."
        )

    return result


def _normalize_mapping(
    mapping: Mapping[Any, Any],
    feature: str,
) -> dict[str, int]:
    """Normalize categorical mapping keys and integer codes."""

    normalized: dict[str, int] = {}

    for category, code in mapping.items():

        try:
            normalized[
                str(category)
            ] = int(code)

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise ProductionArtifactError(
                f"Invalid categorical code for "
                f"'{feature}': {category!r} -> {code!r}"
            ) from exc

    if not normalized:
        raise ProductionArtifactError(
            f"Categorical mapping for '{feature}' is empty."
        )

    return normalized


def _normalize_timestamp(
    value: Any,
) -> pd.Timestamp:
    """
    Normalize the production prediction timestamp.

    A timezone-aware timestamp is required internally.
    """

    timestamp = pd.Timestamp(
        value
    )

    if pd.isna(timestamp):
        raise ProductionInferenceDataError(
            "Prediction timestamp is invalid."
        )

    if timestamp.tzinfo is None:
        raise ProductionInferenceDataError(
            "Prediction timestamp must be timezone-aware."
        )

    return timestamp


# ============================================================================
# Production inference engine
# ============================================================================


class ProductionXGBoostInference:
    """
    Production inference engine for the frozen Birmingham XGBoost model.

    The class loads the persisted Booster directly rather than attempting
    to reconstruct the training wrapper.

    This is intentional.

    The production artifact contains:

        model.json
        feature_contract.json
        categorical_mappings.json
        model_metadata.json
        release_manifest.json
        checksums.json

    The underlying XGBoost Booster is therefore the authoritative
    prediction object.
    """

    def __init__(
        self,
        *,
        artifact_dir: Path | str | None = None,
        verify_checksums: bool = True,
    ) -> None:

        self.artifact_dir = (
            Path(artifact_dir)
            if artifact_dir is not None
            else self._default_artifact_dir()
        )

        self.verify_checksums = (
            verify_checksums
        )

        self.model_path = (
            self.artifact_dir
            / "model.json"
        )

        self.metadata_path = (
            self.artifact_dir
            / "model_metadata.json"
        )

        self.feature_contract_path = (
            self.artifact_dir
            / "feature_contract.json"
        )

        self.categorical_mappings_path = (
            self.artifact_dir
            / "categorical_mappings.json"
        )

        self.release_manifest_path = (
            self.artifact_dir
            / "release_manifest.json"
        )

        self.checksums_path = (
            self.artifact_dir
            / "checksums.json"
        )

        self._booster: xgb.Booster | None = None

        self._feature_columns: tuple[str, ...] = ()

        self._categorical_mappings: dict[
            str,
            dict[str, int],
        ] = {}

        self._metadata: dict[str, Any] = {}

        self._release_manifest: dict[str, Any] = {}

        self._loaded = False

        self._load_artifact()

    # ========================================================================
    # Repository / artifact paths
    # ========================================================================

    @staticmethod
    def _default_artifact_dir() -> Path:
        """
        Resolve the frozen Birmingham XGBoost production artifact.

        inference.py:
            smart-parking-system/
            └── backend/
                └── app/
                    └── ml/
                        └── production/
                            └── inference.py

        Frozen artifact:
            smart-parking-system/
            └── datasets/
                └── processed/
                    └── birmingham/
                        └── xgboost_final_model/
        """

        project_root = (
            Path(__file__)
            .resolve()
            .parents[4]
        )

        return (
            project_root
            / "datasets"
            / "processed"
            / "birmingham"
            / "xgboost_final_model"
        )

    # ========================================================================
    # Artifact loading
    # ========================================================================

    def _load_artifact(self) -> None:
        """Load and validate the complete frozen artifact."""

        self._validate_artifact_files()

        if self.verify_checksums:
            self._verify_artifact_checksums()

        contract = _load_json(
            self.feature_contract_path
        )

        feature_columns = _extract_feature_list(
            contract
        )

        if len(feature_columns) != (
            EXPECTED_FEATURE_COUNT
        ):
            raise ProductionFeatureContractError(
                "Frozen feature count mismatch: "
                f"expected {EXPECTED_FEATURE_COUNT}, "
                f"found {len(feature_columns)}."
            )

        self._feature_columns = tuple(
            feature_columns
        )

        mappings = _load_json(
            self.categorical_mappings_path
        )

        for feature in CATEGORICAL_FEATURES:

            if feature not in self._feature_columns:
                raise ProductionFeatureContractError(
                    f"Categorical feature '{feature}' "
                    "is missing from the frozen feature contract."
                )

            self._categorical_mappings[
                feature
            ] = _extract_mapping(
                mappings,
                feature,
            )

        self._metadata = _load_json(
            self.metadata_path
        )

        if not isinstance(
            self._metadata,
            dict,
        ):
            raise ProductionArtifactError(
                "model_metadata.json must contain an object."
            )

        self._release_manifest = _load_json(
            self.release_manifest_path
        )

        if not isinstance(
            self._release_manifest,
            dict,
        ):
            raise ProductionArtifactError(
                "release_manifest.json must contain an object."
            )

        self._validate_metadata()

        self._validate_release_manifest()

        # ------------------------------------------------------------
        # Load the underlying XGBoost Booster.
        #
        # IMPORTANT:
        # We intentionally do NOT instantiate XGBoostModel and call
        # predict(), because the wrapper is a training-time abstraction
        # and does not expose a persisted load() contract.
        # ------------------------------------------------------------

        try:

            booster = xgb.Booster()

            booster.load_model(
                str(self.model_path)
            )

        except Exception as exc:

            raise ProductionArtifactError(
                "Unable to load frozen XGBoost Booster "
                f"from '{self.model_path}': "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        self._booster = booster

        self._validate_booster_contract()

        self._loaded = True

    # ========================================================================
    # Artifact validation
    # ========================================================================

    def _validate_artifact_files(self) -> None:
        """Ensure every required production artifact exists."""

        required = (
            self.model_path,
            self.metadata_path,
            self.feature_contract_path,
            self.categorical_mappings_path,
            self.release_manifest_path,
            self.checksums_path,
        )

        missing = [
            str(path)
            for path in required
            if not path.exists()
        ]

        if missing:

            raise ProductionArtifactError(
                "Frozen production artifact is incomplete. "
                "Missing files:\n"
                + "\n".join(
                    f"  - {path}"
                    for path in missing
                )
            )

    def _verify_artifact_checksums(self) -> None:
        """
        Verify SHA256 checksums for the frozen artifact.

        This protects production inference from accidentally using a
        modified/corrupted model artifact.
        """

        manifest = _load_json(
            self.checksums_path
        )

        artifact_files = (
            "model.json",
            "model_metadata.json",
            "feature_contract.json",
            "categorical_mappings.json",
            "release_manifest.json",
        )

        for filename in artifact_files:

            path = (
                self.artifact_dir
                / filename
            )

            expected = (
                _resolve_expected_checksum(
                    manifest,
                    filename,
                )
            )

            if expected is None:
                raise ProductionArtifactError(
                    "No expected SHA256 checksum found for "
                    f"'{filename}'."
                )

            actual = _sha256_file(
                path
            )

            if actual.lower() != expected.lower():

                raise ProductionArtifactError(
                    f"Checksum verification failed for "
                    f"'{filename}'.\n"
                    f"Expected: {expected}\n"
                    f"Actual:   {actual}"
                )

    def _validate_metadata(self) -> None:
        """Validate the frozen model metadata."""

        candidate = (
            self._metadata.get(
                "candidate"
            )
            or self._metadata.get(
                "selected_candidate"
            )
            or self._metadata.get(
                "model_candidate"
            )
        )

        if candidate != SELECTED_CANDIDATE:

            raise ProductionArtifactError(
                "Frozen model candidate mismatch: "
                f"expected {SELECTED_CANDIDATE}, "
                f"found {candidate!r}."
            )

        metadata_feature_count = (
            self._metadata.get(
                "feature_count"
            )
        )

        if (
            metadata_feature_count is not None
            and int(metadata_feature_count)
            != EXPECTED_FEATURE_COUNT
        ):

            raise ProductionArtifactError(
                "Frozen model metadata feature count mismatch: "
                f"expected {EXPECTED_FEATURE_COUNT}, "
                f"found {metadata_feature_count}."
            )

    def _validate_release_manifest(self) -> None:
        """Validate release-manifest contract."""

        release_text = json.dumps(
            self._release_manifest
        )

        if TARGET_COLUMN not in release_text:

            raise ProductionArtifactError(
                "Release manifest does not contain the "
                f"target contract '{TARGET_COLUMN}'."
            )

        if SELECTED_CANDIDATE not in release_text:

            raise ProductionArtifactError(
                "Release manifest does not identify "
                f"the selected candidate '{SELECTED_CANDIDATE}'."
            )

        if str(
            EXPECTED_FEATURE_COUNT
        ) not in release_text:

            raise ProductionArtifactError(
                "Release manifest does not contain the "
                f"{EXPECTED_FEATURE_COUNT}-feature contract."
            )

    def _validate_booster_contract(self) -> None:
        """Validate the loaded Booster against the frozen contract."""

        if self._booster is None:
            raise ProductionArtifactError(
                "XGBoost Booster has not been loaded."
            )

        feature_names = (
            self._booster.feature_names
        )

        if feature_names is None:

            raise ProductionArtifactError(
                "Frozen XGBoost Booster does not expose feature names."
            )

        if len(feature_names) != (
            EXPECTED_FEATURE_COUNT
        ):

            raise ProductionArtifactError(
                "Frozen XGBoost Booster feature count mismatch: "
                f"expected {EXPECTED_FEATURE_COUNT}, "
                f"found {len(feature_names)}."
            )

        if list(feature_names) != list(
            self._feature_columns
        ):

            raise ProductionFeatureContractError(
                "Frozen Booster feature ordering does not match "
                "feature_contract.json."
            )

    # ========================================================================
    # Feature contract
    # ========================================================================

    @property
    def feature_columns(self) -> tuple[str, ...]:
        """Return the frozen 296-feature contract."""

        return self._feature_columns

    @property
    def feature_count(self) -> int:
        """Return the frozen feature count."""

        return len(
            self._feature_columns
        )

    @property
    def model_candidate(self) -> str:
        """Return the frozen candidate identifier."""

        return SELECTED_CANDIDATE

    @property
    def is_loaded(self) -> bool:
        """Return True when the frozen artifact is loaded."""

        return self._loaded

    @property
    def categorical_mappings(
        self,
    ) -> dict[str, dict[str, int]]:
        """Return a defensive copy of categorical mappings."""

        return {
            feature: dict(mapping)
            for feature, mapping
            in self._categorical_mappings.items()
        }

    # ========================================================================
    # Categorical preprocessing
    # ========================================================================

    def _encode_categorical_feature(
        self,
        dataframe: pd.DataFrame,
        feature: str,
    ) -> pd.Series:
        """
        Apply the frozen training-time categorical mapping.

        Known:
            category -> frozen integer code

        Unknown:
            -1

        Missing:
            -1
        """

        mapping = self._categorical_mappings.get(
            feature
        )

        if mapping is None:
            raise ProductionArtifactError(
                f"No frozen categorical mapping for '{feature}'."
            )

        values = (
            dataframe[feature]
            .astype("string")
            .str.strip()
        )

        encoded = (
            values.map(
                mapping
            )
            .fillna(
                UNKNOWN_CATEGORY_CODE
            )
            .astype("int64")
        )

        return encoded

    def prepare_features(
        self,
        features: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Validate and transform a production feature dataframe.

        The input must already contain the frozen production feature
        contract (296 features for TUNE_014).

        This method does NOT perform feature engineering.

        It only:

            1. validates the frozen feature contract
            2. applies the frozen categorical mappings
            3. validates that all resulting features are numeric
            4. rejects infinite numeric values
            5. preserves legitimate NaN values for numeric features
            6. returns the exact frozen XGBoost feature ordering

        IMPORTANT
        ---------
        Numeric NaN values are intentionally allowed.

        The production lag-feature pipeline explicitly does not impute
        missing historical values. Consequently, legitimate historical
        lag features such as:

            occupancy_rate_lag_12h
            occupied_spaces_lag_12h
            available_spaces_lag_12h

        may legitimately contain NaN when the corresponding historical
        observation is unavailable.

        XGBoost natively supports missing numeric values. Therefore
        production must preserve these NaN values rather than replacing
        them with arbitrary values such as zero.

        Categorical features are different. They are transformed using
        the frozen training-time categorical mappings. Missing or
        unknown categorical values are represented by
        UNKNOWN_CATEGORY_CODE (-1).
        """

        # ============================================================
        # 1. Validate input type
        # ============================================================

        if not isinstance(
            features,
            pd.DataFrame,
        ):
            raise ProductionInferenceDataError(
                "Production inference input must be a pandas DataFrame."
            )

        # ============================================================
        # 2. Validate input is not empty
        # ============================================================

        if features.empty:
            raise ProductionInferenceDataError(
                "Production inference dataframe is empty."
            )

        # ============================================================
        # 3. Validate frozen feature contract
        # ============================================================

        missing = [
            feature
            for feature in self._feature_columns
            if feature not in features.columns
        ]

        if missing:
            raise ProductionFeatureContractError(
                "Production inference input is missing "
                f"{len(missing)} frozen features:\n"
                + "\n".join(
                    f"  - {feature}"
                    for feature in missing[:50]
                )
            )

        # ============================================================
        # 4. Select exact frozen feature ordering
        # ============================================================

        prepared = features[
            list(
                self._feature_columns
            )
        ].copy()

        # ============================================================
        # 5. Apply frozen categorical mappings
        # ============================================================
        #
        # Known category:
        #     category -> frozen integer code
        #
        # Missing / unknown category:
        #     -> UNKNOWN_CATEGORY_CODE (-1)
        #
        # This is the ONLY categorical transformation performed here.
        # ============================================================

        for feature in CATEGORICAL_FEATURES:

            if feature not in prepared.columns:
                raise ProductionFeatureContractError(
                    f"Frozen categorical feature '{feature}' "
                    "is missing from the production feature dataframe."
                )

            prepared[
                feature
            ] = self._encode_categorical_feature(
                prepared,
                feature,
            )

        # ============================================================
        # 6. Validate that every feature is numeric
        # ============================================================
        #
        # At this stage the two categorical features have already been
        # converted to integer codes.
        #
        # Therefore every one of the 296 frozen model features must now
        # be numeric.
        # ============================================================

        non_numeric: list[str] = []

        for feature in self._feature_columns:

            if not pd.api.types.is_numeric_dtype(
                prepared[feature]
            ):
                non_numeric.append(
                    feature
                )

        if non_numeric:

            raise ProductionFeatureContractError(
                "Production model feature dataframe contains "
                "non-numeric features outside the frozen "
                "categorical contract:\n"
                + "\n".join(
                    f"  - {feature}"
                    for feature in non_numeric
                )
            )

        # ============================================================
        # 7. Convert to numeric matrix for validation
        # ============================================================
        #
        # IMPORTANT:
        # Do NOT use fillna(), interpolation, forward-fill or
        # backward-fill here.
        #
        # Legitimate numeric NaN values must be preserved for XGBoost.
        # ============================================================

        numeric = prepared.to_numpy(
            dtype=np.float64,
            copy=False,
        )

        # ============================================================
        # 8. Reject infinite values
        # ============================================================
        #
        # NaN is allowed.
        #
        # Positive and negative infinity are not valid production
        # inference values and must be rejected.
        # ============================================================

        infinite_mask = np.isinf(
            numeric
        )

        if infinite_mask.any():

            bad_columns = [
                self._feature_columns[index]
                for index in np.where(
                    infinite_mask.any(
                        axis=0
                    )
                )[0]
            ]

            raise ProductionInferenceDataError(
                "Infinite values detected in production "
                "inference features:\n"
                + "\n".join(
                    f"  - {feature}"
                    for feature in bad_columns
                )
            )

        # ============================================================
        # 9. Explicitly document/allow legitimate NaN values
        # ============================================================
        #
        # We deliberately DO NOT reject NaN here.
        #
        # XGBoost supports NaN natively.
        #
        # This is required for historical lag features where the
        # required historical observation does not exist.
        #
        # Example:
        #
        #   occupancy_rate_lag_12h      -> NaN
        #   occupied_spaces_lag_12h     -> NaN
        #   available_spaces_lag_12h    -> NaN
        #
        # The training lag pipeline reports:
        #
        #   missing_values_filled = False
        #
        # Therefore replacing these values would create a production
        # preprocessing behaviour that was not present during training.
        # ============================================================

        # Intentionally no np.isnan(...).any() rejection here.

        # ============================================================
        # 10. Final schema assertion
        # ============================================================

        if prepared.shape[1] != (
            EXPECTED_FEATURE_COUNT
        ):
            raise ProductionFeatureContractError(
                "Prepared production feature matrix has "
                f"{prepared.shape[1]} columns; "
                f"expected {EXPECTED_FEATURE_COUNT}."
            )

        # ============================================================
        # 11. Final feature-order assertion
        # ============================================================

        if list(
            prepared.columns
        ) != list(
            self._feature_columns
        ):
            raise ProductionFeatureContractError(
                "Prepared production feature columns do not match "
                "the frozen XGBoost feature ordering."
            )

        # ============================================================
        # 12. Return exact production inference matrix
        # ============================================================

        return prepared

    # ========================================================================
    # Prediction
    # ========================================================================

    def predict(
        self,
        features: pd.DataFrame,
    ) -> float:
        """
        Generate a single production prediction.

        Parameters
        ----------
        features:
            DataFrame containing exactly one inference observation
            and the complete 296-feature contract.

        Returns
        -------
        float
            Predicted occupancy rate for T + 30 minutes.
        """

        if not self._loaded:
            raise ProductionArtifactError(
                "Frozen XGBoost artifact is not loaded."
            )

        if len(features) != 1:

            raise ProductionInferenceDataError(
                "ProductionXGBoostInference.predict() expects "
                f"exactly one inference row; received {len(features)}."
            )

        prepared = self.prepare_features(
            features
        )

        if self._booster is None:
            raise ProductionArtifactError(
                "Frozen XGBoost Booster is unavailable."
            )

        try:

            matrix = xgb.DMatrix(
                prepared,
                feature_names=list(
                    self._feature_columns
                ),
            )

            predictions = self._booster.predict(
                matrix
            )

        except Exception as exc:

            raise ProductionInferenceError(
                "Frozen XGBoost inference failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if len(predictions) != 1:

            raise ProductionInferenceError(
                "Frozen XGBoost returned an unexpected "
                f"prediction count: {len(predictions)}."
            )

        prediction = float(
            predictions[0]
        )

        if not math.isfinite(
            prediction
        ):

            raise ProductionInferenceError(
                "Frozen XGBoost returned a non-finite prediction."
            )

        # ------------------------------------------------------------
        # Occupancy-rate production contract.
        #
        # The training model configuration uses:
        #
        #     clip_predictions = True
        #     prediction_min   = 0.0
        #     prediction_max   = 1.0
        #
        # Therefore production inference applies the same constraint.
        # ------------------------------------------------------------

        prediction = float(
            np.clip(
                prediction,
                PREDICTION_MIN,
                PREDICTION_MAX,
            )
        )

        return prediction

    # ========================================================================
    # Prediction with production timestamp
    # ========================================================================

    def predict_at(
        self,
        *,
        features: pd.DataFrame,
        prediction_timestamp: Any,
    ) -> ProductionPrediction:
        """
        Generate a production prediction for timestamp T.

        The feature dataframe must already represent information available
        at or before T.

        This method deliberately does not attempt to construct or alter
        the feature dataframe.
        """

        timestamp = _normalize_timestamp(
            prediction_timestamp
        )

        prediction = self.predict(
            features
        )

        forecast_timestamp = (
            timestamp
            + pd.Timedelta(
                minutes=FORECAST_HORIZON_MINUTES
            )
        )

        return ProductionPrediction(
            prediction=prediction,
            prediction_timestamp=timestamp,
            forecast_timestamp=forecast_timestamp,
            forecast_horizon_minutes=(
                FORECAST_HORIZON_MINUTES
            ),
            model_candidate=SELECTED_CANDIDATE,
            target_column=TARGET_COLUMN,
            feature_count=EXPECTED_FEATURE_COUNT,
        )

    # ========================================================================
    # Batch prediction
    # ========================================================================

    def predict_batch(
        self,
        features: pd.DataFrame,
    ) -> np.ndarray:
        """
        Generate predictions for multiple production rows.

        This is useful for operator/admin analytics.

        The same frozen feature contract and categorical mappings
        are applied to every row.
        """

        if not self._loaded:
            raise ProductionArtifactError(
                "Frozen XGBoost artifact is not loaded."
            )

        prepared = self.prepare_features(
            features
        )

        if self._booster is None:
            raise ProductionArtifactError(
                "Frozen XGBoost Booster is unavailable."
            )

        try:

            matrix = xgb.DMatrix(
                prepared,
                feature_names=list(
                    self._feature_columns
                ),
            )

            predictions = self._booster.predict(
                matrix
            )

        except Exception as exc:

            raise ProductionInferenceError(
                "Frozen XGBoost batch inference failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        predictions = np.asarray(
            predictions,
            dtype=np.float64,
        )

        if not np.isfinite(
            predictions
        ).all():

            raise ProductionInferenceError(
                "Frozen XGBoost produced non-finite "
                "batch predictions."
            )

        predictions = np.clip(
            predictions,
            PREDICTION_MIN,
            PREDICTION_MAX,
        )

        return predictions

    # ========================================================================
    # Model information
    # ========================================================================

    def model_info(self) -> dict[str, Any]:
        """
        Return production-safe model metadata.

        This intentionally exposes contract information rather than
        internal mutable XGBoost state.
        """

        booster_feature_names = (
            list(
                self._booster.feature_names
            )
            if self._booster is not None
            and self._booster.feature_names is not None
            else []
        )

        return {
            "model_candidate": SELECTED_CANDIDATE,
            "target_column": TARGET_COLUMN,
            "forecast_horizon_minutes": (
                FORECAST_HORIZON_MINUTES
            ),
            "feature_count": (
                EXPECTED_FEATURE_COUNT
            ),
            "feature_columns": list(
                self._feature_columns
            ),
            "categorical_features": list(
                CATEGORICAL_FEATURES
            ),
            "categorical_mapping_sizes": {
                feature: len(mapping)
                for feature, mapping
                in self._categorical_mappings.items()
            },
            "booster_feature_count": len(
                booster_feature_names
            ),
            "artifact_directory": str(
                self.artifact_dir
            ),
            "loaded": self._loaded,
            "training_performed": False,
            "hyperparameter_tuning_performed": False,
            "feature_pipeline_rebuilt": False,
        }


# ============================================================================
# Convenience factory
# ============================================================================


def build_production_xgboost_inference(
    *,
    artifact_dir: Path | str | None = None,
    verify_checksums: bool = True,
) -> ProductionXGBoostInference:
    """
    Build the frozen production XGBoost inference engine.
    """

    return ProductionXGBoostInference(
        artifact_dir=artifact_dir,
        verify_checksums=verify_checksums,
    )


# ============================================================================
# Module exports
# ============================================================================


__all__ = [
    "TARGET_COLUMN",
    "SELECTED_CANDIDATE",
    "EXPECTED_FEATURE_COUNT",
    "FORECAST_HORIZON_MINUTES",
    "CATEGORICAL_FEATURES",
    "ProductionInferenceError",
    "ProductionArtifactError",
    "ProductionFeatureContractError",
    "ProductionInferenceDataError",
    "ProductionPrediction",
    "ProductionXGBoostInference",
    "build_production_xgboost_inference",
]