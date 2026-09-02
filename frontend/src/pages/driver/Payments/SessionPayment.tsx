import { useCallback, useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import {
  AlertCircle,
  ArrowLeft,
  ArrowUpRight,
  CheckCircle2,
  Clock3,
  CreditCard,
  Gift,
  Loader2,
  RefreshCw,
  Smartphone,
  Wallet,
  XCircle,
} from "lucide-react";

import { useAuth } from "../../../auth/AuthContext";
import {
  api,
  parkingBaysApi,
  parkingFacilitiesApi,
  parkingZonesApi,
} from "../../../api";

// ==========================================================
// Types
// ==========================================================

type CheckoutStatus =
  | "IDLE"
  | "PROCESSING"
  | "PENDING"
  | "SUCCESSFUL"
  | "FAILED"
  | "CANCELLED";

interface BackendSession {
  id: number;
  session_number?: string | null;
  status?: string | null;
  vehicle_registration?: string | null;
  entry_time?: string | null;
  duration_minutes?: number | null;
  calculated_amount?: number | string | null;
  paid_amount?: number | string | null;
  payment_status?: string | null;
  currency?: string | null;
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
  facility?: {
    name?: string | null;
    address?: string | null;
  } | null;
  parking_facility?: {
    name?: string | null;
    address?: string | null;
  } | null;
  [key: string]: any;
}

interface BackendQuote {
  amount?: number | string | null;
  total_amount?: number | string | null;
  calculated_amount?: number | string | null;
  currency?: string | null;
  duration_minutes?: number | null;
  [key: string]: any;
}

interface CheckoutSession {
  id: number;
  amount: number | null;
  currency: string;
  sessionNumber?: string | null;
  facility?: string | null;
  zone?: string | null;
  vehicle?: string | null;
  bay?: string | null;
  entryTime?: string | null;
  durationMinutes?: number | null;
  paymentStatus?: string | null;
  status?: string | null;
}

interface LoyaltyAccount {
  id?: number;
  customer_id?: number;
  points_balance?: number | string | null;
  lifetime_points?: number | string | null;
  tier?: string | null;
  is_active?: boolean;
  [key: string]: any;
}

// ==========================================================
// Error Helpers
// ==========================================================

function getErrorMessage(error: any): string {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail.map((item: any) => item?.msg ?? String(item)).join(", ");
  }

  if (typeof error?.response?.data?.message === "string") {
    return error.response.data.message;
  }

  if (typeof error?.message === "string") {
    return error.message;
  }

  switch (error?.response?.status) {
    case 401:
      return "Your session has expired. Please sign in again.";

    case 403:
      return "You are not authorized to make this payment.";

    case 404:
      return "The parking session or backend pricing service could not be found.";

    case 409:
      return "This parking session cannot currently be paid.";

    case 422:
      return "The payment information supplied is invalid.";

    default:
      return "Unable to prepare or complete the parking payment.";
  }
}

// ==========================================================
// Formatting Helpers
// ==========================================================

