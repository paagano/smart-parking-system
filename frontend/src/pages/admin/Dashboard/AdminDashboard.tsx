import { Activity, BrainCircuit, Building2, ParkingCircle, Users } from "lucide-react";

import Page, { Card, Metric } from "../../../components/common/Page";

export default function AdminDashboard() {
  return (
    <div className="space-y-6">
      <Page
        title="SmartPark AI Command Centre"
        text="Govern users, facilities, analytics and AI services."
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="Users"
          value="—"
          note="Awaiting backend data"
          Icon={Users}
        />

        <Metric
          label="Operators"
          value="—"
          note="Awaiting backend data"
          Icon={Building2}
        />

        <Metric
          label="Facilities"
          value="—"
          note="Awaiting backend data"
          Icon={ParkingCircle}
        />

        <Metric
          label="AI predictions"
          value="—"
          note="Production service"
          Icon={BrainCircuit}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="AI model monitoring" sub="Production service health">
          {[
            "Forecast API",
            "Feature Builder",
            "Model inference",
            "Prediction latency",
          ].map((item) => (
            <div
              className="flex justify-between items-center py-4 border-b last:border-0"
              key={item}
            >
              <span className="flex gap-3 items-center">
                <i className="h-2.5 w-2.5 rounded-full bg-slate-400" />

                {item}
              </span>

              <b className="text-slate-500">Pending live status</b>
            </div>
          ))}
        </Card>

        <Card title="Platform activity" sub="Recent events">
          <div className="rounded-2xl bg-slate-50 p-8 text-center">
            <Activity className="mx-auto text-slate-400" size={32} />

            <p className="mt-3 text-sm text-slate-500">
              Platform activity will be retrieved from backend services.
            </p>
          </div>
        </Card>
      </div>
    </div>
  );
}

// ==========================================================
// Simple Page
// ==========================================================


