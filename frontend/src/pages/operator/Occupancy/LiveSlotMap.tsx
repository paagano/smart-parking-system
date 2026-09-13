import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import {
  AlertCircle,
  CarFront,
  CheckCircle2,
  ChevronDown,
  Clock3,
  MapPinned,
  RefreshCw,
  Search,
  ShieldAlert,
  Ticket,
  X,
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

// ==========================================================
// Types
// ==========================================================

type BayStatus = "AVAILABLE" | "OCCUPIED" | "RESERVED" | "OUT_OF_SERVICE";

interface BayViewModel extends ParkingBay {
  status: BayStatus;
  session: ParkingSession | null;
  reservation: ParkingReservation | null;
}

// ==========================================================
// Helpers
// ==========================================================

function normalize(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

function formatStatus(value: BayStatus): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
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

function formatTime(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ==========================================================
// Component
// ==========================================================

export default function LiveSlotMap() {
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

  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<BayStatus | "ALL">("ALL");
  const [expandedZoneIds, setExpandedZoneIds] = useState<Set<number>>(
    () => new Set(),
  );
  const [selectedBay, setSelectedBay] = useState<BayViewModel | null>(null);

  // ========================================================
  // Load facility-scoped occupancy data
  // ========================================================

  const loadMap = useCallback(
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
          facilityResult,
          zoneResult,
          bayResult,
          sessionResult,
          reservationResult,
        ] = await Promise.all([
          parkingFacilitiesApi.get(facilityId),
          parkingZonesApi.byFacility(facilityId, 0, 500),
          parkingBaysApi.list(0, 500),
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

        const facilityZones = zoneResult.items.filter(
          (zone) => zone.facility_id === facilityId && zone.is_active,
        );

        const zoneIds = new Set(facilityZones.map((zone) => zone.id));

        setFacility(facilityResult);
        setZones(facilityZones);
        setBays(
          bayResult.items.filter(
            (bay) => zoneIds.has(bay.zone_id),
          ),
        );
        setSessions(sessionResult.items);
        setReservations(reservationResult.data.items);
        setLastUpdated(new Date());
      } catch (loadError) {
        console.error("[LiveSlotMap] Failed to load occupancy map:", loadError);
        setError(getApiErrorMessage(loadError));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [facilityId],
  );

  useEffect(() => {
    void loadMap();

    const interval = window.setInterval(() => {
      void loadMap(true);
    }, 10_000);

    return () => window.clearInterval(interval);
  }, [loadMap]);

  // ========================================================
  // Authoritative bay state
  // ========================================================

  const activeSessionByBayId = useMemo(() => {
    const map = new Map<number, ParkingSession>();

    for (const session of sessions) {
      if (!map.has(session.parking_bay_id)) {
        map.set(session.parking_bay_id, session);
      }
    }

    return map;
  }, [sessions]);

  const confirmedReservationByBayId = useMemo(() => {
    const map = new Map<number, ParkingReservation>();

    for (const reservation of reservations) {
      const status = String(reservation.status).toUpperCase();

      if (
        reservation.is_active &&
        status === "CONFIRMED" &&
        !reservation.checked_in_at
      ) {
        const existing = map.get(reservation.parking_bay_id);

        if (!existing) {
          map.set(reservation.parking_bay_id, reservation);
          continue;
        }

        // Prefer the reservation with the earliest arrival window.
        if (
          new Date(reservation.reserved_from).getTime() <
          new Date(existing.reserved_from).getTime()
        ) {
          map.set(reservation.parking_bay_id, reservation);
        }
      }
    }

    return map;
  }, [reservations]);

  const bayViewModels = useMemo<BayViewModel[]>(() => {
    return bays.map((bay) => {
      if (!bay.is_active) {
        return {
          ...bay,
          status: "OUT_OF_SERVICE",
          session: null,
          reservation: null,
        };
      }

      const session = activeSessionByBayId.get(bay.id) ?? null;

      if (session) {
        return {
          ...bay,
          status: "OCCUPIED",
          session,
          reservation: null,
        };
      }

      const reservation =
        confirmedReservationByBayId.get(bay.id) ?? null;

      if (reservation) {
        return {
          ...bay,
          status: "RESERVED",
          session: null,
          reservation,
        };
      }

      return {
        ...bay,
        status: "AVAILABLE",
        session: null,
        reservation: null,
      };
    });
  }, [activeSessionByBayId, bays, confirmedReservationByBayId]);

  // ========================================================
  // Search / filter
  // ========================================================

  const filteredBays = useMemo(() => {
    const query = normalize(searchTerm);

    return bayViewModels.filter((bay) => {
      const matchesStatus =
        statusFilter === "ALL" || bay.status === statusFilter;

      if (!matchesStatus) {
        return false;
      }

      if (!query) {
        return true;
      }

      const zone = zones.find((item) => item.id === bay.zone_id);

      const searchableText = [
        bay.code,
        bay.bay_number,
        bay.bay_type,
        bay.vehicle_type,
        zone?.name,
        zone?.code,
        bay.session?.vehicle_registration,
        bay.session?.session_number,
        bay.reservation?.vehicle_registration,
        bay.reservation?.reservation_number,
      ]
        .filter(Boolean)
        .join(" ");

      return normalize(searchableText).includes(query);
    });
  }, [bayViewModels, searchTerm, statusFilter, zones]);

  const baysByZone = useMemo(() => {
    const map = new Map<number, BayViewModel[]>();

    for (const bay of filteredBays) {
      const current = map.get(bay.zone_id) ?? [];
      current.push(bay);
      map.set(bay.zone_id, current);
    }

    return map;
  }, [filteredBays]);

  // ========================================================
  // Summary
  // ========================================================

  const summary = useMemo(() => {
    return bayViewModels.reduce(
      (result, bay) => {
        result.total += 1;
        result[bay.status] += 1;
        return result;
      },
      {
        total: 0,
        AVAILABLE: 0,
        OCCUPIED: 0,
        RESERVED: 0,
        OUT_OF_SERVICE: 0,
      } as Record<BayStatus | "total", number>,
    );
  }, [bayViewModels]);

  const occupancyRate =
    summary.total > 0
      ? Math.round((summary.OCCUPIED / summary.total) * 100)
      : 0;

  // ========================================================
  // Zone helpers
  // ========================================================

  const getZoneSummary = (zone: ParkingZone) => {
    const zoneBays = bayViewModels.filter(
      (bay) => bay.zone_id === zone.id,
    );

    const operationalBays = zoneBays.filter(
      (bay) => bay.status !== "OUT_OF_SERVICE",
    );

    const occupied = zoneBays.filter(
      (bay) => bay.status === "OCCUPIED",
    ).length;

    const reserved = zoneBays.filter(
      (bay) => bay.status === "RESERVED",
    ).length;

    const available = zoneBays.filter(
      (bay) => bay.status === "AVAILABLE",
    ).length;

    const outOfService = zoneBays.filter(
      (bay) => bay.status === "OUT_OF_SERVICE",
    ).length;

    const occupancy =
      operationalBays.length > 0
        ? Math.round((occupied / operationalBays.length) * 100)
        : 0;

    return {
      total: zoneBays.length,
      occupied,
      reserved,
      available,
      outOfService,
      occupancy,
    };
  };

  const toggleZone = (zoneId: number) => {
    setExpandedZoneIds((current) => {
      const next = new Set(current);

      if (next.has(zoneId)) {
        next.delete(zoneId);
      } else {
        next.add(zoneId);
      }

      return next;
    });
  };

  // ========================================================
  // Render
  // ========================================================

  return (
    <div className="space-y-6">
      <Page
        title="Live Slot Map"
        text={
          facility
            ? `${facility.name} · Real-time parking bay occupancy`
            : "Visualise parking bays by zone and operational state."
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-emerald-100 bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            Live occupancy
          </div>

          {lastUpdated && (
            <p className="mt-2 text-xs font-medium text-slate-500">
              Last updated {formatTime(lastUpdated.toISOString())}
              {" · "}
              Auto-refresh every 10 seconds
            </p>
          )}
        </div>

        <button
          type="button"
          onClick={() => void loadMap(true)}
          disabled={loading || refreshing}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw
            size={15}
            className={refreshing ? "animate-spin" : ""}
          />
          {refreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-extrabold">Unable to load live slot map</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Metric
          label="Total Bays"
          value={loading ? "—" : summary.total}
          note="Configured facility bays"
          Icon={MapPinned}
        />
        <Metric
          label="Available"
          value={loading ? "—" : summary.AVAILABLE}
          note="Ready for vehicle entry"
          Icon={CheckCircle2}
        />
        <Metric
          label="Occupied"
          value={loading ? "—" : summary.OCCUPIED}
          note={`${occupancyRate}% of operational capacity`}
          Icon={CarFront}
        />
        <Metric
          label="Reserved"
          value={loading ? "—" : summary.RESERVED}
          note="Confirmed reservations"
          Icon={Ticket}
        />
        <Metric
          label="Out of Service"
          value={loading ? "—" : summary.OUT_OF_SERVICE}
          note="Unavailable bays"
          Icon={ShieldAlert}
        />
      </div>

      <Card
        title="Slot map"
        sub="Select a zone to expand its individual parking bays."
      >
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="relative min-w-0 flex-1">
            <Search
              size={17}
              className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
            />
            <input
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search bay, zone, vehicle or session..."
              className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-10 pr-4 text-sm font-medium text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            {(
              [
                ["ALL", "All"],
                ["AVAILABLE", "Available"],
                ["OCCUPIED", "Occupied"],
                ["RESERVED", "Reserved"],
                ["OUT_OF_SERVICE", "Out of service"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() =>
                  setStatusFilter(value as BayStatus | "ALL")
                }
                className={`rounded-lg px-3 py-2 text-xs font-bold transition ${
                  statusFilter === value
                    ? "bg-[#071a2d] text-white"
                    : "border border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="mt-5 space-y-3">
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((item) => (
                <div
                  key={item}
                  className="h-16 animate-pulse rounded-xl bg-slate-100"
                />
              ))}
            </div>
          ) : zones.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center">
              <MapPinned
                size={30}
                className="mx-auto text-slate-400"
              />
              <p className="mt-3 text-sm font-bold text-slate-700">
                No active parking zones found
              </p>
              <p className="mt-1 text-sm text-slate-500">
                Configure zones and bays for this facility before using the
                live slot map.
              </p>
            </div>
          ) : filteredBays.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center">
              <Search
                size={30}
                className="mx-auto text-slate-400"
              />
              <p className="mt-3 text-sm font-bold text-slate-700">
                No bays match your search
              </p>
              <p className="mt-1 text-sm text-slate-500">
                Try another bay, zone, vehicle registration or session number.
              </p>
            </div>
          ) : (
            zones.map((zone) => {
              const zoneBays = baysByZone.get(zone.id) ?? [];

              if (zoneBays.length === 0) {
                return null;
              }

              const zoneStats = getZoneSummary(zone);
              const expanded = expandedZoneIds.has(zone.id);

              return (
                <div
                  key={zone.id}
                  className="overflow-hidden rounded-2xl border border-slate-200 bg-white"
                >
                  <button
                    type="button"
                    onClick={() => toggleZone(zone.id)}
                    aria-expanded={expanded}
                    className="flex w-full items-center justify-between gap-4 px-4 py-4 text-left transition hover:bg-slate-50 sm:px-5"
                  >
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate text-sm font-black text-slate-900">
                          {zone.name}
                        </h3>
                        <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                          {zone.code}
                        </span>
                      </div>

                      <p className="mt-1 text-xs font-medium text-slate-500">
                        {zoneStats.available} available ·{" "}
                        {zoneStats.occupied} occupied ·{" "}
                        {zoneStats.reserved} reserved
                        {zoneStats.outOfService > 0
                          ? ` · ${zoneStats.outOfService} out of service`
                          : ""}
                      </p>
                    </div>

                    <div className="flex shrink-0 items-center gap-3">
                      <div className="hidden text-right sm:block">
                        <p className="text-xs font-black text-slate-900">
                          {zoneStats.occupancy}%
                        </p>
                        <p className="text-[10px] font-medium text-slate-400">
                          occupied
                        </p>
                      </div>

                      <ChevronDown
                        size={18}
                        className={`text-slate-400 transition-transform ${
                          expanded ? "rotate-180" : ""
                        }`}
                      />
                    </div>
                  </button>

                  {expanded && (
                    <div className="border-t border-slate-100 bg-slate-50/70 p-3 sm:p-4">
                      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
                        {zoneBays.map((bay) => (
                          <button
                            key={bay.id}
                            type="button"
                            onClick={() => setSelectedBay(bay)}
                            className={`group min-h-[112px] rounded-xl border p-3 text-left transition hover:-translate-y-0.5 hover:shadow-md ${
                              bay.status === "AVAILABLE"
                                ? "border-emerald-200 bg-emerald-50 hover:border-emerald-300"
                                : bay.status === "OCCUPIED"
                                  ? "border-rose-200 bg-rose-50 hover:border-rose-300"
                                  : bay.status === "RESERVED"
                                    ? "border-amber-200 bg-amber-50 hover:border-amber-300"
                                    : "border-slate-200 bg-slate-100 hover:border-slate-300"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-2">
                              <span
                                className={`grid h-8 w-8 place-items-center rounded-lg ${
                                  bay.status === "AVAILABLE"
                                    ? "bg-white text-emerald-600"
                                    : bay.status === "OCCUPIED"
                                      ? "bg-white text-rose-600"
                                      : bay.status === "RESERVED"
                                        ? "bg-white text-amber-600"
                                        : "bg-white text-slate-500"
                                }`}
                              >
                                <CarFront size={16} />
                              </span>

                              <span
                                className={`rounded-full px-2 py-1 text-[9px] font-black uppercase tracking-wide ${
                                  bay.status === "AVAILABLE"
                                    ? "bg-emerald-100 text-emerald-700"
                                    : bay.status === "OCCUPIED"
                                      ? "bg-rose-100 text-rose-700"
                                      : bay.status === "RESERVED"
                                        ? "bg-amber-100 text-amber-700"
                                        : "bg-slate-200 text-slate-600"
                                }`}
                              >
                                {bay.status === "OUT_OF_SERVICE"
                                  ? "OOS"
                                  : formatStatus(bay.status)}
                              </span>
                            </div>

                            <p className="mt-3 text-sm font-black text-slate-900">
                              {bay.code || bay.bay_number}
                            </p>

                            {bay.status === "OCCUPIED" &&
                              bay.session && (
                                <p className="mt-1 truncate text-[10px] font-semibold text-slate-600">
                                  {bay.session.vehicle_registration}
                                </p>
                              )}

                            {bay.status === "RESERVED" &&
                              bay.reservation && (
                                <p className="mt-1 truncate text-[10px] font-semibold text-slate-600">
                                  {bay.reservation.vehicle_registration}
                                </p>
                              )}

                            {bay.status === "AVAILABLE" && (
                              <p className="mt-1 text-[10px] font-semibold text-emerald-700">
                                Ready
                              </p>
                            )}

                            {bay.status === "OUT_OF_SERVICE" && (
                              <p className="mt-1 text-[10px] font-semibold text-slate-500">
                                Unavailable
                              </p>
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </Card>

      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 text-xs font-semibold text-slate-600">
        <span className="font-black text-slate-800">Legend:</span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500" />
          Available
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-rose-500" />
          Occupied
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-amber-500" />
          Reserved
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full bg-slate-400" />
          Out of service
        </span>
      </div>

      {selectedBay && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-lg overflow-hidden rounded-3xl bg-white shadow-2xl">
            <div className="flex items-start justify-between gap-4 border-b border-slate-100 px-6 py-5">
              <div>
                <p className="text-xs font-bold uppercase tracking-[0.16em] text-emerald-600">
                  Parking bay
                </p>
                <h2 className="mt-1 text-2xl font-black text-slate-900">
                  {selectedBay.code || selectedBay.bay_number}
                </h2>
              </div>

              <button
                type="button"
                onClick={() => setSelectedBay(null)}
                aria-label="Close bay details"
                className="rounded-xl p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              >
                <X size={18} />
              </button>
            </div>

            <div className="space-y-4 p-6">
              <div className="flex items-center justify-between rounded-2xl bg-slate-50 p-4">
                <span className="text-xs font-bold uppercase tracking-wide text-slate-400">
                  Status
                </span>
                <span
                  className={`rounded-full px-3 py-1.5 text-xs font-black ${
                    selectedBay.status === "AVAILABLE"
                      ? "bg-emerald-100 text-emerald-700"
                      : selectedBay.status === "OCCUPIED"
                        ? "bg-rose-100 text-rose-700"
                        : selectedBay.status === "RESERVED"
                          ? "bg-amber-100 text-amber-700"
                          : "bg-slate-200 text-slate-600"
                  }`}
                >
                  {formatStatus(selectedBay.status)}
                </span>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <Detail
                  label="Bay"
                  value={selectedBay.code || selectedBay.bay_number}
                />
                <Detail
                  label="Bay type"
                  value={selectedBay.bay_type || "—"}
                />
                <Detail
                  label="Vehicle type"
                  value={selectedBay.vehicle_type || "—"}
                />
                <Detail
                  label="Size"
                  value={selectedBay.size || "—"}
                />
              </div>

              {selectedBay.session && (
                <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4">
                  <p className="text-xs font-black uppercase tracking-wide text-rose-700">
                    Current vehicle
                  </p>
                  <p className="mt-2 text-lg font-black text-slate-900">
                    {selectedBay.session.vehicle_registration}
                  </p>
                  <div className="mt-3 grid gap-2 text-xs text-slate-600">
                    <p>
                      Session:{" "}
                      <strong>{selectedBay.session.session_number}</strong>
                    </p>
                    <p>
                      Check-in:{" "}
                      <strong>
                        {formatDateTime(selectedBay.session.entry_time)}
                      </strong>
                    </p>
                    <p>
                      Access:{" "}
                      <strong>
                        {String(selectedBay.session.entry_method).replace(
                          /_/g,
                          " ",
                        )}
                      </strong>
                    </p>
                  </div>
                </div>
              )}

              {selectedBay.reservation && (
                <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                  <p className="text-xs font-black uppercase tracking-wide text-amber-700">
                    Reserved for
                  </p>
                  <p className="mt-2 text-lg font-black text-slate-900">
                    {selectedBay.reservation.vehicle_registration}
                  </p>
                  <div className="mt-3 grid gap-2 text-xs text-slate-600">
                    <p>
                      Reservation:{" "}
                      <strong>
                        {selectedBay.reservation.reservation_number}
                      </strong>
                    </p>
                    <p>
                      Arrival:{" "}
                      <strong>
                        {formatDateTime(
                          selectedBay.reservation.reserved_from,
                        )}
                      </strong>
                    </p>
                    <p>
                      Ends:{" "}
                      <strong>
                        {formatDateTime(
                          selectedBay.reservation.reserved_until,
                        )}
                      </strong>
                    </p>
                  </div>
                </div>
              )}

              {selectedBay.status === "AVAILABLE" && (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
                  <div className="flex items-start gap-2">
                    <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
                    <p>
                      This bay is currently available for vehicle admission.
                    </p>
                  </div>
                </div>
              )}

              <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:justify-end">
                {selectedBay.status === "OCCUPIED" && (
                  <Link
                    to="/operator/access/manual"
                    className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#071a2d] px-4 py-2.5 text-xs font-black text-white transition hover:bg-[#0b2a4a]"
                  >
                    Manage vehicle exit
                  </Link>
                )}

                <button
                  type="button"
                  onClick={() => setSelectedBay(null)}
                  className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-bold text-slate-700 transition hover:bg-slate-50"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Detail({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-sm font-bold text-slate-800">{value}</p>
    </div>
  );
}