function money(value: number | null, currency = "KES"): string {
  if (value === null || !Number.isFinite(value)) {
    return "—";
  }

  try {
    return new Intl.NumberFormat("en-KE", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  } catch {
    return `${currency} ${value.toFixed(2)}`;
  }
}

function normalizePhone(value: string): string {
  const digits = value.replace(/\D/g, "");

  if (digits.startsWith("254")) {
    return digits;
  }

  if (digits.startsWith("0")) {
    return `254${digits.slice(1)}`;
  }

  if (digits.startsWith("7") || digits.startsWith("1")) {
    return `254${digits}`;
  }

  return digits;
}

function validMpesaPhone(value: string): boolean {
  return /^254(7|1)\d{8}$/.test(value);
}

function readBackendAmount(
  value: BackendSession | BackendQuote,
): number | null {
  const candidates = [
    (value as BackendQuote).amount,
    (value as BackendQuote).total_amount,
    (value as BackendQuote).calculated_amount,
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

function readPointsBalance(account: LoyaltyAccount | number | null): number {
  if (account === null || account === undefined) {
    return 0;
  }

  const candidate =
    typeof account === "number"
      ? account
      : (account.points_balance ??
        (account as any).balance ??
        (account as any).points ??
        (account as any).data?.points_balance ??
        (account as any).data?.balance ??
        (account as any).data?.points ??
        (account as any).data);

  const numeric = Number(candidate);

  if (!Number.isFinite(numeric)) {
    return 0;
  }

  return Math.max(0, Math.floor(numeric));
}

function formatDuration(minutes: number | null): string {
  if (minutes === null || !Number.isFinite(minutes)) {
    return "—";
  }

  const safe = Math.max(0, Math.floor(minutes));

  if (safe < 60) {
    return `${safe} min`;
  }

  const hours = Math.floor(safe / 60);
  const remaining = safe % 60;

  return remaining === 0 ? `${hours}h` : `${hours}h ${remaining}m`;
}

// ==========================================================
// Reusable Components
// ==========================================================

function CheckoutDetail({
  label,
  value,
  mono = false,
  emphasis = false,
}: {
  label: string;
  value?: string | null;
  mono?: boolean;
  emphasis?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
      <span className="text-xs font-semibold text-slate-500">{label}</span>

      <span
        className={`break-all text-sm sm:text-right ${
          emphasis
            ? "font-black text-slate-900"
            : "font-extrabold text-slate-700"
        } ${mono ? "font-mono text-xs" : ""}`}
      >
        {value ?? "—"}
      </span>
    </div>
  );
}

// ==========================================================
// Component
// ==========================================================

export default function SessionPayment() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const sessionId = new URLSearchParams(location.search).get("sessionId");

  // --------------------------------------------------------
  // Parking Session
  // --------------------------------------------------------

  const [session, setSession] = useState<CheckoutSession | null>(null);

  const [loading, setLoading] = useState(true);

  const [refreshing, setRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);

  // --------------------------------------------------------
  // Loyalty
  // --------------------------------------------------------

  const [loyaltyAccount, setLoyaltyAccount] = useState<LoyaltyAccount | null>(
    null,
  );

  const [loyaltyLoading, setLoyaltyLoading] = useState(false);

  const [useLoyaltyPoints, setUseLoyaltyPoints] = useState(false);

  const [loyaltyPointsInput, setLoyaltyPointsInput] = useState("0");

  // --------------------------------------------------------
  // Payment
  // --------------------------------------------------------

  const [paymentMethod, setPaymentMethod] = useState<"WALLET" | "MPESA">(
    "WALLET",
  );

  const [paymentProvider, setPaymentProvider] = useState<
    "INTERNAL" | "SAFARICOM"
  >("INTERNAL");

  const [mpesaPhone, setMpesaPhone] = useState(
    String(user?.phone_number ?? ""),
  );

  const [paymentId, setPaymentId] = useState<number | null>(null);

  const [status, setStatus] = useState<CheckoutStatus>("IDLE");

  const [message, setMessage] = useState<string | null>(null);

  const [processing, setProcessing] = useState(false);

  const [liveNow, setLiveNow] = useState(Date.now());

  // ==========================================================
  // Loyalty Account
  // ==========================================================

  const loadLoyaltyAccount = useCallback(async () => {
    if (!user?.id) {
      setLoyaltyAccount(null);
      return;
    }

    setLoyaltyLoading(true);

    try {
      /*
       * The SmartPark loyalty balance endpoint resolves the
       * authenticated customer's own spendable balance.
       *
       * Keep this call isolated from parking-session pricing.
       */
      const response = await api.get<
        | LoyaltyAccount
        | number
        | {
            points_balance?: number | string | null;
            balance?: number | string | null;
            points?: number | string | null;
            data?: any;
          }
      >("/loyalty/balance");

      const payload: any = response.data;
      const accountData =
        payload?.data && typeof payload.data === "object"
          ? payload.data
          : payload;

      setLoyaltyAccount(
        typeof accountData === "number"
          ? { points_balance: accountData }
          : (accountData ?? null),
      );
    } catch (err) {
      /*
       * Loyalty is an optional payment facility.
       *
       * If the customer has no loyalty account, the normal
       * Wallet/M-PESA checkout must continue to work.
       */
      console.warn("[SmartPark Loyalty] Unable to load loyalty account:", err);

      setLoyaltyAccount(null);
    } finally {
      setLoyaltyLoading(false);
    }
  }, [user?.id]);

  useEffect(() => {
    void loadLoyaltyAccount();
  }, [loadLoyaltyAccount]);

  // ==========================================================
  // Load Parking Session + Authoritative Quote
  // ==========================================================

  const loadSessionAndQuote = useCallback(
    async (manual = false) => {
      if (!sessionId) {
        setError("No parking session was specified.");
        setLoading(false);
        return;
      }

      if (manual) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setError(null);

      try {
        const sessionResponse = await api.get<BackendSession>(
          `/parking-sessions/${encodeURIComponent(sessionId)}`,
        );

        const raw = sessionResponse.data;

        let backendAmount = readBackendAmount(raw);

        let quoteDuration = raw.duration_minutes ?? null;

        /*
         * IMPORTANT:
         *
         * The frontend does NOT calculate parking fees.
         *
         * The authoritative parking amount is requested from
         * the backend quote endpoint.
         */

        if (String(raw.status ?? "").toUpperCase() === "ACTIVE") {
          const quoteResponse = await api.get<BackendQuote>(
            `/parking-sessions/${encodeURIComponent(sessionId)}/quote`,
          );

          backendAmount = readBackendAmount(quoteResponse.data);

          quoteDuration = quoteResponse.data.duration_minutes ?? quoteDuration;
        }

        let facilityName =
          raw.facility_name ??
          raw.facility?.name ??
          raw.parking_facility?.name ??
          null;

        let zoneName = raw.parking_zone_name ?? null;

        let zoneCode: string | null = null;

        let bayNumber = raw.parking_bay_number ?? raw.bay_number ?? null;

        let bayCode = raw.parking_bay_code ?? raw.bay_code ?? null;

        /*
         * The session endpoint may expose only database IDs.
         * Resolve those IDs through the same human-readable
         * metadata used by the Parking Sessions page.
         *
         * IDs are normalised to strings before comparison because
         * the backend may serialise PostgreSQL IDs as numbers or strings.
         */
        if (!facilityName || !zoneName || !bayNumber || !bayCode) {
          try {
            const [facilitiesResponse, zonesResponse, baysResponse] =
              await Promise.all([
                parkingFacilitiesApi.list(0, 100),
                parkingZonesApi.list(0, 100),
                parkingBaysApi.list(0, 100),
              ]);

            const facilities = facilitiesResponse.items ?? [];
            const zones = zonesResponse.items ?? [];
            const bays = baysResponse.items ?? [];

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
              raw.facility_id ??
              raw.parking_facility_id ??
              zone?.facility_id ??
              undefined;

            const facility =
              facilityId !== null && facilityId !== undefined
                ? facilities.find(
                    (item) => String(item.id) === String(facilityId),
                  )
                : undefined;

            facilityName = facilityName ?? facility?.name ?? null;

            zoneName = zoneName ?? zone?.name ?? null;

            zoneCode = zone?.code ?? null;

            bayNumber = bayNumber ?? bay?.bay_number ?? null;

            bayCode = bayCode ?? bay?.code ?? null;
          } catch (metadataError) {
            console.warn(
              "[SmartPark Session Payment] Unable to resolve parking metadata:",
              metadataError,
            );
          }
        }

        const humanReadableZone = [zoneName, zoneCode]
          .filter(Boolean)
          .join(" · ");

        const humanReadableBay = [bayNumber, bayCode]
          .filter(Boolean)
          .join(" · ");

        setSession({
          id: raw.id,
          amount: backendAmount,
          currency: raw.currency ?? "KES",

          sessionNumber: raw.session_number,

          facility: facilityName ?? "Parking facility",

          zone: humanReadableZone || "—",

          vehicle: raw.vehicle_registration ?? "—",

          bay: humanReadableBay || "—",

          entryTime: raw.entry_time,

          durationMinutes: quoteDuration,

          paymentStatus: raw.payment_status,

          status: raw.status,
        });
      } catch (err) {
        console.error(
          "[SmartPark Session Payment] Failed to load session/quote:",
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

  useEffect(() => {
    void loadSessionAndQuote();
  }, [loadSessionAndQuote]);

  // ==========================================================
  // Periodic Backend Quote Refresh
  // ==========================================================

  useEffect(() => {
    const interval = window.setInterval(
      () => {
        void loadSessionAndQuote(true);
      },
      15 * 60 * 1000,
    );

    return () => window.clearInterval(interval);
  }, [loadSessionAndQuote]);

  // ==========================================================
  // Live Clock
  // ==========================================================

  useEffect(() => {
    const interval = window.setInterval(() => setLiveNow(Date.now()), 1000);

    return () => window.clearInterval(interval);
  }, []);

  // ==========================================================
  // Duration
  // ==========================================================

  const liveDuration = useMemo(() => {
    if (!session) {
      return null;
    }

    if (
      session.durationMinutes !== null &&
      session.durationMinutes !== undefined
    ) {
      if (String(session.status ?? "").toUpperCase() !== "ACTIVE") {
        return session.durationMinutes;
      }
    }

    if (!session.entryTime) {
      return session.durationMinutes ?? null;
    }

    const start = new Date(session.entryTime).getTime();

    if (!Number.isFinite(start)) {
      return session.durationMinutes ?? null;
    }

    const end =
      String(session.status ?? "").toUpperCase() === "ACTIVE"
        ? liveNow
        : session.durationMinutes !== null &&
            session.durationMinutes !== undefined
          ? start + session.durationMinutes * 60_000
          : liveNow;

    return Math.max(0, Math.floor((end - start) / 60_000));
  }, [session, liveNow]);

  // ==========================================================
  // Loyalty Calculations
  // ==========================================================

  const availableLoyaltyPoints = useMemo(
    () => readPointsBalance(loyaltyAccount),
    [loyaltyAccount],
  );

  const requestedLoyaltyPoints = useMemo(() => {
    const numeric = Number(loyaltyPointsInput);

    if (!Number.isFinite(numeric)) {
      return 0;
    }

    return Math.max(0, Math.floor(numeric));
  }, [loyaltyPointsInput]);

  const maximumRedeemablePoints = useMemo(() => {
    if (
      session?.amount === null ||
      session?.amount === undefined ||
      !Number.isFinite(session.amount)
    ) {
      return 0;
    }

    /*
     * One loyalty point represents
     * KES 1.00 of payment value.
     *
     * Never allow the frontend control
     * to request more points than the
     * parking charge itself.
     */
    const amountCap = Math.max(0, Math.floor(session.amount));

    return Math.min(availableLoyaltyPoints, amountCap);
  }, [session?.amount, availableLoyaltyPoints]);

  const loyaltyPointsToRedeem = useLoyaltyPoints
    ? Math.min(requestedLoyaltyPoints, maximumRedeemablePoints)
    : 0;

  const loyaltyValue = loyaltyPointsToRedeem;

  const remainingAmount = useMemo(() => {
    if (
      session?.amount === null ||
      session?.amount === undefined ||
      !Number.isFinite(session.amount)
    ) {
      return null;
    }

    return Math.max(0, session.amount - loyaltyValue);
  }, [session?.amount, loyaltyValue]);

  const loyaltyCoversFullAmount =
    remainingAmount !== null && remainingAmount <= 0;

  // ==========================================================
  // Status Flags
  // ==========================================================

  const displayStatus = status.toUpperCase();

  const successful = displayStatus === "SUCCESSFUL";

  const failed = displayStatus === "FAILED" || displayStatus === "CANCELLED";

  const pending = displayStatus === "PENDING" || displayStatus === "PROCESSING";

  // ==========================================================
  // Loyalty Input Helpers
  // ==========================================================

  const setMaximumLoyaltyPoints = () => {
    setLoyaltyPointsInput(String(maximumRedeemablePoints));

    setStatus("IDLE");
    setMessage(null);
  };

  const clearLoyaltyPoints = () => {
    setLoyaltyPointsInput("0");

    setStatus("IDLE");
    setMessage(null);
  };

  const handleLoyaltyPointsChange = (value: string) => {
    /*
     * Allow the input to be temporarily
     * empty while typing.
     */
    if (value === "") {
      setLoyaltyPointsInput("");
      return;
    }

    const digits = value.replace(/\D/g, "");

    if (!digits) {
      setLoyaltyPointsInput("0");
      return;
    }

    const numeric = Math.max(0, Math.floor(Number(digits)));

    const capped = Math.min(numeric, maximumRedeemablePoints);

    setLoyaltyPointsInput(String(capped));

    setStatus("IDLE");
    setMessage(null);
  };

  // ==========================================================
  // Process Payment
  // ==========================================================

  const processPayment = async () => {
    if (!user?.id) {
      setStatus("FAILED");

      setMessage(
        "Authenticated customer information is missing. Please sign in again.",
      );

      return;
    }

    if (
      !session ||
      session.amount === null ||
      !Number.isFinite(session.amount)
    ) {
      setStatus("FAILED");

      setMessage(
        "The backend did not return a payable amount for this parking session. Please refresh and try again.",
      );

      return;
    }

    /*
     * Validate loyalty redemption.
     *
     * The backend remains the final authority and will
     * validate the customer's actual balance before
     * completing the transaction.
     */
    if (loyaltyPointsToRedeem > availableLoyaltyPoints) {
      setStatus("FAILED");

      setMessage(
        "You do not have enough loyalty points for the selected redemption amount.",
      );

      return;
    }

    if (loyaltyPointsToRedeem > Math.floor(session.amount)) {
      setStatus("FAILED");

      setMessage(
        "The selected loyalty points cannot exceed the parking amount due.",
      );

      return;
    }

    const normalizedPhone = normalizePhone(mpesaPhone);

    /*
     * M-PESA validation is only required when
     * there is still a monetary amount to pay.
     *
     * A zero-value checkout is valid during the
     * parking grace period and does not require
     * a payment phone number.
     */
    if (
      paymentMethod === "MPESA" &&
      (remainingAmount ?? 0) > 0 &&
      !validMpesaPhone(normalizedPhone)
    ) {
      setStatus("FAILED");

      setMessage(
        "Please enter a valid Kenyan M-PESA number, for example 0712345678 or 254712345678.",
      );

      return;
    }

    /*
     * Loyalty redemption is optional.
     *
     * When the remaining amount is zero, the backend
     * accepts the zero-value transaction and completes
     * the checkout without requiring Wallet/M-PESA.
     */
    setProcessing(true);
    setStatus("PROCESSING");
    setMessage(null);

    try {
      const monetaryAmount = remainingAmount ?? 0;

      const response = await api.post<{
        id: number;
        status: string;
        paid_at?: string | null;
      }>("/payments/session", {
        payment_method: paymentMethod,

        payment_provider: paymentProvider,

        payment_purpose: "PARKING_SESSION",

        payment_type: "PAYMENT",

        currency: session.currency,

        /*
         * IMPORTANT:
         *
         * The parking charge comes from the backend.
         * The frontend only separates the loyalty
         * contribution from the monetary amount.
         */
        subtotal_amount: session.amount,

        discount_amount: 0,

        tax_amount: 0,

        total_amount: monetaryAmount,

        payer_name: `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim(),

        payer_phone:
          paymentMethod === "MPESA"
            ? normalizedPhone
            : String(user.phone_number ?? ""),

        payer_email: user.email,

        parking_session_id: session.id,

        customer_id: user.id,

        notes: `Parking session payment: ${
          session.sessionNumber ?? `#${session.id}`
        }`,

        /*
         * Critical loyalty integration field.
         */
        loyalty_points_to_redeem: loyaltyPointsToRedeem,
      });

      const nextStatus = String(
        response.data.status ?? "PENDING",
      ).toUpperCase() as CheckoutStatus;

      setPaymentId(response.data.id);

      setStatus(nextStatus);

      if (nextStatus === "SUCCESSFUL") {
        setProcessing(false);

        setMessage(
          (remainingAmount ?? 0) <= 0
            ? loyaltyPointsToRedeem > 0
              ? `Checkout successful. ${loyaltyPointsToRedeem.toLocaleString(
                  "en-KE",
                )} loyalty points were redeemed and the remaining parking charge was KES 0.00. Proceed to the exit within 15 minutes.`
              : "Checkout successful. Your parking charge is KES 0.00 under the grace period. Proceed to the exit within 15 minutes."
            : loyaltyPointsToRedeem > 0
              ? `Payment successful. ${loyaltyPointsToRedeem.toLocaleString(
                  "en-KE",
                )} loyalty points were redeemed and your remaining parking charge was settled.`
              : "Payment successful. Your parking charge has been settled. Proceed to the exit within 15 minutes.",
        );

        /*
         * Refresh loyalty balance so the UI reflects
         * the points consumed by the payment.
         */
        void loadLoyaltyAccount();
      } else if (["FAILED", "CANCELLED"].includes(nextStatus)) {
        setProcessing(false);

        setMessage(
          "Payment was not completed. Your parking session remains active.",
        );
      } else {
        setMessage(
          (remainingAmount ?? 0) <= 0
            ? loyaltyPointsToRedeem > 0
              ? "Your loyalty redemption is being processed. Please wait for confirmation."
              : "Your zero-value checkout is being processed. Please wait for confirmation."
            : paymentMethod === "MPESA"
              ? "M-PESA payment request sent. Complete the prompt on your phone; SmartPark will confirm the payment automatically."
              : "Payment is being processed. Please wait for confirmation.",
        );
      }
    } catch (err) {
      console.error("[SmartPark Session Payment] Payment failed:", err);

      setProcessing(false);

      setStatus("FAILED");

      setMessage(getErrorMessage(err));
    }
  };

  // ==========================================================
  // Payment Status Polling
  // ==========================================================

  useEffect(() => {
    if (!paymentId || !["PENDING", "PROCESSING"].includes(status)) {
      return;
    }

    let cancelled = false;

    let attempts = 0;

    const maxAttempts = 60;

    const poll = async () => {
      attempts += 1;

      try {
        const response = await api.get<{
          id: number;
          status: string;
          paid_at?: string | null;
        }>(`/payments/${paymentId}`);

        if (cancelled) {
          return;
        }

        const nextStatus = String(
          response.data.status ?? "PENDING",
        ).toUpperCase() as CheckoutStatus;

        setStatus(nextStatus);

        if (nextStatus === "SUCCESSFUL") {
          setProcessing(false);

          setMessage(
            (remainingAmount ?? 0) <= 0
              ? loyaltyPointsToRedeem > 0
                ? `Checkout successful. ${loyaltyPointsToRedeem.toLocaleString(
                    "en-KE",
                  )} loyalty points were redeemed and the remaining parking charge was KES 0.00. Proceed to the exit within 15 minutes.`
                : "Checkout successful. Your parking charge is KES 0.00 under the grace period. Proceed to the exit within 15 minutes."
              : loyaltyPointsToRedeem > 0
                ? `Payment successful. ${loyaltyPointsToRedeem.toLocaleString(
                    "en-KE",
                  )} loyalty points were redeemed and your remaining parking charge was settled.`
                : "Payment successful. Your parking charge has been settled. Proceed to the exit within 15 minutes.",
          );

          void loadLoyaltyAccount();

          return;
        }

        if (["FAILED", "CANCELLED"].includes(nextStatus)) {
          setProcessing(false);

          setMessage(
            "Payment was not completed. Your parking session remains active.",
          );

          return;
        }

        if (attempts >= maxAttempts) {
          setProcessing(false);

          setMessage(
            "We could not confirm the payment within the expected time. Please check Payment History before retrying.",
          );
        }
      } catch (err) {
        console.warn(
          "[SmartPark Session Payment] Payment status refresh failed:",
          err,
        );

        if (attempts >= maxAttempts && !cancelled) {
          setProcessing(false);

          setMessage(
            "Payment status could not be confirmed automatically. Please check Payment History before retrying.",
          );
        }
      }
    };

    void poll();

    const interval = window.setInterval(() => void poll(), 3000);

    return () => {
      cancelled = true;

      window.clearInterval(interval);
    };
  }, [paymentId, status, loyaltyPointsToRedeem, loadLoyaltyAccount]);

  // ==========================================================
  // Loading State
  // ==========================================================

  if (loading) {
    return (
      <div className="mx-auto flex min-h-[500px] w-full max-w-5xl items-center justify-center">
        <div className="text-center">
          <Loader2
            size={32}
            className="mx-auto animate-spin text-emerald-600"
          />

          <h2 className="mt-4 text-lg font-black text-slate-900">
            Preparing checkout
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Retrieving the authoritative parking charge from SmartPark AI...
          </p>
        </div>
      </div>
    );
  }

  // ==========================================================
  // Main UI
  // ==========================================================

  return (
    <div className="mx-auto w-full max-w-5xl space-y-6">
      {/* ======================================================
          Header
      ====================================================== */}

      <section className="overflow-hidden rounded-3xl bg-[#071a2d] text-white shadow-sm">
        <div className="p-6 sm:p-8">
          <button
            type="button"
            onClick={() => navigate("/parking-sessions")}
            disabled={processing}
            className="mb-6 inline-flex items-center gap-2 text-sm font-bold text-slate-300 hover:text-white disabled:opacity-50"
          >
            <ArrowLeft size={16} />
            Back to Parking Sessions
          </button>

          <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="text-xs font-bold uppercase tracking-[.2em] text-emerald-300">
                SmartPark AI Checkout
              </div>

              <h1 className="mt-3 text-3xl font-black">Pay & Check Out</h1>

              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">
                Settle the parking charge for this active session. Loyalty
                points are optional; you may use them toward the charge or pay
                the full amount using Wallet or M-PESA.
              </p>
            </div>

            <div className="rounded-2xl bg-emerald-400/10 px-5 py-4 ring-1 ring-emerald-300/20">
              <div className="text-xs font-bold uppercase tracking-wider text-emerald-300">
                Parking Charge
              </div>

              <div className="mt-1 text-2xl font-black">
                {money(session?.amount ?? null, session?.currency ?? "KES")}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ======================================================
          Error
      ====================================================== */}

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-rose-800">
          <AlertCircle size={19} className="mt-0.5 shrink-0" />

          <div className="min-w-0 flex-1">
            <b>Checkout service message</b>

            <p className="mt-1 text-sm leading-6">{error}</p>
          </div>
        </div>
      )}

      {/* ======================================================
          Content
      ====================================================== */}

      {session && (
        <section className="grid gap-6 lg:grid-cols-[1.1fr_.9fr]">
          {/* ==================================================
              Session Summary
          ================================================== */}

          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-7">
            <div className="flex items-center gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-2xl bg-slate-100 text-slate-600">
                <CreditCard size={22} />
              </div>

              <div>
                <h2 className="text-lg font-black text-slate-900">
                  Parking Session
                </h2>

                <p className="text-xs font-semibold text-slate-400">
                  Review the backend-calculated charge before payment.
                </p>
              </div>
            </div>

            <div className="mt-6 divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-100">
              <CheckoutDetail
                label="Session"
                value={session.sessionNumber ?? `#${session.id}`}
                mono
              />

              <CheckoutDetail label="Facility" value={session.facility} />

              <CheckoutDetail label="Parking Zone" value={session.zone} />

              <CheckoutDetail label="Vehicle" value={session.vehicle} />

              <CheckoutDetail label="Parking Bay" value={session.bay} />

              <CheckoutDetail
                label="Current Duration"
                value={formatDuration(liveDuration)}
              />

              <CheckoutDetail
                label="Parking Charge"
                value={money(session.amount, session.currency)}
                emphasis
              />

              <CheckoutDetail
                label="Loyalty Redemption"
                value={
                  loyaltyPointsToRedeem > 0
                    ? `${loyaltyPointsToRedeem.toLocaleString(
                        "en-KE",
                      )} points (${money(loyaltyValue, session.currency)})`
                    : "None"
                }
              />

              <CheckoutDetail
                label="Remaining Amount"
                value={money(remainingAmount, session.currency)}
                emphasis
              />
            </div>

            {/* =================================================
                Loyalty Summary
                ================================================= */}

            <div className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
              <div className="flex items-start gap-3">
                <Gift size={20} className="mt-0.5 shrink-0 text-emerald-600" />

                <div className="min-w-0">
                  <div className="font-black text-emerald-900">
                    Loyalty Points
                  </div>

                  {loyaltyLoading ? (
                    <div className="mt-2 flex items-center gap-2 text-sm text-emerald-700">
                      <Loader2 size={15} className="animate-spin" />
                      Checking your loyalty balance...
                    </div>
                  ) : (
                    <>
                      <p className="mt-1 text-sm leading-6 text-emerald-800">
                        Available balance:{" "}
                        <strong>
                          {availableLoyaltyPoints.toLocaleString("en-KE")}{" "}
                          points
                        </strong>
                      </p>

                      <p className="mt-1 text-xs leading-5 text-emerald-700">
                        1 loyalty point = KES 1.00 toward this parking payment.
                      </p>
                    </>
                  )}
                </div>
              </div>
            </div>

            {/* =================================================
                Important
                ================================================= */}

            <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <div className="font-black">Important</div>

              <p className="mt-1 leading-6">
                After successful payment, proceed to the exit. You have{" "}
                <strong>15 minutes</strong> to leave the premises. The IoT exit
                scanner completes the physical session.
              </p>
            </div>
          </div>

          {/* ==================================================
              Payment Panel
              ================================================== */}

          <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm sm:p-7">
            {!successful && (
              <>
                <h2 className="text-lg font-black text-slate-900">
                  Choose Payment Method
                </h2>

                <p className="mt-1 text-sm text-slate-500">
                  Loyalty points are optional. Choose whether to use them, then
                  select how to settle any remaining amount.
                </p>

                {/* ==============================================
                    Loyalty Redemption
                    ============================================== */}

                <div className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
                  <div className="flex items-start gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-emerald-600 shadow-sm">
                      <Gift size={20} />
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                        <h3 className="font-black text-emerald-900">
                          Loyalty Points
                        </h3>

                        <span className="text-xs font-bold text-emerald-700">
                          Balance:{" "}
                          {availableLoyaltyPoints.toLocaleString("en-KE")} pts
                        </span>
                      </div>

                      <p className="mt-1 text-xs leading-5 text-emerald-700">
                        Loyalty points are optional. If you choose to use them,
                        you can redeem up to{" "}
                        <strong>
                          {maximumRedeemablePoints.toLocaleString("en-KE")}{" "}
                          points
                        </strong>{" "}
                        for this payment.
                      </p>

                      <label className="mt-4 flex cursor-pointer items-center gap-3 rounded-xl border border-emerald-200 bg-white px-3 py-3">
                        <input
                          type="checkbox"
                          checked={useLoyaltyPoints}
                          onChange={(e) => {
                            setUseLoyaltyPoints(e.target.checked);
                            setStatus("IDLE");
                            setMessage(null);
                          }}
                          disabled={
                            processing ||
                            loyaltyLoading ||
                            maximumRedeemablePoints <= 0
                          }
                          className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                        />
                        <span className="text-sm font-bold text-emerald-900">
                          Use loyalty points for this payment
                        </span>
                      </label>
                    </div>
                  </div>

                  <div className="mt-4">
                    <label className="block text-sm font-bold text-slate-700">
                      Points to Redeem{useLoyaltyPoints ? "" : " (optional)"}
                      <div className="mt-2 flex gap-2">
                        <input
                          value={loyaltyPointsInput}
                          onChange={(e) =>
                            handleLoyaltyPointsChange(e.target.value)
                          }
                          inputMode="numeric"
                          pattern="[0-9]*"
                          min={0}
                          max={maximumRedeemablePoints}
                          disabled={
                            processing ||
                            loyaltyLoading ||
                            !useLoyaltyPoints ||
                            availableLoyaltyPoints <= 0
                          }
                          placeholder="0"
                          className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-bold outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-100"
                        />

                        <button
                          type="button"
                          onClick={setMaximumLoyaltyPoints}
                          disabled={
                            processing ||
                            loyaltyLoading ||
                            !useLoyaltyPoints ||
                            maximumRedeemablePoints <= 0
                          }
                          className="rounded-xl border border-emerald-200 bg-white px-4 py-3 text-xs font-black text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          MAX
                        </button>

                        <button
                          type="button"
                          onClick={clearLoyaltyPoints}
                          disabled={processing || loyaltyLoading}
                          className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs font-black text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          CLEAR
                        </button>
                      </div>
                    </label>
                  </div>

                  {/* ============================================
                      Loyalty Calculation
                      ============================================ */}

                  <div className="mt-4 grid gap-3 sm:grid-cols-2">
                    <div className="rounded-xl bg-white p-3 ring-1 ring-emerald-100">
                      <div className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        Loyalty Value
                      </div>

                      <div className="mt-1 text-lg font-black text-emerald-700">
                        {money(loyaltyValue, session.currency)}
                      </div>
                    </div>

                    <div className="rounded-xl bg-white p-3 ring-1 ring-emerald-100">
                      <div className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        Remaining
                      </div>

                      <div className="mt-1 text-lg font-black text-slate-900">
                        {money(remainingAmount, session.currency)}
                      </div>
                    </div>
                  </div>

                  {loyaltyCoversFullAmount && (
                    <div className="mt-4 rounded-xl border border-emerald-200 bg-white p-3 text-sm font-bold text-emerald-800">
                      {loyaltyPointsToRedeem > 0
                        ? "✓ Your loyalty points cover the full parking charge. No additional monetary payment is required."
                        : "✓ No monetary payment is required. This session is within the free parking grace period."}
                    </div>
                  )}
                </div>

                {/* ==============================================
                    Payment Methods
                    ============================================== */}

                <div className="mt-6 grid gap-3">
                  {/* Wallet */}

                  <button
                    type="button"
                    disabled={processing}
                    onClick={() => {
                      setPaymentMethod("WALLET");

                      setPaymentProvider("INTERNAL");

                      setStatus("IDLE");

                      setMessage(null);
                    }}
                    className={`rounded-2xl border p-4 text-left transition disabled:opacity-60 ${
                      paymentMethod === "WALLET"
                        ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                        : "border-slate-200 bg-white hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Wallet size={21} className="text-emerald-600" />

                      <span className="font-extrabold text-slate-900">
                        SmartPark Wallet
                      </span>
                    </div>

                    <p className="mt-2 text-xs leading-5 text-slate-500">
                      Pay the remaining balance using your SmartPark wallet.
                    </p>
                  </button>

                  {/* M-PESA */}

                  <button
                    type="button"
                    disabled={processing}
                    onClick={() => {
                      setPaymentMethod("MPESA");

                      setPaymentProvider("SAFARICOM");

                      setStatus("IDLE");

                      setMessage(null);
                    }}
                    className={`rounded-2xl border p-4 text-left transition disabled:opacity-60 ${
                      paymentMethod === "MPESA"
                        ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                        : "border-slate-200 bg-white hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Smartphone size={21} className="text-emerald-600" />

                      <span className="font-extrabold text-slate-900">
                        M-PESA
                      </span>
                    </div>

                    <p className="mt-2 text-xs leading-5 text-slate-500">
                      Pay the remaining balance using an M-PESA number.
                    </p>
                  </button>
                </div>

                {/* ==========================================
                        M-PESA Number
                        ========================================== */}

                {paymentMethod === "MPESA" && (
                  <label className="mt-5 block text-sm font-bold text-slate-700">
                    M-PESA Phone Number
                    <input
                      value={mpesaPhone}
                      onChange={(e) => setMpesaPhone(e.target.value)}
                      placeholder="0712345678"
                      inputMode="tel"
                      disabled={processing}
                      className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-3 text-sm font-medium outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                    />
                  </label>
                )}

                {/* ==============================================
                    Message
                    ============================================== */}

                {message && (
                  <div
                    className={`mt-5 rounded-2xl border p-4 text-sm ${
                      failed
                        ? "border-rose-200 bg-rose-50 text-rose-800"
                        : pending
                          ? "border-amber-200 bg-amber-50 text-amber-800"
                          : "border-slate-200 bg-slate-50 text-slate-700"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {failed ? (
                        <XCircle size={18} className="mt-0.5 shrink-0" />
                      ) : (
                        <AlertCircle size={18} className="mt-0.5 shrink-0" />
                      )}

                      <span>{message}</span>
                    </div>
                  </div>
                )}

                {/* ==============================================
                    Pay Button
                    ============================================== */}

                <button
                  type="button"
                  onClick={() => void processPayment()}
                  disabled={
                    processing ||
                    session.amount === null ||
                    session.amount < 0 ||
                    loyaltyLoading ||
                    loyaltyPointsToRedeem > availableLoyaltyPoints
                  }
                  className="mt-6 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3.5 text-sm font-extrabold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {processing ? (
                    <RefreshCw size={17} className="animate-spin" />
                  ) : loyaltyPointsToRedeem > 0 && loyaltyCoversFullAmount ? (
                    <Gift size={17} />
                  ) : (remainingAmount ?? 0) <= 0 ? (
                    <CheckCircle2 size={17} />
                  ) : (
                    <CreditCard size={17} />
                  )}

                  {processing
                    ? "Processing Checkout..."
                    : session.amount === null
                      ? "Amount unavailable"
                      : (remainingAmount ?? 0) <= 0
                        ? loyaltyPointsToRedeem > 0
                          ? `Redeem ${loyaltyPointsToRedeem.toLocaleString(
                              "en-KE",
                            )} Points & Complete Checkout`
                          : "Complete Free Checkout"
                        : `Pay ${money(remainingAmount, session.currency)}`}
                </button>

                {/* ==============================================
                    Refresh
                    ============================================== */}

                <button
                  type="button"
                  onClick={() => {
                    void loadSessionAndQuote(true);

                    void loadLoyaltyAccount();
                  }}
                  disabled={refreshing || processing}
                  className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 px-5 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
                >
                  <RefreshCw
                    size={16}
                    className={refreshing ? "animate-spin" : ""}
                  />
                  Refresh amount & loyalty balance
                </button>
              </>
            )}

            {/* ==================================================
                Successful Payment
                ================================================== */}

            {successful && (
              <div>
                <div className="rounded-3xl border border-emerald-200 bg-emerald-50 p-6">
                  <div className="flex items-start gap-4">
                    <CheckCircle2
                      size={30}
                      className="mt-0.5 shrink-0 text-emerald-600"
                    />

                    <div>
                      <h2 className="text-xl font-black text-emerald-900">
                        Checkout successful
                      </h2>

                      <p className="mt-2 text-sm leading-6 text-emerald-800">
                        {(remainingAmount ?? 0) <= 0
                          ? loyaltyPointsToRedeem > 0
                            ? "Your parking charge has been settled using loyalty points."
                            : "Your parking charge was KES 0.00 under the grace period, so no monetary payment was required."
                          : "Your parking charge has been settled successfully."}
                      </p>

                      {loyaltyPointsToRedeem > 0 && (
                        <p className="mt-2 text-sm font-bold text-emerald-800">
                          {loyaltyPointsToRedeem.toLocaleString("en-KE")}{" "}
                          loyalty points were redeemed.
                        </p>
                      )}
                    </div>
                  </div>
                </div>

                <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-5">
                  <div className="flex items-start gap-3">
                    <Clock3
                      size={20}
                      className="mt-0.5 shrink-0 text-amber-600"
                    />

                    <div>
                      <h3 className="font-black text-slate-900">
                        Proceed to the exit
                      </h3>

                      <p className="mt-1 text-sm leading-6 text-slate-600">
                        You have <strong>15 minutes</strong> to exit the
                        premises. The IoT exit scanner will complete the parking
                        session once your vehicle leaves.
                      </p>
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => navigate("/sessions")}
                  className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-extrabold text-white hover:bg-slate-800"
                >
                  Return to Parking Sessions
                  <ArrowUpRight size={17} />
                </button>
              </div>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
