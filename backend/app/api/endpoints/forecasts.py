"""
SmartPark AI - Production Forecast API

HTTP/API boundary for the production parking occupancy forecasting service.

Production flow:

    HTTP Request
        |
        v
    Forecast API
        |
        v
    ObservationRepository
        |
        v
    ProductionForecastService
        |
        +--> ProductionFeatureBuilder
        |
        +--> Frozen XGBoost TUNE_014
        |
        v
    ProductionForecastResult
        |
        v
    JSON Response

IMPORTANT
---------
This endpoint performs inference only.

It does NOT:

- train a model
- tune hyperparameters
- rebuild the feature pipeline
- modify occupancy observations
- modify the frozen model artifact
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Path,
)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db

from app.ml.production.observation_repository import (
    OccupancyObservationRepository,
)

from app.ml.production.service import (
    FeatureConstructionError,
    ForecastRequestError,
    ObservationDataError,
    PredictionValidationError,
    ProductionForecastResult,
    ProductionForecastService,
)


# ============================================================================
# Router
# ============================================================================

router = APIRouter(
    prefix="/forecasts",
    tags=["Production Forecasting"],
)


# ============================================================================
# Request DTO
# ============================================================================


class ForecastRequest(BaseModel):
    """
    Request for a production parking occupancy forecast.

    prediction_timestamp:
        Timestamp T at which the prediction is made.

    lookback_minutes:
        Historical observation window supplied to the production
        feature builder.

    The default is 1,440 minutes (24 hours), matching the current
    production integration contract.
    """

    model_config = ConfigDict(
        extra="forbid",
    )

    prediction_timestamp: datetime = Field(
        ...,
        description=(
            "Timezone-aware prediction timestamp T. "
            "The model forecasts occupancy at T + 30 minutes."
        ),
    )

    lookback_minutes: int = Field(
        default=1440,
        ge=1,
        le=10080,
        description=(
            "Historical observation lookback in minutes. "
            "Default: 1,440 minutes."
        ),
    )


# ============================================================================
# Response DTO
# ============================================================================


class ForecastResponse(BaseModel):
    """
    Production occupancy forecast API response.
    """

    model_config = ConfigDict(
        from_attributes=True,
    )

    facility_id: int

    prediction_timestamp: datetime

    forecast_timestamp: datetime

    forecast_horizon_minutes: int

    predicted_occupancy_rate: float = Field(
        ...,
        ge=0.0,
        le=1.0,
    )

    model_candidate: str

    target_column: str

    feature_count: int

    feature_information: str = (
        "available_at_or_before_prediction_timestamp"
    )

    inference_only: bool = True


# ============================================================================
# Dependencies
# ============================================================================


def get_observation_repository(
    db: AsyncSession = Depends(get_db),
) -> OccupancyObservationRepository:
    """
    Create the production observation repository.

    The repository owns database access.

    The forecast service does not receive an SQLAlchemy session directly.
    """

    return OccupancyObservationRepository(
        db,
    )


def get_production_forecast_service(
    repository: OccupancyObservationRepository = Depends(
        get_observation_repository,
    ),
) -> ProductionForecastService:
    """
    Create the production forecast service.

    The repository is adapted into the service's observation-provider
    interface.

    This keeps the ML service independent of SQLAlchemy.
    """

    async def observation_provider(
        facility_id: int,
        prediction_timestamp: datetime,
        lookback_minutes: int,
    ):
        """
        Production observation provider.

        Delegates exclusively to the existing repository.

        This operation is read-only.
        """

        return await repository.get_observations_for_forecast(
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
            lookback_minutes=lookback_minutes,
        )

    return ProductionForecastService(
        observation_provider=observation_provider,
    )


# ============================================================================
# Helpers
# ============================================================================


def _ensure_timezone_aware(
    timestamp: datetime,
) -> datetime:
    """
    Ensure the API receives a timezone-aware timestamp.

    We intentionally do NOT silently assign UTC to a naive timestamp.

    A production prediction timestamp must explicitly identify its timezone.
    """

    if timestamp.tzinfo is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "prediction_timestamp must be timezone-aware. "
                "Use an ISO-8601 timestamp with a timezone, "
                "for example: 2016-12-19T16:30:00Z."
            ),
        )

    return timestamp.astimezone(
        timezone.utc,
    )


def _result_to_response(
    result: ProductionForecastResult,
) -> ForecastResponse:
    """
    Convert the production service result into the public API DTO.

    The exact fields are taken from the production result contract.
    """

    return ForecastResponse(
        facility_id=result.facility_id,
        prediction_timestamp=result.prediction_timestamp,
        forecast_timestamp=result.forecast_timestamp,
        forecast_horizon_minutes=result.forecast_horizon_minutes,
        predicted_occupancy_rate=result.predicted_occupancy_rate,
        model_candidate=result.model_candidate,
        target_column=result.target_column,
        feature_count=result.feature_count,
    )


# ============================================================================
# Production Forecast Endpoint
# ============================================================================


@router.post(
    "/facilities/{facility_id}",
    response_model=ForecastResponse,
    status_code=200,
    summary="Generate a 30-minute parking occupancy forecast",
    description=(
        "Generate a production parking occupancy forecast using the "
        "frozen Birmingham XGBoost model. "
        "The prediction is made at T and forecasts occupancy at T + 30 minutes. "
        "This endpoint performs inference only and does not modify database "
        "observations or model artifacts."
    ),
)
async def generate_forecast(
    request: ForecastRequest,
    facility_id: int = Path(
        ...,
        ge=1,
        description="Canonical parking facility ID.",
    ),
    service: ProductionForecastService = Depends(
        get_production_forecast_service,
    ),
) -> ForecastResponse:
    """
    Generate a production occupancy forecast.

    Production contract:

        Prediction timestamp = T
        Forecast timestamp  = T + 30 minutes

    Historical observations are retrieved through the existing
    OccupancyObservationRepository.

    No database writes are performed.
    """

    prediction_timestamp = _ensure_timezone_aware(
        request.prediction_timestamp,
    )

    try:

        result = await service.forecast(
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
            lookback_minutes=request.lookback_minutes,
        )

        return _result_to_response(
            result,
        )

    # ------------------------------------------------------------------
    # Invalid request
    # ------------------------------------------------------------------

    except ForecastRequestError as exc:

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    # ------------------------------------------------------------------
    # Insufficient/invalid production observations
    # ------------------------------------------------------------------

    except ObservationDataError as exc:

        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    # ------------------------------------------------------------------
    # Production feature construction failure
    # ------------------------------------------------------------------

    except FeatureConstructionError as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Production forecast feature construction failed."
            ),
        ) from exc

    # ------------------------------------------------------------------
    # Frozen model inference/prediction validation failure
    # ------------------------------------------------------------------

    except PredictionValidationError as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Production forecast inference failed."
            ),
        ) from exc

    # ------------------------------------------------------------------
    # Unexpected failure
    # ------------------------------------------------------------------

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Unexpected error while generating production forecast."
            ),
        ) from exc


# ============================================================================
# Router Health / Contract Endpoint
# ============================================================================


@router.get(
    "/health",
    tags=["Production Forecasting"],
    summary="Production forecasting service health",
)
async def forecast_health(
    service: ProductionForecastService = Depends(
        get_production_forecast_service,
    ),
) -> dict[str, Any]:
    """
    Return the production forecast service diagnostic state.

    This endpoint does not perform a prediction and does not write data.
    """

    try:

        diagnostics = service.diagnostics()

        return {
            "application": "SmartPark AI",
            "component": "Production Forecasting",
            "status": diagnostics.get(
                "status",
                "unknown",
            ),
            "diagnostics": diagnostics,
        }

    except Exception as exc:

        raise HTTPException(
            status_code=500,
            detail=(
                "Unable to retrieve production forecasting health."
            ),
        ) from exc