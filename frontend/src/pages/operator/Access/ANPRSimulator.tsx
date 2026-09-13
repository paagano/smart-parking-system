import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertCircle,
  ArrowDownToLine,
  ArrowUpFromLine,
  Camera,
  CameraOff,
  CarFront,
  CheckCircle2,
  CircleDot,
  Clock3,
  Cpu,
  Loader2,
  MapPin,
  ParkingCircle,
  RefreshCw,
  ScanLine,
  ShieldCheck,
  Square,
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
// ANPR Simulator
// ==========================================================
//
// This is an operator-facing ANPR simulation harness.
//
// IMPORTANT:
// - The browser camera preview is real.
// - The operator does NOT type the registration.
// - A 5-second capture countdown gives the operator time to hold a
//   registration plate/paper in the camera view.
// - The browser sends the captured frame to the authenticated FastAPI
//   ANPR endpoint, which performs PaddleOCR server-side.
// - For Drive-In, the next available bay is selected automatically and
//   the operator gets a 30-second configuration window before automatic
//   session creation.
// - For Reservation, the detected registration is matched automatically
//   against confirmed reservations and the existing reservation check-in
//   workflow creates the parking session without operator intervention.
// - The existing ParkingSessionService remains authoritative for
//   vehicle resolution, bay validation, duplicate-session checks,
//   session creation and occupancy updates.
// ==========================================================

type Operation = "ENTRY" | "EXIT";
type EntryMode = "DRIVE_IN" | "RESERVATION";

type DetectedPlate = {
  registration: string;
  confidence: number;
  detectedAt: string;
};

const VEHICLE_TYPES = [
  { value: "CAR", label: "Car" },
  { value: "SUV", label: "SUV" },
  { value: "TRUCK", label: "Truck" },
  { value: "MOTORCYCLE", label: "Motorcycle" },
  { value: "BUS", label: "Bus" },
];

const BILLING_TYPES = [
  { value: "HOURLY", label: "Hourly" },
  { value: "DAILY", label: "Daily" },
  { value: "FLAT", label: "Flat" },
];

