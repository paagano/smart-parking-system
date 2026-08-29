import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import {
  ArrowLeft,
  CarFront,
  CheckCircle2,
  Info,
  Loader2,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import { api } from "../../../api";

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

// ==========================================================
// Form Type
// ==========================================================

interface VehicleForm {
  plate_country: string;
  registration_number: string;
  nickname: string;
  make: string;
  model: string;
  colour: string;
  year: string;
  vehicle_type: string;
  parking_profile: string;
  is_default: boolean;
}

// ==========================================================
// Vehicle Types
// ==========================================================

const VEHICLE_TYPES = [
  {
    value: "CAR",
    label: "Car",
    description: "Standard passenger car",
  },
  {
    value: "SUV",
    label: "SUV",
    description: "Sport utility vehicle",
  },
  {
    value: "TRUCK",
    label: "Truck",
    description: "Pickup or commercial truck",
  },
  {
    value: "MOTORCYCLE",
    label: "Motorcycle",
    description: "Motorcycle or similar two-wheeler",
  },
  {
    value: "BUS",
    label: "Bus",
    description: "Bus or passenger transport vehicle",
  },
  {
    value: "ANY",
    label: "Any",
    description: "General vehicle classification",
  },
] as const;

// ==========================================================
// Parking Profiles
// ==========================================================

const PARKING_PROFILES = [
  {
    value: "STANDARD",
    label: "Standard",
    description: "Normal parking requirements",
  },
  {
    value: "ELECTRIC",
    label: "Electric",
    description: "Vehicle requiring EV charging facilities",
  },
  {
    value: "ACCESSIBLE",
    label: "Accessible",
    description: "Vehicle requiring accessible parking facilities",
  },
  {
    value: "VIP",
    label: "VIP",
    description: "Vehicle associated with VIP parking privileges",
  },
  {
    value: "COMMERCIAL",
    label: "Commercial",
    description: "Commercial or business vehicle",
  },
  {
    value: "EMERGENCY",
    label: "Emergency",
    description: "Emergency-response vehicle",
  },
] as const;

// ==========================================================
// Helpers
// ==========================================================

const currentYear = new Date().getFullYear();

const minimumYear = 1950;

function emptyForm(): VehicleForm {
  return {
    plate_country: "KE",
    registration_number: "",
    nickname: "",
    make: "",
    model: "",
    colour: "",
    year: "",
    vehicle_type: "CAR",
    parking_profile: "STANDARD",
    is_default: false,
  };
}

// ==========================================================
// Component
// ==========================================================

export default function EditVehicle() {
  const navigate = useNavigate();

  const { vehicleId } = useParams<{
    vehicleId: string;
  }>();

  // --------------------------------------------------------
  // State
  // --------------------------------------------------------

  const [vehicle, setVehicle] = useState<Vehicle | null>(null);

  const [form, setForm] = useState<VehicleForm>(emptyForm());

  const [loading, setLoading] = useState(true);

  const [isSubmitting, setIsSubmitting] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [success, setSuccess] = useState<Vehicle | null>(null);

  // ========================================================
  // Load Vehicle
  // ========================================================

  useEffect(() => {
    let cancelled = false;

    const loadVehicle = async () => {
      if (!vehicleId) {
        setError("No vehicle ID was provided.");
        setLoading(false);
        return;
      }

      const numericVehicleId = Number(vehicleId);

      if (!Number.isInteger(numericVehicleId) || numericVehicleId <= 0) {
        setError("The vehicle ID is invalid.");
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);

      try {
        /*
         * GET /vehicles/{vehicle_id}
         *
         * The backend determines the authenticated
         * customer from the JWT.
         */
        const response = await api.get<Vehicle>(
          `/vehicles/${numericVehicleId}`,
        );

        if (cancelled) {
          return;
        }

        const loadedVehicle = response.data;

        /*
         * Only active vehicles can be edited
         * by the backend service.
         */
        if (loadedVehicle.is_active === false) {
          setError("Inactive vehicles cannot be edited.");
          setVehicle(loadedVehicle);
          return;
        }

        setVehicle(loadedVehicle);

        setForm({
          plate_country: loadedVehicle.plate_country ?? "KE",

          registration_number: loadedVehicle.registration_number ?? "",

          nickname: loadedVehicle.nickname ?? "",

          make: loadedVehicle.make ?? "",

          model: loadedVehicle.model ?? "",

          colour: loadedVehicle.colour ?? "",

          year: loadedVehicle.year != null ? String(loadedVehicle.year) : "",

          vehicle_type: loadedVehicle.vehicle_type ?? "CAR",

          parking_profile: loadedVehicle.parking_profile ?? "STANDARD",

          is_default: Boolean(loadedVehicle.is_default),
        });
      } catch (err: any) {
        console.error("[SmartPark Edit Vehicle] Failed to load vehicle:", err);

        if (cancelled) {
          return;
        }

        setError(extractErrorMessage(err));
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void loadVehicle();

    return () => {
      cancelled = true;
    };
  }, [vehicleId]);

  // ========================================================
  // Selected Vehicle Type
  // ========================================================

  const selectedVehicleType = useMemo(
    () => VEHICLE_TYPES.find((item) => item.value === form.vehicle_type),
    [form.vehicle_type],
  );

  // ========================================================
  // Selected Parking Profile
  // ========================================================

  const selectedParkingProfile = useMemo(
    () => PARKING_PROFILES.find((item) => item.value === form.parking_profile),
    [form.parking_profile],
  );

  // ========================================================
  // Update Field
  // ========================================================

  const updateField = <K extends keyof VehicleForm>(
    field: K,
    value: VehicleForm[K],
  ) => {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));

    if (error) {
      setError(null);
    }

    if (success) {
      setSuccess(null);
    }
  };

  // ========================================================
  // Registration Change
  // ========================================================

  const handleRegistrationChange = (value: string) => {
    /*
     * Match the backend's expected registration
     * character set.
     */
    const normalized = value.toUpperCase().replace(/[^A-Z0-9 -]/g, "");

    updateField("registration_number", normalized);
  };

  // ========================================================
  // Validation
  // ========================================================

  const validateForm = (): string | null => {
    const registration = form.registration_number.replace(/\s+/g, "").trim();

    if (!registration) {
      return "Vehicle registration number is required.";
    }

    if (registration.length < 3) {
      return "Vehicle registration number must contain at least 3 characters.";
    }

    if (registration.length > 20) {
      return "Vehicle registration number cannot exceed 20 characters.";
    }

    if (!form.plate_country.trim()) {
      return "Plate country is required.";
    }

    if (!form.make.trim()) {
      return "Vehicle make is required.";
    }

    if (!form.model.trim()) {
      return "Vehicle model is required.";
    }

    if (!form.vehicle_type) {
      return "Please select a vehicle type.";
    }

    if (!form.parking_profile) {
      return "Please select a parking profile.";
    }

    if (form.year.trim()) {
      const numericYear = Number(form.year);

      if (!Number.isInteger(numericYear)) {
        return "Vehicle year must be a valid year.";
      }

      if (numericYear < minimumYear || numericYear > currentYear + 1) {
        return `Vehicle year must be between ${minimumYear} and ${currentYear + 1}.`;
      }
    }

    return null;
  };

  // ========================================================
  // Submit
  // ========================================================

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (isSubmitting) {
      return;
    }

    if (!vehicle) {
      setError("Vehicle information is not available.");
      return;
    }

    if (!vehicleId) {
      setError("No vehicle ID was provided.");
      return;
    }

    setError(null);
    setSuccess(null);

    const validationError = validateForm();

    if (validationError) {
      setError(validationError);
      return;
    }

    setIsSubmitting(true);

    try {
      const numericVehicleId = Number(vehicleId);

      /*
       * VehicleUpdate is a partial-update schema,
       * but sending the complete editable state is
       * appropriate here because this screen represents
       * the complete vehicle profile.
       *
       * customer_id is deliberately NOT included.
       */
      const payload = {
        plate_country: form.plate_country.trim().toUpperCase(),

        registration_number: form.registration_number
          .replace(/\s+/g, "")
          .trim()
          .toUpperCase(),

        nickname: form.nickname.trim() || null,

        make: form.make.trim(),

        model: form.model.trim(),

        colour: form.colour.trim() || null,

        year: form.year.trim() ? Number(form.year) : null,

        vehicle_type: form.vehicle_type,

        parking_profile: form.parking_profile,

        is_default: form.is_default,
      };

      /*
       * PATCH /vehicles/{vehicle_id}
       */
      const response = await api.patch<Vehicle>(
        `/vehicles/${numericVehicleId}`,
        payload,
      );

      const updatedVehicle = response.data;

      setVehicle(updatedVehicle);

      setSuccess(updatedVehicle);
    } catch (err: any) {
      console.error("[SmartPark Edit Vehicle] Failed to update vehicle:", err);

      setError(extractErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  // ========================================================
  // Loading State
  // ========================================================

  if (loading) {
    return (
      <div className="mx-auto flex min-h-[420px] w-full max-w-4xl items-center justify-center">
        <div className="text-center">
          <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
            <Loader2 size={28} className="animate-spin" />
          </div>

          <h2 className="mt-5 text-lg font-black text-slate-900">
            Loading vehicle
          </h2>

          <p className="mt-1 text-sm text-slate-500">
            Retrieving your vehicle information...
          </p>
        </div>
      </div>
    );
  }

  // ========================================================
  // Error / Vehicle Not Found
  // ========================================================

  if (!vehicle && error) {
    return (
      <div className="mx-auto w-full max-w-3xl">
        <Link
          to="/vehicles"
          className="inline-flex items-center gap-2 text-sm font-bold text-slate-500 transition hover:text-emerald-600"
        >
          <ArrowLeft size={16} />
          Back to My Vehicles
        </Link>

        <div className="mt-6 rounded-3xl border border-rose-200 bg-white p-8 text-center shadow-sm sm:p-12">
          <div className="mx-auto grid h-16 w-16 place-items-center rounded-full bg-rose-50 text-rose-600">
            <XCircle size={34} />
          </div>

          <h1 className="mt-5 text-xl font-black text-slate-900">
            Unable to load vehicle
          </h1>

          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500">
            {error}
          </p>

          <Link
            to="/vehicles"
            className="mt-7 inline-flex items-center justify-center rounded-xl bg-emerald-600 px-6 py-3 text-sm font-extrabold text-white transition hover:bg-emerald-700"
          >
            Return to My Vehicles
          </Link>
        </div>
      </div>
    );
  }

  // ========================================================
  // Success State
  // ========================================================

  if (success) {
    return (
      <div className="mx-auto w-full max-w-3xl">
        <div className="rounded-3xl border border-emerald-200 bg-white p-8 text-center shadow-sm sm:p-12">
          <div className="mx-auto grid h-20 w-20 place-items-center rounded-full bg-emerald-50 text-emerald-600">
            <CheckCircle2 size={42} />
          </div>

          <h1 className="mt-6 text-2xl font-black tracking-tight text-slate-900">
            Vehicle Updated Successfully
          </h1>

          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">
            Your vehicle details have been successfully updated.
          </p>

          <div className="mx-auto mt-7 max-w-md rounded-2xl border border-slate-200 bg-slate-50 p-5 text-left">
            <div className="flex items-center gap-4">
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-emerald-100 text-emerald-600">
                <CarFront size={25} />
              </div>

              <div className="min-w-0">
                <p className="text-lg font-black tracking-tight text-slate-900">
                  {success.registration_number}
                </p>

                <p className="text-sm font-semibold text-slate-500">
                  {success.make} {success.model}
                </p>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-white p-3">
                <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                  Type
                </p>

                <p className="mt-1 text-sm font-extrabold text-slate-800">
                  {VEHICLE_TYPES.find(
                    (item) => item.value === success.vehicle_type,
                  )?.label ?? success.vehicle_type}
                </p>
              </div>

              <div className="rounded-xl bg-white p-3">
                <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
                  Status
                </p>

                <p className="mt-1 text-sm font-extrabold text-emerald-700">
                  {success.is_active ? "Active" : "Inactive"}
                </p>
              </div>
            </div>

            {success.is_default && (
              <div className="mt-3 flex items-center gap-2 rounded-xl bg-amber-50 px-3 py-2.5 text-xs font-bold text-amber-700">
                <CheckCircle2 size={15} />
                This is your default vehicle.
              </div>
            )}
          </div>

          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <Link
              to="/vehicles"
              className="inline-flex items-center justify-center rounded-xl bg-emerald-600 px-6 py-3 text-sm font-extrabold text-white transition hover:bg-emerald-700"
            >
              View My Vehicles
            </Link>

            <button
              type="button"
              onClick={() => setSuccess(null)}
              className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-6 py-3 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50"
            >
              Continue Editing
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ========================================================
  // Main Form
  // ========================================================

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6">
      {/* ====================================================
          HEADER
      ==================================================== */}

      <div>
        <Link
          to="/vehicles"
          className="inline-flex items-center gap-2 text-sm font-bold text-slate-500 transition hover:text-emerald-600"
        >
          <ArrowLeft size={16} />
          Back to My Vehicles
        </Link>

        <div className="mt-4 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
            <CarFront size={24} />
          </div>

          <div>
            <h1 className="text-2xl font-black tracking-tight text-slate-900">
              Edit Vehicle
            </h1>

            <p className="mt-0.5 text-sm font-medium text-slate-500">
              Update your SmartPark AI vehicle details.
            </p>
          </div>
        </div>
      </div>

      {/* ====================================================
          CURRENT VEHICLE BADGE
      ==================================================== */}

      {vehicle && (
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-center gap-4">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-600">
              <CarFront size={24} />
            </div>

            <div className="min-w-0 flex-1">
              <p className="text-xs font-bold uppercase tracking-wide text-slate-400">
                Editing vehicle
              </p>

              <p className="mt-1 text-lg font-black tracking-wide text-slate-900">
                {vehicle.registration_number}
              </p>

              <p className="text-sm font-semibold text-slate-500">
                {vehicle.make} {vehicle.model}
              </p>
            </div>

            {vehicle.is_default && (
              <span className="hidden items-center gap-1.5 rounded-full bg-amber-50 px-3 py-1.5 text-xs font-extrabold text-amber-700 sm:inline-flex">
                <ShieldCheck size={14} />
                Default
              </span>
            )}
          </div>
        </div>
      )}

      {/* ====================================================
          ERROR
      ==================================================== */}

      {error && (
        <div
          role="alert"
          className="rounded-2xl border border-rose-200 bg-rose-50 px-5 py-4"
        >
          <div className="flex items-start gap-3">
            <XCircle size={20} className="mt-0.5 shrink-0 text-rose-600" />

            <div className="min-w-0 flex-1">
              <p className="text-sm font-extrabold text-rose-900">
                Unable to update vehicle
              </p>

              <p className="mt-1 text-sm leading-6 text-rose-800">{error}</p>
            </div>

            <button
              type="button"
              onClick={() => setError(null)}
              aria-label="Dismiss error"
              className="shrink-0 text-rose-500 transition hover:text-rose-700"
            >
              <XCircle size={17} />
            </button>
          </div>
        </div>
      )}

      {/* ====================================================
          INFORMATION
      ==================================================== */}

      <div className="rounded-2xl border border-blue-100 bg-blue-50 px-5 py-4">
        <div className="flex items-start gap-3">
          <Info size={19} className="mt-0.5 shrink-0 text-blue-600" />

          <div>
            <p className="text-sm font-extrabold text-blue-900">
              Registration number
            </p>

            <p className="mt-1 text-xs leading-5 text-blue-800">
              Registration numbers are normalized by SmartPark AI. The backend
              will convert the registration to uppercase and check that it is
              not already registered to another vehicle.
            </p>
          </div>
        </div>
      </div>

      {/* ====================================================
          FORM
      ==================================================== */}

      <form onSubmit={handleSubmit} noValidate className="space-y-6">
        {/* ==================================================
            VEHICLE INFORMATION
        ================================================== */}

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-6 py-5">
            <h2 className="text-base font-black text-slate-900">
              Vehicle Information
            </h2>

            <p className="mt-1 text-xs leading-5 text-slate-500">
              Update the basic information for this vehicle.
            </p>
          </div>

          <div className="grid gap-5 p-6 md:grid-cols-2">
            {/* ----------------------------------------------
                Plate Country
            ---------------------------------------------- */}

            <div>
              <label
                htmlFor="plate_country"
                className="mb-2 block text-sm font-extrabold text-slate-800"
              >
                Plate Country
                <span className="ml-1 text-rose-500">*</span>
              </label>

              <input
                id="plate_country"
                name="plate_country"
                type="text"
                value={form.plate_country}
                onChange={(event) =>
                  updateField(
                    "plate_country",
                    event.target.value.toUpperCase().slice(0, 3),
                  )
                }
                maxLength={3}
                autoComplete="country"
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-bold uppercase text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />

              <p className="mt-1.5 text-xs text-slate-400">
                ISO country code, e.g. KE
              </p>
            </div>

            {/* ----------------------------------------------
                Registration
            ---------------------------------------------- */}

            <div>
              <label
                htmlFor="registration_number"
                className="mb-2 block text-sm font-extrabold text-slate-800"
              >
                Registration Number
                <span className="ml-1 text-rose-500">*</span>
              </label>

              <input
                id="registration_number"
                name="registration_number"
                type="text"
                value={form.registration_number}
                onChange={(event) =>
                  handleRegistrationChange(event.target.value)
                }
                maxLength={20}
                autoComplete="off"
                spellCheck={false}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-black uppercase tracking-wide text-slate-900 outline-none transition placeholder:font-medium placeholder:tracking-normal placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />

              <p className="mt-1.5 text-xs text-slate-400">Example: KDA123A</p>
            </div>

            {/* ----------------------------------------------
                Make
            ---------------------------------------------- */}

            <div>
              <label
                htmlFor="make"
                className="mb-2 block text-sm font-extrabold text-slate-800"
              >
                Make
                <span className="ml-1 text-rose-500">*</span>
              </label>

              <input
                id="make"
                name="make"
                type="text"
                value={form.make}
                onChange={(event) => updateField("make", event.target.value)}
                maxLength={100}
                placeholder="Toyota"
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />
            </div>

            {/* ----------------------------------------------
                Model
            ---------------------------------------------- */}

            <div>
              <label
                htmlFor="model"
                className="mb-2 block text-sm font-extrabold text-slate-800"
              >
                Model
                <span className="ml-1 text-rose-500">*</span>
              </label>

              <input
                id="model"
                name="model"
                type="text"
                value={form.model}
                onChange={(event) => updateField("model", event.target.value)}
                maxLength={100}
                placeholder="Corolla"
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />
            </div>

            {/* ----------------------------------------------
                Colour
            ---------------------------------------------- */}

            <div>
              <label
                htmlFor="colour"
                className="mb-2 block text-sm font-extrabold text-slate-800"
              >
                Colour
              </label>

              <input
                id="colour"
                name="colour"
                type="text"
                value={form.colour}
                onChange={(event) => updateField("colour", event.target.value)}
                maxLength={50}
                placeholder="White"
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />

              <p className="mt-1.5 text-xs text-slate-400">Optional</p>
            </div>

            {/* ----------------------------------------------
                Year
            ---------------------------------------------- */}

            <div>
              <label
                htmlFor="year"
                className="mb-2 block text-sm font-extrabold text-slate-800"
              >
                Year
              </label>

              <input
                id="year"
                name="year"
                type="number"
                value={form.year}
                onChange={(event) => updateField("year", event.target.value)}
                min={minimumYear}
                max={currentYear + 1}
                inputMode="numeric"
                placeholder={String(currentYear)}
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />

              <p className="mt-1.5 text-xs text-slate-400">Optional</p>
            </div>

            {/* ----------------------------------------------
                Nickname
            ---------------------------------------------- */}

            <div className="md:col-span-2">
              <label
                htmlFor="nickname"
                className="mb-2 block text-sm font-extrabold text-slate-800"
              >
                Vehicle Nickname
              </label>

              <input
                id="nickname"
                name="nickname"
                type="text"
                value={form.nickname}
                onChange={(event) =>
                  updateField("nickname", event.target.value)
                }
                maxLength={100}
                placeholder="e.g. My Daily Car"
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />

              <p className="mt-1.5 text-xs text-slate-400">Optional</p>
            </div>
          </div>
        </section>

        {/* ==================================================
            VEHICLE TYPE
        ================================================== */}

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-6 py-5">
            <h2 className="text-base font-black text-slate-900">
              Vehicle Type
            </h2>

            <p className="mt-1 text-xs leading-5 text-slate-500">
              Select the classification that best describes this vehicle.
            </p>
          </div>

          <div className="grid gap-3 p-6 sm:grid-cols-2 lg:grid-cols-3">
            {VEHICLE_TYPES.map((vehicleType) => {
              const selected = form.vehicle_type === vehicleType.value;

              return (
                <button
                  key={vehicleType.value}
                  type="button"
                  onClick={() => updateField("vehicle_type", vehicleType.value)}
                  className={`relative rounded-2xl border p-4 text-left transition ${
                    selected
                      ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                      : "border-slate-200 bg-white hover:border-emerald-200 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="grid h-10 w-10 place-items-center rounded-xl bg-slate-100 text-slate-600">
                      <CarFront size={20} />
                    </div>

                    {selected && (
                      <CheckCircle2 size={19} className="text-emerald-600" />
                    )}
                  </div>

                  <p className="mt-4 text-sm font-black text-slate-900">
                    {vehicleType.label}
                  </p>

                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    {vehicleType.description}
                  </p>
                </button>
              );
            })}
          </div>
        </section>

        {/* ==================================================
            PARKING PROFILE
        ================================================== */}

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-6 py-5">
            <h2 className="text-base font-black text-slate-900">
              Parking Profile
            </h2>

            <p className="mt-1 text-xs leading-5 text-slate-500">
              This profile is used for parking eligibility and future SmartPark
              recommendations.
            </p>
          </div>

          <div className="grid gap-3 p-6 sm:grid-cols-2 lg:grid-cols-3">
            {PARKING_PROFILES.map((profile) => {
              const selected = form.parking_profile === profile.value;

              return (
                <button
                  key={profile.value}
                  type="button"
                  onClick={() => updateField("parking_profile", profile.value)}
                  className={`rounded-2xl border p-4 text-left transition ${
                    selected
                      ? "border-emerald-500 bg-emerald-50 ring-2 ring-emerald-100"
                      : "border-slate-200 bg-white hover:border-emerald-200 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-sm font-black text-slate-900">
                      {profile.label}
                    </span>

                    {selected && (
                      <CheckCircle2
                        size={18}
                        className="shrink-0 text-emerald-600"
                      />
                    )}
                  </div>

                  <p className="mt-1.5 text-xs leading-5 text-slate-500">
                    {profile.description}
                  </p>
                </button>
              );
            })}
          </div>
        </section>

        {/* ==================================================
            DEFAULT VEHICLE
        ================================================== */}

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="p-6">
            <label className="flex cursor-pointer items-start gap-4">
              <input
                type="checkbox"
                checked={form.is_default}
                onChange={(event) =>
                  updateField("is_default", event.target.checked)
                }
                className="mt-1 h-5 w-5 rounded border-slate-300 accent-emerald-600 focus:ring-emerald-500"
              />

              <span className="min-w-0">
                <span className="flex items-center gap-2 text-sm font-black text-slate-900">
                  Make this my default vehicle
                  <ShieldCheck size={16} className="text-emerald-600" />
                </span>

                <span className="mt-1 block text-xs leading-5 text-slate-500">
                  Your default vehicle is automatically selected when creating a
                  parking reservation.
                </span>
              </span>
            </label>

            <div className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-800">
              <strong>Important:</strong> The current backend update
              implementation sets the updated vehicle as the default vehicle
              when the update is saved.
            </div>
          </div>
        </section>

        {/* ==================================================
            PREVIEW
        ================================================== */}

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
          <div className="border-b border-slate-200 px-6 py-5">
            <h2 className="text-base font-black text-slate-900">
              Updated Vehicle Preview
            </h2>

            <p className="mt-1 text-xs text-slate-500">
              Review the changes before saving.
            </p>
          </div>

          <div className="grid gap-4 p-6 sm:grid-cols-2 lg:grid-cols-4">
            <PreviewItem
              label="Registration"
              value={form.registration_number || "—"}
            />

            <PreviewItem
              label="Vehicle"
              value={
                form.make || form.model
                  ? `${form.make} ${form.model}`.trim()
                  : "—"
              }
            />

            <PreviewItem
              label="Type"
              value={selectedVehicleType?.label ?? "—"}
            />

            <PreviewItem
              label="Parking Profile"
              value={selectedParkingProfile?.label ?? "—"}
            />
          </div>
        </section>

        {/* ==================================================
            ACTIONS
        ================================================== */}

        <div className="flex flex-col-reverse gap-3 border-t border-slate-200 pt-6 sm:flex-row sm:items-center sm:justify-between">
          <Link
            to="/vehicles"
            className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-extrabold text-slate-700 transition hover:bg-slate-50"
          >
            Cancel
          </Link>

          <button
            type="submit"
            disabled={isSubmitting || !vehicle || !vehicle.is_active}
            className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-7 py-3 text-sm font-extrabold text-white shadow-sm transition hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSubmitting ? (
              <>
                <Loader2 size={17} className="animate-spin" />
                Saving Changes...
              </>
            ) : (
              <>
                <CheckCircle2 size={17} />
                Save Changes
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
}

// ==========================================================
// Preview Item
// ==========================================================

function PreviewItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white p-4">
      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-400">
        {label}
      </p>

      <p className="mt-1.5 text-sm font-black text-slate-900">{value}</p>
    </div>
  );
}

// ==========================================================
// Error Extraction
// ==========================================================

function extractErrorMessage(err: any): string {
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

        if (typeof item?.msg === "string") {
          return item.msg;
        }

        return "Validation error";
      })
      .join(", ");
  }

  const message = err?.response?.data?.message;

  if (typeof message === "string") {
    return message;
  }

  if (typeof err?.message === "string") {
    return err.message;
  }

  switch (err?.response?.status) {
    case 401:
      return "Your session has expired. Please sign in again.";

    case 403:
      return "You are not authorized to modify this vehicle.";

    case 404:
      return "The vehicle could not be found.";

    case 409:
      return "A vehicle with this registration number already exists.";

    case 422:
      return "Some of the vehicle information is invalid.";

    default:
      return "Unable to update the vehicle. Please try again.";
  }
}
