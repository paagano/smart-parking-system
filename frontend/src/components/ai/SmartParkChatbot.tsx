import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { aiApi, api, getApiErrorMessage } from "../../api";
import { useAuth } from "../../auth/AuthContext";

// ==========================================================
// Types
// ==========================================================

interface SmartParkSpeechRecognitionEvent extends Event {
  results: SpeechRecognitionResultList;
  resultIndex: number;
}

interface SmartParkSpeechRecognitionErrorEvent extends Event {
  error: string;
  message?: string;
}

interface SmartParkSpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onstart: ((event: Event) => void) | null;
  onend: ((event: Event) => void) | null;
  onresult: ((event: SmartParkSpeechRecognitionEvent) => void) | null;
  onerror: ((event: SmartParkSpeechRecognitionErrorEvent) => void) | null;
}

interface SmartParkSpeechRecognitionConstructor {
  new (): SmartParkSpeechRecognitionInstance;
}

declare global {
  interface Window {
    SpeechRecognition?: SmartParkSpeechRecognitionConstructor;
    webkitSpeechRecognition?: SmartParkSpeechRecognitionConstructor;
  }
}

type InteractionMode = "text" | "voice";

type RealtimeToolCallEvent = {
  type: "response.function_call_arguments.done";
  call_id: string;
  name: string;
  arguments: string;
};

type RealtimeTranscriptEvent = {
  type: string;
  transcript?: string;
  item_id?: string;
  delta?: string;
};

type RealtimeErrorEvent = {
  type: "error";
  error?: {
    message?: string;
    code?: string;
  };
};

type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  paymentReservationNumber?: string;
  paymentSessionId?: number;
  attachmentName?: string;
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

type ChatAttachment = {
  file: File;
  name: string;
  size: number;
};

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

type NavigationPresentation = {
  facilityName: string;
  facilityCode?: string;
  address?: string;
  navigationUrl: string;
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
    /^#{1,6}\s*Parking Forecasting\s*[—-]\s*(.+?)(?:\s*\(([^)]+)\))?\s*$/im,
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

const parseNavigationPresentation = (
  content: string,
  originCoordinates?: Coordinates | null,
): NavigationPresentation | null => {
  /*
   * SmartPark may return a complete Google Maps Directions URL, but it may
   * also return only the destination coordinates and tell the customer to
   * "open your preferred maps app".
   *
   * The latter is what the production response can currently look like:
   *
   *   Two Rivers Mall is at Limuru Road, Nairobi.
   *   You're currently near -1.203129, 36.777630.
   *   Open your preferred maps app and navigate to:
   *   Two Rivers Mall
   *   Coordinates: -1.210490, 36.802871
   *
   * Therefore the presentation layer supports BOTH forms:
   *   1. A Google Maps Directions URL supplied by the AI.
   *   2. Destination coordinates supplied by the AI, from which the
   *      frontend constructs the Google Maps Directions URL.
   */

  const googleMapsStart = content.search(
    /https:\/\/www\.google\.com\/maps\/dir\/\?/i,
  );

  let navigationUrl: string | undefined;

  if (googleMapsStart >= 0) {
    let rawNavigationUrl = content.slice(googleMapsStart);

    const closingParenthesisIndex = rawNavigationUrl.indexOf(")");
    if (closingParenthesisIndex >= 0) {
      rawNavigationUrl = rawNavigationUrl.slice(0, closingParenthesisIndex);
    }

    const candidateUrl = rawNavigationUrl
      .replace(/[\r\n\t\s]+/g, "")
      .replace(/[.,;:]+$/, "");

    if (
      /^https:\/\/www\.google\.com\/maps\/dir\/\?api=1(?:&|$)/i.test(
        candidateUrl,
      ) &&
      /[?&]destination=/i.test(candidateUrl)
    ) {
      navigationUrl = candidateUrl;
    }
  }

  /*
   * If the AI did not return a Google Maps URL, use the destination
   * coordinates in the response to construct one ourselves.
   *
   * Prefer an explicit "Coordinates:" line so that the customer's current
   * location is never mistaken for the facility destination.
   */
  const destinationCoordinatesMatch = content.match(
    /(?:^|\n)\s*(?:[-*]\s*)?\*?\*?Coordinates\*?\*?\s*[:：]\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/im,
  );

  const destinationLatitude = destinationCoordinatesMatch
    ? Number(destinationCoordinatesMatch[1])
    : undefined;
  const destinationLongitude = destinationCoordinatesMatch
    ? Number(destinationCoordinatesMatch[2])
    : undefined;

  if (
    !navigationUrl &&
    destinationLatitude !== undefined &&
    destinationLongitude !== undefined &&
    Number.isFinite(destinationLatitude) &&
    Number.isFinite(destinationLongitude)
  ) {
    /*
     * Use the coordinates already obtained by the chatbot when available.
     * If they are not available, the AI response may itself contain the
     * customer's current coordinates in a "You're currently near ..." line.
     */
    let originLatitude = originCoordinates?.latitude;
    let originLongitude = originCoordinates?.longitude;

    if (originLatitude === undefined || originLongitude === undefined) {
      const responseOriginMatch = content.match(
        /(?:currently\s+near|your\s+(?:current\s+)?location)\s*[:：]?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/i,
      );

      if (responseOriginMatch) {
        originLatitude = Number(responseOriginMatch[1]);
        originLongitude = Number(responseOriginMatch[2]);
      }
    }

    const originIsValid =
      originLatitude !== undefined &&
      originLongitude !== undefined &&
      Number.isFinite(originLatitude) &&
      Number.isFinite(originLongitude);

    const destination = `${destinationLatitude},${destinationLongitude}`;

    navigationUrl = originIsValid
      ? `https://www.google.com/maps/dir/?api=1&origin=${encodeURIComponent(
          `${originLatitude},${originLongitude}`,
        )}&destination=${encodeURIComponent(destination)}&travelmode=driving`
      : `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(
          destination,
        )}&travelmode=driving`;
  }

  if (!navigationUrl) {
    return null;
  }

  /*
   * Prefer an explicit Facility/Address label when the AI provides one.
   * Otherwise, handle the natural response format used by SmartPark, e.g.:
   * "Two Rivers Mall is at Limuru Road, Nairobi."
   */
  const facilityFromNaturalSentence = content.match(
    /(?:^|\n)\s*([^\n]+?)\s+is\s+at\s+/i,
  )?.[1];

  const facilityName =
    extractLabeledValue(content, "Facility") ||
    facilityFromNaturalSentence?.replace(/^[-*]\s*/, "").trim();

  const facilityCode = extractLabeledValue(content, "Facility code");

  const addressFromNaturalSentence = content.match(
    /\bis\s+at\s+\*?\*?([^\n*]+?)\*?\*?\.?\s*(?:\n|$)/i,
  )?.[1];

  const address =
    extractLabeledValue(content, "Address") ||
    addressFromNaturalSentence?.trim();

  /*
   * Do not turn ordinary facility-coordinate information into a navigation
   * card unless the response is actually navigation-related.
   *
   * A Google Maps Directions URL is itself an explicit navigation signal.
   * For coordinate-only responses, require navigation wording.
   */
  const hasNavigationLanguage =
    /open your preferred maps app|navigate to|navigation|directions|how do i get to|how do i get there|take me to|get me to/i.test(
      content,
    );

  if (!hasNavigationLanguage && googleMapsStart < 0) {
    return null;
  }

  return {
    facilityName: cleanMarkdownValue(facilityName || "SmartPark Facility"),
    facilityCode,
    address: address ? cleanMarkdownValue(address) : undefined,
    navigationUrl,
  };
};

const renderNavigationCard = (navigation: NavigationPresentation) => (
  <article className="mb-3 w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
    <div className="border-b border-slate-100 bg-gradient-to-br from-slate-50 via-white to-blue-50/60 px-4 py-3.5">
      <div className="flex items-center gap-2">
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
              d="M12 21s7-6.1 7-12a7 7 0 1 0-14 0c0 5.9 7 12 7 12Z"
            />
            <circle cx="12" cy="9" r="2.2" />
          </svg>
        </span>

        <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
          Navigation
        </span>
      </div>

      <h3 className="mt-2 text-sm font-semibold text-slate-900">
        {navigation.facilityName}
      </h3>

      {navigation.facilityCode && (
        <p className="mt-0.5 text-[11px] font-medium text-slate-500">
          {navigation.facilityCode}
        </p>
      )}

      {navigation.address && (
        <p className="mt-2 text-[11px] leading-4 text-slate-500">
          {cleanMarkdownValue(navigation.address)}
        </p>
      )}
    </div>

    <div className="px-4 py-3">
      <a
        href={navigation.navigationUrl}
        target="_blank"
        rel="noopener noreferrer"
        aria-label={`Start navigation to ${navigation.facilityName}`}
        className="
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
            d="M12 19V5m0 0-5 5m5-5 5 5"
          />
          <path strokeLinecap="round" strokeLinejoin="round" d="M5 19h14" />
        </svg>
        Start Navigation
      </a>
    </div>
  </article>
);

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

const parseSessionPaymentId = (content: string): number | undefined => {
  const match = content.match(/\[\[SESSION_PAYMENT:(\d+)\]\]/i);

  if (!match) {
    return undefined;
  }

  const sessionId = Number(match[1]);

  return Number.isInteger(sessionId) && sessionId > 0 ? sessionId : undefined;
};

const removeSessionPaymentMarker = (content: string): string =>
  content
    .replace(/\[\[SESSION_PAYMENT:\d+\]\]/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

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

const isVehicleInventoryResponse = (content: string): boolean =>
  /^\s*Your vehicles\s*:/im.test(content) && /^\s*\d+[.)]\s+.+$/m.test(content);

const renderVehicleInventory = (content: string) => {
  const lines = content.replace(/\r/g, "").split("\n");
  const headingIndex = lines.findIndex((line) =>
    /^\s*Your vehicles\s*:/i.test(line.trim()),
  );

  if (headingIndex < 0) {
    return renderFriendlyMarkdown(content);
  }

  const before = lines.slice(0, headingIndex).filter((line) => line.trim());
  const vehicleItems: Array<{ title: string; details: string[] }> = [];
  let currentItem: { title: string; details: string[] } | null = null;

  for (const rawLine of lines.slice(headingIndex + 1)) {
    const line = rawLine.trim();

    if (!line) {
      continue;
    }

    const numberedMatch = line.match(/^\d+[.)]\s+(.+)$/);

    if (numberedMatch) {
      if (currentItem) {
        vehicleItems.push(currentItem);
      }

      currentItem = {
        title: numberedMatch[1],
        details: [],
      };
      continue;
    }

    if (currentItem) {
      currentItem.details.push(line);
    }
  }

  if (currentItem) {
    vehicleItems.push(currentItem);
  }

  if (vehicleItems.length === 0) {
    return renderFriendlyMarkdown(content);
  }

  return (
    <div className="text-sm leading-5 text-slate-700">
      {before.map((line, index) => (
        <p key={`vehicle-before-${index}`} className="my-1.5 leading-5">
          {renderInlineMarkdown(line)}
        </p>
      ))}

      <p className="my-1.5 leading-5">
        {renderInlineMarkdown(lines[headingIndex].trim())}
      </p>

      <ol className="my-2 space-y-2 list-decimal pl-5">
        {vehicleItems.map((item, index) => (
          <li key={`vehicle-${index}`} className="pl-1 leading-5">
            <div>{renderInlineMarkdown(item.title)}</div>

            {item.details.map((detail, detailIndex) => (
              <div
                key={`vehicle-${index}-detail-${detailIndex}`}
                className="mt-0.5 text-sm leading-5"
              >
                {renderInlineMarkdown(detail)}
              </div>
            ))}
          </li>
        ))}
      </ol>
    </div>
  );
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
      /*
       * Keep a numbered/bulleted list open across blank lines.
       *
       * The AI may return numbered items separated by blank lines, e.g.:
       *
       *   1. First vehicle
       *
       *   1. Second vehicle
       *
       *   1. Third vehicle
       *
       * If we flush the <ol> at every blank line, each item becomes a
       * separate one-item <ol>, so the browser correctly renders every
       * one as "1.". Only flush here when the next non-empty line is not
       * another item of the same list type.
       */
      const nextNonEmptyLine = lines
        .slice(index + 1)
        .map((nextLine) => nextLine.trim())
        .find(Boolean);

      const continuesNumberedList =
        numberedItems.length > 0 &&
        !!nextNonEmptyLine &&
        /^\d+[.)]\s+(.+)$/.test(nextNonEmptyLine);

      const continuesBulletList =
        bulletItems.length > 0 &&
        !!nextNonEmptyLine &&
        /^[-*]\s+(.+)$/.test(nextNonEmptyLine);

      if (continuesNumberedList || continuesBulletList) {
        return;
      }

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

