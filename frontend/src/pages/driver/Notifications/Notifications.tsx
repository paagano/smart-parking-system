import { useCallback, useEffect, useMemo, useState } from "react";
import type React from "react";

import {
  AlertCircle,
  Bell,
  BellRing,
  Check,
  CheckCheck,
  ChevronRight,
  Info,
  RefreshCw,
  ShieldCheck,
  Trash2,
  X,
} from "lucide-react";

import { api } from "../../../api";

// ==========================================================
// Types
// ==========================================================

interface NotificationItem {
  id: number | string;

  title?: string | null;
  message?: string | null;
  body?: string | null;
  content?: string | null;

  notification_type?: string | null;
  type?: string | null;

  channel?: string | null;

  is_read?: boolean;
  read?: boolean;
  read_at?: string | null;

  created_at?: string | null;
  updated_at?: string | null;

  reference_type?: string | null;
  reference_id?: number | string | null;

  data?: Record<string, any> | null;

  [key: string]: any;
}

type FilterType = "ALL" | "UNREAD" | "READ";

type NotificationTone = "success" | "warning" | "error" | "info" | "default";

// ==========================================================
// Helpers
// ==========================================================

function unwrap<T = any>(response: any): T {
  return response?.data ?? response;
}

// ----------------------------------------------------------
// Extract notification array
// ----------------------------------------------------------

function extractList<T>(value: any): T[] {
  const data = unwrap<any>(value);

  if (Array.isArray(data)) {
    return data;
  }

  if (Array.isArray(data?.items)) {
    return data.items;
  }

  if (Array.isArray(data?.notifications)) {
    return data.notifications;
  }

  if (Array.isArray(data?.results)) {
    return data.results;
  }

  if (Array.isArray(data?.data)) {
    return data.data;
  }

  return [];
}

// ----------------------------------------------------------
// Extract numeric count
// ----------------------------------------------------------

