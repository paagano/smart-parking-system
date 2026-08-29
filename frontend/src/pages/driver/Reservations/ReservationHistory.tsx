import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  CalendarClock,
  CarFront,
  CheckCircle2,
  Clock3,
  ParkingCircle,
  RefreshCw,
  Search,
  XCircle,
} from "lucide-react";

import { useAuth } from "../../../auth/AuthContext";
import {
  parkingBaysApi,
  parkingFacilitiesApi,
  parkingReservationsApi,
  parkingZonesApi,
  type ParkingBay,
  type ParkingFacility,
  type ParkingReservation,
  type ParkingZone,
} from "../../../api";

import { Card, Metric, default as Page } from "../../../components/common/Page";

export default function ReservationHistory() {
  const { user } = useAuth();

  const [reservations, setReservations] = useState<ParkingReservation[]>([]);
  const [facilities, setFacilities] = useState<ParkingFacility[]>([]);
  const [zones, setZones] = useState<ParkingZone[]>([]);
  const [bays, setBays] = useState<ParkingBay[]>([]);

  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [searchTerm, setSearchTerm] = useState("");

  useEffect(() => {
    let cancelled = false;

    const loadHistory = async (manualRefresh = false) => {
      if (!user?.id) {
        setReservations([]);
        setLoading(false);
        return;
      }

      if (manualRefresh) {
        setIsRefreshing(true);
      } else {
        setLoading(true);
      }

      setError(null);

      try {
        const [reservationResult, facilityResult, zoneResult, bayResult] =
          await Promise.allSettled([
            parkingReservationsApi.byCustomer(user.id),
            parkingFacilitiesApi.list(0, 500),
            parkingZonesApi.list(0, 500),
            parkingBaysApi.list(0, 500),
          ]);

        if (cancelled) return;

        const failures: string[] = [];

        if (reservationResult.status === "fulfilled") {
          setReservations(reservationResult.value.items);
        } else {
          failures.push("reservations");
        }

        if (facilityResult.status === "fulfilled") {
          setFacilities(facilityResult.value.items);
        } else {
          failures.push("parking facilities");
        }

        if (zoneResult.status === "fulfilled") {
          setZones(zoneResult.value.items);
        } else {
          failures.push("parking zones");
        }

        if (bayResult.status === "fulfilled") {
          setBays(bayResult.value.items);
        } else {
          failures.push("parking bays");
        }

        if (failures.includes("reservations")) {
          setError(
            "Unable to load your reservation history from the SmartPark AI backend.",
          );
        } else if (failures.length > 0) {
          setError(
            `Reservation history loaded, but some parking details could not be resolved: ${failures.join(
              ", ",
            )}.`,
          );
        }

        setLastUpdated(new Date());
      } catch (err) {
        if (cancelled) return;

        setError(
          err instanceof Error
            ? err.message
            : "Unable to load your reservation history from the SmartPark AI backend.",
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
          setIsRefreshing(false);
        }
      }
    };

    void loadHistory();

    const refreshTimer = window.setInterval(() => {
      void loadHistory(true);
    }, 10000);

    return () => {
      cancelled = true;
      window.clearInterval(refreshTimer);
    };
  }, [user]);

  const bayMap = useMemo(
    () => new Map(bays.map((bay) => [bay.id, bay])),
    [bays],
  );

  const zoneMap = useMemo(
    () => new Map(zones.map((zone) => [zone.id, zone])),
    [zones],
  );

  const facilityMap = useMemo(
    () => new Map(facilities.map((facility) => [facility.id, facility])),
    [facilities],
  );

  const getBay = (reservation: ParkingReservation) =>
    bayMap.get(reservation.parking_bay_id) ?? null;

  const getZone = (reservation: ParkingReservation) => {
    const bay = getBay(reservation);
    return bay ? (zoneMap.get(bay.zone_id) ?? null) : null;
  };

  const getFacility = (reservation: ParkingReservation) => {
    const zone = getZone(reservation);
    return zone ? (facilityMap.get(zone.facility_id) ?? null) : null;
  };

  const formatDateTime = (value: string | null | undefined) => {
    if (!value) return "—";

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";

    return new Intl.DateTimeFormat("en-KE", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  };

  const formatDate = (value: string | null | undefined) => {
    if (!value) return "—";

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";

    return new Intl.DateTimeFormat("en-KE", {
      dateStyle: "medium",
    }).format(date);
  };

  const formatTime = (value: string | null | undefined) => {
    if (!value) return "—";

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";

    return new Intl.DateTimeFormat("en-KE", {
      timeStyle: "short",
    }).format(date);
  };

  const formatAmount = (
    amount: number | string | null | undefined,
    currency = "KES",
  ) => {
    if (amount === null || amount === undefined || amount === "") {
      return "—";
    }

    const numericAmount = Number(amount);

    if (Number.isNaN(numericAmount)) {
      return `${currency} ${amount}`;
    }

    return new Intl.NumberFormat("en-KE", {
      style: "currency",
      currency,
      maximumFractionDigits: 2,
    }).format(numericAmount);
  };

  const getStatus = (reservation: ParkingReservation) => {
    const status = String(reservation.status ?? "").toLowerCase();

    if (status.includes("cancel") || reservation.cancelled_at) {
      return {
        label: "Cancelled",
        className: "bg-rose-50 text-rose-700 ring-1 ring-rose-200",
      };
    }

    if (status.includes("complete") || reservation.completed_at) {
      return {
        label: "Completed",
        className: "bg-slate-100 text-slate-700 ring-1 ring-slate-200",
      };
    }

    if (status.includes("expire")) {
      return {
        label: "Expired",
        className: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
      };
    }

    if (status.includes("check") || reservation.checked_in_at) {
      return {
        label: "Checked In",
        className: "bg-blue-50 text-blue-700 ring-1 ring-blue-200",
      };
    }

    if (status.includes("confirm")) {
      return {
        label: "Confirmed",
        className: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
      };
    }

    if (status.includes("create")) {
      return {
        label: "Created",
        className: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
      };
    }

    return {
      label: reservation.status
        ? String(reservation.status)
            .replace(/_/g, " ")
            .replace(/\b\w/g, (letter) => letter.toUpperCase())
        : "Unknown",
      className: "bg-slate-100 text-slate-700 ring-1 ring-slate-200",
    };
  };

  const historyReservations = useMemo(() => {
    const now = Date.now();

    return reservations
      .filter((reservation) => {
        const status = String(reservation.status ?? "").toLowerCase();

        const isCompleted =
          status.includes("complete") || Boolean(reservation.completed_at);

        const isCancelled =
          status.includes("cancel") || Boolean(reservation.cancelled_at);

        const isExpired = status.includes("expire");

        const end = new Date(reservation.reserved_until).getTime();
        const periodHasEnded = Number.isFinite(end) && end < now;

        /*
         * History contains reservations that have left the active/upcoming
         * lifecycle: completed, cancelled, expired, or otherwise ended.
         */
        return isCompleted || isCancelled || isExpired || periodHasEnded;
      })
      .sort((a, b) => {
        const aDate = new Date(
          a.completed_at || a.cancelled_at || a.reserved_until || a.created_at,
        ).getTime();

        const bDate = new Date(
          b.completed_at || b.cancelled_at || b.reserved_until || b.created_at,
        ).getTime();

        return bDate - aDate;
      });
  }, [reservations]);

  const visibleReservations = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();

    if (!query) return historyReservations;

    const tokens = query
      .split(/\s+/)
      .map((token) => token.trim())
      .filter(Boolean);

    return historyReservations.filter((reservation) => {
      const bay = getBay(reservation);
      const zone = getZone(reservation);
      const facility = getFacility(reservation);
      const status = getStatus(reservation);

      const searchableText = [
        reservation.reservation_number,
        reservation.vehicle_registration,
        reservation.vehicle_type,
        reservation.status,
        status.label,
        facility?.name,
        zone?.name,
        bay?.bay_number,
        bay?.code,
        reservation.notes,
        formatDate(reservation.reserved_from),
        formatDate(reservation.reserved_until),
        formatDateTime(reservation.completed_at),
        formatDateTime(reservation.cancelled_at),
        formatDateTime(reservation.reserved_from),
        formatDateTime(reservation.reserved_until),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return tokens.every((token) => searchableText.includes(token));
    });
  }, [historyReservations, searchTerm, bayMap, zoneMap, facilityMap]);

  const completedCount = useMemo(
    () =>
      historyReservations.filter((reservation) => {
        const status = String(reservation.status ?? "").toLowerCase();
        return status.includes("complete") || Boolean(reservation.completed_at);
      }).length,
    [historyReservations],
  );

  const cancelledCount = useMemo(
    () =>
      historyReservations.filter((reservation) => {
        const status = String(reservation.status ?? "").toLowerCase();
        return status.includes("cancel") || Boolean(reservation.cancelled_at);
      }).length,
    [historyReservations],
  );

  const expiredCount = useMemo(
    () =>
      historyReservations.filter((reservation) =>
        String(reservation.status ?? "")
          .toLowerCase()
          .includes("expire"),
      ).length,
    [historyReservations],
  );

  const refresh = async () => {
    if (!user?.id) return;

    setIsRefreshing(true);
    setError(null);

    try {
      const result = await parkingReservationsApi.byCustomer(user.id);
      setReservations(result.items);
      setLastUpdated(new Date());
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to refresh reservation history.",
      );
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <Page
          title="Reservation History"
          text="View your completed, cancelled and expired parking reservations."
        />

        <button
          type="button"
          onClick={() => void refresh()}
          disabled={isRefreshing || loading}
          className="inline-flex items-center justify-center gap-2 self-start rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
        >
          <RefreshCw size={16} className={isRefreshing ? "animate-spin" : ""} />
          {isRefreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="History"
          value={loading ? "…" : String(historyReservations.length)}
          note="Past reservations"
          Icon={ParkingCircle}
        />

        <Metric
          label="Completed"
          value={loading ? "…" : String(completedCount)}
          note="Successfully completed"
          Icon={CheckCircle2}
        />

        <Metric
          label="Cancelled"
          value={loading ? "…" : String(cancelledCount)}
          note="Cancelled bookings"
          Icon={XCircle}
        />

        <Metric
          label="Expired"
          value={loading ? "…" : String(expiredCount)}
          note="Expired bookings"
          Icon={Clock3}
        />
      </div>

      {error && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
          <div className="flex items-start gap-3">
            <Activity size={18} className="mt-0.5 shrink-0" />
            <div>
              <b className="font-bold">Live data warning</b>
              <p className="mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      <Card
        title="Reservation History"
        sub={
          lastUpdated
            ? `Live data • Last updated ${formatDateTime(
                lastUpdated.toISOString(),
              )}`
            : "Historical reservation data from SmartPark AI"
        }
      >
        <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative min-w-0 flex-1">
            <Search
              size={18}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />

            <input
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search reservation, vehicle, facility, bay, status or date..."
              aria-label="Search reservation history"
              className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-10 pr-4 text-sm font-medium outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            />
          </div>

          {searchTerm.trim() && (
            <button
              type="button"
              onClick={() => setSearchTerm("")}
              className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-600 transition hover:bg-slate-50"
            >
              Clear
            </button>
          )}
        </div>

        {searchTerm.trim() && !loading && (
          <p className="mb-4 text-xs font-semibold text-slate-500">
            Showing {visibleReservations.length} matching historical reservation
            {visibleReservations.length === 1 ? "" : "s"}.
          </p>
        )}

        {loading ? (
          <div className="space-y-4">
            {[1, 2, 3].map((item) => (
              <div
                key={item}
                className="animate-pulse rounded-2xl border border-slate-200 bg-white p-5"
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-3">
                    <div className="h-5 w-48 rounded bg-slate-200" />
                    <div className="h-4 w-32 rounded bg-slate-200" />
                    <div className="h-4 w-56 rounded bg-slate-200" />
                  </div>
                  <div className="h-7 w-24 rounded-full bg-slate-200" />
                </div>

                <div className="mt-5 grid gap-3 sm:grid-cols-3">
                  <div className="h-16 rounded-xl bg-slate-100" />
                  <div className="h-16 rounded-xl bg-slate-100" />
                  <div className="h-16 rounded-xl bg-slate-100" />
                </div>
              </div>
            ))}
          </div>
        ) : historyReservations.length === 0 ? (
          <div className="rounded-2xl bg-slate-50 px-6 py-12 text-center">
            <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
              <ParkingCircle size={28} />
            </div>

            <h3 className="mt-4 text-lg font-extrabold text-slate-900">
              No reservation history
            </h3>

            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
              Your completed, cancelled or expired reservations will appear
              here.
            </p>
          </div>
        ) : visibleReservations.length === 0 ? (
          <div className="rounded-2xl bg-slate-50 px-6 py-12 text-center">
            <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
              <Search size={28} />
            </div>

            <h3 className="mt-4 text-lg font-extrabold text-slate-900">
              No matching reservations
            </h3>

            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
              Try another reservation number, vehicle registration, facility,
              parking bay, status, or date.
            </p>

            <button
              type="button"
              onClick={() => setSearchTerm("")}
              className="mt-5 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white transition hover:bg-emerald-700"
            >
              Clear search
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {visibleReservations.map((reservation) => {
              const bay = getBay(reservation);
              const zone = getZone(reservation);
              const facility = getFacility(reservation);
              const status = getStatus(reservation);

              return (
                <article
                  key={reservation.id}
                  className="rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-slate-300 hover:shadow-sm"
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex items-center gap-3">
                        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600">
                          <ParkingCircle size={21} />
                        </div>

                        <div className="min-w-0">
                          <h3 className="truncate text-base font-extrabold text-slate-900">
                            {facility?.name ?? "Parking Facility"}
                          </h3>

                          <p className="mt-0.5 text-xs text-slate-500">
                            Reservation{" "}
                            <span className="font-bold text-slate-700">
                              {reservation.reservation_number}
                            </span>
                          </p>
                        </div>
                      </div>
                    </div>

                    <span
                      className={`inline-flex w-fit items-center rounded-full px-3 py-1.5 text-xs font-extrabold ${status.className}`}
                    >
                      {status.label}
                    </span>
                  </div>

                  <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                    <div className="rounded-xl bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                        <CalendarClock size={15} />
                        Reservation Date
                      </div>

                      <p className="mt-2 text-sm font-extrabold text-slate-900">
                        {formatDate(reservation.reserved_from)}
                      </p>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                        <Clock3 size={15} />
                        Time
                      </div>

                      <p className="mt-2 text-sm font-extrabold text-slate-900">
                        {formatTime(reservation.reserved_from)} –{" "}
                        {formatTime(reservation.reserved_until)}
                      </p>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                        <ParkingCircle size={15} />
                        Parking Bay
                      </div>

                      <p className="mt-2 text-sm font-extrabold text-slate-900">
                        {bay?.bay_number ??
                          bay?.code ??
                          `Bay #${reservation.parking_bay_id}`}
                      </p>

                      {zone && (
                        <p className="mt-1 text-xs text-slate-500">
                          {zone.name}
                        </p>
                      )}
                    </div>

                    <div className="rounded-xl bg-slate-50 p-4">
                      <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                        <CarFront size={15} />
                        Vehicle
                      </div>

                      <p className="mt-2 text-sm font-extrabold text-slate-900">
                        {reservation.vehicle_registration || "Not specified"}
                      </p>

                      <p className="mt-1 text-xs text-slate-500">
                        {reservation.vehicle_type || "Vehicle"}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl bg-slate-50 p-4">
                      <span className="text-xs text-slate-500">
                        Estimated amount
                      </span>

                      <p className="mt-0.5 text-base font-extrabold text-slate-900">
                        {formatAmount(
                          reservation.estimated_amount,
                          reservation.currency || "KES",
                        )}
                      </p>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-4">
                      <span className="text-xs text-slate-500">
                        Historical event
                      </span>

                      <p className="mt-0.5 text-sm font-extrabold text-slate-900">
                        {reservation.completed_at
                          ? `Completed ${formatDateTime(
                              reservation.completed_at,
                            )}`
                          : reservation.cancelled_at
                            ? `Cancelled ${formatDateTime(
                                reservation.cancelled_at,
                              )}`
                            : status.label === "Expired"
                              ? `Expired ${formatDateTime(
                                  reservation.reserved_until,
                                )}`
                              : `Reservation ended ${formatDateTime(
                                  reservation.reserved_until,
                                )}`}
                      </p>
                    </div>
                  </div>

                  {(reservation.confirmed_at ||
                    reservation.checked_in_at ||
                    reservation.completed_at ||
                    reservation.cancelled_at) && (
                    <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                      <div className="flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-500">
                        {reservation.confirmed_at && (
                          <span>
                            Confirmed:{" "}
                            <b className="text-slate-700">
                              {formatDateTime(reservation.confirmed_at)}
                            </b>
                          </span>
                        )}

                        {reservation.checked_in_at && (
                          <span>
                            Checked in:{" "}
                            <b className="text-slate-700">
                              {formatDateTime(reservation.checked_in_at)}
                            </b>
                          </span>
                        )}

                        {reservation.completed_at && (
                          <span>
                            Completed:{" "}
                            <b className="text-slate-700">
                              {formatDateTime(reservation.completed_at)}
                            </b>
                          </span>
                        )}

                        {reservation.cancelled_at && (
                          <span>
                            Cancelled:{" "}
                            <b className="text-slate-700">
                              {formatDateTime(reservation.cancelled_at)}
                            </b>
                          </span>
                        )}
                      </div>
                    </div>
                  )}

                  {reservation.notes && (
                    <div className="mt-4 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                      <p className="text-xs font-semibold text-slate-500">
                        Notes
                      </p>

                      <p className="mt-1 text-sm font-medium text-slate-700">
                        {reservation.notes}
                      </p>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
