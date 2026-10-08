"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Recycle } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/empty-state";
import { MetricCard } from "@/components/common/metric-card";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi, usePagedList } from "@/lib/query";
import type { Outcome } from "@/lib/types";
import { formatDate, formatKg } from "@/lib/utils";

interface Recovered { recovered_kg: { evidence_reviewed: number; evidence_submitted: number; self_reported: number } }

export default function RecoveryPage() {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const canReview = hasRole(user, "mrf_operator");
  const list = usePagedList<Outcome>("/processing-transfers/outcomes/all", { sort: "-created" });
  const ov = useApi<Recovered>("/analytics/overview", { date_from: "2000-01-01T00:00:00Z" });
  const review = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "accept" | "reject" }) =>
      api(`/processing-transfers/outcomes/${id}/review`, { method: "POST", body: { decision, notes: decision === "reject" ? t("recovery.rejectNote") : null } }),
    onSuccess: () => {
      toast.success(t("common.saved"));
      qc.invalidateQueries({ predicate: (q) => ["/processing-transfers", "/analytics"].some((p) => String(q.queryKey[0]).startsWith(p)) });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const r = ov.data?.recovered_kg;
  return (
    <>
      <PageHeader title={t("nav.items.recovery")} description={t("recovery.subtitle")} />
      <div className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <MetricCard icon={Recycle} label={t("recovery.reviewed")} value={formatKg(r?.evidence_reviewed ?? null, locale)} hint={t("recovery.reviewedHint")} loading={!r} />
        <MetricCard tone="warning" label={t("recovery.submitted")} value={formatKg(r?.evidence_submitted ?? null, locale)} hint={t("recovery.submittedHint")} loading={!r} />
        <MetricCard tone="neutral" label={t("recovery.selfReported")} value={formatKg(r?.self_reported ?? null, locale)} hint={t("recovery.selfReportedHint")} loading={!r} />
      </div>
      <Alert tone="info" className="mb-4">{t("recovery.rule")}</Alert>
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        <Select aria-label={t("recovery.evidence")} onChange={(e) => list.setFilter("evidence_status", e.target.value || undefined)}>
          <option value="">{t("common.all")}</option>
          {["submitted", "reviewed_accepted", "reviewed_rejected", "none"].map((s) => <option key={s} value={s}>{t(`status.${s === "none" ? "self_reported" : s}`)}</option>)}
        </Select>
      </div>
      {!list.data ? <Skeleton className="h-48" /> : list.data.items.length === 0 ? <EmptyState icon={Recycle} title={t("recovery.empty")} /> : (
        <div className="grid gap-3">
          {list.data.items.map((o) => (
            <Card key={o.id}>
              <CardContent className="flex flex-wrap items-center justify-between gap-3 pt-5">
                <div className="min-w-0">
                  <p className="font-medium">{t(`transfers.outcomeTypes.${o.outcome_type}`)} · {o.category_label}</p>
                  <p className="text-sm text-muted-foreground">
                    <Link className="text-primary hover:underline" href={`/processing-transfers/${o.transfer_id}`}>{o.transfer_code}</Link> · {o.partner_name} ·{" "}
                    {formatKg(o.input_kg, locale)} → {formatKg(o.output_kg, locale)} · {formatDate(o.process_date, locale)}
                  </p>
                  {o.evidence_url && <a className="text-sm text-primary underline" href={o.evidence_url} target="_blank" rel="noreferrer">{t("inventory.viewEvidence")}</a>}
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge value={o.evidence_status === "none" ? "self_reported" : o.evidence_status} />
                  <OriginBadge origin={o.data_origin} />
                  {canReview && o.evidence_status === "submitted" && (
                    <>
                      <Button size="sm" onClick={() => review.mutate({ id: o.id, decision: "accept" })} disabled={review.isPending}>{t("recovery.accept")}</Button>
                      <Button size="sm" variant="outline" onClick={() => review.mutate({ id: o.id, decision: "reject" })} disabled={review.isPending}>{t("recovery.reject")}</Button>
                    </>
                  )}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
    </>
  );
}
