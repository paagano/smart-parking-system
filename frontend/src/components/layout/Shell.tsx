import { useCallback, useEffect, useRef, useState } from "react";
import type React from "react";

import { Link, useLocation, useNavigate } from "react-router";

import {
  Activity,
  Bell,
  BellRing,
  BrainCircuit,
  Building2,
  CalendarPlus,
  CarFront,
  ChevronDown,
  CreditCard,
  Gift,
  History,
  LayoutDashboard,
  Menu,
  ParkingCircle,
  Search,
  Timer,
  User,
  Settings,
  LogOut,
  Wallet,
  Users,
  X,
} from "lucide-react";

import { useAuth } from "../../auth/AuthContext";
import type { Role } from "../../auth/role";
import { api } from "../../api";

export default function Shell({
  role,
  children,
}: {
  role: Role;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);

  const [reservationsOpen, setReservationsOpen] = useState(false);

  const [vehiclesOpen, setVehiclesOpen] = useState(false);

  const [paymentsOpen, setPaymentsOpen] = useState(false);

  const [unreadCount, setUnreadCount] = useState(0);

  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const userMenuRef = useRef<HTMLDivElement>(null);

  const location = useLocation();
  const navigate = useNavigate();

  const { user, logout } = useAuth();

  // ======================================================
  // Close User Menu When Clicking Outside
  // ======================================================

  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      if (
        userMenuRef.current &&
        !userMenuRef.current.contains(event.target as Node)
      ) {
        setUserMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handleOutsideClick);

    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
    };
  }, []);

  // ======================================================
  // Navigation
  // ======================================================

  const items =
    role === "driver"
      ? [
          ["Dashboard", "/dashboard", LayoutDashboard],

          ["Find Parking", "/parking", Search],

          ["Reservations", "/reservations", ParkingCircle],

          // Parking Sessions MUST appear before Payments & Wallet
          ["Parking Sessions", "/sessions", Timer],

          ["Payments & Wallet", "/payments", CreditCard],

          ["Receipts", "/receipts", History],

          ["Vehicles", "/vehicles", CarFront],

          ["AI Prediction", "/forecast", BrainCircuit],

          ["Loyalty Programme", "/loyalty", Gift],
        ]
      : role === "operator"
        ? [
            ["Dashboard", "/operator", LayoutDashboard],
            ["Facilities", "/operator/facilities", Building2],
            ["Reservations", "/reservations", ParkingCircle],
            ["AI Forecasting", "/forecast", BrainCircuit],
          ]
        : [
            ["Dashboard", "/admin", LayoutDashboard],
            ["Users", "/admin", Users],
            ["Facilities", "/operator/facilities", Building2],
            ["AI Monitoring", "/forecast", BrainCircuit],
          ];

  // ======================================================
  // Logout
  // ======================================================

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      navigate("/login", {
        replace: true,
      });
    }
  };

  // ======================================================
  // User Display
  // ======================================================

  const firstName = user?.first_name ?? "User";

  const lastName = user?.last_name ?? "";

  const fullName = `${firstName} ${lastName}`.trim();

  const initials = `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();

  // ======================================================
  // Navigation State
  // ======================================================

  const isReservationsSection =
    role === "driver" && location.pathname.startsWith("/reservations");

  const isVehiclesSection =
    role === "driver" && location.pathname.startsWith("/vehicles");

  const isPaymentsSection =
    role === "driver" &&
    (location.pathname === "/payments" ||
      location.pathname.startsWith("/payments/"));

  const isReceiptsSection =
    role === "driver" &&
    (location.pathname === "/receipts" ||
      location.pathname.startsWith("/receipts/"));

  const isNotificationsSection =
    role === "driver" &&
    (location.pathname === "/notifications" ||
      location.pathname.startsWith("/notifications/"));

  // ======================================================
  // Parking Sessions Section
  // ======================================================

  const isSessionsSection =
    role === "driver" &&
    (location.pathname === "/sessions" ||
      location.pathname.startsWith("/sessions/"));

  // ======================================================
  // Extract Notification Count
  // ======================================================

  const extractUnreadCount = (responseData: unknown): number => {
    /*
     * The API may return any of these common
     * structures:
     *
     * 1. { count: 5 }
     * 2. { unread_count: 5 }
     * 3. { unreadCount: 5 }
     * 4. { data: { count: 5 } }
     * 5. { data: { unread_count: 5 } }
     * 6. { data: { unreadCount: 5 } }
     * 7. { data: 5 }
     * 8. 5
     */

    if (typeof responseData === "number") {
      return responseData;
    }

    if (typeof responseData === "string") {
      const parsed = Number(responseData);

      return Number.isFinite(parsed) ? parsed : 0;
    }

    if (!responseData || typeof responseData !== "object") {
      return 0;
    }

    const data = responseData as Record<string, unknown>;

    // Direct response

    if (typeof data.count === "number") {
      return data.count;
    }

    if (typeof data.unread_count === "number") {
      return data.unread_count;
    }

    if (typeof data.unreadCount === "number") {
      return data.unreadCount;
    }

    // Nested data response

    if (data.data !== null && typeof data.data === "object") {
      const nested = data.data as Record<string, unknown>;

      if (typeof nested.count === "number") {
        return nested.count;
      }

      if (typeof nested.unread_count === "number") {
        return nested.unread_count;
      }

      if (typeof nested.unreadCount === "number") {
        return nested.unreadCount;
      }
    }

    if (typeof data.data === "number") {
      return data.data;
    }

    if (typeof data.data === "string") {
      const parsed = Number(data.data);

      return Number.isFinite(parsed) ? parsed : 0;
    }

    return 0;
  };

  // ======================================================
  // Load Unread Notification Count
  // ======================================================

  const loadUnreadNotificationCount = useCallback(async () => {
    if (role !== "driver") {
      setUnreadCount(0);
      return;
    }

    try {
      const response = await api.get("/notifications/unread/count");

      const count = extractUnreadCount(response?.data);

      if (!Number.isFinite(count) || count <= 0) {
        setUnreadCount(0);
        return;
      }

      setUnreadCount(Math.floor(count));
    } catch (error) {
      console.error("[Shell] Failed to load unread notification count:", error);

      setUnreadCount((current) => current);
    }
  }, [role]);

  // ======================================================
  // Initial / Navigation Refresh
  // ======================================================

  useEffect(() => {
    void loadUnreadNotificationCount();
  }, [loadUnreadNotificationCount, location.pathname]);

  // ======================================================
  // Poll Notification Count
  // ======================================================

  useEffect(() => {
    if (role !== "driver") {
      return;
    }

    const interval = window.setInterval(() => {
      void loadUnreadNotificationCount();
    }, 30_000);

    return () => {
      window.clearInterval(interval);
    };
  }, [role, loadUnreadNotificationCount]);

  // ======================================================
  // Notification Bell
  // ======================================================

  const handleNotificationClick = () => {
    navigate("/notifications");
    setOpen(false);
  };

  // ======================================================
  // Render
  // ======================================================

  return (
    <div className="min-h-screen bg-slate-50">
      {/* ==================================================
          SIDEBAR
      ================================================== */}

      <aside
        className={`
          fixed
          inset-y-0
          left-0
          z-40
          w-72
          bg-[#071a2d]
          text-white
          transition-transform
          lg:translate-x-0
          ${open ? "translate-x-0" : "-translate-x-full"}
        `}
      >
        {/* ==================================================
            LOGO
        ================================================== */}

        <div className="flex h-20 items-center justify-between border-b border-white/10 px-6">
          <Link
            to={
              role === "admin"
                ? "/admin"
                : role === "operator"
                  ? "/operator"
                  : "/dashboard"
            }
            className="flex items-center gap-3 text-xl font-extrabold"
          >
            <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-400 text-[#071a2d]">
              <ParkingCircle size={23} />
            </span>
            SmartPark
            <span className="text-emerald-400">AI</span>
          </Link>

          <button
            type="button"
            className="lg:hidden"
            onClick={() => setOpen(false)}
          >
            <X />
          </button>
        </div>

        {/* ==================================================
            CURRENT PORTAL
        ================================================== */}

        <div className="p-5">
          <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <small className="uppercase tracking-widest text-slate-400">
              Current portal
            </small>

            <div className="mt-2 flex justify-between font-bold">
              <span className="capitalize">{role}</span>

              <ChevronDown size={16} />
            </div>
          </div>
        </div>

        {/* ==================================================
            NAVIGATION
        ================================================== */}

        <nav className="space-y-1 px-4">
          {items.map(([title, path, Icon]) => {
            const IconComponent = Icon as React.ElementType;

            const titleText = title as string;

            const pathText = path as string;

            // ==================================================
            // Reservations
            // ==================================================

            if (role === "driver" && titleText === "Reservations") {
              return (
                <div key={pathText}>
                  <button
                    type="button"
                    onClick={() => setReservationsOpen((current) => !current)}
                    className={`
                        flex
                        w-full
                        items-center
                        gap-3
                        rounded-xl
                        px-4
                        py-3
                        text-sm
                        font-semibold
                        transition
                        ${
                          isReservationsSection
                            ? "bg-emerald-400 text-[#071a2d]"
                            : "text-slate-300 hover:bg-white/10"
                        }
                      `}
                  >
                    <IconComponent size={18} />

                    <span className="flex-1 text-left">Reservations</span>

                    <ChevronDown
                      size={16}
                      className={`transition-transform ${
                        reservationsOpen ? "rotate-180" : ""
                      }`}
                    />
                  </button>

                  {reservationsOpen && (
                    <div className="ml-5 mt-1 space-y-1 border-l border-white/10 pl-3">
                      <Link
                        to="/reservations"
                        onClick={() => setOpen(false)}
                        className={`
                            flex items-center gap-2
                            rounded-lg px-3 py-2.5
                            text-sm font-medium transition
                            ${
                              location.pathname === "/reservations"
                                ? "bg-white/10 text-emerald-300"
                                : "text-slate-300 hover:bg-white/5 hover:text-white"
                            }
                          `}
                      >
                        <ParkingCircle size={15} />
                        My Reservations
                      </Link>

                      <Link
                        to="/reservations/create"
                        onClick={() => setOpen(false)}
                        className={`
                            flex items-center gap-2
                            rounded-lg px-3 py-2.5
                            text-sm font-medium transition
                            ${
                              location.pathname === "/reservations/create"
                                ? "bg-white/10 text-emerald-300"
                                : "text-slate-300 hover:bg-white/5 hover:text-white"
                            }
                          `}
                      >
                        <CalendarPlus size={15} />
                        Create Reservation
                      </Link>

                      <Link
                        to="/reservations/upcoming"
                        onClick={() => setOpen(false)}
                        className={`
                            flex items-center gap-2
                            rounded-lg px-3 py-2.5
                            text-sm font-medium transition
                            ${
                              location.pathname === "/reservations/upcoming"
                                ? "bg-white/10 text-emerald-300"
                                : "text-slate-300 hover:bg-white/5 hover:text-white"
                            }
                          `}
                      >
                        <CalendarPlus size={15} />
                        Upcoming
                      </Link>

                      <Link
                        to="/reservations/active"
                        onClick={() => setOpen(false)}
                        className={`
                            flex items-center gap-2
                            rounded-lg px-3 py-2.5
                            text-sm font-medium transition
                            ${
                              location.pathname === "/reservations/active"
                                ? "bg-white/10 text-emerald-300"
                                : "text-slate-300 hover:bg-white/5 hover:text-white"
                            }
                          `}
                      >
                        <ParkingCircle size={15} />
                        Active
                      </Link>

                      <Link
                        to="/reservations/history"
                        onClick={() => setOpen(false)}
                        className={`
                            flex items-center gap-2
                            rounded-lg px-3 py-2.5
                            text-sm font-medium transition
                            ${
                              location.pathname === "/reservations/history"
                                ? "bg-white/10 text-emerald-300"
                                : "text-slate-300 hover:bg-white/5 hover:text-white"
                            }
                          `}
                      >
                        <History size={15} />
                        History
                      </Link>
                    </div>
                  )}
                </div>
              );
            }

            // ==================================================
            // Vehicles
            // ==================================================

            if (role === "driver" && titleText === "Vehicles") {
              return (
                <div key={pathText}>
                  <button
                    type="button"
                    onClick={() => setVehiclesOpen((current) => !current)}
                    className={`
                        flex w-full items-center gap-3
                        rounded-xl px-4 py-3 text-sm
                        font-semibold transition
                        ${
                          isVehiclesSection
                            ? "bg-emerald-400 text-[#071a2d]"
                            : "text-slate-300 hover:bg-white/10"
                        }
                      `}
                  >
                    <IconComponent size={18} />

                    <span className="flex-1 text-left">Vehicles</span>

                    <ChevronDown
                      size={16}
                      className={`transition-transform ${
                        vehiclesOpen ? "rotate-180" : ""
                      }`}
                    />
                  </button>

                  {vehiclesOpen && (
                    <div className="ml-5 mt-1 space-y-1 border-l border-white/10 pl-3">
                      <Link
                        to="/vehicles"
                        onClick={() => setOpen(false)}
                        className={`
                            flex items-center gap-2
                            rounded-lg px-3 py-2.5
                            text-sm font-medium transition
                            ${
                              location.pathname === "/vehicles"
                                ? "bg-white/10 text-emerald-300"
                                : "text-slate-300 hover:bg-white/5 hover:text-white"
                            }
                          `}
                      >
                        <CarFront size={15} />
                        My Vehicles
                      </Link>

                      <Link
                        to="/vehicles/create"
                        onClick={() => setOpen(false)}
                        className={`
                            flex items-center gap-2
                            rounded-lg px-3 py-2.5
                            text-sm font-medium transition
                            ${
                              location.pathname === "/vehicles/create"
                                ? "bg-white/10 text-emerald-300"
                                : "text-slate-300 hover:bg-white/5 hover:text-white"
                            }
                          `}
                      >
                        <CalendarPlus size={15} />
                        Add Vehicle
                      </Link>
                    </div>
                  )}
                </div>
              );
            }

            // ==================================================
            // Payments & Wallet
            // ==================================================

            if (role === "driver" && titleText === "Payments & Wallet") {
              return (
                <div key={pathText}>
                  <button
                    type="button"
                    onClick={() => setPaymentsOpen((current) => !current)}
                    className={`
                        flex w-full items-center gap-3
                        rounded-xl px-4 py-3 text-sm
                        font-semibold transition
                        ${
                          isPaymentsSection
                            ? "bg-emerald-400 text-[#071a2d]"
                            : "text-slate-300 hover:bg-white/10"
                        }
                      `}
                  >
                    <IconComponent size={18} />

                    <span className="flex-1 text-left">Payments & Wallet</span>

                    <ChevronDown
                      size={16}
                      className={`transition-transform ${
                        paymentsOpen ? "rotate-180" : ""
                      }`}
                    />
                  </button>

                  {paymentsOpen && (
                    <div className="ml-5 mt-1 space-y-1 border-l border-white/10 pl-3">
                      <Link
                        to="/payments"
                        onClick={() => setOpen(false)}
                        className={`
                            flex items-center gap-2
                            rounded-lg px-3 py-2.5
                            text-sm font-medium transition
                            ${
                              location.pathname === "/payments"
                                ? "bg-white/10 text-emerald-300"
                                : "text-slate-300 hover:bg-white/5 hover:text-white"
                            }
                          `}
                      >
                        <CreditCard size={15} />
                        Payment History
                      </Link>

                      <Link
                        to="/payments/wallet"
                        onClick={() => setOpen(false)}
                        className={`
                            flex items-center gap-2
                            rounded-lg px-3 py-2.5
                            text-sm font-medium transition
                            ${
                              location.pathname === "/payments/wallet"
                                ? "bg-white/10 text-emerald-300"
                                : "text-slate-300 hover:bg-white/5 hover:text-white"
                            }
                          `}
                      >
                        <Wallet size={15} />
                        My Wallet
                      </Link>
                    </div>
                  )}
                </div>
              );
            }

            // ==================================================
            // Receipts
            // ==================================================

            if (role === "driver" && titleText === "Receipts") {
              return (
                <Link
                  key={pathText}
                  onClick={() => setOpen(false)}
                  className={`
                      flex items-center gap-3
                      rounded-xl px-4 py-3
                      text-sm font-semibold transition
                      ${
                        isReceiptsSection
                          ? "bg-emerald-400 text-[#071a2d]"
                          : "text-slate-300 hover:bg-white/10"
                      }
                    `}
                  to={pathText}
                >
                  <IconComponent size={18} />

                  {titleText}
                </Link>
              );
            }

            // ==================================================
            // Parking Sessions
            // ==================================================

            if (role === "driver" && titleText === "Parking Sessions") {
              return (
                <Link
                  key={pathText}
                  onClick={() => setOpen(false)}
                  className={`
                      flex items-center gap-3
                      rounded-xl px-4 py-3
                      text-sm font-semibold transition
                      ${
                        isSessionsSection
                          ? "bg-emerald-400 text-[#071a2d]"
                          : "text-slate-300 hover:bg-white/10"
                      }
                    `}
                  to={pathText}
                >
                  <IconComponent size={18} />

                  {titleText}
                </Link>
              );
            }

            // ==================================================
            // Standard Navigation
            // ==================================================

            return (
              <Link
                key={pathText}
                onClick={() => setOpen(false)}
                className={`
                    flex items-center gap-3
                    rounded-xl px-4 py-3
                    text-sm font-semibold
                    ${
                      location.pathname === pathText
                        ? "bg-emerald-400 text-[#071a2d]"
                        : "text-slate-300 hover:bg-white/10"
                    }
                  `}
                to={pathText}
              >
                <IconComponent size={18} />

                {titleText}
              </Link>
            );
          })}
        </nav>

        {/* ==================================================
            AI STATUS
        ================================================== */}

        <div className="absolute bottom-20 left-4 right-4 rounded-2xl border border-emerald-400/20 bg-emerald-400/10 p-4 text-sm">
          <div className="flex items-center gap-2 font-bold text-emerald-300">
            <Activity size={16} />
            AI Engine
          </div>

          <small className="mt-1 block text-slate-400">
            Production forecasting service.
          </small>
        </div>

        {/* ==================================================
            LOGOUT
        ================================================== */}

        <button
          type="button"
          onClick={handleLogout}
          className="absolute bottom-4 left-4 right-4 rounded-xl border border-white/10 px-4 py-2.5 text-sm font-semibold text-slate-300 hover:bg-white/10 hover:text-white"
        >
          Sign out
        </button>
      </aside>

      {/* ==================================================
          MAIN AREA
      ================================================== */}

      <div className="lg:pl-72">
        {/* ==================================================
            HEADER
        ================================================== */}

        <header className="sticky top-0 z-30 flex h-20 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-8">
          <div className="flex items-center gap-3">
            <button
              type="button"
              className="p-2 lg:hidden"
              onClick={() => setOpen(true)}
            >
              <Menu />
            </button>

            <div>
              <small className="font-bold uppercase tracking-widest text-emerald-600">
                SmartPark AI
              </small>

              <div className="font-bold capitalize">{role} Portal</div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* ==================================================
                FUNCTIONAL NOTIFICATION BELL
            ================================================== */}

            <button
              type="button"
              onClick={handleNotificationClick}
              aria-label={
                unreadCount > 0
                  ? `${unreadCount} unread notifications`
                  : "Notifications"
              }
              title={
                unreadCount > 0
                  ? `${unreadCount} unread notification${
                      unreadCount === 1 ? "" : "s"
                    }`
                  : "Notifications"
              }
              className={`
                relative
                rounded-xl
                border
                p-2.5
                transition
                ${
                  isNotificationsSection
                    ? "border-emerald-300 bg-emerald-50 text-emerald-600"
                    : "border-slate-200 text-slate-700 hover:bg-slate-50"
                }
              `}
            >
              {unreadCount > 0 ? <BellRing size={18} /> : <Bell size={18} />}

              {unreadCount > 0 && (
                <span
                  className="
                    absolute
                    -right-1.5
                    -top-1.5
                    flex
                    min-h-[18px]
                    min-w-[18px]
                    items-center
                    justify-center
                    rounded-full
                    bg-rose-500
                    px-1
                    text-[10px]
                    font-extrabold
                    leading-none
                    text-white
                    shadow-sm
                    ring-2
                    ring-white
                  "
                >
                  {unreadCount > 9 ? "9+" : unreadCount}
                </span>
              )}
            </button>

            {/* ==================================================
                USER MENU
            ================================================== */}

            <div ref={userMenuRef} className="relative hidden sm:block">
              <button
                type="button"
                onClick={() => setUserMenuOpen((current) => !current)}
                aria-expanded={userMenuOpen}
                aria-haspopup="menu"
                className="flex items-center gap-3 rounded-2xl px-2 py-1.5 text-left transition hover:bg-slate-50"
              >
                <span className="grid h-10 w-10 place-items-center rounded-full bg-slate-900 font-bold text-white">
                  {initials}
                </span>

                <div className="min-w-0">
                  <b className="block truncate text-sm">{fullName}</b>

                  <small className="block capitalize text-slate-500">
                    Driver
                  </small>
                </div>

                <ChevronDown
                  size={16}
                  className={`shrink-0 text-slate-500 transition-transform ${
                    userMenuOpen ? "rotate-180" : ""
                  }`}
                />
              </button>

              {userMenuOpen && (
                <div
                  role="menu"
                  className="absolute right-0 top-[calc(100%+10px)] z-50 w-56 overflow-hidden rounded-2xl border border-slate-200 bg-white p-2 shadow-xl"
                >
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setUserMenuOpen(false);
                      navigate("/profile");
                    }}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                  >
                    <User size={17} className="text-slate-500" />
                    Profile
                  </button>

                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setUserMenuOpen(false);
                      navigate("/settings");
                    }}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                  >
                    <Settings size={17} className="text-slate-500" />
                    Settings
                  </button>

                  <div className="my-1 border-t border-slate-100" />

                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => {
                      setUserMenuOpen(false);
                      void handleLogout();
                    }}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-sm font-semibold text-rose-600 transition hover:bg-rose-50"
                  >
                    <LogOut size={17} />
                    Sign Out
                  </button>
                </div>
              )}
            </div>
          </div>
        </header>

        {/* ==================================================
            PAGE CONTENT
        ================================================== */}

        <main className="p-4 sm:p-8">{children}</main>
      </div>
    </div>
  );
}
