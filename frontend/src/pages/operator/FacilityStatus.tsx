import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CarFront,
  CheckCircle2,
  Clock3,
  MapPin,
  ParkingCircle,
  RefreshCw,
  ShieldCheck,
  TimerReset,
  Zap,
} from "lucide-react";

import { useAuth } from "../../auth/AuthContext";
import {
  parkingBaysApi,
  parkingFacilitiesApi,
  parkingSessionsApi,
  parkingZonesApi,
  type ParkingBay,
  type ParkingFacility,
  type ParkingSession,
  type ParkingZone,
} from "../../api";
import Page, { Card, Metric } from "../../components/common/Page";

function formatTime(value: string | null | undefined): string {
  if (!value) return "—";

  const parts = String(value).split(":");
  if (parts.length < 2) return value;

  const hours = Number(parts[0]);
  const minutes = Number(parts[1]);

  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) {
    return value;
  }

  const date = new Date();
  date.setHours(hours, minutes, 0, 0);

  return new Intl.DateTimeFormat("en-KE", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-KE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatPercentage(value: number): string {
  return `${Math.round(Math.max(0, Math.min(100, value)))}%`;
}

function isActiveSession(session: ParkingSession): boolean {
  return String(session.status ?? "").trim().toUpperCase() === "ACTIVE";
}

function StatusBadge({
  active,
  checking = false,
}: {
  active: boolean;
  checking?: boolean;
}) {
  const label = checking ? "Checking status…" : active ? "Operational" : "Inactive";

  return (
    <span
      className={[
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-bold",
        checking
          ? "border-slate-200 bg-slate-50 text-slate-600"
          : active
            ? "border-emerald-200 bg-emerald-50 text-emerald-700"
            : "border-rose-200 bg-rose-50 text-rose-700",
      ].join(" ")}
    >
      <span
        className={[
          "h-2 w-2 rounded-full",
          checking
            ? "bg-slate-400 animate-pulse"
            : active
              ? "bg-emerald-500"
              : "bg-rose-500",
        ].join(" ")}
      />
      {label}
    </span>
  );
}

function StatusRow({
  label,
  value,
  good = true,
  detail,
}: {
  label: string;
  value: string;
  good?: boolean;
  detail?: string;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-slate-100 py-3 last:border-0">
      <div className="min-w-0">
        <p className="text-sm font-semibold text-slate-800">{label}</p>
        {detail && <p className="mt-0.5 text-xs text-slate-500">{detail}</p>}
      </div>

      <span
        className={[
          "shrink-0 inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold",
          good
            ? "bg-emerald-50 text-emerald-700"
            : "bg-amber-50 text-amber-700",
        ].join(" ")}
      >
        {good ? <CheckCircle2 size={13} /> : <AlertTriangle size={13} />}
        {value}
      </span>
    </div>
  );
}

function LoadingBlock() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-4 w-2/5 rounded bg-slate-200" />
      <div className="h-3 w-4/5 rounded bg-slate-100" />
      <div className="h-3 w-3/5 rounded bg-slate-100" />
    </div>
  );
}

