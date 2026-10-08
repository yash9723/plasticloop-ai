"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Activity, Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { type Column, DataTable } from "@/components/common/data-table";
import { KeyReveal } from "@/components/devices/key-reveal";
import { Field } from "@/components/common/field";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/i18n/i18n";
import { api, errorMessage, type Page } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useApi, usePagedList } from "@/lib/query";
import type { CollectionPoint, Device, DeviceCreated } from "@/lib/types";
import { formatKg, relativeTime } from "@/lib/utils";

const TYPES = ["combo_node", "weighing_scale", "fill_sensor", "camera"] as const;

function RegisterDialog({ onCreated }: { onCreated: (d: DeviceCreated) => void }) {
  const { t } = useT();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ device_id: "", device_type: "combo_node", collection_point_id: "", weight_max_kg: "150", telemetry_interval_s: "300", is_simulated: false });
  const points = useApi<Page<CollectionPoint>>(open ? "/collection-points" : null, { page_size: 200, sort: "code" });
  const create = useMutation({
    mutationFn: () =>
      api<DeviceCreated>("/devices", {
        method: "POST",
        body: {
          device_id: form.device_id.trim().toUpperCase(),
          device_type: form.device_type,
          collection_point_id: form.collection_point_id || null,
          weight_max_kg: form.weight_max_kg,
          telemetry_interval_s: Number(form.telemetry_interval_s),
          is_simulated: form.is_simulated,
        },
      }),
    onSuccess: (d) => {
      qc.invalidateQueries({ queryKey: ["/devices"] });
      setOpen(false);
      onCreated(d);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const valid = /^[A-Z0-9][A-Z0-9-]{2,39}$/.test(form.device_id.trim().toUpperCase()) && form.collection_point_id;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus /> {t("devices.register")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t("devices.register")}</DialogTitle>
          <DialogDescription>{t("devices.registerHint")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("devices.deviceId")} htmlFor="d-id" required hint="DEV-ESP32-010">
              <Input id="d-id" value={form.device_id} autoCapitalize="characters" onChange={(e) => setForm({ ...form, device_id: e.target.value })} />
            </Field>
            <Field label={t("common.type")} htmlFor="d-type">
              <Select id="d-type" value={form.device_type} onChange={(e) => setForm({ ...form, device_type: e.target.value })}>
                {TYPES.map((ty) => (
                  <option key={ty} value={ty}>
                    {t(`devices.types.${ty}`)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label={t("devices.point")} htmlFor="d-point" required>
            <Select id="d-point" value={form.collection_point_id} onChange={(e) => setForm({ ...form, collection_point_id: e.target.value })}>
              <option value="">—</option>
              {points.data?.items
                .filter((p) => !p.device)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.code} · {p.name}
                  </option>
                ))}
            </Select>
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("devices.maxWeight")} htmlFor="d-max">
              <Input id="d-max" inputMode="decimal" value={form.weight_max_kg} onChange={(e) => setForm({ ...form, weight_max_kg: e.target.value })} />
            </Field>
            <Field label={t("devices.interval")} htmlFor="d-int">
              <Input id="d-int" inputMode="numeric" value={form.telemetry_interval_s} onChange={(e) => setForm({ ...form, telemetry_interval_s: e.target.value })} />
            </Field>
          </div>
          <label className="flex items-center justify-between gap-3 rounded-lg border p-3 text-sm">
            <span>
              <span className="font-medium">{t("devices.simulatedToggle")}</span>
              <span className="block text-xs text-muted-foreground">{t("devices.simulatedHint")}</span>
            </span>
            <Switch checked={form.is_simulated} onCheckedChange={(v) => setForm({ ...form, is_simulated: v })} />
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => create.mutate()} disabled={!valid || create.isPending}>
            {t("devices.register")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function DevicesPage() {
  const { t, locale } = useT();
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const [created, setCreated] = useState<DeviceCreated | null>(null);
  const list = usePagedList<Device>("/devices", { sort: "device_id" });
  const columns: Column<Device>[] = [
    { key: "id", header: t("devices.deviceId"), sortKey: "device_id", cell: (r) => <span className="font-mono text-sm font-medium">{r.device_id}</span> },
    { key: "type", header: t("common.type"), cell: (r) => t(`devices.types.${r.device_type}`) },
    {
      key: "point",
      header: t("devices.point"),
      cell: (r) => (r.collection_point_code ? <span className="block min-w-40">{r.collection_point_code} · {r.village_name}</span> : "—"),
    },
    { key: "fill", header: t("devices.fill"), cell: (r) => (r.last_fill_percent === null ? "—" : `${Math.round(r.last_fill_percent)}%`) },
    { key: "weight", header: t("devices.weight"), cell: (r) => <span className="whitespace-nowrap">{formatKg(r.last_weight_kg, locale)}</span> },
    { key: "battery", header: t("devices.battery"), sortKey: "battery", cell: (r) => (r.battery_percent === null ? "—" : `${r.battery_percent}%`) },
    { key: "seen", header: t("devices.lastSeen"), sortKey: "last_seen", cell: (r) => <span className="whitespace-nowrap">{relativeTime(r.last_seen_at, locale)}</span> },
    {
      key: "status",
      header: t("common.status"),
      sortKey: "status",
      cell: (r) => (
        <span className="flex flex-wrap gap-1">
          <StatusBadge value={r.connection_status} />
          <StatusBadge value={r.calibration_status} />
          {r.is_simulated && <OriginBadge origin="simulated" />}
        </span>
      ),
    },
  ];
  return (
    <>
      <PageHeader
        title={t("nav.items.devices")}
        description={t("devices.subtitle")}
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" asChild>
              <Link href="/devices/simulator">
                <Activity /> {t("nav.items.simulator")}
              </Link>
            </Button>
            {hasRole(user, "gp_admin") && <RegisterDialog onCreated={setCreated} />}
          </div>
        }
      />
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        <Input placeholder={t("devices.search")} aria-label={t("common.search")} onChange={(e) => list.setFilter("q", e.target.value || undefined)} />
        <Select aria-label={t("common.status")} onChange={(e) => list.setFilter("status", e.target.value || undefined)}>
          <option value="">{t("common.all")}</option>
          {["online", "stale", "offline", "never_seen"].map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </Select>
        <Select aria-label={t("devices.kind")} onChange={(e) => list.setFilter("simulated", e.target.value || undefined)}>
          <option value="">{t("devices.allKinds")}</option>
          <option value="false">{t("devices.physical")}</option>
          <option value="true">{t("devices.simulated")}</option>
        </Select>
      </div>
      <DataTable columns={columns} rows={list.data?.items} rowKey={(r) => r.id} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={list.sort} onSortChange={list.setSort} onRowClick={(r) => router.push(`/devices/${r.id}`)} emptyTitle={t("devices.empty")} />
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
      <KeyReveal created={created} onClose={() => setCreated(null)} />
    </>
  );
}