function normalizeRegistration(value: string): string {
  return value
    .trim()
    .toUpperCase()
    .replace(/\s+/g, "")
    .replace(/[^A-Z0-9-]/g, "");
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

function formatTime(value: string | null | undefined): string {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-KE", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function getBayLabel(bay: ParkingBay): string {
  return bay.code || bay.bay_number || `Bay #${bay.id}`;
}

function isActiveSession(session: ParkingSession): boolean {
  return (
    String(session.status).toUpperCase() === "ACTIVE" && !session.exit_time
  );
}

function isCompletedAwaitingExit(session: ParkingSession): boolean {
  return (
    String(session.status).toUpperCase() === "COMPLETED" && !session.exit_time
  );
}

type ImageQuality = {
  score: number;
  brightness: number;
  contrast: number;
  sharpness: number;
};

type AnprApiResponse = {
  recognized: boolean;
  registration: string | null;
  formatted_registration?: string | null;
  confidence: number;
  variant?: string | null;
  candidates?: Array<{
    registration: string;
    confidence: number;
    variant: string;
    agreement_count: number;
  }>;
};

export default function ANPRSimulator() {
  const { user } = useAuth();
  const facilityId = user?.facility_id ?? null;

  const [operation, setOperation] = useState<Operation>("ENTRY");
  const [entryMode, setEntryMode] = useState<EntryMode>("DRIVE_IN");

  const [selectedReservation, setSelectedReservation] =
    useState<ParkingReservation | null>(null);

  const [facility, setFacility] = useState<ParkingFacility | null>(null);
  const [zones, setZones] = useState<ParkingZone[]>([]);
  const [bays, setBays] = useState<ParkingBay[]>([]);
  const [activeSessions, setActiveSessions] = useState<ParkingSession[]>([]);

  // Registration is now an internal ANPR result only. The operator never
  // types it into the UI.
  const [registration, setRegistration] = useState("");
  const [vehicleType, setVehicleType] = useState("CAR");
  const [billingType, setBillingType] = useState("HOURLY");
  const [selectedBayId, setSelectedBayId] = useState("");

  const [detectedPlate, setDetectedPlate] = useState<DetectedPlate | null>(
    null,
  );
  const [captureCountdown, setCaptureCountdown] = useState<number | null>(null);
  const [autoCreateCountdown, setAutoCreateCountdown] = useState<number | null>(
    null,
  );

  const [ocrProgress, setOcrProgress] = useState<number | null>(null);
  const [ocrStatus, setOcrStatus] = useState("Ready for plate capture");
  const [imageQuality, setImageQuality] = useState<ImageQuality | null>(null);

  const [entrySession, setEntrySession] = useState<ParkingSession | null>(null);
  const [exitSession, setExitSession] = useState<ParkingSession | null>(null);

  // Once an entry workflow has successfully created/admitted a session,
  // disable further entry capture actions until the operator resets the scan.
  const [entryCompleted, setEntryCompleted] = useState(false);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const [cameraActive, setCameraActive] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);

  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const captureTimerRef = useRef<number | null>(null);
  const autoCreateTimerRef = useRef<number | null>(null);
  const autoCreateArmedRef = useRef(false);

  const loadFacilityData = useCallback(
    async (silent = false) => {
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

        const facilityZoneIds = new Set(zoneData.items.map((zone) => zone.id));

        const facilityBays = bayData.items.filter((bay) =>
          facilityZoneIds.has(bay.zone_id),
        );

        const facilitySessions = sessionData.items.filter((session) => {
          const bay = facilityBays.find(
            (candidate) => candidate.id === session.parking_bay_id,
          );

          return Boolean(bay);
        });

        setFacility(facilityData);
        setZones(zoneData.items);
        setBays(facilityBays);
        setActiveSessions(facilitySessions);

        setSelectedBayId((current) => {
          if (
            current &&
            facilityBays.some((bay) => String(bay.id) === current)
          ) {
            return current;
          }

          const occupiedBayIds = new Set(
            facilitySessions
              .filter(isActiveSession)
              .map((session) => session.parking_bay_id),
          );

          const firstAvailable = facilityBays.find(
            (bay) => bay.is_active && !occupiedBayIds.has(bay.id),
          );

          return firstAvailable ? String(firstAvailable.id) : "";
        });
      } catch (loadError) {
        setError(getApiErrorMessage(loadError));
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
    return () => {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }
      if (captureTimerRef.current !== null) {
        window.clearInterval(captureTimerRef.current);
      }
      if (autoCreateTimerRef.current !== null) {
        window.clearInterval(autoCreateTimerRef.current);
      }
    };
  }, []);

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

  const selectedBay = useMemo(
    () => bays.find((bay) => bay.id === Number(selectedBayId)) ?? null,
    [bays, selectedBayId],
  );

  const facilityZoneById = useMemo(
    () => new Map(zones.map((zone) => [zone.id, zone])),
    [zones],
  );

  const activeSessionForPlate = useMemo(() => {
    const plate = normalizeRegistration(
      detectedPlate?.registration || registration,
    );

    if (!plate) return null;

    return (
      activeSessions.find(
        (session) =>
          normalizeRegistration(session.vehicle_registration) === plate &&
          isActiveSession(session),
      ) ?? null
    );
  }, [activeSessions, detectedPlate?.registration, registration]);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setCameraActive(false);
  }, []);

  const clearCaptureTimer = useCallback(() => {
    if (captureTimerRef.current !== null) {
      window.clearInterval(captureTimerRef.current);
      captureTimerRef.current = null;
    }
    setCaptureCountdown(null);
  }, []);

  const clearAutoCreateTimer = useCallback(() => {
    if (autoCreateTimerRef.current !== null) {
      window.clearInterval(autoCreateTimerRef.current);
      autoCreateTimerRef.current = null;
    }
    setAutoCreateCountdown(null);
  }, []);

  const startCamera = useCallback(async () => {
    setCameraError(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      setCameraError(
        "Camera access is not available in this browser/context. ANPR capture requires camera access.",
      );
      return false;
    }

    if (streamRef.current && cameraActive) {
      return true;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      });

      streamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      setCameraActive(true);
      return true;
    } catch (cameraAccessError) {
      console.error(
        "[ANPR Simulator] Camera access failed:",
        cameraAccessError,
      );
      setCameraError(
        "Camera permission was denied or the camera is unavailable. Allow camera access and try again.",
      );
      setCameraActive(false);
      return false;
    }
  }, [cameraActive]);

  const measureImageQuality = (source: HTMLCanvasElement): ImageQuality => {
    const context = source.getContext("2d", { willReadFrequently: true });
    if (!context) {
      return {
        score: 0,
        brightness: 0,
        contrast: 0,
        sharpness: 0,
      };
    }

    const image = context.getImageData(0, 0, source.width, source.height);
    const data = image.data;
    const sampleStep = Math.max(
      1,
      Math.floor(Math.sqrt((source.width * source.height) / 180000)),
    );

    let count = 0;
    let sum = 0;
    let sumSquared = 0;
    let edgeSum = 0;

    for (let y = 1; y < source.height - 1; y += sampleStep) {
      for (let x = 1; x < source.width - 1; x += sampleStep) {
        const index = (y * source.width + x) * 4;
        const left = index - 4;
        const right = index + 4;
        const above = index - source.width * 4;
        const below = index + source.width * 4;

        const value =
          data[index] * 0.299 +
          data[index + 1] * 0.587 +
          data[index + 2] * 0.114;

        const leftValue =
          data[left] * 0.299 + data[left + 1] * 0.587 + data[left + 2] * 0.114;

        const rightValue =
          data[right] * 0.299 +
          data[right + 1] * 0.587 +
          data[right + 2] * 0.114;

        const aboveValue =
          data[above] * 0.299 +
          data[above + 1] * 0.587 +
          data[above + 2] * 0.114;

        const belowValue =
          data[below] * 0.299 +
          data[below + 1] * 0.587 +
          data[below + 2] * 0.114;

        sum += value;
        sumSquared += value * value;
        edgeSum +=
          Math.abs(rightValue - leftValue) + Math.abs(belowValue - aboveValue);
        count += 1;
      }
    }

    if (!count) {
      return {
        score: 0,
        brightness: 0,
        contrast: 0,
        sharpness: 0,
      };
    }

    const brightness = sum / count;
    const variance = Math.max(0, sumSquared / count - brightness * brightness);
    const contrast = Math.sqrt(variance);
    const sharpness = edgeSum / count / 2;

    // A plate/paper should normally be neither extremely dark nor completely
    // blown out. Contrast and edge energy are equally important for OCR.
    const brightnessScore = 1 - Math.min(1, Math.abs(brightness - 145) / 145);
    const contrastScore = Math.min(1, contrast / 58);
    const sharpnessScore = Math.min(1, sharpness / 24);

    return {
      score: Math.max(
        0,
        Math.min(
          1,
          brightnessScore * 0.25 + contrastScore * 0.35 + sharpnessScore * 0.4,
        ),
      ),
      brightness,
      contrast,
      sharpness,
    };
  };

  const captureSourceFrame = (
    video: HTMLVideoElement,
    canvas: HTMLCanvasElement,
  ) => {
    const sourceWidth = video.videoWidth;
    const sourceHeight = video.videoHeight;

    if (!sourceWidth || !sourceHeight) {
      throw new Error("The camera did not provide a usable image frame.");
    }

    /*
     * The on-screen guide occupies the central horizontal text band. Sending
     * the entire 1920x1080 camera frame to CPU PaddleOCR makes detection
     * unnecessarily expensive because it also processes the operator,
     * background and unrelated paper area.
     *
     * Capture the guide band instead. The operator is already instructed to
     * keep the registration paper inside this guide.
     */
    const cropX = Math.round(sourceWidth * 0.08);
    const cropWidth = Math.round(sourceWidth * 0.84);
    const cropY = Math.round(sourceHeight * 0.34);
    const cropHeight = Math.round(sourceHeight * 0.28);

    /*
     * Cap the OCR upload at 1280px wide. This is still substantially larger
     * than the original 572px benchmark image while keeping CPU inference
     * practical for the local SmartPark backend.
     */
    const targetWidth = Math.min(1280, cropWidth);
    const targetHeight = Math.max(
      1,
      Math.round(targetWidth * (cropHeight / cropWidth)),
    );

    canvas.width = targetWidth;
    canvas.height = targetHeight;

    const context = canvas.getContext("2d", {
      willReadFrequently: true,
    });

    if (!context) {
      throw new Error("Unable to prepare the ANPR image for OCR.");
    }

    context.imageSmoothingEnabled = true;
    context.imageSmoothingQuality = "high";

    context.drawImage(
      video,
      cropX,
      cropY,
      cropWidth,
      cropHeight,
      0,
      0,
      targetWidth,
      targetHeight,
    );
  };

  const captureAndRecognizePlate = async () => {
    if (scanning || submitting || entryCompleted) return;

    setError(null);
    setSuccess(null);
    setDetectedPlate(null);
    setSelectedReservation(null);
    setOcrProgress(null);
    setImageQuality(null);
    setOcrStatus("Preparing camera capture...");
    autoCreateArmedRef.current = false;
    clearAutoCreateTimer();

    const cameraReady = await startCamera();
    if (!cameraReady) return;

    if (!videoRef.current || videoRef.current.readyState < 2) {
      setError(
        "The camera is not ready yet. Please wait a moment and capture again.",
      );
      return;
    }

    setScanning(true);
    clearCaptureTimer();

    let seconds = 5;
    setCaptureCountdown(seconds);
    setOcrStatus(
      "Hold the registration paper inside the guide — keep characters large, dark and steady...",
    );

    await new Promise<void>((resolve) => {
      captureTimerRef.current = window.setInterval(() => {
        seconds -= 1;
        setCaptureCountdown(seconds);

        if (seconds <= 0) {
          if (captureTimerRef.current !== null) {
            window.clearInterval(captureTimerRef.current);
            captureTimerRef.current = null;
          }
          resolve();
        }
      }, 1000);
    });

    setCaptureCountdown(null);

    try {
      const video = videoRef.current;
      const canvas = canvasRef.current;

      if (!video || !canvas) {
        throw new Error("ANPR camera capture surface is unavailable.");
      }

      /*
       * Capture the registration guide band after the countdown. The browser
       * deliberately does not perform OCR. The image is sent to the
       * authenticated SmartPark FastAPI endpoint, where PaddleOCR performs
       * detection, preprocessing, recognition and Kenyan registration
       * validation.
       */
      captureSourceFrame(video, canvas);

      const quality = measureImageQuality(canvas);
      setImageQuality(quality);
      setOcrProgress(15);
      setOcrStatus(
        `Image captured · quality ${Math.round(quality.score * 100)}% · sending to PaddleOCR...`,
      );

      const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, "image/jpeg", 0.92),
      );

      if (!blob) {
        throw new Error("Unable to encode the captured ANPR image.");
      }

      setOcrProgress(30);
      setOcrStatus(
        "Sending captured image to SmartPark FastAPI → PaddleOCR...",
      );

      const formData = new FormData();
      formData.append("attachment", blob, "anpr-capture.jpg");

      /*
       * Do not manually set Content-Type here. Axios/browser FormData handling
       * supplies the multipart boundary automatically.
       */
      console.info(
        "[ANPR Simulator] Sending captured image to PaddleOCR API:",
        "/ai/anpr/recognize",
        {
          bytes: blob.size,
          type: blob.type,
          width: canvas.width,
          height: canvas.height,
        },
      );

      const response = await api.post<AnprApiResponse>(
        "/ai/anpr/recognize",
        formData,
        {
          /*
           * api has a global application/json default. Explicitly clear it for
           * this FormData request so Axios/browser can generate the correct
           * multipart Content-Type boundary.
           *
           * The existing Axios interceptor still supplies the JWT.
           */
          headers: {
            "Content-Type": undefined,
          },
          /*
           * PaddleOCR CPU inference can legitimately take longer than the
           * normal 15-second application API timeout on the first request.
           * This override applies only to ANPR recognition.
           */
          timeout: 120000,
        },
      );

      console.info(
        "[ANPR Simulator] PaddleOCR API response:",
        response.status,
        response.data,
      );

      setOcrProgress(85);

      const normalizedPlate = normalizeRegistration(
        response.data.registration ?? "",
      );

      if (!response.data.recognized || !normalizedPlate) {
        throw new Error(
          "PaddleOCR could not identify a valid Kenyan vehicle registration. Keep the paper horizontal inside the guide, move it closer, use dark/thick characters and avoid glare before capturing again.",
        );
      }

      const confidence = Math.max(
        0,
        Math.min(1, Number(response.data.confidence ?? 0)),
      );

      if (!confidence) {
        throw new Error(
          "PaddleOCR recognized text but did not return a usable confidence score. Capture the registration again.",
        );
      }

      const result: DetectedPlate = {
        registration: normalizedPlate,
        confidence,
        detectedAt: new Date().toISOString(),
      };

      setRegistration(normalizedPlate);
      setDetectedPlate(result);
      setOcrProgress(100);
      setOcrStatus(
        `${normalizedPlate} recognized by PaddleOCR · ${
          response.data.variant ?? "validated OCR variant"
        }`,
      );
      setSuccess(
        `ANPR recognized ${normalizedPlate} with ${formatConfidence(confidence)} confidence using PaddleOCR.${
          response.data.candidates?.[0]?.agreement_count
            ? ` ${response.data.candidates[0].agreement_count} preprocessing variants agreed on the plate.`
            : ""
        }`,
      );

      /*
       * Reservation admission is intentionally fully automatic after a valid
       * plate recognition. No reservation search, selection or confirmation
       * is required from the operator.
       */
      if (operation === "ENTRY" && entryMode === "RESERVATION") {
        setSubmitting(true);

        try {
          const reservationResponse = await api.get<{
            items: ParkingReservation[];
            total: number;
          }>("/parking-reservations/search", {
            params: { search_term: normalizedPlate },
          });

          const facilityBayIds = new Set(bays.map((bay) => bay.id));

          const eligible = (reservationResponse.data.items ?? []).filter(
            (reservation) => {
              return (
                String(reservation.status ?? "").toUpperCase() ===
                  "CONFIRMED" &&
                !reservation.checked_in_at &&
                normalizeRegistration(reservation.vehicle_registration) ===
                  normalizedPlate &&
                facilityBayIds.has(reservation.parking_bay_id)
              );
            },
          );

          if (eligible.length === 0) {
            throw new Error(
              `No confirmed, paid and eligible reservation was found for ANPR plate ${normalizedPlate} at this facility.`,
            );
          }

          const reservation = eligible[0];
          setSelectedReservation(reservation);

          const checkInResponse = await api.patch<ParkingReservation>(
            `/parking-reservations/${reservation.id}/check-in`,
            null,
            { params: { entry_method: "ANPR" } },
          );

          setEntryCompleted(true);
          setSuccess(
            `Reservation ${checkInResponse.data.reservation_number} automatically checked in. ${normalizedPlate} is admitted via ANPR and the reserved parking session is now ACTIVE.`,
          );

          await loadFacilityData(true);
        } finally {
          setSubmitting(false);
        }
      } else if (operation === "ENTRY") {
        // The next available bay is selected by facility state. The operator
        // can alter configuration during the 30-second review window.
        autoCreateArmedRef.current = true;
      }
    } catch (recognitionError) {
      console.error(
        "[ANPR Simulator] PaddleOCR request/recognition failed:",
        recognitionError,
      );
      setError(getApiErrorMessage(recognitionError));
      setOcrStatus("Recognition failed — capture again");
      setOcrProgress(null);
      autoCreateArmedRef.current = false;
      clearAutoCreateTimer();
    } finally {
      setScanning(false);
    }
  };

  const handleEntry = async () => {
    if (entryMode === "RESERVATION") {
      // Reservation entry is automatic immediately after ANPR recognition.
      setError(
        "Reservation admission is automatic after a valid ANPR recognition.",
      );
      return;
    }

    const plate = normalizeRegistration(
      detectedPlate?.registration || registration,
    );

    if (!plate) {
      setError("No ANPR plate has been detected.");
      return;
    }

    if (!selectedBayId) {
      setError(
        "No available parking bay is currently assigned to this ANPR entry.",
      );
      return;
    }

    if (activeSessionForPlate) {
      setError(
        `Vehicle ${plate} already has an active parking session (${activeSessionForPlate.session_number}).`,
      );
      autoCreateArmedRef.current = false;
      clearAutoCreateTimer();
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);
    setEntrySession(null);
    autoCreateArmedRef.current = false;
    clearAutoCreateTimer();

    try {
      const response = await api.post<ParkingSession>(
        "/parking-sessions/check-in",
        {
          parking_bay_id: Number(selectedBayId),
          customer_id: null,
          vehicle_id: null,
          vehicle_registration: plate,
          vehicle_type: vehicleType,
          billing_type: billingType,
          session_source: "DRIVE_IN",
          entry_method: "ANPR",
          expected_exit_time: null,
          notes: "ANPR camera OCR automated access simulation",
        },
      );

      setEntrySession(response.data);
      setEntryCompleted(true);
      setSuccess(
        `ANPR Drive-In admission accepted. ${response.data.vehicle_registration} was checked in and parking session ${response.data.session_number} is now ACTIVE.`,
      );

      await loadFacilityData(true);
    } catch (submitError) {
      setError(getApiErrorMessage(submitError));
    } finally {
      setSubmitting(false);
    }
  };

  const handleExitDetection = async () => {
    const plate = normalizeRegistration(
      detectedPlate?.registration || registration,
    );

    if (!plate) {
      setError("No ANPR plate has been detected.");
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);
    setExitSession(null);

    try {
      const result = await api.get<{
        items: ParkingSession[];
        total: number;
      }>("/parking-sessions/search", {
        params: { registration: plate },
      });

      const sessions = result.data.items ?? [];

      const session =
        sessions.find(isCompletedAwaitingExit) ??
        sessions.find(isActiveSession) ??
        null;

      if (!session) {
        setError(
          `No active parking session or completed session awaiting physical exit was found for ${plate}.`,
        );
        return;
      }

      setExitSession(session);

      if (isCompletedAwaitingExit(session)) {
        setSuccess(
          `ANPR exit detected for ${plate}. Session ${session.session_number} is already completed by the payment workflow and is ready for physical exit.`,
        );
      } else {
        setSuccess(
          `ANPR exit detected for ${plate}. Session ${session.session_number} is still ACTIVE and must be settled before physical checkout.`,
        );
      }
    } catch (searchError) {
      setError(getApiErrorMessage(searchError));
    } finally {
      setSubmitting(false);
    }
  };

  const handlePhysicalExit = async () => {
    if (!exitSession) {
      setError("Detect the vehicle at the exit first.");
      return;
    }

    if (!isCompletedAwaitingExit(exitSession)) {
      setError(
        "This parking session is still ACTIVE. Complete and settle the parking payment before physical ANPR checkout.",
      );
      return;
    }

    setSubmitting(true);
    setError(null);
    setSuccess(null);

    try {
      const response = await api.post<ParkingSession>(
        "/parking-sessions/check-out",
        {
          vehicle_registration: normalizeRegistration(
            exitSession.vehicle_registration,
          ),
          exit_method: "ANPR",
          notes: "ANPR automated physical exit simulation",
        },
      );

      setExitSession(null);
      setDetectedPlate(null);
      setRegistration("");

      setSuccess(
        `ANPR exit completed. ${response.data.vehicle_registration} has physically exited the facility at ${formatDateTime(response.data.exit_time)}.`,
      );

      await loadFacilityData(true);
    } catch (checkoutError) {
      setError(getApiErrorMessage(checkoutError));
    } finally {
      setSubmitting(false);
    }
  };

  // Drive-In inactivity timer: once ANPR has recognized a plate, SmartPark
  // gives the operator 30 seconds to alter the proposed configuration. If no
  // configuration action occurs, the session is created automatically.
  useEffect(() => {
    clearAutoCreateTimer();

    if (
      operation !== "ENTRY" ||
      entryMode !== "DRIVE_IN" ||
      !detectedPlate ||
      entryCompleted ||
      !autoCreateArmedRef.current ||
      submitting ||
      !selectedBayId
    ) {
      return;
    }

    let seconds = 60; // 60-second countdown for operator review before automatic session creation
    setAutoCreateCountdown(seconds);

    autoCreateTimerRef.current = window.setInterval(() => {
      seconds -= 1;
      setAutoCreateCountdown(seconds);

      if (seconds <= 0) {
        clearAutoCreateTimer();
        autoCreateArmedRef.current = false;
        void handleEntry();
      }
    }, 1000);

    return clearAutoCreateTimer;
  }, [
    operation,
    entryMode,
    detectedPlate,
    vehicleType,
    billingType,
    selectedBayId,
    submitting,
    clearAutoCreateTimer,
    entryCompleted,
  ]);

  const resetScan = () => {
    setDetectedPlate(null);
    setEntrySession(null);
    setEntryCompleted(false);
    setExitSession(null);
    setRegistration("");
    setSelectedReservation(null);
    setCaptureCountdown(null);
    setAutoCreateCountdown(null);
    setOcrProgress(null);
    setOcrStatus("Ready for plate capture");
    setImageQuality(null);
    autoCreateArmedRef.current = false;
    clearCaptureTimer();
    clearAutoCreateTimer();
    setError(null);
    setSuccess(null);
  };

  const handleOperationChange = (next: Operation) => {
    setOperation(next);
    setDetectedPlate(null);
    setEntrySession(null);
    setEntryCompleted(false);
    setExitSession(null);
    setRegistration("");
    setSelectedReservation(null);
    setCaptureCountdown(null);
    setAutoCreateCountdown(null);
    setOcrProgress(null);
    setOcrStatus("Ready for plate capture");
    setImageQuality(null);
    autoCreateArmedRef.current = false;
    clearCaptureTimer();
    clearAutoCreateTimer();
    setError(null);
    setSuccess(null);
  };

  const isEntry = operation === "ENTRY";

  if (loading) {
    return (
      <div className="grid min-h-[60vh] place-items-center">
        <div className="text-center">
          <Loader2
            className="mx-auto animate-spin text-emerald-600"
            size={34}
          />
          <p className="mt-3 text-sm font-semibold text-slate-500">
            Loading ANPR access control...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <div className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-600">
          SmartPark AI · Automated Access
        </div>

        <div className="mt-2 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-black tracking-tight text-slate-950">
              ANPR Simulator
            </h1>
            <p className="mt-1 max-w-3xl text-sm leading-5 text-slate-500">
              Hold a printed vehicle registration in front of the camera.
              SmartPark captures it after a five-second countdown, sends the
              image to the backend PaddleOCR engine for validated recognition,
              and automatically routes the result into the correct parking
              workflow.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void loadFacilityData(true)}
            disabled={refreshing || submitting}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-60"
          >
            <RefreshCw size={15} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* Facility context */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-100 bg-emerald-50/70 px-4 py-3">
        <div className="flex items-center gap-3">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-white text-emerald-600 shadow-sm">
            <ShieldCheck size={20} />
          </span>

          <div>
            <p className="text-sm font-black text-slate-900">
              {facility?.name ?? "Assigned parking facility"}
            </p>
            <p className="mt-0.5 text-xs text-slate-500">
              Facility #{facility?.id ?? user?.facility_id ?? "—"} · ANPR access
              simulator
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 rounded-full border border-emerald-200 bg-white px-2.5 py-1 text-[11px] font-bold text-emerald-700">
          <CircleDot size={13} className="fill-emerald-500" />
          Camera OCR online
        </div>
      </div>

      {/* Alerts */}
      {error && (
        <div className="sticky top-2 z-40 flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50/95 px-4 py-3 text-sm text-rose-700 shadow-lg backdrop-blur">
          <AlertCircle size={19} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-black">ANPR operation could not be completed</p>
            <p className="mt-1">{error}</p>
          </div>
        </div>
      )}

      {success && (
        <div className="sticky top-2 z-30 flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50/95 px-4 py-3 text-sm text-emerald-700 shadow-md backdrop-blur">
          <CheckCircle2 size={19} className="mt-0.5 shrink-0" />
          <div>
            <p className="font-black">ANPR operation successful</p>
            <p className="mt-1">{success}</p>
          </div>
        </div>
      )}

      {/* Entry / Exit selector */}
      <div className="grid gap-3 md:grid-cols-2">
        <button
          type="button"
          onClick={() => handleOperationChange("ENTRY")}
          className={`rounded-xl border p-3.5 text-left transition ${
            isEntry
              ? "border-emerald-300 bg-emerald-50 shadow-sm"
              : "border-slate-200 bg-white hover:border-slate-300"
          }`}
        >
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-white text-emerald-600 shadow-sm">
            <ArrowDownToLine size={21} />
          </span>
          <p className="mt-2 text-base font-black text-slate-900">
            Vehicle Entry
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Detect the number plate and create an ACTIVE parking session.
          </p>
        </button>

        <button
          type="button"
          onClick={() => handleOperationChange("EXIT")}
          className={`rounded-xl border p-3.5 text-left transition ${
            !isEntry
              ? "border-emerald-300 bg-emerald-50 shadow-sm"
              : "border-slate-200 bg-white hover:border-slate-300"
          }`}
        >
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-white text-emerald-600 shadow-sm">
            <ArrowUpFromLine size={21} />
          </span>
          <p className="mt-2 text-base font-black text-slate-900">
            Vehicle Exit
          </p>
          <p className="mt-1 text-sm text-slate-500">
            Detect a plate, locate its session and record ANPR physical exit
            after settlement.
          </p>
        </button>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.08fr_0.92fr]">
        {/* Camera */}
        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-950 shadow-sm">
          <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
            <div>
              <p className="text-sm font-black text-white">ANPR Camera Feed</p>
              <p className="mt-1 text-xs text-slate-400">
                Real browser camera + server-side PaddleOCR. No registration is
                typed by the operator.
              </p>
            </div>

            <div className="flex items-center gap-2">
              <span
                className={`h-2.5 w-2.5 rounded-full ${
                  cameraActive ? "bg-emerald-400" : "bg-slate-600"
                }`}
              />
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                {cameraActive ? "Live" : "Standby"}
              </span>
            </div>
          </div>

          <div className="relative h-[300px] bg-slate-900 sm:h-[330px] lg:h-[350px]">
            <video
              ref={videoRef}
              muted
              playsInline
              className={`h-full w-full object-cover ${
                cameraActive ? "block" : "hidden"
              }`}
            />

            {/*
             * Hidden capture surface used to snapshot the live camera frame
             * before uploading it to the FastAPI PaddleOCR endpoint.
             *
             * This element must remain mounted even though it is not displayed.
             * The capture pipeline obtains canvasRef.current immediately after
             * the countdown, so conditionally rendering the canvas would make
             * the OCR request fail before any network call is made.
             */}
            <canvas ref={canvasRef} className="hidden" aria-hidden="true" />

            {!cameraActive && (
              <div className="absolute inset-0 grid place-items-center">
                <div className="text-center">
                  <CameraOff size={42} className="mx-auto text-slate-600" />
                  <p className="mt-3 text-sm font-bold text-slate-400">
                    Camera preview is off
                  </p>
                  <p className="mt-1 text-xs text-slate-600">
                    Start the camera before beginning ANPR capture.
                  </p>
                </div>
              </div>
            )}

            {captureCountdown !== null && (
              <div className="absolute inset-0 grid place-items-center bg-slate-950/45 backdrop-blur-[1px]">
                <div className="text-center">
                  <div className="mx-auto grid h-28 w-28 place-items-center rounded-full border-4 border-emerald-400 bg-slate-950/80 shadow-2xl">
                    <span className="text-6xl font-black tabular-nums text-white">
                      {captureCountdown}
                    </span>
                  </div>
                  <p className="mt-4 text-xs font-black uppercase tracking-[0.18em] text-emerald-300">
                    Hold plate steady
                  </p>
                </div>
              </div>
            )}

            {!captureCountdown && !detectedPlate && (
              <div className="pointer-events-none absolute left-[8%] top-[34%] w-[84%] h-[28%]">
                <div className="h-full rounded-xl border-2 border-dashed border-emerald-400/90 bg-emerald-400/5 shadow-[0_0_0_9999px_rgba(2,6,23,0.08)]" />
                <p className="absolute left-1/2 top-full mt-2 w-full -translate-x-1/2 text-center text-[10px] font-bold text-emerald-300">
                  Place the registration paper here · fill most of the guide
                </p>
              </div>
            )}

            {scanning && !captureCountdown && (
              <div className="absolute left-1/2 top-5 -translate-x-1/2 rounded-full border border-emerald-300/30 bg-slate-950/90 px-4 py-2 text-[11px] font-black text-emerald-300 shadow-xl backdrop-blur">
                Sending frame to PaddleOCR…
              </div>
            )}

            {detectedPlate && (
              <div className="absolute inset-x-4 bottom-4">
                <div className="rounded-xl border border-emerald-400/30 bg-slate-950/90 p-3 shadow-2xl backdrop-blur">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-400/10 text-emerald-300">
                        <ScanLine size={20} />
                      </span>
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-emerald-300">
                          Plate detected
                        </p>
                        <p className="mt-1 text-xl font-black tracking-[0.12em] text-white">
                          {detectedPlate.registration}
                        </p>
                      </div>
                    </div>

                    <div className="text-right">
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
                        Confidence
                      </p>
                      <p className="mt-1 text-sm font-black text-emerald-300">
                        {formatConfidence(detectedPlate.confidence)}
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          {cameraError && (
            <div className="border-t border-amber-400/10 bg-amber-400/5 px-5 py-3 text-xs text-amber-300">
              {cameraError}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2.5 p-3.5">
            {!cameraActive ? (
              <button
                type="button"
                onClick={() => void startCamera()}
                className="inline-flex items-center gap-2 rounded-lg bg-white px-3 py-2 text-xs font-black text-slate-900 transition hover:bg-slate-100"
              >
                <Camera size={15} />
                Start Camera
              </button>
            ) : (
              <button
                type="button"
                onClick={stopCamera}
                className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs font-black text-white transition hover:bg-white/10"
              >
                <Square size={13} />
                Stop Camera
              </button>
            )}

            {!entryCompleted && (
              <button
                type="button"
                onClick={() => void captureAndRecognizePlate()}
                disabled={scanning || submitting}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-500 px-3 py-2 text-xs font-black text-white transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {scanning ? (
                  <Loader2 size={15} className="animate-spin" />
                ) : (
                  <ScanLine size={15} />
                )}
                {scanning ? "Scanning…" : "Capture Plate"}
              </button>
            )}

            {entryCompleted && (
              <span className="inline-flex items-center gap-2 rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-3 py-2 text-xs font-black text-emerald-300">
                <CheckCircle2 size={14} />
                Session created
              </span>
            )}

            <button
              type="button"
              onClick={resetScan}
              disabled={scanning || submitting}
              className="inline-flex items-center gap-2 rounded-xl border border-white/10 bg-white/5 px-4 py-2.5 text-xs font-black text-slate-300 transition hover:bg-white/10 disabled:opacity-50"
            >
              Reset
            </button>
          </div>
        </section>

        {/* Detection / command panel */}
        <section className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex items-start gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-slate-950 text-emerald-400">
                <ScanLine size={19} />
              </span>
              <div>
                <h2 className="text-sm font-black text-slate-900">
                  Plate Recognition
                </h2>
                <p className="mt-1 text-xs leading-5 text-slate-500">
                  Model A — Server PaddleOCR. SmartPark captures the camera
                  frame, sends it to FastAPI for PP-OCRv6 recognition,
                  preprocessing and Kenyan registration validation before
                  accepting a plate.
                </p>
              </div>
            </div>

            <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.16em] text-slate-500">
                    Camera workflow
                  </p>
                  <p className="mt-1 text-sm font-black text-slate-900">
                    5-second countdown + server-side OCR validation
                  </p>
                </div>
                <span className="rounded-full bg-white px-3 py-1 text-[10px] font-black uppercase tracking-wider text-slate-500 shadow-sm">
                  PaddleOCR · PP-OCRv6
                </span>
              </div>

              <div className="mt-3 flex items-center gap-2">
                {!entryCompleted ? (
                  <button
                    type="button"
                    onClick={() => void captureAndRecognizePlate()}
                    disabled={scanning || submitting}
                    className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-black text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {scanning ? (
                      <Loader2 size={17} className="animate-spin" />
                    ) : (
                      <ScanLine size={17} />
                    )}
                    {scanning
                      ? "Capturing / Recognizing…"
                      : "Capture & Recognize Plate"}
                  </button>
                ) : (
                  <div className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm font-black text-emerald-700">
                    <CheckCircle2 size={17} />
                    Session created — Reset for next vehicle
                  </div>
                )}
              </div>

              <p className="mt-3 text-xs font-semibold text-slate-500">
                {ocrStatus}
              </p>

              {ocrProgress !== null && (
                <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200">
                  <div
                    className="h-full rounded-full bg-emerald-500 transition-all"
                    style={{ width: `${ocrProgress}%` }}
                  />
                </div>
              )}

              {imageQuality && (
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <div className="rounded-lg bg-white p-2.5">
                    <p className="text-[9px] font-black uppercase tracking-wider text-slate-400">
                      Quality
                    </p>
                    <p className="mt-1 text-sm font-black text-slate-900">
                      {Math.round(imageQuality.score * 100)}%
                    </p>
                  </div>
                  <div className="rounded-lg bg-white p-2.5">
                    <p className="text-[9px] font-black uppercase tracking-wider text-slate-400">
                      Brightness
                    </p>
                    <p className="mt-1 text-sm font-black text-slate-900">
                      {Math.round(imageQuality.brightness)}
                    </p>
                  </div>
                  <div className="rounded-lg bg-white p-2.5">
                    <p className="text-[9px] font-black uppercase tracking-wider text-slate-400">
                      Contrast
                    </p>
                    <p className="mt-1 text-sm font-black text-slate-900">
                      {Math.round(imageQuality.contrast)}
                    </p>
                  </div>
                  <div className="rounded-lg bg-white p-2.5">
                    <p className="text-[9px] font-black uppercase tracking-wider text-slate-400">
                      Sharpness
                    </p>
                    <p className="mt-1 text-sm font-black text-slate-900">
                      {Math.round(imageQuality.sharpness)}
                    </p>
                  </div>
                </div>
              )}
            </div>

            {captureCountdown !== null && (
              <div className="mt-3 overflow-hidden rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-center">
                <p className="text-[10px] font-black uppercase tracking-[0.2em] text-emerald-700">
                  Hold plate steady — capturing in
                </p>
                <p className="mt-1 text-4xl font-black tabular-nums text-emerald-900">
                  {captureCountdown}
                </p>
              </div>
            )}

            {detectedPlate && (
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4">
                  <p className="text-[10px] font-black uppercase tracking-wider text-emerald-700">
                    Recognition
                  </p>
                  <p className="mt-1 text-xl font-black tracking-[0.12em] text-emerald-900">
                    {detectedPlate.registration}
                  </p>
                </div>
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-[10px] font-black uppercase tracking-wider text-slate-500">
                    Confidence
                  </p>
                  <p className="mt-1 text-xl font-black text-slate-900">
                    {formatConfidence(detectedPlate.confidence)}
                  </p>
                </div>
              </div>
            )}
          </div>

          {isEntry ? (
            <div className="space-y-4">
              <div className="flex rounded-xl border border-slate-200 bg-white p-1 shadow-sm">
                <button
                  type="button"
                  onClick={() => setEntryMode("DRIVE_IN")}
                  className={`flex-1 rounded-lg px-3 py-2 text-xs font-black transition ${
                    entryMode === "DRIVE_IN"
                      ? "bg-emerald-600 text-white shadow-sm"
                      : "text-slate-500 hover:bg-slate-50"
                  }`}
                >
                  Drive-In
                </button>
                <button
                  type="button"
                  onClick={() => setEntryMode("RESERVATION")}
                  className={`flex-1 rounded-lg px-3 py-2 text-xs font-black transition ${
                    entryMode === "RESERVATION"
                      ? "bg-emerald-600 text-white shadow-sm"
                      : "text-slate-500 hover:bg-slate-50"
                  }`}
                >
                  Reservation
                </button>
              </div>

              {entryMode === "DRIVE_IN" ? (
                <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-start gap-3">
                    <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                      <ParkingCircle size={19} />
                    </span>
                    <div>
                      <h2 className="text-sm font-black text-slate-900">
                        What will be sent to SmartPark
                      </h2>
                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        SmartPark has proposed the next available bay and
                        default vehicle/billing settings. You may change these
                        before the 30-second inactivity timer expires.
                      </p>
                    </div>
                  </div>

                  <div className="mt-3 grid gap-3 sm:grid-cols-2">
                    <label>
                      <span className="text-xs font-black uppercase tracking-wider text-slate-500">
                        Vehicle Type
                      </span>
                      <select
                        value={vehicleType}
                        onChange={(event) => {
                          setVehicleType(event.target.value);
                          autoCreateArmedRef.current = Boolean(detectedPlate);
                        }}
                        className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-bold text-slate-800 outline-none focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                      >
                        {VEHICLE_TYPES.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>

                    <label>
                      <span className="text-xs font-black uppercase tracking-wider text-slate-500">
                        Billing Type
                      </span>
                      <select
                        value={billingType}
                        onChange={(event) => {
                          setBillingType(event.target.value);
                          autoCreateArmedRef.current = Boolean(detectedPlate);
                        }}
                        className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-bold text-slate-800 outline-none focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                      >
                        {BILLING_TYPES.map((item) => (
                          <option key={item.value} value={item.value}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>

                  <label className="mt-3 block">
                    <span className="text-xs font-black uppercase tracking-wider text-slate-500">
                      Parking Bay
                    </span>
                    <select
                      value={selectedBayId}
                      onChange={(event) => {
                        setSelectedBayId(event.target.value);
                        autoCreateArmedRef.current = Boolean(detectedPlate);
                      }}
                      className="mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm font-bold text-slate-800 outline-none focus:border-emerald-400 focus:ring-4 focus:ring-emerald-50"
                    >
                      {availableBays.map((bay) => {
                        const zone = facilityZoneById.get(bay.zone_id);
                        return (
                          <option key={bay.id} value={bay.id}>
                            {getBayLabel(bay)}
                            {zone ? ` · ${zone.name}` : ""}
                          </option>
                        );
                      })}
                    </select>
                  </label>

                  <div className="mt-3 rounded-xl border border-blue-100 bg-blue-50 p-3">
                    <div className="flex items-start gap-3">
                      <Cpu
                        size={18}
                        className="mt-0.5 shrink-0 text-blue-600"
                      />
                      <div className="min-w-0 text-xs leading-5 text-blue-800">
                        <p className="font-black">
                          What will be sent to SmartPark
                        </p>
                        <p className="mt-1">
                          Registration{" "}
                          <strong>{detectedPlate?.registration ?? "—"}</strong>
                          {" · "}Vehicle type{" "}
                          <strong>
                            {VEHICLE_TYPES.find(
                              (item) => item.value === vehicleType,
                            )?.label ?? vehicleType}
                          </strong>
                          {" · "}Billing{" "}
                          <strong>
                            {BILLING_TYPES.find(
                              (item) => item.value === billingType,
                            )?.label ?? billingType}
                          </strong>
                          {" · "}Bay{" "}
                          <strong>
                            {selectedBay ? getBayLabel(selectedBay) : "—"}
                          </strong>
                          {" · "}Entry method <strong>ANPR</strong>
                          {" · "}Source <strong>DRIVE_IN</strong>
                        </p>
                      </div>
                    </div>
                  </div>

                  {autoCreateCountdown !== null && detectedPlate && (
                    <div className="mt-3 flex items-center justify-between gap-3 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5">
                      <div>
                        <p className="text-xs font-black text-amber-900">
                          Automatic session creation armed
                        </p>
                        <p className="mt-0.5 text-[11px] text-amber-700">
                          Change a configuration to reset the inactivity timer.
                        </p>
                      </div>
                      <div className="text-2xl font-black tabular-nums text-amber-900">
                        {autoCreateCountdown}s
                      </div>
                    </div>
                  )}

                  {!entryCompleted && (
                    <button
                      type="button"
                      onClick={() => void handleEntry()}
                      disabled={!detectedPlate || !selectedBayId || submitting}
                      className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm font-black text-slate-800 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {submitting ? (
                        <Loader2 size={17} className="animate-spin" />
                      ) : (
                        <ArrowDownToLine size={17} />
                      )}
                      Create Session Now
                    </button>
                  )}
                </div>
              ) : (
                <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 shadow-sm">
                  <div className="flex items-start gap-3">
                    <span className="grid h-10 w-10 place-items-center rounded-xl bg-white text-emerald-600 shadow-sm">
                      <ShieldCheck size={19} />
                    </span>
                    <div>
                      <h2 className="text-sm font-black text-slate-900">
                        Reservation ANPR Admission
                      </h2>
                      <p className="mt-1 text-xs leading-5 text-slate-600">
                        No reservation number or vehicle registration is entered
                        by the operator. After OCR recognition, SmartPark
                        automatically retrieves the matching confirmed
                        reservation and checks the vehicle in.
                      </p>
                    </div>
                  </div>

                  {selectedReservation ? (
                    <div className="mt-3 rounded-xl border border-emerald-200 bg-white p-3">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-[10px] font-black uppercase tracking-wider text-emerald-700">
                            Reservation matched automatically
                          </p>
                          <p className="mt-1 text-lg font-black text-slate-900">
                            {selectedReservation.reservation_number}
                          </p>
                          <p className="mt-1 text-sm font-bold text-slate-600">
                            {selectedReservation.vehicle_registration}
                          </p>
                        </div>
                        <CheckCircle2 className="text-emerald-600" size={22} />
                      </div>

                      <div className="mt-4 grid gap-2 text-xs text-slate-500 sm:grid-cols-3">
                        <span>Bay #{selectedReservation.parking_bay_id}</span>
                        <span>
                          From{" "}
                          {formatDateTime(selectedReservation.reserved_from)}
                        </span>
                        <span>
                          Until{" "}
                          {formatDateTime(selectedReservation.reserved_until)}
                        </span>
                      </div>

                      <p className="mt-4 text-xs font-bold text-emerald-700">
                        Parking session creation/check-in is being handled
                        automatically by SmartPark.
                      </p>
                    </div>
                  ) : (
                    <div className="mt-3 rounded-xl border border-emerald-200/80 bg-white/80 p-3 text-xs font-semibold leading-5 text-emerald-800">
                      Awaiting ANPR recognition. Once the plate is recognized,
                      SmartPark will retrieve the reservation record, validate
                      it and automatically create the parking session.
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-start gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                  <ArrowUpFromLine size={19} />
                </span>
                <div>
                  <h2 className="text-sm font-black text-slate-900">
                    Exit Detection
                  </h2>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    Detect the vehicle's plate at the exit and locate its
                    parking session.
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => void handleExitDetection()}
                disabled={!detectedPlate || submitting}
                className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-slate-950 px-4 py-2.5 text-sm font-black text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? (
                  <Loader2 size={17} className="animate-spin" />
                ) : (
                  <ScanLine size={17} />
                )}
                Detect Vehicle at Exit
              </button>

              {exitSession && (
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[10px] font-black uppercase tracking-wider text-slate-500">
                        Located Session
                      </p>
                      <p className="mt-1 text-lg font-black text-slate-900">
                        {exitSession.session_number}
                      </p>
                    </div>

                    <span
                      className={`rounded-full px-2.5 py-1 text-[10px] font-black uppercase tracking-wider ${
                        isCompletedAwaitingExit(exitSession)
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-amber-100 text-amber-700"
                      }`}
                    >
                      {exitSession.status}
                    </span>
                  </div>

                  <div className="mt-3 grid grid-cols-2 gap-2">
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Vehicle
                      </p>
                      <p className="mt-1 text-sm font-black text-slate-800">
                        {exitSession.vehicle_registration}
                      </p>
                    </div>

                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                        Entry
                      </p>
                      <p className="mt-1 text-sm font-black text-slate-800">
                        {formatDateTime(exitSession.entry_time)}
                      </p>
                    </div>
                  </div>

                  {!isCompletedAwaitingExit(exitSession) && (
                    <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-2.5 text-xs leading-5 text-amber-800">
                      <Clock3 size={15} className="mt-0.5 shrink-0" />
                      <span>
                        Payment must be settled first. The ANPR simulator does
                        not bypass the payment workflow.
                      </span>
                    </div>
                  )}

                  <button
                    type="button"
                    onClick={() => void handlePhysicalExit()}
                    disabled={
                      !isCompletedAwaitingExit(exitSession) || submitting
                    }
                    className="mt-3 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-black text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {submitting ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <ArrowUpFromLine size={16} />
                    )}
                    Record ANPR Physical Exit
                  </button>
                </div>
              )}
            </div>
          )}
        </section>
      </div>

      {/* Result */}
      {(entrySession || exitSession) && (
        <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex items-start gap-3">
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
              <CheckCircle2 size={19} />
            </span>

            <div>
              <h2 className="text-sm font-black text-slate-900">
                SmartPark Session Result
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                This confirms what the ANPR simulator has handed to the parking
                session workflow.
                {selectedReservation
                  ? " Reservation admission was selected."
                  : ""}
              </p>
            </div>
          </div>

          <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl bg-slate-50 p-3">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-500">
                <CarFront size={14} />
                Vehicle
              </div>
              <p className="mt-1.5 text-sm font-black text-slate-900">
                {entrySession?.vehicle_registration ??
                  exitSession?.vehicle_registration ??
                  "—"}
              </p>
            </div>

            <div className="rounded-xl bg-slate-50 p-3">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-500">
                <ScanLine size={14} />
                Entry Method
              </div>
              <p className="mt-1.5 text-sm font-black text-slate-900">
                {entrySession?.entry_method ?? exitSession?.entry_method ?? "—"}
              </p>
            </div>

            <div className="rounded-xl bg-slate-50 p-3">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-500">
                <MapPin size={14} />
                Parking Bay
              </div>
              <p className="mt-1.5 text-sm font-black text-slate-900">
                {entrySession
                  ? getBayLabel(
                      bays.find(
                        (bay) => bay.id === entrySession.parking_bay_id,
                      ) ?? {
                        id: entrySession.parking_bay_id,
                        zone_id: 0,
                        bay_number: `#${entrySession.parking_bay_id}`,
                        code: `#${entrySession.parking_bay_id}`,
                        bay_type: "",
                        vehicle_type: "",
                        size: "",
                        is_accessible: false,
                        is_ev_charging: false,
                        is_vip: false,
                        is_reservable: false,
                        is_active: true,
                        sort_order: 0,
                        created_at: "",
                        updated_at: "",
                      },
                    )
                  : exitSession
                    ? `Bay #${exitSession.parking_bay_id}`
                    : "—"}
              </p>
            </div>

            <div className="rounded-xl bg-slate-50 p-3">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-500">
                <Clock3 size={14} />
                Status
              </div>
              <p className="mt-1.5 text-sm font-black text-slate-900">
                {entrySession?.status ?? exitSession?.status ?? "—"}
              </p>
            </div>
          </div>
        </section>
      )}

      {/* Operational note */}
      <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
        <div className="flex items-start gap-3">
          <ShieldCheck size={17} className="mt-0.5 shrink-0 text-slate-500" />
          <p className="text-xs leading-5 text-slate-500">
            <strong className="text-slate-700">Model A — Camera OCR:</strong>{" "}
            the browser captures a real camera frame and securely sends it to
            the SmartPark ANPR API, where PaddleOCR performs detection,
            recognition, preprocessing and Kenyan registration validation. It
            remains a simulator rather than a dedicated vehicle-mounted ANPR
            camera, so recognition quality depends on lighting, focus, distance,
            contrast and the quality of the registration presented to the
            camera.
          </p>
        </div>
      </div>
    </div>
  );
}
