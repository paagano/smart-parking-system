import { api } from "./client";

// ==========================================================
// User API
// ==========================================================

export interface CurrentUser {
  id: number;

  first_name: string;

  last_name: string;

  email: string;

  phone_number: number | string;

  role: "DRIVER" | "ATTENDANT" | "ADMIN";

  is_active: boolean;

  is_verified: boolean;

  created_at: string;

  updated_at: string;
}

export const usersApi = {
  /**
   * Retrieve the currently authenticated user.
   *
   * Backend endpoint:
   *
   * GET /users/me
   *
   * Requires:
   *
   * Authorization: Bearer <JWT>
   */
  me: async (): Promise<CurrentUser> => {
    const response = await api.get<CurrentUser>("/users/me");

    return response.data;
  },
};

