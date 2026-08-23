"""
SmartPark AI - Production Occupancy Observation Repository.

This module provides the database adapter used by the production
ML forecasting layer to retrieve observations from:

    occupancy_observations

Architecture
------------

    PostgreSQL
        |
        v
    AsyncSession
        |
        v
    OccupancyObservationRepository
        |
        v
    pandas.DataFrame
        |
        v
    ProductionForecastService
        |
        v
    ProductionFeatureBuilder
        |
        v
    Frozen XGBoost

Responsibilities
----------------
- Read occupancy observations from PostgreSQL.
- Apply facility/time-window filtering.
- Enforce the production temporal cutoff.
- Return observations in the canonical ML observation schema.
- Perform basic repository-level validation.

Non-responsibilities
--------------------
- Feature engineering.
- XGBoost inference.
- Model training.
- Hyperparameter tuning.
- Prediction generation.
- Database writes.

The repository is intentionally read-only.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

import pandas as pd
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.occupancy_observation import OccupancyObservation


# ============================================================
# Constants
# ============================================================

REQUIRED_COLUMNS = (
    "observed_at",
    "total_spaces",
    "occupied_spaces",
    "available_spaces",
    "occupancy_rate",
)

DEFAULT_LOOKBACK_MINUTES = 24 * 60


# ============================================================
# Exceptions
# ============================================================


class OccupancyObservationRepositoryError(
    RuntimeError
):
    """Base repository exception."""


class OccupancyObservationQueryError(
    OccupancyObservationRepositoryError
):
    """Raised when the database query fails."""


class OccupancyObservationValidationError(
    OccupancyObservationRepositoryError
):
    """Raised when retrieved observations violate the contract."""


# ============================================================
# Repository
# ============================================================


class OccupancyObservationRepository:
    """
    Read-only repository for production occupancy observations.

    The repository uses an existing AsyncSession supplied by the
    application layer.

    Example
    -------

        repository = OccupancyObservationRepository(
            session=db_session,
        )

        observations = await repository.get_for_forecast(
            facility_id=1,
            prediction_timestamp=prediction_timestamp,
            lookback_minutes=1440,
        )

    No database session is created or closed by this class.
    Session lifecycle remains the responsibility of the caller.
    """

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        if not isinstance(
            session,
            AsyncSession,
        ):
            raise TypeError(
                "session must be an AsyncSession."
            )

        self._session = session

    # ========================================================
    # Primary Production Query
    # ========================================================

    async def get_for_forecast(
        self,
        *,
        facility_id: int,
        prediction_timestamp: datetime,
        lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
    ) -> pd.DataFrame:
        """
        Retrieve observations required for production forecasting.

        Temporal contract
        -----------------
        Only observations satisfying:

            T - lookback <= observed_at <= T

        are returned.

        Crucially, observations after T are never returned.

        Parameters
        ----------
        facility_id:
            Parking facility identifier.

        prediction_timestamp:
            Prediction timestamp T.

        lookback_minutes:
            Historical observation window.

        Returns
        -------
        pandas.DataFrame
            Canonical occupancy observation DataFrame.

        Raises
        ------
        OccupancyObservationQueryError
            If the database query fails.

        OccupancyObservationValidationError
            If the retrieved observations violate the production
            observation contract.
        """

        self._validate_query_parameters(
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
            lookback_minutes=lookback_minutes,
        )

        window_start = (
            prediction_timestamp
            - timedelta(
                minutes=lookback_minutes
            )
        )

        window_end = prediction_timestamp

        statement = (
            select(
                OccupancyObservation.id,
                OccupancyObservation.facility_id,
                OccupancyObservation.observed_at,
                OccupancyObservation.total_spaces,
                OccupancyObservation.occupied_spaces,
                OccupancyObservation.available_spaces,
                OccupancyObservation.occupancy_rate,
                OccupancyObservation.source,
                OccupancyObservation.quality_status,
                OccupancyObservation.quality_flags,
            )
            .where(
                and_(
                    OccupancyObservation.facility_id
                    == facility_id,

                    OccupancyObservation.observed_at
                    >= window_start,

                    OccupancyObservation.observed_at
                    <= window_end,
                )
            )
            .order_by(
                OccupancyObservation.observed_at.asc()
            )
        )

        try:
            result = await self._session.execute(
                statement
            )

            rows = result.mappings().all()

        except Exception as exc:
            raise OccupancyObservationQueryError(
                "Failed to retrieve occupancy observations "
                f"for facility_id={facility_id}, "
                f"window_start={window_start.isoformat()}, "
                f"window_end={window_end.isoformat()}."
            ) from exc

        dataframe = self._rows_to_dataframe(
            rows
        )

        self._validate_result(
            dataframe=dataframe,
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
        )

        return dataframe

    # ========================================================
    # Production Forecast Read Contract
    # ========================================================

    async def get_observations_for_forecast(
        self,
        *,
        facility_id: int,
        prediction_timestamp: datetime,
        lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
    ) -> pd.DataFrame:
        """
        Retrieve the production observation window required by
        the forecasting service.

        This is the explicit production forecasting repository
        contract. It delegates to ``get_for_forecast()``, which
        already enforces the canonical temporal and observation
        validation rules.

        Temporal contract
        -----------------
        Only observations satisfying:

            T - lookback <= observed_at <= T

        are returned.

        No observation after prediction_timestamp (T) can be
        returned, preventing temporal leakage.

        Parameters
        ----------
        facility_id:
            Canonical SmartPark parking facility ID.

        prediction_timestamp:
            Prediction timestamp T.

        lookback_minutes:
            Historical observation window in minutes.

        Returns
        -------
        pandas.DataFrame
            Canonical production occupancy observation DataFrame.

        Raises
        ------
        ValueError
            If the query parameters are invalid.

        OccupancyObservationQueryError
            If the database query fails.

        OccupancyObservationValidationError
            If retrieved observations violate the production
            observation contract.

        Notes
        -----
        This method is strictly read-only. It performs no INSERT,
        UPDATE, DELETE, training, feature rebuilding, or model
        inference.
        """

        return await self.get_for_forecast(
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
            lookback_minutes=lookback_minutes,
        )

    # ========================================================
    # Latest Observation
    # ========================================================

    async def get_latest(
        self,
        *,
        facility_id: int,
        at_or_before: datetime | None = None,
    ) -> dict[str, Any] | None:
        """
        Retrieve the latest observation for a facility.

        The observation must occur at or before the supplied
        timestamp.

        If ``at_or_before`` is omitted, the current database query
        does not impose a timestamp cutoff beyond the database's
        available records.

        This method is useful for production health/status APIs.
        """

        if not isinstance(
            facility_id,
            int,
        ) or facility_id <= 0:
            raise ValueError(
                "facility_id must be a positive integer."
            )

        statement = (
            select(
                OccupancyObservation.id,
                OccupancyObservation.facility_id,
                OccupancyObservation.observed_at,
                OccupancyObservation.total_spaces,
                OccupancyObservation.occupied_spaces,
                OccupancyObservation.available_spaces,
                OccupancyObservation.occupancy_rate,
                OccupancyObservation.source,
                OccupancyObservation.quality_status,
                OccupancyObservation.quality_flags,
            )
            .where(
                OccupancyObservation.facility_id
                == facility_id
            )
        )

        if at_or_before is not None:
            if at_or_before.tzinfo is None:
                raise ValueError(
                    "at_or_before must be timezone-aware."
                )

            statement = statement.where(
                OccupancyObservation.observed_at
                <= at_or_before
            )

        statement = statement.order_by(
            OccupancyObservation.observed_at.desc()
        ).limit(1)

        try:
            result = await self._session.execute(
                statement
            )

            row = result.mappings().first()

        except Exception as exc:
            raise OccupancyObservationQueryError(
                "Failed to retrieve latest occupancy "
                f"observation for facility_id={facility_id}."
            ) from exc

        if row is None:
            return None

        return self._mapping_to_dict(
            row
        )

    # ========================================================
    # Observation Count
    # ========================================================

    async def count_for_forecast(
        self,
        *,
        facility_id: int,
        prediction_timestamp: datetime,
        lookback_minutes: int = DEFAULT_LOOKBACK_MINUTES,
    ) -> int:
        """
        Return the number of observations available in the
        production forecast window.

        This method is useful for diagnostics without loading the
        complete observation dataset into memory.
        """

        from sqlalchemy import func

        self._validate_query_parameters(
            facility_id=facility_id,
            prediction_timestamp=prediction_timestamp,
            lookback_minutes=lookback_minutes,
        )

        window_start = (
            prediction_timestamp
            - timedelta(
                minutes=lookback_minutes
            )
        )

        statement = select(
            func.count(
                OccupancyObservation.id
            )
        ).where(
            and_(
                OccupancyObservation.facility_id
                == facility_id,

                OccupancyObservation.observed_at
                >= window_start,

                OccupancyObservation.observed_at
                <= prediction_timestamp,
            )
        )

        try:
            result = await self._session.execute(
                statement
            )

            count = result.scalar_one()

        except Exception as exc:
            raise OccupancyObservationQueryError(
                "Failed to count occupancy observations "
                f"for facility_id={facility_id}."
            ) from exc

        return int(count)

    # ========================================================
    # Date Range Query
    # ========================================================

    async def get_between(
        self,
        *,
        facility_id: int,
        start_at: datetime,
        end_at: datetime,
    ) -> pd.DataFrame:
        """
        Retrieve observations between two timestamps.

        This is a general read-only query useful for diagnostics,
        historical inspection and future ML workflows.

        Both boundaries are inclusive.
        """

        if not isinstance(
            facility_id,
            int,
        ) or facility_id <= 0:
            raise ValueError(
                "facility_id must be a positive integer."
            )

        if start_at.tzinfo is None:
            raise ValueError(
                "start_at must be timezone-aware."
            )

        if end_at.tzinfo is None:
            raise ValueError(
                "end_at must be timezone-aware."
            )

        if start_at > end_at:
            raise ValueError(
                "start_at must be earlier than or equal "
                "to end_at."
            )

        statement = (
            select(
                OccupancyObservation.id,
                OccupancyObservation.facility_id,
                OccupancyObservation.observed_at,
                OccupancyObservation.total_spaces,
                OccupancyObservation.occupied_spaces,
                OccupancyObservation.available_spaces,
                OccupancyObservation.occupancy_rate,
                OccupancyObservation.source,
                OccupancyObservation.quality_status,
                OccupancyObservation.quality_flags,
            )
            .where(
                and_(
                    OccupancyObservation.facility_id
                    == facility_id,

                    OccupancyObservation.observed_at
                    >= start_at,

                    OccupancyObservation.observed_at
                    <= end_at,
                )
            )
            .order_by(
                OccupancyObservation.observed_at.asc()
            )
        )

        try:
            result = await self._session.execute(
                statement
            )

            rows = result.mappings().all()

        except Exception as exc:
            raise OccupancyObservationQueryError(
                "Failed to retrieve occupancy observations "
                f"between {start_at.isoformat()} and "
                f"{end_at.isoformat()}."
            ) from exc

        dataframe = self._rows_to_dataframe(
            rows
        )

        return dataframe

    # ========================================================
    # Conversion
    # ========================================================

    @staticmethod
    def _rows_to_dataframe(
        rows: Sequence[Mapping[str, Any]],
    ) -> pd.DataFrame:
        """
        Convert SQLAlchemy mapping rows into the canonical
        production ML DataFrame.
        """

        if not rows:
            return pd.DataFrame(
                columns=[
                    "id",
                    "facility_id",
                    *REQUIRED_COLUMNS,
                    "source",
                    "quality_status",
                    "quality_flags",
                ]
            )

        records: list[dict[str, Any]] = []

        for row in rows:
            records.append(
                OccupancyObservationRepository
                ._mapping_to_dict(
                    row
                )
            )

        dataframe = pd.DataFrame(
            records
        )

        # ----------------------------------------------------
        # Preserve canonical ordering.
        # ----------------------------------------------------

        preferred_order = [
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
        ]

        existing_columns = [
            column
            for column in preferred_order
            if column in dataframe.columns
        ]

        remaining_columns = [
            column
            for column in dataframe.columns
            if column not in existing_columns
        ]

        dataframe = dataframe[
            existing_columns
            + remaining_columns
        ]

        # ----------------------------------------------------
        # Timestamp normalization.
        # ----------------------------------------------------

        dataframe["observed_at"] = pd.to_datetime(
            dataframe["observed_at"],
            utc=True,
            errors="coerce",
        )

        # ----------------------------------------------------
        # Numeric normalization.
        # ----------------------------------------------------

        for column in (
            "total_spaces",
            "occupied_spaces",
            "available_spaces",
        ):
            if column in dataframe.columns:
                dataframe[column] = pd.to_numeric(
                    dataframe[column],
                    errors="coerce",
                )

        if "occupancy_rate" in dataframe.columns:
            dataframe["occupancy_rate"] = pd.to_numeric(
                dataframe["occupancy_rate"],
                errors="coerce",
            )

        return dataframe

    @staticmethod
    def _mapping_to_dict(
        row: Mapping[str, Any],
    ) -> dict[str, Any]:
        """
        Convert a SQLAlchemy mapping row to a normal dictionary.

        Enum values are converted to their string values where
        available so the resulting DataFrame is straightforward
        for the ML layer to consume.
        """

        result: dict[str, Any] = {}

        for key, value in row.items():

            if hasattr(
                value,
                "value",
            ):
                try:
                    value = value.value
                except Exception:
                    pass

            result[str(key)] = value

        return result

    # ========================================================
    # Validation
    # ========================================================

    @staticmethod
    def _validate_query_parameters(
        *,
        facility_id: int,
        prediction_timestamp: datetime,
        lookback_minutes: int,
    ) -> None:
        """
        Validate repository query parameters.
        """

        if not isinstance(
            facility_id,
            int,
        ):
            raise ValueError(
                "facility_id must be an integer."
            )

        if facility_id <= 0:
            raise ValueError(
                "facility_id must be greater than zero."
            )

        if not isinstance(
            prediction_timestamp,
            datetime,
        ):
            raise ValueError(
                "prediction_timestamp must be a datetime."
            )

        if prediction_timestamp.tzinfo is None:
            raise ValueError(
                "prediction_timestamp must be timezone-aware."
            )

        if not isinstance(
            lookback_minutes,
            int,
        ):
            raise ValueError(
                "lookback_minutes must be an integer."
            )

        if lookback_minutes <= 0:
            raise ValueError(
                "lookback_minutes must be greater than zero."
            )

    @staticmethod
    def _validate_result(
        *,
        dataframe: pd.DataFrame,
        facility_id: int,
        prediction_timestamp: datetime,
    ) -> None:
        """
        Validate the repository result.

        This is deliberately stricter than a generic database query
        because the returned data is going directly into production
        ML feature construction.
        """

        if dataframe.empty:
            return

        missing_columns = [
            column
            for column in REQUIRED_COLUMNS
            if column not in dataframe.columns
        ]

        if missing_columns:
            raise OccupancyObservationValidationError(
                "Retrieved observations are missing required "
                f"columns: {missing_columns}"
            )

        # ----------------------------------------------------
        # Timestamp validation.
        # ----------------------------------------------------

        timestamps = pd.to_datetime(
            dataframe["observed_at"],
            utc=True,
            errors="coerce",
        )

        if timestamps.isna().any():
            raise OccupancyObservationValidationError(
                "Retrieved observations contain invalid "
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

        if (
            timestamps
            > prediction_ts
        ).any():
            raise OccupancyObservationValidationError(
                "Repository returned observations after "
                "prediction timestamp T."
            )

        # ----------------------------------------------------
        # Facility validation.
        # ----------------------------------------------------

        if "facility_id" in dataframe.columns:

            facility_values = pd.to_numeric(
                dataframe["facility_id"],
                errors="coerce",
            )

            if (
                facility_values
                != facility_id
            ).any():
                raise OccupancyObservationValidationError(
                    "Repository returned observations belonging "
                    "to a different facility."
                )

        # ----------------------------------------------------
        # Numeric validation.
        # ----------------------------------------------------

        for column in (
            "total_spaces",
            "occupied_spaces",
            "available_spaces",
            "occupancy_rate",
        ):

            values = pd.to_numeric(
                dataframe[column],
                errors="coerce",
            )

            if values.isna().any():
                raise OccupancyObservationValidationError(
                    f"Observation column '{column}' contains "
                    "null or non-numeric values."
                )

        total_spaces = pd.to_numeric(
            dataframe["total_spaces"]
        )

        occupied_spaces = pd.to_numeric(
            dataframe["occupied_spaces"]
        )

        available_spaces = pd.to_numeric(
            dataframe["available_spaces"]
        )

        occupancy_rate = pd.to_numeric(
            dataframe["occupancy_rate"]
        )

        # ----------------------------------------------------
        # Database model constraints repeated at the ML
        # boundary.
        # ----------------------------------------------------

        if (
            total_spaces <= 0
        ).any():
            raise OccupancyObservationValidationError(
                "Retrieved observations contain total_spaces "
                "<= 0."
            )

        if (
            occupied_spaces < 0
        ).any():
            raise OccupancyObservationValidationError(
                "Retrieved observations contain negative "
                "occupied_spaces."
            )

        if (
            available_spaces < 0
        ).any():
            raise OccupancyObservationValidationError(
                "Retrieved observations contain negative "
                "available_spaces."
            )

        if (
            occupied_spaces
            + available_spaces
            != total_spaces
        ).any():
            raise OccupancyObservationValidationError(
                "Retrieved observations violate the occupancy "
                "space-balance rule."
            )

        if (
            (occupancy_rate < 0)
            | (occupancy_rate > 1)
        ).any():
            raise OccupancyObservationValidationError(
                "Retrieved observations contain occupancy_rate "
                "outside [0, 1]."
            )

        # ----------------------------------------------------
        # Duplicate timestamp validation.
        #
        # The DB already has a uniqueness constraint on:
        #
        #     facility_id + observed_at
        #
        # We nevertheless verify the result at the ML boundary.
        # ----------------------------------------------------

        if timestamps.duplicated().any():
            raise OccupancyObservationValidationError(
                "Duplicate observation timestamps detected "
                f"for facility_id={facility_id}."
            )


__all__ = [
    "OccupancyObservationRepository",
    "OccupancyObservationRepositoryError",
    "OccupancyObservationQueryError",
    "OccupancyObservationValidationError",
    "DEFAULT_LOOKBACK_MINUTES",
]