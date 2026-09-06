import { FormEvent, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
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
// Constants
// ==========================================================

const VEHICLE_TYPES = [
  {
    value: "CAR",
    label: "Car",
    description: "Everyday passenger car",
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
    description: "Bus or passenger vehicle",
  },
  {
    value: "ANY",
    label: "Any",
    description: "General vehicle type",
  },
] as const;

const PARKING_PROFILES = [
  {
    value: "STANDARD",
    label: "Standard",
    description: "Standard parking needs",
  },
  {
    value: "ELECTRIC",
    label: "Electric",
    description: "Vehicle that needs EV charging",
  },
  {
    value: "ACCESSIBLE",
    label: "Accessible",
    description: "Vehicle that needs accessible parking",
  },
  {
    value: "VIP",
    label: "VIP",
    description: "Vehicle with VIP parking access",
  },
  {
    value: "COMMERCIAL",
    label: "Commercial",
    description: "Business or commercial vehicle",
  },
  {
    value: "EMERGENCY",
    label: "Emergency",
    description: "Emergency-response vehicle",
  },
] as const;

// ==========================================================
// Initial Form State
// ==========================================================

const INITIAL_FORM = {
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

// ==========================================================
// Component
// ==========================================================

export default function AddVehicle() {
  const navigate = useNavigate();

  // --------------------------------------------------------
  // Form State
  // --------------------------------------------------------

  const [form, setForm] = useState(INITIAL_FORM);

  const [isSubmitting, setIsSubmitting] = useState(false);

  const [error, setError] = useState<string | null>(null);

  const [success, setSuccess] = useState<Vehicle | null>(null);

  // ========================================================
  // Current Year
  // ========================================================

  const currentYear = new Date().getFullYear();

  const minimumYear = 1950;

  // ========================================================
  // Selected Vehicle type
  // ========================================================

  const selectedVehicleType = useMemo(
    () => VEHICLE_TYPES.find((item) => item.value === form.vehicle_type),
    [form.vehicle_type],
  );

  // ========================================================
  // Selected Parking profile
  // ========================================================

  const selectedParkingProfile = useMemo(
    () => PARKING_PROFILES.find((item) => item.value === form.parking_profile),
    [form.parking_profile],
  );

  // ========================================================
  // Update Field
  // ========================================================

  const updateField = <K extends keyof typeof INITIAL_FORM>(
    field: K,
    value: (typeof INITIAL_FORM)[K],
  ) => {
    setForm((current) => ({
      ...current,
      [field]: value,
    }));

    /*
     * Clear an old error as soon as the user
     * starts correcting the form.
     */
    if (error) {
      setError(null);
    }
  };

  // ========================================================
  // Registration Formatting
  // ========================================================

  const handleRegistrationChange = (value: string) => {
    /*
     * Backend ultimately normalizes the registration
     * to uppercase and removes whitespace.
     *
     * We normalize visually as well so the user sees
     * the value that will be submitted.
     */
    const normalized = value.toUpperCase().replace(/[^A-Z0-9 -]/g, "");

    updateField("registration_number", normalized);
  };

  // ========================================================
  // Client Validation
  // ========================================================

  const validateForm = (): string | null => {
    const registration = form.registration_number.replace(/\s+/g, "").trim();

    if (!registration) {
      return "Vehicle registration is required.";
    }

    if (registration.length < 3) {
      return "Vehicle registration must contain at least 3 characters.";
    }

    if (registration.length > 20) {
      return "Vehicle registration cannot exceed 20 characters.";
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
        return "Please enter a valid vehicle year.";
      }

      if (numericYear < minimumYear || numericYear > currentYear + 1) {
        return `Vehicle year must be between ${minimumYear} and ${currentYear + 1}.`;
      }
    }

    return null;
  };

  // ========================================================
  // Error Extraction
  // ========================================================

  const extractErrorMessage = (err: any): string => {
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

    return "Unable to register the vehicle. Please try again.";
  };

  // ========================================================
  // Submit
  // ========================================================

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (isSubmitting) {
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
      /*
       * Build the exact VehicleCreate payload.
       *
       * customer_id is intentionally NOT sent.
       * The authenticated backend user determines
       * ownership.
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
       * Create the vehicle.
       *
       * POST /vehicles
       */
      const response = await api.post<Vehicle>("/vehicles", payload);

      const createdVehicle = response.data;

      setSuccess(createdVehicle);
    } catch (err) {
      console.error("[SmartPark Add vehicle] Failed to create vehicle:", err);

      setError(extractErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  };

  // ========================================================
  // Reset form
  // ========================================================

  const handleReset = () => {
    setForm(INITIAL_FORM);
    setError(null);
    setSuccess(null);
  };

  // ========================================================
  // Success Screen
  // ========================================================

  if (success) {
    return (
      <div className="mx-auto w-full max-w-3xl">
        <div className="rounded-3xl border border-emerald-200 bg-white p-7 text-center shadow-sm sm:p-10">
          {/* ----------------------------------------------
              Success Icon
          ---------------------------------------------- */}

          <div className="mx-auto grid h-20 w-20 place-items-center rounded-full bg-emerald-50 text-emerald-600">
            <CheckCircle2 size={42} />
          </div>

          {/* ----------------------------------------------
              Heading
          ---------------------------------------------- */}

          <h1 className="mt-6 text-2xl font-semibold tracking-tight text-slate-900">
            Vehicle added successfully
          </h1>

          <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">
            Your vehicle has been added and is now available for parking
            bookings.
          </p>

          {/* ----------------------------------------------
              Vehicle Summary
          ---------------------------------------------- */}

          <div className="mx-auto mt-7 max-w-md rounded-2xl border border-slate-200 bg-slate-50 p-5 text-left">
            <div className="flex items-center gap-4">
              <div className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-emerald-100 text-emerald-600">
                <CarFront size={25} />
              </div>

              <div className="min-w-0">
                <p className="text-lg font-semibold tracking-tight text-slate-900">
                  {success.registration_number}
                </p>

                <p className="text-sm font-semibold text-slate-500">
                  {success.make} {success.model}
                </p>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-3">
              <div className="rounded-xl bg-white p-3">
                <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                  Type
                </p>

                <p className="mt-1 text-sm font-semibold text-slate-800">
                  {selectedVehicleType?.label ?? success.vehicle_type}
                </p>
              </div>

              <div className="rounded-xl bg-white p-3">
                <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                  Status
                </p>

                <p className="mt-1 text-sm font-semibold text-emerald-700">
                  Active
                </p>
              </div>
            </div>

            {success.is_default && (
              <div className="mt-3 flex items-center gap-2 rounded-xl bg-amber-50 px-3 py-2.5 text-xs font-medium text-amber-700">
                <CheckCircle2 size={15} />
                This is your default vehicle.
              </div>
            )}
          </div>

          {/* ----------------------------------------------
              Actions
          ---------------------------------------------- */}

          <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
            <button
              type="button"
              onClick={() => navigate("/vehicles")}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-6 py-3 text-sm font-semibold text-white transition hover:bg-emerald-700"
            >
              View my vehicles
            </button>

            <button
              type="button"
              onClick={() => {
                setSuccess(null);
                setForm({
                  ...INITIAL_FORM,
                  is_default: false,
                });
              }}
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white px-6 py-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-emerald-200 hover:bg-emerald-50 hover:text-emerald-700"
            >
              Add another vehicle
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
    <div className="mx-auto w-full max-w-4xl space-y-5 sm:space-y-6">
      {/* ====================================================
          HEADER
      ==================================================== */}

      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <Link
            to="/vehicles"
            className="inline-flex items-center gap-2 text-sm font-medium text-slate-500 transition hover:text-emerald-600"
          >
            <ArrowLeft size={16} />
            Back to my vehicles
          </Link>

          <div className="mt-4">
            <div className="flex items-center gap-3">
              <div className="grid h-11 w-11 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
                <CarFront size={24} />
              </div>

              <div>
                <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
                  Add Vehicle
                </h1>

                <p className="mt-0.5 text-sm font-medium text-slate-500">
                  Add a vehicle you can use for parking bookings.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>

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
              <p className="text-sm font-semibold text-rose-900">
                Unable to add vehicle
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

      {/* <div className="rounded-2xl border border-blue-100 bg-blue-50 px-5 py-4">
        <div className="flex items-start gap-3">
          <Info size={19} className="mt-0.5 shrink-0 text-blue-600" />

          <div>
            <p className="text-sm font-semibold text-blue-900">
              Vehicle Registration
            </p>

            <p className="mt-1 text-xs leading-5 text-blue-800">
              Registration numbers are stored in a normalized format. SmartPark
              AI will automatically convert the registration to uppercase.
            </p>
          </div>
        </div>
      </div> */}

      {/* ====================================================
          FORM
      ==================================================== */}

      <form
        onSubmit={handleSubmit}
        noValidate
        className="space-y-5 sm:space-y-6"
      >
        {/* ==================================================
            BASIC VEHICLE INFORMATION
        ================================================== */}

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-5 py-4 sm:px-6 sm:py-5">
            <h2 className="text-base font-semibold text-slate-900">
              Vehicle information
            </h2>

            <p className="mt-1 text-xs leading-5 text-slate-500">
              Enter the basic details from your vehicle documents.
            </p>
          </div>

          <div className="grid gap-4 p-5 sm:gap-5 sm:p-6 md:grid-cols-2">
            {/* ----------------------------------------------
                Plate country
            ---------------------------------------------- */}

            <div>
              <label
                htmlFor="plate_country"
                className="mb-2 block text-sm font-semibold text-slate-800"
              >
                Plate country
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
                placeholder="KE"
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-medium uppercase text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />

              <p className="mt-1.5 text-xs text-slate-400">
                Country code, e.g. KE
              </p>
            </div>

            {/* ----------------------------------------------
                Registration
            ---------------------------------------------- */}

            <div>
              <label
                htmlFor="registration_number"
                className="mb-2 block text-sm font-semibold text-slate-800"
              >
                Registration number
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
                placeholder="KDA123A"
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold uppercase tracking-wide text-slate-900 outline-none transition placeholder:font-medium placeholder:tracking-normal placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />

              <p className="mt-1.5 text-xs text-slate-400">Example: KDA123A</p>
            </div>

            {/* ----------------------------------------------
                Make
            ---------------------------------------------- */}

            <div>
              <label
                htmlFor="make"
                className="mb-2 block text-sm font-semibold text-slate-800"
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
                autoComplete="off"
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
                className="mb-2 block text-sm font-semibold text-slate-800"
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
                autoComplete="off"
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
                className="mb-2 block text-sm font-semibold text-slate-800"
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
                autoComplete="off"
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
                className="mb-2 block text-sm font-semibold text-slate-800"
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
                className="mb-2 block text-sm font-semibold text-slate-800"
              >
                Vehicle nickname
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
                autoComplete="off"
                placeholder="e.g. My Daily Car"
                className="w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-900 outline-none transition placeholder:text-slate-400 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100"
              />

              <p className="mt-1.5 text-xs text-slate-400">
                Optional. Give your vehicle a name you will recognize.
              </p>
            </div>
          </div>
        </section>

        {/* ==================================================
            VEHICLE TYPE
        ================================================== */}

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-100 px-5 py-4 sm:px-6 sm:py-5">
            <h2 className="text-base font-semibold text-slate-900">
              Vehicle type
            </h2>

            <p className="mt-1 text-xs leading-5 text-slate-500">
              Choose the option that best describes your vehicle.
            </p>
          </div>

          <div className="grid gap-3 p-5 sm:p-6 sm:grid-cols-2 lg:grid-cols-3">
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

                  <p className="mt-4 text-sm font-semibold text-slate-900">
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
          <div className="border-b border-slate-100 px-5 py-4 sm:px-6 sm:py-5">
            <h2 className="text-base font-semibold text-slate-900">
              Parking profile
            </h2>

            <p className="mt-1 text-xs leading-5 text-slate-500">
              Choose any special parking needs that apply to this vehicle.
            </p>
          </div>

          <div className="grid gap-3 p-5 sm:p-6 sm:grid-cols-2 lg:grid-cols-3">
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
                    <span className="text-sm font-semibold text-slate-900">
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
                className="mt-1 h-5 w-5 rounded border-slate-300 text-emerald-600 accent-emerald-600 focus:ring-emerald-500"
              />

              <span className="min-w-0">
                <span className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                  Make this my default vehicle
                  <ShieldCheck size={16} className="text-emerald-600" />
                </span>

                <span className="mt-1 block text-xs leading-5 text-slate-500">
                  This vehicle will be selected automatically when you make a
                  new parking booking.
                </span>
              </span>
            </label>

            <div className="mt-4 rounded-xl bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-800">
              <strong>Important:</strong> If you select this as your default
              vehicle, SmartPark AI will remove the default status from your
              existing default vehicle.
            </div>

            <div className="mt-3 rounded-xl bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600">
              If this is your first vehicle, it will automatically become your
              default vehicle.
            </div>
          </div>
        </section>

        {/* ==================================================
            PREVIEW
        ================================================== */}

        <section className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
          <div className="border-b border-slate-200 px-6 py-5">
            <h2 className="text-base font-semibold text-slate-900">
              Vehicle preview
            </h2>

            <p className="mt-1 text-xs text-slate-500">
              Check the details before adding the vehicle.
            </p>
          </div>

          <div className="grid gap-4 p-5 sm:p-6 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-xl bg-white p-4">
              <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                Registration
              </p>

              <p className="mt-1.5 text-base font-semibold tracking-wide text-slate-900">
                {form.registration_number || "—"}
              </p>
            </div>

            <div className="rounded-xl bg-white p-4">
              <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                Vehicle
              </p>

              <p className="mt-1.5 text-sm font-semibold text-slate-900">
                {form.make || form.model
                  ? `${form.make} ${form.model}`.trim()
                  : "—"}
              </p>
            </div>

            <div className="rounded-xl bg-white p-4">
              <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                Type
              </p>

              <p className="mt-1.5 text-sm font-semibold text-slate-900">
                {selectedVehicleType?.label ?? "—"}
              </p>
            </div>

            <div className="rounded-xl bg-white p-4">
              <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">
                Parking profile
              </p>

              <p className="mt-1.5 text-sm font-semibold text-slate-900">
                {selectedParkingProfile?.label ?? "—"}
              </p>
            </div>
          </div>
        </section>

        {/* ==================================================
            FORM ACTIONS
        ================================================== */}

        <div className="flex flex-col-reverse gap-3 border-t border-slate-200 pt-6 sm:flex-row sm:items-center sm:justify-between">
          <button
            type="button"
            onClick={handleReset}
            disabled={isSubmitting}
            className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Reset form
          </button>

          <div className="flex flex-col gap-3 sm:flex-row">
            <Link
              to="/vehicles"
              className="inline-flex items-center justify-center rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-semibold text-slate-700 shadow-sm transition hover:border-emerald-200 hover:bg-emerald-50 hover:text-emerald-700"
            >
              Cancel
            </Link>

            <button
              type="submit"
              disabled={isSubmitting}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-emerald-600 px-7 py-3 text-sm font-semibold text-white shadow-sm transition hover:bg-emerald-700 hover:shadow-md disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? (
                <>
                  <Loader2 size={17} className="animate-spin" />
                  Adding vehicle...
                </>
              ) : (
                <>
                  <CheckCircle2 size={17} />
                  Add vehicle
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
}
