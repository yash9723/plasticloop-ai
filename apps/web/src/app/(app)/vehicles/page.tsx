"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LocateFixed, Pencil, Plus } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { type Column, DataTable } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useAssignable, useVillages } from "@/lib/lookups";
import { useApi } from "@/lib/query";
import type { Vehicle } from "@/lib/types";
import { formatINR, formatKg } from "@/lib/utils";

const TYPES = ["e_cart", "auto_rickshaw", "tractor_trolley", "mini_truck", "other"] as const;
type Form = { registration_no: string; name: string; vehicle_type: string; capacity_kg: string; depot_name: string; depot_lat: string;
  depot_lng: string; cost_per_km: string; driver_id: string; active: boolean };
const EMPTY: Form = { registration_no: "", name: "", vehicle_type: "e_cart", capacity_kg: "350", depot_name: "", depot_lat: "", depot_lng: "",
  cost_per_km: "12", driver_id: "", active: true };

function VehicleDialog({ editing, open, onOpenChange }: { editing: Vehicle | null; open: boolean; onOpenChange: (o: boolean) => void }) {
  const { t } = useT();
  const qc = useQueryClient();
  const villages = useVillages();
  const drivers = useAssignable(villages.data?.items[0]?.id, "driver");
  const [form, setForm] = useState<Form>(() =>
    editing
      ? { registration_no: editing.registration_no, name: editing.name, vehicle_type: editing.vehicle_type, capacity_kg: String(editing.capacity_kg),
          depot_name: editing.depot_name ?? "", depot_lat: String(editing.depot_lat), depot_lng: String(editing.depot_lng),
          cost_per_km: String(editing.cost_per_km_paise / 100), driver_id: editing.driver_id ?? "", active: editing.active }
      : EMPTY,
  );
  const set = (k: keyof Form, v: string | boolean) => setForm((f) => ({ ...f, [k]: v }));
  const save = useMutation({
    mutationFn: () => {
      const common = { name: form.name, capacity_kg: form.capacity_kg, depot_name: form.depot_name || null, depot_lat: Number(form.depot_lat),
        depot_lng: Number(form.depot_lng), cost_per_km_paise: Math.round(Number(form.cost_per_km) * 100) };
      return editing
        ? api(`/vehicles/${editing.id}`, { method: "PATCH", body: { ...common, active: form.active, driver_id: form.driver_id || null, clear_driver: !form.driver_id } })
        : api("/vehicles", { method: "POST", body: { ...common, registration_no: form.registration_no, vehicle_type: form.vehicle_type, driver_id: form.driver_id || null } });
    },
    onSuccess: () => {
      toast.success(t("common.saved"));
      qc.invalidateQueries({ queryKey: ["/vehicles"] });
      onOpenChange(false);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const locate = () => navigator.geolocation?.getCurrentPosition((p) => setForm((f) => ({ ...f, depot_lat: p.coords.latitude.toFixed(6), depot_lng: p.coords.longitude.toFixed(6) })));
  const valid = form.name.trim().length >= 2 && Number(form.capacity_kg) > 0 && form.depot_lat !== "" && form.depot_lng !== "" && (editing || form.registration_no.trim().length >= 4);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{editing ? t("vehicles.edit") : t("vehicles.add")}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("vehicles.registration")} htmlFor="v-reg" required>
              <Input id="v-reg" value={form.registration_no} disabled={!!editing} onChange={(e) => set("registration_no", e.target.value.toUpperCase())} />
            </Field>
            <Field label={t("common.name")} htmlFor="v-name" required>
              <Input id="v-name" value={form.name} onChange={(e) => set("name", e.target.value)} />
            </Field>
            <Field label={t("common.type")} htmlFor="v-type">
              <Select id="v-type" value={form.vehicle_type} disabled={!!editing} onChange={(e) => set("vehicle_type", e.target.value)}>
                {TYPES.map((ty) => (
                  <option key={ty} value={ty}>
                    {t(`vehicles.types.${ty}`)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("vehicles.capacity")} htmlFor="v-cap" required>
              <Input id="v-cap" inputMode="decimal" value={form.capacity_kg} onChange={(e) => set("capacity_kg", e.target.value)} />
            </Field>
          </div>
          <Field label={t("vehicles.depot")} htmlFor="v-depot">
            <Input id="v-depot" value={form.depot_name} onChange={(e) => set("depot_name", e.target.value)} />
          </Field>
          <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <Field label={t("points.lat")} htmlFor="v-lat" required>
              <Input id="v-lat" inputMode="decimal" value={form.depot_lat} onChange={(e) => set("depot_lat", e.target.value)} />
            </Field>
            <Field label={t("points.lng")} htmlFor="v-lng" required>
              <Input id="v-lng" inputMode="decimal" value={form.depot_lng} onChange={(e) => set("depot_lng", e.target.value)} />
            </Field>
            <Button type="button" variant="outline" onClick={locate}>
              <LocateFixed /> {t("points.useLocation")}
            </Button>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("vehicles.driver")} htmlFor="v-driver">
              <Select id="v-driver" value={form.driver_id} onChange={(e) => set("driver_id", e.target.value)}>
                <option value="">{t("common.unassigned")}</option>
                {drivers.data?.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("vehicles.costPerKm")} htmlFor="v-cost" hint={t("vehicles.costHint")}>
              <Input id="v-cost" inputMode="decimal" value={form.cost_per_km} onChange={(e) => set("cost_per_km", e.target.value)} />
            </Field>
          </div>
          {editing && (
            <label className="flex items-center justify-between rounded-lg border p-3 text-sm font-medium">
              {t("status.active")}
              <Switch checked={form.active} onCheckedChange={(v) => set("active", v)} />
            </label>
          )}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => save.mutate()} disabled={!valid || save.isPending}>
            {t("common.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function VehiclesPage() {
  const { t, locale } = useT();
  const user = useAuth((s) => s.user);
  const isAdmin = hasRole(user, "gp_admin");
  const list = useApi<Vehicle[]>("/vehicles");
  const [dialog, setDialog] = useState<{ open: boolean; editing: Vehicle | null; key: number }>({ open: false, editing: null, key: 0 });
  const openDialog = (editing: Vehicle | null) => setDialog((d) => ({ open: true, editing, key: d.key + 1 }));
  const columns: Column<Vehicle>[] = [
    { key: "name", header: t("common.name"), cell: (r) => <span className="font-medium">{r.name}</span> },
    { key: "reg", header: t("vehicles.registration"), cell: (r) => <span className="font-mono text-sm">{r.registration_no}</span> },
    { key: "type", header: t("common.type"), cell: (r) => t(`vehicles.types.${r.vehicle_type}`) },
    { key: "cap", header: t("vehicles.capacity"), cell: (r) => <span className="whitespace-nowrap">{formatKg(r.capacity_kg, locale)}</span> },
    { key: "driver", header: t("vehicles.driver"), cell: (r) => r.driver_name ?? t("common.unassigned") },
    { key: "cost", header: t("vehicles.costPerKm"), cell: (r) => (r.cost_per_km_paise ? formatINR(r.cost_per_km_paise, locale) : "—") },
    {
      key: "status",
      header: t("common.status"),
      cell: (r) => (
        <span className="flex flex-wrap gap-1">
          <StatusBadge value={r.active ? "active" : "inactive"} />
          {r.is_sample && <OriginBadge origin="demo_seed" />}
        </span>
      ),
    },
    ...(isAdmin
      ? [{ key: "edit", header: "", cell: (r: Vehicle) => (
          <Button size="icon" variant="ghost" aria-label={`${t("common.edit")} ${r.name}`} onClick={() => openDialog(r)}>
            <Pencil />
          </Button>
        ) }]
      : []),
  ];
  return (
    <>
      <PageHeader title={t("nav.items.vehicles")} description={t("vehicles.subtitle")}
        actions={isAdmin && (
          <Button onClick={() => openDialog(null)}>
            <Plus /> {t("vehicles.add")}
          </Button>
        )} />
      <DataTable columns={columns} rows={list.data} rowKey={(r) => r.id} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        emptyTitle={t("vehicles.empty")} />
      {dialog.open && <VehicleDialog key={dialog.key} editing={dialog.editing} open={dialog.open} onOpenChange={(o) => setDialog((d) => ({ ...d, open: o }))} />}
    </>
  );
}
