import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  ArrowLeft,
  ArrowRight,
  Car,
  CheckCircle2,
  Clock3,
  CreditCard,
  MapPin,
  ParkingCircle,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { Link, useNavigate } from "react-router";

import { useAuth } from "../../../auth/AuthContext";
import {
  api,
  parkingBaysApi,
  parkingFacilitiesApi,
  parkingZonesApi,
  type ParkingBay,
  type ParkingFacility,
  type ParkingZone,
} from "../../../api";

// ==========================================================
// Types
// ==========================================================

interface Vehicle {
  id: number;
  registration_number: string;
  nickname: string | null;
  make: string;
  model: string;
  colour: string | null;
  vehicle_type: string;
  is_default: boolean;
  is_active: boolean;
}

interface VehicleListResponse {
  vehicles: Vehicle[];
  total: number;
}

interface ReservationResponse {
  id: number;
  reservation_number: string;
  customer_id: number | null;
  parking_bay_id: number;
  vehicle_id: number | null;
  vehicle_registration: string;
  vehicle_type: string;
  reserved_from: string;
  reserved_until: string;
  estimated_amount: number | string | null;
  currency: string;
  status: string;
  expires_at: string | null;
  confirmed_at: string | null;
  checked_in_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: number | null;
  updated_by: number | null;
}

