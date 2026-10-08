"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useT } from "@/i18n/i18n";
import { api, type Page } from "@/lib/api";
import { useAuth } from "@/lib/auth-store";
import type { NotificationItem } from "@/lib/types";
import { cn, relativeTime } from "@/lib/utils";

const dot = { info: "bg-sky-500", warning: "bg-amber-500", critical: "bg-red-600" } as const;

export function NotificationBell() {
  const { t, locale } = useT();
  const qc = useQueryClient();
  const authed = useAuth((s) => s.status === "authenticated");
  const [open, setOpen] = useState(false);

  const count = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => api<{ unread: number }>("/notifications/unread-count"),
    enabled: authed,
    refetchInterval: 60_000,
  });
  const latest = useQuery({
    queryKey: ["notifications", "latest"],
    queryFn: () => api<Page<NotificationItem>>("/notifications", { query: { page_size: 6 } }),
    enabled: authed && open,
  });
  const readAll = useMutation({
    mutationFn: () => api("/notifications/read-all", { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unread = count.data?.unread ?? 0;
  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={t("notifications.title", { count: unread })}>
          <Bell />
          {unread > 0 && (
            <span className="absolute right-1.5 top-1.5 grid min-w-4 place-items-center rounded-full bg-red-600 px-1 text-[10px] font-semibold leading-4 text-white">
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-[min(22rem,calc(100vw-1.5rem))] p-0">
        <div className="flex items-center justify-between px-3 py-2.5">
          <p className="text-sm font-semibold">{t("nav.items.notifications")}</p>
          <Button variant="ghost" size="sm" disabled={!unread || readAll.isPending} onClick={() => readAll.mutate()}>
            <CheckCheck /> {t("notifications.markAllRead")}
          </Button>
        </div>
        <DropdownMenuSeparator className="m-0" />
        <div className="max-h-80 overflow-y-auto p-1">
          {latest.data?.items.length === 0 && <p className="px-3 py-6 text-center text-sm text-muted-foreground">{t("notifications.empty")}</p>}
          {latest.data?.items.map((n) => (
            <DropdownMenuItem key={n.id} asChild className="items-start">
              <Link href={n.link ?? "/notifications"}>
                <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read_at ? "bg-transparent" : dot[n.severity])} aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className={cn("block truncate text-sm", !n.read_at && "font-medium")}>{n.title}</span>
                  {n.body && <span className="line-clamp-2 block text-xs text-muted-foreground">{n.body}</span>}
                  <span className="block text-[11px] text-muted-foreground">{relativeTime(n.created_at, locale)}</span>
                </span>
              </Link>
            </DropdownMenuItem>
          ))}
        </div>
        <DropdownMenuSeparator className="m-0" />
        <DropdownMenuItem asChild className="justify-center rounded-none py-2.5 text-primary">
          <Link href="/notifications">{t("common.viewAll")}</Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
