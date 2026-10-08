"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Pencil, RefreshCw, Trash2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { toast } from "sonner";
import { CollectionForm } from "@/components/collector/collection-form";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { EmptyState } from "@/components/common/empty-state";
import { useOnline } from "@/components/common/offline-indicator";
import { PageHeader } from "@/components/common/page-header";
import { StatusBadge } from "@/components/common/status-badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useT } from "@/i18n/i18n";
import { api, errorMessage } from "@/lib/api";
import { hasRole, useAuth } from "@/lib/auth-store";
import { type QueuedEvent, getCachedTasks } from "@/lib/offline/db";
import { useLiveQuery, useQueue } from "@/lib/offline/hooks";
import { acknowledgeConflict, discardQueued, syncNow } from "@/lib/offline/sync";
import type { CollectionEvent, SyncReceipt } from "@/lib/types";
import { formatDateTime, formatKg, relativeTime } from "@/lib/utils";

const GROUPS = {
  pending: ["draft", "queued", "syncing"],
  attention: ["failed", "conflict"],
  synced: ["synced"],
} as const;

function QueueItem({ ev, onEdit }: { ev: QueuedEvent; onEdit: (ev: QueuedEvent) => void }) {
  const { t, locale } = useT();
  return (
    <li className="rounded-xl border bg-card p-4 shadow-[var(--shadow-card)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate font-medium">{ev.point_label}</p>
          <p className="text-sm text-muted-foreground">
            {ev.stream_label} · <span className="tabular font-medium text-foreground">{formatKg(Number(ev.payload.weight_kg), locale)}</span>
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {formatDateTime(ev.payload.collected_at, locale)} · <span className="font-mono">PL-{ev.event_id.slice(0, 8).toUpperCase()}</span>
            {ev.replaces && ` · ${t("queue.corrected")}`}
          </p>
        </div>
        <StatusBadge value={ev.status} />
      </div>
      {ev.last_error && ev.status !== "synced" && (
        <p className={ev.status === "queued" ? "mt-2 text-xs text-muted-foreground" : "mt-2 text-sm text-danger-foreground"}>
          {ev.status === "queued"
            ? t("queue.retryAt", { time: relativeTime(ev.next_attempt_at, locale), attempts: ev.attempts })
            : t(`queue.reasons.${ev.last_error.code ?? "UNKNOWN"}`) === `queue.reasons.${ev.last_error.code ?? "UNKNOWN"}`
              ? ev.last_error.message
              : t(`queue.reasons.${ev.last_error.code}`)}
        </p>
      )}
      {ev.status === "synced" && ev.review_status === "flagged" && <p className="mt-2 text-xs text-warning-foreground">{t("queue.flagged")}</p>}
      {(ev.status === "draft" || ev.status === "failed" || ev.status === "conflict") && (
        <div className="mt-3 flex flex-wrap gap-2">
          {(ev.status === "draft" || ev.status === "failed") && (
            <>
              <Button size="sm" variant="outline" onClick={() => onEdit(ev)}>
                <Pencil /> {ev.status === "draft" ? t("queue.editDraft") : t("queue.correct")}
              </Button>
              <ConfirmDialog
                trigger={
                  <Button size="sm" variant="ghost" className="text-danger-foreground">
                    <Trash2 /> {t("queue.discard")}
                  </Button>
                }
                title={t("queue.discardTitle")}
                description={t("queue.discardBody")}
                destructive
                confirmLabel={t("queue.discard")}
                onConfirm={() => discardQueued(ev.event_id)}
              />
            </>
          )}
          {ev.status === "conflict" && (
            <Button size="sm" variant="outline" onClick={() => acknowledgeConflict(ev.event_id)}>
              {t("queue.acknowledge")}
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

function AdminConflicts() {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const conflicts = useQuery({
    queryKey: ["sync-conflicts"],
    queryFn: () => api<{ receipt: SyncReceipt; original: CollectionEvent }[]>("/sync/conflicts"),
  });
  const resolve = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "keep_original" | "apply_new" }) =>
      api(`/sync/conflicts/${id}/resolve`, { method: "POST", body: { action } }),
    onSuccess: () => {
      toast.success(t("queue.resolved"));
      qc.invalidateQueries({ queryKey: ["sync-conflicts"] });
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  if (!conflicts.data?.length) return null;
  return (
    <Card className="mt-6">
      <CardHeader>
        <div>
          <CardTitle>{t("queue.adminTitle")}</CardTitle>
          <CardDescription>{t("queue.adminHint")}</CardDescription>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3">
        {conflicts.data.map(({ receipt, original }) => (
          <div key={receipt.event_id} className="rounded-lg border p-3 text-sm">
            <p className="font-medium">
              {original.collection_point_code} · {original.collector_name}
            </p>
            <p className="text-muted-foreground">
              {t("queue.original")}: {formatKg(original.weight_kg, locale)} · {t("queue.newer")}:{" "}
              {formatKg(Number(receipt.conflict_payload?.weight_kg ?? 0), locale)} ({t("queue.seen", { count: receipt.conflict_count })})
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => resolve.mutate({ id: receipt.event_id, action: "keep_original" })} disabled={resolve.isPending}>
                {t("queue.keepOriginal")}
              </Button>
              <Button size="sm" onClick={() => resolve.mutate({ id: receipt.event_id, action: "apply_new" })} disabled={resolve.isPending}>
                {t("queue.applyNewer")}
              </Button>
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function QueueInner() {
  const { t } = useT();
  const user = useAuth((s) => s.user);
  const status = useAuth((s) => s.status);
  const online = useOnline();
  const params = useSearchParams();
  const events = useQueue();
  const [editing, setEditing] = useState<QueuedEvent | null>(null);
  const [syncing, setSyncing] = useState(false);
  const tasks = useLiveQuery(() => (user ? getCachedTasks(user.id) : Promise.resolve(undefined)), [user?.id], undefined);
  const groups = useMemo(
    () => Object.fromEntries(Object.entries(GROUPS).map(([k, statuses]) => [k, events.filter((e) => (statuses as readonly string[]).includes(e.status))])),
    [events],
  ) as Record<keyof typeof GROUPS, QueuedEvent[]>;
  const editPoint = editing ? tasks?.data.points.find((p) => p.id === editing.payload.collection_point_id) : undefined;

  const runSync = async () => {
    if (!user) return;
    setSyncing(true);
    try {
      const s = await syncNow(user.id, { force: true });
      toast.message(s.offline ? t("collector.syncOffline") : t("collector.syncDone", { synced: s.synced, failed: s.failed + s.conflicts }));
    } finally {
      setSyncing(false);
    }
  };

  const tab = params.get("tab") === "conflicts" ? "attention" : "pending";
  return (
    <>
      <PageHeader
        title={t("queue.title")}
        description={t("queue.subtitle")}
        actions={
          <Button onClick={runSync} disabled={syncing || !online || status !== "authenticated"}>
            <RefreshCw className={syncing ? "animate-spin" : undefined} /> {t("collector.syncNow")}
          </Button>
        }
      />
      <Alert tone="info" className="mb-5">
        <AlertDescription>{t("queue.explainer")}</AlertDescription>
      </Alert>
      <Tabs defaultValue={tab}>
        <TabsList>
          <TabsTrigger value="pending">
            {t("queue.tabs.pending")} ({groups.pending.length})
          </TabsTrigger>
          <TabsTrigger value="attention">
            {groups.attention.length > 0 && <AlertTriangle className="text-warning" />}
            {t("queue.tabs.attention")} ({groups.attention.length})
          </TabsTrigger>
          <TabsTrigger value="synced">
            {t("queue.tabs.synced")} ({groups.synced.length})
          </TabsTrigger>
        </TabsList>
        {(Object.keys(GROUPS) as (keyof typeof GROUPS)[]).map((k) => (
          <TabsContent key={k} value={k}>
            {groups[k].length === 0 ? (
              <EmptyState title={t(`queue.empty.${k}`)} />
            ) : (
              <ul className="grid gap-3">
                {groups[k].map((ev) => (
                  <QueueItem key={ev.event_id} ev={ev} onEdit={setEditing} />
                ))}
              </ul>
            )}
          </TabsContent>
        ))}
      </Tabs>
      {hasRole(user, "gp_admin") && status === "authenticated" && <AdminConflicts />}

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent className="max-w-lg">
          <DialogTitle>{t("queue.editTitle")}</DialogTitle>
          {editing && tasks && editPoint ? (
            <CollectionForm
              point={{ id: editPoint.id, code: editPoint.code, name: editPoint.name, stream_ids: editPoint.stream_ids, device_id: editPoint.device_id }}
              streams={tasks.data.streams}
              editing={editing}
              onSaved={() => {
                setEditing(null);
                toast.success(t("common.saved"));
              }}
              onCancel={() => setEditing(null)}
            />
          ) : (
            <p className="text-sm text-muted-foreground">{t("queue.pointNotCached")}</p>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function OfflineQueuePage() {
  return (
    <Suspense>
      <QueueInner />
    </Suspense>
  );
}
