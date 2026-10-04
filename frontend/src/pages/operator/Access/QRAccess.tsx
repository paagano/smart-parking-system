import { useState } from "react";
import {
  CheckCircle2,
  Clock3,
  Copy,
  QrCode,
  RefreshCw,
  ShieldCheck,
  Smartphone,
} from "lucide-react";
import { QRCodeSVG } from "qrcode.react";

import Page from "../../../components/common/Page";
import {
  qrAccessApi,
  type QRAccessPurpose,
  type QRAccessTokenDisplayResponse,
} from "../../../api/api";

type QRMode = QRAccessPurpose;

function formatExpiry(value: string): string {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "Unknown";
  }

  return date.toLocaleString();
}

function isExpired(value: string): boolean {
  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return true;
  }

  return date.getTime() <= Date.now();
}

export default function QRAccess() {
  const [mode, setMode] = useState<QRMode>("ENTRY");

  const [token, setToken] = useState<QRAccessTokenDisplayResponse | null>(null);

  const [loading, setLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [copied, setCopied] = useState(false);

  const generateToken = async (purpose: QRMode = mode): Promise<void> => {
    setLoading(true);
    setError(null);
    setCopied(false);

    try {
      const response = await qrAccessApi.createToken(purpose, 300);

      setMode(purpose);
      setToken(response);
    } catch (requestError: any) {
      const detail =
        requestError?.response?.data?.detail ??
        requestError?.message ??
        "Failed to generate QR access token.";

      setError(String(detail));
      setToken(null);
    } finally {
      setLoading(false);
    }
  };

  const copyToken = async (): Promise<void> => {
    if (!token?.raw_token) {
      return;
    }

    try {
      await navigator.clipboard.writeText(token.raw_token);

      setCopied(true);

      window.setTimeout(() => {
        setCopied(false);
      }, 2000);
    } catch {
      setError("The QR token could not be copied to the clipboard.");
    }
  };

  const expired = token ? isExpired(token.expires_at) : false;

  const displayValue = token?.qr_url || token?.raw_token || "";

  return (
    <div>
      <Page
        title="QR Access"
        text="Generate temporary QR codes for controlled parking entry and exit."
      />

      <div className="space-y-6">
        {/* ==================================================
            PURPOSE SELECTION
        ================================================== */}

        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex items-start gap-3">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
              <QrCode size={22} />
            </div>

            <div>
              <h2 className="text-base font-black text-slate-900">
                QR Access Control
              </h2>

              <p className="mt-1 text-sm leading-6 text-slate-500">
                Display a temporary QR code that a driver can scan with a mobile
                phone.
              </p>
            </div>
          </div>

          <div className="mt-6 grid gap-4 sm:grid-cols-2">
            {/* ENTRY */}

            <button
              type="button"
              onClick={() => {
                setMode("ENTRY");
                setToken(null);
                setError(null);
                setCopied(false);
              }}
              className={`rounded-2xl border p-5 text-left transition ${
                mode === "ENTRY"
                  ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                  : "border-slate-200 bg-white hover:border-emerald-300"
              }`}
            >
              <div className="flex items-start gap-3">
                <div
                  className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${
                    mode === "ENTRY"
                      ? "bg-emerald-600 text-white"
                      : "bg-slate-100 text-slate-500"
                  }`}
                >
                  <Smartphone size={20} />
                </div>

                <div>
                  <h3 className="font-black text-slate-900">Entry QR</h3>

                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    Driver scans this code when arriving at the parking
                    facility.
                  </p>
                </div>

                {mode === "ENTRY" && (
                  <CheckCircle2
                    size={20}
                    className="ml-auto shrink-0 text-emerald-600"
                  />
                )}
              </div>
            </button>

            {/* EXIT */}

            <button
              type="button"
              onClick={() => {
                setMode("EXIT");
                setToken(null);
                setError(null);
                setCopied(false);
              }}
              className={`rounded-2xl border p-5 text-left transition ${
                mode === "EXIT"
                  ? "border-blue-500 bg-blue-50 ring-2 ring-blue-100"
                  : "border-slate-200 bg-white hover:border-blue-300"
              }`}
            >
              <div className="flex items-start gap-3">
                <div
                  className={`grid h-11 w-11 shrink-0 items-center justify-center rounded-xl ${
                    mode === "EXIT"
                      ? "bg-blue-600 text-white"
                      : "bg-slate-100 text-slate-500"
                  }`}
                >
                  <QrCode size={20} />
                </div>

                <div>
                  <h3 className="font-black text-slate-900">Exit QR</h3>

                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    Driver scans this code when leaving the parking facility.
                  </p>
                </div>

                {mode === "EXIT" && (
                  <CheckCircle2
                    size={20}
                    className="ml-auto shrink-0 text-blue-600"
                  />
                )}
              </div>
            </button>
          </div>

          <button
            type="button"
            onClick={() => generateToken(mode)}
            disabled={loading}
            className="mt-6 inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-black text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw
              size={16}
              className={loading ? "animate-spin" : undefined}
            />

            {loading
              ? "Generating..."
              : `Generate ${mode === "ENTRY" ? "Entry" : "Exit"} QR`}
          </button>
        </section>

        {/* ==================================================
            ERROR
        ================================================== */}

        {error && (
          <section className="rounded-2xl border border-rose-200 bg-rose-50 p-5">
            <p className="text-sm font-bold text-rose-700">{error}</p>
          </section>
        )}

        {/* ==================================================
            QR DISPLAY
        ================================================== */}

        {token && (
          <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-100 px-6 py-5">
              <div className="flex items-center gap-3">
                <div className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                  <QrCode size={20} />
                </div>

                <div>
                  <h2 className="text-base font-black text-slate-900">
                    {token.purpose === "ENTRY"
                      ? "Entry QR Code"
                      : "Exit QR Code"}
                  </h2>

                  <p className="text-xs text-slate-500">
                    Facility {token.facility_id}
                  </p>
                </div>

                <span
                  className={`ml-auto rounded-full px-3 py-1 text-[10px] font-black uppercase ${
                    expired
                      ? "bg-rose-100 text-rose-700"
                      : token.is_active
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-slate-100 text-slate-600"
                  }`}
                >
                  {expired
                    ? "Expired"
                    : token.is_active
                      ? "Active"
                      : "Inactive"}
                </span>
              </div>
            </div>

            <div className="grid gap-8 p-6 lg:grid-cols-[auto_1fr] lg:items-center">
              {/* QR */}

              <div className="flex justify-center">
                <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                  <QRCodeSVG
                    value={displayValue}
                    size={300}
                    level="H"
                    includeMargin
                  />
                </div>
              </div>

              {/* Details */}

              <div className="min-w-0">
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                  <div className="flex items-start gap-3">
                    <ShieldCheck
                      size={19}
                      className="mt-0.5 shrink-0 text-emerald-600"
                    />

                    <div>
                      <h3 className="text-sm font-black text-slate-900">
                        Temporary secure access
                      </h3>

                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        This QR code uses a temporary access token. It expires
                        automatically and is scoped to this parking facility.
                      </p>
                    </div>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  <div className="rounded-xl border border-slate-200 bg-white p-4">
                    <div className="flex items-center gap-2 text-slate-400">
                      <Clock3 size={15} />

                      <span className="text-[10px] font-black uppercase tracking-wider">
                        Expires
                      </span>
                    </div>

                    <p className="mt-2 text-sm font-bold text-slate-800">
                      {formatExpiry(token.expires_at)}
                    </p>
                  </div>

                  <div className="rounded-xl border border-slate-200 bg-white p-4">
                    <span className="text-[10px] font-black uppercase tracking-wider text-slate-400">
                      Purpose
                    </span>

                    <p className="mt-2 text-sm font-black text-slate-800">
                      {token.purpose === "ENTRY"
                        ? "Parking Entry"
                        : "Parking Exit"}
                    </p>
                  </div>
                </div>

                <div className="mt-4">
                  <button
                    type="button"
                    onClick={copyToken}
                    className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-black text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
                  >
                    <Copy size={15} />

                    {copied ? "Copied" : "Copy access token"}
                  </button>
                </div>

                <p className="mt-4 text-[10px] leading-5 text-slate-400">
                  For physical deployment, display this QR code on the entrance
                  or exit operator screen so the driver can scan it using a
                  separate mobile phone.
                </p>
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
