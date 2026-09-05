import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { CheckCircle2, Loader2, MailCheck, ShieldAlert } from "lucide-react";

import { api, getApiErrorMessage } from "../../api";

type VerificationState = "loading" | "success" | "error";

interface VerifyEmailResponse {
  message: string;
  user: {
    id: number;
    first_name: string;
    last_name: string;
    email: string;
    phone_number: number | string;
    profile_picture_url: string | null;
    role: "DRIVER" | "ATTENDANT" | "ADMIN";
    is_active: boolean;
    is_verified: boolean;
    created_at: string;
    updated_at: string;
  };
}

export default function VerifyEmail() {
  const [searchParams] = useSearchParams();

  const [state, setState] = useState<VerificationState>("loading");

  const [message, setMessage] = useState(
    "Please wait while we verify your email address.",
  );

  const verificationStarted = useRef(false);

  useEffect(() => {
    if (verificationStarted.current) {
      return;
    }

    verificationStarted.current = true;

    const token = searchParams.get("token");

    if (!token) {
      setState("error");

      setMessage(
        "This email verification link is invalid because no verification token was provided.",
      );

      return;
    }

    const verifyEmail = async () => {
      try {
        const response = await api.post<VerifyEmailResponse>(
          "/auth/verify-email",
          null,
          {
            params: {
              token,
            },
          },
        );

        setState("success");

        setMessage(
          response.data.message ||
            "Your email address has been verified successfully. Your SmartPark AI account is now verified.",
        );
      } catch (err: unknown) {
        setState("error");

        const apiMessage = getApiErrorMessage(err);

        setMessage(
          apiMessage ||
            "This verification link is invalid or has expired. Please request a new verification email.",
        );
      }
    };

    void verifyEmail();
  }, [searchParams]);

  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4 py-8">
      <div className="w-full max-w-md">
        {/* Brand */}
        <div className="text-center mb-8">
          <Link
            to="/login"
            className="inline-flex items-center gap-2 text-2xl font-black text-slate-900"
          >
            <MailCheck className="h-7 w-7 text-blue-600" />

            <span>
              SmartPark <span className="text-emerald-600">AI</span>
            </span>
          </Link>
        </div>

        {/* Verification Card */}
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-8">
          {/* =====================================================
              LOADING
          ====================================================== */}
          {state === "loading" && (
            <div className="text-center">
              <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-blue-50">
                <Loader2 className="h-8 w-8 text-blue-600 animate-spin" />
              </div>

              <h1 className="text-2xl font-black text-slate-900">
                Verifying Your Email
              </h1>

              <p className="mt-3 text-sm leading-6 text-slate-500">{message}</p>
            </div>
          )}

          {/* =====================================================
              SUCCESS
          ====================================================== */}
          {state === "success" && (
            <div className="text-center">
              <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-50">
                <CheckCircle2 className="h-9 w-9 text-emerald-600" />
              </div>

              <h1 className="text-2xl font-black text-slate-900">
                Email Verified Successfully
              </h1>

              <p className="mt-3 text-sm leading-6 text-slate-500">{message}</p>

              <div className="mt-8">
                <Link
                  to="/login"
                  className="inline-flex w-full items-center justify-center rounded-xl bg-blue-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-blue-700"
                >
                  Continue to Login
                </Link>
              </div>
            </div>
          )}

          {/* =====================================================
              ERROR
          ====================================================== */}
          {state === "error" && (
            <div className="text-center">
              <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-amber-50">
                <ShieldAlert className="h-9 w-9 text-amber-600" />
              </div>

              <h1 className="text-2xl font-black text-slate-900">
                Verification Failed
              </h1>

              <p className="mt-3 text-sm leading-6 text-slate-500">{message}</p>

              <div className="mt-8 space-y-3">
                <Link
                  to="/login"
                  className="inline-flex w-full items-center justify-center rounded-xl bg-blue-600 px-5 py-3 text-sm font-bold text-white transition hover:bg-blue-700"
                >
                  Go to Login
                </Link>

                <p className="text-xs leading-5 text-slate-400">
                  If your verification link has expired, log in and use the
                  profile page to request a new verification email.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <p className="mt-6 text-center text-xs text-slate-400">
          © {new Date().getFullYear()} SmartPark AI. All rights reserved.
        </p>
      </div>
    </div>
  );
}
