import { FormEvent, useState } from "react";

import { Link, useNavigate } from "react-router";

import {
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
  LockKeyhole,
  Mail,
  ParkingCircle,
  Phone,
  User,
  UserRound,
} from "lucide-react";

import { api, getApiErrorMessage } from "../api";

type RegistrationState = "form" | "success";

interface RegisterResponse {
  message?: string;
  user?: {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
  };
}

function PasswordRequirement({ met, label }: { met: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2">
      <span
        className={`grid h-4 w-4 shrink-0 place-items-center rounded-full ${
          met
            ? "bg-emerald-100 text-emerald-600"
            : "bg-slate-100 text-slate-400"
        }`}
      >
        {met ? <CheckCircle2 size={11} /> : null}
      </span>

      <span className={met ? "text-emerald-700" : "text-slate-500"}>
        {label}
      </span>
    </div>
  );
}

export default function Register() {
  const navigate = useNavigate();

  const [firstName, setFirstName] = useState("");

  const [lastName, setLastName] = useState("");

  const [email, setEmail] = useState("");

  const [phoneNumber, setPhoneNumber] = useState("");

  const [password, setPassword] = useState("");

  const [confirmPassword, setConfirmPassword] = useState("");

  const [showPassword, setShowPassword] = useState(false);

  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

  const [isSubmitting, setIsSubmitting] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [registrationState, setRegistrationState] =
    useState<RegistrationState>("form");

  // ======================================================
  // Password validation
  // ======================================================

  const passwordRequirements = {
    length: password.length >= 8,
    uppercase: /[A-Z]/.test(password),
    lowercase: /[a-z]/.test(password),
    number: /[0-9]/.test(password),
    special: /[^A-Za-z0-9]/.test(password),
  };

  const passwordValid =
    passwordRequirements.length &&
    passwordRequirements.uppercase &&
    passwordRequirements.lowercase &&
    passwordRequirements.number &&
    passwordRequirements.special;

  // ======================================================
  // Submit
  // ======================================================

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    setError(null);

    const trimmedFirstName = firstName.trim();

    const trimmedLastName = lastName.trim();

    const trimmedEmail = email.trim().toLowerCase();

    const trimmedPhoneNumber = phoneNumber.trim();

    // ====================================================
    // Basic validation
    // ====================================================

    if (!trimmedFirstName) {
      setError("Please enter your first name.");
      return;
    }

    if (!trimmedLastName) {
      setError("Please enter your last name.");
      return;
    }

    if (!trimmedEmail) {
      setError("Please enter your email address.");
      return;
    }

    if (!trimmedPhoneNumber) {
      setError("Please enter your phone number.");
      return;
    }

    if (!password) {
      setError("Please create a password.");
      return;
    }

    if (!passwordValid) {
      setError(
        "Your password does not meet all the required security requirements.",
      );
      return;
    }

    if (password !== confirmPassword) {
      setError("Your passwords do not match.");
      return;
    }

    setIsSubmitting(true);

    try {
      /*
       * The backend registration endpoint expects:
       *
       * first_name
       * last_name
       * email
       * phone_number
       * password
       *
       * The backend is responsible for:
       *
       * - checking email uniqueness
       * - checking phone uniqueness
       * - hashing the password
       * - creating the user
       * - provisioning the wallet
       * - sending the verification email
       */
      await api.post<RegisterResponse>("/auth/register", {
        first_name: trimmedFirstName,
        last_name: trimmedLastName,
        email: trimmedEmail,
        phone_number: trimmedPhoneNumber,
        password,
      });

      setRegistrationState("success");
    } catch (err: unknown) {
      const backendMessage = getApiErrorMessage(err);

      if (backendMessage) {
        setError(backendMessage);
      } else {
        setError("Unable to create your account. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  // ======================================================
  // SUCCESS
  // ======================================================

  if (registrationState === "success") {
    return (
      <div className="min-h-screen bg-[#071a2d] p-3 sm:p-4 grid place-items-center">
        <div className="w-full max-w-lg">
          {/* Brand */}
          <div className="mb-8 text-center">
            <Link
              to="/login"
              className="inline-flex items-center gap-3 font-extrabold text-2xl text-white"
            >
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-400 text-[#071a2d]">
                <ParkingCircle size={25} />
              </span>
              SmartPark
              <span className="text-emerald-400">AI</span>
            </Link>
          </div>

          {/* Success Card */}
          <div className="rounded-[2rem] bg-white p-8 shadow-2xl sm:p-12">
            <div className="text-center">
              <div className="mx-auto grid h-20 w-20 place-items-center rounded-full bg-emerald-50">
                <CheckCircle2 size={42} className="text-emerald-600" />
              </div>

              <div className="mt-7 text-xs font-bold uppercase tracking-[.2em] text-emerald-600">
                Account created
              </div>

              <h1 className="mt-1 text-2xl font-black text-slate-900">
                Welcome to SmartPark AI
              </h1>

              <p className="mx-auto mt-4 max-w-md text-sm leading-6 text-slate-500">
                Your account has been created successfully. We have sent a
                verification email to:
              </p>

              <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-bold text-slate-800">
                {email.trim().toLowerCase()}
              </div>

              <div className="mt-6 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-4 text-left">
                <div className="flex items-start gap-3">
                  <Mail
                    size={19}
                    className="mt-0.5 shrink-0 text-emerald-600"
                  />

                  <div>
                    <p className="text-sm font-bold text-emerald-800">
                      Verify your email address
                    </p>

                    <p className="mt-1 text-xs leading-5 text-emerald-700">
                      Open the verification email and click
                      <strong> Verify My Email </strong>
                      to activate your verified account.
                    </p>
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={() =>
                  navigate("/login", {
                    replace: true,
                  })
                }
                className="group mt-8 flex w-full items-center justify-center gap-3 rounded-2xl bg-[#071a2d] px-5 py-3.5 font-bold text-white transition hover:bg-[#0a2740]"
              >
                Continue to Login
                <ArrowRight
                  size={18}
                  className="transition-transform group-hover:translate-x-1"
                />
              </button>

              <p className="mt-5 text-xs text-slate-400">
                You can verify your email before signing in.
              </p>
            </div>
          </div>

          <p className="mt-6 text-center text-xs text-slate-500">
            Smart parking. Smarter decisions.
          </p>
        </div>
      </div>
    );
  }

  // ======================================================
  // REGISTRATION FORM
  // ======================================================

  return (
    <div className="min-h-screen bg-[#071a2d] p-3 sm:p-4 grid place-items-center">
      <div className="grid w-full max-w-6xl overflow-hidden rounded-[2rem] bg-white shadow-2xl lg:grid-cols-2">
        {/* ==================================================
                    BRAND PANEL
            ================================================== */}

        <div className="hidden min-h-[680px] bg-[#0a2740] p-10 text-white lg:flex lg:flex-col lg:justify-between">
          <div>
            {/* Logo */}
            <div className="flex items-center gap-3 font-extrabold text-xl">
              <span className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-400 text-[#071a2d]">
                <ParkingCircle />
              </span>
              SmartPark
              <span className="text-emerald-400">AI</span>
            </div>

            {/* Hero */}
            <div className="mt-20 max-w-lg">
              <div className="text-emerald-300 text-xs font-bold uppercase tracking-[.2em]">
                Join SmartPark AI
              </div>

              <h1 className="mt-3 text-4xl font-black leading-tight">
                Park smarter.
                <br />
                Travel better.
                <br />
                <span className="text-emerald-400">Start today.</span>
              </h1>

              <p className="mt-4 leading-6 text-sm text-slate-300">
                Create your SmartPark AI account and get access to real-time
                parking availability, reservations and intelligent parking
                insights.
              </p>
            </div>
          </div>

          {/* Benefits */}
          <div className="space-y-3">
            <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-400/10 text-emerald-300">
                <ParkingCircle size={19} />
              </div>

              <div>
                <div className="text-sm font-bold">Find parking easily</div>

                <div className="mt-0.5 text-xs text-slate-400">
                  Discover available parking spaces.
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-400/10 text-emerald-300">
                <CheckCircle2 size={19} />
              </div>

              <div>
                <div className="text-sm font-bold">Reserve with confidence</div>

                <div className="mt-0.5 text-xs text-slate-400">
                  Plan your parking before you arrive.
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/5 p-4">
              <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-400/10 text-emerald-300">
                <ArrowRight size={19} />
              </div>

              <div>
                <div className="text-sm font-bold">Make smarter journeys</div>

                <div className="mt-0.5 text-xs text-slate-400">
                  Powered by intelligent parking insights.
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* ==================================================
                    REGISTRATION PANEL
            ================================================== */}

        <div className="p-5 sm:p-8 lg:p-9">
          <div className="mx-auto w-full max-w-xl">
            {/* Mobile logo */}
            <div className="mb-5 flex items-center gap-2 font-extrabold text-lg text-slate-900 lg:hidden">
              <span className="grid h-9 w-9 place-items-center rounded-lg bg-emerald-400 text-[#071a2d]">
                <ParkingCircle size={20} />
              </span>
              SmartPark
              <span className="text-emerald-600">AI</span>
            </div>

            {/* Heading */}
            <div>
              <div className="text-xs font-bold uppercase tracking-[.2em] text-emerald-600">
                SmartPark AI
              </div>

              <h2 className="mt-1 text-2xl font-black text-slate-900">
                Create your account
              </h2>

              <p className="mt-2 text-xs leading-5 text-slate-500">
                Join SmartPark AI and start parking smarter.
              </p>
            </div>

            {/* Error */}
            {error && (
              <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-xs leading-5 text-red-700">
                {error}
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="mt-5 space-y-3.5">
              {/* ==================================================
                            NAME
                ================================================== */}

              <div className="grid gap-3 sm:grid-cols-2">
                {/* First name */}
                <div>
                  <label
                    htmlFor="firstName"
                    className="mb-1.5 block text-xs font-semibold text-slate-700"
                  >
                    First name
                  </label>

                  <div className="relative">
                    <User
                      size={18}
                      className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                    />

                    <input
                      id="firstName"
                      type="text"
                      autoComplete="given-name"
                      value={firstName}
                      onChange={(event) => setFirstName(event.target.value)}
                      placeholder="First name"
                      disabled={isSubmitting}
                      className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                    />
                  </div>
                </div>

                {/* Last name */}
                <div>
                  <label
                    htmlFor="lastName"
                    className="mb-1.5 block text-xs font-semibold text-slate-700"
                  >
                    Last name
                  </label>

                  <div className="relative">
                    <UserRound
                      size={18}
                      className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                    />

                    <input
                      id="lastName"
                      type="text"
                      autoComplete="family-name"
                      value={lastName}
                      onChange={(event) => setLastName(event.target.value)}
                      placeholder="Last name"
                      disabled={isSubmitting}
                      className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                    />
                  </div>
                </div>
              </div>

              {/* ==================================================
                            EMAIL
                ================================================== */}

              <div>
                <label
                  htmlFor="email"
                  className="mb-1.5 block text-xs font-semibold text-slate-700"
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
                    autoComplete="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    placeholder="you@example.com"
                    disabled={isSubmitting}
                    className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                  />
                </div>
              </div>

              {/* ==================================================
                            PHONE
                ================================================== */}

              <div>
                <label
                  htmlFor="phoneNumber"
                  className="mb-1.5 block text-xs font-semibold text-slate-700"
                >
                  Phone number
                </label>

                <div className="relative">
                  <Phone
                    size={18}
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                  />

                  <input
                    id="phoneNumber"
                    type="tel"
                    autoComplete="tel"
                    value={phoneNumber}
                    onChange={(event) => setPhoneNumber(event.target.value)}
                    placeholder="2547XXXXXXXX"
                    disabled={isSubmitting}
                    className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-4 text-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                  />
                </div>

                <p className="mt-1 text-[11px] text-slate-400">
                  Use your active mobile number.
                </p>
              </div>

              {/* ==================================================
                            PASSWORD
                ================================================== */}

              <div>
                <label
                  htmlFor="password"
                  className="mb-1.5 block text-xs font-semibold text-slate-700"
                >
                  Password
                </label>

                <div className="relative">
                  <LockKeyhole
                    size={18}
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                  />

                  <input
                    id="password"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    placeholder="Create a secure password"
                    disabled={isSubmitting}
                    className="w-full rounded-xl border border-slate-200 bg-white py-2.5 pl-10 pr-11 text-sm outline-none transition focus:border-emerald-400 focus:ring-2 focus:ring-emerald-100 disabled:bg-slate-50"
                  />

                  <button
                    type="button"
                    onClick={() => setShowPassword((current) => !current)}
                    disabled={isSubmitting}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 transition hover:text-slate-600"
                    aria-label={
                      showPassword ? "Hide password" : "Show password"
                    }
                  >
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>
              </div>

              {/* ==================================================
                        PASSWORD REQUIREMENTS
                ================================================== */}

              <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                <p className="text-xs font-extrabold uppercase tracking-widest text-slate-500">
                  Password requirements
                </p>

                <div className="mt-2 grid gap-1.5 text-[11px] sm:grid-cols-2">
                  <PasswordRequirement
                    met={passwordRequirements.length}
                    label="At least 8 characters"
                  />

                  <PasswordRequirement
                    met={passwordRequirements.uppercase}
                    label="One uppercase letter"
                  />

                  <PasswordRequirement
                    met={passwordRequirements.lowercase}
                    label="One lowercase letter"
                  />

                  <PasswordRequirement
                    met={passwordRequirements.number}
                    label="One number"
                  />

                  <PasswordRequirement
                    met={passwordRequirements.special}
                    label="One special character"
                  />
                </div>
              </div>

              {/* ==================================================
                        CONFIRM PASSWORD
                ================================================== */}

              <div>
                <label
                  htmlFor="confirmPassword"
                  className="mb-1.5 block text-xs font-semibold text-slate-700"
                >
                  Confirm password
                </label>

                <div className="relative">
                  <LockKeyhole
                    size={18}
                    className="absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400"
                  />

                  <input
                    id="confirmPassword"
                    type={showConfirmPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(event) => setConfirmPassword(event.target.value)}
                    placeholder="Confirm your password"
                    disabled={isSubmitting}
                    className={`w-full rounded-2xl border bg-white py-3.5 pl-11 pr-12 text-sm outline-none transition focus:ring-2 disabled:bg-slate-50 ${
                      confirmPassword && password !== confirmPassword
                        ? "border-red-300 focus:border-red-400 focus:ring-red-100"
                        : "border-slate-200 focus:border-emerald-400 focus:ring-emerald-100"
                    }`}
                  />

                  <button
                    type="button"
                    onClick={() =>
                      setShowConfirmPassword((current) => !current)
                    }
                    disabled={isSubmitting}
                    className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 transition hover:text-slate-600"
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

                {confirmPassword && password !== confirmPassword && (
                  <p className="mt-1.5 text-xs font-semibold text-red-600">
                    Passwords do not match.
                  </p>
                )}
              </div>

              {/* ==================================================
                            CREATE ACCOUNT
                ================================================== */}

              <button
                type="submit"
                disabled={isSubmitting}
                className="group flex w-full items-center justify-center gap-3 rounded-xl bg-[#071a2d] px-5 py-3 font-bold text-sm text-white transition hover:bg-[#0a2740] disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSubmitting ? (
                  <>
                    <span className="h-5 w-5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                    Creating account...
                  </>
                ) : (
                  <>
                    Create account
                    <ArrowRight
                      size={18}
                      className="transition-transform group-hover:translate-x-1"
                    />
                  </>
                )}
              </button>
            </form>

            {/* ==================================================
                            LOGIN LINK
                ================================================== */}

            <div className="mt-4 text-center">
              <p className="text-sm text-slate-500">
                Already have an account?{" "}
                <Link
                  to="/login"
                  className="font-bold text-emerald-600 transition hover:text-emerald-700"
                >
                  Sign in
                </Link>
              </p>
            </div>

            {/* Footer */}
            <div className="mt-5 flex items-center justify-center gap-2 text-xs text-slate-400">
              <ParkingCircle size={14} />
              Smart parking. Smarter decisions.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
