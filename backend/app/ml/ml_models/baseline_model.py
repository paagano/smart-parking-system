"""
SmartPark AI - Baseline Models
================================

Generic baseline models for SmartPark AI forecasting.

Purpose
-------
This module provides simple, deterministic forecasting baselines that
establish a performance benchmark before more sophisticated models
(e.g. XGBoost, LSTM) are introduced.

The baselines are intentionally model-independent and dataset-source
agnostic. They operate on already-prepared training/validation/test
datasets.

Supported baseline strategies
-----------------------------
1. MeanBaseline
   Predicts the mean target value observed in the training dataset.

2. LastValueBaseline
   Predicts using the most recent observed target/input value available
   in the supplied feature dataset.

3. SeasonalNaiveBaseline
   Predicts using a historical value at a configurable lag.

The module also provides:
- prediction validation
- regression metrics
- baseline comparison
- model metadata
- reproducibility information

Important leakage contract
--------------------------
Baseline models must never inspect validation or test targets during
fitting.

The fit() method therefore accepts training data only.

Validation/test data may only be supplied to predict() and evaluate().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Sequence

import math

import numpy as np
import pandas as pd


# ============================================================================
# Exceptions
# ============================================================================


class BaselineModelError(Exception):
    """Base exception for baseline model errors."""


class BaselineModelNotFittedError(BaselineModelError):
    """Raised when prediction is attempted before fitting."""


class BaselineModelDataError(BaselineModelError):
    """Raised when supplied training or prediction data is invalid."""


# ============================================================================
# Enums
# ============================================================================


class BaselineStrategy(str, Enum):
    """
    Supported baseline strategies.
    """

    MEAN = "mean"
    LAST_VALUE = "last_value"
    SEASONAL_NAIVE = "seasonal_naive"


# ============================================================================
# Metrics
# ============================================================================


@dataclass(frozen=True)
class RegressionMetrics:
    """
    Standard regression evaluation metrics.
    """

    mae: float
    rmse: float
    r2: float
    mape: Optional[float]
    sample_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "mae": self.mae,
            "rmse": self.rmse,
            "r2": self.r2,
            "mape": self.mape,
            "sample_count": self.sample_count,
        }


# ============================================================================
# Baseline result
# ============================================================================


@dataclass
class BaselineEvaluationResult:
    """
    Result produced when a baseline is evaluated.
    """

    model_name: str
    strategy: str
    target_column: str
    metrics: RegressionMetrics
    predictions: pd.Series
    actuals: pd.Series
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_name": self.model_name,
            "strategy": self.strategy,
            "target_column": self.target_column,
            "metrics": self.metrics.to_dict(),
            "metadata": self.metadata,
        }


# ============================================================================
# Metric helpers
# ============================================================================


def _validate_regression_inputs(
    actual: Sequence[Any],
    predicted: Sequence[Any],
) -> tuple[np.ndarray, np.ndarray]:
    """
    Validate and normalize regression inputs.
    """

    actual_array = np.asarray(actual, dtype=float)
    predicted_array = np.asarray(predicted, dtype=float)

    if actual_array.ndim != 1:
        actual_array = actual_array.reshape(-1)

    if predicted_array.ndim != 1:
        predicted_array = predicted_array.reshape(-1)

    if len(actual_array) != len(predicted_array):
        raise BaselineModelDataError(
            "Actual and predicted values must have "
            f"the same length: {len(actual_array)} != "
            f"{len(predicted_array)}."
        )

    if len(actual_array) == 0:
        raise BaselineModelDataError(
            "Cannot calculate metrics on an empty dataset."
        )

    finite_mask = (
        np.isfinite(actual_array)
        & np.isfinite(predicted_array)
    )

    if not finite_mask.all():
        actual_array = actual_array[finite_mask]
        predicted_array = predicted_array[finite_mask]

    if len(actual_array) == 0:
        raise BaselineModelDataError(
            "No finite actual/predicted observations remain."
        )

    return actual_array, predicted_array


def mean_absolute_error(
    actual: Sequence[Any],
    predicted: Sequence[Any],
) -> float:
    """
    Calculate Mean Absolute Error.
    """

    y_true, y_pred = _validate_regression_inputs(
        actual,
        predicted,
    )

    return float(
        np.mean(
            np.abs(
                y_true - y_pred
            )
        )
    )


def root_mean_squared_error(
    actual: Sequence[Any],
    predicted: Sequence[Any],
) -> float:
    """
    Calculate Root Mean Squared Error.
    """

    y_true, y_pred = _validate_regression_inputs(
        actual,
        predicted,
    )

    return float(
        np.sqrt(
            np.mean(
                np.square(
                    y_true - y_pred
                )
            )
        )
    )


def r2_score(
    actual: Sequence[Any],
    predicted: Sequence[Any],
) -> float:
    """
    Calculate coefficient of determination (R²).
    """

    y_true, y_pred = _validate_regression_inputs(
        actual,
        predicted,
    )

    denominator = np.sum(
        np.square(
            y_true - np.mean(y_true)
        )
    )

    if denominator == 0:
        return 0.0

    numerator = np.sum(
        np.square(
            y_true - y_pred
        )
    )

    return float(
        1.0 - (
            numerator / denominator
        )
    )


def mean_absolute_percentage_error(
    actual: Sequence[Any],
    predicted: Sequence[Any],
) -> Optional[float]:
    """
    Calculate MAPE.

    Zero-valued actual observations are excluded because percentage
    error is undefined for zero actual values.
    """

    y_true, y_pred = _validate_regression_inputs(
        actual,
        predicted,
    )

    non_zero_mask = y_true != 0

    if not non_zero_mask.any():
        return None

    percentage_errors = np.abs(
        (
            y_true[non_zero_mask]
            - y_pred[non_zero_mask]
        )
        / y_true[non_zero_mask]
    )

    return float(
        np.mean(percentage_errors) * 100.0
    )


def calculate_regression_metrics(
    actual: Sequence[Any],
    predicted: Sequence[Any],
) -> RegressionMetrics:
    """
    Calculate the complete baseline regression metric set.
    """

    y_true, y_pred = _validate_regression_inputs(
        actual,
        predicted,
    )

    return RegressionMetrics(
        mae=mean_absolute_error(
            y_true,
            y_pred,
        ),
        rmse=root_mean_squared_error(
            y_true,
            y_pred,
        ),
        r2=r2_score(
            y_true,
            y_pred,
        ),
        mape=mean_absolute_percentage_error(
            y_true,
            y_pred,
        ),
        sample_count=len(y_true),
    )


# ============================================================================
# Base baseline model
# ============================================================================


class BaseBaselineModel:
    """
    Abstract base class for all baseline models.
    """

    strategy: BaselineStrategy

    def __init__(
        self,
        *,
        target_column: str,
        model_name: Optional[str] = None,
    ) -> None:

        if not target_column:
            raise BaselineModelDataError(
                "target_column must not be empty."
            )

        self.target_column = target_column

        self.model_name = (
            model_name
            or self.__class__.__name__
        )

        self._is_fitted = False
        self._training_row_count = 0
        self._training_statistics: dict[str, Any] = {}

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    @property
    def training_row_count(self) -> int:
        return self._training_row_count

    @property
    def training_statistics(self) -> dict[str, Any]:
        return dict(
            self._training_statistics
        )

    def _validate_training_data(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.Series:
        """
        Validate training dataframe and extract target.
        """

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise BaselineModelDataError(
                "Training data must be a pandas DataFrame."
            )

        if self.target_column not in dataframe.columns:
            raise BaselineModelDataError(
                "Target column "
                f"'{self.target_column}' "
                "is missing from training data."
            )

        target = pd.to_numeric(
            dataframe[self.target_column],
            errors="coerce",
        )

        target = target.dropna()

        if target.empty:
            raise BaselineModelDataError(
                "Training target contains no valid "
                "numeric observations."
            )

        if not np.isfinite(
            target.to_numpy(dtype=float)
        ).all():
            raise BaselineModelDataError(
                "Training target contains infinite values."
            )

        return target

    def _validate_prediction_data(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.Series:
        """
        Validate prediction/evaluation dataframe.
        """

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise BaselineModelDataError(
                "Prediction data must be a pandas DataFrame."
            )

        if self.target_column not in dataframe.columns:
            raise BaselineModelDataError(
                "Target column "
                f"'{self.target_column}' "
                "is missing from prediction data."
            )

        target = pd.to_numeric(
            dataframe[self.target_column],
            errors="coerce",
        )

        return target

    def fit(
        self,
        dataframe: pd.DataFrame,
    ) -> "BaseBaselineModel":
        raise NotImplementedError

    def predict(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.Series:
        raise NotImplementedError

    def evaluate(
        self,
        dataframe: pd.DataFrame,
    ) -> BaselineEvaluationResult:
        """
        Evaluate the fitted baseline against supplied data.
        """

        if not self.is_fitted:
            raise BaselineModelNotFittedError(
                f"{self.model_name} has not been fitted."
            )

        actual = self._validate_prediction_data(
            dataframe
        )

        predictions = self.predict(
            dataframe
        )

        valid_mask = (
            actual.notna()
            & predictions.notna()
        )

        if not valid_mask.any():
            raise BaselineModelDataError(
                "No rows contain both a valid target "
                "and a valid prediction."
            )

        actual_valid = actual.loc[
            valid_mask
        ]

        predictions_valid = predictions.loc[
            valid_mask
        ]

        metrics = calculate_regression_metrics(
            actual_valid.to_numpy(),
            predictions_valid.to_numpy(),
        )

        return BaselineEvaluationResult(
            model_name=self.model_name,
            strategy=self.strategy.value,
            target_column=self.target_column,
            metrics=metrics,
            predictions=predictions_valid,
            actuals=actual_valid,
            metadata={
                "training_row_count": (
                    self.training_row_count
                ),
                "evaluation_row_count": (
                    len(actual_valid)
                ),
                "training_statistics": (
                    self.training_statistics
                ),
            },
        )

    def get_metadata(self) -> dict[str, Any]:
        """
        Return model metadata.
        """

        return {
            "model_name": self.model_name,
            "model_type": self.__class__.__name__,
            "strategy": self.strategy.value,
            "target_column": self.target_column,
            "is_fitted": self.is_fitted,
            "training_row_count": (
                self.training_row_count
            ),
            "training_statistics": (
                self.training_statistics
            ),
        }


# ============================================================================
# Mean baseline
# ============================================================================


class MeanBaseline(BaseBaselineModel):
    """
    Predict the mean target observed in the training data.

    This is the simplest deterministic benchmark and should generally
    be the first baseline established for each SmartPark target.
    """

    strategy = BaselineStrategy.MEAN

    def __init__(
        self,
        *,
        target_column: str,
        model_name: Optional[str] = None,
    ) -> None:

        super().__init__(
            target_column=target_column,
            model_name=(
                model_name
                or "mean_baseline"
            ),
        )

        self.mean_value: Optional[float] = None

    def fit(
        self,
        dataframe: pd.DataFrame,
    ) -> "MeanBaseline":

        target = self._validate_training_data(
            dataframe
        )

        self.mean_value = float(
            target.mean()
        )

        self._training_row_count = len(
            target
        )

        self._training_statistics = {
            "mean": self.mean_value,
            "min": float(target.min()),
            "max": float(target.max()),
            "std": float(target.std()),
            "median": float(target.median()),
        }

        self._is_fitted = True

        return self

    def predict(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.Series:

        if not self.is_fitted:
            raise BaselineModelNotFittedError(
                "MeanBaseline must be fitted before "
                "prediction."
            )

        if self.mean_value is None:
            raise BaselineModelError(
                "Mean baseline has no learned mean value."
            )

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise BaselineModelDataError(
                "Prediction data must be a pandas DataFrame."
            )

        return pd.Series(
            self.mean_value,
            index=dataframe.index,
            name=self.target_column,
            dtype=float,
        )


# ============================================================================
# Last-value baseline
# ============================================================================


class LastValueBaseline(BaseBaselineModel):
    """
    Predict using the most recent observed value from the training data.

    This is useful as a persistence benchmark for short-horizon
    forecasting.
    """

    strategy = BaselineStrategy.LAST_VALUE

    def __init__(
        self,
        *,
        target_column: str,
        model_name: Optional[str] = None,
    ) -> None:

        super().__init__(
            target_column=target_column,
            model_name=(
                model_name
                or "last_value_baseline"
            ),
        )

        self.last_value: Optional[float] = None

    def fit(
        self,
        dataframe: pd.DataFrame,
    ) -> "LastValueBaseline":

        target = self._validate_training_data(
            dataframe
        )

        self.last_value = float(
            target.iloc[-1]
        )

        self._training_row_count = len(
            target
        )

        self._training_statistics = {
            "last_value": self.last_value,
            "mean": float(target.mean()),
            "min": float(target.min()),
            "max": float(target.max()),
        }

        self._is_fitted = True

        return self

    def predict(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.Series:

        if not self.is_fitted:
            raise BaselineModelNotFittedError(
                "LastValueBaseline must be fitted before "
                "prediction."
            )

        if self.last_value is None:
            raise BaselineModelError(
                "Last-value baseline has no learned value."
            )

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise BaselineModelDataError(
                "Prediction data must be a pandas DataFrame."
            )

        return pd.Series(
            self.last_value,
            index=dataframe.index,
            name=self.target_column,
            dtype=float,
        )


# ============================================================================
# Seasonal naive baseline
# ============================================================================


class SeasonalNaiveBaseline(BaseBaselineModel):
    """
    Seasonal-naive baseline.

    For a chronological dataset, predictions are generated using a
    previously observed value at a configured lag.

    Example:
        lag=1
            previous observation

        lag=48
            previous same half-hour slot

        lag=336
            previous same half-hour slot one week earlier

    The model requires the prediction dataframe to contain the same
    target column because historical target values are used to construct
    the prediction.

    IMPORTANT:
    This baseline is intended primarily for diagnostic benchmarking.
    During proper production evaluation, the historical lookup must be
    constructed without using future observations.
    """

    strategy = BaselineStrategy.SEASONAL_NAIVE

    def __init__(
        self,
        *,
        target_column: str,
        lag: int,
        model_name: Optional[str] = None,
    ) -> None:

        if lag <= 0:
            raise BaselineModelDataError(
                "Seasonal-naive lag must be greater than zero."
            )

        super().__init__(
            target_column=target_column,
            model_name=(
                model_name
                or "seasonal_naive_baseline"
            ),
        )

        self.lag = int(lag)
        self._history: Optional[pd.Series] = None

    def fit(
        self,
        dataframe: pd.DataFrame,
    ) -> "SeasonalNaiveBaseline":

        target = self._validate_training_data(
            dataframe
        )

        self._history = target.copy()

        self._training_row_count = len(
            target
        )

        self._training_statistics = {
            "lag": self.lag,
            "mean": float(target.mean()),
            "min": float(target.min()),
            "max": float(target.max()),
        }

        self._is_fitted = True

        return self

    def predict(
        self,
        dataframe: pd.DataFrame,
    ) -> pd.Series:

        if not self.is_fitted:
            raise BaselineModelNotFittedError(
                "SeasonalNaiveBaseline must be fitted before "
                "prediction."
            )

        if self._history is None:
            raise BaselineModelError(
                "Seasonal-naive history is unavailable."
            )

        if not isinstance(
            dataframe,
            pd.DataFrame,
        ):
            raise BaselineModelDataError(
                "Prediction data must be a pandas DataFrame."
            )

        if self.target_column not in dataframe.columns:
            raise BaselineModelDataError(
                f"Target column '{self.target_column}' "
                "is required."
            )

        combined = pd.concat(
            [
                self._history,
                pd.to_numeric(
                    dataframe[self.target_column],
                    errors="coerce",
            ),
            ]
        )

        predictions = combined.shift(
            self.lag
        ).iloc[
            len(self._history):
        ]

        predictions.index = dataframe.index
        predictions.name = self.target_column

        return predictions.astype(float)


# ============================================================================
# Baseline factory
# ============================================================================


def create_baseline_model(
    *,
    strategy: BaselineStrategy | str,
    target_column: str,
    lag: Optional[int] = None,
    model_name: Optional[str] = None,
) -> BaseBaselineModel:
    """
    Factory for creating baseline models.
    """

    if isinstance(
        strategy,
        str,
    ):
        try:
            strategy = BaselineStrategy(
                strategy
            )
        except ValueError as exc:
            raise BaselineModelDataError(
                "Unsupported baseline strategy: "
                f"{strategy}"
            ) from exc

    if strategy == BaselineStrategy.MEAN:
        return MeanBaseline(
            target_column=target_column,
            model_name=model_name,
        )

    if strategy == BaselineStrategy.LAST_VALUE:
        return LastValueBaseline(
            target_column=target_column,
            model_name=model_name,
        )

    if strategy == BaselineStrategy.SEASONAL_NAIVE:
        if lag is None:
            raise BaselineModelDataError(
                "lag is required for seasonal_naive."
            )

        return SeasonalNaiveBaseline(
            target_column=target_column,
            lag=lag,
            model_name=model_name,
        )

    raise BaselineModelDataError(
        f"Unsupported baseline strategy: {strategy}"
    )


# ============================================================================
# Baseline comparison
# ============================================================================


def compare_baselines(
    results: Sequence[
        BaselineEvaluationResult
    ],
) -> pd.DataFrame:
    """
    Produce a comparison table for baseline evaluation results.
    """

    if not results:
        raise BaselineModelDataError(
            "At least one baseline result is required."
        )

    rows: list[dict[str, Any]] = []

    for result in results:
        rows.append(
            {
                "model_name": result.model_name,
                "strategy": result.strategy,
                "target_column": result.target_column,
                "mae": result.metrics.mae,
                "rmse": result.metrics.rmse,
                "r2": result.metrics.r2,
                "mape": result.metrics.mape,
                "sample_count": (
                    result.metrics.sample_count
                ),
            }
        )

    comparison = pd.DataFrame(
        rows
    )

    return comparison.sort_values(
        by="mae",
        ascending=True,
    ).reset_index(drop=True)


# ============================================================================
# Convenience runner
# ============================================================================


def run_baseline_benchmark(
    *,
    train_df: pd.DataFrame,
    validation_df: pd.DataFrame,
    target_column: str,
    include_last_value: bool = True,
    include_seasonal_naive: bool = False,
    seasonal_lag: Optional[int] = None,
) -> dict[str, Any]:
    """
    Train and evaluate the configured baseline models.

    Training uses ONLY train_df.

    Validation data is used ONLY for evaluation.

    Returns
    -------
    dict
        Contains fitted models, evaluation results and comparison table.
    """

    if not isinstance(
        train_df,
        pd.DataFrame,
    ):
        raise BaselineModelDataError(
            "train_df must be a pandas DataFrame."
        )

    if not isinstance(
        validation_df,
        pd.DataFrame,
    ):
        raise BaselineModelDataError(
            "validation_df must be a pandas DataFrame."
        )

    models: list[
        BaseBaselineModel
    ] = []

    mean_model = MeanBaseline(
        target_column=target_column
    )

    mean_model.fit(
        train_df
    )

    models.append(
        mean_model
    )

    if include_last_value:

        last_value_model = LastValueBaseline(
            target_column=target_column
        )

        last_value_model.fit(
            train_df
        )

        models.append(
            last_value_model
        )

    if include_seasonal_naive:

        if seasonal_lag is None:
            raise BaselineModelDataError(
                "seasonal_lag must be provided when "
                "include_seasonal_naive=True."
            )

        seasonal_model = SeasonalNaiveBaseline(
            target_column=target_column,
            lag=seasonal_lag,
        )

        seasonal_model.fit(
            train_df
        )

        models.append(
            seasonal_model
        )

    evaluation_results: list[
        BaselineEvaluationResult
    ] = []

    for model in models:

        result = model.evaluate(
            validation_df
        )

        evaluation_results.append(
            result
        )

    comparison = compare_baselines(
        evaluation_results
    )

    return {
        "target_column": target_column,
        "models": models,
        "results": evaluation_results,
        "comparison": comparison,
        "metadata": {
            "training_rows": len(train_df),
            "validation_rows": len(validation_df),
            "target_column": target_column,
            "target_leakage": False,
            "validation_targets_used_during_fit": False,
        },
    }


# ============================================================================
# Public exports
# ============================================================================


__all__ = [
    "BaselineModelError",
    "BaselineModelNotFittedError",
    "BaselineModelDataError",
    "BaselineStrategy",
    "RegressionMetrics",
    "BaselineEvaluationResult",
    "BaseBaselineModel",
    "MeanBaseline",
    "LastValueBaseline",
    "SeasonalNaiveBaseline",
    "create_baseline_model",
    "calculate_regression_metrics",
    "mean_absolute_error",
    "root_mean_squared_error",
    "r2_score",
    "mean_absolute_percentage_error",
    "compare_baselines",
    "run_baseline_benchmark",
]