function extractCount(value: any): number {
  const data = unwrap<any>(value);

  if (typeof data === "number") {
    return data;
  }

  if (typeof data === "string") {
    const parsed = Number(data);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  if (!data || typeof data !== "object") {
    return 0;
  }

  const candidates = [
    data.count,
    data.unread_count,
    data.unreadCount,
    data.total,
    data.value,
  ];

  for (const candidate of candidates) {
    if (typeof candidate === "number" && Number.isFinite(candidate)) {
      return candidate;
    }

    if (typeof candidate === "string") {
      const parsed = Number(candidate);

      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
  }

  // Handle nested data
  if (data.data !== null && data.data !== undefined) {
    return extractCount(data.data);
  }

  return 0;
}

// ----------------------------------------------------------
// Notification read state
// ----------------------------------------------------------

function isNotificationRead(notification: NotificationItem): boolean {
  /*
   * Important:
   *
   * Do not use:
   *
   * Boolean(notification.is_read ?? notification.read ?? ...)
   *
   * because `false` is a valid value and must remain false.
   */

  if (typeof notification.is_read === "boolean") {
    return notification.is_read;
  }

  if (typeof notification.read === "boolean") {
    return notification.read;
  }

  if (notification.read_at !== undefined && notification.read_at !== null) {
    return true;
  }

  return false;
}

// ----------------------------------------------------------
// Notification title
// ----------------------------------------------------------

function notificationTitle(notification: NotificationItem): string {
  return (
    notification.title ??
    notification.data?.title ??
    formatLabel(
      notification.notification_type ?? notification.type ?? "Notification",
    )
  );
}

// ----------------------------------------------------------
// Notification message
// ----------------------------------------------------------

function notificationMessage(notification: NotificationItem): string {
  return (
    notification.message ??
    notification.body ??
    notification.content ??
    notification.data?.message ??
    notification.data?.body ??
    "You have a new SmartPark notification."
  );
}

// ----------------------------------------------------------
// Notification type
// ----------------------------------------------------------

function notificationType(notification: NotificationItem): string {
  return notification.notification_type ?? notification.type ?? "GENERAL";
}

// ----------------------------------------------------------
// Format labels
// ----------------------------------------------------------

function formatLabel(value?: string | null): string {
  if (!value) {
    return "Notification";
  }

  return value
    .replace(/[_-]/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

// ----------------------------------------------------------
// Date formatting
// ----------------------------------------------------------

function formatDate(value?: string | null): string {
  if (!value) {
    return "—";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("en-KE", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// ----------------------------------------------------------
// Relative time
// ----------------------------------------------------------

function relativeTime(value?: string | null): string {
  if (!value) {
    return "";
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const difference = Date.now() - date.getTime();

  const minutes = Math.floor(difference / 60000);

  if (minutes < 1) {
    return "Just now";
  }

  if (minutes < 60) {
    return `${minutes}m ago`;
  }

  const hours = Math.floor(minutes / 60);

  if (hours < 24) {
    return `${hours}h ago`;
  }

  const days = Math.floor(hours / 24);

  if (days < 7) {
    return `${days}d ago`;
  }

  return formatDate(value);
}

// ----------------------------------------------------------
// Notification tone
// ----------------------------------------------------------

function getTone(notification: NotificationItem): NotificationTone {
  const type = notificationType(notification).toUpperCase();

  if (
    type.includes("SUCCESS") ||
    type.includes("COMPLETED") ||
    type.includes("PAYMENT_SUCCESS")
  ) {
    return "success";
  }

  if (
    type.includes("WARNING") ||
    type.includes("PENDING") ||
    type.includes("EXPIR")
  ) {
    return "warning";
  }

  if (
    type.includes("ERROR") ||
    type.includes("FAILED") ||
    type.includes("CANCEL")
  ) {
    return "error";
  }

  if (
    type.includes("INFO") ||
    type.includes("REMINDER") ||
    type.includes("SYSTEM")
  ) {
    return "info";
  }

  return "default";
}

// ----------------------------------------------------------
// Tone classes
// ----------------------------------------------------------

function toneClasses(tone: NotificationTone) {
  switch (tone) {
    case "success":
      return {
        icon: "bg-emerald-50 text-emerald-600",
        badge: "bg-emerald-50 text-emerald-700",
      };

    case "warning":
      return {
        icon: "bg-amber-50 text-amber-600",
        badge: "bg-amber-50 text-amber-700",
      };

    case "error":
      return {
        icon: "bg-rose-50 text-rose-600",
        badge: "bg-rose-50 text-rose-700",
      };

    case "info":
      return {
        icon: "bg-blue-50 text-blue-600",
        badge: "bg-blue-50 text-blue-700",
      };

    default:
      return {
        icon: "bg-slate-100 text-slate-600",
        badge: "bg-slate-100 text-slate-600",
      };
  }
}

// ----------------------------------------------------------
// Notification icon
// ----------------------------------------------------------

function notificationIcon(tone: NotificationTone) {
  switch (tone) {
    case "success":
      return <CheckCheck size={18} />;

    case "warning":
      return <AlertCircle size={18} />;

    case "error":
      return <AlertCircle size={18} />;

    case "info":
      return <Info size={18} />;

    default:
      return <Bell size={18} />;
  }
}

// ----------------------------------------------------------
// API error
// ----------------------------------------------------------

function getErrorMessage(error: any): string {
  const detail = error?.response?.data?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail)) {
    return detail.map((item) => item?.msg ?? String(item)).join(", ");
  }

  return (
    error?.response?.data?.message ??
    error?.message ??
    "Unable to complete the notification request."
  );
}

// ==========================================================
// Component
// ==========================================================

export default function Notifications() {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);

  /*
   * GLOBAL unread count.
   *
   * This comes from /notifications/unread/count
   * and is primarily used for the header bell.
   *
   * IMPORTANT:
   * Do NOT use this to calculate the READ count
   * for the currently loaded notification page.
   */
  const [unreadCount, setUnreadCount] = useState(0);

  const [loading, setLoading] = useState(true);

  const [refreshing, setRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [filter, setFilter] = useState<FilterType>("ALL");

  const [selectedNotification, setSelectedNotification] =
    useState<NotificationItem | null>(null);

  const [processingId, setProcessingId] = useState<number | string | null>(
    null,
  );

  const [markingAllRead, setMarkingAllRead] = useState(false);

  // ========================================================
  // DERIVED COUNTS
  // ========================================================

  /*
   * These counts describe the notifications that are
   * ACTUALLY LOADED into this page.
   *
   * This is deliberately separate from unreadCount.
   */

  const pageUnreadCount = useMemo(
    () =>
      notifications.filter((notification) => !isNotificationRead(notification))
        .length,
    [notifications],
  );

  const pageReadCount = useMemo(
    () =>
      notifications.filter((notification) => isNotificationRead(notification))
        .length,
    [notifications],
  );

  const pageTotalCount = notifications.length;

  // ========================================================
  // Load notifications
  // ========================================================

  const loadNotifications = useCallback(async (manualRefresh = false) => {
    if (manualRefresh) {
      setRefreshing(true);
    } else {
      setLoading(true);
    }

    setError(null);

    try {
      /*
       * Fetch:
       *
       * 1. Complete notification collection
       * 2. Unread collection
       * 3. Global unread count
       *
       * The three responses have different purposes.
       */

      const [notificationsResponse, unreadResponse, unreadCountResponse] =
        await Promise.all([
          api.get("/notifications"),
          api.get("/notifications/unread"),
          api.get("/notifications/unread/count"),
        ]);

      // ------------------------------------------------
      // Main notification collection
      // ------------------------------------------------

      const allNotifications = extractList<NotificationItem>(
        notificationsResponse.data,
      );

      // ------------------------------------------------
      // Unread notification collection
      // ------------------------------------------------

      const unreadNotifications = extractList<NotificationItem>(
        unreadResponse.data,
      );

      // ------------------------------------------------
      // GLOBAL unread count
      // ------------------------------------------------

      const backendUnreadCount = Math.max(
        0,
        Math.floor(extractCount(unreadCountResponse.data)),
      );

      /*
       * Build a Set of IDs returned by the
       * /notifications/unread endpoint.
       */

      const unreadIds = new Set(
        unreadNotifications.map((item) => String(item.id)),
      );

      // ------------------------------------------------
      // Normalize read status
      // ------------------------------------------------

      const normalized = allNotifications.map((item) => {
        /*
         * If the main endpoint explicitly provides
         * is_read/read/read_at, trust it.
         *
         * Otherwise use the unread endpoint.
         */

        const hasExplicitReadState =
          typeof item.is_read === "boolean" ||
          typeof item.read === "boolean" ||
          item.read_at !== undefined;

        return {
          ...item,

          is_read: hasExplicitReadState
            ? isNotificationRead(item)
            : !unreadIds.has(String(item.id)),
        };
      });

      // ------------------------------------------------
      // Most recent first
      // ------------------------------------------------

      normalized.sort((a, b) => {
        const first = a.created_at ? new Date(a.created_at).getTime() : 0;

        const second = b.created_at ? new Date(b.created_at).getTime() : 0;

        return second - first;
      });

      // ------------------------------------------------
      // Update state
      // ------------------------------------------------

      setNotifications(normalized);

      /*
       * IMPORTANT:
       *
       * This remains the GLOBAL backend count.
       * It is NOT used for pageReadCount.
       */
      setUnreadCount(backendUnreadCount);
    } catch (err: any) {
      console.error(
        "[SmartPark Notifications] Failed to load notifications:",
        err,
      );

      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  // ========================================================
  // Initial load
  // ========================================================

  useEffect(() => {
    void loadNotifications();
  }, [loadNotifications]);

  // ========================================================
  // Filter
  // ========================================================

  const filteredNotifications = useMemo(() => {
    if (filter === "UNREAD") {
      return notifications.filter(
        (notification) => !isNotificationRead(notification),
      );
    }

    if (filter === "READ") {
      return notifications.filter((notification) =>
        isNotificationRead(notification),
      );
    }

    return notifications;
  }, [filter, notifications]);

  // ========================================================
  // Mark notification as read
  // ========================================================

  async function markAsRead(notification: NotificationItem) {
    if (isNotificationRead(notification)) {
      setSelectedNotification(notification);
      return;
    }

    setProcessingId(notification.id);

    try {
      await api.patch(`/notifications/${notification.id}/read`);

      const now = new Date().toISOString();

      /*
       * Update the local notification immediately.
       */

      setNotifications((current) =>
        current.map((item) =>
          String(item.id) === String(notification.id)
            ? {
                ...item,
                is_read: true,
                read: true,
                read_at: item.read_at ?? now,
              }
            : item,
        ),
      );

      /*
       * Update the global bell count.
       */

      setUnreadCount((current) => Math.max(0, current - 1));

      /*
       * Update modal state too.
       */

      setSelectedNotification({
        ...notification,
        is_read: true,
        read: true,
        read_at: notification.read_at ?? now,
      });
    } catch (err: any) {
      console.error(
        "[SmartPark Notifications] Failed to mark notification as read:",
        err,
      );

      setError(getErrorMessage(err));
    } finally {
      setProcessingId(null);
    }
  }

  // ========================================================
  // Mark all as read
  // ========================================================

  async function markAllAsRead() {
    if (pageUnreadCount === 0) {
      return;
    }

    setMarkingAllRead(true);
    setError(null);

    try {
      await api.patch("/notifications/read-all");

      const now = new Date().toISOString();

      /*
       * Mark every currently loaded notification
       * as read.
       */

      setNotifications((current) =>
        current.map((notification) => ({
          ...notification,
          is_read: true,
          read: true,
          read_at: notification.read_at ?? now,
        })),
      );

      /*
       * The exact backend global count may include
       * notifications outside the current page.
       *
       * Since read-all has succeeded, set the global
       * unread count to zero.
       */

      setUnreadCount(0);
    } catch (err: any) {
      console.error(
        "[SmartPark Notifications] Failed to mark all notifications as read:",
        err,
      );

      setError(getErrorMessage(err));
    } finally {
      setMarkingAllRead(false);
    }
  }

  // ========================================================
  // Delete notification
  // ========================================================

  async function deleteNotification(notification: NotificationItem) {
    setProcessingId(notification.id);

    setError(null);

    try {
      await api.delete(`/notifications/${notification.id}`);

      const wasUnread = !isNotificationRead(notification);

      setNotifications((current) =>
        current.filter((item) => String(item.id) !== String(notification.id)),
      );

      /*
       * Only decrement global unread count when
       * the deleted notification was unread.
       */

      if (wasUnread) {
        setUnreadCount((current) => Math.max(0, current - 1));
      }

      if (
        selectedNotification &&
        String(selectedNotification.id) === String(notification.id)
      ) {
        setSelectedNotification(null);
      }
    } catch (err: any) {
      console.error(
        "[SmartPark Notifications] Failed to delete notification:",
        err,
      );

      setError(getErrorMessage(err));
    } finally {
      setProcessingId(null);
    }
  }

  // ========================================================
  // Loading state
  // ========================================================

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="h-8 w-64 animate-pulse rounded bg-slate-200" />

            <div className="mt-2 h-4 w-96 animate-pulse rounded bg-slate-200" />
          </div>

          <div className="h-10 w-24 animate-pulse rounded-xl bg-slate-200" />
        </div>

        <div className="grid gap-5 md:grid-cols-3">
          {[1, 2, 3].map((item) => (
            <div
              key={item}
              className="h-32 animate-pulse rounded-2xl border border-slate-200 bg-white"
            />
          ))}
        </div>

        <div className="h-96 animate-pulse rounded-2xl border border-slate-200 bg-white" />
      </div>
    );
  }

  // ========================================================
  // Render
  // ========================================================

  return (
    <div className="space-y-6">
      {/* ====================================================
          HEADER
      ==================================================== */}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div
            className={`grid h-12 w-12 place-items-center rounded-2xl ${
              unreadCount > 0
                ? "bg-emerald-50 text-emerald-600"
                : "bg-slate-100 text-slate-600"
            }`}
          >
            {unreadCount > 0 ? <BellRing size={24} /> : <Bell size={24} />}
          </div>

          <div>
            <h1 className="text-2xl font-extrabold tracking-tight text-slate-900">
              Notifications
            </h1>

            <p className="mt-1 text-sm text-slate-500">
              Stay up to date with your SmartPark activity.
            </p>
          </div>
        </div>

        <div className="flex gap-2">
          {pageUnreadCount > 0 && (
            <button
              type="button"
              onClick={() => void markAllAsRead()}
              disabled={markingAllRead}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {markingAllRead ? (
                <RefreshCw size={16} className="animate-spin" />
              ) : (
                <CheckCheck size={16} />
              )}
              Mark all as read
            </button>
          )}

          <button
            type="button"
            onClick={() => void loadNotifications(true)}
            disabled={refreshing}
            className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw size={16} className={refreshing ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {/* ====================================================
          ERROR
      ==================================================== */}

      {error && (
        <div className="flex items-start gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          <AlertCircle size={18} className="mt-0.5 shrink-0" />

          <div className="flex-1">
            <p className="font-bold">Notification request failed</p>

            <p className="mt-1">{error}</p>
          </div>

          <button
            type="button"
            onClick={() => setError(null)}
            className="rounded-lg p-1 hover:bg-rose-100"
          >
            <X size={16} />
          </button>
        </div>
      )}

      {/* ====================================================
          SUMMARY
      ==================================================== */}

      <div className="grid gap-5 md:grid-cols-3">
        <SummaryCard
          label="Total Notifications"
          value={pageTotalCount}
          helper="Notifications shown"
          icon={<Bell size={22} />}
          iconClass="bg-blue-50 text-blue-600"
        />

        <SummaryCard
          label="Unread"
          value={pageUnreadCount}
          helper="Require your attention"
          icon={<BellRing size={22} />}
          iconClass="bg-emerald-50 text-emerald-600"
        />

        <SummaryCard
          label="Read"
          value={pageReadCount}
          helper="Already reviewed"
          icon={<CheckCheck size={22} />}
          iconClass="bg-slate-100 text-slate-600"
        />
      </div>

      {/* ====================================================
          FILTERS
      ==================================================== */}

      <div className="rounded-2xl border border-slate-200 bg-white p-2 shadow-sm">
        <div className="flex flex-wrap gap-1">
          <FilterButton
            active={filter === "ALL"}
            onClick={() => setFilter("ALL")}
            label={`All (${pageTotalCount})`}
          />

          <FilterButton
            active={filter === "UNREAD"}
            onClick={() => setFilter("UNREAD")}
            label={`Unread (${pageUnreadCount})`}
          />

          <FilterButton
            active={filter === "READ"}
            onClick={() => setFilter("READ")}
            label={`Read (${pageReadCount})`}
          />
        </div>
      </div>

      {/* ====================================================
          NOTIFICATION LIST
      ==================================================== */}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-6 py-5">
          <div>
            <h2 className="text-lg font-extrabold text-slate-900">
              Notification Centre
            </h2>

            <p className="mt-1 text-sm text-slate-500">
              {filteredNotifications.length} notification
              {filteredNotifications.length === 1 ? "" : "s"} shown
            </p>
          </div>

          <div className="hidden items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-xs font-bold text-emerald-700 sm:flex">
            <ShieldCheck size={14} />
            Secure notifications
          </div>
        </div>

        {filteredNotifications.length === 0 ? (
          <div className="p-12 text-center">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-slate-100 text-slate-400">
              <Bell size={30} />
            </div>

            <h3 className="mt-4 font-extrabold text-slate-800">
              {filter === "UNREAD"
                ? "You're all caught up"
                : filter === "READ"
                  ? "No read notifications"
                  : "No notifications yet"}
            </h3>

            <p className="mx-auto mt-2 max-w-md text-sm text-slate-500">
              {filter === "UNREAD"
                ? "There are no unread notifications requiring your attention."
                : "SmartPark notifications will appear here when there is activity on your account."}
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {filteredNotifications.map((notification) => {
              const read = isNotificationRead(notification);

              const tone = getTone(notification);

              const classes = toneClasses(tone);

              const busy = String(processingId) === String(notification.id);

              return (
                <div
                  key={notification.id}
                  className={`group flex items-start gap-4 p-5 transition ${
                    read
                      ? "bg-white hover:bg-slate-50"
                      : "bg-emerald-50/30 hover:bg-emerald-50/60"
                  }`}
                >
                  {/* Icon */}

                  <div
                    className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl ${classes.icon}`}
                  >
                    {notificationIcon(tone)}
                  </div>

                  {/* Content */}

                  <button
                    type="button"
                    onClick={() => void markAsRead(notification)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex min-w-0 items-center gap-2">
                        {!read && (
                          <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
                        )}

                        <h3
                          className={`truncate text-sm ${
                            read
                              ? "font-semibold text-slate-800"
                              : "font-extrabold text-slate-900"
                          }`}
                        >
                          {notificationTitle(notification)}
                        </h3>
                      </div>

                      <span className="shrink-0 text-xs text-slate-400">
                        {relativeTime(notification.created_at)}
                      </span>
                    </div>

                    <p
                      className={`mt-1 line-clamp-2 text-sm ${
                        read ? "text-slate-500" : "font-medium text-slate-600"
                      }`}
                    >
                      {notificationMessage(notification)}
                    </p>

                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span
                        className={`rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${classes.badge}`}
                      >
                        {formatLabel(notificationType(notification))}
                      </span>

                      {notification.channel && (
                        <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-slate-500">
                          {formatLabel(notification.channel)}
                        </span>
                      )}

                      <span className="text-xs text-slate-400">
                        {formatDate(notification.created_at)}
                      </span>
                    </div>
                  </button>

                  {/* Actions */}

                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      title="View notification"
                      onClick={() => setSelectedNotification(notification)}
                      className="grid h-9 w-9 place-items-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                    >
                      <ChevronRight size={18} />
                    </button>

                    <button
                      type="button"
                      title={read ? "Already read" : "Mark as read"}
                      disabled={read || busy}
                      onClick={() => void markAsRead(notification)}
                      className="hidden h-9 w-9 place-items-center rounded-lg text-slate-400 hover:bg-emerald-50 hover:text-emerald-600 disabled:cursor-not-allowed disabled:opacity-40 sm:grid"
                    >
                      {busy ? (
                        <RefreshCw size={16} className="animate-spin" />
                      ) : (
                        <Check size={17} />
                      )}
                    </button>

                    <button
                      type="button"
                      title="Delete notification"
                      disabled={busy}
                      onClick={() => void deleteNotification(notification)}
                      className="hidden h-9 w-9 place-items-center rounded-lg text-slate-400 hover:bg-rose-50 hover:text-rose-600 disabled:cursor-not-allowed disabled:opacity-40 sm:grid"
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ====================================================
          NOTIFICATION DETAILS MODAL
      ==================================================== */}

      {selectedNotification && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 p-4 backdrop-blur-sm"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) {
              setSelectedNotification(null);
            }
          }}
        >
          <div className="w-full max-w-lg overflow-hidden rounded-2xl bg-white shadow-2xl">
            {/* Modal Header */}

            <div className="flex items-start justify-between border-b border-slate-100 px-6 py-5">
              <div className="flex items-center gap-3">
                <div
                  className={`grid h-10 w-10 place-items-center rounded-xl ${
                    toneClasses(getTone(selectedNotification)).icon
                  }`}
                >
                  {notificationIcon(getTone(selectedNotification))}
                </div>

                <div>
                  <p className="text-xs font-bold uppercase tracking-widest text-emerald-600">
                    Notification
                  </p>

                  <h2 className="mt-1 text-lg font-extrabold text-slate-900">
                    {notificationTitle(selectedNotification)}
                  </h2>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setSelectedNotification(null)}
                className="grid h-9 w-9 place-items-center rounded-xl border border-slate-200 text-slate-500 hover:bg-slate-50"
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}

            <div className="p-6">
              <div className="rounded-2xl bg-slate-50 p-5">
                <p className="whitespace-pre-wrap text-sm leading-6 text-slate-700">
                  {notificationMessage(selectedNotification)}
                </p>
              </div>

              <div className="mt-5 overflow-hidden rounded-xl border border-slate-200">
                <DetailRow
                  label="Type"
                  value={formatLabel(notificationType(selectedNotification))}
                />

                <DetailRow
                  label="Channel"
                  value={
                    selectedNotification.channel
                      ? formatLabel(selectedNotification.channel)
                      : "—"
                  }
                />

                <DetailRow
                  label="Status"
                  value={
                    isNotificationRead(selectedNotification) ? "Read" : "Unread"
                  }
                />

                <DetailRow
                  label="Received"
                  value={formatDate(selectedNotification.created_at)}
                />

                {selectedNotification.reference_type && (
                  <DetailRow
                    label="Reference Type"
                    value={formatLabel(selectedNotification.reference_type)}
                  />
                )}

                {selectedNotification.reference_id !== undefined &&
                  selectedNotification.reference_id !== null && (
                    <DetailRow
                      label="Reference"
                      value={String(selectedNotification.reference_id)}
                    />
                  )}
              </div>

              {/* Modal Actions */}

              <div className="mt-6 flex gap-3">
                {!isNotificationRead(selectedNotification) && (
                  <button
                    type="button"
                    onClick={() => void markAsRead(selectedNotification)}
                    disabled={
                      String(processingId) === String(selectedNotification.id)
                    }
                    className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-3 text-sm font-bold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {String(processingId) ===
                    String(selectedNotification.id) ? (
                      <>
                        <RefreshCw size={16} className="animate-spin" />
                        Updating...
                      </>
                    ) : (
                      <>
                        <Check size={16} />
                        Mark as Read
                      </>
                    )}
                  </button>
                )}

                <button
                  type="button"
                  onClick={() => void deleteNotification(selectedNotification)}
                  disabled={
                    String(processingId) === String(selectedNotification.id)
                  }
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-rose-200 px-4 py-3 text-sm font-bold text-rose-600 hover:bg-rose-50 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Trash2 size={16} />
                  Delete
                </button>

                <button
                  type="button"
                  onClick={() => setSelectedNotification(null)}
                  className="rounded-xl border border-slate-200 px-5 py-3 text-sm font-bold text-slate-700 hover:bg-slate-50"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ==========================================================
// Summary Card
// ==========================================================

function SummaryCard({
  label,
  value,
  helper,
  icon,
  iconClass,
}: {
  label: string;
  value: number;
  helper: string;
  icon: React.ReactNode;
  iconClass: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-widest text-slate-400">
            {label}
          </p>

          <p className="mt-3 text-3xl font-extrabold text-slate-900">
            {value.toLocaleString("en-KE")}
          </p>

          <p className="mt-1 text-sm text-slate-500">{helper}</p>
        </div>

        <div
          className={`grid h-11 w-11 place-items-center rounded-xl ${iconClass}`}
        >
          {icon}
        </div>
      </div>
    </div>
  );
}

// ==========================================================
// Filter Button
// ==========================================================

function FilterButton({
  active,
  label,
  onClick,
}: {
  active: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-xl px-4 py-2.5 text-sm font-bold transition ${
        active
          ? "bg-slate-900 text-white"
          : "text-slate-500 hover:bg-slate-100 hover:text-slate-900"
      }`}
    >
      {label}
    </button>
  );
}

// ==========================================================
// Detail Row
// ==========================================================

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-5 border-b border-slate-100 px-4 py-3 last:border-b-0">
      <span className="text-sm text-slate-500">{label}</span>

      <span className="text-right text-sm font-bold text-slate-800">
        {value}
      </span>
    </div>
  );
}
