import { FormEvent, useState } from "react";

import { Link, useNavigate } from "react-router";

import {
  ArrowRight,
  CarFront,
  LockKeyhole,
  Mail,
  ParkingCircle,
} from "lucide-react";

import { useAuth } from "./AuthContext";

import { getDefaultRoute } from "./role";

export default function Login() {
  const navigate = useNavigate();

  const { login } = useAuth();

  const [email, setEmail] = useState("");

  const [password, setPassword] = useState("");

  const [isSubmitting, setIsSubmitting] = useState(false);

  const [error, setError] = useState<string | null>(null);

  // ======================================================
  // Submit
  // ======================================================

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    setError(null);

    const trimmedEmail = email.trim();

    if (!trimmedEmail) {
      setError("Please enter your email address.");

      return;
    }

    if (!password) {
      setError("Please enter your password.");

      return;
    }

    setIsSubmitting(true);

    try {
      const user = await login(trimmedEmail, password);

      /*
       *
       * The destination is determined from
       * the REAL role returned by the backend.
       *
       * DRIVER    -> /dashboard
       * ATTENDANT -> /operator
       * ADMIN     -> /admin
       */

      navigate(getDefaultRoute(user.role), {
        replace: true,
      });
    } catch (err: any) {
      /*
       * Do not expose raw Axios errors to the user.
       */

      const backendMessage = err?.response?.data?.detail;

      if (typeof backendMessage === "string") {
        setError(backendMessage);
      } else if (err?.response?.status === 401) {
        setError("Invalid email or password.");
      } else if (err?.response?.status === 403) {
        setError("Your account is not permitted to access SmartPark AI.");
      } else {
        setError(
          "Unable to sign in. Please contact your system administrator for assistance.",
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#071a2d] p-4 grid place-items-center">
      <div className="grid w-full max-w-6xl overflow-hidden rounded-[2rem] bg-white shadow-2xl lg:grid-cols-2">
        {/* ==================================================
                    BRAND PANEL
                ================================================== */}

        <div className="hidden min-h-[680px] bg-[#0a2740] p-12 text-white lg:flex lg:flex-col lg:justify-between">
          <div>
            <div className="flex items-center gap-3 font-extrabold text-xl">
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-400 text-[#071a2d]">
                <ParkingCircle />
              </span>
              SmartPark
              <span className="text-emerald-400">AI</span>
            </div>

            <div className="mt-28 max-w-lg">
              <div className="text-emerald-300 text-xs font-bold uppercase tracking-[.2em]">
                AI-powered parking intelligence
              </div>

              <h1 className="mt-4 text-5xl font-black leading-tight">
                Find a space.
                <br />
                Plan ahead.
                <br />
                <span className="text-emerald-400">Park smarter.</span>
              </h1>

              <p className="mt-6 leading-7 text-slate-300">
                Real-time availability, reservations and predictive occupancy
                intelligence for Nairobi.
              </p>
            </div>
          </div>

          {/* ==================================================
                        PLATFORM STATISTICS
              ================================================== */}

          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <b className="text-2xl">42</b>

              <div className="text-xs text-slate-400 mt-1">Facilities</div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <b className="text-2xl">2,840</b>

              <div className="text-xs text-slate-400 mt-1">Spaces</div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
              <b className="text-2xl">AI</b>

              <div className="text-xs text-slate-400 mt-1">Prediction</div>
            </div>
          </div>
        </div>

        {/* ==================================================
                    LOGIN PANEL
            ================================================== */}

        <div className="p-8 sm:p-14 grid place-items-center">
          <div className="w-full max-w-md">
            <div className="text-xs font-bold uppercase tracking-[.2em] text-emerald-600">
              SmartPark AI
            </div>

            <h2 className="mt-2 text-3xl font-black text-slate-900">
              Welcome Back!
            </h2>

            <p className="mt-3 text-sm leading-6 text-slate-500">
              Sign in to access your SmartPark AI account.
            </p>

            {/* ==================================================
                            ERROR
                ================================================== */}

            {error && (
              <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            {/* ==================================================
                            FORM
                        ================================================== */}

            <form onSubmit={handleSubmit} className="mt-8 space-y-5">
              {/* EMAIL */}

              <div>
                <label
                  htmlFor="email"
                  className="mb-2 block text-sm font-semibold text-slate-700"
                >
                  Email address
                </label>

                <div className="relative">
                  <Mail
                    size={18}
                    className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"
                  />

                  <input
                    id="email"
                    type="email"
                    autoComplete="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                    disabled={isSubmitting}
                    className="w-full rounded-2xl border border-slate-200 bg-white py-3.5 pl-11 pr-4 text-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                  />
                </div>
              </div>

              {/* PASSWORD */}

              <div>
                <div className="mb-2">
                  <label
                    htmlFor="password"
                    className="block text-sm font-semibold text-slate-700"
                  >
                    Password
                  </label>
                </div>

                <div className="relative">
                  <LockKeyhole
                    size={18}
                    className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"
                  />

                  <input
                    id="password"
                    type="password"
                    autoComplete="current-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Enter your password"
                    disabled={isSubmitting}
                    className="w-full rounded-2xl border border-slate-200 bg-white py-3.5 pl-11 pr-4 text-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                  />
                </div>

                <div className="mt-2 flex justify-end">
                  <Link
                    to="/forgot-password"
                    className="text-sm font-semibold text-emerald-600 transition hover:text-emerald-700"
                  >
                    Forgot password?
                  </Link>
                </div>
              </div>

              {/* ==================================================
                                SIGN IN BUTTON
                  ================================================== */}

              <button
                type="submit"
                disabled={isSubmitting}
                className="group flex w-full items-center justify-center gap-3 rounded-2xl bg-[#071a2d] px-5 py-3.5 font-bold text-white transition hover:bg-[#0a2740] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSubmitting ? (
                  <>
                    <span className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    Signing in...
                  </>
                ) : (
                  <>
                    Sign in
                    <ArrowRight
                      size={18}
                      className="transition-transform group-hover:translate-x-1"
                    />
                  </>
                )}
              </button>
            </form>

            {/* ==================================================
                            REGISTRATION
                ================================================== */}

            <div className="mt-6 text-center">
              <p className="text-sm text-slate-500">
                Don't have an account?{" "}
                <Link
                  to="/register"
                  className="font-bold text-emerald-600 transition hover:text-emerald-700"
                >
                  Create an account
                </Link>
              </p>
            </div>

            {/* ==================================================
                            FOOTER
                        ================================================== */}

            <div className="mt-8 flex items-center justify-center gap-2 text-xs text-slate-400">
              <CarFront size={14} />
              Smart parking. Smarter decisions.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
