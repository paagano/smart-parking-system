import { useEffect, useMemo, useState } from "react";
import type React from "react";
import { Link, useLocation, useNavigate } from "react-router";
import {
  Activity,
  AlertTriangle,
  BarChart3,
  BrainCircuit,
  Building2,
  CalendarPlus,
  ClipboardCheck,
  FileBarChart,
  FileWarning,
  MapPinned,
  ScanLine,
  SlidersHorizontal,
  UserRound,
  CarFront,
  ChevronDown,
  CreditCard,
  Gift,
  History,
  LayoutDashboard,
  ParkingCircle,
  QrCode,
  Radio,
  Search,
  ShieldAlert,
  Timer,
  TrendingUp,
  Wrench,
  Users,
  Wallet,
  X,
} from "lucide-react";

import { useAuth } from "../../auth/AuthContext";
import type { Role } from "../../auth/Role";

type SidebarProps = {
  role: Role;
  open: boolean;
  setOpen: React.Dispatch<React.SetStateAction<boolean>>;
};

type NavigationItem = [title: string, path: string, icon: React.ElementType];

export default function Sidebar({ role, open, setOpen }: SidebarProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const [reservationsOpen, setReservationsOpen] = useState(false);
  const [vehiclesOpen, setVehiclesOpen] = useState(false);
  const [paymentsOpen, setPaymentsOpen] = useState(false);

  const items = useMemo<NavigationItem[]>(() => {
    if (role === "driver") {
      return [
        ["Dashboard", "/dashboard", LayoutDashboard],
        ["Find Parking", "/parking", Search],
        ["Reservations", "/reservations", ParkingCircle],
        ["Parking Sessions", "/sessions", Timer],
        ["Payments & Wallet", "/payments", CreditCard],
        ["Receipts", "/receipts", History],
        ["Vehicles", "/vehicles", CarFront],
        ["AI Prediction", "/forecast", BrainCircuit],
        ["Loyalty Programme", "/loyalty", Gift],
      ];
    }

    if (role === "operator") {
      // Operator navigation is facility-focused.
      // Detailed operator modules are rendered in OperatorNavigationGroups below.
      // Driver navigation above remains unchanged.
      return [["Dashboard", "/operator", LayoutDashboard]];
    }

    return [
      ["Dashboard", "/admin", LayoutDashboard],
      ["Users", "/admin", Users],
      ["Facilities", "/operator/facilities", Building2],
      ["AI Monitoring", "/forecast", BrainCircuit],
    ];
  }, [role]);

  const isReservationsSection =
    role === "driver" && location.pathname.startsWith("/reservations");

  const isVehiclesSection =
    role === "driver" && location.pathname.startsWith("/vehicles");

  const isPaymentsSection =
    role === "driver" && location.pathname.startsWith("/payments");

  const isReceiptsSection =
    role === "driver" && location.pathname === "/receipts";

  const isSessionsSection =
    role === "driver" && location.pathname === "/sessions";

  useEffect(() => {
    if (isReservationsSection) {
      setReservationsOpen(true);
    }

    if (isVehiclesSection) {
      setVehiclesOpen(true);
    }

    if (isPaymentsSection) {
      setPaymentsOpen(true);
    }
  }, [isReservationsSection, isVehiclesSection, isPaymentsSection]);

  const portalLabel =
    role === "admin"
      ? "Administration"
      : role === "operator"
        ? "Operations"
        : "Driver";

  const portalDescription =
    role === "admin"
      ? "Manage the SmartPark platform."
      : role === "operator"
        ? "Manage facilities and operations."
        : "Find, reserve and manage parking.";

  const firstName = user?.first_name ?? "User";
  const initials = firstName.slice(0, 1).toUpperCase();

  const handleLogout = async () => {
    try {
      await logout();
    } finally {
      setOpen(false);
      navigate("/login", { replace: true });
    }
  };

  const closeSidebar = () => {
    setOpen(false);
  };

  const navItemClass = (active: boolean) =>
    [
      "group flex w-full items-center gap-3 rounded-xl px-3.5 py-3",
      "text-sm font-semibold transition-all duration-200",
      active
        ? "bg-emerald-400 text-[#071a2d] shadow-sm shadow-emerald-950/10"
        : "text-slate-300 hover:bg-white/[0.07] hover:text-white",
    ].join(" ");

  const nestedItemClass = (active: boolean) =>
    [
      "group flex items-center gap-2.5 rounded-lg px-3 py-2.5",
      "text-[13px] font-medium transition-all duration-200",
      active
        ? "bg-white/[0.10] text-emerald-300"
        : "text-slate-400 hover:bg-white/[0.06] hover:text-slate-100",
    ].join(" ");

  const isActive = (path: string) => location.pathname === path;

  const renderNestedLink = (
    to: string,
    label: string,
    Icon: React.ElementType,
  ) => (
    <Link
      to={to}
      onClick={closeSidebar}
      className={nestedItemClass(isActive(to))}
    >
      <Icon size={15} className="shrink-0" />
      <span>{label}</span>
    </Link>
  );

  return (
    <>
      {/* Mobile backdrop */}
      {open && (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-slate-950/50 backdrop-blur-[2px] lg:hidden"
          onClick={closeSidebar}
        />
      )}

      <aside
        aria-label="Main navigation"
        className={[
          "fixed inset-y-0 left-0 z-40 flex w-[288px] flex-col",
          "overflow-hidden border-r border-white/[0.06]",
          "bg-[#071a2d] text-white shadow-2xl shadow-slate-950/20",
          "transition-transform duration-300 ease-out",
          "lg:translate-x-0",
          open ? "translate-x-0" : "-translate-x-full",
        ].join(" ")}
      >
        {/* Brand */}
        <div className="shrink-0 border-b border-white/[0.08] px-5">
          <div className="flex h-[72px] items-center justify-between">
            <Link
              to={
                role === "admin"
                  ? "/admin"
                  : role === "operator"
                    ? "/operator"
                    : "/dashboard"
              }
              onClick={closeSidebar}
              className="flex items-center gap-3"
            >
              <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-emerald-400 text-[#071a2d] shadow-lg shadow-emerald-950/20">
                <ParkingCircle size={22} strokeWidth={2.4} />
              </span>

              <span className="leading-none">
                <span className="block text-[17px] font-extrabold tracking-tight text-white">
                  SmartPark <span className="text-emerald-400">AI</span>
                </span>
                <span className="mt-1 block text-[9px] font-bold uppercase tracking-[0.22em] text-slate-500">
                  Intelligent Parking
                </span>
              </span>
            </Link>

            <button
              type="button"
              aria-label="Close navigation"
              className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 transition hover:bg-white/[0.07] hover:text-white lg:hidden"
              onClick={closeSidebar}
            >
              <X size={19} />
            </button>
          </div>
        </div>

        {/* Portal context */}
        <div className="shrink-0 px-4 pt-4">
          <div className="rounded-2xl border border-white/[0.08] bg-white/[0.045] p-3.5">
            <div className="flex items-center gap-3">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-emerald-400/10 text-emerald-300">
                <Activity size={17} />
              </span>

              <div className="min-w-0">
                <p className="truncate text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
                  Current portal
                </p>
                <p className="mt-0.5 truncate text-sm font-bold text-white">
                  {portalLabel}
                </p>
              </div>
            </div>

            <p className="mt-2.5 pl-12 text-[11px] leading-4 text-slate-500">
              {portalDescription}
            </p>
          </div>
        </div>

        {/* Navigation */}
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 [scrollbar-width:thin] [scrollbar-color:rgba(148,163,184,0.25)_transparent]">
          <p className="mb-2 px-2 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-600">
            Workspace
          </p>

          <nav className="space-y-1" aria-label="Workspace">
            {items.map(([title, path, Icon]) => {
              if (role === "operator") {
                const operatorActive = location.pathname === path;

                return (
                  <Link
                    key={path}
                    to={path}
                    onClick={closeSidebar}
                    className={navItemClass(operatorActive)}
                  >
                    <Icon size={18} className="shrink-0" />
                    <span className="min-w-0 flex-1 truncate">{title}</span>
                  </Link>
                );
              }

              if (role === "driver" && title === "Reservations") {
                return (
                  <div key={path}>
                    <button
                      type="button"
                      aria-expanded={reservationsOpen}
                      onClick={() => setReservationsOpen((current) => !current)}
                      className={navItemClass(isReservationsSection)}
                    >
                      <Icon size={18} className="shrink-0" />
                      <span className="min-w-0 flex-1 truncate text-left">
                        Reservations
                      </span>
                      <ChevronDown
                        size={15}
                        className={[
                          "shrink-0 transition-transform duration-200",
                          reservationsOpen ? "rotate-180" : "",
                        ].join(" ")}
                      />
                    </button>

                    {reservationsOpen && (
                      <div className="ml-4 mt-1 space-y-0.5 border-l border-white/[0.10] pl-3">
                        {renderNestedLink(
                          "/reservations",
                          "My Reservations",
                          ParkingCircle,
                        )}
                        {renderNestedLink(
                          "/reservations/create",
                          "Create Reservation",
                          CalendarPlus,
                        )}
                        {renderNestedLink(
                          "/reservations/upcoming",
                          "Upcoming",
                          CalendarPlus,
                        )}
                        {renderNestedLink(
                          "/reservations/active",
                          "Active",
                          ParkingCircle,
                        )}
                        {renderNestedLink(
                          "/reservations/history",
                          "History",
                          History,
                        )}
                      </div>
                    )}
                  </div>
                );
              }

              if (role === "driver" && title === "Vehicles") {
                return (
                  <div key={path}>
                    <button
                      type="button"
                      aria-expanded={vehiclesOpen}
                      onClick={() => setVehiclesOpen((current) => !current)}
                      className={navItemClass(isVehiclesSection)}
                    >
                      <Icon size={18} className="shrink-0" />
                      <span className="min-w-0 flex-1 truncate text-left">
                        Vehicles
                      </span>
                      <ChevronDown
                        size={15}
                        className={[
                          "shrink-0 transition-transform duration-200",
                          vehiclesOpen ? "rotate-180" : "",
                        ].join(" ")}
                      />
                    </button>

                    {vehiclesOpen && (
                      <div className="ml-4 mt-1 space-y-0.5 border-l border-white/[0.10] pl-3">
                        {renderNestedLink("/vehicles", "My Vehicles", CarFront)}
                        {renderNestedLink(
                          "/vehicles/create",
                          "Add Vehicle",
                          CalendarPlus,
                        )}
                      </div>
                    )}
                  </div>
                );
              }

              if (role === "driver" && title === "Payments & Wallet") {
                return (
                  <div key={path}>
                    <button
                      type="button"
                      aria-expanded={paymentsOpen}
                      onClick={() => setPaymentsOpen((current) => !current)}
                      className={navItemClass(isPaymentsSection)}
                    >
                      <Icon size={18} className="shrink-0" />
                      <span className="min-w-0 flex-1 truncate text-left">
                        Payments &amp; Wallet
                      </span>
                      <ChevronDown
                        size={15}
                        className={[
                          "shrink-0 transition-transform duration-200",
                          paymentsOpen ? "rotate-180" : "",
                        ].join(" ")}
                      />
                    </button>

                    {paymentsOpen && (
                      <div className="ml-4 mt-1 space-y-0.5 border-l border-white/[0.10] pl-3">
                        {renderNestedLink(
                          "/payments",
                          "Payment History",
                          CreditCard,
                        )}
                        {renderNestedLink(
                          "/payments/wallet",
                          "My Wallet",
                          Wallet,
                        )}
                      </div>
                    )}
                  </div>
                );
              }

              const active =
                title === "Receipts"
                  ? isReceiptsSection
                  : title === "Parking Sessions"
                    ? isSessionsSection
                    : isActive(path);

              return (
                <Link
                  key={path}
                  to={path}
                  onClick={closeSidebar}
                  className={navItemClass(active)}
                >
                  <Icon size={18} className="shrink-0" />
                  <span className="min-w-0 flex-1 truncate">{title}</span>
                </Link>
              );
            })}
          </nav>

          {role === "operator" && (
            <OperatorNavigationGroups
              closeSidebar={closeSidebar}
              pathname={location.pathname}
            />
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 space-y-3 border-t border-white/[0.08] bg-[#061728] p-4">
          <div className="rounded-2xl border border-emerald-400/15 bg-emerald-400/[0.07] p-3.5">
            <div className="flex items-center gap-2.5">
              <span className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-emerald-400/10 text-emerald-300">
                <Activity size={15} />
                <span className="absolute right-0.5 top-0.5 h-1.5 w-1.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
              </span>

              <div className="min-w-0">
                <p className="text-xs font-bold text-emerald-300">AI Engine</p>
                <p className="mt-0.5 truncate text-[10px] text-slate-500">
                  Forecasting service is Online...
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 rounded-xl border border-white/[0.06] bg-white/[0.025] px-3 py-2.5">
            {user?.profile_picture_url ? (
              <img
                src={user.profile_picture_url}
                alt={`${firstName}'s profile`}
                className="h-8 w-8 shrink-0 rounded-full object-cover ring-1 ring-white/10"
              />
            ) : (
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-slate-700 text-xs font-bold text-white">
                {initials}
              </span>
            )}

            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-bold text-slate-200">
                {firstName}
              </p>
              <p className="truncate text-[10px] capitalize text-slate-500">
                {portalLabel}
              </p>
            </div>

            <button
              type="button"
              onClick={() => void handleLogout()}
              className="grid h-8 w-8 shrink-0 place-items-center rounded-lg text-slate-500 transition hover:bg-rose-500/10 hover:text-rose-300"
              aria-label="Sign out"
              title="Sign out"
            >
              <span className="text-sm font-bold">↗</span>
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}

function OperatorNavigationGroups({
  closeSidebar,
  pathname,
}: {
  closeSidebar: () => void;
  pathname: string;
}) {
  const groups = [
    {
      title: "Reservations",
      items: [
        ["Approve Reservations", "/operator/reservations", ClipboardCheck],
        ["Today's Arrivals", "/operator/reservations/arrivals", CalendarPlus],
        ["Reservation History", "/operator/reservations/history", History],
      ],
    },
    {
      title: "Check-In / Check-Out",
      items: [
        ["Manual Entry", "/operator/access/manual", UserRound],
        ["QR Code", "/operator/access/qr", QrCode],
        ["ANPR Simulator", "/operator/access/anpr", Radio],
        ["RFID Simulator", "/operator/access/rfid", Radio],
        ["Sensor / Scanner", "/operator/access/sensor", Activity],
        ["Mobile App Access", "/operator/access/mobile", CarFront],
      ],
    },
    {
      title: "Parking Operations",
      items: [
        ["Currently Parked Vehicles", "/operator/vehicles", CarFront],
        ["Release Parking Slot", "/operator/release-slots", Wrench],
        ["Vehicle Search", "/operator/vehicles/search", Search],
      ],
    },
    {
      title: "Occupancy",
      items: [
        ["Live Occupancy", "/operator/occupancy", BarChart3],
        ["Live Slot Map", "/operator/occupancy/map", MapPinned],
        ["Occupancy Statistics", "/operator/occupancy/statistics", TrendingUp],
        ["Facility Status", "/operator/facility-status", Building2],
      ],
    },
    {
      title: "Payments & Exceptions",
      items: [
        ["Payment Verification", "/operator/payments", CreditCard],
        ["Exceptions & Incidents", "/operator/exceptions", FileWarning],
      ],
    },
    {
      title: "Reports",
      items: [
        ["Daily Operations", "/operator/reports/daily", FileBarChart],
        ["Occupancy", "/operator/reports/occupancy", BarChart3],
        ["Vehicle Movements", "/operator/reports/vehicles", CarFront],
        ["Reservations", "/operator/reports/reservations", ClipboardCheck],
        ["Revenue", "/operator/reports/revenue", Wallet],
        ["Exceptions", "/operator/reports/exceptions", FileWarning],
      ],
    },
    {
      title: "Smart Insights",
      items: [
        ["Operational Alerts", "/operator/insights/alerts", AlertTriangle],
        ["Occupancy Trends", "/operator/insights/trends", TrendingUp],
        ["Peak Periods", "/operator/insights/peaks", BarChart3],
        ["Capacity Forecast", "/operator/insights/capacity", BrainCircuit],
        ["Anomalies", "/operator/insights/anomalies", ShieldAlert],
      ],
    },
  ] as const;

  const nestedItemClass = (active: boolean) =>
    [
      "group flex items-center gap-2.5 rounded-lg px-3 py-2.5",
      "text-[13px] font-medium transition-all duration-200",
      active
        ? "bg-white/[0.10] text-emerald-300"
        : "text-slate-400 hover:bg-white/[0.06] hover:text-slate-100",
    ].join(" ");

  return (
    <div className="mt-6 space-y-5 border-t border-white/[0.06] pt-5">
      {groups.map((group) => (
        <div key={group.title}>
          <p className="mb-1.5 px-2 text-[9px] font-bold uppercase tracking-[0.16em] text-slate-600">
            {group.title}
          </p>
          <div className="ml-1 space-y-0.5 border-l border-white/[0.08] pl-2">
            {group.items.map(([label, path, Icon]) => (
              <Link
                key={path}
                to={path}
                onClick={closeSidebar}
                className={nestedItemClass(
                  pathname === path || pathname.startsWith(`${path}/`),
                )}
              >
                <Icon size={14} className="shrink-0" />
                <span className="min-w-0 flex-1 truncate">{label}</span>
              </Link>
            ))}
          </div>
        </div>
      ))}

      <div>
        <p className="mb-1.5 px-2 text-[9px] font-bold uppercase tracking-[0.16em] text-slate-600">
          Account
        </p>
        <div className="ml-1 space-y-0.5 border-l border-white/[0.08] pl-2">
          <Link
            to="/operator/profile"
            onClick={closeSidebar}
            className={nestedItemClass(pathname === "/operator/profile")}
          >
            <UserRound size={14} className="shrink-0" />
            <span>My Profile</span>
          </Link>
          <Link
            to="/settings"
            onClick={closeSidebar}
            className={nestedItemClass(pathname === "/settings")}
          >
            <SlidersHorizontal size={14} className="shrink-0" />
            <span>Settings</span>
          </Link>
        </div>
      </div>
    </div>
  );
}

function GaugeIcon(props: React.ComponentProps<typeof ParkingCircle>) {
  return <ParkingCircle {...props} />;
}
