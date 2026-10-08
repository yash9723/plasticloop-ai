"use client";

import { Building2, LifeBuoy, ShieldAlert } from "lucide-react";
import { useT } from "@/i18n/i18n";

const ITEMS = [
  { key: "panchayat", icon: Building2 },
  { key: "support", icon: LifeBuoy },
  { key: "security", icon: ShieldAlert },
];

export default function ContactPage() {
  const { t } = useT();
  return (
    <div className="mx-auto max-w-4xl px-4 py-14 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t("public.contact.title")}</h1>
      <p className="mt-4 max-w-2xl text-lg text-muted-foreground">{t("public.contact.lead")}</p>
      <div className="mt-10 grid gap-4 md:grid-cols-3">
        {ITEMS.map(({ key, icon: Icon }) => (
          <section key={key} className="rounded-2xl border bg-card p-6 shadow-[var(--shadow-card)]">
            <Icon className="size-6 text-primary" aria-hidden />
            <h2 className="mt-3 font-semibold">{t(`public.contact.${key}.title`)}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{t(`public.contact.${key}.body`)}</p>
          </section>
        ))}
      </div>
      <p className="mt-8 text-sm text-muted-foreground">{t("public.contact.note")}</p>
    </div>
  );
}
