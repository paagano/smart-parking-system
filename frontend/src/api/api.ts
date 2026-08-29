// Backward-compatible API barrel.
// Keep this file so older imports remain stable while the API layer
// is now organised by domain.

export * from "./client";
export * from "./auth.api";
export * from "./users.api";
export * from "./forecasting/forecasting.api";
export * from "./parking/facilities.api";
export * from "./parking/zones.api";
export * from "./parking/bays.api";
export * from "./parking/sessions.api";
export * from "./reservations/reservations.api";
