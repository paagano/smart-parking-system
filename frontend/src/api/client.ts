import axios from "axios";

// ==========================================================
// API Configuration
// ==========================================================
//
// Vite loads VITE_* variables from frontend/.env.
//
// Local development:
//
// VITE_API_BASE_URL=http://localhost:8000
//
// The fallback is intentionally retained so the application
// remains usable if the .env file is temporarily missing.
// ==========================================================

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const api = axios.create({
  baseURL: API_BASE_URL,

  headers: {
    "Content-Type": "application/json",
  },

  timeout: 15000,
});

// ==========================================================
// Request Interceptor
// ==========================================================
//
// Automatically attach the JWT access token to every
// authenticated API request.
//
// The backend expects:
//
// Authorization: Bearer <JWT>
// ==========================================================

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem("smartpark_token");

    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    return config;
  },

  (error) => {
    return Promise.reject(error);
  },
);

// ==========================================================
// Response Interceptor
// ==========================================================
//
// If the backend returns 401, the JWT is no longer valid.
// Remove the stale token.
//
// We deliberately do NOT automatically redirect here.
// Routing decisions belong to AuthContext / React Router.
// ==========================================================

api.interceptors.response.use(
  (response) => {
    return response;
  },

  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("smartpark_token");
    }

    return Promise.reject(error);
  },
);

// ==========================================================
// Authentication API
// ==========================================================
// API Utility Helpers
// ==========================================================

/**
 * Return the configured backend URL.
 *
 * Useful for diagnostics and development.
 */
export const getApiBaseUrl = (): string => {
  return API_BASE_URL;
};

/**
 * Determine whether an error was caused by the backend
 * returning an HTTP response.
 */
export const isApiError = (error: unknown): boolean => {
  return axios.isAxiosError(error);
};

/**
 * Extract a useful backend error message.
 *
 * FastAPI commonly returns:
 *
 * {
 *   "detail": "..."
 * }
 *
 * This helper keeps UI error handling consistent.
 */
export const getApiErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const detail = error.response?.data?.detail;

    if (typeof detail === "string") {
      return detail;
    }

    if (Array.isArray(detail)) {
      return detail
        .map((item) => {
          if (typeof item === "string") {
            return item;
          }

          if (item && typeof item === "object" && "msg" in item) {
            return String(item.msg);
          }

          return "Validation error.";
        })
        .join(", ");
    }

    if (error.response) {
      return `Request failed with status ${error.response.status}.`;
    }

    if (error.request) {
      return "Unable to reach the SmartPark AI backend.";
    }
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "An unexpected error occurred.";
};


