"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Printer, RotateCcw, Siren } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { ErrorState } from "@/components/common/error-state";
import { MeasurementBadge, OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useLabels } from "@/lib/lookups";
import { useApi } from "@/lib/query";
import type { CollectionEvent, CollectionPoint, PickupRequest } from "@/lib/types";
import { formatDateTime, formatKg, relativeTime } from "@/lib/utils";

interface PointDetail {
  point: CollectionPoint;
  qr_payload: string;
  recent_collections: CollectionEvent[];
  open_requests: PickupRequest[];
}

function QrLabel({ payload, code, name }: { payload: string; code: string; name: string }) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    QRCode.toString(payload, { type: "svg", margin: 1, errorCorrectionLevel: "M", color: { dark: "#0f172a", light: "#ffffff" } }).then((svg) =>
      setSrc(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`),
    );
  }, [payload]);
  return (
    <div className="mx-auto w-56 rounded-xl border-2 border-dashed p-4 text-center print:border-solid">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {src && <img src={src} alt={`QR ${payload}`} className="mx-auto aspect-square w-44" />}
      <p className="mt-2 font-mono text-sm font-semibold tracking-wider">{payload.replace("plasticloop:cp:", "")}</p>
      <p className="text-xs text-muted-foreground">
        {code} · {name}
      </p>
    </div>
  );
}

export default function PointDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useT();
  const user = useAuth((s) => s.user);
  const labels = useLabels();
  const qc = useQueryClient();
  const detail = useApi<PointDetail>(`/collection-points/${id}`);
  const refresh = () => qc.invalidateQueries({ queryKey: [`/collection-points/${id}`] });
  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => api(`/collection-points/${id}`, { method: "PATCH", body: { ...body, version: detail.data?.point.version } }),
    onSuccess: () => {
      toast.success(t("common.saved"));
      refresh();
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const admin = hasRole(user, "gp_admin");

  if (detail.error) return <ErrorState error={detail.error} onRetry={() => detail.refetch()} />;
  if (!detail.data) return <Skeleton className="h-96 w-full" />;
  const { point: p, qr_payload, recent_collections, open_requests } = detail.data;

  return (
    <>
      <PageHeader
        title={p.name}
        description={`${p.code} · ${p.village_name ?? ""} · ${t(`points.types.${p.point_type}`)}`}
        eyebrow={
          <>
            <StatusBadge value={p.status} />
            {p.emergency_flag && <StatusBadge value="flagged" />}
            {p.is_sample && <OriginBadge origin="demo_seed" />}
          </>
        }
        actions={
          <Button variant="outline" onClick={() => window.print()}>
            <Printer /> {t("points.printLabel")}
          </Button>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.6fr]">
        <div className="grid content-start gap-6">
          <Card>
            <CardHeader>
              <div>
                <CardTitle>{t("points.qrLabel")}</CardTitle>
                <CardDescription>{t("points.qrHint")}</CardDescription>
              </div>
            </CardHeader>
            <CardContent>
              <QrLabel payload={qr_payload} code={p.code} name={p.name} />
              {admin && (
                <div className="mt-4 text-center print:hidden">
                  <ConfirmDialog
                    trigger={
                      <Button variant="ghost" size="sm">
                        <RotateCcw /> {t("points.rotateQr")}
                      </Button>
                    }
                    title={t("points.rotateQr")}
                    description={t("points.rotateHint")}
                    onConfirm={async () => {
                      await api(`/collection-points/${id}/regenerate-qr`, { method: "POST" });
                      refresh();
                    }}
                  />
                </div>
              )}
            </CardContent>
          </Card>
          <Card className="print:hidden">
            <CardHeader>
              <CardTitle>{t("common.details")}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3 text-sm">
              <div>
                <p className="text-muted-foreground">{t("points.fill")}</p>
                {p.fill_percent === null ? (
                  "—"
                ) : (
                  <div className="mt-1 flex items-center gap-3">
                    <Progress value={p.fill_percent} indicatorClassName={p.fill_percent >= 80 ? "bg-amber-500" : "bg-emerald-500"} />
                    <span className="tabular">{Math.round(p.fill_percent)}%</span>
                  </div>
                )}
                <p className="mt-1 text-xs text-muted-foreground">
                  {t("points.fillSource", { source: p.fill_source ?? "—", time: relativeTime(p.fill_updated_at, locale) })}
                </p>
              </div>
              <p>
                <span className="text-muted-foreground">{t("points.schedule")}:</span>{" "}
                {p.pickup_days.map((d) => t(`points.days.${d}`)).join(", ") || "—"} · {p.pickup_window ?? ""}
              </p>
              <p>
                <span className="text-muted-foreground">{t("points.streams")}:</span> {p.stream_ids.map((s) => labels.stream(s)).join(", ")}
              </p>
              <p>
                <span className="text-muted-foreground">{t("common.collector")}:</span> {p.assigned_collector_name ?? t("common.unassigned")}
              </p>
              <p>
                <span className="text-muted-foreground">{t("points.device")}:</span>{" "}
                {p.device ? (
                  <Link className="text-primary hover:underline" href={`/devices/${p.device.id}`}>
                    {p.device.device_id}
                  </Link>
                ) : (
                  t("points.noDevice")
                )}{" "}
                {p.device && <StatusBadge value={p.device.connection_status} />}
              </p>
              <p>
                <span className="text-muted-foreground">{t("common.location")}:</span>{" "}
                {p.lat !== null ? `${p.lat.toFixed(5)}, ${p.lng?.toFixed(5)}` : "—"}
                {p.location_precision === "approximate" && ` (${t("points.approximate")})`}
              </p>
              {admin && (
                <div className="mt-2 grid gap-3 border-t pt-3">
                  <label className="flex items-center justify-between gap-3">
                    <span className="flex items-center gap-2">
                      <Siren className="size-4 text-danger-foreground" /> {t("points.emergency")}
                    </span>
                    <Switch checked={p.emergency_flag} onCheckedChange={(v) => patch.mutate({ emergency_flag: v })} />
                  </label>
                  <label className="flex items-center justify-between gap-3">
                    <span>{t("status.active")}</span>
                    <Switch checked={p.status === "active"} onCheckedChange={(v) => patch.mutate({ status: v ? "active" : "inactive" })} />
                  </label>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
        <div className="grid content-start gap-6 print:hidden">
          <Card>
            <CardHeader>
              <CardTitle>{t("points.recent")}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2">
              {recent_collections.length === 0 && <p className="text-sm text-muted-foreground">{t("common.noData")}</p>}
              {recent_collections.map((c) => (
                <Link key={c.id} href={`/collections/${c.id}`} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border px-3 py-2 text-sm hover:bg-muted/50">
                  <span>{formatDateTime(c.collected_at, locale)}</span>
                  <span className="text-muted-foreground">{labels.stream(c.waste_stream_id)}</span>
                  <MeasurementBadge source={c.measurement_source} />
                  <span className="tabular font-medium">{formatKg(c.weight_kg, locale)}</span>
                </Link>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t("points.openRequests")}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-2">
              {open_requests.length === 0 && <p className="text-sm text-muted-foreground">{t("common.noData")}</p>}
              {open_requests.map((r) => (
                <div key={r.id} className="flex items-center justify-between rounded-lg border px-3 py-2 text-sm">
                  <span>{r.preferred_date ?? "—"}</span>
                  <StatusBadge value={r.status} />
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </>
  );
}
