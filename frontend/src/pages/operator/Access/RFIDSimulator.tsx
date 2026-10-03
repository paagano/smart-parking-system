import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowDownToLine,
  ArrowUpFromLine,
  CheckCircle2,
  ChevronDown,
  CircleDot,
  Clock3,
  Cpu,
  Banknote,
  CreditCard,
  Loader2,
  MapPin,
  ParkingCircle,
  Radio,
  RefreshCw,
  ScanLine,
  ShieldCheck,
  Tag,
  XCircle,
} from "lucide-react";

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
  type ParkingReservation,
  type ParkingZone,
} from "../../../api";

// ==========================================================
// RFID Simulator
// ==========================================================
//
// This module simulates a real RFID reader event using the
// persistent SmartPark RFID registry.
//
// RFID identity is UID-only:
//     RFID UID → RFID Tag → Registered Vehicle → Registered Customer
//
// The simulator never accepts a manually entered registration as
// the identity of an RFID vehicle. The backend is authoritative.
//
// Entry supports:
//   1. A registered customer arriving for an applicable reservation.
//   2. A registered customer arriving without a reservation.
//
// Exit supports automatic registered-wallet settlement first, with
// the existing operator M-Pesa STK Push flow as fallback.
//
// No changes are made to the existing ManualEntryExit workflow.
// ==========================================================

type Operation = "ENTRY" | "EXIT";

type VehicleType = "CAR" | "SUV" | "TRUCK" | "MOTORCYCLE" | "BUS";

type BillingType = "HOURLY" | "DAILY" | "FLAT_RATE";

interface RfidDetection {
  tagUid: string;
  registration: string;
  vehicleId: number;
  customerId: number;
  vehicleType: VehicleType;
  detectedAt: string;
  signalStrength: number;
  readerId: string;
}

interface RfidReaderEvent {
  event_id: string;
  event_type: "TAG_DETECTED";
  tag_uid: string;
  reader_id: string;
  registration: string;
  signal_strength: number;
  detected_at: string;
}

interface RfidScanResponse {
  rfid_tag: {
    id: number;
    uid: string;
    vehicle_id: number | null;
    is_active: boolean;
    vehicle?: unknown;
  };
  vehicle_id: number;
  registration_number: string;
  vehicle_type: VehicleType;
  customer_id: number;
  customer_name: string;
}

interface RfidCheckoutResponse {
  parking_session_id: number;
  vehicle_id: number;
  registration_number: string;
  customer_id: number | null;
  current_bill: number | string;
  wallet_balance: number | string | null;
  wallet_sufficient: boolean;
  payment_required: boolean;
  wallet_payment_successful: boolean;
  payment_transaction_id: number | null;
  payment_reference: string | null;
  checkout_completed: boolean;
  message: string;
}

type ExitPaymentMethod = "MPESA" | "CASH";

interface OperatorStkPayment {
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
}

function normalizeTagUid(value: string): string {
  return value
    .replace(/[^A-Fa-f0-9:-]/g, "")
    .toUpperCase()
    .replace(/:+/g, ":")
    .slice(0, 32);
}

function isActiveSession(session: ParkingSession): boolean {
  return String(session.status ?? "").toUpperCase() === "ACTIVE";
}

function isCompletedAwaitingExit(session: ParkingSession): boolean {
  return (
    String(session.status ?? "").toUpperCase() === "COMPLETED" &&
    !session.exit_time
  );
}

