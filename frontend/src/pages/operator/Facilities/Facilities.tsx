import { Building2 } from "lucide-react";

import Page, { Card } from "../../../components/common/Page";

export default function Facilities() {
  return (
    <div className="space-y-6">
      <Page
        title="Parking Facilities"
        text="Manage facilities, capacity, availability and operating status."
      />

      <Card title="Facilities" sub="Connected to SmartPark AI backend">
        <div className="overflow-x-auto">
          <div className="rounded-2xl bg-slate-50 p-8 text-center">
            <Building2 className="mx-auto text-slate-400" size={32} />

            <p className="mt-3 text-sm text-slate-500">
              Facilities will be loaded from the production parking facilities
              API.
            </p>
          </div>
        </div>
      </Card>
    </div>
  );
}

// ==========================================================
// Admin
// ==========================================================


