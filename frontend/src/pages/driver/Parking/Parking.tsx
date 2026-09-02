import { useCallback, useEffect, useMemo, useState } from "react";
import type { ComponentType } from "react";
import {
  AlertCircle,
  Building2,
  CheckCircle2,
  CalendarPlus,
  Clock3,
  MapPin,
  Navigation,
  ParkingCircle,
  RefreshCw,
  Search,
  XCircle,
} from "lucide-react";

import {
  parkingBaysApi,
  parkingFacilitiesApi,
  parkingSessionsApi,
  parkingZonesApi,
  type ParkingBay,
  type ParkingFacility,
  type ParkingSession,
  type ParkingZone,
} from "../../../api";

// ==========================================================
// Helpers
// ==========================================================

function formatFacilityType(value: string | undefined): string {
  if (!value) {
    return "Parking Facility";
  }

  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatTime(value: string | undefined): string {
  if (!value) {
    return "—";
  }

  const match = value.match(/^(\d{1,2}):(\d{2})/);

  if (!match) {
    return value;
  }

  const hours = Number(match[1]);
  const minutes = match[2];

  const suffix = hours >= 12 ? "PM" : "AM";
  const displayHour = hours % 12 || 12;

  return `${displayHour}:${minutes} ${suffix}`;
}

function isFacilityOpen(facility: ParkingFacility): boolean {
  if (!facility.is_active) {
    return false;
  }

  if (!facility.opening_time || !facility.closing_time) {
    return true;
  }

  const now = new Date();

  const currentMinutes = now.getHours() * 60 + now.getMinutes();

  const openingMatch = facility.opening_time.match(/^(\d{1,2}):(\d{2})/);

  const closingMatch = facility.closing_time.match(/^(\d{1,2}):(\d{2})/);

  if (!openingMatch || !closingMatch) {
    return true;
  }

  const openingMinutes = Number(openingMatch[1]) * 60 + Number(openingMatch[2]);

  const closingMinutes = Number(closingMatch[1]) * 60 + Number(closingMatch[2]);

  return currentMinutes >= openingMinutes && currentMinutes <= closingMinutes;
}

function buildLocation(facility: ParkingFacility): string {
  return [facility.address, facility.city, facility.county]
    .filter(Boolean)
    .join(", ");
}

// ==========================================================
// Component
// ==========================================================

export default function Parking() {
  const [facilities, setFacilities] = useState<ParkingFacility[]>([]);

  const [zones, setZones] = useState<ParkingZone[]>([]);

  const [bays, setBays] = useState<ParkingBay[]>([]);

  const [activeSessions, setActiveSessions] = useState<ParkingSession[]>([]);

  const [query, setQuery] = useState("");

  const [isLoading, setIsLoading] = useState(true);

  const [isRefreshing, setIsRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [userLocation, setUserLocation] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);

  // ========================================================
  // Load facilities
  // ========================================================

  const loadFacilities = useCallback(async (refresh = false) => {
    try {
      if (refresh) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
      }

      setError(null);

      const [facilityResult, zoneResult, bayResult, sessionResult] =
        await Promise.allSettled([
          parkingFacilitiesApi.list(0, 500),
          parkingZonesApi.list(0, 500),
          parkingBaysApi.list(0, 500),
          parkingSessionsApi.active(),
        ]);

      const failures: string[] = [];

      if (facilityResult.status === "fulfilled") {
        setFacilities(facilityResult.value.items);
      } else {
        failures.push("parking facilities");
      }

      if (zoneResult.status === "fulfilled") {
        setZones(zoneResult.value.items);
      } else {
        failures.push("parking zones");
      }

      if (bayResult.status === "fulfilled") {
        setBays(bayResult.value.items);
      } else {
        failures.push("parking bays");
      }

      if (sessionResult.status === "fulfilled") {
        setActiveSessions(sessionResult.value.items);
      } else {
        failures.push("active parking sessions");
      }

      if (failures.length > 0) {
        setError(
          `Some live parking data could not be loaded: ${failures.join(", ")}.`,
        );
      }
    } catch (err: any) {
      console.error("[SmartPark Parking] Failed to load facilities:", err);

      const detail = err?.response?.data?.detail;

      if (typeof detail === "string") {
        setError(detail);
      } else {
        setError(
          "Unable to load parking facilities from the SmartPark AI backend.",
        );
      }
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }, []);

  // ========================================================
  // Initial load
  // ========================================================

  useEffect(() => {
    void loadFacilities();
  }, [loadFacilities]);

  // ========================================================
  // User location
  // ========================================================

  useEffect(() => {
    if (!navigator.geolocation) {
      return;
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        setUserLocation({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
        });
      },
      () => {
        // Location is optional. The facility list still works
        // normally when the user denies location access.
      },
      {
        enableHighAccuracy: false,
        timeout: 5000,
        maximumAge: 300000,
      },
    );
  }, []);

  // ========================================================
  // Search / filtering + proximity sorting
  // ========================================================

  const filteredFacilities = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    const matchingFacilities = normalizedQuery
      ? facilities.filter((facility) => {
          const searchableText = [
            facility.name,
            facility.code,
            facility.description,
            facility.facility_type,
            facility.country,
            facility.county,
            facility.city,
            facility.address,
          ]
            .filter(Boolean)
            .join(" ")
            .toLowerCase();

          return searchableText.includes(normalizedQuery);
        })
      : [...facilities];

    // If browser location is available, order facilities from
    // nearest to farthest using the Haversine formula.
    if (!userLocation) {
      return matchingFacilities;
    }

    const toRadians = (degrees: number) => (degrees * Math.PI) / 180;

    const distanceInKm = (facility: ParkingFacility): number => {
      if (
        facility.latitude === null ||
        facility.latitude === undefined ||
        facility.longitude === null ||
        facility.longitude === undefined
      ) {
        return Number.POSITIVE_INFINITY;
      }

      const earthRadiusKm = 6371;

      const latitude1 = toRadians(userLocation.latitude);
      const latitude2 = toRadians(facility.latitude);

      const deltaLatitude = toRadians(
        facility.latitude - userLocation.latitude,
      );

      const deltaLongitude = toRadians(
        facility.longitude - userLocation.longitude,
      );

      const a =
        Math.sin(deltaLatitude / 2) ** 2 +
        Math.cos(latitude1) *
          Math.cos(latitude2) *
          Math.sin(deltaLongitude / 2) ** 2;

      return earthRadiusKm * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    };

    return matchingFacilities.sort((a, b) => distanceInKm(a) - distanceInKm(b));
  }, [facilities, query, userLocation]);

  // ========================================================
  // Live availability
  // ========================================================

  const zoneFacilityMap = useMemo(() => {
    return new Map(zones.map((zone) => [zone.id, zone.facility_id]));
  }, [zones]);

  const activeSessionBayIds = useMemo(() => {
    return new Set(activeSessions.map((session) => session.parking_bay_id));
  }, [activeSessions]);

  const availabilityByFacility = useMemo(() => {
    const stats = new Map<
      number,
      {
        total: number;
        occupied: number;
        available: number;
      }
    >();

    for (const facility of facilities) {
      stats.set(facility.id, {
        total: 0,
        occupied: 0,
        available: 0,
      });
    }

    for (const bay of bays) {
      if (!bay.is_active) {
        continue;
      }

      const facilityId = zoneFacilityMap.get(bay.zone_id);

      if (!facilityId) {
        continue;
      }

      const current = stats.get(facilityId) ?? {
        total: 0,
        occupied: 0,
        available: 0,
      };

      current.total += 1;

      if (activeSessionBayIds.has(bay.id)) {
        current.occupied += 1;
      } else {
        current.available += 1;
      }

      stats.set(facilityId, current);
    }

    return stats;
  }, [facilities, bays, zoneFacilityMap, activeSessionBayIds]);

  const totalAvailableSpaces = useMemo(() => {
    let total = 0;

    for (const stats of availabilityByFacility.values()) {
      total += stats.available;
    }

    return total;
  }, [availabilityByFacility]);

  // ========================================================
  // Summary
  // ========================================================

  const activeFacilities = facilities.filter(
    (facility) => facility.is_active,
  ).length;

  // ========================================================
  // Render
  // ========================================================

  return (
    <div className="space-y-6">
      {/* ====================================================
          Page Header
      ==================================================== */}

      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <div className="text-xs font-bold uppercase tracking-[.2em] text-emerald-600">
            SmartPark AI
          </div>

          <h1 className="mt-2 text-3xl font-black tracking-tight">
            Find Parking Near You
          </h1>

          <p className="mt-2 max-w-2xl text-slate-500">
            Browse live parking facilities connected to the SmartPark AI
            backend.
          </p>
        </div>

        <button
          type="button"
          onClick={() => void loadFacilities(true)}
          disabled={isRefreshing}
          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm transition hover:border-emerald-300 hover:text-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <RefreshCw size={16} className={isRefreshing ? "animate-spin" : ""} />

          {isRefreshing ? "Refreshing..." : "Refresh"}
        </button>
      </div>

      {/* ====================================================
          Search
      ==================================================== */}

      <div className="rounded-3xl bg-white p-4 shadow-sm ring-1 ring-slate-200 sm:p-5">
        <div className="relative">
          <Search
            className="absolute left-4 top-3.5 text-slate-400"
            size={18}
          />

          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search facility, code, area or city..."
            className="w-full rounded-xl border border-slate-200 bg-slate-50 p-3 pl-11 text-sm outline-none transition focus:border-emerald-400 focus:bg-white focus:ring-2 focus:ring-emerald-100"
          />

          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-3 top-2.5 rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-700"
              aria-label="Clear search"
            >
              <XCircle size={18} />
            </button>
          )}
        </div>
      </div>

      {/* ====================================================
          Live Summary
      ==================================================== */}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          label="Facilities"
          value={facilities.length}
          note="From SmartPark AI backend"
          Icon={Building2}
        />

        <SummaryCard
          label="Active facilities"
          value={activeFacilities}
          note="Currently enabled"
          Icon={CheckCircle2}
        />

        <SummaryCard
          label="Available spaces"
          value={totalAvailableSpaces}
          note="Live bay & session data"
          Icon={ParkingCircle}
        />

        <SummaryCard
          label="Showing"
          value={filteredFacilities.length}
          note={query ? "Matching your search" : "All available facilities"}
          Icon={Search}
        />
      </div>

      {/* ====================================================
          Error
      ==================================================== */}

      {error && (
        <div className="flex flex-col gap-4 rounded-2xl border border-rose-200 bg-rose-50 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <AlertCircle className="mt-0.5 shrink-0 text-rose-600" size={20} />

            <div>
              <p className="font-bold text-rose-800">
                Unable to load parking facilities
              </p>

              <p className="mt-1 text-sm text-rose-700">{error}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => void loadFacilities(true)}
            className="rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-rose-700"
          >
            Try again
          </button>
        </div>
      )}

      {/* ====================================================
          Facility List
      ==================================================== */}

      <section className="rounded-3xl bg-white p-5 shadow-sm ring-1 ring-slate-200 sm:p-6">
        <div className="mb-5">
          <h2 className="font-extrabold">Parking Facilities</h2>

          <p className="mt-1 text-xs text-slate-500">
            Live facility master data from SmartPark AI
          </p>
        </div>

        {/* Loading */}

        {isLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((item) => (
              <div
                key={item}
                className="animate-pulse rounded-2xl border border-slate-200 p-5"
              >
                <div className="h-5 w-1/3 rounded bg-slate-200" />

                <div className="mt-3 h-4 w-2/3 rounded bg-slate-100" />

                <div className="mt-5 grid gap-3 sm:grid-cols-3">
                  <div className="h-12 rounded-xl bg-slate-100" />
                  <div className="h-12 rounded-xl bg-slate-100" />
                  <div className="h-12 rounded-xl bg-slate-100" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty */}

        {!isLoading && !error && filteredFacilities.length === 0 && (
          <div className="rounded-2xl bg-slate-50 p-10 text-center">
            <Search className="mx-auto text-slate-400" size={34} />

            <h3 className="mt-4 font-extrabold">No parking facilities found</h3>

            <p className="mt-2 text-sm text-slate-500">
              {query
                ? "Try a different facility name, code or location."
                : "The SmartPark AI backend currently has no facilities available."}
            </p>

            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="mt-4 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-emerald-700"
              >
                Clear search
              </button>
            )}
          </div>
        )}

        {/* Facilities */}

        {!isLoading && filteredFacilities.length > 0 && (
          <div className="space-y-4">
            {filteredFacilities.map((facility) => {
              const open = isFacilityOpen(facility);

              const location = buildLocation(facility);

              const availability = availabilityByFacility.get(facility.id) ?? {
                total: 0,
                occupied: 0,
                available: 0,
              };

              const hasAvailabilityData = availability.total > 0;

              const availabilityLabel = hasAvailabilityData
                ? `${availability.available} available`
                : "Availability unavailable";

              const availabilityClass = !hasAvailabilityData
                ? "bg-slate-100 text-slate-500"
                : availability.available === 0
                  ? "bg-rose-50 text-rose-700"
                  : availability.available <= 2
                    ? "bg-amber-50 text-amber-700"
                    : "bg-emerald-50 text-emerald-700";

              // ======================================================
              // SURGICAL FIX:
              // Restore the facility distance display using the same
              // Haversine calculation already used for proximity
              // sorting above.
              // ======================================================

              let facilityDistanceKm: number | null = null;

              if (
                userLocation &&
                facility.latitude !== null &&
                facility.latitude !== undefined &&
                facility.longitude !== null &&
                facility.longitude !== undefined
              ) {
                const toRadians = (degrees: number) =>
                  (degrees * Math.PI) / 180;

                const earthRadiusKm = 6371;

                const latitude1 = toRadians(userLocation.latitude);
                const latitude2 = toRadians(facility.latitude);

                const deltaLatitude = toRadians(
                  facility.latitude - userLocation.latitude,
                );

                const deltaLongitude = toRadians(
                  facility.longitude - userLocation.longitude,
                );

                const a =
                  Math.sin(deltaLatitude / 2) ** 2 +
                  Math.cos(latitude1) *
                    Math.cos(latitude2) *
                    Math.sin(deltaLongitude / 2) ** 2;

                facilityDistanceKm =
                  earthRadiusKm *
                  2 *
                  Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
              }

              return (
                <article
                  key={facility.id}
                  className="rounded-2xl border border-slate-200 bg-white p-5 transition hover:border-emerald-300 hover:shadow-md"
                >
                  {/* Top */}

                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="flex items-start gap-4">
                      <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                        <ParkingCircle size={23} />
                      </div>

                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="text-lg font-extrabold">
                            {facility.name}
                          </h3>

                          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-bold uppercase tracking-wide text-slate-500">
                            {facility.code}
                          </span>
                        </div>

                        <p className="mt-1 text-sm text-slate-500">
                          {formatFacilityType(facility.facility_type)}
                        </p>

                        {/* ==================================================
                            RESTORED DISTANCE
                            Example: 7.2 KM
                        ================================================== */}

                        {facilityDistanceKm !== null && (
                          <p className="mt-1 text-xs font-bold text-emerald-600">
                            {facilityDistanceKm.toFixed(1)} KM away
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`inline-flex w-fit items-center gap-2 rounded-full px-3 py-1.5 text-xs font-bold ${availabilityClass}`}
                      >
                        <span className="h-2 w-2 rounded-full bg-current opacity-70" />

                        {availabilityLabel}
                      </span>

                      <span
                        className={`inline-flex w-fit items-center gap-2 rounded-full px-3 py-1.5 text-xs font-bold ${
                          open
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        <span
                          className={`h-2 w-2 rounded-full ${
                            open ? "bg-emerald-500" : "bg-slate-400"
                          }`}
                        />

                        {open
                          ? "Open"
                          : facility.is_active
                            ? "Closed"
                            : "Inactive"}
                      </span>
                    </div>
                  </div>

                  {/* Details */}

                  <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                    <InfoItem
                      Icon={MapPin}
                      label="Location"
                      value={location || "Location not provided"}
                    />

                    <InfoItem
                      Icon={Clock3}
                      label="Operating hours"
                      value={`${formatTime(
                        facility.opening_time,
                      )} – ${formatTime(facility.closing_time)}`}
                    />

                    <InfoItem
                      Icon={Navigation}
                      label="Coordinates"
                      value={
                        facility.latitude !== null &&
                        facility.latitude !== undefined &&
                        facility.longitude !== null &&
                        facility.longitude !== undefined
                          ? `${facility.latitude.toFixed(
                              5,
                            )}, ${facility.longitude.toFixed(5)}`
                          : "Coordinates not provided"
                      }
                    />

                    <AvailabilityItem
                      available={availability.available}
                      occupied={availability.occupied}
                      total={availability.total}
                      hasData={hasAvailabilityData}
                    />
                  </div>

                  {/* Description */}

                  {facility.description && (
                    <p className="mt-4 text-sm leading-6 text-slate-600">
                      {facility.description}
                    </p>
                  )}

                  {/* Actions */}

                  <div className="mt-5 flex flex-wrap gap-3 border-t border-slate-100 pt-4">
                    <a
                      href={`/reservations/create?facilityId=${encodeURIComponent(
                        String(facility.id),
                      )}&facilityName=${encodeURIComponent(facility.name)}`}
                      className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-emerald-700"
                    >
                      <CalendarPlus size={16} />
                      Make a Reservation
                    </a>

                    {facility.latitude !== null &&
                      facility.latitude !== undefined &&
                      facility.longitude !== null &&
                      facility.longitude !== undefined && (
                        <a
                          href={`https://www.google.com/maps/dir/?api=1&destination=${facility.latitude},${facility.longitude}`}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:border-emerald-300 hover:text-emerald-700"
                        >
                          <Navigation size={16} />
                          Navigate to Facility
                        </a>
                      )}

                    <span className="inline-flex items-center gap-2 rounded-xl bg-slate-50 px-4 py-2.5 text-xs font-semibold text-slate-600">
                      <ParkingCircle size={15} />

                      {hasAvailabilityData
                        ? `${availability.available} of ${availability.total} bays available`
                        : "Live availability unavailable"}
                    </span>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

// ==========================================================
// Summary Card
// ==========================================================

function SummaryCard({
  label,
  value,
  note,
  Icon,
}: {
  label: string;
  value: number;
  note: string;
  Icon: ComponentType<{
    size?: number;
    className?: string;
  }>;
}) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <div className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
        <Icon size={19} />
      </div>

      <div className="mt-4 text-2xl font-black">{value}</div>

      <div className="mt-1 text-sm text-slate-500">{label}</div>

      <div className="mt-3 text-xs font-semibold text-emerald-600">{note}</div>
    </div>
  );
}

// ==========================================================
// Availability Item
// ==========================================================

function AvailabilityItem({
  available,
  occupied,
  total,
  hasData,
}: {
  available: number;
  occupied: number;
  total: number;
  hasData: boolean;
}) {
  const occupancyPercent = total > 0 ? Math.round((occupied / total) * 100) : 0;

  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-400">
        <ParkingCircle size={15} />
        Live availability
      </div>

      {hasData ? (
        <>
          <div className="mt-2 flex items-end justify-between gap-3">
            <div>
              <p className="text-lg font-black text-slate-800">
                {available} available
              </p>

              <p className="mt-0.5 text-xs text-slate-500">
                {occupied} occupied of {total}
              </p>
            </div>

            <span className="text-xs font-bold text-emerald-600">
              {occupancyPercent}% occupied
            </span>
          </div>

          <div className="mt-3 h-2 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all"
              style={{ width: `${occupancyPercent}%` }}
            />
          </div>
        </>
      ) : (
        <p className="mt-2 text-sm font-semibold text-slate-500">
          Live availability data unavailable
        </p>
      )}
    </div>
  );
}

// ==========================================================
// Info Item
// ==========================================================

function InfoItem({
  Icon,
  label,
  value,
}: {
  Icon: ComponentType<{
    size?: number;
    className?: string;
  }>;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl bg-slate-50 p-4">
      <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wide text-slate-400">
        <Icon size={15} />
        {label}
      </div>

      <p className="mt-2 text-sm font-semibold text-slate-700">{value}</p>
    </div>
  );
}
