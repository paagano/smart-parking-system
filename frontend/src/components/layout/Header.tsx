import { useEffect, useRef, useState } from "react";
import type React from "react";
import { useLocation, useNavigate } from "react-router";
import {
  Bell,
  BellRing,
  ChevronDown,
  LogOut,
  Menu,
  Settings,
  User,
} from "lucide-react";

import { useAuth } from "../../auth/AuthContext";
import type { Role } from "../../auth/Role";

type HeaderProps = {
  role: Role;
  open: boolean;
  setOpen: React.Dispatch<React.SetStateAction<boolean>>;
  unreadCount: number;
  onNotificationClick: () => void;
  onLogout: () => Promise<void>;
};

export default function Header({
  role,
  open,
  setOpen,
  unreadCount,
  onNotificationClick,
  onLogout,
}: HeaderProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const userMenuRef = useRef<HTMLDivElement>(null);

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

  const fullName =
    [user?.first_name, user?.last_name].filter(Boolean).join(" ") || "User";

  const initials =
    `${user?.first_name?.[0] ?? ""}${user?.last_name?.[0] ?? ""}`.toUpperCase() ||
    "U";

  const portalLabel =
    role === "admin"
      ? "Administration"
      : role === "operator"
        ? "Operations"
        : "Driver";

  const pageTitle = usePageTitle(location.pathname);

  const handleMenuNavigation = (path: string) => {
    setUserMenuOpen(false);
    navigate(path);
  };

  const handleSignOut = () => {
    setUserMenuOpen(false);
    void onLogout();
  };

  return (
    <header className="sticky top-0 z-30 h-[72px] border-b border-slate-200/80 bg-white/90 shadow-sm shadow-slate-900/[0.03] backdrop-blur-xl">
      <div className="flex h-full items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Left side */}
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            aria-label="Open navigation"
            aria-expanded={open}
            className="grid h-10 w-10 shrink-0 place-items-center rounded-xl border border-slate-200 bg-white text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 lg:hidden"
            onClick={() => setOpen(true)}
          >
            <Menu size={19} />
          </button>

          <div className="min-w-0">
            <div className="hidden items-center gap-2 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-400 sm:flex">
              <span>SmartPark AI</span>
              <span className="text-slate-300">/</span>
              <span className="text-emerald-600">{portalLabel}</span>
            </div>

            <div className="mt-0.5 truncate text-base font-extrabold tracking-tight text-slate-900 sm:text-lg">
              {pageTitle}
            </div>
          </div>
        </div>

        {/* Right side */}
        <div className="flex shrink-0 items-center gap-2 sm:gap-3">
          {/* System status */}
          <div className="hidden items-center gap-2 rounded-xl border border-emerald-100 bg-emerald-50/70 px-3 py-2 md:flex">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-60" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-emerald-500" />
            </span>
            <span className="text-[11px] font-bold text-emerald-700">
              System Operational
            </span>
          </div>

          {/* Notifications */}
          <button
            type="button"
            onClick={onNotificationClick}
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
            className={[
              "relative grid h-10 w-10 place-items-center rounded-xl border",
              "transition-all duration-200",
              location.pathname === "/notifications"
                ? "border-emerald-200 bg-emerald-50 text-emerald-600"
                : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50 hover:text-slate-900",
            ].join(" ")}
          >
            {unreadCount > 0 ? <BellRing size={18} /> : <Bell size={18} />}

            {unreadCount > 0 && (
              <span className="absolute -right-1.5 -top-1.5 flex min-h-[18px] min-w-[18px] items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-extrabold leading-none text-white shadow-sm ring-2 ring-white">
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </button>

          {/* User menu */}
          <div ref={userMenuRef} className="relative">
            <button
              type="button"
              onClick={() => setUserMenuOpen((current) => !current)}
              aria-expanded={userMenuOpen}
              aria-haspopup="menu"
              className="flex items-center gap-2 rounded-2xl border border-transparent px-1.5 py-1.5 text-left transition hover:border-slate-200 hover:bg-slate-50 sm:gap-3 sm:px-2"
            >
              {user?.profile_picture_url ? (
                <img
                  src={user.profile_picture_url}
                  alt={`${fullName}'s profile`}
                  className="h-9 w-9 rounded-full object-cover ring-2 ring-white shadow-sm sm:h-10 sm:w-10"
                />
              ) : (
                <span className="grid h-9 w-9 place-items-center rounded-full bg-slate-900 text-xs font-extrabold text-white shadow-sm sm:h-10 sm:w-10">
                  {initials}
                </span>
              )}

              <div className="hidden min-w-0 sm:block">
                <p className="max-w-[150px] truncate text-sm font-bold text-slate-900">
                  {fullName}
                </p>
                <p className="mt-0.5 text-[11px] font-medium capitalize text-slate-500">
                  {role}
                </p>
              </div>

              <ChevronDown
                size={16}
                className={[
                  "hidden shrink-0 text-slate-400 transition-transform duration-200 sm:block",
                  userMenuOpen ? "rotate-180" : "",
                ].join(" ")}
              />
            </button>

            {userMenuOpen && (
              <div
                role="menu"
                aria-label="User menu"
                className="absolute right-0 top-[calc(100%+10px)] z-50 w-60 overflow-hidden rounded-2xl border border-slate-200 bg-white p-2 shadow-2xl shadow-slate-900/10"
              >
                <div className="border-b border-slate-100 px-3 py-3">
                  <div className="flex items-center gap-3">
                    {user?.profile_picture_url ? (
                      <img
                        src={user.profile_picture_url}
                        alt={`${fullName}'s profile`}
                        className="h-10 w-10 rounded-full object-cover"
                      />
                    ) : (
                      <span className="grid h-10 w-10 place-items-center rounded-full bg-slate-900 text-xs font-extrabold text-white">
                        {initials}
                      </span>
                    )}

                    <div className="min-w-0">
                      <p className="truncate text-sm font-bold text-slate-900">
                        {fullName}
                      </p>
                      <p className="mt-0.5 truncate text-xs capitalize text-slate-500">
                        {portalLabel} Portal
                      </p>
                    </div>
                  </div>
                </div>

                <div className="pt-1">
                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => handleMenuNavigation("/profile")}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                  >
                    <span className="grid h-8 w-8 place-items-center rounded-lg bg-slate-100 text-slate-500">
                      <User size={16} />
                    </span>
                    <span>Profile</span>
                  </button>

                  <button
                    type="button"
                    role="menuitem"
                    onClick={() => handleMenuNavigation("/settings")}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-slate-700 transition hover:bg-slate-50"
                  >
                    <span className="grid h-8 w-8 place-items-center rounded-lg bg-slate-100 text-slate-500">
                      <Settings size={16} />
                    </span>
                    <span>Settings</span>
                  </button>

                  <div className="my-1.5 border-t border-slate-100" />

                  <button
                    type="button"
                    role="menuitem"
                    onClick={handleSignOut}
                    className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-semibold text-rose-600 transition hover:bg-rose-50"
                  >
                    <span className="grid h-8 w-8 place-items-center rounded-lg bg-rose-50 text-rose-500">
                      <LogOut size={16} />
                    </span>
                    <span>Sign Out</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

function usePageTitle(pathname: string): string {
  return getPageTitle(pathname);
}

function getPageTitle(pathname: string): string {
  const titles: Array<[string, string]> = [
    ["/dashboard", "Dashboard"],
    ["/parking", "Find Parking"],
    ["/reservations/create", "Create Reservation"],
    ["/reservations/upcoming", "Upcoming Reservations"],
    ["/reservations/active", "Active Reservation"],
    ["/reservations/history", "Reservation History"],
    ["/reservations", "My Reservations"],
    ["/sessions", "Parking Sessions"],
    ["/payments/wallet", "My Wallet"],
    ["/payments", "Payment History"],
    ["/receipts", "Receipts"],
    ["/vehicles/create", "Add Vehicle"],
    ["/vehicles", "My Vehicles"],
    ["/forecast", "AI Forecasting"],
    ["/loyalty", "Loyalty Programme"],
    ["/operator/reservations/arrivals", "Today's Arrivals"],
    ["/operator/reservations/history", "Reservation History"],
    ["/operator/reservations", "Approve Reservations"],
    ["/operator/access/manual", "Manual Entry"],
    ["/operator/access/qr", "QR Code"],
    ["/operator/access/anpr", "ANPR Simulator"],
    ["/operator/access/rfid", "RFID Simulator"],
    ["/operator/access/sensor", "Sensor / Scanner"],
    ["/operator/access/mobile", "Mobile App Access"],
    ["/operator/access", "Check-In / Check-Out"],
    ["/operator/release-slots", "Release Parking Slot"],
    ["/operator/vehicles/search", "Vehicle Search"],
    ["/operator/vehicles", "Currently Parked Vehicles"],
    ["/operator/occupancy/map", "Live Slot Map"],
    ["/operator/occupancy/statistics", "Occupancy Statistics"],
    ["/operator/occupancy", "Live Occupancy"],
    ["/operator/facility-status", "Facility Status"],
    ["/operator/payments", "Payment Verification"],
    ["/operator/exceptions", "Exceptions & Incidents"],
    ["/operator/reports/daily", "Daily Operations Report"],
    ["/operator/reports/occupancy", "Occupancy Report"],
    ["/operator/reports/vehicles", "Vehicle Movements Report"],
    ["/operator/reports/reservations", "Reservations Report"],
    ["/operator/reports/revenue", "Revenue Report"],
    ["/operator/reports/exceptions", "Exceptions Report"],
    ["/operator/reports", "Reports"],
    ["/operator/insights/alerts", "Operational Alerts"],
    ["/operator/insights/trends", "Occupancy Trends"],
    ["/operator/insights/peaks", "Peak Periods"],
    ["/operator/insights/capacity", "Capacity Forecast"],
    ["/operator/insights/anomalies", "Anomalies"],
    ["/operator/profile", "My Profile"],
    ["/operator/facilities", "Facilities"],
    ["/operator", "Operator Dashboard"],
    ["/admin/users", "User Management"],
    ["/admin", "Administration Dashboard"],
    ["/notifications", "Notifications"],
    ["/profile", "Profile"],
    ["/settings", "Settings"],
  ];

  const exactMatch = titles.find(([path]) => pathname === path);
  if (exactMatch) {
    return exactMatch[1];
  }

  if (pathname.startsWith("/reservations/")) {
    return "Reservations";
  }

  if (pathname.startsWith("/vehicles/")) {
    return "Vehicles";
  }

  if (pathname.startsWith("/payments/")) {
    return "Payments & Wallet";
  }

  if (pathname.startsWith("/operator/")) {
    return "Operations";
  }

  if (pathname.startsWith("/admin/")) {
    return "Administration";
  }

  return "Smart Parking";
}
