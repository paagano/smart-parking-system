import { useCallback, useEffect, useMemo, useState } from "react";

import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  Download,
  FileCheck2,
  FileText,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Smartphone,
  Wallet,
  X,
  XCircle,
} from "lucide-react";

import { useAuth } from "../../../auth/AuthContext";
import { api } from "../../../api";

// ==========================================================
// Types
// ==========================================================

interface Receipt {
  id: number;

  receipt_number?: string | null;

  payment_id?: number | null;

  transaction_number?: string | null;

  customer_id?: number | null;

  reservation_id?: number | null;

  parking_session_id?: number | null;

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

  payer_name?: string | null;

  payer_phone?: string | null;

  payer_email?: string | null;

  provider_receipt_number?: string | null;

  provider_transaction_id?: string | null;

  notes?: string | null;

  issued_at?: string | null;

  receipt_date?: string | null;

  paid_at?: string | null;

  created_at?: string | null;

  updated_at?: string | null;

  generated_at?: string | null;

  pdf_url?: string | null;

  url?: string | null;

  download_url?: string | null;

  verification_url?: string | null;

  pdf_generated?: boolean | null;

  is_generated?: boolean | null;

  [key: string]: any;
}

interface ReceiptListResponse {
  items?: Receipt[];

  receipts?: Receipt[];

  total?: number;

  count?: number;

  page?: number;

  limit?: number;
}

interface ReceiptStats {
  total: number;
  successful: number;
  pending: number;
  totalAmount: number;
}

// ==========================================================
// Constants
// ==========================================================

const PAGE_SIZE = 10;

const STATUS_OPTIONS = [
  "ALL",
  "AVAILABLE",
  "SUCCESSFUL",
  "COMPLETED",
  "PENDING",
  "PROCESSING",
  "FAILED",
  "CANCELLED",
  "REFUNDED",
];

const METHOD_OPTIONS = ["ALL", "MPESA", "WALLET", "CARD", "BANK", "CASH"];

// ==========================================================
// Utility Helpers
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

function dateOnly(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-KE", {
    dateStyle: "medium",
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

function normalizeStatus(value: string | null | undefined): string {
  return String(value ?? "").toUpperCase();
}

function isSuccessful(receipt: Receipt): boolean {
  const status = normalizeStatus(receipt.status);

  /*
   * IMPORTANT:
   *
   * `receipt.status` is the receipt lifecycle status, not the payment
   * transaction status. SmartPark creates receipts from successful
   * PaymentTransactions, and generated receipts are returned with
   * status `AVAILABLE`.
   *
   * Therefore AVAILABLE must be treated as a completed/successful
   * payment for the summary cards and total-paid calculation.
   */
  return ["AVAILABLE", "SUCCESSFUL", "COMPLETED", "PAID"].includes(status);
}

function isPending(receipt: Receipt): boolean {
  return ["PENDING", "PROCESSING"].includes(normalizeStatus(receipt.status));
}

function isFailed(receipt: Receipt): boolean {
  return ["FAILED", "CANCELLED"].includes(normalizeStatus(receipt.status));
}

function isRefund(receipt: Receipt): boolean {
  const status = normalizeStatus(receipt.status);

  const purpose = normalizeStatus(receipt.payment_purpose);

  const type = normalizeStatus(receipt.payment_type);

  return (
    status.includes("REFUND") ||
    purpose.includes("REFUND") ||
    type.includes("REFUND")
  );
}

function receiptTitle(receipt: Receipt): string {
  if (isRefund(receipt)) {
    return "Payment Refund";
  }

  const purpose = receipt.payment_purpose;

  if (purpose) {
    return displayText(purpose);
  }

  if (receipt.parking_session_id) {
    return "Parking Session Payment";
  }

  if (receipt.reservation_id) {
    return "Reservation Payment";
  }

  return "SmartPark Payment";
}

function getReceiptDate(receipt: Receipt): string | null {
  return (
    receipt.issued_at ??
    receipt.receipt_date ??
    receipt.paid_at ??
    receipt.generated_at ??
    receipt.created_at ??
    null
  );
}

function getReceiptTimestamp(receipt: Receipt): number {
  const value = getReceiptDate(receipt);

  if (!value) {
    return 0;
  }

  const timestamp = new Date(value).getTime();

  return Number.isFinite(timestamp) ? timestamp : 0;
}

function getReceiptNumber(receipt: Receipt): string {
  return receipt.receipt_number ?? `Receipt #${receipt.id}`;
}

function getTransactionNumber(receipt: Receipt): string {
  return (
    receipt.transaction_number ??
    (receipt.payment_id ? `Payment #${receipt.payment_id}` : "—")
  );
}

function paymentIcon(receipt: Receipt) {
  const method = normalizeStatus(receipt.payment_method);

  if (method === "MPESA") {
    return <Smartphone size={19} />;
  }

  if (method === "WALLET") {
    return <Wallet size={19} />;
  }

  return <FileText size={19} />;
}

function extractError(error: any): string {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail.map((item: any) => item?.msg ?? String(item)).join(", ");
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
      return "You are not authorized to access these receipts.";

    case 404:
      return "The requested receipt could not be found.";

    case 422:
      return "The receipt information supplied is invalid.";

    default:
      return "Unable to retrieve receipt information. Please try again.";
  }
}

