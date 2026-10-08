"use client";

import { useQuery } from "@tanstack/react-query";
import { FlaskConical, Info } from "lucide-react";
import { MetricCard } from "@/components/common/metric-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useT } from "@/i18n/i18n";
import { api } from "@/lib/api";
import { formatKg, formatNumber } from "@/lib/utils";

interface PublicImpact {
  villages: number;
  collection_points: number;
  collected_kg: number;
  suspected_mlp_received_kg: number;
  recovered_evidence_reviewed_kg: number;
  share_synthetic_percent: number;
  demo_mode: boolean;
}

export default function ImpactPage() {
  const { t, locale } = useT();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["public-impact"],
    queryFn: () => api<PublicImpact>("/analytics/public-impact", { auth: false }),
  });
  return (
    <div className="mx-auto max-w-5xl px-4 py-14 sm:px-6">
      <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">{t("public.impact.title")}</h1>
      <p className="mt-4 max-w-2xl text-lg text-muted-foreground">{t("public.impact.lead")}</p>

      {data && data.share_synthetic_percent > 0 && (
        <Alert tone="warning" className="mt-8">
          <FlaskConical />
          <div>
            <AlertTitle>{t("public.impact.syntheticTitle")}</AlertTitle>
            <AlertDescription>{t("public.impact.syntheticBody", { percent: formatNumber(data.share_synthetic_percent, locale, 0) })}</AlertDescription>
          </div>
        </Alert>
      )}
      {isError && (
        <Alert tone="neutral" className="mt-8">
          <Info />
          <AlertDescription>{t("public.impact.unavailable")}</AlertDescription>
        </Alert>
      )}

      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard loading={isLoading} label={t("public.impact.villages")} value={formatNumber(data?.villages, locale, 0)} />
        <MetricCard loading={isLoading} label={t("public.impact.points")} value={formatNumber(data?.collection_points, locale, 0)} />
        <MetricCard loading={isLoading} label={t("public.impact.collected")} value={formatKg(data?.collected_kg, locale)} />
        <MetricCard
          loading={isLoading}
          label={t("public.impact.recovered")}
          value={formatKg(data?.recovered_evidence_reviewed_kg, locale)}
          hint={t("public.impact.recoveredHint")}
        />
      </div>
      <p className="mt-6 text-sm text-muted-foreground">{t("public.impact.method")}</p>
    </div>
  );
}
