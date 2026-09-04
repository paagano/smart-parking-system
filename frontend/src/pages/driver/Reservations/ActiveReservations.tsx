import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  CalendarClock,
  CarFront,
  CheckCircle2,
  Clock3,
  MapPin,
  ParkingCircle,
  RefreshCw,
  Search,
} from "lucide-react";

import { useAuth } from "../../../auth/AuthContext";

import {
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

import { Card, Metric, default as Page } from "../../../components/common/Page";

export default function ActiveReservations() {
  const { user } = useAuth();

  // ==========================================================
  // Data
  // ==========================================================

  const [reservations, setReservations] = useState<ParkingReservation[]>([]);

  const [activeSessions, setActiveSessions] = useState<ParkingSession[]>([]);

  const [facilities, setFacilities] = useState<ParkingFacility[]>([]);

  const [zones, setZones] = useState<ParkingZone[]>([]);

  const [bays, setBays] = useState<ParkingBay[]>([]);

  // ==========================================================
  // UI State
  // ==========================================================

  const [loading, setLoading] = useState(true);

  const [isRefreshing, setIsRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [searchTerm, setSearchTerm] = useState("");

  // ==========================================================
  // Load Active Reservations
  // ==========================================================

  useEffect(() => {
    let cancelled = false;

    const loadActiveReservations = async (manualRefresh = false) => {
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
        /*
         * Load the customer's reservations.
         * The active page is derived strictly by matching these
         * reservations to a currently active parking session.
         *
         * The general customer reservation list is required here
         * because a reservation becomes CHECKED_IN when the vehicle
         * arrives, and must still be discoverable on this page.
         */
        const [
          reservationResult,
          activeSessionResult,
          facilityResult,
          zoneResult,
          bayResult,
        ] = await Promise.allSettled([
          parkingReservationsApi.byCustomer(user.id),
          parkingSessionsApi.active(),
          parkingFacilitiesApi.list(0, 500),
          parkingZonesApi.list(0, 500),
          parkingBaysApi.list(0, 500),
        ]);

        if (cancelled) return;

        const failures: string[] = [];

        // ------------------------------------------------------
        // Active Reservations
        // ------------------------------------------------------

        if (reservationResult.status === "fulfilled") {
          setReservations(reservationResult.value.items);
        } else {
          failures.push("active reservations");
        }

        // ------------------------------------------------------
        // Active Parking Sessions
        // ------------------------------------------------------

        if (activeSessionResult.status === "fulfilled") {
          const sessions = activeSessionResult.value.items ?? [];

          const customerSessions = sessions.filter(
            (session) =>
              session.customer_id === null ||
              session.customer_id === undefined ||
              String(session.customer_id) === String(user.id),
          );

          setActiveSessions(customerSessions);
        } else {
          failures.push("active parking sessions");
        }

        // ------------------------------------------------------
        // Facilities
        // ------------------------------------------------------

        if (facilityResult.status === "fulfilled") {
          setFacilities(facilityResult.value.items);
        } else {
          failures.push("parking facilities");
        }

        // ------------------------------------------------------
        // Zones
        // ------------------------------------------------------

        if (zoneResult.status === "fulfilled") {
          setZones(zoneResult.value.items);
        } else {
          failures.push("parking zones");
        }

        // ------------------------------------------------------
        // Bays
        // ------------------------------------------------------

        if (bayResult.status === "fulfilled") {
          setBays(bayResult.value.items);
        } else {
          failures.push("parking bays");
        }

        if (failures.includes("active reservations")) {
          setError(
            "Unable to load your active parking session from the SmartPark AI backend.",
          );
        } else if (failures.length > 0) {
          setError(
            `Active reservation loaded, but some parking details could not be resolved: ${failures.join(
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
            : "Unable to load your active reservation from the SmartPark AI backend.",
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
          setIsRefreshing(false);
        }
      }
    };

    void loadActiveReservations();

    /*
     * Keep the active reservation page live.
     *
     * Important:
     * When the attendant checks the vehicle out, the backend
     * changes the reservation from CHECKED_IN to COMPLETED.
     *
     * The next refresh will therefore automatically remove it
     * from this page.
     */
    const refreshTimer = window.setInterval(() => {
      void loadActiveReservations(true);
    }, 10000);

    return () => {
      cancelled = true;
      window.clearInterval(refreshTimer);
    };
  }, [user]);

  // ==========================================================
  // Lookup Maps
  // ==========================================================

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

  // ==========================================================
  // Reservation Hierarchy Helpers
  // ==========================================================

  const getBay = (reservation: ParkingReservation) => {
    return bayMap.get(reservation.parking_bay_id) ?? null;
  };

  const getZone = (reservation: ParkingReservation) => {
    const bay = getBay(reservation);

    return bay ? (zoneMap.get(bay.zone_id) ?? null) : null;
  };

  const getFacility = (reservation: ParkingReservation) => {
    const zone = getZone(reservation);

    return zone ? (facilityMap.get(zone.facility_id) ?? null) : null;
  };

  const getActiveSession = (reservation: ParkingReservation) => {
    const reservationRegistration = String(
      reservation.vehicle_registration ?? "",
    )
      .trim()
      .toUpperCase();

    return (
      activeSessions.find((session) => {
        const sessionWithReservation = session as ParkingSession & {
          reservation_id?: number | null;
        };

        // Reservation-created parking sessions carry the exact
        // reservation ID. Prefer this authoritative relationship.
        if (
          sessionWithReservation.reservation_id != null &&
          Number(sessionWithReservation.reservation_id) ===
            Number(reservation.id)
        ) {
          return true;
        }

        const sessionRegistration = String(session.vehicle_registration ?? "")
          .trim()
          .toUpperCase();

        const sameBay =
          Number(session.parking_bay_id) === Number(reservation.parking_bay_id);

        const sameVehicle =
          reservation.vehicle_id != null &&
          session.vehicle_id != null &&
          Number(session.vehicle_id) === Number(reservation.vehicle_id);

        const sameRegistration =
          reservationRegistration !== "" &&
          sessionRegistration !== "" &&
          reservationRegistration === sessionRegistration;

        return sameBay && (sameVehicle || sameRegistration);
      }) ?? null
    );
  };

  // ==========================================================
  // Formatting
  // ==========================================================

  const formatDateTime = (value: string | null | undefined) => {
    if (!value) return "—";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return "—";
    }

    return new Intl.DateTimeFormat("en-KE", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  };

  const formatDate = (value: string | null | undefined) => {
    if (!value) return "—";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return "—";
    }

    return new Intl.DateTimeFormat("en-KE", {
      dateStyle: "medium",
    }).format(date);
  };

  const formatTime = (value: string | null | undefined) => {
    if (!value) return "—";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return "—";
    }

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

  // ==========================================================
  // Only reservations with an ACTIVE parking session
  // ==========================================================

  const checkedInReservations = useMemo(() => {
    return reservations.filter(
      (reservation) => getActiveSession(reservation) !== null,
    );
  }, [reservations, activeSessions]);

  // ==========================================================
  // Status
  // ==========================================================

  const getStatus = (_reservation: ParkingReservation) => ({
    label: "Checked In",
    className: "bg-blue-50 text-blue-700 ring-1 ring-blue-200",
  });

  // ==========================================================
  // Search
  // ==========================================================

  const visibleReservations = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();

    if (!query) {
      return checkedInReservations;
    }

    const tokens = query
      .split(/\s+/)
      .map((token) => token.trim())
      .filter(Boolean);

    return checkedInReservations.filter((reservation) => {
      const bay = getBay(reservation);

      const zone = getZone(reservation);

      const facility = getFacility(reservation);

      const searchableText = [
        reservation.reservation_number,
        reservation.vehicle_registration,
        reservation.vehicle_type,
        reservation.status,

        facility?.name,
        zone?.name,
        bay?.bay_number,
        bay?.code,

        reservation.notes,

        formatDate(reservation.reserved_from),

        formatDateTime(reservation.reserved_from),

        formatDateTime(reservation.reserved_until),

        formatDateTime(reservation.checked_in_at),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return tokens.every((token) => searchableText.includes(token));
    });
  }, [
    checkedInReservations,
    searchTerm,
    bayMap,
    zoneMap,
    facilityMap,
    activeSessions,
  ]);

  // ==========================================================
  // Refresh
  // ==========================================================

  const refresh = async () => {
    if (!user?.id) return;

    setIsRefreshing(true);
    setError(null);

    try {
      const [reservationResult, activeSessionResult] = await Promise.all([
        parkingReservationsApi.byCustomer(user.id),
        parkingSessionsApi.active(),
      ]);

      setReservations(reservationResult.items);

      const sessions = activeSessionResult.items ?? [];

      setActiveSessions(
        sessions.filter(
          (session) =>
            session.customer_id === null ||
            session.customer_id === undefined ||
            String(session.customer_id) === String(user.id),
        ),
      );

      setLastUpdated(new Date());
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to refresh active reservations.",
      );
    } finally {
      setIsRefreshing(false);
    }
  };

  // ==========================================================
  // Render
  // ==========================================================

  return (
    <>
      {/* ======================================================
          PAGE HEADER
      ====================================================== */}

      {/* <Page
        title="Active Reservations"
        text="View your ongoing parking session and current reservation details."
      /> */}

      {/* ======================================================
          PAGE CONTENT
      ====================================================== */}

      <div className="space-y-6">
        {/* ====================================================
            HEADER
        ==================================================== */}

        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Activity className="text-blue-600" size={22} />

              <h2 className="text-xl font-extrabold text-slate-900">
                Active Parking
              </h2>
            </div>

            <p className="mt-1 text-sm text-slate-500">
              {/* Your currently active parking reservation and ongoing parking
              session. */}
              View your ongoing parking session and current reservation details.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void refresh()}
            disabled={isRefreshing || loading}
            className="inline-flex items-center justify-center gap-2 self-start rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
          >
            <RefreshCw
              size={16}
              className={isRefreshing ? "animate-spin" : ""}
            />

            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        {/* ====================================================
            METRICS
        ==================================================== */}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Metric
            label="Active"
            value={loading ? "…" : String(checkedInReservations.length)}
            note="Ongoing parking"
            Icon={Activity}
          />

          <Metric
            label="Checked In"
            value={loading ? "…" : String(checkedInReservations.length)}
            note="Currently on site"
            Icon={CheckCircle2}
          />

          <Metric
            label="Latest Check-In"
            value={
              loading
                ? "…"
                : checkedInReservations[0]
                  ? formatDate(
                      checkedInReservations[0].checked_in_at ??
                        getActiveSession(checkedInReservations[0])?.entry_time,
                    )
                  : "None"
            }
            note={
              checkedInReservations[0]
                ? formatTime(
                    checkedInReservations[0].checked_in_at ??
                      getActiveSession(checkedInReservations[0])?.entry_time,
                  )
                : "No active session"
            }
            Icon={Clock3}
          />
        </div>

        {/* ====================================================
            ERROR
        ==================================================== */}

        {error && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
            <div className="flex items-start gap-3">
              <Clock3 size={18} className="mt-0.5 shrink-0" />

              <div>
                <b className="font-bold">Live data warning</b>

                <p className="mt-1">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* ====================================================
            ACTIVE RESERVATIONS CARD
        ==================================================== */}

        <Card
          title="My Current Checked-In Reservations"
          sub={
            lastUpdated
              ? `Live data • Last updated ${formatDateTime(
                  lastUpdated.toISOString(),
                )}`
              : "Live active reservation data from SmartPark AI"
          }
        >
          {/* ==================================================
              SEARCH
          ================================================== */}

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
                placeholder="Search reservation, vehicle, facility, bay or date..."
                aria-label="Search active reservations"
                className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-10 pr-4 text-sm font-medium outline-none transition placeholder:text-slate-400 focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
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
              Showing {visibleReservations.length} matching active reservation
              {visibleReservations.length === 1 ? "" : "s"}.
            </p>
          )}

          {/* ==================================================
              LOADING
          ================================================== */}

          {loading ? (
            <div className="space-y-4">
              {[1].map((item) => (
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
          ) : reservations.length === 0 ? (
            /* ==================================================
               NO ACTIVE RESERVATIONS
            ================================================== */

            <div className="rounded-2xl bg-slate-50 px-6 py-12 text-center">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
                <ParkingCircle size={28} />
              </div>

              <h3 className="mt-4 text-lg font-extrabold text-slate-900">
                No active parking session
              </h3>

              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
                You currently do not have a vehicle checked in to a SmartPark AI
                parking facility.
              </p>
            </div>
          ) : visibleReservations.length === 0 ? (
            /* ==================================================
               NO SEARCH MATCHES
            ================================================== */

            <div className="rounded-2xl bg-slate-50 px-6 py-12 text-center">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
                <Search size={28} />
              </div>

              <h3 className="mt-4 text-lg font-extrabold text-slate-900">
                No matching active reservation
              </h3>

              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
                Try another reservation number, vehicle registration, facility,
                parking bay, or date.
              </p>

              <button
                type="button"
                onClick={() => setSearchTerm("")}
                className="mt-5 rounded-xl bg-blue-600 px-5 py-3 text-sm font-extrabold text-white transition hover:bg-blue-700"
              >
                Clear search
              </button>
            </div>
          ) : (
            /* ==================================================
               ACTIVE RESERVATION LIST
            ================================================== */

            <div className="space-y-4">
              {visibleReservations.map((reservation) => {
                const bay = getBay(reservation);

                const zone = getZone(reservation);

                const facility = getFacility(reservation);

                const status = getStatus(reservation);

                return (
                  <article
                    key={reservation.id}
                    className="rounded-2xl border border-blue-200 bg-white p-5 shadow-sm transition hover:border-blue-300"
                  >
                    {/* ==========================================
                          ACTIVE SESSION BANNER
                      ========================================== */}

                    <div className="mb-5 flex items-center gap-3 rounded-2xl border border-blue-100 bg-blue-50 px-4 py-3">
                      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-100 text-blue-600">
                        <Activity size={20} />
                      </div>

                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-extrabold text-blue-900">
                          Parking session active
                        </p>

                        <p className="mt-0.5 text-xs text-blue-700">
                          Your vehicle is currently checked in.
                        </p>
                      </div>

                      <span
                        className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-extrabold ${status.className}`}
                      >
                        {status.label}
                      </span>
                    </div>

                    {/* ==========================================
                          HEADER
                      ========================================== */}

                    <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                      <div className="min-w-0">
                        <div className="flex items-center gap-3">
                          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
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

                    {/* ==========================================
                          LOCATION
                      ========================================== */}

                    <div className="mt-5 grid gap-3 sm:grid-cols-3">
                      <div className="rounded-xl bg-slate-50 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <MapPin size={15} />
                          Facility
                        </div>

                        <p className="mt-2 text-sm font-extrabold text-slate-900">
                          {facility?.name ?? "Parking Facility"}
                        </p>
                      </div>

                      <div className="rounded-xl bg-slate-50 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <ParkingCircle size={15} />
                          Zone
                        </div>

                        <p className="mt-2 text-sm font-extrabold text-slate-900">
                          {zone?.name ?? "—"}
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
                      </div>
                    </div>

                    {/* ==========================================
                          VEHICLE
                      ========================================== */}

                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
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

                      <div className="rounded-xl bg-slate-50 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <CheckCircle2 size={15} />
                          Checked In
                        </div>

                        <p className="mt-2 text-sm font-extrabold text-slate-900">
                          {formatDateTime(
                            reservation.checked_in_at ??
                              getActiveSession(reservation)?.entry_time,
                          )}
                        </p>

                        <p className="mt-1 text-xs text-slate-500">
                          Vehicle currently on site
                        </p>
                      </div>
                    </div>

                    {/* ==========================================
                          RESERVATION PERIOD
                      ========================================== */}

                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      <div className="rounded-xl bg-slate-50 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <CalendarClock size={15} />
                          Reserved From
                        </div>

                        <p className="mt-2 text-sm font-extrabold text-slate-900">
                          {formatDateTime(reservation.reserved_from)}
                        </p>
                      </div>

                      <div className="rounded-xl bg-slate-50 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <Clock3 size={15} />
                          Reserved Until
                        </div>

                        <p className="mt-2 text-sm font-extrabold text-slate-900">
                          {formatDateTime(reservation.reserved_until)}
                        </p>
                      </div>
                    </div>

                    {/* ==========================================
                          AMOUNT
                      ========================================== */}

                    <div className="mt-4 flex flex-col gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <span className="text-xs text-slate-500">
                          Reservation Amount
                        </span>

                        <p className="mt-0.5 text-base font-extrabold text-slate-900">
                          {formatAmount(
                            reservation.estimated_amount,
                            reservation.currency || "KES",
                          )}
                        </p>
                      </div>

                      <div className="text-left sm:text-right">
                        <span className="text-xs text-slate-500">
                          Session Status
                        </span>

                        <p className="mt-0.5 text-sm font-extrabold text-blue-700">
                          Ongoing
                        </p>
                      </div>
                    </div>

                    {/* ==========================================
                          NOTES
                      ========================================== */}

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

                    {/* ==========================================
                          INFORMATION
                      ========================================== */}

                    <div className="mt-4 flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50 px-4 py-3">
                      <Activity
                        size={17}
                        className="mt-0.5 shrink-0 text-blue-600"
                      />

                      <p className="text-xs leading-5 text-slate-600">
                        Your parking session is currently active. Once the
                        payment is completed and vehicle is checked out, the
                        reservation will automatically move to
                        <b className="ml-1 text-slate-800">COMPLETED </b>
                         and will no longer appear under Active Reservations.
                      </p>
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </>
  );
}
