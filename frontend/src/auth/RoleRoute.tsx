import { Navigate, Outlet } from "react-router";
import { useAuth } from "./AuthContext";
import { normalizeRole, type Role } from "./role";

// ==========================================================
// Frontend Roles
// ==========================================================
//
// Backend roles:
//   DRIVER
//   ATTENDANT
//   ADMIN
//
// Frontend terminology:
//   driver
//   operator
//   admin
//
// The conversion from backend -> frontend happens here so
// the rest of the frontend has one consistent role model.
// ==========================================================



// ==========================================================
// Props
// ==========================================================

interface RoleRouteProps {
  allowedRoles: Role[];

  /**
   * Optional children allow RoleRoute to be used like:
   *
   * <RoleRoute allowedRoles={["driver"]}>
   *   <DriverDashboard />
   * </RoleRoute>
   *
   * It also supports the Outlet pattern:
   *
   * <RoleRoute allowedRoles={["driver"]} />
   */
  children?: React.ReactNode;
}

// ==========================================================
// Role Route
// ==========================================================

export default function RoleRoute({ allowedRoles, children }: RoleRouteProps) {
  const { user, isLoading } = useAuth();

  // --------------------------------------------------------
  // Authentication is still being restored
  // --------------------------------------------------------

  if (isLoading) {
    return (
      <div className="min-h-[60vh] grid place-items-center">
        <div className="text-center">
          <div className="mx-auto h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-emerald-500" />

          <p className="mt-4 text-sm font-semibold text-slate-500">
            Loading SmartPark AI...
          </p>
        </div>
      </div>
    );
  }

  // --------------------------------------------------------
  // No authenticated user
  // --------------------------------------------------------

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // --------------------------------------------------------
  // Normalise backend role
  // --------------------------------------------------------

  const role = normalizeRole(user.role);

  // --------------------------------------------------------
  // Authorisation
  // --------------------------------------------------------

  if (!allowedRoles.includes(role)) {
    // Send the user to the correct portal instead of leaving
    // them on a blank/unauthorised page.
    if (role === "admin") {
      return <Navigate to="/admin" replace />;
    }

    if (role === "operator") {
      return <Navigate to="/operator" replace />;
    }

    return <Navigate to="/dashboard" replace />;
  }

  // --------------------------------------------------------
  // Authorised
  // --------------------------------------------------------

  if (children) {
    return <>{children}</>;
  }

  return <Outlet />;
}
