import { Card } from "../../components/common/Page";

export default function Settings({
  title = "Settings",
  text = "System and account configuration.",
}: {
  title?: string;
  text?: string;
}) {
  return (
    <div className="space-y-6">
      <div className="mb-2">
        <div className="text-xs font-bold uppercase tracking-[.2em] text-emerald-600">
          SmartPark AI
        </div>
        <h1 className="mt-2 text-3xl font-black tracking-tight">{title}</h1>
        <p className="mt-2 text-slate-500">{text}</p>
      </div>

      <Card title="Configuration" sub="Backend integration">
        <p className="text-sm text-slate-500">
          This area is ready for backend-connected configuration.
        </p>
      </Card>
    </div>
  );
}
