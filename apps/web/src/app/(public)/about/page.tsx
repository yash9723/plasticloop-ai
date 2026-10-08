"use client";

import { useT } from "@/i18n/i18n";

const SECTIONS = ["problem", "approach", "scope", "limits"];

export default function AboutPage() {
  const { t } = useT();
  return (
    <div className="mx-auto max-w-3xl px-4 py-14 sm:px-6">
      <p className="text-sm font-medium text-primary">SIH26259 · Clean &amp; Green Technology</p>
      <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">{t("public.about.title")}</h1>
      <p className="mt-4 text-lg text-muted-foreground">{t("public.about.lead")}</p>
      <div className="mt-10 space-y-8">
        {SECTIONS.map((s) => (
          <section key={s}>
            <h2 className="text-xl font-semibold">{t(`public.about.${s}.title`)}</h2>
            <p className="mt-2 leading-relaxed text-muted-foreground">{t(`public.about.${s}.body`)}</p>
          </section>
        ))}
      </div>
    </div>
  );
}
