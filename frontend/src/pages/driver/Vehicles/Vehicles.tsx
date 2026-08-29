import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import {
  CarFront,
  CheckCircle2,
  CircleDot,
  Edit3,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Star,
  ToggleLeft,
  ToggleRight,
  XCircle,
} from "lucide-react";

import { useAuth } from "../../../auth/AuthContext";
import { api } from "../../../api";
import { Card, Metric, default as Page } from "../../../components/common/Page";

// ==========================================================
// Types
// ==========================================================

interface Vehicle {
  id: number;
  customer_id?: number | null;

  plate_country: string;
  registration_number: string;

  nickname: string | null;

  make: string;
  model: string;

  colour: string | null;

  year: number | null;

  vehicle_type: string;

  parking_profile: string | null;

  is_default: boolean;
  is_active: boolean;

  created_at?: string;
  updated_at?: string;
}

interface VehicleListResponse {
  vehicles: Vehicle[];
  total: number;
}

// ==========================================================
// Constants
// ==========================================================

const VEHICLE_TYPE_LABELS: Record<string, string> = {
  CAR: "Car",
  SUV: "SUV",
  TRUCK: "Truck",
  MOTORCYCLE: "Motorcycle",
  BUS: "Bus",
  ANY: "Any",
};

const VEHICLE_PROFILE_LABELS: Record<string, string> = {
  STANDARD: "Standard",
  COMPACT: "Compact",
  LARGE: "Large",
  MOTORCYCLE: "Motorcycle",
  HEAVY: "Heavy Vehicle",
  BUS: "Bus",
  SUV: "SUV",
  CAR: "Car",
};

// ==========================================================
// Component
// ==========================================================

