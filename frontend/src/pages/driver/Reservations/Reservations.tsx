import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  CalendarPlus,
  CarFront,
  CheckCircle2,
  Clock3,
  CreditCard,
  Pencil,
  ParkingCircle,
  RefreshCw,
  Save,
  Search,
  Smartphone,
  Wallet,
  Trash2,
  XCircle,
} from "lucide-react";

import { useAuth } from "../../../auth/AuthContext";
import {
  api,
  parkingBaysApi,
  parkingFacilitiesApi,
  parkingReservationsApi,
  parkingZonesApi,
  type ParkingBay,
  type ParkingFacility,
  type ParkingReservation,
  type ParkingZone,
} from "../../../api";
import { Card, Metric, default as Page } from "../../../components/common/Page";

export default function Reservations() {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [reservations, setReservations] = useState<ParkingReservation[]>([]);
  const [facilities, setFacilities] = useState<ParkingFacility[]>([]);
  const [zones, setZones] = useState<ParkingZone[]>([]);
  const [bays, setBays] = useState<ParkingBay[]>([]);

  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [processingReservationId, setProcessingReservationId] = useState<
    number | null
  >(null);

  // Search / reservation view
  const [searchParams] = useSearchParams();
  const [searchTerm, setSearchTerm] = useState("");

  // ----------------------------------------------------------
  // Update reservation modal
  // ----------------------------------------------------------

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
  const [successToast, setSuccessToast] = useState<string | null>(null);

  // ----------------------------------------------------------
  // Payment modal
  // ----------------------------------------------------------

  const [paymentReservation, setPaymentReservation] =
    useState<ParkingReservation | null>(null);
  const [paymentMethod, setPaymentMethod] = useState<"WALLET" | "MPESA">(
    "WALLET",
  );
  const [paymentProvider, setPaymentProvider] = useState<
    "INTERNAL" | "SAFARICOM"
  >("INTERNAL");
  const [mpesaPhone, setMpesaPhone] = useState("");
  const [paymentProcessing, setPaymentProcessing] = useState(false);
  const [paymentStatus, setPaymentStatus] = useState<string | null>(null);
  const [paymentMessage, setPaymentMessage] = useState<string | null>(null);
  const [paymentId, setPaymentId] = useState<number | null>(null);

  // ----------------------------------------------------------
  // Load live reservation data
  // ----------------------------------------------------------

  useEffect(() => {
    let cancelled = false;

    const loadReservations = async (manualRefresh = false) => {
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
         * Load reservations together with the parking hierarchy.
         *
         * Reservation
         *    ↓
         * Parking Bay
         *    ↓
         * Parking Zone
         *    ↓
         * Parking Facility
         */
        const [reservationResult, facilityResult, zoneResult, bayResult] =
          await Promise.allSettled([
            parkingReservationsApi.byCustomer(user.id),
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
            "Unable to load your reservations from the SmartPark AI backend.",
          );
        } else if (failures.length > 0) {
          /*
           * The reservation list can still work even if the
           * facility hierarchy fails.
           */
          setError(
            `Reservations loaded, but some parking details could not be resolved: ${failures.join(
              ", ",
            )}.`,
          );
        }

        setLastUpdated(new Date());
      } catch (err) {
        if (cancelled) return;

        if (err instanceof Error) {
          setError(err.message);
        } else {
          setError(
            "Unable to load reservations from the SmartPark AI backend.",
          );
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          setIsRefreshing(false);
        }
      }
    };

    void loadReservations();

    /*
     * Keep the page live.
     *
     * This means changes made to reservations in the backend
     * will automatically appear without requiring a page reload.
     */
    // Keep the reservation lifecycle responsive. In particular, when an
    // attendant checks a parking session out and the backend changes the
    // reservation to COMPLETED, the driver page should reflect that change
    // without requiring a manual page refresh.
    const refreshTimer = window.setInterval(() => {
      void loadReservations(true);
    }, 10000);

    return () => {
      cancelled = true;
      window.clearInterval(refreshTimer);
    };
  }, [user]);

  // ----------------------------------------------------------
  // Lookup maps
  // ----------------------------------------------------------

  const bayMap = useMemo(() => {
    return new Map(bays.map((bay) => [bay.id, bay]));
  }, [bays]);

  const zoneMap = useMemo(() => {
    return new Map(zones.map((zone) => [zone.id, zone]));
  }, [zones]);

  const facilityMap = useMemo(() => {
    return new Map(facilities.map((facility) => [facility.id, facility]));
  }, [facilities]);

  // ----------------------------------------------------------
  // Reservation helpers
  // ----------------------------------------------------------

  const getReservationBay = (reservation: ParkingReservation) => {
    return bayMap.get(reservation.parking_bay_id) ?? null;
  };

  const getReservationZone = (reservation: ParkingReservation) => {
    const bay = getReservationBay(reservation);

    if (!bay) return null;

    return zoneMap.get(bay.zone_id) ?? null;
  };

  const getReservationFacility = (
    reservation: ParkingReservation,
  ): ParkingFacility | null => {
    const zone = getReservationZone(reservation);

    if (!zone) return null;

    return facilityMap.get(zone.facility_id) ?? null;
  };

  // ----------------------------------------------------------
  // Date formatting
  // ----------------------------------------------------------

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

  // ----------------------------------------------------------
  // Reservation status
  // ----------------------------------------------------------

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

    if (status.includes("active")) {
      return {
        label: "Active",
        className: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200",
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

  // ----------------------------------------------------------
  // Reservation categorisation
  // ----------------------------------------------------------

  const now = Date.now();

  const upcomingReservations = useMemo(() => {
    return reservations
      .filter((reservation) => {
        const status = String(reservation.status ?? "").toLowerCase();

        if (
          status.includes("cancel") ||
          status.includes("complete") ||
          status.includes("expire") ||
          reservation.cancelled_at ||
          reservation.completed_at
        ) {
          return false;
        }

        return new Date(reservation.reserved_until).getTime() >= now;
      })
      .sort(
        (a, b) =>
          new Date(a.reserved_from).getTime() -
          new Date(b.reserved_from).getTime(),
      );
  }, [reservations, now]);

  const activeReservations = useMemo(() => {
    return reservations.filter((reservation) => {
      const status = String(reservation.status ?? "").toLowerCase();

      return (
        status.includes("active") ||
        status.includes("check") ||
        Boolean(reservation.checked_in_at)
      );
    });
  }, [reservations]);

  const completedReservations = useMemo(() => {
    return reservations.filter((reservation) => {
      const status = String(reservation.status ?? "").toLowerCase();

      return status.includes("complete") || Boolean(reservation.completed_at);
    });
  }, [reservations]);

  const reservationView = searchParams.get("view") ?? "all";

  const visibleReservations = useMemo(() => {
    const normalizedQuery = searchTerm.trim().toLowerCase();

    const viewFiltered = reservations.filter((reservation) => {
      const status = String(reservation.status ?? "").toLowerCase();

      if (reservationView === "upcoming") {
        return upcomingReservations.some((item) => item.id === reservation.id);
      }

      if (reservationView === "active") {
        return (
          status.includes("active") ||
          status.includes("check") ||
          Boolean(reservation.checked_in_at)
        );
      }

      if (reservationView === "history") {
        return (
          status.includes("complete") ||
          status.includes("cancel") ||
          status.includes("expire") ||
          Boolean(reservation.completed_at) ||
          Boolean(reservation.cancelled_at)
        );
      }

      return true;
    });

    if (!normalizedQuery) return viewFiltered;

    const tokens = normalizedQuery
      .split(/\s+/)
      .map((token) => token.trim())
      .filter(Boolean);

    return viewFiltered.filter((reservation) => {
      const bay = getReservationBay(reservation);
      const zone = getReservationZone(reservation);
      const facility = getReservationFacility(reservation);
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

      // Every search token must match somewhere. This makes searches such as
      // "KDA 123A", "Westlands confirmed", or "August 27" useful without
      // requiring an exact phrase.
      return tokens.every((token) => searchableText.includes(token));
    });
  }, [
    reservations,
    reservationView,
    searchTerm,
    upcomingReservations,
    bayMap,
    zoneMap,
    facilityMap,
  ]);

  // ----------------------------------------------------------
  // Manual refresh
  // ----------------------------------------------------------

  const refresh = async () => {
    if (!user?.id) return;

    setIsRefreshing(true);
    setError(null);

    try {
      const result = await parkingReservationsApi.byCustomer(user.id);

      setReservations(result.items);
      setLastUpdated(new Date());
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError(
          "Unable to refresh reservations from the SmartPark AI backend.",
        );
      }
    } finally {
      setIsRefreshing(false);
    }
  };

  // ----------------------------------------------------------
  // Reservation actions
  // ----------------------------------------------------------

  const toLocalDateTimeInput = (value: string | null | undefined) => {
    if (!value) return "";

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";

    const pad = (part: number) => String(part).padStart(2, "0");

    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
      date.getDate(),
    )}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
  };

  const normalizeKenyanPhone = (value: string) => {
    const digits = value.replace(/\D/g, "");

    if (digits.startsWith("254")) return digits;
    if (digits.startsWith("0")) return `254${digits.slice(1)}`;
    if (digits.startsWith("7") || digits.startsWith("1")) return `254${digits}`;
    return digits;
  };

  const isValidKenyanMpesaPhone = (value: string) =>
    /^254(?:7|1)\d{8}$/.test(value);

  const handleUpdate = (reservation: ParkingReservation) => {
    const bay = getReservationBay(reservation);
    const zone = getReservationZone(reservation);
    const facility = getReservationFacility(reservation);

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
  };

  const closeUpdateModal = () => {
    if (savingUpdate) return;
    setEditingReservation(null);
    setEditError(null);
  };

  useEffect(() => {
    if (!successToast) return;

    const timeoutId = window.setTimeout(() => {
      setSuccessToast(null);
    }, 3500);

    return () => window.clearTimeout(timeoutId);
  }, [successToast]);

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
      setEditingReservation(null);
      setLastUpdated(new Date());
      setSuccessToast(
        `Reservation ${editingReservation.reservation_number} updated successfully.`,
      );
    } catch (err: any) {
      console.error(
        "[SmartPark Reservations] Failed to update reservation:",
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

  const handleConfirm = (reservation: ParkingReservation) => {
    setPaymentReservation(reservation);
    setPaymentMethod("WALLET");
    setPaymentProvider("INTERNAL");
    setMpesaPhone(String(user?.phone_number ?? ""));
    setPaymentStatus(null);
    setPaymentMessage(null);
    setPaymentId(null);
    setError(null);
  };

  const closePaymentModal = () => {
    if (paymentProcessing) return;
    setPaymentReservation(null);
    setPaymentStatus(null);
    setPaymentMessage(null);
    setPaymentId(null);
  };

  const handlePayment = async () => {
    if (!paymentReservation || !user?.id) {
      setPaymentMessage(
        "Reservation or authenticated customer information is missing.",
      );
      return;
    }

    const amount = Number(paymentReservation.estimated_amount ?? 0);
    if (!Number.isFinite(amount) || amount < 0) {
      setPaymentMessage("The reservation returned an invalid payment amount.");
      return;
    }

    const normalizedPhone = normalizeKenyanPhone(mpesaPhone);

    if (
      paymentMethod === "MPESA" &&
      !isValidKenyanMpesaPhone(normalizedPhone)
    ) {
      setPaymentMessage(
        "Please enter a valid Kenyan M-PESA number, for example 0712345678 or 254712345678.",
      );
      return;
    }

    setPaymentProcessing(true);
    setPaymentMessage(null);
    setPaymentStatus("PROCESSING");

    try {
      const response = await api.post<{
        id: number;
        status: string;
        paid_at?: string | null;
      }>("/payments/reservation", {
        payment_method: paymentMethod,
        payment_provider: paymentProvider,
        payment_purpose: "RESERVATION",
        payment_type: "PAYMENT",
        currency: paymentReservation.currency || "KES",
        subtotal_amount: amount,
        discount_amount: 0,
        tax_amount: 0,
        total_amount: amount,
        payer_name: `${user.first_name} ${user.last_name}`.trim(),
        payer_phone:
          paymentMethod === "MPESA"
            ? normalizedPhone
            : String(user.phone_number ?? ""),
        payer_email: user.email,
        notes: paymentReservation.notes ?? null,
        reservation_id: paymentReservation.id,
        customer_id: user.id,
        loyalty_points_to_redeem: 0,
      });

      setPaymentId(response.data.id);
      setPaymentStatus(response.data.status.toUpperCase());

      if (response.data.status.toUpperCase() === "SUCCESSFUL") {
        setReservations((current) =>
          current.map((item) =>
            item.id === paymentReservation.id
              ? {
                  ...item,
                  status: "CONFIRMED",
                  confirmed_at:
                    response.data.paid_at ?? new Date().toISOString(),
                }
              : item,
          ),
        );
        setPaymentMessage(
          "Payment successful. Your reservation is now confirmed.",
        );
        setPaymentProcessing(false);
      } else if (
        ["FAILED", "CANCELLED"].includes(response.data.status.toUpperCase())
      ) {
        setPaymentMessage(
          "Payment was not completed. Your reservation remains unconfirmed.",
        );
        setPaymentProcessing(false);
      } else {
        setPaymentMessage(
          paymentMethod === "MPESA"
            ? "M-PESA payment request sent. Complete the prompt on your phone; we will confirm the reservation automatically once payment succeeds."
            : "Payment is being processed. Please wait for confirmation.",
        );
      }
    } catch (err: any) {
      console.error("[SmartPark Reservations] Payment failed:", err);
      const detail = err?.response?.data?.detail;
      setPaymentStatus("FAILED");
      setPaymentMessage(
        typeof detail === "string"
          ? detail
          : "Payment could not be completed. Your reservation has not been confirmed.",
      );
      setPaymentProcessing(false);
    }
  };

  // Poll asynchronous M-PESA payments until the backend reports a final status.
  useEffect(() => {
    if (!paymentId || !paymentReservation || !paymentStatus) return;
    if (!["PENDING", "PROCESSING"].includes(paymentStatus)) return;

    let cancelled = false;
    let attempts = 0;
    const maxAttempts = 60;

    const refreshPaymentStatus = async () => {
      attempts += 1;

      try {
        const response = await api.get<{
          id: number;
          status: string;
          paid_at?: string | null;
        }>(`/payments/${paymentId}`);

        if (cancelled) return;

        const latestStatus = response.data.status.toUpperCase();
        setPaymentStatus(latestStatus);

        if (latestStatus === "SUCCESSFUL") {
          setReservations((current) =>
            current.map((item) =>
              item.id === paymentReservation.id
                ? {
                    ...item,
                    status: "CONFIRMED",
                    confirmed_at:
                      response.data.paid_at ?? new Date().toISOString(),
                  }
                : item,
            ),
          );
          setPaymentMessage(
            "Payment successful. Your reservation is now confirmed.",
          );
          setPaymentProcessing(false);
        } else if (["FAILED", "CANCELLED"].includes(latestStatus)) {
          setPaymentMessage(
            "Payment was not completed. Your reservation remains unconfirmed.",
          );
          setPaymentProcessing(false);
        } else if (attempts >= maxAttempts) {
          setPaymentProcessing(false);
          setPaymentMessage(
            "We could not confirm the payment within the expected time. Please check your payment status before trying again.",
          );
        }
      } catch (err) {
        console.warn(
          "[SmartPark Reservations] Payment status refresh failed:",
          err,
        );

        if (attempts >= maxAttempts && !cancelled) {
          setPaymentProcessing(false);
          setPaymentMessage(
            "Payment status could not be confirmed automatically. Please refresh your reservations before retrying.",
          );
        }
      }
    };

    const intervalId = window.setInterval(() => {
      void refreshPaymentStatus();
    }, 2000);

    void refreshPaymentStatus();

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [paymentId, paymentReservation?.id, paymentStatus]);

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
    } catch (err: any) {
      console.error(
        "[SmartPark Reservations] Failed to cancel reservation:",
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

  const handleDelete = async (reservation: ParkingReservation) => {
    if (
      !window.confirm(
        `Remove reservation ${reservation.reservation_number} from your reservations list?`,
      )
    ) {
      return;
    }

    setProcessingReservationId(reservation.id);
    setError(null);

    try {
      await api.delete(`/parking-reservations/${reservation.id}`);

      setReservations((current) =>
        current.filter((item) => item.id !== reservation.id),
      );
      setLastUpdated(new Date());
    } catch (err: any) {
      console.error(
        "[SmartPark Reservations] Failed to delete reservation:",
        err,
      );

      const detail = err?.response?.data?.detail;
      setError(
        typeof detail === "string"
          ? detail
          : "The reservation could not be deleted.",
      );
    } finally {
      setProcessingReservationId(null);
    }
  };

  // ----------------------------------------------------------
  // Render
  // ----------------------------------------------------------

  return (
    <div className="space-y-6">
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

      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <Page
          title="My Reservations"
          text="Manage upcoming and completed parking bookings."
        />

        <button
          type="button"
          onClick={refresh}
          disabled={isRefreshing || loading}
          className="inline-flex items-center justify-center gap-2 self-start rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
        >
          <RefreshCw size={16} className={isRefreshing ? "animate-spin" : ""} />

          {isRefreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {/* =====================================================
          Summary Metrics
      ===================================================== */}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Total Reservations"
          value={loading ? "…" : String(reservations.length)}
          note="All reservations"
          Icon={ParkingCircle}
        />

        <Metric
          label="Upcoming"
          value={loading ? "…" : String(upcomingReservations.length)}
          note="Future bookings"
          Icon={Clock3}
        />

        <Metric
          label="Active"
          value={loading ? "…" : String(activeReservations.length)}
          note="Currently active"
          Icon={CheckCircle2}
        />

        <Metric
          label="Completed"
          value={loading ? "…" : String(completedReservations.length)}
          note="Completed bookings"
          Icon={Activity}
        />
      </div>

      {/* =====================================================
          Error
      ===================================================== */}

      {error && !editingReservation && (
        <div className="rounded-2xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-800">
          <div className="flex items-start gap-3">
            <Activity size={18} className="mt-0.5 shrink-0" />

            <div>
              <b className="font-bold">Live data warning</b>

              <p className="mt-1">{error}</p>
            </div>
          </div>
        </div>
      )}

      {/* =====================================================
          Reservations Card
      ===================================================== */}

      <Card
        title="Reservations"
        sub={
          lastUpdated
            ? `Live data • Last updated ${formatDateTime(
                lastUpdated.toISOString(),
              )}`
            : "Live reservation data from SmartPark AI"
        }
      >
        {/* ---------------------------------------------------
            Intelligent reservation search
        --------------------------------------------------- */}
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
              placeholder="Search reservation number, vehicle, facility, bay, status or date..."
              aria-label="Search reservations"
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
            Showing {visibleReservations.length} matching reservation
            {visibleReservations.length === 1 ? "" : "s"}.
          </p>
        )}

        {/* ---------------------------------------------------
            Loading
        --------------------------------------------------- */}

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
        ) : reservations.length === 0 ? (
          /* -------------------------------------------------
             Empty state
          ------------------------------------------------- */

          <div className="rounded-2xl bg-slate-50 px-6 py-12 text-center">
            <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
              <ParkingCircle size={28} />
            </div>

            <h3 className="mt-4 text-lg font-extrabold text-slate-900">
              No reservations yet
            </h3>

            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
              You currently have no parking reservations. Find a parking
              facility and reserve a space when you are ready.
            </p>

            <Link
              to="/parking"
              className="mt-5 inline-flex items-center gap-2 rounded-xl bg-emerald-500 px-5 py-3 text-sm font-extrabold text-slate-950 transition hover:bg-emerald-400"
            >
              Find Parking
              <ArrowRight size={16} />
            </Link>
          </div>
        ) : visibleReservations.length === 0 ? (
          /* -------------------------------------------------
             No search/view matches
          ------------------------------------------------- */

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

            {searchTerm.trim() && (
              <button
                type="button"
                onClick={() => setSearchTerm("")}
                className="mt-5 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white transition hover:bg-emerald-700"
              >
                Clear search
              </button>
            )}
          </div>
        ) : (
          /* -------------------------------------------------
             Live reservation list
          ------------------------------------------------- */

          <div className="space-y-4">
            {visibleReservations
              .slice()
              .sort(
                (a, b) =>
                  new Date(b.created_at).getTime() -
                  new Date(a.created_at).getTime(),
              )
              .map((reservation) => {
                const bay = getReservationBay(reservation);
                const zone = getReservationZone(reservation);
                const facility = getReservationFacility(reservation);

                const status = getStatus(reservation);

                return (
                  <article
                    key={reservation.id}
                    className="rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-slate-300 hover:shadow-sm"
                  >
                    {/* ---------------------------------------
                        Header
                    --------------------------------------- */}

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

                    {/* ---------------------------------------
                        Main information
                    --------------------------------------- */}

                    <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                      <div className="rounded-xl bg-slate-50 p-4">
                        <div className="flex items-center gap-2 text-xs font-semibold text-slate-500">
                          <CalendarPlus size={15} />
                          Date
                        </div>

                        <p className="mt-2 text-sm font-extrabold text-slate-900">
                          {formatDate(reservation.reserved_from)}
                        </p>
                      </div>

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

                    {/* ---------------------------------------
                        Footer
                    --------------------------------------- */}

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

                    {/* ---------------------------------------
                        Reservation actions
                    --------------------------------------- */}

                    <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
                      {status.label === "Cancelled" ||
                      status.label === "Expired" ? (
                        <button
                          type="button"
                          onClick={() => void handleDelete(reservation)}
                          disabled={processingReservationId === reservation.id}
                          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-600 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          <Trash2 size={15} />
                          {processingReservationId === reservation.id
                            ? "Processing..."
                            : "Delete"}
                        </button>
                      ) : status.label === "Checked In" ? (
                        <div className="inline-flex items-center gap-2 rounded-xl border border-blue-200 bg-blue-50 px-4 py-2.5 text-sm font-bold text-blue-700">
                          <Activity size={15} />
                          Parking session in progress...
                        </div>
                      ) : status.label === "Completed" ? null : (
                        <>
                          <button
                            type="button"
                            onClick={() => handleUpdate(reservation)}
                            disabled={
                              processingReservationId === reservation.id
                            }
                            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            <Pencil size={15} />
                            Update
                          </button>

                          <button
                            type="button"
                            onClick={() => void handleCancel(reservation)}
                            disabled={
                              processingReservationId === reservation.id
                            }
                            className="inline-flex items-center justify-center gap-2 rounded-xl border border-rose-200 bg-white px-4 py-2.5 text-sm font-bold text-rose-700 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            <XCircle size={15} />
                            {processingReservationId === reservation.id
                              ? "Processing..."
                              : "Cancel"}
                          </button>

                          {String(reservation.status ?? "").toUpperCase() ===
                            "CREATED" && (
                            <button
                              type="button"
                              onClick={() => handleConfirm(reservation)}
                              disabled={
                                processingReservationId === reservation.id
                              }
                              className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                            >
                              <CreditCard size={15} />
                              Confirm Reservation
                            </button>
                          )}
                        </>
                      )}
                    </div>

                    {/* ---------------------------------------
                        Lifecycle information
                    --------------------------------------- */}

                    {(reservation.confirmed_at ||
                      reservation.checked_in_at ||
                      reservation.completed_at ||
                      reservation.cancelled_at) && (
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

                          {reservation.checked_in_at && (
                            <span>
                              Checked in:{" "}
                              <b className="text-slate-700">
                                {formatDateTime(reservation.checked_in_at)}
                              </b>
                            </span>
                          )}

                          {reservation.completed_at && (
                            <span>
                              Completed:{" "}
                              <b className="text-slate-700">
                                {formatDateTime(reservation.completed_at)}
                              </b>
                            </span>
                          )}

                          {reservation.cancelled_at && (
                            <span>
                              Cancelled:{" "}
                              <b className="text-slate-700">
                                {formatDateTime(reservation.cancelled_at)}
                              </b>
                            </span>
                          )}
                        </div>
                      </div>
                    )}
                  </article>
                );
              })}
          </div>
        )}
      </Card>

      {/* =====================================================
          Update Reservation Modal
      ===================================================== */}

      {editingReservation && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="update-reservation-title"
        >
          <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-3xl bg-white shadow-2xl">
            <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-slate-100 bg-white px-6 py-5">
              <div>
                <h2
                  id="update-reservation-title"
                  className="text-xl font-extrabold text-slate-900"
                >
                  Update Reservation
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Reservation {editingReservation.reservation_number}
                </p>
              </div>
              <button
                type="button"
                onClick={closeUpdateModal}
                disabled={savingUpdate}
                className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-50"
                aria-label="Close update reservation dialog"
              >
                <XCircle size={18} />
              </button>
            </div>

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

              <div className="flex flex-col-reverse gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={closeUpdateModal}
                  disabled={savingUpdate}
                  className="rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-sm font-extrabold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  Close
                </button>
                <button
                  type="button"
                  onClick={() => void handleSaveUpdate()}
                  disabled={savingUpdate}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-extrabold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
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

      {/* =====================================================
          Payment Modal
      ===================================================== */}

      {paymentReservation && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          aria-labelledby="reservation-payment-title"
        >
          <div className="max-h-[92vh] w-full max-w-xl overflow-y-auto rounded-3xl bg-white shadow-2xl">
            <div className="border-b border-slate-100 px-6 py-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-extrabold uppercase tracking-wider text-emerald-600">
                    Reservation Payment
                  </p>
                  <h2
                    id="reservation-payment-title"
                    className="mt-1 text-xl font-extrabold text-slate-900"
                  >
                    Confirm & Pay
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {paymentReservation.reservation_number} •{" "}
                    {formatDate(paymentReservation.reserved_from)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={closePaymentModal}
                  disabled={paymentProcessing}
                  className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-50"
                  aria-label="Close payment dialog"
                >
                  <XCircle size={18} />
                </button>
              </div>
            </div>

            <div className="space-y-5 p-6">
              <div className="rounded-2xl bg-slate-50 p-5">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="text-xs font-semibold text-slate-500">
                      Amount payable
                    </p>
                    <p className="mt-1 text-2xl font-extrabold text-slate-900">
                      {formatAmount(
                        paymentReservation.estimated_amount,
                        paymentReservation.currency || "KES",
                      )}
                    </p>
                  </div>
                  <CreditCard className="text-emerald-600" size={30} />
                </div>
              </div>

              {!paymentStatus ||
              ["FAILED", "CANCELLED"].includes(paymentStatus) ? (
                <>
                  <div>
                    <p className="mb-3 text-sm font-extrabold text-slate-900">
                      Choose payment method
                    </p>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <button
                        type="button"
                        onClick={() => {
                          setPaymentMethod("WALLET");
                          setPaymentProvider("INTERNAL");
                        }}
                        className={`rounded-2xl border p-4 text-left transition ${paymentMethod === "WALLET" ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100" : "border-slate-200 bg-white hover:bg-slate-50"}`}
                      >
                        <div className="flex items-center gap-3">
                          <Wallet size={21} className="text-emerald-600" />
                          <span className="font-extrabold text-slate-900">
                            SmartPark Wallet
                          </span>
                        </div>
                        <p className="mt-2 text-xs leading-5 text-slate-500">
                          Pay using your SmartPark wallet balance.
                        </p>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          setPaymentMethod("MPESA");
                          setPaymentProvider("SAFARICOM");
                        }}
                        className={`rounded-2xl border p-4 text-left transition ${paymentMethod === "MPESA" ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100" : "border-slate-200 bg-white hover:bg-slate-50"}`}
                      >
                        <div className="flex items-center gap-3">
                          <Smartphone size={21} className="text-emerald-600" />
                          <span className="font-extrabold text-slate-900">
                            M-PESA
                          </span>
                        </div>
                        <p className="mt-2 text-xs leading-5 text-slate-500">
                          Pay using an M-PESA number.
                        </p>
                      </button>
                    </div>
                  </div>

                  {paymentMethod === "MPESA" && (
                    <label className="block text-sm font-bold text-slate-700">
                      M-PESA Phone Number
                      <input
                        value={mpesaPhone}
                        onChange={(event) => setMpesaPhone(event.target.value)}
                        placeholder="0712345678"
                        inputMode="tel"
                        className="mt-2 w-full rounded-xl border border-slate-200 px-3 py-2.5 text-sm font-medium outline-none focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                      />
                    </label>
                  )}

                  {paymentMessage && (
                    <div className="flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
                      <AlertCircle size={18} className="mt-0.5 shrink-0" />
                      <span>{paymentMessage}</span>
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={() => void handlePayment()}
                    disabled={paymentProcessing}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {paymentProcessing ? (
                      <RefreshCw size={17} className="animate-spin" />
                    ) : (
                      <CreditCard size={17} />
                    )}
                    {paymentProcessing
                      ? "Processing Payment..."
                      : `Pay ${formatAmount(paymentReservation.estimated_amount, paymentReservation.currency || "KES")}`}
                  </button>
                </>
              ) : paymentStatus === "SUCCESSFUL" ? (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
                  <div className="flex items-start gap-3">
                    <CheckCircle2
                      className="mt-0.5 text-emerald-600"
                      size={22}
                    />
                    <div>
                      <h3 className="font-extrabold text-emerald-900">
                        Payment successful
                      </h3>
                      <p className="mt-1 text-sm text-emerald-800">
                        Your reservation has been confirmed successfully.
                      </p>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={closePaymentModal}
                    className="mt-4 w-full rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white hover:bg-emerald-700"
                  >
                    Done
                  </button>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="rounded-2xl border border-blue-200 bg-blue-50 p-5">
                    <div className="flex items-start gap-3">
                      <RefreshCw
                        className="mt-0.5 animate-spin text-blue-600"
                        size={20}
                      />
                      <div>
                        <h3 className="font-extrabold text-blue-900">
                          Payment pending
                        </h3>
                        <p className="mt-1 text-sm leading-6 text-blue-800">
                          {paymentMessage ||
                            "We are waiting for the payment provider to confirm your payment."}
                        </p>
                      </div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={closePaymentModal}
                    disabled={paymentProcessing}
                    className="w-full rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-extrabold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                  >
                    Close
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
