import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowDownLeft,
  ArrowUpRight,
  CheckCircle2,
  CreditCard,
  History,
  Loader2,
  RefreshCw,
  Smartphone,
  Wallet as WalletIcon,
  X,
  XCircle,
} from "lucide-react";

import { useAuth } from "../../../auth/AuthContext";
import { api } from "../../../api";

// ==========================================================
// Types
// ==========================================================

interface Wallet {
  id: number;
  wallet_number: string;
  customer_id: number;

  currency: string;
  status: string;

  available_balance: number | string;
  reserved_balance: number | string;

  total_credited: number | string;
  total_debited: number | string;

  created_at?: string | null;
  updated_at?: string | null;
}

interface WalletTransaction {
  id?: number;

  wallet_id?: number;

  payment_transaction_id?: number | null;

  transaction_number?: string | null;

  reference?: string | null;

  transaction_type?: string | null;

  status?: string | null;

  currency?: string | null;

  amount?: number | string | null;

  balance_before?: number | string | null;

  balance_after?: number | string | null;

  description?: string | null;

  notes?: string | null;

  posted_at?: string | null;

  created_at?: string | null;
}

interface WalletStatistics {
  total_transactions?: number;
  successful_transactions?: number;
  pending_transactions?: number;
  failed_transactions?: number;
  refunded_transactions?: number;

  total_credited?: number | string;
  total_debited?: number | string;

  currency?: string;
}

interface TopUpResponse {
  id: number;

  transaction_number?: string;

  status: string;

  paid_at?: string | null;

  total_amount?: number | string;

  currency?: string;

  provider_transaction_id?: string | null;
}

// ==========================================================
// Constants
// ==========================================================

const MIN_TOP_UP_AMOUNT = 10;
const MAX_TOP_UP_AMOUNT = 1_000_000;

const TOP_UP_PAYMENT_OPTIONS = [
  {
    method: "MPESA" as const,
    provider: "SAFARICOM" as const,
    label: "M-PESA",
    description: "Top up using your M-PESA number.",
    icon: Smartphone,
  },
];

// ==========================================================
// Helpers
// ==========================================================

