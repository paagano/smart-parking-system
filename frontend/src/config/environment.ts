// ==========================================================
// SmartPark AI - Frontend Environment Configuration
// ==========================================================
//
// All frontend environment-specific configuration should
// be accessed through this file.
//
// Do NOT read import.meta.env directly throughout the
// application.
//
// Configuration is supplied through Vite VITE_* variables.
// ==========================================================

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const environment = {
  apiBaseUrl: API_BASE_URL,
} as const;

export const getApiBaseUrl = (): string => {
  return environment.apiBaseUrl;
};