const parseReservationDetails = (content: string) => ({
  reservationNumber: parseReservationNumber(content),
  facility: parseReservationFacility(content),
  bay: extractLabeledValue(content, "Bay"),
  date: extractLabeledValue(content, "Date"),
  time: extractLabeledValue(content, "Time"),
  vehicle: extractLabeledValue(content, "Vehicle"),
  estimatedAmount:
    extractLabeledValue(content, "Estimated amount") ||
    extractLabeledValue(content, "Estimated amount (KES)"),
});

const renderReservationDetail = (
  icon: JSX.Element,
  label: string,
  value?: string,
) => {
  if (!value) return null;

  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-100 bg-slate-50/70 px-3 py-2.5">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white text-[#0b2a4a] shadow-sm ring-1 ring-slate-100">
        {icon}
      </span>
      <div className="min-w-0">
        <p className="text-[9px] font-semibold uppercase tracking-[0.1em] text-slate-400">
          {label}
        </p>
        <p className="mt-0.5 break-words text-[11px] font-semibold leading-4 text-slate-700">
          {cleanMarkdownValue(value)}
        </p>
      </div>
    </div>
  );
};

const renderReservationCard = (content: string) => {
  const details = parseReservationDetails(content);
  if (!details.reservationNumber) return null;

  const status = parseReservationStatus(content);
  const isCreated = status === "Created";
  const isConfirmed = status === "Confirmed";

  return (
    <article className="mb-3 w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-gradient-to-br from-slate-50 via-white to-blue-50/60 px-4 py-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[#0b2a4a] text-white">
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

            <h3 className="text-base font-bold tracking-tight text-slate-900">
              {isConfirmed ? "Reservation Confirmed" : "Reservation Created"}
            </h3>

            {details.facility && (
              <p className="mt-1 text-xs font-medium text-slate-500">
                {cleanMarkdownValue(details.facility)}
              </p>
            )}

            <p className="mt-2 text-[10px] font-medium uppercase tracking-wide text-slate-400">
              Booking reference
            </p>
            <p className="mt-0.5 text-xs font-bold text-[#0b2a4a]">
              {details.reservationNumber}
            </p>
          </div>

          <span
            className={`shrink-0 rounded-full border px-2.5 py-1 text-[10px] font-semibold ${
              isConfirmed
                ? "border-emerald-200 bg-emerald-50 text-emerald-700"
                : isCreated
                  ? "border-amber-200 bg-amber-50 text-amber-700"
                  : "border-slate-200 bg-slate-50 text-slate-600"
            }`}
          >
            {isConfirmed
              ? "Confirmed"
              : isCreated
                ? "Payment Required"
                : status}
          </span>
        </div>
      </div>

      <div className="space-y-2 px-4 py-4">
        <div className="grid grid-cols-2 gap-2">
          {renderReservationDetail(
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
                d="M5 5h14v14H5zM8 3v4M16 3v4M5 10h14"
              />
            </svg>,
            "Date",
            details.date,
          )}

          {renderReservationDetail(
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              className="h-4 w-4"
              aria-hidden="true"
            >
              <circle cx="12" cy="12" r="8.5" />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 7v5l3 2"
              />
            </svg>,
            "Time",
            details.time,
          )}

          {renderReservationDetail(
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
                d="M5 16.5V10l2-4h10l2 4v6.5M4 16.5h16M7.5 16.5v2M16.5 16.5v2M7 10h10"
              />
              <circle cx="7.5" cy="13.5" r="1" />
              <circle cx="16.5" cy="13.5" r="1" />
            </svg>,
            "Vehicle",
            details.vehicle,
          )}

          {renderReservationDetail(
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
                d="M4 6h16M6 6v12M18 6v12M4 18h16"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M9 10h6M9 14h6"
              />
            </svg>,
            "Parking Bay",
            details.bay,
          )}
        </div>

        {details.estimatedAmount && (
          <div className="flex items-center justify-between rounded-xl border border-blue-100 bg-blue-50/60 px-3 py-3">
            <div>
              <p className="text-[9px] font-semibold uppercase tracking-[0.1em] text-slate-400">
                Estimated amount
              </p>
              <p className="mt-0.5 text-base font-bold text-[#0b2a4a]">
                {cleanMarkdownValue(details.estimatedAmount)}
              </p>
            </div>

            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-white text-[#0b2a4a] shadow-sm ring-1 ring-blue-100">
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
                  d="M12 3v18M16 7.5c0-1.4-1.8-2.5-4-2.5S8 6.1 8 7.5s1.8 2.5 4 2.5 4 1.1 4 2.5-1.8 2.5-4 2.5-4-1.1-4-2.5"
                />
              </svg>
            </span>
          </div>
        )}

        <div
          className={`rounded-xl px-3 py-3 text-[11px] leading-5 ${
            isCreated
              ? "border border-amber-100 bg-amber-50/70 text-amber-800"
              : isConfirmed
                ? "border border-emerald-100 bg-emerald-50/70 text-emerald-800"
                : "border border-slate-100 bg-slate-50 text-slate-600"
          }`}
        >
          <div className="flex items-start gap-2">
            <span className="mt-0.5 shrink-0">
              {isCreated ? "💳" : isConfirmed ? "✓" : "ℹ"}
            </span>
            <p>
              {isCreated
                ? "Your reservation has been created successfully. Payment is required to confirm your booking."
                : isConfirmed
                  ? "Your reservation is confirmed. We look forward to seeing you at the facility."
                  : "Your reservation details are shown above."}
            </p>
          </div>
        </div>
      </div>
    </article>
  );
};

type VehicleActionPresentation = {
  action: "ADD" | "EDIT";
  vehicleId?: number;
};

const parseVehicleActionPresentation = (
  content: string,
): VehicleActionPresentation | null => {
  if (/\[\[VEHICLE_ACTION:ADD\]\]/i.test(content)) return { action: "ADD" };
  const match = content.match(/\[\[VEHICLE_ACTION:EDIT:(\d+)\]\]/i);
  if (!match) return null;
  const vehicleId = Number(match[1]);
  return Number.isInteger(vehicleId) && vehicleId > 0
    ? { action: "EDIT", vehicleId }
    : null;
};

const removeVehicleActionMarker = (content: string): string =>
  content
    .replace(/\[\[VEHICLE_ACTION:ADD\]\]/gi, "")
    .replace(/\[\[VEHICLE_ACTION:EDIT:\d+\]\]/gi, "")
    .replace(/\n{3,}/g, "\n\n")
    .trim();

const renderVehicleActionCard = (
  action: VehicleActionPresentation,
  navigate: (path: string) => void,
) => {
  const isAdd = action.action === "ADD";
  return (
    <article className="mb-3 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 bg-gradient-to-br from-slate-50 via-white to-blue-50/50 px-4 py-3.5">
        <div className="text-[10px] font-semibold uppercase tracking-[0.12em] text-slate-500">
          Vehicle Management
        </div>
        <h3 className="mt-2 text-sm font-semibold text-slate-900">
          {isAdd ? "Add a vehicle" : "Edit vehicle details"}
        </h3>
        <p className="mt-1 text-[11px] leading-4 text-slate-500">
          {isAdd
            ? "Open the vehicle registration page to add a new vehicle."
            : "Open the vehicle details page to review and update this vehicle."}
        </p>
      </div>
      <div className="px-4 py-3">
        <button
          type="button"
          onClick={() =>
            navigate(
              isAdd ? "/vehicles/create" : `/vehicles/${action.vehicleId}/edit`,
            )
          }
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#0b2a4a] px-4 py-2.5 text-xs font-semibold text-white shadow-sm transition hover:bg-[#123b63] focus:outline-none focus:ring-4 focus:ring-blue-100"
        >
          {isAdd ? "Add Vehicle" : "Edit Vehicle"}
        </button>
      </div>
    </article>
  );
};

const isStructuredAssistantContent = (
  content: string,
  originCoordinates?: Coordinates | null,
): boolean => {
  try {
    return Boolean(
      parseForecastPresentation(content) ||
      parseNavigationPresentation(content, originCoordinates) ||
      parseReservationNumber(content),
    );
  } catch (error) {
    console.error(
      "[SmartPark AI] Failed to classify assistant response:",
      error,
    );
    return false;
  }
};

const renderAssistantContent = (
  content: string,
  originCoordinates?: Coordinates | null,
  navigate?: (path: string) => void,
) => {
  /*
   * Presentation must never be allowed to break the whole application.
   * If a response does not match one of the structured formats, or a
   * presentation parser encounters unexpected AI output, fall back to
   * the friendly Markdown renderer instead of throwing during render.
   */
  try {
    const vehicleAction = parseVehicleActionPresentation(content);
    if (vehicleAction && navigate) {
      const cleanContent = removeVehicleActionMarker(content);
      return (
        <>
          {renderVehicleActionCard(vehicleAction, navigate)}
          {cleanContent && renderFriendlyMarkdown(cleanContent)}
        </>
      );
    }

    if (isVehicleInventoryResponse(content)) {
      return renderVehicleInventory(content);
    }

    const forecast = parseForecastPresentation(content);

    if (forecast) {
      return renderForecastCard(forecast);
    }

    const navigation = parseNavigationPresentation(content, originCoordinates);

    if (navigation) {
      /*
       * Remove the complete Markdown navigation link from the conversational
       * response. The navigation card owns the actual Google Maps action.
       * Keep this replacement independent of the generated URL so special
       * URL characters can never break a dynamic RegExp.
       */
      const contentWithoutNavigationLink = content
        // Remove Markdown navigation labels when present.
        .replace(/\[[^\]]*start\s+navigation[^\]]*\]\s*/gi, "")
        // Remove a complete Google Maps Directions URL when present.
        .replace(/https:\/\/www\.google\.com\/maps\/dir\/\?[^\s)]+/gi, "")
        // Remove the conversational instruction used when the AI returns
        // coordinates instead of a URL.
        .replace(/you(?:'|’)?re currently near[^\n]*\n?/gi, "")
        .replace(/open your preferred maps app and navigate to:\s*/gi, "")
        // Remove the destination coordinate line because the navigation card
        // already represents that action.
        .replace(
          /(?:^|\n)\s*(?:[-*]\s*)?\*?\*?Coordinates\*?\*?\s*[:：]\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\.?\s*/gim,
          "\n",
        )
        .trim();

      return (
        <>
          {renderNavigationCard(navigation)}
          {contentWithoutNavigationLink &&
            renderFriendlyMarkdown(contentWithoutNavigationLink)}
        </>
      );
    }

    const reservationNumber = parseReservationNumber(content);
    if (reservationNumber) {
      return renderReservationCard(content);
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
  const [isMaximized, setIsMaximized] = useState(false);

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
  const [realtimeTextInput, setRealtimeTextInput] = useState("");
  const [realtimeSelectedAttachment, setRealtimeSelectedAttachment] =
    useState<ChatAttachment | null>(null);

  const [selectedAttachment, setSelectedAttachment] =
    useState<ChatAttachment | null>(null);

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
  const [isListening, setIsListening] = useState(false);
  const [speechSupported, setSpeechSupported] = useState(false);
  const [speechError, setSpeechError] = useState<string | null>(null);

  const speechRecognitionRef =
    useRef<SmartParkSpeechRecognitionInstance | null>(null);
  const speechInputPrefixRef = useRef("");
  const [speechOutputSupported, setSpeechOutputSupported] = useState(false);
  const [isSpeakingMessageId, setIsSpeakingMessageId] = useState<number | null>(
    null,
  );
  const [speechOutputError, setSpeechOutputError] = useState<string | null>(
    null,
  );

  const speechSynthesisRef = useRef<SpeechSynthesis | null>(null);
  const speechUtteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const lastSpokenAssistantMessageIdRef = useRef(1);

  // ----------------------------------------------------------
  // Realtime voice conversation state
  // ----------------------------------------------------------

  const [interactionMode, setInteractionMode] =
    useState<InteractionMode>("text");
  const [isRealtimeConnecting, setIsRealtimeConnecting] = useState(false);
  const [isRealtimeConnected, setIsRealtimeConnected] = useState(false);
  const [isRealtimePaused, setIsRealtimePaused] = useState(false);
  const [realtimeError, setRealtimeError] = useState<string | null>(null);

  const realtimePeerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const realtimeDataChannelRef = useRef<RTCDataChannel | null>(null);
  const realtimeAudioElementRef = useRef<HTMLAudioElement | null>(null);
  const realtimeAssistantTranscriptRef = useRef("");
  const realtimeMicStatsIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const realtimeMicAudioContextRef = useRef<AudioContext | null>(null);
  const realtimeMicAnalyserRef = useRef<AnalyserNode | null>(null);
  const realtimeMicSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const realtimeMicLevelIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const realtimeAssistantMessageIdRef = useRef<number | null>(null);
  const realtimeToolCallsRef = useRef(new Set<string>());

  // ----------------------------------------------------------
  // Refs
  // ----------------------------------------------------------

  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const realtimeTextInputRef = useRef<HTMLInputElement | null>(null);
  const realtimeAttachmentInputRef = useRef<HTMLInputElement | null>(null);

  const attachmentInputRef = useRef<HTMLInputElement | null>(null);

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
        // Hiding the chatbot must not terminate an active realtime voice
        // conversation. The WebRTC session remains alive while the component
        // stays mounted; the user can reopen the window and continue.
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
        // Escape hides the UI only; it does not end an active voice session.
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

  useEffect(() => {
    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setSpeechSupported(false);
      return;
    }

    setSpeechSupported(true);

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-KE";

    recognition.onstart = () => {
      setSpeechError(null);
      setIsListening(true);
    };

    recognition.onresult = (event) => {
      let transcript = "";

      for (
        let index = event.resultIndex;
        index < event.results.length;
        index += 1
      ) {
        transcript += event.results[index][0]?.transcript ?? "";
      }

      const prefix = speechInputPrefixRef.current;
      setInput(`${prefix}${transcript}`.replace(/\s+/g, " ").trimStart());
    };

    recognition.onerror = (event) => {
      if (event.error === "aborted") return;

      const messages: Record<string, string> = {
        "not-allowed":
          "Microphone permission was denied. Please allow microphone access in your browser.",
        "service-not-allowed":
          "Speech recognition is not allowed by your browser.",
        "no-speech":
          "I didn't hear anything. Please tap the microphone and try again.",
        "audio-capture":
          "No working microphone was detected. Please check your microphone.",
        network:
          "Speech recognition could not connect to the browser speech service.",
      };

      setSpeechError(
        messages[event.error] ||
          "Voice input could not be started. Please try again.",
      );
      setIsListening(false);
    };

    recognition.onend = () => {
      setIsListening(false);
      speechRecognitionRef.current = null;
    };

    speechRecognitionRef.current = recognition;

    return () => {
      recognition.onstart = null;
      recognition.onend = null;
      recognition.onresult = null;
      recognition.onerror = null;
      try {
        recognition.abort();
      } catch {
        // Ignore cleanup errors.
      }
      speechRecognitionRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!("speechSynthesis" in window)) {
      setSpeechOutputSupported(false);
      return;
    }

    speechSynthesisRef.current = window.speechSynthesis;
    setSpeechOutputSupported(true);

    return () => {
      try {
        window.speechSynthesis.cancel();
      } catch {
        // Ignore cleanup errors.
      }

      speechSynthesisRef.current = null;
    };
  }, []);

  const stopVoiceInput = () => {
    const recognition = speechRecognitionRef.current;

    if (!recognition) {
      setIsListening(false);
      return;
    }

    try {
      recognition.stop();
    } catch {
      setIsListening(false);
      speechRecognitionRef.current = null;
    }
  };

  const toggleVoiceInput = () => {
    if (isSending) return;

    if (!speechSupported || !speechRecognitionRef.current) {
      setSpeechError("Voice input is not supported by this browser.");
      return;
    }

    if (isListening) {
      stopVoiceInput();
      return;
    }

    setSpeechError(null);
    speechInputPrefixRef.current = input.trim() ? `${input.trim()} ` : "";

    try {
      speechRecognitionRef.current.start();
    } catch {
      setSpeechError("Voice input could not be started. Please try again.");
    }
  };

  const stopSpeech = () => {
    const synthesis = speechSynthesisRef.current;

    if (synthesis) {
      synthesis.cancel();
    }

    speechUtteranceRef.current = null;
    setIsSpeakingMessageId(null);
  };

  const prepareSpeechText = (content: string): string => {
    return content
      .replace(/\[\[SESSION_PAYMENT:\d+\]\]/gi, "")
      .replace(/\[\[VEHICLE_ACTION:[^\]]+\]\]/gi, "")
      .replace(/https?:\/\/\S+/gi, "")
      .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .replace(/^#{1,6}\s+/gm, "")
      .replace(/^\s*[-*]\s+/gm, "")
      .replace(/^\s*\d+[.)]\s+/gm, "")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/__([^_]+)__/g, "$1")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/\n{2,}/g, ". ")
      .replace(/\n/g, " ")
      .replace(/\s{2,}/g, " ")
      .trim();
  };

  const speakAssistantMessage = (messageId: number, content: string) => {
    const synthesis = speechSynthesisRef.current;

    if (!synthesis) {
      setSpeechOutputError(
        "Voice responses are not supported by this browser.",
      );
      return;
    }

    const speechText = prepareSpeechText(content);

    if (!speechText) {
      return;
    }

    synthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(speechText);
    utterance.lang = "en-KE";
    utterance.rate = 0.98;
    utterance.pitch = 1;

    utterance.onstart = () => {
      setSpeechOutputError(null);
      setIsSpeakingMessageId(messageId);
    };

    utterance.onend = () => {
      if (speechUtteranceRef.current === utterance) {
        speechUtteranceRef.current = null;
        setIsSpeakingMessageId(null);
      }
    };

    utterance.onerror = (event) => {
      if (event.error !== "canceled" && event.error !== "interrupted") {
        setSpeechOutputError(
          "SmartPark AI could not play the voice response. Please try again.",
        );
      }

      if (speechUtteranceRef.current === utterance) {
        speechUtteranceRef.current = null;
        setIsSpeakingMessageId(null);
      }
    };

    speechUtteranceRef.current = utterance;
    synthesis.speak(utterance);
  };

  // ----------------------------------------------------------
  // Realtime voice conversation
  // ----------------------------------------------------------

  const stopRealtimeVoice = () => {
    if (realtimeMicStatsIntervalRef.current) {
      clearInterval(realtimeMicStatsIntervalRef.current);
      realtimeMicStatsIntervalRef.current = null;
    }

    if (realtimeMicLevelIntervalRef.current) {
      clearInterval(realtimeMicLevelIntervalRef.current);
      realtimeMicLevelIntervalRef.current = null;
    }

    try {
      realtimeMicSourceRef.current?.disconnect();
    } catch {
      // Ignore cleanup errors.
    }
    realtimeMicSourceRef.current = null;
    realtimeMicAnalyserRef.current = null;

    if (realtimeMicAudioContextRef.current) {
      void realtimeMicAudioContextRef.current.close().catch(() => {});
      realtimeMicAudioContextRef.current = null;
    }

    const dataChannel = realtimeDataChannelRef.current;

    if (dataChannel) {
      dataChannel.onopen = null;
      dataChannel.onclose = null;
      dataChannel.onerror = null;
      dataChannel.onmessage = null;

      try {
        dataChannel.close();
      } catch {
        // Ignore cleanup errors.
      }
    }

    const peerConnection = realtimePeerConnectionRef.current;

    if (peerConnection) {
      peerConnection.ontrack = null;
      peerConnection.onconnectionstatechange = null;

      try {
        peerConnection.getSenders().forEach((sender) => {
          if (sender.track) {
            sender.track.stop();
          }
        });
      } catch {
        // Ignore cleanup errors.
      }

      try {
        peerConnection.close();
      } catch {
        // Ignore cleanup errors.
      }
    }

    realtimeDataChannelRef.current = null;
    realtimePeerConnectionRef.current = null;

    if (realtimeAudioElementRef.current) {
      realtimeAudioElementRef.current.srcObject = null;
    }

    realtimeAssistantTranscriptRef.current = "";
    realtimeAssistantMessageIdRef.current = null;
    realtimeToolCallsRef.current.clear();

    setIsRealtimeConnecting(false);
    setIsRealtimeConnected(false);
    setIsRealtimePaused(false);
  };

  // ----------------------------------------------------------
  // Pause/resume microphone without ending the Realtime session
  // ----------------------------------------------------------

  const pauseRealtimeVoice = () => {
    if (!isRealtimeConnected || isRealtimePaused) {
      return;
    }

    const peerConnection = realtimePeerConnectionRef.current;

    if (!peerConnection) {
      return;
    }

    // Disable the existing microphone track instead of stopping it. This
    // keeps the same RTCPeerConnection, data channel, and conversation alive.
    peerConnection.getSenders().forEach((sender) => {
      if (sender.track?.kind === "audio") {
        sender.track.enabled = false;
      }
    });

    // Discard any audio buffered at the moment pause is requested. The
    // Realtime session itself remains open.
    const dataChannel = realtimeDataChannelRef.current;
    if (dataChannel?.readyState === "open") {
      try {
        dataChannel.send(
          JSON.stringify({ type: "input_audio_buffer.clear" }),
        );
      } catch {
        // Ignore a transient data-channel error; the microphone is disabled.
      }
    }

    setIsRealtimePaused(true);
    console.log(
      "[SmartPark Realtime] Voice input paused; existing Realtime session remains active.",
    );
  };

  const resumeRealtimeVoice = () => {
    if (!isRealtimeConnected || !isRealtimePaused) {
      return;
    }

    const peerConnection = realtimePeerConnectionRef.current;

    if (!peerConnection) {
      return;
    }

    // Re-enable the same microphone track. No new WebRTC/Realtime session is
    // created, so the existing conversation context is preserved.
    peerConnection.getSenders().forEach((sender) => {
      if (sender.track?.kind === "audio") {
        sender.track.enabled = true;
      }
    });

    setIsRealtimePaused(false);
    setRealtimeError(null);
    console.log(
      "[SmartPark Realtime] Voice input resumed; existing Realtime session remains active.",
    );
  };

  const appendRealtimeUserTranscript = (transcript: string) => {
    const cleanTranscript = transcript.trim();

    if (!cleanTranscript) {
      return;
    }

    setMessages((previous) => [
      ...previous,
      {
        id: Date.now() + Math.floor(Math.random() * 1000),
        role: "user",
        content: cleanTranscript,
      },
    ]);
  };

  const appendRealtimeAssistantTranscript = (transcript: string) => {
    const cleanTranscript = transcript.trim();

    if (!cleanTranscript) {
      return;
    }

    setMessages((previous) => {
      const existingId = realtimeAssistantMessageIdRef.current;

      if (existingId !== null) {
        const existingIndex = previous.findIndex(
          (message) => message.id === existingId,
        );

        if (existingIndex >= 0) {
          const updated = [...previous];
          updated[existingIndex] = {
            ...updated[existingIndex],
            content: cleanTranscript,
          };
          return updated;
        }
      }

      const messageId = Date.now() + Math.floor(Math.random() * 1000);
      realtimeAssistantMessageIdRef.current = messageId;

      return [
        ...previous,
        {
          id: messageId,
          role: "assistant",
          content: cleanTranscript,
        },
      ];
    });
  };

  // ----------------------------------------------------------
  // Send typed text inside an active Realtime voice conversation
  // ----------------------------------------------------------

  const handleRealtimeAttachmentChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    const allowedTypes = new Set([
      "application/pdf",
      "application/msword",
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "application/vnd.ms-excel",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      "application/vnd.ms-powerpoint",
      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      "text/plain",
      "text/csv",
      "application/json",
      "image/jpeg",
      "image/png",
      "image/webp",
    ]);

    if (!allowedTypes.has(file.type.toLowerCase())) {
      window.alert(
        "Please attach a PDF, Word, Excel, PowerPoint, text, CSV, JSON, JPEG, PNG, or WebP document.",
      );
      event.target.value = "";
      return;
    }

    const maxAttachmentBytes = 10 * 1024 * 1024;

    if (file.size > maxAttachmentBytes) {
      window.alert("Document attachments must not exceed 10 MB.");
      event.target.value = "";
      return;
    }

    setRealtimeSelectedAttachment({
      file,
      name: file.name,
      size: file.size,
    });
  };

  const removeRealtimeAttachment = () => {
    setRealtimeSelectedAttachment(null);
    if (realtimeAttachmentInputRef.current) {
      realtimeAttachmentInputRef.current.value = "";
    }
  };

  const sendRealtimeTextCommand = async () => {
    const trimmedMessage = realtimeTextInput.trim();
    const attachment = realtimeSelectedAttachment?.file ?? null;
    const dataChannel = realtimeDataChannelRef.current;

    if (
      (!trimmedMessage && !attachment) ||
      !dataChannel ||
      dataChannel.readyState !== "open"
    ) {
      return;
    }

    try {
      let uploadedFileId: string | null = null;
      let documentContext: string | null = null;

      if (attachment) {
        const formData = new FormData();
        formData.append("attachment", attachment);

        const uploadResponse = await api.post<{
          file_id: string;
          filename: string;
          document_context: string;
        }>("/ai/realtime/file", formData, {
          // The shared Axios client defaults to application/json.
          // Remove that default for this FormData request so the browser
          // supplies the correct multipart/form-data boundary.
          headers: {
            "Content-Type": undefined,
          },
          timeout: 90000,
        });

        uploadedFileId = uploadResponse.data.file_id;
        documentContext = uploadResponse.data.document_context;
      }

      const displayContent = trimmedMessage
        ? attachment
          ? `${trimmedMessage}\n\n📎 ${attachment.name}`
          : trimmedMessage
        : `📎 ${attachment?.name ?? "Document attached"}`;

      setMessages((previous) => [
        ...previous,
        {
          id: Date.now(),
          role: "user",
          content: displayContent,
          attachmentName: attachment?.name,
        },
      ]);

      setRealtimeTextInput("");
      setRealtimeSelectedAttachment(null);
      if (realtimeAttachmentInputRef.current) {
        realtimeAttachmentInputRef.current.value = "";
      }

      // Realtime conversation.item.create supports input_text/input_audio here.
      // The backend has already analyzed the attachment through the Responses API
      // and returned a factual document briefing. Inject that briefing as text so
      // the same live Realtime conversation can continue and answer aloud.
      const textParts = [
        trimmedMessage ||
          "Please review the attached document and tell me what is relevant to my request.",
      ];

      if (uploadedFileId && documentContext) {
        textParts.push(
          `\nAttached document: ${attachment?.name ?? "document"}\n` +
            "Document briefing from SmartPark document analysis:\n" +
            documentContext,
        );
      }

      dataChannel.send(
        JSON.stringify({
          type: "conversation.item.create",
          item: {
            type: "message",
            role: "user",
            content: [
              {
                type: "input_text",
                text: textParts.join("\n"),
              },
            ],
          },
        }),
      );

      dataChannel.send(JSON.stringify({ type: "response.create" }));
    } catch (error) {
      setRealtimeError(
        error instanceof Error
          ? error.message
          : "The command or document could not be sent to SmartPark AI.",
      );
    }
  };

  const handleRealtimeEvent = async (
    event: RealtimeTranscriptEvent | RealtimeToolCallEvent | RealtimeErrorEvent,
  ) => {
    if (
      event.type === "conversation.item.input_audio_transcription.completed"
    ) {
      appendRealtimeUserTranscript(event.transcript || "");
      return;
    }

    if (
      event.type === "response.output_audio_transcript.done" ||
      event.type === "response.audio_transcript.done"
    ) {
      const transcript = event.transcript || "";
      realtimeAssistantTranscriptRef.current = transcript;
      appendRealtimeAssistantTranscript(transcript);
      realtimeAssistantMessageIdRef.current = null;
      return;
    }

    if (
      event.type === "response.output_audio_transcript.delta" ||
      event.type === "response.audio_transcript.delta"
    ) {
      if (event.delta) {
        realtimeAssistantTranscriptRef.current += event.delta;
        appendRealtimeAssistantTranscript(
          realtimeAssistantTranscriptRef.current,
        );
      }
      return;
    }

    if (event.type === "response.function_call_arguments.done") {
      const toolEvent = event as RealtimeToolCallEvent;

      if (realtimeToolCallsRef.current.has(toolEvent.call_id)) {
        return;
      }

      realtimeToolCallsRef.current.add(toolEvent.call_id);

      let argumentsObject: Record<string, unknown> = {};

      try {
        const parsed = JSON.parse(toolEvent.arguments || "{}");
        if (parsed && typeof parsed === "object") {
          argumentsObject = parsed as Record<string, unknown>;
        }
      } catch {
        argumentsObject = {};
      }

      try {
        const response = await api.post<{
          tool_name: string;
          output: unknown;
        }>("/ai/realtime/tool", {
          tool_name: toolEvent.name,
          arguments: argumentsObject,
          latitude: coordinates?.latitude ?? null,
          longitude: coordinates?.longitude ?? null,
        });

        const dataChannel = realtimeDataChannelRef.current;

        if (!dataChannel || dataChannel.readyState !== "open") {
          throw new Error("Realtime data channel is not available.");
        }

        dataChannel.send(
          JSON.stringify({
            type: "conversation.item.create",
            item: {
              type: "function_call_output",
              call_id: toolEvent.call_id,
              output: JSON.stringify(response.data.output ?? {}),
            },
          }),
        );

        dataChannel.send(JSON.stringify({ type: "response.create" }));
      } catch (error) {
        const dataChannel = realtimeDataChannelRef.current;

        if (dataChannel && dataChannel.readyState === "open") {
          dataChannel.send(
            JSON.stringify({
              type: "conversation.item.create",
              item: {
                type: "function_call_output",
                call_id: toolEvent.call_id,
                output: JSON.stringify({
                  error:
                    getApiErrorMessage(error) ||
                    "The requested SmartPark operation could not be completed.",
                }),
              },
            }),
          );

          dataChannel.send(JSON.stringify({ type: "response.create" }));
        }
      }

      return;
    }

    if (event.type === "input_audio_buffer.speech_started") {
      console.log("[SmartPark Realtime] Server VAD detected speech.");
      return;
    }

    if (event.type === "input_audio_buffer.speech_stopped") {
      console.log("[SmartPark Realtime] Server VAD detected end of speech.");
      return;
    }

    if (event.type === "error") {
      const realtimeErrorEvent = event as RealtimeErrorEvent;
      setRealtimeError(
        realtimeErrorEvent.error?.message ||
          "SmartPark voice encountered a realtime error.",
      );
    }
  };

  const startRealtimeVoice = async () => {
    if (isRealtimeConnecting || isRealtimeConnected) {
      return;
    }

    if (
      typeof RTCPeerConnection === "undefined" ||
      !navigator.mediaDevices?.getUserMedia
    ) {
      setRealtimeError(
        "Realtime voice is not supported by this browser. Please use a modern Chrome, Edge, Safari, or Firefox browser.",
      );
      return;
    }

    setRealtimeError(null);
    setIsRealtimePaused(false);
    setIsRealtimeConnecting(true);
    stopSpeech();
    stopVoiceInput();

    try {
      const currentCoordinates = coordinates || (await requestLocation());

      // IMPORTANT: Some Windows systems expose "Stereo Mix" / loopback
      // devices as the browser's default audio input. That device captures
      // system playback rather than the user's microphone, so Realtime VAD
      // receives silence when the user speaks.
      //
      // First obtain permission, enumerate the now-visible audio inputs, and
      // prefer a physical microphone over known loopback/virtual capture
      // devices. MDN documents that device labels become available after
      // media permission is granted and that a specific device can then be
      // selected with the deviceId constraint.
      const audioConstraints: MediaTrackConstraints = {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      };

      let localStream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraints,
      });

      const initialAudioTrack = localStream.getAudioTracks()[0];
      const initialLabel = initialAudioTrack?.label || "";

      const loopbackPattern =
        /stereo\s*mix|what\s*u\s*hear|wave\s*out|loopback|cable\s*(output|input)|virtual\s*(audio|mic|microphone)|voicemeeter|vb-?audio|blackhole|soundflower/i;

      try {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const audioInputs = devices.filter((device) => device.kind === "audioinput");

        console.log(
          "[SmartPark Realtime] Available audio inputs:",
          audioInputs.map((device) => ({
            deviceId: device.deviceId,
            label: device.label,
            groupId: device.groupId,
          })),
        );

        const physicalMic = audioInputs.find(
          (device) =>
            device.deviceId &&
            device.deviceId !== "default" &&
            !loopbackPattern.test(device.label || ""),
        );

        const initialIsLoopback = loopbackPattern.test(initialLabel);

        if (initialIsLoopback && physicalMic) {
          console.warn(
            "[SmartPark Realtime] Browser selected a loopback audio input. Switching to physical microphone:",
            {
              selectedByBrowser: initialLabel,
              selectedPhysicalMic: physicalMic.label,
              deviceId: physicalMic.deviceId,
            },
          );

          localStream.getTracks().forEach((track) => track.stop());

          localStream = await navigator.mediaDevices.getUserMedia({
            audio: {
              ...audioConstraints,
              deviceId: { exact: physicalMic.deviceId },
            },
          });
        } else {
          console.log(
            "[SmartPark Realtime] Browser audio input accepted:",
            {
              label: initialLabel,
              loopback: initialIsLoopback,
              physicalMicCandidate: physicalMic?.label || null,
            },
          );
        }
      } catch (deviceSelectionError) {
        console.warn(
          "[SmartPark Realtime] Could not enumerate/select a physical microphone; continuing with the browser-selected input:",
          deviceSelectionError,
        );
      }

      const audioTracks = localStream.getAudioTracks();

      if (audioTracks.length === 0) {
        throw new Error("No microphone audio track was created by the browser.");
      }

      audioTracks.forEach((track) => {
        track.enabled = true;
        try {
          track.contentHint = "speech";
        } catch {
          // contentHint is optional and is not supported by every browser.
        }

        console.log("[SmartPark Realtime] Microphone track:", {
          id: track.id,
          label: track.label,
          enabled: track.enabled,
          muted: track.muted,
          readyState: track.readyState,
          settings: track.getSettings(),
        });

        track.onmute = () => {
          console.warn("[SmartPark Realtime] Microphone track muted.");
        };

        track.onunmute = () => {
          console.log("[SmartPark Realtime] Microphone track unmuted.");
        };
      });

      // Diagnostic only: prove that the browser is actually receiving
      // non-silent microphone samples before we blame WebRTC/OpenAI VAD.
      try {
        const AudioContextCtor =
          window.AudioContext ||
          (window as typeof window & { webkitAudioContext?: typeof AudioContext })
            .webkitAudioContext;

        if (AudioContextCtor) {
          const audioContext = new AudioContextCtor();
          const source = audioContext.createMediaStreamSource(localStream);
          const analyser = audioContext.createAnalyser();
          analyser.fftSize = 2048;
          source.connect(analyser);

          realtimeMicAudioContextRef.current = audioContext;
          realtimeMicSourceRef.current = source;
          realtimeMicAnalyserRef.current = analyser;

          const samples = new Uint8Array(analyser.fftSize);
          realtimeMicLevelIntervalRef.current = setInterval(() => {
            analyser.getByteTimeDomainData(samples);
            let sumSquares = 0;
            for (const sample of samples) {
              const normalized = (sample - 128) / 128;
              sumSquares += normalized * normalized;
            }
            const rms = Math.sqrt(sumSquares / samples.length);
            console.log("[SmartPark Realtime] Local microphone RMS:", Number(rms.toFixed(4)));
          }, 1000);

          void audioContext.resume().catch(() => {});
        } else {
          console.warn("[SmartPark Realtime] AudioContext is unavailable; local mic level diagnostic skipped.");
        }
      } catch (audioDiagnosticError) {
        console.warn("[SmartPark Realtime] Local microphone level diagnostic failed:", audioDiagnosticError);
      }

      const peerConnection = new RTCPeerConnection();
      realtimePeerConnectionRef.current = peerConnection;

      localStream.getTracks().forEach((track) => {
        peerConnection.addTrack(track, localStream);
      });

      const audioElement = new Audio();
      audioElement.autoplay = true;
      audioElement.setAttribute("playsinline", "true");
      realtimeAudioElementRef.current = audioElement;

      peerConnection.ontrack = (event) => {
        const [remoteStream] = event.streams;

        if (remoteStream) {
          audioElement.srcObject = remoteStream;
          void audioElement.play().catch(() => {
            // The user gesture that started the call normally permits playback.
          });
        }
      };

      peerConnection.onconnectionstatechange = () => {
        const state = peerConnection.connectionState;
        console.log("[SmartPark Realtime] Peer connection state:", state);

        if (state === "connected") {
          setIsRealtimeConnecting(false);
          setIsRealtimeConnected(true);
          setRealtimeError(null);
        }

        if (
          state === "failed" ||
          state === "closed" ||
          state === "disconnected"
        ) {
          setIsRealtimeConnected(false);
          setIsRealtimePaused(false);
        }
      };

      const dataChannel = peerConnection.createDataChannel("oai-events");
      realtimeDataChannelRef.current = dataChannel;

      dataChannel.onopen = () => {
        setIsRealtimeConnecting(false);
        setIsRealtimeConnected(true);
        setRealtimeError(null);
      };

      dataChannel.onclose = () => {
        setIsRealtimeConnected(false);
        setIsRealtimePaused(false);
      };

      dataChannel.onerror = () => {
        setRealtimeError(
          "The SmartPark realtime voice connection encountered an error.",
        );
      };

      dataChannel.onmessage = (messageEvent) => {
        try {
          const event = JSON.parse(messageEvent.data) as
            | RealtimeTranscriptEvent
            | RealtimeToolCallEvent
            | RealtimeErrorEvent;

          console.log("[SmartPark Realtime] Server event:", event);

          if (
            event.type === "input_audio_buffer.speech_started" ||
            event.type === "input_audio_buffer.speech_stopped" ||
            event.type === "conversation.item.input_audio_transcription.completed"
          ) {
            console.log(
              "[SmartPark Realtime] AUDIO EVENT:",
              event.type,
              event,
            );
          }

          void handleRealtimeEvent(event);
        } catch {
          setRealtimeError("SmartPark returned an invalid realtime event.");
        }
      };

      const offer = await peerConnection.createOffer();
      await peerConnection.setLocalDescription(offer);

      const localDescription = peerConnection.localDescription;

      if (!localDescription?.sdp) {
        throw new Error("Could not create the WebRTC SDP offer.");
      }

      console.log("[SmartPark Realtime] Local audio senders:",
        peerConnection.getSenders().map((sender) => ({
          kind: sender.track?.kind,
          enabled: sender.track?.enabled,
          muted: sender.track?.muted,
          readyState: sender.track?.readyState,
          trackId: sender.track?.id,
        })),
      );

      const formData = new FormData();
      formData.append("sdp", localDescription.sdp);

      if (currentCoordinates) {
        formData.append("latitude", String(currentCoordinates.latitude));
        formData.append("longitude", String(currentCoordinates.longitude));
      }

      const response = await api.post<string>(
        "/ai/realtime/session",
        formData,
        {
          headers: {
            Accept: "application/sdp",
            "Content-Type": "multipart/form-data",
          },
          responseType: "text",
          timeout: 30000,
        },
      );

      const answerSdp = response.data;

      if (!answerSdp) {
        throw new Error("SmartPark returned an empty realtime SDP answer.");
      }

      await peerConnection.setRemoteDescription({
        type: "answer",
        sdp: answerSdp,
      });

      // Diagnostic only: verify that the RTP sender is actually transmitting
      // microphone packets after the WebRTC connection is established.
      realtimeMicStatsIntervalRef.current = setInterval(async () => {
        try {
          const stats = await peerConnection.getStats();
          const outboundAudio = Array.from(stats.values())
            .filter(
              (report) =>
                report.type === "outbound-rtp" &&
                report.kind === "audio",
            )
            .map((report) => ({
              bytesSent: report.bytesSent,
              packetsSent: report.packetsSent,
              packetsLost: report.packetsLost,
              audioLevel: report.audioLevel,
              trackIdentifier: report.trackIdentifier,
            }));

          console.log("[SmartPark Realtime] Outbound audio RTP stats:", outboundAudio);
        } catch (statsError) {
          console.warn("[SmartPark Realtime] Could not read outbound audio RTP stats:", statsError);
        }
      }, 2000);
    } catch (error) {
      stopRealtimeVoice();
      setRealtimeError(
        getApiErrorMessage(error) ||
          "I couldn't start the SmartPark realtime voice conversation. Please try again.",
      );
    } finally {
      setIsRealtimeConnecting(false);
    }
  };

  const toggleInteractionMode = (mode: InteractionMode) => {
    if (mode === interactionMode) {
      return;
    }

    if (mode === "text") {
      stopRealtimeVoice();
      setRealtimeError(null);
      setInteractionMode("text");
      return;
    }

    stopSpeech();
    stopVoiceInput();
    setInteractionMode("voice");
    void startRealtimeVoice();
  };

  useEffect(() => {
    return () => {
      stopRealtimeVoice();
    };
  }, []);

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
    stopSpeech();
    setPendingPaymentReservationNumber(null);
    setIsOpen(false);

    navigate(
      `/reservations?payReservation=${encodeURIComponent(reservationNumber)}`,
    );
  };

  const handlePayActiveSession = (sessionId: number) => {
    stopSpeech();
    setIsOpen(false);

    const params = new URLSearchParams({
      checkout: "1",
      sessionId: String(sessionId),
    });

    navigate(`/payments?${params.toString()}`);
  };

  // ----------------------------------------------------------
  // Receipt attachment
  // ----------------------------------------------------------

  const handleAttachmentChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];

    if (!file) {
      return;
    }

    const allowedTypes = new Set([
      "application/pdf",
      "image/jpeg",
      "image/png",
      "image/webp",
    ]);

    if (!allowedTypes.has(file.type.toLowerCase())) {
      window.alert(
        "Please attach a SmartPark receipt as a PDF, JPEG, PNG, or WebP file.",
      );
      event.target.value = "";
      return;
    }

    const maxAttachmentBytes = 10 * 1024 * 1024;

    if (file.size > maxAttachmentBytes) {
      window.alert("Receipt attachments must not exceed 10 MB.");
      event.target.value = "";
      return;
    }

    setSelectedAttachment({
      file,
      name: file.name,
      size: file.size,
    });
  };

  const removeAttachment = () => {
    setSelectedAttachment(null);

    if (attachmentInputRef.current) {
      attachmentInputRef.current.value = "";
    }
  };

  // ----------------------------------------------------------
  // Send message
  // ----------------------------------------------------------

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    stopSpeech();

    const trimmedMessage =
      input.trim() || (selectedAttachment ? "Please verify this receipt." : "");

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
      attachmentName: selectedAttachment?.name,
    };

    const attachmentToSend = selectedAttachment?.file ?? null;

    setMessages((previous) => [...previous, userMessage]);

    setInput("");
    setSelectedAttachment(null);

    if (attachmentInputRef.current) {
      attachmentInputRef.current.value = "";
    }

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

      const chatPayload = {
        message: trimmedMessage,
        latitude: currentCoordinates?.latitude ?? null,
        longitude: currentCoordinates?.longitude ?? null,
        previous_response_id: previousResponseId,
      };

      const response = attachmentToSend
        ? await aiApi.chatWithAttachment(chatPayload, attachmentToSend)
        : await aiApi.chat(chatPayload);

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

      const paymentSessionId = parseSessionPaymentId(response.message);

      let assistantContent = removeSessionPaymentMarker(response.message);

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
        paymentSessionId,
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

    stopRealtimeVoice();
    setRealtimeError(null);

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
    setSelectedAttachment(null);

    if (attachmentInputRef.current) {
      attachmentInputRef.current.value = "";
    }

    setInput("");
    setRealtimeTextInput("");

    setTimeout(() => {
      inputRef.current?.focus();
    }, 50);
  };

  // ----------------------------------------------------------
  // Minimize / close
  // ----------------------------------------------------------

  const minimizeChat = () => {
    // IMPORTANT: minimizing/hiding the chatbot must preserve the active
    // conversation, including an ongoing WebRTC voice session.
    setIsOpen(false);
  };

  const toggleMaximizeChat = () => {
    setIsMaximized((previous) => !previous);
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
          {isRealtimeConnected && (
            <button
              type="button"
              onClick={openChat}
              className="mb-1 flex items-center gap-2 rounded-full border border-emerald-200 bg-white px-3 py-2 text-[10px] font-semibold text-slate-700 shadow-lg transition hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-emerald-100"
              aria-label="Reopen active SmartPark AI voice conversation"
              title="Reopen active voice conversation"
            >
              <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
              Live voice conversation active
            </button>
          )}

          {showLaunchGreeting && !isRealtimeConnected && (
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
          className={`
            fixed
            z-50
            flex
            min-h-0
            flex-col
            overflow-hidden
            rounded-2xl
            ${
              isMaximized
                ? "inset-3 h-[calc(100vh-24px)] w-[calc(100vw-24px)] md:inset-5 md:h-[calc(100vh-40px)] md:w-[calc(100vw-40px)]"
                : "bottom-5 right-5 h-[min(680px,calc(100vh-40px))] w-[min(420px,calc(100vw-40px))]"
            }
            border
            border-slate-200
            bg-white
            shadow-[0_20px_60px_rgba(15,23,42,0.25)]
          `}
        >
          {/* ==================================================
              Header
              ================================================== */}

          <div
            className="
              sticky
              top-0
              z-40
              flex
              shrink-0
              items-center
              justify-between
              bg-[#0b2a4a]
              px-5
              py-4
              text-white
            "
          >
            <div className="flex min-w-0 flex-1 items-center gap-3">
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

              <div className="min-w-0">
                <div className="truncate text-sm font-semibold">
                  SmartPark AI
                </div>

                <div className="mt-0.5 flex items-center gap-1.5 text-xs text-blue-100">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                  Your reliable Parking Assistant
                </div>
              </div>
            </div>

            {/* ==================================================
                Header Controls
                ================================================== */}

            <div className="ml-2 flex shrink-0 items-center gap-0.5">
              {/* Clear Chat */}

              <button
                type="button"
                onClick={handleClearChat}
                aria-label="Clear chat history"
                title="Clear chat"
                className="
                  flex
                  h-8
                  w-8
                  shrink-0
                  items-center
                  justify-center
                  rounded-lg
                  p-1.5
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

              {/* Maximize / restore */}

              <button
                type="button"
                onClick={toggleMaximizeChat}
                aria-label={
                  isMaximized
                    ? "Restore SmartPark AI size"
                    : "Maximize SmartPark AI"
                }
                title={isMaximized ? "Restore" : "Maximize"}
                className="
                  flex
                  h-8
                  w-8
                  shrink-0
                  items-center
                  justify-center
                  rounded-lg
                  p-1.5
                  text-white/80
                  transition
                  hover:bg-white/10
                  hover:text-white
                  focus:outline-none
                "
              >
                {isMaximized ? (
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    className="h-5 w-5"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M9 15H5V11M15 9h4v4"
                    />
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M5 15l5-5M19 9l-5 5"
                    />
                  </svg>
                ) : (
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    className="h-5 w-5"
                    aria-hidden="true"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5"
                    />
                  </svg>
                )}
              </button>

              {/* Minimize */}

              <button
                type="button"
                onClick={minimizeChat}
                aria-label="Minimize SmartPark AI"
                title="Minimize"
                className="
                  flex
                  h-8
                  w-8
                  shrink-0
                  items-center
                  justify-center
                  rounded-lg
                  p-1.5
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
                  flex
                  h-8
                  w-8
                  shrink-0
                  items-center
                  justify-center
                  rounded-lg
                  p-1.5
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
              Interaction Mode
              ================================================== */}

          <div className="sticky top-0 z-30 shrink-0 border-b border-white/10 bg-[#0b2a4a] px-4 pb-3">
            <div className="flex items-center justify-between gap-3 rounded-xl bg-white/10 p-1">
              <button
                type="button"
                onClick={() => toggleInteractionMode("text")}
                className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-[11px] font-semibold transition ${
                  interactionMode === "text"
                    ? "bg-white text-[#0b2a4a] shadow-sm"
                    : "text-white/80 hover:bg-white/10 hover:text-white"
                }`}
                aria-pressed={interactionMode === "text"}
              >
                <span aria-hidden="true">⌨</span>
                Text
              </button>

              <button
                type="button"
                onClick={() => toggleInteractionMode("voice")}
                className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-[11px] font-semibold transition ${
                  interactionMode === "voice"
                    ? "bg-white text-[#0b2a4a] shadow-sm"
                    : "text-white/80 hover:bg-white/10 hover:text-white"
                }`}
                aria-pressed={interactionMode === "voice"}
              >
                <span aria-hidden="true">🎙</span>
                Voice
              </button>
            </div>

            {interactionMode === "voice" && (
              <div className="mt-2 flex items-center justify-between gap-2 px-1 text-[10px] text-blue-100">
                <span>
                  {isRealtimeConnecting
                    ? "Connecting to SmartPark AI…"
                    : isRealtimeConnected
                      ? isRealtimePaused
                        ? "Voice conversation paused"
                        : "Live voice conversation"
                      : "Voice conversation offline"}
                </span>

                {isRealtimeConnected && (
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={
                        isRealtimePaused
                          ? resumeRealtimeVoice
                          : pauseRealtimeVoice
                      }
                      className="rounded-md bg-white/10 px-2 py-1 font-semibold text-white hover:bg-white/20"
                    >
                      {isRealtimePaused ? "Resume voice" : "Pause voice"}
                    </button>
                    <button
                      type="button"
                      onClick={() => stopRealtimeVoice()}
                      className="rounded-md bg-white/10 px-2 py-1 font-semibold text-white hover:bg-white/20"
                    >
                      End voice
                    </button>
                  </div>
                )}
              </div>
            )}

            {realtimeError && interactionMode === "voice" && (
              <div className="mt-2 rounded-lg bg-red-400/10 px-2.5 py-2 text-[10px] leading-4 text-red-100">
                {realtimeError}
              </div>
            )}
          </div>

          {/* ==================================================
              Location Status
              ================================================== */}

          <div
            className="
              flex
              shrink-0
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
              min-h-0
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
                        ? isStructuredAssistantContent(
                            message.content,
                            coordinates,
                          )
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
                    renderAssistantContent(
                      message.content,
                      coordinates,
                      navigate,
                    )
                  ) : (
                    <div className="space-y-2">
                      {message.attachmentName && (
                        <div className="flex items-center gap-2 rounded-lg bg-white/10 px-2.5 py-2 text-xs">
                          <svg
                            xmlns="http://www.w3.org/2000/svg"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="1.8"
                            className="h-4 w-4 shrink-0"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              d="m15.5 5.5-7.8 7.8a3 3 0 1 0 4.2 4.2l8-8a5 5 0 0 0-7.1-7.1l-8 8a7 7 0 1 0 9.9 9.9l6.2-6.2"
                            />
                          </svg>
                          <span className="min-w-0 truncate">
                            {message.attachmentName}
                          </span>
                        </div>
                      )}
                      <div className="whitespace-pre-wrap">
                        {message.content}
                      </div>
                    </div>
                  )}

                  {message.role === "assistant" &&
                    interactionMode === "text" &&
                    speechOutputSupported && (
                      <div className="mt-2 flex justify-end">
                        <button
                          type="button"
                          onClick={() =>
                            isSpeakingMessageId === message.id
                              ? stopSpeech()
                              : speakAssistantMessage(
                                  message.id,
                                  message.content,
                                )
                          }
                          aria-label={
                            isSpeakingMessageId === message.id
                              ? "Stop speaking"
                              : "Speak this response"
                          }
                          title={
                            isSpeakingMessageId === message.id
                              ? "Stop speaking"
                              : "Read response aloud"
                          }
                          className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-[10px] font-medium text-slate-400 transition hover:bg-slate-100 hover:text-[#0b2a4a] focus:outline-none focus:ring-2 focus:ring-blue-100"
                        >
                          {isSpeakingMessageId === message.id ? (
                            <>
                              <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="1.8"
                                className="h-3.5 w-3.5"
                                aria-hidden="true"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M8 7v10M16 7v10"
                                />
                              </svg>
                              Stop speaking
                            </>
                          ) : (
                            <>
                              <svg
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                strokeWidth="1.8"
                                className="h-3.5 w-3.5"
                                aria-hidden="true"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M11 5 6 9H3v6h3l5 4V5Z"
                                />
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M15.5 8.5a5 5 0 0 1 0 7M18 6a8.5 8.5 0 0 1 0 12"
                                />
                              </svg>
                              Listen
                            </>
                          )}
                        </button>
                      </div>
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
                  {message.role === "assistant" && message.paymentSessionId && (
                    <button
                      type="button"
                      onClick={() =>
                        handlePayActiveSession(message.paymentSessionId!)
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
                      Pay for Parking Session
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

              <button
                type="button"
                onClick={() => sendQuickPrompt("Show me my reservations.")}
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
                My reservations
              </button>

              <button
                type="button"
                onClick={() =>
                  sendQuickPrompt(
                    "Do I currently have an active parking session?",
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
                Active session
              </button>
            </div>
          </div>

          {/* ==================================================
              Input
              ================================================== */}

          <form
            onSubmit={handleSubmit}
            className={`
              ${interactionMode === "voice" ? "hidden" : ""}
              border-t
              border-slate-200
              bg-white
              p-3
            `}
          >
            <input
              ref={attachmentInputRef}
              type="file"
              accept="application/pdf,image/jpeg,image/png,image/webp"
              onChange={handleAttachmentChange}
              className="hidden"
              aria-label="Attach receipt"
            />

            {selectedAttachment && (
              <div className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50 px-3 py-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white text-blue-700 shadow-sm">
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      className="h-4 w-4"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="m15.5 5.5-7.8 7.8a3 3 0 1 0 4.2 4.2l8-8a5 5 0 0 0-7.1-7.1l-8 8a7 7 0 1 0 9.9 9.9l6.2-6.2"
                      />
                    </svg>
                  </span>
                  <div className="min-w-0">
                    <p className="truncate text-xs font-medium text-slate-700">
                      {selectedAttachment.name}
                    </p>
                    <p className="text-[10px] text-slate-400">
                      Receipt attached •{" "}
                      {(selectedAttachment.size / 1024 / 1024).toFixed(2)} MB
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={removeAttachment}
                  disabled={isSending}
                  className="shrink-0 rounded-lg p-1.5 text-slate-400 transition hover:bg-white hover:text-slate-700 disabled:opacity-50"
                  aria-label="Remove receipt attachment"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    className="h-4 w-4"
                  >
                    <path strokeLinecap="round" d="M6 6l12 12M18 6 6 18" />
                  </svg>
                </button>
              </div>
            )}

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
              <button
                type="button"
                onClick={() => attachmentInputRef.current?.click()}
                disabled={isSending}
                aria-label="Attach receipt"
                title="Attach receipt"
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-white hover:text-[#0b2a4a] disabled:cursor-not-allowed disabled:opacity-40"
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
                    d="m15.5 5.5-7.8 7.8a3 3 0 1 0 4.2 4.2l8-8a5 5 0 0 0-7.1-7.1l-8 8a7 7 0 1 0 9.9 9.9l6.2-6.2"
                  />
                </svg>
              </button>

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
                type="button"
                onClick={toggleVoiceInput}
                disabled={isSending || !speechSupported}
                aria-label={
                  isListening ? "Stop voice input" : "Start voice input"
                }
                title={
                  !speechSupported
                    ? "Voice input is not supported by this browser"
                    : isListening
                      ? "Stop voice input"
                      : "Speak to SmartPark AI"
                }
                className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-lg transition focus:outline-none focus:ring-4 focus:ring-blue-100 ${
                  isListening
                    ? "bg-red-500 text-white hover:bg-red-600"
                    : speechSupported
                      ? "text-slate-500 hover:bg-white hover:text-blue-600"
                      : "cursor-not-allowed text-slate-300"
                }`}
              >
                {isListening && (
                  <span className="absolute inset-0 animate-ping rounded-lg bg-red-400/30" />
                )}
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  className="relative h-5 w-5"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"
                  />
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3M8 22h8"
                  />
                </svg>
              </button>

              <button
                type="submit"
                disabled={isSending || (!input.trim() && !selectedAttachment)}
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

            {speechOutputError ? (
              <div className="mt-2 text-center text-[10px] text-amber-600">
                {speechOutputError}
              </div>
            ) : speechOutputSupported ? (
              <div className="mt-2 text-center text-[10px] text-slate-400">
                SmartPark AI will read new responses aloud. Use “Listen” on any
                response to replay it.
              </div>
            ) : null}

            <div className="mt-2 text-center text-[10px] text-slate-400">
              SmartPark AI uses your location only when you allow browser
              location access.
            </div>
          </form>

          {interactionMode === "voice" && (
            <div className="border-t border-slate-200 bg-white">
              <details open className="group">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 border-b border-slate-100 bg-slate-50 px-4 py-2.5 select-none focus:outline-none focus:ring-2 focus:ring-inset focus:ring-blue-100">
                  <div className="min-w-0">
                    <p className="text-[10px] font-semibold uppercase tracking-[0.08em] text-slate-500">
                      Voice controls
                    </p>
                    <p className="mt-0.5 truncate text-[10px] text-slate-400">
                      {isRealtimeConnecting
                        ? "Connecting to SmartPark AI…"
                        : isRealtimeConnected
                          ? isRealtimePaused
                            ? "Conversation paused"
                            : "Conversation active"
                          : "Voice conversation offline"}
                    </p>
                  </div>

                  <span
                    className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-[10px] font-semibold text-slate-600 shadow-sm transition group-hover:bg-slate-50"
                    aria-hidden="true"
                  >
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      className="h-3.5 w-3.5 transition-transform group-open:rotate-180"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="m6 9 6 6 6-6"
                      />
                    </svg>
                    <span>Minimize / Expand</span>
                  </span>
                </summary>

                <div className="p-4">
                  <div className="rounded-2xl border border-blue-100 bg-gradient-to-br from-slate-50 via-white to-blue-50/60 px-5 py-6 text-center">
                    <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-[#0b2a4a] text-white shadow-lg">
                      {isRealtimeConnecting ? (
                        <span className="h-7 w-7 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                      ) : (
                        <svg
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
                            d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"
                          />
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M19 10v2a7 7 0 0 1-14 0v-2M12 19v3M8 22h8"
                          />
                        </svg>
                      )}
                    </div>

                    <h3 className="mt-4 text-sm font-semibold text-slate-900">
                      {isRealtimeConnecting
                        ? "Connecting to SmartPark AI…"
                        : isRealtimeConnected
                          ? isRealtimePaused
                            ? "SmartPark AI is paused"
                            : "SmartPark AI is listening"
                          : "Start a voice conversation"}
                    </h3>

                    <p className="mx-auto mt-1.5 max-w-sm text-xs leading-5 text-slate-500">
                      {isRealtimeConnected
                        ? isRealtimePaused
                          ? "Voice input is paused. Your conversation remains active, and you can resume without starting a new conversation."
                          : "Speak naturally. SmartPark AI will listen, respond aloud, and keep the conversation visible as text."
                        : "Use natural speech to ask questions, find parking, manage vehicles, make reservations, check sessions, and use the same SmartPark AI capabilities available in text mode."}
                    </p>

                    {!isRealtimeConnected && !isRealtimeConnecting && (
                      <button
                        type="button"
                        onClick={() => void startRealtimeVoice()}
                        className="mt-5 inline-flex items-center justify-center gap-2 rounded-xl bg-[#0b2a4a] px-5 py-3 text-xs font-semibold text-white shadow-sm transition hover:bg-[#123b63] focus:outline-none focus:ring-4 focus:ring-blue-100"
                      >
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
                            d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"
                          />
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M19 10v2a7 7 0 0 1-14 0v-2"
                          />
                        </svg>
                        Start Voice Conversation
                      </button>
                    )}

                    {isRealtimeConnected && (
                      <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
                        <button
                          type="button"
                          onClick={
                            isRealtimePaused
                              ? resumeRealtimeVoice
                              : pauseRealtimeVoice
                          }
                          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-blue-100"
                        >
                          <span aria-hidden="true">
                            {isRealtimePaused ? "▶" : "⏸"}
                          </span>
                          {isRealtimePaused ? "Resume Voice" : "Pause Voice"}
                        </button>

                        <button
                          type="button"
                          onClick={stopRealtimeVoice}
                          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-xs font-semibold text-slate-700 shadow-sm transition hover:bg-slate-50 focus:outline-none focus:ring-4 focus:ring-blue-100"
                        >
                          End Voice Conversation
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              </details>

              {isRealtimeConnected && (
                <div className="px-4 pb-4">
                  <form
                    onSubmit={(event) => {
                      event.preventDefault();
                      void sendRealtimeTextCommand();
                    }}
                    className="text-left"
                  >
                    <div className="mb-2 flex items-center justify-between gap-2">
                      <label
                        htmlFor="smartpark-realtime-text-input"
                        className="text-[11px] font-semibold text-slate-600"
                      >
                        Type a command
                      </label>
                      <span className="text-[10px] text-slate-400">
                        Voice response enabled
                      </span>
                    </div>

                    <input
                      ref={realtimeAttachmentInputRef}
                      type="file"
                      accept="application/pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.json,image/jpeg,image/png,image/webp"
                      onChange={handleRealtimeAttachmentChange}
                      className="hidden"
                      aria-label="Attach document to live conversation"
                    />

                    {realtimeSelectedAttachment && (
                      <div className="mb-2 flex items-center justify-between gap-3 rounded-xl border border-blue-100 bg-blue-50 px-3 py-2">
                        <div className="flex min-w-0 items-center gap-2">
                          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white text-blue-700 shadow-sm">
                            📎
                          </span>
                          <div className="min-w-0">
                            <p className="truncate text-xs font-medium text-slate-700">
                              {realtimeSelectedAttachment.name}
                            </p>
                            <p className="text-[10px] text-slate-400">
                              Document attached •{" "}
                              {(
                                realtimeSelectedAttachment.size /
                                1024 /
                                1024
                              ).toFixed(2)}{" "}
                              MB
                            </p>
                          </div>
                        </div>

                        <button
                          type="button"
                          onClick={removeRealtimeAttachment}
                          className="shrink-0 rounded-lg px-2 py-1 text-xs font-medium text-slate-500 hover:bg-white hover:text-slate-700"
                        >
                          Remove
                        </button>
                      </div>
                    )}

                    <div className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-1.5 shadow-sm focus-within:border-blue-300 focus-within:ring-2 focus-within:ring-blue-100">
                      <button
                        type="button"
                        onClick={() =>
                          realtimeAttachmentInputRef.current?.click()
                        }
                        aria-label="Attach document"
                        title="Attach document"
                        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-slate-500 transition hover:bg-blue-50 hover:text-blue-700"
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
                            d="m15.5 5.5-7.8 7.8a3 3 0 1 0 4.2 4.2l8-8a5 5 0 1 0-7.1-7.1l-8 8a7 7 0 1 0 9.9 9.9l6.2-6.2"
                          />
                        </svg>
                      </button>

                      <input
                        ref={realtimeTextInputRef}
                        id="smartpark-realtime-text-input"
                        type="text"
                        value={realtimeTextInput}
                        onChange={(event) =>
                          setRealtimeTextInput(event.target.value)
                        }
                        placeholder="Type if you'd rather not speak…"
                        maxLength={4000}
                        className="min-w-0 flex-1 bg-transparent px-2 py-2 text-xs text-slate-700 outline-none placeholder:text-slate-400"
                      />

                      <button
                        type="submit"
                        disabled={
                          !realtimeTextInput.trim() &&
                          !realtimeSelectedAttachment
                        }
                        aria-label="Send typed command"
                        title="Send typed command"
                        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-[#0b2a4a] text-white transition hover:bg-[#123b63] disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
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

                    <p className="mt-2 text-center text-[10px] leading-4 text-slate-400">
                      Type a command or attach a document whenever speaking is
                      difficult. SmartPark AI will review the document, answer
                      aloud, and keep the exchange in this conversation.
                    </p>
                  </form>
                </div>
              )}

              {realtimeError && (
                <p className="px-4 pb-2 text-[10px] leading-4 text-red-600">
                  {realtimeError}
                </p>
              )}

              <p className="px-4 pb-4 text-center text-[10px] text-slate-400">
                Your microphone stays active only while the realtime voice
                conversation is connected.
              </p>
            </div>
          )}
        </div>
      )}
    </>
  );
}
