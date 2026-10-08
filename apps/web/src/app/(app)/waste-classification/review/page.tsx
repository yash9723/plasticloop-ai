"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FlaskConical } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/empty-state";
import { ErrorState } from "@/components/common/error-state";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { Candidates } from "@/components/vision/candidates";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi, usePagedList } from "@/lib/query";
import type { VisionPrediction } from "@/lib/types";
import { cn, formatDateTime } from "@/lib/utils";

const LABELS = ["rigid_plastic", "flexible_plastic", "suspected_multilayer_packaging", "paper_cardboard", "metal", "other_unknown"] as const;

interface Agreement {
  by_adapter: Record<string, { reviewed: number; agreed: number; no_suggestion: number }>;
  notice: string;
}

function ReviewCard({ p, canReview }: { p: VisionPrediction; canReview: boolean }) {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const [label, setLabel] = useState<string>(p.top_label ?? "");
  const [notes, setNotes] = useState("");
  const save = useMutation({
    mutationFn: () => api(`/vision/predictions/${p.id}/review`, { method: "POST", body: { final_label: label, notes: notes || null } }),
    onSuccess: () => {
      toast.success(t("vision.reviewSaved"));
      qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/vision") });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardContent className="grid gap-4 pt-5 sm:grid-cols-[160px_minmax(0,1fr)]">
        {p.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL
          <img src={p.image_url} alt={t("vision.sampleAlt")} className="aspect-square w-full rounded-lg border object-cover sm:w-40" />
        ) : (
          <div className="aspect-square rounded-lg bg-muted" />
        )}
        <div className="grid min-w-0 content-start gap-3">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">{formatDateTime(p.created_at, locale)}</span>
            <Badge tone={p.adapter === "trained" ? "info" : "warning"}>{t(`vision.kinds.${p.adapter}`)}</Badge>
            {p.low_confidence && <Badge tone="warning">{t("vision.lowConfidence")}</Badge>}
          </div>
          {p.candidates.length > 0 ? <Candidates prediction={p} limit={3} /> : <p className="text-sm text-muted-foreground">{t("vision.none")}</p>}
          {p.review ? (
            <Alert tone="success">
              <span className="flex items-center gap-2">
                <CheckCircle2 className="size-4" />
                {t("vision.finalLabel", { label: t(`vision.labels.${p.review.final_label}`), name: p.review.reviewer_name ?? "" })}
              </span>
            </Alert>
          ) : canReview ? (
            <div className="grid gap-2">
              <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={t("vision.finalLabelPrompt")}>
                {LABELS.map((l) => (
                  <button key={l} type="button" role="radio" aria-checked={label === l} onClick={() => setLabel(l)}
                    className={cn("rounded-lg border px-3 py-1.5 text-sm", label === l && "border-primary bg-secondary font-medium")}>
                    {t(`vision.labels.${l}`)}
                  </button>
                ))}
              </div>
              <Input placeholder={t("vision.notesPlaceholder")} aria-label={t("common.notes")} value={notes} onChange={(e) => setNotes(e.target.value)} />
              <Button className="justify-self-start" disabled={!label || save.isPending} onClick={() => save.mutate()}>
                {t("vision.confirmLabel")}
              </Button>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export default function ReviewPage() {
  const { t } = useT();
  const user = useAuth((s) => s.user);
  const canReview = hasRole(user, "mrf_operator", "gp_admin");
  const list = usePagedList<VisionPrediction>("/vision/predictions", { sort: "-created", pageSize: 10, filters: { reviewed: false } });
  const agreement = useApi<Agreement>("/vision/agreement");
  return (
    <>
      <PageHeader title={t("nav.items.classificationReview")} description={t("vision.reviewSubtitle")}
        actions={
          <Select aria-label={t("common.status")} value={String(list.filters.reviewed)} onChange={(e) => list.setFilter("reviewed", e.target.value === "" ? undefined : e.target.value === "true")} className="w-44">
            <option value="false">{t("vision.toReview")}</option>
            <option value="true">{t("vision.reviewed")}</option>
            <option value="">{t("common.all")}</option>
          </Select>
        } />
      {agreement.data && Object.keys(agreement.data.by_adapter).length > 0 && (
        <Alert tone="info" className="mb-4">
          {Object.entries(agreement.data.by_adapter).map(([k, v]) => (
            <span key={k} className="mr-4">{t(`vision.kinds.${k}`)}: {t("vision.agreement", { agreed: v.agreed, reviewed: v.reviewed })}</span>
          ))}
          <span className="block text-xs opacity-80">{t("vision.agreementNotice")}</span>
        </Alert>
      )}
      {list.error ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : !list.data ? (
        <Skeleton className="h-64" />
      ) : list.data.items.length === 0 ? (
        <EmptyState icon={FlaskConical} title={t("vision.queueEmpty")} />
      ) : (
        <div className="grid gap-3">
          {list.data.items.map((p) => <ReviewCard key={p.id} p={p} canReview={canReview} />)}
        </div>
      )}
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
    </>
  );
}
