import {
  Activity,
  AlertCircle,
  BrainCircuit,
  CalendarPlus,
  CheckCircle2,
  ChevronDown,
  Clock3,
  ExternalLink,
  Gauge,
  MapPin,
  Navigation,
  RefreshCw,
  Search,
  ServerCog,
  Sparkles,
  TrendingUp,
  X,
} from "lucide-react";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Card } from "../../../components/common/Page";

import {
  forecastApi,
  parkingFacilitiesApi,
  type ForecastResponse,
  type ParkingFacility,
} from "../../../api";

// ==========================================================
// Production Forecast Configuration
// ==========================================================

const LOOKBACK_MINUTES = 1440;

// Production model currently supports:
// Prediction timestamp -> +30 minutes
const AUTO_REFRESH_INTERVAL_MS = 5 * 60 * 1000;

// The currently deployed model is backed by historical
// Birmingham parking observations.
//
// This timestamp is known to work against the production
// inference endpoint from Swagger.
const KNOWN_GOOD_FORECAST_TIMESTAMP = "2016-12-19T16:30:00Z";

// The production model currently has a verified historical
// timestamp that can be used when live observations are unavailable.
// The timestamp is NOT restricted to a single facility: the selected
// facility ID is always passed through to the forecasting endpoint.

// Keep facility 47 as the initial default because it is the
// currently verified production test facility. This does NOT
// restrict forecasting to facility 47.
const KNOWN_GOOD_FACILITY_ID = 47;

// ==========================================================
// Types
// ==========================================================

type ServiceStatus = "checking" | "live" | "degraded" | "offline";

type DemandTone = "low" | "moderate" | "high" | "very-high";

// ParkingFacility may evolve as the backend gains additional
// location fields. These optional fields allow this page to
// use coordinates when they are available without requiring
// them in the base API type.
type FacilityWithLocation = ParkingFacility & {
  latitude?: number | string | null;
  longitude?: number | string | null;
  lat?: number | string | null;
  lng?: number | string | null;
  longitude_deg?: number | string | null;
  latitude_deg?: number | string | null;
};

// ==========================================================
// Helpers
// ==========================================================

function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) {
    return "—";
  }

  const date = value instanceof Date ? value : new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-KE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatTime(value: string | Date | null | undefined): string {
  if (!value) {
    return "—";
  }

  const date = value instanceof Date ? value : new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-KE", {
    timeStyle: "short",
  }).format(date);
}

function formatPercentage(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }

  return `${(value * 100).toFixed(1)}%`;
}

function clampRate(value: number): number {
  return Math.max(0, Math.min(1, value));
}

// ==========================================================
// Demand Classification
// ==========================================================

function getDemandLevel(rate: number | null): {
  label: string;
  description: string;
  tone: DemandTone;
} {
  if (rate === null) {
    return {
      label: "Awaiting prediction",
      description:
        "Generate a production forecast to determine expected parking demand.",
      tone: "moderate",
    };
  }

  if (rate >= 0.9) {
    return {
      label: "Very High Demand",
      description:
        "Parking demand is expected to be very high at the forecast time.",
      tone: "very-high",
    };
  }

  if (rate >= 0.75) {
    return {
      label: "High Demand",
      description:
        "Parking demand is expected to be high. Consider securing a space early.",
      tone: "high",
    };
  }

  if (rate >= 0.5) {
    return {
      label: "Moderate Demand",
      description: "Moderate parking demand is expected at the forecast time.",
      tone: "moderate",
    };
  }

  return {
    label: "Low Demand",
    description: "Parking demand is expected to remain relatively manageable.",
    tone: "low",
  };
}

// ==========================================================
// Demand Styles
// ==========================================================

function getDemandStyles(tone: DemandTone) {
  switch (tone) {
    case "very-high":
      return {
        badge: "bg-red-50 text-red-700 ring-red-200",
        bar: "bg-red-500",
        icon: "bg-red-50 text-red-600",
        gauge: "#ef4444",
      };

    case "high":
      return {
        badge: "bg-orange-50 text-orange-700 ring-orange-200",
        bar: "bg-orange-500",
        icon: "bg-orange-50 text-orange-600",
        gauge: "#f97316",
      };

    case "moderate":
      return {
        badge: "bg-amber-50 text-amber-700 ring-amber-200",
        bar: "bg-amber-500",
        icon: "bg-amber-50 text-amber-600",
        gauge: "#f59e0b",
      };

    case "low":
    default:
      return {
        badge: "bg-emerald-50 text-emerald-700 ring-emerald-200",
        bar: "bg-emerald-500",
        icon: "bg-emerald-50 text-emerald-600",
        gauge: "#10b981",
      };
  }
}

// ==========================================================
// API Error Handling
// ==========================================================

function extractApiError(error: any): string {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }

  const message = error?.response?.data?.message;

  if (typeof message === "string" && message.trim()) {
    return message;
  }

  if (typeof error?.message === "string" && error.message.trim()) {
    return error.message;
  }

  switch (error?.response?.status) {
    case 401:
      return "Your session has expired. Please sign in again.";

    case 403:
      return "You are not authorized to use the forecasting service.";

    case 404:
      return "The requested forecasting resource could not be found.";

    case 422:
      return "The forecasting request could not be validated.";

    case 500:
      return "The production forecasting service encountered an internal error.";

    default:
      return "Unable to generate the production forecast. Please try again.";
  }
}

// ==========================================================
// Health Status
// ==========================================================

function resolveHealthStatus(responseData: any): ServiceStatus {
  const status = String(
    responseData?.status ?? responseData?.diagnostics?.status ?? "",
  ).toLowerCase();

  if (
    status === "healthy" ||
    status === "ok" ||
    status === "ready" ||
    status === "available" ||
    status === "live"
  ) {
    return "live";
  }

  if (status === "degraded" || status === "warning") {
    return "degraded";
  }

  if (
    status === "offline" ||
    status === "unavailable" ||
    status === "error" ||
    status === "failed"
  ) {
    return "offline";
  }

  return "live";
}

// ==========================================================
// Status Badge
// ==========================================================

