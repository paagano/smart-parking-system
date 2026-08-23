"""
SmartPark AI - Production ML Forecast Service.

This module is the production orchestration layer for the frozen
XGBoost forecasting model.

Production flow
---------------

    occupancy_observations
            |
            v
    observation retrieval
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
        30-minute forecast


Responsibilities
----------------
- Orchestrate production feature construction and inference.
- Enforce the frozen XGBoost production contract.
- Validate prediction timestamps and forecast horizon.
- Validate the final prediction range.
- Provide a clean service interface for the API layer.
- Remain independent of FastAPI and SQLAlchemy session management.

Non-responsibilities
--------------------
- Model training.
- Hyperparameter tuning.
- Feature pipeline rebuilding.
- Model artifact creation.
- Direct database session management.
- Dataset modification.

The frozen model artifact is loaded by:

    app.ml.production.inference.ProductionXGBoostInference
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

import pandas as pd

from app.ml.production.feature_builder import (
    ProductionFeatureBuilder,
    ProductionFeatureBuilderError,
    ProductionFeatureResult,
)
from app.ml.production.inference import (
    ProductionArtifactError,
    ProductionInferenceError,
    ProductionXGBoostInference,
)


# ============================================================
# Constants
# ============================================================

TARGET_COLUMN = "target_occupancy_rate_30m"

FORECAST_HORIZON_MINUTES = 30

EXPECTED_FEATURE_COUNT = 296

MIN_PREDICTION = 0.0
MAX_PREDICTION = 1.0


# ============================================================
# Exceptions
# ============================================================


class ProductionForecastServiceError(RuntimeError):
    """Base exception for production forecast service failures."""


class ObservationDataError(ProductionForecastServiceError):
    """Raised when production observations are invalid or insufficient."""


class FeatureConstructionError(ProductionForecastServiceError):
    """Raised when production feature construction fails."""


class PredictionValidationError(ProductionForecastServiceError):
    """Raised when the generated prediction violates the contract."""


class ForecastRequestError(ProductionForecastServiceError):
    """Raised when a forecast request is invalid."""


# ============================================================
# Result DTO
# ============================================================


@dataclass(frozen=True)
class ProductionForecastResult:
    """
    Immutable production forecast result.

    This object represents the output of the complete production
    ML inference flow.

    Attributes
    ----------
    facility_id:
        SmartPark parking facility identifier.

    prediction_timestamp:
        The timestamp T at which the prediction is made.

    forecast_timestamp:
        The timestamp T + 30 minutes being predicted.

    predicted_occupancy_rate:
        XGBoost predicted occupancy rate in [0, 1].

    predicted_occupancy_percentage:
        Same prediction expressed as a percentage.

    model_candidate:
        Frozen model candidate, expected to be TUNE_014.

    target_column:
        Production target being predicted.

    forecast_horizon_minutes:
        Forecast horizon, expected to be 30 minutes.

    feature_count:
        Number of features supplied to the model.

    observation_count:
        Number of observations used to construct the production
        feature vector.

    source:
        Optional source/provenance identifier.

    generated_at:
        Timestamp at which the forecast was generated.
    """

    facility_id: int
    prediction_timestamp: datetime
    forecast_timestamp: datetime

    predicted_occupancy_rate: float
    predicted_occupancy_percentage: float

    model_candidate: str
    target_column: str
    forecast_horizon_minutes: int
    feature_count: int

    observation_count: int

    source: str | None
    generated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON/API-friendly representation."""

        payload = asdict(self)

        payload["prediction_timestamp"] = (
            self.prediction_timestamp.isoformat()
        )

        payload["forecast_timestamp"] = (
            self.forecast_timestamp.isoformat()
        )

        payload["generated_at"] = (
            self.generated_at.isoformat()
        )

        return payload


# ============================================================
# Observation Provider Contract
# ============================================================


ObservationProvider = Callable[
    [int, datetime, int],
    pd.DataFrame,
]


# ============================================================
# Production Forecast Service
# ============================================================


