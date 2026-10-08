"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";
import { type Column, DataTable } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, isReadOnly, useAuth } from "@/lib/auth-store";
import { useAssignable, useLabels } from "@/lib/lookups";
import { usePagedList } from "@/lib/query";
import type { PickupRequest } from "@/lib/types";
import { formatDate, formatKg } from "@/lib/utils";

function NewRequestDialog({ defaultOpen }: { defaultOpen: boolean }) {
  const { t } = useT();
  const qc = useQueryClient();
  const labels = useLabels();
  const [open, setOpen] = useState(defaultOpen);
  const [f, setF] = useState({ preferred_date: "", waste_stream_id: "", estimated_weight_kg: "", notes: "" });
  const create = useMutation({
    mutationFn: () =>
      api("/pickup-requests", {
        method: "POST",
        body: {
          preferred_date: f.preferred_date || null,
          waste_stream_id: f.waste_stream_id || null,
          estimated_weight_kg: f.estimated_weight_kg ? Number(f.estimated_weight_kg).toFixed(3) : null,
          notes: f.notes || null,
        },
      }),
    onSuccess: () => {
      toast.success(t("pickups.created"));
      qc.invalidateQueries({ queryKey: ["/pickup-requests"] });
      setOpen(false);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus /> {t("pickups.request")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("pickups.request")}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <Field label={t("pickups.preferredDate")} htmlFor="r-date">
            <Input id="r-date" type="date" value={f.preferred_date} onChange={(e) => setF({ ...f, preferred_date: e.target.value })} />
          </Field>
          <Field label={t("common.stream")} htmlFor="r-stream">
            <Select id="r-stream" value={f.waste_stream_id} onChange={(e) => setF({ ...f, waste_stream_id: e.target.value })}>
              <option value="">{t("pickups.anyStream")}</option>
              {labels.streams.map((s) => (
                <option key={s.id} value={s.id}>
                  {labels.stream(s.id)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label={t("pickups.estimate")} htmlFor="r-weight" hint={t("common.optional")}>
            <Input id="r-weight" inputMode="decimal" value={f.estimated_weight_kg} onChange={(e) => setF({ ...f, estimated_weight_kg: e.target.value })} />
          </Field>
          <Field label={t("common.notes")} htmlFor="r-notes">
            <Textarea id="r-notes" value={f.notes} maxLength={500} onChange={(e) => setF({ ...f, notes: e.target.value })} />
          </Field>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => create.mutate()} disabled={create.isPending}>
            {t("common.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function RowActions({ r }: { r: PickupRequest }) {
  const { t } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const collectors = useAssignable(hasRole(user, "gp_admin") && r.status === "submitted" ? r.village_id : null);
  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) => api(`/pickup-requests/${r.id}`, { method: "PATCH", body: { ...body, version: r.version } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["/pickup-requests"] }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (isReadOnly(user) || ["completed", "cancelled"].includes(r.status)) return null;
  const isAdmin = hasRole(user, "gp_admin");
  const mine = user?.roles.includes("collector") && r.assigned_collector_id === user?.id;
  return (
    <div className="flex flex-wrap justify-end gap-1.5" onClick={(e) => e.stopPropagation()}>
      {isAdmin && r.status === "submitted" && (
        <Select aria-label={t("pickups.assign")} className="h-8 min-w-36 text-xs" value="" onChange={(e) => e.target.value && update.mutate({ status: "assigned", assigned_collector_id: e.target.value })}>
          <option value="">{t("pickups.assign")}</option>
          {collectors.data?.map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name}
            </option>
          ))}
        </Select>
      )}
      {(mine || isAdmin) && r.status === "assigned" && (
        <Button size="sm" variant="outline" onClick={() => update.mutate({ status: "in_progress" })}>
          {t("pickups.start")}
        </Button>
      )}
      {(mine || isAdmin) && ["assigned", "in_progress"].includes(r.status) && (
        <Button size="sm" onClick={() => update.mutate({ status: "completed" })}>
          {t("pickups.complete")}
        </Button>
      )}
      {(isAdmin || ["submitted", "assigned"].includes(r.status)) && !mine && (
        <Button size="sm" variant="ghost" onClick={() => update.mutate({ status: "cancelled", cancelled_reason: "Cancelled from web" })}>
          {t("common.cancel")}
        </Button>
      )}
    </div>
  );
}

function PickupsInner() {
  const { t, locale } = useT();
  const params = useSearchParams();
  const user = useAuth((s) => s.user);
  const labels = useLabels();
  const list = usePagedList<PickupRequest>("/pickup-requests", { sort: "-created" });
  const columns: Column<PickupRequest>[] = [
    { key: "created", header: t("common.created"), sortKey: "created", cell: (r) => <span className="whitespace-nowrap">{formatDate(r.created_at, locale)}</span> },
    { key: "preferred", header: t("pickups.preferredDate"), sortKey: "preferred", cell: (r) => formatDate(r.preferred_date, locale) },
    { key: "village", header: t("common.village"), cell: (r) => <span className="whitespace-nowrap">{labels.village(r.village_id)}</span> },
    { key: "stream", header: t("common.stream"), cell: (r) => (r.waste_stream_id ? labels.stream(r.waste_stream_id) : t("pickups.anyStream")) },
    { key: "estimate", header: t("pickups.estimate"), align: "right", cell: (r) => formatKg(r.estimated_weight_kg, locale) },
    { key: "notes", header: t("common.notes"), cell: (r) => <span className="line-clamp-2 max-w-60 text-xs text-muted-foreground">{r.notes ?? ""}</span> },
    {
      key: "status",
      header: t("common.status"),
      cell: (r) => (
        <span className="flex gap-1">
          <StatusBadge value={r.status} />
          <OriginBadge origin={r.data_origin} />
        </span>
      ),
    },
    { key: "actions", header: <span className="sr-only">{t("common.actions")}</span>, align: "right", cell: (r) => <RowActions r={r} /> },
  ];
  const canRequest = hasRole(user, "household", "gp_admin") && !isReadOnly(user) && !!user?.household_id;
  return (
    <>
      <PageHeader
        title={t("nav.items.pickupRequests")}
        description={t("pickups.subtitle")}
        actions={canRequest && <NewRequestDialog defaultOpen={params.get("new") === "1"} />}
      />
      <div className="mb-4 max-w-xs">
        <Select aria-label={t("common.status")} onChange={(e) => list.setFilter("status", e.target.value || undefined)}>
          <option value="">{t("common.all")}</option>
          {["submitted", "assigned", "in_progress", "completed", "cancelled"].map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </Select>
      </div>
      <DataTable columns={columns} rows={list.data?.items} rowKey={(r) => r.id} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={list.sort} onSortChange={list.setSort} emptyTitle={t("pickups.empty")} />
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
    </>
  );
}

export default function PickupRequestsPage() {
  return (
    <Suspense>
      <PickupsInner />
    </Suspense>
  );
}
