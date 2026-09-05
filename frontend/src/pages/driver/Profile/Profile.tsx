import { useEffect, useRef, useState } from "react";
import type React from "react";

import {
  ArrowRight,
  CalendarDays,
  Camera,
  CheckCircle2,
  Mail,
  Phone,
  Save,
  ShieldCheck,
  Trash2,
  User,
  UserRound,
  X,
} from "lucide-react";

import { Link } from "react-router";
import { api, usersApi } from "../../../api";
import { useAuth } from "../../../auth/AuthContext";

// ==========================================================
// Helpers
// ==========================================================

function formatDate(value?: string | null): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-KE", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(date);
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
// Profile
// ==========================================================

export default function Profile() {
  const { updateUser } = useAuth();

  const [user, setUser] = useState<Awaited<
    ReturnType<typeof usersApi.me>
  > | null>(null);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);

  const [saving, setSaving] = useState(false);

  const [saveError, setSaveError] = useState<string | null>(null);

  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

  const [profilePictureSaving, setProfilePictureSaving] = useState(false);

  const [profilePictureError, setProfilePictureError] = useState<string | null>(
    null,
  );

  // ========================================================
  // Email Verification
  // ========================================================

  const [verificationSending, setVerificationSending] = useState(false);

  const [verificationError, setVerificationError] = useState<string | null>(
    null,
  );

  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    phone_number: "",
  });

  // ========================================================
  // Load authenticated user
  // ========================================================

  useEffect(() => {
    let mounted = true;

    async function loadProfile() {
      try {
        setLoading(true);
        setError(null);

        const currentUser = await usersApi.me();

        if (mounted) {
          setUser(currentUser);
          updateUser(currentUser);
        }
      } catch (err: any) {
        console.error("[SmartPark Profile] Failed to load current user:", err);

        if (mounted) {
          setError(
            err?.response?.data?.detail ??
              err?.message ??
              "Unable to load your profile information.",
          );
        }
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    void loadProfile();

    return () => {
      mounted = false;
    };
  }, [updateUser]);

  // ========================================================
  // Begin Editing
  // ========================================================

  function startEditing() {
    if (!user) {
      return;
    }

    setForm({
      first_name: user.first_name ?? "",
      last_name: user.last_name ?? "",
      phone_number: String(user.phone_number ?? ""),
    });

    setSaveError(null);
    setSaveSuccess(null);
    setProfilePictureError(null);
    setVerificationError(null);
    setEditing(true);
  }

  // ========================================================
  // Cancel Editing
  // ========================================================

  function cancelEditing() {
    if (saving || profilePictureSaving || verificationSending) {
      return;
    }

    setEditing(false);
    setSaveError(null);
    setSaveSuccess(null);
    setProfilePictureError(null);
    setVerificationError(null);

    if (user) {
      setForm({
        first_name: user.first_name ?? "",
        last_name: user.last_name ?? "",
        phone_number: String(user.phone_number ?? ""),
      });
    }
  }

  // ========================================================
  // Save Profile
  // ========================================================

  async function saveProfile() {
    if (!user || saving || profilePictureSaving || verificationSending) {
      return;
    }

    const firstName = form.first_name.trim();
    const lastName = form.last_name.trim();
    const phoneNumber = form.phone_number.trim();

    if (!firstName) {
      setSaveError("First name cannot be blank.");
      return;
    }

    if (!lastName) {
      setSaveError("Last name cannot be blank.");
      return;
    }

    if (!phoneNumber) {
      setSaveError("Phone number cannot be blank.");
      return;
    }

    try {
      setSaving(true);
      setSaveError(null);
      setSaveSuccess(null);

      const response = await api.patch("/users/me", {
        first_name: firstName,
        last_name: lastName,
        phone_number: phoneNumber,
      });

      const updatedUser = response.data;

      setUser(updatedUser);
      updateUser(updatedUser);

      setForm({
        first_name: updatedUser.first_name ?? "",
        last_name: updatedUser.last_name ?? "",
        phone_number: String(updatedUser.phone_number ?? ""),
      });

      setEditing(false);
      setSaveSuccess("Your profile has been updated successfully.");
    } catch (err: any) {
      console.error("[SmartPark Profile] Failed to update profile:", err);

      const detail = err?.response?.data?.detail;

      let message = "Unable to update your profile.";

      if (Array.isArray(detail)) {
        message = detail
          .map((item: any) => item?.msg)
          .filter(Boolean)
          .join(" ");
      } else if (typeof detail === "string") {
        message = detail;
      } else if (err?.message) {
        message = err.message;
      }

      setSaveError(message);
    } finally {
      setSaving(false);
    }
  }

  // ========================================================
  // Resend Email Verification
  // ========================================================

  async function handleResendVerification() {
    if (!user || user.is_verified || verificationSending) {
      return;
    }

    try {
      setVerificationSending(true);
      setVerificationError(null);
      setSaveSuccess(null);

      const response = await api.post<{ message: string }>(
        "/auth/resend-verification",
      );

      const message = response.data.message;

      setSaveSuccess(
        message ||
          "A new verification email has been sent to your email address.",
      );
    } catch (err: any) {
      console.error(
        "[SmartPark Profile] Failed to resend email verification:",
        err,
      );

      const detail = err?.response?.data?.detail;

      let message = "Unable to send the verification email.";

      if (Array.isArray(detail)) {
        message = detail
          .map((item: any) => item?.msg)
          .filter(Boolean)
          .join(" ");
      } else if (typeof detail === "string") {
        message = detail;
      } else if (err?.message) {
        message = err.message;
      }

      setVerificationError(message);
    } finally {
      setVerificationSending(false);
    }
  }

  // ========================================================
  // Open Profile Picture Picker
  // ========================================================

  function openProfilePicturePicker() {
    if (saving || profilePictureSaving || verificationSending) {
      return;
    }

    setProfilePictureError(null);
    fileInputRef.current?.click();
  }

  // ========================================================
  // Profile Picture Change
  // ========================================================

  async function handleProfilePictureChange(
    event: React.ChangeEvent<HTMLInputElement>,
  ) {
    const file = event.target.files?.[0];

    // Allow selecting the same file again later.
    event.target.value = "";

    if (!file) {
      return;
    }

    setProfilePictureError(null);

    // --------------------------------------------------------
    // Client-side validation
    // --------------------------------------------------------

    const allowedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);

    if (!allowedTypes.has(file.type)) {
      setProfilePictureError("Please select a JPEG, PNG, or WEBP image.");
      return;
    }

    const maxFileSize = 5 * 1024 * 1024;

    if (file.size > maxFileSize) {
      setProfilePictureError("Profile picture must not be larger than 5 MB.");
      return;
    }

    try {
      setProfilePictureSaving(true);

      const updatedUser = await usersApi.uploadProfilePicture(file);

      setUser(updatedUser);
      updateUser(updatedUser);

      setSaveSuccess("Your profile picture has been updated successfully.");
    } catch (err: any) {
      console.error(
        "[SmartPark Profile] Failed to upload profile picture:",
        err,
      );

      const detail = err?.response?.data?.detail;

      let message = "Unable to update your profile picture.";

      if (Array.isArray(detail)) {
        message = detail
          .map((item: any) => item?.msg)
          .filter(Boolean)
          .join(" ");
      } else if (typeof detail === "string") {
        message = detail;
      } else if (err?.message) {
        message = err.message;
      }

      setProfilePictureError(message);
    } finally {
      setProfilePictureSaving(false);
    }
  }

  // ========================================================
  // Remove Profile Picture
  // ========================================================

  async function handleRemoveProfilePicture() {
    if (
      !user?.profile_picture_url ||
      saving ||
      profilePictureSaving ||
      verificationSending
    ) {
      return;
    }

    try {
      setProfilePictureSaving(true);
      setProfilePictureError(null);

      const updatedUser = await usersApi.deleteProfilePicture();

      setUser(updatedUser);
      updateUser(updatedUser);

      setSaveSuccess("Your profile picture has been removed.");
    } catch (err: any) {
      console.error(
        "[SmartPark Profile] Failed to remove profile picture:",
        err,
      );

      const detail = err?.response?.data?.detail;

      let message = "Unable to remove your profile picture.";

      if (Array.isArray(detail)) {
        message = detail
          .map((item: any) => item?.msg)
          .filter(Boolean)
          .join(" ");
      } else if (typeof detail === "string") {
        message = detail;
      } else if (err?.message) {
        message = err.message;
      }

      setProfilePictureError(message);
    } finally {
      setProfilePictureSaving(false);
    }
  }

  // ========================================================
  // Form Change
  // ========================================================

  function handleFormChange(
    field: "first_name" | "last_name" | "phone_number",
    value: string,
  ) {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));

    if (saveError) {
      setSaveError(null);
    }

    if (saveSuccess) {
      setSaveSuccess(null);
    }
  }

  // ========================================================
  // Loading
  // ========================================================

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <div className="h-8 w-40 animate-pulse rounded bg-slate-200" />
          <div className="mt-2 h-4 w-80 animate-pulse rounded bg-slate-200" />
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="h-80 animate-pulse rounded-2xl border border-slate-200 bg-white" />
          <div className="h-80 animate-pulse rounded-2xl border border-slate-200 bg-white lg:col-span-2" />
        </div>
      </div>
    );
  }

  // ========================================================
  // Error
  // ========================================================

  if (error && !user) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
            Profile
          </h1>

          <p className="mt-1 text-sm text-slate-500">
            View your SmartPark account information.
          </p>
        </div>

        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5 text-sm text-rose-700">
          <p className="font-extrabold">Unable to load your profile</p>

          <p className="mt-1">{error}</p>
        </div>
      </div>
    );
  }

  const firstName = user?.first_name ?? "User";
  const lastName = user?.last_name ?? "";
  const fullName = `${firstName} ${lastName}`.trim();

  const initials = `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();

  return (
    <div className="space-y-6">
      {/* ====================================================
          HEADER
      ==================================================== */}

      <div>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
              <UserRound size={24} />
            </div>

            <div>
              <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
                My Profile
              </h1>

              <p className="mt-1 text-sm text-slate-500">
                View your SmartPark account information and membership details.
              </p>
            </div>
          </div>

          {!editing && (
            <button
              type="button"
              onClick={startEditing}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-extrabold text-white shadow-sm transition hover:bg-emerald-700"
            >
              <User size={16} />
              Edit Profile
            </button>
          )}
        </div>
      </div>

      {/* ====================================================
          SUCCESS MESSAGE
      ==================================================== */}

      {saveSuccess && (
        <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-700">
          <div className="flex items-center gap-2">
            <CheckCircle2 size={18} />
            <p className="font-bold">{saveSuccess}</p>
          </div>
        </div>
      )}

      {/* ====================================================
          SAVE ERROR
      ==================================================== */}

      {saveError && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <div className="flex items-start gap-2">
            <X size={18} className="mt-0.5 shrink-0" />

            <div>
              <p className="font-extrabold">Unable to update your profile</p>

              <p className="mt-1">{saveError}</p>
            </div>
          </div>
        </div>
      )}

      {/* ====================================================
          PROFILE OVERVIEW
      ==================================================== */}

      <section className="grid gap-6 lg:grid-cols-3">
        {/* ==================================================
            PROFILE CARD
        ================================================== */}

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col items-center text-center">
            {/* ==================================================
                PROFILE PICTURE
            ================================================== */}

            <div className="relative">
              {user?.profile_picture_url ? (
                <img
                  src={user.profile_picture_url}
                  alt={`${fullName}'s profile`}
                  className="h-28 w-28 rounded-full object-cover ring-8 ring-slate-100"
                />
              ) : (
                <div className="grid h-28 w-28 place-items-center rounded-full bg-slate-900 text-2xl font-extrabold text-white ring-8 ring-slate-100">
                  {initials || "U"}
                </div>
              )}

              {profilePictureSaving && (
                <div className="absolute inset-0 grid place-items-center rounded-full bg-slate-900/60">
                  <span className="h-7 w-7 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                </div>
              )}
            </div>

            {/* ==================================================
                PROFILE PICTURE CONTROLS
            ================================================== */}

            {editing && (
              <div className="mt-5 w-full">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(event) => void handleProfilePictureChange(event)}
                  className="hidden"
                />

                <div className="flex flex-col gap-2 sm:flex-row sm:justify-center">
                  <button
                    type="button"
                    onClick={openProfilePicturePicker}
                    disabled={
                      saving || profilePictureSaving || verificationSending
                    }
                    className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <Camera size={16} />
                    {profilePictureSaving
                      ? "Updating..."
                      : user?.profile_picture_url
                        ? "Change Photo"
                        : "Add Photo"}
                  </button>

                  {user?.profile_picture_url && (
                    <button
                      type="button"
                      onClick={() => void handleRemoveProfilePicture()}
                      disabled={
                        saving || profilePictureSaving || verificationSending
                      }
                      className="inline-flex items-center justify-center gap-2 rounded-xl border border-rose-200 bg-white px-4 py-2.5 text-sm font-extrabold text-rose-600 transition hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      <Trash2 size={16} />
                      Remove Photo
                    </button>
                  )}
                </div>

                <p className="mt-2 text-center text-xs text-slate-400">
                  JPEG, PNG or WEBP · Maximum 5 MB
                </p>

                {profilePictureError && (
                  <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-left text-xs font-semibold text-rose-700">
                    {profilePictureError}
                  </div>
                )}
              </div>
            )}

            <h2 className="mt-5 text-xl font-extrabold text-slate-900">
              {fullName}
            </h2>

            <p className="mt-1 text-sm text-slate-500">{user?.email ?? "—"}</p>

            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700">
                <ShieldCheck size={14} />
                {formatRole(user?.role)}
              </span>

              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-bold ${
                  user?.is_active
                    ? "bg-blue-50 text-blue-700"
                    : "bg-rose-50 text-rose-700"
                }`}
              >
                <CheckCircle2 size={14} />
                {user?.is_active ? "Active" : "Inactive"}
              </span>
            </div>
          </div>

          <div className="mt-7 border-t border-slate-100 pt-5">
            <div className="flex items-center justify-between gap-4">
              <span className="text-sm text-slate-500">Verification</span>

              <span
                className={`text-sm font-extrabold ${
                  user?.is_verified ? "text-emerald-600" : "text-amber-600"
                }`}
              >
                {user?.is_verified ? "Verified" : "Not verified"}
              </span>
            </div>

            {!user?.is_verified && (
              <div className="mt-4">
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
                  <div className="flex items-start gap-3">
                    <Mail
                      size={18}
                      className="mt-0.5 shrink-0 text-amber-600"
                    />

                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-extrabold text-amber-900">
                        Verify your email address
                      </p>

                      <p className="mt-1 text-xs leading-5 text-amber-800">
                        We will send a secure verification link to{" "}
                        <span className="font-bold">
                          {user?.email ?? "your email address"}
                        </span>
                        .
                      </p>

                      <button
                        type="button"
                        onClick={() => void handleResendVerification()}
                        disabled={verificationSending}
                        className="mt-3 inline-flex items-center justify-center gap-2 rounded-lg bg-amber-600 px-3 py-2 text-xs font-extrabold text-white transition hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        <Mail size={14} />
                        {verificationSending
                          ? "Sending..."
                          : "Resend Verification Email"}
                      </button>
                    </div>
                  </div>
                </div>

                {verificationError && (
                  <div className="mt-3 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs font-semibold text-rose-700">
                    {verificationError}
                  </div>
                )}
              </div>
            )}

            <div className="mt-3 flex items-center justify-between">
              <span className="text-sm text-slate-500">Member since</span>

              <span className="text-sm font-extrabold text-slate-800">
                {formatDate(user?.created_at)}
              </span>
            </div>
          </div>
        </div>

        {/* ==================================================
            PERSONAL INFORMATION
        ================================================== */}

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm lg:col-span-2">
          <div>
            <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">
              Personal Information
            </p>

            <h2 className="mt-1 text-lg font-extrabold text-slate-900">
              Account details
            </h2>

            <p className="mt-1 text-sm text-slate-500">
              Information associated with your authenticated SmartPark account.
            </p>
          </div>

          {editing ? (
            <>
              {/* ==================================================
                  EDIT FORM
              ================================================== */}

              <div className="mt-6 grid gap-4 md:grid-cols-2">
                {/* First Name */}

                <div>
                  <label
                    htmlFor="profile-first-name"
                    className="mb-2 block text-xs font-bold uppercase tracking-widest text-slate-500"
                  >
                    First name
                  </label>

                  <div className="relative">
                    <User
                      size={18}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                    />

                    <input
                      id="profile-first-name"
                      type="text"
                      value={form.first_name}
                      onChange={(event) =>
                        handleFormChange("first_name", event.target.value)
                      }
                      disabled={saving || profilePictureSaving}
                      maxLength={100}
                      className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-10 pr-4 text-sm font-semibold text-slate-800 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:cursor-not-allowed disabled:bg-slate-50"
                    />
                  </div>
                </div>

                {/* Last Name */}

                <div>
                  <label
                    htmlFor="profile-last-name"
                    className="mb-2 block text-xs font-bold uppercase tracking-widest text-slate-500"
                  >
                    Last name
                  </label>

                  <div className="relative">
                    <User
                      size={18}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                    />

                    <input
                      id="profile-last-name"
                      type="text"
                      value={form.last_name}
                      onChange={(event) =>
                        handleFormChange("last_name", event.target.value)
                      }
                      disabled={saving || profilePictureSaving}
                      maxLength={100}
                      className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-10 pr-4 text-sm font-semibold text-slate-800 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:cursor-not-allowed disabled:bg-slate-50"
                    />
                  </div>
                </div>

                {/* Email */}

                <div>
                  <label
                    htmlFor="profile-email"
                    className="mb-2 block text-xs font-bold uppercase tracking-widest text-slate-500"
                  >
                    Email address
                  </label>

                  <div className="relative">
                    <Mail
                      size={18}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                    />

                    <input
                      id="profile-email"
                      type="email"
                      value={user?.email ?? ""}
                      disabled
                      className="w-full cursor-not-allowed rounded-xl border border-slate-200 bg-slate-50 py-3 pl-10 pr-4 text-sm font-semibold text-slate-500"
                    />
                  </div>

                  <p className="mt-1.5 text-xs text-slate-400">
                    Email address cannot be changed here.
                  </p>
                </div>

                {/* Phone Number */}

                <div>
                  <label
                    htmlFor="profile-phone"
                    className="mb-2 block text-xs font-bold uppercase tracking-widest text-slate-500"
                  >
                    Phone number
                  </label>

                  <div className="relative">
                    <Phone
                      size={18}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                    />

                    <input
                      id="profile-phone"
                      type="tel"
                      value={form.phone_number}
                      onChange={(event) =>
                        handleFormChange("phone_number", event.target.value)
                      }
                      disabled={saving || profilePictureSaving}
                      maxLength={20}
                      className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-10 pr-4 text-sm font-semibold text-slate-800 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:cursor-not-allowed disabled:bg-slate-50"
                    />
                  </div>
                </div>
              </div>

              {/* ==================================================
                  FORM ACTIONS
              ================================================== */}

              <div className="mt-6 flex flex-col-reverse gap-3 border-t border-slate-100 pt-5 sm:flex-row sm:justify-end">
                <button
                  type="button"
                  onClick={cancelEditing}
                  disabled={saving || profilePictureSaving}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-2.5 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <X size={16} />
                  Cancel
                </button>

                <button
                  type="button"
                  onClick={() => void saveProfile()}
                  disabled={saving || profilePictureSaving}
                  className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-extrabold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Save size={16} />

                  {saving ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </>
          ) : (
            <>
              {/* ==================================================
                  READ-ONLY PROFILE FIELDS
              ================================================== */}

              <div className="mt-6 grid gap-4 md:grid-cols-2">
                <ProfileField
                  icon={<User size={18} />}
                  label="First name"
                  value={user?.first_name ?? "—"}
                />

                <ProfileField
                  icon={<User size={18} />}
                  label="Last name"
                  value={user?.last_name ?? "—"}
                />

                <ProfileField
                  icon={<Mail size={18} />}
                  label="Email address"
                  value={user?.email ?? "—"}
                />

                <ProfileField
                  icon={<Phone size={18} />}
                  label="Phone number"
                  value={String(user?.phone_number ?? "—")}
                />
              </div>
            </>
          )}

          <div className="mt-5 rounded-xl border border-slate-100 bg-slate-50 p-4">
            <div className="flex items-start gap-3">
              <CalendarDays
                size={18}
                className="mt-0.5 shrink-0 text-slate-400"
              />

              <div>
                <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
                  Account created
                </p>

                <p className="mt-1 text-sm font-bold text-slate-700">
                  {formatDate(user?.created_at)}
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ====================================================
          ACCOUNT STATUS
      ==================================================== */}

      <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-4">
            <div className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
              <ShieldCheck size={21} />
            </div>

            <div>
              <h2 className="text-lg font-extrabold text-slate-900">
                Account & Security
              </h2>

              <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-500">
                Manage your notification, display and account-security
                preferences from Settings.
              </p>
            </div>
          </div>

          <Link
            to="/settings"
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50"
          >
            Open Settings
            <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      {/* ====================================================
          PROFILE NOTICE
      ==================================================== */}

      <div className="rounded-2xl border border-blue-100 bg-blue-50 p-5">
        <div className="flex items-start gap-3">
          <User size={19} className="mt-0.5 shrink-0 text-blue-600" />

          <div>
            <p className="font-extrabold text-blue-900">Profile information</p>

            <p className="mt-1 text-sm leading-6 text-blue-800">
              Your profile information is retrieved from the authenticated
              SmartPark account. You can update your name and phone number using
              the Edit Profile option above.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

// ==========================================================
// Profile Field
// ==========================================================

function ProfileField({
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
