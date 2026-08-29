import {
  Activity,
  BarChart3,
  Building2,
  ParkingCircle,
  TrendingUp,
  Zap,
} from "lucide-react";

import Page, { Card, Metric } from "../../../components/common/Page";

export default function OperatorDashboard() {
  return (
    <div className="space-y-6">
      <Page
        title="Parking Operator Dashboard"
        text="Monitor facilities, occupancy, reservations and revenue."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Facilities"
          value="—"
          note="Awaiting backend data"
          Icon={Building2}
        />

        <Metric
          label="Total spaces"
          value="—"
          note="Awaiting backend data"
          Icon={ParkingCircle}
        />

        <Metric
          label="Occupancy"
          value="—"
          note="Live observations"
          Icon={TrendingUp}
        />

        <Metric
          label="Revenue"
          value="—"
          note="Payment backend"
          Icon={BarChart3}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card title="Network occupancy" sub="Live operational view">
          <div className="rounded-2xl bg-slate-50 p-8 text-center">
            <Activity className="mx-auto text-slate-400" size={32} />

            <p className="mt-3 text-sm text-slate-500">
              Occupancy information will come from production data.
            </p>
          </div>
        </Card>

        <Card title="Operational alerts" sub="Requires attention">
          <div className="rounded-2xl bg-slate-50 p-8 text-center">
            <Zap className="mx-auto text-slate-400" size={32} />

            <p className="mt-3 text-sm text-slate-500">
              Operational alerts will be populated from backend services.
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
}

// ==========================================================
// Facilities
// ==========================================================


