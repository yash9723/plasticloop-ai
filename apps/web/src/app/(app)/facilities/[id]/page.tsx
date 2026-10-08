"use client";

import { AlertTriangle, CheckCircle2, Scale } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { type Column, DataTable } from "@/components/common/data-table";
import { ErrorState } from "@/components/common/error-state";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { useApi, usePagedList } from "@/lib/query";
import type { CategoryStock, Facility, Intake, MassBalance } from "@/lib/types";
import { formatDateTime, formatKg } from "@/lib/utils";

const PERIODS = [7, 30, 90] as const;

function MassBalanceCard({ facilityId }: { facilityId: string }) {
  const { t, locale } = useT();
  const [days, setDays] = useState<number>(30);
  const [now] = useState(() => Date.now());
  const mb = useApi<MassBalance>(`/facilities/${facilityId}/mass-balance`, { start: new Date(now - days * 86400_000).toISOString() });
  const d = mb.data;
  const rows: [string, number | null, string?][] = d
    ? [
        ["opening", d.opening_kg],
        ["intake", d.intake_kg, "+"],
        ["returned", d.returned_kg, "+"],
        ["transferred", -d.transferred_out_kg, "−"],
        ["loss", -d.loss_kg, "−"],
        ["disposed", -d.disposed_kg, "−"],
        ["adjustment", d.adjustment_kg],
        ["unexplained", -d.unexplained_processing_difference_kg, "−"],
        ["closing", d.closing_kg],
      ]
    : [];
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-2">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <Scale className="size-4" /> {t("facilities.massBalance")}
          </CardTitle>
          <CardDescription>{t("facilities.massBalanceHint")}</CardDescription>
        </div>
        <Select aria-label={t("facilities.period")} value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-32">
          {PERIODS.map((p) => (
            <option key={p} value={p}>
              {t("facilities.lastDays", { n: p })}
            </option>
          ))}
        </Select>
      </CardHeader>
      <CardContent className="grid gap-3">
        {!d ? (
          <Skeleton className="h-48" />
        ) : (
          <>
            <dl className="grid gap-1 text-sm">
              {rows.map(([key, value]) => (
                <div key={key} className={`flex justify-between gap-2 ${key === "closing" || key === "opening" ? "border-t pt-1 font-medium" : ""}`}>
                  <dt className="text-muted-foreground">{t(`facilities.mb.${key}`)}</dt>
                  <dd className="tabular">{formatKg(value, locale)}</dd>
                </div>
              ))}
            </dl>
            {d.flagged ? (
              <Alert tone="warning">
                <span className="flex items-center gap-2"><AlertTriangle className="size-4 shrink-0" />
                  {t("facilities.mbFlagged", { kg: formatKg(d.unexplained_processing_difference_kg, locale), tol: formatKg(d.tolerance_kg, locale) })}</span>
              </Alert>
            ) : (
              <p className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-400">
                <CheckCircle2 className="size-4" /> {t("facilities.mbOk", { tol: formatKg(d.tolerance_kg, locale) })}
              </p>
            )}
            {d.declared_collected_kg != null && (
              <p className="text-xs text-muted-foreground">
                {t("facilities.collectionGap", { declared: formatKg(d.declared_collected_kg, locale), gap: formatKg(d.collection_to_intake_gap_kg, locale) })}
              </p>
            )}
            <p className="text-xs text-muted-foreground">{d.ledger_consistent ? t("facilities.ledgerOk") : t("facilities.ledgerBad")}</p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export default function FacilityDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useT();
  const router = useRouter();
  const facility = useApi<Facility>(`/facilities/${id}`);
  const stock = useApi<CategoryStock[]>(`/facilities/${id}/stock`);
  const intakes = usePagedList<Intake>(`/facilities/${id}/intakes`, { sort: "-received", pageSize: 10 });
  if (facility.error) return <ErrorState error={facility.error} onRetry={() => facility.refetch()} />;
  const f = facility.data;
  const chart = (stock.data ?? []).filter((s) => s.stock_kg > 0).map((s) => ({ name: s.category_label, kg: s.stock_kg, mlp: s.is_mlp }));
  const columns: Column<Intake>[] = [
    { key: "code", header: t("common.code"), cell: (r) => <span className="font-mono text-xs">{r.code}</span> },
    { key: "when", header: t("facilities.received"), cell: (r) => <span className="whitespace-nowrap">{formatDateTime(r.received_at, locale)}</span> },
    { key: "village", header: t("common.village"), cell: (r) => r.village_name ?? r.transporter_name ?? "—" },
    { key: "net", header: t("facilities.net"), cell: (r) => <span className="whitespace-nowrap font-medium">{formatKg(r.net_kg, locale)}</span> },
    { key: "declared", header: t("facilities.declared"), cell: (r) => <span className="whitespace-nowrap">{formatKg(r.declared_collected_kg, locale)}</span> },
    { key: "batch", header: t("inventory.batch"), cell: (r) => (r.batch_id ? <Link className="text-primary hover:underline" href={`/inventory/${r.batch_id}`} onClick={(e) => e.stopPropagation()}>{r.batch_code}</Link> : "—") },
    { key: "origin", header: "", cell: (r) => <OriginBadge origin={r.data_origin} /> },
  ];
  return (
    <>
      <PageHeader title={f?.name ?? t("common.loading")} description={f ? `${f.code} · ${t(`facilities.types.${f.facility_type}`)} · ${f.village_names.join(", ")}` : undefined}
        actions={f?.is_sample && <OriginBadge origin="demo_seed" />} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,380px)]">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="text-base">{t("facilities.stockByCategory")}</CardTitle>
            <CardDescription>{t("facilities.stockHint")}</CardDescription>
          </CardHeader>
          <CardContent>
            {!stock.data ? (
              <Skeleton className="h-64" />
            ) : (
              <>
                <div className="h-64" role="img" aria-label={t("facilities.stockByCategory")}>
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chart} layout="vertical" margin={{ left: 8, right: 16 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" horizontal={false} />
                      <XAxis type="number" tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} unit=" kg" />
                      <YAxis type="category" dataKey="name" width={130} tick={{ fontSize: 11, fill: "var(--muted-foreground)" }} />
                      <Tooltip formatter={(v) => formatKg(Number(v), locale)} contentStyle={{ background: "var(--popover)", border: "1px solid var(--border)", borderRadius: 10, fontSize: 12 }} />
                      <Bar dataKey="kg" fill="var(--chart-1)" radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <ul className="mt-3 grid gap-1 text-sm sm:grid-cols-2">
                  {stock.data.map((s) => (
                    <li key={s.category_code} className="flex items-center justify-between gap-2">
                      <Link className="hover:underline" href={`/inventory?facility_id=${id}&category=${s.category_code}`}>
                        {s.category_label} {s.is_mlp && <Badge tone="warning">{t("inventory.suspectedOnly")}</Badge>}
                      </Link>
                      <span className="tabular text-muted-foreground">{formatKg(s.stock_kg, locale)} · {s.batches}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </CardContent>
        </Card>
        <MassBalanceCard facilityId={id} />
      </div>
      <h2 className="mb-3 mt-8 text-lg font-semibold">{t("facilities.intakes")}</h2>
      <DataTable columns={columns} rows={intakes.data?.items} rowKey={(r) => r.id} loading={intakes.isLoading} error={intakes.error}
        onRetry={() => intakes.refetch()} onRowClick={(r) => r.batch_id && router.push(`/inventory/${r.batch_id}`)} emptyTitle={t("facilities.noIntakes")} />
      <Pagination page={intakes.page} pageSize={intakes.pageSize} total={intakes.data?.total ?? 0} onPageChange={intakes.setPage} />
    </>
  );
}
