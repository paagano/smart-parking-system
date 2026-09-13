import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowDownToLine,
  ArrowUpFromLine,
  Banknote,
  CarFront,
  CheckCircle2,
  ChevronDown,
  Clock3,
  LogIn,
  LogOut,
  ParkingCircle,
  RefreshCw,
  Search,
  ShieldCheck,
  Smartphone,
  Loader2,
  Send,
} from "lucide-react";

import { useAuth } from "../../../auth/AuthContext";
import { api } from "../../../api";
import {
  getApiErrorMessage,
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
import { Card } from "../../../components/common/Page";

// ==========================================================
// Types / constants
// ==========================================================

type Operation = "ENTRY" | "EXIT";
type EntryMode = "DRIVE_IN" | "RESERVATION";

const VEHICLE_TYPES = [
  { value: "CAR", label: "Car" },
  { value: "SUV", label: "SUV" },
  { value: "TRUCK", label: "Truck" },
  { value: "MOTORCYCLE", label: "Motorcycle" },
  { value: "BUS", label: "Bus" },
];

const BILLING_TYPES = [
  { value: "HOURLY", label: "Hourly" },
  { value: "DAILY", label: "Daily" },
  { value: "FLAT", label: "Flat" },
];

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";

  return new Intl.DateTimeFormat("en-KE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function formatMoney(value: number | string | null | undefined): string {
  const amount = Number(value ?? 0);

  if (!Number.isFinite(amount)) return "KES 0.00";

  return new Intl.NumberFormat("en-KE", {
    style: "currency",
    currency: "KES",
    minimumFractionDigits: 2,
  }).format(amount);
}

function normalizeRegistration(value: string): string {
  return value.trim().toUpperCase();
}

function isReservationCurrentlyRelevant(
  reservation: ParkingReservation,
): boolean {
  /*
   * Reservation API responses intentionally expose the reservation lifecycle
   * status, but the current ParkingReservationResponse schema does not expose
   * the separate payment_status field. A successfully paid reservation is
   * promoted to CONFIRMED by the existing payment workflow.
   *
   * Therefore the UI must use CONFIRMED as the searchable operator state.
   * The backend remains authoritative and performs the final confirmation and
   * payment validation when the operator checks the reservation in.
   */
  return String(reservation.status).toUpperCase() === "CONFIRMED";
}

// ==========================================================
// Component
// ==========================================================

export default function ManualEntryExit() {
  const { user } = useAuth();

  const [operation, setOperation] = useState<Operation>("ENTRY");
  const [entryMode, setEntryMode] = useState<EntryMode>("DRIVE_IN");

  const [facility, setFacility] = useState<ParkingFacility | null>(null);
  const [zones, setZones] = useState<ParkingZone[]>([]);
  const [bays, setBays] = useState<ParkingBay[]>([]);
  const [activeSessions, setActiveSessions] = useState<ParkingSession[]>([]);

  const [reservations, setReservations] = useState<ParkingReservation[]>([]);
  const [reservationSearch, setReservationSearch] = useState("");
  const [selectedReservation, setSelectedReservation] =
    useState<ParkingReservation | null>(null);
  const [reservationResults, setReservationResults] = useState<
    ParkingReservation[]
  >([]);

  const [registration, setRegistration] = useState("");
  const [vehicleType, setVehicleType] = useState("CAR");
  const [billingType, setBillingType] = useState("HOURLY");
  const [selectedBayId, setSelectedBayId] = useState("");
  const [notes, setNotes] = useState("");

  const [exitSession, setExitSession] = useState<ParkingSession | null>(null);
  const [quote, setQuote] = useState<{
    total_amount: number | string;
    duration_minutes: number;
    billable_minutes: number;
    grace_period_applied: boolean;
    tariff_name: string;
  } | null>(null);

  type MpesaTarget = "REGISTERED" | "OTHER";
  type ExitPaymentMethod = "MPESA" | "CASH";

  const [exitPaymentMethod, setExitPaymentMethod] =
    useState<ExitPaymentMethod>("MPESA");
  const [mpesaTarget, setMpesaTarget] = useState<MpesaTarget>("OTHER");
  const [registeredDriver, setRegisteredDriver] = useState<{
    available: boolean;
    name: string | null;
    mobileMasked: string | null;
  } | null>(null);
  const [alternativeMpesaNumber, setAlternativeMpesaNumber] = useState("");
  const [stkPayment, setStkPayment] = useState<{
    payment_id: number;
    transaction_number: string;
    amount: number | string;
    status: string;
    phone_number: string;
    checkout_request_id?: string | null;
    message: string;
  } | null>(null);
  const [stkInitiating, setStkInitiating] = useState(false);
  const [stkPolling, setStkPolling] = useState(false);
  const [cashProcessing, setCashProcessing] = useState(false);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [searching, setSearching] = useState(false);
  const [quoting, setQuoting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [checkInToast, setCheckInToast] = useState<{
    title: string;
    message: string;
  } | null>(null);

  // ========================================================
  // Facility data
  // ========================================================

  const loadFacilityData = useCallback(
    async (manualRefresh = false) => {
      if (!user?.facility_id) {
        setError(
          "Your operator account is not assigned to a parking facility.",
        );
        setLoading(false);
        return;
      }

      setError(null);
      setSuccess(null);

      if (manualRefresh) setRefreshing(true);
      else setLoading(true);

      try {
        const [
          facilityResult,
          zonesResult,
          baysResult,
          sessionsResult,
          reservationsResult,
        ] = await Promise.all([
          parkingFacilitiesApi.get(user.facility_id),
          parkingZonesApi.byFacility(user.facility_id, 0, 500),
          parkingBaysApi.list(0, 500),
          parkingSessionsApi.active(),
          parkingReservationsApi.list(),
        ]);

        const zoneIds = new Set(
          zonesResult.items
            .filter((zone) => zone.facility_id === user.facility_id)
            .map((zone) => zone.id),
        );

        setFacility(facilityResult);
        setZones(
          zonesResult.items.filter(
            (zone) => zone.facility_id === user.facility_id,
          ),
        );
        setBays(baysResult.items.filter((bay) => zoneIds.has(bay.zone_id)));
        setActiveSessions(sessionsResult.items);

        const relevantReservations = reservationsResult.items.filter(
          isReservationCurrentlyRelevant,
        );
        setReservations(relevantReservations);
        setReservationResults(relevantReservations);

        if (manualRefresh) {
          setSelectedReservation((current) => {
            if (!current) return null;
            return (
              relevantReservations.find((item) => item.id === current.id) ??
              null
            );
          });
        }
      } catch (loadError) {
        setError(getApiErrorMessage(loadError));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [user?.facility_id],
  );

  useEffect(() => {
    void loadFacilityData();
  }, [loadFacilityData]);

  useEffect(() => {
    if (!checkInToast) return;

    const timeoutId = window.setTimeout(() => {
      setCheckInToast(null);
    }, 6000);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [checkInToast]);

  // ========================================================
  // Derived bay state
  // ========================================================

  const occupiedBayIds = useMemo(
    () => new Set(activeSessions.map((session) => session.parking_bay_id)),
    [activeSessions],
  );

  const reservedBayIds = useMemo(() => {
    const now = Date.now();

    return new Set(
      reservations
        .filter((reservation) => {
          const from = new Date(reservation.reserved_from).getTime();
          const until = new Date(reservation.reserved_until).getTime();
          return from <= now && now < until;
        })
        .map((reservation) => reservation.parking_bay_id),
    );
  }, [reservations]);

  const availableBays = useMemo(
    () =>
      bays.filter(
        (bay) =>
          bay.is_active &&
          !occupiedBayIds.has(bay.id) &&
          !reservedBayIds.has(bay.id),
      ),
    [bays, occupiedBayIds, reservedBayIds],
  );

  const zoneNameById = useMemo(
    () => new Map(zones.map((zone) => [zone.id, zone.name])),
    [zones],
  );

  const availableBaysByZone = useMemo(() => {
    const grouped = new Map<number, ParkingBay[]>();

    for (const bay of availableBays) {
      const current = grouped.get(bay.zone_id) ?? [];
      current.push(bay);
      grouped.set(bay.zone_id, current);
    }

    return grouped;
  }, [availableBays]);

  const [expandedZoneIds, setExpandedZoneIds] = useState<Set<number>>(
    () => new Set(),
  );

  useEffect(() => {
    setExpandedZoneIds((current) => {
      const next = new Set<number>();

      for (const zone of zones) {
        if (current.has(zone.id)) {
          next.add(zone.id);
        }
      }

      return next;
    });
  }, [zones]);

  // ========================================================
  // Reservation search
  // ========================================================

  const searchReservations = async () => {
    const term = reservationSearch.trim();

    if (!term) {
      setSelectedReservation(null);
      setReservationResults(reservations);
      setError(null);
      return;
    }

    setSearching(true);
    setError(null);
    setSuccess(null);
    setSelectedReservation(null);

    /*
     * Surgical reliability fix:
     *
     * The operator page already loads the facility-scoped reservations into
     * `reservations`. Search those records first. This avoids making the
     * manual check-in flow depend on the optional API helper being present in
     * the frontend API barrel and also makes exact reservation-number lookup
     * instantaneous.
     *
     * If the reservation is not in the current in-memory list, fall back to
     * the backend search endpoint directly. Axios will send `search_term`
     * using the exact FastAPI query parameter expected by the backend.
     */
    const normalizedTerm = term.toUpperCase().replace(/\s+/g, "");

    const localMatches = reservations.filter((reservation) => {
      const reservationNumber = String(reservation.reservation_number ?? "")
        .toUpperCase()
        .replace(/\s+/g, "");

      const vehicleRegistration = String(reservation.vehicle_registration ?? "")
        .toUpperCase()
        .replace(/\s+/g, "");

      return (
        reservationNumber.includes(normalizedTerm) ||
        vehicleRegistration.includes(normalizedTerm)
      );
    });

    if (localMatches.length > 0) {
      setReservationResults(localMatches);

      if (localMatches.length === 1) {
        setSelectedReservation(localMatches[0]);
      }

      setSearching(false);
      return;
    }

    try {
      const response = await api.get<{
        items: ParkingReservation[];
        total: number;
      }>("/parking-reservations/search", {
        params: {
          search_term: term,
        },
      });

      const filtered = (response.data.items ?? []).filter(
        isReservationCurrentlyRelevant,
      );

      setReservationResults(filtered);

      if (filtered.length === 1) {
        setSelectedReservation(filtered[0]);
      } else if (filtered.length === 0) {
        setError(
          `No confirmed and paid reservation was found for "${term}" at your assigned facility.`,
        );
      }
    } catch (searchError) {
      setReservationResults([]);
      setError(getApiErrorMessage(searchError));
    } finally {
      setSearching(false);
    }
  };

  // ========================================================
  // Entry
  // ========================================================

  const handleDriveIn = async () => {
    const normalizedRegistration = normalizeRegistration(registration);

    if (!normalizedRegistration) {
      setError("Vehicle registration is required.");
      return;
    }

    if (!selectedBayId) {
      setError("Please select an available parking bay.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const session = await parkingSessionsApi.checkIn({
        parking_bay_id: Number(selectedBayId),
        customer_id: null,
        vehicle_id: null,
        vehicle_registration: normalizedRegistration,
        vehicle_type: vehicleType,
        billing_type: billingType,
        session_source: "ATTENDANT",
        entry_method: "MANUAL",
        notes: notes.trim() || null,
      });

      setCheckInToast({
        title: "Vehicle checked in successfully",
        message: `${session.vehicle_registration} has been admitted and parking session ${session.session_number} has been started.`,
      });
      setSuccess(null);
      setRegistration("");
      setSelectedBayId("");
      setNotes("");
      await loadFacilityData(true);
    } catch (submitError) {
      setError(getApiErrorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  };

  const handleReservationCheckIn = async () => {
    if (!selectedReservation) {
      setError("Search for and select a reservation first.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const reservation = await parkingReservationsApi.checkIn(
        selectedReservation.id,
        "MANUAL",
      );

      const sessionResult = await parkingSessionsApi.search(
        normalizeRegistration(reservation.vehicle_registration),
      );

      const startedSession =
        sessionResult.items.find(
          (session) =>
            String(session.status).toUpperCase() === "ACTIVE" &&
            !session.exit_time,
        ) ?? null;

      setCheckInToast({
        title: "Reservation checked in successfully",
        message: startedSession
          ? `${reservation.vehicle_registration} has been admitted and parking session ${startedSession.session_number} has been started.`
          : `${reservation.vehicle_registration} has been admitted and a new parking session has been started.`,
      });
      setSuccess(null);
      setSelectedReservation(null);
      setReservationSearch("");
      await loadFacilityData(true);
    } catch (submitError) {
      setError(getApiErrorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  };

  // ========================================================
  // Exit search / quote / checkout
  // ========================================================

  const findExitSession = async () => {
    const normalizedRegistration = normalizeRegistration(registration);

    if (!normalizedRegistration) {
      setError(
        "Vehicle registration is required to locate the parking session.",
      );
      return;
    }

    setSearching(true);
    setError(null);
    setSuccess(null);
    setQuote(null);

    try {
      const result = await parkingSessionsApi.search(normalizedRegistration);
      const active = result.items.find(
        (session) =>
          String(session.status).toUpperCase() === "ACTIVE" &&
          !session.exit_time,
      );
      const completedAwaitingExit = result.items.find(
        (session) =>
          String(session.status).toUpperCase() === "COMPLETED" &&
          !session.exit_time,
      );

      const session = completedAwaitingExit ?? active ?? null;

      if (!session) {
        setExitSession(null);
        setError(
          "No active parking session or completed session awaiting physical exit was found for this vehicle at your facility.",
        );
        return;
      }

      setExitSession(session);
      setRegisteredDriver(null);
      setMpesaTarget("OTHER");

      try {
        const optionsResponse = await api.get<{
          parking_session_id: number;
          registered_driver_available: boolean;
          registered_driver_name?: string | null;
          registered_mobile_masked?: string | null;
        }>(`/payments/operator/session/${session.id}/payment-options`);

        const options = optionsResponse.data;
        setRegisteredDriver({
          available: options.registered_driver_available,
          name: options.registered_driver_name ?? null,
          mobileMasked: options.registered_mobile_masked ?? null,
        });

        if (options.registered_driver_available) {
          setMpesaTarget("REGISTERED");
        }
      } catch (optionsError) {
        console.error(
          "[Operator Payment Options] Registered-driver lookup failed:",
          optionsError,
        );
        setRegisteredDriver({
          available: false,
          name: null,
          mobileMasked: null,
        });
        setMpesaTarget("OTHER");
      }
    } catch (searchError) {
      setExitSession(null);
      setError(getApiErrorMessage(searchError));
    } finally {
      setSearching(false);
    }
  };

  const loadQuote = async () => {
    if (!exitSession) return;

    setQuoting(true);
    setError(null);

    try {
      const result = await parkingSessionsApi.quote(exitSession.id);
      setQuote(result);
    } catch (quoteError) {
      setError(getApiErrorMessage(quoteError));
    } finally {
      setQuoting(false);
    }
  };

  const recordOperatorCashPayment = async () => {
    if (!exitSession) {
      setError("Locate a vehicle parking session first.");
      return;
    }

    if (String(exitSession.status).toUpperCase() !== "ACTIVE") {
      setError(
        "Cash payment can only be recorded while the parking session is ACTIVE.",
      );
      return;
    }

    setCashProcessing(true);
    setError(null);
    setSuccess(null);
    setStkPayment(null);

    try {
      const response = await api.post<{
        payment_id: number;
        transaction_number: string;
        parking_session_id: number;
        amount: number | string;
        currency: string;
        status: string;
        message: string;
        duration_minutes: number;
        billable_minutes: number;
        grace_period_applied: boolean;
        tariff_name: string;
      }>("/payments/operator/session/cash", {
        parking_session_id: exitSession.id,
        notes: notes.trim() || null,
      });

      const data = response.data;

      setQuote({
        total_amount: data.amount,
        duration_minutes: data.duration_minutes,
        billable_minutes: data.billable_minutes,
        grace_period_applied: data.grace_period_applied,
        tariff_name: data.tariff_name,
      });

      setSuccess(
        `Cash payment ${data.transaction_number} of ${formatMoney(data.amount)} recorded successfully. The vehicle is now cleared for physical exit.`,
      );

      await findExitSession();
    } catch (paymentError) {
      setError(getApiErrorMessage(paymentError));
    } finally {
      setCashProcessing(false);
    }
  };

  const initiateOperatorMpesaPayment = async () => {
    if (!exitSession) {
      setError("Locate a vehicle parking session first.");
      return;
    }

    if (String(exitSession.status).toUpperCase() !== "ACTIVE") {
      setError(
        "M-Pesa STK Push can only be initiated while the parking session is ACTIVE.",
      );
      return;
    }

    if (mpesaTarget === "OTHER" && !alternativeMpesaNumber.trim()) {
      setError("Enter the alternative Safaricom mobile number.");
      return;
    }

    setStkInitiating(true);
    setError(null);
    setSuccess(null);
    setStkPayment(null);

    try {
      const response = await api.post<{
        payment_id: number;
        transaction_number: string;
        parking_session_id: number;
        amount: number | string;
        currency: string;
        status: string;
        phone_number: string;
        checkout_request_id?: string | null;
        message: string;
        duration_minutes: number;
        billable_minutes: number;
        grace_period_applied: boolean;
        tariff_name: string;
      }>("/payments/operator/session/stk-push", {
        parking_session_id: exitSession.id,
        use_registered_number: mpesaTarget === "REGISTERED",
        mobile_number:
          mpesaTarget === "OTHER" ? alternativeMpesaNumber.trim() : null,
        notes: notes.trim() || null,
      });

      const data = response.data;

      setQuote((current) => ({
        total_amount: data.amount,
        duration_minutes: data.duration_minutes,
        billable_minutes: data.billable_minutes,
        grace_period_applied: data.grace_period_applied,
        tariff_name: data.tariff_name,
      }));

      setStkPayment(data);

      if (String(data.status).toUpperCase() === "SUCCESSFUL") {
        setSuccess(
          `M-Pesa payment ${data.transaction_number} was completed successfully.`,
        );
        setStkInitiating(false);
        await findExitSession();
        return;
      }

      setSuccess(
        `STK Push sent successfully to ${data.phone_number}. Ask the driver to complete the M-Pesa prompt on their phone.`,
      );
    } catch (paymentError) {
      setError(getApiErrorMessage(paymentError));
    } finally {
      setStkInitiating(false);
    }
  };

  useEffect(() => {
    if (!stkPayment?.payment_id) {
      setStkPolling(false);
      return;
    }

    const initialStatus = String(stkPayment.status).toUpperCase();

    if (!["PENDING", "PROCESSING"].includes(initialStatus)) {
      setStkPolling(false);
      return;
    }

    let cancelled = false;
    let intervalId: number | undefined;

    const pollPayment = async () => {
      if (cancelled) return;

      try {
        const response = await api.get<{
          id: number;
          status: string;
          total_amount?: number | string | null;
          provider_transaction_id?: string | null;
          provider_status_message?: string | null;
        }>(`/payments/${stkPayment.payment_id}`);

        if (cancelled) return;

        const status = String(response.data.status ?? "PENDING").toUpperCase();

        setStkPayment((current) =>
          current
            ? {
                ...current,
                status,
                amount: response.data.total_amount ?? current.amount,
                checkout_request_id:
                  response.data.provider_transaction_id ??
                  current.checkout_request_id,
                message:
                  response.data.provider_status_message ?? current.message,
              }
            : current,
        );

        if (status === "SUCCESSFUL") {
          if (intervalId !== undefined) {
            window.clearInterval(intervalId);
          }

          setStkPolling(false);
          setSuccess(
            "M-Pesa payment received successfully. The parking session has been completed and is ready for physical checkout.",
          );

          await findExitSession();
        } else if (["FAILED", "CANCELLED"].includes(status)) {
          if (intervalId !== undefined) {
            window.clearInterval(intervalId);
          }

          setStkPolling(false);
          setError(
            "The M-Pesa payment was not completed. The parking session remains active.",
          );
        }
      } catch (pollError) {
        console.error(
          "[Operator STK Push] Payment status check failed:",
          pollError,
        );
      }
    };

    setStkPolling(true);
    void pollPayment();

    intervalId = window.setInterval(() => {
      void pollPayment();
    }, 2000);

    return () => {
      cancelled = true;
      if (intervalId !== undefined) {
        window.clearInterval(intervalId);
      }
      setStkPolling(false);
    };
  }, [stkPayment?.payment_id, stkPayment?.status]);

  const handleCheckout = async () => {
    if (!exitSession) {
      setError("Locate a vehicle parking session first.");
      return;
    }

    if (String(exitSession.status).toUpperCase() !== "COMPLETED") {
      setError(
        "This session has not been completed by the payment workflow yet. Payment must be settled before the vehicle can be physically checked out.",
      );
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const session = await parkingSessionsApi.checkOut({
        vehicle_registration: normalizeRegistration(registration),
        exit_method: "MANUAL",
        notes: notes.trim() || null,
      });

      setSuccess(
        `Vehicle ${session.vehicle_registration} checked out successfully. Physical exit recorded at ${formatDateTime(session.exit_time)}.`,
      );
      setRegistration("");
      setNotes("");
      setExitSession(null);
      setQuote(null);
      await loadFacilityData(true);
    } catch (submitError) {
      setError(getApiErrorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  };

  // ========================================================
  // Render
  // ========================================================

  const isEntry = operation === "ENTRY";
  const selectedBay = bays.find((bay) => bay.id === Number(selectedBayId));
  const exitNeedsPayment =
    exitSession && String(exitSession.status).toUpperCase() === "ACTIVE";

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs font-bold uppercase tracking-[.2em] text-emerald-600">
          SmartPark AI · Operations
        </div>
        <h1 className="mt-2 text-3xl font-black tracking-tight text-slate-950">
          Manual Entry | Exit
        </h1>
        <p className="mt-2 max-w-3xl text-slate-500">
          Manually admit or release vehicles when automated access channels such
          as QR, ANPR, RFID or sensors are unavailable.
        </p>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-emerald-100 bg-emerald-50/70 px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-white text-emerald-600 shadow-sm">
            <ShieldCheck size={19} />
          </span>
          <div>
            <p className="text-sm font-extrabold text-slate-900">
              {facility?.name ?? "Assigned parking facility"}
            </p>
            <p className="text-xs text-slate-500">
              Facility #{user?.facility_id ?? "—"} · Operator-controlled manual
              access
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={() => void loadFacilityData(true)}
          disabled={loading || refreshing}
          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2 text-xs font-bold text-slate-700 shadow-sm hover:bg-slate-50 disabled:opacity-60"
        >
          <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
          Refresh facility data
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-extrabold">Operation could not be completed</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      {success && (
        <div className="flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
          <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-extrabold">Operation successful</p>
            <p className="mt-1">{success}</p>
          </div>
        </div>
      )}

      {checkInToast && (
        <div
          role="status"
          aria-live="polite"
          className="fixed right-5 top-5 z-50 w-[min(420px,calc(100vw-2.5rem))] rounded-2xl border border-emerald-200 bg-white p-4 shadow-2xl ring-1 ring-emerald-100"
        >
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
              <CheckCircle2 size={20} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-black text-slate-900">
                {checkInToast.title}
              </p>
              <p className="mt-1 text-sm leading-5 text-slate-600">
                {checkInToast.message}
              </p>
            </div>
            <button
              type="button"
              onClick={() => setCheckInToast(null)}
              aria-label="Dismiss notification"
              className="rounded-lg p-1 text-lg leading-none text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            >
              ×
            </button>
          </div>
        </div>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <button
          type="button"
          onClick={() => {
            setOperation("ENTRY");
            setError(null);
            setSuccess(null);
            setCheckInToast(null);
            setExitSession(null);
            setQuote(null);
            setStkPayment(null);
            setExitPaymentMethod("MPESA");
            setRegisteredDriver(null);
            setMpesaTarget("OTHER");
          }}
          className={`rounded-2xl border p-5 text-left transition ${
            isEntry
              ? "border-emerald-300 bg-emerald-50 shadow-sm"
              : "border-slate-200 bg-white hover:border-slate-300"
          }`}
        >
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-white text-emerald-600 shadow-sm">
            <ArrowDownToLine size={21} />
          </span>
          <p className="mt-4 text-lg font-black text-slate-900">
            Vehicle Entry
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Start a parking session for a drive-in or reservation.
          </p>
        </button>

        <button
          type="button"
          onClick={() => {
            setOperation("EXIT");
            setError(null);
            setSuccess(null);
            setCheckInToast(null);
            setSelectedReservation(null);
            setQuote(null);
            setStkPayment(null);
            setExitPaymentMethod("MPESA");
            setRegisteredDriver(null);
            setMpesaTarget("OTHER");
          }}
          className={`rounded-2xl border p-5 text-left transition ${
            !isEntry
              ? "border-emerald-300 bg-emerald-50 shadow-sm"
              : "border-slate-200 bg-white hover:border-slate-300"
          }`}
        >
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-white text-emerald-600 shadow-sm">
            <ArrowUpFromLine size={21} />
          </span>
          <p className="mt-4 text-lg font-black text-slate-900">Vehicle Exit</p>
          <p className="mt-1 text-sm text-slate-500">
            Locate the parking session and record the vehicle's physical exit.
          </p>
        </button>
      </div>

      {isEntry ? (
        <Card
          title="Manual vehicle admission"
          sub="Choose whether this is a new drive-in or an existing reservation."
        >
          <div className="mb-6 grid gap-3 md:grid-cols-2">
            <button
              type="button"
              onClick={() => {
                setEntryMode("DRIVE_IN");
                setCheckInToast(null);
              }}
              className={`rounded-2xl border p-4 text-left ${
                entryMode === "DRIVE_IN"
                  ? "border-emerald-300 bg-emerald-50"
                  : "border-slate-200 bg-white"
              }`}
            >
              <div className="flex items-center gap-3">
                <CarFront size={19} className="text-emerald-600" />
                <span className="font-extrabold text-slate-900">
                  Drive-In (No Reservation)
                </span>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Create a new attendant-originated parking session.
              </p>
            </button>

            <button
              type="button"
              onClick={() => {
                setEntryMode("RESERVATION");
                setCheckInToast(null);
              }}
              className={`rounded-2xl border p-4 text-left ${
                entryMode === "RESERVATION"
                  ? "border-emerald-300 bg-emerald-50"
                  : "border-slate-200 bg-white"
              }`}
            >
              <div className="flex items-center gap-3">
                <ParkingCircle size={19} className="text-emerald-600" />
                <span className="font-extrabold text-slate-900">
                  Reservation
                </span>
              </div>
              <p className="mt-2 text-xs text-slate-500">
                Locate the reservation and convert it into an active parking
                session.
              </p>
            </button>
          </div>

          {entryMode === "DRIVE_IN" ? (
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="space-y-4">
                <Field label="Vehicle registration" required>
                  <input
                    value={registration}
                    onChange={(event) =>
                      setRegistration(event.target.value.toUpperCase())
                    }
                    placeholder="e.g. KDA 123A"
                    className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm font-medium text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                    autoComplete="off"
                  />
                </Field>

                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Vehicle type" required>
                    <select
                      value={vehicleType}
                      onChange={(event) => setVehicleType(event.target.value)}
                      className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm font-medium text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                    >
                      {VEHICLE_TYPES.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </Field>

                  <Field label="Billing type" required>
                    <select
                      value={billingType}
                      onChange={(event) => setBillingType(event.target.value)}
                      className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm font-medium text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                    >
                      {BILLING_TYPES.map((item) => (
                        <option key={item.value} value={item.value}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                </div>

                <Field label="Operator notes">
                  <textarea
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    rows={4}
                    placeholder="Optional reason or operational note..."
                    className="w-full resize-none rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm font-medium text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                  />
                </Field>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-extrabold text-slate-900">
                      Select parking bay
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Only active, currently unoccupied and
                      not-currently-reserved bays are shown.
                    </p>
                  </div>
                  <span className="rounded-full bg-white px-2.5 py-1 text-xs font-bold text-emerald-700">
                    {availableBays.length} available
                  </span>
                </div>

                <div className="mt-4 max-h-80 space-y-2 overflow-auto pr-1">
                  {zones.map((zone) => {
                    const zoneBays = availableBaysByZone.get(zone.id) ?? [];

                    if (zoneBays.length === 0) {
                      return null;
                    }

                    const expanded = expandedZoneIds.has(zone.id);

                    return (
                      <div
                        key={zone.id}
                        className="overflow-hidden rounded-xl border border-slate-200 bg-white"
                      >
                        <button
                          type="button"
                          onClick={() => {
                            setExpandedZoneIds((current) => {
                              const next = new Set(current);

                              if (next.has(zone.id)) {
                                next.delete(zone.id);
                              } else {
                                next.add(zone.id);
                              }

                              return next;
                            });
                          }}
                          aria-expanded={expanded}
                          className="flex w-full items-center justify-between gap-3 px-3.5 py-3 text-left transition hover:bg-slate-50"
                        >
                          <div className="min-w-0">
                            <p className="text-sm font-extrabold text-slate-900">
                              {zone.name}
                            </p>
                            <p className="mt-0.5 text-xs text-slate-500">
                              {zoneBays.length} available{" "}
                              {zoneBays.length === 1 ? "bay" : "bays"}
                            </p>
                          </div>
                          <div className="flex shrink-0 items-center gap-2">
                            {zoneBays.some(
                              (bay) => selectedBayId === String(bay.id),
                            ) && (
                              <span className="rounded-full bg-emerald-100 px-2 py-1 text-[10px] font-extrabold uppercase tracking-wide text-emerald-700">
                                Selected
                              </span>
                            )}
                            <ChevronDown
                              size={17}
                              className={`text-slate-500 transition-transform ${
                                expanded ? "rotate-180" : ""
                              }`}
                            />
                          </div>
                        </button>

                        {expanded && (
                          <div className="space-y-2 border-t border-slate-100 bg-slate-50/60 p-2">
                            {zoneBays.map((bay) => (
                              <button
                                key={bay.id}
                                type="button"
                                onClick={() => setSelectedBayId(String(bay.id))}
                                className={`w-full rounded-xl border px-3 py-3 text-left transition ${
                                  selectedBayId === String(bay.id)
                                    ? "border-emerald-400 bg-white ring-2 ring-emerald-100"
                                    : "border-slate-200 bg-white hover:border-slate-300"
                                }`}
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <div>
                                    <p className="text-sm font-extrabold text-slate-900">
                                      {bay.code || bay.bay_number}
                                    </p>
                                    <p className="mt-0.5 text-xs text-slate-500">
                                      {zone.name}
                                    </p>
                                  </div>
                                  {selectedBayId === String(bay.id) && (
                                    <CheckCircle2
                                      size={18}
                                      className="text-emerald-600"
                                    />
                                  )}
                                </div>
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}

                  {!loading && availableBays.length === 0 && (
                    <div className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500">
                      No suitable parking bays are currently available.
                    </div>
                  )}
                </div>

                {selectedBay && (
                  <div className="mt-4 rounded-xl bg-emerald-50 p-3 text-xs text-emerald-700">
                    Selected:{" "}
                    <strong>
                      {selectedBay.code || selectedBay.bay_number}
                    </strong>{" "}
                    · {zoneNameById.get(selectedBay.zone_id) ?? "Zone"}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div className="space-y-5">
              <div className="flex flex-col gap-3 sm:flex-row">
                <input
                  value={reservationSearch}
                  onChange={(event) => setReservationSearch(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void searchReservations();
                  }}
                  placeholder="Reservation number or vehicle registration"
                  className="w-full flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm font-medium text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                />
                <button
                  type="button"
                  onClick={() => void searchReservations()}
                  disabled={searching}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-extrabold text-white hover:bg-slate-800 disabled:opacity-60"
                >
                  <Search size={17} />
                  {searching ? "Searching..." : "Find Reservation"}
                </button>
              </div>

              <div className="space-y-2">
                {reservationResults.map((reservation) => (
                  <button
                    key={reservation.id}
                    type="button"
                    onClick={() => setSelectedReservation(reservation)}
                    className={`w-full rounded-2xl border p-4 text-left ${
                      selectedReservation?.id === reservation.id
                        ? "border-emerald-400 bg-emerald-50"
                        : "border-slate-200 bg-white hover:border-slate-300"
                    }`}
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="font-extrabold text-slate-900">
                          {reservation.reservation_number}
                        </p>
                        <p className="mt-1 text-sm text-slate-600">
                          {reservation.vehicle_registration}
                        </p>
                        <p className="mt-1 text-xs font-bold text-emerald-700">
                          Confirmed · Paid
                        </p>
                      </div>
                      <StatusBadge status={reservation.status} />
                    </div>
                    <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-3">
                      <span>Bay #{reservation.parking_bay_id}</span>
                      <span>
                        From {formatDateTime(reservation.reserved_from)}
                      </span>
                      <span>
                        Until {formatDateTime(reservation.reserved_until)}
                      </span>
                    </div>
                  </button>
                ))}

                {!searching && reservationResults.length === 0 && (
                  <div className="rounded-2xl border border-dashed border-slate-300 p-7 text-center text-sm text-slate-500">
                    Search by reservation number or vehicle registration to
                    locate an eligible reservation.
                  </div>
                )}
              </div>

              {selectedReservation && (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wider text-emerald-700">
                        Selected reservation
                      </p>
                      <h3 className="mt-1 text-lg font-black text-slate-900">
                        {selectedReservation.reservation_number}
                      </h3>
                      <p className="mt-1 text-sm text-slate-600">
                        {selectedReservation.vehicle_registration} · Bay #
                        {selectedReservation.parking_bay_id}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void handleReservationCheckIn()}
                      disabled={submitting}
                      className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white hover:bg-emerald-700 disabled:opacity-60"
                    >
                      <LogIn size={17} />
                      {submitting ? "Checking in..." : "Check In Reservation"}
                    </button>
                  </div>
                  <p className="mt-4 text-xs leading-5 text-emerald-800">
                    The backend validates the facility, reservation window,
                    confirmation and payment status, then creates the active
                    parking session using <strong>MANUAL</strong> as the entry
                    method.
                  </p>
                </div>
              )}
            </div>
          )}

          {entryMode === "DRIVE_IN" && (
            <div className="mt-6 flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-5">
              <p className="text-xs text-slate-500">
                This creates an active parking session and marks the selected
                bay occupied.
              </p>
              <button
                type="button"
                onClick={() => void handleDriveIn()}
                disabled={submitting || loading || availableBays.length === 0}
                className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white hover:bg-emerald-700 disabled:opacity-60"
              >
                <LogIn size={17} />
                {submitting ? "Checking in..." : "Check In Vehicle"}
              </button>
            </div>
          )}
        </Card>
      ) : (
        <Card
          title="Manual vehicle exit"
          sub="Locate the vehicle by registration, review the session and record the physical exit."
        >
          <div className="flex flex-col gap-3 sm:flex-row">
            <input
              value={registration}
              onChange={(event) =>
                setRegistration(event.target.value.toUpperCase())
              }
              onKeyDown={(event) => {
                if (event.key === "Enter") void findExitSession();
              }}
              placeholder="Vehicle registration e.g. KDA 123A"
              className="w-full flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm font-medium text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
              autoComplete="off"
            />
            <button
              type="button"
              onClick={() => void findExitSession()}
              disabled={searching}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-extrabold text-white hover:bg-slate-800 disabled:opacity-60"
            >
              <Search size={17} />
              {searching ? "Finding..." : "Find Vehicle"}
            </button>
          </div>

          {exitSession && (
            <div className="mt-6 rounded-2xl border border-slate-200 bg-slate-50 p-5">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Parking session
                  </p>
                  <h3 className="mt-1 text-2xl font-black text-slate-900">
                    {exitSession.vehicle_registration}
                  </h3>
                  <p className="mt-1 text-sm text-slate-500">
                    {exitSession.session_number}
                  </p>
                </div>
                <StatusBadge status={exitSession.status} />
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Info
                  label="Entry time"
                  value={formatDateTime(exitSession.entry_time)}
                />
                <Info label="Bay" value={`#${exitSession.parking_bay_id}`} />
                <Info
                  label="Payment"
                  value={String(exitSession.payment_status).replace(/_/g, " ")}
                />
                <Info
                  label="Recorded Amount"
                  value={formatMoney(exitSession.calculated_amount)}
                />
              </div>

              {exitNeedsPayment ? (
                <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 p-5">
                  <div className="flex items-start gap-3">
                    <Clock3
                      size={18}
                      className="mt-0.5 shrink-0 text-amber-700"
                    />
                    <div>
                      <p className="font-extrabold text-amber-900">
                        Payment required before exit
                      </p>
                      <p className="mt-1 text-sm leading-6 text-amber-800">
                        Calculate the current parking charge, then select M-Pesa
                        or Cash. For M-Pesa, the driver completes the STK prompt
                        on their own phone. For Cash, the Operator records the
                        cash received.
                      </p>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => void loadQuote()}
                    disabled={quoting}
                    className="mt-4 inline-flex items-center gap-2 rounded-xl border border-amber-300 bg-white px-4 py-2.5 text-xs font-extrabold text-amber-800 hover:bg-amber-100 disabled:opacity-60"
                  >
                    <Clock3 size={15} />
                    {quoting ? "Calculating..." : "View Current Parking Charge"}
                  </button>

                  <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-4">
                    <div className="flex items-start gap-3">
                      <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                        {exitPaymentMethod === "CASH" ? (
                          <Banknote size={18} />
                        ) : (
                          <Smartphone size={18} />
                        )}
                      </span>
                      <div>
                        <p className="font-extrabold text-slate-900">
                          Operator payment
                        </p>
                        <p className="mt-1 text-xs leading-5 text-slate-500">
                          The parking charge is calculated by the backend from
                          the current parking session. The Operator cannot edit
                          the amount.
                        </p>
                      </div>
                    </div>

                    <div className="mt-4 grid gap-3 sm:grid-cols-2">
                      <button
                        type="button"
                        onClick={() => setExitPaymentMethod("MPESA")}
                        className={`rounded-xl border p-3 text-left ${
                          exitPaymentMethod === "MPESA"
                            ? "border-emerald-400 bg-emerald-50"
                            : "border-slate-200 bg-white"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <Smartphone size={16} className="text-emerald-600" />
                          <p className="text-sm font-extrabold text-slate-900">
                            M-Pesa
                          </p>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          Send an STK Push to a registered or supplied M-Pesa
                          number.
                        </p>
                      </button>

                      <button
                        type="button"
                        onClick={() => setExitPaymentMethod("CASH")}
                        className={`rounded-xl border p-3 text-left ${
                          exitPaymentMethod === "CASH"
                            ? "border-emerald-400 bg-emerald-50"
                            : "border-slate-200 bg-white"
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <Banknote size={16} className="text-emerald-600" />
                          <p className="text-sm font-extrabold text-slate-900">
                            Cash
                          </p>
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          Record cash received by the Operator and clear the
                          session for physical exit.
                        </p>
                      </button>
                    </div>

                    {exitPaymentMethod === "MPESA" && (
                      <>
                        {registeredDriver === null ? (
                          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-500">
                            Checking whether this vehicle registration is tied
                            to a registered SmartPark driver...
                          </div>
                        ) : (
                          <div className="mt-4 grid gap-3 sm:grid-cols-2">
                            {registeredDriver.available && (
                              <button
                                type="button"
                                onClick={() => setMpesaTarget("REGISTERED")}
                                className={`rounded-xl border p-3 text-left ${
                                  mpesaTarget === "REGISTERED"
                                    ? "border-emerald-400 bg-emerald-50"
                                    : "border-slate-200 bg-white"
                                }`}
                              >
                                <p className="text-sm font-extrabold text-slate-900">
                                  Registered driver
                                </p>
                                <p className="mt-1 text-xs text-slate-500">
                                  {registeredDriver.name
                                    ? `${registeredDriver.name} · `
                                    : ""}
                                  Use the registered mobile number
                                  {registeredDriver.mobileMasked
                                    ? ` (${registeredDriver.mobileMasked})`
                                    : ""}
                                  .
                                </p>
                              </button>
                            )}

                            <button
                              type="button"
                              onClick={() => setMpesaTarget("OTHER")}
                              className={`rounded-xl border p-3 text-left ${
                                mpesaTarget === "OTHER"
                                  ? "border-emerald-400 bg-emerald-50"
                                  : "border-slate-200 bg-white"
                              }`}
                            >
                              <p className="text-sm font-extrabold text-slate-900">
                                Enter M-Pesa Number
                              </p>
                              <p className="mt-1 text-xs text-slate-500">
                                Send the request to the Safaricom number
                                supplied by the driver.
                              </p>
                            </button>
                          </div>
                        )}

                        {mpesaTarget === "OTHER" &&
                          registeredDriver !== null && (
                            <div className="mt-4">
                              <Field label="Safaricom mobile number" required>
                                <input
                                  value={alternativeMpesaNumber}
                                  onChange={(event) =>
                                    setAlternativeMpesaNumber(
                                      event.target.value,
                                    )
                                  }
                                  placeholder="e.g. 0712345678"
                                  inputMode="tel"
                                  autoComplete="off"
                                  className="w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm font-medium text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                                />
                              </Field>
                            </div>
                          )}

                        {quote && (
                          <div className="mt-4 rounded-xl bg-slate-50 p-4">
                            <div className="flex flex-wrap items-center justify-between gap-3">
                              <div>
                                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                                  Current charge
                                </p>
                                <p className="mt-1 text-2xl font-black text-slate-900">
                                  {formatMoney(quote.total_amount)}
                                </p>
                                <p className="mt-1 text-xs text-slate-500">
                                  {quote.tariff_name} · {quote.billable_minutes}{" "}
                                  billable minutes
                                  {quote.grace_period_applied
                                    ? " · grace period applied"
                                    : ""}
                                </p>
                              </div>
                              <span className="rounded-full bg-white px-3 py-1.5 text-xs font-bold text-slate-600 ring-1 ring-slate-200">
                                Backend-calculated
                              </span>
                            </div>
                          </div>
                        )}

                        <button
                          type="button"
                          onClick={() => void initiateOperatorMpesaPayment()}
                          disabled={
                            stkInitiating ||
                            quoting ||
                            !quote ||
                            registeredDriver === null
                          }
                          className="mt-4 inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white hover:bg-emerald-700 disabled:opacity-60"
                        >
                          {stkInitiating ? (
                            <Loader2 size={17} className="animate-spin" />
                          ) : (
                            <Send size={17} />
                          )}
                          {stkInitiating
                            ? "Sending STK Push..."
                            : "Send M-Pesa STK Push"}
                        </button>
                      </>
                    )}

                    {exitPaymentMethod === "CASH" && (
                      <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                        <div className="flex items-start gap-3">
                          <Banknote
                            size={18}
                            className="mt-0.5 shrink-0 text-emerald-700"
                          />
                          <div>
                            <p className="font-extrabold text-emerald-900">
                              Cash payment
                            </p>
                            <p className="mt-1 text-xs leading-5 text-emerald-800">
                              Confirm that the driver has paid the current
                              parking charge in cash. SmartPark will calculate
                              and record the authoritative amount. The session
                              will become paid and ready for physical exit.
                            </p>
                          </div>
                        </div>

                        {quote && (
                          <div className="mt-4 rounded-xl bg-white p-4 ring-1 ring-emerald-100">
                            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                              Current charge
                            </p>
                            <p className="mt-1 text-2xl font-black text-slate-900">
                              {formatMoney(quote.total_amount)}
                            </p>
                            <p className="mt-1 text-xs text-slate-500">
                              {quote.tariff_name} · {quote.billable_minutes}{" "}
                              billable minutes
                              {quote.grace_period_applied
                                ? " · grace period applied"
                                : ""}
                            </p>
                          </div>
                        )}

                        <button
                          type="button"
                          onClick={() => void recordOperatorCashPayment()}
                          disabled={cashProcessing || quoting}
                          className="mt-4 inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white hover:bg-emerald-700 disabled:opacity-60"
                        >
                          {cashProcessing ? (
                            <Loader2 size={17} className="animate-spin" />
                          ) : (
                            <Banknote size={17} />
                          )}
                          {cashProcessing
                            ? "Recording Cash Payment..."
                            : "Confirm Cash Payment"}
                        </button>
                      </div>
                    )}

                    {stkPayment && (
                      <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                        <div className="flex items-start gap-3">
                          <CheckCircle2
                            size={18}
                            className="mt-0.5 shrink-0 text-emerald-700"
                          />
                          <div className="min-w-0">
                            <p className="font-extrabold text-emerald-900">
                              {String(stkPayment.status).toUpperCase() ===
                              "SUCCESSFUL"
                                ? "Payment received"
                                : "STK Push sent"}
                            </p>
                            <p className="mt-1 text-sm leading-6 text-emerald-800">
                              {String(stkPayment.status).toUpperCase() ===
                              "SUCCESSFUL"
                                ? "M-Pesa has confirmed the payment."
                                : `Payment request sent to ${stkPayment.phone_number}. Ask the driver to complete the prompt and enter their M-Pesa PIN.`}
                            </p>
                            <div className="mt-3 grid gap-2 text-xs text-emerald-800 sm:grid-cols-2">
                              <span>
                                Transaction:{" "}
                                <strong>{stkPayment.transaction_number}</strong>
                              </span>
                              <span>
                                Amount:{" "}
                                <strong>
                                  {formatMoney(stkPayment.amount)}
                                </strong>
                              </span>
                            </div>
                            {stkPolling && (
                              <p className="mt-3 inline-flex items-center gap-2 text-xs font-bold text-emerald-700">
                                <Loader2 size={13} className="animate-spin" />
                                Waiting for M-Pesa confirmation...
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4">
                  <div className="flex items-start gap-3">
                    <CheckCircle2
                      size={18}
                      className="mt-0.5 shrink-0 text-emerald-700"
                    />
                    <div>
                      <p className="font-extrabold text-emerald-900">
                        Session ready for physical exit
                      </p>
                      <p className="mt-1 text-sm leading-6 text-emerald-800">
                        The session is completed. Manual checkout will record
                        the physical exit and release the occupied bay.
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleCheckout()}
                    disabled={submitting}
                    className="mt-4 inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white hover:bg-emerald-700 disabled:opacity-60"
                  >
                    <LogOut size={17} />
                    {submitting ? "Checking out..." : "Check Out Vehicle"}
                  </button>
                </div>
              )}

              {quote && (
                <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <p className="text-xs font-bold uppercase tracking-wider text-slate-500">
                        Current charge
                      </p>
                      <p className="mt-1 text-2xl font-black text-slate-900">
                        {formatMoney(quote.total_amount)}
                      </p>
                      <p className="mt-1 text-xs text-slate-500">
                        {quote.tariff_name} · {quote.billable_minutes} billable
                        minutes
                        {quote.grace_period_applied
                          ? " · grace period applied"
                          : ""}
                      </p>
                    </div>
                    <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-bold text-slate-600">
                      Payment required before exit
                    </span>
                  </div>
                </div>
              )}

              <div className="mt-5">
                <Field label="Exit notes">
                  <textarea
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    rows={3}
                    placeholder="Optional manual-exit note..."
                    className="w-full resize-none rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm font-medium text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                  />
                </Field>
              </div>
            </div>
          )}

          {!exitSession && !searching && (
            <div className="mt-6 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-8 text-center">
              <LogOut size={28} className="mx-auto text-slate-400" />
              <p className="mt-3 font-extrabold text-slate-700">
                No vehicle selected
              </p>
              <p className="mt-1 text-sm text-slate-500">
                Enter the registration number to locate its facility-scoped
                parking session.
              </p>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

// ==========================================================
// Small presentational helpers
// ==========================================================

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-extrabold uppercase tracking-wide text-slate-600">
        {label} {required && <span className="text-rose-500">*</span>}
      </span>
      {children}
    </label>
  );
}

function Info({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white p-3 ring-1 ring-slate-200">
      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-sm font-extrabold capitalize text-slate-800">
        {value}
      </p>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const normalized = String(status).toUpperCase();
  const positive = ["CONFIRMED", "COMPLETED"].includes(normalized);
  const warning = ["CREATED", "ACTIVE"].includes(normalized);

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-extrabold ${
        positive
          ? "bg-emerald-100 text-emerald-700"
          : warning
            ? "bg-amber-100 text-amber-700"
            : "bg-slate-100 text-slate-600"
      }`}
    >
      {normalized.replace(/_/g, " ")}
    </span>
  );
}
