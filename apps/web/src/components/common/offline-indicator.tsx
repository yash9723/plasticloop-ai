"use client";

import { CloudOff, RefreshCw } from "lucide-react";
import { useSyncExternalStore } from "react";
import { useT } from "@/i18n/i18n";
import { cn } from "@/lib/utils";

function subscribe(cb: () => void) {
  window.addEventListener("online", cb);
  window.addEventListener("offline", cb);
  return () => {
    window.removeEventListener("online", cb);
    window.removeEventListener("offline", cb);
  };
}

/** navigator.onLine only detects "no network interface"; API calls still treat failures as offline. */
export function useOnline(): boolean {
  return useSyncExternalStore(subscribe, () => navigator.onLine, () => true);
}

export function OfflineIndicator({ pending = 0, className }: { pending?: number; className?: string }) {
  const online = useOnline();
  const { t } = useT();
  if (online && pending === 0) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium",
        online ? "bg-info-soft text-info-foreground" : "bg-warning-soft text-warning-foreground",
        className,
      )}
    >
      {online ? <RefreshCw className="size-3.5" aria-hidden /> : <CloudOff className="size-3.5" aria-hidden />}
      {online ? t("offline.pendingCount", { count: pending }) : t("offline.badge")}
      {!online && pending > 0 && <span className="tabular">· {pending}</span>}
    </div>
  );
}
