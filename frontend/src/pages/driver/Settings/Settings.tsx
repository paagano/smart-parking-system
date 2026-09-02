import { useEffect, useState } from "react";
import type React from "react";
import {
  Bell,
  Check,
  ChevronDown,
  LockKeyhole,
  Mail,
  Moon,
  Palette,
  Phone,
  Save,
  ShieldCheck,
  Sun,
  User,
  UserRound,
} from "lucide-react";

import { usersApi } from "../../../api";

// ==========================================================
// Types
// ==========================================================

interface NotificationPreferences {
  parkingSession: boolean;
  payment: boolean;
  reservations: boolean;
  loyalty: boolean;
  system: boolean;
}

interface DisplayPreferences {
  compactMode: boolean;
  use24HourTime: boolean;
}

// ==========================================================
// Storage
// ==========================================================

const NOTIFICATION_PREFERENCES_KEY =
  "smartpark_driver_notification_preferences";

const DISPLAY_PREFERENCES_KEY = "smartpark_driver_display_preferences";

const DEFAULT_NOTIFICATION_PREFERENCES: NotificationPreferences = {
  parkingSession: true,
  payment: true,
  reservations: true,
  loyalty: true,
  system: true,
};

const DEFAULT_DISPLAY_PREFERENCES: DisplayPreferences = {
  compactMode: false,
  use24HourTime: false,
};

// ==========================================================
// Helpers
// ==========================================================

function readStoredPreferences<T>(key: string, fallback: T): T {
  try {
    const stored = localStorage.getItem(key);

    if (!stored) {
      return fallback;
    }

    return {
      ...fallback,
      ...JSON.parse(stored),
    };
  } catch {
    return fallback;
  }
}

function saveStoredPreferences<T>(key: string, value: T) {
  localStorage.setItem(key, JSON.stringify(value));
}

