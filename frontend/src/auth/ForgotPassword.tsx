import { FormEvent, useState } from "react";

import { Link } from "react-router";

import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  LockKeyhole,
  Mail,
} from "lucide-react";

import { api, getApiErrorMessage } from "../api";

export default function ForgotPassword() {
  const [email, setEmail] = useState("");

  const [loading, setLoading] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [success, setSuccess] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError(null);
    setSuccess(null);

    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      setError("Please enter your email address.");
      return;
    }

    setLoading(true);

    try {
      const response = await api.post<{ message: string }>(
        "/auth/forgot-password",
        {
          email: trimmedEmail,
        },
      );

      setSuccess(
        response.data.message ||
          "If an account exists for that email address, a password reset link has been sent.",
      );

      setEmail("");
    } catch (err) {
      console.error("[SmartPark Forgot Password] Request failed:", err);

      setError(getApiErrorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950">
      <div className="grid min-h-screen lg:grid-cols-2">
        {/* ==================================================
            BRAND PANEL
        ================================================== */}

        <div className="hidden lg:flex bg-[#071a2d] p-12 text-white">
          <div className="m-auto max-w-md">
            <div className="flex items-center gap-3">
              <div className="grid h-12 w-12 place-items-center rounded-2xl bg-emerald-500">
                <LockKeyhole size={24} />
              </div>

              <div>
                <div className="text-2xl font-black">
                  SmartPark <span className="text-emerald-400">AI</span>
                </div>

                <div className="text-xs font-bold uppercase tracking-widest text-slate-400">
                  Smart parking. Smarter journeys.
                </div>
              </div>
            </div>

            <h1 className="mt-12 text-4xl font-black leading-tight">
              Recover your account securely.
            </h1>

            <p className="mt-5 text-lg leading-8 text-slate-300">
              Enter your registered email address and we will send you a secure
              link to create a new password.
            </p>

            <div className="mt-10 space-y-4">
              <div className="flex items-center gap-3 text-sm text-slate-300">
                <CheckCircle2 size={18} className="text-emerald-400" />
                Secure password-reset link
              </div>

              <div className="flex items-center gap-3 text-sm text-slate-300">
                <CheckCircle2 size={18} className="text-emerald-400" />
                Link expires after one hour
              </div>

              <div className="flex items-center gap-3 text-sm text-slate-300">
                <CheckCircle2 size={18} className="text-emerald-400" />
                Existing sessions are invalidated
              </div>
            </div>
          </div>
        </div>

        {/* ==================================================
            FORM
        ================================================== */}

        <div className="flex items-center justify-center bg-slate-50 px-5 py-10">
          <div className="w-full max-w-md">
            <div className="mb-8 lg:hidden">
              <div className="flex items-center gap-3">
                <div className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-600 text-white">
                  <LockKeyhole size={21} />
                </div>

                <div className="text-xl font-black text-slate-900">
                  SmartPark <span className="text-emerald-600">AI</span>
                </div>
              </div>
            </div>

            <div className="rounded-3xl border border-slate-200 bg-white p-7 shadow-xl sm:p-9">
              {!success ? (
                <>
                  <div className="mb-8">
                    <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl bg-emerald-50 text-emerald-700">
                      <Mail size={25} />
                    </div>

                    <h2 className="text-3xl font-black text-slate-900">
                      Forgot password?
                    </h2>

                    <p className="mt-2 text-sm leading-6 text-slate-500">
                      Enter your email address and we will send you a secure
                      password-reset link.
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
                        htmlFor="email"
                        className="mb-2 block text-sm font-bold text-slate-700"
                      >
                        Email address
                      </label>

                      <div className="relative">
                        <Mail
                          size={18}
                          className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                        />

                        <input
                          id="email"
                          type="email"
                          value={email}
                          onChange={(event) => setEmail(event.target.value)}
                          placeholder="you@example.com"
                          autoComplete="email"
                          disabled={loading}
                          className="w-full rounded-xl border border-slate-200 bg-white py-3.5 pl-11 pr-4 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-4 focus:ring-emerald-500/10 disabled:bg-slate-100"
                        />
                      </div>
                    </div>

                    <button
                      type="submit"
                      disabled={loading}
                      className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3.5 text-sm font-black text-white transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {loading ? "Sending..." : "Send Reset Link"}

                      {!loading && <ArrowRight size={17} />}
                    </button>
                  </form>
                </>
              ) : (
                <div className="text-center">
                  <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-emerald-50 text-emerald-600">
                    <CheckCircle2 size={31} />
                  </div>

                  <h2 className="mt-6 text-2xl font-black text-slate-900">
                    Check your email
                  </h2>

                  <p className="mt-3 text-sm leading-6 text-slate-500">
                    {success}
                  </p>

                  <p className="mt-4 text-xs leading-5 text-slate-400">
                    If you do not see the message shortly, check your spam or
                    junk folder.
                  </p>

                  <Link
                    to="/login"
                    className="mt-7 inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-black text-slate-700 transition hover:border-emerald-300 hover:text-emerald-700"
                  >
                    <ArrowLeft size={16} />
                    Back to Login
                  </Link>
                </div>
              )}
            </div>

            {!success && (
              <div className="mt-6 text-center">
                <Link
                  to="/login"
                  className="inline-flex items-center gap-2 text-sm font-bold text-slate-500 transition hover:text-emerald-700"
                >
                  <ArrowLeft size={16} />
                  Back to Login
                </Link>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
