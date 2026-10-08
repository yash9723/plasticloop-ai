"use client";

import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CollectionTrend } from "@/components/charts/collection-trend";
import { type Column, DataTable } from "@/components/common/data-table";
import { ErrorState } from "@/components/common/error-state";
import { MetricCard } from "@/components/common/metric-card";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { useApi } from "@/lib/query";
import { formatKg, formatKm } from "@/lib/utils";

interface Operations {
  funnel: { stage: string; kg: number; note: string }[];
  by_village: { village: string; kg: number; collections: number }[];
  by_collector: { collector: string; kg: number; collections: number; offline_share: number }[];
  devices: { device_id: string; simulated: boolean; status: string; readings: number; ok_share: number | null }[];
  routes: { count: number; completed: number; planned_distance_m: number; baseline_distance_m: number; comparable_routes: number;
    distance_basis: string[]; expected_load_kg: number; actual_load_kg: number };
  inventory_aging: { category: string; bucket: string; kg: number }[];
  declared_vs_weighed: { declared_kg: number; weighed_kg: number };
}
interface OverviewLite {
  series: { date: string; kg: number }[];
  collected_kg_by_origin: Record<string, number>;
}

const tooltipStyle = { background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 10, fontSize: 12 };
const axis = { fontSize: 11, fill: "var(--muted-foreground)" };