// ==========================================================
// Component
// ==========================================================

export default function Receipts() {
  const { user } = useAuth();

  // ========================================================
  // Data
  // ========================================================

  const [receipts, setReceipts] = useState<Receipt[]>([]);

  const [loading, setLoading] = useState(true);

  const [refreshing, setRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);

  // ========================================================
  // Filters
  // ========================================================

  const [searchTerm, setSearchTerm] = useState("");

  const [statusFilter, setStatusFilter] = useState("ALL");

  const [methodFilter, setMethodFilter] = useState("ALL");

  const [dateFrom, setDateFrom] = useState("");

  const [dateTo, setDateTo] = useState("");

  const [currentPage, setCurrentPage] = useState(1);

  // ========================================================
  // Selected Receipt
  // ========================================================

  const [selectedReceipt, setSelectedReceipt] = useState<Receipt | null>(null);

  const [detailLoading, setDetailLoading] = useState(false);

  const [detailError, setDetailError] = useState<string | null>(null);

  // ========================================================
  // Download State
  // ========================================================

  const [downloadingReceiptId, setDownloadingReceiptId] = useState<
    number | null
  >(null);

  // ========================================================
  // Load Receipts
  // ========================================================

  const loadReceipts = useCallback(
    async (manualRefresh = false) => {
      if (!user?.id) {
        setReceipts([]);
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
         * Primary driver-facing endpoint:
         *
         * GET /receipts
         *
         * The endpoint is authenticated and is specifically
         * labelled "Get My Receipts".
         *
         * Do NOT use the old /payments/customer/{id}
         * endpoint for this page.
         */
        const response = await api.get<Receipt[] | ReceiptListResponse>(
          "/receipts",
        );

        const data = response.data;

        let items: Receipt[] = [];

        if (Array.isArray(data)) {
          items = data;
        } else if (Array.isArray(data?.items)) {
          items = data.items;
        } else if (Array.isArray(data?.receipts)) {
          items = data.receipts;
        }

        /*
         * Most recent receipt MUST appear first.
         */
        items.sort(
          (first, second) =>
            getReceiptTimestamp(second) - getReceiptTimestamp(first),
        );

        setReceipts(items);

        setCurrentPage(1);
      } catch (err) {
        console.error("[SmartPark Receipts] Failed to load receipts:", err);

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
    void loadReceipts();
  }, [loadReceipts]);

  // ========================================================
  // Filter Receipts
  // ========================================================

  const filteredReceipts = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase();

    return receipts
      .filter((receipt) => {
        // ----------------------------------------------
        // Status
        // ----------------------------------------------

        if (statusFilter !== "ALL") {
          const receiptStatus = normalizeStatus(receipt.status);

          /*
           * SUCCESSFUL is a payment outcome, while AVAILABLE is the
           * receipt lifecycle status used by the receipts API.
           *
           * Treat both as successful when the user chooses Successful.
           */
          const statusMatches =
            statusFilter === "SUCCESSFUL"
              ? isSuccessful(receipt)
              : receiptStatus === statusFilter;

          if (!statusMatches) {
            return false;
          }
        }

        // ----------------------------------------------
        // Payment Method
        // ----------------------------------------------

        if (
          methodFilter !== "ALL" &&
          normalizeStatus(receipt.payment_method) !== methodFilter
        ) {
          return false;
        }

        // ----------------------------------------------
        // Search
        // ----------------------------------------------

        if (normalizedSearch) {
          const searchable = [
            receipt.receipt_number,
            receipt.transaction_number,
            receipt.provider_receipt_number,
            receipt.provider_transaction_id,
            receipt.payment_method,
            receipt.payment_provider,
            receipt.payment_purpose,
            receipt.payment_type,
            receipt.payer_name,
            receipt.payer_phone,
            receipt.payer_email,
            receipt.reservation_id ? String(receipt.reservation_id) : "",
            receipt.parking_session_id
              ? String(receipt.parking_session_id)
              : "",
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();

          if (!searchable.includes(normalizedSearch)) {
            return false;
          }
        }

        // ----------------------------------------------
        // Date From
        // ----------------------------------------------

        const receiptDate = getReceiptDate(receipt);

        if (dateFrom && receiptDate) {
          const from = new Date(`${dateFrom}T00:00:00`);

          const current = new Date(receiptDate);

          if (current < from) {
            return false;
          }
        }

        // ----------------------------------------------
        // Date To
        // ----------------------------------------------

        if (dateTo && receiptDate) {
          const to = new Date(`${dateTo}T23:59:59.999`);

          const current = new Date(receiptDate);

          if (current > to) {
            return false;
          }
        }

        return true;
      })
      .sort(
        (first, second) =>
          getReceiptTimestamp(second) - getReceiptTimestamp(first),
      );
  }, [receipts, searchTerm, statusFilter, methodFilter, dateFrom, dateTo]);

  // ========================================================
  // Pagination
  // ========================================================

  const totalPages = Math.max(
    1,
    Math.ceil(filteredReceipts.length / PAGE_SIZE),
  );

  const safePage = Math.min(currentPage, totalPages);

  const paginatedReceipts = filteredReceipts.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  );

  // ========================================================
  // Statistics
  // ========================================================

  const statistics = useMemo<ReceiptStats>(() => {
    const successful = receipts.filter(isSuccessful);

    const pending = receipts.filter(isPending);

    const totalAmount = successful.reduce(
      (total, receipt) => total + Number(receipt.total_amount ?? 0),
      0,
    );

    return {
      total: receipts.length,

      successful: successful.length,

      pending: pending.length,

      totalAmount,
    };
  }, [receipts]);

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
  // View Receipt
  // ========================================================

  const handleViewReceipt = async (receipt: Receipt) => {
    setDetailError(null);
    setDetailLoading(true);
    setSelectedReceipt(receipt);

    try {
      /*
       * Retrieve the authoritative receipt record.
       */
      const response = await api.get<Receipt>(`/receipts/${receipt.id}`);

      setSelectedReceipt(response.data);
    } catch (err) {
      console.error(
        "[SmartPark Receipts] Failed to load receipt details:",
        err,
      );

      /*
       * Keep the list item visible if the detail endpoint
       * fails. The driver can still see the information
       * returned by GET /receipts.
       */
      setDetailError(extractError(err));
    } finally {
      setDetailLoading(false);
    }
  };

  // ========================================================
  // Download Receipt
  // ========================================================

  const handleDownloadReceipt = async (receipt: Receipt) => {
    if (downloadingReceiptId !== null) {
      return;
    }

    setDownloadingReceiptId(receipt.id);
    setError(null);

    try {
      /*
       * Download the PDF directly from the authenticated backend endpoint.
       *
       * IMPORTANT: Do not use /receipts/{id}/url + window.open() here.
       * If that endpoint returns a relative/frontend URL, the browser can
       * pass it through the React router and land on the Dashboard instead
       * of downloading the receipt.
       */
      let response;

      try {
        response = await api.get(`/receipts/${receipt.id}/download`, {
          responseType: "blob",
        });
      } catch (downloadError: any) {
        /*
         * If the PDF has not been generated yet, generate it first and
         * retry the download.
         */
        if (downloadError?.response?.status !== 404) {
          throw downloadError;
        }

        await api.post(`/receipts/${receipt.id}/generate`);

        response = await api.get(`/receipts/${receipt.id}/download`, {
          responseType: "blob",
        });
      }

      const contentType = String(
        response.headers?.["content-type"] ??
          response.headers?.["Content-Type"] ??
          "",
      ).toLowerCase();

      /*
       * With responseType=blob, an API error can also arrive as a Blob.
       * Do not save that error response as a .pdf.
       */
      if (!contentType.includes("application/pdf")) {
        const data = response.data;

        if (data instanceof Blob) {
          const text = await data.text();

          try {
            const parsed = JSON.parse(text);
            throw new Error(
              parsed?.detail ??
                parsed?.message ??
                "The receipt PDF could not be downloaded.",
            );
          } catch (parseError) {
            if (parseError instanceof Error) {
              throw parseError;
            }
          }
        }

        throw new Error("The receipt PDF could not be downloaded.");
      }

      const blob =
        response.data instanceof Blob
          ? response.data
          : new Blob([response.data], {
              type: "application/pdf",
            });

      const blobUrl = window.URL.createObjectURL(blob);
      const anchor = document.createElement("a");

      const safeReceiptNumber = getReceiptNumber(receipt).replace(
        /[^a-zA-Z0-9-_]/g,
        "_",
      );

      anchor.href = blobUrl;
      anchor.download = `${safeReceiptNumber}.pdf`;

      /*
       * Normal browser download. No React Router navigation and no
       * window.open(), so the Dashboard cannot be triggered by the PDF URL.
       */
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();

      window.setTimeout(() => {
        window.URL.revokeObjectURL(blobUrl);
      }, 1000);
    } catch (err: any) {
      console.error("[SmartPark Receipts] Failed to download receipt:", err);

      let message = extractError(err);

      /* Axios may expose the backend error as a Blob because the request
       * was made with responseType="blob". */
      const responseData = err?.response?.data;

      if (responseData instanceof Blob) {
        try {
          const text = await responseData.text();

          if (text) {
            const parsed = JSON.parse(text);
            message = parsed?.detail ?? parsed?.message ?? message;
          }
        } catch {
          // Keep the normal extracted error message.
        }
      }

      if (err instanceof Error && err.message) {
        message = err.message;
      }

      setError(
        message || "Unable to download the receipt PDF. Please try again.",
      );
    } finally {
      setDownloadingReceiptId(null);
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
            Loading receipts
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Retrieving your SmartPark payment receipts...
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
              <FileCheck2 size={25} />
            </div>

            <div>
              <h1 className="text-2xl font-black tracking-tight text-slate-900">
                Receipts
              </h1>

              <p className="mt-0.5 text-sm font-medium text-slate-500">
                View and download your SmartPark payment receipts.
              </p>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={() => void loadReceipts(true)}
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

            <div className="min-w-0 flex-1">
              <p className="text-sm font-extrabold text-rose-900">
                Receipt operation failed
              </p>

              <p className="mt-1 text-sm text-rose-800">{error}</p>
            </div>

            <button
              type="button"
              onClick={() => setError(null)}
              className="text-rose-500 hover:text-rose-700"
              aria-label="Dismiss error"
            >
              <X size={18} />
            </button>
          </div>
        </div>
      )}

      {/* ====================================================
          Summary Cards
      ==================================================== */}

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <ReceiptStatCard
          icon={<FileText size={20} />}
          label="Total Receipts"
          value={String(statistics.total)}
          description="Your receipt history"
          tone="slate"
        />

        <ReceiptStatCard
          icon={<CheckCircle2 size={20} />}
          label="Successful"
          value={String(statistics.successful)}
          description="Completed payments"
          tone="green"
        />

        <ReceiptStatCard
          icon={<Clock3 size={20} />}
          label="Pending"
          value={String(statistics.pending)}
          description="Awaiting completion"
          tone="amber"
        />

        <ReceiptStatCard
          icon={<Wallet size={20} />}
          label="Total Paid"
          value={money(statistics.totalAmount)}
          description="Successful payments"
          tone="blue"
        />
      </section>

      {/* ====================================================
          Quick Receipt Lookup
      ==================================================== */}

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end">
          <div className="flex-1">
            <div className="mb-2 flex items-center gap-2">
              <Search size={17} className="text-emerald-600" />

              <label className="text-sm font-extrabold text-slate-800">
                Find a Receipt
              </label>
            </div>

            <div className="flex flex-col gap-2 sm:flex-row">
              <input
                type="text"
                value={searchTerm}
                onChange={(event) => {
                  setSearchTerm(event.target.value);

                  setCurrentPage(1);
                }}
                placeholder="Receipt number, transaction, M-PESA reference..."
                className="w-full rounded-xl border border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />
            </div>
          </div>
        </div>
      </section>

      {/* ====================================================
          Filters
      ==================================================== */}

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {/* Status */}

          <FilterSelect
            label="Status"
            value={statusFilter}
            options={STATUS_OPTIONS}
            onChange={(value) => {
              setStatusFilter(value);

              setCurrentPage(1);
            }}
          />

          {/* Method */}

          <FilterSelect
            label="Payment Method"
            value={methodFilter}
            options={METHOD_OPTIONS}
            onChange={(value) => {
              setMethodFilter(value);

              setCurrentPage(1);
            }}
          />

          {/* From */}

          <div>
            <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-400">
              From
            </label>

            <div className="relative">
              <CalendarDays
                size={16}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />

              <input
                type="date"
                value={dateFrom}
                onChange={(event) => {
                  setDateFrom(event.target.value);

                  setCurrentPage(1);
                }}
                className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-sm font-semibold text-slate-700 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />
            </div>
          </div>

          {/* To */}

          <div>
            <label className="mb-2 block text-xs font-bold uppercase tracking-wide text-slate-400">
              To
            </label>

            <div className="relative">
              <CalendarDays
                size={16}
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />

              <input
                type="date"
                value={dateTo}
                onChange={(event) => {
                  setDateTo(event.target.value);

                  setCurrentPage(1);
                }}
                className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-9 pr-3 text-sm font-semibold text-slate-700 outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />
            </div>
          </div>

          {/* Reset */}

          <div className="flex items-end">
            <button
              type="button"
              onClick={resetFilters}
              className="w-full rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-extrabold text-slate-600 transition hover:bg-slate-50"
            >
              Reset Filters
            </button>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-4">
          <p className="text-xs font-semibold text-slate-400">
            Showing{" "}
            <span className="font-black text-slate-700">
              {filteredReceipts.length}
            </span>{" "}
            receipt
            {filteredReceipts.length === 1 ? "" : "s"}
          </p>

          {(searchTerm ||
            statusFilter !== "ALL" ||
            methodFilter !== "ALL" ||
            dateFrom ||
            dateTo) && (
            <button
              type="button"
              onClick={resetFilters}
              className="rounded-full bg-emerald-50 px-3 py-1 text-xs font-extrabold text-emerald-700"
            >
              Clear active filters
            </button>
          )}
        </div>
      </section>

      {/* ====================================================
          Receipt History
      ==================================================== */}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-col gap-3 border-b border-slate-100 px-6 py-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-base font-black text-slate-900">
              Receipt History
            </h2>

            <p className="mt-1 text-xs font-medium text-slate-500">
              Your most recent receipt appears first.
            </p>
          </div>

          <div className="inline-flex w-fit items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-extrabold text-emerald-700">
            <ShieldCheck size={13} />
            Secure receipts
          </div>
        </div>

        {/* ==================================================
            Empty State
        ================================================== */}

        {paginatedReceipts.length === 0 ? (
          <div className="px-6 py-16 text-center">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-slate-100 text-slate-400">
              <FileText size={28} />
            </div>

            <h3 className="mt-4 text-sm font-black text-slate-900">
              No receipts found
            </h3>

            <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-slate-500">
              No receipts match your current search or filter criteria.
            </p>

            <button
              type="button"
              onClick={resetFilters}
              className="mt-5 rounded-xl border border-slate-200 px-4 py-2.5 text-xs font-extrabold text-slate-700 transition hover:bg-slate-50"
            >
              Clear Filters
            </button>
          </div>
        ) : (
          <>
            {/* ==================================================
                Desktop Table
            ================================================== */}

            <div className="hidden overflow-x-auto md:block">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-100 bg-slate-50/70">
                    <th className="px-6 py-3 text-left text-[11px] font-black uppercase tracking-wide text-slate-400">
                      Receipt
                    </th>

                    <th className="px-4 py-3 text-left text-[11px] font-black uppercase tracking-wide text-slate-400">
                      Transaction
                    </th>

                    <th className="px-4 py-3 text-left text-[11px] font-black uppercase tracking-wide text-slate-400">
                      Payment
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
                  {paginatedReceipts.map((receipt, index) => (
                    <ReceiptTableRow
                      key={receipt.id}
                      receipt={receipt}
                      isLatest={index === 0 && safePage === 1}
                      downloading={downloadingReceiptId === receipt.id}
                      onView={() => void handleViewReceipt(receipt)}
                      onDownload={() => void handleDownloadReceipt(receipt)}
                    />
                  ))}
                </tbody>
              </table>
            </div>

            {/* ==================================================
                Mobile Cards
            ================================================== */}

            <div className="divide-y divide-slate-100 md:hidden">
              {paginatedReceipts.map((receipt, index) => (
                <ReceiptMobileCard
                  key={receipt.id}
                  receipt={receipt}
                  isLatest={index === 0 && safePage === 1}
                  downloading={downloadingReceiptId === receipt.id}
                  onView={() => void handleViewReceipt(receipt)}
                  onDownload={() => void handleDownloadReceipt(receipt)}
                />
              ))}
            </div>
          </>
        )}

        {/* ==================================================
            Pagination
        ================================================== */}

        {filteredReceipts.length > PAGE_SIZE && (
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
          Receipt Details Modal
      ==================================================== */}

      {selectedReceipt && (
        <ReceiptDetailsModal
          receipt={selectedReceipt}
          loading={detailLoading}
          error={detailError}
          downloading={downloadingReceiptId === selectedReceipt.id}
          onDownload={() => void handleDownloadReceipt(selectedReceipt)}
          onClose={() => {
            if (downloadingReceiptId === null) {
              setSelectedReceipt(null);

              setDetailError(null);
            }
          }}
        />
      )}
    </div>
  );
}