function formatMoney(
  amount: number | string | null | undefined,
  currency = "KES",
): string {
  const numericAmount = Number(amount ?? 0);

  if (!Number.isFinite(numericAmount)) {
    return `${currency} 0.00`;
  }

  try {
    return new Intl.NumberFormat("en-KE", {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numericAmount);
  } catch {
    return `${currency} ${numericAmount.toFixed(2)}`;
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

function formatTransactionType(value: string | null | undefined): string {
  if (!value) {
    return "Transaction";
  }

  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/**
 * Normalize Kenyan phone numbers to the 2547XXXXXXXX format.
 *
 * Examples:
 * 0712345678  -> 254712345678
 * 254712345678 -> 254712345678
 * +254712345678 -> 254712345678
 * 712345678 -> 254712345678
 */
function normalizePhone(value: string): string {
  const digits = value.replace(/\D/g, "");

  if (digits.startsWith("254")) {
    return digits;
  }

  if (digits.startsWith("0")) {
    return `254${digits.slice(1)}`;
  }

  if (digits.startsWith("7") && digits.length === 9) {
    return `254${digits}`;
  }

  return digits;
}

function resolveTransactionStatus(transaction: WalletTransaction): string {
  const rawStatus = String(transaction.status ?? "")
    .trim()
    .toUpperCase();

  if (rawStatus && rawStatus !== "UNKNOWN") {
    return rawStatus;
  }

  /*
   * Existing wallet ledger entries may not expose a populated
   * status field. A posted/created ledger entry is treated as
   * completed rather than displayed as UNKNOWN.
   */
  if (transaction.posted_at || transaction.created_at) {
    return "COMPLETED";
  }

  return "PENDING";
}

function isValidKenyanPhone(value: string): boolean {
  return /^2547\d{8}$/.test(value);
}

function extractErrorMessage(error: any): string {
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
      return "You are not authorized to access this wallet.";

    case 404:
      return "Wallet information could not be found.";

    case 409:
      return "The wallet transaction could not be completed because of a conflict.";

    case 422:
      return "Some of the information provided is invalid.";

    default:
      return "Unable to complete the wallet operation. Please try again.";
  }
}

// ==========================================================
// Component
// ==========================================================

export default function Wallet() {
  const { user } = useAuth();

  // ========================================================
  // State
  // ========================================================

  const [wallet, setWallet] = useState<Wallet | null>(null);

  const [transactions, setTransactions] = useState<WalletTransaction[]>([]);

  const [statistics, setStatistics] = useState<WalletStatistics | null>(null);

  const [loading, setLoading] = useState(true);

  const [refreshing, setRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [transactionError, setTransactionError] = useState<string | null>(null);

  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // ========================================================
  // Top-up State
  // ========================================================

  const [topUpOpen, setTopUpOpen] = useState(false);

  const [topUpAmount, setTopUpAmount] = useState("");

  const [topUpMethod, setTopUpMethod] = useState<"MPESA" | "WALLET">("MPESA");

  const [topUpProvider, setTopUpProvider] = useState<"SAFARICOM" | "INTERNAL">(
    "SAFARICOM",
  );

  const [mpesaPhone, setMpesaPhone] = useState("");

  const [topUpProcessing, setTopUpProcessing] = useState(false);

  const [topUpMessage, setTopUpMessage] = useState<string | null>(null);

  const [topUpStatus, setTopUpStatus] = useState<string | null>(null);

  const [topUpTransaction, setTopUpTransaction] =
    useState<TopUpResponse | null>(null);

  // ========================================================
  // Transaction Details
  // ========================================================

  const [selectedTransaction, setSelectedTransaction] =
    useState<WalletTransaction | null>(null);

  // ========================================================
  // Load Wallet
  // ========================================================

  const loadWallet = useCallback(
    async (manualRefresh = false) => {
      if (!user?.id) {
        setWallet(null);
        setTransactions([]);
        setStatistics(null);
        setLoading(false);
        return;
      }

      if (manualRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setError(null);
      setTransactionError(null);

      try {
        /*
         * Load the customer's wallet,
         * balance, transactions and statistics.
         *
         * The endpoints are deliberately loaded
         * independently so that a problem with
         * statistics does not blank the wallet.
         */
        const [
          walletResult,
          balanceResult,
          transactionResult,
          statisticsResult,
        ] = await Promise.allSettled([
          api.get<Wallet>(`/wallets/${user.id}`),

          api.get(`/wallets/balance/${user.id}`),

          api.get(`/wallets/transactions/${user.id}`),

          api.get(`/wallets/statistics/${user.id}`),
        ]);

        // --------------------------------------------------
        // Wallet
        // --------------------------------------------------

        if (walletResult.status === "fulfilled") {
          setWallet(walletResult.value.data);
        } else {
          throw walletResult.reason;
        }

        // --------------------------------------------------
        // Balance
        // --------------------------------------------------

        if (balanceResult.status === "fulfilled") {
          /*
           * The balance endpoint may return:
           *
           *  - a raw number
           *  - an object containing balance
           *  - an object containing available_balance
           *
           * Support all three without affecting
           * the primary wallet response.
           */
          const balanceData = balanceResult.value.data as any;

          const extractedBalance =
            typeof balanceData === "number"
              ? balanceData
              : (balanceData?.available_balance ??
                balanceData?.balance ??
                balanceData?.value);

          if (extractedBalance !== undefined && extractedBalance !== null) {
            setWallet((current) =>
              current
                ? {
                    ...current,
                    available_balance: extractedBalance,
                  }
                : current,
            );
          }
        }

        // --------------------------------------------------
        // Transactions
        // --------------------------------------------------

        if (transactionResult.status === "fulfilled") {
          const transactionData = transactionResult.value.data;

          if (Array.isArray(transactionData)) {
            setTransactions(transactionData);
          } else if (Array.isArray(transactionData?.items)) {
            setTransactions(transactionData.items);
          } else if (Array.isArray(transactionData?.transactions)) {
            setTransactions(transactionData.transactions);
          } else {
            setTransactions([]);
          }
        } else {
          setTransactionError(
            "Wallet loaded, but transaction history could not be retrieved.",
          );
        }

        // --------------------------------------------------
        // Statistics
        // --------------------------------------------------

        if (statisticsResult.status === "fulfilled") {
          setStatistics(statisticsResult.value.data);
        }

        setLastUpdated(new Date());
      } catch (err) {
        console.error("[SmartPark Wallet] Failed to load wallet:", err);

        setError(extractErrorMessage(err));
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
    void loadWallet();
  }, [loadWallet]);

  // ========================================================
  // Derived Values
  // ========================================================

  const currency = wallet?.currency || "KES";

  const availableBalance = Number(wallet?.available_balance ?? 0);

  const reservedBalance = Number(wallet?.reserved_balance ?? 0);

  const totalCredited = Number(wallet?.total_credited ?? 0);

  const totalDebited = Number(wallet?.total_debited ?? 0);

  const totalWalletBalance = availableBalance + reservedBalance;

  const successfulTransactionCount = useMemo(() => {
    const completedFromLedger = transactions.filter((transaction) => {
      const status = resolveTransactionStatus(transaction);

      return status === "COMPLETED" || status === "SUCCESSFUL";
    }).length;

    const serverSuccessfulCount = Number(
      statistics?.successful_transactions ?? 0,
    );

    return Math.max(
      Number.isFinite(serverSuccessfulCount) ? serverSuccessfulCount : 0,
      completedFromLedger,
    );
  }, [transactions, statistics]);

  const recentTransactions = useMemo(() => {
    return [...transactions]
      .sort((a, b) => {
        const first = new Date(a.posted_at ?? a.created_at ?? "").getTime();

        const second = new Date(b.posted_at ?? b.created_at ?? "").getTime();

        return second - first;
      })
      .slice(0, 8);
  }, [transactions]);

  // ========================================================
  // Transaction Classification
  // ========================================================

  const isCreditTransaction = (transaction: WalletTransaction) => {
    const type = String(transaction.transaction_type ?? "").toUpperCase();

    return [
      "TOP_UP",
      "OPENING_BALANCE",
      "CREDIT",
      "REFUND",
      "LOYALTY_REWARD",
      "RESERVATION_RELEASE",
    ].includes(type);
  };

  // ========================================================
  // Dynamic M-PESA Description
  // ========================================================

  /*
   * Compare the number entered in the modal with the
   * registered user phone number after normalization.
   *
   * This means:
   *
   * 0712345678
   * 254712345678
   * +254712345678
   *
   * are all treated as the same number.
   */
  const registeredMpesaNumber = String(user?.phone_number ?? "");

  const normalizedRegisteredMpesaNumber = normalizePhone(registeredMpesaNumber);

  const normalizedEnteredMpesaNumber = normalizePhone(mpesaPhone);

  const hasEnteredMpesaNumber = mpesaPhone.trim().length > 0;

  const enteredMpesaNumberIsValid = isValidKenyanPhone(
    normalizedEnteredMpesaNumber,
  );

  const isRegisteredMpesaNumber =
    hasEnteredMpesaNumber &&
    enteredMpesaNumberIsValid &&
    normalizedRegisteredMpesaNumber.length > 0 &&
    normalizedEnteredMpesaNumber === normalizedRegisteredMpesaNumber;

  const mpesaDescription = !hasEnteredMpesaNumber
    ? "Enter an M-PESA number to top up your wallet."
    : !enteredMpesaNumberIsValid
      ? "Enter a valid M-PESA number to continue."
      : isRegisteredMpesaNumber
        ? "Top up using your registered M-PESA number."
        : "Top up using another M-PESA number.";

  // ========================================================
  // Open Top-Up
  // ========================================================

  const openTopUp = () => {
    setTopUpOpen(true);

    setTopUpAmount("");

    setTopUpMethod("MPESA");

    setTopUpProvider("SAFARICOM");

    setMpesaPhone(String(user?.phone_number ?? ""));

    setTopUpMessage(null);

    setTopUpStatus(null);

    setTopUpTransaction(null);

    setError(null);
  };

  // ========================================================
  // Close Top-Up
  // ========================================================

  const closeTopUp = () => {
    if (topUpProcessing) {
      return;
    }

    setTopUpOpen(false);

    setTopUpMessage(null);

    setTopUpStatus(null);

    setTopUpTransaction(null);
  };

  // ========================================================
  // Select Top-Up Method
  // ========================================================

  const selectTopUpMethod = (
    method: "MPESA" | "WALLET",
    provider: "SAFARICOM" | "INTERNAL",
  ) => {
    setTopUpMethod(method);

    setTopUpProvider(provider);

    setTopUpMessage(null);

    setTopUpStatus(null);
  };

  // ========================================================
  // Top-Up
  // ========================================================

  const handleTopUp = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (topUpProcessing || !user?.id) {
      return;
    }

    setTopUpMessage(null);

    setTopUpStatus(null);

    setTopUpTransaction(null);

    const amount = Number(topUpAmount);

    if (!Number.isFinite(amount) || amount <= 0) {
      setTopUpMessage("Please enter a valid top-up amount.");
      return;
    }

    if (amount < MIN_TOP_UP_AMOUNT) {
      setTopUpMessage(
        `The minimum wallet top-up is ${formatMoney(
          MIN_TOP_UP_AMOUNT,
          currency,
        )}.`,
      );

      return;
    }

    if (amount > MAX_TOP_UP_AMOUNT) {
      setTopUpMessage(
        `The maximum wallet top-up is ${formatMoney(
          MAX_TOP_UP_AMOUNT,
          currency,
        )}.`,
      );

      return;
    }

    const normalizedPhone = normalizePhone(mpesaPhone);

    if (topUpMethod === "MPESA" && !isValidKenyanPhone(normalizedPhone)) {
      setTopUpMessage(
        "Please enter a valid Kenyan M-PESA number, for example 0712345678 or 254712345678.",
      );

      return;
    }

    setTopUpProcessing(true);

    setTopUpStatus("PROCESSING");

    try {
      /*
       * WalletTopUpCreate extends PaymentBase.
       *
       * Therefore the backend expects the payment
       * details as well as customer_id.
       */
      const response = await api.post<TopUpResponse>("/payments/wallet/topup", {
        payment_method: topUpMethod,

        payment_provider: topUpProvider,

        payment_purpose: "WALLET_TOPUP",

        payment_type: "WALLET_TOPUP",

        currency,

        subtotal_amount: amount,

        discount_amount: 0,

        tax_amount: 0,

        total_amount: amount,

        payer_name: `${user.first_name ?? ""} ${user.last_name ?? ""}`.trim(),

        payer_phone:
          topUpMethod === "MPESA"
            ? normalizedPhone
            : String(user.phone_number ?? ""),

        payer_email: user.email,

        notes: "SmartPark Wallet Top-up",

        customer_id: user.id,
      });

      const result = response.data;

      const status = String(result.status ?? "").toUpperCase();

      setTopUpTransaction(result);

      setTopUpStatus(status);

      if (status === "SUCCESSFUL" || status === "COMPLETED") {
        setTopUpMessage(
          "Wallet top-up successful. Your wallet balance has been updated.",
        );

        setTopUpProcessing(false);

        /*
         * Refresh the wallet immediately so the
         * displayed balance reflects the successful
         * transaction.
         */
        await loadWallet(true);
      } else if (["FAILED", "CANCELLED"].includes(status)) {
        setTopUpMessage(
          "The wallet top-up was not completed. Your wallet balance has not been changed.",
        );

        setTopUpProcessing(false);
      } else {
        /*
         * M-PESA STK Push is asynchronous. Keep the modal
         * locked and let the polling effect below monitor
         * the transaction until the backend reaches a
         * final status.
         */
        setTopUpProcessing(true);

        setTopUpMessage(
          topUpMethod === "MPESA"
            ? "M-PESA top-up request submitted. Complete the payment prompt on your phone. We are waiting for payment confirmation."
            : "Your wallet top-up is being processed. We are waiting for payment confirmation.",
        );
      }
    } catch (err) {
      console.error("[SmartPark Wallet] Top-up failed:", err);

      setTopUpStatus("FAILED");

      setTopUpProcessing(false);

      setTopUpMessage(extractErrorMessage(err));
    }
  };

  // ========================================================
  // Top-up Payment Status Polling
  // ========================================================

  useEffect(() => {
    if (!topUpTransaction) {
      return;
    }

    const initialStatus = String(topUpTransaction.status ?? "").toUpperCase();

    if (!["PENDING", "PROCESSING"].includes(initialStatus)) {
      return;
    }

    let cancelled = false;

    let attempts = 0;

    const maxAttempts = 60;

    let polling = false;

    let intervalId: number | undefined;

    const refreshTopUpStatus = async () => {
      if (cancelled || polling) {
        return;
      }

      polling = true;

      attempts += 1;

      try {
        const response = await api.get<TopUpResponse>(
          `/payments/${topUpTransaction.id}`,
        );

        if (cancelled) {
          return;
        }

        const latestTransaction = response.data;

        const latestStatus = String(
          latestTransaction.status ?? "",
        ).toUpperCase();

        setTopUpTransaction(latestTransaction);

        setTopUpStatus(latestStatus);

        if (latestStatus === "SUCCESSFUL" || latestStatus === "COMPLETED") {
          setTopUpMessage(
            "Wallet top-up successful. Your wallet balance has been updated.",
          );

          setTopUpProcessing(false);

          if (intervalId !== undefined) {
            window.clearInterval(intervalId);
          }

          await loadWallet(true);
        } else if (["FAILED", "CANCELLED"].includes(latestStatus)) {
          setTopUpMessage(
            "The wallet top-up was not completed. Your wallet balance has not been changed.",
          );

          setTopUpProcessing(false);

          if (intervalId !== undefined) {
            window.clearInterval(intervalId);
          }
        } else if (attempts >= maxAttempts) {
          /*
           * Do not mark the payment as failed merely because
           * the polling window expired. The backend may still
           * receive the provider callback. The user may close
           * the modal and check the wallet again later.
           */
          setTopUpMessage(
            "Payment is still pending. We could not confirm the final status yet. Please check your wallet again shortly.",
          );

          setTopUpProcessing(false);

          if (intervalId !== undefined) {
            window.clearInterval(intervalId);
          }
        } else {
          setTopUpProcessing(true);

          setTopUpMessage(
            "Your payment is still being processed. Please wait while we confirm the transaction.",
          );
        }
      } catch (err) {
        /*
         * A temporary polling failure must not turn a real
         * pending payment into FAILED. Continue polling until
         * the maximum number of attempts is reached.
         */
        console.warn("[SmartPark Wallet] Payment status refresh failed:", err);

        if (attempts >= maxAttempts) {
          setTopUpProcessing(false);

          setTopUpMessage(
            "Payment is still pending. We could not confirm the final status yet. Please check your wallet again shortly.",
          );

          if (intervalId !== undefined) {
            window.clearInterval(intervalId);
          }
        }
      } finally {
        polling = false;
      }
    };

    // Check immediately, then every 2 seconds while pending.
    intervalId = window.setInterval(refreshTopUpStatus, 2000);

    void refreshTopUpStatus();

    return () => {
      cancelled = true;

      if (intervalId !== undefined) {
        window.clearInterval(intervalId);
      }
    };
  }, [topUpTransaction?.id, topUpTransaction?.status, loadWallet]);

  // ========================================================
  // Loading Screen
  // ========================================================

  if (loading) {
    return (
      <div className="mx-auto flex min-h-[500px] w-full max-w-6xl items-center justify-center">
        <div className="text-center">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
            <Loader2 size={30} className="animate-spin" />
          </div>

          <h2 className="mt-5 text-lg font-black text-slate-900">
            Loading your wallet
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Retrieving your latest wallet information...
          </p>
        </div>
      </div>
    );
  }

  // ========================================================
  // Main Page
  // ========================================================

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      {/* ====================================================
          PAGE HEADER
      ==================================================== */}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
              <WalletIcon size={26} />
            </div>

            <div>
              <h1 className="text-2xl font-black tracking-tight text-slate-900">
                My Wallet
              </h1>

              <p className="mt-0.5 text-sm font-medium text-slate-500">
                Manage your SmartPark AI wallet and view your wallet activity.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="hidden text-xs font-medium text-slate-400 sm:block">
              Updated {formatDateTime(lastUpdated.toISOString())}
            </span>
          )}

          <button
            type="button"
            onClick={() => void loadWallet(true)}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>

          <button
            type="button"
            onClick={openTopUp}
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-extrabold text-white shadow-sm transition hover:bg-emerald-700"
          >
            <ArrowDownLeft size={17} />
            Top Up
          </button>
        </div>
      </div>

      {/* ====================================================
          ERROR
      ==================================================== */}

      {error && (
        <div
          role="alert"
          className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4"
        >
          <div className="flex items-start gap-3">
            <XCircle size={20} className="mt-0.5 shrink-0 text-rose-600" />

            <div className="min-w-0 flex-1">
              <p className="text-sm font-extrabold text-rose-900">
                Unable to load wallet
              </p>

              <p className="mt-1 text-sm leading-6 text-rose-800">{error}</p>
            </div>

            <button
              type="button"
              onClick={() => setError(null)}
              aria-label="Dismiss error"
              className="text-rose-500 hover:text-rose-700"
            >
              <X />
            </button>
          </div>
        </div>
      )}

      {/* ====================================================
          WALLET HERO
      ==================================================== */}

      <section className="overflow-hidden rounded-3xl bg-[#071a2d] text-white shadow-sm">
        <div className="relative p-6 sm:p-8">
          <div className="absolute -right-16 -top-20 h-56 w-56 rounded-full bg-emerald-400/10 blur-2xl" />

          <div className="relative">
            <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <div className="flex items-center gap-2 text-sm font-bold text-emerald-300">
                  <WalletIcon size={17} />
                  SmartPark Wallet
                </div>

                <p className="mt-5 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Available Balance
                </p>

                <p className="mt-2 text-4xl font-black tracking-tight sm:text-5xl">
                  {formatMoney(availableBalance, currency)}
                </p>

                <p className="mt-2 text-sm font-medium text-slate-400">
                  Spendable wallet balance
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2 lg:min-w-[390px]">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="text-xs font-semibold text-slate-400">
                    Reserved
                  </p>

                  <p className="mt-1 text-lg font-black text-white">
                    {formatMoney(reservedBalance, currency)}
                  </p>
                </div>

                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="text-xs font-semibold text-slate-400">
                    Total Balance
                  </p>

                  <p className="mt-1 text-lg font-black text-white">
                    {formatMoney(totalWalletBalance, currency)}
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-8 flex flex-col gap-3 border-t border-white/10 pt-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-xs font-semibold text-slate-400">
                  Wallet Number
                </p>

                <p className="mt-1 font-mono text-sm font-bold tracking-wide text-white">
                  {wallet?.wallet_number ?? "—"}
                </p>
              </div>

              <div className="flex items-center gap-2">
                <span
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-extrabold ${
                    String(wallet?.status ?? "").toUpperCase() === "ACTIVE"
                      ? "bg-emerald-400/15 text-emerald-300"
                      : "bg-amber-400/15 text-amber-300"
                  }`}
                >
                  <CheckCircle2 size={13} />

                  {wallet?.status ?? "UNKNOWN"}
                </span>

                <span className="rounded-full bg-white/10 px-3 py-1.5 text-xs font-extrabold text-slate-300">
                  {currency}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ====================================================
          SUMMARY CARDS
      ==================================================== */}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <SummaryCard
          icon={<ArrowDownLeft size={20} />}
          title="Total Credited"
          value={formatMoney(totalCredited, currency)}
          description="Funds added to wallet"
          tone="green"
        />

        <SummaryCard
          icon={<ArrowUpRight size={20} />}
          title="Total Debited"
          value={formatMoney(totalDebited, currency)}
          description="Funds used from wallet"
          tone="blue"
        />

        <SummaryCard
          icon={<History size={20} />}
          title="Transactions"
          value={String(statistics?.total_transactions ?? transactions.length)}
          description="Wallet ledger entries"
          tone="purple"
        />

        <SummaryCard
          icon={<CheckCircle2 size={20} />}
          title="Successful"
          value={String(successfulTransactionCount)}
          description="Completed transactions"
          tone="amber"
        />
      </section>

      {/* ====================================================
          LOW BALANCE NOTICE
      ==================================================== */}

      {availableBalance < 500 && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4">
          <div className="flex items-start gap-3">
            <AlertCircle size={19} className="mt-0.5 shrink-0 text-amber-600" />

            <div>
              <p className="text-sm font-extrabold text-amber-900">
                Your wallet balance is low
              </p>

              <p className="mt-1 text-xs leading-5 text-amber-800">
                Consider topping up your wallet before making your next parking
                payment.
              </p>
            </div>

            <button
              type="button"
              onClick={openTopUp}
              className="ml-auto hidden shrink-0 rounded-xl bg-amber-600 px-4 py-2 text-xs font-extrabold text-white transition hover:bg-amber-700 sm:block"
            >
              Top Up
            </button>
          </div>
        </div>
      )}

      {/* ====================================================
          TRANSACTION HISTORY
      ==================================================== */}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-100 px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-black text-slate-900">
              Recent Wallet Activity
            </h2>

            <p className="mt-1 text-xs text-slate-500">
              Your latest wallet transactions.
            </p>
          </div>

          <span className="text-xs font-bold text-slate-400">
            {transactions.length} transaction
            {transactions.length === 1 ? "" : "s"}
          </span>
        </div>

        {transactionError && (
          <div className="border-b border-amber-100 bg-amber-50 px-6 py-3 text-xs font-semibold text-amber-800">
            {transactionError}
          </div>
        )}

        {recentTransactions.length === 0 ? (
          <div className="px-6 py-14 text-center">
            <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-slate-100 text-slate-400">
              <History size={25} />
            </div>

            <h3 className="mt-4 text-sm font-black text-slate-900">
              No wallet transactions yet
            </h3>

            <p className="mx-auto mt-1 max-w-sm text-xs leading-5 text-slate-500">
              Your wallet activity will appear here after your first
              transaction.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {recentTransactions.map((transaction, index) => {
              const credit = isCreditTransaction(transaction);

              const amount = Number(transaction.amount ?? 0);

              const status = resolveTransactionStatus(transaction);

              return (
                <button
                  key={
                    transaction.id ?? transaction.transaction_number ?? index
                  }
                  type="button"
                  onClick={() => setSelectedTransaction(transaction)}
                  className="flex w-full items-center gap-4 px-6 py-4 text-left transition hover:bg-slate-50"
                >
                  <div
                    className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${
                      credit
                        ? "bg-emerald-50 text-emerald-600"
                        : "bg-slate-100 text-slate-600"
                    }`}
                  >
                    {credit ? (
                      <ArrowDownLeft size={20} />
                    ) : (
                      <ArrowUpRight size={20} />
                    )}
                  </div>

                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-extrabold text-slate-900">
                      {transaction.description ||
                        formatTransactionType(transaction.transaction_type)}
                    </p>

                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-400">
                      <span>
                        {formatDateTime(
                          transaction.posted_at ?? transaction.created_at,
                        )}
                      </span>

                      {transaction.transaction_number && (
                        <span className="font-mono">
                          {transaction.transaction_number}
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="shrink-0 text-right">
                    <p
                      className={`text-sm font-black ${
                        credit ? "text-emerald-600" : "text-slate-900"
                      }`}
                    >
                      {credit ? "+" : "-"}
                      {formatMoney(amount, transaction.currency || currency)}
                    </p>

                    <StatusBadge status={status} />
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </section>

      {/* ====================================================
          WALLET INFORMATION
      ==================================================== */}

      <section className="grid gap-4 md:grid-cols-2">
        <InfoCard title="Wallet Information" icon={<WalletIcon size={19} />}>
          <InfoRow
            label="Wallet Number"
            value={wallet?.wallet_number ?? "—"}
            mono
          />

          <InfoRow label="Currency" value={wallet?.currency ?? "KES"} />

          <InfoRow label="Status" value={wallet?.status ?? "—"} />

          <InfoRow label="Created" value={formatDateTime(wallet?.created_at)} />
        </InfoCard>

        <InfoCard title="Wallet Usage" icon={<CreditCard size={19} />}>
          <InfoRow
            label="Available Balance"
            value={formatMoney(availableBalance, currency)}
          />

          <InfoRow
            label="Reserved Balance"
            value={formatMoney(reservedBalance, currency)}
          />

          <InfoRow
            label="Total Credited"
            value={formatMoney(totalCredited, currency)}
          />

          <InfoRow
            label="Total Debited"
            value={formatMoney(totalDebited, currency)}
          />
        </InfoCard>
      </section>

      {/* ====================================================
          TOP-UP MODAL
      ==================================================== */}

      {topUpOpen && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="wallet-topup-title"
        >
          <div className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-3xl bg-white shadow-2xl">
            {/* ==================================================
                Modal Header
            ================================================== */}

            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
              <div className="flex items-center gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                  <ArrowDownLeft size={21} />
                </div>

                <div>
                  <h2
                    id="wallet-topup-title"
                    className="text-lg font-black text-slate-900"
                  >
                    Top Up Wallet
                  </h2>

                  <p className="text-xs text-slate-500">
                    Add funds to your SmartPark wallet.
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={closeTopUp}
                disabled={topUpProcessing}
                aria-label="Close top-up dialog"
                className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 text-slate-500 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <X size={18} />
              </button>
            </div>

            {/* ==================================================
                Modal Content
            ================================================== */}

            <form onSubmit={handleTopUp} className="space-y-5 p-6">
              {/* ----------------------------------------------
                  Current Balance
              ---------------------------------------------- */}

              <div className="rounded-2xl bg-slate-50 p-5">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs font-semibold text-slate-500">
                      Current balance
                    </p>

                    <p className="mt-1 text-2xl font-black text-slate-900">
                      {formatMoney(availableBalance, currency)}
                    </p>
                  </div>

                  <WalletIcon size={30} className="text-emerald-600" />
                </div>
              </div>

              {/* ----------------------------------------------
                  Amount
              ---------------------------------------------- */}

              <div>
                <label
                  htmlFor="topUpAmount"
                  className="mb-2 block text-sm font-extrabold text-slate-800"
                >
                  Top-up Amount
                </label>

                <div className="relative">
                  <span className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-sm font-black text-slate-500">
                    {currency}
                  </span>

                  <input
                    id="topUpAmount"
                    type="number"
                    min={MIN_TOP_UP_AMOUNT}
                    max={MAX_TOP_UP_AMOUNT}
                    step="0.01"
                    value={topUpAmount}
                    onChange={(event) => {
                      setTopUpAmount(event.target.value);

                      setTopUpMessage(null);

                      setTopUpStatus(null);
                    }}
                    placeholder="500.00"
                    inputMode="decimal"
                    disabled={topUpProcessing}
                    className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-14 pr-4 text-sm font-black text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                  />
                </div>

                <p className="mt-1.5 text-xs text-slate-400">
                  Minimum {formatMoney(MIN_TOP_UP_AMOUNT, currency)}
                </p>
              </div>

              {/* ----------------------------------------------
                  Quick Amounts
              ---------------------------------------------- */}

              <div>
                <p className="mb-2 text-xs font-bold uppercase tracking-wide text-slate-400">
                  Quick Select
                </p>

                <div className="grid grid-cols-4 gap-2">
                  {[500, 1000, 2500, 5000].map((amount) => (
                    <button
                      key={amount}
                      type="button"
                      disabled={topUpProcessing}
                      onClick={() => setTopUpAmount(String(amount))}
                      className={`rounded-xl border px-3 py-2.5 text-xs font-extrabold transition ${
                        Number(topUpAmount) === amount
                          ? "border-emerald-500 bg-emerald-50 text-emerald-700"
                          : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                      }`}
                    >
                      {formatMoney(amount, currency)}
                    </button>
                  ))}
                </div>
              </div>

              {/* ----------------------------------------------
                  Payment Method
              ---------------------------------------------- */}

              <div>
                <p className="mb-3 text-sm font-extrabold text-slate-900">
                  Payment Method
                </p>

                <div
                  className={`grid grid-cols-1 gap-3 ${
                    TOP_UP_PAYMENT_OPTIONS.length > 1 ? "sm:grid-cols-2" : ""
                  }`}
                >
                  {TOP_UP_PAYMENT_OPTIONS.map((option) => {
                    const selected = topUpMethod === option.method;

                    const Icon = option.icon;

                    return (
                      <button
                        key={option.method}
                        type="button"
                        disabled={topUpProcessing}
                        onClick={() =>
                          selectTopUpMethod(option.method, option.provider)
                        }
                        className={`rounded-2xl border p-4 text-left transition ${
                          selected
                            ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                            : "border-slate-200 bg-white hover:bg-slate-50"
                        }`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <div className="grid h-10 w-10 place-items-center rounded-xl bg-slate-100 text-slate-600">
                              <Icon size={20} />
                            </div>

                            <span className="text-sm font-black text-slate-900">
                              {option.label}
                            </span>
                          </div>

                          {selected && (
                            <CheckCircle2
                              size={18}
                              className="text-emerald-600"
                            />
                          )}
                        </div>

                        {option.method === "MPESA" ? (
                          <p className="mt-3 text-xs leading-5 text-slate-500">
                            {mpesaDescription}
                          </p>
                        ) : (
                          <p className="mt-3 text-xs leading-5 text-slate-500">
                            {option.description}
                          </p>
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* ----------------------------------------------
                  M-PESA Number
              ---------------------------------------------- */}

              {topUpMethod === "MPESA" && (
                <div>
                  <label
                    htmlFor="mpesaPhone"
                    className="mb-2 block text-sm font-extrabold text-slate-800"
                  >
                    M-PESA Phone Number
                  </label>

                  <input
                    id="mpesaPhone"
                    type="tel"
                    value={mpesaPhone}
                    onChange={(event) => {
                      setMpesaPhone(event.target.value);

                      setTopUpMessage(null);

                      setTopUpStatus(null);
                    }}
                    placeholder="0712345678"
                    inputMode="tel"
                    autoComplete="tel"
                    disabled={topUpProcessing}
                    className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                  />

                  <p className="mt-1.5 text-xs text-slate-400">
                    Example: 0712345678
                  </p>
                </div>
              )}

              {/* ----------------------------------------------
                  Top-Up Message
              ---------------------------------------------- */}

              {topUpMessage && (
                <div
                  className={`rounded-2xl border p-4 ${
                    topUpStatus === "SUCCESSFUL"
                      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
                      : topUpStatus === "FAILED" || topUpStatus === "CANCELLED"
                        ? "border-rose-200 bg-rose-50 text-rose-800"
                        : "border-amber-200 bg-amber-50 text-amber-800"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    {topUpStatus === "SUCCESSFUL" ||
                    topUpStatus === "COMPLETED" ? (
                      <CheckCircle2 size={19} className="mt-0.5 shrink-0" />
                    ) : topUpStatus === "FAILED" ||
                      topUpStatus === "CANCELLED" ? (
                      <XCircle size={19} className="mt-0.5 shrink-0" />
                    ) : (
                      <Loader2
                        size={19}
                        className="mt-0.5 shrink-0 animate-spin"
                      />
                    )}

                    <div>
                      <p className="text-sm font-extrabold">
                        {topUpStatus === "SUCCESSFUL" ||
                        topUpStatus === "COMPLETED"
                          ? "Top-up Successful"
                          : topUpStatus === "FAILED" ||
                              topUpStatus === "CANCELLED"
                            ? "Top-up Failed"
                            : "Top-up Processing"}
                      </p>

                      <p className="mt-1 text-xs leading-5">{topUpMessage}</p>

                      {topUpTransaction?.transaction_number && (
                        <p className="mt-2 font-mono text-[11px] font-bold">
                          Transaction: {topUpTransaction.transaction_number}
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* ----------------------------------------------
                  Actions
              ---------------------------------------------- */}

              <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={closeTopUp}
                  disabled={topUpProcessing}
                  className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Close
                </button>

                <button
                  type="submit"
                  disabled={topUpProcessing || topUpStatus === "SUCCESSFUL"}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-6 py-3 text-sm font-extrabold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {topUpProcessing ? (
                    <>
                      <Loader2 size={17} className="animate-spin" />
                      Processing...
                    </>
                  ) : (
                    <>
                      <CreditCard size={17} />
                      Top Up Wallet
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ====================================================
          TRANSACTION DETAILS MODAL
      ==================================================== */}

      {selectedTransaction && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="transaction-details-title"
        >
          <div className="w-full max-w-lg overflow-hidden rounded-3xl bg-white shadow-2xl">
            {/* ----------------------------------------------
                Header
            ---------------------------------------------- */}

            <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
              <div>
                <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
                  Wallet Transaction
                </p>

                <h2
                  id="transaction-details-title"
                  className="mt-1 text-lg font-black text-slate-900"
                >
                  Transaction Details
                </h2>
              </div>

              <button
                type="button"
                onClick={() => setSelectedTransaction(null)}
                className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 text-slate-500 transition hover:bg-slate-50"
                aria-label="Close transaction details"
              >
                <X size={18} />
              </button>
            </div>

            {/* ----------------------------------------------
                Details
            ---------------------------------------------- */}

            <div className="space-y-5 p-6">
              <div
                className={`rounded-2xl p-5 ${
                  isCreditTransaction(selectedTransaction)
                    ? "bg-emerald-50"
                    : "bg-slate-50"
                }`}
              >
                <p className="text-xs font-semibold text-slate-500">Amount</p>

                <p
                  className={`mt-1 text-3xl font-black ${
                    isCreditTransaction(selectedTransaction)
                      ? "text-emerald-600"
                      : "text-slate-900"
                  }`}
                >
                  {isCreditTransaction(selectedTransaction) ? "+" : "-"}
                  {formatMoney(
                    selectedTransaction.amount,
                    selectedTransaction.currency || currency,
                  )}
                </p>
              </div>

              <div className="space-y-0 divide-y divide-slate-100 rounded-2xl border border-slate-100">
                <DetailRow
                  label="Transaction Number"
                  value={selectedTransaction.transaction_number ?? "—"}
                  mono
                />

                <DetailRow
                  label="Reference"
                  value={selectedTransaction.reference ?? "—"}
                  mono
                />

                <DetailRow
                  label="Transaction Type"
                  value={formatTransactionType(
                    selectedTransaction.transaction_type,
                  )}
                />

                <DetailRow
                  label="Status"
                  value={resolveTransactionStatus(selectedTransaction)}
                />

                <DetailRow
                  label="Posted"
                  value={formatDateTime(
                    selectedTransaction.posted_at ??
                      selectedTransaction.created_at,
                  )}
                />

                <DetailRow
                  label="Balance Before"
                  value={formatMoney(
                    selectedTransaction.balance_before,
                    selectedTransaction.currency || currency,
                  )}
                />

                <DetailRow
                  label="Balance After"
                  value={formatMoney(
                    selectedTransaction.balance_after,
                    selectedTransaction.currency || currency,
                  )}
                />

                <DetailRow
                  label="Description"
                  value={selectedTransaction.description ?? "—"}
                />
              </div>

              {selectedTransaction.notes && (
                <div className="rounded-2xl bg-slate-50 p-4">
                  <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
                    Notes
                  </p>

                  <p className="mt-1.5 text-sm leading-6 text-slate-700">
                    {selectedTransaction.notes}
                  </p>
                </div>
              )}
            </div>

            {/* ----------------------------------------------
                Footer
            ---------------------------------------------- */}

            <div className="border-t border-slate-100 px-6 py-4">
              <button
                type="button"
                onClick={() => setSelectedTransaction(null)}
                className="w-full rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ==========================================================
// Summary Card
// ==========================================================

function SummaryCard({
  icon,
  title,
  value,
  description,
  tone,
}: {
  icon: React.ReactNode;
  title: string;
  value: string;
  description: string;
  tone: "green" | "blue" | "purple" | "amber";
}) {
  const toneClasses = {
    green: "bg-emerald-50 text-emerald-600",
    blue: "bg-blue-50 text-blue-600",
    purple: "bg-violet-50 text-violet-600",
    amber: "bg-amber-50 text-amber-600",
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div
        className={`grid h-10 w-10 place-items-center rounded-xl ${toneClasses[tone]}`}
      >
        {icon}
      </div>

      <p className="mt-4 text-xs font-bold uppercase tracking-wide text-slate-400">
        {title}
      </p>

      <p className="mt-1 text-xl font-black tracking-tight text-slate-900">
        {value}
      </p>

      <p className="mt-1 text-xs text-slate-500">{description}</p>
    </div>
  );
}

// ==========================================================
// Status Badge
// ==========================================================

function StatusBadge({ status }: { status: string }) {
  const normalized = status.toUpperCase();

  const classes =
    normalized === "COMPLETED" || normalized === "SUCCESSFUL"
      ? "bg-emerald-50 text-emerald-700"
      : normalized === "PENDING" || normalized === "PROCESSING"
        ? "bg-amber-50 text-amber-700"
        : normalized === "FAILED" ||
            normalized === "CANCELLED" ||
            normalized === "REVERSED"
          ? "bg-rose-50 text-rose-700"
          : "bg-slate-100 text-slate-600";

  return (
    <span
      className={`mt-1 inline-flex rounded-full px-2 py-0.5 text-[10px] font-extrabold ${classes}`}
    >
      {status
        .replace(/_/g, " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase())}
    </span>
  );
}

// ==========================================================
// Info Card
// ==========================================================

function InfoCard({
  title,
  icon,
  children,
}: {
  title: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-center gap-2 border-b border-slate-100 px-6 py-5">
        <span className="text-emerald-600">{icon}</span>

        <h2 className="text-base font-black text-slate-900">{title}</h2>
      </div>

      <div className="divide-y divide-slate-100">{children}</div>
    </section>
  );
}

// ==========================================================
// Info Row
// ==========================================================

function InfoRow({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-5 px-6 py-4">
      <span className="text-xs font-semibold text-slate-500">{label}</span>

      <span
        className={`text-right text-sm font-extrabold text-slate-800 ${
          mono ? "font-mono" : ""
        }`}
      >
        {value}
      </span>
    </div>
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
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-5">
      <span className="text-xs font-semibold text-slate-500">{label}</span>

      <span
        className={`break-all text-sm font-extrabold text-slate-800 sm:text-right ${
          mono ? "font-mono text-xs" : ""
        }`}
      >
        {value}
      </span>
    </div>
  );
}
