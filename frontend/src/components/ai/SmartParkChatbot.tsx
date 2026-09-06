import { FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { aiApi, getApiErrorMessage } from "../../api";
import { useAuth } from "../../auth/AuthContext";

// ==========================================================
// Types
// ==========================================================

type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  paymentReservationNumber?: string;
};

type Coordinates = {
  latitude: number;
  longitude: number;
};

type LocationStatus =
  | "idle"
  | "requesting"
  | "available"
  | "denied"
  | "unavailable";

type ForecastPresentation = {
  facilityName: string;
  facilityCode?: string;
  predictedOccupancy: number;
  predictionTimestamp?: string;
  forecastTimestamp?: string;
  forecastHorizon?: string;
  modelCandidate?: string;
  observationCount?: string;
};

// ==========================================================
// Assistant response presentation helpers
// ==========================================================

const cleanMarkdownValue = (value: string): string =>
  value.replace(/\*\*/g, "").replace(/__/g, "").replace(/`/g, "").trim();

const extractLabeledValue = (
  content: string,
  label: string,
): string | undefined => {
  const escapedLabel = label.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = content.match(
    new RegExp(
      `(?:^|\\n)\\s*[-*]\\s*\*?\\*?${escapedLabel}\\*?\\*?\\s*[:：]\\s*([^\\n\\r]+)`,
      "i",
    ),
  );

  return match?.[1] ? cleanMarkdownValue(match[1]) : undefined;
};

const parseForecastPresentation = (
  content: string,
): ForecastPresentation | null => {
  const normalized = content.replace(/\r/g, "");

  const hasForecastSignals =
    /parking forecasting portal|production forecasting engine result|predicted occupancy|prediction timestamp|forecast timestamp|forecast horizon|model candidate|observation count/i.test(
      normalized,
    );

  if (!hasForecastSignals) {
    return null;
  }

  const occupancyMatch = normalized.match(
    /(?:predicted occupancy(?: rate| percentage)?|occupancy)\s*[:：]?\s*(\d+(?:\.\d+)?)\s*%/i,
  );

  if (!occupancyMatch) {
    return null;
  }

  let facilityName: string | undefined;
  let facilityCode: string | undefined;

  const portalHeadingMatch = normalized.match(
    /^#{1,6}\s*Parking Forecasting Portal\s*[—-]\s*(.+?)(?:\s*\(([^)]+)\))?\s*$/im,
  );

  if (portalHeadingMatch) {
    facilityName = cleanMarkdownValue(portalHeadingMatch[1]);
    facilityCode = portalHeadingMatch[2]?.trim();
  }

  const facilityLineMatch = normalized.match(
    /^\s*[-*]?\s*\*?\*?Facility\*?\*?\s*[:：]\s*(.+?)(?:\s*[—-]\s*([A-Z0-9][A-Z0-9_-]{2,}))?\s*$/im,
  );

  if (facilityLineMatch) {
    facilityName = cleanMarkdownValue(facilityLineMatch[1]);
    facilityCode = facilityLineMatch[2]?.trim() || facilityCode;
  }

  return {
    facilityName: facilityName || "SmartPark Facility",
    facilityCode,
    predictedOccupancy: Number(occupancyMatch[1]),
    predictionTimestamp: extractLabeledValue(
      normalized,
      "Prediction timestamp",
    ),
    forecastTimestamp: extractLabeledValue(normalized, "Forecast timestamp"),
    forecastHorizon: extractLabeledValue(normalized, "Forecast horizon"),
    modelCandidate: extractLabeledValue(normalized, "Model candidate"),
    observationCount: extractLabeledValue(normalized, "Observation count"),
  };
};

const formatForecastTimestamp = (value?: string): string | null => {
  if (!value) return null;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;

  return new Intl.DateTimeFormat("en-KE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Africa/Nairobi",
    timeZoneName: "short",
  }).format(date);
};

const getForecastStatus = (occupancy: number) => {
  if (occupancy >= 90) {
    return {
      label: "Very High",
      description: "Parking is expected to be highly occupied.",
      badgeClassName: "border-red-200 bg-red-50 text-red-700",
      accentClassName: "text-red-600",
      meterClassName: "bg-red-500",
    };
  }

  if (occupancy >= 75) {
    return {
      label: "High",
      description: "Parking is expected to be busy.",
      badgeClassName: "border-amber-200 bg-amber-50 text-amber-700",
      accentClassName: "text-amber-600",
      meterClassName: "bg-amber-500",
    };
  }

  if (occupancy >= 50) {
    return {
      label: "Moderate",
      description: "Moderate parking demand is expected.",
      badgeClassName: "border-blue-200 bg-blue-50 text-blue-700",
      accentClassName: "text-blue-600",
      meterClassName: "bg-blue-500",
    };
  }

  return {
    label: "Low",
    description: "Lower parking demand is expected.",
    badgeClassName: "border-emerald-200 bg-emerald-50 text-emerald-700",
    accentClassName: "text-emerald-600",
    meterClassName: "bg-emerald-500",
  };
};

const renderForecastCard = (forecast: ForecastPresentation) => {
  const status = getForecastStatus(forecast.predictedOccupancy);
  const predictionTime = formatForecastTimestamp(forecast.predictionTimestamp);
  const forecastTime = formatForecastTimestamp(forecast.forecastTimestamp);

  const metadata = [
    predictionTime ? ["Prediction time", predictionTime] : null,
    forecastTime ? ["Forecast time", forecastTime] : null,
    forecast.forecastHorizon ? ["Horizon", forecast.forecastHorizon] : null,
    forecast.modelCandidate ? ["Model", forecast.modelCandidate] : null,
    forecast.observationCount
      ? ["Observations", forecast.observationCount]
      : null,
  ].filter(Boolean) as [string, string][];

  return (
    <article className="w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-gradient-to-br from-slate-50 via-white to-blue-50/60 px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-[#0b2a4a] text-white">
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  className="h-4 w-4"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 19V9m5 10V5m5 14v-7m5 7V3"
                  />
                </svg>
              </span>
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
                Occupancy Forecast
              </span>
            </div>
            <h3 className="truncate text-sm font-semibold text-slate-900">
              {forecast.facilityName}
            </h3>
            {forecast.facilityCode && (
              <p className="mt-0.5 text-[11px] font-medium text-slate-500">
                {forecast.facilityCode}
              </p>
            )}
          </div>

          <span
            className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${status.badgeClassName}`}
          >
            {status.label}
          </span>
        </div>
      </div>

      <div className="px-4 py-4">
        <div className="flex items-end justify-between gap-4">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wide leading-5 text-slate-400">
              Predictedr occupancy
            </p>
            <div
              className={`mt-1 text-4xl font-bold tracking-tight ${status.accentClassName}`}
            >
              {forecast.predictedOccupancy.toFixed(1)}%
            </div>
          </div>

          <div className="max-w-[125px] pb-1 text-right">
            <p className="text-[11px] font-medium text-slate-500">
              {forecast.forecastHorizon
                ? `${forecast.forecastHorizon} forecast`
                : "Production forecast"}
            </p>
            <p className="mt-1 text-[10px] leading-4 text-slate-400">
              {status.description}
            </p>
          </div>
        </div>

        <div className="mt-4">
          <div className="h-2 overflow-hidden rounded-full bg-slate-100">
            <div
              className={`h-full rounded-full ${status.meterClassName}`}
              style={{
                width: `${Math.min(Math.max(forecast.predictedOccupancy, 0), 100)}%`,
              }}
            />
          </div>
          <div className="mt-1.5 flex justify-between text-[9px] font-medium text-slate-400">
            <span>0%</span>
            <span>50%</span>
            <span>100%</span>
          </div>
        </div>

        {metadata.length > 0 && (
          <dl className="mt-4 grid grid-cols-2 gap-2">
            {metadata.map(([label, value]) => (
              <div
                key={label}
                className="rounded-xl border border-slate-100 bg-slate-50 px-3 py-2.5"
              >
                <dt className="text-[9px] font-semibold uppercase tracking-wide text-slate-400">
                  {label}
                </dt>
                <dd className="mt-1 break-words text-[11px] font-semibold text-slate-700">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        )}

        <div className="mt-3 flex items-center gap-1.5 border-t border-slate-100 pt-3 text-[9px] text-slate-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          Production model prediction
        </div>
      </div>
    </article>
  );
};

const parseReservationNumber = (content: string): string | undefined =>
  content.match(/\bRES-[A-Z0-9-]+\b/i)?.[0]?.toUpperCase();

const parseReservationFacility = (content: string): string | undefined =>
  extractLabeledValue(content, "Facility") ||
  content
    .match(/(?:parking facility|facility)\s*[:：-]\s*([^\n\r]+)/i)?.[1]
    ?.trim();

const parseReservationStatus = (content: string): string | undefined => {
  /*
   * "Not yet confirmed" / "payment is required" must remain CREATED.
   * Check the unpaid state before the generic "confirmed" match so the
   * reservation card does not incorrectly show a confirmed badge.
   */
  if (
    /not yet confirmed|not confirmed|awaiting payment|payment is required/i.test(
      content,
    )
  ) {
    return "Created";
  }

  if (/\bconfirmed\b/i.test(content)) return "Confirmed";
  if (/\bcreated\b/i.test(content)) return "Created";
  if (/\bcancelled\b/i.test(content)) return "Cancelled";
  if (/\bcompleted\b/i.test(content)) return "Completed";
  return undefined;
};

const renderInlineMarkdown = (text: string) => {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g);

  return parts.map((part, index) => {
    if (/^\*\*[^*]+\*\*$/.test(part)) {
      return (
        <strong key={index} className="font-semibold text-slate-900">
          {part.slice(2, -2)}
        </strong>
      );
    }
    if (/^`[^`]+`$/.test(part)) {
      return (
        <code
          key={index}
          className="rounded bg-slate-100 px-1.5 py-0.5 text-[0.9em] font-medium text-slate-700"
        >
          {part.slice(1, -1)}
        </code>
      );
    }
    if (/^\*[^*]+\*$/.test(part)) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    return <span key={index}>{part}</span>;
  });
};

const renderFriendlyMarkdown = (content: string) => {
  const lines = content.replace(/\r/g, "").split("\n");
  const elements: JSX.Element[] = [];
  let bulletItems: string[] = [];
  let numberedItems: string[] = [];

  const flushLists = () => {
    if (bulletItems.length > 0) {
      elements.push(
        <ul key={`ul-${elements.length}`} className="my-2 space-y-1.5 pl-4">
          {bulletItems.map((item, index) => (
            <li
              key={index}
              className="relative pl-1.5 leading-5 before:absolute before:-left-3 before:top-[0.55rem] before:h-1.5 before:w-1.5 before:rounded-full before:bg-slate-400"
            >
              {renderInlineMarkdown(item)}
            </li>
          ))}
        </ul>,
      );
      bulletItems = [];
    }

    if (numberedItems.length > 0) {
      elements.push(
        <ol
          key={`ol-${elements.length}`}
          className="my-2 space-y-1.5 list-decimal pl-5"
        >
          {numberedItems.map((item, index) => (
            <li key={index} className="pl-1 leading-5">
              {renderInlineMarkdown(item)}
            </li>
          ))}
        </ol>,
      );
      numberedItems = [];
    }
  };

  lines.forEach((rawLine, index) => {
    const line = rawLine.trim();

    if (!line) {
      flushLists();
      return;
    }

    const headingMatch = line.match(/^#{1,6}\s+(.+)$/);
    if (headingMatch) {
      flushLists();
      elements.push(
        <h3
          key={`heading-${index}`}
          className="mb-2 mt-1 text-sm font-semibold text-slate-900"
        >
          {renderInlineMarkdown(
            headingMatch[1].replace(
              /^\s*Parking Forecasting Portal\s*[—-]\s*/i,
              "",
            ),
          )}
        </h3>,
      );
      return;
    }

    const bulletMatch = line.match(/^[-*]\s+(.+)$/);
    if (bulletMatch) {
      numberedItems.length && flushLists();
      bulletItems.push(bulletMatch[1]);
      return;
    }

    const numberedMatch = line.match(/^\d+[.)]\s+(.+)$/);
    if (numberedMatch) {
      bulletItems.length && flushLists();
      numberedItems.push(numberedMatch[1]);
      return;
    }

    flushLists();

    elements.push(
      <p key={`paragraph-${index}`} className="my-1.5 leading-5">
        {renderInlineMarkdown(line)}
      </p>,
    );
  });

  flushLists();
  return <div className="text-sm leading-5 text-slate-700">{elements}</div>;
};

const renderReservationCard = (content: string) => {
  const reservationNumber = parseReservationNumber(content);
  if (!reservationNumber) return null;

  const facility = parseReservationFacility(content);
  const status = parseReservationStatus(content);

  return (
    <div className="mb-3 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="flex items-start justify-between gap-3 border-b border-slate-100 bg-gradient-to-br from-slate-50 via-white to-blue-50/50 px-4 py-3.5">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#0b2a4a] text-white">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                className="h-4 w-4"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3 7.5 12 4l9 3.5M4.5 8.5v8.5L12 20l7.5-3V8.5M8 6v8l4 2 4-2V6"
                />
              </svg>
            </span>
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
              Parking Reservation
            </span>
          </div>
          <p className="mt-2 text-sm font-semibold text-slate-900">
            {reservationNumber}
          </p>
          {facility && (
            <p className="mt-0.5 text-[11px] text-slate-500">
              {cleanMarkdownValue(facility)}
            </p>
          )}
        </div>

        {status && (
          <span
            className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${status === "Confirmed" ? "border-emerald-200 bg-emerald-50 text-emerald-700" : status === "Created" ? "border-amber-200 bg-amber-50 text-amber-700" : "border-slate-200 bg-slate-50 text-slate-600"}`}
          >
            {status}
          </span>
        )}
      </div>

      <div className="px-4 py-3 text-[11px] text-slate-500">
        {status === "Created"
          ? "Your reservation has been created and is awaiting payment confirmation."
          : status === "Confirmed"
            ? "Your reservation is confirmed."
            : "Your reservation details are shown below."}
      </div>
    </div>
  );
};

