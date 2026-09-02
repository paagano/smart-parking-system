import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";

import {
  Activity,
  AlertCircle,
  ArrowLeft,
  CarFront,
  CheckCircle2,
  Clock3,
  CreditCard,
  FileText,
  LogOut,
  MapPin,
  ParkingCircle,
  RefreshCw,
  Timer,
  X,
} from "lucide-react";

import {
  api,
  parkingBaysApi,
  parkingFacilitiesApi,
  parkingZonesApi,
  type ParkingBay,
  type ParkingFacility,
  type ParkingZone,
} from "../../../api";
import { Card } from "../../../components/common/Page";

// ==========================================================
// Types
// ==========================================================

type SessionStatus =
  | "ACTIVE"
  | "COMPLETED"
  | "CHECKED_IN"
  | "CHECKED_OUT"
  | "CHECKOUT_PENDING"
  | "CANCELLED"
  | "PENDING"
  | "UNKNOWN";

interface ParkingSession {
  id: number;

  session_number?: string | null;

  status?: string | null;

  facility_id?: number | string | null;
  parking_facility_id?: number | string | null;
  facility_name?: string | null;

  parking_zone_id?: number | string | null;
  zone_id?: number | string | null;
  parking_zone_name?: string | null;

  parking_bay_id?: number | string | null;
  parking_bay_number?: string | null;
  parking_bay_code?: string | null;
  bay_number?: string | null;
  bay_code?: string | null;

  vehicle_id?: number | null;
  vehicle_registration?: string | null;
  vehicle_type?: string | null;

  entry_time?: string | null;
  exit_time?: string | null;

  check_in_at?: string | null;
  checked_in_at?: string | null;
  start_time?: string | null;

  check_out_at?: string | null;
  checked_out_at?: string | null;
  end_time?: string | null;

  duration_minutes?: number | null;

  amount?: number | string | null;
  total_amount?: number | string | null;
  calculated_amount?: number | string | null;
  current_amount?: number | string | null;
  outstanding_amount?: number | string | null;
  payable_amount?: number | string | null;
  parking_fee?: number | string | null;
  amount_paid?: number | string | null;

  currency?: string | null;

  payment_method?: string | null;
  payment_status?: string | null;
  payment_completed_at?: string | null;

  reservation_id?: number | null;
  reservation_number?: string | null;

  notes?: string | null;

  created_at?: string | null;
  updated_at?: string | null;

  [key: string]: any;
}

// ==========================================================
// Helpers
// ==========================================================

function getErrorMessage(error: any): string {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail
      .map((item: any) =>
        typeof item === "string" ? item : (item?.msg ?? "Validation error"),
      )
      .join(", ");
  }

  const message = error?.response?.data?.message;

  if (typeof message === "string") {
    return message;
  }

  if (typeof error?.message === "string") {
    return error.message;
  }

  switch (error?.response?.status) {
    case 401:
      return "Your session has expired. Please sign in again.";

    case 403:
      return "You are not authorized to view this parking session.";

    case 404:
      return "The requested parking session could not be found.";

    case 409:
      return "The parking session could not be processed because of a conflict.";

    case 422:
      return "Some of the parking session information is invalid.";

    default:
      return "Unable to load the parking session. Please try again.";
  }
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }

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
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-KE", {
    timeStyle: "short",
  }).format(date);
}