export default function FacilityStatus() {
  const { user } = useAuth();
  const facilityId = user?.facility_id ?? null;

  const [facility, setFacility] = useState<ParkingFacility | null>(null);
  const [zones, setZones] = useState<ParkingZone[]>([]);
  const [bays, setBays] = useState<ParkingBay[]>([]);
  const [sessions, setSessions] = useState<ParkingSession[]>([]);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const loadStatus = useCallback(
    async (silent = false) => {
      if (!facilityId) {
        setLoading(false);
        setRefreshing(false);
        setFacility(null);
        setZones([]);
        setBays([]);
        setSessions([]);
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
        const [facilityData, zoneData, bayData, sessionData] =
          await Promise.all([
            parkingFacilitiesApi.get(facilityId),
            parkingZonesApi.byFacility(facilityId),
            parkingBaysApi.list(),
            parkingSessionsApi.active(),
          ]);

        const activeZoneIds = new Set(
          zoneData.items
            .filter((zone) => zone.is_active)
            .map((zone) => zone.id),
        );

        setFacility(facilityData);
        setZones(zoneData.items.filter((zone) => zone.is_active));
        setBays(
          bayData.items.filter(
            (bay) => bay.is_active && activeZoneIds.has(bay.zone_id),
          ),
        );
        setSessions(
          sessionData.items.filter((session) => isActiveSession(session)),
        );
        setLastUpdated(new Date());
      } catch (loadError) {
        console.error("[FacilityStatus] Failed to load facility status:", loadError);
        setError(
          "Unable to load live facility status. Please try again.",
        );
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [facilityId],
  );

  useEffect(() => {
    void loadStatus();

    const interval = window.setInterval(() => {
      void loadStatus(true);
    }, 30_000);

    return () => window.clearInterval(interval);
  }, [loadStatus]);

  const stats = useMemo(() => {
    const occupiedBayIds = new Set(
      sessions
        .map((session) => session.parking_bay_id)
        .filter((id): id is number => Number.isFinite(id)),
    );

    const total = bays.length;
    const occupied = [...occupiedBayIds].filter((bayId) =>
      bays.some((bay) => bay.id === bayId),
    ).length;
    const available = Math.max(0, total - occupied);

    const occupancyRate = total > 0 ? (occupied / total) * 100 : 0;

    const ev = bays.filter((bay) => bay.is_ev_charging).length;
    const accessible = bays.filter((bay) => bay.is_accessible).length;
    const vip = bays.filter((bay) => bay.is_vip).length;
    const reservable = bays.filter((bay) => bay.is_reservable).length;

    return {
      total,
      occupied,
      available,
      occupancyRate,
      ev,
      accessible,
      vip,
      reservable,
    };
  }, [bays, sessions]);

  const zoneStats = useMemo(() => {
    const occupiedBayIds = new Set(
      sessions
        .map((session) => session.parking_bay_id)
        .filter((id): id is number => Number.isFinite(id)),
    );

    return zones.map((zone) => {
      const zoneBays = bays.filter((bay) => bay.zone_id === zone.id);
      const occupied = zoneBays.filter((bay) =>
        occupiedBayIds.has(bay.id),
      ).length;
      const total = zoneBays.length;
      const available = Math.max(0, total - occupied);
      const rate = total > 0 ? (occupied / total) * 100 : 0;

      return {
        ...zone,
        total,
        occupied,
        available,
        rate,
      };
    });
  }, [bays, sessions, zones]);

  const operationalState = facility?.is_active === true;

  return (
    <div className="space-y-6">
      <Page
        title="Facility Status"
        text={
          facility
            ? `${facility.name} · Live operational health and capacity status`
            : "Live operational status for your assigned parking facility."
        }
      />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge
            active={operationalState}
            checking={loading}
          />

          {lastUpdated && (
            <span className="text-xs font-medium text-slate-500">
              Updated {formatDateTime(lastUpdated.toISOString())}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => void loadStatus(true)}
          disabled={loading || refreshing}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw
            size={15}
            className={refreshing ? "animate-spin" : ""}
          />
          Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <AlertTriangle className="mt-0.5 shrink-0" size={18} />
          <div>
            <p className="font-bold">Facility status unavailable</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      {!error && !facility && !loading && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">
          No facility information is available for this operator account.
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Facility status"
          value={loading ? "—" : operationalState ? "Active" : "Inactive"}
          note="Configured facility state"
          Icon={ShieldCheck}
        />

        <Metric
          label="Total capacity"
          value={loading ? "—" : String(stats.total)}
          note="Active parking bays"
          Icon={ParkingCircle}
        />

        <Metric
          label="Occupied"
          value={loading ? "—" : String(stats.occupied)}
          note={`${formatPercentage(stats.occupancyRate)} occupancy`}
          Icon={CarFront}
        />

        <Metric
          label="Available"
          value={loading ? "—" : String(stats.available)}
          note="Currently available bays"
          Icon={Activity}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <Card
          title="Facility information"
          sub="Configuration and operating information"
        >
          {loading ? (
            <LoadingBlock />
          ) : facility ? (
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-white p-2.5 shadow-sm">
                    <ParkingCircle size={20} className="text-slate-700" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
                      Facility
                    </p>
                    <p className="mt-1 text-base font-black text-slate-900">
                      {facility.name}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Code: {facility.code || "—"}
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-white p-2.5 shadow-sm">
                    <MapPin size={20} className="text-slate-700" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
                      Location
                    </p>
                    <p className="mt-1 text-sm font-bold text-slate-900">
                      {facility.address || "Address not configured"}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {[facility.city, facility.county, facility.country]
                        .filter(Boolean)
                        .join(", ") || "Location not configured"}
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-white p-2.5 shadow-sm">
                    <Clock3 size={20} className="text-slate-700" />
                  </div>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
                      Operating hours
                    </p>
                    <p className="mt-1 text-sm font-black text-slate-900">
                      {formatTime(facility.opening_time)} —{" "}
                      {formatTime(facility.closing_time)}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Timezone: {facility.timezone || "—"}
                    </p>
                  </div>
                </div>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start gap-3">
                  <div className="rounded-xl bg-white p-2.5 shadow-sm">
                    <Zap size={20} className="text-slate-700" />
                  </div>
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
                      Facility type
                    </p>
                    <p className="mt-1 text-sm font-black text-slate-900">
                      {facility.facility_type || "—"}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      {facility.description || "No description configured."}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-500">
              Facility information is not available.
            </p>
          )}
        </Card>

        <Card title="Operational health" sub="Current data-driven checks">
          {loading ? (
            <LoadingBlock />
          ) : (
            <div>
              <StatusRow
                label="Facility configuration"
                value={facility ? "Available" : "Unavailable"}
                good={Boolean(facility)}
                detail="Facility record returned by the backend"
              />

              <StatusRow
                label="Parking zones"
                value={`${zones.length} active`}
                good={zones.length > 0}
                detail="Active zones belonging to the assigned facility"
              />

              <StatusRow
                label="Parking inventory"
                value={`${stats.total} active`}
                good={stats.total > 0}
                detail="Active bays across active zones"
              />

              <StatusRow
                label="Live sessions"
                value={`${sessions.length} active`}
                good
                detail="Current active sessions returned by the backend"
              />

              <StatusRow
                label="Occupancy"
                value={formatPercentage(stats.occupancyRate)}
                good={stats.occupancyRate < 90}
                detail={
                  stats.occupancyRate >= 90
                    ? "Capacity is critically high"
                    : stats.occupancyRate >= 80
                      ? "Capacity is approaching a high-utilization level"
                      : "Within normal operational capacity"
                }
              />
            </div>
          )}
        </Card>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="EV bays"
          value={loading ? "—" : String(stats.ev)}
          note="Configured EV charging bays"
          Icon={Zap}
        />
        <Metric
          label="Accessible bays"
          value={loading ? "—" : String(stats.accessible)}
          note="Accessibility-designated bays"
          Icon={ShieldCheck}
        />
        <Metric
          label="VIP bays"
          value={loading ? "—" : String(stats.vip)}
          note="VIP-designated bays"
          Icon={CarFront}
        />
        <Metric
          label="Reservable bays"
          value={loading ? "—" : String(stats.reservable)}
          note="Configured for reservations"
          Icon={TimerReset}
        />
      </div>

      <Card
        title="Zone status"
        sub="Live capacity distribution across active parking zones"
      >
        {loading ? (
          <LoadingBlock />
        ) : zoneStats.length === 0 ? (
          <div className="rounded-2xl bg-slate-50 p-8 text-center">
            <ParkingCircle className="mx-auto text-slate-400" size={32} />
            <p className="mt-3 text-sm font-semibold text-slate-700">
              No active parking zones are configured.
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Zone capacity will appear here once the facility has active
              parking zones and bays.
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {zoneStats.map((zone) => {
              const rate = Math.max(0, Math.min(100, zone.rate));
              const highUtilization = rate >= 80;

              return (
                <div key={zone.id}>
                  <div className="mb-2 flex items-center justify-between gap-4">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-extrabold text-slate-900">
                        {zone.name}
                      </p>
                      <p className="mt-0.5 text-xs text-slate-500">
                        {zone.code} · {zone.total} bays
                      </p>
                    </div>

                    <div className="shrink-0 text-right">
                      <p className="text-sm font-black text-slate-900">
                        {formatPercentage(rate)}
                      </p>
                      <p className="text-xs text-slate-500">
                        {zone.occupied} occupied · {zone.available} available
                      </p>
                    </div>
                  </div>

                  <div className="h-2.5 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${rate}%`,
                        background:
                          highUtilization
                            ? "linear-gradient(90deg, #f59e0b, #ef4444)"
                            : "linear-gradient(90deg, #10b981, #14b8a6)",
                      }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <Card
        title="Live operational snapshot"
        sub="Current facility state from active parking data"
      >
        {loading ? (
          <LoadingBlock />
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
                  Capacity utilization
                </p>
                <Activity size={18} className="text-slate-400" />
              </div>
              <p className="mt-2 text-3xl font-black text-slate-900">
                {formatPercentage(stats.occupancyRate)}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                {stats.occupied} of {stats.total} active bays occupied
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
                  Active parking
                </p>
                <CarFront size={18} className="text-slate-400" />
              </div>
              <p className="mt-2 text-3xl font-black text-slate-900">
                {sessions.length}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Active parking sessions currently returned
              </p>
            </div>

            <div className="rounded-2xl border border-slate-200 bg-white p-5">
              <div className="flex items-center justify-between">
                <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
                  Available capacity
                </p>
                <ParkingCircle size={18} className="text-slate-400" />
              </div>
              <p className="mt-2 text-3xl font-black text-slate-900">
                {stats.available}
              </p>
              <p className="mt-1 text-xs text-slate-500">
                Active bays not currently occupied
              </p>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
