import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  CarFront,
  CheckCircle2,
  Clock3,
  MapPin,
  ParkingCircle,
  RefreshCw,
  Search,
  Timer,
  X,
} from "lucide-react";

import { useNavigate } from "react-router";

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
  type ParkingSession,
  type ParkingZone,
} from "../../../api";

import { Card } from "../../../components/common/Page";

// ==========================================================
// Types
// ==========================================================

type SessionFilter = "ALL" | "ACTIVE" | "COMPLETED";

type NormalizedStatus =
  | "ACTIVE"
  | "COMPLETED"
  | "CANCELLED"
  | "PENDING"
  | "UNKNOWN";

interface BackendQuote {
  amount?: number | string | null;
  total_amount?: number | string | null;
  calculated_amount?: number | string | null;
  current_amount?: number | string | null;
  outstanding_amount?: number | string | null;
  payable_amount?: number | string | null;
  currency?: string | null;
  duration_minutes?: number | null;

  [key: string]: any;
}

// ==========================================================
// Helpers
// ==========================================================

function normalizeStatus(value: string | null | undefined): NormalizedStatus {
  const status = String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");

  if (status === "ACTIVE" || status === "CHECKED_IN" || status === "CHECK_IN") {
    return "ACTIVE";
  }

  if (
    status === "COMPLETED" ||
    status === "CHECKED_OUT" ||
    status === "CHECK_OUT"
  ) {
    return "COMPLETED";
  }

  if (status === "CANCELLED" || status === "CANCELED") {
    return "CANCELLED";
  }

  if (status === "PENDING") {
    return "PENDING";
  }

  return "UNKNOWN";
}

function isActive(session: ParkingSession): boolean {
  return normalizeStatus(session.status) === "ACTIVE";
}

function getCheckIn(session: ParkingSession): string | null {
  return session.entry_time ?? null;
}

function getCheckOut(session: ParkingSession): string | null {
  return session.exit_time ?? null;
}

function getStoredAmount(session: ParkingSession): number | null {
  const value = Number(session.calculated_amount);

  return Number.isFinite(value) ? value : null;
}

function getPaidAmount(session: ParkingSession): number | null {
  const value = Number(session.paid_amount);

  return Number.isFinite(value) ? value : null;
}

