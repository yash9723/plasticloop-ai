"use client";

import {
  AlertTriangle,
  CalendarClock,
  ClipboardList,
  Cpu,
  FlaskConical,
  IndianRupee,
  Layers,
  MessageSquareWarning,
  Recycle,
  Scale,
  Smartphone,
  Users,
} from "lucide-react";
import Link from "next/link";
import { MetricCard } from "@/components/common/metric-card";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { CollectionTrend } from "@/components/charts/collection-trend";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { localized, useT } from "@/i18n/i18n";
import type { Page } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { CollectionEvent, PickupRequest } from "@/lib/types";
import { formatDate, formatINR, formatKg, formatNumber } from "@/lib/utils";

export interface Overview {
  collected_kg: number;
  collections: number;
  active_collectors: number;
  flagged_collections: number;
  collected_kg_by_origin: Record<string, number>;
  by_stream: { stream_id: string; code: string; label: string; labels: Record<string, string>; color: string; kg: number }[];
  series: { date: string; kg: number; events: number }[];
  pending_pickups: number;
  open_complaints: number;
  devices: { total: number; online: number; stale: number; offline: number; never_seen: number };
  suspected_mlp_received_kg: number;
  verified_mlp_in_stock_kg: number;
  recovered_kg: { evidence_reviewed: number; evidence_submitted: number; self_reported: number };
  pending_transfers: number;
  revenue_paise: number;
  expenses_paise: number;
  operating_balance_paise: number;
}

