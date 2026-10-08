"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Battery, Clock, Gauge, KeyRound, Radio, Scale, ShieldOff, Wrench } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { DeviceReadingsChart } from "@/components/charts/device-readings";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { type Column, DataTable } from "@/components/common/data-table";
import { ErrorState } from "@/components/common/error-state";
import { Field } from "@/components/common/field";
import { MetricCard } from "@/components/common/metric-card";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { KeyReveal } from "@/components/devices/key-reveal";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { api, errorMessage, type Page } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi } from "@/lib/query";
import type { Calibration, Device, DeviceCreated, DeviceReading } from "@/lib/types";
import { formatDateTime, formatKg, relativeTime } from "@/lib/utils";

function CommandsCard({ device }: { device: Device }) {
  const { t } = useT();
  const [mass, setMass] = useState("5");
  const [interval, setIntervalS] = useState(String(device.telemetry_interval_s));
  const send = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<{ command_id: string }>(`/devices/${device.id}/commands`, { method: "POST", body }),
    onSuccess: () => toast.success(t("devices.commandSent")),
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Radio className="size-4" /> {t("devices.commands")}
        </CardTitle>
        <CardDescription>{t("devices.commandsHint")}</CardDescription>
      </CardHeader>
      <CardContent className="grid gap-3">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" disabled={send.isPending} onClick={() => send.mutate({ command: "ping" })}>
            {t("devices.cmd.ping")}
          </Button>
          <Button variant="outline" size="sm" disabled={send.isPending} onClick={() => send.mutate({ command: "tare" })}>
            {t("devices.cmd.tare")}
          </Button>
        </div>
        <div className="flex items-end gap-2">
          <Field label={t("devices.knownMass")} htmlFor="c-mass" className="flex-1">
            <Input id="c-mass" inputMode="decimal" value={mass} onChange={(e) => setMass(e.target.value)} />
          </Field>
          <Button variant="outline" disabled={send.isPending || !(Number(mass) > 0)} onClick={() => send.mutate({ command: "calibrate", known_mass_kg: Number(mass) })}>
            {t("devices.cmd.calibrate")}
          </Button>
        </div>
        <div className="flex items-end gap-2">
          <Field label={t("devices.interval")} htmlFor="c-int" className="flex-1">
            <Input id="c-int" inputMode="numeric" value={interval} onChange={(e) => setIntervalS(e.target.value)} />
          </Field>
          <Button variant="outline" disabled={send.isPending || !(Number(interval) >= 10)} onClick={() => send.mutate({ command: "set_interval", interval_s: Number(interval) })}>
            {t("devices.cmd.setInterval")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CalibrationCard({ device, canEdit }: { device: Device; canEdit: boolean }) {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const cals = useApi<Calibration[]>(`/devices/${device.id}/calibrations`);
  const [form, setForm] = useState({ method: "known_mass", result: "pass", reference_mass_kg: "10", notes: "" });
  const record = useMutation({
    mutationFn: () =>
      api(`/devices/${device.id}/calibrations`, {
        method: "POST",
        body: { ...form, reference_mass_kg: form.method === "tare" ? null : Number(form.reference_mass_kg), notes: form.notes || null },
      }),
    onSuccess: () => {
      toast.success(t("common.saved"));
      qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith(`/devices/${device.id}`) });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Wrench className="size-4" /> {t("devices.calibration")}
        </CardTitle>
        <CardDescription>
          <StatusBadge value={device.calibration_status} />{" "}
          {device.last_calibration_at && t("devices.lastCalibrated", { when: relativeTime(device.last_calibration_at, locale) })}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4">
        {canEdit && (
          <div className="grid gap-2 rounded-lg border p-3">
            <div className="grid grid-cols-2 gap-2">
              <Select aria-label={t("devices.method")} value={form.method} onChange={(e) => setForm({ ...form, method: e.target.value })}>
                {["known_mass", "tare", "two_point", "factory"].map((m) => (
                  <option key={m} value={m}>
                    {t(`devices.methods.${m}`)}
                  </option>
                ))}
              </Select>
              <Select aria-label={t("devices.result")} value={form.result} onChange={(e) => setForm({ ...form, result: e.target.value })}>
                <option value="pass">{t("status.pass")}</option>
                <option value="fail">{t("status.fail")}</option>
              </Select>
            </div>
            {form.method !== "tare" && (
              <Input aria-label={t("devices.knownMass")} inputMode="decimal" value={form.reference_mass_kg} onChange={(e) => setForm({ ...form, reference_mass_kg: e.target.value })} />
            )}
            <Button size="sm" onClick={() => record.mutate()} disabled={record.isPending}>
              {t("devices.recordCalibration")}
            </Button>
          </div>
        )}
        <ul className="grid gap-2 text-sm">
          {cals.data?.length === 0 && <li className="text-muted-foreground">{t("devices.noCalibrations")}</li>}
          {cals.data?.map((c) => (
            <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 border-b pb-2 last:border-0">
              <span>
                {t(`devices.methods.${c.method}`)}
                {c.reference_mass_kg !== null && ` · ${formatKg(c.reference_mass_kg, locale)}`}
                <span className="block text-xs text-muted-foreground">
                  {formatDateTime(c.performed_at, locale)} · {t(`devices.sources.${c.source}`)}
                </span>
              </span>
              <StatusBadge value={c.result} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}

export default function DeviceDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { t, locale } = useT();
  const user = useAuth((s) => s.user);
  const qc = useQueryClient();
  const isAdmin = hasRole(user, "gp_admin");
  const [created, setCreated] = useState<DeviceCreated | null>(null);
  const device = useApi<Device>(`/devices/${id}`);
  const [since] = useState(() => new Date(Date.now() - 24 * 3600_000).toISOString());
  const chart = useApi<Page<DeviceReading>>(`/devices/${id}/readings`, { since, page_size: 200 });
  const recent = useApi<Page<DeviceReading>>(`/devices/${id}/readings`, { page_size: 15 });
  const refresh = () => qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith(`/devices`) });

  if (device.error) return <ErrorState error={device.error} onRetry={() => device.refetch()} />;
  const d = device.data;
  if (!d) return <Skeleton className="h-96" />;

  const columns: Column<DeviceReading>[] = [
    { key: "time", header: t("common.date"), cell: (r) => <span className="whitespace-nowrap">{formatDateTime(r.device_timestamp, locale)}</span> },
    { key: "weight", header: t("devices.weight"), cell: (r) => formatKg(r.weight_kg, locale) },
    { key: "fill", header: t("devices.fill"), cell: (r) => (r.fill_percent === null ? "—" : `${r.fill_percent}%`) },
    { key: "battery", header: t("devices.battery"), cell: (r) => (r.battery_percent === null ? "—" : `${r.battery_percent}%`) },
    { key: "via", header: t("devices.transport"), cell: (r) => r.transport.toUpperCase() },
    {
      key: "quality",
      header: t("devices.quality"),
      cell: (r) => (
        <span className="flex flex-wrap items-center gap-1" title={r.quality_notes ?? undefined}>
          <StatusBadge value={r.quality} />
          {r.is_synthetic && <OriginBadge origin="simulated" />}
        </span>
      ),
    },
  ];

  return (
    <>
      <PageHeader
        title={d.device_id}
        description={
          d.collection_point_id ? (
            <Link className="text-primary hover:underline" href={`/collection-points/${d.collection_point_id}`}>
              {d.collection_point_code} · {d.collection_point_name} · {d.village_name}
            </Link>
          ) : (
            t("devices.unattached")
          )
        }
        actions={
          <div className="flex flex-wrap gap-1.5">
            <StatusBadge value={d.connection_status} />
            {d.is_simulated && <OriginBadge origin="simulated" />}
            {!d.active && <StatusBadge value="inactive" />}
          </div>
        }
      />
      {d.is_simulated && <Alert tone="warning" className="mb-4">{t("devices.simulatedNotice")}</Alert>}
      <div className="mb-6 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <MetricCard icon={Gauge} tone="teal" label={t("devices.fill")} value={d.last_fill_percent === null ? "—" : `${Math.round(d.last_fill_percent)}%`} />
        <MetricCard icon={Scale} tone="primary" label={t("devices.weight")} value={formatKg(d.last_weight_kg, locale)} hint={t("devices.maxHint", { kg: d.weight_max_kg })} />
        <MetricCard icon={Battery} tone={d.battery_percent !== null && d.battery_percent <= 20 ? "warning" : "neutral"} label={t("devices.battery")}
          value={d.battery_percent === null ? "—" : `${d.battery_percent}%`} />
        <MetricCard icon={Clock} tone="neutral" label={t("devices.lastSeen")} value={relativeTime(d.last_seen_at, locale)}
          hint={t("devices.everySeconds", { s: d.telemetry_interval_s })} />
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="grid min-w-0 grid-cols-1 gap-4 xl:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("devices.last24h")}</CardTitle>
              <CardDescription>{t("devices.chartHint")}</CardDescription>
            </CardHeader>
            <CardContent>{chart.isLoading ? <Skeleton className="h-60" /> : <DeviceReadingsChart readings={chart.data?.items ?? []} />}</CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("devices.recentReadings")}</CardTitle>
            </CardHeader>
            <CardContent>
              <DataTable columns={columns} rows={recent.data?.items} rowKey={(r) => r.id} loading={recent.isLoading} error={recent.error}
                onRetry={() => recent.refetch()} emptyTitle={t("devices.noReadings")} />
            </CardContent>
          </Card>
        </div>
        <div className="grid min-w-0 grid-cols-1 content-start gap-4">
          {isAdmin && d.active && <CommandsCard device={d} />}
          <CalibrationCard device={d} canEdit={isAdmin} />
          {isAdmin && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <KeyRound className="size-4" /> {t("devices.credentials")}
                </CardTitle>
                <CardDescription>{t("devices.credentialsHint")}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                <ConfirmDialog
                  trigger={<Button variant="outline" size="sm"><KeyRound /> {t("devices.rotateKey")}</Button>}
                  title={t("devices.rotateKey")}
                  description={t("devices.rotateConfirm")}
                  onConfirm={async () => {
                    setCreated(await api<DeviceCreated>(`/devices/${d.id}/rotate-key`, { method: "POST" }));
                    refresh();
                  }}
                />
                <ConfirmDialog
                  destructive
                  trigger={<Button variant="outline" size="sm"><ShieldOff /> {t("devices.revoke")}</Button>}
                  title={t("devices.revoke")}
                  description={t("devices.revokeConfirm")}
                  onConfirm={async () => {
                    await api(`/devices/${d.id}/revoke`, { method: "POST" });
                    toast.success(t("devices.revoked"));
                    refresh();
                  }}
                />
              </CardContent>
            </Card>
          )}
        </div>
      </div>
      <KeyReveal created={created} onClose={() => setCreated(null)} />
    </>
  );
}
