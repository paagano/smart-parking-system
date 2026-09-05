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
   * Logout the currently authenticated session.
   *
   * Backend endpoint:
   *
   * POST /auth/logout
   *
   * The backend extracts the JWT JTI and stores it in the
   * revoked_tokens table.
   *
   * The local JWT is removed regardless of whether the
   * backend request succeeds, ensuring the frontend always
   * terminates the local session.
   */
  logout: async (): Promise<void> => {
    const token = localStorage.getItem("smartpark_token");

    if (!token) {
      return;
    }

    try {
      await api.post("/auth/logout");
    } finally {
      //
      // Always clear the local token.
      //
      // This is important if the backend is temporarily
      // unavailable: the user must still be logged out
      // locally.
      //
      localStorage.removeItem("smartpark_token");
    }
  },

  /**
   * Verify a user's email address.
   *
   * Backend endpoint:
   *
   * POST /auth/verify-email?token=<verification_token>
   *
   * This endpoint is public and does not require the
   * normal authenticated JWT.
   */
  verifyEmail: async (token: string): Promise<CurrentUser> => {
    const response = await api.post<{
      message: string;
      user: CurrentUser;
    }>("/auth/verify-email", null, {
      params: {
        token,
      },
    });

    return response.data.user;
  },

  /**
   * Request a password-reset link.
   *
   * Backend endpoint:
   *
   * POST /auth/forgot-password
   *
   * The backend intentionally returns the same generic response
   * whether or not the supplied email belongs to an account.
   */
  forgotPassword: async (email: string): Promise<string> => {
    const response = await api.post<{ message: string }>(
      "/auth/forgot-password",
      {
        email: email.trim(),
      },
    );

    return response.data.message;
  },

  /**
   * Reset a user's password using a password-reset token.
   *
   * Backend endpoint:
   *
   * POST /auth/reset-password
   */
  resetPassword: async (
    token: string,
    newPassword: string,
    confirmPassword: string,
  ): Promise<string> => {
    const response = await api.post<{ message: string }>(
      "/auth/reset-password",
      {
        token,
        new_password: newPassword,
        confirm_password: confirmPassword,
      },
    );

    return response.data.message;
  },

  /**
   * Resend the authenticated user's email verification link.
   *
   * Backend endpoint:
   *
   * POST /auth/resend-verification
   *
   * This endpoint requires the normal authenticated JWT.
   */
  resendVerification: async (): Promise<string> => {
    const response = await api.post<{ message: string }>(
      "/auth/resend-verification",
    );

    return response.data.message;
  },
};

// ==========================================================
// User API
// ==========================================================

export interface CurrentUser {
  id: number;

  first_name: string;

  last_name: string;

  email: string;

  phone_number: number | string;

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
   * Update the authenticated user's profile picture.
   *
   * Backend endpoint:
   *
   * POST /users/me/profile-picture
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
   * Delete the authenticated user's profile picture.
   *
   * Backend endpoint:
   *
   * DELETE /users/me/profile-picture
   */
  deleteProfilePicture: async (): Promise<CurrentUser> => {
    const response = await api.delete<CurrentUser>("/users/me/profile-picture");

    return response.data;
  },

  /**
   * Change the authenticated user's password.
   *
   * Backend endpoint:
   *
   * POST /users/me/change-password
   */
  changePassword: async (
    currentPassword: string,
    newPassword: string,
  ): Promise<void> => {
    await api.post("/users/me/change-password", {
      current_password: currentPassword,
      new_password: newPassword,
    });
  },
};

// ==========================================================
// Forecast API
// ==========================================================
//
// Current production forecasting contract:
//
// POST /forecasts/facilities/{facility_id}
//
// The current backend implementation performs
// inference using the frozen production model.
//
// IMPORTANT:
// This API intentionally represents the CURRENT backend
// contract. We will generalise the ML architecture later
// so the frontend does not become coupled to Birmingham,
// XGBoost, or a particular forecast horizon.
// ==========================================================

export interface ForecastRequest {
  /**
   * Prediction timestamp T.
   *
   * ISO-8601 timestamp.
   */
  prediction_timestamp: string;

  /**
   * Historical observation lookback window.
   *
   * Current production contract:
   * 1440 minutes = 24 hours.
   */
  lookback_minutes: number;
}

