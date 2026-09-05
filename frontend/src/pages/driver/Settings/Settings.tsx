import { useState } from "react";
import type React from "react";
import {
  Bell,
  Check,
  ChevronDown,
  LockKeyhole,
  Eye,
  EyeOff,
  Loader2,
  Moon,
  Palette,
  Save,
  ShieldCheck,
  Sun,
  UserRound,
} from "lucide-react";

import { api } from "../../api";
import { useAuth } from "../../auth/AuthContext";
import { useNavigate } from "react-router";

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

// ==========================================================
// Component
// ==========================================================

export default function Settings() {
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
  // Password change
  // ========================================================

  const navigate = useNavigate();
  const { logout } = useAuth();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");

  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmNewPassword, setShowConfirmNewPassword] = useState(false);

  const [changingPassword, setChangingPassword] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState<string | null>(null);

  const [showChangePasswordForm, setShowChangePasswordForm] = useState(false);

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
  // Change password
  // ========================================================

  async function handleChangePassword() {
    setPasswordError(null);
    setPasswordSuccess(null);

    if (!currentPassword) {
      setPasswordError("Please enter your current password.");
      return;
    }

    if (!newPassword) {
      setPasswordError("Please enter a new password.");
      return;
    }

    if (newPassword.length < 8) {
      setPasswordError("New password must be at least 8 characters long.");
      return;
    }

    if (!/[A-Z]/.test(newPassword)) {
      setPasswordError(
        "New password must contain at least one uppercase letter.",
      );
      return;
    }

    if (!/[a-z]/.test(newPassword)) {
      setPasswordError(
        "New password must contain at least one lowercase letter.",
      );
      return;
    }

    if (!/[0-9]/.test(newPassword)) {
      setPasswordError("New password must contain at least one number.");
      return;
    }

    if (!/[^A-Za-z0-9]/.test(newPassword)) {
      setPasswordError(
        "New password must contain at least one special character.",
      );
      return;
    }

    if (newPassword !== confirmNewPassword) {
      setPasswordError("The new passwords do not match.");
      return;
    }

    setChangingPassword(true);

    try {
      await api.post("/users/me/change-password", {
        current_password: currentPassword,
        new_password: newPassword,
      });

      setPasswordSuccess(
        "Your password has been changed successfully. Please sign in again.",
      );

      setCurrentPassword("");
      setNewPassword("");
      setConfirmNewPassword("");
      setShowCurrentPassword(false);
      setShowNewPassword(false);
      setShowConfirmNewPassword(false);

      // The backend revokes the JWT used for the password change.
      // Clear the frontend authentication state and return to login.
      try {
        await logout();
      } catch {
        // The token has already been revoked by the backend.
        // AuthContext.logout clears the local authentication state
        // even when its follow-up logout request returns 401.
      }

      navigate("/login", { replace: true });
    } catch (err: any) {
      console.error("[SmartPark Settings] Failed to change password:", err);

      const detail = err?.response?.data?.detail;

      if (typeof detail === "string") {
        setPasswordError(detail);
      } else if (Array.isArray(detail)) {
        setPasswordError(
          detail
            .map((item: any) =>
              typeof item === "string"
                ? item
                : (item?.msg ?? "Validation error."),
            )
            .join(", "),
        );
      } else {
        setPasswordError(err?.message ?? "Unable to change your password.");
      }
    } finally {
      setChangingPassword(false);
    }
  }

  function cancelChangePassword() {
    if (changingPassword) {
      return;
    }

    setCurrentPassword("");
    setNewPassword("");
    setConfirmNewPassword("");
    setPasswordError(null);
    setPasswordSuccess(null);
    setShowCurrentPassword(false);
    setShowNewPassword(false);
    setShowConfirmNewPassword(false);
    setShowChangePasswordForm(false);
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
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-4">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white text-slate-600 shadow-sm">
                <LockKeyhole size={19} />
              </div>

              <div>
                <h3 className="font-extrabold text-slate-800">
                  Password & Authentication
                </h3>

                <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
                  Keep your SmartPark account secure by regularly updating your
                  password.
                </p>
              </div>
            </div>

            {!showChangePasswordForm && (
              <button
                type="button"
                onClick={() => {
                  setPasswordError(null);
                  setPasswordSuccess(null);
                  setShowChangePasswordForm(true);
                }}
                className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-extrabold text-white transition hover:bg-slate-800"
              >
                <LockKeyhole size={16} />
                Change Password
              </button>
            )}
          </div>

          {showChangePasswordForm && (
            <div className="mt-5 border-t border-slate-200 pt-5">
              {passwordError && (
                <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                  <p className="font-bold">Unable to change password</p>
                  <p className="mt-1">{passwordError}</p>
                </div>
              )}

              {passwordSuccess && (
                <div className="mb-4 flex items-start gap-3 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm font-semibold text-emerald-700">
                  <Check size={17} className="mt-0.5 shrink-0" />
                  <p>{passwordSuccess}</p>
                </div>
              )}

              <div className="grid gap-4 md:grid-cols-3">
                <PasswordField
                  label="Current password"
                  value={currentPassword}
                  onChange={setCurrentPassword}
                  showPassword={showCurrentPassword}
                  onToggleVisibility={() =>
                    setShowCurrentPassword((current) => !current)
                  }
                  disabled={changingPassword}
                  autoComplete="current-password"
                />

                <PasswordField
                  label="New password"
                  value={newPassword}
                  onChange={setNewPassword}
                  showPassword={showNewPassword}
                  onToggleVisibility={() =>
                    setShowNewPassword((current) => !current)
                  }
                  disabled={changingPassword}
                  autoComplete="new-password"
                />

                <PasswordField
                  label="Confirm new password"
                  value={confirmNewPassword}
                  onChange={setConfirmNewPassword}
                  showPassword={showConfirmNewPassword}
                  onToggleVisibility={() =>
                    setShowConfirmNewPassword((current) => !current)
                  }
                  disabled={changingPassword}
                  autoComplete="new-password"
                />
              </div>

              <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
                <p className="text-xs font-extrabold uppercase tracking-widest text-slate-500">
                  Password requirements
                </p>

                <div className="mt-3 grid gap-2 text-xs text-slate-500 sm:grid-cols-2">
                  <PasswordRequirement
                    met={newPassword.length >= 8}
                    label="At least 8 characters"
                  />
                  <PasswordRequirement
                    met={/[A-Z]/.test(newPassword)}
                    label="One uppercase letter"
                  />
                  <PasswordRequirement
                    met={/[a-z]/.test(newPassword)}
                    label="One lowercase letter"
                  />
                  <PasswordRequirement
                    met={/[0-9]/.test(newPassword)}
                    label="One number"
                  />
                  <PasswordRequirement
                    met={/[^A-Za-z0-9]/.test(newPassword)}
                    label="One special character"
                  />
                  <PasswordRequirement
                    met={
                      Boolean(newPassword) &&
                      Boolean(confirmNewPassword) &&
                      newPassword === confirmNewPassword
                    }
                    label="Passwords match"
                  />
                </div>
              </div>

              <div className="mt-5 flex flex-col-reverse gap-3 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={cancelChangePassword}
                  disabled={changingPassword}
                  className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  Cancel
                </button>

                <button
                  type="button"
                  onClick={() => void handleChangePassword()}
                  disabled={changingPassword}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-extrabold text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {changingPassword ? (
                    <>
                      <Loader2 size={16} className="animate-spin" />
                      Updating Password...
                    </>
                  ) : (
                    <>
                      <LockKeyhole size={16} />
                      Update Password
                    </>
                  )}
                </button>
              </div>

              <p className="mt-4 text-xs leading-5 text-slate-500">
                For security, you will be signed out after successfully changing
                your password and will need to sign in again with your new
                password.
              </p>
            </div>
          )}
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
// Password Field
// ==========================================================

function PasswordField({
  label,
  value,
  onChange,
  showPassword,
  onToggleVisibility,
  disabled,
  autoComplete,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  showPassword: boolean;
  onToggleVisibility: () => void;
  disabled: boolean;
  autoComplete: string;
}) {
  return (
    <div>
      <label className="mb-2 block text-sm font-extrabold text-slate-700">
        {label}
      </label>

      <div className="relative">
        <input
          type={showPassword ? "text" : "password"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          autoComplete={autoComplete}
          className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 pr-11 text-sm font-medium text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:cursor-not-allowed disabled:bg-slate-100"
          placeholder="Enter password"
        />

        <button
          type="button"
          onClick={onToggleVisibility}
          disabled={disabled}
          aria-label={showPassword ? "Hide password" : "Show password"}
          className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-600 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
        </button>
      </div>
    </div>
  );
}

// ==========================================================
// Password Requirement
// ==========================================================

function PasswordRequirement({ met, label }: { met: boolean; label: string }) {
  return (
    <div
      className={`flex items-center gap-2 ${met ? "text-emerald-600" : "text-slate-500"}`}
    >
      <span
        className={`grid h-4 w-4 shrink-0 place-items-center rounded-full border ${
          met
            ? "border-emerald-500 bg-emerald-500 text-white"
            : "border-slate-300 bg-white"
        }`}
      >
        {met && <Check size={10} strokeWidth={3} />}
      </span>
      <span>{label}</span>
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
