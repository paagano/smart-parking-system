import { useEffect, useState } from "react";
import type React from "react";

import {
  ArrowRight,
  CalendarDays,
  CheckCircle2,
  Mail,
  Phone,
  ShieldCheck,
  User,
  UserRound,
} from "lucide-react";

import { Link } from "react-router";
import { usersApi } from "../../../api";

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
  const [user, setUser] = useState<Awaited<
    ReturnType<typeof usersApi.me>
  > | null>(null);

  const [loading, setLoading] = useState(true);

  const [error, setError] = useState<string | null>(null);

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
  }, []);

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
        <div className="flex items-center gap-3">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
            <UserRound size={24} />
          </div>

          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              Profile
            </h1>

            <p className="mt-1 text-sm text-slate-500">
              View your SmartPark account information and membership details.
            </p>
          </div>
        </div>
      </div>

      {/* ====================================================
          PROFILE OVERVIEW
      ==================================================== */}

      <section className="grid gap-6 lg:grid-cols-3">
        {/* ==================================================
            PROFILE CARD
        ================================================== */}

        <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <div className="flex flex-col items-center text-center">
            <div className="grid h-28 w-28 place-items-center rounded-full bg-slate-900 text-2xl font-extrabold text-white ring-8 ring-slate-100">
              {initials || "U"}
            </div>

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
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-500">Verification</span>

              <span
                className={`text-sm font-extrabold ${
                  user?.is_verified ? "text-emerald-600" : "text-amber-600"
                }`}
              >
                {user?.is_verified ? "Verified" : "Not verified"}
              </span>
            </div>

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
              SmartPark account. Editing personal details can be enabled here
              once the corresponding backend update endpoint is available.
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