export interface ForecastResponse {
  facility_id: number;

  prediction_timestamp: string;

  forecast_timestamp: string;

  forecast_horizon_minutes: number;

  predicted_occupancy_rate: number;

  model_candidate: string;

  target_column: string;

  feature_count: number;

  feature_information: string;

  inference_only: boolean;
}

export const forecastApi = {
  /**
   * Check production forecasting service health.
   *
   * Backend:
   *
   * GET /forecasts/health
   */
  health: () => api.get("/forecasts/health"),

  /**
   * Generate a production occupancy forecast.
   *
   * Backend:
   *
   * POST /forecasts/facilities/{facility_id}
   *
   * Current implementation:
   *
   * T -> T + 30 minutes
   */
  forecast: (facilityId: number, payload: ForecastRequest) =>
    api.post<ForecastResponse>(`/forecasts/facilities/${facilityId}`, payload),
};

// ==========================================================
// Parking Facilities API
// ==========================================================

export interface ParkingFacility {
  id: number;
  name: string;
  code: string;
  facility_type: string;
  description: string | null;
  country: string;
  county: string | null;
  city: string | null;
  address: string | null;
  postal_code: string | null;
  latitude: number | null;
  longitude: number | null;
  timezone: string;
  opening_time: string;
  closing_time: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ParkingFacilityListResponse {
  total: number;

  items: ParkingFacility[];
}

export const parkingFacilitiesApi = {
  /**
   * Retrieve parking facilities.
   *
   * Backend:
   *
   * GET /parking-facilities
   */
  list: async (skip = 0, limit = 100): Promise<ParkingFacilityListResponse> => {
    const response = await api.get<ParkingFacilityListResponse>(
      "/parking-facilities",
      {
        params: {
          skip,
          limit,
        },
      },
    );

    return response.data;
  },

  /**
   * Retrieve a specific parking facility.
   *
   * Backend:
   *
   * GET /parking-facilities/{facility_id}
   */
  get: async (facilityId: number): Promise<ParkingFacility> => {
    const response = await api.get<ParkingFacility>(
      `/parking-facilities/${facilityId}`,
    );

    return response.data;
  },

  /**
   * Search parking facilities.
   *
   * Backend:
   *
   * GET /parking-facilities/search
   */
  search: async (
    query: string,
    skip = 0,
    limit = 100,
  ): Promise<ParkingFacilityListResponse> => {
    const response = await api.get<ParkingFacilityListResponse>(
      "/parking-facilities/search",
      {
        params: {
          q: query,
          skip,
          limit,
        },
      },
    );

    return response.data;
  },
};

// ==========================================================
// Parking Zones API
// ==========================================================

export interface ParkingZone {
  id: number;
  facility_id: number;
  parent_zone_id: number | null;
  name: string;
  code: string;
  zone_type: string;
  description?: string | null;
  sort_order: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ParkingZoneListResponse {
  total: number;
  items: ParkingZone[];
}

export const parkingZonesApi = {
  list: async (skip = 0, limit = 500): Promise<ParkingZoneListResponse> => {
    const response = await api.get<ParkingZoneListResponse>("/parking-zones", {
      params: {
        skip,
        limit,
      },
    });

    return response.data;
  },

  byFacility: async (
    facilityId: number,
    skip = 0,
    limit = 500,
  ): Promise<ParkingZoneListResponse> => {
    const response = await api.get<ParkingZoneListResponse>(
      `/parking-zones/facility/${facilityId}`,
      {
        params: {
          skip,
          limit,
        },
      },
    );

    return response.data;
  },
};

// ==========================================================
// Parking Bays API
// ==========================================================

export interface ParkingBay {
  id: number;
  zone_id: number;
  bay_number: string;
  code: string;
  bay_type: string;
  vehicle_type: string;
  size: string;
  is_accessible: boolean;
  is_ev_charging: boolean;
  is_vip: boolean;
  is_reservable: boolean;
  is_active: boolean;
  sort_order: number;
  description?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ParkingBayListResponse {
  total: number;
  items: ParkingBay[];
}

export const parkingBaysApi = {
  list: async (skip = 0, limit = 500): Promise<ParkingBayListResponse> => {
    const response = await api.get<ParkingBayListResponse>("/parking-bays", {
      params: {
        skip,
        limit,
      },
    });

    return response.data;
  },

  byZone: async (
    zoneId: number,
    skip = 0,
    limit = 500,
  ): Promise<ParkingBayListResponse> => {
    const response = await api.get<ParkingBayListResponse>(
      `/parking-bays/zone/${zoneId}`,
      {
        params: {
          skip,
          limit,
        },
      },
    );

    return response.data;
  },
};

// ==========================================================
// Parking Sessions API
// ==========================================================

export interface ParkingSession {
  id: number;
  parking_bay_id: number;
  customer_id: number | null;
  vehicle_id: number | null;
  vehicle_registration: string;
  vehicle_type: string;
  billing_type: string;
  session_source: string;
  entry_method: string;
  expected_exit_time: string | null;
  notes: string | null;
  session_number: string;
  status: string;
  exit_method: string | null;
  entry_time: string;
  exit_time: string | null;
  duration_minutes: number | null;
  calculated_amount: number | string;
  paid_amount: number | string;
  payment_status: string;
  created_by: number | null;
  updated_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface ParkingSessionListResponse {
  items: ParkingSession[];
  total: number;
}

export const parkingSessionsApi = {
  active: async (): Promise<ParkingSessionListResponse> => {
    const response =
      await api.get<ParkingSessionListResponse>("/parking-sessions");

    return response.data;
  },

  completed: async (): Promise<ParkingSessionListResponse> => {
    const response = await api.get<ParkingSessionListResponse>(
      "/parking-sessions/completed",
    );

    return response.data;
  },

  get: async (sessionId: number): Promise<ParkingSession> => {
    const response = await api.get<ParkingSession>(
      `/parking-sessions/${sessionId}`,
    );

    return response.data;
  },

  byNumber: async (sessionNumber: string): Promise<ParkingSession> => {
    const response = await api.get<ParkingSession>(
      `/parking-sessions/number/${encodeURIComponent(sessionNumber)}`,
    );

    return response.data;
  },

  vehicleHistory: async (
    registration: string,
  ): Promise<ParkingSessionListResponse> => {
    const response = await api.get<ParkingSessionListResponse>(
      `/parking-sessions/vehicle/${encodeURIComponent(registration)}`,
    );

    return response.data;
  },
};

// ==========================================================
// Parking Reservations API
// ==========================================================

export interface ParkingReservation {
  id: number;
  reservation_number: string;
  customer_id: number | null;
  parking_bay_id: number;
  vehicle_id: number | null;
  vehicle_registration: string;
  vehicle_type: string;
  reserved_from: string;
  reserved_until: string;
  estimated_amount: number | string | null;
  currency: string;
  status: string;
  expires_at: string | null;
  confirmed_at: string | null;
  checked_in_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  notes: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
  created_by: number | null;
  updated_by: number | null;
}

export interface ParkingReservationListResponse {
  items: ParkingReservation[];
  total: number;
}

export const parkingReservationsApi = {
  activeByCustomer: async (
    customerId: number,
  ): Promise<ParkingReservationListResponse> => {
    const response = await api.get<ParkingReservationListResponse>(
      `/parking-reservations/customer/${customerId}/active`,
    );

    return response.data;
  },

  byCustomer: async (
    customerId: number,
  ): Promise<ParkingReservationListResponse> => {
    const response = await api.get<ParkingReservationListResponse>(
      `/parking-reservations/customer/${customerId}`,
    );

    return response.data;
  },

  get: async (reservationId: number): Promise<ParkingReservation> => {
    const response = await api.get<ParkingReservation>(
      `/parking-reservations/${reservationId}`,
    );

    return response.data;
  },

  confirm: async (reservationId: number): Promise<ParkingReservation> => {
    const response = await api.patch<ParkingReservation>(
      `/parking-reservations/${reservationId}/confirm`,
    );

    return response.data;
  },

  cancel: async (reservationId: number): Promise<ParkingReservation> => {
    const response = await api.patch<ParkingReservation>(
      `/parking-reservations/${reservationId}/cancel`,
    );

    return response.data;
  },

  checkIn: async (reservationId: number): Promise<ParkingReservation> => {
    const response = await api.patch<ParkingReservation>(
      `/parking-reservations/${reservationId}/check-in`,
    );

    return response.data;
  },
};

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
