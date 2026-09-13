import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import {
  Activity,
  AlertCircle,
  ArrowDownToLine,
  ArrowUpFromLine,
  CarFront,
  CheckCircle2,
  Clock3,
  Gauge,
  MapPinned,
  RefreshCw,
  Search,
  ShieldAlert,
  Ticket,
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

type BayState = "AVAILABLE" | "OCCUPIED" | "RESERVED" | "OUT_OF_SERVICE";

function n(value: unknown): number {
  const valueAsNumber = Number(value ?? 0);
  return Number.isFinite(valueAsNumber) ? valueAsNumber : 0;
}

function text(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

function dateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-KE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function timeOnly(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function durationFrom(value: string | null | undefined, now: number): string {
  if (!value) return "—";
  const started = new Date(value).getTime();
  if (!Number.isFinite(started)) return "—";

  const minutes = Math.max(0, Math.floor((now - started) / 60000));
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const mins = minutes % 60;

  if (days) return `${days}d ${hours}h ${mins}m`;
  if (hours) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

function statusLabel(state: BayState): string {
  return state === "OUT_OF_SERVICE"
    ? "Out of service"
    : state.charAt(0) + state.slice(1).toLowerCase();
}

function stateClass(state: BayState): string {
  switch (state) {
    case "OCCUPIED":
      return "bg-rose-50 text-rose-700 border-rose-200";
    case "RESERVED":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "OUT_OF_SERVICE":
      return "bg-slate-100 text-slate-600 border-slate-200";
    default:
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
  }
}

export default function LiveOccupancy() {
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
  const [search, setSearch] = useState("");
  const [now, setNow] = useState(Date.now());

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
        const [facilityResult, zoneResult, bayResult, sessionResult, reservationResult] =
          await Promise.all([
            parkingFacilitiesApi.get(facilityId),
            parkingZonesApi.byFacility(facilityId, 0, 500),
            parkingBaysApi.list(0, 500),
            parkingSessionsApi.active(),
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
        setSessions(sessionResult.items);
        setReservations(reservationResult.data.items);
        setLastUpdated(new Date());
      } catch (loadError) {
        console.error("[LiveOccupancy] Failed to load occupancy:", loadError);
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
    const interval = window.setInterval(() => void load(true), 10_000);
    return () => window.clearInterval(interval);
  }, [load]);

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 10_000);
    return () => window.clearInterval(interval);
  }, []);

  const sessionByBay = useMemo(
    () => new Map(sessions.map((session) => [session.parking_bay_id, session])),
    [sessions],
  );

  const reservationByBay = useMemo(() => {
    const map = new Map<number, ParkingReservation>();

    reservations.forEach((reservation) => {
      if (
        reservation.is_active &&
        String(reservation.status).toUpperCase() === "CONFIRMED" &&
        !reservation.checked_in_at &&
        !map.has(reservation.parking_bay_id)
      ) {
        map.set(reservation.parking_bay_id, reservation);
      }
    });

    return map;
  }, [reservations]);

  const bayRows = useMemo(() => {
    return bays.map((bay) => {
      const session = sessionByBay.get(bay.id) ?? null;
      const reservation = reservationByBay.get(bay.id) ?? null;

      const state: BayState = !bay.is_active
        ? "OUT_OF_SERVICE"
        : session
          ? "OCCUPIED"
          : reservation
            ? "RESERVED"
            : "AVAILABLE";

      return { bay, session, reservation, state };
    });
  }, [bays, reservationByBay, sessionByBay]);

  const stats = useMemo(() => {
    const total = bayRows.length;
    const occupied = bayRows.filter((row) => row.state === "OCCUPIED").length;
    const reserved = bayRows.filter((row) => row.state === "RESERVED").length;
    const outOfService = bayRows.filter((row) => row.state === "OUT_OF_SERVICE").length;
    const available = bayRows.filter((row) => row.state === "AVAILABLE").length;

    return {
      total,
      occupied,
      reserved,
      outOfService,
      available,
      occupancyRate:
        total > 0 ? Math.round((occupied / Math.max(total - outOfService, 1)) * 100) : 0,
    };
  }, [bayRows]);

  const zoneRows = useMemo(() => {
    return zones.map((zone) => {
      const rows = bayRows.filter((row) => row.bay.zone_id === zone.id);
      const operational = rows.filter((row) => row.state !== "OUT_OF_SERVICE");
      const occupied = rows.filter((row) => row.state === "OCCUPIED").length;
      const reserved = rows.filter((row) => row.state === "RESERVED").length;
      const available = rows.filter((row) => row.state === "AVAILABLE").length;

      return {
        zone,
        total: rows.length,
        occupied,
        reserved,
        available,
        occupancy:
          operational.length > 0
            ? Math.round((occupied / operational.length) * 100)
            : 0,
      };
    });
  }, [bayRows, zones]);

  const parkedRows = useMemo(() => {
    const query = text(search);

    return sessions
      .map((session) => {
        const bay = bays.find((item) => item.id === session.parking_bay_id);
        const zone = zones.find((item) => item.id === bay?.zone_id);

        return { session, bay, zone };
      })
      .filter(({ session, bay, zone }) => {
        if (!query) return true;

        return text(
          [
            session.vehicle_registration,
            session.session_number,
            bay?.code,
            bay?.bay_number,
            zone?.name,
            zone?.code,
          ].join(" "),
        ).includes(query);
      })
      .sort(
        (a, b) =>
          new Date(a.session.entry_time).getTime() -
          new Date(b.session.entry_time).getTime(),
      );
  }, [bays, search, sessions, zones]);

  const operationalPressure =
    stats.occupancyRate >= 90
      ? "Critical"
      : stats.occupancyRate >= 80
        ? "High"
        : stats.occupancyRate >= 60
          ? "Moderate"
          : "Healthy";

  return (
    <div className="space-y-6">
      <Page
        title="Live Occupancy"
        text={
          facility
            ? `${facility.name} · Real-time facility occupancy and vehicle status`
            : "Monitor the current state of facility capacity and parked vehicles."
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1.5 text-xs font-black text-emerald-700">
            <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
            LIVE
          </span>
          <span className="text-xs font-medium text-slate-500">
            Auto-refresh every 10 seconds
          </span>
          {lastUpdated && (
            <span className="text-xs font-medium text-slate-400">
              · Updated {timeOnly(lastUpdated.toISOString())}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => void load(true)}
          disabled={loading || refreshing}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-black text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-60"
        >
          <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-black">Unable to load live occupancy</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Total Bays" value={loading ? "—" : stats.total} note="Configured facility bays" Icon={MapPinned} />
        <Metric label="Occupied" value={loading ? "—" : stats.occupied} note={`${stats.occupancyRate}% occupancy`} Icon={CarFront} />
        <Metric label="Available" value={loading ? "—" : stats.available} note="Ready for admission" Icon={ArrowDownToLine} />
        <Metric label="Reserved" value={loading ? "—" : stats.reserved} note="Confirmed reservations" Icon={Ticket} />
        <Metric label="Out of Service" value={loading ? "—" : stats.outOfService} note="Not operational" Icon={ShieldAlert} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
        <Card title="Current facility position" sub="Immediate operating picture for the assigned facility.">
          <div className="flex flex-col gap-6 sm:flex-row sm:items-center">
            <div className="relative mx-auto h-44 w-44 shrink-0">
              <div
                className="h-full w-full rounded-full"
                style={{
                  background: `conic-gradient(#10b981 0 ${Math.min(stats.occupancyRate, 100)}%, #e2e8f0 ${Math.min(stats.occupancyRate, 100)}% 100%)`,
                }}
              />
              <div className="absolute inset-5 grid place-items-center rounded-full bg-white text-center shadow-inner">
                <div>
                  <p className="text-3xl font-black text-slate-900">{stats.occupancyRate}%</p>
                  <p className="text-[10px] font-black uppercase tracking-[0.14em] text-slate-400">Occupied</p>
                </div>
              </div>
            </div>

            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-3">
                <Gauge size={21} className="text-emerald-600" />
                <div>
                  <p className="text-sm font-black text-slate-900">{operationalPressure} operating pressure</p>
                  <p className="text-xs text-slate-500">
                    {stats.available} bays are currently available.
                  </p>
                </div>
              </div>

              <div className="mt-5 grid grid-cols-2 gap-3">
                <MiniStat label="Occupied" value={stats.occupied} />
                <MiniStat label="Available" value={stats.available} />
                <MiniStat label="Reserved" value={stats.reserved} />
                <MiniStat label="Out of service" value={stats.outOfService} />
              </div>
            </div>
          </div>
        </Card>

        <Card title="Zone occupancy" sub="Live utilization by parking zone.">
          <div className="space-y-4">
            {zoneRows.length === 0 ? (
              <Empty message="No active parking zones are configured." />
            ) : (
              zoneRows.map((row) => (
                <div key={row.zone.id}>
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate text-xs font-black text-slate-800">{row.zone.name}</p>
                      <p className="text-[10px] font-medium text-slate-400">
                        {row.occupied} occupied · {row.available} available · {row.reserved} reserved
                      </p>
                    </div>
                    <p className="text-sm font-black text-slate-900">{row.occupancy}%</p>
                  </div>
                  <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-emerald-500 transition-all duration-500"
                      style={{ width: `${Math.min(row.occupancy, 100)}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      <Card title="Vehicles currently parked" sub="Live vehicles occupying the facility right now.">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative min-w-0 flex-1">
            <Search size={17} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search vehicle, session, zone or bay..."
              className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-10 pr-4 text-sm font-medium text-slate-800 outline-none focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
            />
          </div>

          <Link
            to="/operator/occupancy/map"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#071a2d] px-4 py-3 text-xs font-black text-white hover:bg-[#0b2a4a]"
          >
            <MapPinned size={15} />
            Open Slot Map
          </Link>
        </div>

        <div className="mt-5 overflow-x-auto">
          <table className="min-w-[900px] w-full border-separate border-spacing-0">
            <thead>
              <tr className="text-left">
                {["Vehicle", "Parking Session", "Zone", "Bay", "Check-in", "Duration", "Access"].map((heading) => (
                  <th key={heading} className="border-b border-slate-200 px-4 py-3 text-[10px] font-black uppercase tracking-[0.12em] text-slate-400 first:pl-0">
                    {heading}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {parkedRows.map(({ session, bay, zone }) => (
                <tr key={session.id} className="group">
                  <td className="border-b border-slate-100 px-4 py-4 pl-0">
                    <div className="flex items-center gap-3">
                      <div className="grid h-9 w-9 place-items-center rounded-lg bg-slate-100 text-slate-600">
                        <CarFront size={16} />
                      </div>
                      <div>
                        <p className="text-sm font-black text-slate-900">{session.vehicle_registration}</p>
                        <p className="text-[10px] font-medium text-slate-400">{session.vehicle_type}</p>
                      </div>
                    </div>
                  </td>
                  <td className="border-b border-slate-100 px-4 py-4 text-xs font-bold text-slate-700">{session.session_number}</td>
                  <td className="border-b border-slate-100 px-4 py-4 text-xs font-bold text-slate-700">{zone?.name ?? "—"}</td>
                  <td className="border-b border-slate-100 px-4 py-4 text-xs font-black text-slate-900">{bay?.code ?? bay?.bay_number ?? "—"}</td>
                  <td className="border-b border-slate-100 px-4 py-4 text-xs font-medium text-slate-600">
                    {dateTime(session.entry_time)}
                  </td>
                  <td className="border-b border-slate-100 px-4 py-4">
                    <div className="flex items-center gap-2">
                      <Clock3 size={14} className="text-emerald-600" />
                      <span className="text-xs font-black text-slate-800">{durationFrom(session.entry_time, now)}</span>
                    </div>
                  </td>
                  <td className="border-b border-slate-100 px-4 py-4">
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-black uppercase text-slate-600">
                      {String(session.entry_method || "MANUAL").replace(/_/g, " ")}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {!loading && parkedRows.length === 0 && (
            <Empty message={search ? "No parked vehicles match your search." : "No vehicles are currently parked."} />
          )}
        </div>
      </Card>

      <div className="grid gap-3 sm:grid-cols-3">
        <Link to="/operator/access/manual" className="rounded-2xl border border-slate-200 bg-white p-4 hover:border-emerald-200 hover:shadow-sm">
          <ArrowUpFromLine size={19} className="text-emerald-600" />
          <p className="mt-3 text-sm font-black text-slate-900">Manual Check-In / Exit</p>
          <p className="mt-1 text-xs text-slate-500">Admit or release a vehicle manually.</p>
        </Link>
        <Link to="/operator/occupancy/map" className="rounded-2xl border border-slate-200 bg-white p-4 hover:border-emerald-200 hover:shadow-sm">
          <MapPinned size={19} className="text-emerald-600" />
          <p className="mt-3 text-sm font-black text-slate-900">Live Slot Map</p>
          <p className="mt-1 text-xs text-slate-500">Inspect individual bays and their states.</p>
        </Link>
        <Link to="/operator/occupancy/statistics" className="rounded-2xl border border-slate-200 bg-white p-4 hover:border-emerald-200 hover:shadow-sm">
          <Activity size={19} className="text-emerald-600" />
          <p className="mt-3 text-sm font-black text-slate-900">Occupancy Analytics</p>
          <p className="mt-1 text-xs text-slate-500">Review operational patterns and performance.</p>
        </Link>
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
      <p className="text-[10px] font-black uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-xl font-black text-slate-900">{value}</p>
    </div>
  );
}

function Empty({ message }: { message: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
      <CheckCircle2 size={27} className="mx-auto text-slate-400" />
      <p className="mt-3 text-sm font-bold text-slate-700">{message}</p>
    </div>
  );
}