// ==========================================================
// Receipt Table Row
// ==========================================================

function ReceiptTableRow({
  receipt,
  isLatest,
  downloading,
  onView,
  onDownload,
}: {
  receipt: Receipt;
  isLatest: boolean;
  downloading: boolean;
  onView: () => void;
  onDownload: () => void;
}) {
  const currency = receipt.currency ?? "KES";

  return (
    <tr className="group transition hover:bg-slate-50/80">
      {/* Receipt */}

      <td className="px-6 py-4">
        <div className="flex items-center gap-3">
          <div
            className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl ${
              isSuccessful(receipt)
                ? "bg-emerald-50 text-emerald-600"
                : "bg-slate-100 text-slate-500"
            }`}
          >
            <FileCheck2 size={18} />
          </div>

          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <p className="max-w-[200px] truncate font-mono text-xs font-black text-slate-900">
                {getReceiptNumber(receipt)}
              </p>

              {isLatest && (
                <span className="shrink-0 rounded-full bg-emerald-100 px-2 py-0.5 text-[9px] font-black uppercase tracking-wide text-emerald-700">
                  Latest
                </span>
              )}
            </div>

            <p className="mt-1 truncate text-[10px] font-semibold text-slate-400">
              {receiptTitle(receipt)}
            </p>
          </div>
        </div>
      </td>

      {/* Transaction */}

      <td className="px-4 py-4">
        <p className="max-w-[190px] truncate font-mono text-xs font-bold text-slate-700">
          {getTransactionNumber(receipt)}
        </p>

        {receipt.provider_receipt_number && (
          <p className="mt-1 max-w-[190px] truncate text-[10px] font-semibold text-slate-400">
            Provider: {receipt.provider_receipt_number}
          </p>
        )}
      </td>

      {/* Payment */}

      <td className="px-4 py-4">
        <p className="text-xs font-extrabold text-slate-700">
          {displayText(receipt.payment_method)}
        </p>

        <p className="mt-0.5 text-[10px] font-semibold text-slate-400">
          {displayText(receipt.payment_provider)}
        </p>
      </td>

      {/* Date */}

      <td className="px-4 py-4">
        <p className="text-xs font-bold text-slate-700">
          {dateTime(getReceiptDate(receipt))}
        </p>
      </td>

      {/* Amount */}

      <td className="px-4 py-4 text-right">
        <p className="text-sm font-black text-slate-900">
          {money(receipt.total_amount, currency)}
        </p>
      </td>

      {/* Status */}

      <td className="px-4 py-4">
        <ReceiptStatusBadge status={receipt.status} />
      </td>

      {/* Actions */}

      <td className="px-6 py-4">
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onView}
            className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-extrabold text-slate-700 transition hover:bg-slate-50"
          >
            View
          </button>

          <button
            type="button"
            onClick={onDownload}
            disabled={downloading}
            className="grid h-8 w-8 place-items-center rounded-lg bg-slate-900 text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            title="Download PDF"
            aria-label="Download receipt PDF"
          >
            {downloading ? (
              <Loader2 size={14} className="animate-spin" />
            ) : (
              <Download size={14} />
            )}
          </button>
        </div>
      </td>
    </tr>
  );
}

// ==========================================================
// Mobile Receipt Card
// ==========================================================

function ReceiptMobileCard({
  receipt,
  isLatest,
  downloading,
  onView,
  onDownload,
}: {
  receipt: Receipt;
  isLatest: boolean;
  downloading: boolean;
  onView: () => void;
  onDownload: () => void;
}) {
  const currency = receipt.currency ?? "KES";

  return (
    <div className="p-5">
      <div className="flex items-start gap-3">
        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
          <FileCheck2 size={19} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="truncate font-mono text-xs font-black text-slate-900">
                  {getReceiptNumber(receipt)}
                </p>

                {isLatest && (
                  <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[9px] font-black uppercase tracking-wide text-emerald-700">
                    Latest
                  </span>
                )}
              </div>

              <p className="mt-1 text-xs font-bold text-slate-600">
                {receiptTitle(receipt)}
              </p>
            </div>

            <p className="shrink-0 text-sm font-black text-slate-900">
              {money(receipt.total_amount, currency)}
            </p>
          </div>

          <div className="mt-3 grid grid-cols-2 gap-3">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                Transaction
              </p>

              <p className="mt-1 truncate font-mono text-[10px] font-bold text-slate-700">
                {getTransactionNumber(receipt)}
              </p>
            </div>

            <div>
              <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                Date
              </p>

              <p className="mt-1 text-[10px] font-bold text-slate-700">
                {dateOnly(getReceiptDate(receipt))}
              </p>
            </div>
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <ReceiptStatusBadge status={receipt.status} />

            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold text-slate-500">
              {displayText(receipt.payment_method)}
            </span>
          </div>

          <div className="mt-4 flex gap-2">
            <button
              type="button"
              onClick={onView}
              className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-extrabold text-slate-700 transition hover:bg-slate-50"
            >
              View Receipt
            </button>

            <button
              type="button"
              onClick={onDownload}
              disabled={downloading}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-xs font-extrabold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {downloading ? (
                <Loader2 size={14} className="animate-spin" />
              ) : (
                <Download size={14} />
              )}
              PDF
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ==========================================================
// Status Badge
// ==========================================================

function ReceiptStatusBadge({ status }: { status: string | null | undefined }) {
  const normalized = normalizeStatus(status);

  let classes = "bg-slate-100 text-slate-600";

  let Icon = AlertCircle;

  if (["AVAILABLE", "SUCCESSFUL", "COMPLETED", "PAID"].includes(normalized)) {
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

    Icon = CheckCircle2;
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[10px] font-extrabold ${classes}`}
    >
      <Icon size={12} />

      {displayText(status ?? "UNKNOWN")}
    </span>
  );
}