function formatDate(value?: string | null): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleDateString("en-KE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatRole(role?: string | null): string {
  if (!role) {
    return "Driver";
  }

  return role
    .replace(/[_-]/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

// ==========================================================
// Component
// ==========================================================

export default function Settings() {
  const [user, setUser] = useState<Awaited<
    ReturnType<typeof usersApi.me>
  > | null>(null);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);

  const [savedMessage, setSavedMessage] = useState<string | null>(null);

  const [notificationPreferences, setNotificationPreferences] =
    useState<NotificationPreferences>(() =>
      readStoredPreferences(
        NOTIFICATION_PREFERENCES_KEY,
        DEFAULT_NOTIFICATION_PREFERENCES,
      ),
    );

  const [displayPreferences, setDisplayPreferences] =
    useState<DisplayPreferences>(() =>
      readStoredPreferences(
        DISPLAY_PREFERENCES_KEY,
        DEFAULT_DISPLAY_PREFERENCES,
      ),
    );

  const [expandedSection, setExpandedSection] = useState<string | null>(null);

  // ========================================================
  // Load current user
  // ========================================================

  useEffect(() => {
    let mounted = true;

    async function loadUser() {
      try {
        setLoading(true);
        setError(null);

        const currentUser = await usersApi.me();

        if (mounted) {
          setUser(currentUser);
        }
      } catch (err: any) {
        console.error("[SmartPark Settings] Failed to load current user:", err);

        if (mounted) {
          setError(
            err?.response?.data?.detail ??
              err?.message ??
              "Unable to load your account information.",
          );
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    void loadUser();

    return () => {
      mounted = false;
    };
  }, []);

  // ========================================================
  // Save preferences
  // ========================================================

  function savePreferences() {
    saveStoredPreferences(
      NOTIFICATION_PREFERENCES_KEY,
      notificationPreferences,
    );

    saveStoredPreferences(DISPLAY_PREFERENCES_KEY, displayPreferences);

    setSavedMessage("Your preferences have been saved.");

    window.setTimeout(() => {
      setSavedMessage(null);
    }, 3000);
  }

  function toggleNotification(key: keyof NotificationPreferences) {
    setNotificationPreferences((current) => ({
      ...current,
      [key]: !current[key],
    }));
  }

  // ========================================================
  // Loading state
  // ========================================================

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <div className="h-8 w-48 animate-pulse rounded bg-slate-200" />
          <div className="mt-2 h-4 w-96 animate-pulse rounded bg-slate-200" />
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="h-72 animate-pulse rounded-2xl border border-slate-200 bg-white" />
          <div className="h-72 animate-pulse rounded-2xl border border-slate-200 bg-white lg:col-span-2" />
        </div>

        <div className="h-80 animate-pulse rounded-2xl border border-slate-200 bg-white" />
      </div>
    );
  }

  // ========================================================
  // Render
  // ========================================================

  return (
    <div className="space-y-6">
      {/* ====================================================
          HEADER
      ==================================================== */}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
              <UserRound size={24} />
            </div>

            <div>
              <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
                Settings
              </h1>

              <p className="mt-1 text-sm text-slate-500">
                Manage your SmartPark account and personal preferences.
              </p>
            </div>
          </div>
        </div>

        <button
          type="button"
          onClick={savePreferences}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-2.5 text-sm font-bold text-white shadow-sm transition hover:bg-slate-800"
        >
          <Save size={16} />
          Save Preferences
        </button>
      </div>

      {/* ====================================================
          SUCCESS
      ==================================================== */}

      {savedMessage && (
        <div className="flex items-center gap-3 rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-700">
          <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-emerald-100">
            <Check size={16} />
          </div>

          {savedMessage}
        </div>
      )}

      {/* ====================================================
          ERROR
      ==================================================== */}

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <p className="font-bold">Unable to load account information</p>
          <p className="mt-1">{error}</p>
        </div>
      )}

      {/* ====================================================
          PROFILE
      ==================================================== */}

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col items-center text-center">
            <div className="grid h-24 w-24 place-items-center rounded-full bg-emerald-50 text-emerald-600 ring-8 ring-emerald-50/60">
              <User size={42} />
            </div>

            <h2 className="mt-5 text-xl font-extrabold text-slate-900">
              {user ? `${user.first_name} ${user.last_name}` : "Driver"}
            </h2>

            <p className="mt-1 text-sm text-slate-500">{user?.email ?? "—"}</p>

            <span className="mt-4 inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700">
              <ShieldCheck size={14} />
              {formatRole(user?.role)}
            </span>

            <div className="mt-6 w-full border-t border-slate-100 pt-5 text-left">
              <div className="flex items-center justify-between">
                <span className="text-sm text-slate-500">Account status</span>

                <span
                  className={`text-sm font-bold ${
                    user?.is_active ? "text-emerald-600" : "text-rose-600"
                  }`}
                >
                  {user?.is_active ? "Active" : "Inactive"}
                </span>
              </div>

              <div className="mt-3 flex items-center justify-between">
                <span className="text-sm text-slate-500">Verification</span>

                <span className="text-sm font-bold text-slate-800">
                  {user?.is_verified ? "Verified" : "Not verified"}
                </span>
              </div>

              <div className="mt-3 flex items-center justify-between">
                <span className="text-sm text-slate-500">Member since</span>

                <span className="text-sm font-bold text-slate-800">
                  {formatDate(user?.created_at)}
                </span>
              </div>
            </div>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">
              Account Information
            </p>

            <h2 className="mt-1 text-lg font-extrabold text-slate-900">
              Personal details
            </h2>

            <p className="mt-1 text-sm text-slate-500">
              Information associated with your SmartPark account.
            </p>
          </div>

          <div className="mt-6 grid gap-4 md:grid-cols-2">
            <InfoField
              icon={<User size={17} />}
              label="First name"
              value={user?.first_name ?? "—"}
            />

            <InfoField
              icon={<User size={17} />}
              label="Last name"
              value={user?.last_name ?? "—"}
            />

            <InfoField
              icon={<Mail size={17} />}
              label="Email address"
              value={user?.email ?? "—"}
            />

            <InfoField
              icon={<Phone size={17} />}
              label="Phone number"
              value={String(user?.phone_number ?? "—")}
            />
          </div>

          <div className="mt-5 rounded-xl bg-slate-50 p-4 text-sm text-slate-500">
            Your account details are managed by SmartPark authentication.
            Profile editing can be enabled here once the corresponding backend
            update endpoint is exposed.
          </div>
        </div>
      </section>

      {/* ====================================================
          NOTIFICATION PREFERENCES
      ==================================================== */}

      <SettingsSection
        title="Notification Preferences"
        description="Choose which SmartPark activity notifications you want to receive."
        icon={<Bell size={21} />}
        expanded={expandedSection === "notifications"}
        onToggle={() =>
          setExpandedSection((current) =>
            current === "notifications" ? null : "notifications",
          )
        }
      >
        <PreferenceRow
          title="Parking session updates"
          description="Check-in, session completion and vehicle exit activity."
          enabled={notificationPreferences.parkingSession}
          onToggle={() => toggleNotification("parkingSession")}
        />

        <PreferenceRow
          title="Payment notifications"
          description="Successful payments, payment status and wallet activity."
          enabled={notificationPreferences.payment}
          onToggle={() => toggleNotification("payment")}
        />

        <PreferenceRow
          title="Reservation notifications"
          description="Reservation creation, confirmation, cancellation and expiry."
          enabled={notificationPreferences.reservations}
          onToggle={() => toggleNotification("reservations")}
        />

        <PreferenceRow
          title="Loyalty programme"
          description="Points, rewards and loyalty account activity."
          enabled={notificationPreferences.loyalty}
          onToggle={() => toggleNotification("loyalty")}
        />

        <PreferenceRow
          title="System notifications"
          description="Important SmartPark service and account notifications."
          enabled={notificationPreferences.system}
          onToggle={() => toggleNotification("system")}
        />
      </SettingsSection>

      {/* ====================================================
          DISPLAY PREFERENCES
      ==================================================== */}

      <SettingsSection
        title="Display & Preferences"
        description="Personalise how information is presented in your driver portal."
        icon={<Palette size={21} />}
        expanded={expandedSection === "display"}
        onToggle={() =>
          setExpandedSection((current) =>
            current === "display" ? null : "display",
          )
        }
      >
        <PreferenceRow
          title="Compact mode"
          description="Use a more compact layout when viewing parking information and lists."
          enabled={displayPreferences.compactMode}
          onToggle={() =>
            setDisplayPreferences((current) => ({
              ...current,
              compactMode: !current.compactMode,
            }))
          }
        />

        <PreferenceRow
          title="24-hour time"
          description="Display times using the 24-hour clock format."
          enabled={displayPreferences.use24HourTime}
          onToggle={() =>
            setDisplayPreferences((current) => ({
              ...current,
              use24HourTime: !current.use24HourTime,
            }))
          }
        />

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <PreferenceInfo
            icon={<Sun size={18} />}
            title="Light interface"
            description="Optimised for normal daytime use."
          />

          <PreferenceInfo
            icon={<Moon size={18} />}
            title="Dark interface"
            description="Can be added when the portal theme preference is connected."
          />
        </div>
      </SettingsSection>

      {/* ====================================================
          SECURITY
      ==================================================== */}

      <SettingsSection
        title="Security"
        description="Account security and authentication settings."
        icon={<LockKeyhole size={21} />}
        expanded={expandedSection === "security"}
        onToggle={() =>
          setExpandedSection((current) =>
            current === "security" ? null : "security",
          )
        }
      >
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
          <div className="flex items-start gap-4">
            <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-slate-600 shadow-sm">
              <LockKeyhole size={19} />
            </div>

            <div>
              <h3 className="font-extrabold text-slate-800">
                Password & authentication
              </h3>

              <p className="mt-1 text-sm leading-6 text-slate-500">
                Your SmartPark account is protected using authenticated access.
                Password-management controls should be connected here when the
                backend password-change endpoint is exposed.
              </p>
            </div>
          </div>
        </div>

        <div className="mt-4 rounded-2xl border border-emerald-100 bg-emerald-50/60 p-5">
          <div className="flex items-start gap-4">
            <ShieldCheck
              size={20}
              className="mt-0.5 shrink-0 text-emerald-600"
            />

            <div>
              <h3 className="font-extrabold text-emerald-800">
                Account protection
              </h3>

              <p className="mt-1 text-sm leading-6 text-emerald-700">
                Only your authenticated SmartPark account can access your driver
                data, parking sessions, payments, vehicles and loyalty
                information.
              </p>
            </div>
          </div>
        </div>
      </SettingsSection>

      {/* ====================================================
          SAVE
      ==================================================== */}

      <div className="flex justify-end">
        <button
          type="button"
          onClick={savePreferences}
          className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-6 py-3 text-sm font-extrabold text-white shadow-sm transition hover:bg-emerald-700"
        >
          <Save size={17} />
          Save Preferences
        </button>
      </div>
    </div>
  );
}

