import type React from "react";
import { Link, useLocation } from "react-router";
import {
  BrainCircuit,
  Building2,
  CarFront,
  CreditCard,
  Gift,
  LayoutDashboard,
  ParkingCircle,
  Search,
  Timer,
  Users,
} from "lucide-react";

import type { Role } from "../../auth/Role";

type MobileNavProps = {
  role: Role;
};

type MobileNavItem = {
  label: string;
  path: string;
  icon: React.ElementType;
};

export default function MobileNav({ role }: MobileNavProps) {
  const location = useLocation();

  const items: MobileNavItem[] =
    role === "driver"
      ? [
          {
            label: "Home",
            path: "/dashboard",
            icon: LayoutDashboard,
          },
          {
            label: "Parking",
            path: "/parking",
            icon: Search,
          },
          {
            label: "Bookings",
            path: "/reservations",
            icon: ParkingCircle,
          },
          {
            label: "Sessions",
            path: "/sessions",
            icon: Timer,
          },
          {
            label: "Wallet",
            path: "/payments/wallet",
            icon: CreditCard,
          },
        ]
      : role === "operator"
        ? [
            {
              label: "Dashboard",
              path: "/operator",
              icon: LayoutDashboard,
            },
            {
              label: "Reservations",
              path: "/operator/reservations",
              icon: ParkingCircle,
            },
            {
              label: "Check In/Out",
              path: "/operator/access",
              icon: CarFront,
            },
            {
              label: "Occupancy",
              path: "/operator/occupancy",
              icon: Building2,
            },
            {
              label: "Reports",
              path: "/operator/reports",
              icon: BrainCircuit,
            },
          ]
        : [
            {
              label: "Home",
              path: "/admin",
              icon: LayoutDashboard,
            },
            {
              label: "Users",
              path: "/admin",
              icon: Users,
            },
            {
              label: "Facilities",
              path: "/operator/facilities",
              icon: Building2,
            },
            {
              label: "Monitoring",
              path: "/forecast",
              icon: BrainCircuit,
            },
          ];

  const isItemActive = (path: string) => {
    if (path === "/dashboard" || path === "/operator" || path === "/admin") {
      return location.pathname === path;
    }

    if (path === "/parking") {
      return location.pathname === "/parking";
    }

    if (path === "/reservations") {
      return location.pathname.startsWith("/reservations");
    }

    if (path === "/sessions") {
      return location.pathname === "/sessions";
    }

    if (path === "/payments/wallet") {
      return location.pathname.startsWith("/payments");
    }

    if (path.startsWith("/operator/")) {
      return location.pathname.startsWith(path);
    }

    if (path === "/operator/facilities") {
      return location.pathname.startsWith("/operator/facilities");
    }

    if (path === "/forecast") {
      return location.pathname === "/forecast";
    }

    return location.pathname === path;
  };

  return (
    <nav
      aria-label="Mobile navigation"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-200/90 bg-white/95 px-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] pt-2 shadow-[0_-8px_30px_rgba(15,23,42,0.08)] backdrop-blur-xl lg:hidden"
    >
      <div className="mx-auto flex max-w-xl items-center justify-around gap-1">
        {items.map(({ label, path, icon: Icon }) => {
          const active = isItemActive(path);

          return (
            <Link
              key={`${label}-${path}`}
              to={path}
              aria-current={active ? "page" : undefined}
              className={[
                "group relative flex min-w-0 flex-1 flex-col items-center justify-center",
                "rounded-xl px-1 py-1.5 transition-all duration-200",
                active
                  ? "text-emerald-600"
                  : "text-slate-500 hover:bg-slate-50 hover:text-slate-800",
              ].join(" ")}
            >
              {active && (
                <span className="absolute -top-2 h-1 w-8 rounded-full bg-emerald-400" />
              )}

              <span
                className={[
                  "grid h-8 w-8 place-items-center rounded-xl transition-all duration-200",
                  active
                    ? "bg-emerald-50 text-emerald-600"
                    : "bg-transparent group-hover:bg-slate-100",
                ].join(" ")}
              >
                <Icon size={18} strokeWidth={active ? 2.4 : 2} />
              </span>

              <span
                className={[
                  "mt-0.5 max-w-full truncate text-[10px] font-bold",
                  active ? "text-emerald-700" : "text-slate-500",
                ].join(" ")}
              >
                {label}
              </span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
