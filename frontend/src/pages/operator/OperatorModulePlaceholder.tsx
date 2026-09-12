import { useMemo } from "react";
import { useLocation, Link } from "react-router";
import {
  ArrowLeft,
  BarChart3,
  BrainCircuit,
  CarFront,
  CheckCircle2,
  ClipboardCheck,
  CreditCard,
  FileBarChart,
  MapPinned,
  ParkingCircle,
  QrCode,
  Radio,
  ScanLine,
  ShieldAlert,
  Wrench,
} from "lucide-react";

import Page, { Card } from "../../components/common/Page";

const MODULES: Record<
  string,
  { title: string; description: string; Icon: typeof ParkingCircle }
> = {
  "/operator/reservations": {
    title: "Approve Reservations",
    description:
      "Review, approve and manage reservations assigned to your facility.",
    Icon: ClipboardCheck,
  },
  "/operator/access": {
    title: "Check-In / Check-Out",
    description:
      "Process vehicle entry and exit using the supported access channels.",
    Icon: ScanLine,
  },
  "/operator/release-slots": {
    title: "Release Parking Slots",
    description:
      "Review occupied or reserved bays and release slots when operationally appropriate.",
    Icon: Wrench,
  },
  "/operator/occupancy": {
    title: "Occupancy Statistics",
    description:
      "Analyse current facility occupancy, capacity and bay availability.",
    Icon: BarChart3,
  },
  "/operator/vehicles": {
    title: "Vehicle Search",
    description:
      "Locate active vehicles and review vehicle movement information for your facility.",
    Icon: CarFront,
  },
  "/operator/reports": {
    title: "Reports",
    description:
      "Operational, occupancy, vehicle movement, revenue and exception reporting.",
    Icon: FileBarChart,
  },
  "/operator/reservations/arrivals": {
    title: "Today's Arrivals",
    description:
      "Monitor reservations expected to arrive at your facility today.",
    Icon: CheckCircle2,
  },
  "/operator/reservations/history": {
    title: "Reservation History",
    description:
      "Review completed, cancelled and expired reservations for your facility.",
    Icon: ClipboardCheck,
  },
  "/operator/access/qr": {
    title: "QR Code Access",
    description: "Process secure QR-based vehicle access at the facility.",
    Icon: QrCode,
  },
  "/operator/access/anpr": {
    title: "ANPR Simulator",
    description:
      "Simulate automatic number plate recognition events using the operator access workflow.",
    Icon: Radio,
  },
  "/operator/access/rfid": {
    title: "RFID Simulator",
    description:
      "Simulate RFID vehicle identification events using the operator access workflow.",
    Icon: Radio,
  },
  "/operator/access/sensor": {
    title: "Sensor / Scanner",
    description:
      "Simulate parking sensor or scanner events for vehicle entry and exit.",
    Icon: ScanLine,
  },
  "/operator/access/mobile": {
    title: "Mobile App Access",
    description:
      "Process vehicle access originating from the SmartPark mobile application.",
    Icon: CarFront,
  },
  "/operator/occupancy/map": {
    title: "Live Slot Map",
    description: "Visualise parking bays by zone and operational state.",
    Icon: MapPinned,
  },
  "/operator/facility-status": {
    title: "Facility Status",
    description: "Review operational status and facility-level information.",
    Icon: ParkingCircle,
  },
  "/operator/payments": {
    title: "Payment Verification",
    description:
      "Review and verify parking payments associated with facility operations.",
    Icon: CreditCard,
  },
  "/operator/exceptions": {
    title: "Exceptions & Incidents",
    description:
      "Record and manage operational exceptions requiring operator attention.",
    Icon: ShieldAlert,
  },
  "/operator/insights/alerts": {
    title: "Operational Alerts",
    description:
      "Review alerts generated from facility occupancy and operational activity.",
    Icon: ShieldAlert,
  },
  "/operator/insights/trends": {
    title: "Occupancy Trends",
    description: "Analyse occupancy patterns and operational demand over time.",
    Icon: BarChart3,
  },
  "/operator/insights/peaks": {
    title: "Peak Periods",
    description:
      "Identify periods of elevated parking demand for operational planning.",
    Icon: BarChart3,
  },
  "/operator/insights/capacity": {
    title: "Capacity Forecast",
    description:
      "Use SmartPark intelligence to anticipate capacity pressure and availability.",
    Icon: BrainCircuit,
  },
  "/operator/insights/anomalies": {
    title: "Anomalies",
    description:
      "Surface unusual occupancy and vehicle activity for investigation.",
    Icon: ShieldAlert,
  },
  "/operator/profile": {
    title: "My Profile",
    description:
      "Manage your operator account information and profile settings.",
    Icon: CarFront,
  },
};

export default function OperatorModulePlaceholder() {
  const location = useLocation();
  const module = useMemo(() => {
    const exact = MODULES[location.pathname];
    if (exact) return exact;

    const prefix = Object.keys(MODULES)
      .filter((path) => location.pathname.startsWith(`${path}/`))
      .sort((a, b) => b.length - a.length)[0];

    return prefix ? MODULES[prefix] : null;
  }, [location.pathname]);

  const Icon = module?.Icon ?? ParkingCircle;

  return (
    <div className="space-y-6">
      <Page
        title={module?.title ?? "Operator Workspace"}
        text={module?.description ?? "Facility-scoped operator functionality."}
      />

      <Card title="Module workspace" sub="Operator functionality">
        <div className="mx-auto max-w-2xl py-10 text-center">
          <span className="mx-auto grid h-16 w-16 place-items-center rounded-2xl bg-emerald-50 text-emerald-600">
            <Icon size={28} />
          </span>
          <h2 className="mt-5 text-xl font-black text-slate-900">
            Operator module ready for implementation
          </h2>
          <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-500">
            The navigation and facility-scoped shell are in place. This module
            will be connected to its operational workflow next without changing
            the Driver portal.
          </p>
          <Link
            to="/operator"
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2.5 text-sm font-bold text-white transition hover:bg-slate-800"
          >
            <ArrowLeft size={16} />
            Back to Dashboard
          </Link>
        </div>
      </Card>
    </div>
  );
}
