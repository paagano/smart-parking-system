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
      <section className="rounded-3xl bg-[#071a2d] p-7 sm:p-9 text-white">
        <div className="max-w-3xl">
          <h1 className="mt-3 text-3xl sm:text-4xl font-black">
            Welcome to SmartPark.
          </h1>

          <br />

          <div className="text-emerald-300 text-xs font-bold uppercase tracking-[.2em]">
            AN AI-powered parking intelligence
          </div>

          <p className="mt-3 text-slate-300 leading-7">
            Find nearby parking, reserve spaces and use AI-powered occupancy
            predictions before you arrive.
          </p>
        </div>

        <div className="driver-dashboard-hero-actions">
          <div className="driver-dashboard-hero-links">
            <Link
              to="/parking"
              className="rounded-xl bg-emerald-400 text-[#071a2d] px-5 py-3 font-extrabold text-sm"
            >
              Find Parking
            </Link>

            <Link
              to="/forecast"
              className="rounded-xl bg-white/5 border border-white/10 px-5 py-3 font-bold text-sm"
            >
              View AI Prediction
            </Link>
          </div>

          <button
            type="button"
            onClick={refresh}
            disabled={isRefreshing}
            aria-label="Refresh dashboard data"
            className="driver-dashboard-hero-refresh inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/5 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw
              size={16}
              className={isRefreshing ? "animate-spin" : ""}
            />

            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </section>

      {error && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800 flex items-center justify-between gap-4">
          <span>{error}</span>

          <button
            type="button"
            onClick={refresh}
            disabled={isRefreshing}
            className="shrink-0 rounded-lg bg-white px-3 py-2 font-bold ring-1 ring-amber-200 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
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

      <div className="grid gap-6 xl:grid-cols-2">
        <Card
          title="Nearby Parking Facility"
          sub="Live availability from SmartPark AI"
        >
          {nearestFacility ? (
            <div className="rounded-2xl bg-slate-50 p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <ParkingCircle className="text-emerald-600" size={22} />

                    <b className="text-lg">{nearestFacility.name}</b>
                  </div>

                  {/* ==================================================
                      FACILITY TYPE
                      ================================================== */}

                  {nearestFacility.facility_type && (
                    <p className="mt-1 text-xs font-medium uppercase tracking-wide text-slate-500">
                      {nearestFacility.facility_type}
                    </p>
                  )}

                  <p className="mt-1 text-sm text-slate-500">
                    {nearestFacility.address}, {nearestFacility.city}
                  </p>

                  {/* ==================================================
                      DISTANCE
                      ================================================== */}

                  {nearestFacilityDistanceKm !== null && (
                    <p className="mt-1 text-xs font-bold text-emerald-600">
                      {nearestFacilityDistanceKm.toFixed(1)} KM away
                    </p>
                  )}
                </div>

                <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-700">
                  {nearestStats.available} available
                </span>
              </div>

              <div className="mt-5 grid grid-cols-3 gap-3 text-center">
                <div className="rounded-xl bg-white p-3 ring-1 ring-slate-200">
                  <b className="text-lg">{nearestStats.total}</b>

                  <small className="block text-slate-500">Active bays</small>
                </div>

                <div className="rounded-xl bg-white p-3 ring-1 ring-slate-200">
                  <b className="text-lg">
                    {nearestStats.total - nearestStats.available}
                  </b>

                  <small className="block text-slate-500">Occupied</small>
                </div>

                <div className="rounded-xl bg-white p-3 ring-1 ring-slate-200">
                  <b className="text-lg">
                    {nearestFacility.is_active === false ? "Closed" : "Open"}
                  </b>

                  <small className="block text-slate-500">
                    Facility status
                  </small>
                </div>
              </div>

              <div className="driver-dashboard-facility-actions">
                <div className="driver-dashboard-facility-primary-actions">
                  <Link
                    to={createReservationUrl}
                    className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-emerald-700"
                  >
                    <CalendarPlus size={16} />
                    Make a Reservation
                  </Link>

                  {navigationUrl ? (
                    <a
                      href={navigationUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:border-emerald-300 hover:text-emerald-700"
                    >
                      <Navigation size={16} />
                      Navigate to Facility
                    </a>
                  ) : (
                    <span className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-400">
                      <Navigation size={16} />
                      Navigation unavailable
                    </span>
                  )}
                </div>

                <Link
                  to="/parking"
                  className="driver-dashboard-find-more inline-flex items-center gap-2 text-sm font-bold text-emerald-700"
                >
                  Find More Facilities
                  <ArrowRight size={16} />
                </Link>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl bg-slate-50 p-8 text-center">
              <ParkingCircle className="mx-auto text-slate-400" size={28} />

              <p className="mt-3 text-sm text-slate-500">
                No parking facilities are currently available from the backend.
              </p>
            </div>
          )}
        </Card>

        <Card title="AI Prediction" sub="Production forecasting service">
          <div className="rounded-2xl bg-emerald-50 p-6">
            <BrainCircuit className="text-emerald-600" size={28} />

            <div className="mt-4 flex items-center justify-between gap-4">
              <div>
                <b className="text-emerald-900">
                  Forecast service: {forecastStatus}
                </b>

                <p className="mt-1 text-sm text-emerald-800">
                  {forecastModel
                    ? `Production model: ${forecastModel}.`
                    : "Production model diagnostics are available."}
                </p>
              </div>

              <span className="h-3 w-3 rounded-full bg-emerald-500" />
            </div>

            <p className="mt-4 text-xs leading-5 text-emerald-800">
              The current production forecast API exposes the validated
              30-minute inference flow.
            </p>

            <Link
              to="/forecast"
              className="mt-4 flex justify-center rounded-xl bg-emerald-600 text-white py-3 text-sm font-bold"
            >
              Open prediction engine
              <ArrowRight size={16} className="ml-2" />
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
