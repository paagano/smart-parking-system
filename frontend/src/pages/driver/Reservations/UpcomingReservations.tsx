import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowRight,
  CalendarClock,
  CalendarPlus,
  CarFront,
  CheckCircle2,
  Clock3,
  CreditCard,
  ParkingCircle,
  Pencil,
  RefreshCw,
  Save,
  Search,
  XCircle,
} from "lucide-react";

import { useAuth } from "../../../auth/AuthContext";
import {
  api,
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

export default function UpcomingReservations() {
  const { user } = useAuth();

  const [reservations, setReservations] = useState<ParkingReservation[]>([]);
  const [activeSessions, setActiveSessions] = useState<ParkingSession[]>([]);
  const [facilities, setFacilities] = useState<ParkingFacility[]>([]);
  const [zones, setZones] = useState<ParkingZone[]>([]);
  const [bays, setBays] = useState<ParkingBay[]>([]);

  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [searchTerm, setSearchTerm] = useState("");

  // ==========================================================
  // Manage Reservation Modal
  // ==========================================================

  const [selectedReservation, setSelectedReservation] =
    useState<ParkingReservation | null>(null);

  // ==========================================================
  // Update Reservation Modal
  // ==========================================================

  const [editingReservation, setEditingReservation] =
    useState<ParkingReservation | null>(null);

  const [editFacilityId, setEditFacilityId] = useState<number | "">("");
  const [editZoneId, setEditZoneId] = useState<number | "">("");
  const [editBayId, setEditBayId] = useState<number | "">("");

  const [editVehicleRegistration, setEditVehicleRegistration] = useState("");

  const [editVehicleType, setEditVehicleType] = useState("CAR");

  const [editReservedFrom, setEditReservedFrom] = useState("");
  const [editReservedUntil, setEditReservedUntil] = useState("");
  const [editNotes, setEditNotes] = useState("");

  const [savingUpdate, setSavingUpdate] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);

  // ==========================================================
  // Reservation processing
  // ==========================================================

  const [processingReservationId, setProcessingReservationId] = useState<
    number | null
  >(null);

  const [successToast, setSuccessToast] = useState<string | null>(null);

  // ==========================================================
  // Load reservations
  // ==========================================================

  useEffect(() => {
    let cancelled = false;

    const loadUpcomingReservations = async (manualRefresh = false) => {
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

        if (reservationResult.status === "fulfilled") {
          setReservations(reservationResult.value.items);
        } else {
          failures.push("reservations");
        }

        if (activeSessionResult.status === "fulfilled") {
          const sessions = activeSessionResult.value.items ?? [];

          setActiveSessions(
            sessions.filter(
              (session) =>
                session.customer_id === null ||
                session.customer_id === undefined ||
                String(session.customer_id) === String(user.id),
            ),
          );
        } else {
          failures.push("active parking sessions");
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
            "Unable to load your upcoming reservations from the SmartPark AI backend.",
          );
        } else if (failures.length > 0) {
          setError(
            `Upcoming reservations loaded, but some parking details could not be resolved: ${failures.join(
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
            : "Unable to load upcoming reservations from the SmartPark AI backend.",
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
          setIsRefreshing(false);
        }
      }
    };

    void loadUpcomingReservations();

    // Keep this page responsive when reservation status changes elsewhere.
    const refreshTimer = window.setInterval(() => {
      void loadUpcomingReservations(true);
    }, 10000);

    return () => {
      cancelled = true;
      window.clearInterval(refreshTimer);
    };
  }, [user]);

  // ==========================================================
  // Lookup maps
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

  const getActiveSession = (reservation: ParkingReservation) => {
    const reservationRegistration = String(
      reservation.vehicle_registration ?? "",
    )
      .trim()
      .toUpperCase();

    return (
      activeSessions.find((session) => {
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

  // ==========================================================
  // Reservation status
  // ==========================================================

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

    if (status.includes("expire")) {
      return {
        label: "Expired",
        className: "bg-amber-50 text-amber-700 ring-1 ring-amber-200",
      };
    }

    if (status.includes("pending")) {
      return {
        label: "Pending",
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

  // ==========================================================
  // Upcoming reservations
  // ==========================================================

  const now = Date.now();

  const upcomingReservations = useMemo(() => {
    return reservations
      .filter((reservation) => {
        const status = String(reservation.status ?? "").toLowerCase();

        /*
         * Upcoming reservations must still be valid and must not already
         * be cancelled, completed, expired, active, or checked in.
         */
        if (
          status !== "confirmed" ||
          reservation.cancelled_at ||
          reservation.completed_at ||
          reservation.checked_in_at ||
          getActiveSession(reservation)
        ) {
          return false;
        }

        const start = new Date(reservation.reserved_from).getTime();
        const end = new Date(reservation.reserved_until).getTime();

        /*
         * Keep the reservation visible until its reservation period ends.
         */
        return (
          Number.isFinite(start) &&
          Number.isFinite(end) &&
          end >= start &&
          end >= now
        );
      })
      .sort(
        (a, b) =>
          new Date(a.reserved_from).getTime() -
          new Date(b.reserved_from).getTime(),
      );
  }, [reservations, activeSessions, now]);

  // ==========================================================
  // Search
  // ==========================================================

  const visibleReservations = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();

    if (!query) return upcomingReservations;

    const tokens = query
      .split(/\s+/)
      .map((token) => token.trim())
      .filter(Boolean);

    return upcomingReservations.filter((reservation) => {
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
        formatDateTime(reservation.reserved_from),
        formatDateTime(reservation.reserved_until),
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      return tokens.every((token) => searchableText.includes(token));
    });
  }, [upcomingReservations, searchTerm, bayMap, zoneMap, facilityMap]);

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
          : "Unable to refresh upcoming reservations.",
      );
    } finally {
      setIsRefreshing(false);
    }
  };

  // ==========================================================
  // Success toast
  // ==========================================================

  useEffect(() => {
    if (!successToast) return;

    const timeoutId = window.setTimeout(() => {
      setSuccessToast(null);
    }, 3500);

    return () => window.clearTimeout(timeoutId);
  }, [successToast]);

  // ==========================================================
  // Manage Reservation
  // ==========================================================

  const openManageModal = (reservation: ParkingReservation) => {
    setSelectedReservation(reservation);
    setError(null);
  };

  const closeManageModal = () => {
    if (processingReservationId !== null) return;

    setSelectedReservation(null);
  };

  // ==========================================================
  // Convert ISO datetime to datetime-local value
  // ==========================================================

  const toLocalDateTimeInput = (value: string | null | undefined): string => {
    if (!value) return "";

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) return "";

    const pad = (part: number) => String(part).padStart(2, "0");

    return `${date.getFullYear()}-${pad(
      date.getMonth() + 1,
    )}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(
      date.getMinutes(),
    )}`;
  };

  // ==========================================================
  // Open Update Modal
  // ==========================================================

  const handleUpdate = (reservation: ParkingReservation) => {
    const bay = getBay(reservation);
    const zone = getZone(reservation);
    const facility = getFacility(reservation);

    setEditingReservation(reservation);

    setEditFacilityId(facility?.id ?? "");
    setEditZoneId(zone?.id ?? bay?.zone_id ?? "");
    setEditBayId(reservation.parking_bay_id);

    setEditVehicleRegistration(reservation.vehicle_registration ?? "");

    setEditVehicleType(reservation.vehicle_type ?? "CAR");

    setEditReservedFrom(toLocalDateTimeInput(reservation.reserved_from));

    setEditReservedUntil(toLocalDateTimeInput(reservation.reserved_until));

    setEditNotes(reservation.notes ?? "");

    setEditError(null);
    setError(null);

    /*
     * Close the details modal while editing.
     */
    setSelectedReservation(null);
  };

  // ==========================================================
  // Close Update Modal
  // ==========================================================

  const closeUpdateModal = () => {
    if (savingUpdate) return;

    setEditingReservation(null);
    setEditError(null);
  };

  // ==========================================================
  // Save Updated Reservation
  // ==========================================================

  const handleSaveUpdate = async () => {
    if (!editingReservation) return;

    if (editBayId === "") {
      setEditError("Please select a parking bay.");
      return;
    }

    if (!editReservedFrom || !editReservedUntil) {
      setEditError("Please select both reservation start and end times.");
      return;
    }

    const from = new Date(editReservedFrom);
    const until = new Date(editReservedUntil);

    if (!Number.isFinite(from.getTime()) || !Number.isFinite(until.getTime())) {
      setEditError("Please provide valid reservation times.");
      return;
    }

    if (until <= from) {
      setEditError("Reservation end time must be later than the start time.");
      return;
    }

    if (from <= new Date()) {
      setEditError("Reservation start time must be in the future.");
      return;
    }

    if (!editVehicleRegistration.trim()) {
      setEditError("Please provide the vehicle registration number.");
      return;
    }

    setSavingUpdate(true);
    setEditError(null);

    try {
      const response = await api.put<ParkingReservation>(
        `/parking-reservations/${editingReservation.id}`,
        {
          parking_bay_id: Number(editBayId),
          vehicle_id: editingReservation.vehicle_id,
          vehicle_registration: editVehicleRegistration.trim().toUpperCase(),
          vehicle_type: editVehicleType,
          reserved_from: from.toISOString(),
          reserved_until: until.toISOString(),
          notes: editNotes.trim() || null,
        },
      );

      setReservations((current) =>
        current.map((item) =>
          item.id === editingReservation.id ? response.data : item,
        ),
      );

      setLastUpdated(new Date());

      setSuccessToast(
        `Reservation ${editingReservation.reservation_number} updated successfully.`,
      );

      /*
       * Close update modal and immediately show the updated
       * reservation in the Manage Reservation modal.
       */
      setEditingReservation(null);
      setEditError(null);
    } catch (err: any) {
      console.error(
        "[SmartPark Upcoming Reservations] Failed to update reservation:",
        err,
      );

      const detail = err?.response?.data?.detail;

      setEditError(
        typeof detail === "string"
          ? detail
          : "The reservation could not be updated. Please review the selected details and try again.",
      );
    } finally {
      setSavingUpdate(false);
    }
  };

  // ==========================================================
  // Cancel Reservation
  // ==========================================================

  const handleCancel = async (reservation: ParkingReservation) => {
    if (
      !window.confirm(`Cancel reservation ${reservation.reservation_number}?`)
    ) {
      return;
    }

    setProcessingReservationId(reservation.id);
    setError(null);

    try {
      const response = await api.patch<ParkingReservation>(
        `/parking-reservations/${reservation.id}/cancel`,
      );

      setReservations((current) =>
        current.map((item) =>
          item.id === reservation.id ? response.data : item,
        ),
      );

      setLastUpdated(new Date());

      setSelectedReservation(null);

      setSuccessToast(
        `Reservation ${reservation.reservation_number} cancelled successfully.`,
      );
    } catch (err: any) {
      console.error(
        "[SmartPark Upcoming Reservations] Failed to cancel reservation:",
        err,
      );

      const detail = err?.response?.data?.detail;

      setError(
        typeof detail === "string"
          ? detail
          : "The reservation could not be cancelled.",
      );
    } finally {
      setProcessingReservationId(null);
    }
  };

  // ==========================================================
  // Render
  // ==========================================================

  return (
    <>
      {/* ======================================================
          SUCCESS TOAST
      ====================================================== */}

      {successToast && (
        <div
          className="fixed left-1/2 top-1/2 z-[100] -translate-x-1/2 -translate-y-1/2"
          role="status"
          aria-live="polite"
        >
          <div className="flex min-w-[320px] max-w-[90vw] items-center gap-3 rounded-2xl border border-emerald-200 bg-white px-5 py-4 text-sm font-bold text-emerald-800 shadow-2xl ring-1 ring-black/5">
            <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-emerald-100 text-emerald-600">
              <CheckCircle2 size={20} />
            </div>

            <div>
              <p className="font-extrabold text-emerald-900">Success</p>

              <p className="mt-0.5 font-medium text-emerald-700">
                {successToast}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================
          PAGE HEADER
      ====================================================== */}

      {/* <Page
        title="Upcoming Reservations"
        text="View your future parking reservations and their scheduled details."
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
              <CalendarClock className="text-emerald-600" size={22} />

              <h2 className="text-xl font-extrabold text-slate-900">
                My Upcoming Reservations
              </h2>
            </div>

            <p className="mt-1 text-sm text-slate-500">
              View your reservations scheduled for a future date and time.
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
            label="Upcoming"
            value={loading ? "…" : String(upcomingReservations.length)}
            note="Future bookings"
            Icon={CalendarClock}
          />

          <Metric
            label="Next Reservation"
            value={
              loading
                ? "…"
                : upcomingReservations[0]
                  ? formatDate(upcomingReservations[0].reserved_from)
                  : "None"
            }
            note={
              upcomingReservations[0]
                ? formatTime(upcomingReservations[0].reserved_from)
                : "No future booking"
            }
            Icon={Clock3}
          />

          <Metric
            label="Confirmed"
            value={
              loading
                ? "…"
                : String(
                    upcomingReservations.filter(
                      (reservation) =>
                        getStatus(reservation).label === "Confirmed",
                    ).length,
                  )
            }
            note="Ready for Check-In"
            Icon={CheckCircle2}
          />
        </div>

        {/* ====================================================
            ERROR
        ==================================================== */}

        {error && !editingReservation && (
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
            FUTURE BOOKINGS
        ==================================================== */}

        <Card
          title="My Future Bookings"
          sub={
            lastUpdated
              ? `Live data • Last updated ${formatDateTime(
                  lastUpdated.toISOString(),
                )}`
              : "Live reservation data from SmartPark AI"
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
                aria-label="Search upcoming reservations"
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
              Showing {visibleReservations.length} matching upcoming reservation
              {visibleReservations.length === 1 ? "" : "s"}.
            </p>
          )}

          {/* ==================================================
              LOADING
          ================================================== */}

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
          ) : upcomingReservations.length === 0 ? (
            /* ==================================================
               NO UPCOMING RESERVATIONS
            ================================================== */

            <div className="rounded-2xl bg-slate-50 px-6 py-12 text-center">
              <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
                <CalendarClock size={28} />
              </div>

              <h3 className="mt-4 text-lg font-extrabold text-slate-900">
                No upcoming reservations
              </h3>

              <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
                You currently have no future parking reservations. Create a
                reservation when you are ready to book a parking space.
              </p>

              <a
                href="/reservations/create"
                className="mt-5 inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-3 text-sm font-extrabold text-slate-950 transition hover:bg-emerald-400"
              >
                Create Reservation
                <ArrowRight size={16} />
              </a>
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
            /* ==================================================
               RESERVATION LIST
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
                    className="rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-slate-300 hover:shadow-sm"
                  >
                    {/* ==================================================
                        HEADER
                    ================================================== */}

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

                    {/* ==================================================
                        RESERVATION DETAILS
                    ================================================== */}

                    <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      {/* Date */}

                      <div className="rounded-xl bg-slate-50 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <CalendarPlus size={15} />
                          Date
                        </div>

                        <p className="mt-2 text-sm font-extrabold text-slate-900">
                          {formatDate(reservation.reserved_from)}
                        </p>
                      </div>

                      {/* Time */}

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

                      {/* Parking Bay */}

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

                      {/* Vehicle */}

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

                    {/* ==================================================
                        AMOUNT / RESERVED UNTIL
                    ================================================== */}

                    <div className="mt-4 flex flex-col gap-3 border-t border-slate-100 pt-4 sm:flex-row sm:items-center sm:justify-between">
                      <div>
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

                      <div className="text-left sm:text-right">
                        <span className="text-xs text-slate-500">
                          Reserved until
                        </span>

                        <p className="mt-0.5 text-sm font-bold text-slate-700">
                          {formatDateTime(reservation.reserved_until)}
                        </p>
                      </div>
                    </div>

                    {/* ==================================================
                        NOTES
                    ================================================== */}

                    {(reservation.confirmed_at || reservation.notes) && (
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

                          {reservation.notes && (
                            <span>
                              Notes:{" "}
                              <b className="text-slate-700">
                                {reservation.notes}
                              </b>
                            </span>
                          )}
                        </div>
                      </div>
                    )}

                    {/* ==================================================
                        ACTIONS
                    ================================================== */}

                    <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
                      <button
                        type="button"
                        onClick={() => openManageModal(reservation)}
                        className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
                      >
                        <ParkingCircle size={15} />
                        Manage Reservation
                      </button>

                      {String(reservation.status ?? "").toUpperCase() ===
                        "CREATED" && (
                        <div className="inline-flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm font-bold text-amber-700">
                          <CreditCard size={15} />
                          Payment required
                        </div>
                      )}

                      {status.label === "Confirmed" && (
                        <div className="inline-flex items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm font-bold text-emerald-700">
                          <CheckCircle2 size={15} />
                          Ready for Check-In
                        </div>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      {/* ========================================================
          MANAGE RESERVATION MODAL
      ======================================================== */}

      {selectedReservation && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="manage-reservation-title"
        >
          <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white shadow-2xl">
            {/* ==================================================
                MODAL HEADER
            ================================================== */}

            <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-slate-100 bg-white px-6 py-5">
              <div>
                <p className="text-xs font-extrabold uppercase tracking-wider text-emerald-600">
                  Reservation Management
                </p>

                <h2
                  id="manage-reservation-title"
                  className="mt-1 text-xl font-extrabold text-slate-900"
                >
                  Reservation Details
                </h2>

                <p className="mt-1 text-sm text-slate-500">
                  Reservation{" "}
                  <span className="font-bold text-slate-700">
                    {selectedReservation.reservation_number}
                  </span>
                </p>
              </div>

              <button
                type="button"
                onClick={closeManageModal}
                disabled={processingReservationId === selectedReservation.id}
                className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-slate-200 text-slate-500 transition hover:bg-slate-50 disabled:opacity-50"
                aria-label="Close reservation details"
              >
                <XCircle size={18} />
              </button>
            </div>

            {/* ==================================================
                MODAL BODY
            ================================================== */}

            <div className="space-y-5 p-6">
              {error && (
                <div
                  className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
                  role="alert"
                >
                  <AlertCircle
                    size={18}
                    className="mt-0.5 shrink-0 text-rose-600"
                  />

                  <div>
                    <p className="font-extrabold text-rose-900">
                      Unable to complete action
                    </p>

                    <p className="mt-1">{error}</p>
                  </div>
                </div>
              )}

              {/* ==================================================
                  STATUS
              ================================================== */}

              <div className="flex items-center justify-between gap-4 rounded-2xl bg-slate-50 p-5">
                <div>
                  <p className="text-xs font-semibold text-slate-500">
                    Reservation Status
                  </p>

                  <p className="mt-1 text-lg font-extrabold text-slate-900">
                    {getStatus(selectedReservation).label}
                  </p>
                </div>

                <span
                  className={`inline-flex items-center rounded-full px-3 py-1.5 text-xs font-extrabold ${
                    getStatus(selectedReservation).className
                  }`}
                >
                  {getStatus(selectedReservation).label}
                </span>
              </div>

              {/* ==================================================
                  FACILITY / LOCATION
              ================================================== */}

              <div>
                <h3 className="mb-3 text-sm font-extrabold text-slate-900">
                  Parking Location
                </h3>

                <div className="grid gap-3 sm:grid-cols-3">
                  <div className="rounded-xl bg-slate-50 p-4">
                    <p className="text-xs font-semibold text-slate-500">
                      Facility
                    </p>

                    <p className="mt-1 text-sm font-extrabold text-slate-900">
                      {getFacility(selectedReservation)?.name ??
                        "Parking Facility"}
                    </p>
                  </div>

                  <div className="rounded-xl bg-slate-50 p-4">
                    <p className="text-xs font-semibold text-slate-500">
                      Zone / Level
                    </p>

                    <p className="mt-1 text-sm font-extrabold text-slate-900">
                      {getZone(selectedReservation)?.name ?? "—"}
                    </p>
                  </div>

                  <div className="rounded-xl bg-slate-50 p-4">
                    <p className="text-xs font-semibold text-slate-500">
                      Parking Bay
                    </p>

                    <p className="mt-1 text-sm font-extrabold text-slate-900">
                      {getBay(selectedReservation)?.bay_number ??
                        getBay(selectedReservation)?.code ??
                        `Bay #${selectedReservation.parking_bay_id}`}
                    </p>
                  </div>
                </div>
              </div>

              {/* ==================================================
                  DATE / TIME
              ================================================== */}

              <div>
                <h3 className="mb-3 text-sm font-extrabold text-slate-900">
                  Booking Schedule
                </h3>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl bg-slate-50 p-4">
                    <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                      <CalendarPlus size={15} />
                      Start
                    </div>

                    <p className="mt-2 text-sm font-extrabold text-slate-900">
                      {formatDateTime(selectedReservation.reserved_from)}
                    </p>
                  </div>

                  <div className="rounded-xl bg-slate-50 p-4">
                    <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                      <Clock3 size={15} />
                      End
                    </div>

                    <p className="mt-2 text-sm font-extrabold text-slate-900">
                      {formatDateTime(selectedReservation.reserved_until)}
                    </p>
                  </div>
                </div>
              </div>

              {/* ==================================================
                  VEHICLE
              ================================================== */}

              <div>
                <h3 className="mb-3 text-sm font-extrabold text-slate-900">
                  Vehicle
                </h3>

                <div className="grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl bg-slate-50 p-4">
                    <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                      <CarFront size={15} />
                      Registration
                    </div>

                    <p className="mt-2 text-sm font-extrabold text-slate-900">
                      {selectedReservation.vehicle_registration ||
                        "Not specified"}
                    </p>
                  </div>

                  <div className="rounded-xl bg-slate-50 p-4">
                    <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                      <CarFront size={15} />
                      Vehicle Type
                    </div>

                    <p className="mt-2 text-sm font-extrabold text-slate-900">
                      {selectedReservation.vehicle_type || "Vehicle"}
                    </p>
                  </div>
                </div>
              </div>

              {/* ==================================================
                  PAYMENT / NOTES
              ================================================== */}

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs font-semibold text-slate-500">
                    Estimated Amount
                  </p>

                  <p className="mt-1 text-base font-extrabold text-slate-900">
                    {formatAmount(
                      selectedReservation.estimated_amount,
                      selectedReservation.currency || "KES",
                    )}
                  </p>
                </div>

                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs font-semibold text-slate-500">
                    Reserved Until
                  </p>

                  <p className="mt-1 text-sm font-extrabold text-slate-900">
                    {formatDateTime(selectedReservation.reserved_until)}
                  </p>
                </div>
              </div>

              {selectedReservation.notes && (
                <div className="rounded-xl border border-slate-100 bg-slate-50 p-4">
                  <p className="text-xs font-semibold text-slate-500">Notes</p>

                  <p className="mt-1 text-sm font-medium text-slate-700">
                    {selectedReservation.notes}
                  </p>
                </div>
              )}

              {/* ==================================================
                  ACTIONS
              ================================================== */}

              <div className="flex flex-col gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={closeManageModal}
                  disabled={processingReservationId === selectedReservation.id}
                  className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                >
                  Close
                </button>

                <button
                  type="button"
                  onClick={() => handleCancel(selectedReservation)}
                  disabled={processingReservationId === selectedReservation.id}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-rose-200 bg-white px-5 py-2.5 text-sm font-extrabold text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <XCircle size={16} />

                  {processingReservationId === selectedReservation.id
                    ? "Cancelling..."
                    : "Cancel Reservation"}
                </button>

                <button
                  type="button"
                  onClick={() => handleUpdate(selectedReservation)}
                  disabled={processingReservationId === selectedReservation.id}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-extrabold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Pencil size={16} />
                  Update Reservation
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ========================================================
          UPDATE RESERVATION MODAL
      ======================================================== */}

      {editingReservation && (
        <div
          className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="update-reservation-title"
        >
          <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-3xl bg-white shadow-2xl">
            {/* ==================================================
                HEADER
            ================================================== */}

            <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-slate-100 bg-white px-6 py-5">
              <div>
                <h2
                  id="update-reservation-title"
                  className="text-xl font-extrabold text-slate-900"
                >
                  Update Reservation
                </h2>

                <p className="mt-1 text-sm text-slate-500">
                  Reservation{" "}
                  <span className="font-bold text-slate-700">
                    {editingReservation.reservation_number}
                  </span>
                </p>
              </div>

              <button
                type="button"
                onClick={closeUpdateModal}
                disabled={savingUpdate}
                className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 text-slate-500 transition hover:bg-slate-50 disabled:opacity-50"
                aria-label="Close update reservation dialog"
              >
                <XCircle size={18} />
              </button>
            </div>

            {/* ==================================================
                BODY
            ================================================== */}

            <div className="space-y-5 p-6">
              {editError && (
                <div
                  className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800"
                  role="alert"
                  aria-live="assertive"
                >
                  <AlertCircle
                    size={18}
                    className="mt-0.5 shrink-0 text-rose-600"
                  />

                  <div className="min-w-0">
                    <p className="font-extrabold text-rose-900">
                      Unable to update reservation
                    </p>

                    <p className="mt-1 leading-5">{editError}</p>
                  </div>
                </div>
              )}

              {/* ==================================================
                  LOCATION
              ================================================== */}

              <div className="grid gap-4 sm:grid-cols-2">
                <label className="text-sm font-bold text-slate-700">
                  Facility
                  <select
                    value={editFacilityId}
                    onChange={(event) => {
                      const value = event.target.value
                        ? Number(event.target.value)
                        : "";

                      setEditFacilityId(value);
                      setEditZoneId("");
                      setEditBayId("");
                    }}
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                  >
                    <option value="">Select facility</option>

                    {facilities
                      .filter((facility) => facility.is_active !== false)
                      .map((facility) => (
                        <option key={facility.id} value={facility.id}>
                          {facility.name}
                        </option>
                      ))}
                  </select>
                </label>

                <label className="text-sm font-bold text-slate-700">
                  Zone / Level
                  <select
                    value={editZoneId}
                    onChange={(event) => {
                      const value = event.target.value
                        ? Number(event.target.value)
                        : "";

                      setEditZoneId(value);
                      setEditBayId("");
                    }}
                    disabled={editFacilityId === ""}
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                  >
                    <option value="">Select zone</option>

                    {zones
                      .filter(
                        (zone) =>
                          zone.facility_id === editFacilityId &&
                          zone.is_active !== false,
                      )
                      .map((zone) => (
                        <option key={zone.id} value={zone.id}>
                          {zone.name}
                        </option>
                      ))}
                  </select>
                </label>

                <label className="text-sm font-bold text-slate-700">
                  Parking Bay
                  <select
                    value={editBayId}
                    onChange={(event) =>
                      setEditBayId(
                        event.target.value ? Number(event.target.value) : "",
                      )
                    }
                    disabled={editZoneId === ""}
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                  >
                    <option value="">Select bay</option>

                    {bays
                      .filter(
                        (bay) =>
                          bay.zone_id === editZoneId &&
                          bay.is_active !== false &&
                          bay.is_reservable !== false,
                      )
                      .map((bay) => (
                        <option key={bay.id} value={bay.id}>
                          {bay.bay_number || bay.code}
                        </option>
                      ))}
                  </select>
                </label>

                <label className="text-sm font-bold text-slate-700">
                  Vehicle Type
                  <select
                    value={editVehicleType}
                    onChange={(event) => setEditVehicleType(event.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-medium outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                  >
                    {["CAR", "SUV", "TRUCK", "MOTORCYCLE", "BUS", "ANY"].map(
                      (type) => (
                        <option key={type} value={type}>
                          {type.replace(/_/g, " ")}
                        </option>
                      ),
                    )}
                  </select>
                </label>

                {/* ==================================================
                    VEHICLE REGISTRATION
                ================================================== */}

                <label className="text-sm font-bold text-slate-700 sm:col-span-2">
                  Vehicle Registration
                  <input
                    value={editVehicleRegistration}
                    onChange={(event) =>
                      setEditVehicleRegistration(
                        event.target.value.toUpperCase(),
                      )
                    }
                    className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-medium uppercase outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                    placeholder="KDA 123A"
                  />
                </label>

                {/* ==================================================
                    START
                ================================================== */}

                <label className="text-sm font-bold text-slate-700">
                  Start Time
                  <input
                    type="datetime-local"
                    value={editReservedFrom}
                    onChange={(event) =>
                      setEditReservedFrom(event.target.value)
                    }
                    className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-medium outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                  />
                </label>

                {/* ==================================================
                    END
                ================================================== */}

                <label className="text-sm font-bold text-slate-700">
                  End Time
                  <input
                    type="datetime-local"
                    min={editReservedFrom || undefined}
                    value={editReservedUntil}
                    onChange={(event) =>
                      setEditReservedUntil(event.target.value)
                    }
                    className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-medium outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                  />
                </label>

                {/* ==================================================
                    NOTES
                ================================================== */}

                <label className="text-sm font-bold text-slate-700 sm:col-span-2">
                  Notes
                  <textarea
                    value={editNotes}
                    onChange={(event) => setEditNotes(event.target.value)}
                    rows={3}
                    className="mt-2 w-full resize-none rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-medium outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                    placeholder="Optional reservation notes"
                  />
                </label>
              </div>

              {/* ==================================================
                  ACTIONS
              ================================================== */}

              <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={closeUpdateModal}
                  disabled={savingUpdate}
                  className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                >
                  Close
                </button>

                <button
                  type="button"
                  onClick={() => void handleSaveUpdate()}
                  disabled={savingUpdate}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-extrabold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {savingUpdate ? (
                    <RefreshCw size={16} className="animate-spin" />
                  ) : (
                    <Save size={16} />
                  )}

                  {savingUpdate ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