export default function Vehicles() {
  const { user } = useAuth();
  const navigate = useNavigate();

  // --------------------------------------------------------
  // State
  // --------------------------------------------------------

  const [vehicles, setVehicles] = useState<Vehicle[]>([]);

  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const [searchTerm, setSearchTerm] = useState("");

  const [processingVehicleId, setProcessingVehicleId] = useState<number | null>(
    null,
  );

  const [showInactive, setShowInactive] = useState(true);

  // ========================================================
  // Helpers
  // ========================================================

  const extractErrorMessage = (err: any) => {
    const detail = err?.response?.data?.detail;

    if (typeof detail === "string") {
      return detail;
    }

    if (Array.isArray(detail)) {
      return detail
        .map((item: any) => {
          if (typeof item === "string") {
            return item;
          }

          return item?.msg ?? "Validation error";
        })
        .join(", ");
    }

    if (typeof err?.response?.data?.message === "string") {
      return err.response.data.message;
    }

    if (typeof err?.message === "string") {
      return err.message;
    }

    return "An unexpected error occurred while processing the vehicle.";
  };

  const formatVehicleType = (vehicleType: string | null | undefined) => {
    if (!vehicleType) {
      return "Vehicle";
    }

    const normalized = String(vehicleType).toUpperCase();

    return (
      VEHICLE_TYPE_LABELS[normalized] ??
      normalized
        .replace(/_/g, " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase())
    );
  };

  const formatParkingProfile = (profile: string | null | undefined) => {
    if (!profile) {
      return "Standard";
    }

    const normalized = String(profile).toUpperCase();

    return (
      VEHICLE_PROFILE_LABELS[normalized] ??
      normalized
        .replace(/_/g, " ")
        .replace(/\b\w/g, (letter) => letter.toUpperCase())
    );
  };

  const formatDate = (value: string | null | undefined) => {
    if (!value) {
      return "—";
    }

    const date = new Date(value);

    if (Number.isNaN(date.getTime())) {
      return "—";
    }

    return new Intl.DateTimeFormat("en-KE", {
      dateStyle: "medium",
    }).format(date);
  };

  // ========================================================
  // Load Vehicles
  // ========================================================

  const loadVehicles = useCallback(
    async (manualRefresh = false) => {
      if (!user?.id) {
        setVehicles([]);
        setLoading(false);
        return;
      }

      if (manualRefresh) {
        setIsRefreshing(true);
      } else {
        setLoading(true);
      }

      setError(null);

      try {
        /*
         * The existing SmartPark AI vehicle API returns:
         *
         * {
         *   vehicles: Vehicle[],
         *   total: number
         * }
         *
         * We deliberately load ALL customer vehicles here,
         * including inactive vehicles, because inactive vehicles
         * are retained for historical purposes.
         */
        const response = await api.get<VehicleListResponse>("/vehicles");

        setVehicles(response.data?.vehicles ?? []);
      } catch (err) {
        console.error("[SmartPark Vehicles] Failed to load vehicles:", err);

        setError(
          extractErrorMessage(err) ||
            "Unable to load your vehicles from the SmartPark AI backend.",
        );
      } finally {
        setLoading(false);
        setIsRefreshing(false);
      }
    },
    [user?.id],
  );

  // ========================================================
  // Initial Load
  // ========================================================

  useEffect(() => {
    void loadVehicles();
  }, [loadVehicles]);

  // ========================================================
  // Clear Success Message
  // ========================================================

  useEffect(() => {
    if (!successMessage) {
      return;
    }

    const timer = window.setTimeout(() => {
      setSuccessMessage(null);
    }, 4500);

    return () => {
      window.clearTimeout(timer);
    };
  }, [successMessage]);

  // ========================================================
  // Search / Filtering
  // ========================================================

  const filteredVehicles = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();

    const normalizedVehicles = showInactive
      ? vehicles
      : vehicles.filter((vehicle) => vehicle.is_active);

    if (!query) {
      return [...normalizedVehicles].sort((a, b) => {
        /*
         * Default vehicle first.
         * Active vehicles before inactive vehicles.
         */
        if (a.is_default !== b.is_default) {
          return a.is_default ? -1 : 1;
        }

        if (a.is_active !== b.is_active) {
          return a.is_active ? -1 : 1;
        }

        return a.registration_number.localeCompare(b.registration_number);
      });
    }

    /*
     * Intelligent multi-field search.
     *
     * Examples:
     *   KDA
     *   KDA 123A
     *   Toyota
     *   Corolla
     *   SUV
     *   blue
     *   default
     *   inactive
     */
    const tokens = query
      .split(/\s+/)
      .map((token) => token.trim())
      .filter(Boolean);

    return normalizedVehicles
      .filter((vehicle) => {
        const searchableText = [
          vehicle.registration_number,
          vehicle.plate_country,
          vehicle.nickname,
          vehicle.make,
          vehicle.model,
          vehicle.colour,
          vehicle.year,
          vehicle.vehicle_type,
          formatVehicleType(vehicle.vehicle_type),
          vehicle.parking_profile,
          formatParkingProfile(vehicle.parking_profile),
          vehicle.is_default ? "default" : "",
          vehicle.is_active ? "active" : "inactive",
          vehicle.is_active ? "enabled" : "disabled",
        ]
          .filter(
            (value) => value !== null && value !== undefined && value !== "",
          )
          .join(" ")
          .toLowerCase();

        /*
         * Every search token must be present.
         *
         * Therefore:
         * "toyota suv"
         *
         * matches a Toyota SUV but not a Toyota sedan
         * or a Nissan SUV.
         */
        return tokens.every((token) => searchableText.includes(token));
      })
      .sort((a, b) => {
        if (a.is_default !== b.is_default) {
          return a.is_default ? -1 : 1;
        }

        if (a.is_active !== b.is_active) {
          return a.is_active ? -1 : 1;
        }

        return a.registration_number.localeCompare(b.registration_number);
      });
  }, [vehicles, searchTerm, showInactive]);

  // ========================================================
  // Summary
  // ========================================================

  const activeVehicles = useMemo(
    () => vehicles.filter((vehicle) => vehicle.is_active).length,
    [vehicles],
  );

  const inactiveVehicles = useMemo(
    () => vehicles.filter((vehicle) => !vehicle.is_active).length,
    [vehicles],
  );

  const defaultVehicle = useMemo(
    () =>
      vehicles.find((vehicle) => vehicle.is_default && vehicle.is_active) ??
      null,
    [vehicles],
  );

  // ========================================================
  // Set Default Vehicle
  // ========================================================

  const setDefaultVehicle = async (vehicle: Vehicle) => {
    if (!user?.id) {
      return;
    }

    if (!vehicle.is_active) {
      setError("Inactive vehicles cannot be set as the default vehicle.");
      return;
    }

    if (vehicle.is_default) {
      return;
    }

    setProcessingVehicleId(vehicle.id);
    setError(null);
    setSuccessMessage(null);

    try {
      const response = await api.patch<Vehicle>(
        `/vehicles/${vehicle.id}/default`,
      );

      const updatedVehicle = response.data;

      /*
       * Update the local state immediately.
       *
       * The backend removes default status from the
       * customer's previous default vehicle.
       */
      setVehicles((current) =>
        current.map((item) => {
          if (item.id === updatedVehicle.id) {
            return updatedVehicle;
          }

          return {
            ...item,
            is_default: updatedVehicle.is_default ? false : item.is_default,
          };
        }),
      );

      setSuccessMessage(
        `${vehicle.registration_number} is now your default vehicle.`,
      );
    } catch (err) {
      console.error("[SmartPark Vehicles] Failed to set default vehicle:", err);

      setError(
        extractErrorMessage(err) ||
          "Unable to set this vehicle as your default vehicle.",
      );
    } finally {
      setProcessingVehicleId(null);
    }
  };

  // ========================================================
  // Deactivate Vehicle
  // ========================================================

  const deactivateVehicle = async (vehicle: Vehicle) => {
    if (!user?.id) {
      return;
    }

    const confirmed = window.confirm(
      `Deactivate vehicle ${vehicle.registration_number}?\n\nThe vehicle will be retained for historical reservations, but it will no longer be available for new reservations.`,
    );

    if (!confirmed) {
      return;
    }

    setProcessingVehicleId(vehicle.id);
    setError(null);
    setSuccessMessage(null);

    try {
      const response = await api.patch<Vehicle>(
        `/vehicles/${vehicle.id}/deactivate`,
      );

      const updatedVehicle = response.data;

      setVehicles((current) =>
        current.map((item) =>
          item.id === updatedVehicle.id ? updatedVehicle : item,
        ),
      );

      setSuccessMessage(`${vehicle.registration_number} has been deactivated.`);
    } catch (err) {
      console.error("[SmartPark Vehicles] Failed to deactivate vehicle:", err);

      setError(
        extractErrorMessage(err) || "Unable to deactivate this vehicle.",
      );
    } finally {
      setProcessingVehicleId(null);
    }
  };

  // ========================================================
  // Activate Vehicle
  // ========================================================

  const activateVehicle = async (vehicle: Vehicle) => {
    if (!user?.id) {
      return;
    }

    setProcessingVehicleId(vehicle.id);
    setError(null);
    setSuccessMessage(null);

    try {
      const response = await api.patch<Vehicle>(
        `/vehicles/${vehicle.id}/activate`,
      );

      const updatedVehicle = response.data;

      setVehicles((current) =>
        current.map((item) =>
          item.id === updatedVehicle.id ? updatedVehicle : item,
        ),
      );

      setSuccessMessage(
        `${vehicle.registration_number} has been activated and is available for new reservations.`,
      );
    } catch (err) {
      console.error("[SmartPark Vehicles] Failed to activate vehicle:", err);

      setError(extractErrorMessage(err) || "Unable to activate this vehicle.");
    } finally {
      setProcessingVehicleId(null);
    }
  };

  // ========================================================
  // Refresh
  // ========================================================

  const handleRefresh = async () => {
    setSuccessMessage(null);
    await loadVehicles(true);
  };

  // ========================================================
  // Render
  // ========================================================

  return (
    <div className="space-y-6">
      {/* ====================================================
          PAGE HEADER
      ==================================================== */}

      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <Page
          title="My Vehicles"
          text="Manage the vehicles you use for SmartPark AI parking reservations."
        />

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => void handleRefresh()}
            disabled={loading || isRefreshing}
            className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshCw
              size={16}
              className={isRefreshing ? "animate-spin" : ""}
            />

            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>

          <Link
            to="/vehicles/create"
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white shadow-sm transition hover:bg-emerald-700"
          >
            <Plus size={17} />
            Add Vehicle
          </Link>
        </div>
      </div>

      {/* ====================================================
          SUCCESS TOAST
      ==================================================== */}

      {successMessage && (
        <div className="fixed left-1/2 top-1/2 z-[100] w-[min(92vw,480px)] -translate-x-1/2 -translate-y-1/2">
          <div className="rounded-2xl border border-emerald-200 bg-white px-6 py-5 text-center shadow-2xl ring-1 ring-black/5">
            <div className="mx-auto grid h-12 w-12 place-items-center rounded-full bg-emerald-100 text-emerald-600">
              <CheckCircle2 size={25} />
            </div>

            <h3 className="mt-3 text-base font-extrabold text-slate-900">
              Success
            </h3>

            <p className="mt-1 text-sm text-slate-600">{successMessage}</p>
          </div>
        </div>
      )}

      {/* ====================================================
          ERROR
      ==================================================== */}

      {error && (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4">
          <div className="flex items-start gap-3">
            <XCircle size={19} className="mt-0.5 shrink-0 text-rose-600" />

            <div className="min-w-0">
              <p className="text-sm font-extrabold text-rose-900">
                Unable to complete request
              </p>

              <p className="mt-1 text-sm leading-6 text-rose-800">{error}</p>
            </div>

            <button
              type="button"
              onClick={() => setError(null)}
              className="ml-auto shrink-0 text-xs font-bold text-rose-700 hover:text-rose-900"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* ====================================================
          METRICS
      ==================================================== */}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Total Vehicles"
          value={loading ? "…" : String(vehicles.length)}
          note="Registered to your profile"
          Icon={CarFront}
        />

        <Metric
          label="Active"
          value={loading ? "…" : String(activeVehicles)}
          note="Available for reservations"
          Icon={CheckCircle2}
        />

        <Metric
          label="Inactive"
          value={loading ? "…" : String(inactiveVehicles)}
          note="Retained for history"
          Icon={CircleDot}
        />

        <Metric
          label="Default"
          value={
            loading
              ? "…"
              : defaultVehicle
                ? defaultVehicle.registration_number
                : "None"
          }
          note={
            defaultVehicle
              ? `${defaultVehicle.make} ${defaultVehicle.model}`
              : "Select an active vehicle"
          }
          Icon={Star}
        />
      </div>

      {/* ====================================================
          VEHICLES CARD
      ==================================================== */}

      <Card
        title="Your Vehicles"
        sub="Active and historical vehicles associated with your SmartPark AI account."
      >
        {/* ==================================================
            SEARCH / FILTER BAR
        ================================================== */}

        <div className="mb-6 flex flex-col gap-3 lg:flex-row lg:items-center">
          <div className="relative min-w-0 flex-1">
            <Search
              size={18}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />

            <input
              type="search"
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="Search registration, make, model, type, colour, profile..."
              aria-label="Search vehicles"
              className="w-full rounded-xl border border-slate-200 bg-white py-3 pl-10 pr-4 text-sm font-medium outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
            />
          </div>

          <button
            type="button"
            onClick={() => setShowInactive((current) => !current)}
            className={`inline-flex items-center justify-center gap-2 rounded-xl border px-4 py-3 text-sm font-bold transition ${
              showInactive
                ? "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                : "border-emerald-200 bg-emerald-50 text-emerald-700"
            }`}
          >
            {showInactive ? (
              <ToggleRight size={18} />
            ) : (
              <ToggleLeft size={18} />
            )}

            {showInactive ? "Showing inactive" : "Active vehicles only"}
          </button>

          {searchTerm.trim() && (
            <button
              type="button"
              onClick={() => setSearchTerm("")}
              className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold text-slate-600 transition hover:bg-slate-50"
            >
              Clear
            </button>
          )}
        </div>

        {!loading && (
          <div className="mb-5 flex flex-wrap items-center justify-between gap-2 text-xs font-semibold text-slate-500">
            <span>
              Showing {filteredVehicles.length} of {vehicles.length} vehicle
              {vehicles.length === 1 ? "" : "s"}
            </span>

            {searchTerm.trim() && <span>Search: "{searchTerm.trim()}"</span>}
          </div>
        )}

        {/* ==================================================
            LOADING
        ================================================== */}

        {loading ? (
          <div className="grid gap-5 md:grid-cols-2">
            {[1, 2, 3, 4].map((item) => (
              <div
                key={item}
                className="animate-pulse rounded-2xl border border-slate-200 bg-white p-5"
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-3">
                    <div className="h-12 w-12 rounded-xl bg-slate-200" />

                    <div className="space-y-2">
                      <div className="h-5 w-32 rounded bg-slate-200" />
                      <div className="h-4 w-44 rounded bg-slate-200" />
                    </div>
                  </div>

                  <div className="h-6 w-20 rounded-full bg-slate-200" />
                </div>

                <div className="mt-5 grid grid-cols-2 gap-3">
                  <div className="h-16 rounded-xl bg-slate-100" />
                  <div className="h-16 rounded-xl bg-slate-100" />
                  <div className="h-16 rounded-xl bg-slate-100" />
                  <div className="h-16 rounded-xl bg-slate-100" />
                </div>

                <div className="mt-5 h-10 rounded-xl bg-slate-200" />
              </div>
            ))}
          </div>
        ) : vehicles.length === 0 ? (
          /* ==================================================
             EMPTY STATE
          ================================================== */

          <div className="rounded-2xl bg-slate-50 px-6 py-14 text-center">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
              <CarFront size={31} />
            </div>

            <h3 className="mt-5 text-lg font-extrabold text-slate-900">
              No vehicles registered
            </h3>

            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
              Add your first vehicle to make parking reservations faster and
              easier.
            </p>

            <Link
              to="/vehicles/create"
              className="mt-6 inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white transition hover:bg-emerald-700"
            >
              <Plus size={17} />
              Add Your First Vehicle
            </Link>
          </div>
        ) : filteredVehicles.length === 0 ? (
          /* ==================================================
             NO SEARCH RESULTS
          ================================================== */

          <div className="rounded-2xl bg-slate-50 px-6 py-14 text-center">
            <div className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-white text-slate-400 shadow-sm ring-1 ring-slate-200">
              <Search size={30} />
            </div>

            <h3 className="mt-5 text-lg font-extrabold text-slate-900">
              No matching vehicles
            </h3>

            <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
              Try another registration number, make, model, vehicle type, colour
              or parking profile.
            </p>

            <button
              type="button"
              onClick={() => setSearchTerm("")}
              className="mt-6 rounded-xl bg-emerald-600 px-5 py-3 text-sm font-extrabold text-white transition hover:bg-emerald-700"
            >
              Clear Search
            </button>
          </div>
        ) : (
          /* ==================================================
             VEHICLE LIST
          ================================================== */

          <div className="grid gap-5 md:grid-cols-2">
            {filteredVehicles.map((vehicle) => {
              const isProcessing = processingVehicleId === vehicle.id;

              return (
                <article
                  key={vehicle.id}
                  className={`relative overflow-hidden rounded-2xl border bg-white p-5 shadow-sm transition ${
                    vehicle.is_active
                      ? "border-slate-200 hover:border-emerald-200 hover:shadow-md"
                      : "border-slate-200 bg-slate-50/70 opacity-90"
                  }`}
                >
                  {/* ========================================
                        DEFAULT ACCENT
                    ======================================== */}

                  {vehicle.is_default && vehicle.is_active && (
                    <div className="absolute right-0 top-0">
                      <div className="rounded-bl-xl bg-amber-400 px-3 py-1.5 text-[11px] font-black text-amber-950">
                        DEFAULT
                      </div>
                    </div>
                  )}

                  {/* ========================================
                        VEHICLE HEADER
                    ======================================== */}

                  <div className="flex items-start justify-between gap-4">
                    <div className="flex min-w-0 items-center gap-3">
                      <div
                        className={`grid h-12 w-12 shrink-0 place-items-center rounded-xl ${
                          vehicle.is_active
                            ? "bg-emerald-50 text-emerald-600"
                            : "bg-slate-200 text-slate-500"
                        }`}
                      >
                        <CarFront size={25} />
                      </div>

                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <h3 className="truncate text-lg font-black tracking-tight text-slate-900">
                            {vehicle.registration_number}
                          </h3>

                          {vehicle.is_default && vehicle.is_active && (
                            <Star
                              size={15}
                              className="fill-current text-amber-500"
                            />
                          )}
                        </div>

                        <p className="mt-0.5 truncate text-sm font-semibold text-slate-500">
                          {vehicle.nickname ||
                            `${vehicle.make} ${vehicle.model}`}
                        </p>
                      </div>
                    </div>

                    {/* ========================================
                          STATUS
                      ======================================== */}

                    <span
                      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-extrabold ${
                        vehicle.is_active
                          ? "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200"
                          : "bg-slate-200 text-slate-600 ring-1 ring-slate-300"
                      }`}
                    >
                      {vehicle.is_active ? (
                        <CheckCircle2 size={13} />
                      ) : (
                        <CircleDot size={13} />
                      )}

                      {vehicle.is_active ? "Active" : "Inactive"}
                    </span>
                  </div>

                  {/* ========================================
                        VEHICLE DETAILS
                    ======================================== */}

                  <div className="mt-5 grid grid-cols-2 gap-3">
                    <div className="rounded-xl bg-slate-50 p-3.5">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        Make & Model
                      </p>

                      <p className="mt-1 text-sm font-extrabold text-slate-900">
                        {vehicle.make || "—"} {vehicle.model || ""}
                      </p>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-3.5">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        Type
                      </p>

                      <p className="mt-1 text-sm font-extrabold text-slate-900">
                        {formatVehicleType(vehicle.vehicle_type)}
                      </p>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-3.5">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        Colour
                      </p>

                      <p className="mt-1 text-sm font-extrabold text-slate-900">
                        {vehicle.colour || "—"}
                      </p>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-3.5">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        Year
                      </p>

                      <p className="mt-1 text-sm font-extrabold text-slate-900">
                        {vehicle.year ?? "—"}
                      </p>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-3.5">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        Plate Country
                      </p>

                      <p className="mt-1 text-sm font-extrabold text-slate-900">
                        {vehicle.plate_country || "—"}
                      </p>
                    </div>

                    <div className="rounded-xl bg-slate-50 p-3.5">
                      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                        Parking Profile
                      </p>

                      <p className="mt-1 text-sm font-extrabold text-slate-900">
                        {formatParkingProfile(vehicle.parking_profile)}
                      </p>
                    </div>
                  </div>

                  {/* ========================================
                        ACTIVE VEHICLE INFO
                    ======================================== */}

                  {vehicle.is_active && (
                    <div className="mt-4 flex items-start gap-3 rounded-xl border border-emerald-100 bg-emerald-50 px-4 py-3">
                      <ShieldCheck
                        size={17}
                        className="mt-0.5 shrink-0 text-emerald-600"
                      />

                      <p className="text-xs leading-5 text-emerald-800">
                        This vehicle is available for new SmartPark AI
                        reservations.
                      </p>
                    </div>
                  )}

                  {/* ========================================
                        INACTIVE VEHICLE INFO
                    ======================================== */}

                  {!vehicle.is_active && (
                    <div className="mt-4 flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-100 px-4 py-3">
                      <CircleDot
                        size={17}
                        className="mt-0.5 shrink-0 text-slate-500"
                      />

                      <p className="text-xs leading-5 text-slate-600">
                        This vehicle is inactive and cannot currently be used
                        for new reservations. Its record is retained for
                        historical parking records.
                      </p>
                    </div>
                  )}

                  {/* ========================================
                        ACTIONS
                    ======================================== */}

                  <div className="mt-5 flex flex-col gap-2 border-t border-slate-100 pt-4 sm:flex-row sm:flex-wrap">
                    {/* ----------------------------------------
                          EDIT
                      ---------------------------------------- */}

                    {vehicle.is_active && (
                      <button
                        type="button"
                        onClick={() => navigate(`/vehicles/${vehicle.id}/edit`)}
                        disabled={isProcessing}
                        className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-bold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <Edit3 size={15} />
                        Edit
                      </button>
                    )}

                    {/* ----------------------------------------
                          SET DEFAULT
                      ---------------------------------------- */}

                    {vehicle.is_active && !vehicle.is_default && (
                      <button
                        type="button"
                        onClick={() => void setDefaultVehicle(vehicle)}
                        disabled={isProcessing}
                        className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm font-bold text-amber-700 transition hover:border-amber-300 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isProcessing ? (
                          <RefreshCw size={15} className="animate-spin" />
                        ) : (
                          <Star size={15} />
                        )}
                        Set Default
                      </button>
                    )}

                    {/* ----------------------------------------
                          DEFAULT LABEL
                      ---------------------------------------- */}

                    {vehicle.is_active && vehicle.is_default && (
                      <div className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm font-bold text-amber-700">
                        <Star size={15} className="fill-current" />
                        Default Vehicle
                      </div>
                    )}

                    {/* ----------------------------------------
                          DEACTIVATE
                      ---------------------------------------- */}

                    {vehicle.is_active && (
                      <button
                        type="button"
                        onClick={() => void deactivateVehicle(vehicle)}
                        disabled={isProcessing}
                        className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-rose-200 bg-rose-50 px-4 py-2.5 text-sm font-bold text-rose-700 transition hover:border-rose-300 hover:bg-rose-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isProcessing ? (
                          <RefreshCw size={15} className="animate-spin" />
                        ) : (
                          <ToggleLeft size={16} />
                        )}
                        Deactivate
                      </button>
                    )}

                    {/* ----------------------------------------
                          ACTIVATE
                      ---------------------------------------- */}

                    {!vehicle.is_active && (
                      <button
                        type="button"
                        onClick={() => void activateVehicle(vehicle)}
                        disabled={isProcessing}
                        className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-2.5 text-sm font-bold text-emerald-700 transition hover:border-emerald-300 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {isProcessing ? (
                          <RefreshCw size={15} className="animate-spin" />
                        ) : (
                          <ToggleRight size={16} />
                        )}
                        Activate
                      </button>
                    )}
                  </div>

                  {/* ========================================
                        CREATED / UPDATED
                    ======================================== */}

                  {vehicle.created_at && (
                    <p className="mt-3 text-right text-[11px] font-medium text-slate-400">
                      Added {formatDate(vehicle.created_at)}
                    </p>
                  )}
                </article>
              );
            })}
          </div>
        )}

        {/* ==================================================
            FOOTER INFORMATION
        ================================================== */}

        {!loading && vehicles.length > 0 && (
          <div className="mt-6 rounded-2xl border border-slate-100 bg-slate-50 px-5 py-4">
            <div className="flex items-start gap-3">
              <ShieldCheck
                size={18}
                className="mt-0.5 shrink-0 text-emerald-600"
              />

              <div>
                <p className="text-sm font-extrabold text-slate-800">
                  Vehicle management
                </p>

                <p className="mt-1 text-xs leading-5 text-slate-600">
                  Your default vehicle is automatically preferred when creating
                  a new parking reservation. Inactive vehicles remain in your
                  history but are not available for new reservations.
                </p>
              </div>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
