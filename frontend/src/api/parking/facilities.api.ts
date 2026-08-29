import { api } from "../client";

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
  county: string;
  city: string;
  address: string;
  postal_code: string | null;
  latitude: number;
  longitude: number;
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