function asNumber(value: number | string | null | undefined): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatCurrency(
  amount: number | string | null | undefined,
  currency = "KES",
): string {
  const numeric = asNumber(amount);

  return new Intl.NumberFormat("en-KE", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(numeric);
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-KE", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function formatDuration(
  session: ParkingSession | null,
  now = Date.now(),
): string {
  if (!session?.entry_time) {
    return "—";
  }

  const start = new Date(session.entry_time).getTime();

  if (!Number.isFinite(start)) {
    return "—";
  }

  const end = isActiveSession(session)
    ? now
    : session.exit_time
      ? new Date(session.exit_time).getTime()
      : now;

  if (!Number.isFinite(end)) {
    return "—";
  }

  const minutes = Math.max(0, Math.floor((end - start) / 60000));
  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;

  if (hours === 0) {
    return `${remaining} min`;
  }

  if (remaining === 0) {
    return `${hours} hr${hours === 1 ? "" : "s"}`;
  }

  return `${hours} hr${hours === 1 ? "" : "s"} ${remaining} min`;
}

function createEventId(): string {
  return `RFID-${Date.now().toString(36).toUpperCase()}-${Math.random()
    .toString(36)
    .slice(2, 8)
    .toUpperCase()}`;
}

function getFirstAvailableBay(
  bays: ParkingBay[],
  activeSessions: ParkingSession[],
): ParkingBay | null {
  const occupiedBayIds = new Set(
    activeSessions
      .filter(isActiveSession)
      .map((session) => session.parking_bay_id),
  );

  return (
    bays.find((bay) => bay.is_active && !occupiedBayIds.has(bay.id)) ?? null
  );
}

export default function RFIDSimulator() {
  const { user } = useAuth();

  const facilityId = user?.facility_id ?? null;

  const [facility, setFacility] = useState<ParkingFacility | null>(null);
  const [zones, setZones] = useState<ParkingZone[]>([]);
  const [bays, setBays] = useState<ParkingBay[]>([]);
  const [activeSessions, setActiveSessions] = useState<ParkingSession[]>([]);

  const [operation, setOperation] = useState<Operation>("ENTRY");

  const [tagUid, setTagUid] = useState("");
  const [vehicleType, setVehicleType] = useState<VehicleType>("CAR");
  const [billingType, setBillingType] = useState<BillingType>("HOURLY");

  const [selectedBayId, setSelectedBayId] = useState("");
  const [readerId, setReaderId] = useState("RFID-GATE-01");

  const [detection, setDetection] = useState<RfidDetection | null>(null);
  const [readerEvent, setReaderEvent] = useState<RfidReaderEvent | null>(null);
  const [locatedSession, setLocatedSession] = useState<ParkingSession | null>(
    null,
  );
  const [completedSession, setCompletedSession] =
    useState<ParkingSession | null>(null);

  const [reservationForDetectedVehicle, setReservationForDetectedVehicle] =
    useState<ParkingReservation | null>(null);
  const [reservationLookupInProgress, setReservationLookupInProgress] =
    useState(false);

  const [rfidPaymentQuote, setRfidPaymentQuote] =
    useState<RfidCheckoutResponse | null>(null);
  const [exitPaymentMethod, setExitPaymentMethod] =
    useState<ExitPaymentMethod>("MPESA");
  const [mpesaTarget, setMpesaTarget] = useState<"REGISTERED" | "OTHER">(
    "REGISTERED",
  );
  const [alternativeMpesaNumber, setAlternativeMpesaNumber] = useState("");
  const [stkPayment, setStkPayment] = useState<OperatorStkPayment | null>(null);
  const [stkInitiating, setStkInitiating] = useState(false);
  const [stkPolling, setStkPolling] = useState(false);
  const [cashProcessing, setCashProcessing] = useState(false);
  const [cashPaymentRecorded, setCashPaymentRecorded] = useState(false);

  const [now, setNow] = useState(() => Date.now());

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Automatic RFID entry countdown.
  // Once a tag is detected, the simulator gives the operator 60 seconds
  // to make any entry configuration change. If no change is made, the
  // backend RFID check-in is submitted automatically.
  const [autoEntryCountdown, setAutoEntryCountdown] = useState<number | null>(
    null,
  );
  const [autoEntryCancelled, setAutoEntryCancelled] = useState(false);
  const handleEntryRef = useRef<(() => Promise<void>) | null>(null);

  // --------------------------------------------------------
  // Load facility-scoped operator data
  // --------------------------------------------------------

  const loadFacilityData = useCallback(
    async (silent = false, suppressError = false) => {
      if (!facilityId) {
        setLoading(false);
        setRefreshing(false);
        setError(
          "Your operator account is not assigned to a parking facility.",
        );
        return;
      }

      if (silent) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      setError(null);

      try {
        const [facilityData, zoneData, bayData, sessionData] =
          await Promise.all([
            parkingFacilitiesApi.get(facilityId),
            parkingZonesApi.byFacility(facilityId),
            parkingBaysApi.list(),
            parkingSessionsApi.active(),
          ]);

        const facilityBays = (bayData.items ?? []).filter((bay) =>
          zoneData.items.some(
            (zone) =>
              zone.id === bay.zone_id && zone.facility_id === facilityId,
          ),
        );

        setFacility(facilityData);
        setZones(zoneData.items ?? []);
        setBays(facilityBays);
        setActiveSessions(sessionData.items ?? []);

        setSelectedBayId((current) => {
          if (
            current &&
            facilityBays.some((bay) => bay.id === Number(current))
          ) {
            return current;
          }

          const firstAvailable = getFirstAvailableBay(
            facilityBays,
            sessionData.items ?? [],
          );

          return firstAvailable ? String(firstAvailable.id) : "";
        });
      } catch (loadError) {
        if (!suppressError) {
          setError(getApiErrorMessage(loadError));
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [facilityId],
  );

  useEffect(() => {
    void loadFacilityData();
  }, [loadFacilityData]);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setNow(Date.now());
    }, 10000);

    return () => window.clearInterval(interval);
  }, []);

  // --------------------------------------------------------
  // Derived facility state
  // --------------------------------------------------------

  const occupiedBayIds = useMemo(
    () =>
      new Set(
        activeSessions
          .filter(isActiveSession)
          .map((session) => session.parking_bay_id),
      ),
    [activeSessions],
  );

  const availableBays = useMemo(
    () => bays.filter((bay) => bay.is_active && !occupiedBayIds.has(bay.id)),
    [bays, occupiedBayIds],
  );

  const availableBaysByZone = useMemo(() => {
    return zones
      .map((zone) => ({
        zone,
        bays: availableBays.filter((bay) => bay.zone_id === zone.id),
      }))
      .filter((group) => group.bays.length > 0);
  }, [zones, availableBays]);

  const selectedBay = useMemo(
    () => bays.find((bay) => bay.id === Number(selectedBayId)) ?? null,
    [bays, selectedBayId],
  );

  const selectedZone = useMemo(
    () =>
      selectedBay
        ? (zones.find((zone) => zone.id === selectedBay.zone_id) ?? null)
        : null,
    [selectedBay, zones],
  );

  const effectiveRegistration = detection?.registration ?? "";

  const activeSessionForDetectedVehicle = useMemo(() => {
    if (!detection?.vehicleId) {
      return null;
    }

    return (
      activeSessions.find(
        (session) =>
          session.vehicle_id === detection.vehicleId &&
          isActiveSession(session),
      ) ?? null
    );
  }, [activeSessions, detection?.vehicleId]);

  // --------------------------------------------------------
  // Reset current RFID event
  // --------------------------------------------------------

  const resetEvent = () => {
    setDetection(null);
    setReaderEvent(null);
    setLocatedSession(null);
    setCompletedSession(null);
    setReservationForDetectedVehicle(null);
    setReservationLookupInProgress(false);
    setRfidPaymentQuote(null);
    setStkPayment(null);
    setStkPolling(false);
    setCashPaymentRecorded(false);
    setExitPaymentMethod("MPESA");
    setAutoEntryCountdown(null);
    setAutoEntryCancelled(false);
    setError(null);
    setSuccess(null);
  };

  // --------------------------------------------------------
  // Simulate RFID reader detection
  // --------------------------------------------------------

  const handleScan = async () => {
    const normalizedTag = normalizeTagUid(tagUid);

    if (!normalizedTag) {
      setError("Enter a registered RFID tag UID before scanning.");
      return;
    }

    setScanning(true);
    setError(null);
    setSuccess(null);
    setDetection(null);
    setReaderEvent(null);
    setLocatedSession(null);
    setCompletedSession(null);
    setReservationForDetectedVehicle(null);
    setReservationLookupInProgress(false);
    setRfidPaymentQuote(null);
    setStkPayment(null);
    setCashPaymentRecorded(false);
    setExitPaymentMethod("MPESA");
    setAutoEntryCountdown(null);
    setAutoEntryCancelled(false);

    try {
      // Simulate the short physical RFID-reader acquisition delay.
      await new Promise((resolve) => window.setTimeout(resolve, 700));

      const scanResponse = await api.post<RfidScanResponse>("/rfid-tags/scan", {
        uid: normalizedTag,
      });

      const data = scanResponse.data;
      const detectedAt = new Date().toISOString();
      const signalStrength = 88 + Math.floor(Math.random() * 11);
      const effectiveReaderId = readerId.trim() || "RFID-GATE-01";

      const detected: RfidDetection = {
        tagUid: normalizedTag,
        registration: data.registration_number,
        vehicleId: data.vehicle_id,
        customerId: data.customer_id,
        vehicleType: data.vehicle_type,
        detectedAt,
        signalStrength,
        readerId: effectiveReaderId,
      };

      const event: RfidReaderEvent = {
        event_id: createEventId(),
        event_type: "TAG_DETECTED",
        tag_uid: normalizedTag,
        reader_id: effectiveReaderId,
        registration: data.registration_number,
        signal_strength: signalStrength,
        detected_at: detectedAt,
      };

      setTagUid(normalizedTag);
      setVehicleType(data.vehicle_type);
      setDetection(detected);
      setReaderEvent(event);

      if (operation === "ENTRY") {
        const firstAvailable = getFirstAvailableBay(bays, activeSessions);

        const existingActive =
          activeSessions.find(
            (session) =>
              session.vehicle_id === data.vehicle_id &&
              isActiveSession(session),
          ) ?? null;

        if (existingActive) {
          setError(
            `Vehicle ${data.registration_number} already has an active parking session (${existingActive.session_number}).`,
          );
        } else if (!firstAvailable) {
          setError(
            "No available parking bay is currently available at the assigned facility.",
          );
        } else {
          setReservationLookupInProgress(true);

          try {
            const reservationResponse = await api.get<{
              items: ParkingReservation[];
              total: number;
            }>("/parking-reservations/search", {
              params: {
                search_term: data.registration_number,
              },
            });

            const nowMs = Date.now();
            const applicableReservation = (
              reservationResponse.data.items ?? []
            ).find((reservation) => {
              const status = String(reservation.status ?? "").toUpperCase();
              const reservedFrom = new Date(
                reservation.reserved_from,
              ).getTime();
              const reservedUntil = new Date(
                reservation.reserved_until,
              ).getTime();

              const reservedBay = bays.find(
                (bay) => bay.id === reservation.parking_bay_id,
              );

              const belongsToFacility = Boolean(
                reservedBay &&
                zones.some(
                  (zone) =>
                    zone.id === reservedBay.zone_id &&
                    zone.facility_id === facilityId,
                ),
              );

              return (
                reservation.vehicle_id === data.vehicle_id &&
                (status === "CREATED" || status === "CONFIRMED") &&
                !reservation.checked_in_at &&
                reservation.is_active &&
                nowMs >= reservedFrom - 30 * 60 * 1000 &&
                nowMs < reservedUntil &&
                belongsToFacility
              );
            });

            if (applicableReservation) {
              setReservationForDetectedVehicle(applicableReservation);

              const reservedBay = bays.find(
                (bay) => bay.id === applicableReservation.parking_bay_id,
              );

              if (reservedBay) {
                setSelectedBayId(String(reservedBay.id));
                setSuccess(
                  `RFID tag resolved successfully. Registered vehicle ${data.registration_number} belongs to ${data.customer_name}. Active reservation ${applicableReservation.reservation_number} detected; its reserved bay ${reservedBay.bay_number ?? reservedBay.code ?? `#${reservedBay.id}`} has been selected automatically.`,
                );
              } else {
                setSelectedBayId(String(firstAvailable.id));
                setError(
                  `A valid reservation was found for ${data.registration_number}, but its reserved bay could not be found in the assigned facility. Select an available bay before check-in.`,
                );
              }
            } else {
              setReservationForDetectedVehicle(null);
              setSelectedBayId(String(firstAvailable.id));
              setSuccess(
                `RFID tag resolved successfully. Registered vehicle ${data.registration_number} belongs to ${data.customer_name}. No applicable reservation was found; the next available bay has been selected.`,
              );
            }
          } catch (reservationError) {
            // RFID check-in remains backend-authoritative. If the optional
            // reservation lookup fails, keep the normal drive-in bay selection
            // available and let the check-in endpoint determine the final
            // reservation state.
            setReservationForDetectedVehicle(null);
            setSelectedBayId(String(firstAvailable.id));
            setSuccess(
              `RFID tag resolved successfully. Registered vehicle ${data.registration_number} belongs to ${data.customer_name}.`,
            );
          } finally {
            setReservationLookupInProgress(false);
          }
        }
      } else {
        setSuccess(
          `RFID tag resolved to registered vehicle ${data.registration_number}.`,
        );
        await locateExitSession(detected);
      }
    } catch (scanError) {
      setError(getApiErrorMessage(scanError));
    } finally {
      setScanning(false);
    }
  };

  // --------------------------------------------------------
  // Locate exit session
  // --------------------------------------------------------

  const locateExitSession = useCallback(
    async (targetDetection: RfidDetection) => {
      const exitDetection = targetDetection ?? detection;

      if (!exitDetection) {
        return;
      }

      setSubmitting(true);
      setError(null);
      setSuccess(null);

      try {
        const response = await parkingSessionsApi.vehicleHistory(
          exitDetection.registration,
        );

        const sessions = response.items ?? [];

        const active =
          sessions.find(
            (session) =>
              session.vehicle_id === exitDetection.vehicleId &&
              isActiveSession(session),
          ) ?? null;

        const completedAwaitingExit =
          sessions.find(
            (session) =>
              session.vehicle_id === exitDetection.vehicleId &&
              isCompletedAwaitingExit(session),
          ) ?? null;

        const located = completedAwaitingExit ?? active;

        if (!located) {
          setLocatedSession(null);
          setCompletedSession(null);
          setError(
            `No pending parking session was found for registered vehicle ${exitDetection.registration}.`,
          );
          return;
        }

        setLocatedSession(located);

        if (isCompletedAwaitingExit(located)) {
          setCompletedSession(located);
          setSuccess(
            `RFID exit detected for ${exitDetection.registration}. Session ${located.session_number} is already paid and awaiting physical checkout.`,
          );
          return;
        }

        setCompletedSession(null);
        setSuccess(
          `RFID exit detected for ${exitDetection.registration}. Current parking session ${located.session_number} is ACTIVE. RFID checkout will first attempt wallet payment.`,
        );
      } catch (lookupError) {
        setError(getApiErrorMessage(lookupError));
        setLocatedSession(null);
        setCompletedSession(null);
      } finally {
        setSubmitting(false);
      }
    },
    [detection],
  );

  // --------------------------------------------------------
  // Entry
  // --------------------------------------------------------

  const handleEntry = async () => {
    if (!detection) {
      setError("Scan an RFID tag before creating the parking session.");
      return;
    }

    if (!selectedBayId) {
      setError("No available parking bay is selected.");
      return;
    }

    if (activeSessionForDetectedVehicle) {
      setError(
        `Vehicle ${detection.registration} already has an active parking session (${activeSessionForDetectedVehicle.session_number}).`,
      );
      return;
    }

    setAutoEntryCancelled(true);
    setAutoEntryCountdown(null);
    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await api.post<ParkingSession>("/rfid-tags/check-in", {
        uid: detection.tagUid,
        parking_bay_id: Number(selectedBayId),
        billing_type: billingType,
        expected_exit_time: null,
        notes: `RFID automated access simulation · Tag ${detection.tagUid} · Reader ${detection.readerId}`,
      });

      setActiveSessions((current) => [...current, response.data]);

      const reservationMessage = response.data.reservation_id
        ? ` Reservation ${response.data.reservation_id} was checked in.`
        : " No prior reservation was used; this is a registered-user drive-in session.";

      setSuccess(
        `RFID entry accepted. ${response.data.vehicle_registration} was checked in successfully. Parking session ${response.data.session_number} is now ACTIVE.${reservationMessage}`,
      );

      setSelectedBayId("");
      await loadFacilityData(true);
    } catch (entryError) {
      setError(getApiErrorMessage(entryError));
    } finally {
      setSubmitting(false);
    }
  };

  // Keep the latest entry handler available to the countdown without
  // making the countdown restart every time the handler is recreated.
  handleEntryRef.current = handleEntry;

  // --------------------------------------------------------
  // Automatic RFID entry
  // --------------------------------------------------------
  //
  // After a successful RFID scan, the operator has 60 seconds to make
  // an entry configuration change. If no change is made, the simulator
  // automatically submits the normal RFID check-in request.
  //
  // Vehicle type is intentionally not operator-editable because RFID
  // resolves it from the registered vehicle. Billing type is the
  // operator-editable entry setting and changing it cancels automation.
  // --------------------------------------------------------

  useEffect(() => {
    if (
      operation !== "ENTRY" ||
      !detection ||
      !selectedBayId ||
      activeSessionForDetectedVehicle ||
      reservationLookupInProgress ||
      autoEntryCancelled
    ) {
      setAutoEntryCountdown(null);
      return;
    }

    let remaining = 60;
    let cancelled = false;

    setAutoEntryCountdown(remaining);

    const intervalId = window.setInterval(() => {
      if (cancelled) {
        return;
      }

      remaining -= 1;
      setAutoEntryCountdown(Math.max(remaining, 0));

      if (remaining <= 0) {
        window.clearInterval(intervalId);

        if (!cancelled) {
          setAutoEntryCountdown(null);
          void handleEntryRef.current?.();
        }
      }
    }, 1000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [
    operation,
    detection?.tagUid,
    selectedBayId,
    activeSessionForDetectedVehicle?.id,
    reservationLookupInProgress,
    autoEntryCancelled,
  ]);

  // --------------------------------------------------------
  // RFID checkout
  // --------------------------------------------------------

  const handlePhysicalExit = async () => {
    if (!detection) {
      setError("Detect a registered RFID vehicle at the exit first.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);
    setRfidPaymentQuote(null);

    try {
      const response = await api.post<RfidCheckoutResponse>(
        "/rfid-tags/check-out",
        {
          uid: detection.tagUid,
          notes: `RFID automated physical exit · Tag ${detection.tagUid} · Reader ${detection.readerId}`,
        },
      );

      const data = response.data;

      if (data.checkout_completed) {
        setSuccess(
          `${data.message} Vehicle ${data.registration_number} exited successfully.`,
        );
        setLocatedSession(null);
        setCompletedSession(null);
        setRfidPaymentQuote(null);
        setStkPayment(null);
        setCashPaymentRecorded(false);
        setExitPaymentMethod("MPESA");
        setDetection(null);
        setReaderEvent(null);
        setTagUid("");
        await loadFacilityData(true, true);
        return;
      }

      if (data.payment_required) {
        setRfidPaymentQuote(data);
        setExitPaymentMethod("MPESA");
        setCashPaymentRecorded(false);
        setLocatedSession(
          (current) =>
            current ??
            ({
              id: data.parking_session_id,
              vehicle_id: data.vehicle_id,
              vehicle_registration: data.registration_number,
              customer_id: data.customer_id,
            } as ParkingSession),
        );
        setSuccess(
          `Wallet payment could not be completed automatically. ${data.message}`,
        );
        return;
      }

      setSuccess(data.message);
    } catch (exitError) {
      setError(getApiErrorMessage(exitError));
    } finally {
      setSubmitting(false);
    }
  };

  const initiateMpesaPayment = async () => {
    if (!rfidPaymentQuote) {
      setError(
        "First detect the RFID vehicle and obtain the current parking bill.",
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
      const response = await api.post<OperatorStkPayment>(
        "/payments/operator/session/stk-push",
        {
          parking_session_id: rfidPaymentQuote.parking_session_id,
          use_registered_number: mpesaTarget === "REGISTERED",
          mobile_number:
            mpesaTarget === "OTHER" ? alternativeMpesaNumber.trim() : null,
          notes: "RFID checkout M-Pesa fallback",
        },
      );

      const data = response.data;
      setStkPayment(data);

      if (String(data.status).toUpperCase() === "SUCCESSFUL") {
        setSuccess(
          `M-Pesa payment ${data.transaction_number} was completed successfully. Retry RFID checkout to complete the physical exit.`,
        );
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

  const recordOperatorCashPayment = async () => {
    if (!rfidPaymentQuote) {
      setError(
        "First detect the RFID vehicle and obtain the current parking bill.",
      );
      return;
    }

    if (!rfidPaymentQuote.payment_required) {
      setError("No external payment is required for this RFID checkout.");
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
        parking_session_id: rfidPaymentQuote.parking_session_id,
        notes: "RFID operator-recorded cash settlement",
      });

      const data = response.data;

      setCashPaymentRecorded(true);

      setSuccess(
        `Cash payment ${data.transaction_number} of ${formatCurrency(
          data.amount,
          data.currency || "KES",
        )} recorded successfully. Retry RFID checkout to complete the physical exit.`,
      );
    } catch (paymentError) {
      setError(getApiErrorMessage(paymentError));
    } finally {
      setCashProcessing(false);
    }
  };

  const retryRfidCheckoutAfterPayment = async () => {
    if (!detection) {
      setError(
        "The RFID tag is no longer available. Scan the registered RFID tag again.",
      );
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await api.post<RfidCheckoutResponse>(
        "/rfid-tags/check-out",
        {
          uid: detection.tagUid,
          notes: `RFID checkout after M-Pesa payment · Tag ${detection.tagUid} · Reader ${detection.readerId}`,
        },
      );

      const data = response.data;

      if (!data.checkout_completed) {
        setRfidPaymentQuote(data);
        setError(data.message);
        return;
      }

      setSuccess(
        `${data.message} Vehicle ${data.registration_number} exited successfully.`,
      );
      setRfidPaymentQuote(null);
      setStkPayment(null);
      setCashPaymentRecorded(false);
      setLocatedSession(null);
      setCompletedSession(null);
      setDetection(null);
      setReaderEvent(null);
      setTagUid("");
      await loadFacilityData(true, true);
    } catch (checkoutError) {
      setError(getApiErrorMessage(checkoutError));
    } finally {
      setSubmitting(false);
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
            "M-Pesa payment received successfully. Retry RFID checkout to complete the physical exit.",
          );
        } else if (["FAILED", "CANCELLED"].includes(status)) {
          if (intervalId !== undefined) {
            window.clearInterval(intervalId);
          }

          setStkPolling(false);
          setError(
            response.data.provider_status_message ||
              `M-Pesa payment ${status.toLowerCase()}.`,
          );
        }
      } catch (pollError) {
        if (!cancelled) {
          setStkPolling(false);
          setError(getApiErrorMessage(pollError));
        }

        if (intervalId !== undefined) {
          window.clearInterval(intervalId);
        }
      }
    };

    setStkPolling(true);
    void pollPayment();

    intervalId = window.setInterval(() => {
      void pollPayment();
    }, 3000);

    return () => {
      cancelled = true;
      if (intervalId !== undefined) {
        window.clearInterval(intervalId);
      }
    };
  }, [stkPayment?.payment_id]);

  const handleBaySelectionChange = (bayId: string) => {
    setSelectedBayId(bayId);

    if (detection) {
      setAutoEntryCancelled(true);
      setAutoEntryCountdown(null);

      const selected = bays.find((bay) => bay.id === Number(bayId));
      const selectedLabel = selected
        ? selected.bay_number || selected.code || `#${selected.id}`
        : bayId;

      setSuccess(
        reservationForDetectedVehicle
          ? `Parking bay changed to ${selectedLabel}. The reservation remains associated with the RFID check-in; automatic check-in has been cancelled.`
          : `Parking bay changed to ${selectedLabel}. Automatic RFID check-in has been cancelled; use the button below when ready.`,
      );
    }
  };

  const handleOperationChange = (next: Operation) => {
    setOperation(next);
    resetEvent();

    if (next === "ENTRY") {
      setSelectedBayId((current) => {
        if (
          current &&
          availableBays.some((bay) => bay.id === Number(current))
        ) {
          return current;
        }

        return availableBays[0] ? String(availableBays[0].id) : "";
      });
    }
  };

  const entryReady =
    operation === "ENTRY" &&
    Boolean(detection) &&
    Boolean(selectedBayId) &&
    !activeSessionForDetectedVehicle &&
    !reservationLookupInProgress;

  const exitReady = operation === "EXIT" && Boolean(detection);

  const exitNeedsPayment =
    operation === "EXIT" && Boolean(rfidPaymentQuote?.payment_required);

  const walletPaymentReady =
    Boolean(rfidPaymentQuote) && !rfidPaymentQuote?.wallet_sufficient;

  return (
    <div className="space-y-5">
      {/* ====================================================
          Header
      ==================================================== */}
      <div>
        <div className="text-xs font-bold uppercase tracking-[.2em] text-emerald-600">
          SmartPark AI · Operations
        </div>

        <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-3xl font-black tracking-tight text-slate-950">
              RFID Simulator
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-500">
              Simulate registered RFID vehicle identification and access events
              using the facility-scoped operator workflow.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void loadFacilityData(true)}
            disabled={loading || refreshing}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-xs font-bold text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* ====================================================
          Facility banner
      ==================================================== */}
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
              Facility #{facilityId ?? "—"} · RFID-controlled access
            </p>
          </div>
        </div>

        <div className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-[10px] font-black uppercase tracking-wider text-emerald-700 shadow-sm">
          <CircleDot size={12} />
          Reader simulation online
        </div>
      </div>

      {/* ====================================================
          Alerts
      ==================================================== */}
      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-extrabold">
              RFID operation could not be completed
            </p>
            <p className="mt-1 leading-5">{error}</p>
          </div>
        </div>
      )}

      {success && (
        <div className="flex items-start gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
          <CheckCircle2 size={18} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-extrabold">RFID operation successful</p>
            <p className="mt-1 leading-5">{success}</p>
          </div>
        </div>
      )}

      {/* ====================================================
          Main workspace
      ==================================================== */}
      <div className="grid gap-5 xl:grid-cols-[1.15fr_.85fr]">
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-start gap-3">
              <span className="grid h-11 w-11 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
                <Radio size={21} />
              </span>

              <div>
                <h2 className="text-sm font-black text-slate-900">
                  RFID Reader Event
                </h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Simulate a vehicle tag being detected at an RFID access gate.
                </p>
              </div>
            </div>

            <div className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-[10px] font-black uppercase tracking-wider text-slate-600">
              <Cpu size={13} />
              {readerId || "RFID-GATE-01"}
            </div>
          </div>

          {/* Operation */}
          <div className="mt-5 grid grid-cols-2 gap-2 rounded-2xl bg-slate-100 p-1">
            <button
              type="button"
              onClick={() => handleOperationChange("ENTRY")}
              className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-black transition ${
                operation === "ENTRY"
                  ? "bg-white text-emerald-700 shadow-sm"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              <ArrowDownToLine size={16} />
              Entry
            </button>

            <button
              type="button"
              onClick={() => handleOperationChange("EXIT")}
              className={`inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2.5 text-sm font-black transition ${
                operation === "EXIT"
                  ? "bg-white text-emerald-700 shadow-sm"
                  : "text-slate-500 hover:text-slate-800"
              }`}
            >
              <ArrowUpFromLine size={16} />
              Exit
            </button>
          </div>

          {/* RFID inputs */}
          <div className="mt-5 grid gap-4 sm:grid-cols-[1fr_auto]">
            <label className="block">
              <span className="text-[10px] font-black uppercase tracking-wider text-slate-400">
                RFID Tag UID
              </span>

              <div className="mt-1.5 flex gap-2">
                <input
                  value={tagUid}
                  onChange={(event) => {
                    setTagUid(normalizeTagUid(event.target.value));
                    setError(null);
                  }}
                  placeholder="e.g. 04:A7:9C:21:6F:80:12"
                  className="min-w-0 flex-1 rounded-xl border border-slate-200 bg-white px-3.5 py-3 font-mono text-sm font-bold text-slate-900 outline-none transition placeholder:text-slate-300 focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                />

                <span className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2 text-xs font-black text-slate-500">
                  <Tag size={15} />
                  Registered UID only
                </span>
              </div>
            </label>

            <label className="block">
              <span className="text-[10px] font-black uppercase tracking-wider text-slate-400">
                Reader
              </span>

              <select
                value={readerId}
                onChange={(event) => setReaderId(event.target.value)}
                className="mt-1.5 min-w-[180px] rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm font-bold text-slate-800 outline-none focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
              >
                <option value="RFID-GATE-01">RFID-GATE-01 · Entry</option>
                <option value="RFID-GATE-02">RFID-GATE-02 · Exit</option>
                <option value="RFID-GATE-03">RFID-GATE-03 · Auxiliary</option>
              </select>
            </label>
          </div>

          {/* Vehicle identity */}
          <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-start gap-3">
              <ShieldCheck
                size={17}
                className="mt-0.5 shrink-0 text-emerald-600"
              />
              <div>
                <p className="text-[10px] font-black uppercase tracking-wider text-slate-400">
                  Registered Vehicle Identity
                </p>
                <p className="mt-1 text-sm font-black text-slate-900">
                  {effectiveRegistration || "Awaiting RFID scan"}
                </p>
                <p className="mt-1 text-[10px] leading-4 text-slate-500">
                  Vehicle registration, vehicle type and registered customer are
                  resolved exclusively by the RFID registry. Manual registration
                  entry is not permitted.
                </p>
              </div>
            </div>
          </div>

          <button
            type="button"
            onClick={() => void handleScan()}
            disabled={loading || scanning || !tagUid}
            className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-950 px-5 py-3.5 text-sm font-black text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {scanning ? (
              <>
                <Loader2 size={17} className="animate-spin" />
                Reading RFID Tag…
              </>
            ) : (
              <>
                <ScanLine size={17} />
                Scan RFID Tag
              </>
            )}
          </button>

          {/* Detected event */}
          {detection && (
            <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50/60 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <span className="grid h-9 w-9 place-items-center rounded-xl bg-white text-emerald-600 shadow-sm">
                    <Radio size={17} />
                  </span>

                  <div>
                    <p className="text-[10px] font-black uppercase tracking-wider text-emerald-700">
                      RFID Tag Detected
                    </p>

                    <p className="mt-1 font-mono text-sm font-black text-slate-900">
                      {detection.tagUid}
                    </p>

                    <p className="mt-1 text-xs text-slate-500">
                      Vehicle{" "}
                      <span className="font-black text-slate-800">
                        {detection.registration}
                      </span>{" "}
                      · {detection.readerId}
                    </p>
                  </div>
                </div>

                <span className="rounded-full bg-emerald-100 px-2.5 py-1 text-[10px] font-black text-emerald-700">
                  {detection.signalStrength}% signal
                </span>
              </div>

              <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
                <div className="rounded-xl bg-white/80 p-3">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Detected
                  </p>
                  <p className="mt-1 font-bold text-slate-700">
                    {formatDateTime(detection.detectedAt)}
                  </p>
                </div>

                <div className="rounded-xl bg-white/80 p-3">
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Event ID
                  </p>
                  <p className="mt-1 truncate font-mono font-bold text-slate-700">
                    {readerEvent?.event_id ?? "—"}
                  </p>
                </div>
              </div>
            </div>
          )}
        </section>

        {/* ==================================================
            Configuration / action panel
        ================================================== */}
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          {operation === "ENTRY" ? (
            <>
              <div className="flex items-start gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-2xl bg-blue-50 text-blue-600">
                  <ArrowDownToLine size={20} />
                </span>

                <div>
                  <h2 className="text-sm font-black text-slate-900">
                    Entry Configuration
                  </h2>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    A valid reservation uses its reserved bay automatically. The
                    operator can change the bay before check-in if required.
                  </p>
                </div>
              </div>

              <div className="mt-5 grid gap-4 sm:grid-cols-2">
                <div className="rounded-xl border border-slate-200 bg-slate-50 px-3 py-3">
                  <span className="text-[10px] font-black uppercase tracking-wider text-slate-400">
                    Vehicle Type
                  </span>
                  <p className="mt-1 text-sm font-bold text-slate-800">
                    {detection?.vehicleType ?? "Awaiting RFID scan"}
                  </p>
                  <p className="mt-1 text-[10px] text-slate-400">
                    Resolved from the registered vehicle.
                  </p>
                </div>

                <label>
                  <span className="text-[10px] font-black uppercase tracking-wider text-slate-400">
                    Billing Type
                  </span>

                  <select
                    value={billingType}
                    onChange={(event) => {
                      setBillingType(event.target.value as BillingType);

                      if (detection) {
                        setAutoEntryCancelled(true);
                        setAutoEntryCountdown(null);
                        setSuccess(
                          "Billing type changed. Automatic RFID check-in has been cancelled; use the button below to check in when ready.",
                        );
                      }
                    }}
                    className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-bold text-slate-800 outline-none focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                  >
                    <option value="HOURLY">Hourly</option>
                    <option value="DAILY">Daily</option>
                    <option value="FLAT_RATE">Flat Rate</option>
                  </select>
                </label>
              </div>

              {reservationForDetectedVehicle && (
                <div className="mt-4 rounded-2xl border border-emerald-200 bg-emerald-50 p-4">
                  <div className="flex items-start gap-3">
                    <ShieldCheck
                      size={17}
                      className="mt-0.5 shrink-0 text-emerald-600"
                    />
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-wider text-emerald-700">
                        Reservation Detected
                      </p>
                      <p className="mt-1 text-sm font-black text-slate-900">
                        {reservationForDetectedVehicle.reservation_number}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-slate-600">
                        Reserved bay{" "}
                        {reservationForDetectedVehicle.parking_bay_id} was
                        selected automatically. You may choose another available
                        bay below if the customer requests a change.
                      </p>
                    </div>
                  </div>
                </div>
              )}

              <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-start gap-3">
                  <MapPin
                    size={17}
                    className="mt-0.5 shrink-0 text-emerald-600"
                  />

                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] font-black uppercase tracking-wider text-slate-400">
                      Parking Bay Selection
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      Select a basement / level, then choose an available bay in
                      that zone.
                    </p>

                    <div className="mt-3 space-y-2">
                      {availableBaysByZone.map(
                        ({ zone, bays: zoneBays }, index) => {
                          const hasSelectedBay = zoneBays.some(
                            (bay) => bay.id === Number(selectedBayId),
                          );

                          return (
                            <details
                              key={zone.id}
                              open={hasSelectedBay || index === 0}
                              className="overflow-hidden rounded-xl border border-slate-200 bg-white"
                            >
                              <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-black text-slate-800">
                                <span className="flex items-center gap-2">
                                  <MapPin
                                    size={15}
                                    className="text-emerald-600"
                                  />
                                  {zone.name}
                                </span>
                                <ChevronDown
                                  size={16}
                                  className="text-slate-400"
                                />
                              </summary>

                              <div className="border-t border-slate-100 p-3">
                                <select
                                  value={hasSelectedBay ? selectedBayId : ""}
                                  onChange={(event) =>
                                    handleBaySelectionChange(event.target.value)
                                  }
                                  className="w-full rounded-xl border border-slate-200 bg-white px-3 py-3 text-sm font-bold text-slate-800 outline-none focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                                >
                                  <option value="">
                                    Select available bay in {zone.name}
                                  </option>
                                  {zoneBays.map((bay) => (
                                    <option key={bay.id} value={bay.id}>
                                      {bay.code ||
                                        bay.bay_number ||
                                        `Bay #${bay.id}`}
                                      {bay.bay_type ? ` · ${bay.bay_type}` : ""}
                                    </option>
                                  ))}
                                </select>
                              </div>
                            </details>
                          );
                        },
                      )}

                      {availableBaysByZone.length === 0 && (
                        <p className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-bold text-amber-800">
                          No available parking bays are currently available at
                          the assigned facility.
                        </p>
                      )}
                    </div>

                    {selectedBay && (
                      <div className="mt-3 rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-3">
                        <p className="text-[10px] font-black uppercase tracking-wider text-emerald-700">
                          Selected Bay
                        </p>
                        <p className="mt-1 text-sm font-black text-slate-900">
                          {selectedBay.code ||
                            selectedBay.bay_number ||
                            `Bay #${selectedBay.id}`}
                        </p>
                        <p className="mt-1 text-xs text-slate-500">
                          {selectedZone?.name ?? "Selected zone"} · Bay ID{" "}
                          {selectedBay.id}
                        </p>
                      </div>
                    )}
                  </div>
                </div>
              </div>

              <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
                <div className="flex items-start gap-3">
                  <CreditCard
                    size={17}
                    className="mt-0.5 shrink-0 text-blue-600"
                  />

                  <div>
                    <p className="text-[10px] font-black uppercase tracking-wider text-blue-700">
                      What will be sent to SmartPark
                    </p>

                    <div className="mt-2 space-y-1.5 text-xs text-slate-600">
                      <p>
                        RFID Tag:{" "}
                        <span className="font-mono font-black text-slate-800">
                          {detection?.tagUid ?? "Awaiting scan"}
                        </span>
                      </p>
                      <p>
                        Registration:{" "}
                        <span className="font-black text-slate-800">
                          {effectiveRegistration || "Awaiting scan"}
                        </span>
                      </p>
                      <p>
                        Vehicle Type:{" "}
                        <span className="font-black text-slate-800">
                          {detection?.vehicleType || "Awaiting scan"}
                        </span>
                      </p>
                      <p>
                        Customer ID:{" "}
                        <span className="font-black text-slate-800">
                          {detection?.customerId ?? "Awaiting scan"}
                        </span>
                      </p>
                      <p>
                        Billing:{" "}
                        <span className="font-black text-slate-800">
                          {billingType}
                        </span>
                      </p>
                      <p>
                        Entry method:{" "}
                        <span className="font-black text-slate-800">RFID</span>
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {reservationLookupInProgress && (
                <div className="mt-4 rounded-2xl border border-blue-200 bg-blue-50 p-4 text-xs font-semibold text-blue-800">
                  Checking for an applicable reservation for the registered RFID
                  vehicle…
                </div>
              )}

              {detection &&
                !autoEntryCancelled &&
                autoEntryCountdown !== null && (
                  <div className="mt-4 rounded-2xl border border-amber-200 bg-amber-50 p-4">
                    <div className="flex items-start gap-3">
                      <Clock3
                        size={17}
                        className="mt-0.5 shrink-0 text-amber-700"
                      />
                      <div>
                        <p className="text-[10px] font-black uppercase tracking-wider text-amber-700">
                          Automatic RFID Check-In
                        </p>
                        <p className="mt-1 text-xs leading-5 text-amber-900">
                          No entry configuration changes detected. RFID check-in
                          will happen automatically in{" "}
                          <span className="font-black">
                            {autoEntryCountdown} seconds
                          </span>
                          .
                        </p>
                      </div>
                    </div>
                  </div>
                )}

              {detection &&
                autoEntryCancelled &&
                !activeSessionForDetectedVehicle && (
                  <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                    <div className="flex items-start gap-3">
                      <Clock3
                        size={17}
                        className="mt-0.5 shrink-0 text-slate-500"
                      />
                      <div>
                        <p className="text-[10px] font-black uppercase tracking-wider text-slate-500">
                          Automatic Check-In Cancelled
                        </p>
                        <p className="mt-1 text-xs leading-5 text-slate-600">
                          An entry setting was changed. Review the configuration
                          and use the manual check-in button below when ready.
                        </p>
                      </div>
                    </div>
                  </div>
                )}

              <button
                type="button"
                onClick={() => void handleEntry()}
                disabled={!entryReady || submitting}
                className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3.5 text-sm font-black text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <Loader2 size={17} className="animate-spin" />
                    Creating Parking Session…
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={17} />
                    Check In RFID Vehicle
                  </>
                )}
              </button>

              {!detection && (
                <p className="mt-3 text-center text-[10px] font-semibold text-slate-400">
                  Scan an RFID tag to enable session creation.
                </p>
              )}
            </>
          ) : (
            <>
              <div className="flex items-start gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-2xl bg-amber-50 text-amber-600">
                  <ArrowUpFromLine size={20} />
                </span>

                <div>
                  <h2 className="text-sm font-black text-slate-900">
                    Exit Detection
                  </h2>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    RFID identifies the vehicle and locates its parking session.
                  </p>
                </div>
              </div>

              {locatedSession ? (
                <div className="mt-5 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-wider text-slate-400">
                        Located Session
                      </p>
                      <p className="mt-1 text-lg font-black text-slate-900">
                        {locatedSession.session_number}
                      </p>
                    </div>

                    <span
                      className={`rounded-full px-2.5 py-1 text-[10px] font-black uppercase tracking-wider ${
                        isCompletedAwaitingExit(locatedSession)
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-amber-100 text-amber-700"
                      }`}
                    >
                      {locatedSession.status}
                    </span>
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Vehicle
                      </p>
                      <p className="mt-1 text-sm font-black text-slate-800">
                        {locatedSession.vehicle_registration}
                      </p>
                    </div>

                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Bay
                      </p>
                      <p className="mt-1 text-sm font-black text-slate-800">
                        #{locatedSession.parking_bay_id}
                      </p>
                    </div>

                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Entry
                      </p>
                      <p className="mt-1 text-xs font-bold text-slate-700">
                        {formatDateTime(locatedSession.entry_time)}
                      </p>
                    </div>

                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Duration
                      </p>
                      <p className="mt-1 text-xs font-bold text-slate-700">
                        {formatDuration(locatedSession, now)}
                      </p>
                    </div>

                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Payment
                      </p>
                      <p className="mt-1 text-xs font-black text-slate-700">
                        {locatedSession.payment_status || "UNKNOWN"}
                      </p>
                    </div>

                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Amount
                      </p>
                      <p className="mt-1 text-xs font-black text-slate-700">
                        {formatCurrency(locatedSession.calculated_amount)}
                      </p>
                    </div>
                  </div>

                  {rfidPaymentQuote && (
                    <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-4">
                      <div className="flex items-start gap-3">
                        <CreditCard
                          size={17}
                          className="mt-0.5 shrink-0 text-amber-700"
                        />
                        <div className="min-w-0 flex-1">
                          <p className="text-[10px] font-black uppercase tracking-wider text-amber-700">
                            RFID Checkout Payment
                          </p>

                          <div className="mt-2 grid grid-cols-2 gap-3">
                            <div>
                              <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700/70">
                                Current Bill
                              </p>
                              <p className="mt-1 text-lg font-black text-slate-900">
                                {formatCurrency(rfidPaymentQuote.current_bill)}
                              </p>
                            </div>
                            <div>
                              <p className="text-[10px] font-bold uppercase tracking-wider text-amber-700/70">
                                Wallet Balance
                              </p>
                              <p className="mt-1 text-lg font-black text-slate-900">
                                {formatCurrency(
                                  rfidPaymentQuote.wallet_balance,
                                )}
                              </p>
                            </div>
                          </div>

                          <p className="mt-3 text-xs leading-5 text-amber-900">
                            {rfidPaymentQuote.wallet_sufficient
                              ? "The registered customer's wallet was sufficient and the backend completed payment."
                              : "Wallet balance is insufficient. Use operator M-Pesa STK Push or operator-recorded Cash as the payment fallback."}
                          </p>

                          {walletPaymentReady && (
                            <>
                              <div className="mt-4 flex rounded-xl border border-slate-200 bg-white p-1">
                                <button
                                  type="button"
                                  onClick={() => setExitPaymentMethod("MPESA")}
                                  disabled={
                                    stkInitiating ||
                                    stkPolling ||
                                    cashProcessing
                                  }
                                  className={`flex-1 rounded-lg px-3 py-2 text-xs font-black transition ${
                                    exitPaymentMethod === "MPESA"
                                      ? "bg-emerald-600 text-white shadow-sm"
                                      : "text-slate-600 hover:bg-slate-50"
                                  }`}
                                >
                                  <span className="inline-flex items-center justify-center gap-2">
                                    <CreditCard size={14} />
                                    M-Pesa STK
                                  </span>
                                </button>

                                <button
                                  type="button"
                                  onClick={() => setExitPaymentMethod("CASH")}
                                  disabled={
                                    stkInitiating ||
                                    stkPolling ||
                                    cashProcessing
                                  }
                                  className={`flex-1 rounded-lg px-3 py-2 text-xs font-black transition ${
                                    exitPaymentMethod === "CASH"
                                      ? "bg-emerald-600 text-white shadow-sm"
                                      : "text-slate-600 hover:bg-slate-50"
                                  }`}
                                >
                                  <span className="inline-flex items-center justify-center gap-2">
                                    <Banknote size={14} />
                                    Cash
                                  </span>
                                </button>
                              </div>

                              {exitPaymentMethod === "MPESA" && (
                                <>
                                  <div className="mt-3 grid grid-cols-2 gap-2 rounded-xl bg-white/70 p-1">
                                    <button
                                      type="button"
                                      onClick={() =>
                                        setMpesaTarget("REGISTERED")
                                      }
                                      className={`rounded-lg px-3 py-2 text-xs font-black ${
                                        mpesaTarget === "REGISTERED"
                                          ? "bg-slate-950 text-white"
                                          : "text-slate-600"
                                      }`}
                                    >
                                      Registered Number
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => setMpesaTarget("OTHER")}
                                      className={`rounded-lg px-3 py-2 text-xs font-black ${
                                        mpesaTarget === "OTHER"
                                          ? "bg-slate-950 text-white"
                                          : "text-slate-600"
                                      }`}
                                    >
                                      Other Number
                                    </button>
                                  </div>

                                  {mpesaTarget === "OTHER" && (
                                    <input
                                      value={alternativeMpesaNumber}
                                      onChange={(event) =>
                                        setAlternativeMpesaNumber(
                                          event.target.value,
                                        )
                                      }
                                      placeholder="e.g. 0712345678"
                                      className="mt-3 w-full rounded-xl border border-slate-200 bg-white px-3.5 py-3 text-sm font-bold text-slate-800 outline-none focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                                    />
                                  )}

                                  <button
                                    type="button"
                                    onClick={() => void initiateMpesaPayment()}
                                    disabled={
                                      stkInitiating ||
                                      stkPolling ||
                                      cashProcessing
                                    }
                                    className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-xs font-black text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    {stkInitiating || stkPolling ? (
                                      <>
                                        <Loader2
                                          size={15}
                                          className="animate-spin"
                                        />
                                        {stkPolling
                                          ? "Waiting for M-Pesa confirmation…"
                                          : "Sending STK Push…"}
                                      </>
                                    ) : (
                                      <>
                                        <CreditCard size={15} />
                                        Pay{" "}
                                        {formatCurrency(
                                          rfidPaymentQuote.current_bill,
                                        )}{" "}
                                        via M-Pesa
                                      </>
                                    )}
                                  </button>
                                </>
                              )}

                              {exitPaymentMethod === "CASH" && (
                                <div className="mt-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3">
                                  <div className="flex items-start gap-2">
                                    <Banknote
                                      size={17}
                                      className="mt-0.5 shrink-0 text-emerald-700"
                                    />
                                    <div>
                                      <p className="text-sm font-black text-emerald-900">
                                        Record Cash Payment
                                      </p>
                                      <p className="mt-1 text-xs leading-5 text-emerald-800">
                                        Confirm that the driver has paid the
                                        current parking charge in cash.
                                        SmartPark will record the authoritative
                                        amount and complete the normal payment
                                        workflow.
                                      </p>
                                    </div>
                                  </div>

                                  <button
                                    type="button"
                                    onClick={() =>
                                      void recordOperatorCashPayment()
                                    }
                                    disabled={
                                      cashProcessing ||
                                      stkInitiating ||
                                      stkPolling
                                    }
                                    className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-xs font-black text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
                                  >
                                    {cashProcessing ? (
                                      <Loader2
                                        size={15}
                                        className="animate-spin"
                                      />
                                    ) : (
                                      <Banknote size={15} />
                                    )}
                                    {cashProcessing
                                      ? "Recording Cash Payment…"
                                      : `Confirm Cash Payment · ${formatCurrency(rfidPaymentQuote.current_bill)}`}
                                  </button>
                                </div>
                              )}
                            </>
                          )}

                          {stkPayment && (
                            <div className="mt-3 rounded-xl border border-slate-200 bg-white p-3 text-xs">
                              <p className="font-black text-slate-800">
                                M-Pesa status:{" "}
                                {String(stkPayment.status).toUpperCase()}
                              </p>
                              <p className="mt-1 text-slate-500">
                                {stkPayment.message}
                              </p>
                              <p className="mt-1 font-mono text-[10px] text-slate-400">
                                Transaction: {stkPayment.transaction_number}
                              </p>
                            </div>
                          )}

                          {exitPaymentMethod === "CASH" &&
                            cashPaymentRecorded &&
                            !cashProcessing && (
                              <button
                                type="button"
                                onClick={() =>
                                  void retryRfidCheckoutAfterPayment()
                                }
                                disabled={submitting}
                                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-xs font-black text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {submitting ? (
                                  <Loader2 size={15} className="animate-spin" />
                                ) : (
                                  <CheckCircle2 size={15} />
                                )}
                                Complete RFID Physical Exit After Cash Payment
                              </button>
                            )}

                          {stkPayment &&
                            String(stkPayment.status).toUpperCase() ===
                              "SUCCESSFUL" && (
                              <button
                                type="button"
                                onClick={() =>
                                  void retryRfidCheckoutAfterPayment()
                                }
                                disabled={submitting}
                                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-xs font-black text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {submitting ? (
                                  <Loader2 size={15} className="animate-spin" />
                                ) : (
                                  <CheckCircle2 size={15} />
                                )}
                                Complete RFID Physical Exit
                              </button>
                            )}
                        </div>
                      </div>
                    </div>
                  )}

                  {!rfidPaymentQuote &&
                    isCompletedAwaitingExit(locatedSession) && (
                      <div className="mt-4 flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
                        <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
                        <div>
                          <p className="font-black">
                            Payment settled · Physical exit permitted
                          </p>
                          <p className="mt-1 leading-5">
                            The session is completed and awaiting the physical
                            RFID exit event.
                          </p>
                        </div>
                      </div>
                    )}
                </div>
              ) : (
                <div className="mt-5 rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-5 text-center">
                  <ParkingCircle size={24} className="mx-auto text-slate-300" />
                  <p className="mt-2 text-sm font-black text-slate-700">
                    Awaiting RFID exit detection
                  </p>
                  <p className="mt-1 text-xs leading-5 text-slate-400">
                    Enter a registered RFID UID, then scan the RFID tag.
                  </p>
                </div>
              )}

              <div className="mt-4 flex gap-2">
                <button
                  type="button"
                  onClick={() => void handleScan()}
                  disabled={scanning || submitting || !tagUid}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-slate-950 px-4 py-3 text-sm font-black text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {scanning || submitting ? (
                    <Loader2 size={17} className="animate-spin" />
                  ) : (
                    <ScanLine size={17} />
                  )}
                  Detect Vehicle
                </button>

                <button
                  type="button"
                  onClick={resetEvent}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs font-black text-slate-700 hover:bg-slate-50"
                >
                  Clear
                </button>
              </div>

              <button
                type="button"
                onClick={() => void handlePhysicalExit()}
                disabled={!exitReady || submitting || Boolean(rfidPaymentQuote)}
                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3.5 text-sm font-black text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? (
                  <>
                    <Loader2 size={17} className="animate-spin" />
                    Recording Physical Exit…
                  </>
                ) : (
                  <>
                    <CheckCircle2 size={17} />
                    Record RFID Physical Exit
                  </>
                )}
              </button>
            </>
          )}
        </section>
      </div>

      {/* ====================================================
          Event payload
      ==================================================== */}
      {readerEvent && (
        <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-slate-100 text-slate-600">
              <Clock3 size={18} />
            </span>

            <div>
              <h2 className="text-sm font-black text-slate-900">
                Last RFID Reader Event
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                Event payload generated by the simulator.
              </p>
            </div>
          </div>

          <pre className="mt-4 overflow-x-auto rounded-2xl bg-slate-950 p-4 text-xs leading-6 text-slate-200">
            {JSON.stringify(readerEvent, null, 2)}
          </pre>
        </section>
      )}

      {/* ====================================================
          Operational note
      ==================================================== */}
      <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-500">
        <span className="font-black text-slate-700">RFID workflow:</span>{" "}
        Registered UID detected → registered vehicle/customer resolved →
        reservation checked when applicable or registered-user drive-in created
        → registered wallet attempted at exit → operator M-Pesa STK Push or
        operator-recorded Cash used when wallet funds are insufficient →
        physical exit recorded with <span className="font-black">RFID</span>.
      </div>
    </div>
  );
}
