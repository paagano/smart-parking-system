import type { ElementType, ReactNode } from "react";

export default function Page({ title, text }: { title: string; text: string }) {
  return (
    <div className="mb-2">
      <div className="text-xs font-bold uppercase tracking-[.2em] text-emerald-600">
        SmartPark AI
      </div>

      <h1 className="mt-2 text-3xl font-black tracking-tight">{title}</h1>

      <p className="mt-2 text-slate-500">{text}</p>
    </div>
  );
}

export function Card({
  title,
  sub,
  children,
}: {
  title: string;
  sub?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-3xl bg-white p-5 sm:p-6 shadow-sm ring-1 ring-slate-200">
      <h2 className="font-extrabold">{title}</h2>

      {sub && <p className="text-xs text-slate-500 mt-1 mb-5">{sub}</p>}

      <div className={sub ? "" : "mt-5"}>{children}</div>
    </section>
  );
}

export function Metric({
  label,
  value,
  note,
  Icon,
}: {
  label: string;
  value: string;
  note: string;
  Icon: ElementType;
}) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-slate-200">
      <div className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-50 text-emerald-600">
        <Icon size={19} />
      </div>

      <div className="mt-5 text-2xl font-black">{value}</div>

      <small className="text-slate-500 font-semibold">{label}</small>

      <div className="mt-3 text-[11px] font-bold text-emerald-600">{note}</div>
    </div>
  );
}