// ==========================================================
// Info Field
// ==========================================================

function InfoField({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-center gap-2 text-slate-400">
        {icon}

        <span className="text-xs font-bold uppercase tracking-widest">
          {label}
        </span>
      </div>

      <p className="mt-2 break-words text-sm font-extrabold text-slate-800">
        {value}
      </p>
    </div>
  );
}

// ==========================================================
// Settings Section
// ==========================================================

function SettingsSection({
  title,
  description,
  icon,
  expanded,
  onToggle,
  children,
}: {
  title: string;
  description: string;
  icon: React.ReactNode;
  expanded: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-4 p-6 text-left transition hover:bg-slate-50"
        aria-expanded={expanded}
      >
        <div className="flex min-w-0 items-start gap-4">
          <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600">
            {icon}
          </div>

          <div className="min-w-0">
            <h2 className="text-lg font-extrabold text-slate-900">{title}</h2>

            <p className="mt-1 text-sm text-slate-500">{description}</p>
          </div>
        </div>

        <ChevronDown
          size={20}
          className={`shrink-0 text-slate-400 transition-transform ${
            expanded ? "rotate-180" : ""
          }`}
        />
      </button>

      {expanded && (
        <div className="border-t border-slate-100 p-6">{children}</div>
      )}
    </section>
  );
}

