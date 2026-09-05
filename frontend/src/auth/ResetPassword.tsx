import { FormEvent, useMemo, useState } from "react";

import { Link, useNavigate, useSearchParams } from "react-router";

import {
  ArrowLeft,
  CheckCircle2,
  Eye,
  EyeOff,
  LockKeyhole,
  XCircle,
} from "lucide-react";

import { api, getApiErrorMessage } from "../api";

function PasswordRequirement({ met, label }: { met: boolean; label: string }) {
  return (
    <div
      className={`flex items-center gap-2 ${
        met ? "text-emerald-700" : "text-slate-400"
      }`}
    >
      {met ? <CheckCircle2 size={14} /> : <XCircle size={14} />}

      <span>{label}</span>
    </div>
  );
}

export default function ResetPassword() {
  const navigate = useNavigate();

  const [searchParams] = useSearchParams();

  const token = searchParams.get("token") ?? "";

  const [newPassword, setNewPassword] = useState("");

  const [confirmPassword, setConfirmPassword] = useState("");

  const [showPassword, setShowPassword] = useState(false);

  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [loading, setLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [success, setSuccess] = useState(false);

  const requirements = useMemo(
    () => ({
      length: newPassword.length >= 8,
      uppercase: /[A-Z]/.test(newPassword),
      lowercase: /[a-z]/.test(newPassword),
      number: /[0-9]/.test(newPassword),
      special: /[^A-Za-z0-9]/.test(newPassword),
      matching:
        Boolean(newPassword) &&
        Boolean(confirmPassword) &&
        newPassword === confirmPassword,
    }),
    [newPassword, confirmPassword],
  );

  const passwordValid =
    requirements.length &&
    requirements.uppercase &&
    requirements.lowercase &&
    requirements.number &&
    requirements.special &&
    requirements.matching;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError(null);

    if (!token) {
      setError("This password reset link is invalid or incomplete.");
      return;
    }

    if (!requirements.length) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    if (!requirements.uppercase) {
      setError("Password must contain at least one uppercase letter.");
      return;
    }

    if (!requirements.lowercase) {
      setError("Password must contain at least one lowercase letter.");
      return;
    }

    if (!requirements.number) {
      setError("Password must contain at least one number.");
      return;
    }

    if (!requirements.special) {
      setError("Password must contain at least one special character.");
      return;
    }

    if (!requirements.matching) {
      setError("The passwords do not match.");
      return;
    }

    setLoading(true);

    try {
      await api.post("/auth/reset-password", {
        token,
        new_password: newPassword,
        confirm_password: confirmPassword,
      });

      setSuccess(true);

      setNewPassword("");
      setConfirmPassword("");

      window.setTimeout(() => {
        navigate("/login", {
          replace: true,
        });
      }, 1800);
    } catch (err) {
      console.error("[SmartPark Reset Password] Reset failed:", err);

      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  if (success) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 px-5 py-10">
        <div className="w-full max-w-md rounded-3xl border border-slate-200 bg-white p-8 text-center shadow-2xl">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-emerald-50 text-emerald-600">
            <CheckCircle2 size={32} />
          </div>

          <h1 className="mt-6 text-2xl font-black text-slate-900">
            Password reset successful
          </h1>

          <p className="mt-3 text-sm leading-6 text-slate-500">
            Your password has been changed successfully. You will be redirected
            to the login page.
          </p>

          <Link
            to="/login"
            className="mt-7 inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-black text-white"
          >
            <ArrowLeft size={16} />
            Continue to Login
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950">
      <div className="flex min-h-screen items-center justify-center bg-slate-50 px-5 py-10">
        <div className="w-full max-w-md">
          <div className="mb-7 flex items-center justify-center gap-3">
            <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-600 text-white">
              <LockKeyhole size={23} />
            </div>

            <div className="text-2xl font-black text-slate-900">
              SmartPark <span className="text-emerald-600">AI</span>
            </div>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-7 shadow-xl sm:p-9">
            <div className="mb-7 text-center">
              <h1 className="text-3xl font-black text-slate-900">
                Create a new password
              </h1>

              <p className="mt-2 text-sm leading-6 text-slate-500">
                Choose a strong password for your SmartPark AI account.
              </p>
            </div>

            {error && (
              <div className="mb-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-700">
                {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label
                  htmlFor="new-password"
                  className="mb-2 block text-sm font-bold text-slate-700"
                >
                  New password
                </label>

                <div className="relative">
                  <LockKeyhole
                    size={18}
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                  />

                  <input
                    id="new-password"
                    type={showPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={(event) => setNewPassword(event.target.value)}
                    autoComplete="new-password"
                    disabled={loading}
                    className="w-full rounded-xl border border-slate-200 py-3.5 pl-11 pr-11 text-sm outline-none focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10 disabled:bg-slate-100"
                  />

                  <button
                    type="button"
                    onClick={() => setShowPassword((current) => !current)}
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
                    aria-label={
                      showPassword ? "Hide password" : "Show password"
                    }
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              <div>
                <label
                  htmlFor="confirm-password"
                  className="mb-2 block text-sm font-bold text-slate-700"
                >
                  Confirm new password
                </label>

                <div className="relative">
                  <LockKeyhole
                    size={18}
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                  />

                  <input
                    id="confirm-password"
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    autoComplete="new-password"
                    disabled={loading}
                    className="w-full rounded-xl border border-slate-200 py-3.5 pl-11 pr-11 text-sm outline-none focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10 disabled:bg-slate-100"
                  />

                  <button
                    type="button"
                    onClick={() =>
                      setShowConfirmPassword((current) => !current)
                    }
                    className="absolute right-3.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700"
                    aria-label={
                      showConfirmPassword ? "Hide password" : "Show password"
                    }
                  >
                    {showConfirmPassword ? (
                      <EyeOff size={18} />
                    ) : (
                      <Eye size={18} />
                    )}
                  </button>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <p className="text-xs font-black uppercase tracking-widest text-slate-500">
                  Password requirements
                </p>

                <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
                  <PasswordRequirement
                    met={requirements.length}
                    label="At least 8 characters"
                  />

                  <PasswordRequirement
                    met={requirements.uppercase}
                    label="One uppercase letter"
                  />

                  <PasswordRequirement
                    met={requirements.lowercase}
                    label="One lowercase letter"
                  />

                  <PasswordRequirement
                    met={requirements.number}
                    label="One number"
                  />

                  <PasswordRequirement
                    met={requirements.special}
                    label="One special character"
                  />

                  <PasswordRequirement
                    met={requirements.matching}
                    label="Passwords match"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading || !token}
                className="w-full rounded-xl bg-emerald-600 px-5 py-3.5 text-sm font-black text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? "Resetting Password..." : "Reset Password"}
              </button>
            </form>

            <div className="mt-6 text-center">
              <Link
                to="/login"
                className="inline-flex items-center gap-2 text-sm font-bold text-slate-500 hover:text-emerald-700"
              >
                <ArrowLeft size={16} />
                Back to Login
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
