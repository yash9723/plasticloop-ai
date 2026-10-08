"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, Flag, Play, SkipForward, XCircle } from "lucide-react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { ErrorState } from "@/components/common/error-state";
import { Field } from "@/components/common/field";
import { MetricCard } from "@/components/common/metric-card";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import type { MapAnchor, MapPoint } from "@/components/maps/route-map";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { RouteDetail, RouteStop } from "@/lib/types";
import { formatDate, formatDateTime, formatDuration, formatKg, formatKm } from "@/lib/utils";

const RouteMap = dynamic(() => import("@/components/maps/route-map").then((m) => m.RouteMap), {
  ssr: false,
  loading: () => <Skeleton className="h-[380px]" />,
});

const eta = (start: string, seconds: number) => {
  const [h, m] = start.split(":").map(Number);
  const total = h * 60 + m + Math.round(seconds / 60);
  return `${String(Math.floor(total / 60) % 24).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
};

export default function RouteDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useT();
  const qc = useQueryClient();
  const user = useAuth((s) => s.user);
  const route = useApi<RouteDetail>(`/routes/${id}`);
  const [skip, setSkip] = useState<RouteStop | null>(null);
  const [reason, setReason] = useState("");
  const [delay, setDelay] = useState({ open: false, minutes: "15", reason: "" });
  const [load, setLoad] = useState("");

  const refresh = (r: RouteDetail) => {
    qc.setQueryData([`/routes/${id}`, {}], r);
    qc.invalidateQueries({ queryKey: ["/routes"] });
  };
  const action = useMutation({
    mutationFn: ({ path, body }: { path: string; body?: unknown }) => api<RouteDetail>(`/routes/${id}${path}`, { method: "POST", body }),
    onSuccess: (r) => refresh(r),
    onError: (e) => toast.error(errorMessage(e)),
  });

  if (route.error) return <ErrorState error={route.error} onRetry={() => route.refetch()} />;
  const r = route.data;
  if (!r) return <Skeleton className="h-96" />;
  const canOperate = !!user && (hasRole(user, "gp_admin") || r.driver_id === user.id);
  const running = r.status === "in_progress";
  const shift = String(r.inputs.shift_start ?? "07:00").slice(0, 5);
  const nextStop = r.stops.find((s) => s.status === "pending");

  const points: MapPoint[] = r.stops.filter((s) => s.lat != null && s.lng != null).map((s) => ({
    id: s.id, lat: s.lat!, lng: s.lng!, sequence: s.sequence, label: `${s.sequence}. ${s.code} · ${s.name}`,
    color: s.status === "completed" ? "#15803d" : s.status === "skipped" ? "#b45309" : "#0072B2",
  }));
  const anchors: MapAnchor[] = [
    ...(r.depot ? [{ id: "depot", lat: r.depot[0], lng: r.depot[1], kind: "depot" as const, label: t("vehicles.depot") }] : []),
    ...(r.facility_location ? [{ id: "fac", lat: r.facility_location[0], lng: r.facility_location[1], kind: "facility" as const, label: r.facility_name ?? "" }] : []),
  ];
  const path: [number, number][] = [
    ...(r.depot ? [r.depot as [number, number]] : []),
    ...points.map((p) => [p.lat, p.lng] as [number, number]),
    ...(r.facility_location ? [r.facility_location as [number, number]] : r.depot ? [r.depot as [number, number]] : []),
  ];

  return (
    <>
      <PageHeader
        title={`${r.vehicle_name} · ${formatDate(r.planned_date, locale)}`}
        description={`${r.driver_name ?? t("common.unassigned")}${r.facility_name ? ` → ${r.facility_name}` : ""}`}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge value={r.status} />
            {canOperate && r.status === "planned" && (
              <Button onClick={() => action.mutate({ path: "/start" })} disabled={action.isPending}>
                <Play /> {t("routes.start")}
              </Button>
            )}
            {canOperate && (r.status === "planned" || running) && (
              <Button variant="outline" onClick={() => setDelay((d) => ({ ...d, open: true }))}>
                <Clock /> {t("routes.reportDelay")}
              </Button>
            )}
          </div>
        }
      />
      {r.distance_basis === "haversine_estimate" && <Alert tone="info" className="mb-4">{t("planner.estimateNotice")}</Alert>}
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard label={t("routes.stops")} value={`${r.stops_done}/${r.stops_total}`} />
        <MetricCard label={t("routes.distance")} value={formatKm(r.distance_m, locale)}
          hint={r.baseline_distance_m ? t("planner.baselineKm", { km: formatKm(r.baseline_distance_m, locale) }) : undefined} />
        <MetricCard label={t("routes.duration")} value={formatDuration(r.duration_s)} />
        <MetricCard label={t("routes.load")} value={formatKg(r.load_kg, locale)}
          hint={r.actual_load_kg != null ? t("routes.actualLoad", { kg: formatKg(r.actual_load_kg, locale) }) : t("planner.estimatedLoad")} />
      </div>
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,420px)]">
        <div className="grid min-w-0 grid-cols-1 content-start gap-3">
          <RouteMap points={points} anchors={anchors} lines={[{ id: "route", color: "#0072B2", positions: path }]} height={380} ariaLabel={t("routes.mapAria")} />
          <p className="text-xs text-muted-foreground">{t("planner.mapNote")}</p>
          {r.delay_reports.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{t("routes.delays")}</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="grid gap-1 text-sm">
                  {(r.delay_reports as { at: string; minutes: number; reason: string }[]).map((d) => (
                    <li key={d.at}>
                      {formatDateTime(d.at, locale)} · +{d.minutes} min · {d.reason}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle className="text-base">{t("routes.stopList")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="grid gap-2">
              {r.stops.map((s) => (
                <li key={s.id} className={`rounded-lg border p-3 ${s.id === nextStop?.id && running ? "border-primary ring-1 ring-primary" : ""}`}>
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-medium">
                        <span className="tabular mr-1 text-muted-foreground">{s.sequence}.</span>
                        <Link href={`/collection-points/${s.collection_point_id}`} className="hover:underline">
                          {s.code}
                        </Link>
                      </p>
                      <p className="truncate text-sm text-muted-foreground">{s.name}</p>
                      <p className="tabular text-xs text-muted-foreground">
                        {t("planner.eta")} {eta(shift, s.planned_arrival_s)} · {formatKg(s.expected_load_kg, locale)} {t("routes.expected")}
                      </p>
                      {s.skip_reason && <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">{s.skip_reason}</p>}
                    </div>
                    <StatusBadge value={s.status} />
                  </div>
                  {canOperate && running && s.status === "pending" && (
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button size="sm" onClick={() => action.mutate({ path: `/stops/${s.id}`, body: { action: "complete" } })} disabled={action.isPending}>
                        <CheckCircle2 /> {t("routes.collected")}
                      </Button>
                      <Button size="sm" variant="outline" asChild>
                        <Link href="/collector">{t("routes.recordWeight")}</Link>
                      </Button>
                      <Button size="sm" variant="ghost" onClick={() => { setSkip(s); setReason(""); }}>
                        <SkipForward /> {t("routes.skip")}
                      </Button>
                    </div>
                  )}
                </li>
              ))}
            </ol>
            {canOperate && running && (
              <div className="mt-4 grid gap-2 rounded-lg border p-3">
                <Field label={t("routes.actualLoadLabel")} htmlFor="rt-load" hint={t("routes.actualLoadHint")}>
                  <Input id="rt-load" inputMode="decimal" value={load} onChange={(e) => setLoad(e.target.value)} />
                </Field>
                <ConfirmDialog
                  trigger={<Button><Flag /> {t("routes.finish")}</Button>}
                  title={t("routes.finish")}
                  description={nextStop ? t("routes.finishPending") : undefined}
                  onConfirm={() => action.mutateAsync({ path: "/complete", body: { actual_load_kg: load || null } })}
                />
              </div>
            )}
            {canOperate && hasRole(user, "gp_admin") && r.status === "planned" && (
              <ConfirmDialog destructive
                trigger={<Button variant="ghost" className="mt-3 text-destructive"><XCircle /> {t("routes.cancel")}</Button>}
                title={t("routes.cancel")}
                onConfirm={() => action.mutateAsync({ path: "/cancel" })} />
            )}
          </CardContent>
        </Card>
      </div>

      <Dialog open={!!skip} onOpenChange={(o) => !o && setSkip(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("routes.skipTitle", { code: skip?.code ?? "" })}</DialogTitle>
          </DialogHeader>
          <Field label={t("routes.skipReason")} htmlFor="rt-skip" required>
            <Textarea id="rt-skip" value={reason} onChange={(e) => setReason(e.target.value)} />
          </Field>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSkip(null)}>{t("common.cancel")}</Button>
            <Button disabled={reason.trim().length < 3 || action.isPending}
              onClick={() => action.mutate({ path: `/stops/${skip!.id}`, body: { action: "skip", reason } }, { onSuccess: () => setSkip(null) })}>
              {t("routes.skip")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <Dialog open={delay.open} onOpenChange={(o) => setDelay((d) => ({ ...d, open: o }))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("routes.reportDelay")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3">
            <Field label={t("routes.delayMinutes")} htmlFor="rt-dmin">
              <Input id="rt-dmin" inputMode="numeric" value={delay.minutes} onChange={(e) => setDelay((d) => ({ ...d, minutes: e.target.value }))} />
            </Field>
            <Field label={t("routes.delayReason")} htmlFor="rt-dreason" required>
              <Textarea id="rt-dreason" value={delay.reason} onChange={(e) => setDelay((d) => ({ ...d, reason: e.target.value }))} />
            </Field>
          </div>
          <DialogFooter>
            <Button disabled={delay.reason.trim().length < 3 || !(Number(delay.minutes) > 0) || action.isPending}
              onClick={() => action.mutate({ path: "/delay", body: { minutes: Number(delay.minutes), reason: delay.reason } },
                { onSuccess: () => { setDelay({ open: false, minutes: "15", reason: "" }); toast.success(t("routes.delayReported")); } })}>
              {t("common.submit")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
