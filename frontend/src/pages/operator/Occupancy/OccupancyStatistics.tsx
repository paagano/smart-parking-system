import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import {
  Activity,
  AlertCircle,
  ArrowDownToLine,
  ArrowUpFromLine,
  BarChart3,
  BrainCircuit,
  CarFront,
  CheckCircle2,
  Clock3,
  Gauge,
  MapPinned,
  RefreshCw,
  ShieldAlert,
  Ticket,
  TrendingUp,
} from "lucide-react";

import Page, { Card, Metric } from "../../../components/common/Page";
import { useAuth } from "../../../auth/AuthContext";
import {
  api,
  getApiErrorMessage,
  parkingBaysApi,
  parkingFacilitiesApi,
  parkingSessionsApi,
  parkingZonesApi,
  type ParkingBay,
  type ParkingFacility,
  type ParkingReservation,
  type ParkingSession,
  type ParkingZone,
} from "../../../api";

// ==========================================================
// Helpers
// ==========================================================

function asNumber(value: number | string | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function normalize(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

function formatTime(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";

  return new Intl.DateTimeFormat("en-KE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function formatCurrency(value: number | string | null | undefined): string {
  const amount = asNumber(value);

  return new Intl.NumberFormat("en-KE", {
    style: "currency",
    currency: "KES",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

function formatDuration(minutes: number): string {
  const safeMinutes = Math.max(0, Math.floor(minutes));

  const days = Math.floor(safeMinutes / 1440);
  const hours = Math.floor((safeMinutes % 1440) / 60);
  const mins = safeMinutes % 60;

  if (days > 0) {
    return `${days}d ${hours}h ${mins}m`;
  }

  if (hours > 0) {
    return `${hours}h ${mins}m`;
  }

  return `${mins}m`;
}

function minutesSince(value: string | null | undefined, now: number): number {
  if (!value) return 0;

  const timestamp = new Date(value).getTime();

  if (!Number.isFinite(timestamp)) return 0;

  return Math.max(0, Math.floor((now - timestamp) / 60000));
}

function statusTone(occupancy: number): {
  label: string;
  className: string;
  description: string;
} {
  if (occupancy >= 90) {
    return {
      label: "Critical",
      className: "bg-rose-100 text-rose-700",
      description: "Facility is approaching full capacity.",
    };
  }

  if (occupancy >= 80) {
    return {
      label: "High",
      className: "bg-amber-100 text-amber-700",
      description: "Occupancy is elevated and available capacity is limited.",
    };
  }

  if (occupancy >= 60) {
    return {
      label: "Moderate",
      className: "bg-sky-100 text-sky-700",
      description: "Occupancy is within a moderate operating range.",
    };
  }

  return {
    label: "Healthy",
    className: "bg-emerald-100 text-emerald-700",
    description: "The facility has healthy available capacity.",
  };
}

// ==========================================================
// Component
// ==========================================================

export default function OccupancyStatistics() {
  const { user } = useAuth();
  const facilityId = user?.facility_id ?? null;

  const [facility, setFacility] = useState<ParkingFacility | null>(null);
  const [zones, setZones] = useState<ParkingZone[]>([]);
  const [bays, setBays] = useState<ParkingBay[]>([]);
  const [sessions, setSessions] = useState<ParkingSession[]>([]);
  const [reservations, setReservations] = useState<ParkingReservation[]>([]);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [liveNow, setLiveNow] = useState(() => Date.now());

  // ========================================================
  // Facility-scoped data
  // ========================================================

  const loadStatistics = useCallback(
    async (silent = false) => {
      if (!facilityId) {
        setLoading(false);
        setRefreshing(false);
        setError(
          "Your operator account is not assigned to a parking facility.",
        );
        return;
      }

      if (silent) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setError(null);

      try {
        const [
          facilityData,
          zoneData,
          bayData,
          sessionData,
          reservationData,
        ] = await Promise.all([
          parkingFacilitiesApi.get(facilityId),
          parkingZonesApi.byFacility(facilityId),
          parkingBaysApi.list(),
          parkingSessionsApi.active(),
          api.get<{ items: ParkingReservation[]; total: number }>(
            "/parking-reservations",
            {
              params: {
                skip: 0,
                limit: 500,
              },
            },
          ),
        ]);

        const facilityZones = zoneData.items.filter(
          (zone) => zone.facility_id === facilityId && zone.is_active,
        );

        const zoneIds = new Set(facilityZones.map((zone) => zone.id));

        setFacility(facilityData);
        setZones(facilityZones);
        setBays(
          bayData.items.filter((bay) => zoneIds.has(bay.zone_id)),
        );
        setSessions(sessionData.items);
        setReservations(reservationData.data.items);
        setLastUpdated(new Date());
      } catch (loadError) {
        console.error(
          "[OccupancyStatistics] Failed to load occupancy statistics:",
          loadError,
        );
        setError(getApiErrorMessage(loadError));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [facilityId],
  );

  useEffect(() => {
    void loadStatistics();

    const interval = window.setInterval(() => {
      void loadStatistics(true);
    }, 30_000);

    return () => window.clearInterval(interval);
  }, [loadStatistics]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setLiveNow(Date.now());
    }, 10_000);

    return () => window.clearInterval(interval);
  }, []);

  // ========================================================
  // Current capacity model
  // ========================================================

  const stats = useMemo(() => {
    const activeBays = bays.filter((bay) => bay.is_active);

    const occupiedBayIds = new Set(
      sessions
        .map((session) => session.parking_bay_id)
        .filter((id): id is number => Number.isFinite(id)),
    );

    const confirmedReservations = reservations.filter((reservation) => {
      const status = String(reservation.status).toUpperCase();

      return (
        reservation.is_active &&
        status === "CONFIRMED" &&
        !reservation.checked_in_at &&
        !occupiedBayIds.has(reservation.parking_bay_id)
      );
    });

    const unconfirmedReservations = reservations.filter((reservation) => {
      const status = String(reservation.status).toUpperCase();

      return (
        reservation.is_active &&
        status === "CREATED" &&
        !reservation.checked_in_at
      );
    });

    const occupied = sessions.length;
    const reserved = confirmedReservations.length;
    const total = activeBays.length;
    const outOfService = bays.filter((bay) => !bay.is_active).length;

    // A confirmed reservation holds a bay only if it is not already occupied.
    // This prevents double-counting an occupied bay in available capacity.
    const available = Math.max(total - occupied - reserved, 0);

    const occupancyRate =
      total > 0 ? Math.round((occupied / total) * 100) : 0;

    const utilizationRate =
      total > 0
        ? Math.round(((occupied + reserved) / total) * 100)
        : 0;

    const currentDurations = sessions.map((session) =>
      minutesSince(session.entry_time, liveNow),
    );

    const averageDuration =
      currentDurations.length > 0
        ? Math.round(
            currentDurations.reduce((sum, value) => sum + value, 0) /
              currentDurations.length,
          )
        : 0;

    const longestDuration =
      currentDurations.length > 0
        ? Math.max(...currentDurations)
        : 0;

    return {
      total,
      occupied,
      reserved,
      available,
      outOfService,
      occupancyRate,
      utilizationRate,
      confirmedReservations: confirmedReservations.length,
      unconfirmedReservations: unconfirmedReservations.length,
      averageDuration,
      longestDuration,
    };
  }, [bays, liveNow, reservations, sessions]);

  // ========================================================
  // Zone analytics
  // ========================================================

  const zoneStats = useMemo(() => {
    return zones
      .map((zone) => {
        const zoneBays = bays.filter(
          (bay) => bay.zone_id === zone.id && bay.is_active,
        );

        const zoneBayIds = new Set(zoneBays.map((bay) => bay.id));

        const occupied = sessions.filter((session) =>
          zoneBayIds.has(session.parking_bay_id),
        ).length;

        const reserved = reservations.filter((reservation) => {
          const status = String(reservation.status).toUpperCase();

          return (
            reservation.is_active &&
            status === "CONFIRMED" &&
            !reservation.checked_in_at &&
            zoneBayIds.has(reservation.parking_bay_id) &&
            !sessions.some(
              (session) =>
                session.parking_bay_id === reservation.parking_bay_id,
            )
          );
        }).length;

        const available = Math.max(
          zoneBays.length - occupied - reserved,
          0,
        );

        const occupancy =
          zoneBays.length > 0
            ? Math.round((occupied / zoneBays.length) * 100)
            : 0;

        return {
          ...zone,
          total: zoneBays.length,
          occupied,
          reserved,
          available,
          occupancy,
        };
      })
      .sort((a, b) => b.occupancy - a.occupancy);
  }, [bays, reservations, sessions, zones]);

  // ========================================================
  // Access channel analytics
  // ========================================================

  const accessBreakdown = useMemo(() => {
    const counts = new Map<string, number>();

    sessions.forEach((session) => {
      const method = String(
        session.entry_method || "MANUAL",
      ).toUpperCase();

      counts.set(method, (counts.get(method) ?? 0) + 1);
    });

    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([method, count]) => ({
        method,
        count,
        percentage:
          sessions.length > 0
            ? Math.round((count / sessions.length) * 100)
            : 0,
      }));
  }, [sessions]);

  // ========================================================
  // Operational insights
  // ========================================================

  const insights = useMemo(() => {
    const items: Array<{
      title: string;
      text: string;
      tone: "critical" | "warning" | "positive" | "info";
      Icon: typeof Activity;
    }> = [];

    if (stats.total === 0) {
      items.push({
        title: "No operational capacity configured",
        text:
          "No active parking bays are currently configured for this facility.",
        tone: "warning",
        Icon: ShieldAlert,
      });

      return items;
    }

    if (stats.occupancyRate >= 90) {
      items.push({
        title: "Facility is near capacity",
        text: `${stats.occupancyRate}% of active bays are occupied. Only ${stats.available} bay${
          stats.available === 1 ? "" : "s"
        } remain available.`,
        tone: "critical",
        Icon: ShieldAlert,
      });
    } else if (stats.occupancyRate >= 80) {
      items.push({
        title: "High occupancy pressure",
        text: `${stats.occupancyRate}% occupancy indicates elevated demand. Monitor arrivals and available capacity closely.`,
        tone: "warning",
        Icon: Gauge,
      });
    } else {
      items.push({
        title: "Capacity position is healthy",
        text: `${stats.available} of ${stats.total} active bays are currently available for new admissions.`,
        tone: "positive",
        Icon: CheckCircle2,
      });
    }

    if (stats.reserved > 0) {
      items.push({
        title: "Future capacity is already committed",
        text: `${stats.reserved} bay${
          stats.reserved === 1 ? "" : "s"
        } are held by confirmed reservations.`,
        tone: "info",
        Icon: Ticket,
      });
    }

    if (stats.averageDuration > 0) {
      items.push({
        title: "Current parking duration",
        text: `Vehicles currently on site have remained parked for an average of ${formatDuration(
          stats.averageDuration,
        )}. The longest active stay is ${formatDuration(
          stats.longestDuration,
        )}.`,
        tone: "info",
        Icon: Clock3,
      });
    }

    return items.slice(0, 4);
  }, [stats]);

  const occupancyTone = statusTone(stats.occupancyRate);

  return (
    <div className="space-y-6">
      <Page
        title="Occupancy Statistics"
        text={
          facility
            ? `${facility.name} · Live capacity, utilization and operational insights`
            : "Analyse current facility occupancy, capacity and bay availability."
        }
      />

      {/* ======================================================
          Status / refresh
      ====================================================== */}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
            Live occupancy
          </span>

          <span
            className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-black ${occupancyTone.className}`}
          >
            {occupancyTone.label} · {stats.occupancyRate}%
          </span>

          {lastUpdated && (
            <span className="text-xs font-medium text-slate-500">
              Updated {formatTime(lastUpdated.toISOString())}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => void loadStatistics(true)}
          disabled={loading || refreshing}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw
            size={15}
            className={refreshing ? "animate-spin" : ""}
          />
          {refreshing ? "Refreshing..." : "Refresh statistics"}
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-extrabold">
              Unable to load occupancy statistics
            </p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      {/* ======================================================
          Primary KPIs
      ====================================================== */}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Metric
          label="Total Capacity"
          value={loading ? "—" : stats.total}
          note="Active operational bays"
          Icon={MapPinned}
        />

        <Metric
          label="Occupied"
          value={loading ? "—" : stats.occupied}
          note={`${stats.occupancyRate}% of capacity`}
          Icon={CarFront}
        />

        <Metric
          label="Available"
          value={loading ? "—" : stats.available}
          note="Ready for admission"
          Icon={ArrowDownToLine}
        />

        <Metric
          label="Reserved"
          value={loading ? "—" : stats.reserved}
          note="Confirmed reservations"
          Icon={Ticket}
        />

        <Metric
          label="Out of Service"
          value={loading ? "—" : stats.outOfService}
          note="Inactive configured bays"
          Icon={ShieldAlert}
        />
      </div>

      {/* ======================================================
          Capacity overview
      ====================================================== */}

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Card
          title="Current capacity position"
          sub="A live view of how the facility's usable capacity is being consumed."
        >
          <div className="grid gap-6 lg:grid-cols-[220px_1fr] lg:items-center">
            <div className="relative mx-auto h-48 w-48">
              <div
                className="h-full w-full rounded-full"
                style={{
                  background: `conic-gradient(
                    #10b981 0 ${Math.min(stats.occupancyRate, 100)}%,
                    #f59e0b ${Math.min(stats.occupancyRate, 100)}% ${Math.min(
                      stats.occupancyRate + (stats.total > 0 ? (stats.reserved / stats.total) * 100 : 0),
                      100,
                    )}%,
                    #e2e8f0 ${Math.min(
                      stats.occupancyRate +
                        (stats.total > 0
                          ? (stats.reserved / stats.total) * 100
                          : 0),
                      100,
                    )}% 100%
                  )`,
                }}
              />

              <div className="absolute inset-5 grid place-items-center rounded-full bg-white text-center shadow-inner">
                <div>
                  <p className="text-4xl font-black text-slate-900">
                    {stats.occupancyRate}%
                  </p>
                  <p className="mt-1 text-[10px] font-black uppercase tracking-[0.16em] text-slate-400">
                    Occupied
                  </p>
                </div>
              </div>
            </div>

            <div className="space-y-4">
              <CapacityRow
                label="Occupied"
                value={stats.occupied}
                total={stats.total}
                className="bg-emerald-500"
              />
              <CapacityRow
                label="Reserved"
                value={stats.reserved}
                total={stats.total}
                className="bg-amber-400"
              />
              <CapacityRow
                label="Available"
                value={stats.available}
                total={stats.total}
                className="bg-slate-300"
              />

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start gap-3">
                  <Gauge
                    size={19}
                    className="mt-0.5 shrink-0 text-emerald-600"
                  />
                  <div>
                    <p className="text-sm font-extrabold text-slate-900">
                      {occupancyTone.label} operating pressure
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-600">
                      {occupancyTone.description}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </Card>

        <Card
          title="Utilization indicators"
          sub="Operational indicators calculated from the current facility state."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <InsightMetric
              icon={TrendingUp}
              label="Usable capacity"
              value={`${stats.total - stats.outOfService}`}
              note="Active bays"
            />

            <InsightMetric
              icon={Activity}
              label="Committed capacity"
              value={`${stats.utilizationRate}%`}
              note="Occupied + reserved"
            />

            <InsightMetric
              icon={Clock3}
              label="Average current stay"
              value={formatDuration(stats.averageDuration)}
              note="Active vehicles"
            />

            <InsightMetric
              icon={ArrowUpFromLine}
              label="Longest current stay"
              value={formatDuration(stats.longestDuration)}
              note="Active vehicle"
            />
          </div>

          <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.14em] text-slate-400">
                  Capacity remaining
                </p>
                <p className="mt-1 text-2xl font-black text-slate-900">
                  {stats.available} bays
                </p>
              </div>

              <div className="grid h-12 w-12 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                <CheckCircle2 size={21} />
              </div>
            </div>

            <div className="mt-4 h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                style={{
                  width: `${
                    stats.total > 0
                      ? Math.min((stats.available / stats.total) * 100, 100)
                      : 0
                  }%`,
                }}
              />
            </div>
          </div>
        </Card>
      </div>

      {/* ======================================================
          Zone analysis
      ====================================================== */}

      <Card
        title="Occupancy by zone"
        sub="Compare current utilization and available capacity across the facility."
      >
        {loading ? (
          <div className="space-y-3">
            {[1, 2, 3].map((item) => (
              <div
                key={item}
                className="h-20 animate-pulse rounded-2xl bg-slate-100"
              />
            ))}
          </div>
        ) : zoneStats.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center">
            <MapPinned size={30} className="mx-auto text-slate-400" />
            <p className="mt-3 text-sm font-bold text-slate-700">
              No active zones found
            </p>
            <p className="mt-1 text-sm text-slate-500">
              Configure parking zones for this facility to see zone-level
              occupancy.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {zoneStats.map((zone) => {
              const zoneTone = statusTone(zone.occupancy);

              return (
                <div
                  key={zone.id}
                  className="rounded-2xl border border-slate-200 bg-white p-4"
                >
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-sm font-black text-slate-900">
                          {zone.name}
                        </h3>
                        <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                          {zone.code}
                        </span>
                        <span
                          className={`rounded-full px-2 py-1 text-[10px] font-black ${zoneTone.className}`}
                        >
                          {zoneTone.label}
                        </span>
                      </div>

                      <p className="mt-1 text-xs font-medium text-slate-500">
                        {zone.occupied} occupied · {zone.reserved} reserved ·{" "}
                        {zone.available} available · {zone.total} active bays
                      </p>
                    </div>

                    <div className="text-left sm:text-right">
                      <p className="text-2xl font-black text-slate-900">
                        {zone.occupancy}%
                      </p>
                      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                        Occupied
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                      style={{
                        width: `${Math.min(zone.occupancy, 100)}%`,
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* ======================================================
          Access channel + live operating profile
      ====================================================== */}

      <div className="grid gap-6 xl:grid-cols-2">
        <Card
          title="Active access channels"
          sub="How vehicles currently parked at the facility entered."
        >
          {accessBreakdown.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
              <CarFront
                size={28}
                className="mx-auto text-slate-400"
              />
              <p className="mt-3 text-sm font-bold text-slate-700">
                No active vehicles
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Access-channel statistics will appear when vehicles are
                checked in.
              </p>
            </div>
          ) : (
            <div className="space-y-4">
              {accessBreakdown.map((item) => (
                <div key={item.method}>
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-black text-slate-800">
                      {item.method.replace(/_/g, " ")}
                    </p>
                    <p className="text-xs font-black text-slate-700">
                      {item.count} · {item.percentage}%
                    </p>
                  </div>

                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-emerald-500"
                      style={{
                        width: `${item.percentage}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card
          title="Operational intelligence"
          sub="Signals that help the operator understand current parking pressure."
        >
          <div className="space-y-3">
            {insights.map((item) => {
              const tone =
                item.tone === "critical"
                  ? "border-rose-200 bg-rose-50 text-rose-700"
                  : item.tone === "warning"
                    ? "border-amber-200 bg-amber-50 text-amber-700"
                    : item.tone === "positive"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                      : "border-slate-200 bg-slate-50 text-slate-700";

              return (
                <div
                  key={item.title}
                  className={`rounded-2xl border p-4 ${tone}`}
                >
                  <div className="flex items-start gap-3">
                    <item.Icon
                      size={19}
                      className="mt-0.5 shrink-0"
                    />
                    <div>
                      <p className="text-sm font-extrabold">
                        {item.title}
                      </p>
                      <p className="mt-1 text-xs leading-5 opacity-80">
                        {item.text}
                      </p>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4">
            <div className="flex items-start gap-3">
              <BrainCircuit
                size={19}
                className="mt-0.5 shrink-0 text-emerald-600"
              />
              <div>
                <p className="text-sm font-extrabold text-slate-900">
                  Smart monitoring
                </p>
                <p className="mt-1 text-xs leading-5 text-slate-600">
                  Current occupancy is recalculated from active parking
                  sessions and facility bays. The page refreshes automatically
                  every 30 seconds while the displayed duration clock updates
                  every 10 seconds.
                </p>
              </div>
            </div>
          </div>
        </Card>
      </div>

      {/* ======================================================
          Quick operational links
      ====================================================== */}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Link
          to="/operator/occupancy/map"
          className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-md"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-black text-slate-900">
                Open Live Slot Map
              </p>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Inspect every parking bay by zone and operational state.
              </p>
            </div>
            <MapPinned
              size={20}
              className="text-emerald-600 transition group-hover:translate-x-0.5"
            />
          </div>
        </Link>

        <Link
          to="/operator/access/manual"
          className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-md"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-black text-slate-900">
                Manual Check-In / Exit
              </p>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Admit vehicles, process reservations and manage exits.
              </p>
            </div>
            <CarFront
              size={20}
              className="text-emerald-600 transition group-hover:translate-x-0.5"
            />
          </div>
        </Link>

        <Link
          to="/operator"
          className="group rounded-2xl border border-slate-200 bg-white p-5 transition hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-md"
        >
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-black text-slate-900">
                Return to Dashboard
              </p>
              <p className="mt-1 text-xs leading-5 text-slate-500">
                Review the overall operator dashboard and current alerts.
              </p>
            </div>
            <BarChart3
              size={20}
              className="text-emerald-600 transition group-hover:translate-x-0.5"
            />
          </div>
        </Link>
      </div>
    </div>
  );
}

// ==========================================================
// Small presentational components
// ==========================================================

function CapacityRow({
  label,
  value,
  total,
  className,
}: {
  label: string;
  value: number;
  total: number;
  className: string;
}) {
  const percentage =
    total > 0 ? Math.min((value / total) * 100, 100) : 0;

  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <p className="text-xs font-bold text-slate-600">{label}</p>
        <p className="text-xs font-black text-slate-800">
          {value} · {Math.round(percentage)}%
        </p>
      </div>

      <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all duration-500 ${className}`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}

function InsightMetric({
  icon: Icon,
  label,
  value,
  note,
}: {
  icon: typeof Activity;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">
            {label}
          </p>
          <p className="mt-1 text-xl font-black text-slate-900">
            {value}
          </p>
          <p className="mt-1 text-[11px] font-medium text-slate-500">
            {note}
          </p>
        </div>

        <div className="grid h-9 w-9 place-items-center rounded-lg bg-white text-emerald-600 shadow-sm">
          <Icon size={17} />
        </div>
      </div>
    </div>
  );
}
