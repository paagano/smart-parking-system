import { Navigate, Outlet, useLocation } from "react-router";
import { useAuth } from "./AuthContext";

// ==========================================================
// Protected Route
// ==========================================================
//
// Ensures that only authenticated users can access the
// SmartPark AI application.
//
// Authentication itself is handled by AuthContext.
// This component only controls route access.
// ==========================================================

export default function ProtectedRoute({
  children,
}: {
  children?: React.ReactNode;
}) {
  const { user, isAuthenticated, isLoading } = useAuth();

  const location = useLocation();

  // --------------------------------------------------------
  // Restore authentication state
  // --------------------------------------------------------

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[#071a2d] grid place-items-center">
        <div className="text-center text-white">
          <div className="mx-auto h-12 w-12 animate-spin rounded-full border-4 border-white/20 border-t-emerald-400" />

          <p className="mt-4 text-sm font-semibold text-slate-300">
            Loading SmartPark AI...
          </p>
        </div>
      </div>
    );
  }

  // --------------------------------------------------------
  // Not authenticated
  // --------------------------------------------------------

  if (!isAuthenticated || !user) {
    return (
      <Navigate
        to="/login"
        replace
        state={{
          from: location,
        }}
      />
    );
  }

  // --------------------------------------------------------
  // Authenticated
  // --------------------------------------------------------

  if (children) {
    return <>{children}</>;
  }

  return <Outlet />;
}
