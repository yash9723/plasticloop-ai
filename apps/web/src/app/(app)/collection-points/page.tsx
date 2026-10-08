"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { LocateFixed, Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";
import { type Column, DataTable } from "@/components/common/data-table";
import { Field } from "@/components/common/field";
import { OriginBadge } from "@/components/common/origin-badge";
import { PageHeader } from "@/components/common/page-header";
import { Pagination } from "@/components/common/pagination";
import { StatusBadge } from "@/components/common/status-badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Select } from "@/components/ui/select";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { useAssignable, useLabels } from "@/lib/lookups";
import { usePagedList } from "@/lib/query";
import type { CollectionPoint } from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";

const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"] as const;
const TYPES = ["community_bin", "household", "institution", "market", "other"] as const;

function NewPointDialog() {
  const { t } = useT();
  const qc = useQueryClient();
  const labels = useLabels();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ village_id: "", name: "", point_type: "community_bin", lat: "", lng: "", assigned_collector_id: "", pickup_window: "07:00-11:00", priority: "3" });
  const [streams, setStreams] = useState<string[]>([]);
  const [days, setDays] = useState<string[]>(["mon", "thu"]);
  const collectors = useAssignable(form.village_id);
  const set = (k: keyof typeof form, v: string) => setForm((f) => ({ ...f, [k]: v }));
  const create = useMutation({
    mutationFn: () =>
      api<CollectionPoint>("/collection-points", {
        method: "POST",
        body: {
          village_id: form.village_id,
          name: form.name,
          point_type: form.point_type,
          lat: form.lat ? Number(form.lat) : null,
          lng: form.lng ? Number(form.lng) : null,
          stream_ids: streams,
          assigned_collector_id: form.assigned_collector_id || null,
          pickup_days: days,
          pickup_window: form.pickup_window || null,
          priority: Number(form.priority),
        },
      }),
    onSuccess: (cp) => {
      toast.success(t("points.created", { code: cp.code }));
      qc.invalidateQueries({ queryKey: ["/collection-points"] });
      setOpen(false);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const locate = () =>
    navigator.geolocation?.getCurrentPosition((p) => setForm((f) => ({ ...f, lat: p.coords.latitude.toFixed(6), lng: p.coords.longitude.toFixed(6) })));
  const valid = form.village_id && form.name.trim().length >= 2 && streams.length > 0;

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus /> {t("points.add")}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{t("points.add")}</DialogTitle>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("common.village")} htmlFor="p-village" required>
              <Select id="p-village" value={form.village_id} onChange={(e) => set("village_id", e.target.value)}>
                <option value="">{t("auth.selectVillage")}</option>
                {labels.villages.map((v) => (
                  <option key={v.id} value={v.id}>
                    {v.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("common.type")} htmlFor="p-type">
              <Select id="p-type" value={form.point_type} onChange={(e) => set("point_type", e.target.value)}>
                {TYPES.map((ty) => (
                  <option key={ty} value={ty}>
                    {t(`points.types.${ty}`)}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
          <Field label={t("common.name")} htmlFor="p-name" required>
            <Input id="p-name" value={form.name} onChange={(e) => set("name", e.target.value)} />
          </Field>
          <div className="grid gap-2 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <Field label={t("points.lat")} htmlFor="p-lat">
              <Input id="p-lat" inputMode="decimal" value={form.lat} onChange={(e) => set("lat", e.target.value)} />
            </Field>
            <Field label={t("points.lng")} htmlFor="p-lng">
              <Input id="p-lng" inputMode="decimal" value={form.lng} onChange={(e) => set("lng", e.target.value)} />
            </Field>
            <Button type="button" variant="outline" onClick={locate}>
              <LocateFixed /> {t("points.useLocation")}
            </Button>
          </div>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">{t("points.streams")}</legend>
            <div className="flex flex-wrap gap-2">
              {labels.streams.map((s) => (
                <label key={s.id} className={cn("flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-sm", streams.includes(s.id) && "border-primary bg-secondary")}>
                  <input type="checkbox" className="sr-only" checked={streams.includes(s.id)}
                    onChange={() => setStreams((xs) => (xs.includes(s.id) ? xs.filter((x) => x !== s.id) : [...xs, s.id]))} />
                  <span className="size-2.5 rounded-full" style={{ background: s.color }} aria-hidden />
                  {labels.stream(s.id)}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">{t("points.pickupDays")}</legend>
            <div className="flex flex-wrap gap-1.5">
              {DAYS.map((d) => (
                <button key={d} type="button" aria-pressed={days.includes(d)}
                  onClick={() => setDays((xs) => (xs.includes(d) ? xs.filter((x) => x !== d) : [...xs, d]))}
                  className={cn("rounded-lg border px-3 py-1.5 text-sm", days.includes(d) && "border-primary bg-secondary font-medium")}>
                  {t(`points.days.${d}`)}
                </button>
              ))}
            </div>
          </fieldset>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label={t("common.collector")} htmlFor="p-collector">
              <Select id="p-collector" value={form.assigned_collector_id} onChange={(e) => set("assigned_collector_id", e.target.value)} disabled={!form.village_id}>
                <option value="">{t("common.unassigned")}</option>
                {collectors.data?.map((u) => (
                  <option key={u.id} value={u.id}>
                    {u.full_name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label={t("points.window")} htmlFor="p-window">
              <Input id="p-window" value={form.pickup_window} onChange={(e) => set("pickup_window", e.target.value)} placeholder="07:00-11:00" />
            </Field>
            <Field label={t("common.priority")} htmlFor="p-priority">
              <Select id="p-priority" value={form.priority} onChange={(e) => set("priority", e.target.value)}>
                {[1, 2, 3, 4, 5].map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </Select>
            </Field>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            {t("common.cancel")}
          </Button>
          <Button onClick={() => create.mutate()} disabled={!valid || create.isPending}>
            {t("common.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function CollectionPointsPage() {
  const { t, locale } = useT();
  const router = useRouter();
  const user = useAuth((s) => s.user);
  const labels = useLabels();
  const list = usePagedList<CollectionPoint>("/collection-points", { sort: "code" });
  const columns: Column<CollectionPoint>[] = [
    { key: "code", header: t("common.code"), sortKey: "code", cell: (r) => <span className="font-medium">{r.code}</span> },
    { key: "name", header: t("common.name"), sortKey: "name", cell: (r) => <span className="block min-w-44">{r.name}</span> },
    { key: "type", header: t("common.type"), cell: (r) => t(`points.types.${r.point_type}`) },
    { key: "village", header: t("common.village"), cell: (r) => <span className="whitespace-nowrap">{r.village_name}</span> },
    {
      key: "fill",
      header: t("points.fill"),
      sortKey: "fill",
      cell: (r) =>
        r.fill_percent === null ? (
          "—"
        ) : (
          <span className="flex min-w-28 items-center gap-2">
            <Progress value={r.fill_percent} className="h-1.5 w-16" indicatorClassName={r.fill_percent >= 80 ? "bg-amber-500" : "bg-emerald-500"} />
            <span className="tabular text-xs">{Math.round(r.fill_percent)}%</span>
          </span>
        ),
    },
    { key: "last", header: t("points.lastCollected"), sortKey: "last_collected", cell: (r) => <span className="whitespace-nowrap">{relativeTime(r.last_collected_at, locale)}</span> },
    { key: "collector", header: t("common.collector"), cell: (r) => r.assigned_collector_name ?? t("common.unassigned") },
    {
      key: "status",
      header: t("common.status"),
      cell: (r) => (
        <span className="flex flex-wrap gap-1">
          <StatusBadge value={r.status} />
          {r.device && <StatusBadge value={r.device.connection_status} />}
          {r.is_sample && <OriginBadge origin="demo_seed" />}
        </span>
      ),
    },
  ];
  return (
    <>
      <PageHeader title={t("nav.items.collectionPoints")} description={t("points.subtitle")} actions={hasRole(user, "gp_admin") && <NewPointDialog />} />
      <div className="mb-4 grid gap-2 sm:grid-cols-3">
        <Input placeholder={t("points.search")} aria-label={t("common.search")} onChange={(e) => list.setFilter("q", e.target.value || undefined)} />
        <Select aria-label={t("common.village")} onChange={(e) => list.setFilter("village_id", e.target.value || undefined)}>
          <option value="">{t("collections.allVillages")}</option>
          {labels.villages.map((v) => (
            <option key={v.id} value={v.id}>
              {v.name}
            </option>
          ))}
        </Select>
        <Select aria-label={t("common.status")} onChange={(e) => list.setFilter("status", e.target.value || undefined)}>
          <option value="">{t("common.all")}</option>
          <option value="active">{t("status.active")}</option>
          <option value="inactive">{t("status.inactive")}</option>
        </Select>
      </div>
      <DataTable columns={columns} rows={list.data?.items} rowKey={(r) => r.id} loading={list.isLoading} error={list.error} onRetry={() => list.refetch()}
        sort={list.sort} onSortChange={list.setSort} onRowClick={(r) => router.push(`/collection-points/${r.id}`)} />
      <Pagination page={list.page} pageSize={list.pageSize} total={list.data?.total ?? 0} onPageChange={list.setPage} />
    </>
  );
}
