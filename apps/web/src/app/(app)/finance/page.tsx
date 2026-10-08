"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { IndianRupee, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { type Column, DataTable } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { MetricCard } from "@/components/common/metric-card";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n/i18n";
import { api, errorMessage, type Page } from "@/lib/api";
import { hasRole, isReadOnly, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { ExpenseRow, SaleRow } from "@/lib/types";
import { formatDate, formatINR, formatKg } from "@/lib/utils";

interface Summary {
  revenue_paise: number; received_paise: number; receivable_paise: number; expenses_recorded_paise: number; expenses_estimated_paise: number;
  operating_balance_paise: number; collected_kg: number; recorded_cost_per_kg_paise: number | null; includes_synthetic_records: boolean;
  expenses_by_category: { category: string; estimate: boolean; amount_paise: number }[];
}
const CATEGORIES = ["collection_labor", "fuel_vehicle", "transport", "equipment_maintenance", "facility_operations", "processing_fees", "other"] as const;

function ExpenseDialog({ onClose }: { onClose: () => void }) {
  const { t } = useT();
  const qc = useQueryClient();
  const [f, setF] = useState({ category: "collection_labor", amount: "", date: new Date().toISOString().slice(0, 10), description: "", estimate: false, assumption: "" });
  const save = useMutation({
    mutationFn: () => api("/finance/expenses", { method: "POST", body: { category: f.category, amount_paise: Math.round(Number(f.amount) * 100), incurred_on: f.date,
      description: f.description || null, is_estimate: f.estimate, assumption_note: f.estimate ? f.assumption : null } }),
    onSuccess: () => { toast.success(t("common.saved")); qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/finance") }); onClose(); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader><DialogTitle>{t("finance.addExpense")}</DialogTitle></DialogHeader>
        <div className="grid gap-3">
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("common.type")} htmlFor="ex-cat">
              <Select id="ex-cat" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>
                {CATEGORIES.map((c) => <option key={c} value={c}>{t(`finance.cats.${c}`)}</option>)}
              </Select>
            </Field>
            <Field label={t("finance.amount")} htmlFor="ex-amt" required><Input id="ex-amt" inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
          </div>
          <Field label={t("common.date")} htmlFor="ex-date"><Input id="ex-date" type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          <Field label={t("common.notes")} htmlFor="ex-desc"><Textarea id="ex-desc" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
          <label className="flex items-center justify-between gap-2 text-sm">{t("finance.isEstimate")}<Switch checked={f.estimate} onCheckedChange={(v) => setF({ ...f, estimate: v })} /></label>
          {f.estimate && <Field label={t("finance.assumption")} htmlFor="ex-ass" required><Textarea id="ex-ass" value={f.assumption} onChange={(e) => setF({ ...f, assumption: e.target.value })} /></Field>}
        </div>
        <DialogFooter><Button disabled={!(Number(f.amount) > 0) || (f.estimate && f.assumption.trim().length < 5) || save.isPending} onClick={() => save.mutate()}>{t("common.save")}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function FinancePage() {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const [days, setDays] = useState(30);
  const [now] = useState(() => Date.now());
  const s = useApi<Summary>("/finance/summary", { date_from: new Date(now - days * 86400_000).toISOString() });
  const sales = useApi<Page<SaleRow>>("/finance/sales", { page_size: 20 });
  const expenses = useApi<Page<ExpenseRow>>("/finance/expenses", { page_size: 20 });
  const [open, setOpen] = useState(false);
  const pay = useMutation({
    mutationFn: (sale: SaleRow) => api(`/finance/sales/${sale.id}/payments`, { method: "POST", body: {
      amount_paise: sale.total_paise - sale.paid_paise, paid_on: new Date().toISOString().slice(0, 10), method: "bank_transfer" } }),
    onSuccess: () => { toast.success(t("common.saved")); qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/finance") }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const d = s.data;
  const saleCols: Column<SaleRow>[] = [
    { key: "date", header: t("common.date"), cell: (r) => <span className="whitespace-nowrap">{formatDate(r.sold_on, locale)}</span> },
    { key: "buyer", header: t("finance.buyer"), cell: (r) => r.buyer_name },
    { key: "kg", header: t("common.weight"), cell: (r) => formatKg(r.quantity_kg, locale) },
    { key: "total", header: t("finance.total"), cell: (r) => <span className="tabular">{formatINR(r.total_paise, locale)}</span> },
    { key: "paid", header: t("finance.paid"), cell: (r) => <span className="tabular">{formatINR(r.paid_paise, locale)}</span> },
    { key: "status", header: t("common.status"), cell: (r) => (
      <span className="flex items-center gap-1">
        <StatusBadge value={r.payment_status} /><OriginBadge origin={r.data_origin} />
        {hasRole(user, "mrf_operator") && r.payment_status !== "paid" && (
          <Button size="sm" variant="outline" onClick={() => pay.mutate(r)} disabled={pay.isPending}>{t("finance.markPaid")}</Button>
        )}
      </span>
    ) },
  ];
  const expCols: Column<ExpenseRow>[] = [
    { key: "date", header: t("common.date"), cell: (r) => <span className="whitespace-nowrap">{formatDate(r.incurred_on, locale)}</span> },
    { key: "cat", header: t("common.type"), cell: (r) => t(`finance.cats.${r.category}`) },
    { key: "amount", header: t("finance.amount"), cell: (r) => <span className="tabular">{formatINR(r.amount_paise, locale)}</span> },
    { key: "est", header: "", cell: (r) => (
      <span className="flex gap-1">{r.is_estimate && <Badge tone="warning" title={r.assumption_note ?? undefined}>{t("finance.estimate")}</Badge>}<OriginBadge origin={r.data_origin} /></span>
    ) },
  ];
  return (
    <>
      <PageHeader title={t("nav.items.finance")} description={t("finance.subtitle")}
        actions={
          <div className="flex gap-2">
            <Select aria-label={t("facilities.period")} value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-36">
              {[30, 90, 365].map((n) => <option key={n} value={n}>{t("facilities.lastDays", { n })}</option>)}
            </Select>
            {!isReadOnly(user) && <Button onClick={() => setOpen(true)}><Plus /> {t("finance.addExpense")}</Button>}
          </div>
        } />
      {d?.includes_synthetic_records && <Alert tone="warning" className="mb-4">{t("finance.synthetic")}</Alert>}
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard icon={IndianRupee} label={t("finance.revenue")} value={formatINR(d?.revenue_paise ?? null, locale)} loading={!d}
          hint={d ? t("finance.receivedHint", { received: formatINR(d.received_paise, locale) }) : undefined} />
        <MetricCard tone="warning" label={t("finance.receivable")} value={formatINR(d?.receivable_paise ?? null, locale)} loading={!d} />
        <MetricCard tone="neutral" label={t("finance.expenses")} value={formatINR(d?.expenses_recorded_paise ?? null, locale)} loading={!d}
          hint={d?.expenses_estimated_paise ? t("finance.plusEstimates", { amount: formatINR(d.expenses_estimated_paise, locale) }) : undefined} />
        <MetricCard tone={d && d.operating_balance_paise < 0 ? "danger" : "primary"} label={t("finance.balance")} value={formatINR(d?.operating_balance_paise ?? null, locale)} loading={!d}
          hint={d?.recorded_cost_per_kg_paise != null ? t("finance.perKg", { cost: formatINR(d.recorded_cost_per_kg_paise, locale) }) : undefined} />
      </div>
      <p className="mb-6 text-xs text-muted-foreground">{t("finance.notes")}</p>
      <div className="grid gap-4 xl:grid-cols-2">
        <Card className="min-w-0"><CardHeader><CardTitle className="text-base">{t("finance.sales")}</CardTitle></CardHeader>
          <CardContent><DataTable columns={saleCols} rows={sales.data?.items} rowKey={(r) => r.id} loading={sales.isLoading} emptyTitle={t("finance.noSales")} /></CardContent></Card>
        <Card className="min-w-0"><CardHeader><CardTitle className="text-base">{t("finance.expenseList")}</CardTitle></CardHeader>
          <CardContent><DataTable columns={expCols} rows={expenses.data?.items} rowKey={(r) => r.id} loading={expenses.isLoading} emptyTitle={t("finance.noExpenses")} /></CardContent></Card>
      </div>
      {open && <ExpenseDialog onClose={() => setOpen(false)} />}
    </>
  );
}
