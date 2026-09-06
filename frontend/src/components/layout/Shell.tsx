import { useCallback, useEffect, useState } from "react";
import type React from "react";

import { useLocation, useNavigate } from "react-router";

import { useAuth } from "../../auth/AuthContext";
import type { Role } from "../../auth/Role";
import { api } from "../../api";

import Sidebar from "./Sidebar";
import Header from "./Header";
import MobileNav from "./MobileNav";
import SmartParkChatbot from "../ai/SmartParkChatbot";

export default function Shell({
  role,
  children,
}: {
  role: Role;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);

  const location = useLocation();
  const navigate = useNavigate();

  const { logout } = useAuth();

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
  // Extract Notification Count
  // ======================================================

  const extractUnreadCount = (responseData: unknown): number => {
    /*
     * The API may return any of these common structures:
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

      // Preserve the last known value if the refresh fails.
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
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <Sidebar role={role} open={open} setOpen={setOpen} />

      <div className="lg:pl-[288px]">
        <Header
          role={role}
          open={open}
          setOpen={setOpen}
          unreadCount={unreadCount}
          onNotificationClick={handleNotificationClick}
          onLogout={handleLogout}
        />

        <main className="min-h-[calc(100vh-72px)] p-4 pb-24 sm:p-6 sm:pb-24 lg:p-8 lg:pb-8">
          <div className="mx-auto w-full max-w-[1600px]">{children}</div>
        </main>
      </div>

      <MobileNav role={role} />

      {/* ======================================================
          Global SmartPark AI Assistant
          Appears on every authenticated page.
          ====================================================== */}
      <SmartParkChatbot />
    </div>
  );
}