function StatusBadge({ status }: { status: ServiceStatus }) {
  const config = {
    checking: {
      label: "CHECKING",
      classes: "bg-slate-100 text-slate-600 ring-slate-200",
      dot: "bg-slate-400",
    },

    live: {
      label: "LIVE",
      classes: "bg-emerald-50 text-emerald-700 ring-emerald-200",
      dot: "bg-emerald-500",
    },

    degraded: {
      label: "DEGRADED",
      classes: "bg-amber-50 text-amber-700 ring-amber-200",
      dot: "bg-amber-500",
    },

    offline: {
      label: "OFFLINE",
      classes: "bg-red-50 text-red-700 ring-red-200",
      dot: "bg-red-500",
    },
  }[status];

  return (
    <span
      className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-extrabold ring-1 ${config.classes}`}
    >
      <span className={`h-2 w-2 rounded-full ${config.dot}`} />

      {config.label}
    </span>
  );
}

// ==========================================================
// Horizon Card
// ==========================================================

function HorizonCard({
  title,
  value,
  description,
  active = false,
  loading = false,
}: {
  title: string;
  value: string;
  description: string;
  active?: boolean;
  loading?: boolean;
}) {
  return (
    <div
      className={`rounded-3xl bg-white p-5 ring-1 transition ${
        active ? "ring-emerald-300 shadow-sm" : "ring-slate-200"
      }`}
    >
      <div className="flex items-center justify-between">
        <small className="font-bold uppercase tracking-widest text-slate-400">
          {title}
        </small>

        {active && (
          <span className="inline-flex items-center gap-1 text-[10px] font-extrabold uppercase tracking-wider text-emerald-600">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
            Live
          </span>
        )}
      </div>

      <div className="mt-5 text-3xl font-black text-slate-950">
        {loading ? (
          <span className="inline-flex items-center gap-2">
            <RefreshCw size={22} className="animate-spin text-emerald-600" />
          </span>
        ) : (
          value
        )}
      </div>

      <small className="mt-2 block leading-5 text-slate-500">
        {description}
      </small>
    </div>
  );
}

// ==========================================================
// Occupancy Gauge
// ==========================================================

function OccupancyGauge({ rate }: { rate: number }) {
  const safeRate = clampRate(rate);
  const percentage = safeRate * 100;

  const demand = getDemandLevel(safeRate);
  const styles = getDemandStyles(demand.tone);

  const gaugeAngle = percentage * 0.75;

  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
            AI occupancy gauge
          </p>

          <p className="mt-1 text-sm text-slate-500">
            Expected parking occupancy at the forecast time
          </p>
        </div>

        <span
          className={`rounded-full px-3 py-1 text-xs font-extrabold ring-1 ${styles.badge}`}
        >
          {demand.label}
        </span>
      </div>

      <div className="mt-7 flex justify-center">
        <div
          className="relative h-44 w-44 rounded-full p-4"
          style={{
            background: `conic-gradient(
              from 270deg,
              ${styles.gauge} 0deg ${gaugeAngle * 3.6}deg,
              #e2e8f0 ${gaugeAngle * 3.6}deg 270deg,
              transparent 270deg
            )`,
          }}
        >
          <div className="grid h-full w-full place-items-center rounded-full bg-white shadow-inner">
            <div className="text-center">
              <div className="text-4xl font-black tracking-tight text-slate-950">
                {percentage.toFixed(1)}%
              </div>

              <div className="mt-1 text-xs font-semibold text-slate-400">
                predicted
              </div>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-4 gap-2 text-center text-[10px] font-bold uppercase tracking-wide">
        <div className="rounded-xl bg-emerald-50 px-2 py-2 text-emerald-700">
          Low
          <span className="mt-1 block normal-case text-slate-400">&lt;50%</span>
        </div>

        <div className="rounded-xl bg-amber-50 px-2 py-2 text-amber-700">
          Moderate
          <span className="mt-1 block normal-case text-slate-400">50–74%</span>
        </div>

        <div className="rounded-xl bg-orange-50 px-2 py-2 text-orange-700">
          High
          <span className="mt-1 block normal-case text-slate-400">75–89%</span>
        </div>

        <div className="rounded-xl bg-red-50 px-2 py-2 text-red-700">
          Very high
          <span className="mt-1 block normal-case text-slate-400">90%+</span>
        </div>
      </div>
    </div>
  );
}

// ==========================================================
// Demand Scale
// ==========================================================

function DemandScale({ rate }: { rate: number }) {
  const percentage = clampRate(rate) * 100;

  const markerLeft = Math.min(98, Math.max(2, percentage));

  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
            Demand outlook
          </p>

          <h3 className="mt-1 text-lg font-black text-slate-900">
            How busy is the facility likely to be?
          </h3>
        </div>

        <Gauge className="text-emerald-600" size={21} />
      </div>

      <div className="mt-8">
        <div className="relative h-5 overflow-hidden rounded-full bg-slate-100">
          <div className="absolute inset-y-0 left-0 w-1/2 bg-emerald-400" />

          <div className="absolute inset-y-0 left-1/2 w-1/4 bg-amber-400" />

          <div className="absolute inset-y-0 left-3/4 w-[15%] bg-orange-400" />

          <div className="absolute inset-y-0 right-0 w-[10%] bg-red-500" />

          <div
            className="absolute top-1/2 h-8 w-8 -translate-x-1/2 -translate-y-1/2 rounded-full border-4 border-white bg-slate-950 shadow-lg transition-all duration-700"
            style={{
              left: `${markerLeft}%`,
            }}
            aria-label={`Predicted occupancy ${percentage.toFixed(1)} percent`}
          />
        </div>

        <div className="mt-3 flex justify-between text-[11px] font-bold text-slate-400">
          <span>0%</span>
          <span>50%</span>
          <span>75%</span>
          <span>90%</span>
          <span>100%</span>
        </div>
      </div>

      <div className="mt-7 rounded-2xl bg-slate-50 p-4">
        <div className="flex items-center justify-between gap-4">
          <span className="text-sm font-semibold text-slate-600">
            Predicted occupancy
          </span>

          <span className="text-lg font-black text-slate-950">
            {percentage.toFixed(1)}%
          </span>
        </div>

        <p className="mt-1 text-xs leading-5 text-slate-500">
          This is the model prediction returned by the production inference
          service. It is not a real-time space count.
        </p>
      </div>
    </div>
  );
}

// ==========================================================
// Forecast Timeline
// ==========================================================

function ForecastTimeline({
  predictionTimestamp,
  forecastTimestamp,
}: {
  predictionTimestamp: string;
  forecastTimestamp: string;
}) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
      <div>
        <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
          Forecast timeline
        </p>

        <h3 className="mt-1 text-lg font-black text-slate-900">
          Prediction window
        </h3>

        <p className="mt-1 text-sm text-slate-500">
          The production model currently supports a 30-minute horizon.
        </p>
      </div>

      <div className="relative mt-10 px-3">
        <div className="absolute left-10 right-10 top-3 h-1 rounded-full bg-slate-200" />

        <div className="absolute left-10 top-3 h-1 w-1/2 rounded-full bg-emerald-500" />

        <div className="relative flex items-start justify-between">
          <div className="w-32">
            <div className="grid h-7 w-7 place-items-center rounded-full bg-slate-900 text-white ring-4 ring-slate-100">
              <Clock3 size={13} />
            </div>

            <p className="mt-3 text-xs font-bold uppercase tracking-wider text-slate-400">
              Prediction
            </p>

            <p className="mt-1 text-sm font-black text-slate-900">
              {formatTime(predictionTimestamp)}
            </p>

            <p className="mt-1 text-[11px] text-slate-400">
              {formatDateTime(predictionTimestamp)}
            </p>
          </div>

          <div className="w-32 text-right">
            <div className="ml-auto grid h-7 w-7 place-items-center rounded-full bg-emerald-600 text-white ring-4 ring-emerald-50">
              <TrendingUp size={13} />
            </div>

            <p className="mt-3 text-xs font-bold uppercase tracking-wider text-slate-400">
              Forecast
            </p>

            <p className="mt-1 text-sm font-black text-slate-900">
              {formatTime(forecastTimestamp)}
            </p>

            <p className="mt-1 text-[11px] text-slate-400">
              {formatDateTime(forecastTimestamp)}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ==========================================================
// Driver Insight
// ==========================================================

function DriverInsight({
  rate,
  forecastTimestamp,
}: {
  rate: number;
  forecastTimestamp: string;
}) {
  const demand = getDemandLevel(rate);
  const percentage = clampRate(rate) * 100;

  const message =
    percentage >= 90
      ? "The model expects the facility to be very busy. If your plans are flexible, consider checking another facility."
      : percentage >= 75
        ? "The model expects high demand. Allow extra time for parking and consider arriving earlier."
        : percentage >= 50
          ? "The model expects moderate demand. Parking may be reasonably busy around the forecast time."
          : "The model expects relatively manageable demand around the forecast time.";

  return (
    <div className="rounded-3xl bg-[#071a2d] p-6 text-white shadow-sm">
      <div className="flex items-start gap-4">
        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-emerald-500/15 text-emerald-300">
          <Sparkles size={21} />
        </div>

        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-emerald-300">
            SmartPark AI insight
          </p>

          <h3 className="mt-1 text-xl font-black">{demand.label}</h3>

          <p className="mt-3 text-sm leading-6 text-slate-300">{message}</p>
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Expected occupancy
          </div>

          <div className="mt-1 text-2xl font-black">
            {percentage.toFixed(1)}%
          </div>
        </div>

        <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
            Forecast time
          </div>

          <div className="mt-1 text-2xl font-black">
            {formatTime(forecastTimestamp)}
          </div>
        </div>
      </div>
    </div>
  );
}

// ==========================================================
// Main Forecast Page
// ==========================================================

export default function Forecast() {
  // ========================================================
  // State
  // ========================================================

  const [facilities, setFacilities] = useState<ParkingFacility[]>([]);

  const [selectedFacilityId, setSelectedFacilityId] = useState<number | "">("");

  const [facilitySearch, setFacilitySearch] = useState("");

  const [facilityPickerOpen, setFacilityPickerOpen] = useState(false);

  const [forecast, setForecast] = useState<ForecastResponse | null>(null);

  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>("checking");

  const [loadingFacilities, setLoadingFacilities] = useState(true);

  const [generating, setGenerating] = useState(false);

  const [refreshing, setRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [predictionLatency, setPredictionLatency] = useState<number | null>(
    null,
  );

  // ========================================================
  // Selected Facility
  // ========================================================

  const selectedFacility = useMemo(() => {
    if (selectedFacilityId === "") {
      return null;
    }

    return (
      facilities.find((facility) => facility.id === selectedFacilityId) ?? null
    );
  }, [facilities, selectedFacilityId]);

  const selectedFacilityWithLocation =
    selectedFacility as FacilityWithLocation | null;

  // ========================================================
  // Intelligent Facility Search
  // ========================================================

  const filteredFacilities = useMemo(() => {
    const query = facilitySearch.trim().toLowerCase();

    if (!query) {
      return facilities;
    }

    const terms = query.split(/\s+/).filter(Boolean);

    return facilities.filter((facility) => {
      const haystack = [
        facility.name,
        facility.code,
        facility.id,
        facility.city,
        facility.county,
        facility.country,
        facility.address,
      ]
        .filter((value) => value !== null && value !== undefined)
        .join(" ")
        .toLowerCase();

      return terms.every((term) => haystack.includes(term));
    });
  }, [facilities, facilitySearch]);

  const selectedFacilityLabel = selectedFacility
    ? `${selectedFacility.name}${
        selectedFacility.code ? ` (${selectedFacility.code})` : ""
      } — ID ${selectedFacility.id}`
    : "";

  // ========================================================
  // Load Facilities
  // ========================================================

  const loadFacilities = useCallback(async () => {
    try {
      setLoadingFacilities(true);

      const response = await parkingFacilitiesApi.list(0, 100);

      const activeFacilities = (response.items ?? []).filter(
        (facility) => facility.is_active !== false,
      );

      setFacilities(activeFacilities);

      setSelectedFacilityId((current) => {
        if (
          current !== "" &&
          activeFacilities.some((facility) => facility.id === current)
        ) {
          return current;
        }

        // Prefer facility 47 because it is the
        // currently verified production test facility.
        const knownGoodFacility = activeFacilities.find(
          (facility) => facility.id === KNOWN_GOOD_FACILITY_ID,
        );

        if (knownGoodFacility) {
          return knownGoodFacility.id;
        }

        return activeFacilities.length > 0 ? activeFacilities[0].id : "";
      });
    } catch (err: any) {
      console.error("[SmartPark Forecast] Failed to load facilities:", err);

      setError(extractApiError(err));
    } finally {
      setLoadingFacilities(false);
    }
  }, []);

  // ========================================================
  // Check Forecast Service Health
  // ========================================================

  const checkHealth = useCallback(async () => {
    try {
      setServiceStatus("checking");

      const response = await forecastApi.health();

      setServiceStatus(resolveHealthStatus(response.data));
    } catch (err: any) {
      console.error("[SmartPark Forecast] Health check failed:", err);

      setServiceStatus("offline");
    }
  }, []);

  // ========================================================
  // Generate Production Forecast
  // ========================================================

  const generateForecast = useCallback(
    async (showRefreshingState = false) => {
      if (selectedFacilityId === "") {
        setError(
          "Please select a parking facility before generating a forecast.",
        );

        return;
      }

      if (showRefreshingState) {
        setRefreshing(true);
      } else {
        setGenerating(true);
      }

      setError(null);

      const startedAt = performance.now();

      try {
        const facilityId = Number(selectedFacilityId);

        const currentTimestamp = new Date().toISOString();

        const requestForecast = (predictionTimestamp: string) =>
          forecastApi.forecast(facilityId, {
            prediction_timestamp: predictionTimestamp,
            lookback_minutes: LOOKBACK_MINUTES,
          });

        let response;
        let usedHistoricalFallback = false;

        // ====================================================
        // FIRST ATTEMPT
        // Current live timestamp
        // ====================================================

        try {
          response = await requestForecast(currentTimestamp);
        } catch (firstError: any) {
          const firstErrorMessage = extractApiError(firstError);

          const noObservations =
            /no occupancy observations/i.test(firstErrorMessage) ||
            /no observations/i.test(firstErrorMessage) ||
            /observations.*available/i.test(firstErrorMessage);

          // Never hide authentication,
          // authorization or server failures.
          if (!noObservations) {
            throw firstError;
          }

          // ==================================================
          // HISTORICAL TEST FALLBACK
          //
          // The deployed model may not have current observations
          // available for the requested time. In that case, retry
          // using the verified historical model timestamp.
          //
          // IMPORTANT:
          // Do NOT restrict this fallback to facility 47.
          // requestForecast() still uses the facility selected by
          // the user, so every facility gets its own prediction.
          // ==================================================

          response = await requestForecast(KNOWN_GOOD_FORECAST_TIMESTAMP);

          usedHistoricalFallback = true;
        }

        const latency = Math.round(performance.now() - startedAt);

        setForecast(response.data);

        setPredictionLatency(latency);

        setLastUpdated(new Date());

        // Successful inference means the production
        // forecasting endpoint is operational.
        setServiceStatus("live");

        if (usedHistoricalFallback) {
          setError(
            `The production model does not yet have current occupancy observations. ` +
              `A historical observation window was used for testing. ` +
              `The selected facility was still used for AI inference.`,
          );
        }
      } catch (err: any) {
        console.error("[SmartPark Forecast] Production forecast failed:", err);

        setError(extractApiError(err));
      } finally {
        setGenerating(false);
        setRefreshing(false);
      }
    },
    [selectedFacilityId],
  );

  // ========================================================
  // Initial Page Load
  // ========================================================

  useEffect(() => {
    void loadFacilities();
    void checkHealth();
  }, [loadFacilities, checkHealth]);

  // ========================================================
  // Close Facility Picker When Clicking Outside
  // ========================================================

  useEffect(() => {
    if (!facilityPickerOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;

      if (
        target?.closest("#forecast-facility-search") ||
        target?.closest("#forecast-facility-results")
      ) {
        return;
      }

      setFacilityPickerOpen(false);
    };

    document.addEventListener("mousedown", handlePointerDown);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
    };
  }, [facilityPickerOpen]);

  // ========================================================
  // Generate Forecast When Facility Is Selected
  // ========================================================

  useEffect(() => {
    if (loadingFacilities || selectedFacilityId === "") {
      return;
    }

    if (forecast && forecast.facility_id === selectedFacilityId) {
      return;
    }

    void generateForecast();
  }, [loadingFacilities, selectedFacilityId, forecast, generateForecast]);

  // ========================================================
  // Auto Refresh
  // ========================================================

  useEffect(() => {
    if (selectedFacilityId === "") {
      return;
    }

    const interval = window.setInterval(() => {
      void generateForecast(true);
    }, AUTO_REFRESH_INTERVAL_MS);

    return () => {
      window.clearInterval(interval);
    };
  }, [selectedFacilityId, generateForecast]);

  // ========================================================
  // Handle Facility Change
  // ========================================================

  const handleFacilityChange = (facilityId: number | "") => {
    setForecast(null);

    setPredictionLatency(null);

    setLastUpdated(null);

    setError(null);

    setFacilitySearch("");

    setFacilityPickerOpen(false);

    setSelectedFacilityId(facilityId);
  };

  // ========================================================
  // Full Refresh
  // ========================================================

  const handleRefresh = async () => {
    setError(null);

    await checkHealth();

    await loadFacilities();

    if (selectedFacilityId !== "") {
      await generateForecast(true);
    }
  };

  // ========================================================
  // Make Reservation
  // ========================================================

  const handleMakeReservation = () => {
    if (!selectedFacility) {
      setError("Please select a parking facility before making a reservation.");

      return;
    }

    /*
     * IMPORTANT:
     *
     * We deliberately use window.location instead of
     * react-router-dom so this page does not require the
     * react-router-dom package.
     */

    window.location.assign("/reservations/create");
  };

  // ========================================================
  // Navigate to Facility
  // ========================================================

  const handleNavigateToFacility = () => {
    if (!selectedFacility) {
      setError("Please select a parking facility before starting navigation.");

      return;
    }

    const facility = selectedFacilityWithLocation;

    const latitude = Number(
      facility?.latitude ?? facility?.lat ?? facility?.latitude_deg,
    );

    const longitude = Number(
      facility?.longitude ?? facility?.lng ?? facility?.longitude_deg,
    );

    let mapsUrl: string;

    /*
     * Prefer exact coordinates if the backend provides them.
     */
    if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
      mapsUrl =
        `https://www.google.com/maps/dir/?api=1` +
        `&destination=${encodeURIComponent(`${latitude},${longitude}`)}`;
    } else {
      /*
       * Otherwise use the facility name/address as the
       * Google Maps destination.
       */
      const destination = [
        selectedFacility.name,
        selectedFacility.address,
        selectedFacility.city,
        selectedFacility.county,
        selectedFacility.country,
      ]
        .filter(Boolean)
        .join(", ");

      mapsUrl =
        `https://www.google.com/maps/search/?api=1` +
        `&query=${encodeURIComponent(destination)}`;
    }

    window.open(mapsUrl, "_blank", "noopener,noreferrer");
  };

  // ========================================================
  // Derived Forecast Information
  // ========================================================

  const predictedRate = forecast?.predicted_occupancy_rate ?? null;

  const demand = getDemandLevel(predictedRate);

  const demandStyles = getDemandStyles(demand.tone);

  const progressWidth =
    predictedRate === null ? 0 : clampRate(predictedRate) * 100;

  // ========================================================
  // Recommendation
  // ========================================================

  const recommendation =
    predictedRate === null
      ? "Generate a production forecast to receive an AI-assisted parking demand recommendation."
      : predictedRate >= 0.9
        ? "Very high parking demand is expected. Consider securing a parking space early or checking another nearby facility."
        : predictedRate >= 0.75
          ? "High parking demand is expected. Reserving your parking space early is recommended."
          : predictedRate >= 0.5
            ? "Moderate parking demand is expected. Consider securing your parking space before travelling."
            : "Current production prediction indicates relatively manageable parking demand at the forecast time.";

  // ========================================================
  // Render
  // ========================================================

  return (
    <div className="space-y-6">
      {/* ==================================================
          HERO
      ================================================== */}

      <section className="rounded-3xl bg-[#071a2d] p-7 text-white">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[.2em] text-emerald-300">
              <BrainCircuit size={16} />
              Production AI Forecasting
            </div>

            <h1 className="mt-3 text-3xl font-black">
              Predict parking demand before you arrive.
            </h1>

            <p className="mt-2 max-w-2xl text-slate-300">
              SmartPark AI uses the production forecasting service to predict
              parking occupancy 30 minutes into the future.
            </p>
          </div>

          <StatusBadge status={serviceStatus} />
        </div>
      </section>

      {/* ==================================================
          SERVICE MESSAGE
      ================================================== */}

      {error && (
        <div
          className={`rounded-2xl border p-4 ${
            error.includes("historical observation")
              ? "border-amber-200 bg-amber-50"
              : "border-red-200 bg-red-50"
          }`}
        >
          <div className="flex items-start gap-3">
            <AlertCircle
              size={20}
              className={`mt-0.5 shrink-0 ${
                error.includes("historical observation")
                  ? "text-amber-600"
                  : "text-red-600"
              }`}
            />

            <div className="min-w-0 flex-1">
              <b
                className={`text-sm ${
                  error.includes("historical observation")
                    ? "text-amber-800"
                    : "text-red-800"
                }`}
              >
                Forecast service message
              </b>

              <p
                className={`mt-1 text-sm leading-6 ${
                  error.includes("historical observation")
                    ? "text-amber-700"
                    : "text-red-700"
                }`}
              >
                {error}
              </p>
            </div>

            <button
              type="button"
              onClick={() => setError(null)}
              className={`text-lg font-bold ${
                error.includes("historical observation")
                  ? "text-amber-500 hover:text-amber-700"
                  : "text-red-500 hover:text-red-700"
              }`}
              aria-label="Dismiss message"
            >
              ×
            </button>
          </div>
        </div>
      )}

      {/* ==================================================
          FACILITY SELECTOR
      ================================================== */}

      <Card
        title="Forecast location"
        sub="Search and choose the parking facility for the AI prediction"
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
          <div className="relative min-w-0 flex-1">
            <label
              htmlFor="forecast-facility-search"
              className="mb-2 block text-xs font-bold uppercase tracking-widest text-slate-400"
            >
              Parking Facility
            </label>

            {/* ==================================================
                Search Input
            ================================================== */}

            <div className="relative">
              <Search
                size={18}
                className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"
              />

              <input
                id="forecast-facility-search"
                type="text"
                value={
                  facilityPickerOpen
                    ? facilitySearch
                    : selectedFacility
                      ? selectedFacilityLabel
                      : facilitySearch
                }
                onChange={(event) => {
                  setFacilitySearch(event.target.value);

                  setFacilityPickerOpen(true);
                }}
                onFocus={() => {
                  setFacilityPickerOpen(true);

                  if (selectedFacility) {
                    setFacilitySearch("");
                  }
                }}
                onKeyDown={(event) => {
                  if (event.key === "Escape") {
                    setFacilityPickerOpen(false);

                    setFacilitySearch("");

                    return;
                  }

                  if (event.key === "Enter" && filteredFacilities.length > 0) {
                    event.preventDefault();

                    handleFacilityChange(filteredFacilities[0].id);
                  }
                }}
                placeholder={
                  loadingFacilities
                    ? "Loading parking facilities..."
                    : "Search facility name, code, city or ID..."
                }
                disabled={loadingFacilities || generating}
                autoComplete="off"
                role="combobox"
                aria-expanded={facilityPickerOpen}
                aria-controls="forecast-facility-results"
                className="min-h-12 w-full rounded-2xl border border-slate-200 bg-white py-3 pl-11 pr-20 text-sm font-semibold text-slate-800 outline-none transition focus:border-emerald-500 focus:ring-4 focus:ring-emerald-100 disabled:bg-slate-50"
              />

              {facilitySearch && (
                <button
                  type="button"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => setFacilitySearch("")}
                  disabled={loadingFacilities || generating}
                  className="absolute right-11 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50"
                  aria-label="Clear facility search"
                >
                  <X size={16} />
                </button>
              )}

              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => setFacilityPickerOpen((open) => !open)}
                disabled={loadingFacilities || generating}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50"
                aria-label={
                  facilityPickerOpen
                    ? "Close facility search results"
                    : "Open facility search results"
                }
              >
                <ChevronDown
                  size={18}
                  className={`transition-transform ${
                    facilityPickerOpen ? "rotate-180" : ""
                  }`}
                />
              </button>
            </div>

            {/* ==================================================
                Search Results
            ================================================== */}

            {facilityPickerOpen && !loadingFacilities && (
              <div
                id="forecast-facility-results"
                className="absolute left-0 right-0 z-30 mt-2 max-h-80 overflow-y-auto rounded-2xl border border-slate-200 bg-white p-2 shadow-xl ring-1 ring-black/5"
                role="listbox"
              >
                <div className="px-3 py-2 text-[11px] font-bold uppercase tracking-wider text-slate-400">
                  {facilitySearch.trim()
                    ? `${filteredFacilities.length} matching ${
                        filteredFacilities.length === 1
                          ? "facility"
                          : "facilities"
                      }`
                    : `${facilities.length} available facilities`}
                </div>

                {filteredFacilities.length > 0 ? (
                  filteredFacilities.map((facility) => {
                    const isSelected = facility.id === selectedFacilityId;

                    return (
                      <button
                        key={facility.id}
                        type="button"
                        role="option"
                        aria-selected={isSelected}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => handleFacilityChange(facility.id)}
                        className={`w-full rounded-xl px-3 py-3 text-left transition ${
                          isSelected
                            ? "bg-emerald-50 ring-1 ring-emerald-200"
                            : "hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <div
                              className={`truncate text-sm font-bold ${
                                isSelected
                                  ? "text-emerald-800"
                                  : "text-slate-800"
                              }`}
                            >
                              {facility.name}
                            </div>

                            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                              {facility.code && (
                                <span className="font-semibold">
                                  {facility.code}
                                </span>
                              )}

                              <span>ID {facility.id}</span>

                              {(facility.city ||
                                facility.county ||
                                facility.country) && (
                                <span className="inline-flex items-center gap-1">
                                  <MapPin size={12} />

                                  {facility.city ??
                                    facility.county ??
                                    facility.country}
                                </span>
                              )}
                            </div>

                            {facility.address && (
                              <div className="mt-1 truncate text-xs text-slate-400">
                                {facility.address}
                              </div>
                            )}
                          </div>

                          {isSelected && (
                            <CheckCircle2
                              size={18}
                              className="mt-0.5 shrink-0 text-emerald-600"
                            />
                          )}
                        </div>
                      </button>
                    );
                  })
                ) : (
                  <div className="px-4 py-8 text-center">
                    <Search size={28} className="mx-auto text-slate-300" />

                    <p className="mt-3 text-sm font-bold text-slate-700">
                      No facilities found
                    </p>

                    <p className="mt-1 text-xs leading-5 text-slate-500">
                      Try searching by facility name, code, city or facility ID.
                    </p>

                    <button
                      type="button"
                      onClick={() => setFacilitySearch("")}
                      className="mt-3 text-xs font-bold text-emerald-600 hover:text-emerald-700"
                    >
                      Clear search
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* ==================================================
                Selected Facility Details
            ================================================== */}

            {selectedFacility && (
              <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-slate-500">
                <span className="inline-flex items-center gap-1.5">
                  <MapPin size={13} />

                  {selectedFacility.city ??
                    selectedFacility.county ??
                    selectedFacility.country}
                </span>

                {selectedFacility.address && (
                  <span>{selectedFacility.address}</span>
                )}
              </div>
            )}
          </div>

          {/* ==================================================
              Forecast Actions
          ================================================== */}

          <div className="flex shrink-0 items-center gap-3 lg:pt-[1.75rem]">
            <button
              type="button"
              onClick={() => void generateForecast()}
              disabled={selectedFacilityId === "" || generating}
              className="inline-flex min-h-12 min-w-[196px] items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-6 text-sm font-extrabold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {generating ? (
                <>
                  <RefreshCw size={17} className="animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Sparkles size={17} />
                  Generate Forecast
                </>
              )}
            </button>

            <button
              type="button"
              onClick={() => void handleRefresh()}
              disabled={refreshing || generating}
              className="inline-flex min-h-12 min-w-[120px] items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RefreshCw
                size={17}
                className={refreshing ? "animate-spin" : ""}
              />
              Refresh
            </button>
          </div>
        </div>
      </Card>

      {/* ==================================================
          FORECAST HORIZONS
      ================================================== */}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <HorizonCard
          title="30 Minutes"
          value={
            forecast ? formatPercentage(forecast.predicted_occupancy_rate) : "—"
          }
          description={
            forecast
              ? "Live production prediction"
              : generating
                ? "Generating prediction..."
                : "Awaiting prediction"
          }
          active
          loading={generating && !forecast}
        />

        <HorizonCard
          title="1 Hour"
          value="—"
          description="Not supported by the current production model"
        />

        <HorizonCard
          title="2 Hours"
          value="—"
          description="Not supported by the current production model"
        />

        <HorizonCard
          title="Tomorrow Morning"
          value="—"
          description="Not supported by the current production model"
        />
      </div>

      {/* ==================================================
          LIVE OCCUPANCY FORECAST
      ================================================== */}

      <Card
        title="Occupancy forecast"
        sub={
          selectedFacility
            ? `Production forecast for ${selectedFacility.name}`
            : "Production forecast service"
        }
      >
        {!forecast && !generating && (
          <div className="rounded-2xl bg-slate-50 p-10 text-center">
            <BrainCircuit className="mx-auto text-slate-400" size={36} />

            <p className="mt-3 font-bold text-slate-700">Awaiting prediction</p>

            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">
              Select a parking facility and generate a production AI forecast.
            </p>
          </div>
        )}

        {generating && !forecast && (
          <div className="rounded-2xl bg-slate-50 p-10 text-center">
            <div className="mx-auto grid h-14 w-14 place-items-center rounded-full bg-emerald-50">
              <RefreshCw size={27} className="animate-spin text-emerald-600" />
            </div>

            <p className="mt-4 font-black text-slate-700">
              Running production inference...
            </p>

            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">
              SmartPark AI is retrieving historical occupancy observations and
              generating the production prediction.
            </p>
          </div>
        )}

        {forecast && (
          <div className="space-y-6">
            {/* ==================================================
                Prediction Summary
            ================================================== */}

            <div className="rounded-3xl bg-slate-50 p-6">
              <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="text-xs font-bold uppercase tracking-widest text-slate-400">
                    Predicted Occupancy
                  </div>

                  <div className="mt-2 text-5xl font-black tracking-tight text-slate-950">
                    {formatPercentage(forecast.predicted_occupancy_rate)}
                  </div>

                  <div className="mt-3">
                    <span
                      className={`inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-extrabold ring-1 ${demandStyles.badge}`}
                    >
                      <span className="h-2 w-2 rounded-full bg-current" />

                      {demand.label}
                    </span>
                  </div>

                  <p className="mt-3 max-w-xl text-sm leading-6 text-slate-500">
                    {demand.description}
                  </p>
                </div>

                {/* ==================================================
                    Forecast Time
                ================================================== */}

                <div className="min-w-[250px] rounded-2xl bg-white p-5 ring-1 ring-slate-200">
                  <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-slate-400">
                    <Clock3 size={14} />
                    Forecast Time
                  </div>

                  <div className="mt-2 text-xl font-black text-slate-900">
                    {formatTime(forecast.forecast_timestamp)}
                  </div>

                  <div className="mt-1 text-sm text-slate-500">
                    {formatDateTime(forecast.forecast_timestamp)}
                  </div>

                  <div className="mt-4 border-t border-slate-100 pt-3">
                    <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                      Prediction generated from
                    </div>

                    <div className="mt-1 text-xs font-semibold text-slate-600">
                      {formatDateTime(forecast.prediction_timestamp)}
                    </div>
                  </div>
                </div>
              </div>

              {/* ==================================================
                  Occupancy Progress Bar
              ================================================== */}

              <div className="mt-8">
                <div className="mb-2 flex items-center justify-between text-xs font-bold text-slate-500">
                  <span>Expected occupancy</span>

                  <span>
                    {formatPercentage(forecast.predicted_occupancy_rate)}
                  </span>
                </div>

                <div className="h-4 overflow-hidden rounded-full bg-slate-200">
                  <div
                    className={`h-full rounded-full transition-all duration-700 ${demandStyles.bar}`}
                    style={{
                      width: `${progressWidth}%`,
                    }}
                  />
                </div>

                <div className="mt-2 flex justify-between text-[11px] font-semibold text-slate-400">
                  <span>0%</span>
                  <span>25%</span>
                  <span>50%</span>
                  <span>75%</span>
                  <span>100%</span>
                </div>
              </div>
            </div>

            {/* ==================================================
                Visual Analytics
            ================================================== */}

            <div className="grid gap-6 lg:grid-cols-2">
              <OccupancyGauge rate={forecast.predicted_occupancy_rate} />

              <DemandScale rate={forecast.predicted_occupancy_rate} />
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <ForecastTimeline
                predictionTimestamp={forecast.prediction_timestamp}
                forecastTimestamp={forecast.forecast_timestamp}
              />

              <DriverInsight
                rate={forecast.predicted_occupancy_rate}
                forecastTimestamp={forecast.forecast_timestamp}
              />
            </div>

            {/* ==================================================
                Forecast Metadata
            ================================================== */}

            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
              <div className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                  <Clock3 size={14} />
                  Horizon
                </div>

                <div className="mt-2 text-lg font-black text-slate-900">
                  {forecast.forecast_horizon_minutes} minutes
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                  <BrainCircuit size={14} />
                  Model
                </div>

                <div className="mt-2 break-all text-lg font-black text-slate-900">
                  {forecast.model_candidate || "—"}
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                  <Gauge size={14} />
                  Features
                </div>

                <div className="mt-2 text-lg font-black text-slate-900">
                  {forecast.feature_count}
                </div>

                <div className="text-xs text-slate-500">
                  Production feature set
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 p-4">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
                  <Activity size={14} />
                  Latency
                </div>

                <div className="mt-2 text-lg font-black text-slate-900">
                  {predictionLatency !== null ? `${predictionLatency} ms` : "—"}
                </div>

                <div className="text-xs text-slate-500">
                  API inference request
                </div>
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* ==================================================
          AI RECOMMENDATION + MODEL STATUS
      ================================================== */}

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ==================================================
            AI RECOMMENDATION
        ================================================== */}

        <Card title="AI recommendation" sub="Decision support">
          <div
            className={`rounded-2xl p-5 ${
              forecast ? demandStyles.badge : "bg-slate-50"
            }`}
          >
            <div className="flex items-start gap-3">
              <div
                className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${
                  forecast ? demandStyles.icon : "bg-white text-slate-400"
                }`}
              >
                <TrendingUp size={20} />
              </div>

              <div>
                <b className={forecast ? "" : "text-slate-700"}>
                  {forecast ? demand.label : "Awaiting prediction"}
                </b>

                <p className="mt-2 text-sm leading-6 opacity-90">
                  {recommendation}
                </p>
              </div>
            </div>
          </div>

          {forecast && (
            <div className="mt-4 flex items-center gap-2 text-xs font-semibold text-slate-400">
              <Sparkles size={14} />
              Recommendation generated from the production forecast.
            </div>
          )}
        </Card>

        {/* ==================================================
            MODEL STATUS
        ================================================== */}

        <Card title="Model status" sub="Production intelligence">
          <div className="divide-y divide-slate-100">
            {/* Forecast Service */}

            <div className="flex items-center justify-between gap-4 py-3">
              <div className="flex items-center gap-3">
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                  <ServerCog size={17} />
                </div>

                <span className="text-sm font-semibold text-slate-600">
                  Forecast service
                </span>
              </div>

              <StatusBadge status={serviceStatus} />
            </div>

            {/* Feature Builder */}

            <div className="flex items-center justify-between gap-4 py-3">
              <div className="flex items-center gap-3">
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-blue-50 text-blue-600">
                  <Gauge size={17} />
                </div>

                <span className="text-sm font-semibold text-slate-600">
                  Feature Builder
                </span>
              </div>

              {forecast ? (
                <span className="inline-flex items-center gap-1.5 text-sm font-bold text-emerald-600">
                  <CheckCircle2 size={16} />
                  Validated
                </span>
              ) : (
                <span className="text-sm font-bold text-slate-400">
                  Pending
                </span>
              )}
            </div>

            {/* Model Inference */}

            <div className="flex items-center justify-between gap-4 py-3">
              <div className="flex items-center gap-3">
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-violet-50 text-violet-600">
                  <BrainCircuit size={17} />
                </div>

                <span className="text-sm font-semibold text-slate-600">
                  Model inference
                </span>
              </div>

              {forecast ? (
                <span className="inline-flex items-center gap-1.5 text-sm font-bold text-emerald-600">
                  <CheckCircle2 size={16} />
                  Successful
                </span>
              ) : generating ? (
                <span className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-500">
                  <RefreshCw size={15} className="animate-spin" />
                  Running
                </span>
              ) : (
                <span className="text-sm font-bold text-slate-400">
                  Pending
                </span>
              )}
            </div>

            {/* Prediction Latency */}

            <div className="flex items-center justify-between gap-4 py-3">
              <div className="flex items-center gap-3">
                <div className="grid h-9 w-9 place-items-center rounded-xl bg-amber-50 text-amber-600">
                  <Clock3 size={17} />
                </div>

                <span className="text-sm font-semibold text-slate-600">
                  Prediction latency
                </span>
              </div>

              <b className="text-sm text-slate-600">
                {predictionLatency !== null ? `${predictionLatency} ms` : "—"}
              </b>
            </div>
          </div>
        </Card>
      </div>

      {/* ==================================================
          QUICK ACTIONS
      ================================================== */}

      {forecast && selectedFacility && (
        <Card
          title="Take Action"
          sub={`Reserve a parking space at ${selectedFacility.name}`}
        >
          <div className="rounded-3xl bg-slate-50 p-5">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-start gap-4">
                <div className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-emerald-100 text-emerald-600">
                  <MapPin size={22} />
                </div>

                <div>
                  <div className="text-sm font-bold text-slate-900">
                    {selectedFacility.name}
                  </div>

                  <div className="mt-1 text-xs text-slate-500">
                    {selectedFacility.code ? `${selectedFacility.code} • ` : ""}
                    Facility ID {selectedFacility.id}
                  </div>

                  {selectedFacility.address && (
                    <div className="mt-1 text-xs text-slate-400">
                      {selectedFacility.address}
                    </div>
                  )}
                </div>
              </div>

              <div className="flex flex-col gap-3 sm:flex-row">
                {/* ==================================================
                    MAKE A RESERVATION
                ================================================== */}

                <button
                  type="button"
                  onClick={handleMakeReservation}
                  className="inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl bg-emerald-600 px-5 text-sm font-extrabold text-white shadow-sm transition hover:bg-emerald-700 hover:shadow-md"
                >
                  <CalendarPlus size={18} />
                  Make a Reservation
                </button>

                {/* ==================================================
                    NAVIGATE
                ================================================== */}

                <button
                  type="button"
                  onClick={handleNavigateToFacility}
                  className="inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl border border-slate-200 bg-white px-5 text-sm font-extrabold text-slate-700 shadow-sm transition hover:bg-slate-100 hover:shadow-md"
                >
                  <Navigation size={18} />
                  Navigate to Facility
                  <ExternalLink size={14} className="text-slate-400" />
                </button>
              </div>
            </div>

            <div className="mt-4 flex items-center gap-2 text-xs text-slate-400">
              <Sparkles size={14} />
              Based on the selected facility and current AI forecast.
            </div>
          </div>
        </Card>
      )}

      {/* ==================================================
          PRODUCTION FORECAST DETAILS
      ================================================== */}

      {forecast && (
        <Card
          title="Production forecast details"
          sub="Read-only metadata returned by the forecasting service"
        >
          <div className="grid gap-5 md:grid-cols-2">
            <div>
              <div className="text-xs font-bold uppercase tracking-widest text-slate-400">
                Target column
              </div>

              <div className="mt-2 break-all rounded-xl bg-slate-50 px-4 py-3 font-mono text-sm font-semibold text-slate-700">
                {forecast.target_column}
              </div>
            </div>

            <div>
              <div className="text-xs font-bold uppercase tracking-widest text-slate-400">
                Feature information
              </div>

              <div className="mt-2 rounded-xl bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700">
                {forecast.feature_information ||
                  "Available at or before prediction timestamp"}
              </div>
            </div>

            <div>
              <div className="text-xs font-bold uppercase tracking-widest text-slate-400">
                Inference mode
              </div>

              <div className="mt-2 flex items-center gap-2 rounded-xl bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700">
                {forecast.inference_only ? (
                  <>
                    <CheckCircle2 size={17} className="text-emerald-600" />
                    Inference only
                  </>
                ) : (
                  <>
                    <AlertCircle size={17} className="text-amber-600" />
                    Non-inference mode
                  </>
                )}
              </div>
            </div>

            <div>
              <div className="text-xs font-bold uppercase tracking-widest text-slate-400">
                Last prediction
              </div>

              <div className="mt-2 rounded-xl bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700">
                {lastUpdated ? formatDateTime(lastUpdated) : "—"}
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* ==================================================
          FOOTER
      ================================================== */}

      <div className="flex flex-col gap-2 text-xs text-slate-400 sm:flex-row sm:items-center sm:justify-between">
        <div>
          {lastUpdated
            ? `Forecast updated ${formatDateTime(lastUpdated)}`
            : "No production forecast generated yet."}
        </div>

        <div className="flex items-center gap-2">
          <ServerCog size={14} />
          SmartPark AI Production Forecasting
        </div>
      </div>
    </div>
  );
}
