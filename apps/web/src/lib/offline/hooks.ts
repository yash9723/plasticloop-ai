"use client";

import { liveQuery } from "dexie";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { useT } from "@/i18n/i18n";
import { useAuth } from "@/lib/auth-store";
import { type QueuedEvent, countPending, getDb } from "./db";
import { syncNow } from "./sync";

/** Subscribes to an IndexedDB query and re-renders whenever the underlying tables change. */
export function useLiveQuery<T>(query: () => Promise<T>, deps: unknown[], initial: T): T {
  const [value, setValue] = useState<T>(initial);
  useEffect(() => {
    const sub = liveQuery(query).subscribe({ next: setValue, error: (e) => console.warn("liveQuery", e) });
    return () => sub.unsubscribe();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return value;
}

export function usePendingCount(): number {
  const userId = useAuth((s) => s.user?.id);
  return useLiveQuery(() => (userId ? countPending(userId) : Promise.resolve(0)), [userId], 0);
}

export function useQueue(): QueuedEvent[] {
  const userId = useAuth((s) => s.user?.id);
  return useLiveQuery(
    async () => (userId ? (await getDb().events.where("user_id").equals(userId).toArray()).sort((a, b) => b.created_at - a.created_at) : []),
    [userId],
    [] as QueuedEvent[],
  );
}

/** Foreground sync: on start, when the network returns, and every 30 s while the app is open. */
export function useAutoSync() {
  const userId = useAuth((s) => s.user?.id);
  const status = useAuth((s) => s.status);
  const { t } = useT();
  useEffect(() => {
    if (!userId || status !== "authenticated") return;
    const run = (force = false) =>
      syncNow(userId, { force })
        .then((s) => {
          if (s.synced) toast.success(t("offline.syncedCount", { count: s.synced }));
          if (s.failed || s.conflicts) toast.warning(t("offline.needsAttention", { count: s.failed + s.conflicts }));
        })
        .catch(() => {});
    run();
    const onOnline = () => run(true);
    window.addEventListener("online", onOnline);
    const timer = window.setInterval(() => navigator.onLine && run(), 30_000);
    return () => {
      window.removeEventListener("online", onOnline);
      window.clearInterval(timer);
    };
  }, [userId, status, t]);
}