interface PaymentResponse {
  id: number;
  transaction_number: string;
  reservation_id: number | null;
  customer_id: number | null;
  payment_type: string;
  payment_purpose: string;
  payment_method: string;
  payment_provider: string;
  status: string;
  currency: string;
  subtotal_amount: number | string;
  discount_amount: number | string;
  tax_amount: number | string;
  total_amount: number | string;
  balance_after: number | string | null;
  receipt_number: string | null;
  external_reference: string | null;
  provider_transaction_id: string | null;
  provider_status_message: string | null;
  payer_name: string | null;
  payer_phone: string | null;
  payer_email: string | null;
  loyalty_points_earned: number;
  loyalty_points_redeemed: number;
  is_reconciled: boolean;
  paid_at: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

interface ActiveBayReservation {
  id: number;
  parking_bay_id: number;
  reserved_from: string;
  reserved_until: string;
  status: string;
}

// ==========================================================
// Constants
// ==========================================================

const VEHICLE_TYPE_LABELS: Record<string, string> = {
  CAR: "Car",
  SUV: "SUV",
  TRUCK: "Truck",
  MOTORCYCLE: "Motorcycle",
  BUS: "Bus",
  ANY: "Any",
};

const PAYMENT_OPTIONS = [
  {
    method: "WALLET",
    provider: "INTERNAL",
    label: "SmartPark Wallet",
    description: "Pay using your SmartPark wallet balance.",
  },
  {
    method: "MPESA",
    provider: "SAFARICOM",
    label: "M-PESA",
    description: "Pay using the M-PESA number you enter.",
  },
] as const;

// ==========================================================
// Helpers
// ==========================================================

function formatVehicleType(value: string): string {
  return VEHICLE_TYPE_LABELS[value] ?? value.replace(/_/g, " ");
}

function formatMoney(
  amount: number | string | null | undefined,
  currency = "KES",
): string {
  const numericAmount = Number(amount ?? 0);

  if (!Number.isFinite(numericAmount)) {
    return `${currency} 0.00`;
  }

  return new Intl.NumberFormat("en-KE", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(numericAmount);
}

function formatDateTime(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("en-KE", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatReservationDuration(totalMinutes: number): string {
  if (!Number.isFinite(totalMinutes) || totalMinutes <= 0) {
    return "";
  }

  const minutes = Math.round(totalMinutes);
  const days = Math.floor(minutes / (24 * 60));
  const remainingAfterDays = minutes % (24 * 60);
  const hours = Math.floor(remainingAfterDays / 60);
  const remainingMinutes = remainingAfterDays % 60;

  const parts: string[] = [];

  if (days > 0) {
    parts.push(`${days} ${days === 1 ? "day" : "days"}`);
  }

  if (hours > 0) {
    parts.push(`${hours} ${hours === 1 ? "hour" : "hours"}`);
  }

  if (remainingMinutes > 0) {
    parts.push(
      `${remainingMinutes} ${remainingMinutes === 1 ? "minute" : "minutes"}`,
    );
  }

  return parts.join(" ");
}

function toLocalDateTimeInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");

  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function localInputToIso(value: string): string {
  return new Date(value).toISOString();
}

function getFacilityCoordinates(
  facility: ParkingFacility,
): { latitude: number; longitude: number } | null {
  const candidate = facility as ParkingFacility & {
    latitude?: number | string | null;
    longitude?: number | string | null;
  };

  const latitude = Number(candidate.latitude);
  const longitude = Number(candidate.longitude);

  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) {
    return null;
  }

  return { latitude, longitude };
}

function calculateDistanceKm(
  fromLatitude: number,
  fromLongitude: number,
  toLatitude: number,
  toLongitude: number,
): number {
  const earthRadiusKm = 6371;
  const latitudeDifference = ((toLatitude - fromLatitude) * Math.PI) / 180;
  const longitudeDifference = ((toLongitude - fromLongitude) * Math.PI) / 180;

  const a =
    Math.sin(latitudeDifference / 2) ** 2 +
    Math.cos((fromLatitude * Math.PI) / 180) *
      Math.cos((toLatitude * Math.PI) / 180) *
      Math.sin(longitudeDifference / 2) ** 2;

  return earthRadiusKm * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function formatDistance(distanceKm: number): string {
  if (distanceKm < 1) return `${Math.round(distanceKm * 1000)} m away`;
  return `${distanceKm.toFixed(1)} km away`;
}

function getApiErrorMessage(error: any): string {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((item: any) => {
        const location = Array.isArray(item?.loc)
          ? item.loc.filter(
              (part: unknown) =>
                part !== "body" && part !== "query" && part !== "path",
            )
          : [];

        const field = location.length
          ? String(location[location.length - 1])
              .replace(/_/g, " ")
              .replace(/\b\w/g, (char) => char.toUpperCase())
          : "Reservation details";

        const message =
          typeof item?.msg === "string" ? item.msg : "Please check this value.";

        return `${field}: ${message}`;
      })
      .join(" ");
  }

  return "The reservation could not be created. Please review your selections and try again.";
}

function normalizeKenyanPhone(value: string): string {
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

function isValidKenyanMpesaPhone(value: string): boolean {
  return /^254(?:7|1)\d{8}$/.test(value);
}

function isReservationActiveForPeriod(
  reservation: ActiveBayReservation,
  from: Date,
  until: Date,
): boolean {
  const reservationFrom = new Date(reservation.reserved_from);
  const reservationUntil = new Date(reservation.reserved_until);

  return (
    reservationFrom < until &&
    reservationUntil > from &&
    !["CANCELLED", "EXPIRED", "COMPLETED"].includes(
      reservation.status.toUpperCase(),
    )
  );
}

// ==========================================================
// Component
// ==========================================================

export default function CreateReservation() {
  const navigate = useNavigate();
  const { user } = useAuth();

  // --------------------------------------------------------
  // Data
  // --------------------------------------------------------

  const [facilities, setFacilities] = useState<ParkingFacility[]>([]);
  const [facilitySearch, setFacilitySearch] = useState("");
  const [userLocation, setUserLocation] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);
  const [zones, setZones] = useState<ParkingZone[]>([]);
  const [bays, setBays] = useState<ParkingBay[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);

  // --------------------------------------------------------
  // Selection
  // --------------------------------------------------------

  const [facilityId, setFacilityId] = useState<number | "">("");
  const [parkingZoneId, setParkingZoneId] = useState<number | "">("");
  const [parkingBayId, setParkingBayId] = useState<number | "">("");
  const [vehicleId, setVehicleId] = useState<number | "">("");

  const [vehicleMode, setVehicleMode] = useState<"REGISTERED" | "BORROWED">(
    "REGISTERED",
  );
  const [borrowedRegistration, setBorrowedRegistration] = useState("");
  const [borrowedVehicleType, setBorrowedVehicleType] = useState("CAR");

  // --------------------------------------------------------
  // Reservation period
  // --------------------------------------------------------

  const initialFrom = useMemo(() => {
    const date = new Date();
    date.setMinutes(date.getMinutes() + 30);
    date.setSeconds(0);
    date.setMilliseconds(0);

    return toLocalDateTimeInputValue(date);
  }, []);

  const initialUntil = useMemo(() => {
    const date = new Date();
    date.setMinutes(date.getMinutes() + 90);
    date.setSeconds(0);
    date.setMilliseconds(0);

    return toLocalDateTimeInputValue(date);
  }, []);

  const [reservedFrom, setReservedFrom] = useState(initialFrom);
  const [reservedUntil, setReservedUntil] = useState(initialUntil);

  const [notes, setNotes] = useState("");

  // --------------------------------------------------------
  // Payment
  // --------------------------------------------------------

  const [paymentMethod, setPaymentMethod] = useState("WALLET");
  const [paymentProvider, setPaymentProvider] = useState("INTERNAL");
  const [useRegisteredMpesaPhone, setUseRegisteredMpesaPhone] = useState(true);
  const [mpesaPhone, setMpesaPhone] = useState("");

  // --------------------------------------------------------
  // Workflow
  // --------------------------------------------------------

  const [step, setStep] = useState(1);

  const [createdReservation, setCreatedReservation] =
    useState<ReservationResponse | null>(null);

  const [payment, setPayment] = useState<PaymentResponse | null>(null);

  // --------------------------------------------------------
  // Loading / error
  // --------------------------------------------------------

  const [loading, setLoading] = useState(true);
  const [submittingReservation, setSubmittingReservation] = useState(false);
  const [processingPayment, setProcessingPayment] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [payLaterToastVisible, setPayLaterToastVisible] = useState(false);

  // Keep the M-PESA field aligned with the authenticated customer's
  // registered phone number when the account is loaded/restored.
  useEffect(() => {
    const registeredPhone = normalizeKenyanPhone(
      String(user?.phone_number ?? ""),
    );

    setMpesaPhone(registeredPhone);
    setUseRegisteredMpesaPhone(Boolean(registeredPhone));
  }, [user?.phone_number]);

  // ========================================================
  // Load required data
  // ========================================================

  useEffect(() => {
    let cancelled = false;

    const loadData = async () => {
      setLoading(true);
      setError(null);

      try {
        const [
          facilitiesResponse,
          zonesResponse,
          baysResponse,
          vehiclesResponse,
        ] = await Promise.all([
          parkingFacilitiesApi.list(0, 500),
          parkingZonesApi.list(0, 500),
          parkingBaysApi.list(0, 500),
          api.get<VehicleListResponse>("/vehicles"),
        ]);

        if (cancelled) {
          return;
        }

        setFacilities(
          facilitiesResponse.items.filter(
            (facility) => facility.is_active !== false,
          ),
        );

        setZones(zonesResponse.items);

        setBays(bayResponseItems(baysResponse.items));

        const activeVehicles = vehiclesResponse.data.vehicles.filter(
          (vehicle) => vehicle.is_active,
        );

        setVehicles(activeVehicles);

        const defaultVehicle =
          activeVehicles.find((vehicle) => vehicle.is_default) ??
          activeVehicles[0];

        if (defaultVehicle) {
          setVehicleId(defaultVehicle.id);
        }
      } catch (err: any) {
        console.error(
          "[SmartPark Create Reservation] Failed to load data:",
          err,
        );

        const detail = err?.response?.data?.detail;

        setError(
          typeof detail === "string"
            ? detail
            : "Unable to load the information required to create a reservation.",
        );
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadData();

    return () => {
      cancelled = true;
    };
  }, []);

  // ========================================================
  // Facility → Bay relationship
  // ========================================================

  const facilityZoneIds = useMemo(() => {
    if (facilityId === "") {
      return new Set<number>();
    }

    return new Set(
      zones
        .filter((zone) => zone.facility_id === facilityId)
        .map((zone) => zone.id),
    );
  }, [facilityId, zones]);

  const facilityZones = useMemo(() => {
    if (facilityId === "") {
      return [];
    }

    return zones.filter(
      (zone) => zone.facility_id === facilityId && zone.is_active !== false,
    );
  }, [facilityId, zones]);

  const facilityBays = useMemo(() => {
    return bays.filter(
      (bay) => facilityZoneIds.has(bay.zone_id) && bay.is_active !== false,
    );
  }, [bays, facilityZoneIds]);

  // Bays displayed in Step 2B must belong to the currently selected zone.
  // Keep this derived from the existing facilityBays so we do not change
  // any of the existing Facility → Zone → Bay workflow.
  const zoneBays = useMemo(() => {
    if (parkingZoneId === "") {
      return [];
    }

    return facilityBays.filter((bay) => bay.zone_id === parkingZoneId);
  }, [facilityBays, parkingZoneId]);

  // Clear selected bay when facility changes.

  useEffect(() => {
    setParkingZoneId("");
    setParkingBayId("");
  }, [facilityId]);

  // ========================================================
  // Driver location — used to order facilities by proximity
  useEffect(() => {
    if (!navigator.geolocation) return;

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
      },
      (locationError) => {
        console.warn(
          "[SmartPark Create Reservation] Unable to determine driver location:",
          locationError.message,
        );
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 300000 },
    );
  }, []);

  // Selected objects
  // ========================================================

  const selectedFacility = useMemo(
    () => facilities.find((facility) => facility.id === facilityId) ?? null,
    [facilities, facilityId],
  );

  const selectedZone = useMemo(
    () => zones.find((zone) => zone.id === parkingZoneId) ?? null,
    [zones, parkingZoneId],
  );

  const selectedBay = useMemo(
    () => bays.find((bay) => bay.id === parkingBayId) ?? null,
    [bays, parkingBayId],
  );

  const selectedVehicle = useMemo(
    () => vehicles.find((vehicle) => vehicle.id === vehicleId) ?? null,
    [vehicles, vehicleId],
  );

  const filteredFacilities = useMemo(() => {
    const query = facilitySearch.trim().toLowerCase();

    const matchingFacilities = query
      ? facilities.filter((facility) =>
          [
            facility.name,
            facility.code,
            facility.facility_type,
            facility.address,
            facility.city,
          ]
            .filter(Boolean)
            .some((value) => String(value).toLowerCase().includes(query)),
        )
      : facilities;

    if (!userLocation) return matchingFacilities;

    return [...matchingFacilities].sort((first, second) => {
      const firstCoordinates = getFacilityCoordinates(first);
      const secondCoordinates = getFacilityCoordinates(second);

      if (!firstCoordinates && !secondCoordinates) return 0;
      if (!firstCoordinates) return 1;
      if (!secondCoordinates) return -1;

      return (
        calculateDistanceKm(
          userLocation.latitude,
          userLocation.longitude,
          firstCoordinates.latitude,
          firstCoordinates.longitude,
        ) -
        calculateDistanceKm(
          userLocation.latitude,
          userLocation.longitude,
          secondCoordinates.latitude,
          secondCoordinates.longitude,
        )
      );
    });
  }, [facilities, facilitySearch, userLocation]);

  // ========================================================
  // Validation
  // ========================================================

  const periodValidation = useMemo(() => {
    if (!reservedFrom || !reservedUntil) {
      return "Please select both reservation start and end times.";
    }

    const from = new Date(reservedFrom);
    const until = new Date(reservedUntil);

    if (Number.isNaN(from.getTime()) || Number.isNaN(until.getTime())) {
      return "Please provide valid reservation times.";
    }

    if (until <= from) {
      return "Reservation end time must be later than the start time.";
    }

    if (from <= new Date()) {
      return "Reservation start time must be in the future.";
    }

    return null;
  }, [reservedFrom, reservedUntil]);

  const reservationDuration = useMemo(() => {
    if (periodValidation || !reservedFrom || !reservedUntil) {
      return null;
    }

    const from = new Date(reservedFrom);
    const until = new Date(reservedUntil);
    const totalMinutes = (until.getTime() - from.getTime()) / (1000 * 60);

    if (!Number.isFinite(totalMinutes) || totalMinutes <= 0) {
      return null;
    }

    return formatReservationDuration(totalMinutes);
  }, [reservedFrom, reservedUntil, periodValidation]);

  // ========================================================
  // Existing active reservations for selected bay
  // ========================================================

  const [bayReservations, setBayReservations] = useState<
    ActiveBayReservation[]
  >([]);

  const [checkingBayAvailability, setCheckingBayAvailability] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const checkBayReservations = async () => {
      if (parkingBayId === "" || periodValidation) {
        setBayReservations([]);
        return;
      }

      setCheckingBayAvailability(true);

      try {
        const response = await api.get<{
          items: ActiveBayReservation[];
          total: number;
        }>(`/parking-reservations/parking-bay/${parkingBayId}/active`);

        if (!cancelled) {
          setBayReservations(response.data.items);
        }
      } catch (err) {
        console.error(
          "[SmartPark Create Reservation] Failed to check bay availability:",
          err,
        );

        if (!cancelled) {
          setBayReservations([]);
        }
      } finally {
        if (!cancelled) {
          setCheckingBayAvailability(false);
        }
      }
    };

    void checkBayReservations();

    return () => {
      cancelled = true;
    };
  }, [parkingBayId, reservedFrom, reservedUntil, periodValidation]);

  const bayConflict = useMemo(() => {
    if (periodValidation || !reservedFrom || !reservedUntil) {
      return false;
    }

    const from = new Date(reservedFrom);
    const until = new Date(reservedUntil);

    return bayReservations.some((reservation) =>
      isReservationActiveForPeriod(reservation, from, until),
    );
  }, [bayReservations, reservedFrom, reservedUntil, periodValidation]);

  // ========================================================
  // Step validation
  // ========================================================

  const validateStepOne = (): string | null => {
    if (facilityId === "") {
      return "Please select a parking facility.";
    }

    return null;
  };

  const validateStepTwo = (): string | null => {
    if (parkingZoneId === "") {
      return "Please select a parking zone or level.";
    }

    if (parkingBayId === "") {
      return "Please select a parking bay.";
    }

    if (periodValidation) {
      return periodValidation;
    }

    if (checkingBayAvailability) {
      return "Please wait while we check parking bay availability.";
    }

    if (bayConflict) {
      return "This parking bay is already reserved for part of the selected period. Please choose another bay or time.";
    }

    return null;
  };

  const validateStepThree = (): string | null => {
    if (vehicleMode === "REGISTERED") {
      if (vehicleId === "") {
        return "Please select a registered vehicle or choose Borrowed / Unregistered Vehicle.";
      }

      return null;
    }

    if (!borrowedRegistration.trim()) {
      return "Please enter the borrowed or unregistered vehicle registration number.";
    }

    if (borrowedRegistration.trim().length < 2) {
      return "Please enter a valid vehicle registration number.";
    }

    if (!borrowedVehicleType) {
      return "Please select the borrowed vehicle type.";
    }

    return null;
  };

  // ========================================================
  // Navigation between steps
  // ========================================================

  const nextStep = () => {
    setError(null);

    if (step === 1) {
      const validation = validateStepOne();

      if (validation) {
        setError(validation);
        return;
      }
    }

    if (step === 2) {
      const validation = validateStepTwo();

      if (validation) {
        setError(validation);
        return;
      }
    }

    if (step === 3) {
      const validation = validateStepThree();

      if (validation) {
        setError(validation);
        return;
      }
    }

    setStep((current) => Math.min(current + 1, 5));
  };

  const previousStep = () => {
    setError(null);

    setStep((current) => Math.max(current - 1, 1));
  };

  // ========================================================
  // Create reservation
  // ========================================================

  const createReservation = async () => {
    const validation =
      validateStepOne() ?? validateStepTwo() ?? validateStepThree();

    if (validation) {
      setError(validation);
      return;
    }

    const registeredVehicle =
      vehicleMode === "REGISTERED" ? selectedVehicle : null;

    if (vehicleMode === "REGISTERED" && !registeredVehicle) {
      setError("The selected registered vehicle could not be found.");
      return;
    }

    setSubmittingReservation(true);
    setError(null);

    try {
      const reservationPayload =
        vehicleMode === "REGISTERED"
          ? {
              // Registered vehicle: send ONLY the vehicle ID.
              // The backend derives the registration/type from the registered vehicle.
              parking_bay_id: parkingBayId,
              vehicle_id: registeredVehicle!.id,
              reserved_from: localInputToIso(reservedFrom),
              reserved_until: localInputToIso(reservedUntil),
              notes: notes.trim() || null,
            }
          : {
              // Borrowed / unregistered vehicle: do NOT send vehicle_id.
              // The backend requires the registration and vehicle type instead.
              parking_bay_id: parkingBayId,
              vehicle_registration: borrowedRegistration.trim().toUpperCase(),
              vehicle_type: borrowedVehicleType,
              reserved_from: localInputToIso(reservedFrom),
              reserved_until: localInputToIso(reservedUntil),
              notes: notes.trim() || null,
            };

      const response = await api.post<ReservationResponse>(
        "/parking-reservations",
        reservationPayload,
      );

      setCreatedReservation(response.data);

      setStep(5);
    } catch (err: any) {
      console.error(
        "[SmartPark Create Reservation] Failed to create reservation:",
        err,
      );

      setError(getApiErrorMessage(err));
    } finally {
      setSubmittingReservation(false);
    }
  };

  // ========================================================
  // Payment
  // ========================================================

  const markReservationConfirmed = (latestPayment: PaymentResponse) => {
    if (latestPayment.status.toUpperCase() !== "SUCCESSFUL") {
      return;
    }

    setCreatedReservation((current) =>
      current
        ? {
            ...current,
            status: "CONFIRMED",
            confirmed_at: latestPayment.paid_at ?? new Date().toISOString(),
          }
        : current,
    );
  };

  const processPayment = async () => {
    if (!createdReservation || !user) {
      setError("Reservation or authenticated customer information is missing.");
      return;
    }

    const amount = Number(createdReservation.estimated_amount ?? 0);

    if (!Number.isFinite(amount) || amount < 0) {
      setError("The reservation returned an invalid payment amount.");
      return;
    }

    const normalizedMpesaPhone = normalizeKenyanPhone(mpesaPhone);

    if (
      paymentMethod === "MPESA" &&
      !isValidKenyanMpesaPhone(normalizedMpesaPhone)
    ) {
      setError(
        "Please enter a valid Kenyan M-PESA number, for example 0712345678 or 254712345678.",
      );
      return;
    }

    setProcessingPayment(true);
    setError(null);

    try {
      const response = await api.post<PaymentResponse>(
        "/payments/reservation",
        {
          payment_method: paymentMethod,
          payment_provider: paymentProvider,
          payment_purpose: "RESERVATION",
          payment_type: "PAYMENT",
          currency: createdReservation.currency || "KES",
          subtotal_amount: amount,
          discount_amount: 0,
          tax_amount: 0,
          total_amount: amount,
          payer_name: `${user.first_name} ${user.last_name}`.trim(),
          payer_phone:
            paymentMethod === "MPESA"
              ? normalizedMpesaPhone
              : String(user.phone_number ?? ""),
          payer_email: user.email,
          notes: notes.trim() || null,
          reservation_id: createdReservation.id,
          customer_id: user.id,
          loyalty_points_to_redeem: 0,
        },
      );

      setPayment(response.data);
      markReservationConfirmed(response.data);

      /*
       * The backend payment service automatically confirms a
       * reservation when the reservation payment succeeds.
       *
       * We therefore deliberately DO NOT call:
       *
       * PATCH /parking-reservations/{id}/confirm
       *
       * here.
       *
       * For M-PESA, the POST normally returns PENDING because the
       * STK Push is asynchronous. The payment status polling effect
       * below re-reads the payment from the backend until the
       * Safaricom callback changes it to SUCCESSFUL/FAILED/CANCELLED.
       */
    } catch (err: any) {
      console.error("[SmartPark Create Reservation] Payment failed:", err);

      const detail = err?.response?.data?.detail;

      setError(
        typeof detail === "string"
          ? detail
          : "Payment could not be completed. Your reservation has not been confirmed.",
      );
    } finally {
      setProcessingPayment(false);
    }
  };

  // ========================================================
  // Payment status polling
  // ========================================================

  useEffect(() => {
    if (!payment || !createdReservation) {
      return;
    }

    const initialStatus = payment.status.toUpperCase();

    if (!["PENDING", "PROCESSING"].includes(initialStatus)) {
      return;
    }

    let cancelled = false;
    let attempts = 0;
    const maxAttempts = 60;
    let polling = false;

    const refreshPaymentStatus = async () => {
      if (cancelled || polling) {
        return;
      }

      polling = true;
      attempts += 1;

      try {
        const response = await api.get<PaymentResponse>(
          `/payments/${payment.id}`,
        );

        if (cancelled) {
          return;
        }

        const latestPayment = response.data;

        setPayment(latestPayment);
        markReservationConfirmed(latestPayment);

        const latestStatus = latestPayment.status.toUpperCase();

        if (
          !["PENDING", "PROCESSING"].includes(latestStatus) ||
          attempts >= maxAttempts
        ) {
          clearInterval(intervalId);
        }
      } catch (err) {
        // Do not turn a temporary polling failure into a payment failure.
        // The payment may still complete through the M-PESA callback.
        console.warn(
          "[SmartPark Create Reservation] Payment status refresh failed:",
          err,
        );

        if (attempts >= maxAttempts) {
          clearInterval(intervalId);
        }
      } finally {
        polling = false;
      }
    };

    // Check immediately, then every 2 seconds while the payment is pending.
    const intervalId = window.setInterval(refreshPaymentStatus, 2000);
    void refreshPaymentStatus();

    return () => {
      cancelled = true;
      clearInterval(intervalId);
    };
  }, [payment?.id, payment?.status, createdReservation?.id]);

  // ========================================================
  // Payment state
  // ========================================================

  const paymentStatus = payment?.status?.toUpperCase() ?? "";

  const paymentSuccessful = paymentStatus === "SUCCESSFUL";

  const paymentPending =
    payment !== null && ["PENDING", "PROCESSING"].includes(paymentStatus);

  const paymentFailed =
    payment !== null && ["FAILED", "CANCELLED"].includes(paymentStatus);

  // ========================================================
  // Pay Later
  // ========================================================

  const handlePayLater = () => {
    setError(null);
    setPayLaterToastVisible(true);

    // Automatically continue after 10 seconds if the user does not
    // acknowledge the notification.
    window.setTimeout(() => {
      setPayLaterToastVisible(false);
      navigate("/reservations");
    }, 10000);
  };

  const handlePayLaterAcknowledged = () => {
    setPayLaterToastVisible(false);
    navigate("/reservations");
  };

  // ========================================================
  // Render
  // ========================================================

  if (loading) {
    return (
      <div className="space-y-6">
        <PageHeading />

        <div className="rounded-3xl bg-white p-8 shadow-sm ring-1 ring-slate-200">
          <div className="flex items-center justify-center gap-3 py-16 text-slate-500">
            <RefreshCw className="animate-spin" size={20} />
            Loading reservation options...
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeading />

      {/* ====================================================
          Progress
      ==================================================== */}

      <div className="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:p-6">
        <div className="grid grid-cols-5 gap-2">
          {["Facility", "Time & Bay", "Vehicle", "Review", "Payment"].map(
            (label, index) => {
              const itemStep = index + 1;
              const completed = step > itemStep;
              const active = step === itemStep;

              return (
                <div key={label} className="text-center">
                  <div
                    className={`mx-auto grid h-9 w-9 place-items-center rounded-full text-xs font-black ${
                      completed
                        ? "bg-emerald-600 text-white"
                        : active
                          ? "bg-emerald-100 text-emerald-700 ring-2 ring-emerald-500"
                          : "bg-slate-100 text-slate-400"
                    }`}
                  >
                    {completed ? <CheckCircle2 size={17} /> : itemStep}
                  </div>

                  <p
                    className={`mt-2 hidden text-xs font-bold sm:block ${
                      active ? "text-emerald-700" : "text-slate-500"
                    }`}
                  >
                    {label}
                  </p>
                </div>
              );
            },
          )}
        </div>
      </div>

      {/* ====================================================
          Error
      ==================================================== */}

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-rose-800">
          <AlertCircle className="mt-0.5 shrink-0 text-rose-600" size={20} />

          <div>
            <p className="font-bold">Something needs your attention</p>

            <p className="mt-1 text-sm">{error}</p>
          </div>
        </div>
      )}

      {payLaterToastVisible && (
        <div
          role="status"
          aria-live="polite"
          className="fixed inset-0 z-50 flex items-center justify-center px-4"
        >
          <div className="flex max-w-md items-start gap-3 rounded-2xl border border-amber-200 bg-white px-5 py-4 text-slate-800 shadow-2xl ring-1 ring-black/5">
            <ShieldCheck className="mt-0.5 shrink-0 text-amber-600" size={22} />

            <div className="min-w-0 flex-1">
              <p className="font-extrabold">Reservation not yet confirmed</p>
              <p className="mt-1 text-sm leading-5 text-slate-600">
                Your reservation is awaiting payment. It will only be confirmed
                after successful payment.
              </p>

              <button
                type="button"
                onClick={handlePayLaterAcknowledged}
                className="mt-4 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-bold text-white hover:bg-emerald-700"
              >
                Understood
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ====================================================
          Step Content
      ==================================================== */}

      <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
        <main className="rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200 sm:p-8">
          {/* ==================================================
              STEP 1 — Facility
          ================================================== */}

          {step === 1 && (
            <StepContainer
              title="Choose a Parking Facility"
              description="Select where you would like to park."
            >
              <div className="mb-5">
                <label className="relative block">
                  <span className="sr-only">Search parking facilities</span>

                  <Search
                    size={18}
                    className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"
                  />

                  <input
                    type="search"
                    value={facilitySearch}
                    onChange={(event) => setFacilitySearch(event.target.value)}
                    placeholder="Search by facility name, code or location..."
                    className="w-full rounded-2xl border border-slate-200 bg-white py-3.5 pl-11 pr-4 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
                  />
                </label>

                <div className="mt-2 flex items-center justify-between px-1">
                  <p className="text-xs text-slate-500">
                    {facilitySearch.trim()
                      ? `${filteredFacilities.length} ${
                          filteredFacilities.length === 1
                            ? "facility"
                            : "facilities"
                        } found`
                      : `${facilities.length} facilities available`}
                  </p>

                  {facilitySearch && (
                    <button
                      type="button"
                      onClick={() => setFacilitySearch("")}
                      className="text-xs font-bold text-emerald-700 hover:text-emerald-800"
                    >
                      Clear search
                    </button>
                  )}
                </div>
              </div>

              <div className="grid gap-4">
                {filteredFacilities.map((facility) => {
                  const selected = facility.id === facilityId;

                  return (
                    <div
                      key={facility.id}
                      className={`w-full rounded-2xl border p-5 text-left transition ${
                        selected
                          ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                          : "border-slate-200 hover:border-emerald-300 hover:bg-slate-50"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => setFacilityId(facility.id)}
                        className="w-full text-left"
                      >
                        <div className="flex items-start gap-4">
                          <div
                            className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl ${
                              selected
                                ? "bg-emerald-600 text-white"
                                : "bg-emerald-50 text-emerald-600"
                            }`}
                          >
                            <ParkingCircle size={23} />
                          </div>

                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <h3 className="font-extrabold">
                                {facility.name}
                              </h3>

                              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                                {facility.code}
                              </span>
                            </div>

                            <p className="mt-1 text-xs font-bold uppercase tracking-wide text-slate-400">
                              {facility.facility_type}
                            </p>

                            <p className="mt-2 flex items-center gap-1.5 text-sm text-slate-500">
                              <MapPin size={14} />
                              {facility.address}, {facility.city}
                            </p>

                            {userLocation &&
                              getFacilityCoordinates(facility) && (
                                <p className="mt-1 text-xs font-bold text-emerald-600">
                                  {formatDistance(
                                    calculateDistanceKm(
                                      userLocation.latitude,
                                      userLocation.longitude,
                                      getFacilityCoordinates(facility)!
                                        .latitude,
                                      getFacilityCoordinates(facility)!
                                        .longitude,
                                    ),
                                  )}
                                </p>
                              )}
                          </div>

                          {selected && (
                            <CheckCircle2
                              className="shrink-0 text-emerald-600"
                              size={22}
                            />
                          )}
                        </div>
                      </button>

                      {selected && (
                        <div className="mt-5 flex items-center justify-between gap-4 border-t border-emerald-200 pt-4">
                          <div>
                            <p className="text-sm font-extrabold text-emerald-900">
                              Facility selected
                            </p>
                            <p className="mt-0.5 text-xs text-emerald-700">
                              Continue to choose your time, zone and parking
                              bay.
                            </p>
                          </div>

                          <button
                            type="button"
                            onClick={nextStep}
                            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-emerald-700"
                          >
                            Continue
                            <ArrowRight size={16} />
                          </button>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              {facilities.length === 0 ? (
                <EmptyState message="No active parking facilities are currently available." />
              ) : filteredFacilities.length === 0 ? (
                <EmptyState message="No parking facilities match your search." />
              ) : null}
            </StepContainer>
          )}

          {/* ==================================================
              STEP 2 — Time / Zone / Bay
          ================================================== */}

          {step === 2 && (
            <StepContainer
              title="Choose your time, parking zone and bay"
              description="Select the reservation period, parking zone or level, and an available bay."
            >
              <div className="grid gap-5 md:grid-cols-2">
                <Field label="Reserved from">
                  <input
                    type="datetime-local"
                    value={reservedFrom}
                    min={toLocalDateTimeInputValue(new Date())}
                    onChange={(event) => setReservedFrom(event.target.value)}
                    className="input"
                  />
                </Field>

                <Field label="Reserved until">
                  <input
                    type="datetime-local"
                    value={reservedUntil}
                    min={reservedFrom}
                    onChange={(event) => setReservedUntil(event.target.value)}
                    className="input"
                  />
                </Field>
              </div>

              {reservationDuration && (
                <div className="mt-4 flex items-center justify-between gap-4 rounded-2xl border border-emerald-100 bg-emerald-50 px-4 py-3.5">
                  <div className="flex items-center gap-3">
                    <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-emerald-600 shadow-sm ring-1 ring-emerald-100">
                      <Clock3 size={19} />
                    </div>

                    <div>
                      <p className="text-xs font-bold uppercase tracking-[.14em] text-emerald-700">
                        Duration
                      </p>
                      <p className="mt-0.5 text-base font-extrabold text-slate-900">
                        {reservationDuration}
                      </p>
                    </div>
                  </div>

                  <p className="hidden text-right text-xs font-semibold text-emerald-700 sm:block">
                    Based on your selected reservation times
                  </p>
                </div>
              )}

              {periodValidation && (
                <InlineWarning>{periodValidation}</InlineWarning>
              )}

              <div className="mt-8">
                <div className="mb-3">
                  <p className="text-xs font-bold uppercase tracking-[.16em] text-emerald-600">
                    Step 2A
                  </p>
                  <h3 className="mt-1 text-lg font-extrabold">
                    Select a parking zone / level
                  </h3>
                  <p className="mt-1 text-sm text-slate-500">
                    {selectedFacility?.name ?? "Selected facility"} · Choose the
                    zone or level where you want to park.
                  </p>
                </div>

                {facilityZones.length > 0 ? (
                  <div className="grid gap-3 sm:grid-cols-2">
                    {facilityZones.map((zone) => {
                      const selected = zone.id === parkingZoneId;
                      const availableBays = bays.filter(
                        (bay) =>
                          bay.zone_id === zone.id &&
                          bay.is_active !== false &&
                          bay.is_reservable !== false,
                      ).length;

                      return (
                        <button
                          key={zone.id}
                          type="button"
                          disabled={availableBays === 0}
                          onClick={() => setParkingZoneId(zone.id)}
                          className={`rounded-2xl border p-4 text-left transition ${
                            selected
                              ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                              : availableBays === 0
                                ? "cursor-not-allowed border-slate-200 bg-slate-50 opacity-60"
                                : "border-slate-200 hover:border-emerald-300 hover:bg-slate-50"
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <div
                              className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${
                                selected
                                  ? "bg-emerald-600 text-white"
                                  : "bg-emerald-50 text-emerald-600"
                              }`}
                            >
                              <ParkingCircle size={21} />
                            </div>

                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <h4 className="font-extrabold">{zone.name}</h4>
                                <span className="rounded-full bg-slate-100 px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                                  {zone.code}
                                </span>
                              </div>

                              <p className="mt-1 text-xs font-bold uppercase tracking-wide text-slate-400">
                                {zone.zone_type.replace(/_/g, " ")}
                              </p>

                              <p className="mt-2 text-xs font-semibold text-slate-500">
                                {availableBays}{" "}
                                {availableBays === 1 ? "bay" : "bays"} available
                              </p>
                            </div>

                            {selected && (
                              <CheckCircle2
                                className="shrink-0 text-emerald-600"
                                size={20}
                              />
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <EmptyState message="No parking zones or levels are configured for this facility." />
                )}
              </div>

              <div className="mt-8">
                <div className="mb-3 flex items-center justify-between gap-4">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[.16em] text-emerald-600">
                      Step 2B
                    </p>
                    <h3 className="mt-1 text-lg font-extrabold">
                      Choose an available parking bay
                    </h3>
                    <p className="mt-1 text-sm text-slate-500">
                      {selectedZone
                        ? `${selectedZone.name} · ${selectedZone.code}`
                        : "Select a parking zone / level first."}
                    </p>
                  </div>

                  {checkingBayAvailability && (
                    <RefreshCw
                      className="animate-spin text-emerald-600"
                      size={17}
                    />
                  )}
                </div>

                {parkingZoneId === "" ? (
                  <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-7 text-center">
                    <ParkingCircle
                      className="mx-auto text-slate-400"
                      size={30}
                    />
                    <p className="mt-3 text-sm font-semibold text-slate-600">
                      Select a parking zone / level above to see its bays.
                    </p>
                  </div>
                ) : zoneBays.length > 0 ? (
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {zoneBays.map((bay) => {
                      const selected = bay.id === parkingBayId;
                      const occupiedByReservation =
                        bay.id === parkingBayId && bayConflict;

                      return (
                        <button
                          key={bay.id}
                          type="button"
                          onClick={() => setParkingBayId(bay.id)}
                          className={`rounded-2xl border p-4 text-left transition ${
                            selected
                              ? occupiedByReservation
                                ? "border-rose-400 bg-rose-50"
                                : "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                              : "border-slate-200 hover:border-emerald-300"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-3">
                            <div className="flex items-center gap-3">
                              <div
                                className={`grid h-10 w-10 place-items-center rounded-xl ${
                                  selected
                                    ? occupiedByReservation
                                      ? "bg-rose-100 text-rose-600"
                                      : "bg-emerald-600 text-white"
                                    : "bg-slate-100 text-slate-500"
                                }`}
                              >
                                <ParkingCircle size={19} />
                              </div>

                              <div>
                                <p className="font-extrabold">
                                  {bay.bay_number}
                                </p>
                                <p className="text-xs text-slate-500">
                                  {bay.code} · Available
                                </p>
                              </div>
                            </div>

                            {selected && (
                              <CheckCircle2
                                className={
                                  occupiedByReservation
                                    ? "text-rose-600"
                                    : "text-emerald-600"
                                }
                                size={19}
                              />
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <EmptyState message="No active reservable parking bays are available in this zone." />
                )}
              </div>

              {bayConflict && (
                <InlineWarning>
                  This bay is already reserved during part of your selected
                  period. Please choose another bay or adjust the time.
                </InlineWarning>
              )}

              <div className="mt-7">
                <Field label="Notes (optional)">
                  <textarea
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    maxLength={1000}
                    rows={3}
                    placeholder="Anything the parking operator should know?"
                    className="input w-full resize-none"
                  />
                </Field>
              </div>

              <StepActions onBack={previousStep} onNext={nextStep} />
            </StepContainer>
          )}

          {/* ==================================================
              STEP 3 — Vehicle
          ================================================== */}

          {step === 3 && (
            <StepContainer
              title="Select your vehicle"
              description="Use one of your registered vehicles or provide a borrowed / unregistered vehicle."
            >
              <div className="grid gap-3 sm:grid-cols-2">
                <button
                  type="button"
                  onClick={() => setVehicleMode("REGISTERED")}
                  className={`rounded-2xl border p-5 text-left transition ${
                    vehicleMode === "REGISTERED"
                      ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                      : "border-slate-200 hover:border-emerald-300"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${
                        vehicleMode === "REGISTERED"
                          ? "bg-emerald-600 text-white"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      <Car size={21} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="font-extrabold">My registered vehicle</h3>
                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        Choose a vehicle already registered to your SmartPark
                        account.
                      </p>
                    </div>
                    {vehicleMode === "REGISTERED" && (
                      <CheckCircle2
                        className="shrink-0 text-emerald-600"
                        size={20}
                      />
                    )}
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    setVehicleMode("BORROWED");
                    setVehicleId("");
                  }}
                  className={`rounded-2xl border p-5 text-left transition ${
                    vehicleMode === "BORROWED"
                      ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                      : "border-slate-200 hover:border-emerald-300"
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div
                      className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${
                        vehicleMode === "BORROWED"
                          ? "bg-emerald-600 text-white"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      <Car size={21} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h3 className="font-extrabold">
                        Borrowed / Unregistered Vehicle
                      </h3>
                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        Use a borrowed, hired, company, visitor or other vehicle
                        not registered to your account.
                      </p>
                    </div>
                    {vehicleMode === "BORROWED" && (
                      <CheckCircle2
                        className="shrink-0 text-emerald-600"
                        size={20}
                      />
                    )}
                  </div>
                </button>
              </div>

              {vehicleMode === "REGISTERED" ? (
                vehicles.length > 0 ? (
                  <div className="mt-6 grid gap-4">
                    {vehicles.map((vehicle) => {
                      const selected = vehicle.id === vehicleId;

                      return (
                        <button
                          key={vehicle.id}
                          type="button"
                          onClick={() => setVehicleId(vehicle.id)}
                          className={`rounded-2xl border p-5 text-left transition ${
                            selected
                              ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                              : "border-slate-200 hover:border-emerald-300"
                          }`}
                        >
                          <div className="flex items-center gap-4">
                            <div
                              className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl ${
                                selected
                                  ? "bg-emerald-600 text-white"
                                  : "bg-slate-100 text-slate-500"
                              }`}
                            >
                              <Car size={23} />
                            </div>

                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <h3 className="font-extrabold">
                                  {vehicle.registration_number}
                                </h3>

                                {vehicle.is_default && (
                                  <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-emerald-700">
                                    Default
                                  </span>
                                )}
                              </div>

                              <p className="mt-1 text-sm text-slate-500">
                                {vehicle.make} {vehicle.model}
                              </p>

                              <p className="mt-1 text-xs font-bold uppercase tracking-wide text-slate-400">
                                {formatVehicleType(vehicle.vehicle_type)}
                                {vehicle.colour ? ` · ${vehicle.colour}` : ""}
                              </p>
                            </div>

                            {selected && (
                              <CheckCircle2
                                className="shrink-0 text-emerald-600"
                                size={22}
                              />
                            )}
                          </div>
                        </button>
                      );
                    })}
                  </div>
                ) : (
                  <div className="mt-6 rounded-2xl border border-amber-200 bg-amber-50 p-5">
                    <div className="flex items-start gap-3">
                      <Car className="mt-0.5 text-amber-600" size={21} />
                      <div>
                        <h3 className="font-extrabold text-amber-900">
                          No registered vehicle
                        </h3>
                        <p className="mt-1 text-sm text-amber-800">
                          You can switch to Borrowed / Unregistered Vehicle
                          above and continue without registering the vehicle.
                        </p>
                      </div>
                    </div>
                  </div>
                )
              ) : (
                <div className="mt-6 rounded-2xl border border-emerald-200 bg-emerald-50/60 p-5">
                  <div className="mb-5">
                    <h3 className="font-extrabold text-slate-900">
                      Borrowed / Unregistered Vehicle Details
                    </h3>
                    <p className="mt-1 text-sm text-slate-500">
                      Enter the vehicle details exactly as they appear on the
                      vehicle.
                    </p>
                  </div>

                  <div className="grid gap-5 md:grid-cols-2">
                    <Field label="Vehicle registration number">
                      <input
                        type="text"
                        value={borrowedRegistration}
                        onChange={(event) =>
                          setBorrowedRegistration(
                            event.target.value.toUpperCase(),
                          )
                        }
                        placeholder="e.g. KDA123A"
                        maxLength={20}
                        autoComplete="off"
                        className="input w-full uppercase"
                      />
                    </Field>

                    <Field label="Vehicle type">
                      <select
                        value={borrowedVehicleType}
                        onChange={(event) =>
                          setBorrowedVehicleType(event.target.value)
                        }
                        className="input w-full"
                      >
                        {Object.entries(VEHICLE_TYPE_LABELS)
                          .filter(([value]) => value !== "ANY")
                          .map(([value, label]) => (
                            <option key={value} value={value}>
                              {label}
                            </option>
                          ))}
                      </select>
                    </Field>
                  </div>

                  <div className="mt-4 rounded-xl bg-white p-4 text-xs leading-5 text-slate-600 ring-1 ring-emerald-100">
                    This vehicle will be attached to this reservation only. It
                    does not become a registered vehicle in your account.
                  </div>
                </div>
              )}

              <StepActions onBack={previousStep} onNext={nextStep} />
            </StepContainer>
          )}

          {/* ==================================================
              STEP 4 — Review
          ================================================== */}

          {step === 4 && (
            <StepContainer
              title="Review your reservation"
              description="Check everything carefully before creating the reservation."
            >
              <div className="space-y-4">
                <ReviewRow
                  icon={<ParkingCircle size={18} />}
                  label="Facility"
                  value={
                    selectedFacility ? selectedFacility.name : "Not selected"
                  }
                />

                <ReviewRow
                  icon={<MapPin size={18} />}
                  label="Parking zone / level"
                  value={
                    selectedZone
                      ? `${selectedZone.name} · ${selectedZone.code}`
                      : "Not selected"
                  }
                />

                <ReviewRow
                  icon={<MapPin size={18} />}
                  label="Parking bay"
                  value={selectedBay?.bay_number ?? "Not selected"}
                />

                <ReviewRow
                  icon={<Clock3 size={18} />}
                  label="Reservation period"
                  value={
                    reservedFrom && reservedUntil
                      ? `${formatDateTime(
                          localInputToIso(reservedFrom),
                        )} → ${formatDateTime(localInputToIso(reservedUntil))}`
                      : "Not selected"
                  }
                />

                <ReviewRow
                  icon={<Car size={18} />}
                  label="Vehicle"
                  value={
                    vehicleMode === "BORROWED"
                      ? `${borrowedRegistration.trim().toUpperCase()} · ${formatVehicleType(borrowedVehicleType)} · Borrowed / Unregistered`
                      : selectedVehicle
                        ? `${selectedVehicle.registration_number} · ${selectedVehicle.make} ${selectedVehicle.model}`
                        : "Not selected"
                  }
                />

                {notes.trim() && (
                  <ReviewRow
                    icon={<ShieldCheck size={18} />}
                    label="Notes"
                    value={notes.trim()}
                  />
                )}
              </div>

              <div className="mt-6 rounded-2xl bg-slate-50 p-5">
                <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
                  Important
                </p>

                <p className="mt-2 text-sm leading-6 text-slate-600">
                  Creating the reservation does not confirm it. The reservation
                  must be successfully paid before it becomes confirmed.
                </p>
              </div>

              <div className="mt-7 flex flex-col-reverse gap-3 sm:flex-row sm:justify-between">
                <button
                  type="button"
                  onClick={previousStep}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-3 text-sm font-bold text-slate-700 hover:border-slate-300"
                >
                  <ArrowLeft size={16} />
                  Back
                </button>

                <button
                  type="button"
                  onClick={createReservation}
                  disabled={submittingReservation}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-bold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {submittingReservation ? (
                    <>
                      <RefreshCw size={16} className="animate-spin" />
                      Creating reservation...
                    </>
                  ) : (
                    <>
                      Create Reservation
                      <ArrowRight size={16} />
                    </>
                  )}
                </button>
              </div>
            </StepContainer>
          )}

          {/* ==================================================
              STEP 5 — Payment
          ================================================== */}

          {step === 5 && createdReservation && (
            <StepContainer
              title={
                paymentSuccessful
                  ? "Reservation confirmed"
                  : "Complete your payment"
              }
              description={
                paymentSuccessful
                  ? "Your reservation has been successfully paid and confirmed."
                  : "Payment is required before your reservation can be confirmed."
              }
            >
              {!payment && (
                <>
                  <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-5">
                    <div className="flex items-start gap-3">
                      <ShieldCheck
                        className="mt-0.5 shrink-0 text-emerald-600"
                        size={22}
                      />

                      <div>
                        <h3 className="font-extrabold text-emerald-900">
                          Reservation created
                        </h3>

                        <p className="mt-1 text-sm text-emerald-800">
                          Reservation{" "}
                          <strong>
                            {createdReservation.reservation_number}
                          </strong>{" "}
                          has been created and is awaiting payment.
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="mt-6 rounded-2xl bg-slate-50 p-6">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
                          Amount payable
                        </p>

                        <p className="mt-2 text-3xl font-black text-slate-900">
                          {formatMoney(
                            createdReservation.estimated_amount,
                            createdReservation.currency,
                          )}
                        </p>
                      </div>

                      <CreditCard className="text-emerald-600" size={30} />
                    </div>
                  </div>

                  <div className="mt-6">
                    <h3 className="font-extrabold">Select payment method</h3>

                    <div className="mt-3 grid gap-3">
                      {PAYMENT_OPTIONS.map((option) => {
                        const selected = paymentMethod === option.method;

                        return (
                          <button
                            key={option.method}
                            type="button"
                            onClick={() => {
                              setPaymentMethod(option.method);
                              setPaymentProvider(option.provider);

                              if (option.method === "MPESA") {
                                const registeredPhone = normalizeKenyanPhone(
                                  String(user?.phone_number ?? ""),
                                );

                                setMpesaPhone(registeredPhone || mpesaPhone);
                                setUseRegisteredMpesaPhone(
                                  Boolean(registeredPhone),
                                );
                              }
                            }}
                            className={`rounded-2xl border p-4 text-left transition ${
                              selected
                                ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                                : "border-slate-200 hover:border-emerald-300"
                            }`}
                          >
                            <div className="flex items-center gap-3">
                              <div
                                className={`grid h-10 w-10 place-items-center rounded-xl ${
                                  selected
                                    ? "bg-emerald-600 text-white"
                                    : "bg-slate-100 text-slate-500"
                                }`}
                              >
                                <CreditCard size={18} />
                              </div>

                              <div>
                                <p className="font-extrabold">{option.label}</p>

                                <p className="mt-1 text-xs text-slate-500">
                                  {option.description}
                                </p>
                              </div>

                              {selected && (
                                <CheckCircle2
                                  className="ml-auto text-emerald-600"
                                  size={20}
                                />
                              )}
                            </div>
                          </button>
                        );
                      })}
                    </div>

                    {paymentMethod === "MPESA" && (
                      <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50/60 p-5">
                        <div className="mb-4">
                          <h4 className="font-extrabold text-slate-900">
                            M-PESA Payment
                          </h4>
                          <p className="mt-1 text-sm text-slate-600">
                            Enter the M-PESA number you want to use for this
                            payment.
                          </p>
                        </div>

                        <Field label="M-PESA Number">
                          <input
                            type="tel"
                            inputMode="numeric"
                            value={mpesaPhone}
                            onChange={(event) =>
                              setMpesaPhone(event.target.value)
                            }
                            placeholder="254 7XX XXX XXX"
                            autoComplete="tel"
                            disabled={useRegisteredMpesaPhone}
                            className={`input w-full ${
                              useRegisteredMpesaPhone
                                ? "cursor-not-allowed bg-slate-100 text-slate-500"
                                : ""
                            }`}
                          />
                        </Field>

                        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm font-semibold text-slate-700">
                          <input
                            type="checkbox"
                            checked={useRegisteredMpesaPhone}
                            onChange={(event) => {
                              const checked = event.target.checked;
                              setUseRegisteredMpesaPhone(checked);

                              if (checked) {
                                setMpesaPhone(
                                  normalizeKenyanPhone(
                                    String(user?.phone_number ?? ""),
                                  ),
                                );
                              }
                            }}
                            className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
                          />
                          Use my registered phone number
                        </label>

                        {useRegisteredMpesaPhone ? (
                          <p className="mt-2 text-xs text-slate-500">
                            The STK Push will be sent to your registered
                            SmartPark phone number.
                          </p>
                        ) : (
                          <p className="mt-2 text-xs text-slate-500">
                            You can use a different M-PESA number, such as a
                            borrowed phone or another personal line.
                          </p>
                        )}
                      </div>
                    )}
                  </div>

                  <button
                    type="button"
                    onClick={processPayment}
                    disabled={processingPayment}
                    className="mt-7 flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3.5 text-sm font-bold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {processingPayment ? (
                      <>
                        <RefreshCw size={17} className="animate-spin" />
                        Processing payment...
                      </>
                    ) : (
                      <>
                        <CreditCard size={17} />
                        Pay{" "}
                        {formatMoney(
                          createdReservation.estimated_amount,
                          createdReservation.currency,
                        )}
                      </>
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={handlePayLater}
                    disabled={processingPayment || payLaterToastVisible}
                    className="mt-3 flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3.5 text-sm font-bold text-slate-700 hover:border-amber-300 hover:bg-amber-50 hover:text-amber-800 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <Clock3 size={17} />
                    Pay Later
                  </button>
                </>
              )}

              {payment && (
                <div className="space-y-5">
                  <div
                    className={`rounded-2xl p-6 ${
                      paymentSuccessful
                        ? "bg-emerald-50 text-emerald-900"
                        : paymentPending
                          ? "bg-amber-50 text-amber-900"
                          : "bg-rose-50 text-rose-900"
                    }`}
                  >
                    <div className="flex items-start gap-4">
                      {paymentSuccessful ? (
                        <CheckCircle2
                          className="shrink-0 text-emerald-600"
                          size={28}
                        />
                      ) : paymentPending ? (
                        <Clock3 className="shrink-0 text-amber-600" size={28} />
                      ) : (
                        <AlertCircle
                          className="shrink-0 text-rose-600"
                          size={28}
                        />
                      )}

                      <div>
                        <h3 className="text-lg font-extrabold">
                          {paymentSuccessful
                            ? "Payment successful"
                            : paymentPending
                              ? "Payment pending"
                              : "Payment unsuccessful"}
                        </h3>

                        <p className="mt-1 text-sm">
                          {paymentSuccessful
                            ? "Your reservation has been confirmed."
                            : paymentPending
                              ? "Your payment is still being processed. The reservation is not yet confirmed."
                              : "The payment was not completed. Your reservation remains unconfirmed."}
                        </p>
                      </div>
                    </div>
                  </div>

                  <div className="rounded-2xl border border-slate-200 p-5">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <DetailItem
                        label="Reservation"
                        value={createdReservation.reservation_number}
                      />

                      <DetailItem
                        label="Payment status"
                        value={payment.status}
                      />

                      <DetailItem
                        label="Transaction"
                        value={payment.transaction_number}
                      />

                      <DetailItem
                        label="Amount"
                        value={formatMoney(
                          payment.total_amount,
                          payment.currency,
                        )}
                      />

                      {payment.receipt_number && (
                        <DetailItem
                          label="Receipt"
                          value={payment.receipt_number}
                        />
                      )}
                    </div>
                  </div>

                  {paymentPending && (
                    <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4">
                      <div className="flex items-start gap-3">
                        <RefreshCw
                          className="mt-0.5 shrink-0 animate-spin text-amber-600"
                          size={18}
                        />
                        <div>
                          <p className="text-sm font-extrabold text-amber-900">
                            Waiting for payment confirmation
                          </p>
                          <p className="mt-1 text-xs leading-5 text-amber-800">
                            We are checking the payment status automatically.
                            You do not need to refresh the page.
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  <div className="flex flex-col gap-3 sm:flex-row">
                    {paymentSuccessful ? (
                      <button
                        type="button"
                        onClick={() => navigate("/reservations")}
                        className="flex-1 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-bold text-white hover:bg-emerald-700"
                      >
                        View My Reservations
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setPayment(null);
                          setError(null);
                        }}
                        className="flex-1 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-bold text-white hover:bg-emerald-700"
                      >
                        Try Payment Again
                      </button>
                    )}

                    <Link
                      to="/dashboard"
                      className="flex-1 rounded-xl border border-slate-200 px-5 py-3 text-center text-sm font-bold text-slate-700 hover:border-emerald-300"
                    >
                      Return to Dashboard
                    </Link>
                  </div>
                </div>
              )}

              {!payment && (
                <button
                  type="button"
                  onClick={() => setStep(4)}
                  className="mt-4 inline-flex items-center gap-2 text-sm font-bold text-slate-500 hover:text-slate-800"
                >
                  <ArrowLeft size={16} />
                  Back to review
                </button>
              )}
            </StepContainer>
          )}
        </main>

        {/* ==================================================
            Summary
        ================================================== */}

        <aside className="h-fit rounded-3xl bg-white p-6 shadow-sm ring-1 ring-slate-200">
          <h2 className="font-extrabold">Reservation Summary</h2>

          <div className="mt-5 space-y-4">
            <SummaryItem
              label="Facility"
              value={selectedFacility?.name ?? "Not selected"}
            />

            <SummaryItem
              label="Parking zone / level"
              value={
                selectedZone
                  ? `${selectedZone.name} · ${selectedZone.code}`
                  : "Not selected"
              }
            />

            <SummaryItem
              label="Parking bay"
              value={selectedBay?.bay_number ?? "Not selected"}
            />

            <SummaryItem
              label="Vehicle"
              value={
                vehicleMode === "BORROWED"
                  ? `${borrowedRegistration.trim().toUpperCase() || "Not entered"} · ${formatVehicleType(borrowedVehicleType)}`
                  : (selectedVehicle?.registration_number ?? "Not selected")
              }
            />

            <SummaryItem
              label="From"
              value={
                reservedFrom
                  ? formatDateTime(localInputToIso(reservedFrom))
                  : "Not selected"
              }
            />

            <SummaryItem
              label="Until"
              value={
                reservedUntil
                  ? formatDateTime(localInputToIso(reservedUntil))
                  : "Not selected"
              }
            />
          </div>

          {createdReservation && (
            <div className="mt-5 border-t border-slate-100 pt-5">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
                Reservation amount
              </p>

              <p className="mt-2 text-2xl font-black">
                {formatMoney(
                  createdReservation.estimated_amount,
                  createdReservation.currency,
                )}
              </p>

              <p className="mt-1 text-xs text-slate-500">
                Calculated by the SmartPark AI pricing service.
              </p>
            </div>
          )}

          <div className="mt-6 rounded-2xl bg-slate-50 p-4">
            <div className="flex items-start gap-3">
              <ShieldCheck
                className="mt-0.5 shrink-0 text-emerald-600"
                size={18}
              />

              <p className="text-xs leading-5 text-slate-600">
                Your reservation is only confirmed after successful payment.
              </p>
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}

// ==========================================================
// Page Heading
// ==========================================================

function PageHeading() {
  return (
    <div>
      <Link
        to="/reservations"
        className="inline-flex items-center gap-2 text-sm font-bold text-slate-500 hover:text-emerald-700"
      >
        <ArrowLeft size={16} />
        Back to Reservations
      </Link>

      <div className="mt-4 text-xs font-bold uppercase tracking-[.2em] text-emerald-600">
        SmartPark AI
      </div>

      <h1 className="mt-2 text-3xl font-black tracking-tight">
        Create Reservation
      </h1>

      <p className="mt-2 max-w-2xl text-slate-500">
        Reserve a parking space, review the calculated fee and complete payment
        to confirm your reservation.
      </p>
    </div>
  );
}

// ==========================================================
// Step Container
// ==========================================================

function StepContainer({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <div>
        <h2 className="text-2xl font-black">{title}</h2>

        <p className="mt-2 text-sm text-slate-500">{description}</p>
      </div>

      <div className="mt-7">{children}</div>
    </>
  );
}

// ==========================================================
// Step Actions
// ==========================================================

function StepActions({
  onBack,
  onNext,
}: {
  onBack?: () => void;
  onNext: () => void;
}) {
  return (
    <div className="mt-8 flex flex-col-reverse gap-3 border-t border-slate-100 pt-6 sm:flex-row sm:items-center sm:justify-between">
      {onBack ? (
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 px-4 py-3 text-sm font-bold text-slate-700 hover:border-slate-300"
        >
          <ArrowLeft size={16} />
          Back
        </button>
      ) : (
        <span />
      )}

      <button
        type="button"
        onClick={onNext}
        className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-bold text-white hover:bg-emerald-700"
      >
        Continue
        <ArrowRight size={16} />
      </button>
    </div>
  );
}

// ==========================================================
// Field
// ==========================================================

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-2 block text-sm font-bold text-slate-700">
        {label}
      </span>

      {children}
    </label>
  );
}

// ==========================================================
// Inline Warning
// ==========================================================

function InlineWarning({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800">
      {children}
    </div>
  );
}

// ==========================================================
// Review Row
// ==========================================================

function ReviewRow({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-start gap-4 rounded-2xl bg-slate-50 p-4">
      <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-emerald-600 ring-1 ring-slate-200">
        {icon}
      </div>

      <div className="min-w-0">
        <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
          {label}
        </p>

        <p className="mt-1 text-sm font-bold text-slate-800">{value}</p>
      </div>
    </div>
  );
}

// ==========================================================
// Summary Item
// ==========================================================

function SummaryItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
        {label}
      </p>

      <p className="mt-1 text-sm font-bold text-slate-700">{value}</p>
    </div>
  );
}

// ==========================================================
// Detail Item
// ==========================================================

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
        {label}
      </p>

      <p className="mt-1 text-sm font-extrabold text-slate-800">{value}</p>
    </div>
  );
}

// ==========================================================
// Empty State
// ==========================================================

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-2xl bg-slate-50 p-8 text-center">
      <ParkingCircle className="mx-auto text-slate-400" size={30} />

      <p className="mt-3 text-sm text-slate-500">{message}</p>
    </div>
  );
}

// ==========================================================
// Bay response compatibility helper
// ==========================================================

function bayResponseItems(items: ParkingBay[]): ParkingBay[] {
  return Array.isArray(items) ? items : [];
}
