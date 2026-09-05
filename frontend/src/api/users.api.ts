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

  // NEW: Profile picture
  profile_picture_url: string | null;

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

  /**
   * Upload or replace the currently authenticated user's
   * profile picture.
   *
   * Backend endpoint:
   *
   * POST /users/me/profile-picture
   *
   * Requires:
   *
   * Authorization: Bearer <JWT>
   */
  uploadProfilePicture: async (file: File): Promise<CurrentUser> => {
    const formData = new FormData();

    formData.append("file", file);

    const response = await api.post<CurrentUser>(
      "/users/me/profile-picture",
      formData,
    );

    return response.data;
  },

  /**
   * Delete the currently authenticated user's profile picture.
   *
   * Backend endpoint:
   *
   * DELETE /users/me/profile-picture
   *
   * Requires:
   *
   * Authorization: Bearer <JWT>
   */
  deleteProfilePicture: async (): Promise<CurrentUser> => {
    const response = await api.delete<CurrentUser>("/users/me/profile-picture");

    return response.data;
  },
};
