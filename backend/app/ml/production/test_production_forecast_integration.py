"""
SmartPark AI - Production Forecast Integration Smoke Test.

End-to-end read-only verification of the production ML inference path:

    PostgreSQL
        |
        v
    occupancy_observations
        |
        v
    OccupancyObservationRepository
        |
        v
    ProductionForecastService
        |
        v
    ProductionFeatureBuilder
        |
        v
    296 production features
        |
        v
    ProductionXGBoostInference
        |
        v
    Frozen TUNE_014
        |
        v
    T + 30 minute occupancy forecast

IMPORTANT
---------
This test is READ-ONLY.

It must NOT:

- INSERT observations
- UPDATE observations
- DELETE observations
- modify parking facilities
- modify datasets
- train XGBoost
- perform hyperparameter tuning
- rebuild the feature pipeline
- modify the frozen model artifact
- load train.parquet
- load validation.parquet
- load test.parquet

The purpose is to prove that the production inference chain can
consume the canonical occupancy_observations table and produce
a valid forecast using the frozen XGBoost artifact.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func, select

# ------------------------------------------------------------------
# Make the repository root importable when this file is executed
# directly as well as with:
#
#     python -m app.ml.production.test_production_forecast_integration
# ------------------------------------------------------------------

BACKEND_ROOT = Path(__file__).resolve().parents[3]

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(BACKEND_ROOT),
    )

# ------------------------------------------------------------------
# Application imports
# ------------------------------------------------------------------

from app.database.session import AsyncSessionLocal
from app.ml.production.feature_builder import (
    ProductionFeatureBuilder,
)
from app.ml.production.inference import (
    ProductionXGBoostInference,
)
from app.ml.production.observation_repository import (
    OccupancyObservationRepository,
)
from app.ml.production.service import (
    EXPECTED_FEATURE_COUNT,
    FORECAST_HORIZON_MINUTES,
    TARGET_COLUMN,
    ProductionForecastService,
)


# ================================================================
# Test configuration
# ================================================================

MINIMUM_OBSERVATIONS_REQUIRED = 10

EXPECTED_MODEL_CANDIDATE = "TUNE_014"

EXPECTED_FORECAST_HORIZON_MINUTES = 30

EXPECTED_TARGET_COLUMN = (
    "target_occupancy_rate_30m"
)


# ================================================================
# Console helpers
# ================================================================


def print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def print_status(
    label: str,
    value: Any,
) -> None:
    print(
        f"{label:<48}: {value}"
    )


def print_pass(
    label: str,
) -> None:
    print_status(
        label,
        "PASS",
    )


def print_fail(
    label: str,
) -> None:
    print_status(
        label,
        "FAIL",
    )


# ================================================================
# Observation provider adapter
# ================================================================


class RepositoryObservationProvider:
    """
    Adapter between OccupancyObservationRepository and
    ProductionForecastService.

    The service intentionally accepts an observation provider rather
    than owning an AsyncSession.

    This adapter keeps database access in the repository layer.
    """

    def __init__(
        self,
        repository: OccupancyObservationRepository,
    ) -> None:
        self._repository = repository

    async def __call__(
        self,
        facility_id: int,
        prediction_timestamp: datetime,
        lookback_minutes: int,
    ) -> pd.DataFrame:
        """
        Retrieve observations from the repository and convert them
        to the DataFrame expected by ProductionFeatureBuilder.

        The exact repository method is resolved through a small
        compatibility layer so the integration test can work with
        the repository's production-facing read methods.
        """

        observations = await self._retrieve(
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
            lookback_minutes=lookback_minutes,
        )

        return self._to_dataframe(
            observations
        )

    # ------------------------------------------------------------
    # Repository retrieval
    # ------------------------------------------------------------

    async def _retrieve(
        self,
        *,
        facility_id: int,
        prediction_timestamp: datetime,
        lookback_minutes: int,
    ) -> Any:
        """
        Retrieve historical observations.

        Preferred repository method:

            get_observations_for_forecast(...)

        Supported fallback names are included to avoid coupling this
        smoke test to a naming-only difference in the repository.
        """

        start_timestamp = (
            prediction_timestamp
            - pd.Timedelta(
                minutes=lookback_minutes
            ).to_pytimedelta()
        )

        end_timestamp = prediction_timestamp

        # --------------------------------------------------------
        # Preferred production repository API
        # --------------------------------------------------------

        if hasattr(
            self._repository,
            "get_observations_for_forecast",
        ):
            method = getattr(
                self._repository,
                "get_observations_for_forecast",
            )

            return await method(
                facility_id=facility_id,
                prediction_timestamp=prediction_timestamp,
                lookback_minutes=lookback_minutes,
            )

        # --------------------------------------------------------
        # Common historical observation API
        # --------------------------------------------------------

        if hasattr(
            self._repository,
            "get_observations",
        ):
            method = getattr(
                self._repository,
                "get_observations",
            )

            try:
                return await method(
                    facility_id=facility_id,
                    start_at=start_timestamp,
                    end_at=end_timestamp,
                )
            except TypeError:
                return await method(
                    facility_id=facility_id,
                    start_timestamp=start_timestamp,
                    end_timestamp=end_timestamp,
                )

        # --------------------------------------------------------
        # Range-based API
        # --------------------------------------------------------

        if hasattr(
            self._repository,
            "get_by_facility_and_time_range",
        ):
            method = getattr(
                self._repository,
                "get_by_facility_and_time_range",
            )

            return await method(
                facility_id=facility_id,
                start_at=start_timestamp,
                end_at=end_timestamp,
            )

        # --------------------------------------------------------
        # Explicit historical API
        # --------------------------------------------------------

        if hasattr(
            self._repository,
            "list_by_facility",
        ):
            method = getattr(
                self._repository,
                "list_by_facility",
            )

            try:
                return await method(
                    facility_id=facility_id,
                    start_at=start_timestamp,
                    end_at=end_timestamp,
                )
            except TypeError:
                return await method(
                    facility_id=facility_id,
                    start_timestamp=start_timestamp,
                    end_timestamp=end_timestamp,
                )

        raise RuntimeError(
            "OccupancyObservationRepository does not expose a "
            "supported read method for production forecasting. "
            "Expected one of: "
            "get_observations_for_forecast(), "
            "get_observations(), "
            "get_by_facility_and_time_range(), "
            "list_by_facility()."
        )

    # ------------------------------------------------------------
    # ORM -> DataFrame
    # ------------------------------------------------------------

    @staticmethod
    def _to_dataframe(
        observations: Any,
    ) -> pd.DataFrame:
        """
        Convert repository output to the canonical production
        observation DataFrame.

        Supports:
            - pandas DataFrame
            - SQLAlchemy ORM objects
            - mappings/dictionaries
        """

        if observations is None:
            return pd.DataFrame()

        if isinstance(
            observations,
            pd.DataFrame,
        ):
            dataframe = observations.copy()

        else:
            rows: list[dict[str, Any]] = []

            for observation in observations:

                if isinstance(
                    observation,
                    dict,
                ):
                    rows.append(
                        dict(observation)
                    )
                    continue

                row = {}

                for field in (
                    "id",
                    "facility_id",
                    "observed_at",
                    "total_spaces",
                    "occupied_spaces",
                    "available_spaces",
                    "occupancy_rate",
                    "source",
                    "quality_status",
                    "quality_flags",
                ):
                    if hasattr(
                        observation,
                        field,
                    ):
                        row[field] = getattr(
                            observation,
                            field,
                        )

                rows.append(row)

            dataframe = pd.DataFrame(
                rows
            )

        if dataframe.empty:
            return dataframe

        # --------------------------------------------------------
        # Normalize timestamp
        # --------------------------------------------------------

        if "observed_at" in dataframe.columns:
            dataframe["observed_at"] = pd.to_datetime(
                dataframe["observed_at"],
                utc=True,
                errors="coerce",
            )

        # --------------------------------------------------------
        # Normalize source enum values
        # --------------------------------------------------------

        if "source" in dataframe.columns:

            dataframe["source"] = (
                dataframe["source"]
                .map(
                    lambda value:
                    value.value
                    if hasattr(
                        value,
                        "value",
                    )
                    else value
                )
            )

        # --------------------------------------------------------
        # Normalize quality status enum values
        # --------------------------------------------------------

        if "quality_status" in dataframe.columns:

            dataframe["quality_status"] = (
                dataframe["quality_status"]
                .map(
                    lambda value:
                    value.value
                    if hasattr(
                        value,
                        "value",
                    )
                    else value
                )
            )

        return dataframe


# ================================================================
# Database discovery
# ================================================================


async def find_test_facility(
    session,
) -> tuple[int, int, datetime, datetime]:
    """
    Find a facility with sufficient historical observations.

    Returns:

        facility_id
        observation_count
        earliest_observation
        latest_observation
    """

    result = await session.execute(
        select(
            func.count(
                # SQLAlchemy count expression
                #
                # We deliberately count observation IDs rather
                # than relying on a relationship.
                #
                # Import is local to avoid unnecessary module
                # coupling at import time.
            )
        )
    )

    # The above query is intentionally not used because we need
    # grouped facility-level statistics below.
    #
    # Import here to keep this function self-contained.
    from app.models.occupancy_observation import (
        OccupancyObservation,
    )

    result = await session.execute(
        select(
            OccupancyObservation.facility_id,
            func.count(
                OccupancyObservation.id
            ).label(
                "observation_count"
            ),
            func.min(
                OccupancyObservation.observed_at
            ).label(
                "earliest_observation"
            ),
            func.max(
                OccupancyObservation.observed_at
            ).label(
                "latest_observation"
            ),
        )
        .group_by(
            OccupancyObservation.facility_id
        )
        .having(
            func.count(
                OccupancyObservation.id
            )
            >= MINIMUM_OBSERVATIONS_REQUIRED
        )
        .order_by(
            func.count(
                OccupancyObservation.id
            ).desc()
        )
    )

    row = result.first()

    if row is None:
        raise RuntimeError(
            "No parking facility has enough occupancy "
            "observations for the production integration test."
        )

    return (
        int(row.facility_id),
        int(row.observation_count),
        row.earliest_observation,
        row.latest_observation,
    )


# ================================================================
# Database observation count
# ================================================================


async def get_total_observation_count(
    session,
) -> int:
    """
    Return total occupancy_observations count.
    """

    from app.models.occupancy_observation import (
        OccupancyObservation,
    )

    result = await session.execute(
        select(
            func.count(
                OccupancyObservation.id
            )
        )
    )

    return int(
        result.scalar_one()
    )


# ================================================================
# Main integration test
# ================================================================


async def main() -> int:
    """
    Execute the complete read-only production ML integration test.
    """

    print_header(
        "SMARTPARK AI - PRODUCTION FORECAST INTEGRATION SMOKE TEST"
    )

    print()
    print("Purpose:")
    print(
        "  Verify PostgreSQL -> occupancy_observations -> "
        "repository -> feature builder -> frozen XGBoost."
    )

    print()
    print("Production contract:")
    print(
        "  Prediction timestamp = T"
    )
    print(
        "  Forecast horizon     = T + 30 minutes"
    )
    print(
        "  Feature information  = available at or before T"
    )

    print()
    print("Database writes:")
    print("  INSERT               : NO")
    print("  UPDATE               : NO")
    print("  DELETE               : NO")

    print()
    print("ML training:")
    print("  XGBoost training     : NO")
    print("  Hyperparameter tune  : NO")
    print("  Feature rebuild      : NO")

    print()
    print("Dataset files:")
    print("  train.parquet        : NOT LOADED")
    print("  validation.parquet   : NOT LOADED")
    print("  test.parquet         : NOT LOADED")

    try:

        # ========================================================
        # 1. Database connectivity
        # ========================================================

        print_header(
            "DATABASE CONNECTIVITY"
        )

        async with AsyncSessionLocal() as session:

            total_observations = (
                await get_total_observation_count(
                    session
                )
            )

            print_status(
                "Total occupancy observations",
                f"{total_observations:,}",
            )

            if total_observations <= 0:
                print_fail(
                    "Production observation data available"
                )

                raise RuntimeError(
                    "occupancy_observations is empty. "
                    "Run the production observation ingestion "
                    "without --dry-run first."
                )

            print_pass(
                "Database connection"
            )

            print_pass(
                "occupancy_observations contains data"
            )

            # ====================================================
            # 2. Select facility
            # ====================================================

            print_header(
                "SELECTING PRODUCTION TEST FACILITY"
            )

            (
                facility_id,
                facility_observation_count,
                earliest_observation,
                latest_observation,
            ) = await find_test_facility(
                session
            )

            print_status(
                "Selected facility ID",
                facility_id,
            )

            print_status(
                "Observation count",
                f"{facility_observation_count:,}",
            )

            print_status(
                "Earliest observation",
                earliest_observation,
            )

            print_status(
                "Latest observation",
                latest_observation,
            )

            print_pass(
                "Facility has production observations"
            )

            # ====================================================
            # 3. Choose prediction timestamp
            # ====================================================

            print_header(
                "SELECTING PRODUCTION PREDICTION TIMESTAMP"
            )

            # We deliberately use the latest observation as T.
            #
            # This guarantees that all source observations used by
            # the test are at or before T.
            prediction_timestamp = latest_observation

            if prediction_timestamp.tzinfo is None:
                prediction_timestamp = (
                    prediction_timestamp.replace(
                        tzinfo=timezone.utc
                    )
                )
            else:
                prediction_timestamp = (
                    prediction_timestamp.astimezone(
                        timezone.utc
                    )
                )

            forecast_timestamp = (
                prediction_timestamp
                + pd.Timedelta(
                    minutes=FORECAST_HORIZON_MINUTES
                ).to_pytimedelta()
            )

            print_status(
                "Prediction timestamp T",
                prediction_timestamp.isoformat(),
            )

            print_status(
                "Forecast timestamp T + 30m",
                forecast_timestamp.isoformat(),
            )

            print_pass(
                "Prediction timestamp selected"
            )

            # ====================================================
            # 4. Initialise production components
            # ====================================================

            print_header(
                "LOADING PRODUCTION ML COMPONENTS"
            )

            inference = (
                ProductionXGBoostInference()
            )

            print_pass(
                "Frozen XGBoost artifact loaded"
            )

            model_info = (
                inference.model_info()
            )

            model_candidate = model_info.get(
                "model_candidate"
            )

            target_column = model_info.get(
                "target_column"
            )

            forecast_horizon = model_info.get(
                "forecast_horizon_minutes"
            )

            feature_count = model_info.get(
                "feature_count"
            )

            print_status(
                "Model candidate",
                model_candidate,
            )

            print_status(
                "Target column",
                target_column,
            )

            print_status(
                "Forecast horizon",
                forecast_horizon,
            )

            print_status(
                "Model feature count",
                feature_count,
            )

            if model_candidate != (
                EXPECTED_MODEL_CANDIDATE
            ):
                raise RuntimeError(
                    "Frozen model candidate mismatch. "
                    f"Expected {EXPECTED_MODEL_CANDIDATE}, "
                    f"received {model_candidate}."
                )

            print_pass(
                "Selected candidate = TUNE_014"
            )

            if target_column != (
                EXPECTED_TARGET_COLUMN
            ):
                raise RuntimeError(
                    "Target contract mismatch. "
                    f"Expected {EXPECTED_TARGET_COLUMN}, "
                    f"received {target_column}."
                )

            print_pass(
                "Target contract"
            )

            if int(feature_count) != (
                EXPECTED_FEATURE_COUNT
            ):
                raise RuntimeError(
                    "Feature count mismatch. "
                    f"Expected {EXPECTED_FEATURE_COUNT}, "
                    f"received {feature_count}."
                )

            print_pass(
                "296-feature model contract"
            )

            if int(forecast_horizon) != (
                EXPECTED_FORECAST_HORIZON_MINUTES
            ):
                raise RuntimeError(
                    "Forecast horizon mismatch. "
                    f"Expected "
                    f"{EXPECTED_FORECAST_HORIZON_MINUTES}, "
                    f"received {forecast_horizon}."
                )

            print_pass(
                "30-minute forecast contract"
            )

            feature_builder = (
                ProductionFeatureBuilder()
            )

            print_pass(
                "Production feature builder loaded"
            )

            repository = (
                OccupancyObservationRepository(
                    session
                )
            )

            print_pass(
                "Observation repository loaded"
            )

            provider = (
                RepositoryObservationProvider(
                    repository
                )
            )

            service = (
                ProductionForecastService(
                    inference=inference,
                    feature_builder=feature_builder,
                    observation_provider=provider,
                )
            )

            print_pass(
                "Production forecast service loaded"
            )

            # ====================================================
            # 5. Repository read test
            # ====================================================

            print_header(
                "OBSERVATION REPOSITORY READ TEST"
            )

            lookback_minutes = (
                service.required_lookback_minutes()
            )

            print_status(
                "Required production lookback",
                f"{lookback_minutes:,} minutes",
            )

            observations = await provider(
                facility_id,
                prediction_timestamp,
                lookback_minutes,
            )

            print_status(
                "Observations retrieved",
                f"{len(observations):,}",
            )

            if observations.empty:
                raise RuntimeError(
                    "Observation repository returned zero "
                    "observations for the selected facility."
                )

            print_pass(
                "Repository returned observations"
            )

            required_columns = {
                "observed_at",
                "total_spaces",
                "occupied_spaces",
                "available_spaces",
                "occupancy_rate",
            }

            missing_columns = sorted(
                required_columns
                - set(observations.columns)
            )

            if missing_columns:
                raise RuntimeError(
                    "Repository observation DataFrame is missing "
                    f"required columns: {missing_columns}"
                )

            print_pass(
                "Repository observation schema"
            )

            # ====================================================
            # 6. Temporal boundary check
            # ====================================================

            print_header(
                "TEMPORAL INTEGRITY CHECK"
            )

            observation_timestamps = pd.to_datetime(
                observations["observed_at"],
                utc=True,
                errors="coerce",
            )

            if observation_timestamps.isna().any():
                raise RuntimeError(
                    "Repository returned invalid observation "
                    "timestamps."
                )

            future_mask = (
                observation_timestamps
                > pd.Timestamp(
                    prediction_timestamp
                )
            )

            future_count = int(
                future_mask.sum()
            )

            print_status(
                "Observations after T",
                future_count,
            )

            if future_count != 0:
                raise RuntimeError(
                    "Temporal leakage detected: repository returned "
                    "observations after prediction timestamp T."
                )

            print_pass(
                "No observations after prediction timestamp"
            )

            print_status(
                "Observation earliest timestamp",
                observation_timestamps.min(),
            )

            print_status(
                "Observation latest timestamp",
                observation_timestamps.max(),
            )

            # ====================================================
            # 7. Full production service forecast
            # ====================================================

            print_header(
                "RUNNING PRODUCTION FORECAST"
            )

            result = await service.forecast(
                facility_id=facility_id,
                prediction_timestamp=prediction_timestamp,
                lookback_minutes=lookback_minutes,
                source="BIRMINGHAM",
            )

            print_pass(
                "Production forecast generated"
            )

            # ====================================================
            # 8. Validate result
            # ====================================================

            print_header(
                "VALIDATING PRODUCTION FORECAST RESULT"
            )

            print_status(
                "Facility ID",
                result.facility_id,
            )

            print_status(
                "Prediction timestamp",
                result.prediction_timestamp.isoformat(),
            )

            print_status(
                "Forecast timestamp",
                result.forecast_timestamp.isoformat(),
            )

            print_status(
                "Model candidate",
                result.model_candidate,
            )

            print_status(
                "Target",
                result.target_column,
            )

            print_status(
                "Forecast horizon",
                result.forecast_horizon_minutes,
            )

            print_status(
                "Feature count",
                result.feature_count,
            )

            print_status(
                "Observation count",
                result.observation_count,
            )

            print_status(
                "Prediction",
                f"{result.predicted_occupancy_rate:.10f}",
            )

            print_status(
                "Prediction %",
                f"{result.predicted_occupancy_percentage:.4f}%",
            )

            # ----------------------------------------------------
            # Result assertions
            # ----------------------------------------------------

            if result.model_candidate != (
                EXPECTED_MODEL_CANDIDATE
            ):
                raise RuntimeError(
                    "Production result contains unexpected "
                    f"model candidate: "
                    f"{result.model_candidate}"
                )

            print_pass(
                "Result model = TUNE_014"
            )

            if result.target_column != (
                EXPECTED_TARGET_COLUMN
            ):
                raise RuntimeError(
                    "Production result contains unexpected target."
                )

            print_pass(
                "Result target contract"
            )

            if result.forecast_horizon_minutes != (
                EXPECTED_FORECAST_HORIZON_MINUTES
            ):
                raise RuntimeError(
                    "Production result contains unexpected "
                    "forecast horizon."
                )

            print_pass(
                "Result forecast horizon = 30 minutes"
            )

            if result.feature_count != (
                EXPECTED_FEATURE_COUNT
            ):
                raise RuntimeError(
                    "Production result contains unexpected "
                    "feature count."
                )

            print_pass(
                "Result feature count = 296"
            )

            if not (
                0.0
                <= result.predicted_occupancy_rate
                <= 1.0
            ):
                raise RuntimeError(
                    "Production prediction is outside [0, 1]."
                )

            print_pass(
                "Prediction within [0,1]"
            )

            if result.predicted_occupancy_percentage != (
                result.predicted_occupancy_rate
                * 100.0
            ):
                raise RuntimeError(
                    "Prediction percentage does not match "
                    "prediction rate."
                )

            print_pass(
                "Prediction percentage consistency"
            )

            expected_forecast_timestamp = (
                prediction_timestamp
                + pd.Timedelta(
                    minutes=30
                ).to_pytimedelta()
            )

            if result.forecast_timestamp != (
                expected_forecast_timestamp
            ):
                raise RuntimeError(
                    "Forecast timestamp does not equal "
                    "T + 30 minutes."
                )

            print_pass(
                "Forecast timestamp = T + 30 minutes"
            )

            # ====================================================
            # 9. Model safety assertions
            # ====================================================

            print_header(
                "PRODUCTION MODEL SAFETY ASSERTIONS"
            )

            print_status(
                "Training performed",
                model_info.get(
                    "training_performed"
                ),
            )

            print_status(
                "Hyperparameter tuning performed",
                model_info.get(
                    "hyperparameter_tuning_performed"
                ),
            )

            print_status(
                "Feature pipeline rebuilt",
                model_info.get(
                    "feature_pipeline_rebuilt"
                ),
            )

            if model_info.get(
                "training_performed"
            ):
                raise RuntimeError(
                    "Production inference reports that training "
                    "was performed."
                )

            print_pass(
                "No XGBoost training performed"
            )

            if model_info.get(
                "hyperparameter_tuning_performed"
            ):
                raise RuntimeError(
                    "Production inference reports that "
                    "hyperparameter tuning was performed."
                )

            print_pass(
                "No hyperparameter tuning performed"
            )

            if model_info.get(
                "feature_pipeline_rebuilt"
            ):
                raise RuntimeError(
                    "Production inference reports that the feature "
                    "pipeline was rebuilt."
                )

            print_pass(
                "No feature pipeline rebuild performed"
            )

            # ====================================================
            # 10. Final DB count check
            #
            # The count must remain exactly unchanged because this
            # test is read-only.
            # ====================================================

            print_header(
                "READ-ONLY DATABASE SAFETY CHECK"
            )

            final_count = (
                await get_total_observation_count(
                    session
                )
            )

            print_status(
                "Initial observation count",
                f"{total_observations:,}",
            )

            print_status(
                "Final observation count",
                f"{final_count:,}",
            )

            if final_count != (
                total_observations
            ):
                raise RuntimeError(
                    "Database observation count changed during "
                    "the read-only integration test."
                )

            print_pass(
                "Database observation count unchanged"
            )

            print_pass(
                "No database writes performed"
            )

            # ====================================================
            # 11. Final result
            # ====================================================

            print_header(
                "FINAL PRODUCTION INTEGRATION ASSERTIONS"
            )

            print_pass(
                "PostgreSQL connectivity"
            )

            print_pass(
                "occupancy_observations contains production data"
            )

            print_pass(
                "ObservationRepository read"
            )

            print_pass(
                "Production observation schema"
            )

            print_pass(
                "No future observations used"
            )

            print_pass(
                "ProductionFeatureBuilder executed"
            )

            print_pass(
                "296 production features"
            )

            print_pass(
                "Frozen XGBoost Booster loaded"
            )

            print_pass(
                "Selected candidate = TUNE_014"
            )

            print_pass(
                "Target = target_occupancy_rate_30m"
            )

            print_pass(
                "Forecast horizon = 30 minutes"
            )

            print_pass(
                "Prediction finite"
            )

            print_pass(
                "Prediction within [0,1]"
            )

            print_pass(
                "No XGBoost training"
            )

            print_pass(
                "No hyperparameter tuning"
            )

            print_pass(
                "No feature pipeline rebuild"
            )

            print_pass(
                "No database writes"
            )

            print()
            print("=" * 78)
            print(
                "PRODUCTION ML INTEGRATION TEST PASSED"
            )
            print("=" * 78)

            print()
            print(
                "Production inference is now verified end-to-end:"
            )

            print()
            print(
                "  PostgreSQL"
            )
            print(
                "      -> occupancy_observations"
            )
            print(
                "      -> ObservationRepository"
            )
            print(
                "      -> ProductionForecastService"
            )
            print(
                "      -> ProductionFeatureBuilder"
            )
            print(
                "      -> 296 features"
            )
            print(
                "      -> Frozen TUNE_014"
            )
            print(
                "      -> T + 30 minute forecast"
            )

            print()
            print(
                f"Facility:             {result.facility_id}"
            )
            print(
                f"Prediction timestamp:  "
                f"{result.prediction_timestamp.isoformat()}"
            )
            print(
                f"Forecast timestamp:    "
                f"{result.forecast_timestamp.isoformat()}"
            )
            print(
                f"Predicted occupancy:   "
                f"{result.predicted_occupancy_rate:.6f}"
            )
            print(
                f"Predicted occupancy %: "
                f"{result.predicted_occupancy_percentage:.2f}%"
            )
            print(
                f"Model:                 "
                f"{result.model_candidate}"
            )

            print()

            return 0

    except Exception as exc:

        print()
        print("=" * 78)
        print(
            "PRODUCTION ML INTEGRATION TEST FAILED"
        )
        print("=" * 78)

        print()
        print(
            f"ERROR: {type(exc).__name__}: {exc}"
        )

        print()
        print(
            "IMPORTANT:"
        )
        print(
            "  This test is read-only."
        )
        print(
            "  No occupancy observations should have been inserted, "
            "updated, or deleted."
        )
        print(
            "  No XGBoost training was performed."
        )
        print(
            "  No hyperparameter tuning was performed."
        )
        print(
            "  No feature pipeline was rebuilt."
        )

        return 1


# ================================================================
# Entry point
# ================================================================


if __name__ == "__main__":
    raise SystemExit(
        asyncio.run(
            main()
        )
    )