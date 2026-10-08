"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Printer } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { ErrorState } from "@/components/common/error-state";
import { MeasurementBadge, OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { CollectionEvent, Receipt } from "@/lib/types";
import { formatDateTime, formatKg } from "@/lib/utils";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-4 border-b py-2.5 text-sm last:border-0">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{children}</dd>
    </div>
  );
}

export default function CollectionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useT();
  const user = useAuth((s) => s.user);
  const qc = useQueryClient();
  const event = useApi<CollectionEvent>(`/collections/${id}`);
  const receipt = useApi<Receipt>(`/collections/${id}/receipt`);
  const [note, setNote] = useState("");
  const review = useMutation({
    mutationFn: () => api(`/collections/${id}/review`, { method: "PATCH", body: { review_status: "resolved", note } }),
    onSuccess: () => {
      toast.success(t("common.saved"));
      qc.invalidateQueries({ queryKey: [`/collections/${id}`] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (event.error) return <ErrorState error={event.error} onRetry={() => event.refetch()} />;
  const e = event.data;
  const r = receipt.data;
  return (
    <>
      <PageHeader
        title={r ? `${t("collector.receiptNo")} ${r.receipt_no}` : t("collections.detail")}
        eyebrow={e && (<><StatusBadge value={e.review_status} /><OriginBadge origin={e.data_origin} /></>)}
        actions={
          <Button variant="outline" onClick={() => window.print()}>
            <Printer /> {t("common.print")}
          </Button>
        }
      />
      {e?.review_status === "flagged" && (
        <Alert tone="warning" className="mb-5">
          <AlertDescription>{e.review_reason}</AlertDescription>
        </Alert>
      )}
      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>{t("collections.receipt")}</CardTitle>
          </CardHeader>
          <CardContent>
            {!e || !r ? (
              <Skeleton className="h-64 w-full" />
            ) : (
              <dl>
                <Row label={t("collections.point")}>
                  <Link className="text-primary hover:underline" href={`/collection-points/${e.collection_point_id}`}>
                    {r.collection_point_code}
                  </Link>{" "}
                  · {r.collection_point_name}
                </Row>
                <Row label={t("common.village")}>{r.village_name}</Row>
                <Row label={t("common.stream")}>{r.stream_label}</Row>
                <Row label={t("common.weight")}>
                  <span className="tabular text-lg">{formatKg(r.weight_kg, locale)}</span>
                </Row>
                <Row label={t("collections.source")}>
                  <MeasurementBadge source={e.measurement_source} />
                </Row>
                {e.calibration_meta && (
                  <Row label={t("collections.calibration")}>
                    {String(e.calibration_meta.device_id)} · {t(`status.${String(e.calibration_meta.calibration_status)}`)}
                  </Row>
                )}
                <Row label={t("collections.collectedAt")}>{formatDateTime(r.collected_at, locale)}</Row>
                <Row label={t("collections.acknowledgedAt")}>{formatDateTime(r.acknowledged_at, locale)}</Row>
                <Row label={t("common.collector")}>{r.collector_name}</Row>
                <Row label={t("collections.capturedOffline")}>{e.offline_captured ? t("common.yes") : t("common.no")}</Row>
                {e.gps_lat !== null && (
                  <Row label={t("common.location")}>
                    {e.gps_lat?.toFixed(5)}, {e.gps_lng?.toFixed(5)} (±{e.gps_accuracy_m ?? "?"} m)
                  </Row>
                )}
                {e.notes && <Row label={t("common.notes")}>{e.notes}</Row>}
              </dl>
            )}
          </CardContent>
        </Card>
        <div className="grid content-start gap-6">
          {e?.photo_url && (
            <Card>
              <CardHeader>
                <CardTitle>{t("collections.photo")}</CardTitle>
              </CardHeader>
              <CardContent>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={e.photo_url} alt={t("collections.photo")} className="w-full rounded-lg object-cover" />
              </CardContent>
            </Card>
          )}
          {e?.review_status === "flagged" && hasRole(user, "gp_admin") && (
            <Card>
              <CardHeader>
                <CardTitle>{t("collections.resolveTitle")}</CardTitle>
              </CardHeader>
              <CardContent className="grid gap-3">
                <Textarea value={note} onChange={(ev) => setNote(ev.target.value)} placeholder={t("collections.resolveHint")} />
                <Button onClick={() => review.mutate()} disabled={note.trim().length < 3 || review.isPending}>
                  {t("collections.markResolved")}
                </Button>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
