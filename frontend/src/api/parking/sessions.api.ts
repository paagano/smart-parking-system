import { api } from "../client";

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
    const response = await api.get<ParkingSessionListResponse>(
      "/parking-sessions",
    );
    return response.data;
  },

  vehicleHistory: async (registration: string): Promise<ParkingSessionListResponse> => {
    const response = await api.get<ParkingSessionListResponse>(
      `/parking-sessions/vehicle/${encodeURIComponent(registration)}`,
    );
    return response.data;
  },
};

