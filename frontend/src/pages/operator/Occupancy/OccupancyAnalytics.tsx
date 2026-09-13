import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import {
  Activity,
  AlertCircle,
  ArrowDownToLine,
  ArrowUpFromLine,
  BarChart3,
  CalendarClock,
  CarFront,
  CheckCircle2,
  Clock3,
  Gauge,
  MapPinned,
  RefreshCw,
  Ticket,
  TrendingUp,
} from "lucide-react";

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
import { Card, Metric, default as Page } from "../../../components/common/Page";

function number(value: unknown): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function money(value: unknown): string {
  return new Intl.NumberFormat("en-KE", {
    style: "currency",
    currency: "KES",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(number(value));
}

function minutesBetween(start: string | null | undefined, end: string | null | undefined): number {
  if (!start) return 0;
  const a = new Date(start).getTime();
  const b = end ? new Date(end).getTime() : Date.now();
  if (!Number.isFinite(a) || !Number.isFinite(b)) return 0;
  return Math.max(0, Math.floor((b - a) / 60000));
}

function durationLabel(minutes: number): string {
  const safe = Math.max(0, Math.round(minutes));
  const days = Math.floor(safe / 1440);
  const hours = Math.floor((safe % 1440) / 60);
  const mins = safe % 60;

  if (days) return `${days}d ${hours}h ${mins}m`;
  if (hours) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

function dayKey(value: string | null | undefined): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 10);
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

export default function OccupancyAnalytics() {
  const { user } = useAuth();
  const facilityId = user?.facility_id ?? null;

  const [facility, setFacility] = useState<ParkingFacility | null>(null);
  const [zones, setZones] = useState<ParkingZone[]>([]);
  const [bays, setBays] = useState<ParkingBay[]>([]);
  const [activeSessions, setActiveSessions] = useState<ParkingSession[]>([]);
  const [completedSessions, setCompletedSessions] = useState<ParkingSession[]>([]);
  const [reservations, setReservations] = useState<ParkingReservation[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const load = useCallback(
    async (silent = false) => {
      if (!facilityId) {
        setLoading(false);
        setError("Your operator account is not assigned to a parking facility.");
        return;
      }

      silent ? setRefreshing(true) : setLoading(true);
      setError(null);

      try {
        const [
          facilityResult,
          zoneResult,
          bayResult,
          activeResult,
          completedResult,
          reservationResult,
        ] = await Promise.all([
          parkingFacilitiesApi.get(facilityId),
          parkingZonesApi.byFacility(facilityId, 0, 500),
          parkingBaysApi.list(0, 500),
          parkingSessionsApi.active(),
          parkingSessionsApi.completed(),
          api.get<{ items: ParkingReservation[]; total: number }>(
            "/parking-reservations",
            { params: { skip: 0, limit: 500 } },
          ),
        ]);

        const facilityZones = zoneResult.items.filter(
          (zone) => zone.facility_id === facilityId && zone.is_active,
        );
        const zoneIds = new Set(facilityZones.map((zone) => zone.id));

        setFacility(facilityResult);
        setZones(facilityZones);
        setBays(bayResult.items.filter((bay) => zoneIds.has(bay.zone_id)));
        setActiveSessions(activeResult.items);
        setCompletedSessions(completedResult.items);
        setReservations(reservationResult.data.items);
        setLastUpdated(new Date());
      } catch (loadError) {
        console.error("[OccupancyAnalytics] Failed to load analytics:", loadError);
        setError(getApiErrorMessage(loadError));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [facilityId],
  );

  useEffect(() => {
    void load();
    const interval = window.setInterval(() => void load(true), 30_000);
    return () => window.clearInterval(interval);
  }, [load]);

  const today = new Date();
  const todayKey = today.toISOString().slice(0, 10);

  const todayCompleted = useMemo(
    () =>
      completedSessions.filter(
        (session) =>
          dayKey(session.entry_time) === todayKey ||
          dayKey(session.exit_time) === todayKey,
      ),
    [completedSessions, todayKey],
  );

  const todayArrivals = useMemo(
    () => completedSessions.filter((session) => dayKey(session.entry_time) === todayKey).length +
      activeSessions.filter((session) => dayKey(session.entry_time) === todayKey).length,
    [activeSessions, completedSessions, todayKey],
  );

  const todayDepartures = useMemo(
    () => completedSessions.filter((session) => dayKey(session.exit_time) === todayKey).length,
    [completedSessions, todayKey],
  );

  const averageCompletedDuration = useMemo(() => {
    if (!todayCompleted.length) return 0;

    const total = todayCompleted.reduce(
      (sum, session) =>
        sum +
        minutesBetween(
          session.entry_time,
          session.exit_time ?? session.updated_at,
        ),
      0,
    );

    return Math.round(total / todayCompleted.length);
  }, [todayCompleted]);

  const currentDuration = useMemo(() => {
    if (!activeSessions.length) return 0;

    const total = activeSessions.reduce(
      (sum, session) => sum + minutesBetween(session.entry_time, null),
      0,
    );

    return Math.round(total / activeSessions.length);
  }, [activeSessions]);

  const activeEstimatedAmount = useMemo(
    () =>
      activeSessions.reduce(
        (sum, session) => sum + number(session.calculated_amount),
        0,
      ),
    [activeSessions],
  );

  const todayCollectedAmount = useMemo(
    () =>
      todayCompleted.reduce(
        (sum, session) => sum + number(session.paid_amount),
        0,
      ),
    [todayCompleted],
  );

  const confirmedReservations = useMemo(
    () =>
      reservations.filter(
        (reservation) =>
          reservation.is_active &&
          String(reservation.status).toUpperCase() === "CONFIRMED" &&
          !reservation.checked_in_at,
      ),
    [reservations],
  );

  const unconfirmedReservations = useMemo(
    () =>
      reservations.filter(
        (reservation) =>
          reservation.is_active &&
          String(reservation.status).toUpperCase() === "CREATED",
      ),
    [reservations],
  );

  const operationalBays = bays.filter((bay) => bay.is_active);
  const occupiedCount = activeSessions.length;
  const occupancyRate =
    operationalBays.length > 0
      ? Math.round((occupiedCount / operationalBays.length) * 100)
      : 0;

  const zoneAnalytics = useMemo(() => {
    return zones
      .map((zone) => {
        const zoneBays = bays.filter(
          (bay) => bay.zone_id === zone.id && bay.is_active,
        );
        const ids = new Set(zoneBays.map((bay) => bay.id));
        const occupied = activeSessions.filter((session) =>
          ids.has(session.parking_bay_id),
        ).length;
        const reserved = confirmedReservations.filter((reservation) =>
          ids.has(reservation.parking_bay_id),
        ).length;
        const available = Math.max(zoneBays.length - occupied - reserved, 0);

        return {
          zone,
          total: zoneBays.length,
          occupied,
          reserved,
          available,
          utilization:
            zoneBays.length > 0
              ? Math.round((occupied / zoneBays.length) * 100)
              : 0,
        };
      })
      .sort((a, b) => b.utilization - a.utilization);
  }, [activeSessions, bays, confirmedReservations, zones]);

  const accessMix = useMemo(() => {
    const counts = new Map<string, number>();

    activeSessions.forEach((session) => {
      const method = String(session.entry_method || "MANUAL").toUpperCase();
      counts.set(method, (counts.get(method) ?? 0) + 1);
    });

    return Array.from(counts.entries())
      .map(([method, count]) => ({
        method,
        count,
        percentage:
          activeSessions.length > 0
            ? Math.round((count / activeSessions.length) * 100)
            : 0,
      }))
      .sort((a, b) => b.count - a.count);
  }, [activeSessions]);

  const billingMix = useMemo(() => {
    const counts = new Map<string, number>();

    activeSessions.forEach((session) => {
      const billing = String(session.billing_type || "UNKNOWN").replace(/_/g, " ");
      counts.set(billing, (counts.get(billing) ?? 0) + 1);
    });

    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [activeSessions]);

  const durationBands = useMemo(() => {
    const bands = [
      { label: "< 30 min", min: 0, max: 30 },
      { label: "30–60 min", min: 30, max: 60 },
      { label: "1–2 hrs", min: 60, max: 120 },
      { label: "2–4 hrs", min: 120, max: 240 },
      { label: "4+ hrs", min: 240, max: Infinity },
    ];

    return bands.map((band) => ({
      ...band,
      count: activeSessions.filter((session) => {
        const duration = minutesBetween(session.entry_time, null);
        return duration >= band.min && duration < band.max;
      }).length,
    }));
  }, [activeSessions]);

  const insight = useMemo(() => {
    if (occupancyRate >= 90) {
      return {
        title: "Capacity pressure is critical",
        text: `The facility is ${occupancyRate}% occupied. Only ${
          operationalBays.length - occupiedCount
        } active bays remain outside the current occupied count.`,
        className: "border-rose-200 bg-rose-50 text-rose-700",
      };
    }

    if (occupancyRate >= 80) {
      return {
        title: "Capacity pressure is high",
        text: `Occupancy is ${occupancyRate}%. Monitor arrivals, confirmed reservations and the busiest zones closely.`,
        className: "border-amber-200 bg-amber-50 text-amber-700",
      };
    }

    return {
      title: "Current capacity is healthy",
      text: `${Math.max(operationalBays.length - occupiedCount, 0)} active bays are outside the current occupied count.`,
      className: "border-emerald-200 bg-emerald-50 text-emerald-700",
    };
  }, [occupiedCount, occupancyRate, operationalBays.length]);

  return (
    <div className="space-y-6">
      <Page
        title="Occupancy Analytics"
        text={
          facility
            ? `${facility.name} · Operational occupancy analysis and decision support`
            : "Analyse occupancy performance, parking duration and facility utilization."
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-black text-slate-700">
            <BarChart3 size={14} className="text-emerald-600" />
            Analytical view
          </span>
          {lastUpdated && (
            <span className="ml-2 text-xs font-medium text-slate-400">
              Updated {lastUpdated.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => void load(true)}
          disabled={loading || refreshing}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-black text-slate-700 hover:bg-slate-50 disabled:opacity-60"
        >
          <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
          {refreshing ? "Refreshing..." : "Refresh analytics"}
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-black">Unable to load occupancy analytics</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Current Occupancy" value={loading ? "—" : `${occupancyRate}%`} note={`${occupiedCount} vehicles currently parked`} Icon={Gauge} />
        <Metric label="Today's Arrivals" value={loading ? "—" : todayArrivals} note="Sessions started today" Icon={ArrowUpFromLine} />
        <Metric label="Today's Departures" value={loading ? "—" : todayDepartures} note="Sessions exited today" Icon={ArrowDownToLine} />
        <Metric label="Avg. Completed Stay" value={loading ? "—" : durationLabel(averageCompletedDuration)} note="Today's completed sessions" Icon={Clock3} />
        <Metric label="Confirmed Reservations" value={loading ? "—" : confirmedReservations.length} note={`${unconfirmedReservations.length} unconfirmed`} Icon={Ticket} />
      </div>

      <div className={`rounded-2xl border p-4 ${insight.className}`}>
        <div className="flex items-start gap-3">
          <TrendingUp size={20} className="mt-0.5 shrink-0" />
          <div>
            <p className="text-sm font-black">{insight.title}</p>
            <p className="mt-1 text-xs leading-5 opacity-80">{insight.text}</p>
          </div>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.05fr_0.95fr]">
        <Card title="Zone utilization" sub="Which zones are carrying the greatest current parking load.">
          <div className="space-y-4">
            {zoneAnalytics.length === 0 ? (
              <Empty message="No active zones are available for analysis." />
            ) : (
              zoneAnalytics.map((row) => (
                <div key={row.zone.id} className="rounded-2xl border border-slate-200 bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-black text-slate-900">{row.zone.name}</p>
                      <p className="mt-1 text-[10px] font-medium text-slate-400">
                        {row.occupied} occupied · {row.reserved} reserved · {row.available} available · {row.total} active bays
                      </p>
                    </div>
                    <p className="text-xl font-black text-slate-900">{row.utilization}%</p>
                  </div>
                  <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: `${Math.min(row.utilization, 100)}%` }} />
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        <Card title="Current parking duration profile" sub="Distribution of vehicles currently inside the facility.">
          <div className="space-y-4">
            {durationBands.map((band) => {
              const percentage =
                activeSessions.length > 0
                  ? Math.round((band.count / activeSessions.length) * 100)
                  : 0;

              return (
                <div key={band.label}>
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs font-bold text-slate-700">{band.label}</p>
                    <p className="text-xs font-black text-slate-800">{band.count} · {percentage}%</p>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: `${percentage}%` }} />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-5 grid grid-cols-2 gap-3">
            <SmallMetric label="Avg. current stay" value={durationLabel(currentDuration)} />
            <SmallMetric label="Live estimated amount" value={money(activeEstimatedAmount)} />
          </div>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Access-channel mix" sub="Entry channels represented by vehicles currently parked.">
          {accessMix.length === 0 ? (
            <Empty message="No active vehicles to analyse." />
          ) : (
            <div className="space-y-4">
              {accessMix.map((item) => (
                <div key={item.method}>
                  <div className="flex justify-between gap-3">
                    <p className="text-xs font-black text-slate-700">{item.method.replace(/_/g, " ")}</p>
                    <p className="text-xs font-black text-slate-800">{item.count} · {item.percentage}%</p>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div className="h-full rounded-full bg-emerald-500" style={{ width: `${item.percentage}%` }} />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Billing profile" sub="Billing types represented in the current active sessions.">
          {billingMix.length === 0 ? (
            <Empty message="No active billing data is available." />
          ) : (
            <div className="space-y-3">
              {billingMix.map(([billing, count]) => (
                <div key={billing} className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                  <span className="text-xs font-black capitalize text-slate-700">{billing}</span>
                  <span className="rounded-full bg-white px-2.5 py-1 text-xs font-black text-slate-800">{count}</span>
                </div>
              ))}
            </div>
          )}

          <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-4">
            <div className="flex items-start gap-3">
              <Activity size={19} className="mt-0.5 text-emerald-600" />
              <div>
                <p className="text-sm font-black text-slate-900">Today's completed-session value</p>
                <p className="mt-1 text-2xl font-black text-slate-900">{money(todayCollectedAmount)}</p>
                <p className="mt-1 text-xs text-slate-500">Based on recorded paid amounts for completed sessions included in today's data.</p>
              </div>
            </div>
          </div>
        </Card>
      </div>

      <Card title="Today's operational summary" sub="A concise view of today's parking movement and reservation pressure.">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Summary icon={CarFront} label="Vehicles processed" value={todayArrivals + todayDepartures} note="Arrivals + departures" />
          <Summary icon={CalendarClock} label="Arrivals" value={todayArrivals} note="Sessions started today" />
          <Summary icon={ArrowOutIcon} label="Departures" value={todayDepartures} note="Sessions completed today" />
          <Summary icon={Ticket} label="Reservation pressure" value={confirmedReservations.length} note="Confirmed not checked in" />
        </div>
      </Card>

      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
        <div className="flex items-start gap-3">
          <CheckCircle2 size={19} className="mt-0.5 shrink-0 text-emerald-600" />
          <div>
            <p className="text-sm font-black text-slate-900">Analytics integrity</p>
            <p className="mt-1 text-xs leading-5 text-slate-600">
              This page deliberately reports only metrics supported by the existing SmartPark operational APIs. It does not fabricate historical occupancy trends. When a dedicated historical occupancy-observation endpoint is exposed to the Operator portal, this page can safely add hourly, daily, weekly and monthly trend charts.
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <Link to="/operator/occupancy" className="rounded-2xl border border-slate-200 bg-white p-4 hover:border-emerald-200 hover:shadow-sm">
          <Activity size={19} className="text-emerald-600" />
          <p className="mt-3 text-sm font-black text-slate-900">Live Occupancy</p>
          <p className="mt-1 text-xs text-slate-500">Return to the real-time operational view.</p>
        </Link>
        <Link to="/operator/occupancy/map" className="rounded-2xl border border-slate-200 bg-white p-4 hover:border-emerald-200 hover:shadow-sm">
          <MapPinned size={19} className="text-emerald-600" />
          <p className="mt-3 text-sm font-black text-slate-900">Live Slot Map</p>
          <p className="mt-1 text-xs text-slate-500">Inspect individual bay states by zone.</p>
        </Link>
      </div>
    </div>
  );
}

function SmallMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <p className="text-[10px] font-black uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-black text-slate-900">{value}</p>
    </div>
  );
}

function Summary({
  icon: Icon,
  label,
  value,
  note,
}: {
  icon: typeof Activity;
  label: string;
  value: number;
  note: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10px] font-black uppercase tracking-wide text-slate-400">{label}</p>
          <p className="mt-1 text-2xl font-black text-slate-900">{value}</p>
          <p className="mt-1 text-xs text-slate-500">{note}</p>
        </div>
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-emerald-50 text-emerald-600">
          <Icon size={17} />
        </div>
      </div>
    </div>
  );
}

function Empty({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
      <BarChart3 size={28} className="mx-auto text-slate-400" />
      <p className="mt-3 text-sm font-bold text-slate-700">{message}</p>
    </div>
  );
}

