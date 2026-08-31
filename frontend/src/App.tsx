import { Navigate, Route, Routes } from "react-router";

import Login from "./auth/Login";
import ProtectedRoute from "./auth/ProtectedRoute";
import RoleRoute from "./auth/RoleRoute";
import { normalizeRole } from "./auth/role";
import { useAuth } from "./auth/AuthContext";
import Shell from "./components/layout/Shell";

// ==========================================================
// DRIVER
// ==========================================================

import DriverDashboard from "./pages/driver/Dashboard/DriverDashboard";

import Parking from "./pages/driver/Parking/Parking";

import Reservations from "./pages/driver/Reservations/Reservations";
import ActiveReservations from "./pages/driver/Reservations/ActiveReservations";
import UpcomingReservations from "./pages/driver/Reservations/UpcomingReservations";
import CreateReservation from "./pages/driver/Reservations/CreateReservation";
import ReservationHistory from "./pages/driver/Reservations/ReservationHistory";

import Vehicles from "./pages/driver/Vehicles/Vehicles";
import AddVehicle from "./pages/driver/Vehicles/AddVehicle";
import EditVehicle from "./pages/driver/Vehicles/EditVehicle";

import Payments from "./pages/driver/Payments/Payments";
import Wallet from "./pages/driver/Payments/Wallet";

import Receipts from "./pages/driver/Receipts/Receipts";

import Forecast from "./pages/driver/Forecast/Forecast";

import Loyalty from "./pages/driver/Loyalty/Loyalty";

import Notifications from "./pages/driver/Notifications/Notifications";

import ParkingSessions from "./pages/driver/Sessions/ParkingSessions";
import SessionDetails from "./pages/driver/Sessions/SessionDetails";

// ==========================================================
// OPERATOR
// ==========================================================

import OperatorDashboard from "./pages/operator/Dashboard/OperatorDashboard";
import Facilities from "./pages/operator/Facilities/Facilities";

// ==========================================================
// ADMIN
// ==========================================================

import AdminDashboard from "./pages/admin/Dashboard/AdminDashboard";

// ==========================================================
// SHARED
// ==========================================================

import Settings from "./pages/shared/Settings";

// ==========================================================
// APPLICATION
// ==========================================================

export default function App() {
  return (
    <Routes>
      {/* ==================================================
          LOGIN
      ================================================== */}

      <Route path="/login" element={<Login />} />

      {/* ==================================================
          PROTECTED APPLICATION
      ================================================== */}

      <Route
        path="/*"
        element={
          <ProtectedRoute>
            <AuthenticatedApplication />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

// ==========================================================
// AUTHENTICATED APPLICATION
// ==========================================================

function AuthenticatedApplication() {
  const { user } = useAuth();

  const role = normalizeRole(user?.role);

  return (
    <Shell role={role}>
      <Routes>
        {/* ==================================================
            ROOT
        ================================================== */}

        <Route
          path="/"
          element={
            <Navigate
              to={
                role === "admin"
                  ? "/admin"
                  : role === "operator"
                    ? "/operator"
                    : "/dashboard"
              }
              replace
            />
          }
        />

        {/* ==================================================
            DRIVER — DASHBOARD
        ================================================== */}

        <Route
          path="/dashboard"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <DriverDashboard />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — PARKING
        ================================================== */}

        <Route
          path="/parking"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <Parking />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — LOYALTY PROGRAMME
        ================================================== */}

        <Route
          path="/loyalty"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <Loyalty />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — NOTIFICATIONS
        ================================================== */}

        <Route
          path="/notifications"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <Notifications />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — PAYMENT HISTORY
        ==================================================
        
            This is the normal payment-history page.
            Do NOT use this route for parking-session checkout.
        ================================================== */}

        <Route
          path="/payments"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <Payments />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — PARKING SESSION CHECKOUT
        ==================================================
        
            Dedicated checkout route.

            Expected URL:

            /payments/checkout
              ?sessionId=28
              &amount=500
              &currency=KES
              &checkout=1

            The actual checkout UI should be handled by the
            Payments component based on these query parameters.
        ================================================== */}

        <Route
          path="/payments/checkout"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <Payments />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — WALLET
        ================================================== */}

        <Route
          path="/payments/wallet"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <Wallet />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — RECEIPTS
        ================================================== */}

        <Route
          path="/receipts"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <Receipts />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — RESERVATIONS — MY RESERVATIONS
        ================================================== */}

        <Route
          path="/reservations"
          element={
            <RoleRoute allowedRoles={["driver", "operator", "admin"]}>
              <Reservations />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — RESERVATIONS — UPCOMING
        ================================================== */}

        <Route
          path="/reservations/upcoming"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <UpcomingReservations />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — RESERVATIONS — ACTIVE
        ================================================== */}

        <Route
          path="/reservations/active"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <ActiveReservations />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — RESERVATIONS — HISTORY
        ================================================== */}

        <Route
          path="/reservations/history"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <ReservationHistory />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — RESERVATIONS — CREATE
        ================================================== */}

        <Route
          path="/reservations/create"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <CreateReservation />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — VEHICLES — MY VEHICLES
        ================================================== */}

        <Route
          path="/vehicles"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <Vehicles />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — VEHICLES — ADD VEHICLE
        ================================================== */}

        <Route
          path="/vehicles/create"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <AddVehicle />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — VEHICLES — EDIT VEHICLE
        ================================================== */}

        <Route
          path="/vehicles/:vehicleId/edit"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <EditVehicle />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — PARKING SESSIONS
        ================================================== */}

        <Route
          path="/sessions"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <ParkingSessions />
            </RoleRoute>
          }
        />

        {/* ==================================================
            DRIVER — SESSION DETAILS
        ================================================== */}

        <Route
          path="/sessions/:sessionId"
          element={
            <RoleRoute allowedRoles={["driver"]}>
              <SessionDetails />
            </RoleRoute>
          }
        />

        {/* ==================================================
            FORECAST
        ================================================== */}

        <Route
          path="/forecast"
          element={
            <RoleRoute allowedRoles={["driver", "operator", "admin"]}>
              <Forecast />
            </RoleRoute>
          }
        />

        {/* ==================================================
            OPERATOR — DASHBOARD
        ================================================== */}

        <Route
          path="/operator"
          element={
            <RoleRoute allowedRoles={["operator"]}>
              <OperatorDashboard />
            </RoleRoute>
          }
        />

        {/* ==================================================
            OPERATOR — FACILITIES
        ================================================== */}

        <Route
          path="/operator/facilities"
          element={
            <RoleRoute allowedRoles={["operator", "admin"]}>
              <Facilities />
            </RoleRoute>
          }
        />

        {/* ==================================================
            ADMIN — DASHBOARD
        ================================================== */}

        <Route
          path="/admin"
          element={
            <RoleRoute allowedRoles={["admin"]}>
              <AdminDashboard />
            </RoleRoute>
          }
        />

        {/* ==================================================
            SETTINGS
        ================================================== */}

        <Route
          path="/settings"
          element={
            <RoleRoute allowedRoles={["driver", "operator", "admin"]}>
              <Settings />
            </RoleRoute>
          }
        />

        {/* ==================================================
            FALLBACK
        ================================================== */}

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Shell>
  );
}
