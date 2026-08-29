import { api } from "../client";

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
    const response = await api.get<ParkingBayListResponse>(
      "/parking-bays",
      { params: { skip, limit } },
    );
    return response.data;
  },

  byZone: async (zoneId: number, skip = 0, limit = 500): Promise<ParkingBayListResponse> => {
    const response = await api.get<ParkingBayListResponse>(
      `/parking-bays/zone/${zoneId}`,
      { params: { skip, limit } },
    );
    return response.data;
  },
};

