"""
SmartPark AI - XGBoost Regression Model
=======================================

Reusable XGBoost regression model abstraction for the SmartPark AI
machine-learning layer.

Architecture
------------

This module belongs to:

    app.ml.ml_models

Responsibilities:

    - XGBoost model configuration
    - Model construction
    - Model fitting
    - Prediction
    - Regression evaluation
    - Feature importance extraction
    - Model metadata
    - Model-specific categorical feature encoding

It is NOT responsible for:

    - Loading datasets
    - Dataset paths
    - Birmingham-specific logic
    - Train/validation/test splitting
    - Feature engineering
    - Target creation
    - Persistence of training datasets
    - Final production model registration

Leakage Contract
----------------

The model accepts X and y explicitly.

The caller is responsible for:

    X_train / y_train -> fit()
    X_validation      -> predict/evaluate()
    X_test            -> untouched until final evaluation

The model never loads or discovers datasets.

Categorical Feature Contract
----------------------------

The SmartPark feature pipeline intentionally contains some categorical
features.

Current categorical features:

    - occupancy_level
    - demand_class

These remain part of the original feature registry.

This model performs model-specific ordinal encoding:

    training data:
        category -> integer code

    validation/test data:
        known category -> training code
        unseen category -> -1
        missing category -> -1

IMPORTANT:

    The category mappings are fitted ONLY from the training dataset.

Therefore:

    - validation data does not influence encoding
    - test data does not influence encoding
    - target values do not influence encoding
    - feature engineering remains untouched
    - the persisted 296-feature contract remains intact

Initial Model
-------------

The default configuration is deliberately conservative.

This first model is a benchmark model, not an aggressively tuned
production model.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import numpy as np
import pandas as pd

try:
    from xgboost import XGBRegressor
except ImportError as exc:
    raise ImportError(
        "XGBoost is required for SmartPark AI XGBoostModel. "
        "Install it with: python -m pip install xgboost"
    ) from exc


# ============================================================================
# EXCEPTIONS
# ============================================================================


class XGBoostModelError(Exception):
    """
    Base exception for SmartPark AI XGBoost model errors.
    """


class XGBoostModelNotFittedError(XGBoostModelError):
    """
    Raised when prediction/evaluation is attempted before fitting.
    """


class XGBoostModelDataError(XGBoostModelError):
    """
    Raised when model input data is invalid.
    """


# ============================================================================
# CONFIGURATION
# ============================================================================


@dataclass(frozen=True)
class XGBoostModelConfig:
    """
    Configuration for the SmartPark AI XGBoost regression model.

    The defaults are intentionally suitable for a first benchmark.
    """

    objective: str = "reg:squarederror"

    n_estimators: int = 300

    learning_rate: float = 0.05

    max_depth: int = 6

    min_child_weight: float = 1.0

    subsample: float = 0.90

    colsample_bytree: float = 0.90

    gamma: float = 0.0

    reg_alpha: float = 0.0

    reg_lambda: float = 1.0

    random_state: int = 42

    n_jobs: int = -1

    tree_method: str = "hist"

    verbosity: int = 0

    # ------------------------------------------------------------------
    # Early stopping is deliberately disabled for the first benchmark.
    # ------------------------------------------------------------------

    early_stopping_rounds: Optional[int] = None

    # ------------------------------------------------------------------
    # Prediction constraints.
    # ------------------------------------------------------------------

    clip_predictions: bool = True

    prediction_min: float = 0.0

    prediction_max: float = 1.0

    # ------------------------------------------------------------------
    # Model-specific categorical features.
    #
    # These are NOT removed from the 296-feature contract.
    # They are encoded internally before being passed to XGBoost.
    # ------------------------------------------------------------------

    categorical_features: tuple[str, ...] = (
        "occupancy_level",
        "demand_class",
    )

    def __post_init__(self) -> None:
        """
        Validate configuration values.
        """

        if self.n_estimators <= 0:
            raise ValueError(
                "n_estimators must be greater than zero."
            )

        if self.learning_rate <= 0:
            raise ValueError(
                "learning_rate must be greater than zero."
            )

        if self.max_depth < 0:
            raise ValueError(
                "max_depth cannot be negative."
            )

        if self.min_child_weight < 0:
            raise ValueError(
                "min_child_weight cannot be negative."
            )

        if not 0 < self.subsample <= 1:
            raise ValueError(
                "subsample must be in the range (0, 1]."
            )

        if not 0 < self.colsample_bytree <= 1:
            raise ValueError(
                "colsample_bytree must be in the range (0, 1]."
            )

        if self.gamma < 0:
            raise ValueError(
                "gamma cannot be negative."
            )

        if self.reg_alpha < 0:
            raise ValueError(
                "reg_alpha cannot be negative."
            )

        if self.reg_lambda < 0:
            raise ValueError(
                "reg_lambda cannot be negative."
            )

        if self.prediction_min > self.prediction_max:
            raise ValueError(
                "prediction_min cannot be greater than "
                "prediction_max."
            )

        if (
            self.early_stopping_rounds is not None
            and self.early_stopping_rounds <= 0
        ):
            raise ValueError(
                "early_stopping_rounds must be greater than "
                "zero when configured."
            )

        duplicates = (
            len(self.categorical_features)
            != len(set(self.categorical_features))
        )

        if duplicates:
            raise ValueError(
                "categorical_features contains duplicate names."
            )


# ============================================================================
# METRICS
# ============================================================================


@dataclass(frozen=True)
class XGBoostRegressionMetrics:
    """
    Standard regression evaluation metrics.
    """

    mae: float

    rmse: float

    r2: float

    mape: Optional[float]

    sample_count: int

    target_mean: float

    prediction_mean: float

    target_min: float

    target_max: float

    prediction_min: float

    prediction_max: float

    def to_dict(self) -> dict[str, Any]:
        """
        Convert metrics to a JSON-safe dictionary.
        """

        return asdict(self)


# ============================================================================
# FEATURE IMPORTANCE
# ============================================================================


@dataclass(frozen=True)
class XGBoostFeatureImportance:
    """
    Feature importance record.
    """

    feature: str

    importance: float

    rank: int

    importance_type: str = "gain"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ============================================================================
# MODEL RESULT
# ============================================================================


@dataclass(frozen=True)
class XGBoostEvaluationResult:
    """
    Complete result of evaluating an XGBoost model.
    """

    model_name: str

    target_column: Optional[str]

    metrics: XGBoostRegressionMetrics

    feature_count: int

    sample_count: int

    metadata: dict[str, Any] = field(
        default_factory=dict
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "target_column": self.target_column,
            "metrics": self.metrics.to_dict(),
            "feature_count": self.feature_count,
            "sample_count": self.sample_count,
            "metadata": self.metadata,
        }


# ============================================================================
# MODEL
# ============================================================================


class XGBoostModel:
    """
    Reusable XGBoost regression model for SmartPark AI.

    Example
    -------

        model = XGBoostModel(
            target_column="target_occupancy_rate_30m"
        )

        model.fit(
            X_train,
            y_train,
        )

        predictions = model.predict(
            X_validation
        )

        evaluation = model.evaluate(
            X_validation,
            y_validation,
        )
    """

    MODEL_TYPE = "xgboost_regressor"

    MODEL_VERSION = "1.1"

    # Internal representation for missing/unseen categorical values.
    UNKNOWN_CATEGORY_CODE = -1

    def __init__(
        self,
        *,
        target_column: Optional[str] = None,
        config: Optional[XGBoostModelConfig] = None,
        model_name: str = "xgboost_regressor",
    ) -> None:

        self.target_column = target_column

        self.config = (
            config
            if config is not None
            else XGBoostModelConfig()
        )

        self.model_name = model_name

        self._model: Optional[XGBRegressor] = None

        # Original feature schema.
        self._feature_columns: tuple[str, ...] = ()

        # Feature schema passed to XGBoost after encoding.
        self._encoded_feature_columns: tuple[str, ...] = ()

        # Training-only categorical mappings.
        self._categorical_mappings: dict[
            str,
            dict[str, int],
        ] = {}

        self._fitted: bool = False

        self._training_rows: int = 0

        self._training_feature_count: int = 0

        self._training_target_mean: Optional[float] = None

        self._training_target_min: Optional[float] = None

        self._training_target_max: Optional[float] = None

        self._fit_metadata: dict[str, Any] = {}

    # ========================================================================
    # MODEL CONSTRUCTION
    # ========================================================================

    def _build_model(self) -> XGBRegressor:
        """
        Construct a fresh XGBoost regressor from configuration.
        """

        config = self.config

        parameters: dict[str, Any] = {
            "objective": config.objective,
            "n_estimators": config.n_estimators,
            "learning_rate": config.learning_rate,
            "max_depth": config.max_depth,
            "min_child_weight": config.min_child_weight,
            "subsample": config.subsample,
            "colsample_bytree": config.colsample_bytree,
            "gamma": config.gamma,
            "reg_alpha": config.reg_alpha,
            "reg_lambda": config.reg_lambda,
            "random_state": config.random_state,
            "n_jobs": config.n_jobs,
            "tree_method": config.tree_method,
            "verbosity": config.verbosity,
        }

        return XGBRegressor(**parameters)

    # ========================================================================
    # BASIC DATA VALIDATION
    # ========================================================================

    @staticmethod
    def _validate_dataframe(
        X: Any,
    ) -> pd.DataFrame:
        """
        Convert X to a DataFrame and validate basic structure.
        """

        if isinstance(X, pd.DataFrame):
            dataframe = X.copy()
        else:
            try:
                dataframe = pd.DataFrame(X)
            except Exception as exc:
                raise XGBoostModelDataError(
                    "Unable to convert X into a pandas DataFrame."
                ) from exc

        if dataframe.empty:
            raise XGBoostModelDataError(
                "Feature dataframe X is empty."
            )

        if dataframe.columns.duplicated().any():
            duplicates = tuple(
                dataframe.columns[
                    dataframe.columns.duplicated()
                ]
            )

            raise XGBoostModelDataError(
                "Feature dataframe contains duplicate "
                f"columns: {duplicates}"
            )

        dataframe.columns = [
            str(column)
            for column in dataframe.columns
        ]

        return dataframe

    # ========================================================================
    # FEATURE SCHEMA VALIDATION
    # ========================================================================

    def _validate_feature_schema(
        self,
        dataframe: pd.DataFrame,
        *,
        expected_columns: Optional[
            tuple[str, ...]
        ] = None,
    ) -> pd.DataFrame:
        """
        Validate the feature schema.

        During fitting, no expected schema exists.

        During prediction, the schema must exactly match
        the schema learned during fitting.
        """

        if expected_columns is None:
            return dataframe

        actual_columns = tuple(
            str(column)
            for column in dataframe.columns
        )

        if actual_columns != expected_columns:

            missing = [
                column
                for column in expected_columns
                if column not in dataframe.columns
            ]

            extra = [
                column
                for column in dataframe.columns
                if column not in expected_columns
            ]

            raise XGBoostModelDataError(
                "Prediction feature schema does not match "
                "the training feature schema. "
                f"Missing={missing}; Extra={extra}."
            )

        return dataframe.loc[
            :,
            list(expected_columns),
        ]

    # ========================================================================
    # NUMERIC FEATURE VALIDATION
    # ========================================================================

    def _validate_numeric_features(
        self,
        dataframe: pd.DataFrame,
    ) -> None:
        """
        Validate all non-categorical features.

        Categorical features are intentionally excluded because they
        are handled by the model-specific encoder.

        Missing numeric values (NaN) are allowed because XGBoost
        natively supports missing feature values.

        Positive and negative infinity are NOT allowed.
        """

        categorical = set(
            self.config.categorical_features
        )

        non_numeric: list[str] = []

        for column in dataframe.columns:

            if column in categorical:
                continue

            if not pd.api.types.is_numeric_dtype(
                dataframe[column]
            ):
                non_numeric.append(column)

        if non_numeric:

            raise XGBoostModelDataError(
                "X contains non-numeric feature columns "
                "that are not configured as categorical features: "
                f"{non_numeric}"
            )

        numeric_columns = [
            column
            for column in dataframe.columns
            if column not in categorical
        ]

        if not numeric_columns:
            return

        numeric_values = dataframe[
            numeric_columns
        ].to_numpy(
            dtype=float
        )

        # --------------------------------------------------------------
        # IMPORTANT:
        #
        # np.isfinite() returns False for BOTH NaN and infinity.
        #
        # NaN is allowed because XGBoost supports missing numeric
        # feature values natively.
        #
        # Therefore we explicitly test ONLY for positive/negative
        # infinity.
        # --------------------------------------------------------------

        infinite_mask = np.isinf(
            numeric_values
        )

        if infinite_mask.any():

            infinite_positions = np.argwhere(
                infinite_mask
            )

            offending_columns = sorted(
                {
                    numeric_columns[
                        int(position[1])
                    ]
                    for position in infinite_positions
                }
            )

            raise XGBoostModelDataError(
                "X contains positive or negative "
                "infinite numeric values in feature(s): "
                f"{offending_columns}"
            )

    # ========================================================================
    # CATEGORICAL ENCODING
    # ========================================================================

    @staticmethod
    def _normalise_category(
        value: Any,
    ) -> str:
        """
        Convert a categorical value into a deterministic string key.

        Missing values are represented by a dedicated token.
        """

        if pd.isna(value):
            return "__MISSING__"

        return str(value)

    def _fit_categorical_mappings(
        self,
        dataframe: pd.DataFrame,
    ) -> None:
        """
        Learn categorical mappings from TRAINING DATA ONLY.

        This method must only be called during fit().
        """

        self._categorical_mappings = {}

        for column in self.config.categorical_features:

            if column not in dataframe.columns:
                continue

            values = [
                self._normalise_category(value)
                for value in dataframe[column]
            ]

            unique_values = sorted(
                set(values)
            )

            mapping = {
                category: index
                for index, category
                in enumerate(unique_values)
            }

            self._categorical_mappings[column] = mapping

    def _encode_categorical_features(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Encode categorical features using mappings learned during fit().

        Known categories receive their training code.

        Unknown categories receive -1.

        Missing categories receive the training missing-value code
        if such a value existed during training; otherwise -1.
        """

        result = dataframe.copy()

        for column in self.config.categorical_features:

            if column not in result.columns:
                continue

            mapping = self._categorical_mappings.get(
                column
            )

            if mapping is None:
                raise XGBoostModelDataError(
                    "Categorical feature mapping has not been "
                    f"fitted for column '{column}'."
                )

            encoded = []

            for value in result[column]:

                key = self._normalise_category(
                    value
                )

                encoded.append(
                    mapping.get(
                        key,
                        self.UNKNOWN_CATEGORY_CODE,
                    )
                )

            result[column] = np.asarray(
                encoded,
                dtype=np.int64,
            )

        return result

    # ========================================================================
    # MODEL MATRIX PREPARATION
    # ========================================================================

    def _prepare_model_matrix(
        self,
        X: Any,
        *,
        expected_columns: Optional[
            tuple[str, ...]
        ] = None,
    ) -> pd.DataFrame:
        """
        Validate and convert X into the numeric matrix consumed by XGBoost.

        IMPORTANT:

        The original feature schema is preserved.

        Only categorical values are encoded internally.
        """

        dataframe = self._validate_dataframe(
            X
        )

        dataframe = self._validate_feature_schema(
            dataframe,
            expected_columns=expected_columns,
        )

        self._validate_numeric_features(
            dataframe
        )

        if self.config.categorical_features:

            dataframe = (
                self._encode_categorical_features(
                    dataframe
                )
            )

        # --------------------------------------------------------------
        # Final numeric validation.
        #
        # NaN values are allowed because XGBoost natively supports
        # missing numeric feature values.
        #
        # Positive/negative infinity is not allowed.
        # --------------------------------------------------------------

        non_numeric = [
            column
            for column in dataframe.columns
            if not pd.api.types.is_numeric_dtype(
                dataframe[column]
            )
        ]

        if non_numeric:

            raise XGBoostModelDataError(
                "Model matrix still contains non-numeric "
                f"columns after encoding: {non_numeric}"
            )

        numeric_values = dataframe.to_numpy(
            dtype=float
        )

        infinite_mask = np.isinf(
            numeric_values
        )

        if infinite_mask.any():

            infinite_positions = np.argwhere(
                infinite_mask
            )

            offending_columns = sorted(
                {
                    str(
                        dataframe.columns[
                            int(position[1])
                        ]
                    )
                    for position in infinite_positions
                }
            )

            raise XGBoostModelDataError(
                "Model matrix contains positive or negative "
                "infinite values in feature(s): "
                f"{offending_columns}"
            )

        return dataframe

    # ========================================================================
    # TARGET VALIDATION
    # ========================================================================

    @staticmethod
    def _validate_y(
        y: Any,
    ) -> np.ndarray:
        """
        Validate target values.
        """

        if isinstance(y, pd.Series):

            try:
                values = y.to_numpy(
                    dtype=float
                )
            except Exception as exc:
                raise XGBoostModelDataError(
                    "Unable to convert target y to numeric values."
                ) from exc

        elif isinstance(y, pd.DataFrame):

            if y.shape[1] != 1:
                raise XGBoostModelDataError(
                    "Target dataframe y must contain exactly "
                    "one column."
                )

            try:
                values = y.iloc[
                    :,
                    0,
                ].to_numpy(
                    dtype=float
                )
            except Exception as exc:
                raise XGBoostModelDataError(
                    "Unable to convert target y to numeric values."
                ) from exc

        else:

            try:
                values = np.asarray(
                    y,
                    dtype=float,
                )
            except Exception as exc:
                raise XGBoostModelDataError(
                    "Unable to convert y to numeric values."
                ) from exc

        values = values.reshape(-1)

        if len(values) == 0:
            raise XGBoostModelDataError(
                "Target y is empty."
            )

        if not np.isfinite(values).all():
            raise XGBoostModelDataError(
                "Target y contains NaN or infinite values."
            )

        return values

    # ========================================================================
    # FIT
    # ========================================================================

    def fit(
        self,
        X: Any,
        y: Any,
    ) -> "XGBoostModel":
        """
        Fit the XGBoost model.

        IMPORTANT:

        Only the supplied X/y data is used.

        No validation or test data is discovered or loaded.

        Categorical mappings are learned exclusively from X.
        """

        raw_features = self._validate_dataframe(
            X
        )

        raw_features = self._validate_feature_schema(
            raw_features
        )

        target = self._validate_y(
            y
        )

        if len(raw_features) != len(target):
            raise XGBoostModelDataError(
                "X and y row counts do not match: "
                f"X={len(raw_features)}, "
                f"y={len(target)}."
            )

        # --------------------------------------------------------------
        # Validate non-categorical feature types.
        # --------------------------------------------------------------

        self._validate_numeric_features(
            raw_features
        )

        # --------------------------------------------------------------
        # Remember original feature schema.
        # --------------------------------------------------------------

        self._feature_columns = tuple(
            str(column)
            for column in raw_features.columns
        )

        self._training_rows = len(
            raw_features
        )

        self._training_feature_count = len(
            raw_features.columns
        )

        self._training_target_mean = float(
            np.mean(target)
        )

        self._training_target_min = float(
            np.min(target)
        )

        self._training_target_max = float(
            np.max(target)
        )

        # --------------------------------------------------------------
        # Fit categorical mappings using TRAINING DATA ONLY.
        # --------------------------------------------------------------

        self._fit_categorical_mappings(
            raw_features
        )

        # --------------------------------------------------------------
        # Transform training matrix.
        # --------------------------------------------------------------

        features = self._prepare_model_matrix(
            raw_features,
            expected_columns=self._feature_columns,
        )

        self._encoded_feature_columns = tuple(
            str(column)
            for column in features.columns
        )

        # --------------------------------------------------------------
        # Build fresh model.
        # --------------------------------------------------------------

        self._model = self._build_model()

        fit_kwargs: dict[str, Any] = {}

        # --------------------------------------------------------------
        # Deliberately do not pass eval_set for the initial benchmark.
        # --------------------------------------------------------------

        self._model.fit(
            features,
            target,
            **fit_kwargs,
        )

        self._fitted = True

        self._fit_metadata = {
            "training_rows": self._training_rows,
            "training_feature_count": (
                self._training_feature_count
            ),
            "encoded_feature_count": len(
                self._encoded_feature_columns
            ),
            "training_target_mean": (
                self._training_target_mean
            ),
            "training_target_min": (
                self._training_target_min
            ),
            "training_target_max": (
                self._training_target_max
            ),
            "validation_data_used": False,
            "test_data_used": False,
            "early_stopping_used": False,
            "random_state": (
                self.config.random_state
            ),
            "categorical_features": list(
                self.config.categorical_features
            ),
            "categorical_encoding": (
                "training_only_ordinal_mapping"
            ),
            "unknown_category_code": (
                self.UNKNOWN_CATEGORY_CODE
            ),
        }

        return self

    # ========================================================================
    # FIT STATUS
    # ========================================================================

    @property
    def is_fitted(self) -> bool:
        """
        Return whether the model has been fitted.
        """

        return self._fitted

    # ========================================================================
    # FEATURE SCHEMA
    # ========================================================================

    @property
    def feature_columns(
        self,
    ) -> tuple[str, ...]:
        """
        Return the original feature schema learned during fitting.
        """

        return self._feature_columns

    @property
    def encoded_feature_columns(
        self,
    ) -> tuple[str, ...]:
        """
        Return the feature schema passed internally to XGBoost.
        """

        return self._encoded_feature_columns

    # ========================================================================
    # CATEGORICAL MAPPINGS
    # ========================================================================

    @property
    def categorical_mappings(
        self,
    ) -> dict[str, dict[str, int]]:
        """
        Return a copy of the training-only categorical mappings.
        """

        return {
            column: dict(mapping)
            for column, mapping
            in self._categorical_mappings.items()
        }

    # ========================================================================
    # UNDERLYING MODEL
    # ========================================================================

    @property
    def model(self) -> XGBRegressor:
        """
        Return the fitted XGBoost estimator.
        """

        if not self._fitted:
            raise XGBoostModelNotFittedError(
                "XGBoost model has not been fitted yet."
            )

        assert self._model is not None

        return self._model

    # ========================================================================
    # PREDICTION
    # ========================================================================

    def predict(
        self,
        X: Any,
    ) -> np.ndarray:
        """
        Generate predictions.

        The prediction feature schema must exactly match the
        training feature schema.

        Categorical encoding uses mappings learned from training data.
        """

        if not self._fitted:
            raise XGBoostModelNotFittedError(
                "Cannot predict before the XGBoost model "
                "has been fitted."
            )

        features = self._prepare_model_matrix(
            X,
            expected_columns=self._feature_columns,
        )

        predictions = self.model.predict(
            features
        )

        predictions = np.asarray(
            predictions,
            dtype=float,
        )

        if not np.isfinite(
            predictions
        ).all():

            raise XGBoostModelError(
                "XGBoost produced NaN or infinite predictions."
            )

        if self.config.clip_predictions:

            predictions = np.clip(
                predictions,
                self.config.prediction_min,
                self.config.prediction_max,
            )

        return predictions

    # ========================================================================
    # METRIC CALCULATION
    # ========================================================================

    @staticmethod
    def _mae(
        y_true: np.ndarray,
        y_pred: np.ndarray,
    ) -> float:

        return float(
            np.mean(
                np.abs(
                    y_true - y_pred
                )
            )
        )

    @staticmethod
    def _rmse(
        y_true: np.ndarray,
        y_pred: np.ndarray,
    ) -> float:

        return float(
            np.sqrt(
                np.mean(
                    (
                        y_true - y_pred
                    ) ** 2
                )
            )
        )

    @staticmethod
    def _r2(
        y_true: np.ndarray,
        y_pred: np.ndarray,
    ) -> float:

        denominator = np.sum(
            (
                y_true - np.mean(y_true)
            ) ** 2
        )

        if denominator == 0:
            return 0.0

        numerator = np.sum(
            (
                y_true - y_pred
            ) ** 2
        )

        return float(
            1.0
            - (
                numerator / denominator
            )
        )

    @staticmethod
    def _mape(
        y_true: np.ndarray,
        y_pred: np.ndarray,
    ) -> Optional[float]:
        """
        Calculate MAPE while excluding zero-valued actual targets.
        """

        non_zero = (
            np.abs(y_true) > 1e-12
        )

        if not np.any(non_zero):
            return None

        percentage_error = (
            np.abs(
                (
                    y_true[non_zero]
                    - y_pred[non_zero]
                )
                / y_true[non_zero]
            )
            * 100.0
        )

        return float(
            np.mean(
                percentage_error
            )
        )

    @classmethod
    def calculate_metrics(
        cls,
        y_true: Any,
        y_pred: Any,
    ) -> XGBoostRegressionMetrics:
        """
        Calculate standard regression metrics.
        """

        actual = cls._validate_y(
            y_true
        )

        predicted = cls._validate_y(
            y_pred
        )

        if len(actual) != len(predicted):
            raise XGBoostModelDataError(
                "y_true and y_pred lengths do not match: "
                f"{len(actual)} != {len(predicted)}"
            )

        return XGBoostRegressionMetrics(
            mae=cls._mae(
                actual,
                predicted,
            ),
            rmse=cls._rmse(
                actual,
                predicted,
            ),
            r2=cls._r2(
                actual,
                predicted,
            ),
            mape=cls._mape(
                actual,
                predicted,
            ),
            sample_count=len(actual),
            target_mean=float(
                np.mean(actual)
            ),
            prediction_mean=float(
                np.mean(predicted)
            ),
            target_min=float(
                np.min(actual)
            ),
            target_max=float(
                np.max(actual)
            ),
            prediction_min=float(
                np.min(predicted)
            ),
            prediction_max=float(
                np.max(predicted)
            ),
        )

    # ========================================================================
    # EVALUATION
    # ========================================================================

    def evaluate(
        self,
        X: Any,
        y: Any,
    ) -> XGBoostEvaluationResult:
        """
        Evaluate the fitted model.

        IMPORTANT:

        This method does not fit or modify the model.
        """

        if not self._fitted:
            raise XGBoostModelNotFittedError(
                "Cannot evaluate before the XGBoost model "
                "has been fitted."
            )

        target = self._validate_y(
            y
        )

        predictions = self.predict(
            X
        )

        if len(predictions) != len(target):
            raise XGBoostModelDataError(
                "Prediction and target row counts do not match: "
                f"predictions={len(predictions)}, "
                f"target={len(target)}."
            )

        metrics = self.calculate_metrics(
            target,
            predictions,
        )

        return XGBoostEvaluationResult(
            model_name=self.model_name,
            target_column=self.target_column,
            metrics=metrics,
            feature_count=len(
                self._feature_columns
            ),
            sample_count=len(
                target
            ),
            metadata={
                "model_type": self.MODEL_TYPE,
                "model_version": self.MODEL_VERSION,
                "training_rows": (
                    self._training_rows
                ),
                "training_feature_count": (
                    self._training_feature_count
                ),
                "encoded_feature_count": (
                    len(
                        self._encoded_feature_columns
                    )
                ),
                "validation_data_used_during_fit": False,
                "test_data_used": False,
                "prediction_clipping": (
                    self.config.clip_predictions
                ),
                "categorical_features": list(
                    self.config.categorical_features
                ),
                "categorical_encoding": (
                    "training_only_ordinal_mapping"
                ),
                "unknown_category_code": (
                    self.UNKNOWN_CATEGORY_CODE
                ),
            },
        )

    # ========================================================================
    # FEATURE IMPORTANCE
    # ========================================================================

    def feature_importance(
        self,
        *,
        importance_type: str = "gain",
        top_n: Optional[int] = 20,
    ) -> list[
        XGBoostFeatureImportance
    ]:
        """
        Return ranked XGBoost feature importance.

        Supported importance types:

            weight
            gain
            cover
            total_gain
            total_cover
        """

        if not self._fitted:
            raise XGBoostModelNotFittedError(
                "Cannot calculate feature importance before "
                "the model has been fitted."
            )

        if importance_type not in {
            "weight",
            "gain",
            "cover",
            "total_gain",
            "total_cover",
        }:

            raise ValueError(
                "Unsupported importance_type: "
                f"{importance_type}"
            )

        assert self._model is not None

        booster = (
            self._model.get_booster()
        )

        score = (
            booster.get_score(
                importance_type=importance_type
            )
        )

        records: list[
            XGBoostFeatureImportance
        ] = []

        for feature, importance in score.items():

            resolved_feature = feature

            # XGBoost may expose generated names such as f0/f1.
            if (
                feature.startswith("f")
                and feature[1:].isdigit()
            ):

                index = int(
                    feature[1:]
                )

                if (
                    0 <= index
                    < len(
                        self._encoded_feature_columns
                    )
                ):

                    resolved_feature = (
                        self._encoded_feature_columns[
                            index
                        ]
                    )

            records.append(
                XGBoostFeatureImportance(
                    feature=resolved_feature,
                    importance=float(
                        importance
                    ),
                    rank=0,
                    importance_type=(
                        importance_type
                    ),
                )
            )

        records.sort(
            key=lambda item: item.importance,
            reverse=True,
        )

        ranked: list[
            XGBoostFeatureImportance
        ] = []

        for rank, item in enumerate(
            records,
            start=1,
        ):

            ranked.append(
                XGBoostFeatureImportance(
                    feature=item.feature,
                    importance=item.importance,
                    rank=rank,
                    importance_type=item.importance_type,
                )
            )

        if top_n is not None:

            if top_n <= 0:
                raise ValueError(
                    "top_n must be greater than zero "
                    "when specified."
                )

            ranked = ranked[:top_n]

        return ranked

    # ========================================================================
    # MODEL METADATA
    # ========================================================================

    def metadata(self) -> dict[str, Any]:
        """
        Return model metadata.
        """

        return {
            "model_name": self.model_name,
            "model_type": self.MODEL_TYPE,
            "model_version": self.MODEL_VERSION,
            "target_column": self.target_column,
            "fitted": self._fitted,
            "feature_count": len(
                self._feature_columns
            ),
            "encoded_feature_count": len(
                self._encoded_feature_columns
            ),
            "feature_columns": list(
                self._feature_columns
            ),
            "encoded_feature_columns": list(
                self._encoded_feature_columns
            ),
            "categorical_features": list(
                self.config.categorical_features
            ),
            "categorical_mappings": {
                column: dict(mapping)
                for column, mapping
                in self._categorical_mappings.items()
            },
            "categorical_encoding": (
                "training_only_ordinal_mapping"
            ),
            "unknown_category_code": (
                self.UNKNOWN_CATEGORY_CODE
            ),
            "training_rows": (
                self._training_rows
            ),
            "training_target_mean": (
                self._training_target_mean
            ),
            "training_target_min": (
                self._training_target_min
            ),
            "training_target_max": (
                self._training_target_max
            ),
            "config": asdict(
                self.config
            ),
            "fit_metadata": dict(
                self._fit_metadata
            ),
        }

    # ========================================================================
    # CONFIGURATION
    # ========================================================================

    def get_params(self) -> dict[str, Any]:
        """
        Return XGBoost configuration parameters.
        """

        return asdict(
            self.config
        )

    # ========================================================================
    # FEATURE COUNT
    # ========================================================================

    @property
    def feature_count(self) -> int:
        """
        Return number of original features learned during fitting.
        """

        return len(
            self._feature_columns
        )

    # ========================================================================
    # TRAINING ROW COUNT
    # ========================================================================

    @property
    def training_rows(self) -> int:
        """
        Return number of training rows used during fitting.
        """

        return self._training_rows


# ============================================================================
# FACTORY
# ============================================================================


def build_xgboost_model(
    *,
    target_column: Optional[str] = None,
    config: Optional[
        XGBoostModelConfig
    ] = None,
    model_name: str = "xgboost_regressor",
) -> XGBoostModel:
    """
    Build a configured XGBoost regression model.

    This factory keeps callers independent from the concrete model
    constructor.
    """

    return XGBoostModel(
        target_column=target_column,
        config=config,
        model_name=model_name,
    )


# ============================================================================
# MODULE EXPORTS
# ============================================================================


__all__ = [
    "XGBoostModel",
    "XGBoostModelConfig",
    "XGBoostModelError",
    "XGBoostModelNotFittedError",
    "XGBoostModelDataError",
    "XGBoostRegressionMetrics",
    "XGBoostFeatureImportance",
    "XGBoostEvaluationResult",
    "build_xgboost_model",
]