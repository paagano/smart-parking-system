import { api } from "../client";

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
  activeByCustomer: async (customerId: number): Promise<ParkingReservationListResponse> => {
    const response = await api.get<ParkingReservationListResponse>(
      `/parking-reservations/customer/${customerId}/active`,
    );
    return response.data;
  },

  byCustomer: async (customerId: number): Promise<ParkingReservationListResponse> => {
    const response = await api.get<ParkingReservationListResponse>(
      `/parking-reservations/customer/${customerId}`,
    );
    return response.data;
  },
};

