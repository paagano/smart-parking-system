import { api } from "../client";

// ==========================================================
// Forecast API
// ==========================================================
//
// Current production forecasting contract:
//
// POST /forecasts/facilities/{facility_id}
//
// The current backend implementation performs
// inference using the frozen production model.
//
// IMPORTANT:
// This API intentionally represents the CURRENT backend
// contract. We will generalise the ML architecture later
// so the frontend does not become coupled to Birmingham,
// XGBoost, or a particular forecast horizon.
// ==========================================================

export interface ForecastRequest {
  /**
   * Prediction timestamp T.
   *
   * ISO-8601 timestamp.
   */
  prediction_timestamp: string;

  /**
   * Historical observation lookback window.
   *
   * Current production contract:
   * 1440 minutes = 24 hours.
   */
  lookback_minutes: number;
}

export interface ForecastResponse {
  facility_id: number;

  prediction_timestamp: string;

  forecast_timestamp: string;

  forecast_horizon_minutes: number;

  predicted_occupancy_rate: number;

  model_candidate: string;

  target_column: string;

  feature_count: number;

  feature_information: string;

  inference_only: boolean;
}

export const forecastApi = {
  /**
   * Check production forecasting service health.
   *
   * Backend:
   *
   * GET /forecasts/health
   */
  health: () => api.get("/forecasts/health"),

  /**
   * Generate a production occupancy forecast.
   *
   * Backend:
   *
   * POST /forecasts/facilities/{facility_id}
   *
   * Current implementation:
   *
   * T -> T + 30 minutes
   */
  forecast: (facilityId: number, payload: ForecastRequest) =>
    api.post<ForecastResponse>(`/forecasts/facilities/${facilityId}`, payload),
};