const isStructuredAssistantContent = (content: string): boolean => {
  try {
    return Boolean(
      parseForecastPresentation(content) || parseReservationNumber(content),
    );
  } catch (error) {
    console.error(
      "[SmartPark AI] Failed to classify assistant response:",
      error,
    );
    return false;
  }
};

const renderAssistantContent = (content: string) => {
  /*
   * Presentation must never be allowed to break the whole application.
   * If a response does not match one of the structured formats, or a
   * presentation parser encounters unexpected AI output, fall back to
   * the friendly Markdown renderer instead of throwing during render.
   */
  try {
    const forecast = parseForecastPresentation(content);

    if (forecast) {
      return renderForecastCard(forecast);
    }

    const reservationNumber = parseReservationNumber(content);
    if (reservationNumber) {
      return (
        <>
          {renderReservationCard(content)}
          {renderFriendlyMarkdown(content)}
        </>
      );
    }

    return renderFriendlyMarkdown(content);
  } catch (error) {
    console.error("[SmartPark AI] Failed to render assistant response:", error);

    return (
      <div className="whitespace-pre-wrap text-sm leading-6 text-slate-700">
        {content}
      </div>
    );
  }
};

// ==========================================================
// Component
// ==========================================================

export default function SmartParkChatbot() {
  // ----------------------------------------------------------
  // UI state
  // ----------------------------------------------------------

  const [isOpen, setIsOpen] = useState(false);

  /*
   * Show a welcome bubble when the authenticated
   * application first launches. The bubble is dismissed once
   * the customer opens the chatbot or closes the greeting.
   */
  const [showLaunchGreeting, setShowLaunchGreeting] = useState(true);

  const { user } = useAuth();

  const firstName = user?.first_name?.trim() || "there";

  const greetingTimeOfDay = (() => {
    const hour = new Date().getHours();

    if (hour < 12) {
      return "Good morning";
    }

    if (hour < 17) {
      return "Good afternoon";
    }

    return "Good evening";
  })();

  const launchGreeting = `${greetingTimeOfDay} ${firstName}, I'm SmartPark AI, your reliable SmartPark Assistant. How may I assist you today?`;

  const [input, setInput] = useState("");

  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 1,
      role: "assistant",
      content:
        "Hello! I'm SmartPark AI. I can help you find nearby parking, check availability, EV charging bays, facility information, and more.",
    },
  ]);

  const [isSending, setIsSending] = useState(false);

  // ----------------------------------------------------------
  // Reservation payment hand-off
  // ----------------------------------------------------------

  /*
   * A newly-created reservation remains CREATED until payment
   * succeeds. Keep its reservation number so an affirmative
   * "pay now" response can open the existing Reservations
   * payment modal for that exact booking.
   */
  const [pendingPaymentReservationNumber, setPendingPaymentReservationNumber] =
    useState<string | null>(null);

  const navigate = useNavigate();

  // ----------------------------------------------------------
  // Conversation state
  // ----------------------------------------------------------

  /*
   * OpenAI Responses API conversation continuity.
   *
   * The backend returns a response_id after every successful
   * message. That ID is sent back with the next message as
   * previous_response_id so SmartPark AI can remember the
   * conversation across separate HTTP requests.
   */
  const [previousResponseId, setPreviousResponseId] = useState<string | null>(
    null,
  );

  // ----------------------------------------------------------
  // Location state
  // ----------------------------------------------------------

  const [coordinates, setCoordinates] = useState<Coordinates | null>(null);

  const [locationStatus, setLocationStatus] = useState<LocationStatus>("idle");

  // ----------------------------------------------------------
  // Refs
  // ----------------------------------------------------------

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const inputRef = useRef<HTMLInputElement | null>(null);

  const chatWindowRef = useRef<HTMLDivElement | null>(null);

  // ----------------------------------------------------------
  // Automatically scroll to latest message
  // ----------------------------------------------------------

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({
      behavior: "smooth",
    });
  }, [messages, isSending]);

  // ----------------------------------------------------------
  // Focus input when chatbot opens
  // ----------------------------------------------------------

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const timer = window.setTimeout(() => {
      inputRef.current?.focus();
    }, 50);

    return () => {
      window.clearTimeout(timer);
    };
  }, [isOpen]);

  // ----------------------------------------------------------
  // Close/minimize when clicking outside the chatbot
  // ----------------------------------------------------------

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleOutsideClick = (event: MouseEvent) => {
      const target = event.target;

      if (!(target instanceof Node)) {
        return;
      }

      if (chatWindowRef.current && !chatWindowRef.current.contains(target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);

    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
    };
  }, [isOpen]);

  // ----------------------------------------------------------
  // Close/minimize with Escape key
  // ----------------------------------------------------------

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen]);

  // ----------------------------------------------------------
  // Request browser location
  // ----------------------------------------------------------

  const requestLocation = (): Promise<Coordinates | null> => {
    return new Promise((resolve) => {
      if (!navigator.geolocation) {
        setLocationStatus("unavailable");
        setCoordinates(null);
        resolve(null);
        return;
      }

      setLocationStatus("requesting");

      navigator.geolocation.getCurrentPosition(
        (position) => {
          const newCoordinates: Coordinates = {
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
          };

          setCoordinates(newCoordinates);
          setLocationStatus("available");

          resolve(newCoordinates);
        },
        () => {
          setCoordinates(null);
          setLocationStatus("denied");

          resolve(null);
        },
        {
          enableHighAccuracy: true,
          timeout: 10000,
          maximumAge: 300000,
        },
      );
    });
  };

  // ----------------------------------------------------------
  // Request location when chatbot opens
  // ----------------------------------------------------------

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    if (locationStatus === "idle") {
      void requestLocation();
    }
  }, [isOpen, locationStatus]);

  // ----------------------------------------------------------
  // Determine whether a message likely needs location
  // ----------------------------------------------------------

  const messageNeedsLocation = (message: string): boolean => {
    const normalizedMessage = message.trim().toLowerCase();

    const locationTerms = [
      "near me",
      "nearby",
      "nearest",
      "closest",
      "close to me",
      "around me",
      "my location",
      "where am i",
      "parking near",
      "parking close",
      "facility near",
      "facilities near",
      "ev charging near",
      "ev charger near",
    ];

    return locationTerms.some((term) => normalizedMessage.includes(term));
  };

  // ----------------------------------------------------------
  // Open existing reservation payment screen
  // ----------------------------------------------------------

  const handlePayAndConfirmReservation = (reservationNumber: string) => {
    setPendingPaymentReservationNumber(null);
    setIsOpen(false);

    navigate(
      `/reservations?payReservation=${encodeURIComponent(reservationNumber)}`,
    );
  };

  // ----------------------------------------------------------
  // Send message
  // ----------------------------------------------------------

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const trimmedMessage = input.trim();

    if (!trimmedMessage || isSending) {
      return;
    }

    const needsLocation = messageNeedsLocation(trimmedMessage);

    // ----------------------------------------------------------
    // Existing reservation -> payment hand-off
    // ----------------------------------------------------------

    /*
     * If the AI has just created a reservation and asked whether
     * the customer wants to pay, route an affirmative response
     * directly into the existing Reservations payment modal.
     */
    const normalizedMessage = trimmedMessage
      .toLowerCase()
      .replace(/[!?.,]/g, "")
      .trim();

    const affirmativePaymentResponse =
      /^(yes|yes please|please do|go ahead|proceed|pay now|yes pay now|pay|sure|okay|ok|yep|yeah|confirm|confirmed|let'?s pay|i want to pay)$/.test(
        normalizedMessage,
      );

    const negativePaymentResponse =
      /^(no|no thanks|not now|later|cancel)$/.test(normalizedMessage);

    if (pendingPaymentReservationNumber && affirmativePaymentResponse) {
      const reservationNumber = pendingPaymentReservationNumber;

      const userMessage: ChatMessage = {
        id: Date.now(),
        role: "user",
        content: trimmedMessage,
      };

      setMessages((previous) => [
        ...previous,
        userMessage,
        {
          id: Date.now() + 1,
          role: "assistant",
          content: `Absolutely. I'll open the payment screen for reservation ${reservationNumber} so you can complete the payment and confirm your booking.`,
          paymentReservationNumber: reservationNumber,
        },
      ]);

      setInput("");

      // Keep the payment action pending until the customer
      // explicitly clicks "Pay & Confirm Reservation".
      return;
    }

    if (pendingPaymentReservationNumber && negativePaymentResponse) {
      const userMessage: ChatMessage = {
        id: Date.now(),
        role: "user",
        content: trimmedMessage,
      };

      setMessages((previous) => [
        ...previous,
        userMessage,
        {
          id: Date.now() + 1,
          role: "assistant",
          content:
            "No problem. Your reservation remains created but is not yet confirmed. Payment is required to confirm it.",
        },
      ]);

      setInput("");
      setPendingPaymentReservationNumber(null);
      return;
    }

    const userMessage: ChatMessage = {
      id: Date.now(),
      role: "user",
      content: trimmedMessage,
    };

    setMessages((previous) => [...previous, userMessage]);

    setInput("");

    setIsSending(true);

    try {
      // ------------------------------------------------------
      // Location handling
      // ------------------------------------------------------

      // Location is requested ONLY when the user's question
      // actually requires it.
      //
      // The user never needs to enter coordinates manually.
      // ------------------------------------------------------

      let currentCoordinates = coordinates;

      if (needsLocation && !currentCoordinates) {
        currentCoordinates = await requestLocation();

        // ----------------------------------------------------
        // If location is required but unavailable, explain
        // this naturally to the user and do not send an
        // incomplete nearest-location request to the backend.
        // ----------------------------------------------------

        if (!currentCoordinates) {
          const locationMessage =
            locationStatus === "unavailable"
              ? "I can't access your current location because location services aren't supported by this browser.\n\nYou can still ask me about specific SmartPark facilities, available spaces, EV charging bays, and other parking information."
              : "I need access to your current location to find the nearest SmartPark facilities. Please allow location access in your browser and try again.\n\nYou can still ask me about specific SmartPark facilities, available spaces, EV charging bays, and other parking information without sharing your location.";

          const assistantMessage: ChatMessage = {
            id: Date.now() + 1,
            role: "assistant",
            content: locationMessage,
          };

          setMessages((previous) => [...previous, assistantMessage]);

          return;
        }
      }

      // ------------------------------------------------------
      // Send request to SmartPark AI
      // ------------------------------------------------------

      const response = await aiApi.chat({
        message: trimmedMessage,
        latitude: currentCoordinates?.latitude ?? null,
        longitude: currentCoordinates?.longitude ?? null,
        previous_response_id: previousResponseId,
      });

      // ------------------------------------------------------
      // Preserve conversation continuity
      // ------------------------------------------------------

      /*
       * Store the response ID returned by the backend.
       *
       * The next user message will send this ID as
       * previous_response_id, allowing the backend/OpenAI
       * Responses API to retain the conversation context.
       */
      setPreviousResponseId(response.response_id);

      /*
       * Capture the reservation number from a newly-created
       * reservation. The reservation is CREATED at this point,
       * not CONFIRMED, so make the payment requirement explicit
       * to the customer and offer to open the existing payment
       * screen.
       */
      const reservationMatch = response.message.match(/\bRES-[A-Z0-9-]+\b/i);

      let assistantContent = response.message;

      /*
       * Only attach the payment hand-off to a response that actually
       * represents a newly-created, unpaid reservation.
       *
       * Do NOT trigger this merely because an existing reservation
       * number appears in the AI response. This is important after
       * successful payment, when the AI may mention the reservation
       * number while confirming that the booking is already paid/
       * confirmed.
       */
      /*
       * Do not treat "reservation is not yet confirmed" as a successful
       * payment/confirmation response. The negative/unpaid state must win.
       */
      const indicatesPaymentSuccess =
        /payment (went through|was successful|successful)|successfully paid|paid successfully|payment.*confirmed|reservation.*confirmed|booking.*confirmed|all set/i.test(
          response.message,
        );

      const isAwaitingPayment =
        /not yet confirmed|not confirmed|awaiting payment|payment is required/i.test(
          response.message,
        );

      const isPaymentSuccessResponse =
        indicatesPaymentSuccess && !isAwaitingPayment;

      const isNewReservationResponse =
        reservationMatch &&
        /reservation.*(created|successfully)|successfully.*reservation|reservation.*(has been|was) created/i.test(
          response.message,
        ) &&
        !isPaymentSuccessResponse;

      if (isNewReservationResponse && reservationMatch) {
        const reservationNumber = reservationMatch[0].toUpperCase();

        setPendingPaymentReservationNumber(reservationNumber);

        if (
          !/not yet confirmed|payment is required|pay now|awaiting payment/i.test(
            response.message,
          )
        ) {
          assistantContent =
            `${response.message}\n\n` +
            "Please note: your reservation is not yet confirmed. " +
            "Payment is required to confirm your booking. Would you like to pay now?";
        }
      }

      const assistantMessage: ChatMessage = {
        id: Date.now() + 1,
        role: "assistant",
        content: assistantContent,
        paymentReservationNumber:
          isNewReservationResponse && reservationMatch
            ? reservationMatch[0].toUpperCase()
            : undefined,
      };

      setMessages((previous) => [...previous, assistantMessage]);
    } catch (error) {
      const assistantMessage: ChatMessage = {
        id: Date.now() + 1,
        role: "assistant",
        content:
          getApiErrorMessage(error) ||
          "I'm sorry, I couldn't process that request right now.",
      };

      setMessages((previous) => [...previous, assistantMessage]);
    } finally {
      setIsSending(false);

      setTimeout(() => {
        inputRef.current?.focus();
      }, 50);
    }
  };

  // ----------------------------------------------------------
  // Location status text
  // ----------------------------------------------------------

  const getLocationText = (): string => {
    switch (locationStatus) {
      case "requesting":
        return "Getting your location…";

      case "available":
        return "Location Enabled";

      case "denied":
        return "Location unavailable";

      case "unavailable":
        return "Location not supported";

      default:
        return "Location available when needed";
    }
  };

  // ----------------------------------------------------------
  // Location icon
  // ----------------------------------------------------------

  const getLocationIcon = (): string => {
    switch (locationStatus) {
      case "available":
        return "●";

      case "requesting":
        return "◌";

      default:
        return "○";
    }
  };

  // ----------------------------------------------------------
  // Quick prompts
  // ----------------------------------------------------------

  const sendQuickPrompt = (prompt: string) => {
    if (isSending) {
      return;
    }

    setInput(prompt);

    setTimeout(() => {
      inputRef.current?.focus();
    }, 50);
  };

  // ----------------------------------------------------------
  // Clear chat history
  // ----------------------------------------------------------

  const handleClearChat = () => {
    const confirmed = window.confirm(
      "Clear this conversation?\n\nAll messages in the current chat will be removed.",
    );

    if (!confirmed) {
      return;
    }

    // --------------------------------------------------------
    // Reset both visible messages AND OpenAI conversation state.
    // --------------------------------------------------------

    setMessages([
      {
        id: Date.now(),
        role: "assistant",
        content:
          "Hello! I'm SmartPark AI. I can help you find nearby parking, check availability, EV charging bays, facility information, and more.",
      },
    ]);

    setPreviousResponseId(null);
    setPendingPaymentReservationNumber(null);

    setInput("");

    setTimeout(() => {
      inputRef.current?.focus();
    }, 50);
  };

  // ----------------------------------------------------------
  // Minimize / close
  // ----------------------------------------------------------

  const minimizeChat = () => {
    setIsOpen(false);
  };

  const openChat = () => {
    setShowLaunchGreeting(false);
    setIsOpen(true);
  };

  // ----------------------------------------------------------
  // Render
  // ----------------------------------------------------------

  return (
    <>
      {/* ======================================================
          Floating Launcher + Launch Greeting
          ====================================================== */}

      {!isOpen && (
        <div className="fixed bottom-6 right-6 z-50 flex items-end gap-2">
          {showLaunchGreeting && (
            <div className="relative mb-1 flex max-w-[min(360px,calc(100vw-110px))] items-start gap-2">
              <button
                type="button"
                onClick={() => setShowLaunchGreeting(false)}
                aria-label="Dismiss SmartPark AI greeting"
                title="Dismiss"
                className="
                  mt-2
                  flex
                  h-7
                  w-7
                  shrink-0
                  items-center
                  justify-center
                  rounded-full
                  bg-slate-800
                  text-white
                  shadow-md
                  transition
                  hover:bg-slate-900
                  focus:outline-none
                  focus:ring-4
                  focus:ring-slate-200
                "
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2.2"
                  className="h-4 w-4"
                  aria-hidden="true"
                >
                  <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
                </svg>
              </button>

              <button
                type="button"
                onClick={openChat}
                aria-label="Open SmartPark AI greeting"
                className="
                  relative
                  rounded-xl
                  bg-slate-800
                  px-4
                  py-3
                  text-left
                  text-xs
                  font-semibold
                  leading-5
                  text-white
                  shadow-[0_8px_24px_rgba(15,23,42,0.22)]
                  transition
                  duration-200
                  hover:bg-slate-900
                  focus:outline-none
                  focus:ring-4
                  focus:ring-slate-200
                "
              >
                {launchGreeting}

                <span
                  className="
                    absolute
                    -right-2
                    bottom-3
                    h-0
                    w-0
                    border-y-[7px]
                    border-l-[9px]
                    border-y-transparent
                    border-l-slate-800
                  "
                  aria-hidden="true"
                />
              </button>
            </div>
          )}

          <button
            type="button"
            onClick={openChat}
            aria-label="Open SmartPark AI"
            title="Open SmartPark AI"
            className="
              relative
              flex
              h-14
              w-14
              shrink-0
              items-center
              justify-center
              rounded-full
              border-4
              border-white
              bg-white
              text-[#0b2a4a]
              shadow-[0_8px_30px_rgba(0,0,0,0.25)]
              transition
              duration-200
              hover:scale-105
              focus:outline-none
              focus:ring-4
              focus:ring-blue-200
            "
          >
            <span
              className="
                flex
                h-11
                w-11
                items-center
                justify-center
                rounded-full
                bg-[#0b2a4a]
                text-white
              "
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                className="h-7 w-7"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M8 10h8M8 14h5"
                />

                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M20 11.5c0 4.142-3.582 7.5-8 7.5-1.018 0-1.988-.17-2.875-.48L5 20l1.04-2.96C4.78 15.67 4 13.67 4 11.5 4 7.358 7.582 4 12 4s8 3.358 8 7.5Z"
                />
              </svg>
            </span>

            <span
              className="
                absolute
                right-0
                top-0
                h-3.5
                w-3.5
                rounded-full
                border-2
                border-white
                bg-emerald-500
              "
              aria-hidden="true"
            />

            <span
              className="
                absolute
                -bottom-1
                -right-1
                flex
                h-7
                w-7
                items-center
                justify-center
                rounded-full
                border
                border-slate-200
                bg-slate-100
                text-slate-700
                shadow-md
              "
              aria-hidden="true"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                className="h-4 w-4"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="m6 15 6-6 6 6"
                />
              </svg>
            </span>
          </button>
        </div>
      )}

      {/* ======================================================
          Chat Window
          ====================================================== */}

      {isOpen && (
        <div
          ref={chatWindowRef}
          className="
            fixed
            bottom-5
            right-5
            z-50
            flex
            h-[min(680px,calc(100vh-40px))]
            w-[min(420px,calc(100vw-40px))]
            flex-col
            overflow-hidden
            rounded-2xl
            border
            border-slate-200
            bg-white
            shadow-[0_20px_60px_rgba(15,23,42,0.25)]
          "
        >
          {/* ==================================================
              Header
              ================================================== */}

          <div
            className="
              flex
              items-center
              justify-between
              bg-[#0b2a4a]
              px-5
              py-4
              text-white
            "
          >
            <div className="flex items-center gap-3">
              <div
                className="
                  flex
                  h-10
                  w-10
                  items-center
                  justify-center
                  rounded-xl
                  bg-white/10
                "
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  className="h-6 w-6"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M8 10h8M8 14h5"
                  />

                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M20 11.5c0 4.142-3.582 7.5-8 7.5-1.018 0-1.988-.17-2.875-.48L5 20l1.04-2.96C4.78 15.67 4 13.67 4 11.5 4 7.358 7.582 4 12 4s8 3.358 8 7.5Z"
                  />
                </svg>
              </div>

              <div>
                <div className="text-sm font-semibold">SmartPark AI</div>

                <div className="mt-0.5 flex items-center gap-1.5 text-xs text-blue-100">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  You reliable Parking Assistant
                </div>
              </div>
            </div>

            {/* ==================================================
                Header Controls
                ================================================== */}

            <div className="flex items-center gap-1">
              {/* Clear Chat */}

              <button
                type="button"
                onClick={handleClearChat}
                aria-label="Clear chat history"
                title="Clear chat"
                className="
                  rounded-lg
                  p-2
                  text-white/80
                  transition
                  hover:bg-white/10
                  hover:text-white
                  focus:outline-none
                "
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  className="h-5 w-5"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M4 7h16"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M10 11v6M14 11v6"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M6 7l1 13h10l1-13"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M9 7V4h6v3"
                  />
                </svg>
              </button>

              {/* Minimize */}

              <button
                type="button"
                onClick={minimizeChat}
                aria-label="Minimize SmartPark AI"
                title="Minimize"
                className="
                  rounded-lg
                  p-2
                  text-white/80
                  transition
                  hover:bg-white/10
                  hover:text-white
                  focus:outline-none
                "
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="h-5 w-5"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M5 12h14"
                  />
                </svg>
              </button>

              {/* Close */}

              <button
                type="button"
                onClick={minimizeChat}
                aria-label="Close SmartPark AI"
                title="Close"
                className="
                  rounded-lg
                  p-2
                  text-white/80
                  transition
                  hover:bg-white/10
                  hover:text-white
                  focus:outline-none
                "
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="h-5 w-5"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M6 6l12 12M18 6L6 18"
                  />
                </svg>
              </button>
            </div>
          </div>

          {/* ==================================================
              Location Status
              ================================================== */}

          <div
            className="
              flex
              items-center
              justify-between
              border-b
              border-slate-100
              bg-slate-50
              px-4
              py-2.5
            "
          >
            <div className="flex items-center gap-2">
              <span
                className={`
                  text-xs
                  ${
                    locationStatus === "available"
                      ? "text-emerald-500"
                      : locationStatus === "requesting"
                        ? "text-blue-500"
                        : "text-slate-400"
                  }
                `}
              >
                {getLocationIcon()}
              </span>

              <span className="text-xs text-slate-600">
                {getLocationText()}
              </span>
            </div>

            {(locationStatus === "denied" ||
              locationStatus === "unavailable") && (
              <button
                type="button"
                onClick={() => void requestLocation()}
                className="
                  text-xs
                  font-medium
                  text-blue-600
                  hover:text-blue-800
                "
              >
                Try again
              </button>
            )}
          </div>

          {/* ==================================================
              Messages
              ================================================== */}

          <div
            className="
              flex-1
              space-y-4
              overflow-y-auto
              bg-slate-50
              px-4
              py-5
            "
          >
            {messages.map((message) => (
              <div
                key={message.id}
                className={`
                  flex
                  ${message.role === "user" ? "justify-end" : "justify-start"}
                `}
              >
                <div
                  className={`
                    ${
                      message.role === "assistant"
                        ? isStructuredAssistantContent(message.content)
                          ? "w-[min(100%,380px)] max-w-[98%]"
                          : "max-w-[94%] rounded-bl-md border border-slate-200 bg-white px-4 py-3 text-slate-700 shadow-sm"
                        : "max-w-[84%] rounded-br-md bg-[#0b2a4a] px-4 py-3 text-white"
                    }
                    rounded-2xl
                    text-sm
                    leading-6
                  `}
                >
                  {message.role === "assistant" ? (
                    renderAssistantContent(message.content)
                  ) : (
                    <div className="whitespace-pre-wrap">{message.content}</div>
                  )}

                  {message.role === "assistant" &&
                    message.paymentReservationNumber && (
                      <button
                        type="button"
                        onClick={() =>
                          handlePayAndConfirmReservation(
                            message.paymentReservationNumber!,
                          )
                        }
                        className="
                          mt-3
                          flex
                          w-full
                          items-center
                          justify-center
                          gap-2
                          rounded-xl
                          bg-[#0b2a4a]
                          px-4
                          py-2.5
                          text-xs
                          font-semibold
                          text-white
                          shadow-sm
                          transition
                          hover:bg-[#123b63]
                          focus:outline-none
                          focus:ring-4
                          focus:ring-blue-100
                        "
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          strokeWidth="1.8"
                          className="h-4 w-4"
                        >
                          <rect x="3" y="5" width="18" height="14" rx="2" />
                          <path strokeLinecap="round" d="M3 10h18M7 15h3" />
                        </svg>
                        Pay & Confirm Reservation
                      </button>
                    )}
                </div>
              </div>
            ))}

            {/* =================================================
                Typing indicator
                ================================================= */}

            {isSending && (
              <div className="flex justify-start">
                <div
                  className="
                    rounded-2xl
                    rounded-bl-md
                    border
                    border-slate-200
                    bg-white
                    px-4
                    py-3
                    shadow-sm
                  "
                >
                  <div className="flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" />

                    <span
                      className="
                        h-1.5
                        w-1.5
                        animate-bounce
                        rounded-full
                        bg-slate-400
                        [animation-delay:120ms]
                      "
                    />

                    <span
                      className="
                        h-1.5
                        w-1.5
                        animate-bounce
                        rounded-full
                        bg-slate-400
                        [animation-delay:240ms]
                      "
                    />
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* ==================================================
              Quick prompts
              ================================================== */}

          <div
            className="
              border-t
              border-slate-100
              bg-white
              px-4
              py-3
            "
          >
            <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-slate-400">
              Quick questions
            </div>

            <div className="flex gap-2 overflow-x-auto pb-1">
              <button
                type="button"
                onClick={() =>
                  sendQuickPrompt("What is the nearest parking facility to me?")
                }
                className="
                  whitespace-nowrap
                  rounded-full
                  border
                  border-slate-200
                  bg-white
                  px-3
                  py-1.5
                  text-xs
                  font-medium
                  text-slate-600
                  transition
                  hover:border-blue-200
                  hover:bg-blue-50
                  hover:text-blue-700
                "
              >
                Nearest parking
              </button>

              <button
                type="button"
                onClick={() =>
                  sendQuickPrompt(
                    "What parking facilities are currently available?",
                  )
                }
                className="
                  whitespace-nowrap
                  rounded-full
                  border
                  border-slate-200
                  bg-white
                  px-3
                  py-1.5
                  text-xs
                  font-medium
                  text-slate-600
                  transition
                  hover:border-blue-200
                  hover:bg-blue-50
                  hover:text-blue-700
                "
              >
                Available parking
              </button>

              <button
                type="button"
                onClick={() =>
                  sendQuickPrompt("Are there EV charging bays near me?")
                }
                className="
                  whitespace-nowrap
                  rounded-full
                  border
                  border-slate-200
                  bg-white
                  px-3
                  py-1.5
                  text-xs
                  font-medium
                  text-slate-600
                  transition
                  hover:border-blue-200
                  hover:bg-blue-50
                  hover:text-blue-700
                "
              >
                EV charging
              </button>
            </div>
          </div>

          {/* ==================================================
              Input
              ================================================== */}

          <form
            onSubmit={handleSubmit}
            className="
              border-t
              border-slate-200
              bg-white
              p-3
            "
          >
            <div
              className="
                flex
                items-center
                gap-2
                rounded-xl
                border
                border-slate-200
                bg-slate-50
                p-1.5
                transition
                focus-within:border-blue-300
                focus-within:ring-2
                focus-within:ring-blue-100
              "
            >
              <input
                ref={inputRef}
                type="text"
                value={input}
                onChange={(event) => setInput(event.target.value)}
                disabled={isSending}
                placeholder="Ask SmartPark AI…"
                maxLength={4000}
                className="
                  min-w-0
                  flex-1
                  bg-transparent
                  px-3
                  py-2
                  text-sm
                  text-slate-700
                  outline-none
                  placeholder:text-slate-400
                  disabled:cursor-not-allowed
                  disabled:opacity-60
                "
              />

              <button
                type="submit"
                disabled={isSending || !input.trim()}
                aria-label="Send message"
                className="
                  flex
                  h-9
                  w-9
                  shrink-0
                  items-center
                  justify-center
                  rounded-lg
                  bg-[#0b2a4a]
                  text-white
                  transition
                  hover:bg-[#123b63]
                  disabled:cursor-not-allowed
                  disabled:opacity-40
                "
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="h-4 w-4"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M22 2 11 13"
                  />

                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="m22 2-7 20-4-9-9-4 20-7Z"
                  />
                </svg>
              </button>
            </div>

            <div className="mt-2 text-center text-[10px] text-slate-400">
              SmartPark AI uses your location only when you allow browser
              location access.
            </div>
          </form>
        </div>
      )}
    </>
  );
}
