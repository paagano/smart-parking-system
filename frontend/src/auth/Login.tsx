import { FormEvent, useEffect, useState } from "react";

import { Link, useNavigate } from "react-router";

import {
  ArrowRight,
  CarFront,
  Check,
  Copy,
  LockKeyhole,
  Mail,
  ParkingCircle,
  X,
} from "lucide-react";

import { useAuth } from "./AuthContext";

import { getDefaultRoute } from "./role";

const SAMPLE_CREDENTIALS = [
  {
    role: "Driver",
    username: "jack.wallet@test.com",
    password: "Password@123",
  },
  {
    role: "Parking Attendant",
    username: "rhungu@test.com",
    password: "Password@123",
  },
  {
    role: "Administrator",
    username: "agano@test.com",
    password: "Password@123",
  },
];

export default function Login() {
  const navigate = useNavigate();

  const { login } = useAuth();

  const [email, setEmail] = useState("");

  const [password, setPassword] = useState("");

  const [isSubmitting, setIsSubmitting] = useState(false);

  const [error, setError] = useState<string | null>(null);
  const [credentialsOpen, setCredentialsOpen] = useState(false);
  const [copiedValue, setCopiedValue] = useState<string | null>(null);
  const [modalActivity, setModalActivity] = useState(0);

  useEffect(() => {
    if (!credentialsOpen) return;
    const timeout = window.setTimeout(() => {
      setCredentialsOpen(false);
      setCopiedValue(null);
    }, 10_000);
    return () => window.clearTimeout(timeout);
  }, [credentialsOpen, modalActivity]);

  useEffect(() => {
    if (!credentialsOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setCredentialsOpen(false);
        setCopiedValue(null);
      } else {
        setModalActivity((activity) => activity + 1);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [credentialsOpen]);

  const markModalActivity = () => {
    setModalActivity((activity) => activity + 1);
  };

  const copyCredential = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedValue(value);
      markModalActivity();
    } catch {
      setCopiedValue(null);
    }
  };

  const useSampleCredentials = (
    credential: (typeof SAMPLE_CREDENTIALS)[number],
  ) => {
    setEmail(credential.username);
    setPassword(credential.password);
    setError(null);
    setCredentialsOpen(false);
    setCopiedValue(null);
  };

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
          "Server restarting... Please try again after 15 seconds.",
        );
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="relative min-h-screen bg-[#071a2d] p-4 sm:p-6 lg:p-8 grid place-items-center">
      <div className="absolute left-1/2 top-6 z-10 flex w-full max-w-6xl -translate-x-1/2 justify-end px-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={() => {
            setCredentialsOpen(true);
            setCopiedValue(null);
            markModalActivity();
          }}
          className="motion-safe:animate-pulse rounded-xl border border-emerald-300/40 bg-[#0b2942] px-4 py-2.5 text-xs font-bold text-emerald-300 shadow-lg transition hover:border-emerald-300 hover:bg-[#103651] sm:text-sm"
        >
          Click here to get sample login credentials
        </button>
      </div>
      <div className="grid w-full max-w-6xl overflow-hidden rounded-[2rem] border border-slate-200/80 bg-white shadow-[0_24px_70px_rgba(15,23,42,0.18)] lg:grid-cols-[1.02fr_0.98fr]">
        {/* ==================================================
                    BRAND PANEL
                ================================================== */}

        <div className="hidden min-h-[680px] bg-[#071f35] p-10 text-white lg:flex lg:flex-col lg:justify-between xl:p-12">
          <div>
            <div className="flex items-center gap-3 text-xl font-extrabold tracking-tight">
              <span className="grid h-11 w-11 place-items-center rounded-2xl bg-emerald-400 text-[#071a2d] shadow-lg shadow-emerald-950/20">
                <ParkingCircle />
              </span>
              SmartPark
              <span className="text-emerald-400">AI</span>
            </div>

            <div className="mt-24 max-w-xl">
              <div className="text-xs font-bold uppercase tracking-[.2em] text-emerald-300">
                AI-powered parking intelligence
              </div>

              <h1 className="mt-4 text-4xl font-black leading-[1.08] xl:text-5xl">
                Find a space.
                <br />
                Plan ahead.
                <br />
                <span className="text-emerald-400">Park smarter.</span>
              </h1>

              <p className="mt-6 max-w-lg text-sm leading-7 text-slate-300 xl:text-base">
                Real-time availability, reservations and predictive occupancy
                intelligence for smart cities.
              </p>
            </div>
          </div>

          {/* ==================================================
                        PLATFORM STATISTICS
              ================================================== */}

          <div className="grid grid-cols-3 gap-3">
            <div className="rounded-2xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur-sm">
              <b className="text-2xl">42</b>

              <div className="text-xs text-slate-400 mt-1">Facilities</div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur-sm">
              <b className="text-2xl">2,840</b>

              <div className="text-xs text-slate-400 mt-1">Spaces</div>
            </div>

            <div className="rounded-2xl border border-white/10 bg-white/[0.06] p-4 backdrop-blur-sm">
              <b className="text-2xl">AI</b>

              <div className="text-xs text-slate-400 mt-1">Prediction</div>
            </div>
          </div>
        </div>

        {/* ==================================================
                    LOGIN PANEL
            ================================================== */}

        <div className="grid place-items-center p-7 sm:p-12 lg:p-14">
          <div className="w-full max-w-[430px]">
            <div className="text-xs font-bold uppercase tracking-[.2em] text-emerald-600">
              SmartPark AI
            </div>

            <h2 className="mt-2 text-3xl font-extrabold tracking-tight text-slate-950">
              Welcome Back!
            </h2>

            <p className="mt-2 text-sm leading-6 text-slate-500">
              Sign in to access your SmartPark AI account.
            </p>

            {/* ==================================================
                            ERROR
                ================================================== */}

            {error && (
              <div className="mt-5 flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3.5 text-sm leading-5 text-rose-700">
                {error}
              </div>
            )}

            {/* ==================================================
                            FORM
                        ================================================== */}

            <form onSubmit={handleSubmit} className="mt-7 space-y-5">
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
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50/40 py-3.5 pl-11 pr-4 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-50 disabled:bg-slate-100"
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
                    className="w-full rounded-2xl border border-slate-200 bg-slate-50/40 py-3.5 pl-11 pr-4 text-sm text-slate-900 outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-emerald-400 focus:bg-white focus:ring-4 focus:ring-emerald-50 disabled:bg-slate-100"
                  />
                </div>

                <div className="mt-2.5 flex justify-end">
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
                className="group flex w-full items-center justify-center gap-3 rounded-2xl bg-[#071a2d] px-5 py-3.5 font-bold text-white shadow-lg shadow-slate-900/10 transition hover:-translate-y-0.5 hover:bg-[#0a2740] hover:shadow-xl disabled:cursor-not-allowed disabled:opacity-60 disabled:hover:translate-y-0"
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

            <div className="mt-5 flex items-center justify-center gap-2 text-[11px] font-medium text-slate-400">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
              Secure access to your SmartPark account
            </div>

            {/* ==================================================
                            REGISTRATION
                ================================================== */}

            <div className="mt-7 border-t border-slate-100 pt-6 text-center">
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

            <div className="mt-7 flex items-center justify-center gap-2 text-xs text-slate-400">
              <CarFront size={14} />
              Smart parking. Smarter decisions.
            </div>
          </div>
        </div>
      </div>

      {credentialsOpen && (
        <div
          className="fixed inset-0 z-50 grid place-items-center bg-slate-950/65 p-4 backdrop-blur-sm"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setCredentialsOpen(false);
              setCopiedValue(null);
            }
          }}
          onPointerDown={markModalActivity}
          onKeyDown={markModalActivity}
        >
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="sample-credentials-title"
            className="w-full max-w-5xl overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-2xl"
          >
            <div className="flex items-start justify-between gap-4 bg-[#071f35] px-6 py-5 text-white sm:px-8">
              <div>
                <div className="text-xs font-bold uppercase tracking-[.18em] text-emerald-300">
                  SmartPark AI
                </div>
                <h2
                  id="sample-credentials-title"
                  className="mt-1 text-xl font-extrabold sm:text-2xl"
                >
                  Sample Login Credentials
                </h2>
                <p className="mt-2 text-sm leading-5 text-slate-300">
                  Copy a username or password, then paste it into the sign-in
                  form OR click the auto-fill button.
                </p>
              </div>
              <button
                type="button"
                aria-label="Close sample credentials"
                onClick={() => {
                  setCredentialsOpen(false);
                  setCopiedValue(null);
                }}
                className="rounded-xl p-2 text-slate-300 transition hover:bg-white/10 hover:text-white"
              >
                <X size={20} />
              </button>
            </div>
            <div className="p-5 sm:p-8">
              <div className="overflow-x-auto rounded-2xl border border-slate-200">
                <table className="w-full min-w-[820px] text-left text-sm">
                  <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-4 py-3 font-bold">Role</th>
                      <th className="px-4 py-3 font-bold">Username</th>
                      <th className="px-4 py-3 font-bold">Password</th>
                      <th className="px-4 py-3 text-right font-bold">Login</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {SAMPLE_CREDENTIALS.map((credential) => (
                      <tr key={credential.role} className="align-middle">
                        <th
                          scope="row"
                          className="px-4 py-4 font-semibold text-slate-700"
                        >
                          {credential.role}
                        </th>
                        {[credential.username, credential.password].map(
                          (value) => (
                            <td
                              key={value + credential.role}
                              className="px-4 py-4"
                            >
                              <div className="flex items-center gap-2">
                                <code className="whitespace-nowrap rounded-lg bg-slate-50 px-2 py-1.5 text-xs text-slate-700">
                                  {value}
                                </code>
                                <button
                                  type="button"
                                  onClick={() => void copyCredential(value)}
                                  aria-label={`Copy ${value}`}
                                  title={`Copy ${value}`}
                                  className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-200 px-2 py-1.5 text-xs font-semibold text-slate-600 transition hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700"
                                >
                                  {copiedValue === value ? (
                                    <Check size={14} />
                                  ) : (
                                    <Copy size={14} />
                                  )}
                                  <span>
                                    {copiedValue === value ? "Copied" : "Copy"}
                                  </span>
                                </button>
                              </div>
                            </td>
                          ),
                        )}
                        <td className="px-4 py-4 text-right">
                          <button
                            type="button"
                            onClick={() => useSampleCredentials(credential)}
                            className="motion-safe:animate-pulse whitespace-nowrap rounded-xl bg-emerald-600 px-3 py-2 text-xs font-bold text-white transition hover:bg-emerald-700 focus:outline-none focus:ring-4 focus:ring-emerald-100"
                          >
                            Click to Auto-Fill Login Form
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="mt-5 flex flex-col gap-3 text-xs text-slate-500 sm:flex-row sm:items-center sm:justify-between">
                <p>
                  For demonstration access only. Please DO NOT delete any
                  records in the system using the Admin credentials.
                </p>
                <button
                  type="button"
                  onClick={() => {
                    setCredentialsOpen(false);
                    setCopiedValue(null);
                  }}
                  className="self-end rounded-xl bg-[#071a2d] px-4 py-2.5 font-bold text-white transition hover:bg-[#0a2740] sm:self-auto"
                >
                  Close
                </button>
              </div>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
