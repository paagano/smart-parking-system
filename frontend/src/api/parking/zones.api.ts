import { api } from "../client";

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
    const response = await api.get<ParkingZoneListResponse>(
      "/parking-zones",
      { params: { skip, limit } },
    );
    return response.data;
  },

  byFacility: async (facilityId: number, skip = 0, limit = 500): Promise<ParkingZoneListResponse> => {
    const response = await api.get<ParkingZoneListResponse>(
      `/parking-zones/facility/${facilityId}`,
      { params: { skip, limit } },
    );
    return response.data;
  },
};

