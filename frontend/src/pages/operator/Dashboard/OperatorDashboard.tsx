import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import {
  AlertTriangle,
  ArrowDownToLine,
  ArrowUpFromLine,
  ArrowRight,
  ClipboardCheck,
  MapPinned,
  QrCode,
  ScanLine,
  BrainCircuit,
  CarFront,
  CheckCircle2,
  Clock3,
  Gauge,
  ParkingCircle,
  RefreshCw,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";

import Page, { Card, Metric } from "../../../components/common/Page";
import { useAuth } from "../../../auth/AuthContext";
import {
  api,
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

function asNumber(value: number | string | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
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

export default function OperatorDashboard() {
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

  const loadDashboard = useCallback(
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
        const [facilityData, zoneData, bayData, sessionData, reservationData] =
          await Promise.all([
            parkingFacilitiesApi.get(facilityId),
            parkingZonesApi.byFacility(facilityId),
            parkingBaysApi.list(),
            parkingSessionsApi.active(),
            // The backend now scopes this collection to the operator's facility.
            fetchOperatorReservations(),
          ]);

        const zoneIds = new Set(zoneData.items.map((zone) => zone.id));

        setFacility(facilityData);
        setZones(zoneData.items);
        setBays(bayData.items.filter((bay) => zoneIds.has(bay.zone_id)));
        setSessions(sessionData.items);
        setReservations(reservationData);
        setLastUpdated(new Date());
      } catch (loadError) {
        console.error(
          "[OperatorDashboard] Failed to load dashboard:",
          loadError,
        );
        setError("Unable to load live facility data. Please try again.");
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [facilityId],
  );

  useEffect(() => {
    void loadDashboard();

    const interval = window.setInterval(() => {
      void loadDashboard(true);
    }, 30_000);

    return () => window.clearInterval(interval);
  }, [loadDashboard]);

  const stats = useMemo(() => {
    const activeBays = bays.filter((bay) => bay.is_active);
    const occupiedBayIds = new Set(
      sessions
        .map((session) => session.parking_bay_id)
        .filter((id): id is number => Number.isFinite(id)),
    );

    // Reservation lifecycle in the backend uses CREATED for an
    // unconfirmed reservation and CONFIRMED for a confirmed/paid
    // reservation. Only confirmed reservations should reserve a bay
    // on the operational capacity view.
    const confirmedReservations = reservations.filter((reservation) => {
      const status = reservation.status.toUpperCase();
      return (
        reservation.is_active &&
        status === "CONFIRMED" &&
        !reservation.checked_in_at
      );
    });

    const unconfirmedReservations = reservations.filter((reservation) => {
      const status = reservation.status.toUpperCase();
      return reservation.is_active && status === "CREATED";
    });

    const reservedBayIds = new Set(
      confirmedReservations
        .map((reservation) => reservation.parking_bay_id)
        .filter((id): id is number => Number.isFinite(id)),
    );

    const total = activeBays.length;
    const occupied = [...occupiedBayIds].filter((id) =>
      activeBays.some((bay) => bay.id === id),
    ).length;
    const reserved = [...reservedBayIds].filter(
      (id) =>
        !occupiedBayIds.has(id) && activeBays.some((bay) => bay.id === id),
    ).length;
    const available = Math.max(total - occupied - reserved, 0);
    const occupancy = total > 0 ? Math.round((occupied / total) * 100) : 0;

    return {
      total,
      occupied,
      reserved,
      available,
      occupancy,
      activeSessions: sessions.length,
      confirmedReservations: confirmedReservations.length,
      unconfirmedReservations: unconfirmedReservations.length,
      reservations:
        confirmedReservations.length + unconfirmedReservations.length,
    };
  }, [bays, reservations, sessions]);

  const recentSessions = useMemo(
    () =>
      [...sessions]
        .sort(
          (a, b) =>
            new Date(b.entry_time).getTime() - new Date(a.entry_time).getTime(),
        )
        .slice(0, 6),
    [sessions],
  );

  const zoneSummary = useMemo(() => {
    return zones.map((zone) => {
      const zoneBays = bays.filter(
        (bay) => bay.zone_id === zone.id && bay.is_active,
      );
      const zoneBayIds = new Set(zoneBays.map((bay) => bay.id));
      const occupied = sessions.filter((session) =>
        zoneBayIds.has(session.parking_bay_id),
      ).length;

      return {
        ...zone,
        total: zoneBays.length,
        occupied,
        available: Math.max(zoneBays.length - occupied, 0),
        occupancy:
          zoneBays.length > 0
            ? Math.round((occupied / zoneBays.length) * 100)
            : 0,
      };
    });
  }, [bays, sessions, zones]);

  const alerts = useMemo(() => {
    const items: Array<{
      title: string;
      text: string;
      tone: "warning" | "critical" | "info";
      Icon: typeof AlertTriangle;
    }> = [];

    if (stats.occupancy >= 90) {
      items.push({
        title: "Facility near capacity",
        text: `${stats.occupancy}% occupancy. Available capacity is limited.`,
        tone: "critical",
        Icon: ShieldAlert,
      });
    } else if (stats.occupancy >= 80) {
      items.push({
        title: "High occupancy",
        text: `${stats.occupancy}% of active bays are currently occupied.`,
        tone: "warning",
        Icon: AlertTriangle,
      });
    }

    if (stats.unconfirmedReservations > 0) {
      items.push({
        title: "Unconfirmed reservations require attention",
        text: `${stats.unconfirmedReservations} unconfirmed / unpaid reservation${
          stats.unconfirmedReservations === 1 ? "" : "s"
        } require operator attention.`,
        tone: "info",
        Icon: Clock3,
      });
    }

    if (items.length === 0) {
      items.push({
        title: "Operations look normal",
        text: "No immediate occupancy or reservation exceptions detected.",
        tone: "info",
        Icon: CheckCircle2,
      });
    }

    return items.slice(0, 3);
  }, [stats]);

  const accessBreakdown = useMemo(() => {
    const counts = new Map<string, number>();

    sessions.forEach((session) => {
      const method = String(session.entry_method || "MANUAL").toUpperCase();
      counts.set(method, (counts.get(method) ?? 0) + 1);
    });

    return Array.from(counts.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5);
  }, [sessions]);

  const facilityStatus = facility?.is_active ? "Operational" : "Inactive";

  return (
    <div className="space-y-6">
      <Page
        title="Operator Dashboard"
        text={
          facility
            ? `${facility.name} · ${facility.city}`
            : "Live operational view for your assigned parking facility."
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            {facilityStatus}
          </span>
          {lastUpdated && (
            <span className="text-xs font-medium text-slate-500">
              Updated {formatTime(lastUpdated.toISOString())}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => void loadDashboard(true)}
          disabled={loading || refreshing}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <AlertTriangle className="mt-0.5 shrink-0" size={18} />
          <div>
            <p className="font-bold">Dashboard data unavailable</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Total capacity"
          value={loading ? "—" : String(stats.total)}
          note={`${zones.length} active zone${zones.length === 1 ? "" : "s"}`}
          Icon={ParkingCircle}
        />
        <Metric
          label="Occupied"
          value={loading ? "—" : String(stats.occupied)}
          note={`${stats.occupancy}% facility occupancy`}
          Icon={CarFront}
        />
        <Metric
          label="Available"
          value={loading ? "—" : String(stats.available)}
          note={`${stats.reserved} reserved`}
          Icon={Gauge}
        />
        <Metric
          label="Active sessions"
          value={loading ? "—" : String(stats.activeSessions)}
          note={`${stats.confirmedReservations} confirmed · ${stats.unconfirmedReservations} unconfirmed`}
          Icon={TrendingUp}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-2">
        <Card title="Reservations" sub="Current facility reservation status">
          <div className="grid gap-3 sm:grid-cols-2">
            <ReservationMetric
              label="Confirmed"
              value={loading ? "—" : stats.confirmedReservations}
              note="Confirmed / paid"
              className="border-emerald-100 bg-emerald-50/60"
              valueClassName="text-emerald-700"
            />
            <ReservationMetric
              label="Unconfirmed"
              value={loading ? "—" : stats.unconfirmedReservations}
              note="Unconfirmed / unpaid"
              className="border-amber-100 bg-amber-50/60"
              valueClassName="text-amber-700"
            />
          </div>
        </Card>

        <Card
          title="Reservation capacity"
          sub="Confirmed reservations currently holding active bays"
        >
          <div className="flex items-center justify-between gap-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div>
              <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
                Reserved bays
              </p>
              <p className="mt-1 text-3xl font-black text-slate-900">
                {loading ? "—" : stats.reserved}
              </p>
            </div>
            <Link
              to="/operator/reservations"
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50"
            >
              Review reservations
              <ArrowRight size={14} />
            </Link>
          </div>
        </Card>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <QuickAction
          to="/operator/reservations"
          label="Approve reservations"
          Icon={ClipboardCheck}
        />
        <QuickAction
          to="/operator/access"
          label="Check-in / check-out"
          Icon={ScanLine}
        />
        <QuickAction
          to="/operator/occupancy/map"
          label="View live slot map"
          Icon={MapPinned}
        />
        <QuickAction
          to="/operator/access/qr"
          label="Process QR access"
          Icon={QrCode}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.4fr_0.9fr]">
        <Card title="Live occupancy" sub="Current capacity by parking zone">
          {loading ? (
            <LoadingRows />
          ) : zoneSummary.length === 0 ? (
            <EmptyState text="No parking zones are configured for this facility." />
          ) : (
            <div className="space-y-4">
              {zoneSummary.map((zone) => (
                <div key={zone.id}>
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-extrabold text-slate-900">
                        {zone.name}
                      </p>
                      <p className="text-[11px] font-semibold text-slate-500">
                        {zone.code} · {zone.total} active bays
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-black text-slate-900">
                        {zone.occupied}/{zone.total}
                      </p>
                      <p className="text-[11px] font-bold text-slate-500">
                        {zone.occupancy}%
                      </p>
                    </div>
                  </div>
                  <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-emerald-400 transition-all duration-500"
                      style={{ width: `${Math.min(zone.occupancy, 100)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Operational alerts" sub="Items requiring attention">
          <div className="space-y-3">
            {alerts.map(({ title, text, tone, Icon }) => (
              <div
                key={title}
                className={[
                  "flex gap-3 rounded-2xl border p-3.5",
                  tone === "critical"
                    ? "border-rose-200 bg-rose-50"
                    : tone === "warning"
                      ? "border-amber-200 bg-amber-50"
                      : "border-slate-200 bg-slate-50",
                ].join(" ")}
              >
                <Icon
                  size={18}
                  className={
                    tone === "critical"
                      ? "text-rose-600"
                      : tone === "warning"
                        ? "text-amber-600"
                        : "text-slate-500"
                  }
                />
                <div className="min-w-0">
                  <p className="text-sm font-extrabold text-slate-900">
                    {title}
                  </p>
                  <p className="mt-1 text-xs leading-5 text-slate-600">
                    {text}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <Card
          title="Current access mix"
          sub="Entry channels represented in active parking sessions"
        >
          {loading ? (
            <LoadingRows />
          ) : accessBreakdown.length === 0 ? (
            <EmptyState text="No active sessions are available for access-channel analysis." />
          ) : (
            <div className="space-y-4">
              {accessBreakdown.map(([method, count]) => {
                const share =
                  stats.activeSessions > 0
                    ? Math.round((count / stats.activeSessions) * 100)
                    : 0;

                return (
                  <div key={method}>
                    <div className="mb-1.5 flex items-center justify-between gap-3">
                      <span className="text-xs font-bold text-slate-700">
                        {method.replaceAll("_", " ")}
                      </span>
                      <span className="text-xs font-black text-slate-900">
                        {count} · {share}%
                      </span>
                    </div>
                    <div className="h-2 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-emerald-400 transition-all duration-500"
                        style={{ width: `${share}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        <Card title="Capacity mix" sub="Current state of active bays">
          <div className="flex items-center gap-6">
            <div
              className="relative grid h-36 w-36 shrink-0 place-items-center rounded-full"
              style={{
                background: `conic-gradient(#10b981 0 ${stats.total ? (stats.occupied / stats.total) * 100 : 0}%, #f59e0b ${stats.total ? (stats.occupied / stats.total) * 100 : 0}% ${stats.total ? ((stats.occupied + stats.reserved) / stats.total) * 100 : 0}%, #e2e8f0 ${stats.total ? ((stats.occupied + stats.reserved) / stats.total) * 100 : 0}% 100%)`,
              }}
            >
              <div className="grid h-24 w-24 place-items-center rounded-full bg-white">
                <div className="text-center">
                  <p className="text-2xl font-black text-slate-900">
                    {stats.occupancy}%
                  </p>
                  <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                    occupied
                  </p>
                </div>
              </div>
            </div>
            <div className="min-w-0 flex-1 space-y-3">
              <LegendRow
                label="Occupied"
                value={stats.occupied}
                className="bg-emerald-400"
              />
              <LegendRow
                label="Reserved"
                value={stats.reserved}
                className="bg-amber-400"
              />
              <LegendRow
                label="Available"
                value={stats.available}
                className="bg-slate-300"
              />
            </div>
          </div>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card
          title="Vehicles currently parked"
          sub="Latest active parking sessions"
        >
          {loading ? (
            <LoadingRows />
          ) : recentSessions.length === 0 ? (
            <EmptyState text="No vehicles are currently recorded as parked." />
          ) : (
            <div className="divide-y divide-slate-100">
              {recentSessions.map((session) => (
                <div
                  key={session.id}
                  className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600">
                      <CarFront size={17} />
                    </span>
                    <div className="min-w-0">
                      <p className="truncate text-sm font-extrabold text-slate-900">
                        {session.vehicle_registration}
                      </p>
                      <p className="truncate text-[11px] font-semibold text-slate-500">
                        {session.session_number} · Bay {session.parking_bay_id}
                      </p>
                    </div>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="text-xs font-bold text-emerald-700">Parked</p>
                    <p className="mt-0.5 text-[11px] text-slate-500">
                      {formatTime(session.entry_time)}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card title="Operator snapshot" sub="Useful operational indicators">
          <div className="grid gap-3 sm:grid-cols-2">
            <Snapshot
              icon={ArrowUpFromLine}
              label="Vehicles parked"
              value={stats.activeSessions}
            />
            <Snapshot
              icon={ArrowDownToLine}
              label="Available bays"
              value={stats.available}
            />
            <Snapshot
              icon={Clock3}
              label="Unconfirmed reservations"
              value={stats.unconfirmedReservations}
            />
            <Snapshot
              icon={BrainCircuit}
              label="Smart monitoring"
              value="Active"
              text
            />
          </div>

          <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-start gap-3">
              <BrainCircuit className="mt-0.5 text-emerald-600" size={19} />
              <div>
                <p className="text-sm font-extrabold text-slate-900">
                  Smart operational insight
                </p>
                <p className="mt-1 text-xs leading-5 text-slate-600">
                  {stats.occupancy >= 80
                    ? "Occupancy is elevated. Prioritise upcoming departures and monitor reservation arrivals."
                    : "Capacity is currently healthy. Continue monitoring arrivals, reservations and bay availability."}
                </p>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

async function fetchOperatorReservations(): Promise<ParkingReservation[]> {
  const response = await api.get<{ items?: ParkingReservation[] }>(
    "/parking-reservations",
  );

  return response.data.items ?? [];
}

function QuickAction({
  to,
  label,
  Icon,
}: {
  to: string;
  label: string;
  Icon: typeof ClipboardCheck;
}) {
  return (
    <Link
      to={to}
      className="group flex items-center justify-between gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3.5 shadow-sm transition hover:-translate-y-0.5 hover:border-emerald-200 hover:shadow-md"
    >
      <span className="flex min-w-0 items-center gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
          <Icon size={17} />
        </span>
        <span className="truncate text-xs font-extrabold text-slate-800">
          {label}
        </span>
      </span>
      <ArrowRight
        size={15}
        className="shrink-0 text-slate-400 transition group-hover:translate-x-0.5 group-hover:text-emerald-600"
      />
    </Link>
  );
}

function LegendRow({
  label,
  value,
  className,
}: {
  label: string;
  value: number;
  className: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-xs">
      <span className="flex items-center gap-2 font-semibold text-slate-600">
        <span className={`h-2.5 w-2.5 rounded-full ${className}`} />
        {label}
      </span>
      <span className="font-black text-slate-900">{value}</span>
    </div>
  );
}

function ReservationMetric({
  label,
  value,
  note,
  className,
  valueClassName,
}: {
  label: string;
  value: number | string;
  note: string;
  className: string;
  valueClassName: string;
}) {
  return (
    <div className={`rounded-2xl border p-4 ${className}`}>
      <p className="text-[11px] font-bold uppercase tracking-[0.12em] text-slate-500">
        {label}
      </p>
      <p className={`mt-1 text-3xl font-black ${valueClassName}`}>{value}</p>
      <p className="mt-1 text-xs font-semibold text-slate-500">{note}</p>
    </div>
  );
}

function LoadingRows() {
  return (
    <div className="space-y-4">
      {[1, 2, 3].map((item) => (
        <div key={item} className="animate-pulse">
          <div className="h-3 w-1/3 rounded bg-slate-100" />
          <div className="mt-2 h-2.5 w-full rounded bg-slate-100" />
        </div>
      ))}
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-8 text-center">
      <ParkingCircle className="mx-auto text-slate-400" size={30} />
      <p className="mt-3 text-sm text-slate-500">{text}</p>
    </div>
  );
}

function Snapshot({
  icon: Icon,
  label,
  value,
  text = false,
}: {
  icon: typeof ArrowUpFromLine;
  label: string;
  value: number | string;
  text?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
        <Icon size={17} />
      </span>
      <p className="mt-4 text-[11px] font-bold uppercase tracking-[0.12em] text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-black text-slate-900">
        {text ? value : asNumber(value)}
      </p>
    </div>
  );
}