// ==========================================================
// Statistics Card
// ==========================================================

function ReceiptStatCard({
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
  const toneClasses = {
    slate: "bg-slate-100 text-slate-600",

    green: "bg-emerald-50 text-emerald-600",

    amber: "bg-amber-50 text-amber-600",

    blue: "bg-blue-50 text-blue-600",
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <div
        className={`grid h-10 w-10 place-items-center rounded-xl ${toneClasses[tone]}`}
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
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
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
// Receipt Details Modal
// ==========================================================

function ReceiptDetailsModal({
  receipt,
  loading,
  error,
  downloading,
  onDownload,
  onClose,
}: {
  receipt: Receipt;
  loading: boolean;
  error: string | null;
  downloading: boolean;
  onDownload: () => void;
  onClose: () => void;
}) {
  const currency = receipt.currency ?? "KES";

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="receipt-details-title"
    >
      <div className="max-h-[92vh] w-full max-w-2xl overflow-y-auto rounded-3xl bg-white shadow-2xl">
        {/* ==================================================
            Header
        ================================================== */}

        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-100 bg-white px-6 py-5">
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-wide text-emerald-600">
              SmartPark AI
            </p>

            <h2
              id="receipt-details-title"
              className="mt-1 text-lg font-black text-slate-900"
            >
              Payment Receipt
            </h2>

            <p className="mt-0.5 truncate font-mono text-xs font-bold text-slate-400">
              {getReceiptNumber(receipt)}
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            disabled={downloading}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-slate-200 text-slate-500 transition hover:bg-slate-50 disabled:opacity-50"
            aria-label="Close receipt"
          >
            <X size={18} />
          </button>
        </div>

        {/* ==================================================
            Loading Detail
        ================================================== */}

        {loading && (
          <div className="flex items-center justify-center px-6 py-5">
            <Loader2 size={18} className="animate-spin text-emerald-600" />

            <span className="ml-2 text-xs font-semibold text-slate-500">
              Loading receipt details...
            </span>
          </div>
        )}

        {/* ==================================================
            Detail Error
        ================================================== */}

        {error && (
          <div className="mx-6 mt-5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
            <div className="flex items-start gap-2">
              <AlertCircle
                size={16}
                className="mt-0.5 shrink-0 text-amber-600"
              />

              <p className="text-xs font-semibold leading-5 text-amber-800">
                {error}
              </p>
            </div>
          </div>
        )}

        {/* ==================================================
            Hero
        ================================================== */}

        <div className="mx-6 mt-6 rounded-2xl bg-emerald-50 p-6">
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-xs font-semibold text-slate-500">
                {receiptTitle(receipt)}
              </p>

              <p className="mt-1 text-3xl font-black tracking-tight text-slate-900">
                {money(receipt.total_amount, currency)}
              </p>

              <p className="mt-2 text-xs font-medium text-slate-500">
                {dateTime(getReceiptDate(receipt))}
              </p>
            </div>

            <ReceiptStatusBadge status={receipt.status} />
          </div>
        </div>

        {/* ==================================================
            Content
        ================================================== */}

        <div className="space-y-6 p-6">
          {/* Receipt Identity */}

          <DetailsSection title="Receipt Information">
            <DetailItem
              label="Receipt Number"
              value={getReceiptNumber(receipt)}
              mono
              emphasis
            />

            <DetailItem
              label="Transaction Number"
              value={getTransactionNumber(receipt)}
              mono
            />

            <DetailItem
              label="Receipt Date"
              value={dateTime(getReceiptDate(receipt))}
            />

            <DetailItem
              label="Payment Purpose"
              value={displayText(receipt.payment_purpose)}
            />
          </DetailsSection>

          {/* Payment */}

          <DetailsSection title="Payment Details">
            <DetailItem
              label="Payment Method"
              value={displayText(receipt.payment_method)}
            />

            <DetailItem
              label="Payment Provider"
              value={displayText(receipt.payment_provider)}
            />

            <DetailItem
              label="Provider Transaction"
              value={receipt.provider_transaction_id}
              mono
            />

            <DetailItem
              label="Provider Receipt"
              value={receipt.provider_receipt_number}
              mono
              emphasis
            />
          </DetailsSection>

          {/* Amount */}

          <DetailsSection title="Amount Breakdown">
            <DetailItem
              label="Subtotal"
              value={money(receipt.subtotal_amount, currency)}
            />

            <DetailItem
              label="Discount"
              value={money(receipt.discount_amount, currency)}
            />

            <DetailItem
              label="Tax"
              value={money(receipt.tax_amount, currency)}
            />

            <DetailItem
              label="Total Paid"
              value={money(receipt.total_amount, currency)}
              emphasis
            />
          </DetailsSection>

          {/* SmartPark References */}

          <DetailsSection title="SmartPark Reference">
            <DetailItem
              label="Parking Session"
              value={
                receipt.parking_session_id
                  ? String(receipt.parking_session_id)
                  : null
              }
            />

            <DetailItem
              label="Reservation"
              value={
                receipt.reservation_id ? String(receipt.reservation_id) : null
              }
            />

            <DetailItem
              label="Payment ID"
              value={receipt.payment_id ? String(receipt.payment_id) : null}
            />
          </DetailsSection>

          {/* Customer */}

          {(receipt.payer_name ||
            receipt.payer_phone ||
            receipt.payer_email) && (
            <DetailsSection title="Customer Information">
              <DetailItem label="Name" value={receipt.payer_name} />

              <DetailItem label="Phone" value={receipt.payer_phone} />

              <DetailItem label="Email" value={receipt.payer_email} />
            </DetailsSection>
          )}

          {/* Notes */}

          {receipt.notes && (
            <div className="rounded-2xl bg-slate-50 p-4">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
                Notes
              </p>

              <p className="mt-2 text-sm leading-6 text-slate-700">
                {receipt.notes}
              </p>
            </div>
          )}

          {/* Verification */}

          <div className="rounded-2xl border border-emerald-100 bg-emerald-50/60 p-4">
            <div className="flex items-start gap-3">
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white text-emerald-600">
                <ShieldCheck size={18} />
              </div>

              <div>
                <p className="text-xs font-black text-emerald-900">
                  Authentic SmartPark Receipt
                </p>

                <p className="mt-1 text-xs leading-5 text-emerald-800">
                  This receipt is associated with your SmartPark payment record.
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* ==================================================
            Footer
        ================================================== */}

        <div className="sticky bottom-0 border-t border-slate-100 bg-white px-6 py-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={onDownload}
              disabled={downloading}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {downloading ? (
                <Loader2 size={17} className="animate-spin" />
              ) : (
                <Download size={17} />
              )}

              {downloading ? "Preparing PDF..." : "Download Receipt PDF"}
            </button>

            <button
              type="button"
              onClick={onClose}
              disabled={downloading}
              className="rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
            >
              Close
            </button>
          </div>
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
