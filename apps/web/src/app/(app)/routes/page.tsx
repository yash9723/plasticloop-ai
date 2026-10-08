"use client";

import { Waypoints } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type Column, DataTable } from "@/components/common/data-table";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useT } from "@/i18n/i18n";
import { hasRole, useAuth } from "@/lib/auth-store";
import { usePagedList } from "@/lib/query";
import type { RouteRow } from "@/lib/types";
import { formatDate, formatKg, formatKm } from "@/lib/utils";

export default function RoutesPage() {
  const { t, locale } = useT();
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const list = usePagedList<RouteRow>("/routes", { sort: "-date" });
  const columns: Column<RouteRow>[] = [
    { key: "date", header: t("common.date"), sortKey: "date", cell: (r) => <span className="whitespace-nowrap font-medium">{formatDate(r.planned_date, locale)}</span> },
    { key: "vehicle", header: t("routes.vehicle"), cell: (r) => <span className="block min-w-36">{r.vehicle_name}</span> },
    { key: "driver", header: t("vehicles.driver"), cell: (r) => r.driver_name ?? t("common.unassigned") },
    { key: "stops", header: t("routes.stops"), cell: (r) => `${r.stops_done}/${r.stops_total}` },
    {
      key: "distance",
      header: t("routes.distance"),
      sortKey: "distance",
      cell: (r) => (
        <span className="flex items-center gap-1.5 whitespace-nowrap">
          {formatKm(r.distance_m, locale)}
          {r.distance_basis === "haversine_estimate" && <Badge tone="neutral">{t("routes.estimate")}</Badge>}
        </span>
      ),
    },
    { key: "load", header: t("routes.load"), cell: (r) => <span className="whitespace-nowrap">{formatKg(r.load_kg, locale)}</span> },
    { key: "status", header: t("common.status"), sortKey: "status", cell: (r) => <StatusBadge value={r.status} /> },
  ];
  return (
    <>
      <PageHeader title={t("nav.items.routes")} description={t("routes.subtitle")}
        actions={hasRole(user, "gp_admin") && (
          <Button asChild>
            <Link href="/routes/planner">
              <Waypoints /> {t("nav.items.routePlanner")}
            </Link>
          </Button>
        )} />
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        <Input type="date" aria-label={t("common.date")} onChange={(e) => list.setFilter("planned_date", e.target.value || undefined)} />
        <Select aria-label={t("common.status")} onChange={(e) => list.setFilter("status", e.target.value || undefined)}>
          <option value="">{t("common.all")}</option>
          {["planned", "in_progress", "completed", "cancelled"].map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </Select>
      </div>
      <DataTable columns={columns} rows={list.data?.items} rowKey={(r) => r.id} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={list.sort} onSortChange={list.setSort} onRowClick={(r) => router.push(`/routes/${r.id}`)} emptyTitle={t("routes.empty")} />
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
    </>
  );
}
