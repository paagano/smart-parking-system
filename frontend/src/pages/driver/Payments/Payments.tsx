import { useCallback, useEffect, useMemo, useState } from "react";

import {
  AlertCircle,
  ArrowDownLeft,
  ArrowUpRight,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  CreditCard,
  FileText,
  History,
  Loader2,
  RefreshCw,
  Search,
  Smartphone,
  Wallet,
  X,
  XCircle,
} from "lucide-react";

import { useAuth } from "../../../auth/AuthContext";
import { api } from "../../../api";
import { useLocation } from "react-router";
import SessionPayment from "./SessionPayment";

// ==========================================================
// Types
// ==========================================================

interface Payment {
  id: number;

  reservation_id?: number | null;
  parking_session_id?: number | null;
  customer_id?: number | null;
  parent_transaction_id?: number | null;

  transaction_number?: string | null;

  receipt_number?: string | null;

  payment_method?: string | null;
  payment_provider?: string | null;
  payment_purpose?: string | null;
  payment_type?: string | null;

  currency?: string | null;

  subtotal_amount?: number | string | null;
  discount_amount?: number | string | null;
  tax_amount?: number | string | null;
  total_amount?: number | string | null;

  status?: string | null;

  provider_transaction_id?: string | null;
  provider_receipt_number?: string | null;
  provider_status_message?: string | null;

  payer_name?: string | null;
  payer_phone?: string | null;
  payer_email?: string | null;

  notes?: string | null;

  paid_at?: string | null;
  created_at?: string | null;
  updated_at?: string | null;

  reconciled?: boolean;
  is_reconciled?: boolean;
}

interface PaymentListResponse {
  items: Payment[];
  total: number;
}

interface PaymentStats {
  total: number;
  successful: number;
  pending: number;
  failed: number;
  refunded: number;
  totalAmount: number;
}

// ==========================================================
// Constants
// ==========================================================

const PAGE_SIZE = 10;

const PAYMENT_STATUSES = [
  "ALL",
  "SUCCESSFUL",
  "PENDING",
  "PROCESSING",
  "FAILED",
  "CANCELLED",
  "REFUNDED",
  "PARTIALLY_REFUNDED",
  "REVERSED",
];

const PAYMENT_METHODS = ["ALL", "WALLET", "MPESA", "CARD", "BANK", "CASH"];

// ==========================================================
// Helpers
// ==========================================================