function formatCurrency(
  value: number | null | undefined,
  currency = "KES",
): string {
  const amount = Number(value ?? 0);

  if (!Number.isFinite(amount)) {
    return "Ksh 0.00";
  }

  try {
    return new Intl.NumberFormat("en-KE", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `Ksh ${amount.toFixed(2)}`;
  }
}

function normalizeStatus(status: string | null | undefined): SessionStatus {
  const value = String(status ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

  if (value === "ACTIVE" || value === "CHECKED_IN" || value === "CHECK_IN") {
    return "ACTIVE";
  }

  if (
    value === "CHECKOUT_REQUESTED" ||
    value === "CHECKOUT_PENDING" ||
    value === "AWAITING_EXIT" ||
    value === "EXIT_PENDING"
  ) {
    return "CHECKOUT_PENDING";
  }

  if (
    value === "COMPLETED" ||
    value === "CHECKED_OUT" ||
    value === "CHECK_OUT"
  ) {
    return "COMPLETED";
  }

  if (value === "CANCELLED" || value === "CANCELED") {
    return "CANCELLED";
  }

  if (value === "PENDING") {
    return "PENDING";
  }

  return "UNKNOWN";
}

function getCheckInTime(session: ParkingSession): string | null {
  return (
    session.entry_time ??
    session.check_in_at ??
    session.checked_in_at ??
    session.start_time ??
    null
  );
}

function getCheckOutTime(session: ParkingSession): string | null {
  return (
    session.exit_time ??
    session.check_out_at ??
    session.checked_out_at ??
    session.end_time ??
    null
  );
}

function getFacilityName(session: ParkingSession): string {
  return (
    session.facility_name ??
    session.facility?.name ??
    session.parking_facility?.name ??
    "Parking facility"
  );
}

function getFacilityAddress(session: ParkingSession): string | null {
  const facility = session.facility ?? session.parking_facility;

  if (!facility) {
    return null;
  }

  return facility.address ?? facility.location ?? facility.city ?? null;
}

function getZoneName(session: ParkingSession): string {
  return (
    session.parking_zone_name ??
    session.zone_name ??
    session.parking_zone?.name ??
    "—"
  );
}

function getBayName(session: ParkingSession): string {
  return (
    session.parking_bay_number ??
    session.bay_number ??
    session.parking_bay?.bay_number ??
    session.parking_bay?.name ??
    "—"
  );
}

function getBayDisplayName(session: ParkingSession): string {
  const number =
    session.parking_bay_number ??
    session.bay_number ??
    session.parking_bay?.bay_number ??
    session.parking_bay?.name ??
    null;

  const code =
    session.parking_bay_code ??
    session.bay_code ??
    session.parking_bay?.code ??
    null;

  return [number, code].filter(Boolean).join(" · ") || "—";
}

function getZoneDisplayName(session: ParkingSession): string {
  const name =
    session.parking_zone_name ??
    session.zone_name ??
    session.parking_zone?.name ??
    null;

  const code =
    session.parking_zone_code ??
    session.zone_code ??
    session.parking_zone?.code ??
    null;

  return [name, code].filter(Boolean).join(" · ") || "—";
}

function extractQuoteAmount(value: any): number | null {
  const candidates = [
    value?.outstanding_amount,
    value?.payable_amount,
    value?.current_amount,
    value?.total_amount,
    value?.calculated_amount,
    value?.amount,
  ];

  for (const candidate of candidates) {
    if (candidate === null || candidate === undefined || candidate === "") {
      continue;
    }

    const numeric = Number(candidate);

    if (Number.isFinite(numeric)) {
      return numeric;
    }
  }

  return null;
}

function getVehicleRegistration(session: ParkingSession): string {
  return (
    session.vehicle_registration ??
    session.vehicle?.registration_number ??
    session.vehicle?.registration ??
    "—"
  );
}

function getVehicleType(session: ParkingSession): string {
  return (
    session.vehicle_type ??
    session.vehicle?.vehicle_type ??
    session.vehicle?.type ??
    "—"
  );
}

function getAmount(session: ParkingSession): number {
  const candidates = [
    session.current_amount,
    session.outstanding_amount,
    session.payable_amount,
    session.total_amount,
    session.calculated_amount,
    session.parking_fee,
    session.amount,
    session.amount_paid,
  ];

  for (const value of candidates) {
    const amount = Number(value);

    if (Number.isFinite(amount)) {
      return amount;
    }
  }

  return 0;
}

function getDurationMinutes(session: ParkingSession): number | null {
  if (
    session.duration_minutes !== null &&
    session.duration_minutes !== undefined
  ) {
    const value = Number(session.duration_minutes);

    if (Number.isFinite(value)) {
      return value;
    }
  }

  const start = getCheckInTime(session);

  if (!start) {
    return null;
  }

  const startDate = new Date(start);

  if (Number.isNaN(startDate.getTime())) {
    return null;
  }

  const end = getCheckOutTime(session);
  const endDate = end ? new Date(end) : new Date();

  if (Number.isNaN(endDate.getTime())) {
    return null;
  }

  return Math.max(
    0,
    Math.floor((endDate.getTime() - startDate.getTime()) / 60000),
  );
}

function getLiveDurationMinutes(
  session: ParkingSession,
  nowMs: number,
): number | null {
  const start = getCheckInTime(session);
  if (!start) return null;

  const startMs = new Date(start).getTime();
  if (!Number.isFinite(startMs)) return null;

  const end = getCheckOutTime(session);
  const endMs = end ? new Date(end).getTime() : nowMs;
  if (!Number.isFinite(endMs)) return null;

  return Math.max(0, Math.floor((endMs - startMs) / 60000));
}

function formatDuration(minutes: number | null): string {
  if (minutes === null) {
    return "—";
  }

  if (minutes < 60) {
    return `${minutes} min`;
  }

  const hours = Math.floor(minutes / 60);

  const remainingMinutes = minutes % 60;

  if (remainingMinutes === 0) {
    return `${hours}h`;
  }

  return `${hours}h ${remainingMinutes}m`;
}

// ==========================================================
// Status Badge
// ==========================================================

function StatusBadge({ status }: { status: SessionStatus }) {
  if (status === "ACTIVE") {
    return (
      <span className="inline-flex items-center gap-2 rounded-full bg-emerald-400/10 px-3 py-1.5 text-xs font-bold text-emerald-300 ring-1 ring-emerald-300/20">
        <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-400" />
        ACTIVE
      </span>
    );
  }

  if (status === "CHECKOUT_PENDING") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700">
        <Clock3 size={13} />
        EXIT VERIFICATION
      </span>
    );
  }

  if (status === "COMPLETED") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-3 py-1.5 text-xs font-bold text-slate-200 ring-1 ring-white/10">
        <CheckCircle2 size={14} />
        COMPLETED
      </span>
    );
  }

  if (status === "CANCELLED") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-red-400/10 px-3 py-1.5 text-xs font-bold text-red-300 ring-1 ring-red-300/20">
        CANCELLED
      </span>
    );
  }

  if (status === "PENDING") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-400/10 px-3 py-1.5 text-xs font-bold text-amber-300 ring-1 ring-amber-300/20">
        <Clock3 size={14} />
        PENDING
      </span>
    );
  }

  return (
    <span className="inline-flex items-center rounded-full bg-white/10 px-3 py-1.5 text-xs font-bold text-slate-300 ring-1 ring-white/10">
      {status}
    </span>
  );
}

