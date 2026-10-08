"use client";

import { CheckCircle2, CircleDashed, CircleDot } from "lucide-react";
import { PageHeader } from "@/components/common/page-header";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { localized, useT } from "@/i18n/i18n";
import { useStreams } from "@/lib/lookups";

type Status = "done" | "partial" | "planned";

/** Honest feature status, kept in sync with docs/IMPLEMENTATION_STATUS.md. */
const FEATURES: { key: string; status: Status }[] = [
  { key: "auth", status: "done" },
  { key: "collection", status: "done" },
  { key: "offline", status: "done" },
  { key: "qr", status: "done" },
  { key: "households", status: "done" },
  { key: "i18n", status: "done" },
  { key: "devices", status: "done" },
  { key: "routing", status: "done" },
  { key: "mrf", status: "done" },
  { key: "vision", status: "done" },
  { key: "recovery", status: "done" },
  { key: "finance", status: "done" },
  { key: "backgroundSync", status: "planned" },
];

const icon = { done: CheckCircle2, partial: CircleDot, planned: CircleDashed };
const tone = { done: "success", partial: "warning", planned: "neutral" } as const;

export default function HelpPage() {
  const { t, locale } = useT();
  const streams = useStreams();
  return (
    <>
      <PageHeader title={t("nav.items.help")} description={t("help.subtitle")} />
      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader>
            <div>
              <CardTitle>{t("help.segregationTitle")}</CardTitle>
              <CardDescription>{t("help.segregationHint")}</CardDescription>
            </div>
          </CardHeader>
          <CardContent className="grid gap-3">
            {streams.data?.map((s) => (
              <div key={s.id} className="rounded-xl border p-4">
                <p className="flex items-center gap-2 font-medium">
                  <span className="size-3 rounded-full" style={{ background: s.color }} aria-hidden />
                  {localized(s.labels, s.label, locale)}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">{localized(s.descriptions, s.description ?? "", locale)}</p>
                {s.rules.length > 0 && (
                  <ul className="mt-2 list-inside list-disc text-sm">
                    {s.rules.map((r) => (
                      <li key={String(r)}>{String(r)}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
            <p className="text-sm text-muted-foreground">{t("help.mlpNote")}</p>
          </CardContent>
        </Card>
        <div className="grid content-start gap-6">
          <Card>
            <CardHeader>
              <CardTitle>{t("help.offlineTitle")}</CardTitle>
            </CardHeader>
            <CardContent>
              <ol className="list-inside list-decimal space-y-2 text-sm">
                {["one", "two", "three", "four", "five"].map((k) => (
                  <li key={k}>{t(`help.offlineSteps.${k}`)}</li>
                ))}
              </ol>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <div>
                <CardTitle>{t("help.statusTitle")}</CardTitle>
                <CardDescription>{t("help.statusHint")}</CardDescription>
              </div>
            </CardHeader>
            <CardContent className="grid gap-2">
              {FEATURES.map((f) => {
                const Icon = icon[f.status];
                return (
                  <div key={f.key} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2 text-sm">
                    <span className="flex items-center gap-2">
                      <Icon className="size-4 text-muted-foreground" aria-hidden />
                      {t(`help.features.${f.key}`)}
                    </span>
                    <Badge tone={tone[f.status]}>{t(`help.featureStatus.${f.status}`)}</Badge>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
