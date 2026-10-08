"use client";

import { Boxes, Building2, Factory, FileBarChart2, Home, Recycle, ScanLine, Smartphone, Truck, Waypoints } from "lucide-react";
import { useT } from "@/i18n/i18n";

const STEPS = [
  { key: "household", icon: Home },
  { key: "point", icon: ScanLine },
  { key: "collector", icon: Smartphone },
  { key: "route", icon: Waypoints },
  { key: "vehicle", icon: Truck },
  { key: "mrf", icon: Factory },
  { key: "sorting", icon: Boxes },
  { key: "processor", icon: Building2 },
  { key: "recovery", icon: Recycle },
  { key: "reporting", icon: FileBarChart2 },
];

export default function HowItWorksPage() {
  const { t } = useT();
  return (
    <div className="mx-auto max-w-4xl px-4 py-14 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t("public.how.title")}</h1>
      <p className="mt-4 max-w-2xl text-lg text-muted-foreground">{t("public.how.lead")}</p>
      <ol className="relative mt-12 space-y-8 border-l pl-8">
        {STEPS.map(({ key, icon: Icon }, i) => (
          <li key={key} className="relative">
            <span className="absolute -left-[3.05rem] grid size-9 place-items-center rounded-full border bg-card text-primary shadow-sm">
              <Icon className="size-4" aria-hidden />
            </span>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {t("public.how.step", { n: i + 1 })}
            </p>
            <h2 className="mt-1 text-lg font-semibold">{t(`public.how.steps.${key}.title`)}</h2>
            <p className="mt-1 text-muted-foreground">{t(`public.how.steps.${key}.body`)}</p>
          </li>
        ))}
      </ol>
    </div>
  );
}