export default function AnalyticsPage() {
  const { t, locale } = useT();
  const [days, setDays] = useState(30);
  const [now] = useState(() => Date.now());
  const range = { date_from: new Date(now - days * 86400_000).toISOString() };
  const ops = useApi<Operations>("/analytics/operations", range);
  const ov = useApi<OverviewLite>("/analytics/overview", range);
  const d = ops.data;

  const aging = Object.values(
    (d?.inventory_aging ?? []).reduce<Record<string, Record<string, number | string>>>((acc, r) => {
      acc[r.category] ??= { category: r.category };
      acc[r.category][r.bucket] = r.kg;
      return acc;
    }, {}),
  );
  const savings = d && d.routes.baseline_distance_m ? Math.round((1 - d.routes.planned_distance_m / d.routes.baseline_distance_m) * 1000) / 10 : null;
  const collectorCols: Column<Operations["by_collector"][number]>[] = [
    { key: "name", header: t("common.collector"), cell: (r) => r.collector },
    { key: "kg", header: t("common.weight"), cell: (r) => <span className="tabular">{formatKg(r.kg, locale)}</span> },
    { key: "n", header: t("analytics.collections"), cell: (r) => r.collections },
    { key: "off", header: t("analytics.offlineShare"), cell: (r) => `${r.offline_share}%` },
  ];
  const deviceCols: Column<Operations["devices"][number]>[] = [
    { key: "id", header: t("devices.deviceId"), cell: (r) => <span className="font-mono text-xs">{r.device_id}</span> },
    { key: "status", header: t("common.status"), cell: (r) => (
      <span className="flex gap-1"><StatusBadge value={r.status} />{r.simulated && <Badge tone="warning">{t("provenance.simulated")}</Badge>}</span>
    ) },
    { key: "n", header: t("analytics.readings"), cell: (r) => r.readings },
    { key: "q", header: t("analytics.quality"), cell: (r) => (r.ok_share === null ? "—" : `${r.ok_share}%`) },
  ];

  return (
    <>
      <PageHeader title={t("nav.items.analytics")} description={t("analytics.subtitle")}
        actions={
          <Select aria-label={t("facilities.period")} value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-36">
            {[7, 30, 90].map((n) => <option key={n} value={n}>{t("facilities.lastDays", { n })}</option>)}
          </Select>
        } />
      {ops.error ? (
        <ErrorState error={ops.error} onRetry={() => ops.refetch()} />
      ) : !d ? (
        <Skeleton className="h-96" />
      ) : (
        <div className="grid gap-4">
          {ov.data && Object.keys(ov.data.collected_kg_by_origin).some((k) => k !== "live") && (
            <Alert tone="warning">{t("analytics.syntheticNotice")}</Alert>
          )}
          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="min-w-0">
              <CardHeader>
                <CardTitle className="text-base">{t("analytics.funnel")}</CardTitle>
                <CardDescription>{t("analytics.funnelHint")}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-64" role="img" aria-label={t("analytics.funnel")}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.funnel.map((s) => ({ ...s, name: t(`analytics.stages.${s.stage}`) }))} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                      <XAxis type="number" tick={axis} unit=" kg" />
                      <YAxis type="category" dataKey="name" width={140} tick={axis} />
                      <Tooltip contentStyle={tooltipStyle} formatter={(v) => formatKg(Number(v), locale)} />
                      <Bar dataKey="kg" fill="var(--chart-2)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-xs text-muted-foreground">{t("analytics.funnelNote")}</p>
              </CardContent>
            </Card>
            <Card className="min-w-0">
              <CardHeader>
                <CardTitle className="text-base">{t("analytics.trend")}</CardTitle>
              </CardHeader>
              <CardContent>{ov.data ? <CollectionTrend data={ov.data.series} /> : <Skeleton className="h-64" />}</CardContent>
            </Card>
          </div>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <MetricCard label={t("analytics.routesCompleted")} value={`${d.routes.completed}/${d.routes.count}`} />
            <MetricCard label={t("analytics.routeDistance")} value={formatKm(d.routes.planned_distance_m, locale)}
              hint={d.routes.distance_basis.includes("haversine_estimate") ? t("routes.estimate") : undefined} />
            <MetricCard tone="teal" label={t("planner.vsBaseline")} value={savings === null ? "—" : `${savings > 0 ? "−" : "+"}${Math.abs(savings)}%`}
              hint={t("analytics.comparable", { n: d.routes.comparable_routes })} />
            <MetricCard label={t("analytics.declaredVsWeighed")} value={formatKg(d.declared_vs_weighed.weighed_kg, locale)}
              hint={t("analytics.declared", { kg: formatKg(d.declared_vs_weighed.declared_kg, locale) })} />
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <Card className="min-w-0">
              <CardHeader><CardTitle className="text-base">{t("analytics.byVillage")}</CardTitle></CardHeader>
              <CardContent>
                <div className="h-60" role="img" aria-label={t("analytics.byVillage")}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.by_village} margin={{ left: -8, right: 8 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                      <XAxis dataKey="village" tick={axis} tickFormatter={(v: string) => v.replace(" (synthetic)", "")} />
                      <YAxis tick={axis} />
                      <Tooltip contentStyle={tooltipStyle} formatter={(v) => formatKg(Number(v), locale)} />
                      <Bar dataKey="kg" fill="var(--chart-1)" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
            <Card className="min-w-0">
              <CardHeader>
                <CardTitle className="text-base">{t("analytics.aging")}</CardTitle>
                <CardDescription>{t("analytics.agingHint")}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-60" role="img" aria-label={t("analytics.aging")}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={aging} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                      <XAxis type="number" tick={axis} unit=" kg" />
                      <YAxis type="category" dataKey="category" width={130} tick={axis} />
                      <Tooltip contentStyle={tooltipStyle} formatter={(v) => formatKg(Number(v), locale)} />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="0-7" stackId="a" name={t("analytics.ageBuckets.fresh")} fill="var(--chart-2)" />
                      <Bar dataKey="7-30" stackId="a" name={t("analytics.ageBuckets.mid")} fill="var(--chart-4)" />
                      <Bar dataKey="30+" stackId="a" name={t("analytics.ageBuckets.old")} fill="var(--chart-5)" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </CardContent>
            </Card>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <div className="min-w-0">
              <h2 className="mb-2 font-semibold">{t("analytics.byCollector")}</h2>
              <DataTable columns={collectorCols} rows={d.by_collector} rowKey={(r) => r.collector} />
            </div>
            <div className="min-w-0">
              <h2 className="mb-2 font-semibold">{t("analytics.deviceQuality")}</h2>
              <DataTable columns={deviceCols} rows={d.devices} rowKey={(r) => r.device_id} emptyTitle={t("devices.empty")} />
            </div>
          </div>
        </div>
      )}
    </>
  );
}
