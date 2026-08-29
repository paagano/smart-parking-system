import { api } from "./client";

// ==========================================================

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export const authApi = {
  /**
   * Authenticate a SmartPark AI user.
   *
   * Backend endpoint:
   *
   * POST /auth/login
   *
   * FastAPI uses OAuth2PasswordRequestForm,
   * therefore credentials MUST be submitted as
   * application/x-www-form-urlencoded.
   *
   * The backend expects:
   *
   * username = user's email address
   * password = user's password
   */
  login: async (email: string, password: string): Promise<LoginResponse> => {
    const formData = new URLSearchParams();

    formData.append("username", email.trim());

    formData.append("password", password);

    const response = await api.post<LoginResponse>("/auth/login", formData, {
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
      },
    });

    return response.data;
  },

  /**
   * Remove the locally stored JWT.
   *
   * There is currently no backend logout endpoint,
   * so logout is handled client-side by removing
   * the access token.
   */
  logout: (): void => {
    localStorage.removeItem("smartpark_token");
  },
};