function getDuration(session: ParkingSession, now = Date.now()): number | null {
  if (
    session.duration_minutes !== null &&
    session.duration_minutes !== undefined &&
    Number.isFinite(Number(session.duration_minutes))
  ) {
    /*
     * For completed sessions the backend duration
     * is authoritative.
     *
     * For active sessions we continue to display
     * elapsed time based on entry_time.
     */
    if (!isActive(session)) {
      return Number(session.duration_minutes);
    }
  }

  if (!session.entry_time) {
    return null;
  }

  const start = new Date(session.entry_time).getTime();

  if (!Number.isFinite(start)) {
    return null;
  }

  const end = isActive(session)
    ? now
    : session.exit_time
      ? new Date(session.exit_time).getTime()
      : now;

  if (!Number.isFinite(end)) {
    return null;
  }

  return Math.max(0, Math.floor((end - start) / 60000));
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
  value: number | string | null | undefined,
  currency = "KES",
): string {
  if (value === null || value === undefined || value === "") {
    return "—";
  }

  const amount = Number(value);

  if (!Number.isFinite(amount)) {
    return "—";
  }

  try {
    return new Intl.NumberFormat("en-KE", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${currency} ${amount.toFixed(2)}`;
  }
}

function formatDuration(minutes: number | null): string {
  if (minutes === null) {
    return "—";
  }

  const rounded = Math.max(0, Math.floor(minutes));

  if (rounded < 60) {
    return `${rounded} min`;
  }

  const hours = Math.floor(rounded / 60);

  const remaining = rounded % 60;

  return remaining === 0 ? `${hours}h` : `${hours}h ${remaining}m`;
}

function humanize(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }

  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function extractSessions(payload: any): ParkingSession[] {
  if (Array.isArray(payload)) {
    return payload;
  }

  if (Array.isArray(payload?.items)) {
    return payload.items;
  }

  if (Array.isArray(payload?.data)) {
    return payload.data;
  }

  if (Array.isArray(payload?.results)) {
    return payload.results;
  }

  return [];
}

function unwrapPayload<T = any>(payload: any): T {
  if (
    payload?.data &&
    typeof payload.data === "object" &&
    !Array.isArray(payload.data)
  ) {
    return payload.data;
  }

  return payload as T;
}

function extractQuoteAmount(quote: BackendQuote): number | null {
  /*
   * Accept the common names used by the
   * pricing/quote response while keeping
   * the calculation entirely on the backend.
   *
   * Priority:
   * outstanding/payable/current amount,
   * then total/calculated amount.
   */
  const candidates = [
    quote.outstanding_amount,
    quote.payable_amount,
    quote.current_amount,
    quote.total_amount,
    quote.calculated_amount,
    quote.amount,
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

// ==========================================================
// Status Badge
// ==========================================================

function StatusBadge({ status }: { status: NormalizedStatus }) {
  if (status === "ACTIVE") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-500" />
        ACTIVE
      </span>
    );
  }

  if (status === "COMPLETED") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-600">
        <CheckCircle2 size={13} />
        COMPLETED
      </span>
    );
  }

  if (status === "CANCELLED") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-red-50 px-3 py-1 text-xs font-bold text-red-600">
        CANCELLED
      </span>
    );
  }

  if (status === "PENDING") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1 text-xs font-bold text-amber-700">
        <Clock3 size={13} />
        PENDING
      </span>
    );
  }

  return (
    <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-500">
      {humanize(status)}
    </span>
  );
}

// ==========================================================
// Summary Metric
// ==========================================================

function SummaryMetric({
  label,
  value,
  description,
  icon,
  iconClass,
}: {
  label: string;
  value: string | number;
  description: string;
  icon: React.ReactNode;
  iconClass: string;
}) {
  return (
    <div className="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-slate-400">
            {label}
          </div>

          <div className="mt-3 text-3xl font-black text-slate-950">{value}</div>

          <div className="mt-1 text-sm text-slate-500">{description}</div>
        </div>

        <div
          className={`grid h-11 w-11 shrink-0 place-items-center rounded-2xl ${iconClass}`}
        >
          {icon}
        </div>
      </div>
    </div>
  );
}

// ==========================================================
// Active Session Card
// ==========================================================

function ActiveSessionCard({
  session,
  facility,
  zone,
  bay,
  liveNow,
  currentAmount,
  quoteLoading,
  quoteCurrency,
  onView,
  onPay,
}: {
  session: ParkingSession;
  facility: ParkingFacility | null;
  zone: ParkingZone | null;
  bay: ParkingBay | null;
  liveNow: number;
  currentAmount: number | null;
  quoteLoading: boolean;
  quoteCurrency: string;
  onView: () => void;
  onPay: () => void;
}) {
  const duration = getDuration(session, liveNow);

  const facilityLocation = [facility?.address, facility?.city, facility?.county]
    .filter(
      (value) =>
        value !== null && value !== undefined && String(value).trim() !== "",
    )
    .join(", ");

  return (
    <section className="overflow-hidden rounded-3xl bg-[#071a2d] text-white shadow-sm">
      <div className="p-6 sm:p-7">
        {/* ==================================================
            Header
        ================================================== */}

        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[.2em] text-emerald-300">
              <Activity size={16} />
              Active Parking Session
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-3">
              <h2 className="text-2xl font-black tracking-tight sm:text-3xl">
                {session.session_number ?? `Session #${session.id}`}
              </h2>

              <StatusBadge status="ACTIVE" />
            </div>

            <p className="mt-2 text-sm text-slate-300">
              Your latest active parking session.
            </p>
          </div>
        </div>

        {/* ==================================================
            Main Session Information
        ================================================== */}

        <div className="mt-7 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10 xl:col-span-1">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <MapPin size={15} />
              Facility
            </div>

            <div className="mt-2 text-base font-black text-white">
              {facility?.name ?? "Facility information unavailable"}
            </div>

            {facility?.code && (
              <div className="mt-1 text-xs font-bold uppercase tracking-wide text-emerald-300">
                {facility.code}
              </div>
            )}

            {facilityLocation && (
              <div className="mt-2 text-xs leading-5 text-slate-400">
                {facilityLocation}
              </div>
            )}
          </div>

          <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <CarFront size={15} />
              Vehicle
            </div>

            <div className="mt-2 text-base font-black">
              {session.vehicle_registration ?? "—"}
            </div>

            <div className="mt-1 text-xs text-slate-400">
              {humanize(session.vehicle_type)}
            </div>
          </div>

          <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <MapPin size={15} />
              Parking Zone
            </div>

            <div className="mt-2 text-base font-black">
              {zone?.name ?? "Zone information unavailable"}
            </div>

            {zone?.code && (
              <div className="mt-1 text-xs font-bold uppercase tracking-wide text-emerald-300">
                {zone.code}
              </div>
            )}

            {zone?.zone_type && (
              <div className="mt-1 text-xs text-slate-400">
                {humanize(zone.zone_type)}
              </div>
            )}
          </div>

          <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <ParkingCircle size={15} />
              Parking Bay
            </div>

            <div className="mt-2 text-base font-black">
              {bay?.bay_number ?? `Bay #${session.parking_bay_id}`}
            </div>

            {bay?.code && (
              <div className="mt-1 text-xs font-bold uppercase tracking-wide text-emerald-300">
                {bay.code}
              </div>
            )}

            {bay?.bay_type && (
              <div className="mt-1 text-xs text-slate-400">
                {humanize(bay.bay_type)}
              </div>
            )}
          </div>

          <div className="rounded-2xl bg-white/5 p-4 ring-1 ring-white/10">
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              <Timer size={15} />
              Duration
            </div>

            <div className="mt-2 text-base font-black">
              {formatDuration(duration)}
            </div>

            <div className="mt-1 text-xs text-slate-400">
              Started {formatTime(getCheckIn(session))}
            </div>
          </div>
        </div>

        {/* ==================================================
            Current Parking Amount
        ================================================== */}

        <div className="mt-4 rounded-2xl bg-emerald-400/10 p-5 ring-1 ring-emerald-300/20">
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div>
              <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-[.15em] text-emerald-300">
                <CreditCardIcon />
                Current Outstanding Bill
              </div>

              <div className="mt-2 text-3xl font-black tracking-tight text-white">
                {quoteLoading
                  ? "Updating..."
                  : currentAmount === null
                    ? "—"
                    : formatCurrency(currentAmount, quoteCurrency)}
              </div>

              <p className="mt-1 text-xs leading-5 text-slate-400">
                Current outstanding bill calculated by the SmartPark AI pricing
                engine.
              </p>
            </div>

            <div className="rounded-xl bg-white/5 px-4 py-3 text-xs text-slate-400 ring-1 ring-white/10">
              <div className="font-bold text-slate-300">Pricing Status</div>

              <div className="mt-1">
                {quoteLoading
                  ? "Retrieving latest quote..."
                  : currentAmount !== null
                    ? "Latest Quote"
                    : "Current quote unavailable"}
              </div>
            </div>
          </div>
        </div>

        {/* ==================================================
            Session Info Strip
        ================================================== */}

        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl bg-white/5 px-4 py-3 ring-1 ring-white/10">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Check-in
            </div>

            <div className="mt-1 text-sm font-bold text-white">
              {formatDateTime(getCheckIn(session))}
            </div>
          </div>

          <div className="rounded-2xl bg-white/5 px-4 py-3 ring-1 ring-white/10">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Billing Type
            </div>

            <div className="mt-1 text-sm font-bold text-white">
              {humanize(session.billing_type)}
            </div>
          </div>

          <div className="rounded-2xl bg-white/5 px-4 py-3 ring-1 ring-white/10">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
              Session Source
            </div>

            <div className="mt-1 text-sm font-bold text-white">
              {humanize(session.session_source)}
            </div>
          </div>
        </div>

        {/* ==================================================
            Information Message
        ================================================== */}

        <div className="mt-5 rounded-2xl border border-white/10 bg-white/5 p-4">
          <div className="flex items-start gap-3">
            <Clock3 size={18} className="mt-0.5 shrink-0 text-emerald-300" />

            <div>
              <div className="text-sm font-bold">Parking session is active</div>

              <p className="mt-1 text-xs leading-5 text-slate-400">
                The displayed duration and outstanding bill updates periodically
                while you remain parked.
              </p>
            </div>
          </div>
        </div>

        {/* ==================================================
            Actions
        ================================================== */}

        <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-end">
          <button
            type="button"
            onClick={onView}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/15 bg-white/5 px-5 py-3 text-sm font-bold text-white transition hover:bg-white/10"
          >
            View Session
            <ArrowRight size={16} />
          </button>

          <button
            type="button"
            onClick={onPay}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-500 px-5 py-3 text-sm font-bold text-white transition hover:bg-emerald-400"
          >
            Pay & Check Out
            <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </section>
  );
}

// ==========================================================
// Small Credit Card Icon
// ==========================================================

function CreditCardIcon() {
  return (
    <svg
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="2" y="5" width="20" height="14" rx="2" />
      <line x1="2" y1="10" x2="22" y2="10" />
    </svg>
  );
}

// ==========================================================
// Session Row
// ==========================================================

function SessionRow({
  session,
  onView,
}: {
  session: ParkingSession;
  onView: () => void;
}) {
  const status = normalizeStatus(session.status);

  const storedAmount = getStoredAmount(session);

  const paidAmount = getPaidAmount(session);

  const duration = getDuration(session);

  // ----------------------------------------------------------
  // Current amount for this specific active session
  // ----------------------------------------------------------
  const [rowAmount, setRowAmount] = useState<number | null>(storedAmount);
  const [rowCurrency, setRowCurrency] = useState("KES");
  const [rowQuoteLoading, setRowQuoteLoading] = useState(false);

  const loadRowQuote = useCallback(async () => {
    if (!isActive(session) || !session.id) {
      setRowAmount(storedAmount);
      return;
    }

    setRowQuoteLoading(true);

    try {
      const response = await api.get<
        | BackendQuote
        | { data?: BackendQuote; quote?: BackendQuote; result?: BackendQuote }
      >(`/parking-sessions/${encodeURIComponent(session.id)}/quote`);

      const responseBody = response.data;

      const quote =
        responseBody &&
        typeof responseBody === "object" &&
        ("data" in responseBody ||
          "quote" in responseBody ||
          "result" in responseBody)
          ? ((responseBody.data ??
              responseBody.quote ??
              responseBody.result ??
              responseBody) as BackendQuote)
          : (responseBody as BackendQuote);

      const amount = extractQuoteAmount(quote);

      setRowAmount(amount);
      setRowCurrency(quote.currency ?? "KES");
    } catch (err) {
      console.warn(
        "[SmartPark Sessions] Current quote unavailable for session row:",
        err,
      );

      // Preserve the existing session amount if the live quote is unavailable.
      setRowAmount(storedAmount);
      setRowCurrency("KES");
    } finally {
      setRowQuoteLoading(false);
    }
  }, [session, storedAmount]);

  useEffect(() => {
    void loadRowQuote();

    if (!isActive(session)) {
      return;
    }

    const interval = window.setInterval(() => {
      void loadRowQuote();
    }, 60_000);

    return () => window.clearInterval(interval);
  }, [loadRowQuote, session]);

  return (
    <div className="border-b border-slate-100 px-5 py-5 last:border-0 sm:px-6">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex min-w-0 items-start gap-4">
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-slate-100 text-slate-500">
            <ParkingCircle size={20} />
          </div>

          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={onView}
                className="truncate text-left text-sm font-bold text-slate-900 hover:text-emerald-600"
              >
                {session.session_number ?? `Session #${session.id}`}
              </button>

              <StatusBadge status={status} />
            </div>

            <div className="mt-1 text-sm font-semibold text-slate-700">
              Parking Bay #{session.parking_bay_id}
            </div>

            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-500">
              <span className="inline-flex items-center gap-1">
                <CarFront size={13} />
                {session.vehicle_registration}
              </span>

              <span className="inline-flex items-center gap-1">
                <Clock3 size={13} />
                {formatDateTime(session.entry_time)}
              </span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4 xl:min-w-[560px]">
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Check-in
            </div>

            <div className="mt-1 text-sm font-bold text-slate-700">
              {formatTime(session.entry_time)}
            </div>
          </div>

          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Check-out
            </div>

            <div className="mt-1 text-sm font-bold text-slate-700">
              {formatTime(session.exit_time)}
            </div>
          </div>

          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
              Duration
            </div>

            <div className="mt-1 text-sm font-bold text-slate-700">
              {formatDuration(duration)}
            </div>
          </div>

          <div className="flex items-end justify-between gap-3 sm:items-center">
            <div>
              <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                Amount
              </div>

              <div className="mt-1 text-sm font-black text-slate-900">
                {rowQuoteLoading && rowAmount === null
                  ? "Updating..."
                  : rowAmount === null
                    ? "—"
                    : formatCurrency(rowAmount, rowCurrency)}
              </div>

              {paidAmount !== null && (
                <div className="mt-0.5 text-[11px] text-slate-400">
                  Paid: {formatCurrency(paidAmount)}
                </div>
              )}
            </div>

            <button
              type="button"
              onClick={onView}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-slate-200 text-slate-500 transition hover:border-emerald-200 hover:bg-emerald-50 hover:text-emerald-600"
              title="View session"
              aria-label={`View ${
                session.session_number ?? `session ${session.id}`
              }`}
            >
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ==========================================================
// Main Component
// ==========================================================

export default function ParkingSessions() {
  const { user } = useAuth();

  const navigate = useNavigate();

  // --------------------------------------------------------
  // Sessions
  // --------------------------------------------------------

  const [activeSessions, setActiveSessions] = useState<ParkingSession[]>([]);

  const [completedSessions, setCompletedSessions] = useState<ParkingSession[]>(
    [],
  );

  // --------------------------------------------------------
  // Parking metadata
  // --------------------------------------------------------

  const [facilities, setFacilities] = useState<ParkingFacility[]>([]);

  const [zones, setZones] = useState<ParkingZone[]>([]);

  const [bays, setBays] = useState<ParkingBay[]>([]);

  // --------------------------------------------------------
  // Current active-session pricing quote
  // --------------------------------------------------------

  const [currentAmount, setCurrentAmount] = useState<number | null>(null);

  const [quoteCurrency, setQuoteCurrency] = useState("KES");

  const [quoteLoading, setQuoteLoading] = useState(false);

  // --------------------------------------------------------
  // UI
  // --------------------------------------------------------

  const [loading, setLoading] = useState(true);

  const [refreshing, setRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [searchTerm, setSearchTerm] = useState("");

  const [filter, setFilter] = useState<SessionFilter>("ALL");

  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const [liveNow, setLiveNow] = useState(() => Date.now());

  // ========================================================
  // Live display clock
  // ========================================================

  useEffect(() => {
    if (activeSessions.length === 0) {
      return;
    }

    const interval = window.setInterval(() => {
      setLiveNow(Date.now());
    }, 30_000);

    return () => window.clearInterval(interval);
  }, [activeSessions.length]);

  // ========================================================
  // Load Parking Metadata
  // ========================================================

  const loadParkingMetadata = useCallback(async () => {
    /*
     * Load the parking hierarchy using a backend-safe page size.
     *
     * The session hierarchy is:
     *
     *     Parking Session
     *          ↓ parking_bay_id
     *     Parking Bay
     *          ↓ zone_id
     *     Parking Zone
     *          ↓ facility_id
     *     Parking Facility
     *
     * The previous implementation requested 500 / 1000 / 2000
     * records. If the backend rejects an oversized limit, Promise.allSettled
     * leaves the metadata arrays empty and the UI falls back to
     * "information unavailable" even though the records exist.
     *
     * 100 is sufficient for the current data set and is also consistent
     * with the facilities API default.
     */
    const [facilitiesResult, zonesResult, baysResult] =
      await Promise.allSettled([
        parkingFacilitiesApi.list(0, 100),
        parkingZonesApi.list(0, 100),
        parkingBaysApi.list(0, 100),
      ]);

    if (facilitiesResult.status === "fulfilled") {
      setFacilities(facilitiesResult.value.items ?? []);
    } else {
      console.warn(
        "[SmartPark Sessions] Failed to load parking facilities:",
        facilitiesResult.reason,
      );
    }

    if (zonesResult.status === "fulfilled") {
      setZones(zonesResult.value.items ?? []);
    } else {
      console.warn(
        "[SmartPark Sessions] Failed to load parking zones:",
        zonesResult.reason,
      );
    }

    if (baysResult.status === "fulfilled") {
      setBays(baysResult.value.items ?? []);
    } else {
      console.warn(
        "[SmartPark Sessions] Failed to load parking bays:",
        baysResult.reason,
      );
    }
  }, []);

  // ========================================================
  // Load Sessions
  // ========================================================

  const loadSessions = useCallback(
    async (manualRefresh = false) => {
      if (manualRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setError(null);

      try {
        const [activeResult, completedResult] = await Promise.allSettled([
          parkingSessionsApi.active(),

          api.get<any>("/parking-sessions/completed"),
        ]);

        const failures: string[] = [];

        // --------------------------------------------------
        // Active sessions
        // --------------------------------------------------

        if (activeResult.status === "fulfilled") {
          const sessions = activeResult.value.items ?? [];

          // The authenticated active-sessions endpoint already returns
          // the driver's active sessions. Do not apply a second customer_id
          // filter here, as it can incorrectly hide valid active sessions.
          setActiveSessions(sessions);
        } else {
          failures.push("active sessions");
        }

        // --------------------------------------------------
        // Completed sessions
        // --------------------------------------------------

        if (completedResult.status === "fulfilled") {
          const payload = unwrapPayload(completedResult.value.data);
          const sessions = extractSessions(payload);

          const driverSessions = user?.id
            ? sessions.filter(
                (session) =>
                  session.customer_id === null ||
                  session.customer_id === undefined ||
                  String(session.customer_id) === String(user.id),
              )
            : sessions;

          setCompletedSessions(driverSessions);
        } else if (user?.id) {
          /*
           * Fallback for the current backend response-model mismatch:
           * /parking-sessions/completed can fail after a paid checkout
           * because completed sessions carry payment_status = PAID while
           * ParkingSessionListResponse currently rejects that enum value.
           *
           * Customer payment history still exposes parking_session_id,
           * so use it to retrieve the customer's completed sessions.
           * This keeps the dashboard functional without changing the
           * payment/session business logic.
           */
          try {
            const paymentResponse = await api.get<any>(
              `/payments/customer/${encodeURIComponent(user.id)}?limit=100&offset=0`,
            );

            const paymentPayload = paymentResponse.data;
            const payments = Array.isArray(paymentPayload)
              ? paymentPayload
              : Array.isArray(paymentPayload?.items)
                ? paymentPayload.items
                : Array.isArray(paymentPayload?.data)
                  ? paymentPayload.data
                  : [];

            const sessionIds = Array.from(
              new Set(
                payments
                  .map((payment: any) => payment?.parking_session_id)
                  .filter(
                    (sessionId: any) =>
                      sessionId !== null &&
                      sessionId !== undefined &&
                      String(sessionId).trim() !== "",
                  )
                  .map((sessionId: any) => String(sessionId)),
              ),
            );

            const sessionResults = await Promise.allSettled(
              sessionIds.map((sessionId) =>
                api.get<any>(
                  `/parking-sessions/${encodeURIComponent(sessionId)}`,
                ),
              ),
            );

            const recoveredSessions = sessionResults
              .filter(
                (result): result is PromiseFulfilledResult<{ data: any }> =>
                  result.status === "fulfilled",
              )
              .map((result) => {
                const payload = unwrapPayload<any>(result.value.data);
                return payload;
              })
              .filter(
                (session: any) =>
                  session &&
                  normalizeStatus(session.status) === "COMPLETED" &&
                  (session.customer_id === null ||
                    session.customer_id === undefined ||
                    String(session.customer_id) === String(user.id)),
              );

            setCompletedSessions(recoveredSessions);
          } catch (fallbackError) {
            console.warn(
              "[SmartPark Sessions] Completed-session fallback failed:",
              fallbackError,
            );
            failures.push("completed sessions");
          }
        } else {
          failures.push("completed sessions");
        }

        if (failures.length === 2) {
          const reason =
            activeResult.status === "rejected"
              ? activeResult.reason
              : completedResult.reason;

          throw reason;
        }

        if (failures.length > 0) {
          setError(
            `Some session information could not be loaded: ${failures.join(
              " and ",
            )}.`,
          );
        }

        setLiveNow(Date.now());

        setLastUpdated(new Date());
      } catch (err) {
        console.error("[SmartPark Sessions] Failed to load sessions:", err);

        setError(getApiErrorMessage(err));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [user?.id],
  );

  // ========================================================
  // Initial Load
  // ========================================================

  useEffect(() => {
    void loadSessions();
    void loadParkingMetadata();
  }, [loadSessions, loadParkingMetadata]);

  // ========================================================
  // Periodic Session Refresh
  // ========================================================

  useEffect(() => {
    if (activeSessions.length === 0) {
      return;
    }

    const interval = window.setInterval(() => {
      void loadSessions(true);
    }, 60_000);

    return () => window.clearInterval(interval);
  }, [activeSessions.length, loadSessions]);

  // ========================================================
  // Resolve Metadata
  // ========================================================

  const facilityMap = useMemo(() => {
    const map = new Map<string, ParkingFacility>();

    facilities.forEach((facility) => {
      map.set(String(facility.id), facility);
    });

    return map;
  }, [facilities]);

  const zoneMap = useMemo(() => {
    const map = new Map<string, ParkingZone>();

    zones.forEach((zone) => {
      map.set(String(zone.id), zone);
    });

    return map;
  }, [zones]);

  const bayMap = useMemo(() => {
    const map = new Map<string, ParkingBay>();

    bays.forEach((bay) => {
      map.set(String(bay.id), bay);
    });

    return map;
  }, [bays]);

  /*
   * Resolve parking metadata defensively.
   *
   * The backend can serialise PostgreSQL integer IDs as numbers or strings.
   * Comparing those values directly can make valid metadata appear missing.
   * We therefore normalise IDs to strings before looking them up.
   *
   * We also support direct session-level zone/facility IDs when they are
   * present in the backend response, while retaining the normal relationship:
   * session -> bay -> zone -> facility.
   */
  const getSessionMetadataIds = useCallback((session: ParkingSession) => {
    const rawSession = session as ParkingSession & {
      parking_zone_id?: number | string | null;
      zone_id?: number | string | null;
      parking_facility_id?: number | string | null;
      facility_id?: number | string | null;
    };

    return {
      zoneId: rawSession.parking_zone_id ?? rawSession.zone_id ?? null,
      facilityId:
        rawSession.parking_facility_id ?? rawSession.facility_id ?? null,
    };
  }, []);

  const resolveBay = useCallback(
    (session: ParkingSession) => {
      if (
        session.parking_bay_id === null ||
        session.parking_bay_id === undefined
      ) {
        return null;
      }

      return bayMap.get(String(session.parking_bay_id)) ?? null;
    },
    [bayMap],
  );

  const resolveZone = useCallback(
    (session: ParkingSession) => {
      const directIds = getSessionMetadataIds(session);

      if (directIds.zoneId !== null && directIds.zoneId !== undefined) {
        const directZone = zoneMap.get(String(directIds.zoneId));

        if (directZone) {
          return directZone;
        }
      }

      const bay = resolveBay(session);

      if (!bay) {
        return null;
      }

      return zoneMap.get(String(bay.zone_id)) ?? null;
    },
    [getSessionMetadataIds, resolveBay, zoneMap],
  );

  const resolveFacility = useCallback(
    (session: ParkingSession) => {
      const directIds = getSessionMetadataIds(session);

      if (directIds.facilityId !== null && directIds.facilityId !== undefined) {
        const directFacility = facilityMap.get(String(directIds.facilityId));

        if (directFacility) {
          return directFacility;
        }
      }

      const zone = resolveZone(session);

      if (!zone) {
        return null;
      }

      return facilityMap.get(String(zone.facility_id)) ?? null;
    },
    [facilityMap, getSessionMetadataIds, resolveZone],
  );

  // ========================================================
  // Most Recent Active Session
  // ========================================================

  const activeSession = useMemo(() => {
    const active = activeSessions.filter(isActive);

    if (active.length === 0) {
      return null;
    }

    return [...active].sort((a, b) => {
      const aTime = new Date(a.entry_time).getTime();

      const bTime = new Date(b.entry_time).getTime();

      return bTime - aTime;
    })[0];
  }, [activeSessions]);

  // ========================================================
  // Other Active Sessions
  // ========================================================

  /*
   * The large navy card above is reserved for the single
   * most recent active session.
   *
   * This section contains every other currently active
   * session, ordered from newest to oldest.
   *
   * The first/most recent active session is explicitly
   * excluded so it cannot appear twice on the page.
   */
  const otherActiveSessions = useMemo(() => {
    const active = activeSessions.filter(isActive).sort((a, b) => {
      const aTime = new Date(a.entry_time).getTime();

      const bTime = new Date(b.entry_time).getTime();

      return bTime - aTime;
    });

    if (active.length <= 1) {
      return [];
    }

    return active.slice(1);
  }, [activeSessions]);

  // ========================================================
  // Current Pricing Engine Quote
  // ========================================================

  const loadCurrentQuote = useCallback(async (session: ParkingSession) => {
    if (!session.id) {
      setCurrentAmount(null);

      return;
    }

    setQuoteLoading(true);

    try {
      const response = await api.get<
        | BackendQuote
        | { data?: BackendQuote; quote?: BackendQuote; result?: BackendQuote }
      >(`/parking-sessions/${encodeURIComponent(session.id)}/quote`);

      const responseBody = response.data;

      const quote =
        responseBody &&
        typeof responseBody === "object" &&
        ("data" in responseBody ||
          "quote" in responseBody ||
          "result" in responseBody)
          ? ((responseBody.data ??
              responseBody.quote ??
              responseBody.result ??
              responseBody) as BackendQuote)
          : (responseBody as BackendQuote);

      const amount = extractQuoteAmount(quote);

      setCurrentAmount(amount);

      setQuoteCurrency(quote.currency ?? "KES");
    } catch (err) {
      console.warn(
        "[SmartPark Sessions] Current pricing-engine quote unavailable:",
        err,
      );

      const storedAmount = getStoredAmount(session);

      if (storedAmount !== null && storedAmount > 0) {
        setCurrentAmount(storedAmount);
      } else {
        setCurrentAmount(null);
      }

      setQuoteCurrency("KES");
    } finally {
      setQuoteLoading(false);
    }
  }, []);

  // ========================================================
  // Load quote whenever active session changes
  // ========================================================

  useEffect(() => {
    if (!activeSession) {
      setCurrentAmount(null);

      return;
    }

    void loadCurrentQuote(activeSession);
  }, [activeSession, loadCurrentQuote]);

  // ========================================================
  // Refresh current quote frequently
  // ========================================================

  useEffect(() => {
    if (!activeSession) {
      return;
    }

    const interval = window.setInterval(() => {
      void loadCurrentQuote(activeSession);
    }, 60_000);

    return () => window.clearInterval(interval);
  }, [activeSession, loadCurrentQuote]);

  // ========================================================
  // All Sessions
  // ========================================================

  const allSessions = useMemo(() => {
    const map = new Map<number, ParkingSession>();

    [...activeSessions, ...completedSessions].forEach((session) => {
      map.set(session.id, session);
    });

    return Array.from(map.values());
  }, [activeSessions, completedSessions]);

  // ========================================================
  // Filtered Sessions
  // ========================================================

  const filteredSessions = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();

    let sessions = [...allSessions];

    if (filter === "ACTIVE") {
      sessions = sessions.filter(isActive);
    }

    if (filter === "COMPLETED") {
      sessions = sessions.filter(
        (session) => normalizeStatus(session.status) === "COMPLETED",
      );
    }

    if (query) {
      const terms = query.split(/\s+/).filter(Boolean);

      sessions = sessions.filter((session) => {
        const bay = resolveBay(session);

        const zone = resolveZone(session);

        const facility = resolveFacility(session);

        const haystack = [
          session.id,
          session.session_number,
          session.vehicle_registration,
          session.vehicle_type,
          session.parking_bay_id,
          session.customer_id,
          session.payment_status,
          session.billing_type,
          session.session_source,

          bay?.bay_number,
          bay?.code,

          zone?.name,
          zone?.code,

          facility?.name,
          facility?.code,
          facility?.city,
          facility?.county,
          facility?.address,
        ]
          .filter((value) => value !== null && value !== undefined)
          .join(" ")
          .toLowerCase();

        return terms.every((term) => haystack.includes(term));
      });
    }

    return sessions.sort((a, b) => {
      const aDate = new Date(a.entry_time || a.created_at).getTime();

      const bDate = new Date(b.entry_time || b.created_at).getTime();

      return bDate - aDate;
    });
  }, [
    allSessions,
    filter,
    searchTerm,
    resolveBay,
    resolveZone,
    resolveFacility,
  ]);

  // ========================================================
  // Summary Metrics
  // ========================================================

  const activeCount = activeSessions.filter(isActive).length;

  const completedCount = completedSessions.filter(
    (session) => normalizeStatus(session.status) === "COMPLETED",
  ).length;

  const totalParkingMinutes = completedSessions.reduce(
    (total, session) => total + (getDuration(session) ?? 0),
    0,
  );

  const totalSpend = completedSessions.reduce(
    (total, session) => total + (getStoredAmount(session) ?? 0),
    0,
  );

  // ========================================================
  // Navigation
  // ========================================================

  const handleViewSession = (session: ParkingSession) => {
    navigate(`/sessions/${session.id}`);
  };

  const handlePayAndCheckOut = (session: ParkingSession) => {
    const params = new URLSearchParams();

    params.set("checkout", "1");

    params.set("sessionId", String(session.id));

    navigate(`/payments?${params.toString()}`);
  };

  // ========================================================
  // Render
  // ========================================================

  return (
    <div className="space-y-6">
      {/* ====================================================
          PAGE HEADER
      ==================================================== */}

      <section>
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
              <ParkingCircle size={25} />
            </div>

            <div>
              <h1 className="text-3xl font-black text-slate-950">
                Parking Sessions
              </h1>

              <p className="mt-1 text-sm text-slate-500">
                Track your active and completed parking sessions.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {lastUpdated && (
              <span className="hidden text-xs text-slate-400 sm:block">
                Updated {formatTime(lastUpdated.toISOString())}
              </span>
            )}

            <button
              type="button"
              onClick={() => {
                void loadSessions(true);

                void loadParkingMetadata();
              }}
              disabled={refreshing}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw
                size={16}
                className={refreshing ? "animate-spin" : ""}
              />
              Refresh
            </button>
          </div>
        </div>
      </section>

      {/* ====================================================
          ERROR
      ==================================================== */}

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-red-200 bg-red-50 p-4 text-red-700">
          <AlertCircle size={19} className="mt-0.5 shrink-0" />

          <div className="min-w-0 flex-1">
            <div className="font-bold">Session Service Message</div>

            <div className="mt-1 text-sm">{error}</div>
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

      {/* ====================================================
          REDESIGNED ACTIVE SESSION
      ==================================================== */}

      {activeSession && (
        <ActiveSessionCard
          session={activeSession}
          facility={resolveFacility(activeSession)}
          zone={resolveZone(activeSession)}
          bay={resolveBay(activeSession)}
          liveNow={liveNow}
          currentAmount={currentAmount}
          quoteLoading={quoteLoading}
          quoteCurrency={quoteCurrency}
          onView={() => handleViewSession(activeSession)}
          onPay={() => handlePayAndCheckOut(activeSession)}
        />
      )}

      {/* ====================================================
          SUMMARY METRICS
      ==================================================== */}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryMetric
          label="Active Sessions"
          value={activeCount}
          description="Currently parked"
          icon={<Activity size={21} />}
          iconClass="bg-emerald-50 text-emerald-600"
        />

        <SummaryMetric
          label="Completed"
          value={completedCount}
          description="Finished parking sessions"
          icon={<CheckCircle2 size={21} />}
          iconClass="bg-blue-50 text-blue-600"
        />

        <SummaryMetric
          label="Parking Time"
          value={formatDuration(totalParkingMinutes)}
          description="Across completed sessions"
          icon={<Clock3 size={21} />}
          iconClass="bg-violet-50 text-violet-600"
        />

        <SummaryMetric
          label="Total Spend"
          value={formatCurrency(totalSpend)}
          description="Completed parking"
          icon={<ParkingCircle size={21} />}
          iconClass="bg-amber-50 text-amber-600"
        />
      </div>

      {/* ====================================================
          SEARCH
      ==================================================== */}

      <Card
        title="Find a parking session"
        sub="Search by session number, vehicle, facility, zone or parking bay."
      >
        <div className="space-y-4">
          <div className="relative">
            <Search
              size={19}
              className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"
            />

            <input
              type="text"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Session number, vehicle, facility, zone, bay..."
              className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-11 pr-4 text-sm text-slate-700 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            {(
              [
                ["ALL", `All (${allSessions.length})`],
                ["ACTIVE", `Active (${activeCount})`],
                ["COMPLETED", `Completed (${completedCount})`],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                className={`rounded-xl px-4 py-2.5 text-sm font-bold transition ${
                  filter === value
                    ? "bg-[#071a2d] text-white"
                    : "bg-slate-50 text-slate-600 hover:bg-slate-100"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      </Card>

      {/* ====================================================
          OTHER ACTIVE SESSIONS
      ==================================================== */}

      <Card
        title="Other Active Sessions"
        sub="All other currently active parking sessions, newest first."
      >
        {loading ? (
          <div className="flex min-h-[300px] items-center justify-center">
            <div className="text-center">
              <RefreshCw
                size={28}
                className="mx-auto animate-spin text-emerald-600"
              />

              <p className="mt-3 text-sm font-semibold text-slate-500">
                Loading your active parking sessions...
              </p>
            </div>
          </div>
        ) : otherActiveSessions.length === 0 ? (
          <div className="flex min-h-[220px] flex-col items-center justify-center px-6 text-center">
            <div className="grid h-16 w-16 place-items-center rounded-3xl bg-slate-100 text-slate-400">
              <ParkingCircle size={30} />
            </div>

            <h3 className="mt-5 text-lg font-black text-slate-800">
              No other active sessions
            </h3>

            <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
              The most recent active parking session is displayed in the active
              session card above.
            </p>
          </div>
        ) : (
          <div>
            {otherActiveSessions.map((session) => (
              <SessionRow
                key={session.id}
                session={session}
                onView={() => handleViewSession(session)}
              />
            ))}
          </div>
        )}
      </Card>

      {/* ====================================================
          SESSION HISTORY
      ==================================================== */}

      <Card
        title="Session History"
        sub="Your parking sessions, filtered by the selection above."
      >
        {loading ? (
          <div className="flex min-h-[220px] items-center justify-center">
            <div className="text-center">
              <RefreshCw
                size={28}
                className="mx-auto animate-spin text-emerald-600"
              />
              <p className="mt-3 text-sm font-semibold text-slate-500">
                Loading parking session history...
              </p>
            </div>
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="flex min-h-[220px] flex-col items-center justify-center px-6 text-center">
            <div className="grid h-16 w-16 place-items-center rounded-3xl bg-slate-100 text-slate-400">
              <ParkingCircle size={30} />
            </div>

            <h3 className="mt-5 text-lg font-black text-slate-800">
              {filter === "COMPLETED"
                ? "No completed parking sessions"
                : filter === "ACTIVE"
                  ? "No active parking sessions"
                  : "No parking sessions found"}
            </h3>

            <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
              {filter === "COMPLETED"
                ? "Completed sessions will appear here after successful checkout."
                : filter === "ACTIVE"
                  ? "Currently active parking sessions will appear here."
                  : "Your parking session history will appear here."}
            </p>
          </div>
        ) : (
          <div>
            {filteredSessions.map((session) => (
              <SessionRow
                key={session.id}
                session={session}
                onView={() => handleViewSession(session)}
              />
            ))}
          </div>
        )}
      </Card>

      {/* ====================================================
          NO ACTIVE SESSION
      ==================================================== */}

      {!activeSession && (
        <div className="rounded-3xl border border-emerald-100 bg-emerald-50 p-5">
          <div className="flex items-start gap-4">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-white text-emerald-600 shadow-sm">
              <CarFront size={21} />
            </div>

            <div>
              <h3 className="font-black text-slate-900">Ready to park?</h3>

              <p className="mt-1 text-sm leading-6 text-slate-600">
                Find a parking facility or make a reservation before arriving.
                Your active parking session will appear here after check-in.
              </p>

              <button
                type="button"
                onClick={() => navigate("/parking")}
                className="mt-4 inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-emerald-500"
              >
                Find Parking
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
