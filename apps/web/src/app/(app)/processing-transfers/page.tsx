"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { type Column, DataTable } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { useT } from "@/i18n/i18n";
import { api, errorMessage, type Page } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi, usePagedList } from "@/lib/query";
import type { Batch, Partner, Transfer, TransferDetail } from "@/lib/types";
import { formatDate, formatKg } from "@/lib/utils";

function NewTransfer({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const router = useRouter();
  const batches = useApi<Page<Batch>>("/inventory/batches", { status: "active", page_size: 200, sort: "-created" });
  const [batchId, setBatchId] = useState("");
  const batch = batches.data?.items.find((b) => b.id === batchId);
  const partners = useApi<Partner[]>(batch ? "/processors" : null, { category: batch?.category_code });
  const [partnerId, setPartnerId] = useState("");
  const [kg, setKg] = useState("");
  const [transporter, setTransporter] = useState("");
  const save = useMutation({
    mutationFn: () => api<TransferDetail>("/processing-transfers", { method: "POST", body: { batch_id: batchId, partner_id: partnerId, kg, transporter_name: transporter || null } }),
    onSuccess: (r) => {
      r.warnings.forEach((w) => toast.warning(w));
      qc.invalidateQueries({ predicate: (q) => ["/processing-transfers", "/inventory"].some((p) => String(q.queryKey[0]).startsWith(p)) });
      onOpenChange(false);
      router.push(`/processing-transfers/${r.id}`);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const eligible = (batches.data?.items ?? []).filter((b) => b.category_code !== "mixed_unsorted" && b.processing_eligible);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("transfers.new")}</DialogTitle>
          <DialogDescription>{t("transfers.newHint")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-3">
          <Field label={t("inventory.batch")} htmlFor="tr-batch" required>
            <Select id="tr-batch" value={batchId} onChange={(e) => { setBatchId(e.target.value); setPartnerId(""); setKg(""); }}>
              <option value="">—</option>
              {eligible.map((b) => (
                <option key={b.id} value={b.id}>{b.code} · {b.category_label} · {formatKg(b.current_weight_kg, locale)}</option>
              ))}
            </Select>
          </Field>
          {batch?.verification_status === "suspected" && <Alert tone="warning">{t("transfers.suspectedNote")}</Alert>}
          <Field label={t("transfers.partner")} htmlFor="tr-partner" required hint={batch && partners.data?.length === 0 ? t("transfers.noPartner") : undefined}>
            <Select id="tr-partner" value={partnerId} onChange={(e) => setPartnerId(e.target.value)} disabled={!batch}>
              <option value="">—</option>
              {partners.data?.map((p) => <option key={p.id} value={p.id}>{p.display_name}</option>)}
            </Select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t("transfers.kg")} htmlFor="tr-kg" required>
              <Input id="tr-kg" inputMode="decimal" value={kg} placeholder={batch ? String(batch.current_weight_kg) : ""} onChange={(e) => setKg(e.target.value)} />
            </Field>
            <Field label={t("intake.transporter")} htmlFor="tr-transporter">
              <Input id="tr-transporter" value={transporter} onChange={(e) => setTransporter(e.target.value)} />
            </Field>
          </div>
        </div>
        <DialogFooter>
          <Button disabled={!batchId || !partnerId || !(Number(kg) > 0) || save.isPending} onClick={() => save.mutate()}>{t("transfers.allocate")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function TransfersPage() {
  const { t, locale } = useT();
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const list = usePagedList<Transfer>("/processing-transfers", { sort: "-created" });
  const [open, setOpen] = useState(false);
  const columns: Column<Transfer>[] = [
    { key: "code", header: t("common.code"), cell: (r) => <span className="font-mono text-xs font-medium">{r.code}</span> },
    { key: "date", header: t("common.created"), cell: (r) => <span className="whitespace-nowrap">{formatDate(r.created_at, locale)}</span> },
    { key: "material", header: t("inventory.category"), cell: (r) => <span className="block min-w-32">{r.category_label}</span> },
    { key: "partner", header: t("transfers.partner"), cell: (r) => <span className="block min-w-36">{r.partner_name}</span> },
    { key: "kg", header: t("transfers.kg"), cell: (r) => <span className="tabular whitespace-nowrap">{formatKg(r.allocated_kg, locale)}</span> },
    { key: "received", header: t("transfers.received"), cell: (r) => (
      <span className="flex items-center gap-1 whitespace-nowrap">
        {formatKg(r.received_kg, locale)}
        {r.discrepancy_flag && <AlertTriangle className="size-4 text-amber-600" aria-label={t("transfers.discrepancy")} />}
      </span>
    ) },
    { key: "status", header: t("common.status"), cell: (r) => <span className="flex gap-1"><StatusBadge value={r.status} /><OriginBadge origin={r.data_origin} /></span> },
  ];
  return (
    <>
      <PageHeader title={t("nav.items.transfers")} description={t("transfers.subtitle")}
        actions={hasRole(user, "mrf_operator") && <Button onClick={() => setOpen(true)}><Plus /> {t("transfers.new")}</Button>} />
      <Alert tone="info" className="mb-4">{t("transfers.notRecycled")}</Alert>
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        <Select aria-label={t("common.status")} onChange={(e) => list.setFilter("status", e.target.value || undefined)}>
          <option value="">{t("common.all")}</option>
          {["allocated", "dispatched", "received", "accepted", "partially_accepted", "rejected", "completed", "cancelled"].map((s) => (
            <option key={s} value={s}>{t(`status.${s}`)}</option>
          ))}
        </Select>
      </div>
      <DataTable columns={columns} rows={list.data?.items} rowKey={(r) => r.id} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        onRowClick={(r) => router.push(`/processing-transfers/${r.id}`)} emptyTitle={t("transfers.empty")} />
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
      {open && <NewTransfer open={open} onOpenChange={setOpen} />}
    </>
  );
}
