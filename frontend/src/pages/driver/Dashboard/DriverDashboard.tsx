import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import {
  ArrowRight,
  BrainCircuit,
  CalendarPlus,
  Clock3,
  Navigation,
  ParkingCircle,
  RefreshCw,
  TrendingUp,
} from "lucide-react";

import { useAuth } from "../../../auth/AuthContext";
import {
  forecastApi,
  parkingBaysApi,
  parkingFacilitiesApi,
  parkingReservationsApi,
  parkingSessionsApi,
  parkingZonesApi,
  type ParkingBay,
  type ParkingFacility,
  type ParkingReservation,
  type ParkingSession,
  type ParkingZone,
} from "../../../api";
import { Card, Metric } from "../../../components/common/Page";

export default function DriverDashboard() {
  const { user } = useAuth();

  const [facilities, setFacilities] = useState<ParkingFacility[]>([]);
  const [zones, setZones] = useState<ParkingZone[]>([]);
  const [bays, setBays] = useState<ParkingBay[]>([]);
  const [activeSessions, setActiveSessions] = useState<ParkingSession[]>([]);
  const [reservations, setReservations] = useState<ParkingReservation[]>([]);
  const [forecastStatus, setForecastStatus] = useState<string>("Checking...");
  const [forecastModel, setForecastModel] = useState<string | null>(null);
  const [location, setLocation] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshVersion, setRefreshVersion] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const loadDashboard = async () => {
      setLoading(true);
      setError(null);

      const results = await Promise.allSettled([
        parkingFacilitiesApi.list(0, 500),
        parkingZonesApi.list(0, 500),
        parkingBaysApi.list(0, 500),
        parkingSessionsApi.active(),
        user
          ? parkingReservationsApi.activeByCustomer(user.id)
          : Promise.resolve({ items: [], total: 0 }),
        forecastApi.health(),
      ]);

      if (cancelled) return;

      const failures: string[] = [];

      const [
        facilityResult,
        zoneResult,
        bayResult,
        sessionResult,
        reservationResult,
        forecastResult,
      ] = results;

      if (facilityResult.status === "fulfilled")
        setFacilities(facilityResult.value.items);
      else failures.push("parking facilities");

      if (zoneResult.status === "fulfilled") setZones(zoneResult.value.items);
      else failures.push("parking zones");

      if (bayResult.status === "fulfilled") setBays(bayResult.value.items);
      else failures.push("parking bays");

      if (sessionResult.status === "fulfilled")
        setActiveSessions(sessionResult.value.items);
      else failures.push("active parking sessions");

      if (reservationResult.status === "fulfilled")
        setReservations(reservationResult.value.items);
      else failures.push("your reservations");

      if (forecastResult.status === "fulfilled") {
        const data = forecastResult.value.data as {
          status?: string;
          diagnostics?: { model?: { candidate?: string; name?: string } };
        };

        const status = String(data.status ?? "unknown").toLowerCase();

        setForecastStatus(
          status === "ready" || status === "healthy" ? "Online" : status,
        );

        setForecastModel(
          data.diagnostics?.model?.candidate ??
            data.diagnostics?.model?.name ??
            null,
        );
      } else {
        setForecastStatus("Unavailable");
      }

      if (failures.length > 0) {
        setError(
          `Your session has ended. Some live dashboard data could not be loaded: ${failures.join(", ")}. Please login again.`,
        );
      }

      setLoading(false);
      setIsRefreshing(false);
    };

    void loadDashboard();

    const refreshTimer = window.setInterval(() => {
      void loadDashboard();
    }, 30000);

    return () => {
      cancelled = true;
      window.clearInterval(refreshTimer);
    };
  }, [user, refreshVersion]);

  useEffect(() => {
    if (!navigator.geolocation) return;

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
      },
      () => {
        // Location is optional. The dashboard still works without it.
      },
      { enableHighAccuracy: false, timeout: 5000, maximumAge: 300000 },
    );
  }, []);

  const zoneFacilityMap = useMemo(() => {
    return new Map(zones.map((zone) => [zone.id, zone.facility_id]));
  }, [zones]);

  const activeSessionBayIds = useMemo(
    () => new Set(activeSessions.map((session) => session.parking_bay_id)),
    [activeSessions],
  );

  const facilityStats = useMemo(() => {
    const stats = new Map<number, { total: number; available: number }>();

    for (const facility of facilities) {
      stats.set(facility.id, { total: 0, available: 0 });
    }

    for (const bay of bays) {
      if (!bay.is_active) continue;

      const facilityId = zoneFacilityMap.get(bay.zone_id);
      if (!facilityId) continue;

      const current = stats.get(facilityId) ?? { total: 0, available: 0 };
      current.total += 1;

      if (!activeSessionBayIds.has(bay.id)) {
        current.available += 1;
      }

      stats.set(facilityId, current);
    }

    return stats;
  }, [facilities, bays, zoneFacilityMap, activeSessionBayIds]);

  const nearestFacility = useMemo(() => {
    if (facilities.length === 0) return null;

    const distance = (facility: ParkingFacility) => {
      if (
        !location ||
        typeof facility.latitude !== "number" ||
        typeof facility.longitude !== "number"
      ) {
        return Number.POSITIVE_INFINITY;
      }

      const lat1 = (location.latitude * Math.PI) / 180;
      const lat2 = (facility.latitude * Math.PI) / 180;
      const dLat = ((facility.latitude - location.latitude) * Math.PI) / 180;
      const dLon = ((facility.longitude - location.longitude) * Math.PI) / 180;

      const a =
        Math.sin(dLat / 2) ** 2 +
        Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;

      return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    };

    return (
      [...facilities]
        .filter((facility) => facility.is_active !== false)
        .sort((a, b) => distance(a) - distance(b))[0] ?? facilities[0]
    );
  }, [facilities, location]);

  // ==========================================================
  // Distance to the selected nearest facility
  // ==========================================================

  const nearestFacilityDistanceKm = useMemo(() => {
    if (
      !nearestFacility ||
      !location ||
      typeof nearestFacility.latitude !== "number" ||
      typeof nearestFacility.longitude !== "number"
    ) {
      return null;
    }

    const lat1 = (location.latitude * Math.PI) / 180;
    const lat2 = (nearestFacility.latitude * Math.PI) / 180;

    const dLat =
      ((nearestFacility.latitude - location.latitude) * Math.PI) / 180;

    const dLon =
      ((nearestFacility.longitude - location.longitude) * Math.PI) / 180;

    const a =
      Math.sin(dLat / 2) ** 2 +
      Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;

    return 6371 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  }, [nearestFacility, location]);

  const nearestStats = nearestFacility
    ? (facilityStats.get(nearestFacility.id) ?? {
        total: 0,
        available: 0,
      })
    : { total: 0, available: 0 };

  const nextReservation = useMemo(() => {
    const now = Date.now();

    return (
      [...reservations]
        .filter(
          (reservation) =>
            new Date(reservation.reserved_until).getTime() >= now,
        )
        .sort(
          (a, b) =>
            new Date(a.reserved_from).getTime() -
            new Date(b.reserved_from).getTime(),
        )[0] ?? null
    );
  }, [reservations]);

  const occupancyRate =
    nearestStats.total > 0
      ? Math.round(
          ((nearestStats.total - nearestStats.available) / nearestStats.total) *
            100,
        )
      : null;

  const refresh = () => {
    setIsRefreshing(true);
    setRefreshVersion((current) => current + 1);
  };

  const createReservationUrl = nearestFacility
    ? `/reservations/create?facilityId=${encodeURIComponent(
        String(nearestFacility.id),
      )}&facilityName=${encodeURIComponent(nearestFacility.name)}`
    : "/reservations";

  const navigationUrl =
    nearestFacility &&
    typeof nearestFacility.latitude === "number" &&
    typeof nearestFacility.longitude === "number"
      ? `https://www.google.com/maps/dir/?api=1&destination=${nearestFacility.latitude},${nearestFacility.longitude}`
      : null;

  return (
    <div className="space-y-6">
      {/* ==========================================================
          HERO / WELCOME
      ========================================================== */}
      <section className="relative overflow-hidden rounded-3xl bg-[#071a2d] px-5 py-6 text-white shadow-sm sm:px-7 sm:py-7 lg:px-8">
        <div className="pointer-events-none absolute -right-20 -top-24 h-64 w-64 rounded-full bg-emerald-400/[0.07] blur-2xl" />
        <div className="pointer-events-none absolute -bottom-28 right-24 h-56 w-56 rounded-full bg-cyan-400/[0.045] blur-3xl" />

        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0 max-w-2xl">
            <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-emerald-400/15 bg-emerald-400/[0.07] px-3 py-1.5 text-[10px] font-medium uppercase tracking-[0.16em] text-emerald-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              AI-powered parking intelligence
            </div>

            <h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">
              Welcome to SmartPark.
            </h1>

            <p className="mt-2 max-w-xl text-sm leading-6 text-slate-300">
              Find nearby parking, reserve spaces and use AI-powered occupancy
              predictions before you arrive.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <Link
              to="/parking"
              className="inline-flex items-center justify-center rounded-xl bg-emerald-400 px-4 py-2.5 text-xs font-semibold text-[#071a2d] transition hover:bg-emerald-300 focus:outline-none focus:ring-2 focus:ring-emerald-300/60 focus:ring-offset-2 focus:ring-offset-[#071a2d]"
            >
              Find Parking Space
            </Link>

            <Link
              to="/forecast"
              className="inline-flex items-center justify-center rounded-xl border border-white/10 bg-white/[0.05] px-4 py-2.5 text-xs font-medium text-white transition hover:bg-white/[0.09] focus:outline-none focus:ring-2 focus:ring-white/30"
            >
              View AI Prediction
            </Link>

            <button
              type="button"
              onClick={refresh}
              disabled={isRefreshing}
              aria-label="Refresh dashboard data"
              className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border border-white/10 bg-white/[0.035] px-3.5 py-2.5 text-xs font-medium text-slate-200 transition hover:bg-white/[0.08] disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw
                size={15}
                className={isRefreshing ? "animate-spin" : ""}
              />
              {isRefreshing ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>
      </section>

      {/* ==========================================================
          PARTIAL-DATA WARNING
      ========================================================== */}
      {error && (
        <div className="flex flex-col gap-3 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3.5 text-xs text-amber-800 sm:flex-row sm:items-center sm:justify-between">
          <span className="leading-5">{error}</span>

          <button
            type="button"
            onClick={refresh}
            disabled={isRefreshing}
            className="shrink-0 self-start rounded-lg bg-white px-3 py-1.5 text-xs font-medium text-amber-800 ring-1 ring-amber-200 transition hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
          >
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      )}

      {/* ==========================================================
          KEY METRICS
      ========================================================== */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4 [&>div]:!min-h-0 [&>div]:!p-4">
        <Metric
          label="Available spaces"
          value={
            loading
              ? "..."
              : nearestFacility
                ? String(nearestStats.available)
                : "0"
          }
          note={
            nearestFacility ? "Live bay & session data" : "No active facilities"
          }
          Icon={ParkingCircle}
        />

        <Metric
          label="Nearest facility"
          value={loading ? "..." : (nearestFacility?.name ?? "None")}
          note={
            nearestFacility && location
              ? `${nearestFacility.city} · location enabled`
              : "Using facility list"
          }
          Icon={Navigation}
        />

        <Metric
          label="Occupancy"
          value={occupancyRate === null ? "—" : `${occupancyRate}%`}
          note="Derived from active sessions"
          Icon={TrendingUp}
        />

        <Metric
          label="Next reservation"
          value={
            nextReservation
              ? formatReservationTime(nextReservation.reserved_from)
              : "None"
          }
          note={
            nextReservation
              ? nextReservation.reservation_number
              : "No active reservation"
          }
          Icon={Clock3}
        />
      </div>

      {/* ==========================================================
          PRIMARY WORKSPACE
      ========================================================== */}
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(320px,0.75fr)]">
        <Card
          title="Nearby Parking Facility"
          sub="Live availability from SmartPark AI"
        >
          {nearestFacility ? (
            <div className="rounded-2xl border border-slate-200/80 bg-slate-50/80 p-4 sm:p-5">
              <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="flex items-start gap-3">
                    <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-emerald-100 text-emerald-700">
                      <ParkingCircle size={18} />
                    </span>

                    <div className="min-w-0">
                      <h2 className="truncate text-base font-semibold text-slate-900">
                        {nearestFacility.name}
                      </h2>

                      {nearestFacility.facility_type && (
                        <p className="mt-1 text-[11px] font-medium uppercase tracking-[0.12em] text-slate-500">
                          {nearestFacility.facility_type}
                        </p>
                      )}

                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        {nearestFacility.address}, {nearestFacility.city}
                      </p>

                      {nearestFacilityDistanceKm !== null && (
                        <p className="mt-1 text-xs font-medium text-emerald-700">
                          {nearestFacilityDistanceKm.toFixed(1)} km away
                        </p>
                      )}
                    </div>
                  </div>
                </div>

                <span className="inline-flex w-fit shrink-0 items-center rounded-full bg-emerald-100 px-3 py-1.5 text-xs font-medium text-emerald-700">
                  {nearestStats.available} available
                </span>
              </div>

              <div className="mt-5 grid grid-cols-3 gap-2.5">
                <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-center">
                  <div className="text-base font-semibold text-slate-900">
                    {nearestStats.total}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    Active Bays
                  </div>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-center">
                  <div className="text-base font-semibold text-slate-900">
                    {nearestStats.total - nearestStats.available}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    Occupied
                  </div>
                </div>

                <div className="rounded-xl border border-slate-200 bg-white px-3 py-3 text-center">
                  <div className="text-base font-semibold text-slate-900">
                    {nearestFacility.is_active === false ? "Closed" : "Open"}
                  </div>
                  <div className="mt-0.5 text-[11px] text-slate-500">
                    Facility status
                  </div>
                </div>
              </div>

              <div className="mt-5 flex flex-col gap-3 border-t border-slate-200 pt-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex flex-wrap gap-2">
                  <Link
                    to={createReservationUrl}
                    className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-3.5 py-2.5 text-xs font-semibold text-white transition hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-600/30"
                  >
                    <CalendarPlus size={15} />
                    Make a Reservation
                  </Link>

                  {navigationUrl ? (
                    <a
                      href={navigationUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs font-medium text-slate-700 transition hover:border-emerald-300 hover:text-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-600/20"
                    >
                      <Navigation size={15} />
                      Navigate to Facility
                    </a>
                  ) : (
                    <span className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs font-medium text-slate-400">
                      <Navigation size={15} />
                      Navigation unavailable
                    </span>
                  )}
                </div>

                <Link
                  to="/parking"
                  className="inline-flex w-fit items-center gap-1.5 text-xs font-medium text-emerald-700 transition hover:text-emerald-800"
                >
                  Find more facilities
                  <ArrowRight size={15} />
                </Link>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-5 py-8 text-center">
              <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-slate-100 text-slate-400">
                <ParkingCircle size={22} />
              </span>

              <p className="mx-auto mt-3 max-w-sm text-sm leading-5 text-slate-500">
                No parking facilities are currently available from the backend.
              </p>
            </div>
          )}
        </Card>

        <Card title="AI Prediction" sub="Production forecasting service">
          <div className="rounded-2xl border border-emerald-100 bg-emerald-50/70 p-4 sm:p-5">
            <div className="flex items-start justify-between gap-4">
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-100 text-emerald-700">
                <BrainCircuit size={21} />
              </span>

              <span
                className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${
                  forecastStatus === "Online"
                    ? "bg-emerald-500"
                    : "bg-amber-500"
                }`}
                aria-label={`Forecast service ${forecastStatus}`}
              />
            </div>

            <div className="mt-4">
              <p className="text-sm font-medium text-emerald-950">
                Forecast Service:{" "}
                <span className="font-semibold">{forecastStatus}</span>
              </p>

              <p className="mt-1.5 text-xs leading-5 text-emerald-800">
                {forecastModel
                  ? `Production model: ${forecastModel}.`
                  : "Production model diagnostics are available."}
              </p>
            </div>

            <div className="mt-4 rounded-xl border border-emerald-100/80 bg-white/45 px-3.5 py-3">
              <p className="text-[11px] leading-4 text-emerald-800">
                The current production forecast API exposes the validated
                30-minute inference flow.
              </p>
            </div>

            <Link
              to="/forecast"
              className="mt-4 inline-flex w-full items-center justify-center rounded-xl bg-emerald-600 px-3 py-2.5 text-xs font-semibold text-white transition hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-600/25"
            >
              Open prediction engine
              <ArrowRight size={15} className="ml-2" />
            </Link>
          </div>
        </Card>
      </div>
    </div>
  );
}

function formatReservationTime(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "Scheduled";

  return date.toLocaleString([], {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ==========================================================
// Parking
// ==========================================================
