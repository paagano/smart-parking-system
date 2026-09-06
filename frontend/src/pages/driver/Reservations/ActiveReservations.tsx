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
        // Current Parking Sessions
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
        // Parking Areas
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
            "Unable to load your current parking details right now. Please try again.",
          );
        } else if (failures.length > 0) {
          setError(
            `Your booking is available, but some parking details could not be loaded: ${failures.join(
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
            : "Unable to load your current parking details right now. Please try again.",
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
  // Booking Hierarchy Helpers
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
        const sessionWithBooking = session as ParkingSession & {
          reservation_id?: number | null;
        };

        // Reservation-created parking sessions carry the exact
        // reservation ID. Prefer this authoritative relationship.
        if (
          sessionWithBooking.reservation_id != null &&
          Number(sessionWithBooking.reservation_id) === Number(reservation.id)
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
    label: "Currently parked",
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
  // Refresh parking
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
        text="View your parking session and booking details while your vehicle is on site."
      /> */}

      {/* ======================================================
          PAGE CONTENT
      ====================================================== */}

      <div className="space-y-5 sm:space-y-6">
        {/* ====================================================
            HEADER
        ==================================================== */}

        <div className="flex flex-col gap-4 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <div>
            <div className="flex items-center gap-2">
              <Activity className="text-blue-600" size={22} />

              <h2 className="text-2xl font-extrabold tracking-tight text-slate-950">
                Current Parking
              </h2>
            </div>

            <p className="mt-1.5 max-w-2xl text-sm leading-6 text-slate-500">
              {/* Your currently active parking reservation and ongoing parking
              session. */}
              View your parking session and booking details while your vehicle
              is on site.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void refresh()}
            disabled={isRefreshing || loading}
            className="inline-flex items-center justify-center gap-2 self-start rounded-xl border border-slate-200 bg-slate-50 px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm transition hover:border-emerald-200 hover:bg-emerald-50 hover:text-emerald-700 disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
          >
            <RefreshCw
              size={16}
              className={isRefreshing ? "animate-spin" : ""}
            />

            {isRefreshing ? "Refreshing..." : "Refresh bookings"}
          </button>
        </div>

        {/* ====================================================
            METRICS
        ==================================================== */}

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <Metric
            label="Active"
            value={loading ? "…" : String(checkedInReservations.length)}
            note="Currently parked"
            Icon={Activity}
          />

          <Metric
            label="Checked in"
            value={loading ? "…" : String(checkedInReservations.length)}
            note="Vehicle on site"
            Icon={CheckCircle2}
          />

          <Metric
            label="Latest Check-in"
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
                : "No active parking"
            }
            Icon={Clock3}
          />
        </div>

        {/* ====================================================
            ERROR
        ==================================================== */}

        {error && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm leading-6 text-amber-800 shadow-sm">
            <div className="flex items-start gap-3">
              <Clock3 size={18} className="mt-0.5 shrink-0" />

              <div>
                <b className="font-medium">Live data warning</b>

                <p className="mt-1">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* ====================================================
            ACTIVE RESERVATIONS CARD
        ==================================================== */}

        <Card
          title="Currently Parked"
          sub={
            lastUpdated
              ? `Updated ${formatDateTime(lastUpdated.toISOString())}`
              : "Your current parking details"
          }
        >
          {/* ==================================================
              SEARCH
          ================================================== */}

          <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
            <div className="relative min-w-0 flex-1">
              <Search
                size={18}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />

              <input
                type="search"
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Search booking, vehicle, location, space or date..."
                aria-label="Search current parking"
                className="w-full rounded-xl border border-slate-200 bg-slate-50 py-3 pl-10 pr-4 text-sm font-medium outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-500 focus:bg-white focus:ring-4 focus:ring-emerald-50"
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
              Showing {visibleReservations.length} matching booking
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

                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
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

            <div className="rounded-3xl border border-slate-200 bg-slate-50/80 px-6 py-10 text-center sm:py-12">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
                <ParkingCircle size={28} />
              </div>

              <h3 className="mt-4 text-lg font-semibold text-slate-900">
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

            <div className="rounded-3xl border border-slate-200 bg-slate-50/80 px-6 py-10 text-center sm:py-12">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
                <Search size={28} />
              </div>

              <h3 className="mt-4 text-lg font-semibold text-slate-900">
                No matching booking
              </h3>

              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
                Try another reservation number, vehicle registration, facility,
                parking bay, or date.
              </p>

              <button
                type="button"
                onClick={() => setSearchTerm("")}
                className="mt-5 rounded-xl bg-blue-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-blue-700"
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
                    className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition hover:border-emerald-200 hover:shadow-md sm:p-6"
                  >
                    {/* ==========================================
                          ACTIVE SESSION BANNER
                      ========================================== */}

                    <div className="mb-4 flex items-center gap-3 rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3">
                      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-100 text-emerald-600">
                        <Activity size={20} />
                      </div>

                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-semibold text-emerald-900">
                          Parking session active
                        </p>

                        <p className="mt-0.5 text-xs text-emerald-700">
                          Your vehicle is currently checked in.
                        </p>
                      </div>

                      <span
                        className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-semibold ${status.className}`}
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
                            <h3 className="truncate text-base font-semibold text-slate-900">
                              {facility?.name ?? "Parking Location"}
                            </h3>

                            <p className="mt-0.5 text-xs text-slate-500">
                              Reservation{" "}
                              <span className="font-medium text-slate-700">
                                {reservation.reservation_number}
                              </span>
                            </p>
                          </div>
                        </div>
                      </div>

                      <span
                        className={`inline-flex w-fit items-center rounded-full px-3 py-1.5 text-xs font-semibold ${status.className}`}
                      >
                        {status.label}
                      </span>
                    </div>

                    {/* ==========================================
                          LOCATION
                      ========================================== */}

                    <div className="mt-4 grid gap-3 sm:grid-cols-3">
                      <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <MapPin size={15} />
                          Parking Location
                        </div>

                        <p className="mt-1.5 text-sm font-bold text-slate-900">
                          {facility?.name ?? "Parking Location"}
                        </p>
                      </div>

                      <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <ParkingCircle size={15} />
                          Parking Area
                        </div>

                        <p className="mt-1.5 text-sm font-bold text-slate-900">
                          {zone?.name ?? "—"}
                        </p>
                      </div>

                      <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <ParkingCircle size={15} />
                          Parking Space
                        </div>

                        <p className="mt-1.5 text-sm font-bold text-slate-900">
                          {bay?.bay_number ??
                            bay?.code ??
                            `Space #${reservation.parking_bay_id}`}
                        </p>
                      </div>
                    </div>

                    {/* ==========================================
                          VEHICLE
                      ========================================== */}

                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <CarFront size={15} />
                          Vehicle
                        </div>

                        <p className="mt-1.5 text-sm font-bold text-slate-900">
                          {reservation.vehicle_registration || "Not specified"}
                        </p>

                        <p className="mt-1 text-xs leading-5 text-slate-500">
                          {reservation.vehicle_type || "Vehicle"}
                        </p>
                      </div>

                      <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <CheckCircle2 size={15} />
                          Checked in
                        </div>

                        <p className="mt-1.5 text-sm font-bold text-slate-900">
                          {formatDateTime(
                            reservation.checked_in_at ??
                              getActiveSession(reservation)?.entry_time,
                          )}
                        </p>

                        <p className="mt-1 text-xs leading-5 text-slate-500">
                          Vehicle currently on site
                        </p>
                      </div>
                    </div>

                    {/* ==========================================
                          RESERVATION PERIOD
                      ========================================== */}

                    <div className="mt-3 grid gap-3 sm:grid-cols-2">
                      <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <CalendarClock size={15} />
                          Started
                        </div>

                        <p className="mt-1.5 text-sm font-bold text-slate-900">
                          {formatDateTime(reservation.reserved_from)}
                        </p>
                      </div>

                      <div className="rounded-2xl border border-slate-100 bg-slate-50/80 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <Clock3 size={15} />
                          Ends
                        </div>

                        <p className="mt-1.5 text-sm font-bold text-slate-900">
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
                          Booking Amount
                        </span>

                        <p className="mt-0.5 text-base font-semibold text-slate-900">
                          {formatAmount(
                            reservation.estimated_amount,
                            reservation.currency || "KES",
                          )}
                        </p>
                      </div>

                      <div className="text-left sm:text-right">
                        <span className="text-xs text-slate-500">
                          Parking Status
                        </span>

                        <p className="mt-0.5 text-sm font-semibold text-emerald-700">
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

                    <div className="mt-4 flex items-start gap-3 rounded-2xl border border-slate-100 bg-slate-50/80 px-4 py-3">
                      <Activity
                        size={17}
                        className="mt-0.5 shrink-0 text-blue-600"
                      />

                      <p className="text-xs leading-5 text-slate-600">
                        Your parking session is currently active. When your
                        vehicle leaves, your booking will automatically move to
                        your parking history.
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