class ProductionForecastService:
    """
    Production orchestration service for SmartPark AI forecasting.

    The service coordinates:

        observation provider
            ->
        production feature builder
            ->
        frozen XGBoost inference

    The database implementation is deliberately injected through
    ``observation_provider``.

    This prevents the ML service from becoming tightly coupled to
    SQLAlchemy/FastAPI infrastructure.

    Example
    -------

        service = ProductionForecastService(
            inference=ProductionXGBoostInference(),
            feature_builder=ProductionFeatureBuilder(),
            observation_provider=my_provider,
        )

        result = await service.forecast(
            facility_id=1,
            prediction_timestamp=datetime.now(timezone.utc),
        )

    Notes
    -----
    The provider may be synchronous or asynchronous.

    The expected provider signature is:

        provider(
            facility_id,
            prediction_timestamp,
            lookback_minutes,
        ) -> pandas.DataFrame

    The resulting DataFrame must contain the raw observation fields
    required by ProductionFeatureBuilder.
    """

    def __init__(
        self,
        *,
        inference: ProductionXGBoostInference | None = None,
        feature_builder: ProductionFeatureBuilder | None = None,
        observation_provider: ObservationProvider | None = None,
    ) -> None:
        """
        Initialise the production forecast service.

        Parameters
        ----------
        inference:
            Frozen production XGBoost inference component.

        feature_builder:
            Production feature builder.

        observation_provider:
            Callable responsible for retrieving observations from
            ``occupancy_observations``.
        """

        self._inference = (
            inference
            if inference is not None
            else ProductionXGBoostInference()
        )

        self._feature_builder = (
            feature_builder
            if feature_builder is not None
            else ProductionFeatureBuilder()
        )

        self._observation_provider = observation_provider

    # ========================================================
    # Public API
    # ========================================================

    async def forecast(
        self,
        *,
        facility_id: int,
        prediction_timestamp: datetime,
        lookback_minutes: int | None = None,
        source: str | None = None,
    ) -> ProductionForecastResult:
        """
        Generate a production 30-minute occupancy forecast.

        Parameters
        ----------
        facility_id:
            Parking facility to forecast.

        prediction_timestamp:
            Prediction timestamp T.

        lookback_minutes:
            Historical observation window required by the feature
            contract. If omitted, the service derives it from the
            feature requirements.

        source:
            Optional observation source/provenance identifier.

        Returns
        -------
        ProductionForecastResult
            Validated production forecast.

        Raises
        ------
        ForecastRequestError
            If the request is invalid.

        ObservationDataError
            If insufficient observations are available.

        FeatureConstructionError
            If feature construction fails.

        PredictionValidationError
            If the resulting prediction violates the production
            contract.
        """

        # ----------------------------------------------------
        # 1. Validate request
        # ----------------------------------------------------

        self._validate_forecast_request(
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
            lookback_minutes=lookback_minutes,
        )

        # ----------------------------------------------------
        # 2. Determine required observation history
        # ----------------------------------------------------

        effective_lookback = (
            lookback_minutes
            if lookback_minutes is not None
            else self.required_lookback_minutes()
        )

        # ----------------------------------------------------
        # 3. Load operational observations
        # ----------------------------------------------------

        observations = await self._load_observations(
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
            lookback_minutes=effective_lookback,
        )

        # ----------------------------------------------------
        # 4. Validate observations
        # ----------------------------------------------------

        self._validate_observations(
            observations=observations,
            prediction_timestamp=prediction_timestamp,
        )

        # ----------------------------------------------------
        # 5. Build production features
        #
        # IMPORTANT:
        #
        # ProductionFeatureBuilder.build() returns a
        # ProductionFeatureResult, NOT a DataFrame.
        #
        # We must extract:
        #
        #     result.inference_dataframe
        #
        # and:
        #
        #     result.feature_columns
        #
        # before passing the data to XGBoost.
        # ----------------------------------------------------

        feature_result = self._build_features(
            observations=observations,
            prediction_timestamp=prediction_timestamp,
        )

        # ----------------------------------------------------
        # 6. Extract the exact inference matrix
        #
        # The inference engine expects:
        #
        #     - exactly one row
        #     - exactly the frozen 296 features
        #     - frozen feature ordering
        #
        # ProductionXGBoostInference.prepare_features()
        # subsequently applies the frozen categorical mappings
        # and performs its own final validation.
        # ----------------------------------------------------

        features = self._extract_inference_features(
            feature_result=feature_result,
        )

        # ----------------------------------------------------
        # 7. Run frozen XGBoost inference
        # ----------------------------------------------------

        prediction = self._run_inference(
            features=features,
        )

        # ----------------------------------------------------
        # 8. Build validated production result
        # ----------------------------------------------------

        return self._build_result(
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
            prediction=prediction,
            observation_count=len(observations),
            source=source,
            feature_result=feature_result,
        )

    # ========================================================
    # Convenience API
    # ========================================================

    def model_info(self) -> dict[str, Any]:
        """
        Return frozen production model information.
        """

        return self._inference.model_info()

    def required_lookback_minutes(self) -> int:
        """
        Return the minimum observation history required by the
        production feature contract.

        The frozen feature contract contains features reaching back
        to 1 day through lag and rolling features.

        Therefore production inference requires at least 24 hours
        of historical observations.

        We use 24 hours as the baseline production window.
        """

        return 24 * 60

    def health_check(self) -> dict[str, Any]:
        """
        Return production ML service health information.

        This method does not access the database and does not
        perform model training.
        """

        try:
            info = self._inference.model_info()

            feature_count = int(
                info.get(
                    "feature_count",
                    0,
                )
            )

            loaded = bool(
                info.get(
                    "loaded",
                    False,
                )
            )

            candidate = info.get(
                "model_candidate"
            )

            return {
                "status": (
                    "healthy"
                    if (
                        loaded
                        and feature_count
                        == EXPECTED_FEATURE_COUNT
                    )
                    else "unhealthy"
                ),
                "model_loaded": loaded,
                "model_candidate": candidate,
                "target_column": info.get(
                    "target_column"
                ),
                "forecast_horizon_minutes": info.get(
                    "forecast_horizon_minutes"
                ),
                "feature_count": feature_count,
                "expected_feature_count": (
                    EXPECTED_FEATURE_COUNT
                ),
                "training_performed": bool(
                    info.get(
                        "training_performed",
                        False,
                    )
                ),
                "hyperparameter_tuning_performed": bool(
                    info.get(
                        "hyperparameter_tuning_performed",
                        False,
                    )
                ),
                "feature_pipeline_rebuilt": bool(
                    info.get(
                        "feature_pipeline_rebuilt",
                        False,
                    )
                ),
                "observation_provider_configured": (
                    self._observation_provider is not None
                ),
            }

        except Exception as exc:
            return {
                "status": "unhealthy",
                "model_loaded": False,
                "error": str(exc),
            }

    # ========================================================
    # Diagnostics
    # ========================================================

    def diagnostics(self) -> dict[str, Any]:
        """
        Return a compact production service diagnostic payload.
        """

        model_info = self._inference.model_info()

        return {
            "service": (
                "ProductionForecastService"
            ),
            "status": "ready",
            "target_column": TARGET_COLUMN,
            "forecast_horizon_minutes": (
                FORECAST_HORIZON_MINUTES
            ),
            "expected_feature_count": (
                EXPECTED_FEATURE_COUNT
            ),
            "required_lookback_minutes": (
                self.required_lookback_minutes()
            ),
            "model": model_info,
            "observation_provider_configured": (
                self._observation_provider is not None
            ),
            "training_performed": False,
            "hyperparameter_tuning_performed": False,
            "feature_pipeline_rebuilt": False,
        }

    # ========================================================
    # Observation Loading
    # ========================================================

    async def _load_observations(
        self,
        *,
        facility_id: int,
        prediction_timestamp: datetime,
        lookback_minutes: int,
    ) -> pd.DataFrame:
        """
        Retrieve observations from the configured provider.

        The provider is intentionally kept outside this service so
        that SQLAlchemy session management remains the responsibility
        of the application/repository layer.
        """

        if self._observation_provider is None:
            raise ObservationDataError(
                "No observation provider has been configured. "
                "ProductionForecastService requires an observation "
                "provider connected to occupancy_observations."
            )

        try:
            result = self._observation_provider(
                facility_id,
                prediction_timestamp,
                lookback_minutes,
            )

            # Support both synchronous and asynchronous providers.
            if hasattr(
                result,
                "__await__",
            ):
                result = await result

        except Exception as exc:
            raise ObservationDataError(
                "Failed to load production occupancy observations "
                f"for facility_id={facility_id}: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if result is None:
            raise ObservationDataError(
                "Observation provider returned None."
            )

        if not isinstance(
            result,
            pd.DataFrame,
        ):
            raise ObservationDataError(
                "Observation provider must return a pandas "
                "DataFrame."
            )

        return result

    # ========================================================
    # Observation Validation
    # ========================================================

    @staticmethod
    def _validate_observations(
        *,
        observations: pd.DataFrame,
        prediction_timestamp: datetime,
    ) -> None:
        """
        Validate observations before feature construction.

        Production inference must never use observations occurring
        after T.
        """

        if observations.empty:
            raise ObservationDataError(
                "No occupancy observations are available for "
                "production inference."
            )

        required_columns = {
            "observed_at",
            "total_spaces",
            "occupied_spaces",
            "available_spaces",
            "occupancy_rate",
        }

        missing = sorted(
            required_columns
            - set(observations.columns)
        )

        if missing:
            raise ObservationDataError(
                "Production observations are missing required "
                f"columns: {missing}"
            )

        # ----------------------------------------------------
        # Timestamp validation
        # ----------------------------------------------------

        timestamps = pd.to_datetime(
            observations["observed_at"],
            utc=True,
            errors="coerce",
        )

        if timestamps.isna().any():
            raise ObservationDataError(
                "Production observations contain invalid "
                "observed_at timestamps."
            )

        prediction_ts = pd.Timestamp(
            prediction_timestamp
        )

        if prediction_ts.tzinfo is None:
            prediction_ts = prediction_ts.tz_localize(
                "UTC"
            )
        else:
            prediction_ts = prediction_ts.tz_convert(
                "UTC"
            )

        future_mask = (
            timestamps > prediction_ts
        )

        if future_mask.any():
            future_count = int(
                future_mask.sum()
            )

            raise ObservationDataError(
                "Production observation contract violated: "
                f"{future_count} observation(s) occur after "
                f"prediction timestamp T={prediction_timestamp}."
            )

        # ----------------------------------------------------
        # Basic numeric integrity checks
        # ----------------------------------------------------

        numeric_columns = [
            "total_spaces",
            "occupied_spaces",
            "available_spaces",
            "occupancy_rate",
        ]

        for column in numeric_columns:

            values = pd.to_numeric(
                observations[column],
                errors="coerce",
            )

            if values.isna().any():
                raise ObservationDataError(
                    f"Observation column '{column}' contains "
                    "non-numeric or null values."
                )

        total_spaces = pd.to_numeric(
            observations["total_spaces"]
        )

        occupied_spaces = pd.to_numeric(
            observations["occupied_spaces"]
        )

        available_spaces = pd.to_numeric(
            observations["available_spaces"]
        )

        occupancy_rate = pd.to_numeric(
            observations["occupancy_rate"]
        )

        # ----------------------------------------------------
        # Capacity validation
        # ----------------------------------------------------

        if (
            total_spaces <= 0
        ).any():
            raise ObservationDataError(
                "Production observations contain "
                "total_spaces <= 0."
            )

        if (
            occupied_spaces < 0
        ).any():
            raise ObservationDataError(
                "Production observations contain negative "
                "occupied_spaces."
            )

        if (
            available_spaces < 0
        ).any():
            raise ObservationDataError(
                "Production observations contain negative "
                "available_spaces."
            )

        # ----------------------------------------------------
        # Space balance
        # ----------------------------------------------------

        if (
            occupied_spaces
            + available_spaces
            != total_spaces
        ).any():
            raise ObservationDataError(
                "Production observation space-balance contract "
                "violated."
            )

        # ----------------------------------------------------
        # Occupancy rate range
        # ----------------------------------------------------

        if (
            (occupancy_rate < 0)
            | (occupancy_rate > 1)
        ).any():
            raise ObservationDataError(
                "Production observations contain occupancy_rate "
                "outside [0, 1]."
            )

    # ========================================================
    # Feature Construction
    # ========================================================

    def _build_features(
        self,
        *,
        observations: pd.DataFrame,
        prediction_timestamp: datetime,
    ) -> ProductionFeatureResult:
        """
        Build the frozen 296-feature production matrix.

        IMPORTANT
        ---------
        ProductionFeatureBuilder.build() returns a
        ProductionFeatureResult.

        The actual inference matrix is available through:

            result.inference_dataframe

        while the exact frozen model feature names are available
        through:

            result.feature_columns
        """

        try:

            feature_result = self._feature_builder.build(
                observations,
                inference_at=prediction_timestamp,
            )

        except ProductionFeatureBuilderError as exc:
            raise FeatureConstructionError(
                "Failed to build production inference features: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        except Exception as exc:
            raise FeatureConstructionError(
                "Unexpected error during production feature construction: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        if not isinstance(
            feature_result,
            ProductionFeatureResult,
        ):
            raise FeatureConstructionError(
                "ProductionFeatureBuilder.build() must return "
                "ProductionFeatureResult."
            )

        if feature_result.inference_dataframe.empty:
            raise FeatureConstructionError(
                "ProductionFeatureBuilder returned an empty "
                "inference dataframe."
            )

        if not feature_result.feature_columns:
            raise FeatureConstructionError(
                "ProductionFeatureBuilder returned no model "
                "feature columns."
            )

        if len(feature_result.feature_columns) != (
            EXPECTED_FEATURE_COUNT
        ):
            raise FeatureConstructionError(
                "Production feature count mismatch. "
                f"Expected {EXPECTED_FEATURE_COUNT}, "
                f"received {len(feature_result.feature_columns)}."
            )

        return feature_result

    # ========================================================
    # Inference Feature Extraction
    # ========================================================

    @staticmethod
    def _extract_inference_features(
        *,
        feature_result: ProductionFeatureResult,
    ) -> pd.DataFrame:
        """
        Extract the exact single-row inference matrix.

        The ProductionFeatureBuilder deliberately returns both:

            dataframe
                Complete production feature dataframe.

            inference_dataframe
                Row(s) intended for model inference.

        The frozen XGBoost inference layer requires exactly one
        inference row.

        Therefore this method:

            1. Uses inference_dataframe.
            2. Selects only feature_columns.
            3. Preserves the builder's feature ordering.
            4. Validates that exactly one row is supplied.
            5. Validates that exactly 296 model features exist.
        """

        inference_dataframe = (
            feature_result.inference_dataframe
        )

        feature_columns = list(
            feature_result.feature_columns
        )

        if inference_dataframe.empty:
            raise FeatureConstructionError(
                "Inference dataframe is empty."
            )

        if len(inference_dataframe) != 1:
            raise FeatureConstructionError(
                "Production inference requires exactly one "
                "inference row. "
                f"Received {len(inference_dataframe)} rows."
            )

        missing_features = [
            column
            for column in feature_columns
            if column not in inference_dataframe.columns
        ]

        if missing_features:
            raise FeatureConstructionError(
                "Production inference dataframe is missing "
                f"registered model features: {missing_features}"
            )

        features = inference_dataframe[
            feature_columns
        ].copy()

        if features.shape[1] != (
            EXPECTED_FEATURE_COUNT
        ):
            raise FeatureConstructionError(
                "Production inference feature count mismatch. "
                f"Expected {EXPECTED_FEATURE_COUNT}, "
                f"received {features.shape[1]}."
            )

        return features

    # ========================================================
    # Inference
    # ========================================================

    def _run_inference(
        self,
        *,
        features: pd.DataFrame,
    ) -> float:
        """
        Execute frozen XGBoost inference.
        """

        if features.shape[0] != 1:
            raise PredictionValidationError(
                "Production XGBoost inference requires exactly "
                f"one row. Received {features.shape[0]}."
            )

        if features.shape[1] != (
            EXPECTED_FEATURE_COUNT
        ):
            raise PredictionValidationError(
                "Production feature count mismatch. "
                f"Expected {EXPECTED_FEATURE_COUNT}, "
                f"received {features.shape[1]}."
            )

        try:

            prediction = self._inference.predict(
                features
            )

        except (
            ProductionArtifactError,
            ProductionInferenceError,
        ) as exc:

            raise PredictionValidationError(
                "Frozen XGBoost production inference failed: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        except Exception as exc:

            raise PredictionValidationError(
                "Unexpected error during frozen XGBoost "
                "production inference: "
                f"{type(exc).__name__}: {exc}"
            ) from exc

        # ----------------------------------------------------
        # Normalize supported inference return forms
        # ----------------------------------------------------

        if isinstance(
            prediction,
            (list, tuple),
        ):

            if not prediction:
                raise PredictionValidationError(
                    "XGBoost inference returned no prediction."
                )

            prediction = prediction[0]

        elif isinstance(
            prediction,
            pd.Series,
        ):

            if prediction.empty:
                raise PredictionValidationError(
                    "XGBoost inference returned an empty "
                    "prediction series."
                )

            prediction = prediction.iloc[0]

        elif isinstance(
            prediction,
            pd.DataFrame,
        ):

            if prediction.empty:
                raise PredictionValidationError(
                    "XGBoost inference returned an empty "
                    "prediction DataFrame."
                )

            prediction = prediction.iloc[0, 0]

        # ----------------------------------------------------
        # Convert to float
        # ----------------------------------------------------

        try:

            prediction_value = float(
                prediction
            )

        except (
            TypeError,
            ValueError,
        ) as exc:

            raise PredictionValidationError(
                "XGBoost inference returned a non-numeric "
                "prediction."
            ) from exc

        # ----------------------------------------------------
        # Finite check
        # ----------------------------------------------------

        if not pd.notna(
            prediction_value
        ):
            raise PredictionValidationError(
                "XGBoost prediction is NaN or null."
            )

        # ----------------------------------------------------
        # Range contract
        # ----------------------------------------------------

        if not (
            MIN_PREDICTION
            <= prediction_value
            <= MAX_PREDICTION
        ):
            raise PredictionValidationError(
                "XGBoost prediction violates occupancy-rate "
                f"range [0, 1]: {prediction_value}"
            )

        return prediction_value

    # ========================================================
    # Result Construction
    # ========================================================

    def _build_result(
        self,
        *,
        facility_id: int,
        prediction_timestamp: datetime,
        prediction: float,
        observation_count: int,
        source: str | None,
        feature_result: ProductionFeatureResult,
    ) -> ProductionForecastResult:
        """
        Construct the validated production forecast result.
        """

        forecast_timestamp = (
            prediction_timestamp
            + timedelta(
                minutes=FORECAST_HORIZON_MINUTES
            )
        )

        model_info = self._inference.model_info()

        model_candidate = str(
            model_info.get(
                "model_candidate",
                "UNKNOWN",
            )
        )

        feature_count = int(
            model_info.get(
                "feature_count",
                0,
            )
        )

        target_column = str(
            model_info.get(
                "target_column",
                TARGET_COLUMN,
            )
        )

        forecast_horizon = int(
            model_info.get(
                "forecast_horizon_minutes",
                FORECAST_HORIZON_MINUTES,
            )
        )

        # ----------------------------------------------------
        # Frozen model contract
        # ----------------------------------------------------

        if feature_count != (
            EXPECTED_FEATURE_COUNT
        ):
            raise PredictionValidationError(
                "Frozen model feature contract mismatch. "
                f"Expected {EXPECTED_FEATURE_COUNT}, "
                f"received {feature_count}."
            )

        if target_column != (
            TARGET_COLUMN
        ):
            raise PredictionValidationError(
                "Frozen model target contract mismatch. "
                f"Expected '{TARGET_COLUMN}', "
                f"received '{target_column}'."
            )

        if forecast_horizon != (
            FORECAST_HORIZON_MINUTES
        ):
            raise PredictionValidationError(
                "Frozen model forecast horizon mismatch. "
                f"Expected {FORECAST_HORIZON_MINUTES} minutes, "
                f"received {forecast_horizon}."
            )

        # ----------------------------------------------------
        # Builder contract
        # ----------------------------------------------------

        builder_feature_count = len(
            feature_result.feature_columns
        )

        if builder_feature_count != (
            EXPECTED_FEATURE_COUNT
        ):
            raise PredictionValidationError(
                "ProductionFeatureBuilder feature contract "
                "mismatch. "
                f"Expected {EXPECTED_FEATURE_COUNT}, "
                f"received {builder_feature_count}."
            )

        # ----------------------------------------------------
        # Build result
        # ----------------------------------------------------

        return ProductionForecastResult(
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
            forecast_timestamp=forecast_timestamp,
            predicted_occupancy_rate=prediction,
            predicted_occupancy_percentage=(
                prediction * 100.0
            ),
            model_candidate=model_candidate,
            target_column=target_column,
            forecast_horizon_minutes=forecast_horizon,
            feature_count=feature_count,
            observation_count=observation_count,
            source=source,
            generated_at=datetime.now(
                tz=prediction_timestamp.tzinfo
            ),
        )

    # ========================================================
    # Request Validation
    # ========================================================

    @staticmethod
    def _validate_forecast_request(
        *,
        facility_id: int,
        prediction_timestamp: datetime,
        lookback_minutes: int | None,
    ) -> None:
        """
        Validate a production forecast request.
        """

        if not isinstance(
            facility_id,
            int,
        ):
            raise ForecastRequestError(
                "facility_id must be an integer."
            )

        if facility_id <= 0:
            raise ForecastRequestError(
                "facility_id must be greater than zero."
            )

        if not isinstance(
            prediction_timestamp,
            datetime,
        ):
            raise ForecastRequestError(
                "prediction_timestamp must be a datetime."
            )

        if prediction_timestamp.tzinfo is None:
            raise ForecastRequestError(
                "prediction_timestamp must be timezone-aware."
            )

        if lookback_minutes is not None:

            if not isinstance(
                lookback_minutes,
                int,
            ):
                raise ForecastRequestError(
                    "lookback_minutes must be an integer."
                )

            if lookback_minutes <= 0:
                raise ForecastRequestError(
                    "lookback_minutes must be greater than zero."
                )

            minimum_lookback = (
                24 * 60
            )

            if lookback_minutes < minimum_lookback:
                raise ForecastRequestError(
                    "lookback_minutes is too small for the "
                    "frozen 296-feature production contract. "
                    f"Minimum expected lookback is "
                    f"{minimum_lookback} minutes."
                )


# ============================================================
# Factory
# ============================================================


def create_production_forecast_service(
    *,
    observation_provider: ObservationProvider | None = None,
) -> ProductionForecastService:
    """
    Create the standard SmartPark production forecast service.

    The factory keeps application wiring simple while allowing
    tests to inject a controlled observation provider.
    """

    return ProductionForecastService(
        inference=ProductionXGBoostInference(),
        feature_builder=ProductionFeatureBuilder(),
        observation_provider=observation_provider,
    )


# ============================================================
# Public exports
# ============================================================


__all__ = [
    "TARGET_COLUMN",
    "FORECAST_HORIZON_MINUTES",
    "EXPECTED_FEATURE_COUNT",
    "ProductionForecastService",
    "ProductionForecastResult",
    "ProductionForecastServiceError",
    "ObservationDataError",
    "FeatureConstructionError",
    "PredictionValidationError",
    "ForecastRequestError",
    "create_production_forecast_service",
]