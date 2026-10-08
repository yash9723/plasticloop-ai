"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileCheck2, Minus, Plus, Scissors, ShieldCheck, Shuffle, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { type Column, DataTable } from "@/components/common/data-table";
import { ErrorState } from "@/components/common/error-state";
import { Field } from "@/components/common/field";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { BatchDetail, MaterialCategory } from "@/lib/types";
import { formatDateTime, formatKg } from "@/lib/utils";

type Movement = BatchDetail["movements"][number];
type Dialogs = "sort" | "split" | "adjust" | "review" | null;
const KG_RE = /^\d{1,5}(\.\d{1,3})?$/;
const num = (s: string) => (KG_RE.test(s) ? Number(s) : NaN);

export default function BatchPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const detail = useApi<BatchDetail>(`/inventory/batches/${id}`);
  const categories = useApi<MaterialCategory[]>("/settings/material-categories");
  const [open, setOpen] = useState<Dialogs>(null);
  const [rows, setRows] = useState<{ category_id: string; kg: string }[]>([{ category_id: "", kg: "" }]);
  const [parts, setParts] = useState<string[]>(["", ""]);
  const [adjust, setAdjust] = useState({ type: "loss", kg: "", reason: "" });
  const [review, setReview] = useState<{ decision: "verify" | "reject"; note: string; file: File | null }>({ decision: "verify", note: "", file: null });

  const invalidate = () =>
    qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/inventory") || String(q.queryKey[0]).startsWith("/facilities") });
  const run = useMutation({
    mutationFn: async (kind: Exclude<Dialogs, null>) => {
      const b = detail.data!.batch;
      if (kind === "sort")
        return api(`/inventory/batches/${id}/sort`, { method: "POST", body: { version: b.version, outputs: rows.map((r) => ({ category_id: r.category_id, weight_kg: r.kg })) } });
      if (kind === "split") return api(`/inventory/batches/${id}/split`, { method: "POST", body: { version: b.version, parts_kg: parts.filter(Boolean) } });
      if (kind === "adjust")
        return api(`/inventory/batches/${id}/adjust`, { method: "POST", body: { version: b.version, movement_type: adjust.type, quantity_kg: Number(adjust.kg), reason: adjust.reason } });
      let media_id: string | null = null;
      if (review.file) {
        const form = new FormData();
        form.append("file", review.file, review.file.name);
        form.append("purpose", "verification_evidence");
        media_id = (await api<{ id: string }>("/media", { method: "POST", form })).id;
      }
      return api(`/inventory/batches/${id}/mlp-review`, { method: "POST", body: { version: b.version, decision: review.decision, note: review.note, media_id } });
    },
    onSuccess: () => {
      toast.success(t("common.saved"));
      setOpen(null);
      invalidate();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (detail.error) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  const d = detail.data;
  if (!d) return <Skeleton className="h-96" />;
  const b = d.batch;
  const canEdit = hasRole(user, "mrf_operator") && b.status === "active";
  const sortTotal = rows.reduce((a, r) => a + (num(r.kg) || 0), 0);
  const sortValid = rows.length > 0 && rows.every((r) => r.category_id && num(r.kg) > 0) && sortTotal <= b.current_weight_kg + 0.5;
  const splitTotal = parts.reduce((a, p) => a + (num(p) || 0), 0);
  const splitValid = parts.filter(Boolean).length >= 1 && parts.filter(Boolean).every((p) => num(p) > 0) && splitTotal <= b.current_weight_kg;
  const sortable = (categories.data ?? []).filter((c) => !c.is_unsorted);
  const mlpReviewable = b.is_mlp && (b.verification_status === "suspected" || b.verification_status === "unverified");

  const columns: Column<Movement>[] = [
    { key: "when", header: t("common.date"), cell: (m) => <span className="whitespace-nowrap">{formatDateTime(m.occurred_at, locale)}</span> },
    { key: "type", header: t("common.type"), cell: (m) => t(`inventory.movements.${m.movement_type}`) },
    { key: "qty", header: t("inventory.quantity"), cell: (m) => (
      <span className={`tabular whitespace-nowrap font-medium ${m.quantity_kg < 0 ? "text-red-700 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400"}`}>
        {m.quantity_kg > 0 ? "+" : ""}{formatKg(m.quantity_kg, locale)}
      </span>
    ) },
    { key: "bal", header: t("inventory.balance"), cell: (m) => <span className="tabular whitespace-nowrap">{formatKg(m.balance_after_kg, locale)}</span> },
    { key: "who", header: t("inventory.by"), cell: (m) => m.actor_name ?? "—" },
    { key: "reason", header: t("inventory.reason"), cell: (m) => <span className="block max-w-56 text-sm text-muted-foreground">{m.reason ?? ""}</span> },
  ];

  return (
    <>
      <PageHeader
        title={`${b.code} · ${b.category_label}`}
        description={`${b.facility_name}${b.storage_location ? ` · ${b.storage_location}` : ""}`}
        actions={
          <div className="flex flex-wrap items-center gap-1.5">
            <StatusBadge value={b.status} />
            <StatusBadge value={b.verification_status} />
            <OriginBadge origin={b.data_origin} />
          </div>
        }
      />
      {b.is_mlp && b.verification_status === "suspected" && <Alert tone="warning" className="mb-4">{t("inventory.suspectedNotice")}</Alert>}
      {b.verification_status === "verified_with_evidence" && (
        <Alert tone="success" className="mb-4">
          {t("inventory.verifiedNotice")} {b.verification_note && <q>{b.verification_note}</q>}{" "}
          {d.verification_evidence_url && <a className="font-medium underline" href={d.verification_evidence_url} target="_blank" rel="noreferrer">{t("inventory.viewEvidence")}</a>}
        </Alert>
      )}
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground">{t("inventory.current")}</p><p className="tabular text-2xl font-semibold">{formatKg(b.current_weight_kg, locale)}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground">{t("inventory.initial")}</p><p className="tabular text-2xl font-semibold">{formatKg(b.initial_weight_kg, locale)}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground">{t("inventory.ledgerSum")}</p><p className="tabular text-2xl font-semibold">{formatKg(d.ledger_sum_kg, locale)}</p></CardContent></Card>
        <Card><CardContent className="pt-5"><p className="text-xs text-muted-foreground">{t("inventory.source")}</p><p className="text-2xl font-semibold">{t(`inventory.sources.${b.source}`)}</p></CardContent></Card>
      </div>
      {canEdit && (
        <div className="mb-6 flex flex-wrap gap-2">
          {b.category_code === "mixed_unsorted" && <Button onClick={() => { setRows([{ category_id: "", kg: "" }]); setOpen("sort"); }}><Shuffle /> {t("inventory.sort")}</Button>}
          <Button variant="outline" onClick={() => { setParts(["", ""]); setOpen("split"); }}><Scissors /> {t("inventory.split")}</Button>
          <Button variant="outline" onClick={() => { setAdjust({ type: "loss", kg: "", reason: "" }); setOpen("adjust"); }}><TriangleAlert /> {t("inventory.adjust")}</Button>
          {mlpReviewable && <Button variant="outline" onClick={() => { setReview({ decision: "verify", note: "", file: null }); setOpen("review"); }}><ShieldCheck /> {t("inventory.reviewMlp")}</Button>}
        </div>
      )}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,340px)]">
        <div className="min-w-0">
          <h2 className="mb-3 text-lg font-semibold">{t("inventory.ledger")}</h2>
          <DataTable columns={columns} rows={d.movements} rowKey={(m) => m.id} />
          <p className="mt-2 text-xs text-muted-foreground">{t("inventory.ledgerNote")}</p>
        </div>
        <div className="grid min-w-0 content-start gap-4">
          {[["parents", d.parents], ["children", d.children]].map(([key, links]) => (
            <Card key={key as string}>
              <CardHeader><CardTitle className="text-base">{t(`inventory.${key}`)}</CardTitle></CardHeader>
              <CardContent>
                {(links as BatchDetail["parents"]).length === 0 ? (
                  <p className="text-sm text-muted-foreground">—</p>
                ) : (
                  <ul className="grid gap-1 text-sm">
                    {(links as BatchDetail["parents"]).map((l) => (
                      <li key={l.batch_id} className="flex justify-between gap-2">
                        <Link className="text-primary hover:underline" href={`/inventory/${l.batch_id}`}>{l.code} · {l.category_label}</Link>
                        <span className="tabular text-muted-foreground">{formatKg(l.weight_kg, locale)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          ))}
          {d.operations.map((o) => (
            <Card key={o.id}>
              <CardHeader><CardTitle className="text-base">{t(`inventory.ops.${o.operation_type}`)} · {formatDateTime(o.created_at, locale)}</CardTitle></CardHeader>
              <CardContent className="grid gap-1 text-sm">
                <p>{t("inventory.opInOut", { input: formatKg(o.input_kg, locale), output: formatKg(o.output_kg, locale) })}</p>
                {o.difference_kg !== 0 && <p className="text-amber-700 dark:text-amber-400">{t("inventory.opDifference", { kg: formatKg(o.difference_kg, locale) })}</p>}
                {o.notes && <p className="text-muted-foreground">{o.notes}</p>}
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <Dialog open={open === "sort"} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{t("inventory.sortTitle", { kg: formatKg(b.current_weight_kg, locale) })}</DialogTitle>
            <DialogDescription>{t("inventory.sortHint")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            {rows.map((r, i) => (
              <div key={i} className="grid grid-cols-[1fr_7rem_auto] gap-2">
                <Select aria-label={t("inventory.category")} value={r.category_id} onChange={(e) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, category_id: e.target.value } : x)))}>
                  <option value="">—</option>
                  {sortable.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                </Select>
                <Input aria-label={t("common.weight")} inputMode="decimal" placeholder="kg" value={r.kg} onChange={(e) => setRows((rs) => rs.map((x, j) => (j === i ? { ...x, kg: e.target.value } : x)))} />
                <Button size="icon" variant="ghost" aria-label={t("common.delete")} disabled={rows.length === 1} onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))}><Minus /></Button>
              </div>
            ))}
            <Button variant="ghost" className="justify-start" onClick={() => setRows((rs) => [...rs, { category_id: "", kg: "" }])}><Plus /> {t("inventory.addFraction")}</Button>
            <p className="text-sm">{t("inventory.sortTotals", { out: formatKg(sortTotal, locale), diff: formatKg(b.current_weight_kg - sortTotal, locale) })}</p>
            {sortTotal > b.current_weight_kg + 0.5 && <Alert tone="danger">{t("inventory.sortTooMuch")}</Alert>}
            <p className="text-xs text-muted-foreground">{t("inventory.mlpRule")}</p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(null)}>{t("common.cancel")}</Button>
            <Button disabled={!sortValid || run.isPending} onClick={() => run.mutate("sort")}>{t("inventory.saveSort")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={open === "split"} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("inventory.split")}</DialogTitle>
            <DialogDescription>{t("inventory.splitHint")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            {parts.map((p, i) => (
              <Input key={i} aria-label={`${t("inventory.part")} ${i + 1}`} inputMode="decimal" placeholder={`${t("inventory.part")} ${i + 1} (kg)`} value={p}
                onChange={(e) => setParts((ps) => ps.map((x, j) => (j === i ? e.target.value : x)))} />
            ))}
            <Button variant="ghost" className="justify-start" onClick={() => setParts((ps) => [...ps, ""])}><Plus /> {t("inventory.addPart")}</Button>
            <p className="text-sm">{t("inventory.splitTotals", { total: formatKg(splitTotal, locale), left: formatKg(b.current_weight_kg - splitTotal, locale) })}</p>
          </div>
          <DialogFooter>
            <Button disabled={!splitValid || run.isPending} onClick={() => run.mutate("split")}>{t("inventory.split")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={open === "adjust"} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("inventory.adjust")}</DialogTitle>
            <DialogDescription>{t("inventory.adjustHint")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <Select aria-label={t("common.type")} value={adjust.type} onChange={(e) => setAdjust((a) => ({ ...a, type: e.target.value }))}>
              {["loss", "disposal", "adjustment"].map((m) => <option key={m} value={m}>{t(`inventory.movements.${m}`)}</option>)}
            </Select>
            <Field label={t("inventory.quantity")} htmlFor="adj-kg" hint={adjust.type === "adjustment" ? t("inventory.signedHint") : undefined}>
              <Input id="adj-kg" inputMode="decimal" value={adjust.kg} onChange={(e) => setAdjust((a) => ({ ...a, kg: e.target.value }))} />
            </Field>
            <Field label={t("inventory.reason")} htmlFor="adj-reason" required>
              <Textarea id="adj-reason" value={adjust.reason} onChange={(e) => setAdjust((a) => ({ ...a, reason: e.target.value }))} />
            </Field>
          </div>
          <DialogFooter>
            <Button disabled={!Number(adjust.kg) || adjust.reason.trim().length < 5 || run.isPending} onClick={() => run.mutate("adjust")}>{t("common.save")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={open === "review"} onOpenChange={(o) => !o && setOpen(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2"><FileCheck2 className="size-5" /> {t("inventory.reviewMlp")}</DialogTitle>
            <DialogDescription>{t("inventory.reviewHint")}</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <Select aria-label={t("devices.result")} value={review.decision} onChange={(e) => setReview((r) => ({ ...r, decision: e.target.value as "verify" | "reject" }))}>
              <option value="verify">{t("inventory.decisionVerify")}</option>
              <option value="reject">{t("inventory.decisionReject")}</option>
            </Select>
            <Field label={t("inventory.evidence")} htmlFor="rv-file" required={review.decision === "verify"} hint={t("inventory.evidenceHint")}>
              <Input id="rv-file" type="file" accept="application/pdf,image/jpeg,image/png,image/webp" onChange={(e) => setReview((r) => ({ ...r, file: e.target.files?.[0] ?? null }))} />
            </Field>
            <Field label={t("inventory.reviewNote")} htmlFor="rv-note" required>
              <Textarea id="rv-note" value={review.note} onChange={(e) => setReview((r) => ({ ...r, note: e.target.value }))} />
            </Field>
          </div>
          <DialogFooter>
            <Button disabled={review.note.trim().length < 10 || (review.decision === "verify" && !review.file) || run.isPending} onClick={() => run.mutate("review")}>
              {t("common.submit")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