// ==========================================================
// Preference Row
// ==========================================================

function PreferenceRow({
  title,
  description,
  enabled,
  onToggle,
}: {
  title: string;
  description: string;
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-5 border-b border-slate-100 py-5 last:border-b-0 last:pb-0 first:pt-0">
      <div className="min-w-0">
        <h3 className="font-extrabold text-slate-800">{title}</h3>

        <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
          {description}
        </p>
      </div>

      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        onClick={onToggle}
        className={`relative mt-1 h-6 w-11 shrink-0 rounded-full transition ${
          enabled ? "bg-emerald-600" : "bg-slate-300"
        }`}
      >
        <span
          className={`absolute top-1 h-4 w-4 rounded-full bg-white shadow-sm transition ${
            enabled ? "left-6" : "left-1"
          }`}
        />
      </button>
    </div>
  );
}

// ==========================================================
// Preference Info
// ==========================================================

function PreferenceInfo({
  icon,
  title,
  description,
}: {
  icon: React.ReactNode;
  title: string;
  description: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-4">
      <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-600">
        {icon}
      </div>

      <div>
        <h3 className="text-sm font-extrabold text-slate-800">{title}</h3>

        <p className="mt-1 text-xs leading-5 text-slate-500">{description}</p>
      </div>
    </div>
  );
}
