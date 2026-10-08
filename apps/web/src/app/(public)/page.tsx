"use client";

import {
  ArrowRight,
  Boxes,
  Building2,
  CheckCircle2,
  Cpu,
  Factory,
  FileCheck2,
  Home,
  Recycle,
  ScanLine,
  ShieldCheck,
  Smartphone,
  Truck,
  WifiOff,
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useT } from "@/i18n/i18n";

const JOURNEY = [
  { key: "household", icon: Home },
  { key: "point", icon: ScanLine },
  { key: "collector", icon: Smartphone },
  { key: "vehicle", icon: Truck },
  { key: "mrf", icon: Factory },
  { key: "sorting", icon: Boxes },
  { key: "processor", icon: Building2 },
  { key: "recovery", icon: Recycle },
];

const PILLARS = [
  { key: "offline", icon: WifiOff },
  { key: "iot", icon: Cpu },
  { key: "ledger", icon: FileCheck2 },
];

export default function LandingPage() {
  const { t } = useT();
  return (
    <>
      <section className="relative overflow-hidden border-b">
        <div
          aria-hidden
          className="absolute inset-0 -z-10 bg-[radial-gradient(60rem_30rem_at_10%_-10%,rgb(16_185_129/0.18),transparent),radial-gradient(40rem_24rem_at_90%_10%,rgb(13_148_136/0.14),transparent)]"
        />
        <div className="mx-auto grid max-w-6xl gap-12 px-4 py-16 sm:px-6 md:py-24 lg:grid-cols-[1.15fr_1fr] lg:items-center">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border bg-card px-3 py-1 text-xs font-medium text-muted-foreground">
              <span className="size-1.5 rounded-full bg-emerald-500" aria-hidden />
              {t("public.hero.eyebrow")}
            </p>
            <h1 className="mt-5 text-4xl font-semibold leading-[1.1] tracking-tight sm:text-5xl">{t("public.hero.title")}</h1>
            <p className="mt-5 max-w-xl text-lg text-muted-foreground">{t("public.hero.subtitle")}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button asChild size="lg">
                <Link href="/login">
                  {t("public.hero.primaryCta")} <ArrowRight />
                </Link>
              </Button>
              <Button asChild size="lg" variant="outline">
                <Link href="/how-it-works">{t("public.hero.secondaryCta")}</Link>
              </Button>
            </div>
          </div>
          <div className="rounded-2xl border bg-card p-5 shadow-[var(--shadow-elevated)]">
            <p className="text-sm font-medium">{t("public.journey.title")}</p>
            <ol className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
              {JOURNEY.map(({ key, icon: Icon }, i) => (
                <li key={key} className="relative rounded-xl border bg-background p-3">
                  <span className="text-[10px] font-semibold text-muted-foreground">{String(i + 1).padStart(2, "0")}</span>
                  <Icon className="mt-1 size-5 text-primary" aria-hidden />
                  <p className="mt-2 text-xs font-medium leading-snug">{t(`public.journey.${key}`)}</p>
                </li>
              ))}
            </ol>
            <p className="mt-4 flex items-start gap-2 rounded-lg bg-secondary p-3 text-xs text-secondary-foreground">
              <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden />
              {t("public.journey.note")}
            </p>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6">
        <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">{t("public.pillars.title")}</h2>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {PILLARS.map(({ key, icon: Icon }) => (
            <article key={key} className="rounded-2xl border bg-card p-6 shadow-[var(--shadow-card)]">
              <span className="grid size-10 place-items-center rounded-xl bg-secondary text-primary">
                <Icon className="size-5" aria-hidden />
              </span>
              <h3 className="mt-4 font-semibold">{t(`public.pillars.${key}.title`)}</h3>
              <p className="mt-2 text-sm text-muted-foreground">{t(`public.pillars.${key}.body`)}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="border-y bg-card">
        <div className="mx-auto grid max-w-6xl gap-10 px-4 py-16 sm:px-6 md:grid-cols-2">
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">{t("public.honesty.title")}</h2>
            <p className="mt-3 text-muted-foreground">{t("public.honesty.body")}</p>
          </div>
          <ul className="space-y-3">
            {["one", "two", "three", "four"].map((k) => (
              <li key={k} className="flex gap-3 text-sm">
                <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-primary" aria-hidden />
                <span>{t(`public.honesty.${k}`)}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="mx-auto max-w-6xl px-4 py-16 text-center sm:px-6">
        <h2 className="text-2xl font-semibold tracking-tight">{t("public.cta.title")}</h2>
        <p className="mx-auto mt-3 max-w-2xl text-muted-foreground">{t("public.cta.body")}</p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <Button asChild size="lg">
            <Link href="/login">{t("nav.items.login")}</Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link href="/register">{t("public.cta.citizen")}</Link>
          </Button>
        </div>
      </section>
    </>
  );
}
