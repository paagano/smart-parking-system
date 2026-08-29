import type { CurrentUser } from "../api";

export function getRoleLabel(role: CurrentUser["role"]): string {
  switch (role) {
    case "DRIVER":
      return "Driver";

    case "ATTENDANT":
      return "Operator";

    case "ADMIN":
      return "Administrator";

    default:
      return "User";
  }
}

export function getDefaultRoute(role: CurrentUser["role"]): string {
  switch (role) {
    case "DRIVER":
      return "/dashboard";

    case "ATTENDANT":
      return "/operator";

    case "ADMIN":
      return "/admin";

    default:
      return "/dashboard";
  }
}


export type Role = "driver" | "operator" | "admin";

export function normalizeRole(role: unknown): Role {
  const normalized = String(role ?? "")
    .trim()
    .toLowerCase();

  if (normalized === "admin") return "admin";
  if (normalized === "attendant" || normalized === "operator") return "operator";
  return "driver";
}
