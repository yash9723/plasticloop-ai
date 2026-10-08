"use client";

import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, Route as RouteIcon, Save, Siren, Sparkles } from "lucide-react";
import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/empty-state";
import { Field } from "@/components/common/field";
import { MetricCard } from "@/components/common/metric-card";
import { PageHeader } from "@/components/common/page-header";
import type { MapAnchor, MapLine, MapPoint } from "@/components/maps/route-map";
import { ROUTE_COLORS } from "@/components/maps/route-map";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { isReadOnly, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { Facility, PlanResult, RouteCandidate, Vehicle } from "@/lib/types";
import { cn, formatDuration, formatINR, formatKg, formatKm } from "@/lib/utils";

const RouteMap = dynamic(() => import("@/components/maps/route-map").then((m) => m.RouteMap), {
  ssr: false,
  loading: () => <Skeleton className="h-[460px]" />,
});

const tomorrow = () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return d.toISOString().slice(0, 10);
};

export default function PlannerPage() {
  const { t, locale } = useT();
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const readOnly = isReadOnly(user);
  const [date, setDate] = useState(tomorrow);
  const [shiftStart, setShiftStart] = useState("07:00");
  const [facilityId, setFacilityId] = useState<string | null>(null);
  const [vehicleOff, setVehicleOff] = useState<Set<string>>(new Set());
  const [excluded, setExcluded] = useState<Set<string>>(new Set());
  const [emergency, setEmergency] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<PlanResult | null>(null);

  const candidates = useApi<RouteCandidate[]>("/routes/candidates", { planned_date: date });
  const vehicles = useApi<Vehicle[]>("/vehicles", { active: true });
  const facilities = useApi<Facility[]>("/facilities");
  const facility = facilityId ?? facilities.data?.[0]?.id ?? "";
  const chosenVehicles = (vehicles.data ?? []).filter((v) => !vehicleOff.has(v.id));
  const chosenPoints = (candidates.data ?? []).filter((c) => !excluded.has(c.collection_point_id));
  const toggle = (set: Set<string>, id: string) => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  };

  const plan = useMutation({
    mutationFn: (save: boolean) =>
      api<PlanResult>("/routes/plan", {
        method: "POST",
        body: {
          vehicle_ids: chosenVehicles.map((v) => v.id),
          planned_date: date,
          point_ids: chosenPoints.map((c) => c.collection_point_id),
          emergency_point_ids: [...emergency].filter((id) => !excluded.has(id)),
          facility_id: facility || null,
          shift_start: shiftStart,
          time_limit_s: 3,
          save,
        },
      }),
    onSuccess: (r, save) => {
      setResult(r);
      if (save) {
        toast.success(t("planner.saved", { n: r.saved_route_ids.length }));
        router.push("/routes");
      }
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const colorOf = useMemo(() => {
    const m = new Map<string, string>();
    result?.routes.forEach((r, i) => m.set(r.vehicle_id, ROUTE_COLORS[i % ROUTE_COLORS.length]));
    return m;
  }, [result]);

  const mapPoints: MapPoint[] = useMemo(() => {
    if (result) {
      const planned = result.routes.flatMap((r) =>
        r.stops.map((s) => ({ id: s.collection_point_id, lat: s.lat, lng: s.lng, sequence: s.sequence, color: colorOf.get(r.vehicle_id),
          label: `${s.sequence}. ${s.code} · ${s.name} · ${t("planner.eta")} ${s.eta} · ${formatKg(s.expected_kg, locale)}` })),
      );
      const byId = new Map((candidates.data ?? []).map((c) => [c.collection_point_id, c]));
      const dropped = result.dropped.flatMap((d) => {
        const c = byId.get(d.collection_point_id);
        return c ? [{ id: d.collection_point_id, lat: c.lat, lng: c.lng, tone: "dropped" as const, label: `${d.code}: ${t(`planner.reasons.${d.reason}`)}` }] : [];
      });
      return [...planned, ...dropped];
    }
    return (candidates.data ?? []).map((c) => ({
      id: c.collection_point_id, lat: c.lat, lng: c.lng, label: `${c.code} · ${c.name} · ${formatKg(c.expected_kg, locale)}`,
      tone: excluded.has(c.collection_point_id) ? ("default" as const) : emergency.has(c.collection_point_id) ? ("emergency" as const) : ("selected" as const),
      onClick: () => setExcluded((s) => toggle(s, c.collection_point_id)),
    }));
  }, [result, candidates.data, excluded, emergency, colorOf, locale, t]);

  const lines: MapLine[] = result ? result.routes.filter((r) => r.stops.length).map((r) => ({ id: r.vehicle_id, color: colorOf.get(r.vehicle_id)!, positions: r.path })) : [];
  const facilityObj = facilities.data?.find((f) => f.id === facility);
  const anchors: MapAnchor[] = [
    ...chosenVehicles.map((v) => ({ id: `d-${v.id}`, lat: v.depot_lat, lng: v.depot_lng, kind: "depot" as const, label: `${t("vehicles.depot")}: ${v.depot_name ?? v.name}` })),
    ...(facilityObj?.lat != null && facilityObj.lng != null ? [{ id: "f", lat: facilityObj.lat, lng: facilityObj.lng, kind: "facility" as const, label: facilityObj.name }] : []),
  ];
  const resetResult = () => setResult(null);
  const totalExpected = chosenPoints.reduce((a, c) => a + c.expected_kg, 0);
  const totalCapacity = chosenVehicles.reduce((a, v) => a + v.capacity_kg, 0);

  return (
    <>
      <PageHeader title={t("nav.items.routePlanner")} description={t("planner.subtitle")} />
      <div className="grid gap-4 xl:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
        <div className="grid min-w-0 grid-cols-1 content-start gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("planner.setup")}</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-3">
              <div className="grid grid-cols-2 gap-3">
                <Field label={t("common.date")} htmlFor="pl-date">
                  <Input id="pl-date" type="date" value={date} onChange={(e) => { setDate(e.target.value); resetResult(); }} />
                </Field>
                <Field label={t("planner.shiftStart")} htmlFor="pl-shift">
                  <Input id="pl-shift" type="time" value={shiftStart} onChange={(e) => { setShiftStart(e.target.value); resetResult(); }} />
                </Field>
              </div>
              <Field label={t("planner.unloadAt")} htmlFor="pl-fac">
                <Select id="pl-fac" value={facility} onChange={(e) => { setFacilityId(e.target.value); resetResult(); }}>
                  <option value="">{t("planner.returnToDepot")}</option>
                  {facilities.data?.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <fieldset>
                <legend className="mb-2 text-sm font-medium">{t("planner.vehicles")}</legend>
                <div className="grid gap-1.5">
                  {vehicles.data?.length === 0 && <p className="text-sm text-muted-foreground">{t("vehicles.empty")}</p>}
                  {vehicles.data?.map((v) => (
                    <label key={v.id} className="flex cursor-pointer items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm">
                      <span className="flex items-center gap-2">
                        <input type="checkbox" checked={!vehicleOff.has(v.id)} onChange={() => { setVehicleOff((s) => toggle(s, v.id)); resetResult(); }} />
                        {v.name}
                      </span>
                      <span className="tabular text-xs text-muted-foreground">{formatKg(v.capacity_kg, locale)}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
              <p className={cn("text-xs", totalExpected > totalCapacity ? "text-amber-700 dark:text-amber-400" : "text-muted-foreground")}>
                {t("planner.capacityCheck", { expected: formatKg(totalExpected, locale), capacity: formatKg(totalCapacity, locale) })}
              </p>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("planner.stops", { n: chosenPoints.length })}</CardTitle>
              <CardDescription>{t("planner.stopsHint")}</CardDescription>
            </CardHeader>
            <CardContent>
              {candidates.isLoading ? (
                <Skeleton className="h-40" />
              ) : candidates.data?.length === 0 ? (
                <p className="text-sm text-muted-foreground">{t("planner.noCandidates")}</p>
              ) : (
                <ul className="grid max-h-80 gap-1 overflow-y-auto pr-1 text-sm">
                  {candidates.data?.map((c) => {
                    const on = !excluded.has(c.collection_point_id);
                    const urgent = emergency.has(c.collection_point_id);
                    return (
                      <li key={c.collection_point_id} className={cn("flex items-center gap-2 rounded-md px-2 py-1.5", on ? "bg-muted/50" : "opacity-60")}>
                        <input type="checkbox" aria-label={c.code} checked={on} onChange={() => { setExcluded((s) => toggle(s, c.collection_point_id)); resetResult(); }} />
                        <span className="min-w-0 flex-1">
                          <span className="font-medium">{c.code}</span> · {formatKg(c.expected_kg, locale)}
                          <span className="block truncate text-xs text-muted-foreground">
                            {c.reasons.map((r) => t(`planner.why.${r}`)).join(", ")} · {t(`planner.basis.${c.load_basis.split("+")[0]}`)}
                          </span>
                        </span>
                        <button type="button" aria-pressed={urgent} title={t("planner.emergency")} aria-label={`${t("planner.emergency")} ${c.code}`}
                          onClick={() => { setEmergency((s) => toggle(s, c.collection_point_id)); resetResult(); }}
                          className={cn("rounded p-1", urgent ? "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" : "text-muted-foreground hover:bg-muted")}>
                          <Siren className="size-4" />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </CardContent>
          </Card>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => plan.mutate(false)} disabled={plan.isPending || !chosenVehicles.length || !chosenPoints.length}>
              <Sparkles /> {t("planner.optimise")}
            </Button>
            {!readOnly && (
              <Button variant="outline" onClick={() => plan.mutate(true)} disabled={plan.isPending || !result || !result.totals.stops_planned}>
                <Save /> {t("planner.save")}
              </Button>
            )}
          </div>
        </div>

        <div className="grid min-w-0 grid-cols-1 content-start gap-4">
          <RouteMap points={mapPoints} lines={lines} anchors={anchors} height={460} ariaLabel={t("planner.mapAria")} />
          <p className="-mt-2 text-xs text-muted-foreground">{t("planner.mapNote")}</p>
          {!result ? (
            <EmptyState icon={RouteIcon} title={t("planner.emptyTitle")} description={t("planner.emptyHint")} />
          ) : (
            <>
              {result.distance_basis === "haversine_estimate" && <Alert tone="info">{t("planner.estimateNotice")}</Alert>}
              {result.warnings.map((w) => (
                <Alert key={w} tone="warning">{w}</Alert>
              ))}
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <MetricCard icon={RouteIcon} label={t("planner.totalDistance")} value={formatKm(result.totals.distance_m, locale)}
                  hint={result.distance_basis === "haversine_estimate" ? t("routes.estimate") : t("planner.roadDistance")} />
                <MetricCard icon={Sparkles} tone="teal" label={t("planner.vsBaseline")}
                  value={result.totals.savings_pct === null ? "—" : `${result.totals.savings_pct > 0 ? "−" : "+"}${Math.abs(result.totals.savings_pct)}%`}
                  hint={result.totals.baseline_distance_m === null ? t("planner.noBaseline") : t("planner.baselineKm", { km: formatKm(result.totals.baseline_distance_m, locale) })} />
                <MetricCard label={t("planner.stopsPlanned")} value={`${result.totals.stops_planned}/${result.totals.candidates}`}
                  tone={result.totals.stops_dropped ? "warning" : "primary"} hint={result.totals.stops_dropped ? t("planner.droppedN", { n: result.totals.stops_dropped }) : undefined} />
                <MetricCard label={t("planner.expectedLoad")} value={formatKg(result.totals.expected_load_kg, locale)} hint={t("planner.estimatedLoad")} />
              </div>
              <p className="text-xs text-muted-foreground">
                {t("planner.baselineExplain")} · {result.solver} · {t("planner.status")}: {result.solver_status}
              </p>
              {result.dropped.length > 0 && (
                <Alert tone="warning">
                  <span className="flex items-center gap-2 font-medium">
                    <AlertTriangle className="size-4" /> {t("planner.droppedTitle")}
                  </span>
                  <ul className="mt-1 list-disc pl-5 text-sm">
                    {result.dropped.map((d) => (
                      <li key={d.collection_point_id}>
                        {d.code} ({formatKg(d.expected_kg, locale)}): {t(`planner.reasons.${d.reason}`)}
                      </li>
                    ))}
                  </ul>
                </Alert>
              )}
              <div className="grid gap-4 lg:grid-cols-2">
                {result.routes.map((r) => (
                  <Card key={r.vehicle_id}>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2 text-base">
                        <span className="size-3 rounded-full" style={{ background: colorOf.get(r.vehicle_id) }} aria-hidden />
                        {r.vehicle_name}
                      </CardTitle>
                      <CardDescription>
                        {r.stops.length ? t("planner.routeSummary", { stops: r.stops.length, km: formatKm(r.distance_m, locale), time: formatDuration(r.duration_s) }) : t("planner.unused")}
                      </CardDescription>
                    </CardHeader>
                    {r.stops.length > 0 && (
                      <CardContent className="grid gap-3">
                        <div>
                          <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                            <span>{t("planner.load", { load: formatKg(r.load_kg, locale), cap: formatKg(r.capacity_kg, locale) })}</span>
                            <span>{r.utilization_pct}%</span>
                          </div>
                          <Progress value={Math.min(100, r.utilization_pct)} className="h-1.5" />
                        </div>
                        <ol className="grid gap-1 text-sm">
                          {r.stops.map((s) => (
                            <li key={s.collection_point_id} className="flex items-center justify-between gap-2 border-b pb-1 last:border-0">
                              <span className="min-w-0 truncate">
                                <span className="tabular mr-1 text-muted-foreground">{s.sequence}.</span>
                                {s.code}
                                {s.emergency && <Badge tone="danger" className="ml-1">{t("planner.emergency")}</Badge>}
                              </span>
                              <span className="tabular shrink-0 text-xs text-muted-foreground">{s.eta} · {formatKg(s.expected_kg, locale)}</span>
                            </li>
                          ))}
                        </ol>
                        <p className="text-xs text-muted-foreground">{t("planner.costEstimate", { cost: formatINR(r.cost_estimate_paise, locale) })}</p>
                      </CardContent>
                    )}
                  </Card>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}