function HouseholdDashboard() {
  const { t, locale } = useT();
  const requests = useApi<Page<PickupRequest>>("/pickup-requests", { page_size: 5 });
  const collections = useApi<Page<CollectionEvent>>("/collections", { page_size: 5 });
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>{t("dashboard.household.requests")}</CardTitle>
            <CardDescription>{t("dashboard.household.requestsHint")}</CardDescription>
          </div>
          <Button asChild size="sm">
            <Link href="/pickup-requests?new=1">{t("pickups.request")}</Link>
          </Button>
        </CardHeader>
        <CardContent className="grid gap-2">
          {requests.data?.items.length === 0 && <p className="text-sm text-muted-foreground">{t("dashboard.household.noRequests")}</p>}
          {requests.data?.items.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
              <span>{formatDate(r.preferred_date ?? r.created_at, locale)}</span>
              <StatusBadge value={r.status} />
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <div>
            <CardTitle>{t("dashboard.household.history")}</CardTitle>
            <CardDescription>{t("dashboard.household.historyHint")}</CardDescription>
          </div>
          <Button asChild size="sm" variant="outline">
            <Link href="/complaints?new=1">{t("complaints.report")}</Link>
          </Button>
        </CardHeader>
        <CardContent className="grid gap-2">
          {collections.data?.items.length === 0 && <p className="text-sm text-muted-foreground">{t("common.noData")}</p>}
          {collections.data?.items.map((c) => (
            <div key={c.id} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
              <span>{formatDate(c.collected_at, locale)}</span>
              <span className="tabular font-medium">{formatKg(c.weight_kg, locale)}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}

export default function DashboardPage() {
  const { t, locale } = useT();
  const user = useAuth((s) => s.user);
  const isHousehold = !!user && user.roles.length === 1 && user.roles[0] === "household";
  const ov = useApi<Overview>(isHousehold ? null : "/analytics/overview");
  const d = ov.data;
  const totalKg = d?.collected_kg ?? 0;
  const syntheticKg = (d?.collected_kg_by_origin.demo_seed ?? 0) + (d?.collected_kg_by_origin.simulated ?? 0);
  const fieldOnly = hasRole(user, "collector", "driver") && !hasRole(user, "gp_admin");

  return (
    <>
      <PageHeader
        title={t("dashboard.greeting", { name: user?.full_name.split(" ")[0] ?? "" })}
        description={isHousehold ? t("dashboard.household.subtitle") : t("dashboard.subtitle")}
        actions={
          fieldOnly ? (
            <Button asChild size="lg">
              <Link href="/collector">
                <Smartphone /> {t("nav.items.collector")}
              </Link>
            </Button>
          ) : undefined
        }
      />
      {isHousehold ? (
        <HouseholdDashboard />
      ) : (
        <>
          {d && syntheticKg > 0 && (
            <Alert tone="warning" className="mb-6">
              <FlaskConical />
              <div>
                <AlertTitle>{t("dashboard.syntheticTitle")}</AlertTitle>
                <AlertDescription>
                  {t("dashboard.syntheticBody", { percent: formatNumber(totalKg ? (syntheticKg / totalKg) * 100 : 0, locale, 0) })}
                </AlertDescription>
              </div>
            </Alert>
          )}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <MetricCard loading={ov.isLoading} icon={Scale} label={t("dashboard.kpi.collected")} value={formatKg(d?.collected_kg, locale)}
              hint={t("dashboard.kpi.collectedHint", { count: formatNumber(d?.collections, locale, 0) })} href="/collections" />
            <MetricCard loading={ov.isLoading} icon={Layers} tone="teal" label={t("dashboard.kpi.mlp")} value={formatKg(d?.suspected_mlp_received_kg, locale)}
              hint={t("dashboard.kpi.mlpHint", { verified: formatKg(d?.verified_mlp_in_stock_kg, locale) })} href="/inventory" />
            <MetricCard loading={ov.isLoading} icon={Recycle} label={t("dashboard.kpi.recovered")} value={formatKg(d?.recovered_kg.evidence_reviewed, locale)}
              hint={t("dashboard.kpi.recoveredHint", { pending: formatKg((d?.recovered_kg.evidence_submitted ?? 0) + (d?.recovered_kg.self_reported ?? 0), locale) })}
              href="/recovery" />
            <MetricCard loading={ov.isLoading} icon={IndianRupee} tone={d && d.operating_balance_paise < 0 ? "danger" : "primary"}
              label={t("dashboard.kpi.balance")} value={formatINR(d?.operating_balance_paise, locale)} hint={t("dashboard.kpi.balanceHint")} href="/finance" />
            <MetricCard loading={ov.isLoading} icon={CalendarClock} tone="warning" label={t("dashboard.kpi.pendingPickups")}
              value={formatNumber(d?.pending_pickups, locale, 0)} href="/pickup-requests" />
            <MetricCard loading={ov.isLoading} icon={Users} tone="neutral" label={t("dashboard.kpi.activeCollectors")}
              value={formatNumber(d?.active_collectors, locale, 0)} />
            <MetricCard loading={ov.isLoading} icon={Cpu} tone="teal" label={t("dashboard.kpi.devices")}
              value={d ? `${d.devices.online}/${d.devices.total}` : "—"} hint={t("dashboard.kpi.devicesHint", { offline: d?.devices.offline ?? 0 })} href="/devices" />
            <MetricCard loading={ov.isLoading} icon={MessageSquareWarning} tone={d && d.open_complaints > 0 ? "warning" : "neutral"}
              label={t("dashboard.kpi.complaints")} value={formatNumber(d?.open_complaints, locale, 0)} href="/complaints" />
          </div>

          <div className="mt-6 grid gap-6 xl:grid-cols-[2fr_1fr]">
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>{t("dashboard.trendTitle")}</CardTitle>
                  <CardDescription>{t("dashboard.trendHint")}</CardDescription>
                </div>
              </CardHeader>
              <CardContent>{ov.isLoading ? <Skeleton className="h-64 w-full" /> : <CollectionTrend data={d?.series ?? []} />}</CardContent>
            </Card>
            <Card>
              <CardHeader>
                <div>
                  <CardTitle>{t("dashboard.streamsTitle")}</CardTitle>
                  <CardDescription>{t("dashboard.streamsHint")}</CardDescription>
                </div>
              </CardHeader>
              <CardContent className="grid gap-3">
                {ov.isLoading && <Skeleton className="h-40 w-full" />}
                {d?.by_stream.length === 0 && <p className="text-sm text-muted-foreground">{t("common.noData")}</p>}
                {d?.by_stream.map((s) => (
                  <div key={s.stream_id}>
                    <div className="flex justify-between text-sm">
                      <span className="flex items-center gap-2">
                        <span className="size-2.5 rounded-full" style={{ background: s.color }} aria-hidden />
                        {localized(s.labels, s.label, locale)}
                      </span>
                      <span className="tabular text-muted-foreground">{formatKg(s.kg, locale)}</span>
                    </div>
                    <div className="mt-1.5 h-1.5 rounded-full bg-muted">
                      <div className="h-full rounded-full" style={{ width: `${totalKg ? (s.kg / totalKg) * 100 : 0}%`, background: s.color }} />
                    </div>
                  </div>
                ))}
                {d && (
                  <div className="mt-2 flex flex-wrap items-center gap-2 border-t pt-3 text-xs text-muted-foreground">
                    {t("dashboard.origin")}:
                    {Object.entries(d.collected_kg_by_origin).map(([o, kg]) => (
                      <span key={o} className="inline-flex items-center gap-1">
                        <OriginBadge origin={o} showLive /> {formatKg(kg, locale)}
                      </span>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {d && d.flagged_collections > 0 && (
            <Alert tone="warning" className="mt-6">
              <AlertTriangle />
              <AlertDescription>
                {t("dashboard.flagged", { count: d.flagged_collections })}{" "}
                <Link className="underline" href="/collections?review_status=flagged">
                  <ClipboardList className="inline size-3.5" /> {t("common.review")}
                </Link>
              </AlertDescription>
            </Alert>
          )}
        </>
      )}
    </>
  );
}
