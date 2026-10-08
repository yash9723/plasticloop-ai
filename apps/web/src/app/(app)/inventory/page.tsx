"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Combine } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { type Column, DataTable } from "@/components/common/data-table";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi, usePagedList } from "@/lib/query";
import type { Batch, Facility, MaterialCategory } from "@/lib/types";
import { formatDate, formatKg } from "@/lib/utils";

function InventoryList() {
  const { t, locale } = useT();
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const canEdit = hasRole(user, "mrf_operator");
  const facilities = useApi<Facility[]>("/facilities");
  const categories = useApi<MaterialCategory[]>("/settings/material-categories");
  const list = usePagedList<Batch>("/inventory/batches", {
    sort: "-created",
    filters: { facility_id: params.get("facility_id") ?? undefined, category: params.get("category") ?? undefined, status: "active" },
  });
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const merge = useMutation({
    mutationFn: () => api<{ batches: Batch[] }>("/inventory/merge", { method: "POST", body: { batch_ids: [...selected] } }),
    onSuccess: (r) => {
      toast.success(t("inventory.merged", { code: r.batches[0].code }));
      setSelected(new Set());
      qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/inventory") || String(q.queryKey[0]).startsWith("/facilities") });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  const columns: Column<Batch>[] = [
    ...(canEdit
      ? [{ key: "sel", header: "", cell: (r: Batch) => r.status === "active" && (
          <input type="checkbox" aria-label={`${t("inventory.select")} ${r.code}`} checked={selected.has(r.id)}
            onClick={(e) => e.stopPropagation()} onChange={() => toggle(r.id)} />
        ) }]
      : []),
    { key: "code", header: t("inventory.batch"), sortKey: "code", cell: (r) => <span className="font-mono text-xs font-medium">{r.code}</span> },
    { key: "cat", header: t("inventory.category"), cell: (r) => <span className="block min-w-32">{r.category_label}</span> },
    { key: "facility", header: t("common.facility"), cell: (r) => <span className="block min-w-32 text-sm">{r.facility_name}</span> },
    { key: "weight", header: t("inventory.current"), sortKey: "weight", cell: (r) => <span className="whitespace-nowrap font-medium">{formatKg(r.current_weight_kg, locale)}</span> },
    { key: "verify", header: t("inventory.verification"), cell: (r) => <StatusBadge value={r.verification_status} /> },
    { key: "created", header: t("common.created"), sortKey: "created", cell: (r) => <span className="whitespace-nowrap">{formatDate(r.created_at, locale)}</span> },
    {
      key: "status",
      header: t("common.status"),
      cell: (r) => (
        <span className="flex flex-wrap gap-1">
          <StatusBadge value={r.status} />
          <OriginBadge origin={r.data_origin} />
        </span>
      ),
    },
  ];
  return (
    <>
      <PageHeader title={t("nav.items.inventory")} description={t("inventory.subtitle")}
        actions={canEdit && (
          <Button variant="outline" disabled={selected.size < 2 || merge.isPending} onClick={() => merge.mutate()}>
            <Combine /> {t("inventory.mergeN", { n: selected.size })}
          </Button>
        )} />
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
        <Input placeholder={t("inventory.search")} aria-label={t("common.search")} onChange={(e) => list.setFilter("q", e.target.value || undefined)} />
        <Select aria-label={t("common.facility")} value={String(list.filters.facility_id ?? "")} onChange={(e) => list.setFilter("facility_id", e.target.value || undefined)}>
          <option value="">{t("inventory.allFacilities")}</option>
          {facilities.data?.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </Select>
        <Select aria-label={t("inventory.category")} value={String(list.filters.category ?? "")} onChange={(e) => list.setFilter("category", e.target.value || undefined)}>
          <option value="">{t("inventory.allCategories")}</option>
          {categories.data?.map((c) => (
            <option key={c.code} value={c.code}>
              {c.label}
            </option>
          ))}
        </Select>
        <Select aria-label={t("inventory.verification")} onChange={(e) => list.setFilter("verification", e.target.value || undefined)}>
          <option value="">{t("inventory.anyVerification")}</option>
          {["unverified", "suspected", "verified_with_evidence", "verification_rejected"].map((v) => (
            <option key={v} value={v}>
              {t(`status.${v}`)}
            </option>
          ))}
        </Select>
        <Select aria-label={t("common.status")} value={String(list.filters.status ?? "")} onChange={(e) => list.setFilter("status", e.target.value || undefined)}>
          <option value="active">{t("status.active")}</option>
          <option value="depleted">{t("status.depleted")}</option>
          <option value="">{t("common.all")}</option>
        </Select>
      </div>
      <DataTable columns={columns} rows={list.data?.items} rowKey={(r) => r.id} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={list.sort} onSortChange={list.setSort} onRowClick={(r) => router.push(`/inventory/${r.id}`)} emptyTitle={t("inventory.empty")} />
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
    </>
  );
}

export default function InventoryPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <InventoryList />
    </Suspense>
  );
}
