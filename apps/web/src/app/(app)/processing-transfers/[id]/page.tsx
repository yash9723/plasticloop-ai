"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Circle, PackageCheck, Send, Truck } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { ErrorState } from "@/components/common/error-state";
import { Field } from "@/components/common/field";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { TransferDetail } from "@/lib/types";
import { cn, formatDate, formatDateTime, formatKg } from "@/lib/utils";

const STEPS = ["allocated", "dispatched", "received", "decided", "completed"] as const;
const OUTCOMES = ["recycled_with_evidence", "recovered_documented_process", "accepted_for_processing", "awaiting_confirmation"] as const;

function stepIndex(status: string) {
  if (status === "allocated") return 0;
  if (status === "dispatched") return 1;
  if (status === "received") return 2;
  if (["accepted", "partially_accepted", "rejected"].includes(status)) return 3;
  return status === "completed" ? 4 : -1;
}

export default function TransferPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const detail = useApi<TransferDetail>(`/processing-transfers/${id}`);
  const [receive, setReceive] = useState({ kg: "", ref: "" });
  const [decide, setDecide] = useState({ accepted: "", rejected: "0", reason: "", ret: true });
  const [outcome, setOutcome] = useState({ type: "recycled_with_evidence", input: "", output: "", date: new Date().toISOString().slice(0, 10), attested: "", desc: "" });
  const [file, setFile] = useState<File | null>(null);
  const act = useMutation({
    mutationFn: async ({ path, body }: { path: string; body: unknown }) => api(`/processing-transfers/${path}`, { method: "POST", body }),
    onSuccess: () => {
      toast.success(t("common.saved"));
      qc.invalidateQueries({ predicate: (q) => ["/processing-transfers", "/inventory", "/facilities", "/analytics"].some((p) => String(q.queryKey[0]).startsWith(p)) });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const report = useMutation({
    mutationFn: async () => {
      let evidence_media_id: string | null = null;
      if (file) {
        const form = new FormData();
        form.append("file", file, file.name);
        form.append("purpose", "outcome_evidence");
        evidence_media_id = (await api<{ id: string }>("/media", { method: "POST", form })).id;
      }
      return api(`/processing-transfers/${id}/outcomes`, { method: "POST", body: {
        outcome_type: outcome.type, input_kg: outcome.input, output_kg: outcome.output, process_date: outcome.date,
        attested_by_name: outcome.attested, process_description: outcome.desc || null, evidence_media_id } });
    },
    onSuccess: () => {
      toast.success(t("transfers.outcomeSaved"));
      setFile(null);
      qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/processing-transfers") });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (detail.error) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  const d = detail.data;
  if (!d) return <Skeleton className="h-96" />;
  const isOperator = hasRole(user, "mrf_operator");
  const isPartner = hasRole(user, "processor");
  const step = stepIndex(d.status);
  const needsEvidence = outcome.type === "recycled_with_evidence" || outcome.type === "recovered_documented_process";
  const acceptedValue = decide.accepted !== "" ? decide.accepted : String(+((d.received_kg ?? 0) - Number(decide.rejected || 0)).toFixed(3));
  const reported = d.outcomes.filter((o) => o.outcome_type !== "rejected").reduce((a, o) => a + o.input_kg, 0);

  return (
    <>
      <PageHeader title={`${d.code} · ${d.category_label}`} description={`${d.facility_name} → ${d.partner_name}`}
        actions={<div className="flex gap-1.5"><StatusBadge value={d.status} /><OriginBadge origin={d.data_origin} /></div>} />
      <ol className="mb-6 grid grid-cols-5 gap-2 text-xs" aria-label={t("transfers.progress")}>
        {STEPS.map((s, i) => (
          <li key={s} className={cn("flex flex-col items-center gap-1 text-center", i <= step ? "text-primary" : "text-muted-foreground")}>
            {i <= step ? <CheckCircle2 className="size-5" /> : <Circle className="size-5" />}
            {t(`transfers.steps.${s}`)}
          </li>
        ))}
      </ol>
      {d.verification_status === "suspected" && <Alert tone="warning" className="mb-4">{t("transfers.suspectedNote")}</Alert>}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,380px)]">
        <div className="grid min-w-0 content-start gap-4">
          <Card>
            <CardHeader><CardTitle className="text-base">{t("transfers.weights")}</CardTitle></CardHeader>
            <CardContent>
              <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
                {[
                  ["allocated", d.allocated_kg], ["received", d.received_kg], ["discrepancy", d.receipt_discrepancy_kg],
                  ["accepted", d.accepted_kg], ["rejected", d.rejected_kg], ["returned", d.returned_kg],
                ].map(([k, v]) => (
                  <div key={k as string}>
                    <dt className="text-xs text-muted-foreground">{t(`transfers.w.${k}`)}</dt>
                    <dd className={cn("tabular text-lg font-semibold", k === "discrepancy" && d.discrepancy_flag && "text-amber-600")}>{formatKg(v as number | null, locale, true)}</dd>
                  </div>
                ))}
              </dl>
              {d.rejection_reason && <p className="mt-3 text-sm text-muted-foreground">{t("transfers.rejectionReason")}: {d.rejection_reason}</p>}
              <p className="mt-3 text-xs text-muted-foreground">
                <Link className="text-primary hover:underline" href={`/inventory/${d.batch_id}`}>{d.batch_code}</Link>
                {d.dispatched_at && ` · ${t("transfers.dispatchedAt")} ${formatDateTime(d.dispatched_at, locale)}`}
                {d.transporter_name && ` · ${d.transporter_name}`}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("transfers.outcomes")}</CardTitle>
              <CardDescription>{t("transfers.outcomesHint")}</CardDescription>
            </CardHeader>
            <CardContent>
              {d.outcomes.length === 0 ? <p className="text-sm text-muted-foreground">{t("transfers.noOutcomes")}</p> : (
                <ul className="grid gap-2 text-sm">
                  {d.outcomes.map((o) => (
                    <li key={o.id} className="rounded-lg border p-3">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-medium">{t(`transfers.outcomeTypes.${o.outcome_type}`)}</span>
                        <StatusBadge value={o.evidence_status === "none" ? "self_reported" : o.evidence_status} />
                      </div>
                      <p className="text-muted-foreground">
                        {formatKg(o.input_kg, locale)} → {formatKg(o.output_kg, locale)} · {formatDate(o.process_date, locale)} · {o.attested_by_name}
                      </p>
                      {o.evidence_url && <a className="text-primary underline" href={o.evidence_url} target="_blank" rel="noreferrer">{t("inventory.viewEvidence")}</a>}
                    </li>
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="grid min-w-0 content-start gap-4">
          {isOperator && d.status === "allocated" && (
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2 text-base"><Truck className="size-4" /> {t("transfers.dispatch")}</CardTitle>
                <CardDescription>{t("transfers.dispatchHint")}</CardDescription></CardHeader>
              <CardContent className="flex gap-2">
                <ConfirmDialog trigger={<Button><Send /> {t("transfers.dispatch")}</Button>} title={t("transfers.dispatch")} description={t("transfers.dispatchHint")}
                  onConfirm={() => act.mutateAsync({ path: `${id}/dispatch`, body: { version: d.version } })} />
                <ConfirmDialog destructive trigger={<Button variant="ghost">{t("common.cancel")}</Button>} title={t("transfers.cancel")}
                  onConfirm={() => act.mutateAsync({ path: `${id}/cancel`, body: { version: d.version } })} />
              </CardContent>
            </Card>
          )}
          {isPartner && d.status === "dispatched" && (
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2 text-base"><PackageCheck className="size-4" /> {t("transfers.receive")}</CardTitle></CardHeader>
              <CardContent className="grid gap-3">
                <Field label={t("transfers.w.received")} htmlFor="t-rec" required>
                  <Input id="t-rec" inputMode="decimal" value={receive.kg} onChange={(e) => setReceive({ ...receive, kg: e.target.value })} />
                </Field>
                <Field label={t("transfers.receiptRef")} htmlFor="t-ref">
                  <Input id="t-ref" value={receive.ref} onChange={(e) => setReceive({ ...receive, ref: e.target.value })} />
                </Field>
                <Button disabled={!(Number(receive.kg) >= 0) || !receive.kg || act.isPending}
                  onClick={() => act.mutate({ path: `${id}/receive`, body: { version: d.version, received_kg: receive.kg, receipt_reference: receive.ref || null } })}>
                  {t("transfers.confirmReceipt")}
                </Button>
              </CardContent>
            </Card>
          )}
          {isPartner && d.status === "received" && (
            <Card>
              <CardHeader><CardTitle className="text-base">{t("transfers.decide")}</CardTitle>
                <CardDescription>{t("transfers.decideHint", { kg: formatKg(d.received_kg, locale, true) })}</CardDescription></CardHeader>
              <CardContent className="grid gap-3">
                <div className="grid grid-cols-2 gap-3">
                  <Field label={t("transfers.w.accepted")} htmlFor="t-acc"><Input id="t-acc" inputMode="decimal" value={acceptedValue} onChange={(e) => setDecide({ ...decide, accepted: e.target.value })} /></Field>
                  <Field label={t("transfers.w.rejected")} htmlFor="t-rej"><Input id="t-rej" inputMode="decimal" value={decide.rejected} onChange={(e) => setDecide({ ...decide, rejected: e.target.value })} /></Field>
                </div>
                {Number(decide.rejected) > 0 && (
                  <>
                    <Field label={t("transfers.rejectionReason")} htmlFor="t-reason" required><Textarea id="t-reason" value={decide.reason} onChange={(e) => setDecide({ ...decide, reason: e.target.value })} /></Field>
                    <label className="flex items-center justify-between gap-2 text-sm">{t("transfers.returnRejected")}<Switch checked={decide.ret} onCheckedChange={(v) => setDecide({ ...decide, ret: v })} /></label>
                  </>
                )}
                <Button disabled={act.isPending || acceptedValue === ""}
                  onClick={() => act.mutate({ path: `${id}/decide`, body: { version: d.version, accepted_kg: acceptedValue, rejected_kg: decide.rejected || "0", rejection_reason: decide.reason || null, return_rejected: decide.ret } })}>
                  {t("common.submit")}
                </Button>
              </CardContent>
            </Card>
          )}
          {isPartner && ["accepted", "partially_accepted"].includes(d.status) && (
            <Card>
              <CardHeader><CardTitle className="text-base">{t("transfers.reportOutcome")}</CardTitle>
                <CardDescription>{t("transfers.remaining", { kg: formatKg((d.accepted_kg ?? 0) - reported, locale, true) })}</CardDescription></CardHeader>
              <CardContent className="grid gap-3">
                <Select aria-label={t("common.type")} value={outcome.type} onChange={(e) => setOutcome({ ...outcome, type: e.target.value })}>
                  {OUTCOMES.map((o) => <option key={o} value={o}>{t(`transfers.outcomeTypes.${o}`)}</option>)}
                </Select>
                <div className="grid grid-cols-2 gap-3">
                  <Field label={t("transfers.input")} htmlFor="o-in"><Input id="o-in" inputMode="decimal" value={outcome.input} onChange={(e) => setOutcome({ ...outcome, input: e.target.value })} /></Field>
                  <Field label={t("transfers.output")} htmlFor="o-out"><Input id="o-out" inputMode="decimal" value={outcome.output} onChange={(e) => setOutcome({ ...outcome, output: e.target.value })} /></Field>
                </div>
                <Field label={t("transfers.processDate")} htmlFor="o-date"><Input id="o-date" type="date" value={outcome.date} onChange={(e) => setOutcome({ ...outcome, date: e.target.value })} /></Field>
                <Field label={t("transfers.attestedBy")} htmlFor="o-att" required><Input id="o-att" value={outcome.attested} onChange={(e) => setOutcome({ ...outcome, attested: e.target.value })} /></Field>
                <Field label={t("transfers.processDesc")} htmlFor="o-desc"><Textarea id="o-desc" value={outcome.desc} onChange={(e) => setOutcome({ ...outcome, desc: e.target.value })} /></Field>
                <Field label={t("inventory.evidence")} htmlFor="o-file" required={needsEvidence} hint={needsEvidence ? t("transfers.evidenceNeeded") : t("transfers.selfReportedNote")}>
                  <Input id="o-file" type="file" accept="application/pdf,image/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
                </Field>
                <Button disabled={report.isPending || !outcome.input || !outcome.output || outcome.attested.trim().length < 3 || (needsEvidence && !file)} onClick={() => report.mutate()}>
                  {t("common.submit")}
                </Button>
              </CardContent>
            </Card>
          )}
          <Alert tone="info">{t("transfers.notRecycled")}</Alert>
        </div>
      </div>
    </>
  );
}