function money(
  amount: number | string | null | undefined,
  currency = "KES",
): string {
  const value = Number(amount ?? 0);

  if (!Number.isFinite(value)) {
    return `${currency} 0.00`;
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

function dateTime(value: string | null | undefined): string {
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

function displayText(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }

  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function statusLabel(value: string | null | undefined): string {
  return displayText(value ?? "UNKNOWN");
}

function extractError(error: any): string {
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
      return "You are not authorized to access these payments.";

    case 404:
      return "The requested payment could not be found.";

    case 422:
      return "The payment information supplied is invalid.";

    default:
      return "Unable to retrieve payment information. Please try again.";
  }
}

function isSuccessful(payment: Payment): boolean {
  return String(payment.status ?? "").toUpperCase() === "SUCCESSFUL";
}

function isRefund(payment: Payment): boolean {
  const status = String(payment.status ?? "").toUpperCase();

  const purpose = String(payment.payment_purpose ?? "").toUpperCase();

  const type = String(payment.payment_type ?? "").toUpperCase();

  return (
    status.includes("REFUND") ||
    purpose.includes("REFUND") ||
    type.includes("REFUND")
  );
}

function paymentIsCredit(payment: Payment): boolean {
  if (isRefund(payment)) {
    return true;
  }

  const purpose = String(payment.payment_purpose ?? "").toUpperCase();

  const type = String(payment.payment_type ?? "").toUpperCase();

  return (
    purpose.includes("TOP_UP") ||
    purpose.includes("CREDIT") ||
    type.includes("TOP_UP")
  );
}

function paymentTitle(payment: Payment): string {
  if (isRefund(payment)) {
    return "Payment Refund";
  }

  const purpose = payment.payment_purpose;

  if (purpose) {
    return displayText(purpose);
  }

  if (payment.parking_session_id) {
    return "Parking Session Payment";
  }

  if (payment.reservation_id) {
    return "Reservation Payment";
  }

  return "Payment";
}

// ==========================================================
// Component
// ==========================================================

function PaymentsHistory() {
  const { user } = useAuth();

  // ========================================================
  // Data State
  // ========================================================

  const [payments, setPayments] = useState<Payment[]>([]);

  const [loading, setLoading] = useState(true);

  const [refreshing, setRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [selectedPayment, setSelectedPayment] = useState<Payment | null>(null);

  // ========================================================
  // Search / Filter State
  // ========================================================

  const [searchTerm, setSearchTerm] = useState("");

  const [statusFilter, setStatusFilter] = useState("ALL");

  const [methodFilter, setMethodFilter] = useState("ALL");

  const [currentPage, setCurrentPage] = useState(1);

  // ========================================================
  // Date Filter
  // ========================================================

  const [dateFrom, setDateFrom] = useState("");

  const [dateTo, setDateTo] = useState("");

  // ========================================================
  // Receipt Search
  // ========================================================

  const [receiptSearch, setReceiptSearch] = useState("");

  const [receiptLoading, setReceiptLoading] = useState(false);

  const [receiptError, setReceiptError] = useState<string | null>(null);

  // ========================================================
  // Load Payments
  // ========================================================

  const loadPayments = useCallback(
    async (manualRefresh = false) => {
      if (!user?.id) {
        setPayments([]);
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
        /*
         * The backend exposes:
         *
         * GET /payments/customer/{customer_id}
         *
         * with limit and offset.
         *
         * We deliberately request a sufficiently large
         * customer history and perform presentation-level
         * filtering in this page.
         */
        const response = await api.get<Payment[]>(
          `/payments/customer/${user.id}`,
          {
            params: {
              limit: 500,
              offset: 0,
            },
          },
        );

        const data = response.data;

        if (Array.isArray(data)) {
          setPayments(data);
        } else if (Array.isArray((data as any)?.items)) {
          setPayments((data as any).items);
        } else if (Array.isArray((data as any)?.payments)) {
          setPayments((data as any).payments);
        } else {
          setPayments([]);
        }
      } catch (err) {
        console.error("[SmartPark Payments] Failed to load payments:", err);

        setError(extractError(err));
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
    void loadPayments();
  }, [loadPayments]);

  // ========================================================
  // Filter Payments
  // ========================================================

  const filteredPayments = useMemo(() => {
    const search = searchTerm.trim().toLowerCase();

    return payments
      .filter((payment) => {
        if (
          statusFilter !== "ALL" &&
          String(payment.status ?? "").toUpperCase() !== statusFilter
        ) {
          return false;
        }

        if (
          methodFilter !== "ALL" &&
          String(payment.payment_method ?? "").toUpperCase() !== methodFilter
        ) {
          return false;
        }

        if (search) {
          const searchable = [
            payment.transaction_number,
            payment.receipt_number,
            payment.provider_transaction_id,
            payment.provider_receipt_number,
            payment.payment_method,
            payment.payment_provider,
            payment.payment_purpose,
            payment.payment_type,
            payment.parking_session_id
              ? String(payment.parking_session_id)
              : "",
            payment.reservation_id ? String(payment.reservation_id) : "",
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();

          if (!searchable.includes(search)) {
            return false;
          }
        }

        const timestamp = payment.paid_at ?? payment.created_at;

        if (dateFrom && timestamp) {
          const start = new Date(`${dateFrom}T00:00:00`);

          const paymentDate = new Date(timestamp);

          if (paymentDate < start) {
            return false;
          }
        }

        if (dateTo && timestamp) {
          const end = new Date(`${dateTo}T23:59:59.999`);

          const paymentDate = new Date(timestamp);

          if (paymentDate > end) {
            return false;
          }
        }

        return true;
      })
      .sort((a, b) => {
        const first = new Date(a.paid_at ?? a.created_at ?? "").getTime();

        const second = new Date(b.paid_at ?? b.created_at ?? "").getTime();

        return second - first;
      });
  }, [payments, searchTerm, statusFilter, methodFilter, dateFrom, dateTo]);

  // ========================================================
  // Pagination
  // ========================================================

  const totalPages = Math.max(
    1,
    Math.ceil(filteredPayments.length / PAGE_SIZE),
  );

  const safePage = Math.min(currentPage, totalPages);

  const paginatedPayments = filteredPayments.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  );

  // ========================================================
  // Statistics
  // ========================================================

  const statistics = useMemo<PaymentStats>(() => {
    const successful = payments.filter(isSuccessful);

    const pending = payments.filter((payment) => {
      const status = String(payment.status ?? "").toUpperCase();

      return ["PENDING", "PROCESSING"].includes(status);
    });

    const failed = payments.filter((payment) => {
      const status = String(payment.status ?? "").toUpperCase();

      return ["FAILED", "CANCELLED"].includes(status);
    });

    const refunded = payments.filter(isRefund);

    const totalAmount = successful.reduce(
      (total, payment) => total + Number(payment.total_amount ?? 0),
      0,
    );

    return {
      total: payments.length,
      successful: successful.length,
      pending: pending.length,
      failed: failed.length,
      refunded: refunded.length,
      totalAmount,
    };
  }, [payments]);

  // ========================================================
  // Reset Filters
  // ========================================================

  const resetFilters = () => {
    setSearchTerm("");
    setStatusFilter("ALL");
    setMethodFilter("ALL");
    setDateFrom("");
    setDateTo("");
    setCurrentPage(1);
  };

  // ========================================================
  // Receipt Lookup
  // ========================================================

  const searchReceipt = async () => {
    const receipt = receiptSearch.trim();

    if (!receipt) {
      setReceiptError("Enter a receipt number.");
      return;
    }

    setReceiptLoading(true);
    setReceiptError(null);

    try {
      const response = await api.get<Payment>(
        `/payments/receipt/${encodeURIComponent(receipt)}`,
      );

      setSelectedPayment(response.data);
    } catch (err) {
      setReceiptError(extractError(err));
    } finally {
      setReceiptLoading(false);
    }
  };

  // ========================================================
  // Payment Lookup
  // ========================================================

  const lookupTransaction = async () => {
    const transaction = searchTerm.trim();

    if (!transaction) {
      return;
    }

    /*
     * Only attempt direct transaction lookup when
     * the search resembles a SmartPark payment number.
     *
     * Example:
     * PAY-20260802-143255-A3F9C2
     */
    if (!transaction.toUpperCase().startsWith("PAY-")) {
      return;
    }

    try {
      const response = await api.get<Payment>(
        `/payments/transaction/${encodeURIComponent(transaction)}`,
      );

      setSelectedPayment(response.data);
    } catch (err) {
      setError(extractError(err));
    }
  };

  // ========================================================
  // Loading
  // ========================================================

  if (loading) {
    return (
      <div className="mx-auto flex min-h-[500px] w-full max-w-6xl items-center justify-center">
        <div className="text-center">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
            <Loader2 size={30} className="animate-spin" />
          </div>

          <h2 className="mt-5 text-lg font-black text-slate-900">
            Loading payments
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Retrieving your payment history...
          </p>
        </div>
      </div>
    );
  }

  // ========================================================
  // Main
  // ========================================================

  return (
    <div className="mx-auto w-full max-w-6xl space-y-6">
      {/* ====================================================
          Header
      ==================================================== */}

      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
              <CreditCard size={25} />
            </div>

            <div>
              <h1 className="text-2xl font-black tracking-tight text-slate-900">
                Payments
              </h1>

              <p className="mt-0.5 text-sm font-medium text-slate-500">
                View and manage your SmartPark AI payment history.
              </p>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => void loadPayments(true)}
          disabled={refreshing}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {/* ====================================================
          Error
      ==================================================== */}

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4">
          <div className="flex items-start gap-3">
            <AlertCircle size={20} className="mt-0.5 shrink-0 text-rose-600" />

            <div className="flex-1">
              <p className="text-sm font-extrabold text-rose-900">
                Payment information unavailable
              </p>

              <p className="mt-1 text-sm text-rose-800">{error}</p>
            </div>

            <button
              type="button"
              onClick={() => setError(null)}
              className="text-rose-500 hover:text-rose-700"
            >
              <X size={18} />
            </button>
          </div>
        </div>
      )}

      {/* ====================================================
          Statistics
      ==================================================== */}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <PaymentStatCard
          icon={<History size={20} />}
          label="Total Payments"
          value={String(statistics.total)}
          description="All recorded transactions"
          tone="slate"
        />

        <PaymentStatCard
          icon={<CheckCircle2 size={20} />}
          label="Successful"
          value={String(statistics.successful)}
          description="Successfully completed"
          tone="green"
        />

        <PaymentStatCard
          icon={<Clock3 size={20} />}
          label="Pending"
          value={String(statistics.pending)}
          description="Awaiting completion"
          tone="amber"
        />

        <PaymentStatCard
          icon={<CreditCard size={20} />}
          label="Amount Paid"
          value={money(statistics.totalAmount)}
          description="Successful payments"
          tone="blue"
        />
      </section>

      {/* ====================================================
          Receipt Lookup
      ==================================================== */}

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
          <div className="flex-1">
            <div className="mb-2 flex items-center gap-2">
              <FileText size={17} className="text-emerald-600" />

              <label className="text-sm font-extrabold text-slate-800">
                Find a Payment / Receipt
              </label>
            </div>

            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                type="text"
                value={receiptSearch}
                onChange={(event) => {
                  setReceiptSearch(event.target.value);
                  setReceiptError(null);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void searchReceipt();
                  }
                }}
                placeholder="Enter receipt number e.g. RCP-..."
                className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />

              <button
                type="button"
                onClick={() => void searchReceipt()}
                disabled={receiptLoading}
                className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-extrabold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {receiptLoading ? (
                  <Loader2 size={16} className="animate-spin" />
                ) : (
                  <Search size={16} />
                )}
                Search
              </button>
            </div>

            {receiptError && (
              <p className="mt-2 text-xs font-semibold text-rose-600">
                {receiptError}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* ====================================================
          Filters
      ==================================================== */}

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid gap-4 xl:grid-cols-[2fr_1fr_1fr_1fr_1fr_auto]">
          {/* Search */}

          <div>
            <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-400">
              Search
            </label>

            <div className="relative">
              <Search
                size={17}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />

              <input
                type="search"
                value={searchTerm}
                onChange={(event) => {
                  setSearchTerm(event.target.value);
                  setCurrentPage(1);
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void lookupTransaction();
                  }
                }}
                placeholder="Transaction, receipt, provider..."
                className="w-full rounded-xl border border-slate-200 py-2.5 pl-10 pr-4 text-sm font-semibold outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />
            </div>
          </div>

          {/* Status */}

          <FilterSelect
            label="Status"
            value={statusFilter}
            onChange={(value) => {
              setStatusFilter(value);
              setCurrentPage(1);
            }}
            options={PAYMENT_STATUSES}
          />

          {/* Method */}

          <FilterSelect
            label="Method"
            value={methodFilter}
            onChange={(value) => {
              setMethodFilter(value);
              setCurrentPage(1);
            }}
            options={PAYMENT_METHODS}
          />

          {/* From */}

          <div>
            <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-400">
              From
            </label>

            <input
              type="date"
              value={dateFrom}
              onChange={(event) => {
                setDateFrom(event.target.value);
                setCurrentPage(1);
              }}
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-semibold outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            />
          </div>

          {/* To */}

          <div>
            <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-400">
              To
            </label>

            <input
              type="date"
              value={dateTo}
              onChange={(event) => {
                setDateTo(event.target.value);
                setCurrentPage(1);
              }}
              className="w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-semibold outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            />
          </div>

          {/* Reset */}

          <button
            type="button"
            onClick={resetFilters}
            className="self-end rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-extrabold text-slate-600 transition hover:bg-slate-50"
          >
            Reset
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-4">
          <p className="text-xs font-semibold text-slate-400">
            Showing{" "}
            <span className="font-black text-slate-700">
              {filteredPayments.length}
            </span>{" "}
            matching payment
            {filteredPayments.length === 1 ? "" : "s"}
          </p>

          {(searchTerm ||
            statusFilter !== "ALL" ||
            methodFilter !== "ALL" ||
            dateFrom ||
            dateTo) && (
            <span className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-extrabold text-emerald-700">
              Filters active
            </span>
          )}
        </div>
      </section>

      {/* ====================================================
          Payment Table
      ==================================================== */}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
          <div>
            <h2 className="text-base font-black text-slate-900">
              Payment History
            </h2>

            <p className="mt-1 text-xs text-slate-500">
              Your SmartPark AI financial transactions.
            </p>
          </div>

          <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-extrabold text-slate-600">
            {filteredPayments.length} records
          </span>
        </div>

        {paginatedPayments.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-slate-100 text-slate-400">
              <CreditCard size={27} />
            </div>

            <h3 className="mt-4 text-sm font-black text-slate-900">
              No payments found
            </h3>

            <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-slate-500">
              There are no payment transactions matching your current search and
              filter criteria.
            </p>

            <button
              type="button"
              onClick={resetFilters}
              className="mt-5 rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-extrabold text-slate-700 hover:bg-slate-50"
            >
              Clear Filters
            </button>
          </div>
        ) : (
          <>
            {/* Desktop */}

            <div className="hidden overflow-x-auto md:block">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50/70">
                    <th className="px-6 py-3 text-left text-[11px] font-black uppercase tracking-wide text-slate-400">
                      Payment
                    </th>

                    <th className="px-4 py-3 text-left text-[11px] font-black uppercase tracking-wide text-slate-400">
                      Method
                    </th>

                    <th className="px-4 py-3 text-left text-[11px] font-black uppercase tracking-wide text-slate-400">
                      Date
                    </th>

                    <th className="px-4 py-3 text-right text-[11px] font-black uppercase tracking-wide text-slate-400">
                      Amount
                    </th>

                    <th className="px-4 py-3 text-left text-[11px] font-black uppercase tracking-wide text-slate-400">
                      Status
                    </th>

                    <th className="px-6 py-3 text-right text-[11px] font-black uppercase tracking-wide text-slate-400">
                      Action
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-100">
                  {paginatedPayments.map((payment) => (
                    <PaymentTableRow
                      key={payment.id}
                      payment={payment}
                      currency={payment.currency ?? "KES"}
                      onView={() => setSelectedPayment(payment)}
                    />
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile */}

            <div className="divide-y divide-slate-100 md:hidden">
              {paginatedPayments.map((payment) => (
                <PaymentMobileCard
                  key={payment.id}
                  payment={payment}
                  currency={payment.currency ?? "KES"}
                  onView={() => setSelectedPayment(payment)}
                />
              ))}
            </div>
          </>
        )}

        {/* Pagination */}

        {filteredPayments.length > PAGE_SIZE && (
          <div className="flex items-center justify-between border-t border-slate-100 px-6 py-4">
            <p className="text-xs font-semibold text-slate-500">
              Page <span className="font-black text-slate-800">{safePage}</span>{" "}
              of <span className="font-black text-slate-800">{totalPages}</span>
            </p>

            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={safePage <= 1}
                onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
                className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="Previous page"
              >
                <ChevronLeft size={17} />
              </button>

              <button
                type="button"
                disabled={safePage >= totalPages}
                onClick={() =>
                  setCurrentPage((page) => Math.min(totalPages, page + 1))
                }
                className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 text-slate-600 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                aria-label="Next page"
              >
                <ChevronRight size={17} />
              </button>
            </div>
          </div>
        )}
      </section>

      {/* ====================================================
          Payment Details Modal
      ==================================================== */}

      {selectedPayment && (
        <PaymentDetailsModal
          payment={selectedPayment}
          onClose={() => setSelectedPayment(null)}
        />
      )}
    </div>
  );
}

// ==========================================================
// Payment Table Row
// ==========================================================

function PaymentTableRow({
  payment,
  currency,
  onView,
}: {
  payment: Payment;
  currency: string;
  onView: () => void;
}) {
  const credit = paymentIsCredit(payment);

  const amount = Number(payment.total_amount ?? 0);

  return (
    <tr className="group transition hover:bg-slate-50/80">
      <td className="px-6 py-4">
        <div className="flex items-center gap-3">
          <div
            className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${
              credit
                ? "bg-emerald-50 text-emerald-600"
                : "bg-blue-50 text-blue-600"
            }`}
          >
            {credit ? <ArrowDownLeft size={18} /> : <ArrowUpRight size={18} />}
          </div>

          <div className="min-w-0">
            <p className="max-w-[230px] truncate text-sm font-extrabold text-slate-900">
              {paymentTitle(payment)}
            </p>

            <p className="mt-0.5 truncate font-mono text-[10px] font-bold text-slate-400">
              {payment.transaction_number ?? `Payment #${payment.id}`}
            </p>

            {payment.receipt_number && (
              <p className="mt-0.5 truncate text-[10px] font-semibold text-slate-400">
                Receipt: {payment.receipt_number}
              </p>
            )}
          </div>
        </div>
      </td>

      <td className="px-4 py-4">
        <div className="text-xs font-extrabold text-slate-700">
          {displayText(payment.payment_method)}
        </div>

        <div className="mt-0.5 text-[10px] font-semibold text-slate-400">
          {displayText(payment.payment_provider)}
        </div>
      </td>

      <td className="px-4 py-4">
        <p className="text-xs font-bold text-slate-700">
          {dateTime(payment.paid_at ?? payment.created_at)}
        </p>
      </td>

      <td className="px-4 py-4 text-right">
        <p
          className={`text-sm font-black ${
            credit ? "text-emerald-600" : "text-slate-900"
          }`}
        >
          {credit ? "+" : ""}
          {money(amount, currency)}
        </p>
      </td>

      <td className="px-4 py-4">
        <PaymentStatusBadge status={payment.status} />
      </td>

      <td className="px-6 py-4 text-right">
        <button
          type="button"
          onClick={onView}
          className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-extrabold text-slate-700 transition hover:bg-slate-50"
        >
          View
        </button>
      </td>
    </tr>
  );
}

// ==========================================================
// Mobile Payment Card
// ==========================================================

function PaymentMobileCard({
  payment,
  currency,
  onView,
}: {
  payment: Payment;
  currency: string;
  onView: () => void;
}) {
  const credit = paymentIsCredit(payment);

  return (
    <button
      type="button"
      onClick={onView}
      className="block w-full p-5 text-left transition hover:bg-slate-50"
    >
      <div className="flex items-start gap-3">
        <div
          className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${
            credit
              ? "bg-emerald-50 text-emerald-600"
              : "bg-blue-50 text-blue-600"
          }`}
        >
          {credit ? <ArrowDownLeft size={19} /> : <ArrowUpRight size={19} />}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-extrabold text-slate-900">
                {paymentTitle(payment)}
              </p>

              <p className="mt-1 truncate font-mono text-[10px] font-bold text-slate-400">
                {payment.transaction_number ?? `Payment #${payment.id}`}
              </p>
            </div>

            <p
              className={`shrink-0 text-sm font-black ${
                credit ? "text-emerald-600" : "text-slate-900"
              }`}
            >
              {credit ? "+" : ""}
              {money(payment.total_amount, currency)}
            </p>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <PaymentStatusBadge status={payment.status} />

            <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold text-slate-500">
              {displayText(payment.payment_method)}
            </span>

            <span className="text-[10px] font-semibold text-slate-400">
              {dateTime(payment.paid_at ?? payment.created_at)}
            </span>
          </div>
        </div>
      </div>
    </button>
  );
}

// ==========================================================
// Payment Status Badge
// ==========================================================

function PaymentStatusBadge({ status }: { status: string | null | undefined }) {
  const normalized = String(status ?? "UNKNOWN").toUpperCase();

  let classes = "bg-slate-100 text-slate-600";

  let Icon = AlertCircle;

  if (["SUCCESSFUL", "COMPLETED"].includes(normalized)) {
    classes = "bg-emerald-50 text-emerald-700";
    Icon = CheckCircle2;
  } else if (["PENDING", "PROCESSING"].includes(normalized)) {
    classes = "bg-amber-50 text-amber-700";
    Icon = Clock3;
  } else if (["FAILED", "CANCELLED"].includes(normalized)) {
    classes = "bg-rose-50 text-rose-700";
    Icon = XCircle;
  } else if (["REFUNDED", "PARTIALLY_REFUNDED"].includes(normalized)) {
    classes = "bg-violet-50 text-violet-700";
    Icon = ArrowDownLeft;
  } else if (normalized === "REVERSED") {
    classes = "bg-orange-50 text-orange-700";
    Icon = ArrowDownLeft;
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-extrabold ${classes}`}
    >
      <Icon size={12} />

      {statusLabel(status)}
    </span>
  );
}

// ==========================================================
// Statistics Card
// ==========================================================

function PaymentStatCard({
  icon,
  label,
  value,
  description,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  description: string;
  tone: "slate" | "green" | "amber" | "blue";
}) {
  const classes = {
    slate: "bg-slate-100 text-slate-600",
    green: "bg-emerald-50 text-emerald-600",
    amber: "bg-amber-50 text-amber-600",
    blue: "bg-blue-50 text-blue-600",
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div
        className={`grid h-10 w-10 place-items-center rounded-xl ${classes[tone]}`}
      >
        {icon}
      </div>

      <p className="mt-4 text-xs font-bold uppercase tracking-wide text-slate-400">
        {label}
      </p>

      <p className="mt-1 truncate text-xl font-black tracking-tight text-slate-900">
        {value}
      </p>

      <p className="mt-1 text-xs text-slate-500">{description}</p>
    </div>
  );
}

// ==========================================================
// Filter Select
// ==========================================================

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <div>
      <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-400">
        {label}
      </label>

      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm font-semibold text-slate-700 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
      >
        {options.map((option) => (
          <option key={option} value={option}>
            {option === "ALL" ? "All" : displayText(option)}
          </option>
        ))}
      </select>
    </div>
  );
}

// ==========================================================
// Payment Details Modal
// ==========================================================

function PaymentDetailsModal({
  payment,
  onClose,
}: {
  payment: Payment;
  onClose: () => void;
}) {
  const currency = payment.currency ?? "KES";

  const credit = paymentIsCredit(payment);

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="payment-details-title"
    >
      <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white shadow-2xl">
        {/* Header */}

        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
          <div>
            <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
              SmartPark AI
            </p>

            <h2
              id="payment-details-title"
              className="mt-1 text-lg font-black text-slate-900"
            >
              Payment Details
            </h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 text-slate-500 transition hover:bg-slate-50"
            aria-label="Close payment details"
          >
            <X size={18} />
          </button>
        </div>

        {/* Amount */}

        <div
          className={`mx-6 mt-6 rounded-2xl p-6 ${
            credit ? "bg-emerald-50" : "bg-slate-50"
          }`}
        >
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-semibold text-slate-500">
                {paymentTitle(payment)}
              </p>

              <p
                className={`mt-1 text-3xl font-black ${
                  credit ? "text-emerald-600" : "text-slate-900"
                }`}
              >
                {credit ? "+" : ""}
                {money(payment.total_amount, currency)}
              </p>
            </div>

            <PaymentStatusBadge status={payment.status} />
          </div>
        </div>

        {/* Details */}

        <div className="space-y-6 p-6">
          <DetailsSection title="Transaction">
            <DetailItem
              label="Transaction Number"
              value={payment.transaction_number}
              mono
            />

            <DetailItem
              label="Payment ID"
              value={payment.id ? String(payment.id) : null}
            />

            <DetailItem
              label="Payment Purpose"
              value={displayText(payment.payment_purpose)}
            />

            <DetailItem
              label="Payment Type"
              value={displayText(payment.payment_type)}
            />

            <DetailItem
              label="Date / Time"
              value={dateTime(payment.paid_at ?? payment.created_at)}
            />
          </DetailsSection>

          <DetailsSection title="Payment Method">
            <DetailItem
              label="Method"
              value={displayText(payment.payment_method)}
            />

            <DetailItem
              label="Provider"
              value={displayText(payment.payment_provider)}
            />

            <DetailItem
              label="Provider Transaction"
              value={payment.provider_transaction_id}
              mono
            />

            <DetailItem
              label="Provider Receipt"
              value={payment.provider_receipt_number}
              mono
            />

            <DetailItem
              label="Provider Message"
              value={payment.provider_status_message}
            />
          </DetailsSection>

          <DetailsSection title="Amount Breakdown">
            <DetailItem
              label="Subtotal"
              value={money(payment.subtotal_amount, currency)}
            />

            <DetailItem
              label="Discount"
              value={money(payment.discount_amount, currency)}
            />

            <DetailItem
              label="Tax"
              value={money(payment.tax_amount, currency)}
            />

            <DetailItem
              label="Total"
              value={money(payment.total_amount, currency)}
              emphasis
            />
          </DetailsSection>

          <DetailsSection title="Related SmartPark Record">
            <DetailItem
              label="Parking Session"
              value={
                payment.parking_session_id
                  ? String(payment.parking_session_id)
                  : null
              }
            />

            <DetailItem
              label="Reservation"
              value={
                payment.reservation_id ? String(payment.reservation_id) : null
              }
            />

            <DetailItem
              label="Receipt Number"
              value={payment.receipt_number}
              mono
            />

            <DetailItem
              label="Parent Transaction"
              value={
                payment.parent_transaction_id
                  ? String(payment.parent_transaction_id)
                  : null
              }
            />
          </DetailsSection>

          {(payment.payer_name ||
            payment.payer_phone ||
            payment.payer_email) && (
            <DetailsSection title="Payer Information">
              <DetailItem label="Name" value={payment.payer_name} />

              <DetailItem label="Phone" value={payment.payer_phone} />

              <DetailItem label="Email" value={payment.payer_email} />
            </DetailsSection>
          )}

          {payment.notes && (
            <div className="rounded-2xl bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
                Notes
              </p>

              <p className="mt-2 text-sm leading-6 text-slate-700">
                {payment.notes}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}

        <div className="border-t border-slate-100 px-6 py-4">
          <button
            type="button"
            onClick={onClose}
            className="w-full rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

// ==========================================================
// Details Section
// ==========================================================

function DetailsSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="mb-3 text-sm font-black text-slate-900">{title}</h3>

      <div className="overflow-hidden rounded-2xl border border-slate-100 divide-y divide-slate-100">
        {children}
      </div>
    </section>
  );
}

// ==========================================================
// Detail Item
// ==========================================================

function DetailItem({
  label,
  value,
  mono = false,
  emphasis = false,
}: {
  label: string;
  value: string | null | undefined;
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

export default function Payments() {
  const location = useLocation();
  const params = new URLSearchParams(location.search);
  const isCheckout =
    params.get("checkout") === "1" && Boolean(params.get("sessionId"));

  if (isCheckout) {
    return <SessionPayment />;
  }

  return <PaymentsHistory />;
}
