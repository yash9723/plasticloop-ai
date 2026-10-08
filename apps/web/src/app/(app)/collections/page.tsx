"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { type Column, DataTable } from "@/components/common/data-table";
import { MeasurementBadge, OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useT } from "@/i18n/i18n";
import { hasRole, isReadOnly, useAuth } from "@/lib/auth-store";
import { useLabels } from "@/lib/lookups";
import { usePagedList } from "@/lib/query";
import type { CollectionEvent } from "@/lib/types";
import { formatDateTime, formatKg } from "@/lib/utils";

function CollectionsInner() {
  const { t, locale } = useT();
  const router = useRouter();
  const params = useSearchParams();
  const user = useAuth((s) => s.user);
  const labels = useLabels();
  const list = usePagedList<CollectionEvent>("/collections", {
    sort: "-collected_at",
    filters: { review_status: params.get("review_status") ?? undefined },
  });
  const f = list.filters;

  const columns: Column<CollectionEvent>[] = [
    { key: "time", header: t("common.date"), sortKey: "collected_at", cell: (r) => <span className="whitespace-nowrap">{formatDateTime(r.collected_at, locale)}</span> },
    {
      key: "point",
      header: t("collections.point"),
      cell: (r) => (
        <span className="block min-w-40">
          <span className="block font-medium">{r.collection_point_code}</span>
          <span className="block truncate text-xs text-muted-foreground">{r.collection_point_name}</span>
        </span>
      ),
    },
    {
      key: "stream",
      header: t("common.stream"),
      cell: (r) => (
        <span className="inline-flex items-center gap-2 whitespace-nowrap">
          <span className="size-2.5 rounded-full" style={{ background: labels.streamColor(r.waste_stream_id) }} aria-hidden />
          {labels.stream(r.waste_stream_id)}
        </span>
      ),
    },
    { key: "weight", header: t("common.weight"), sortKey: "weight", align: "right", cell: (r) => <span className="tabular font-medium">{formatKg(r.weight_kg, locale)}</span> },
    { key: "source", header: t("collections.source"), cell: (r) => <MeasurementBadge source={r.measurement_source} /> },
    { key: "collector", header: t("common.collector"), cell: (r) => <span className="whitespace-nowrap">{r.collector_name}</span> },
    {
      key: "status",
      header: t("common.status"),
      cell: (r) => (
        <span className="flex flex-wrap gap-1">
          <StatusBadge value={r.review_status} />
          <OriginBadge origin={r.data_origin} />
        </span>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={t("nav.items.collections")}
        description={t("collections.subtitle")}
        actions={
          hasRole(user, "collector", "gp_admin", "driver") &&
          !isReadOnly(user) && (
            <Button asChild>
              <Link href="/collections/new">
                <Plus /> {t("command.newCollection")}
              </Link>
            </Button>
          )
        }
      />
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <Select aria-label={t("common.village")} value={String(f.village_id ?? "")} onChange={(e) => list.setFilter("village_id", e.target.value || undefined)}>
          <option value="">{t("collections.allVillages")}</option>
          {labels.villages.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </Select>
        <Select aria-label={t("common.stream")} value={String(f.waste_stream_id ?? "")} onChange={(e) => list.setFilter("waste_stream_id", e.target.value || undefined)}>
          <option value="">{t("collections.allStreams")}</option>
          {labels.streams.map((s) => (
            <option key={s.id} value={s.id}>
              {labels.stream(s.id)}
            </option>
          ))}
        </Select>
        <Select aria-label={t("common.status")} value={String(f.review_status ?? "")} onChange={(e) => list.setFilter("review_status", e.target.value || undefined)}>
          <option value="">{t("collections.anyReview")}</option>
          <option value="ok">{t("status.ok")}</option>
          <option value="flagged">{t("status.flagged")}</option>
          <option value="resolved">{t("status.resolved")}</option>
        </Select>
        <Input type="date" aria-label={t("common.from")} value={String(f.date_from ?? "").slice(0, 10)}
          onChange={(e) => list.setFilter("date_from", e.target.value ? `${e.target.value}T00:00:00+05:30` : undefined)} />
        <Input type="date" aria-label={t("common.to")} value={String(f.date_to ?? "").slice(0, 10)}
          onChange={(e) => list.setFilter("date_to", e.target.value ? `${e.target.value}T23:59:59+05:30` : undefined)} />
      </div>
      <DataTable
        columns={columns}
        rows={list.data?.items}
        rowKey={(r) => r.id}
        loading={list.isLoading}
        error={list.error}
        onRetry={() => list.refetch()}
        sort={list.sort}
        onSortChange={list.setSort}
        onRowClick={(r) => router.push(`/collections/${r.id}`)}
        emptyTitle={t("collections.empty")}
      />
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
    </>
  );
}

export default function CollectionsPage() {
  return (
    <Suspense>
      <CollectionsInner />
    </Suspense>
  );
}
