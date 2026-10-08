"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, Send, Terminal, WifiOff } from "lucide-react";
import Link from "next/link";
import { useEffect, useEffectEvent, useState } from "react";
import { toast } from "sonner";
import { EmptyState } from "@/components/common/empty-state";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/i18n/i18n";
import { api, errorMessage, type Page } from "@/lib/api";
import { useApi } from "@/lib/query";
import type { Device, DeviceReading } from "@/lib/types";
import { formatDateTime, formatKg, relativeTime } from "@/lib/utils";

function Slider({ id, label, value, min, max, step, unit, onChange }: {
  id: string; label: string; value: number; min: number; max: number; step: number; unit: string; onChange: (v: number) => void;
}) {
  return (
    <div className="grid gap-1.5">
      <label htmlFor={id} className="flex justify-between text-sm font-medium">
        {label}
        <span className="tabular text-muted-foreground">
          {value}
          {unit}
        </span>
      </label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="h-2 w-full cursor-pointer accent-[var(--primary)]" />
    </div>
  );
}

export default function SimulatorPage() {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const devices = useApi<Page<Device>>("/devices", { simulated: true, page_size: 100, sort: "device_id" });
  const [selected, setSelected] = useState("");
  const deviceId = selected || devices.data?.items[0]?.id || "";
  const device = devices.data?.items.find((d) => d.id === deviceId);
  const [state, setState] = useState({ weight: 20, fill: 50, battery: 80, sensorError: false });
  const [auto, setAuto] = useState(false);
  const readings = useApi<Page<DeviceReading>>(deviceId ? `/devices/${deviceId}/readings` : null, { page_size: 8 }, { refetchInterval: 10_000 });

  const simulate = useMutation({
    mutationFn: (body: Record<string, unknown>) => api(`/demo/devices/${deviceId}/simulate`, { method: "POST", body }),
    onSuccess: () => qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith("/devices") }),
    onError: (e) => {
      setAuto(false);
      toast.error(errorMessage(e));
    },
  });
  type SimState = typeof state;
  const payload = (st: SimState) => ({
    weight_kg: st.weight,
    fill_percent: st.fill,
    battery_percent: st.battery,
    sensor_status: st.sensorError ? "load_cell_error" : "ok",
  });
  const sendReading = () => simulate.mutate(payload(state));
  const onTick = useEffectEvent(() => {
    // A real bin keeps filling: nudge the values each tick so dashboards visibly move.
    const next = { ...state, weight: Math.min(150, +(state.weight + 0.8).toFixed(1)), fill: Math.min(100, state.fill + 2) };
    setState(next);
    simulate.mutate(payload(next));
  });
  useEffect(() => {
    if (!auto || !deviceId) return;
    const timer = setInterval(() => onTick(), 5000);
    return () => clearInterval(timer);
  }, [auto, deviceId]);

  return (
    <>
      <PageHeader title={t("nav.items.simulator")} description={t("devices.simSubtitle")} />
      <Alert tone="warning" className="mb-4">{t("devices.simNotice")}</Alert>
      {devices.data && devices.data.items.length === 0 ? (
        <EmptyState title={t("devices.simEmpty")} description={t("devices.simEmptyHint")} />
      ) : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("devices.simControls")}</CardTitle>
              <CardDescription>{t("devices.simControlsHint")}</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-5">
              <Select aria-label={t("devices.deviceId")} value={deviceId} onChange={(e) => setSelected(e.target.value)}>
                {devices.data?.items.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.device_id} · {d.collection_point_code ?? t("devices.unattached")}
                  </option>
                ))}
              </Select>
              <Slider id="s-weight" label={t("devices.weight")} unit=" kg" min={0} max={Number(device?.weight_max_kg ?? 150) + 20} step={0.1}
                value={state.weight} onChange={(v) => setState({ ...state, weight: v })} />
              <Slider id="s-fill" label={t("devices.fill")} unit="%" min={0} max={100} step={1} value={state.fill} onChange={(v) => setState({ ...state, fill: v })} />
              <Slider id="s-battery" label={t("devices.battery")} unit="%" min={0} max={100} step={1} value={state.battery}
                onChange={(v) => setState({ ...state, battery: v })} />
              <label className="flex items-center justify-between gap-3 text-sm">
                <span>
                  <span className="font-medium">{t("devices.sensorFault")}</span>
                  <span className="block text-xs text-muted-foreground">{t("devices.sensorFaultHint")}</span>
                </span>
                <Switch checked={state.sensorError} onCheckedChange={(v) => setState({ ...state, sensorError: v })} />
              </label>
              <div className="flex flex-wrap gap-2">
                <Button onClick={sendReading} disabled={!deviceId || simulate.isPending}>
                  <Send /> {t("devices.sendReading")}
                </Button>
                <Button variant="outline" onClick={() => setAuto((a) => !a)} disabled={!deviceId} aria-pressed={auto}>
                  {auto ? <Pause /> : <Play />} {auto ? t("devices.stopAuto") : t("devices.startAuto")}
                </Button>
                <Button variant="outline" onClick={() => simulate.mutate({ go_offline: true })} disabled={!deviceId || simulate.isPending}>
                  <WifiOff /> {t("devices.goOffline")}
                </Button>
              </div>
            </CardContent>
          </Card>
          <div className="grid min-w-0 grid-cols-1 content-start gap-4">
            {device && (
              <Card>
                <CardHeader>
                  <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                    <Link href={`/devices/${device.id}`} className="font-mono hover:underline">
                      {device.device_id}
                    </Link>
                    <StatusBadge value={device.connection_status} />
                    <OriginBadge origin="simulated" />
                  </CardTitle>
                  <CardDescription>
                    {t("devices.lastSeen")}: {relativeTime(device.last_seen_at, locale)}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <ul className="grid gap-2 text-sm">
                    {readings.data?.items.map((r) => (
                      <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 border-b pb-2 last:border-0">
                        <span className="tabular">
                          {formatDateTime(r.device_timestamp, locale)}
                          <span className="block text-xs text-muted-foreground">
                            {formatKg(r.weight_kg, locale)} · {r.fill_percent ?? "—"}% · {r.battery_percent ?? "—"}% · {r.transport.toUpperCase()}
                          </span>
                        </span>
                        <StatusBadge value={r.quality} />
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Terminal className="size-4" /> {t("devices.cliTitle")}
                </CardTitle>
                <CardDescription>{t("devices.cliHint")}</CardDescription>
              </CardHeader>
              <CardContent>
                <pre className="overflow-x-auto rounded-md bg-muted p-3 font-mono text-xs">
                  {`pnpm simulator --device-id ${device?.device_id ?? "DEV-ESP32-001"} --demo-key`}
                </pre>
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
