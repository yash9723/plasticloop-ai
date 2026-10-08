"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, ChevronRight, CloudOff, History, Keyboard, QrCode, RefreshCw, Siren } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useState } from "react";
import { toast } from "sonner";
import { CollectionForm, type FormPoint } from "@/components/collector/collection-form";
import { QrScannerModal } from "@/components/collector/qr-scanner-modal";
import { EmptyState } from "@/components/common/empty-state";
import { useOnline } from "@/components/common/offline-indicator";
import { StatusBadge } from "@/components/common/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { useT } from "@/i18n/i18n";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import { type QueuedEvent, cacheTasks, findPointByQr, getCachedTasks, getDb } from "@/lib/offline/db";
import { useLiveQuery, usePendingCount } from "@/lib/offline/hooks";
import { syncNow } from "@/lib/offline/sync";
import type { CollectionPointBrief, MyTasks, TaskStop } from "@/lib/types";
import { cn, formatDate, formatDateTime, formatKg, relativeTime } from "@/lib/utils";

interface Selected {
  point: FormPoint;
  stop?: TaskStop;
}

const toFormPoint = (p: CollectionPointBrief): FormPoint => ({ id: p.id, code: p.code, name: p.name, stream_ids: p.stream_ids, device_id: p.device_id });

function CollectorInner() {
  const { t, locale } = useT();
  const user = useAuth((s) => s.user);
  const status = useAuth((s) => s.status);
  const online = useOnline();
  const params = useSearchParams();
  const pending = usePendingCount();
  const [scanOpen, setScanOpen] = useState(params.get("scan") === "1");
  const [selected, setSelected] = useState<Selected | null>(null);
  const [lastSavedId, setLastSavedId] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const lastSaved = useLiveQuery<QueuedEvent | undefined>(
    () => (lastSavedId ? getDb().events.get(lastSavedId) : Promise.resolve(undefined)),
    [lastSavedId],
    undefined,
  );

  // Offline-first: render the copy saved in IndexedDB; a successful online fetch refreshes that copy.
  const cached = useLiveQuery(() => (user ? getCachedTasks(user.id) : Promise.resolve(undefined)), [user?.id], undefined);
  const remote = useQuery({
    queryKey: ["my-tasks"],
    queryFn: async () => {
      const data = await api<MyTasks>("/collections/my-tasks");
      if (user) await cacheTasks(user.id, data);
      return data;
    },
    enabled: status === "authenticated",
    refetchInterval: 5 * 60_000,
  });
  const tasks: MyTasks | null = remote.data ?? cached?.data ?? null;
  const cachedAt = remote.data ? remote.dataUpdatedAt : (cached?.cached_at ?? null);

  const openPoint = useCallback(
    async (raw: string) => {
      if (!user) return;
      const p = await findPointByQr(user.id, raw);
      if (!p) {
        toast.error(t("collector.pointNotFound"));
        return;
      }
      setSelected({ point: toFormPoint(p), stop: tasks?.stops.find((s) => s.point.id === p.id) });
    },
    [user, tasks, t],
  );

  const runSync = async () => {
    if (!user) return;
    setSyncing(true);
    try {
      const s = await syncNow(user.id, { force: true });
      if (s.offline) toast.warning(t("collector.syncOffline"));
      else if (s.authRequired) toast.warning(t("collector.syncAuth"));
      else toast.success(t("collector.syncDone", { synced: s.synced, failed: s.failed + s.conflicts }));
    } finally {
      setSyncing(false);
    }
  };

  const today = tasks ? formatDate(tasks.date, locale) : formatDate(new Date(), locale);
  const reasonTone = (r: string): "danger" | "warning" | "info" | "primary" =>
    r === "emergency" ? "danger" : r === "bin_full" ? "warning" : r === "pickup_request" ? "info" : "primary";

  return (
    <div className="mx-auto grid max-w-2xl gap-5">
      <Card className="gap-3 py-4">
        <CardContent className="flex flex-wrap items-center gap-3">
          <div className="min-w-0 flex-1">
            <p className="text-xs text-muted-foreground">{today}</p>
            <h1 className="text-xl font-semibold">{t("collector.title")}</h1>
          </div>
          <div className="flex items-center gap-2">
            <Badge tone={online ? "success" : "warning"}>
              {online ? null : <CloudOff aria-hidden />}
              {online ? t("status.online") : t("status.offline")}
            </Badge>
            <Button variant="outline" onClick={runSync} disabled={syncing || !online || status !== "authenticated"}>
              <RefreshCw className={cn(syncing && "animate-spin")} /> {t("collector.syncNow")}
            </Button>
          </div>
          <div className="flex w-full flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <Link href="/collector/offline-queue" className="inline-flex items-center gap-1 font-medium text-foreground hover:underline">
              <History className="size-3.5" aria-hidden /> {t("collector.pending", { count: pending })}
            </Link>
            <span>{cachedAt ? t("collector.cachedAt", { time: relativeTime(cachedAt, locale) }) : t("collector.notCached")}</span>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-3">
        <Button size="xl" className="h-20 flex-col gap-1 text-base" onClick={() => setScanOpen(true)} disabled={!tasks}>
          <QrCode className="size-7" /> {t("collector.scan")}
        </Button>
        <Button size="xl" variant="outline" className="h-20 flex-col gap-1 text-base" onClick={() => setScanOpen(true)} disabled={!tasks}>
          <Keyboard className="size-7" /> {t("collector.enterCode")}
        </Button>
      </div>

      {lastSaved && (
        <Card className="gap-2 border-primary/40 py-4" aria-live="polite">
          <CardContent className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 size-6 shrink-0 text-primary" aria-hidden />
            <div className="min-w-0 flex-1">
              <p className="font-semibold">{t("collector.receiptTitle")}</p>
              <p className="truncate text-sm text-muted-foreground">
                {lastSaved.point_label} · {lastSaved.stream_label}
              </p>
              <p className="tabular text-sm">
                <span className="font-semibold">{formatKg(Number(lastSaved.payload.weight_kg), locale)}</span> ·{" "}
                {t("collector.receiptNo")} <span className="font-mono">PL-{lastSaved.event_id.slice(0, 8).toUpperCase()}</span> ·{" "}
                {formatDateTime(lastSaved.payload.collected_at, locale)}
              </p>
            </div>
            <StatusBadge value={lastSaved.status} />
          </CardContent>
        </Card>
      )}

      <section aria-labelledby="stops-title">
        <h2 id="stops-title" className="mb-3 flex items-center justify-between text-base font-semibold">
          {t("collector.todayStops")}
          {tasks && <span className="text-sm font-normal text-muted-foreground">{tasks.stops.length}</span>}
        </h2>
        {!tasks && remote.isLoading && (
          <div className="grid gap-3">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-24 w-full rounded-xl" />
            ))}
          </div>
        )}
        {!tasks && !remote.isLoading && (
          <EmptyState icon={CloudOff} title={t("collector.noCacheTitle")} description={t("collector.noCacheBody")} />
        )}
        {tasks && tasks.stops.length === 0 && <EmptyState title={t("collector.noStops")} description={t("collector.noStopsHint")} />}
        <ul className="grid gap-3">
          {tasks?.stops.map((stop) => (
            <li key={stop.point.id}>
              <button
                type="button"
                onClick={() => setSelected({ point: toFormPoint(stop.point), stop })}
                className="flex w-full items-center gap-3 rounded-xl border bg-card p-4 text-left shadow-[var(--shadow-card)] transition-colors hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <span
                  className={cn(
                    "grid size-11 shrink-0 place-items-center rounded-xl",
                    stop.due_reasons.includes("emergency") ? "bg-danger-soft text-danger-foreground" : "bg-secondary text-primary",
                  )}
                >
                  {stop.due_reasons.includes("emergency") ? <Siren className="size-5" /> : <QrCode className="size-5" />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{stop.point.name}</span>
                  <span className="block text-xs text-muted-foreground">
                    {stop.point.code} · {stop.point.village_name}
                  </span>
                  <span className="mt-1.5 flex flex-wrap gap-1">
                    {stop.due_reasons.map((r) => (
                      <Badge key={r} tone={reasonTone(r)}>
                        {t(`collector.reasons.${r}`)}
                      </Badge>
                    ))}
                  </span>
                  {stop.point.fill_percent !== null && (
                    <span className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                      <Progress
                        value={stop.point.fill_percent}
                        className="h-1.5 max-w-32"
                        indicatorClassName={stop.point.fill_percent >= 80 ? "bg-amber-500" : "bg-emerald-500"}
                      />
                      {t("collector.fill", { percent: Math.round(stop.point.fill_percent) })}
                    </span>
                  )}
                </span>
                <ChevronRight className="size-5 shrink-0 text-muted-foreground" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      </section>

      <QrScannerModal open={scanOpen} onOpenChange={setScanOpen} onResult={openPoint} />

      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className="max-h-[100dvh] max-w-lg sm:max-h-[92dvh]">
          <DialogTitle className="sr-only">{t("collector.form.title")}</DialogTitle>
          {selected && tasks && (
            <CollectionForm
              point={selected.point}
              streams={tasks.streams}
              context={{ assignment_id: selected.stop?.assignment_id, pickup_request_id: selected.stop?.pickup_request_ids[0] }}
              onSaved={(ev) => {
                setLastSavedId(typeof ev === "string" ? ev : ev.event_id);
                setSelected(null);
                toast.success(online ? t("collector.saved") : t("collector.savedOffline"));
              }}
              onCancel={() => setSelected(null)}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function CollectorPage() {
  return (
    <Suspense>
      <CollectorInner />
    </Suspense>
  );
}