// ==========================================================
// Detail Row
// ==========================================================

function DetailRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1 px-5 py-4 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <span className="text-sm font-semibold text-slate-500">{label}</span>

      <span
        className={`text-sm font-bold text-slate-800 sm:text-right ${
          mono ? "font-mono" : ""
        }`}
      >
        {value}
      </span>
    </div>
  );
}

// ==========================================================
// Timeline Item
// ==========================================================

function TimelineItem({
  title,
  value,
  description,
  icon,
  completed,
  last = false,
}: {
  title: string;
  value: string;
  description: string;
  icon: React.ReactNode;
  completed: boolean;
  last?: boolean;
}) {
  return (
    <div className="relative flex gap-4">
      {!last && (
        <div
          className={`absolute left-[15px] top-8 h-[calc(100%+12px)] w-px ${
            completed ? "bg-emerald-200" : "bg-slate-200"
          }`}
        />
      )}

      <div
        className={`relative z-10 grid h-8 w-8 shrink-0 place-items-center rounded-full ${
          completed
            ? "bg-emerald-600 text-white ring-4 ring-emerald-50"
            : "bg-slate-100 text-slate-400"
        }`}
      >
        {icon}
      </div>

      <div className="pb-7">
        <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
          {title}
        </div>

        <div className="mt-1 text-sm font-black text-slate-900">{value}</div>

        <div className="mt-1 text-xs text-slate-500">{description}</div>
      </div>
    </div>
  );
}

// ==========================================================
// Main Component
// ==========================================================

