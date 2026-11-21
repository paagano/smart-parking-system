import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarClock,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock3,
  RefreshCw,
  Search,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import { api, type ParkingBay, type ParkingReservation } from "../../../api";
import { useAuth } from "../../../auth/AuthContext";

type FilterStatus =
  | "ALL"
  | "CREATED"
  | "CONFIRMED"
  | "CHECKED_IN"
  | "COMPLETED"
  | "CANCELLED";

const PAGE_SIZE = 10;

function text(value: unknown): string {
  return String(value ?? "").trim();
}

function upper(value: unknown): string {
  return text(value).toUpperCase();
}

function dateTime(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "—";

  return new Intl.DateTimeFormat("en-KE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function money(
  value: number | string | null | undefined,
  currency = "KES",
): string {
  const amount = Number(value ?? 0);

  if (!Number.isFinite(amount)) {
    return `${currency} 0.00`;
  }

  return new Intl.NumberFormat("en-KE", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

function statusLabel(status: string): string {
  switch (upper(status)) {
    case "CREATED":
      return "Pending";
    case "CONFIRMED":
      return "Confirmed";
    case "CHECKED_IN":
      return "Checked In";
    case "COMPLETED":
      return "Completed";
    case "CANCELLED":
      return "Cancelled";
    default:
      return status || "Unknown";
  }
}

function statusClasses(status: string): string {
  switch (upper(status)) {
    case "CONFIRMED":
      return "border-emerald-200 bg-emerald-50 text-emerald-700";
    case "CHECKED_IN":
      return "border-blue-200 bg-blue-50 text-blue-700";
    case "COMPLETED":
      return "border-slate-200 bg-slate-100 text-slate-700";
    case "CANCELLED":
      return "border-rose-200 bg-rose-50 text-rose-700";
    default:
      return "border-amber-200 bg-amber-50 text-amber-700";
  }
}

function getApiErrorMessage(error: any): string {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg ?? String(item)).join(", ");
  }

  return (
    error?.response?.data?.message ??
    error?.message ??
    "Unable to complete the reservation request."
  );
}

function Metric({
  label,
  value,
  note,
}: {
  label: string;
  value: number;
  note: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4">
      <p className="text-xs font-bold uppercase tracking-[0.12em] text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-3xl font-black text-slate-900">{value}</p>
      <p className="mt-1 text-xs font-semibold text-slate-500">{note}</p>
    </div>
  );
}

function EmptyState({ text: message }: { text: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 px-6 py-12 text-center">
      <CalendarClock className="mx-auto text-slate-300" size={38} />
      <p className="mt-4 text-sm font-black text-slate-700">{message}</p>
      <p className="mt-1 text-xs text-slate-500">
        Reservations for this facility will appear here when available.
      </p>
    </div>
  );
}

export default function ApproveReservations() {
  const { user } = useAuth();

  const facilityId = user?.facility_id ?? null;

  const [reservations, setReservations] = useState<ParkingReservation[]>([]);
  const [facilityBayIds, setFacilityBayIds] = useState<Set<number>>(new Set());

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [statusFilter, setStatusFilter] = useState<FilterStatus>("ALL");
  const [currentPage, setCurrentPage] = useState(1);

  const [processingId, setProcessingId] = useState<number | null>(null);

  const loadReservations = useCallback(
    async (showRefreshState = false) => {
      if (!facilityId) {
        setReservations([]);
        setFacilityBayIds(new Set());
        setLoading(false);
        return;
      }

      if (showRefreshState) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setError(null);

      try {
        const [reservationResponse, bayResponse] = await Promise.all([
          api.get<{
            items: ParkingReservation[];
            total: number;
          }>("/parking-reservations", {
            params: {
              skip: 0,
              limit: 500,
            },
          }),

          api.get<{
            items: ParkingBay[];
            total: number;
          }>("/parking-bays", {
            params: {
              skip: 0,
              limit: 500,
            },
          }),
        ]);

        const facilityBays = bayResponse.data.items.filter(
          (bay) => bay.is_active,
        );

        const bayIds = new Set(facilityBays.map((bay) => Number(bay.id)));

        setFacilityBayIds(bayIds);

        const facilityReservations = reservationResponse.data.items.filter(
          (reservation) => bayIds.has(Number(reservation.parking_bay_id)),
        );

        setReservations(facilityReservations);
      } catch (err) {
        console.error(
          "[SmartPark Approve Reservations] Failed to load reservations:",
          err,
        );

        setError(getApiErrorMessage(err));
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [facilityId],
  );

  useEffect(() => {
    void loadReservations();
  }, [loadReservations]);

  const filteredReservations = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase();

    return reservations
      .filter((reservation) => {
        if (
          statusFilter !== "ALL" &&
          upper(reservation.status) !== statusFilter
        ) {
          return false;
        }

        if (!normalizedSearch) {
          return true;
        }

        return [
          reservation.reservation_number,
          reservation.vehicle_registration,
          reservation.vehicle_type,
          reservation.parking_bay_id,
          reservation.customer_id,
        ].some((value) => text(value).toLowerCase().includes(normalizedSearch));
      })
      .sort(
        (a, b) =>
          new Date(b.created_at ?? b.reserved_from).getTime() -
          new Date(a.created_at ?? a.reserved_from).getTime(),
      );
  }, [reservations, searchTerm, statusFilter]);

  const totalPages = Math.max(
    1,
    Math.ceil(filteredReservations.length / PAGE_SIZE),
  );

  const safePage = Math.min(currentPage, totalPages);

  const pageItems = filteredReservations.slice(
    (safePage - 1) * PAGE_SIZE,
    safePage * PAGE_SIZE,
  );

  const stats = useMemo(() => {
    return {
      total: reservations.length,
      pending: reservations.filter((item) => upper(item.status) === "CREATED")
        .length,
      confirmed: reservations.filter(
        (item) => upper(item.status) === "CONFIRMED",
      ).length,
      checkedIn: reservations.filter(
        (item) => upper(item.status) === "CHECKED_IN",
      ).length,
    };
  }, [reservations]);

  useEffect(() => {
    if (currentPage > totalPages) {
      setCurrentPage(totalPages);
    }
  }, [currentPage, totalPages]);

  const processReservation = async (
    reservation: ParkingReservation,
    action: "confirm" | "cancel" | "checkIn",
  ) => {
    setProcessingId(reservation.id);
    setError(null);

    try {
      let response;

      if (action === "confirm") {
        response = await api.patch<ParkingReservation>(
          `/parking-reservations/${reservation.id}/confirm`,
        );
      } else if (action === "cancel") {
        response = await api.patch<ParkingReservation>(
          `/parking-reservations/${reservation.id}/cancel`,
        );
      } else {
        response = await api.patch<ParkingReservation>(
          `/parking-reservations/${reservation.id}/check-in`,
        );
      }

      setReservations((current) =>
        current.map((item) =>
          item.id === reservation.id ? response.data : item,
        ),
      );
    } catch (err) {
      console.error(
        `[SmartPark Approve Reservations] Failed to ${action} reservation:`,
        err,
      );

      setError(getApiErrorMessage(err));
    } finally {
      setProcessingId(null);
    }
  };

  const handleConfirm = async (reservation: ParkingReservation) => {
    if (
      !window.confirm(
        `Approve reservation ${reservation.reservation_number} for ${reservation.vehicle_registration}?`,
      )
    ) {
      return;
    }

    await processReservation(reservation, "confirm");
  };

  const handleCancel = async (reservation: ParkingReservation) => {
    if (
      !window.confirm(`Cancel reservation ${reservation.reservation_number}?`)
    ) {
      return;
    }

    await processReservation(reservation, "cancel");
  };

  const handleCheckIn = async (reservation: ParkingReservation) => {
    if (
      !window.confirm(
        `Check in ${reservation.vehicle_registration} using reservation ${reservation.reservation_number}?`,
      )
    ) {
      return;
    }

    await processReservation(reservation, "checkIn");
  };

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-600">
          SmartPark AI
        </p>

        <div className="mt-2 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 className="text-3xl font-black tracking-tight text-slate-900">
              Approve Reservations
            </h1>

            <p className="mt-1 text-sm text-slate-500">
              Review, approve and manage reservations assigned to your facility.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void loadReservations(true)}
            disabled={loading || refreshing}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <XCircle size={19} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-black">Unable to complete the request</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Total"
          value={stats.total}
          note="Facility reservations"
        />
        <Metric
          label="Pending"
          value={stats.pending}
          note="Awaiting approval / confirmation"
        />
        <Metric
          label="Confirmed"
          value={stats.confirmed}
          note="Confirmed reservations"
        />
        <Metric
          label="Checked In"
          value={stats.checkedIn}
          note="Reservations already checked in"
        />
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search
              size={17}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />

            <input
              value={searchTerm}
              onChange={(event) => {
                setSearchTerm(event.target.value);
                setCurrentPage(1);
              }}
              placeholder="Search reservation number, vehicle registration..."
              className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-10 pr-4 text-sm font-medium text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:bg-white"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(event) => {
              setStatusFilter(event.target.value as FilterStatus);
              setCurrentPage(1);
            }}
            className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 outline-none focus:border-emerald-400"
          >
            <option value="ALL">All statuses</option>
            <option value="CREATED">Pending</option>
            <option value="CONFIRMED">Confirmed</option>
            <option value="CHECKED_IN">Checked In</option>
            <option value="COMPLETED">Completed</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-black text-slate-900">
                Facility Reservations
              </h2>
              <p className="mt-1 text-xs font-semibold text-slate-500">
                {filteredReservations.length} reservation
                {filteredReservations.length === 1 ? "" : "s"} shown
              </p>
            </div>

            <ShieldCheck className="text-emerald-500" size={21} />
          </div>
        </div>

        {loading ? (
          <div className="space-y-3 p-5">
            {[1, 2, 3, 4].map((item) => (
              <div
                key={item}
                className="h-20 animate-pulse rounded-xl bg-slate-100"
              />
            ))}
          </div>
        ) : pageItems.length === 0 ? (
          <div className="p-5">
            <EmptyState
              text={
                searchTerm || statusFilter !== "ALL"
                  ? "No reservations match the selected filters."
                  : facilityBayIds.size === 0
                    ? "No active parking bays were found for this facility."
                    : "No reservations are currently assigned to this facility."
              }
            />
          </div>
        ) : (
          <>
            <div className="hidden overflow-x-auto lg:block">
              <table className="min-w-full">
                <thead className="bg-slate-50">
                  <tr className="border-b border-slate-200">
                    <th className="px-5 py-3 text-left text-[11px] font-black uppercase tracking-[0.12em] text-slate-400">
                      Reservation
                    </th>
                    <th className="px-5 py-3 text-left text-[11px] font-black uppercase tracking-[0.12em] text-slate-400">
                      Vehicle
                    </th>
                    <th className="px-5 py-3 text-left text-[11px] font-black uppercase tracking-[0.12em] text-slate-400">
                      Bay
                    </th>
                    <th className="px-5 py-3 text-left text-[11px] font-black uppercase tracking-[0.12em] text-slate-400">
                      Reserved Period
                    </th>
                    <th className="px-5 py-3 text-left text-[11px] font-black uppercase tracking-[0.12em] text-slate-400">
                      Amount
                    </th>
                    <th className="px-5 py-3 text-left text-[11px] font-black uppercase tracking-[0.12em] text-slate-400">
                      Status
                    </th>
                    <th className="px-5 py-3 text-right text-[11px] font-black uppercase tracking-[0.12em] text-slate-400">
                      Actions
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-100">
                  {pageItems.map((reservation) => {
                    const status = upper(reservation.status);
                    const processing = processingId === reservation.id;

                    return (
                      <tr
                        key={reservation.id}
                        className="transition hover:bg-slate-50/70"
                      >
                        <td className="px-5 py-4 align-top">
                          <p className="text-sm font-black text-slate-900">
                            {reservation.reservation_number}
                          </p>
                          <p className="mt-1 text-xs font-semibold text-slate-500">
                            Customer #{reservation.customer_id ?? "—"}
                          </p>
                        </td>

                        <td className="px-5 py-4 align-top">
                          <p className="text-sm font-black text-slate-900">
                            {reservation.vehicle_registration}
                          </p>
                          <p className="mt-1 text-xs font-semibold text-slate-500">
                            {reservation.vehicle_type}
                          </p>
                        </td>

                        <td className="px-5 py-4 align-top">
                          <p className="text-sm font-black text-slate-900">
                            Bay #{reservation.parking_bay_id}
                          </p>
                        </td>

                        <td className="px-5 py-4 align-top">
                          <p className="text-xs font-bold text-slate-700">
                            {dateTime(reservation.reserved_from)}
                          </p>
                          <p className="mt-1 text-xs font-semibold text-slate-500">
                            to {dateTime(reservation.reserved_until)}
                          </p>
                        </td>

                        <td className="px-5 py-4 align-top">
                          <p className="text-sm font-black text-slate-900">
                            {money(
                              reservation.estimated_amount,
                              reservation.currency,
                            )}
                          </p>
                        </td>

                        <td className="px-5 py-4 align-top">
                          <span
                            className={`inline-flex rounded-full border px-2.5 py-1 text-[11px] font-black ${statusClasses(
                              reservation.status,
                            )}`}
                          >
                            {statusLabel(reservation.status)}
                          </span>
                        </td>

                        <td className="px-5 py-4 align-top">
                          <div className="flex justify-end gap-2">
                            {status === "CREATED" && (
                              <>
                                <button
                                  type="button"
                                  onClick={() =>
                                    void handleConfirm(reservation)
                                  }
                                  disabled={processing}
                                  className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-2 text-xs font-black text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  <CheckCircle2 size={14} />
                                  {processing ? "Processing..." : "Approve"}
                                </button>

                                <button
                                  type="button"
                                  onClick={() => void handleCancel(reservation)}
                                  disabled={processing}
                                  className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-white px-3 py-2 text-xs font-black text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  <XCircle size={14} />
                                  Cancel
                                </button>
                              </>
                            )}

                            {status === "CONFIRMED" && (
                              <>
                                <button
                                  type="button"
                                  onClick={() =>
                                    void handleCheckIn(reservation)
                                  }
                                  disabled={processing}
                                  className="inline-flex items-center gap-1.5 rounded-lg bg-slate-900 px-3 py-2 text-xs font-black text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  <ShieldCheck size={14} />
                                  {processing ? "Processing..." : "Check In"}
                                </button>

                                <button
                                  type="button"
                                  onClick={() => void handleCancel(reservation)}
                                  disabled={processing}
                                  className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200 bg-white px-3 py-2 text-xs font-black text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  <XCircle size={14} />
                                  Cancel
                                </button>
                              </>
                            )}

                            {status === "CHECKED_IN" && (
                              <span className="inline-flex items-center gap-1.5 rounded-lg bg-blue-50 px-3 py-2 text-xs font-black text-blue-700">
                                <Clock3 size={14} />
                                Vehicle Parked
                              </span>
                            )}

                            {status === "COMPLETED" && (
                              <span className="text-xs font-bold text-slate-400">
                                Completed
                              </span>
                            )}

                            {status === "CANCELLED" && (
                              <span className="text-xs font-bold text-slate-400">
                                Cancelled
                              </span>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="space-y-3 p-4 lg:hidden">
              {pageItems.map((reservation) => {
                const status = upper(reservation.status);
                const processing = processingId === reservation.id;

                return (
                  <div
                    key={reservation.id}
                    className="rounded-2xl border border-slate-200 bg-white p-4"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-black text-slate-900">
                          {reservation.reservation_number}
                        </p>
                        <p className="mt-1 text-sm font-bold text-slate-700">
                          {reservation.vehicle_registration}
                        </p>
                        <p className="text-xs font-semibold text-slate-500">
                          {reservation.vehicle_type} · Bay #
                          {reservation.parking_bay_id}
                        </p>
                      </div>

                      <span
                        className={`inline-flex shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-black ${statusClasses(
                          reservation.status,
                        )}`}
                      >
                        {statusLabel(reservation.status)}
                      </span>
                    </div>

                    <div className="mt-4 grid grid-cols-2 gap-3 rounded-xl bg-slate-50 p-3">
                      <div>
                        <p className="text-[10px] font-black uppercase tracking-wider text-slate-400">
                          From
                        </p>
                        <p className="mt-1 text-xs font-bold text-slate-700">
                          {dateTime(reservation.reserved_from)}
                        </p>
                      </div>

                      <div>
                        <p className="text-[10px] font-black uppercase tracking-wider text-slate-400">
                          Until
                        </p>
                        <p className="mt-1 text-xs font-bold text-slate-700">
                          {dateTime(reservation.reserved_until)}
                        </p>
                      </div>
                    </div>

                    <div className="mt-3 flex items-center justify-between gap-3">
                      <p className="text-sm font-black text-slate-900">
                        {money(
                          reservation.estimated_amount,
                          reservation.currency,
                        )}
                      </p>

                      <div className="flex gap-2">
                        {status === "CREATED" && (
                          <>
                            <button
                              type="button"
                              onClick={() => void handleConfirm(reservation)}
                              disabled={processing}
                              className="rounded-lg bg-emerald-600 px-3 py-2 text-xs font-black text-white disabled:opacity-50"
                            >
                              Approve
                            </button>

                            <button
                              type="button"
                              onClick={() => void handleCancel(reservation)}
                              disabled={processing}
                              className="rounded-lg border border-rose-200 px-3 py-2 text-xs font-black text-rose-700 disabled:opacity-50"
                            >
                              Cancel
                            </button>
                          </>
                        )}

                        {status === "CONFIRMED" && (
                          <button
                            type="button"
                            onClick={() => void handleCheckIn(reservation)}
                            disabled={processing}
                            className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-black text-white disabled:opacity-50"
                          >
                            Check In
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>

            <div className="flex flex-col gap-3 border-t border-slate-200 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="text-xs font-semibold text-slate-500">
                Showing{" "}
                {filteredReservations.length === 0
                  ? 0
                  : (safePage - 1) * PAGE_SIZE + 1}{" "}
                to {Math.min(safePage * PAGE_SIZE, filteredReservations.length)}{" "}
                of {filteredReservations.length}
              </p>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() =>
                    setCurrentPage((page) => Math.max(1, page - 1))
                  }
                  disabled={safePage <= 1}
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <ChevronLeft size={15} />
                  Previous
                </button>

                <span className="min-w-16 text-center text-xs font-black text-slate-600">
                  {safePage} / {totalPages}
                </span>

                <button
                  type="button"
                  onClick={() =>
                    setCurrentPage((page) => Math.min(totalPages, page + 1))
                  }
                  disabled={safePage >= totalPages}
                  className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-black text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Next
                  <ChevronRight size={15} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
