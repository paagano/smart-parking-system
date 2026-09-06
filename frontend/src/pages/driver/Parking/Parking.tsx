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
      <section className="rounded-3xl border border-slate-200/80 bg-white px-5 py-5 shadow-sm sm:px-6 sm:py-6">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <div className="inline-flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-emerald-600">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
              SmartPark AI
            </div>

            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-900 sm:text-3xl">
              Find Parking Near You
            </h1>

            <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500">
              Browse live parking facilities and check availability before you
              arrive.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void loadFacilities(true)}
            disabled={isRefreshing}
            className="inline-flex shrink-0 items-center justify-center gap-2 self-start rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-medium text-slate-700 shadow-sm transition hover:border-emerald-300 hover:text-emerald-700 disabled:cursor-not-allowed disabled:opacity-60 lg:self-auto"
          >
            <RefreshCw
              size={15}
              className={isRefreshing ? "animate-spin" : ""}
            />
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </section>

      {/* ====================================================
          Search
      ==================================================== */}
      <section className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm sm:p-5">
        <div className="relative">
          <Search
            className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400"
            size={18}
          />

          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search facility, code, area or city..."
            className="w-full rounded-xl border border-slate-200 bg-slate-50 py-3 pl-11 pr-11 text-sm text-slate-800 outline-none transition placeholder:text-slate-400 focus:border-emerald-400 focus:bg-white focus:ring-2 focus:ring-emerald-100"
          />

          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded-lg p-1.5 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700"
              aria-label="Clear search"
            >
              <XCircle size={18} />
            </button>
          )}
        </div>
      </section>

      {/* ====================================================
          Live Summary
      ==================================================== */}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
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
        <div className="flex flex-col gap-4 rounded-2xl border border-rose-200 bg-rose-50 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
          <div className="flex min-w-0 items-start gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-rose-100 text-rose-600">
              <AlertCircle size={18} />
            </span>

            <div className="min-w-0">
              <p className="text-sm font-semibold text-rose-800">
                Unable to load parking facilities
              </p>

              <p className="mt-1 text-xs leading-5 text-rose-700">{error}</p>
            </div>
          </div>

          <button
            type="button"
            onClick={() => void loadFacilities(true)}
            disabled={isRefreshing}
            className="shrink-0 self-start rounded-xl bg-rose-600 px-4 py-2.5 text-xs font-medium text-white transition hover:bg-rose-700 disabled:cursor-not-allowed disabled:opacity-60 sm:self-auto"
          >
            {isRefreshing ? "Refreshing..." : "Try again"}
          </button>
        </div>
      )}

      {/* ====================================================
          Facility List
      ==================================================== */}
      <section className="rounded-3xl border border-slate-200/80 bg-white p-4 shadow-sm sm:p-6">
        <div className="mb-5 flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-base font-semibold text-slate-900">
              Parking Facilities
            </h2>

            <p className="mt-1 text-xs text-slate-500">
              Live facility data from SmartPark AI
            </p>
          </div>

          {!isLoading && (
            <p className="text-xs text-slate-400">
              {filteredFacilities.length}{" "}
              {filteredFacilities.length === 1 ? "facility" : "facilities"}
            </p>
          )}
        </div>

        {/* Loading */}
        {isLoading && (
          <div className="space-y-3">
            {[1, 2, 3].map((item) => (
              <div
                key={item}
                className="animate-pulse rounded-2xl border border-slate-200 p-4 sm:p-5"
              >
                <div className="h-4 w-1/3 rounded bg-slate-200" />
                <div className="mt-3 h-3 w-2/3 rounded bg-slate-100" />

                <div className="mt-5 grid gap-3 sm:grid-cols-3">
                  <div className="h-11 rounded-xl bg-slate-100" />
                  <div className="h-11 rounded-xl bg-slate-100" />
                  <div className="h-11 rounded-xl bg-slate-100" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty */}
        {!isLoading && !error && filteredFacilities.length === 0 && (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-5 py-10 text-center">
            <span className="mx-auto grid h-11 w-11 place-items-center rounded-xl bg-white text-slate-400 ring-1 ring-slate-200">
              <Search size={22} />
            </span>

            <h3 className="mt-4 text-sm font-semibold text-slate-800">
              No parking facilities found
            </h3>

            <p className="mx-auto mt-2 max-w-md text-xs leading-5 text-slate-500">
              {query
                ? "Try a different facility name, code or location."
                : "The SmartPark AI backend currently has no facilities available."}
            </p>

            {query && (
              <button
                type="button"
                onClick={() => setQuery("")}
                className="mt-4 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-600/25"
              >
                Clear search
              </button>
            )}
          </div>
        )}

        {/* Facilities */}
        {!isLoading && filteredFacilities.length > 0 && (
          <div className="space-y-3">
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
                  className="rounded-2xl border border-slate-200 bg-white p-4 transition duration-200 hover:border-emerald-200 hover:shadow-sm sm:p-5"
                >
                  {/* Top */}
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="flex min-w-0 items-start gap-3.5">
                      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                        <ParkingCircle size={21} />
                      </span>

                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="min-w-0 text-base font-semibold text-slate-900 sm:text-[17px]">
                            {facility.name}
                          </h3>

                          <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.08em] text-slate-500">
                            {facility.code}
                          </span>
                        </div>

                        <p className="mt-1 text-xs text-slate-500">
                          {formatFacilityType(facility.facility_type)}
                        </p>

                        {facilityDistanceKm !== null && (
                          <p className="mt-1 text-xs font-medium text-emerald-700">
                            {facilityDistanceKm.toFixed(1)} km away
                          </p>
                        )}
                      </div>
                    </div>

                    <div className="flex flex-wrap items-center gap-2">
                      <span
                        className={`inline-flex w-fit items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-medium ${availabilityClass}`}
                      >
                        <span className="h-1.5 w-1.5 rounded-full bg-current opacity-70" />
                        {availabilityLabel}
                      </span>

                      <span
                        className={`inline-flex w-fit items-center gap-2 rounded-full px-3 py-1.5 text-[11px] font-medium ${
                          open
                            ? "bg-emerald-50 text-emerald-700"
                            : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        <span
                          className={`h-1.5 w-1.5 rounded-full ${
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
                  <div className="mt-4 grid gap-2.5 md:grid-cols-2 xl:grid-cols-4">
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
                    <p className="mt-4 max-w-4xl text-xs leading-5 text-slate-600 sm:text-sm">
                      {facility.description}
                    </p>
                  )}

                  {/* Actions */}
                  <div className="mt-4 flex flex-col gap-2.5 border-t border-slate-100 pt-4 sm:flex-row sm:flex-wrap sm:items-center">
                    <a
                      href={`/reservations/create?facilityId=${encodeURIComponent(
                        String(facility.id),
                      )}&facilityName=${encodeURIComponent(facility.name)}`}
                      className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white transition hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-600/25"
                    >
                      <CalendarPlus size={15} />
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
                          className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-xs font-medium text-slate-700 transition hover:border-emerald-300 hover:text-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-600/20"
                        >
                          <Navigation size={15} />
                          Navigate to Facility
                        </a>
                      )}

                    <span className="inline-flex w-fit items-center gap-2 rounded-xl bg-slate-50 px-3.5 py-2.5 text-[11px] font-medium text-slate-600">
                      <ParkingCircle size={14} />

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
    <div className="rounded-2xl border border-slate-200/80 bg-white p-4 shadow-sm transition hover:border-emerald-200">
      <div className="grid h-9 w-9 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
        <Icon size={18} />
      </div>

      <div className="mt-4 text-xl font-semibold tracking-tight text-slate-900">
        {value}
      </div>

      <div className="mt-1 text-xs font-medium text-slate-500">{label}</div>

      <div className="mt-2.5 text-[11px] leading-4 text-emerald-700">
        {note}
      </div>
    </div>
  );
}

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
    <div className="rounded-xl bg-slate-50 p-3.5">
      <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-400">
        <ParkingCircle size={14} />
        Live availability
      </div>

      {hasData ? (
        <>
          <div className="mt-2 flex items-end justify-between gap-3">
            <div>
              <p className="text-sm font-semibold text-slate-800">
                {available} available
              </p>

              <p className="mt-0.5 text-[11px] text-slate-500">
                {occupied} occupied of {total}
              </p>
            </div>

            <span className="text-[11px] font-medium text-emerald-600">
              {occupancyPercent}% occupied
            </span>
          </div>

          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-emerald-500 transition-all"
              style={{ width: `${occupancyPercent}%` }}
            />
          </div>
        </>
      ) : (
        <p className="mt-2 text-xs font-medium text-slate-500">
          Live availability data unavailable
        </p>
      )}
    </div>
  );
}

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
    <div className="min-w-0 rounded-xl bg-slate-50 p-3.5">
      <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.12em] text-slate-400">
        <Icon size={14} />
        {label}
      </div>

      <p className="mt-2 break-words text-xs font-medium leading-5 text-slate-700">
        {value}
      </p>
    </div>
  );
}