export default function SessionDetails() {
  const navigate = useNavigate();

  const { sessionId } = useParams<{
    sessionId: string;
  }>();

  // ========================================================
  // State
  // ========================================================

  const [session, setSession] = useState<ParkingSession | null>(null);

  const [loading, setLoading] = useState(true);

  const [refreshing, setRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [liveNow, setLiveNow] = useState(() => Date.now());

  // ========================================================
  // Load Session
  // ========================================================

  const loadSession = useCallback(
    async (manualRefresh = false) => {
      if (!sessionId) {
        setError("No parking session was specified.");
        setLoading(false);
        return;
      }

      if (manualRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setError(null);

      try {
        const response = await api.get<ParkingSession>(
          `/parking-sessions/${encodeURIComponent(sessionId)}`,
        );

        const payload = response.data;

        /*
         * Some API response formats wrap
         * the actual object in `data`.
         */
        const rawSession = payload?.data ?? payload;

        if (!rawSession || typeof rawSession !== "object") {
          throw new Error("The backend returned an invalid parking session.");
        }

        /*
         * Resolve the same parking hierarchy used by ParkingSessions:
         *
         *     Parking Session
         *          ↓ parking_bay_id
         *     Parking Bay
         *          ↓ zone_id
         *     Parking Zone
         *          ↓ facility_id
         *     Parking Facility
         *
         * IDs are normalised to strings because the API can serialise
         * PostgreSQL integer IDs as either numbers or strings.
         */
        let resolvedSession = { ...rawSession } as ParkingSession;

        try {
          const [facilitiesResult, zonesResult, baysResult] =
            await Promise.allSettled([
              parkingFacilitiesApi.list(0, 100),
              parkingZonesApi.list(0, 100),
              parkingBaysApi.list(0, 100),
            ]);

          const facilities: ParkingFacility[] =
            facilitiesResult.status === "fulfilled"
              ? (facilitiesResult.value.items ?? [])
              : [];

          const zones: ParkingZone[] =
            zonesResult.status === "fulfilled"
              ? (zonesResult.value.items ?? [])
              : [];

          const bays: ParkingBay[] =
            baysResult.status === "fulfilled"
              ? (baysResult.value.items ?? [])
              : [];

          const raw = rawSession as ParkingSession & {
            parking_zone_id?: number | string | null;
            zone_id?: number | string | null;
            parking_facility_id?: number | string | null;
            facility_id?: number | string | null;
          };

          const bay =
            raw.parking_bay_id !== null && raw.parking_bay_id !== undefined
              ? bays.find(
                  (item) => String(item.id) === String(raw.parking_bay_id),
                )
              : undefined;

          const zoneId =
            raw.parking_zone_id ?? raw.zone_id ?? bay?.zone_id ?? null;

          const zone =
            zoneId !== null && zoneId !== undefined
              ? zones.find((item) => String(item.id) === String(zoneId))
              : undefined;

          const facilityId =
            raw.parking_facility_id ??
            raw.facility_id ??
            zone?.facility_id ??
            null;

          const facility =
            facilityId !== null && facilityId !== undefined
              ? facilities.find(
                  (item) => String(item.id) === String(facilityId),
                )
              : undefined;

          if (facility) {
            resolvedSession.facility_name =
              resolvedSession.facility_name ?? facility.name;
            resolvedSession.facility = {
              ...(resolvedSession.facility ?? {}),
              name: resolvedSession.facility?.name ?? facility.name,
              address:
                resolvedSession.facility?.address ??
                facility.address ??
                facility.city ??
                null,
            };
          }

          if (zone) {
            resolvedSession.parking_zone_name =
              resolvedSession.parking_zone_name ?? zone.name;
            resolvedSession.parking_zone = {
              ...(resolvedSession.parking_zone ?? {}),
              name: resolvedSession.parking_zone?.name ?? zone.name,
              code: resolvedSession.parking_zone?.code ?? zone.code,
            };
            resolvedSession.parking_zone_code =
              resolvedSession.parking_zone_code ?? zone.code;
          }

          if (bay) {
            resolvedSession.parking_bay_number =
              resolvedSession.parking_bay_number ?? bay.bay_number;
            resolvedSession.parking_bay_code =
              resolvedSession.parking_bay_code ?? bay.code;
            resolvedSession.parking_bay = {
              ...(resolvedSession.parking_bay ?? {}),
              bay_number:
                resolvedSession.parking_bay?.bay_number ?? bay.bay_number,
              name: resolvedSession.parking_bay?.name ?? bay.bay_number,
              code: resolvedSession.parking_bay?.code ?? bay.code,
              zone_id: resolvedSession.parking_bay?.zone_id ?? bay.zone_id,
            };
          }
        } catch (metadataError) {
          console.warn(
            "[SmartPark Session Details] Unable to resolve parking metadata:",
            metadataError,
          );
        }

        /*
         * Active-session amount must come from the same authoritative
         * pricing-engine quote used by SessionPayment/ParkingSessions.
         * This prevents the details page from displaying a stale/default
         * stored amount such as Ksh 0.00.
         */
        if (normalizeStatus(resolvedSession.status) === "ACTIVE") {
          try {
            const quoteResponse = await api.get<any>(
              `/parking-sessions/${encodeURIComponent(sessionId)}/quote`,
            );

            const quoteBody = quoteResponse.data;

            const quote =
              quoteBody &&
              typeof quoteBody === "object" &&
              ("data" in quoteBody ||
                "quote" in quoteBody ||
                "result" in quoteBody)
                ? (quoteBody.data ??
                  quoteBody.quote ??
                  quoteBody.result ??
                  quoteBody)
                : quoteBody;

            const quoteAmount = extractQuoteAmount(quote);

            if (quoteAmount !== null) {
              resolvedSession.current_amount = quoteAmount;
            }

            if (
              quote?.duration_minutes !== null &&
              quote?.duration_minutes !== undefined &&
              Number.isFinite(Number(quote.duration_minutes))
            ) {
              resolvedSession.duration_minutes = Number(quote.duration_minutes);
            }

            if (quote?.currency) {
              resolvedSession.currency = String(quote.currency);
            }
          } catch (quoteError) {
            console.warn(
              "[SmartPark Session Details] Current pricing-engine quote unavailable:",
              quoteError,
            );
          }
        }

        /*
         * Completed-session payment method comes from the payment transaction
         * associated with the session. Active sessions intentionally keep the
         * payment method unset and therefore display "—".
         */
        if (normalizeStatus(resolvedSession.status) === "COMPLETED") {
          try {
            const paymentsResponse = await api.get<any>(
              `/payments/session/${encodeURIComponent(sessionId)}?limit=100&offset=0`,
            );

            const paymentsBody = paymentsResponse.data;

            const payments = Array.isArray(paymentsBody)
              ? paymentsBody
              : Array.isArray(paymentsBody?.items)
                ? paymentsBody.items
                : Array.isArray(paymentsBody?.data)
                  ? paymentsBody.data
                  : Array.isArray(paymentsBody?.results)
                    ? paymentsBody.results
                    : [];

            const successfulPayments = payments.filter(
              (payment: any) =>
                String(payment?.status ?? "").toUpperCase() === "SUCCESSFUL" &&
                payment?.payment_method,
            );

            const payment =
              successfulPayments.length > 0
                ? [...successfulPayments].sort(
                    (a: any, b: any) =>
                      new Date(b?.paid_at ?? b?.created_at ?? 0).getTime() -
                      new Date(a?.paid_at ?? a?.created_at ?? 0).getTime(),
                  )[0]
                : null;

            if (payment?.payment_method) {
              resolvedSession.payment_method = String(payment.payment_method);
            }

            if (payment?.paid_at ?? payment?.created_at) {
              resolvedSession.payment_completed_at = String(
                payment.paid_at ?? payment.created_at,
              );
            }
          } catch (paymentError) {
            console.warn(
              "[SmartPark Session Details] Payment method unavailable:",
              paymentError,
            );
          }
        }

        setSession(resolvedSession);
      } catch (err: any) {
        console.error(
          "[SmartPark Session Details] Failed to load session:",
          err,
        );

        setError(getErrorMessage(err));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [sessionId],
  );

  // ========================================================
  // Initial Load
  // ========================================================

  useEffect(() => {
    void loadSession();
  }, [loadSession]);

  // ========================================================
  // Auto Refresh Active Session
  // ========================================================

  useEffect(() => {
    if (!session || normalizeStatus(session.status) !== "ACTIVE") {
      return;
    }

    const interval = window.setInterval(() => {
      void loadSession(true);
    }, 60 * 1000);

    return () => {
      window.clearInterval(interval);
    };
  }, [session, loadSession]);

  useEffect(() => {
    const interval = window.setInterval(() => setLiveNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  // ========================================================
  // Derived Information
  // ========================================================

  const status = useMemo(() => normalizeStatus(session?.status), [session]);

  const checkInTime = useMemo(
    () => (session ? getCheckInTime(session) : null),
    [session],
  );

  const checkOutTime = useMemo(
    () => (session ? getCheckOutTime(session) : null),
    [session],
  );

  const duration = useMemo(
    () =>
      session
        ? status === "ACTIVE" && !getCheckOutTime(session)
          ? getLiveDurationMinutes(session, liveNow)
          : getDurationMinutes(session)
        : null,
    [session, status, liveNow],
  );

  const amount = useMemo(() => (session ? getAmount(session) : 0), [session]);

  const currency = session?.currency ?? "KES";

  const facilityName = session ? getFacilityName(session) : "Parking facility";

  const facilityAddress = session ? getFacilityAddress(session) : null;

  const vehicleRegistration = session ? getVehicleRegistration(session) : "—";

  const vehicleType = session ? getVehicleType(session) : "—";

  const zoneName = session ? getZoneDisplayName(session) : "—";

  const bayName = session ? getBayDisplayName(session) : "—";

  // ========================================================
  // Check Out / Payment
  // ========================================================

  const handleCheckOut = () => {
    if (!session) {
      return;
    }

    const confirmed = window.confirm(
      `Proceed to payment for vehicle ${vehicleRegistration} at ${facilityName}?`,
    );

    if (!confirmed) {
      return;
    }

    const params = new URLSearchParams();
    params.set("checkout", "1");
    params.set("sessionId", String(session.id));
    params.set("currency", currency);
    params.set("facility", facilityName);
    params.set("vehicle", vehicleRegistration);
    params.set("bay", bayName);

    if (session.session_number) {
      params.set("sessionNumber", session.session_number);
    }

    navigate(`/payments?${params.toString()}`);
  };

  // ========================================================
  // Loading
  // ========================================================

  if (loading) {
    return (
      <div className="mx-auto flex min-h-[500px] w-full max-w-6xl items-center justify-center">
        <div className="text-center">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-emerald-50 text-emerald-600">
            <RefreshCw size={30} className="animate-spin" />
          </div>

          <h2 className="mt-5 text-lg font-black text-slate-900">
            Loading parking session
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Retrieving your session details...
          </p>
        </div>
      </div>
    );
  }

  // ========================================================
  // Error / Not Found
  // ========================================================

  if (!session && error) {
    return (
      <div className="mx-auto w-full max-w-4xl space-y-6">
        <button
          type="button"
          onClick={() => navigate("/sessions")}
          className="inline-flex items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-emerald-600"
        >
          <ArrowLeft size={17} />
          Back to Sessions
        </button>

        <div className="rounded-3xl border border-red-200 bg-red-50 p-8 text-center">
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-red-500 shadow-sm">
            <AlertCircle size={27} />
          </div>

          <h1 className="mt-5 text-xl font-black text-slate-900">
            Unable to load session
          </h1>

          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-600">
            {error}
          </p>

          <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
            <button
              type="button"
              onClick={() => void loadSession()}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-emerald-500"
            >
              <RefreshCw size={16} />
              Try Again
            </button>

            <button
              type="button"
              onClick={() => navigate("/sessions")}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-bold text-slate-700 transition hover:bg-slate-50"
            >
              Back to Sessions
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ========================================================
  // No Session
  // ========================================================

  if (!session) {
    return (
      <div className="mx-auto w-full max-w-4xl py-12 text-center">
        <div className="mx-auto grid h-16 w-16 place-items-center rounded-3xl bg-slate-100 text-slate-400">
          <ParkingCircle size={30} />
        </div>

        <h1 className="mt-5 text-xl font-black text-slate-900">
          Parking session not found
        </h1>

        <button
          type="button"
          onClick={() => navigate("/sessions")}
          className="mt-6 inline-flex items-center gap-2 rounded-xl bg-[#071a2d] px-5 py-3 text-sm font-bold text-white"
        >
          <ArrowLeft size={16} />
          Back to Sessions
        </button>
      </div>
    );
  }

  // ========================================================
  // Main Page
  // ========================================================

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      {/* ==================================================
          TOP NAVIGATION
      ================================================== */}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <button
          type="button"
          onClick={() => navigate("/sessions")}
          className="inline-flex w-fit items-center gap-2 text-sm font-bold text-slate-600 transition hover:text-emerald-600"
        >
          <ArrowLeft size={17} />
          Back to Sessions
        </button>

        <button
          type="button"
          onClick={() => void loadSession(true)}
          disabled={refreshing}
          className="inline-flex w-fit items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* ==================================================
          ERROR
      ================================================== */}

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-red-700">
          <AlertCircle size={19} className="mt-0.5 shrink-0" />

          <div className="min-w-0 flex-1">
            <div className="font-bold">Session service message</div>

            <div className="mt-1 text-sm leading-6">{error}</div>
          </div>

          <button
            type="button"
            onClick={() => setError(null)}
            className="text-red-400 transition hover:text-red-600"
            aria-label="Dismiss error"
          >
            <X size={18} />
          </button>
        </div>
      )}

      {/* ==================================================
          HERO
      ================================================== */}

      <section className="overflow-hidden rounded-3xl bg-[#071a2d] text-white shadow-sm">
        <div className="p-6 sm:p-8">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex items-start gap-4">
              <div className="grid h-14 w-14 shrink-0 place-items-center rounded-2xl bg-emerald-500/10 text-emerald-300 ring-1 ring-emerald-300/10">
                <ParkingCircle size={28} />
              </div>

              <div>
                <div className="text-xs font-bold uppercase tracking-[.2em] text-emerald-300">
                  Parking Session
                </div>

                <h1 className="mt-2 text-2xl font-black sm:text-3xl">
                  {session.session_number ?? `Session #${session.id}`}
                </h1>

                <p className="mt-2 text-sm text-slate-300">
                  Session details and parking activity.
                </p>
              </div>
            </div>

            <StatusBadge status={status} />
          </div>

          {/* Hero Metrics */}

          <div className="mt-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Facility
              </div>

              <div className="mt-2 flex items-center gap-2 text-sm font-bold">
                <MapPin size={15} className="shrink-0 text-emerald-300" />

                {facilityName}
              </div>
            </div>

            <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Vehicle
              </div>

              <div className="mt-2 flex items-center gap-2 text-sm font-bold">
                <CarFront size={15} className="shrink-0 text-emerald-300" />

                {vehicleRegistration}
              </div>
            </div>

            <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Duration
              </div>

              <div className="mt-2 flex items-center gap-2 text-sm font-bold">
                <Timer size={15} className="shrink-0 text-emerald-300" />

                {formatDuration(duration)}
              </div>
            </div>

            <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
              <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Parking Amount
              </div>

              <div className="mt-2 flex items-center gap-2 text-sm font-bold">
                <CreditCard size={15} className="shrink-0 text-emerald-300" />

                {formatCurrency(amount, currency)}
              </div>
            </div>
          </div>

          {/* Active session action */}

          {status === "ACTIVE" && (
            <>
              <div className="mt-6 flex flex-col gap-3 rounded-2xl border border-emerald-300/10 bg-emerald-400/5 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="text-sm font-bold text-white">
                    Your parking session is active
                  </div>

                  <div className="mt-1 text-xs text-slate-400">
                    Check out when you are ready to leave the facility.
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleCheckOut}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-500 px-5 py-3 text-sm font-bold text-white transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <>
                    Pay & Check Out
                    <ArrowLeft size={16} className="rotate-180" />
                  </>
                </button>
              </div>

              <div className="mt-3 rounded-xl border border-amber-300/20 bg-amber-400/5 px-4 py-3 text-xs leading-5 text-amber-200">
                Payment completes the parking session. After successful payment,
                proceed to the exit and leave the premises within 15 minutes.
              </div>
            </>
          )}
        </div>
      </section>

      {/* ==================================================
          SESSION TIMELINE + SUMMARY
      ================================================== */}

      <div className="grid gap-6 lg:grid-cols-5">
        {/* Timeline */}

        <div className="lg:col-span-3">
          <Card
            title="Session Timeline"
            sub="Key events recorded during this parking session."
          >
            <div className="p-6">
              <TimelineItem
                title="Parking session started"
                value={formatDateTime(checkInTime)}
                description={
                  checkInTime
                    ? `Vehicle checked in at ${formatTime(checkInTime)}.`
                    : "Check-in time is not available."
                }
                icon={<Activity size={14} />}
                completed={Boolean(checkInTime)}
              />

              <TimelineItem
                title="Parking in progress"
                value={
                  status === "ACTIVE" ? "Currently parked" : "Session completed"
                }
                description={
                  status === "ACTIVE"
                    ? `Current duration: ${formatDuration(duration)}.`
                    : `Total parking duration: ${formatDuration(duration)}.`
                }
                icon={<ParkingCircle size={14} />}
                completed={Boolean(checkInTime)}
              />

              <TimelineItem
                title="Payment successful / session completed"
                value={formatDateTime(session.payment_completed_at)}
                description={
                  session.payment_completed_at
                    ? `Payment was successfully completed and the parking session ended at ${formatTime(session.payment_completed_at)}.`
                    : status === "ACTIVE"
                      ? "Payment has not yet been completed."
                      : "Payment completion time is not available."
                }
                icon={<CheckCircle2 size={14} />}
                completed={Boolean(session.payment_completed_at)}
              />

              <TimelineItem
                title="Vehicle exited"
                value={formatDateTime(checkOutTime)}
                description={
                  checkOutTime
                    ? `Vehicle exited the premises at ${formatTime(checkOutTime)}.`
                    : "Vehicle has not yet left the premises."
                }
                icon={<LogOut size={14} />}
                completed={Boolean(checkOutTime)}
                last
              />
            </div>
          </Card>
        </div>

        {/* Session Summary */}

        <div className="lg:col-span-2">
          <Card
            title="Session Summary"
            sub="A quick overview of your parking session."
          >
            <div className="divide-y divide-slate-100">
              <DetailRow
                label="Session Number"
                value={session.session_number ?? `#${session.id}`}
                mono
              />

              <DetailRow
                label="Status"
                value={<StatusBadge status={status} />}
              />

              <DetailRow label="Duration" value={formatDuration(duration)} />

              <DetailRow
                label="Amount"
                value={formatCurrency(amount, currency)}
              />

              <DetailRow
                label="Payment Status"
                value={
                  session.payment_status
                    ? String(session.payment_status)
                        .replace(/_/g, " ")
                        .replace(/\b\w/g, (letter) => letter.toUpperCase())
                    : "—"
                }
              />

              <DetailRow
                label="Payment Method"
                value={
                  session.payment_method
                    ? String(session.payment_method)
                        .replace(/_/g, " ")
                        .replace(/\b\w/g, (letter) => letter.toUpperCase())
                    : "—"
                }
              />
            </div>
          </Card>
        </div>
      </div>

      {/* ==================================================
          PARKING LOCATION
      ================================================== */}

      <Card
        title="Parking Location"
        sub="Where this parking session took place."
      >
        <div className="grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-4">
          <div className="rounded-2xl bg-slate-50 p-4">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <MapPin size={15} />
              Facility
            </div>

            <div className="mt-2 text-sm font-black text-slate-900">
              {facilityName}
            </div>

            {facilityAddress && (
              <div className="mt-1 text-xs leading-5 text-slate-500">
                {facilityAddress}
              </div>
            )}
          </div>

          <div className="rounded-2xl bg-slate-50 p-4">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <ParkingCircle size={15} />
              Zone
            </div>

            <div className="mt-2 text-sm font-black text-slate-900">
              {zoneName}
            </div>
          </div>

          <div className="rounded-2xl bg-slate-50 p-4">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <ParkingCircle size={15} />
              Parking Bay
            </div>

            <div className="mt-2 text-sm font-black text-slate-900">
              {bayName}
            </div>
          </div>

          <div className="rounded-2xl bg-slate-50 p-4">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <Clock3 size={15} />
              Check-in
            </div>

            <div className="mt-2 text-sm font-black text-slate-900">
              {formatDateTime(checkInTime)}
            </div>
          </div>
        </div>
      </Card>

      {/* ==================================================
          VEHICLE INFORMATION
      ================================================== */}

      <Card
        title="Vehicle Information"
        sub="Vehicle associated with this parking session."
      >
        <div className="grid gap-0 divide-y divide-slate-100 sm:grid-cols-2 sm:divide-x sm:divide-y-0">
          <div className="flex items-center gap-4 p-6">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-blue-50 text-blue-600">
              <CarFront size={21} />
            </div>

            <div>
              <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Registration
              </div>

              <div className="mt-1 font-black text-slate-900">
                {vehicleRegistration}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-4 p-6">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-violet-50 text-violet-600">
              <CarFront size={21} />
            </div>

            <div>
              <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Vehicle Type
              </div>

              <div className="mt-1 font-black text-slate-900">
                {String(vehicleType)
                  .replace(/_/g, " ")
                  .replace(/\b\w/g, (letter) => letter.toUpperCase())}
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* ==================================================
          PAYMENT
      ================================================== */}

      <Card
        title="Parking Charges"
        sub="Financial information associated with this session."
      >
        <div className="grid gap-4 p-6 sm:grid-cols-3">
          <div className="rounded-2xl bg-emerald-50 p-5">
            <div className="text-xs font-bold uppercase tracking-wider text-emerald-700">
              Total Amount
            </div>

            <div className="mt-2 text-2xl font-black text-slate-950">
              {formatCurrency(amount, currency)}
            </div>
          </div>

          <div className="rounded-2xl bg-slate-50 p-5">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Payment Method
            </div>

            <div className="mt-2 flex items-center gap-2 text-sm font-black text-slate-900">
              <CreditCard size={16} className="text-slate-400" />

              {session.payment_method
                ? String(session.payment_method)
                    .replace(/_/g, " ")
                    .replace(/\b\w/g, (letter) => letter.toUpperCase())
                : "—"}
            </div>
          </div>

          <div className="rounded-2xl bg-slate-50 p-5">
            <div className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Payment Status
            </div>

            <div className="mt-2 flex items-center gap-2 text-sm font-black text-slate-900">
              <CheckCircle2
                size={16}
                className={
                  String(session.payment_status ?? "").toUpperCase() === "PAID"
                    ? "text-emerald-600"
                    : "text-slate-400"
                }
              />

              {session.payment_status
                ? String(session.payment_status)
                    .replace(/_/g, " ")
                    .replace(/\b\w/g, (letter) => letter.toUpperCase())
                : "—"}
            </div>
          </div>
        </div>
      </Card>

      {/* ==================================================
          NOTES
      ================================================== */}

      {session.notes && (
        <Card
          title="Session Notes"
          sub="Additional information recorded for this session."
        >
          <div className="flex items-start gap-4 p-6">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-slate-100 text-slate-500">
              <FileText size={21} />
            </div>

            <p className="text-sm leading-7 text-slate-600">{session.notes}</p>
          </div>
        </Card>
      )}

      {/* ==================================================
          RESERVATION REFERENCE
      ================================================== */}

      {(session.reservation_id || session.reservation_number) && (
        <Card
          title="Reservation Reference"
          sub="Reservation associated with this parking session."
        >
          <div className="grid gap-0 divide-y divide-slate-100 sm:grid-cols-2 sm:divide-x sm:divide-y-0">
            <DetailRow
              label="Reservation ID"
              value={session.reservation_id ?? "—"}
              mono
            />

            <DetailRow
              label="Reservation Number"
              value={session.reservation_number ?? "—"}
              mono
            />
          </div>
        </Card>
      )}

      {/* ==================================================
          FOOTER
      ================================================== */}

      <div className="flex flex-col gap-2 border-t border-slate-100 pt-4 text-xs text-slate-400 sm:flex-row sm:items-center sm:justify-between">
        <div>Session created {formatDateTime(session.created_at)}</div>

        <div className="flex items-center gap-2">
          <ParkingCircle size={14} />
          SmartPark AI Parking Management
        </div>
      </div>
    </div>
  );
}
